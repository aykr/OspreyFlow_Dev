"""P7's acceptance run on the kind cluster, the part before the test: what `harness.apply
--demo-analyst --seed hmp,fixture-corp,scenarios` does on a compose deployment, done to the
cloud-platform profile's namespace, which has no install of its own (ADR-148 Amendment 1, "Left").

Kind alone and never rendered: the platform's realm has no demo subjects (`harness.cluster` renders
`demo_analyst=False`), so they are imported here from the realm the harness renders with them, and
their passwords set as `apply` sets them. Synthetic data only (rule 9): the three seed datasets the
compose exit run uses, into one investigation made through the Conduit, as `apply` makes it.

Run on the server from OspreyFlow_Core by `p7_kind.sh accept`; it prints the env lines the
over-the-wire test reads.
"""

from __future__ import annotations

import base64
import json
import secrets
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from harness.cluster_install import REALM, SystemKube
from harness.keycloak_admin import admin_token, set_demo_admin_password, set_demo_analyst_password
from harness.realm import DEMO_ADMIN_SUBJECT, DEMO_ANALYST_SUBJECT, render_realm
from harness.render import load_config

DATASETS = ["hmp", "fixture-corp", "scenarios"]
SEEDS = {"hmp": "scripts.seed_hmp_fixture", "fixture-corp": "scripts.seed_fixture_corp",
         "scenarios": "scripts.seed_scenarios"}  # fmt: skip


def kubectl(namespace: str, *argv: str, stdin: bytes | None = None) -> str:
    done = subprocess.run(["kubectl", "-n", namespace, *argv], input=stdin, capture_output=True,
                          check=False)  # fmt: skip
    if done.returncode:
        raise SystemExit(f"kubectl {' '.join(argv)} failed: {done.stderr.decode()[-2000:]}")
    return done.stdout.decode()


def make_case(issuer: str, secret: str, api_url: str) -> str:
    """`harness.apply.create_investigation`'s request with the dataset the route has required
    since ADR-099 Amendment 12 (main's sends none, and is refused `dataset_refused`): a token
    exchanged for the realm's verify subject, then a case reading a new dataset of its own."""
    from demo_fixtures.datasets import domains_for
    from harness.realm import CONDUIT_CLIENT_ID, VERIFY_SUBJECT

    def post(url: str, data: bytes, headers: dict[str, str]) -> dict:
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())

    token_url = f"{issuer}/realms/{REALM}/protocol/openid-connect/token"
    form = {"Content-Type": "application/x-www-form-urlencoded"}
    own = post(token_url, urllib.parse.urlencode({"grant_type": "client_credentials",
               "client_id": CONDUIT_CLIENT_ID, "client_secret": secret}).encode(), form)  # fmt: skip
    exchanged = post(token_url, urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "client_id": CONDUIT_CLIENT_ID, "client_secret": secret,
        "subject_token": own["access_token"],
        "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "requested_subject": VERIFY_SUBJECT,
        "requested_token_type": "urn:ietf:params:oauth:token-type:access_token"}).encode(), form)  # fmt: skip
    body = {"domains": domains_for(DATASETS), "new_dataset_name": f"P7 acceptance {secrets.token_hex(3)} (synthetic)"}
    case = post(f"{api_url}/v1/investigations", json.dumps(body).encode(),
                {"Authorization": f"Bearer {exchanged['access_token']}",
                 "Content-Type": "application/json"})  # fmt: skip
    return str(case["id"])


def main(config_path: str, namespace: str, out: str) -> None:
    config = load_config(Path(config_path))
    data = json.loads(kubectl(namespace, "get", "secret", "ospreyflow-secrets", "-o", "jsonpath={.data}"))
    values = {k: base64.b64decode(v).decode() for k, v in data.items()}
    admin_user = values.get("OSPREY_KEYCLOAK_ADMIN", "admin")
    admin_password = values["OSPREY_KEYCLOAK_ADMIN_PASSWORD"]
    analyst_password, demo_admin_password = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    kube = SystemKube()

    with kube.port_forward(namespace, "service/keycloak", 8080) as port:
        issuer = f"http://127.0.0.1:{port}"
        # The demo subjects, their groups and roles, from the realm rendered with them.
        demo = render_realm(config, realm_name=REALM, demo_analyst=True)
        wanted = {DEMO_ANALYST_SUBJECT, DEMO_ADMIN_SUBJECT}
        body = {"ifResourceExists": "SKIP",
                "users": [u for u in demo.get("users", []) if u.get("username") in wanted],
                "groups": demo.get("groups", []), "roles": demo.get("roles", {})}  # fmt: skip
        token = admin_token(issuer=issuer, admin_user=admin_user, admin_password=admin_password)
        request = urllib.request.Request(
            f"{issuer}/admin/realms/{REALM}/partialImport", data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )  # fmt: skip
        with urllib.request.urlopen(request, timeout=60) as response:
            print("demo subjects imported:", json.loads(response.read())["added"], "added")
        for setter, password in ((set_demo_analyst_password, analyst_password),
                                 (set_demo_admin_password, demo_admin_password)):  # fmt: skip
            setter(issuer=issuer, realm=REALM, admin_user=admin_user,
                   admin_password=admin_password, password=password)  # fmt: skip
        with kube.port_forward(namespace, "service/api", 8000) as api:
            investigation = make_case(issuer, values["OSPREY_OIDC_CLIENT_SECRET"],
                                      f"http://127.0.0.1:{api}")  # fmt: skip
    print("investigation", investigation)

    # The seeds run in the Conduit's own pod, beside the stores it reaches, with `scripts/` copied
    # in (the image does not carry it, as on compose, where it is mounted read-only).
    pod = kubectl(namespace, "get", "pods", "-l", "app.kubernetes.io/name=api", "-o",
                  "jsonpath={.items[0].metadata.name}").strip()  # fmt: skip
    archive = subprocess.run(["tar", "-c", "--exclude=__pycache__", "scripts"], capture_output=True,
                             check=True).stdout  # fmt: skip
    kubectl(namespace, "exec", "-i", pod, "--", "sh", "-c",
            "rm -rf /tmp/p7-seed && mkdir -p /tmp/p7-seed && tar -x -C /tmp/p7-seed", stdin=archive)  # fmt: skip
    # As the verify subject's unit, which holds the case (the seeds' default, `unit-1`, does not,
    # and a composite joins only one unit's datasets).
    run = ["exec", pod, "--", "env", "PYTHONPATH=/tmp/p7-seed:/app:/app/packages",
           "OSPREY_ORG_UNIT=verify", "python", "-m"]  # fmt: skip
    # The drop folder is read-only to the Conduit (an operator places files there), so the synthetic
    # files go in through a pod of the Conduit's image mounting the shared claim's `ingest` writable,
    # beside its other mounters (the claim is ReadWriteOnce: the shared label's affinity).
    image = kubectl(namespace, "get", "pod", pod, "-o", "jsonpath={.spec.containers[0].image}")
    helper = {
        "apiVersion": "v1", "kind": "Pod",
        "metadata": {"name": "p7-ingest", "labels": {"ospreyflow.io/shared": "true"}},
        "spec": {
            "restartPolicy": "Never",
            "securityContext": {"runAsUser": 10001, "runAsGroup": 10001, "runAsNonRoot": True},
            "affinity": {"podAffinity": {"requiredDuringSchedulingIgnoredDuringExecution": [{
                "labelSelector": {"matchLabels": {"app.kubernetes.io/name": "api"}},
                "topologyKey": "kubernetes.io/hostname"}]}},
            "containers": [{
                "name": "p7-ingest", "image": image, "command": ["sleep", "600"],
                "securityContext": {"allowPrivilegeEscalation": False,
                                    "capabilities": {"drop": ["ALL"]}},
                "volumeMounts": [{"name": "shared", "subPath": "ingest",
                                  "mountPath": "/var/lib/osprey/ingest"}]}],
            "volumes": [{"name": "shared",
                         "persistentVolumeClaim": {"claimName": "ospreyflow-shared"}}],
        },
    }  # fmt: skip
    kubectl(namespace, "delete", "pod", "p7-ingest", "--ignore-not-found", "--wait=true")
    kubectl(namespace, "apply", "-f", "-", stdin=json.dumps(helper).encode())
    kubectl(namespace, "wait", "--for=condition=Ready", "pod/p7-ingest", "--timeout=180s")
    kubectl(namespace, "exec", "-i", "p7-ingest", "--", "sh", "-c",
            "rm -rf /tmp/p7-seed && mkdir -p /tmp/p7-seed && tar -x -C /tmp/p7-seed", stdin=archive)  # fmt: skip
    print(kubectl(namespace, "exec", "p7-ingest", "--", "env",
                  "PYTHONPATH=/tmp/p7-seed:/app:/app/packages", "python", "-m",
                  "scripts.seed_ingest_folder", "--ingest-root", "/var/lib/osprey/ingest").strip())  # fmt: skip
    kubectl(namespace, "delete", "pod", "p7-ingest", "--wait=false")
    for dataset in DATASETS:
        said = kubectl(namespace, *run, SEEDS[dataset], "--investigation-scope", investigation)
        for line in said.splitlines():
            if line.strip():
                print(f"  seed[{dataset}]: {line.strip()}")
    Path(out).write_text(
        f"OSPREY_DEMO_ANALYST_PASSWORD={analyst_password}\n"
        f"OSPREY_DEMO_ADMIN_PASSWORD={demo_admin_password}\n"
        f"OSPREY_LIVE_INVESTIGATION_ID={investigation}\n", encoding="utf-8")  # fmt: skip
    Path(out).chmod(0o600)
    print("written", out)


if __name__ == "__main__":
    main(*sys.argv[1:4])
