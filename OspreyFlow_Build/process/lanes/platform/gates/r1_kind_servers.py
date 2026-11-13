"""Two stand-ins R1's kind cluster runs for what the client's platform gives and kind has not
(r1_kind.py). The standard library, and the api image's own pyjwt and cryptography for the tenant's
signing, so they run in our own api image; nothing here is the product.

    entra    login.microsoftonline.com for one tenant (v0.5.2, step 8: it signs): its v2.0 discovery
             document and signing keys, `/authorize` (one person, signed in at once: no form) and
             `/token` (authorization_code, with PKCE or a client secret; client_credentials). It
             signs with a key it makes at start and never writes out, published beside r1_kind.py's
             own (kept for the refusals the driver crafts). It refuses what Entra refuses on those
             paths, with Entra's error and AADSTS code: another tenant (90002), an unknown client
             (700016), a redirect URI not registered (50011, shown, never redirected to), a scope
             the client was not granted, so no scp (65001), a missing or wrong secret (7000218,
             7000215), a code expired, used, or another client's or redirect's (70008, 70000), a
             PKCE verifier that does not match (50148), a client-credentials scope not
             `<resource>/.default` (1002012) or of another resource (500011), any other grant
             (70003). `tests/test_r1_entra_standin.py` holds each.
    webhook  a mutating admission webhook standing in for EKS's pod identity webhook and the trust a
             real S3, STS and Entra need no help with. To every pod created in the deployment's
             namespace: the stand-in CA beside the public roots, as the system's bundle and by the
             variables Python, curl and the AWS SDKs read. To a pod whose service account the
             platform's Terraform annotates with a role: what EKS's webhook adds (the projected token
             for sts.amazonaws.com, AWS_ROLE_ARN, AWS_WEB_IDENTITY_TOKEN_FILE, the region and
             AWS_STS_REGIONAL_ENDPOINTS) and nothing more: no endpoint URL, which EKS never sets, so
             each SDK asks the regional names CoreDNS gives the stand-in (R1: pyarrow's AWS CRT read
             AWS_ENDPOINT_URL_STS as a host name and fell back to no credentials). Nothing else is
             changed.

    python3 -I r1_kind_servers.py entra|webhook --config c.json --port 443 --tls-cert c --tls-key k
"""

# ruff: noqa: E501 - stand-ins, their lines as read.
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import secrets
import ssl
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

TOKEN_DIR = "/var/run/secrets/eks.amazonaws.com/serviceaccount"
TRUST_DIR = "/etc/r1-trust"
BUNDLE = f"{TRUST_DIR}/ca-bundle.crt"


#: The fields Entra's error answers carry, beside `error` and `error_description`.
GRAPH = "00000003-0000-0000-c000-000000000000"
CODE_SECONDS = 600
TOKEN_SECONDS = 3600


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _throwaway_key() -> tuple[Any, dict[str, Any]]:
    """The stand-in tenant's signing key, made at start and held in memory alone (never written out,
    so no run's key outlives it), and its public half as Entra publishes one."""
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()
    n = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    kid = _b64(hashlib.sha256(n).digest())[:27]
    jwk = {"kty": "RSA", "use": "sig", "alg": "RS256", "kid": kid, "x5t": kid,
           "n": _b64(n), "e": _b64(numbers.e.to_bytes(3, "big"))}  # fmt: skip
    return key, jwk


def entra_handler(config: dict[str, Any]) -> type[BaseHTTPRequestHandler]:
    """Entra ID v2.0 for one tenant: discovery, keys, `/authorize` (one person, signed in at once) and
    `/token` (authorization_code, with or without PKCE and a secret; client_credentials), refusing
    what Entra refuses on those paths with its own error and AADSTS code. `config` is read at each
    request (`clients`, `user`, `api`), so a test may change it while the server runs."""
    import jwt

    tenant = config["tenant_id"]
    issuer = f"https://login.microsoftonline.com/{tenant}/v2.0"
    key, own = _throwaway_key()
    keys = {"keys": [own, *config.get("jwks", [])]}
    discovery = {
        "issuer": issuer,
        "jwks_uri": f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
        "authorization_endpoint": f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
        "token_endpoint": f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "client_credentials"],
        "code_challenge_methods_supported": ["S256", "plain"],
        "subject_types_supported": ["pairwise"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
    }
    codes: dict[str, dict[str, Any]] = {}
    lock = threading.Lock()

    def sign(claims: dict[str, Any]) -> str:
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": own["kid"], "x5t": own["kid"]})

    def pairwise(app: str, oid: str) -> str:
        """Entra's `sub`: the person, as one application sees them."""
        return _b64(hashlib.sha256(f"{app}:{oid}".encode()).digest())[:43]

    def api_names() -> set[str]:
        api = config["api"]
        return {api["app_id"], api.get("identifier", f"api://{api['app_id']}")}

    def split_scopes(scope: str) -> tuple[list[str], list[str], list[str]]:
        """`(openid scopes, the API's delegated scopes asked, other resources' scopes)`."""
        oidc, api, other = [], [], []
        for item in scope.split():
            if item in ("openid", "profile", "email", "offline_access"):
                oidc.append(item)
                continue
            resource, _, name = item.rpartition("/")
            (api if resource in api_names() else other).append(name if resource in api_names() else item)
        return oidc, api, other

    class Handler(BaseHTTPRequestHandler):
        keys_document = keys

        def _send(self, status: int, body: dict[str, Any], headers: dict[str, str] | None = None) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _error(self, status: int, error: str, code: int, words: str) -> None:
            self._send(status, {
                "error": error, "error_description": f"AADSTS{code}: {words}",
                "error_codes": [code], "timestamp": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()),
                "trace_id": secrets.token_hex(16), "correlation_id": secrets.token_hex(16),
            })  # fmt: skip

        def _page(self, code: int, words: str) -> None:
            """A refusal Entra shows on its own page, never sent to the client's redirect URI."""
            data = f"<html><body><h1>Sign in</h1><p>AADSTS{code}: {words}</p></body></html>".encode()
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _redirect(self, uri: str, params: dict[str, str]) -> None:
            self.send_response(302)
            self.send_header("Location", f"{uri}{'&' if '?' in uri else '?'}{urllib.parse.urlencode(params)}")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _tenant(self, path: str) -> bool:
            parts = path.strip("/").split("/")
            if parts and parts[0] not in (tenant, "") and len(parts) > 1:
                words = f"Tenant '{parts[0]}' not found. Check to make sure you have the correct tenant ID."
                if self.command == "GET" and path.endswith("/authorize"):
                    self._page(90002, words)
                else:
                    self._error(400, "invalid_tenant", 90002, words)
                return False
            return True

        def do_GET(self) -> None:  # noqa: N802 - http.server's name
            path, _, query = self.path.partition("?")
            if not self._tenant(path):
                return
            if path == f"/{tenant}/v2.0/.well-known/openid-configuration":
                self._send(200, discovery)
            elif path == f"/{tenant}/discovery/v2.0/keys":
                self._send(200, keys)
            elif path == f"/{tenant}/oauth2/v2.0/authorize":
                self._authorize(dict(urllib.parse.parse_qsl(query)))
            else:
                self._send(404, {"error": "not_found"})

        def _authorize(self, q: dict[str, str]) -> None:
            client = config["clients"].get(q.get("client_id", ""))
            if client is None:
                self._page(700016, f"Application with identifier '{q.get('client_id')}' was not found "
                           f"in the directory '{tenant}'.")  # fmt: skip
                return
            redirect = q.get("redirect_uri", "")
            if redirect not in client.get("redirect_uris", []):
                self._page(50011, f"The redirect URI '{redirect}' specified in the request does not "
                           f"match the redirect URIs configured for the application '{q['client_id']}'.")  # fmt: skip
                return
            state = {"state": q["state"]} if "state" in q else {}
            if q.get("response_type") != "code":
                self._redirect(redirect, {"error": "unsupported_response_type", **state,
                                          "error_description": "AADSTS700054: response_type is not enabled for the application."})  # fmt: skip
                return
            _oidc, asked, other = split_scopes(q.get("scope", ""))
            if other:
                self._redirect(redirect, {"error": "invalid_resource", **state, "error_description":
                                          f"AADSTS500011: The resource principal named {other[0]} was not found in the tenant."})  # fmt: skip
                return
            ungranted = [s for s in asked if s not in client.get("delegated", [])]
            if ungranted:
                self._redirect(redirect, {"error": "consent_required", **state, "error_description":
                                          f"AADSTS65001: The user or administrator has not consented to use the application with ID '{q['client_id']}' for {', '.join(ungranted)}."})  # fmt: skip
                return
            code = secrets.token_urlsafe(48)
            with lock:
                codes[code] = {"client": q["client_id"], "redirect": redirect, "scope": q.get("scope", ""),
                               "challenge": q.get("code_challenge"), "method": q.get("code_challenge_method", "plain"),
                               "nonce": q.get("nonce"), "expires": time.time() + CODE_SECONDS}  # fmt: skip
            self._redirect(redirect, {"code": code, **state, "session_state": secrets.token_hex(16)})

        def do_POST(self) -> None:
            path = self.path.partition("?")[0]
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode()
            if not self._tenant(path):
                return
            if path != f"/{tenant}/oauth2/v2.0/token":
                self._send(404, {"error": "not_found"})
                return
            form = dict(urllib.parse.parse_qsl(body))
            basic = self.headers.get("Authorization", "")
            if basic.startswith("Basic "):
                user, _, password = base64.b64decode(basic[6:]).decode().partition(":")
                form.setdefault("client_id", urllib.parse.unquote(user))
                form.setdefault("client_secret", urllib.parse.unquote(password))
            grant = form.get("grant_type")
            if grant not in ("authorization_code", "client_credentials"):
                self._error(400, "unsupported_grant_type", 70003, "The app requested an unsupported grant type.")
                return
            client_id = form.get("client_id", "")
            client = config["clients"].get(client_id)
            if client is None:
                self._error(400, "invalid_client", 700016, f"Application with identifier '{client_id}' "
                            f"was not found in the directory '{tenant}'.")  # fmt: skip
                return
            secret = client.get("secret")
            given = form.get("client_secret") or None
            if (secret is not None or grant == "client_credentials") and given is None:
                self._error(401, "invalid_client", 7000218, "The request body must contain the following "
                            "parameter: 'client_assertion' or 'client_secret'.")  # fmt: skip
                return
            if given is not None and (secret is None or not hmac.compare_digest(given, secret)):
                self._error(401, "invalid_client", 7000215, "Invalid client secret provided. Ensure the "
                            f"secret being sent in the request is the client secret value for app '{client_id}'.")  # fmt: skip
                return
            if grant == "client_credentials":
                self._client_credentials(client_id, client, form)
            else:
                self._authorization_code(client_id, form)

        def _client_credentials(self, client_id: str, client: dict[str, Any], form: dict[str, str]) -> None:
            scope = form.get("scope", "")
            resource, _, name = scope.rpartition("/")
            if len(scope.split()) != 1 or name != ".default":
                self._error(400, "invalid_scope", 1002012, f"The provided value for scope {scope} is not "
                            "valid. Client credential flows must have a scope value with /.default suffixed "
                            "to the resource identifier.")  # fmt: skip
                return
            if resource not in api_names():
                self._error(400, "invalid_resource", 500011, f"The resource principal named {resource} was "
                            f"not found in the tenant named {tenant}.")  # fmt: skip
                return
            now = int(time.time())
            principal = client.get("service_principal") or client_id
            claims: dict[str, Any] = {
                "aud": config["api"]["app_id"], "iss": issuer, "iat": now, "nbf": now,
                "exp": now + TOKEN_SECONDS, "ver": "2.0", "tid": tenant, "oid": principal, "sub": principal,
                "azp": client_id, "azpacr": "1", "idtyp": "app", "uti": secrets.token_urlsafe(16),
            }  # fmt: skip
            if client.get("roles"):
                claims["roles"] = list(client["roles"])
            self._send(200, {"token_type": "Bearer", "expires_in": TOKEN_SECONDS,
                             "ext_expires_in": TOKEN_SECONDS, "access_token": sign(claims)})  # fmt: skip

        def _authorization_code(self, client_id: str, form: dict[str, str]) -> None:
            with lock:
                held = codes.get(form.get("code", ""))
                if held is None or held["expires"] < time.time():
                    codes.pop(form.get("code", ""), None)
                    self._error(400, "invalid_grant", 70008, "The provided authorization code or refresh "
                                "token has expired due to inactivity, or was already redeemed.")  # fmt: skip
                    return
                if held["client"] != client_id or held["redirect"] != form.get("redirect_uri"):
                    self._error(400, "invalid_grant", 70000, "The provided value for the 'code' parameter "
                                "is not valid for this client or redirect URI.")  # fmt: skip
                    return
                if held["challenge"]:
                    verifier = form.get("code_verifier", "")
                    made = verifier if held["method"] == "plain" else _b64(hashlib.sha256(verifier.encode()).digest())
                    if not hmac.compare_digest(made, held["challenge"]):
                        self._error(400, "invalid_grant", 50148, "The code_verifier does not match the "
                                    "code_challenge supplied in the authorization request.")  # fmt: skip
                        return
                del codes[form["code"]]  # spent, once it is redeemed by its own client
            person = config["user"]
            oidc, asked, _ = split_scopes(held["scope"])
            now = int(time.time())
            base = {"iss": issuer, "iat": now, "nbf": now, "exp": now + TOKEN_SECONDS, "ver": "2.0",
                    "tid": tenant, "oid": person["oid"], "name": person["name"],
                    "preferred_username": person["preferred_username"], "uti": secrets.token_urlsafe(16)}  # fmt: skip
            if asked:
                audience = config["api"]["app_id"]
                access = {**base, "aud": audience, "sub": pairwise(audience, person["oid"]),
                          "azp": client_id, "azpacr": "1" if config["clients"][client_id].get("secret") else "0",
                          "scp": " ".join(asked), **person.get("claims", {})}  # fmt: skip
            else:  # only sign-in scopes: a token for Microsoft Graph, as Entra gives
                access = {**base, "aud": GRAPH, "sub": pairwise(GRAPH, person["oid"]), "azp": client_id,
                          "scp": " ".join(s for s in oidc if s != "openid") or "User.Read"}  # fmt: skip
            answer: dict[str, Any] = {
                "token_type": "Bearer", "expires_in": TOKEN_SECONDS, "ext_expires_in": TOKEN_SECONDS,
                "scope": " ".join([*(f"api://{config['api']['app_id']}/{s}" for s in asked), *oidc]),
                "access_token": sign(access),
            }
            if "openid" in oidc:
                identity = {**base, "aud": client_id, "sub": pairwise(client_id, person["oid"])}
                if held["nonce"]:
                    identity["nonce"] = held["nonce"]
                answer["id_token"] = sign(identity)
            self._send(200, answer)

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
        def do_POST(self) -> None:
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


def make_server(mode: str, config: dict[str, Any], host: str, port: int, tls_cert: str | None = None,
                tls_key: str | None = None) -> ThreadingHTTPServer:
    """The stand-in, bound: over TLS as the cluster serves it, or plain on loopback for its tests."""
    handler = entra_handler(config) if mode == "entra" else webhook_handler(config)
    server = ThreadingHTTPServer((host, port), handler)
    if tls_cert and tls_key:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(tls_cert, tls_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    return server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["entra", "webhook"])
    parser.add_argument("--config", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--tls-cert", required=True)
    parser.add_argument("--tls-key", required=True)
    args = parser.parse_args()
    config = json.load(open(args.config))
    server = make_server(args.mode, config, "0.0.0.0", args.port, args.tls_cert, args.tls_key)
    sys.stderr.write(f"{args.mode} stand-in on {args.port}\n")
    server.serve_forever()


if __name__ == "__main__":
    main()
