"""R1's driver on the kind cluster (r1_kind.sh): the client install's acceptance
(process/lanes/platform/BRIEF.md). Run from OspreyFlow_Core, through `r1_kind.sh py <command>`.

    platform           the client's platform as it stands before the install, by stand-ins: the
                       managed stores (RDS, ElastiCache), S3 with STS and KMS, Entra ID, EKS's IRSA
                       webhook, the names they answer by, the ingress certificate, the namespace
    runbook INSTALL|DECOMMISSION [--from N]
                       the rendered runbook's blocks, **as written**, in order, in one bash shell,
                       stopped at the first failure: every `bash` block verbatim, and in place of each
                       `bash platform` block the stand-in for what the platform team would have done
                       (`stand_in`, below), said so in the record
    check              the check list (CHECKS.md): sign-in, a case, a load, a rule
    backup | restore   the recovery runbook's cloud-platform section (deploy/RUNBOOK.md), its blocks
                       with the placeholders filled as an operator fills them
    memory             the node's memory and every pod's actual use, from the kubelet

Every run writes its record under ~/osprey-runs/platform.r1/records/: each block as run and its
output. Nothing here is the product: the product is the render, the chart, the runbooks and the
images. What this file adds is what the client's platform gives and kind has not, and the checks.
"""

# ruff: noqa: E501, S603, S607 - a driver of shell commands, its lines as the operator reads them.
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from collections.abc import Callable
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
CORE = HERE.parents[4] / "OspreyFlow_Core"
BUILD = HERE.parents[3]
CONFIG = HERE / "r1_kind_osprey.yaml"
SERVERS = HERE / "r1_kind_servers.py"
STANDIN_CODE = BUILD / "tests" / "fixtures" / "cloud_platform" / "s3_standin.py"
STATE = Path.home() / "osprey-runs" / "platform.r1"
RECORDS = STATE / "records"
NS = "ospreyflow-poc"
FOLDER = CORE / "deploy" / "generated" / "cloud-platform"
#: The render the install used, kept outside the copy: each sync to the server prunes what git does not track,
#: the render folder with it, where a platform team keeps theirs for the restore and the decommission.
KEPT = STATE / "render"
MANAGED = "platform-managed"
LOCAL_BIN = Path.home() / ".local" / "bin"  # where `uv tool install` puts a command
ACCOUNT = "123456789012"
REGION = "eu-west-2"
KEY_ARN = f"arn:aws:kms:{REGION}:{ACCOUNT}:key/0f9e8d7c-0011-4000-8000-000000000001"
GLASS = "ospreyflow.r1.test"
PASSWORD = "throwaway-r1"
#: The namespace's OpenSearch domain's endpoint as AWS names one inside a VPC (`vpc-<domain>-<id>.<region>.es.amazonaws.com`;
#: the domain is `<namespace>-search`, opensearch.tf): the S3/STS stand-in answers as it (ADR-148 Amendment 13).
SEARCH_HOST = f"vpc-{NS}-search-r1standin.{REGION}.es.amazonaws.com"
#: The names the platform's services answer by, inside the cluster, at their stand-ins (CoreDNS).
NAMES = {
    "login.microsoftonline.com": "entra-standin",
    f"s3.{REGION}.amazonaws.com": "s3-standin",
    f"sts.{REGION}.amazonaws.com": "s3-standin",
    SEARCH_HOST: "s3-standin",  # checked there as the domain, then proxied to the OpenSearch pod
}
#: The engine behind the domain's stand-in, the poc manifest's OpenSearch_2.17 (one tag, kept here alone).
OPENSEARCH_IMAGE = "opensearchproject/opensearch:2.17.1"
THIRD_PARTY = {  # the managed stores' stand-ins' images, through AWS's mirror of Docker Hub's (no pull limit): Valkey is its own publisher there, not under docker/library
    "postgres:16.4": "public.ecr.aws/docker/library/postgres:16.4",
    "valkey/valkey:8.0": "public.ecr.aws/valkey/valkey:8.0",
    # The engine behind the domain's stand-in: the poc manifest's OpenSearch_2.17.
    OPENSEARCH_IMAGE: f"public.ecr.aws/{OPENSEARCH_IMAGE}",
}


# -- small tools -----------------------------------------------------------------------------------


def sh(*args: str, stdin: str | None = None, check: bool = True) -> str:
    done = subprocess.run(args, input=stdin, capture_output=True, text=True)
    if check and done.returncode != 0:
        raise SystemExit(f"{' '.join(args[:6])}: exit {done.returncode}\n{done.stderr}{done.stdout}")
    return done.stdout


def kubectl(*args: str, stdin: str | None = None, check: bool = True) -> str:
    return sh("kubectl", *args, stdin=stdin, check=check)


def apply(documents: list[dict[str, Any]]) -> None:
    # One v1 List: kubectl reads a JSON stream as JSON, so a YAML `---` between documents is refused.
    kubectl("apply", "-f", "-", stdin=json.dumps({"apiVersion": "v1", "kind": "List", "items": documents}))


def record(name: str) -> Path:
    RECORDS.mkdir(parents=True, exist_ok=True)
    return RECORDS / f"{dt.datetime.now(dt.UTC):%Y%m%dT%H%M%SZ}-{name}.log"


def state() -> dict[str, Any]:
    path = STATE / "state.json"
    return json.loads(path.read_text()) if path.exists() else {}


def save(**changes: Any) -> dict[str, Any]:
    s = {**state(), **changes}
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "state.json").write_text(json.dumps(s, indent=2))
    return s


def b64(text: str | bytes) -> str:
    return base64.b64encode(text.encode() if isinstance(text, str) else text).decode()


# -- the stand-in CA and its certificates ----------------------------------------------------------


def ca() -> Path:
    """One CA for every stand-in's certificate and the ingress's; the pods trust it beside the public
    roots (the webhook's bundle), the checks trust it for the door."""
    d = STATE / "ca"
    if (d / "ca.crt").exists():
        return d
    d.mkdir(parents=True, exist_ok=True)
    sh("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "14", "-subj",
       "/CN=osprey-r1 stand-in CA", "-keyout", str(d / "ca.key"), "-out", str(d / "ca.crt"))
    return d


def certificate(name: str, hosts: list[str]) -> tuple[bytes, bytes]:
    d = ca()
    san = "subjectAltName=" + ",".join(f"DNS:{h}" for h in hosts)
    stale = not (d / f"{name}.san").exists() or (d / f"{name}.san").read_text() != san
    if stale or not (d / f"{name}.crt").exists():  # made again whenever its names change
        sh("openssl", "req", "-newkey", "rsa:2048", "-nodes", "-subj", f"/CN={hosts[0]}",
           "-keyout", str(d / f"{name}.key"), "-out", str(d / f"{name}.csr"))
        (d / f"{name}.san").write_text(san)
        sh("openssl", "x509", "-req", "-in", str(d / f"{name}.csr"), "-CA", str(d / "ca.crt"),
           "-CAkey", str(d / "ca.key"), "-CAcreateserial", "-days", "14", "-extfile",
           str(d / f"{name}.san"), "-out", str(d / f"{name}.crt"))
    return (d / f"{name}.crt").read_bytes(), (d / f"{name}.key").read_bytes()


def tls_secret(namespace: str, name: str, crt: bytes, key: bytes, kind: str = "Opaque") -> dict[str, Any]:
    data = {"tls.crt": b64(crt), "tls.key": b64(key)}
    if kind == "Opaque":
        data["ca.crt"] = b64((ca() / "ca.crt").read_bytes())
    return {"apiVersion": "v1", "kind": "Secret", "type": kind,
            "metadata": {"name": name, "namespace": namespace}, "data": data}


def bundle() -> str:
    """The public roots (certifi's) and the stand-in CA: what every pod of the deployment trusts."""
    import certifi

    return Path(certifi.where()).read_text() + "\n" + (ca() / "ca.crt").read_text()


# -- the platform, as it stands before the install --------------------------------------------------


def standin_image() -> str:
    """The stand-ins run in our own api image (Python and PyJWT), built from this checkout's
    Dockerfile once, apart from the install's own push: the platform's services exist before it."""
    tag = "localhost:5001/r1-standin/api:" + sh("git", "rev-parse", "--short", "HEAD").strip()
    if sh("docker", "manifest", "inspect", "--insecure", tag, check=False).strip():
        return tag
    plan = STATE / "standin-render"
    plan.mkdir(parents=True, exist_ok=True)
    out = sh(".venv/bin/python", "-c", (
        "import sys, yaml; from pathlib import Path; from harness.render import load_config, render; "
        "r = render(load_config(Path(sys.argv[1])), resolver=lambda ref: None, allow_unpinned=True); "
        "print(next(yaml.safe_dump(i) for i in yaml.safe_load(r.artefacts['images.yaml'])['images'] "
        "if '/ospreyflow/api:' in i['target']))"), str(CONFIG))
    api = yaml.safe_load(out)
    args = ["docker", "buildx", "build", "--push", "-t", tag, "-f", api["dockerfile"]]
    for k, v in (api.get("build_args") or {}).items():
        args += ["--build-arg", f"{k}={v}"]
    sh(*args, api.get("context", "."))
    return tag


def mirror_third_party() -> None:
    for local, source in THIRD_PARTY.items():
        target = f"localhost:5001/{local}"
        if not sh("docker", "manifest", "inspect", "--insecure", target, check=False).strip():
            sh("docker", "pull", "-q", source)
            sh("docker", "tag", source, target)
            sh("docker", "push", "-q", target)


def coredns() -> None:
    """The platform's names answer at their stand-ins inside the cluster (and only inside it)."""
    cm = json.loads(kubectl("-n", "kube-system", "get", "configmap", "coredns", "-o", "json"))
    corefile = cm["data"]["Corefile"]
    corefile = re.sub(r"    # r1-standins\n(    rewrite stop \{\n(?:.*\n)*?    \}\n)+", "", corefile)
    rules = "    # r1-standins\n" + "".join(
        f"    rewrite stop {{\n      name exact {name} {svc}.{MANAGED}.svc.cluster.local\n"
        f"      answer name {svc}.{MANAGED}.svc.cluster.local {name}\n    }}\n"
        for name, svc in NAMES.items())
    corefile = corefile.replace("    kubernetes cluster.local", rules + "    kubernetes cluster.local", 1)
    cm["data"]["Corefile"] = corefile
    kubectl("replace", "-f", "-", stdin=json.dumps(cm))
    kubectl("-n", "kube-system", "rollout", "restart", "deployment/coredns")
    kubectl("-n", "kube-system", "rollout", "status", "deployment/coredns", "--timeout=120s")


def entra_keys() -> dict[str, Any]:
    """The stand-in tenant's signing key: private on this machine alone, public in the cluster."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    path = STATE / "entra.key"
    if not path.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
        path.chmod(0o600)
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    numbers = key.public_key().public_numbers()  # type: ignore[union-attr]

    def b64url(n: int) -> str:
        return base64.urlsafe_b64encode(n.to_bytes((n.bit_length() + 7) // 8, "big")).rstrip(b"=").decode()

    kid = hashlib.sha256(str(numbers.n).encode()).hexdigest()[:16]
    return {"kid": kid, "pem": path.read_bytes(),
            "jwk": {"kty": "RSA", "use": "sig", "alg": "RS256", "kid": kid, "n": b64url(numbers.n), "e": b64url(numbers.e)}}


def standins_text(password: str) -> str:
    """The managed stores' stand-ins as the cluster is given them: the run's password, and the RDS
    stand-in's max_connections the render's own (ADR-114 Amendment 46), so kind's PostgreSQL allows
    what the client's parameter group sets."""
    from harness.cloud_platform.connections import POSTGRES_MAX_CONNECTIONS

    text = (HERE / "r1_kind_standins.yaml").read_text()
    return (text.replace("${PASSWORD}", password).replace("${MAX_CONNECTIONS}", str(POSTGRES_MAX_CONNECTIONS))
            .replace("${OPENSEARCH_IMAGE}", OPENSEARCH_IMAGE))


def entra_clients() -> dict[str, str]:
    """Each confidential client's secret, made once per run and kept in the run's state folder (600)."""
    path = STATE / "entra-clients.json"
    if path.is_file():
        return json.loads(path.read_text())
    made = {name: secrets.token_urlsafe(32) for name in ("superset", "report-sync")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600)
    path.write_text(json.dumps(made))
    return made


def entra_config() -> dict[str, Any]:
    """The stand-in tenant: its API and scope, the Glass (public, PKCE), Superset (confidential, by
    code) and the report sync (confidential, client credentials), and the one person who signs in."""
    claims = yaml.safe_load(CONFIG.read_text())["cloud_platform"]["claims"]
    extra = yaml.safe_load((HERE / "r1_kind_entra.yaml").read_text())
    made = entra_clients()
    superset, reports = extra["superset"], extra["report-sync"]
    api = claims["api_client_id"]
    return {
        "tenant_id": claims["tenant_id"],
        "jwks": [entra_keys()["jwk"]],
        "api": {"app_id": api, "identifier": f"api://{api}", "scopes": [claims.get("scope", "access_as_user")]},
        "clients": {
            claims["client_id"]: {"redirect_uris": [f"https://{GLASS}/"], "delegated": [claims.get("scope", "access_as_user")]},
            superset["client_id"]: {"secret": made["superset"], "delegated": superset["delegated"],
                                    "redirect_uris": [f"https://bi.{GLASS}{superset['redirect_path']}"]},
            reports["client_id"]: {"secret": made["report-sync"], "service_principal": reports["service_principal"],
                                   "roles": reports["roles"]},
        },
        "user": {
            "oid": claims["first_administrators"][0], "name": "Synthetic Administrator",
            "preferred_username": "admin@r1.test",
            "claims": {claims["clearance"]["claim"]: "OFFICIAL-SENSITIVE",
                       "groups": [*claims["org_unit"]["groups"], *claims["handling_codes"]["groups"]]},
        },
    }


def _server(name: str, image: str, mode: str, config: dict[str, Any], port: int, tls: str) -> list[dict[str, Any]]:
    """A stand-in server in the platform's own namespace, on the port the real one answers on."""
    labels = {"app": name}
    return [
        {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": name, "namespace": MANAGED},
         "data": {"server.py": SERVERS.read_text(), "config.json": json.dumps(config)}},
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": name, "namespace": MANAGED},
         "spec": {"replicas": 1, "selector": {"matchLabels": labels}, "template": {
             "metadata": {"labels": labels, "annotations": {"r1/config": hashlib.sha256(json.dumps(config).encode()).hexdigest()[:12]}},
             "spec": {"securityContext": {"runAsNonRoot": True, "runAsUser": 10001, "runAsGroup": 10001,
                                          "sysctls": [{"name": "net.ipv4.ip_unprivileged_port_start", "value": "0"}]},
                      "containers": [{"name": name, "image": image,
                                      "command": ["/app/.venv/bin/python", "-I", "/code/server.py", mode, "--config", "/code/config.json",
                                                  "--port", str(port), "--tls-cert", "/tls/tls.crt", "--tls-key", "/tls/tls.key"],
                                      "ports": [{"containerPort": port}],
                                      "volumeMounts": [{"name": "code", "mountPath": "/code"}, {"name": "tls", "mountPath": "/tls"}]}],
                      "volumes": [{"name": "code", "configMap": {"name": name}}, {"name": "tls", "secret": {"secretName": tls}}]}}}},
        {"apiVersion": "v1", "kind": "Service", "metadata": {"name": name, "namespace": MANAGED},
         "spec": {"selector": labels, "ports": [{"port": 443, "targetPort": port}]}},
    ]


def s3_config(prefix: str, roles: dict[str, str]) -> dict[str, Any]:
    """The AWS side as the namespace's Terraform makes it: each role trusted by the cluster's issuer
    for its own service account, given its own policy; the buckets and the backups' key."""
    from harness import cloud_platform_backups as backups
    from harness.cloud_platform.terraform import BUCKETS

    jwks = json.loads(kubectl("get", "--raw", "/openid/v1/jwks"))
    issuer = json.loads(kubectl("get", "--raw", "/.well-known/openid-configuration"))["issuer"]
    provider = f"arn:aws:iam::{ACCOUNT}:oidc-provider/{issuer.removeprefix('https://')}"
    backup_bucket = f"{prefix}{backups.BUCKET_SUFFIX}"
    policies = backups.role_policies(f"arn:aws:s3:::{backup_bucket}", KEY_ARN, REGION)
    stores = [f"arn:aws:s3:::{prefix}{b}" for b in BUCKETS]
    policies["ospreyflow"] = {"Version": "2012-10-17", "Statement": [  # irsa.tf's `buckets`
        {"Effect": "Allow", "Action": ["s3:ListBucket", "s3:GetBucketLocation"], "Resource": stores},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], "Resource": [f"{s}/*" for s in stores]}]}
    out = []
    for account, arn in roles.items():
        subject = f"system:serviceaccount:{NS}:{account}"
        out.append({"arn": arn, "issuer_secret": "unused: the cluster's keys are the trust", "subject": subject,
                    "jwks": jwks, "issuer": issuer,
                    "trust": backups.trust_policy(provider, issuer.removeprefix("https://"), subject),
                    "policies": [policies[account]]})
    role_arns = [roles[backups.SERVICE_ACCOUNT], roles[backups.CLICKHOUSE_SERVICE_ACCOUNT]]
    return {
        "region": REGION, "roles": out,
        "buckets": [{"name": f"{prefix}{b}"} for b in BUCKETS] + [{
            "name": backup_bucket, "kms_key": KEY_ARN,
            "policy": backups.bucket_policy(f"arn:aws:s3:::{backup_bucket}", KEY_ARN, role_arns)}],
        "keys": [{"arn": KEY_ARN, "policy": backups.key_policy(f"arn:aws:iam::{ACCOUNT}:root", role_arns, REGION)}],
        # The domain's access policy admits `aws_iam_role.service` alone (opensearch.tf); what it admits
        # goes on to the OpenSearch pod beside the stand-in (r1_kind_standins.yaml).
        "domains": [{"host": SEARCH_HOST, "roles": [roles["ospreyflow"]],
                     "upstream": f"http://opensearch.{MANAGED}.svc.cluster.local:9200"}],
    }


def platform() -> None:
    """Everything the client's platform has before the install begins: run once, after `up`."""
    log = record("platform")
    mirror_third_party()
    image = standin_image()
    save(standin_image=image)
    apply([{"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": n}} for n in (MANAGED, NS)])
    # Both forms: a pod asks by the full name, the API server calls a webhook's service by `<svc>.<ns>.svc`.
    names = [f"{s}.{MANAGED}.svc{tail}" for s in ("postgres", "valkey", "s3-standin", "entra-standin", "irsa-webhook")
             for tail in (".cluster.local", "")]
    crt, key = certificate("standins", [*names, *NAMES])
    door_crt, door_key = certificate("door", [GLASS])
    apply([
        tls_secret(MANAGED, "standin-tls", crt, key),
        # The ingress's certificate, as the platform's issues it (cloud_platform.tls_secret).
        tls_secret(NS, "osprey-r1-tls", door_crt, door_key, kind="kubernetes.io/tls"),
        # The trust every pod of the deployment is given by the webhook (the platform's own CAs).
        {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "r1-trust", "namespace": NS},
         "data": {"ca-bundle.crt": bundle()}},
    ])
    apply([d for d in yaml.safe_load_all(standins_text(PASSWORD)) if d])
    for s in ("postgres", "valkey", "opensearch"):
        kubectl("-n", MANAGED, "rollout", "status", f"statefulset/{s}", "--timeout=300s")
    coredns()
    # Entra ID: the tenant's discovery, keys, /authorize and /token (v0.5.2, step 8). It signs what it
    # grants with a key it makes at start and never writes out; this driver's own key stays published
    # beside it for the refusals it crafts (another audience, no oid, a group overage).
    apply(_server("entra-standin", image, "entra", entra_config(), 443, "standin-tls"))
    kubectl("-n", MANAGED, "rollout", "status", "deployment/entra-standin", "--timeout=300s")
    log.write_text(f"platform stand-ins up with {image}\n")
    print(f"the platform's stand-ins are up (record {log})")


def irsa_webhook(roles: dict[str, str]) -> None:
    """EKS's pod identity webhook's stand-in, for the deployment's namespace alone; failing closed,
    so no pod starts without what the platform would give it."""
    config = {"roles": roles, "region": REGION, "trust_configmap": "r1-trust",
              "endpoint": f"https://s3-standin.{MANAGED}.svc.cluster.local"}
    apply(_server("irsa-webhook", state()["standin_image"], "webhook", config, 8443, "standin-tls"))
    kubectl("-n", MANAGED, "rollout", "status", "deployment/irsa-webhook", "--timeout=300s")
    apply([{"apiVersion": "admissionregistration.k8s.io/v1", "kind": "MutatingWebhookConfiguration",
            "metadata": {"name": "r1-irsa-standin"},
            "webhooks": [{"name": "irsa.r1.test", "admissionReviewVersions": ["v1"], "sideEffects": "None",
                          "failurePolicy": "Fail", "reinvocationPolicy": "Never",
                          "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": NS}},
                          "clientConfig": {"service": {"name": "irsa-webhook", "namespace": MANAGED, "port": 443},
                                           "caBundle": b64((ca() / "ca.crt").read_bytes())},
                          "rules": [{"operations": ["CREATE"], "apiGroups": [""], "apiVersions": ["v1"], "resources": ["pods"]}]}]}])


# -- the Terraform's stand-in -----------------------------------------------------------------------

_RESOURCE = re.compile(r'^resource "(kubernetes_secret|kubernetes_service_account)" "(\w+)" \{\n(.*?)^\}\n', re.S | re.M)


def _terraform_values(prefix: str, roles: dict[str, str]) -> dict[str, str]:
    """Each Terraform expression the namespace's Kubernetes objects read, as its apply would answer."""
    s = state()
    passwords = s.setdefault("passwords", {})
    out: dict[str, str] = {
        "local.prefix": prefix,
        "aws_s3_bucket.backups.bucket": f"{prefix}backups",
        "aws_kms_key.backups.arn": KEY_ARN,
        "aws_db_instance.postgres.address": f"postgres.{MANAGED}.svc.cluster.local",
        "tostring(aws_db_instance.postgres.port)": "5432",
        "aws_db_instance.postgres.username": "osprey",
        "aws_db_instance.postgres.db_name": "ospreyflow",
        "aws_elasticache_replication_group.redis.primary_endpoint_address": f"valkey.{MANAGED}.svc.cluster.local",
        '"6379"': "6379",
        "aws_iam_role.service.arn": roles["ospreyflow"],
        "aws_iam_role.backup.arn": roles["ospreyflow-backup"],
        "aws_iam_role.backup_clickhouse.arn": roles["ospreyflow-backup-clickhouse"],
        '"https://${aws_opensearch_domain.search.endpoint}"': f"https://{SEARCH_HOST}",
    }
    for name in ("postgres", "redis"):  # the managed stand-ins' own, set when they were made
        passwords[name] = PASSWORD
    save(passwords=passwords)
    out.update({f"random_password.{k}.result": v for k, v in passwords.items()})
    return out


def terraform(folder: Path) -> None:
    """Install step 2's stand-in: what the namespace's Terraform, applied, leaves in the namespace
    (every `kubernetes_secret` and `kubernetes_service_account` the rendered files declare, each value
    as the apply would give it), and the AWS side at the S3 stand-in."""
    s = state()
    prefix = s.get("prefix") or f"{NS}-{secrets.token_hex(4)}-"
    roles = {"ospreyflow": f"arn:aws:iam::{ACCOUNT}:role/{NS}-service",
             "ospreyflow-backup": f"arn:aws:iam::{ACCOUNT}:role/{NS}-backup",
             "ospreyflow-backup-clickhouse": f"arn:aws:iam::{ACCOUNT}:role/{NS}-backup-clickhouse"}
    save(prefix=prefix, roles=roles)
    values = _terraform_values(prefix, roles)
    passwords = state()["passwords"]
    documents: list[dict[str, Any]] = []
    made: list[str] = []
    for tf in sorted((folder / "terraform").glob("*.tf")):
        for kind, _label, body in _RESOURCE.findall(tf.read_text()):
            name = re.search(r'name\s*=\s*"([^"]+)"', body).group(1)  # type: ignore[union-attr]
            if kind == "kubernetes_service_account":
                role = re.search(r'"eks.amazonaws.com/role-arn"\s*=\s*(\S+)', body)
                documents.append({"apiVersion": "v1", "kind": "ServiceAccount", "metadata": {
                    "name": name, "namespace": NS,
                    "annotations": {"eks.amazonaws.com/role-arn": values[role.group(1)]} if role else {}}})
            else:
                data = {}
                for key, expression in re.findall(r"^\s+(\w+)\s*=\s*(.+)$", body.split("data = {", 1)[1], re.M):
                    expression = expression.strip()
                    random = re.fullmatch(r"random_password\.(\w+)\.result", expression)
                    if random and random.group(1) not in passwords:
                        passwords[random.group(1)] = secrets.token_hex(16)
                        save(passwords=passwords)
                        values[expression] = passwords[random.group(1)]
                    if expression not in values:
                        raise SystemExit(f"the Terraform stand-in does not know {expression} ({tf.name}, {name}.{key}): say what the apply would give")
                    data[key] = b64(values[expression])
                documents.append({"apiVersion": "v1", "kind": "Secret", "metadata": {"name": name, "namespace": NS}, "data": data})
            made.append(f"{kind} {name} ({tf.name})")
    apply(documents)
    save(terraform_made=made)
    config = s3_config(prefix, roles)
    s3_standin(config)
    irsa_webhook(roles)
    print("the Terraform's stand-in made:\n  " + "\n  ".join(made))


def s3_standin(config: dict[str, Any]) -> None:
    image = state()["standin_image"]
    labels = {"app": "s3-standin"}
    apply([
        {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "s3-standin", "namespace": MANAGED},
         "data": {"s3_standin.py": STANDIN_CODE.read_text(), "standin.json": json.dumps(config)}},
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "s3-standin", "namespace": MANAGED},
         "spec": {"replicas": 1, "selector": {"matchLabels": labels}, "strategy": {"type": "Recreate"}, "template": {
             "metadata": {"labels": labels},
             "spec": {"securityContext": {"runAsNonRoot": True, "runAsUser": 10001, "runAsGroup": 10001, "fsGroup": 10001,
                                          "sysctls": [{"name": "net.ipv4.ip_unprivileged_port_start", "value": "0"}]},
                      "containers": [{"name": "s3-standin", "image": image,
                                      "command": ["/app/.venv/bin/python", "-I", "/code/s3_standin.py", "--config", "/code/standin.json",
                                                  "--root", "/data", "--port", "443", "--tls-cert", "/tls/tls.crt", "--tls-key", "/tls/tls.key"],
                                      "env": [{"name": "S3_STANDIN_LOG", "value": "1"}],
                                      "volumeMounts": [{"name": "code", "mountPath": "/code"}, {"name": "tls", "mountPath": "/tls"},
                                                       {"name": "data", "mountPath": "/data"}]}],
                      # A claim of its own, so the buckets outlive a restart of the stand-in.
                      "volumes": [{"name": "code", "configMap": {"name": "s3-standin"}}, {"name": "tls", "secret": {"secretName": "standin-tls"}},
                                  {"name": "data", "persistentVolumeClaim": {"claimName": "s3-standin"}}]}}}},
        {"apiVersion": "v1", "kind": "PersistentVolumeClaim", "metadata": {"name": "s3-standin", "namespace": MANAGED},
         "spec": {"accessModes": ["ReadWriteOnce"], "storageClassName": "gp2-expand", "resources": {"requests": {"storage": "5Gi"}}}},
        {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "s3-standin", "namespace": MANAGED},
         "spec": {"selector": labels, "ports": [{"port": 443, "targetPort": 443}]}},
    ])
    kubectl("-n", MANAGED, "rollout", "restart", "deployment/s3-standin")
    kubectl("-n", MANAGED, "rollout", "status", "deployment/s3-standin", "--timeout=300s")


def s3_exec(code: str) -> str:
    """Python run in the S3 stand-in's pod, over its own disk (for the decommission's stand-ins)."""
    return kubectl("-n", MANAGED, "exec", "deployment/s3-standin", "--", "/app/.venv/bin/python", "-c", code)


# -- the platform's blocks, stood in for ------------------------------------------------------------


def _work() -> Path:
    """The runbooks' `$WORK` (step 1 exports it: `${TMPDIR:-/tmp}/ospreyflow-$NS`)."""
    return Path(os.environ.get("WORK") or Path(os.environ.get("TMPDIR", "/tmp")) / f"ospreyflow-{NS}")


def operator_choices(name: str) -> dict[str, str]:
    """What R1's operator exports before a runbook, as *What it needs* asks: for the decommission, the
    backups kept (the brief: the bucket kept with the last set) for 30 days. Never over a choice
    already in the environment, and nothing for the install."""
    if name != "DECOMMISSION" or "BACKUPS" in os.environ:
        return {}
    return {"BACKUPS": "keep", "BACKUP_RETENTION_DAYS": "30"}


def stand_in(runbook: str, step: str) -> None:
    """What the platform team does for a `bash platform` block, by the step it stands in."""
    folder = FOLDER
    if runbook == "INSTALL" and step.startswith("2."):
        terraform(folder)
    elif runbook == "INSTALL" and step.startswith("3."):
        print("stand-in: the cluster's registry (localhost:5001) needs no sign-in")
    elif runbook == "DECOMMISSION" and step.startswith("6."):
        # The buckets emptied of every object (the stand-in keeps no versions), the images left
        # with the registry (removed with the cluster by `r1_kind.sh down`).
        prefix = state()["prefix"]
        from harness.cloud_platform.terraform import BUCKETS
        print(s3_exec("import pathlib, shutil\n" + "".join(
            f"p = pathlib.Path('/data/{prefix}{b}')\n"
            f"n = sum(1 for _ in p.glob('*')) if p.exists() else 0\n"
            f"[shutil.rmtree(x) if x.is_dir() else x.unlink() for x in p.glob('*')]\n"
            f"print('emptied {prefix}{b}:', n, 'files')\n" for b in BUCKETS)))
    elif runbook == "DECOMMISSION" and step.startswith("7."):
        # The pull request applied: what the Terraform made, removed, but the kept backups bucket and
        # key (taken out of the state first); the lifecycle rule is not modelled by the stand-in.
        # First the choice the block requires (ADR-148 Amendment 13: keep or destroy, no default),
        # refused as the block refuses it, then recorded where step 8 reads it.
        choice = os.environ.get("BACKUPS", "")
        if choice not in ("keep", "destroy"):
            raise SystemExit("BACKUPS: choose keep or destroy for the backups bucket and its key (there is no default)")
        if choice == "destroy":
            raise SystemExit("stand-in: BACKUPS=destroy is not modelled (R1 keeps its backups); say what the platform does there")
        days = os.environ.get("BACKUP_RETENTION_DAYS", "")
        if not days.isdigit() or int(days) < 1:
            raise SystemExit("BACKUP_RETENTION_DAYS: the retention you agree for the kept backups, in days")
        work = _work()
        work.mkdir(parents=True, exist_ok=True)
        (work / "backups").write_text(f"{choice}\n")
        print(f"stand-in: backups {choice}, retention {days} days (the lifecycle rule not modelled)")
        made = state().get("terraform_made", [])
        for line in made:
            kind, name = line.split()[:2]
            kubectl("-n", NS, "delete", "secret" if kind == "kubernetes_secret" else "serviceaccount", name, "--ignore-not-found")
        config = json.loads(kubectl("-n", MANAGED, "get", "configmap", "s3-standin", "-o", "jsonpath={.data.standin\\.json}"))
        config["buckets"] = [b for b in config["buckets"] if b["name"].endswith("backups")]
        config["roles"] = []
        # The domain goes with the Terraform (ADR-148 Amendment 13: no index backup), its disks with it.
        config["domains"] = []
        kubectl("-n", MANAGED, "delete", "statefulset", "opensearch", "--ignore-not-found")
        kubectl("-n", MANAGED, "delete", "pvc", "-l", "app=opensearch", "--ignore-not-found")
        # The buckets the Terraform made, deleted as `aws_s3_bucket` deletes one: refused while it holds
        # anything (BucketNotEmpty; no force_destroy), so step 6's emptying is what lets it go.
        prefix = state()["prefix"]
        gone = json.loads(s3_exec(
            "import json, pathlib, shutil\n"
            f"made = [p for p in pathlib.Path('/data').iterdir() if p.is_dir() and p.name.startswith({prefix!r})"
            " and not p.name.endswith('backups')]\n"
            "full = [p.name for p in made if any(f.is_file() for f in p.rglob('*'))]\n"
            "if full: raise SystemExit('BucketNotEmpty: ' + ', '.join(full))\n"
            "[shutil.rmtree(p) for p in made]\n"
            "print(json.dumps([p.name for p in made]))"))
        print(f"stand-in: the Terraform deleted the buckets {gone}")
        s3_standin(config)
        kubectl("delete", "mutatingwebhookconfiguration", "r1-irsa-standin", "--ignore-not-found")
        print("stand-in: the Terraform's removal applied; kept: the backups bucket and its key")
    elif runbook == "DECOMMISSION" and step.startswith("8.") and "STATE:?" in os.environ.get("R1_BLOCK", ""):
        work = _work()
        work.mkdir(parents=True, exist_ok=True)
        (work / "state.txt").write_text("")  # the kept resources were taken out; the rest destroyed
        names = json.loads(s3_exec("import json, pathlib; print(json.dumps([p.name for p in pathlib.Path('/data').iterdir() if p.is_dir()]))"))
        prefix = state()["prefix"]
        (work / "buckets.txt").write_text("".join(f"{n}\n" for n in names if n.startswith(prefix)))
        print(f"stand-in: {work}/state.txt (empty) and buckets.txt ({len(names)} buckets)")
    elif runbook == "DECOMMISSION" and step.startswith("8."):
        # The disks, as the platform team lists them: kind has no EBS, so the cluster's volumes.
        work = _work()
        (work / "volumes.json").write_text(kubectl("get", "pv", "-o", "json"))
        print(f"stand-in: {work}/volumes.json, the cluster's volumes (the platform team's listing)")
    else:
        raise SystemExit(f"no stand-in for {runbook} step {step}: say what the platform does there")


# -- the runbooks, run as written ---------------------------------------------------------------------

_HEAD = re.compile(r"^## (\d+\.[^\n]*)$", re.M)
_BLOCK = re.compile(r"^```bash( platform)?\n(.*?)^```\n", re.S | re.M)


def blocks(text: str) -> list[tuple[str, bool, str]]:
    """(the step's heading, whether the platform's, the block) in order, by the same fences as
    `harness.cloud_platform.runbooks.command_blocks`, whose list of `bash` blocks this must equal."""
    from harness.cloud_platform.runbooks import command_blocks

    heads = [(m.start(), m.group(1)) for m in _HEAD.finditer(text)]
    out = []
    for m in _BLOCK.finditer(text):
        step = next((h for pos, h in reversed(heads) if pos < m.start()), "0. header")
        out.append((step, bool(m.group(1)), m.group(2)))
    assert [b for _, p, b in out if not p] == command_blocks(text, on_the_platform=False)
    return out


def script_for(name: str, text: str, start: int) -> str:
    """The runbook as one bash script: each block as written, each platform block's stand-in."""
    script = ["set -e"]
    for i, (step, platform_block, body) in enumerate(blocks(text), 1):
        # From block N, step 1's settings still first: every later block reads them, in one shell.
        if i < start and not step.startswith("1."):
            continue
        said = f"=== {name} block {i} (step {step}){' [the platform: stand-in]' if platform_block else ''} ==="
        script.append(f"printf '\\n%s\\n' {shlex.quote(said)}")
        if platform_block:
            script.append(f"printf '%s' {shlex.quote(body)} | sed 's/^/  (platform) /'")
            script.append(f'R1_BLOCK={shlex.quote(body)} "$R1_PY" "$R1" stand-in {name} {shlex.quote(step)}')
        else:
            script.append(f"printf '%s' {shlex.quote(body)} | sed 's/^/  $ /'")
            script.append(body)
    script.append(f"printf '\\n=== {name}: every block ran ===\\n'")
    return "\n".join(script) + "\n"


def keep_render() -> None:
    if (FOLDER / "values.yaml").exists():
        shutil.rmtree(KEPT, ignore_errors=True)
        shutil.copytree(FOLDER, KEPT)


def render_back() -> None:
    if not (FOLDER / "values.yaml").exists() and (KEPT / "values.yaml").exists():
        shutil.copytree(KEPT, FOLDER, dirs_exist_ok=True)
        print(f"the install's render put back from {KEPT}")


def runbook(name: str, start: int) -> None:
    render_back()
    if name == "DECOMMISSION" and (KEPT / "values.yaml").exists():
        # The runbook as this release renders it (a fix to its words reaches a decommission already
        # begun), over the values the install put in, which stay the kept ones.
        sh(".venv/bin/python", "-m", "harness.render", "--config", str(CONFIG), "--allow-unpinned")
        for kept in ("values.yaml", "versions.lock", "images.yaml"):
            if (KEPT / kept).exists():
                shutil.copy2(KEPT / kept, FOLDER / kept)
    path = FOLDER / f"{name}.md"
    if name == "INSTALL" and not path.exists():
        # The runbook's own header: the render that writes it, before anything is pushed.
        sh(".venv/bin/python", "-m", "harness.render", "--config", str(CONFIG), "--allow-unpinned")
    log = record(name)
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / f"{name}.sh").write_text(script_for(name, path.read_text(), start))
    # What the operator brings, as *What it needs* says: kubectl pointed at the namespace, the `ospreyflow`
    # command by `uv tool install ./cli` with `~/.local/bin` on PATH (R1's finding 8: `.venv/bin` never held
    # it), and curl's options for a door whose CA the machine does not trust.
    kubectl("config", "set-context", "--current", f"--namespace={NS}")
    if name == "INSTALL":
        sh(shutil.which("uv") or str(LOCAL_BIN / "uv"), "tool", "install", "--force", "./cli")
    node = sh("docker", "inspect", "-f", "{{.NetworkSettings.Networks.kind.IPAddress}}", "osprey-r1-control-plane").strip()
    env = {**os.environ, "CONFIG": str(CONFIG), "R1": str(Path(__file__)), "R1_PY": sys.executable,
           "PATH": f"{LOCAL_BIN}:{os.environ['PATH']}",
           "OSPREY_CURL_OPTS": f"--cacert {ca() / 'ca.crt'} --resolve {GLASS}:443:{node}",
           **operator_choices(name)}
    print(f"running {name} from block {start}; record {log}")
    with log.open("w") as out:
        out.write(f"# {name}.md as rendered, run from block {start} at {os.environ.get('R1_HEAD', 'the copy (no .git)')}\n")
        out.flush()
        started = time.monotonic()
        proc = subprocess.Popen(["bash", str(STATE / f"{name}.sh")], cwd=CORE, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            out.write(line)
        code = proc.wait()
        out.write(f"\n# exit {code} after {time.monotonic() - started:.0f} s\n")
    keep_render()
    if code:
        raise SystemExit(f"{name} stopped (exit {code}): the record is {log}")


# -- the checks ---------------------------------------------------------------------------------------


def token(**overrides: Any) -> str:
    """An Entra v2.0 access token for a person of the stand-in tenant, as Entra shapes it."""
    import jwt

    c = yaml.safe_load(CONFIG.read_text())["cloud_platform"]["claims"]
    keys = entra_keys()
    now = int(time.time())
    claims: dict[str, Any] = {
        "aud": c["api_client_id"], "iss": f"https://login.microsoftonline.com/{c['tenant_id']}/v2.0",
        "iat": now, "nbf": now, "exp": now + 3600, "ver": "2.0", "tid": c["tenant_id"],
        "oid": c["first_administrators"][0], "azp": c["client_id"], "sub": "r1-pairwise-subject-0001",
        "name": "Synthetic Administrator", "preferred_username": "admin@r1.test",
        "scp": "openid profile access_as_user",
        c["clearance"]["claim"]: "OFFICIAL-SENSITIVE",
        "groups": [*c["org_unit"]["groups"], *c["handling_codes"]["groups"]],
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, keys["pem"], algorithm="RS256", headers={"kid": keys["kid"]})


def _foreign_signed() -> str:
    """The administrator's own claims under the tenant's kid, signed by a key the tenant never published."""
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    real = jwt.decode(token(), options={"verify_signature": False})
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return jwt.encode(real, other, algorithm="RS256", headers={"kid": entra_keys()["kid"]})


def door() -> Any:
    """A client to the Glass's door, by its name, over TLS (the stand-in CA trusted), through the
    ingress controller on the kind node: the deployment's name resolved to that node, nothing else."""
    import socket

    import httpx

    ip = sh("docker", "inspect", "-f", "{{.NetworkSettings.Networks.kind.IPAddress}}", "osprey-r1-control-plane").strip()
    real = socket.getaddrinfo
    socket.getaddrinfo = lambda host, *a, **k: real(ip if host == GLASS else host, *a, **k)  # type: ignore[assignment]
    return httpx.Client(base_url=f"https://{GLASS}", verify=str(ca() / "ca.crt"), timeout=60)


#: Run in a pod of the namespace by `domain_probe` (and offline by the domain's tests): a GET of the
#: domain's health signed for `es` as rules' client signs (botocore's SigV4, the pod's IRSA credentials
#: resolved by botocore itself, the platform's CA as AWS_CA_BUNDLE gives it), the same unsigned, and a
#: connection straight to the OpenSearch pod's 9200, which the namespace's egress must not allow.
DOMAIN_PROBE = r"""
import hashlib, json, os, socket, ssl, urllib.error, urllib.request
import botocore.session
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

url = os.environ["OPENSEARCH_URL"].rstrip("/") + "/_cluster/health"
context = ssl.create_default_context(cafile=os.environ.get("AWS_CA_BUNDLE"))

def send(headers):
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, context=context, timeout=30) as answer:
            return [answer.status, answer.read().decode()[:300]]
    except urllib.error.HTTPError as error:
        return [error.code, error.read().decode()[:300]]

credentials = botocore.session.get_session().get_credentials().get_frozen_credentials()
signed = AWSRequest(method="GET", url=url, headers={"x-amz-content-sha256": hashlib.sha256(b"").hexdigest()})
SigV4Auth(credentials, "es", os.environ["AWS_REGION"]).add_auth(signed)
host, _, port = os.environ.get("R1_DIRECT", "opensearch.platform-managed.svc.cluster.local:9200").rpartition(":")
try:
    socket.create_connection((host, int(port)), timeout=5).close()
    direct = "open"
except OSError:
    direct = "closed"
print(json.dumps({"signed": send(dict(signed.headers.items())), "unsigned": send({}), "direct": direct}))
"""


def domain_probe(account: str) -> dict[str, Any]:
    """`DOMAIN_PROBE` in a pod of the namespace under `account`'s service account (so the webhook gives
    it that role), labelled as the search drift check's pods so the namespace's egress admits it to
    the managed networks on 443, as it admits the search Jobs; removed when it ends."""
    image = kubectl("-n", NS, "get", "deployment/api", "-o", "jsonpath={.spec.template.spec.containers[0].image}")
    name = f"r1-domain-{account}"
    kubectl("-n", NS, "delete", "pod", name, "--ignore-not-found", "--wait")
    container = {"name": "probe", "image": image, "command": ["/app/.venv/bin/python", "-c", DOMAIN_PROBE],
                 "env": [{"name": "OPENSEARCH_URL", "valueFrom": {"secretKeyRef": {"name": "opensearch-output", "key": "proxy_url"}}}],
                 "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]},
                                     "runAsNonRoot": True, "runAsUser": 10001}}
    overrides = {"spec": {"serviceAccountName": account, "restartPolicy": "Never", "containers": [container],
                          "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}}}}
    kubectl("-n", NS, "run", name, f"--image={image}", "--restart=Never",
            "--labels=app.kubernetes.io/name=search-drift,app.kubernetes.io/part-of=ospreyflow,r1/probe=domain",
            f"--overrides={json.dumps(overrides)}")
    for _ in range(60):
        phase = kubectl("-n", NS, "get", "pod", name, "-o", "jsonpath={.status.phase}")
        if phase in ("Succeeded", "Failed"):
            break
        time.sleep(5)
    said = kubectl("-n", NS, "logs", name)
    kubectl("-n", NS, "delete", "pod", name, "--ignore-not-found")
    if phase != "Succeeded":
        raise SystemExit(f"the domain probe as {account} ended {phase or 'unstarted'}: {said[-500:]}")
    return json.loads(said.strip().splitlines()[-1])


def domain_checks(ok: Callable[[str, bool, Any], None]) -> None:
    """The domain checked from the namespace's own pods (ADR-148 Amendment 13): the service role's
    signed request reaches OpenSearch, an unsigned one and another role's are refused 403 by the
    domain, the OpenSearch pod is unreachable past it, and the stand-in's log says the same."""
    mine = domain_probe("ospreyflow")
    ok("the namespace's role reaches the domain, signed for es", mine["signed"][0] == 200 and '"status"' in mine["signed"][1], mine)
    ok("an unsigned request is refused by the domain", mine["unsigned"][0] == 403, mine)
    ok("the OpenSearch pod is not reachable past the domain (9200)", mine["direct"] == "closed", mine)
    other = domain_probe("ospreyflow-backup")
    ok("another role of the namespace is refused by the domain", other["signed"][0] == 403 and "not authorized" in other["signed"][1], other)
    logged = [line for line in kubectl("-n", MANAGED, "logs", "deployment/s3-standin", "--since=15m").splitlines()
              if line.startswith(f"domain: {SEARCH_HOST} GET /_cluster/health ")]
    roles = state()["roles"]
    ok("the stand-in's log: the service role admitted, the backup role and the unsigned refused",
       f"200 {roles['ospreyflow']}" in "\n".join(logged) and f"403 {roles['ospreyflow-backup']}" in "\n".join(logged)
       and any(line.endswith("403 anonymous") for line in logged), logged[-6:])


def checks() -> None:
    """The check list (CHECKS.md), each with its expected answer; stops at the first that fails."""
    log = record("check")
    lines: list[str] = []

    def ok(what: str, cond: bool, said: Any = "") -> None:
        line = f"{'PASS' if cond else 'FAIL'} {what}" + (f": {str(said)[:300]}" if said != "" else "")
        print(line)
        lines.append(line)
        log.write_text("\n".join(lines) + "\n")
        if not cond:
            raise SystemExit(f"check failed: {what} (record {log})")

    c = door()
    admin = {"Authorization": f"Bearer {token()}"}
    r = c.get("/healthz")
    ok("the Conduit answers through the Glass's door", r.status_code == 200, r.status_code)
    claims = yaml.safe_load(CONFIG.read_text())["cloud_platform"]["claims"]
    # Sign-in: refusals first, each as Entra would send it.
    for what, t in [
        ("another tenant's token", token(tid="99999999-1111-4222-8333-444444444444",
                                         iss="https://login.microsoftonline.com/99999999-1111-4222-8333-444444444444/v2.0")),
        ("a token for another audience", token(aud="cccccccc-bbbb-4ccc-8ddd-eeeeeeeeeeee")),
        ("an expired token", token(iat=int(time.time()) - 7200, nbf=int(time.time()) - 7200, exp=int(time.time()) - 3600)),
        ("an app-only token", token(scp=None, idtyp="app", roles=["Runs.Write"])),
        ("a guest's token", token(idp="https://sts.windows.net/99999999-1111-4222-8333-444444444444/")),
        ("a token with no oid", token(oid=None)),
        ("a token with a group overage", token(groups=None, _claim_names={"groups": "src1"},
                                               _claim_sources={"src1": {"endpoint": "https://graph.microsoft.com/v1.0/users/x/getMemberObjects"}})),
        ("a token signed by a key the tenant does not publish", _foreign_signed()),
    ]:
        r = c.get("/v1/me", headers={"Authorization": f"Bearer {t}"})
        ok(f"sign-in refuses {what}", r.status_code in (401, 403), f"{r.status_code} {r.text[:120]}")
    r = c.get("/v1/me", headers=admin)
    me = r.json() if r.status_code == 200 else {}
    ok("the first administrator signs in, by the stand-in tenant's token", r.status_code == 200, r.text[:200])
    ok("the first administrator holds Admin at first start", "osprey-admin" in me.get("roles", []), me)
    ok("their clearance is the token's", me.get("clearance") == "OFFICIAL-SENSITIVE", me)
    r = c.get("/v1/admin/people", headers=admin)
    ok("Admin › People lists them", r.status_code == 200 and any(p.get("id") == claims["first_administrators"][0] for p in r.json()), r.text[:200])
    oid = claims["first_administrators"][0]
    r = c.put(f"/v1/admin/people/{oid}/roles", headers=admin, json={"roles": ["osprey-admin", "analyst", "data_engineer"]})
    ok("they give themselves analyst and data engineer in Admin › People", r.status_code == 200, r.text[:200])
    # Roles are the deployment's (ADR-148 Am 8 point 1), not Entra app roles: a person of the tenant whom no
    # administrator gave a role signs in with none and is refused what a role grants. Entra's own "assignment
    # required" refusal (AADSTS50105) happens before a token exists, so only the real tenant can show it.
    stranger = {"Authorization": f"Bearer {token(oid='50000000-0000-4000-8000-0000000000aa', sub='r1-pairwise-subject-00aa')}"}
    r = c.get("/v1/me", headers=stranger)
    ok("a person of the tenant given no role signs in with no role", r.status_code == 200 and not r.json().get("roles"), r.text[:200])
    r = c.get("/v1/admin/people", headers=stranger)
    ok("and is refused Admin › People", r.status_code == 403, f"{r.status_code} {r.text[:120]}")
    r = c.post("/v1/investigations", headers=stranger, json={"name": "R1 refused", "new_dataset_name": "R1 refused"})
    ok("and is refused a new case", r.status_code == 403, f"{r.status_code} {r.text[:120]}")
    # A case.
    r = c.post("/v1/investigations", headers=admin, json={"name": "R1 synthetic case", "new_dataset_name": f"R1 synthetic {secrets.token_hex(3)}"})
    ok("a case is made", r.status_code == 201, r.text[:200])
    case = r.json()["id"]
    save(case=case)
    # A rule before the load: a hotlist on a synthetic number.
    number = "+447700900123"  # the msisdn adapter's own form, which a hotlist matches
    r = c.post(f"/v1/investigations/{case}/hotlists", headers=admin, json={"identifier": number, "review_date": "2026-12-31"})
    ok("a rule (a hotlist on a synthetic number) is made", r.status_code == 201, r.text[:200])
    hotlist = r.json().get("id")
    # A load through the Ingest Studio: upload, recipe, map, verify, publish, run.
    base = f"/v1/investigations/{case}/ingest"
    csv = f"family_name,given_names,phone\nR1Synthetic,Person,{number}\nR1Second,Person,+447700900456\n"
    r = c.post(f"{base}/source-files", params={"name": "r1-people.csv"}, headers={**admin, "Content-Type": "text/csv"}, content=csv)
    ok("a file is uploaded to the Ingest root", r.status_code == 201, r.text[:200])
    location = r.json()["source_location"]
    r = c.post(f"{base}/recipes", headers=admin, json={"label": "R1 people", "connector_profile": "generic-csv",
                                                       "source_location": location, "legal_basis": "synthetic test data (R1)",
                                                       # Connect's three gates (09 §2) before Profile runs.
                                                       "handling": {"classification": "OFFICIAL", "handling_code": "P",
                                                                    "originator": "unit-1", "owning_unit": "unit-1"}})
    ok("a recipe is made", r.status_code == 201, r.text[:200])
    rid = r.json()["recipe_id"]
    r = c.get(f"{base}/recipes/{rid}/profile", headers=admin)
    ok("its file is profiled", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
    template = yaml.safe_load((HERE / "r1_kind_row_template.yaml").read_text())["put_row_template"]
    r = c.put(f"{base}/recipes/{rid}/row-template", headers=admin, json=template)
    ok("it is mapped", r.status_code == 200, r.text[:300])
    for step in ("verify", "publish"):
        r = c.post(f"{base}/recipes/{rid}/{step}", headers=admin, json={})
        ok(f"it is {'verified' if step == 'verify' else 'published'}", r.status_code == 200, r.text[:300])
    r = c.post(f"{base}/recipes/{rid}/run", headers=admin, json={})
    ok("it runs, and makes entities", r.status_code == 200 and r.json().get("nodes_created", 0) > 0, r.text[:300])
    r = c.post(f"/v1/investigations/{case}/search", headers=admin, json={"query": "R1Synthetic", "limit": 5})
    ok("what it loaded is found", r.status_code == 200 and r.json().get("nodes"), r.text[:300])
    for _ in range(30):
        r = c.get(f"/v1/investigations/{case}/alert-queue", headers=admin, params={"status": "all"})
        if r.status_code == 200 and any((a.get("alert") or a).get("rule_id") == f"hotlist:{hotlist}" for a in r.json()):
            break
        time.sleep(5)
    ok("the rule raises its alert on the load", r.status_code == 200 and any((a.get("alert") or a).get("rule_id") == f"hotlist:{hotlist}" for a in r.json()), r.text[:300])
    domain_checks(ok)
    print(f"every check passed (record {log})")


# -- memory ---------------------------------------------------------------------------------------------


def memory() -> None:
    node = "osprey-r1-control-plane"
    summary = json.loads(kubectl("get", "--raw", f"/api/v1/nodes/{node}/proxy/stats/summary"))
    log = record("memory")
    gib = 1024**3
    lines = [f"node {node}: docker limit {sh('docker', 'inspect', '-f', '{{.HostConfig.Memory}}', node).strip()} bytes; "
             f"working set {summary['node']['memory']['workingSetBytes'] / gib:.2f} GiB"]
    pods = sorted(summary["pods"], key=lambda p: -(p.get("memory", {}).get("workingSetBytes") or 0))
    for p in pods:
        ref = p["podRef"]
        lines.append(f"{ref['namespace']}/{ref['name']}: {(p.get('memory', {}).get('workingSetBytes') or 0) / 2**20:.0f} MiB")
    requested = kubectl("-n", NS, "get", "pods", "-o", "jsonpath={range .items[*]}{.metadata.name} {.spec.containers[*].resources.requests.memory} {.spec.containers[*].resources.limits.memory}{'\\n'}{end}")
    lines += ["", f"requests and limits in {NS}:", requested]
    log.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


# -- the recovery runbook's cloud-platform section ---------------------------------------------------------


def recovery_blocks() -> list[str]:
    text = (CORE / "deploy" / "RUNBOOK.md").read_text()
    section = text[text.index("## The `cloud-platform` profile"):]
    section = re.split(r"^## ", section[3:], maxsplit=1, flags=re.M)[0]
    return re.findall(r"^```bash\n(.*?)^```\n", section, re.S | re.M)


def _run_filled(name: str, script: str) -> str:
    log = record(name)
    done = subprocess.run(["bash", "-c", "set -e\n" + script], cwd=CORE, capture_output=True, text=True,
                          env={**os.environ, "PATH": f"{LOCAL_BIN}:{os.environ['PATH']}"})
    log.write_text(f"# as run, placeholders filled:\n{script}\n# output (exit {done.returncode}):\n{done.stdout}{done.stderr}")
    print(done.stdout + done.stderr)
    if done.returncode:
        raise SystemExit(f"{name} stopped (exit {done.returncode}): {log}")
    return done.stdout


def backup() -> None:
    """*A backup now*, as the recovery runbook gives it, for the namespace."""
    render_back()
    block = next(b for b in recovery_blocks() if b.startswith("S=$(( $(date +%s) / 60 ))"))
    out = _run_filled("backup", block.replace("<namespace>", NS) + 'echo "SLOT=$S"\n')
    slot = int(re.search(r"SLOT=(\d+)", out).group(1))  # type: ignore[union-attr]
    name = dt.datetime.fromtimestamp(slot * 60, dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    save(last_set=name)
    print(f"the set: {name}")


def restore(which: str | None) -> None:
    """*A restore*, as the recovery runbook gives it, of the last set (or `which`): steps 1-4, with
    <namespace>, <render> and <set> filled, and step 4's `<each one noted>` from step 2's own output."""
    render_back()
    the_set = which or state()["last_set"]
    block = next(b for b in recovery_blocks() if b.startswith("# 1. No backup during the restore"))
    filled = block.replace("<namespace>", NS).replace("<render>", str(FOLDER)).replace("<set>", the_set)
    noted_at = filled.index("# 4.")
    before, after = filled[:noted_at], filled[noted_at:]
    out = _run_filled("restore-1-3", before)
    counts = re.findall(r"^(\S+)\s+(\d+)\s*$", out, re.M)  # step 2's NAME COPIES table
    noted = [(n, c) for n, c in counts if n != "arcadedb" and n != "NAME"]
    lines = [f'kubectl -n {NS} scale deployment/{n} --replicas={c}' for n, c in noted]
    after = after.replace(f"kubectl -n {NS} scale deployment/<each one noted> --replicas=<as noted>", "\n".join(lines))
    waits = [f'kubectl -n {NS} rollout status deployment/{n} --timeout=10m' for n, _ in noted]
    after = re.sub(rf"kubectl -n {NS} rollout status deployment/<each one noted> --timeout=10m[^\n]*", "\n".join(waits), after)
    _run_filled("restore-4", after)


# -- a change after the set, and what the restore brings back ---------------------------------------------


def _load_file(c: Any, admin: dict[str, str], case: str, name: str, csv: str) -> int:
    """A file through the Ingest Studio as the check list loads one: upload, recipe, profile, map, verify,
    publish, run. Answers the entities the run made; stops at the first refusal, its words recorded."""
    base = f"/v1/investigations/{case}/ingest"
    steps: list[tuple[str, Any]] = []
    r = c.post(f"{base}/source-files", params={"name": name}, headers={**admin, "Content-Type": "text/csv"}, content=csv)
    steps.append(("upload", r))
    if r.status_code == 201:
        r = c.post(f"{base}/recipes", headers=admin, json={
            "label": name, "connector_profile": "generic-csv", "source_location": r.json()["source_location"],
            "legal_basis": "synthetic test data (R1)",
            "handling": {"classification": "OFFICIAL", "handling_code": "P", "originator": "unit-1", "owning_unit": "unit-1"}})
        steps.append(("recipe", r))
    if r.status_code == 201:
        rid = r.json()["recipe_id"]
        template = yaml.safe_load((HERE / "r1_kind_row_template.yaml").read_text())["put_row_template"]
        for what, call in (("profile", lambda: c.get(f"{base}/recipes/{rid}/profile", headers=admin)),
                           ("map", lambda: c.put(f"{base}/recipes/{rid}/row-template", headers=admin, json=template)),
                           ("verify", lambda: c.post(f"{base}/recipes/{rid}/verify", headers=admin, json={})),
                           ("publish", lambda: c.post(f"{base}/recipes/{rid}/publish", headers=admin, json={})),
                           ("run", lambda: c.post(f"{base}/recipes/{rid}/run", headers=admin, json={}))):
            r = call()
            steps.append((what, r))
            if r.status_code != 200:
                break
    what, last = steps[-1]
    if last.status_code not in (200, 201) or what != "run":
        raise SystemExit(f"the load of {name} stopped at {what}: {last.status_code} {last.text[:300]}")
    return int(last.json().get("nodes_created", 0))


def _found(c: Any, admin: dict[str, str], case: str, text: str) -> int:
    r = c.post(f"/v1/investigations/{case}/search", headers=admin, json={"query": text, "limit": 5})
    if r.status_code != 200:
        raise SystemExit(f"search for {text} refused: {r.status_code} {r.text[:200]}")
    return len(r.json().get("nodes") or [])


def _source_files(c: Any, admin: dict[str, str], case: str) -> list[str]:
    r = c.get(f"/v1/investigations/{case}/ingest/source-files", headers=admin)
    if r.status_code != 200:
        raise SystemExit(f"the source files refused: {r.status_code} {r.text[:200]}")
    body = r.json()
    items = body if isinstance(body, list) else body.get("files", [])
    return [f.get("name", "") for f in items]


def change() -> None:
    """After the set: a second load into the check list's case, new entities in ArcadeDB and a new file
    on the Ingest claim, both of which the restore must take away."""
    c, case = door(), state()["case"]
    admin = {"Authorization": f"Bearer {token()}"}
    made = _load_file(c, admin, case, "r1-after-the-set.csv",
                      "family_name,given_names,phone\nR1AfterTheSet,Person,+447700900789\n")
    seen = (_found(c, admin, case, "R1AfterTheSet"), _found(c, admin, case, "R1Synthetic"))
    files = _source_files(c, admin, case)
    record("change").write_text(f"made {made}; found after/before {seen}; files {files}\n")
    print(f"after the set: {made} entities made; R1AfterTheSet found {seen[0]}, R1Synthetic found {seen[1]}; files {files}")
    if not made or not seen[0] or "r1-after-the-set.csv" not in files:
        raise SystemExit("the change after the set did not take")


def restored() -> None:
    """After the restore: the change is gone and the set's load is there (check 9)."""
    c, case = door(), state()["case"]
    admin = {"Authorization": f"Bearer {token()}"}
    after, before = _found(c, admin, case, "R1AfterTheSet"), _found(c, admin, case, "R1Synthetic")
    files = _source_files(c, admin, case)
    lines = [f"{'PASS' if after == 0 else 'FAIL'} the change after the set is gone from the graph: {after} found",
             f"{'PASS' if before > 0 else 'FAIL'} the set's load is there: {before} found",
             f"{'PASS' if 'r1-after-the-set.csv' not in files else 'FAIL'} the file after the set is gone from the "
             f"Ingest claim; the set's is there: {'r1-people.csv' in files} ({files})"]
    record("restored").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    if any(line.startswith("FAIL") for line in lines) or "r1-people.csv" not in files:
        raise SystemExit("the restore did not bring the set back")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("platform")
    r = sub.add_parser("runbook")
    r.add_argument("name", choices=["INSTALL", "DECOMMISSION"])
    r.add_argument("--from", dest="start", type=int, default=1)
    s = sub.add_parser("stand-in")
    s.add_argument("runbook")
    s.add_argument("step")
    sub.add_parser("check")
    sub.add_parser("backup")
    rs = sub.add_parser("restore")
    rs.add_argument("--set")
    sub.add_parser("memory")
    sub.add_parser("change")
    sub.add_parser("restored")
    a = p.parse_args()
    os.chdir(CORE)
    if a.command == "platform":
        platform()
    elif a.command == "runbook":
        runbook(a.name, a.start)
    elif a.command == "stand-in":
        stand_in(a.runbook, a.step)
    elif a.command == "check":
        checks()
    elif a.command == "backup":
        backup()
    elif a.command == "restore":
        restore(a.set)
    elif a.command == "change":
        change()
    elif a.command == "restored":
        restored()
    elif a.command == "memory":
        memory()


if __name__ == "__main__":
    main()
