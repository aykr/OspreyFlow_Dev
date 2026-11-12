"""Two stand-ins R1's kind cluster runs for what the client's platform gives and kind has not
(r1_kind.py). Standard library only, so they run in our own api image; nothing here is the product.

    entra    login.microsoftonline.com for one tenant: its v2.0 discovery document and signing keys,
             as Entra serves them. It refuses what Entra refuses on those paths: another tenant
             (AADSTS90002, 400) and any other path (404). It never signs anything: r1_kind.py mints
             the tokens with the private key, which never enters the cluster.
    webhook  a mutating admission webhook standing in for EKS's pod identity webhook and the trust a
             real S3, STS and Entra need no help with. To every pod created in the deployment's
             namespace: the stand-in CA beside the public roots, as the system's bundle and by the
             variables Python, curl and the AWS SDKs read. To a pod whose service account the
             platform's Terraform annotates with a role: what EKS's webhook adds (the projected token
             for sts.amazonaws.com, AWS_ROLE_ARN, AWS_WEB_IDENTITY_TOKEN_FILE, the region) and the
             S3 and STS endpoints at the stand-in. Nothing else is changed.

    python3 -I r1_kind_servers.py entra|webhook --config c.json --port 443 --tls-cert c --tls-key k
"""

# ruff: noqa: E501 - stand-ins, their lines as read.
from __future__ import annotations

import argparse
import base64
import json
import ssl
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

TOKEN_DIR = "/var/run/secrets/eks.amazonaws.com/serviceaccount"
TRUST_DIR = "/etc/r1-trust"
BUNDLE = f"{TRUST_DIR}/ca-bundle.crt"


def entra_handler(config: dict[str, Any]) -> type[BaseHTTPRequestHandler]:
    tenant = config["tenant_id"]
    issuer = f"https://login.microsoftonline.com/{tenant}/v2.0"
    keys = {"keys": config["jwks"]}
    discovery = {
        "issuer": issuer,
        "jwks_uri": f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
        "authorization_endpoint": f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
        "token_endpoint": f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        "id_token_signing_alg_values_supported": ["RS256"],
    }

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802 - http.server's name
            path = self.path.split("?", 1)[0]
            parts = path.strip("/").split("/")
            if parts and parts[0] not in (tenant, "") and len(parts) > 1:
                self._send(400, {"error": "invalid_tenant", "error_codes": [90002],
                                 "error_description": f"AADSTS90002: Tenant '{parts[0]}' not found."})  # fmt: skip
            elif path == f"/{tenant}/v2.0/.well-known/openid-configuration":
                self._send(200, discovery)
            elif path == f"/{tenant}/discovery/v2.0/keys":
                self._send(200, keys)
            else:
                self._send(404, {"error": "not_found"})

        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("entra-standin: " + (fmt % args) + "\n")

    return Handler


def _patch_pod(pod: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    """The JSON patch for one pod: the trust for every container, and IRSA's additions for a pod
    of an annotated service account."""
    spec = pod["spec"]
    ops: list[dict[str, Any]] = []
    volumes = [{"name": "r1-trust", "configMap": {"name": config["trust_configmap"]}}]
    env = [
        {"name": "SSL_CERT_FILE", "value": BUNDLE},
        {"name": "REQUESTS_CA_BUNDLE", "value": BUNDLE},
        {"name": "CURL_CA_BUNDLE", "value": BUNDLE},
        {"name": "AWS_CA_BUNDLE", "value": BUNDLE},
    ]
    mounts = [
        {"name": "r1-trust", "mountPath": TRUST_DIR, "readOnly": True},
        # The system's bundle too (ClickHouse's openSSL and Arrow's curl read it by its path).
        {"name": "r1-trust", "mountPath": "/etc/ssl/certs/ca-certificates.crt",
         "subPath": "ca-bundle.crt", "readOnly": True},
    ]  # fmt: skip
    role = config["roles"].get(spec.get("serviceAccountName") or spec.get("serviceAccount") or "")
    if role:
        volumes.append({"name": "aws-iam-token", "projected": {"sources": [{"serviceAccountToken": {
            "audience": "sts.amazonaws.com", "expirationSeconds": 86400, "path": "token"}}]}})  # fmt: skip
        env += [
            {"name": "AWS_ROLE_ARN", "value": role},
            {"name": "AWS_WEB_IDENTITY_TOKEN_FILE", "value": f"{TOKEN_DIR}/token"},
            {"name": "AWS_STS_REGIONAL_ENDPOINTS", "value": "regional"},
            {"name": "AWS_REGION", "value": config["region"]},
            {"name": "AWS_DEFAULT_REGION", "value": config["region"]},
            {"name": "AWS_ENDPOINT_URL_S3", "value": config["endpoint"]},
            {"name": "AWS_ENDPOINT_URL_STS", "value": config["endpoint"]},
        ]
        mounts.append({"name": "aws-iam-token", "mountPath": TOKEN_DIR, "readOnly": True})
    if "volumes" not in spec:
        ops.append({"op": "add", "path": "/spec/volumes", "value": volumes})
    else:
        ops += [{"op": "add", "path": "/spec/volumes/-", "value": v} for v in volumes]
    for kind in ("initContainers", "containers"):
        for i, container in enumerate(spec.get(kind, [])):
            base = f"/spec/{kind}/{i}"
            have = {e["name"] for e in container.get("env", [])}
            add = [e for e in env if e["name"] not in have]  # never overrides the pod's own
            if "env" not in container:
                ops.append({"op": "add", "path": f"{base}/env", "value": add})
            else:
                ops += [{"op": "add", "path": f"{base}/env/-", "value": e} for e in add]
            if "volumeMounts" not in container:
                ops.append({"op": "add", "path": f"{base}/volumeMounts", "value": mounts})
            else:
                ops += [{"op": "add", "path": f"{base}/volumeMounts/-", "value": m} for m in mounts]
    return ops


def webhook_handler(config: dict[str, Any]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            review = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            request = review["request"]
            response: dict[str, Any] = {"uid": request["uid"], "allowed": True}
            obj = request.get("object") or {}
            if request.get("kind", {}).get("kind") == "Pod" and request.get("operation") == "CREATE":
                patch = _patch_pod(obj, config)
                response["patchType"] = "JSONPatch"
                response["patch"] = base64.b64encode(json.dumps(patch).encode()).decode()
                name = obj.get("metadata", {}).get("generateName") or obj.get("metadata", {}).get("name")
                sys.stderr.write(f"webhook: {name}: {len(patch)} patch operations\n")
            body = json.dumps({"apiVersion": "admission.k8s.io/v1", "kind": "AdmissionReview",
                               "response": response}).encode()  # fmt: skip
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: Any) -> None:
            pass

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["entra", "webhook"])
    parser.add_argument("--config", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--tls-cert", required=True)
    parser.add_argument("--tls-key", required=True)
    args = parser.parse_args()
    config = json.load(open(args.config))
    handler = entra_handler(config) if args.mode == "entra" else webhook_handler(config)
    server = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(args.tls_cert, args.tls_key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    sys.stderr.write(f"{args.mode} stand-in on {args.port}\n")
    server.serve_forever()


if __name__ == "__main__":
    main()
