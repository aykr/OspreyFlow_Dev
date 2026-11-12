"""P9's driver on the kind cluster (`p9_kind.sh`; ADR-148 Amendment 7): the render cut to what a
backup touches, the S3 stand-in as a pod, the kind-only patches, and the runs themselves.

    roundtrip   seed ArcadeDB and ClickHouse, back up (the CronJob's own Job), destroy both, then
                restore that set, timed, and compare what the stores hold with what was seeded
    reds        the refusals at the real call site, each by a change the platform could make:
                the bucket's policy naming another role, the role without kms:GenerateDataKey, and
                the role's session expired between taking its credentials and ClickHouse's BACKUP

Every run writes its record (JSON) to `<state>/p9_<run>.json` and prints it: the times, the counts,
the lease named by the environment it ran under (rule 14), and each refusal's own words.

Nothing here is the product: the product is the render, the chart's template and the runner. What
this file adds is only what EKS gives and kind has not (IRSA, a CA S3 would not need) and the
stand-in's place on the cluster.
"""

# ruff: noqa: E501 - the scripts run inside the pods (STORES, EXPIRED, the levers) are sent as text, one statement a line.
from __future__ import annotations

import argparse
import base64
import copy
import datetime as dt
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
BUILD = HERE.parents[3]
STANDIN_CODE = BUILD / "tests" / "fixtures" / "cloud_platform" / "s3_standin.py"
CONFIG = HERE / "p9_kind_osprey.yaml"

ACCOUNT = "123456789012"
REGION = "eu-west-2"
KEY_ARN = f"arn:aws:kms:{REGION}:{ACCOUNT}:key/0f9e8d7c-0009-4000-8000-000000000009"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/ospreyflow-dev-backup"
OTHER_ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/ospreyflow-dev-service"
CLICKHOUSE_ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/ospreyflow-dev-backup-clickhouse"
STANDIN_NS = "platform-managed"
STANDIN_HOST = f"s3-standin.{STANDIN_NS}.svc.cluster.local"
STANDIN_PORT = 9443
STANDIN = f"https://{STANDIN_HOST}:{STANDIN_PORT}"
TOKEN_DIR = "/var/run/secrets/eks.amazonaws.com/serviceaccount"
CA_DIR = "/etc/standin-ca"
#: The names ClickHouse reaches S3 and STS by, as on the platform (its STS by the region in
#: AWS_DEFAULT_REGION, never an endpoint override): inside its pod, kind's are the stand-in's.
AWS_NAMES = (f"s3.{REGION}.amazonaws.com", f"sts.{REGION}.amazonaws.com")
KEPT = ("arcadedb", "clickhouse", "clickhouse-keeper")
#: The images those and the backups run: the only ones copied into the cluster's registry.
DEPLOYED_IMAGES = ("arcadedb", "clickhouse-server", "clickhouse-keeper", "api")
#: Memory on kind's 8 GB (the render's are the platform's): enough to run, not to measure speed by.
KIND_MEMORY = {"arcadedb": "2Gi", "clickhouse": "2Gi", "clickhouse-keeper": "512Mi"}
SEED_VERTICES = 5000
SEED_EDGES = 1000
SEED_ROWS = 200_000
SEED_FILES = 300


def sh(*args: str, stdin: str | None = None, check: bool = True) -> str:
    done = subprocess.run(args, input=stdin, capture_output=True, text=True)
    if check and done.returncode != 0:
        raise SystemExit(
            f"{' '.join(args[:6])} …: exit {done.returncode}\n{done.stdout[-2000:]}\n{done.stderr[-2000:]}"
        )
    return done.stdout


def kubectl(*args: str, stdin: str | None = None, check: bool = True) -> str:
    return sh("kubectl", *args, stdin=stdin, check=check)


def apply(document: dict[str, Any] | list[dict[str, Any]]) -> None:
    items = document if isinstance(document, list) else [document]
    kubectl(
        "apply", "-f", "-", stdin=json.dumps({"apiVersion": "v1", "kind": "List", "items": items})
    )


class Run:
    def __init__(self, state: Path, namespace: str, helm_script: str | None = None) -> None:
        self.state, self.ns, self.helm_script = state, namespace, helm_script
        self.out = state / "render"
        self.record: dict[str, Any] = {}
        self.restore_logs = ""

    # -- the render -------------------------------------------------------------------------------

    def values(self) -> dict[str, Any]:
        return yaml.safe_load((self.out / "values.yaml").read_text())

    def render(self, registry: str, resolve: str) -> None:
        """The profile's render, its backups as P9_render.diff calls them, cut to the stores."""
        from harness import cloud_platform_backups as backups
        from harness.cloud_platform import _in_registry
        from harness.cloud_platform.settings import load_platform
        from harness.images import registry_digest_resolver
        from harness.render import load_config, render

        self.out.mkdir(parents=True, exist_ok=True)
        raw = yaml.safe_load(CONFIG.read_text())
        raw["cloud_platform"]["registry"] = registry
        (self.state / "osprey.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
        config = load_config(self.state / "osprey.yaml")

        def in_kind(ref: str) -> str:
            reference, _, digest = ref.partition("@")
            target = _in_registry(reference, registry)
            if ":" not in reference.rsplit("/", 1)[-1] and digest:
                target += ":sha256-" + digest.removeprefix("sha256:")[:12]
            return target

        def deployed(ref: str) -> bool:
            return any(
                f"/{name}:" in str(ref) or f"/{name}@" in str(ref) for name in DEPLOYED_IMAGES
            )

        def resolver(ref: str) -> str | None:
            # Only the images deployed here have copies in the cluster's registry; the rest of the
            # render's are left unpinned (never deployed), and each deployed one is checked below.
            if resolve != "registry" or not deployed(ref):
                return None
            return registry_digest_resolver(in_kind(ref))

        result = render(config, resolver=resolver, allow_unpinned=True)
        values = yaml.safe_load(result.artefacts["values.yaml"])
        if "backups" not in values:  # P9_render.diff not applied: the one hook it adds
            assert config.cloud_platform is not None
            backups.add_backups(config, load_platform(config.cloud_platform.platform), values)
        values["workloads"] = [w for w in values["workloads"] if w["name"] in KEPT]
        values["jobs"] = []
        # The poc shape's Ingest root on a claim of its own, as P7b's render writes it (not on main
        # yet): the backups' claims run reads `storage.claims` (`shared_pod` makes the claim).
        values["storage"]["claims"] = [{"name": "ingest", "size": "1Gi"}]
        if resolve == "registry":
            images = [w["image"] for w in values["workloads"]] + [values["backups"]["image"]]
            unpinned = [i for i in images if "@sha256:" not in i]
            if unpinned:
                raise SystemExit(f"not pinned by the cluster registry's digest: {unpinned}")
        for w in values["workloads"]:
            memory = KIND_MEMORY[w["name"]]
            w["resources"] = {
                "requests": {"cpu": "100m", "memory": memory},
                "limits": {"memory": memory},
            }
            for e in w.get("env", []):
                if e["name"] == "ARCADEDB_OPTS_MEMORY":
                    e["value"] = "-Xms256M -Xmx1G -XX:+ExitOnOutOfMemoryError"
        values["backups"]["resources"] = {
            "requests": {"cpu": "100m", "memory": "512Mi"},
            "limits": {"memory": "1Gi"},
        }
        values["backups"]["arcadedb"]["resources"] = {
            "requests": {"cpu": "100m", "memory": "512Mi"},
            "limits": {"memory": "1Gi"},
        }
        (self.out / "values.yaml").write_text(yaml.safe_dump(values, sort_keys=False, width=4096))

        plan = yaml.safe_load(result.artefacts["images.yaml"])
        theirs = [
            i
            for i in plan["images"]
            if "source" in i
            and any(
                f"/{n}:" in i["target"] or f"/{n}@" in i["target"]
                for n in ("arcadedb", "clickhouse-server", "clickhouse-keeper")
            )
        ]
        ours = [
            i for i in plan["images"] if "dockerfile" in i and "/ospreyflow/api:" in i["target"]
        ]
        (self.out / "theirs.txt").write_text(
            "".join(f"{i['source']} {i['target']}\n" for i in theirs)
        )
        (self.out / "ours").mkdir(exist_ok=True)
        (self.out / "ours" / "images.yaml").write_text(
            yaml.safe_dump({"registry": plan["registry"], "images": ours})
        )
        print(
            f"rendered ({resolve}): {', '.join(w['name'] for w in values['workloads'])} and the backups; "
            f"{len(theirs)} of theirs, {len(ours)} of ours"
        )

    # -- the stand-in -----------------------------------------------------------------------------

    def bucket(self) -> str:
        return "ospreyflow-dev-backups"

    def standin_config(
        self,
        *,
        role_policy: dict[str, Any] | None = None,
        clickhouse_policy: dict[str, Any] | None = None,
        bucket_policy: dict[str, Any] | None = None,
        trusted_account: str | None = None,
        key_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """The AWS side as the namespace's Terraform makes it: each role trusted by its own trust
        document as rendered (`backups.trust_policy`, the cluster's issuer for the provider's),
        verified by the cluster's own keys, and given its own policy."""
        from harness import cloud_platform_backups as backups

        arn = f"arn:aws:s3:::{self.bucket()}"
        jwks = json.loads(kubectl("get", "--raw", "/openid/v1/jwks"))
        issuer = json.loads(kubectl("get", "--raw", "/.well-known/openid-configuration"))["issuer"]
        provider = f"arn:aws:iam::{ACCOUNT}:oidc-provider/{issuer.removeprefix('https://')}"
        policies = backups.role_policies(arn, KEY_ARN, REGION)
        roles = []
        for role_arn, account in ((ROLE_ARN, backups.SERVICE_ACCOUNT),
                                  (CLICKHOUSE_ROLE_ARN, backups.CLICKHOUSE_SERVICE_ACCOUNT)):  # fmt: skip
            subject = f"system:serviceaccount:{self.ns}:{trusted_account or account}"
            roles.append({
                "arn": role_arn, "issuer_secret": "unused: the cluster's keys are the trust",
                "subject": subject, "jwks": jwks, "issuer": issuer,
                "trust": backups.trust_policy(provider, issuer.removeprefix("https://"), subject),
                "policies": [(role_policy if role_arn == ROLE_ARN and role_policy
                              else clickhouse_policy if role_arn == CLICKHOUSE_ROLE_ARN and clickhouse_policy
                              else policies[account])],
            })  # fmt: skip
        return {
            "region": REGION,
            "roles": roles,
            "buckets": [{
                "name": self.bucket(), "kms_key": KEY_ARN,
                "policy": bucket_policy or backups.bucket_policy(arn, KEY_ARN, [ROLE_ARN, CLICKHOUSE_ROLE_ARN]),
            }],
            # The key's own policy as backups.tf writes it; KMS judges by it (the stand-in as AWS).
            "keys": [{"arn": KEY_ARN, "policy": key_policy or backups.key_policy(
                f"arn:aws:iam::{ACCOUNT}:root", [ROLE_ARN, CLICKHOUSE_ROLE_ARN], REGION)}],
        }  # fmt: skip

    def standin(self) -> None:
        ca = self.state / "standin-ca"
        if not (ca / "tls.crt").exists():
            ca.mkdir(parents=True, exist_ok=True)
            sh(
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "7",
                "-subj",
                "/CN=osprey-p9 stand-in CA",
                "-keyout",
                str(ca / "ca.key"),
                "-out",
                str(ca / "ca.crt"),
            )
            sh(
                "openssl",
                "req",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-subj",
                f"/CN={STANDIN_HOST}",
                "-keyout",
                str(ca / "tls.key"),
                "-out",
                str(ca / "tls.csr"),
            )
            (ca / "san").write_text(
                "subjectAltName=" + ",".join(f"DNS:{n}" for n in (STANDIN_HOST, *AWS_NAMES))
            )
            sh(
                "openssl",
                "x509",
                "-req",
                "-in",
                str(ca / "tls.csr"),
                "-CA",
                str(ca / "ca.crt"),
                "-CAkey",
                str(ca / "ca.key"),
                "-CAcreateserial",
                "-days",
                "7",
                "-extfile",
                str(ca / "san"),
                "-out",
                str(ca / "tls.crt"),
            )
        secret = lambda ns, name, files: {  # noqa: E731
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": name, "namespace": ns},
            "data": {f: base64.b64encode((ca / f).read_bytes()).decode() for f in files},
        }
        values = self.values()
        security = values.get("podSecurity") or {"user": 10001, "group": 10001}
        config = self.standin_config()
        (self.state / "standin.json").write_text(json.dumps(config))
        image = values["backups"]["image"]
        apply(
            [
                secret(STANDIN_NS, "standin-tls", ["tls.crt", "tls.key"]),
                secret(self.ns, "standin-ca", ["ca.crt"]),
                {
                    "apiVersion": "v1",
                    "kind": "ConfigMap",
                    "metadata": {"name": "s3-standin", "namespace": STANDIN_NS},
                    "data": {
                        "s3_standin.py": STANDIN_CODE.read_text(),
                        "standin.json": json.dumps(config),
                    },
                },
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": {"name": "s3-standin", "namespace": STANDIN_NS},
                    "spec": {
                        "replicas": 1,
                        "selector": {"matchLabels": {"app": "s3-standin"}},
                        "template": {
                            "metadata": {"labels": {"app": "s3-standin"}},
                            "spec": {
                                "securityContext": {
                                    "runAsNonRoot": True,
                                    "runAsUser": security["user"],
                                    "runAsGroup": security["group"],
                                },
                                "containers": [
                                    {
                                        "name": "s3-standin",
                                        "image": image,
                                        "command": [
                                            "/app/.venv/bin/python",
                                            "-I",
                                            "/code/s3_standin.py",
                                            "--config",
                                            "/code/standin.json",
                                            "--root",
                                            "/data",
                                            "--port",
                                            str(STANDIN_PORT),
                                            "--tls-cert",
                                            "/tls/tls.crt",
                                            "--tls-key",
                                            "/tls/tls.key",
                                        ],
                                        "env": [{"name": "S3_STANDIN_LOG", "value": "1"}],
                                        "ports": [{"containerPort": STANDIN_PORT}],
                                        "volumeMounts": [
                                            {"name": "code", "mountPath": "/code"},
                                            {"name": "tls", "mountPath": "/tls"},
                                            {"name": "data", "mountPath": "/data"},
                                        ],
                                    }
                                ],
                                "volumes": [
                                    {"name": "code", "configMap": {"name": "s3-standin"}},
                                    {"name": "tls", "secret": {"secretName": "standin-tls"}},
                                    {"name": "data", "emptyDir": {}},
                                ],
                            },
                        },
                    },
                },
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {"name": "s3-standin", "namespace": STANDIN_NS},
                    "spec": {
                        "selector": {"app": "s3-standin"},
                        # Its own port, and 443 for the AWS names ClickHouse uses (`patch`).
                        "ports": [
                            {"name": "standin", "port": STANDIN_PORT, "targetPort": STANDIN_PORT},
                            {"name": "https", "port": 443, "targetPort": STANDIN_PORT},
                        ],
                    },
                },
            ]
        )
        kubectl("-n", STANDIN_NS, "rollout", "restart", "deployment/s3-standin")
        kubectl("-n", STANDIN_NS, "rollout", "status", "deployment/s3-standin", "--timeout=300s")
        print(
            f"stand-in at {STANDIN}, trusting the cluster's issuer {config['roles'][0]['issuer']}"
        )

    def lever(self, path: str, body: dict[str, Any] | None = None) -> None:
        """The stand-in's own levers (`/_standin/configure`, `/_standin/expire`), from its pod."""
        code = (
            "import ssl, sys, urllib.request\n"
            "c = ssl.create_default_context(); c.check_hostname = False; c.verify_mode = ssl.CERT_NONE\n"
            f"r = urllib.request.Request('https://127.0.0.1:{STANDIN_PORT}{path}', data=sys.stdin.buffer.read(), method='POST')\n"
            "print(urllib.request.urlopen(r, context=c).status)\n"
        )
        kubectl(
            "-n",
            STANDIN_NS,
            "exec",
            "-i",
            "deployment/s3-standin",
            "--",
            "/app/.venv/bin/python",
            "-c",
            code,
            stdin=json.dumps(body or {}),
        )

    def configure(self, config: dict[str, Any]) -> None:
        self.lever("/_standin/configure", config)

    def bucket_objects(self) -> list[dict[str, Any]]:
        """What the stand-in holds in the backups bucket: each object's key, size and KMS key."""
        code = (
            "import json, pathlib\n"
            f"print(json.dumps([json.loads(p.read_text()) for p in pathlib.Path('/data/{self.bucket()}').glob('*.json')]))\n"
        )
        found: list[dict[str, Any]] = json.loads(
            kubectl(
                "-n",
                STANDIN_NS,
                "exec",
                "deployment/s3-standin",
                "--",
                "/app/.venv/bin/python",
                "-c",
                code,
            )
        )
        return found

    def finished_sets(self) -> list[str]:
        return sorted(
            o["key"].split("/")[1]
            for o in self.bucket_objects()
            if o["key"].endswith("/manifest.json")
        )

    # -- our secrets and the kind-only patches ----------------------------------------------------

    def secrets(self) -> None:
        from harness import cloud_platform_backups as backups

        s = self.values()["secrets"]
        copies = s.get("copies", {})
        data = {k: secrets.token_hex(16) for k in s["keys"] if k not in copies}
        data.update({k: data[original] for k, original in copies.items()})
        existing = kubectl(
            "-n", self.ns, "get", "secret", "ospreyflow-secrets", "-o", "json", check=False
        )
        if existing.strip():  # kept: the stores already hold its passwords
            data = {
                k: base64.b64decode(v).decode() for k, v in json.loads(existing)["data"].items()
            }
        encode = lambda d: {k: base64.b64encode(v.encode()).decode() for k, v in d.items()}  # noqa: E731
        kept = kubectl(
            "-n", self.ns, "get", "secret", backups.BACKUP_SECRET, "-o", "json", check=False
        )
        backup_password = (
            base64.b64decode(json.loads(kept)["data"][backups.BACKUP_SECRET_KEY]).decode()
            if kept.strip() else secrets.token_hex(16)
        )  # fmt: skip
        apply(
            [
                {
                    "apiVersion": "v1",
                    "kind": "Secret",
                    "metadata": {"name": "ospreyflow-secrets", "namespace": self.ns},
                    "data": encode(data),
                },
                # What the namespace's backups.tf writes: the backup user's password, a Secret of
                # its own (never the shared one), the output Secret, and the service accounts.
                {
                    "apiVersion": "v1",
                    "kind": "Secret",
                    "metadata": {"name": backups.BACKUP_SECRET, "namespace": self.ns},
                    "data": encode({backups.BACKUP_SECRET_KEY: backup_password}),
                },
                {
                    "apiVersion": "v1",
                    "kind": "Secret",
                    "metadata": {"name": backups.OUTPUT_SECRET, "namespace": self.ns},
                    "data": encode(
                        {
                            backups.OUTPUT_KEYS["bucket"]: self.bucket(),
                            backups.OUTPUT_KEYS["kms_key"]: KEY_ARN,
                        }
                    ),
                },
                *(
                    {
                        "apiVersion": "v1",
                        "kind": "ServiceAccount",
                        "metadata": {
                            "name": account,
                            "namespace": self.ns,
                            "annotations": {"eks.amazonaws.com/role-arn": role_arn},
                        },
                    }
                    for account, role_arn in (
                        (backups.SERVICE_ACCOUNT, ROLE_ARN),
                        (backups.CLICKHOUSE_SERVICE_ACCOUNT, CLICKHOUSE_ROLE_ARN),
                    )
                ),
            ]
        )

    def irsa(self, pod: dict[str, Any], image: str, role_arn: str = ROLE_ARN) -> None:
        """What EKS's pod identity webhook adds to a pod of the role's service account, and the
        stand-in's endpoints and CA: to each container of the Conduit's image."""
        volumes = pod.setdefault("volumes", [])
        if not any(v["name"] == "aws-iam-token" for v in volumes):
            volumes += [
                {
                    "name": "aws-iam-token",
                    "projected": {
                        "sources": [
                            {
                                "serviceAccountToken": {
                                    "audience": "sts.amazonaws.com",
                                    "expirationSeconds": 86400,
                                    "path": "token",
                                }
                            }
                        ]
                    },
                },
                {"name": "standin-ca", "secret": {"secretName": "standin-ca"}},
            ]
        env = [
            {"name": "AWS_ROLE_ARN", "value": role_arn},
            {"name": "AWS_WEB_IDENTITY_TOKEN_FILE", "value": f"{TOKEN_DIR}/token"},
            {"name": "AWS_STS_REGIONAL_ENDPOINTS", "value": "regional"},
            {"name": "AWS_ENDPOINT_URL_S3", "value": STANDIN},
            {"name": "AWS_ENDPOINT_URL_STS", "value": STANDIN},
            {"name": "AWS_CA_BUNDLE", "value": f"{CA_DIR}/ca.crt"},
        ]
        for container in pod.get("initContainers", []) + pod["containers"]:
            if container["image"] != image:
                continue
            names = {e["name"] for e in env}
            container["env"] = [e for e in container.get("env", []) if e["name"] not in names] + env
            mounts = [
                m
                for m in container.get("volumeMounts", [])
                if m["name"] not in ("aws-iam-token", "standin-ca")
            ]
            container["volumeMounts"] = mounts + [
                {"name": "aws-iam-token", "mountPath": TOKEN_DIR, "readOnly": True}
            ]
            if not any(m["mountPath"] == CA_DIR for m in mounts):
                container["volumeMounts"].append(
                    {"name": "standin-ca", "mountPath": CA_DIR, "readOnly": True}
                )

    def patch(self) -> None:
        image = self.values()["backups"]["image"]
        cron = json.loads(
            kubectl("-n", self.ns, "get", "cronjob", "ospreyflow-backup", "-o", "json")
        )
        self.irsa(cron["spec"]["jobTemplate"]["spec"]["template"]["spec"], image)
        kubectl("replace", "-f", "-", stdin=json.dumps(cron))
        # ClickHouse reaches S3 itself (the BACKUP statement): the stand-in's CA in its openSSL client.
        xml = (
            f"<clickhouse><openSSL><client><caConfig>{CA_DIR}/ca.crt</caConfig>"
            "<loadDefaultCAFile>true</loadDefaultCAFile><verificationMode>strict</verificationMode>"
            "</client></openSSL></clickhouse>\n"
        )
        apply(
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {"name": "p9-clickhouse-ca", "namespace": self.ns},
                "data": {"standin-ca.xml": xml},
            }
        )
        sts = json.loads(kubectl("-n", self.ns, "get", "statefulset", "clickhouse", "-o", "json"))
        pod = sts["spec"]["template"]["spec"]
        container = next(c for c in pod["containers"] if c["name"] == "clickhouse")
        pod["volumes"] = [
            v for v in pod.get("volumes", []) if v["name"] not in ("p9-ca", "p9-ca-config")
        ] + [
            {"name": "p9-ca", "secret": {"secretName": "standin-ca"}},
            {"name": "p9-ca-config", "configMap": {"name": "p9-clickhouse-ca"}},
        ]
        container["volumeMounts"] = [
            m
            for m in container.get("volumeMounts", [])
            if m["name"] not in ("p9-ca", "p9-ca-config")
        ] + [
            {"name": "p9-ca", "mountPath": CA_DIR, "readOnly": True},
            {
                "name": "p9-ca-config",
                "mountPath": "/etc/clickhouse-server/config.d/standin-ca.xml",
                "subPath": "standin-ca.xml",
                "readOnly": True,
            },
        ]
        # ClickHouse runs as the backup role (the render's serviceAccountName): what EKS's webhook
        # adds for that, and the AWS names as the stand-in inside its pod.
        self.irsa(pod, container["image"], CLICKHOUSE_ROLE_ARN)
        address = kubectl(
            "-n", STANDIN_NS, "get", "service", "s3-standin", "-o", "jsonpath={.spec.clusterIP}"
        ).strip()
        pod["hostAliases"] = [{"ip": address, "hostnames": list(AWS_NAMES)}]
        kubectl("replace", "-f", "-", stdin=json.dumps(sts))
        for claims in kubectl("-n", self.ns, "get", "cronjob", "-o", "name").split():
            if claims.endswith("/ospreyflow-backup-claims"):
                cron = json.loads(kubectl("-n", self.ns, "get", claims, "-o", "json"))
                self.irsa(cron["spec"]["jobTemplate"]["spec"]["template"]["spec"], image)
                kubectl("replace", "-f", "-", stdin=json.dumps(cron))
        self.shared_pod()
        print(
            "patched: the backups' and ClickHouse's IRSA; ClickHouse's AWS names and the stand-in's "
            "CA; the Ingest root's claim and a shared pod on it"
        )

    # -- the stores, from a pod of the deployment -------------------------------------------------

    def probe(self, code: str) -> str:
        if not kubectl(
            "-n", self.ns, "get", "pod", "p9-probe", "--ignore-not-found", "-o", "name"
        ).strip():
            values = self.values()
            security = values.get("podSecurity") or {"user": 10001, "group": 10001}
            env = [
                {"name": n, "valueFrom": {"secretKeyRef": {"name": "ospreyflow-secrets", "key": n}}}
                for n in ("ARCADEDB_ROOT_PASSWORD", "CLICKHOUSE_PASSWORD")
            ]
            env.append(
                {"name": "CLICKHOUSE_USER", "value": values["environment"]["CLICKHOUSE_USER"]}
            )
            apply(
                {
                    "apiVersion": "v1",
                    "kind": "Pod",
                    "metadata": {
                        "name": "p9-probe",
                        "namespace": self.ns,
                        "labels": {"app.kubernetes.io/part-of": "ospreyflow"},
                    },
                    "spec": {
                        "securityContext": {
                            "runAsNonRoot": True,
                            "runAsUser": security["user"],
                            "runAsGroup": security["group"],
                        },
                        "containers": [
                            {
                                "name": "probe",
                                "image": values["backups"]["image"],
                                "env": env,
                                "command": [
                                    "/app/.venv/bin/python",
                                    "-c",
                                    "import time; time.sleep(10**9)",
                                ],
                            }
                        ],
                    },
                }
            )
            kubectl(
                "-n", self.ns, "wait", "--for=condition=Ready", "pod/p9-probe", "--timeout=300s"
            )
        return kubectl(
            "-n",
            self.ns,
            "exec",
            "-i",
            "p9-probe",
            "--",
            "/app/.venv/bin/python",
            "-",
            stdin=STORES + code,
        )

    # -- the poc shape's claim of its own (P7b's `ospreyflow-ingest`, emulated) ------------------

    def shared_pod(self) -> None:
        """What P7b's render gives the poc shape and main's chart has not yet: the Ingest root's
        claim (`ospreyflow-ingest`, ReadWriteOnce) and a pod of the shared folders mounting it
        (`ospreyflow.io/shared`), standing for the Conduit and the workers."""
        values = self.values()
        security = values.get("podSecurity") or {"user": 10001, "group": 10001}
        # The chart makes the claim itself since P7b (`storage.claims`); made here only if missing.
        if not kubectl("-n", self.ns, "get", "pvc", "ospreyflow-ingest", "--ignore-not-found", "-o", "name").strip():
            apply(
                {
                    "apiVersion": "v1",
                    "kind": "PersistentVolumeClaim",
                    "metadata": {"name": "ospreyflow-ingest", "namespace": self.ns},
                    "spec": {
                        "accessModes": ["ReadWriteOnce"],
                        "storageClassName": values["storage"]["className"],
                        "resources": {"requests": {"storage": "1Gi"}},
                    },
                }
            )
        if kubectl(
            "-n", self.ns, "get", "pod", "p9-shared", "--ignore-not-found", "-o", "name"
        ).strip():
            return
        apply(
            {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {
                    "name": "p9-shared",
                    "namespace": self.ns,
                    # The Conduit's labels, as the restore's writers check finds the Conduit.
                    "labels": {
                        "app.kubernetes.io/part-of": "ospreyflow",
                        "app.kubernetes.io/name": "api",
                        "ospreyflow.io/shared": "true",
                    },
                },
                "spec": {
                    "securityContext": {
                        "runAsNonRoot": True,
                        "runAsUser": security["user"],
                        "runAsGroup": security["group"],
                        "fsGroup": security["group"],
                    },
                    "containers": [
                        {
                            "name": "shared",
                            "image": values["backups"]["image"],
                            "command": [
                                "/app/.venv/bin/python",
                                "-c",
                                "import time; time.sleep(10**9)",
                            ],
                            "volumeMounts": [{"name": "ingest", "mountPath": "/claims/ingest"}],
                        }
                    ],
                    "volumes": [
                        {
                            "name": "ingest",
                            "persistentVolumeClaim": {"claimName": "ospreyflow-ingest"},
                        }
                    ],
                },
            }
        )
        kubectl("-n", self.ns, "wait", "--for=condition=Ready", "pod/p9-shared", "--timeout=300s")

    def stop_shared(self) -> None:
        kubectl("-n", self.ns, "delete", "pod", "p9-shared", "--ignore-not-found", "--wait=true")

    def in_shared(self, code: str) -> str:
        return kubectl(
            "-n",
            self.ns,
            "exec",
            "-i",
            "p9-shared",
            "--",
            "/app/.venv/bin/python",
            "-",
            stdin=CLAIMS + code,
        )

    # -- the stores -------------------------------------------------------------------------------

    def seed(self) -> dict[str, Any]:
        out = self.probe(
            f"seed({SEED_VERTICES}, {SEED_EDGES}, {SEED_ROWS}); print(json.dumps(counts()))"
        )
        found: dict[str, Any] = json.loads(out.strip().splitlines()[-1])
        found["claims"] = json.loads(
            self.in_shared(f"seed({SEED_FILES}); print(json.dumps(tree()))")
            .strip()
            .splitlines()[-1]
        )
        print("seeded:", found)
        return found

    def counts(self) -> dict[str, Any]:
        found: dict[str, Any] = json.loads(
            self.probe("print(json.dumps(counts()))").strip().splitlines()[-1]
        )
        found["claims"] = json.loads(
            self.in_shared("print(json.dumps(tree()))").strip().splitlines()[-1]
        )
        return found

    def destroy(self) -> dict[str, Any]:
        self.probe("destroy()")
        self.in_shared("destroy()")
        left = self.counts()
        print("destroyed; the stores now hold:", left)
        return left

    # -- jobs -------------------------------------------------------------------------------------

    def wait_job(self, name: str, timeout: float = 1800) -> tuple[bool, str]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = json.loads(kubectl("-n", self.ns, "get", "job", name, "-o", "json")).get(
                "status", {}
            )
            done = {c["type"] for c in status.get("conditions", []) if c.get("status") == "True"}
            if done & {"Complete", "Failed"}:
                logs = kubectl(
                    "-n",
                    self.ns,
                    "logs",
                    f"job/{name}",
                    "--all-containers",
                    "--prefix",
                    check=False,
                )
                return "Complete" in done, logs
            time.sleep(2)
        raise SystemExit(f"job {name} neither finished nor failed in {timeout} s")

    def start_from_cron(
        self,
        name: str,
        cron: str = "ospreyflow-backup",
        *,
        command: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        """A Job of `cron`'s, named as the CronJob would name it for a slot (`<cron>-<minute>`),
        its command or settings changed only where a refusal case says so."""
        kubectl("-n", self.ns, "delete", "job", name, "--ignore-not-found", "--wait=true")
        if command is None and env is None:
            kubectl("-n", self.ns, "create", "job", name, f"--from=cronjob/{cron}")
            return
        spec = copy.deepcopy(
            json.loads(kubectl("-n", self.ns, "get", "cronjob", cron, "-o", "json"))["spec"][
                "jobTemplate"
            ]["spec"]
        )
        spec["backoffLimit"] = 0
        container = spec["template"]["spec"]["containers"][0]
        if command is not None:
            container["command"] = command
        for key, value in (env or {}).items():
            container["env"] = [e for e in container.get("env", []) if e["name"] != key] + [
                {"name": key, "value": value}
            ]
        apply(
            {
                "apiVersion": "batch/v1",
                "kind": "Job",
                "metadata": {"name": name, "namespace": self.ns},
                "spec": spec,
            }
        )

    def backup(self, slot: int | None = None) -> tuple[bool, str, str]:
        """Both runs of one slot, as the two CronJobs start them; the set's name and the logs."""
        slot = slot or int(time.time() // 60)
        main, claims = f"ospreyflow-backup-{slot}", f"ospreyflow-backup-claims-{slot}"
        self.start_from_cron(main)
        self.start_from_cron(claims, "ospreyflow-backup-claims")
        ok_main, logs_main = self.wait_job(main)
        ok_claims, logs_claims = self.wait_job(claims)
        logs = logs_main + logs_claims
        print(f"backup {slot}: {'succeeded' if ok_main and ok_claims else 'FAILED'}\n{logs}")
        return (
            ok_main and ok_claims,
            logs,
            dt.datetime.fromtimestamp(slot * 60, dt.UTC).strftime("%Y%m%dT%H%M%SZ"),
        )

    def restore_api_path(self, present: bool) -> None:
        """Kind alone: the restore's pods' path to the cluster's API, as P7b's per-workload egress
        row will give it (a Calico Allow to the `kubernetes` Service, before the deny). P9 renders
        none of its own (the orchestrator's ruling); without it every restore refuses, closed."""
        name = "default.p9-kind-restore-to-the-api"
        if not present:
            kubectl(
                "-n",
                self.ns,
                "delete",
                "networkpolicies.projectcalico.org",
                name,
                "--ignore-not-found",
            )
            return
        apply({
            "apiVersion": "projectcalico.org/v3", "kind": "NetworkPolicy",
            "metadata": {"name": name, "namespace": self.ns},
            "spec": {"tier": "default", "order": 150,
                     "selector": "app.kubernetes.io/name in {'restore', 'restore-claims'}",
                     "types": ["Egress"],
                     "egress": [{"action": "Allow", "protocol": "TCP",
                                 "destination": {"services": {"name": "kubernetes", "namespace": "default"}}}]},
        })  # fmt: skip

    def restore(self, set_id: str) -> dict[str, float]:
        """ArcadeDB and the shared pods stopped, the restore's two Jobs (rendered as an operator
        does) run, then both started again: each phase timed."""
        assert self.helm_script
        times: dict[str, float] = {}
        self.restore_api_path(True)
        start = time.monotonic()
        kubectl("-n", self.ns, "scale", "statefulset/arcadedb", "--replicas=0")
        self.stop_shared()
        kubectl(
            "-n", self.ns, "wait", "--for=delete", "pod/arcadedb-0", "--timeout=300s", check=False
        )
        times["stopped"] = round(time.monotonic() - start, 1)
        documents = [
            d for d in yaml.safe_load_all(sh("bash", self.helm_script, "restore-job", set_id)) if d
        ]
        jobs = [d for d in documents if d["kind"] == "Job"]
        assert len(jobs) == 2, [j["metadata"]["name"] for j in jobs]
        for job in jobs:
            self.irsa(job["spec"]["template"]["spec"], self.values()["backups"]["image"])
            job["metadata"]["namespace"] = self.ns
            kubectl(
                "-n",
                self.ns,
                "delete",
                "job",
                job["metadata"]["name"],
                "--ignore-not-found",
                "--wait=true",
            )
            apply(job)
        self.restore_logs = ""
        for job in jobs:
            name = job["metadata"]["name"]
            ok, logs = self.wait_job(name)
            self.restore_logs += logs
            times[name] = round(time.monotonic() - start - times["stopped"], 1)
            print(f"{name}: {'succeeded' if ok else 'FAILED'}\n{logs}")
            if not ok:
                # The stores started again first, so a later step does not meet ArcadeDB scaled to
                # nothing (round 3's first run: a name that did not resolve, after this failure).
                kubectl("-n", self.ns, "scale", "statefulset/arcadedb", "--replicas=1")
                self.shared_pod()
                kubectl("-n", self.ns, "rollout", "status", "statefulset/arcadedb", "--timeout=900s", check=False)
                raise SystemExit(f"the restore Job {name} failed")
        restarted = time.monotonic()
        kubectl("-n", self.ns, "scale", "statefulset/arcadedb", "--replicas=1")
        self.shared_pod()
        kubectl("-n", self.ns, "rollout", "status", "statefulset/arcadedb", "--timeout=900s")
        kubectl("-n", self.ns, "wait", "--for=condition=Ready", "pod/arcadedb-0", "--timeout=900s")
        times["started"] = round(time.monotonic() - restarted, 1)
        times["total"] = round(time.monotonic() - start, 1)
        return times

    # -- a restore beside live databases (the orchestrator's review of 7916044, item 4) ------------

    def change(self, tag: str) -> dict[str, Any]:
        """The live stores moved on since the set: people, rows and a file it does not hold."""
        self.probe(f"change({tag!r})")
        self.in_shared(f"change({tag!r})")
        found = self.counts()
        print(f"changed ({tag}):", found)
        return found

    def leftovers(self) -> dict[str, Any]:
        """Anything a restore left beside the live data: ArcadeDB's `<db>.restoring` or `.before`,
        ClickHouse's `_restoring_` or `_before_` databases, the claim's `.osprey-` folders."""
        folder = kubectl("-n", self.ns, "exec", "arcadedb-0", "--", "ls", "-a", "/home/arcadedb/databases")
        names = json.loads(self.probe("print(json.dumps(databases()))").strip().splitlines()[-1])
        claims = json.loads(self.in_shared("print(json.dumps(leftovers()))").strip().splitlines()[-1])
        return {
            "arcadedb": sorted(n for n in folder.split() if n.endswith((".restoring", ".before"))),
            "clickhouse": [n for n in names if "_restoring_" in n or "_before_" in n],
            "claims": claims,
        }

    def plant_truncated_zip(self, set_id: str) -> None:
        """The set's ArcadeDB zip cut to half and its manifest made to match (a zip written while
        the claim filled, say): `verify` and `fetch-graph` pass it, ArcadeDB's own restore fails
        part-way. The originals kept beside the bucket, put back by `unplant_zip`."""
        self._standin_store(
            "saved = root.parent / 'p9-saved'; saved.mkdir(exist_ok=True)\n"
            "def at(key): return root / hashlib.sha256(key.encode()).hexdigest()\n"
            "mkey = f'sets/{a[0]}/manifest.json'\n"
            "manifest = json.loads(at(mkey).read_bytes())\n"
            "zkey = manifest['arcadedb']['key']\n"
            "for key, name in ((mkey, 'manifest'), (zkey, 'zip')):\n"
            "    (saved / name).write_bytes(at(key).read_bytes())\n"
            "    (saved / (name + '.json')).write_text(at(key).with_suffix('.json').read_text())\n"
            "def put(key, body):\n"
            "    at(key).write_bytes(body)\n"
            "    meta = json.loads(at(key).with_suffix('.json').read_text())\n"
            "    meta.update(size=len(body), etag=hashlib.md5(body, usedforsecurity=False).hexdigest())\n"
            "    at(key).with_suffix('.json').write_text(json.dumps(meta))\n"
            "half = at(zkey).read_bytes()[: at(zkey).stat().st_size // 2]\n"
            "put(zkey, half)\n"
            "manifest['arcadedb'].update(bytes=len(half), sha256=hashlib.sha256(half).hexdigest())\n"
            "put(mkey, json.dumps(manifest, indent=2).encode())\n",
            [set_id],
        )

    def unplant_zip(self, set_id: str) -> None:
        self._standin_store(
            "saved = root.parent / 'p9-saved'\n"
            "def at(key): return root / hashlib.sha256(key.encode()).hexdigest()\n"
            "mkey = f'sets/{a[0]}/manifest.json'\n"
            "zkey = json.loads((saved / 'zip.json').read_text())['key']\n"
            "for key, name in ((mkey, 'manifest'), (zkey, 'zip')):\n"
            "    at(key).write_bytes((saved / name).read_bytes())\n"
            "    at(key).with_suffix('.json').write_text((saved / (name + '.json')).read_text())\n"
            "import shutil; shutil.rmtree(saved)\n",
            [set_id],
        )

    def restore_expecting_failure(self, set_id: str) -> str:
        try:
            self.restore(set_id)
        except SystemExit as failed:
            return str(failed)
        return "the restore finished"

    def live_restore(self) -> None:
        """A restore of a set beside live databases changed since it (rule 15: every kind restore
        before ran after `destroy`): it comes back as the set, nothing left beside it; then two
        failures planted part-way, each leaving the live database it was meant to protect."""
        from harness import cloud_platform_backups as backups

        self.shared_pod()
        seeded = self.seed()
        ok, logs, set_id = self.backup()
        if not ok:
            raise SystemExit("the backup failed")
        stores = ("arcadedb_vertices", "arcadedb_edges", "clickhouse_rows")
        same = lambda a, b, keys=stores: all(a.get(k) == b.get(k) for k in keys)  # noqa: E731
        record: dict[str, Any] = {"set": set_id, "seeded": seeded}
        # 1. Beside live databases changed since the set: both swaps run (ArcadeDB's rename on its
        #    claim, ClickHouse's RENAME), and the stores and the claim come back as the set.
        changed = self.change("a")
        assert not same(changed, seeded), "the change did not change the stores"
        record["swap"] = {"changed": changed, "seconds": self.restore(set_id)}
        record["swap"]["restored"] = self.counts()
        record["swap"]["leftovers"] = self.leftovers()
        record["swap"]["as_the_set"] = record["swap"]["restored"] == seeded
        # 2. ArcadeDB's restore failing part-way (a truncated zip its manifest matches): the restore
        #    Job fails in restore-graph; ArcadeDB and ClickHouse are as they were changed.
        changed = self.change("b")
        self.plant_truncated_zip(set_id)
        try:
            said = self.restore_expecting_failure(set_id)
        finally:
            self.unplant_zip(set_id)
        after = self.counts()
        record["arcadedb_planted"] = {
            "changed": changed, "after": after, "said": said, "restore_graph": self.last_logs("restore-graph"),
            "leftovers": self.leftovers(), "stores_untouched": same(after, changed),
        }  # fmt: skip
        # 3. ClickHouse's RESTORE refused part-way (its role without s3:GetObject, after `verify`
        #    passed as the runner): ClickHouse's live database stays; ArcadeDB's swap had finished.
        changed = self.change("c")
        arn = f"arn:aws:s3:::{self.bucket()}"
        refused = backups.role_policies(arn, KEY_ARN, REGION)[backups.CLICKHOUSE_SERVICE_ACCOUNT]
        for statement in refused["Statement"]:
            if isinstance(statement.get("Action"), list):
                statement["Action"] = [a for a in statement["Action"] if a != "s3:GetObject"]
        self.configure(self.standin_config(clickhouse_policy=refused))
        try:
            said = self.restore_expecting_failure(set_id)
        finally:
            self.configure(self.standin_config())
        after = self.counts()
        record["clickhouse_planted"] = {
            "changed": changed, "after": after, "said": said,
            "restore_analytics": self.last_logs("restore-analytics"), "leftovers": self.leftovers(),
            "clickhouse_untouched": after.get("clickhouse_rows") == changed.get("clickhouse_rows"),
            "arcadedb_restored": same(after, seeded, ("arcadedb_vertices", "arcadedb_edges")),
        }  # fmt: skip
        # Every live test removes what it writes: the set from the stand-in.
        self.remove_copies([f"sets/{set_id}/"])
        empty = {"arcadedb": [], "clickhouse": [], "claims": []}
        passed = (record["swap"]["as_the_set"] and record["swap"]["leftovers"] == empty
                  and record["arcadedb_planted"]["stores_untouched"]
                  and record["arcadedb_planted"]["leftovers"]["arcadedb"] == []
                  and "restore-graph refused" in record["arcadedb_planted"]["restore_graph"]
                  and record["clickhouse_planted"]["clickhouse_untouched"]
                  and record["clickhouse_planted"]["arcadedb_restored"]
                  and record["clickhouse_planted"]["leftovers"]["clickhouse"] == [])  # fmt: skip
        record["pass"] = passed
        self.record = {"live_restore": record}
        self.save("live_restore")
        print(f"{'PASS' if passed else 'FAIL'} a restore beside live databases, and two failures part-way")
        if not passed:
            raise SystemExit("FAIL: see the record")

    def last_logs(self, container: str) -> str:
        """The named container's words in the latest restore's logs (`restore` keeps them)."""
        return "\n".join(line for line in self.restore_logs.splitlines() if f"/{container}]" in line)[-2000:]

    # -- the runs ---------------------------------------------------------------------------------

    def lease(self) -> dict[str, str]:
        """The lease this run was taken under (rule 14), as `stack_lease.sh remote` mirrors it: its
        own info file under OSPREY_LEASE_DIR, read here, never named by the caller. An offline run's
        lease directory is empty, and that is said so."""
        folder = Path(os.environ.get("OSPREY_LEASE_DIR", "/nonexistent"))
        found = {p.parent.name: p.read_text().strip() for p in sorted(folder.glob("*/info"))}
        return found or {"lease": f"none ({folder} holds no lease): not a timing run"}

    def save(self, run: str) -> None:
        self.record["at"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        self.record["host"] = os.uname().nodename
        self.record["lease"] = self.lease()
        path = self.state / f"p9_{run}.json"
        path.write_text(json.dumps(self.record, indent=2))
        print(f"== record ({path})\n{json.dumps(self.record, indent=2)}")

    def roundtrip(self) -> None:
        self.shared_pod()
        seeded = self.seed()
        before = set(self.finished_sets())
        started = time.monotonic()
        ok, logs, set_id = self.backup()
        backup_seconds = round(time.monotonic() - started, 1)
        if not ok:
            raise SystemExit("the backup failed")
        new = sorted(set(self.finished_sets()) - before)
        assert new == [set_id], f"the slot's set {set_id} expected, found {new}"
        objects = [o for o in self.bucket_objects() if o["key"].startswith(f"sets/{set_id}/")]
        unencrypted = [o["key"] for o in objects if o.get("kms_key") != KEY_ARN]
        self.record["backup"] = {
            "set": set_id,
            "seconds": backup_seconds,
            "objects": len(objects),
            "bytes": sum(o["size"] for o in objects),
            "not_under_the_key": unencrypted,
            "claims_part": [o["key"] for o in objects if "/claims/" in o["key"]],
            "log": [line for line in logs.splitlines() if "backup" in line and "set " in line],
        }
        self.record["destroyed"] = self.destroy()
        times = self.restore(set_id)
        after = self.counts()
        self.record.update(
            {
                "seeded": seeded,
                "restored": after,
                "restore_seconds": times,
                "match": after == seeded and not unencrypted,
            }
        )
        self.save("roundtrip")
        if not self.record["match"]:
            raise SystemExit(
                "FAIL: the restored stores differ from the seed, or an object was not under the key"
            )
        print(
            f"PASS round trip: set {set_id} restored in {times['total']} s, counts and the claim equal"
        )

    def restore_refused(self) -> None:
        """The orchestrator's ruling, on kind: with no path from the restore's pods to the cluster's
        API (P9 renders no Calico policy of its own; P7b's row is to come), the restore's `verify`
        cannot list the pods and refuses, "cannot confirm the writers are stopped", touching nothing.
        Everything that writes is stopped first, as the runbook says, so only that can refuse it."""
        assert self.helm_script
        self.shared_pod()
        if (
            not self.finished_sets()
        ):  # the stand-in's objects go with its pod: a set of its own first
            self.seed()
            ok, _, _ = self.backup()
            assert ok, "the backup this check restores failed"
        self.restore_api_path(False)
        before = self.counts()
        set_id = self.finished_sets()[-1]
        kubectl("-n", self.ns, "scale", "statefulset/arcadedb", "--replicas=0")
        self.stop_shared()
        kubectl(
            "-n", self.ns, "wait", "--for=delete", "pod/arcadedb-0", "--timeout=300s", check=False
        )
        documents = [
            d for d in yaml.safe_load_all(sh("bash", self.helm_script, "restore-job", set_id)) if d
        ]
        jobs = [d for d in documents if d["kind"] == "Job"]
        said: list[str] = []
        try:
            for job in jobs:
                self.irsa(job["spec"]["template"]["spec"], self.values()["backups"]["image"])
                job["metadata"]["namespace"] = self.ns
                kubectl(
                    "-n",
                    self.ns,
                    "delete",
                    "job",
                    job["metadata"]["name"],
                    "--ignore-not-found",
                    "--wait=true",
                )
                apply(job)
            for job in jobs:
                ok, _ = self.wait_job(job["metadata"]["name"], timeout=600)
                # The refusal is the `verify` init container's: read it there.
                for pod in kubectl("-n", self.ns, "get", "pods", "-l", f"job-name={job['metadata']['name']}",
                                   "-o", "name").split():  # fmt: skip
                    said += [line for line in kubectl("-n", self.ns, "logs", pod, "-c", "verify", check=False).splitlines()
                             if "refused" in line]  # fmt: skip
                assert not ok, (
                    f"{job['metadata']['name']} ran without confirming the writers were stopped"
                )
        finally:
            kubectl("-n", self.ns, "scale", "statefulset/arcadedb", "--replicas=1")
            self.shared_pod()
            kubectl("-n", self.ns, "rollout", "status", "statefulset/arcadedb", "--timeout=900s")
            kubectl(
                "-n", self.ns, "wait", "--for=condition=Ready", "pod/arcadedb-0", "--timeout=900s"
            )
        after = self.counts()
        self.record.update({"set": set_id, "refused": said, "untouched": after == before})
        self.save("restore_refused")
        if not (
            said
            and all("cannot confirm the writers are stopped" in s for s in said)
            and after == before
        ):
            raise SystemExit("FAIL: the restore did not refuse closed, or something was touched")
        print("PASS the restore refused closed in both Jobs; the stores untouched")

    def osprey_sources(self, record_as: str = "osprey_sources") -> None:
        """The orchestrator's blocker, after the fix: as the deployment's own ClickHouse user, each of
        the four that were accepted on 11 November (a set's manifest read, ArcadeDB's zip read, a set
        overwritten, url() to another host) is refused; and ClickHouse's own pod reaches no outside
        address (its egress, platform's policy)."""
        base = f"https://{AWS_NAMES[0]}/{self.bucket()}"
        finished = self.finished_sets()
        assert finished, "a finished set first (the round trip), so RESTORE has a part to read"
        restore_url = f"{base}/sets/{finished[-1]}/clickhouse/"
        # A whole ClickHouse backup put under ArcadeDB's and the claims' prefixes (the stand-in's
        # own store, removed after): there, a refusal can only be the role's access, since a
        # missing backup and a refused one read alike to ClickHouse (BACKUP_NOT_FOUND, round 3).
        copies = self.copy_part(finished[-1])
        try:
            out = self._osprey_queries(base, restore_url, copies)
        finally:
            self.remove_copies(copies)
        self._judge_osprey(out, record_as)

    def copy_part(self, set_id: str) -> list[str]:
        prefixes = [f"sets/{set_id}/arcadedb/p9-bound/", f"sets/{set_id}/claims/p9-bound/"]
        self._standin_store(
            "src = f'sets/{a[0]}/clickhouse/'\n"
            "n = 0\n"
            "for m in [json.loads(p.read_text()) for p in root.glob('*.json')]:\n"
            "    if m['key'].startswith(src):\n"
            "        for prefix in a[1:]:\n"
            "            key = prefix + m['key'][len(src):]\n"
            "            path = root / hashlib.sha256(key.encode()).hexdigest()\n"
            "            path.write_bytes((root / hashlib.sha256(m['key'].encode()).hexdigest()).read_bytes())\n"
            "            path.with_suffix('.json').write_text(json.dumps({**m, 'key': key}))\n"
            "        n += 1\n"
            "assert n, 'no ClickHouse part to copy'\n",
            [set_id, *prefixes],
        )
        return prefixes

    def remove_copies(self, prefixes: list[str]) -> None:
        self._standin_store(
            "for p in list(root.glob('*.json')):\n"
            "    if json.loads(p.read_text())['key'].startswith(tuple(a)):\n"
            "        p.with_suffix('').unlink(missing_ok=True); p.unlink()\n",
            prefixes,
        )
        left = [o["key"] for o in self.bucket_objects() if o["key"].startswith(tuple(prefixes))]
        assert not left, left

    def _standin_store(self, code: str, args: list[str]) -> None:
        kubectl(
            "-n", STANDIN_NS, "exec", "-i", "deployment/s3-standin", "--", "/app/.venv/bin/python", "-c",
            "import hashlib, json, pathlib, sys\n"
            f"root = pathlib.Path('/data/{self.bucket()}')\n"
            "a = json.loads(sys.stdin.read())\n" + code,
            stdin=json.dumps(args),
        )  # fmt: skip

    def _osprey_queries(self, base: str, restore_url: str, copies: list[str]) -> str:
        return self.probe(f"""
print("user:", ch("SELECT currentUser()").strip())
for name, q in [
    ("read a set's manifest", "SELECT count() FROM s3('{base}/sets/*/manifest.json', 'RawBLOB')"),
    ("read ArcadeDB's zip", "SELECT length(raw_blob) FROM s3('{base}/sets/*/arcadedb/ospreyflow.zip', 'RawBLOB') LIMIT 1"),
    ("write over a set", "INSERT INTO FUNCTION s3('{base}/sets/probe/arcadedb/ospreyflow.zip', 'RawBLOB') SELECT 'overwritten'"),
    ("url() to another host", "SELECT count() FROM url('https://{STANDIN_HOST}:{STANDIN_PORT}/', 'RawBLOB')"),
    ("RESTORE a set's ClickHouse part", "RESTORE DATABASE ospreyflow AS p9_osprey_restored FROM S3('{restore_url}')"),
    ("RESTORE from ArcadeDB's part", "RESTORE DATABASE ospreyflow AS p9_osprey_restored_a FROM S3('{base}/{copies[0]}')"),
    ("RESTORE from the claims' part", "RESTORE DATABASE ospreyflow AS p9_osprey_restored_c FROM S3('{base}/{copies[1]}')"),
    ("the S3 table engine", "CREATE TABLE ospreyflow.p9_s3_engine (x String) ENGINE = S3('{base}/sets/probe/x', 'RawBLOB')"),
    ("s3Cluster", "SELECT count() FROM s3Cluster('osprey', '{base}/sets/*/manifest.json', 'RawBLOB')"),
    ("icebergS3", "SELECT count() FROM icebergS3('{base}/sets/probe/')"),
    ("deltaLake", "SELECT count() FROM deltaLake('{base}/sets/probe/')"),
    ("remote() to another server", "SELECT count() FROM remote('{STANDIN_HOST}:9000', system.one)"),
]:
    try:
        if q.startswith("RESTORE"):
            # The restore's own shape, which no set's history refuses: a plain database of osprey's
            # making, then the set's tables into it (a bare `RESTORE … AS` recreates the set's
            # Replicated database at the Keeper path the live one may hold: Code 253 on kind).
            ch("CREATE DATABASE IF NOT EXISTS " + q.split(" AS ")[1].split()[0])
            q += " SETTINGS allow_different_database_def = true"
        print("ACCEPTED", name, "->", ch(q).strip()[:120])
    except RuntimeError as e:
        print("REFUSED", name, "->", str(e)[:260])
    if q.startswith("RESTORE"):
        # Each restored database dropped before the next RESTORE: a restored Replicated database
        # takes the set's Keeper path, and a second would be refused for it (Code 253, not access).
        ch("DROP DATABASE IF EXISTS " + q.split(" AS ")[1].split()[0] + " SYNC")
""")

    def _judge_osprey(self, out: str, record_as: str) -> None:
        lines = [
            line for line in out.splitlines() if line.startswith(("ACCEPTED", "REFUSED", "user:"))
        ]
        egress = kubectl("-n", self.ns, "exec", "clickhouse-0", "--", "sh", "-c",
                         "wget -T 5 -q -O /dev/null http://1.1.1.1/ && echo REACHED || echo REFUSED",
                         check=False).strip()  # fmt: skip
        self.record["osprey_sources"] = lines
        self.record["clickhouse_egress_to_1.1.1.1"] = egress
        refused = [line for line in lines if line.startswith("REFUSED")]
        accepted = [line.split(" -> ")[0].removeprefix("ACCEPTED ") for line in lines
                    if line.startswith("ACCEPTED")]  # fmt: skip
        # The bound on the one acceptance (Amendment 7 point 4): RESTORE reaches only what
        # ClickHouse's own role reaches, so a whole backup under ArcadeDB's or the claims' prefix
        # is refused it (and restored, by a role planted to reach `sets/*`: osprey_bound_red).
        bound = {
            name: next((line for line in refused if line.startswith(f"REFUSED {name} ->")), "")
            for name in BOUND
        }
        outside = [n for n, line in bound.items() if not line]
        self.probe(
            "for d in ('p9_osprey_restored', 'p9_osprey_restored_a', 'p9_osprey_restored_c'):\n"
            "    ch(f'DROP DATABASE IF EXISTS {d} SYNC')"
        )
        self.record["osprey_accepted"] = accepted
        self.record["osprey_restore_bound"] = bound
        self.record["show_grants_osprey"] = (
            self.probe("print(ch('SHOW GRANTS'))").strip().splitlines()
        )
        self.save(record_as)
        if accepted != [PINNED_ACCEPTANCE] or outside or egress.endswith("REACHED"):
            raise SystemExit(
                "FAIL: the deployment's user, or ClickHouse's egress, reaches what it must not: "
                f"accepted {accepted} (only {[PINNED_ACCEPTANCE]} is ruled), RESTORE not refused "
                f"from {outside}, egress {egress}"
            )
        print(
            f"PASS the deployment's user is refused all {len(refused)} but the ruled RESTORE of "
            "ClickHouse's own part, which S3 refuses from ArcadeDB's and the claims'; ClickHouse "
            "reaches no outside address"
        )

    def osprey_bound_red(self) -> None:
        """Rule 15 for the bound: ClickHouse's role planted to reach every set's prefix, the check
        above must fail (osprey's RESTORE from ArcadeDB's and the claims' part no longer refused by
        access); the stand-in put back as the Terraform makes it whatever happens."""
        from harness import cloud_platform_backups as backups

        arn = f"arn:aws:s3:::{self.bucket()}"
        wide = backups.role_policies(arn, KEY_ARN, REGION)[backups.CLICKHOUSE_SERVICE_ACCOUNT]
        wide = json.loads(json.dumps(wide).replace("/sets/*/clickhouse/*", "/sets/*"))
        assert "/sets/*/clickhouse/*" not in json.dumps(wide), wide
        self.configure(self.standin_config(clickhouse_policy=wide))
        try:
            self.osprey_sources(record_as="osprey_bound_planted")
            red, said = False, "the check passed with ClickHouse's role reaching every set"
        except SystemExit as e:
            said = str(e)
            # Red for its stated reason: the two outside ClickHouse's prefix accepted, nothing else new.
            red = sorted(self.record.get("osprey_accepted", [])) == sorted([PINNED_ACCEPTANCE, *BOUND])
        finally:
            self.configure(self.standin_config())
        self.record = {"osprey_bound_red": {"red": red, "said": said,
                                            "bound": self.record.get("osprey_restore_bound")}}  # fmt: skip
        self.save("osprey_bound_red")
        print(f"{'PASS' if red else 'FAIL'} the bound planted wide: {said}")
        if not red:
            raise SystemExit("FAIL: the bound's check did not go red with the role planted wide")

    def reds(self) -> None:
        from harness import cloud_platform_backups as backups

        arn = f"arn:aws:s3:::{self.bucket()}"
        good = self.standin_config()
        results: list[dict[str, Any]] = []
        self.shared_pod()
        slot = int(time.time() // 60) + 10  # slots of their own, after the round trip's

        def expect(
            name: str, words: tuple[str, ...], run: Any, config: dict[str, Any] | None = None
        ) -> None:
            nonlocal slot
            slot += 1
            if config is not None:
                self.configure(config)
            before = self.finished_sets()
            try:
                ok, logs = run(slot)
            finally:
                self.configure(good)
            said = [line for line in logs.splitlines() if "refused" in line]
            red = (
                (not ok)
                and all(any(w in line for line in said) for w in words)
                and self.finished_sets() == before
            )
            results.append(
                {
                    "red": name,
                    "slot": slot,
                    "refused": not ok,
                    "words": said,
                    "no_new_set": self.finished_sets() == before,
                    "as_expected": red,
                }
            )
            print(f"{'PASS' if red else 'FAIL'} {name}: {said or logs[-800:]}")

        def main_only(env: dict[str, str] | None = None) -> Any:
            def go(slot: int) -> tuple[bool, str]:
                self.start_from_cron(f"ospreyflow-backup-{slot}", env=env)
                return self.wait_job(f"ospreyflow-backup-{slot}")

            return go

        def both(slot: int) -> tuple[bool, str]:
            ok, logs, _ = self.backup(slot)
            return ok, logs

        # 1. The bucket's policy written for another role: the backup role is refused by the bucket.
        expect(
            "bucket-policy",
            # The upload, since round 3: the bucket policy no longer refuses others ListBucket
            # (HeadBucket, Terraform's read), so the set's read goes through and its first write is refused.
            ("upload to", "AccessDenied"),
            main_only(),
            self.standin_config(
                bucket_policy=backups.bucket_policy(arn, KEY_ARN, [OTHER_ROLE_ARN])
            ),
        )
        # 2. The key's own policy without the runner's role (KMS as AWS judges it: the key's policy
        # names the roles, so a role it leaves out is refused, whatever its IAM says), naming the
        # action and the key.
        expect(
            "kms-key-policy",
            ("AccessDenied", "kms:GenerateDataKey", "resource-based"),
            main_only(),
            self.standin_config(
                key_policy=backups.key_policy(
                    f"arn:aws:iam::{ACCOUNT}:root", [CLICKHOUSE_ROLE_ARN], REGION
                )
            ),
        )
        # 3a. Every session expired (an hour on the platform): measured, not a refusal. ClickHouse
        # and the runner each take a new one from STS by their pods' identity, and the set is
        # written (measured on osprey-p9, 11 November 2026: ClickHouse renews, it does not keep a
        # dead session).
        self.lever("/_standin/expire")
        slot += 1
        ok, logs, renewed = self.backup(slot)
        results.append(
            {
                "measured": "expired-sessions-renewed",
                "slot": slot,
                "set_written": ok,
                "as_expected": ok and renewed in self.finished_sets(),
            }
        )
        print(
            f"{'PASS' if results[-1]['as_expected'] else 'FAIL'} expired sessions renewed: set {renewed}"
        )
        # 3b. An expired role that cannot be renewed (its trust no longer the backup's service
        # accounts): refused at the runner's own STS call, and at ClickHouse's BACKUP sent by the
        # runner's own `clickhouse_backup`; that ClickHouse was refused **by STS** (not writing
        # anonymously by choice) is read from the stand-in's own log of its pod's call.
        untrusting = self.standin_config(trusted_account="another-account")
        expect(
            "unrenewable-role",
            ("STS refused it", "AssumeRoleWithWebIdentity"),
            main_only(),
            untrusting,
        )
        address = kubectl(
            "-n", self.ns, "get", "pod", "clickhouse-0", "-o", "jsonpath={.status.podIP}"
        ).strip()
        clickhouse_call = (
            "import sys\n"
            "from services.api.platform_backup import BackupRefused, Settings, Stores\n"
            "s = Settings.from_env()\n"
            "try:\n"
            "    Stores(s).clickhouse_backup(f'{s.s3_base}/sets/unrenewable/clickhouse/')\n"
            "except BackupRefused as r:\n"
            "    print(f'clickhouse refused: {r}'); sys.exit(1)\n"
            "print('ACCEPTED')\n"
        )

        def clickhouse_unrenewable(slot: int) -> tuple[bool, str]:
            self.lever("/_standin/expire")  # ClickHouse's session ends; it must ask STS again
            self.start_from_cron(
                f"p9-unrenewable-{slot}", command=["/app/.venv/bin/python", "-c", clickhouse_call]
            )
            return self.wait_job(f"p9-unrenewable-{slot}")

        expect(
            "unrenewable-role-clickhouse",
            ("clickhouse refused",),
            clickhouse_unrenewable,
            untrusting,
        )
        sts_log = [line for line in kubectl("-n", STANDIN_NS, "logs", "deployment/s3-standin", "--tail=400").splitlines()
                   if line.startswith(address + " ") and '"POST / ' in line]  # fmt: skip
        results[-1]["clickhouse_sts_calls"] = sts_log[-3:]
        results[-1]["as_expected"] = results[-1]["as_expected"] and any(
            " 403 " in line for line in sts_log
        )
        print(
            f"{'PASS' if results[-1]['as_expected'] else 'FAIL'} ClickHouse refused by STS: {sts_log[-2:]}"
        )
        # 4. No claims part (the claims run never ran): the main run waits its bounded time, fails
        # in words and leaves the set unfinished; a restore of that set is refused.
        expect(
            "missing-claims",
            ("claims", "unfinished"),
            main_only({"OSPREY_BACKUP_CLAIMS_WAIT": "45"}),
        )
        unfinished = dt.datetime.fromtimestamp(slot * 60, dt.UTC).strftime("%Y%m%dT%H%M%SZ")
        name = f"p9-restore-refused-{slot}"
        self.start_from_cron(
            name,
            command=[
                "/app/.venv/bin/python",
                "-m",
                "services.api.platform_backup",
                "fetch-graph",
                "--set",
                unfinished,
                "--to",
                "/tmp/restore",
            ],
        )
        ok, logs = self.wait_job(name)
        results.append(
            {
                "red": "restore-of-the-unfinished-set",
                "refused": not ok,
                "words": [line for line in logs.splitlines() if "refused" in line],
                "as_expected": (not ok) and "no finished set" in logs,
            }
        )
        print(
            f"{'PASS' if results[-1]['as_expected'] else 'FAIL'} restore of {unfinished}: {results[-1]['words']}"
        )
        # 5. A restore while a writer runs (the shared pod, standing for the Conduit, left running; the
        # API path P7b's row will give, present): both Jobs' verify refuses, naming it, and nothing is
        # touched.
        self.restore_api_path(True)
        self.shared_pod()
        before = self.counts()
        set_id = self.finished_sets()[-1]
        documents = [
            d for d in yaml.safe_load_all(sh("bash", self.helm_script, "restore-job", set_id)) if d
        ]
        said: list[str] = []
        for job in (d for d in documents if d["kind"] == "Job"):
            self.irsa(job["spec"]["template"]["spec"], self.values()["backups"]["image"])
            job["metadata"]["namespace"] = self.ns
            kubectl(
                "-n",
                self.ns,
                "delete",
                "job",
                job["metadata"]["name"],
                "--ignore-not-found",
                "--wait=true",
            )
            apply(job)
            ok, _ = self.wait_job(job["metadata"]["name"], timeout=600)
            for pod in kubectl("-n", self.ns, "get", "pods", "-l", f"job-name={job['metadata']['name']}",
                               "-o", "name").split():  # fmt: skip
                said += [line for line in kubectl("-n", self.ns, "logs", pod, "-c", "verify", check=False).splitlines()
                         if "refused" in line]  # fmt: skip
        untouched = self.counts() == before
        results.append({"red": "restore-beside-a-running-writer", "words": said, "untouched": untouched,
                        "as_expected": bool(said) and all("still running" in w for w in said) and untouched})  # fmt: skip
        print(f"{'PASS' if results[-1]['as_expected'] else 'FAIL'} restore beside a writer: {said}")
        self.record["reds"] = results
        self.save("reds")
        if not all(r["as_expected"] for r in results):
            raise SystemExit("FAIL: a refusal did not happen as the platform would give it")


#: The stores' own HTTP, run in the probe pod (the deployment's own network), with the runner's names.
#: The one statement shape the deployment's ClickHouse user is let do that reaches the bucket: no
#: privilege gates RESTORE (measured, gates/p9_grants_probe3.log); the orchestrator's ruling A of
#: 11 November, Amendment 7 point 4. Anything else accepted turns osprey_sources red.
PINNED_ACCEPTANCE = "RESTORE a set's ClickHouse part"
BOUND = ("RESTORE from ArcadeDB's part", "RESTORE from the claims' part")

STORES = r"""
import base64, json, os, urllib.error, urllib.request
A = "http://arcadedb-0.arcadedb-headless:2480"
AUTH = "Basic " + base64.b64encode(("root:" + os.environ["ARCADEDB_ROOT_PASSWORD"]).encode()).decode()
CH = "http://clickhouse:8123/"
def arcade(path, body):
    r = urllib.request.Request(A + path, data=json.dumps(body).encode(), method="POST",
                               headers={"Authorization": AUTH, "Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(r, timeout=600).read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ArcadeDB {path}: {e.code} {e.read()[:400]!r}") from None
def sql(command, language="sql"):
    return arcade("/api/v1/command/ospreyflow", {"language": language, "command": command})["result"]
def ch(statement):
    r = urllib.request.Request(CH, data=statement.encode(), method="POST", headers={
        "X-ClickHouse-User": os.environ["CLICKHOUSE_USER"], "X-ClickHouse-Key": os.environ["CLICKHOUSE_PASSWORD"]})
    try:
        return urllib.request.urlopen(r, timeout=600).read().decode()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ClickHouse: {e.code} {e.read()[:400]!r}") from None
def seed(vertices, edges, rows):
    # From empty stores every time: a seed that half-ran before is never counted twice.
    try:
        arcade("/api/v1/server", {"command": "drop database ospreyflow"})
    except RuntimeError:
        pass
    ch("DROP DATABASE IF EXISTS ospreyflow ON CLUSTER osprey SYNC")
    try:
        arcade("/api/v1/server", {"command": "create database ospreyflow"})
    except RuntimeError as e:
        if "exist" not in str(e):
            raise
    sql("CREATE VERTEX TYPE P9Person IF NOT EXISTS")
    sql("CREATE EDGE TYPE P9Knows IF NOT EXISTS")
    for start in range(0, vertices, 500):
        rows_ = [{"n": i, "name": f"synthetic person {i}"} for i in range(start, min(start + 500, vertices))]
        sql("INSERT INTO P9Person CONTENT " + json.dumps(rows_))
    sql("CREATE PROPERTY P9Person.n IF NOT EXISTS LONG")
    sql("CREATE INDEX IF NOT EXISTS ON P9Person (n) UNIQUE")
    for i in range(edges):
        sql(f"CREATE EDGE P9Knows FROM (SELECT FROM P9Person WHERE n = {i}) TO (SELECT FROM P9Person WHERE n = {i + 1})")
    ch("CREATE DATABASE IF NOT EXISTS ospreyflow ON CLUSTER osprey ENGINE = Replicated('/clickhouse/databases/ospreyflow', '{shard}', '{replica}')")
    ch("CREATE TABLE IF NOT EXISTS ospreyflow.p9_rows (id UInt64, v String) ENGINE = ReplicatedMergeTree ORDER BY id")
    ch(f"INSERT INTO ospreyflow.p9_rows SELECT number, concat('synthetic row ', toString(number)) FROM numbers({rows})")
def counts():
    found = {}
    try:
        found["arcadedb_vertices"] = sql("SELECT count(*) AS c, sum(n) AS s FROM P9Person")[0]
        found["arcadedb_edges"] = sql("SELECT count(*) AS c FROM P9Knows")[0]["c"]
    except RuntimeError as e:
        found["arcadedb"] = str(e)[:160]
    try:
        found["clickhouse_rows"] = json.loads(ch("SELECT count(), toString(sum(cityHash64(v))) FROM ospreyflow.p9_rows FORMAT JSONCompact"))["data"][0]
    except RuntimeError as e:
        found["clickhouse"] = str(e)[:160]
    return found
def destroy():
    arcade("/api/v1/server", {"command": "drop database ospreyflow"})
    ch("DROP DATABASE IF EXISTS ospreyflow ON CLUSTER osprey SYNC")
def change(tag, vertices=100, rows=300):
    # The live stores moved on since the set: people and rows the set does not hold.
    base = {"a": 1, "b": 2, "c": 3}[tag] * 1_000_000
    people = [{"n": base + i, "name": f"synthetic person added after the set {tag}{i}"} for i in range(vertices)]
    sql("INSERT INTO P9Person CONTENT " + json.dumps(people))
    ch(f"INSERT INTO ospreyflow.p9_rows SELECT {base} + number, 'added after the set {tag}' FROM numbers({rows})")
def databases():
    return sorted(ch("SHOW DATABASES").split())
"""

#: The shared claim's own files, in the shared pod: synthetic uploads and a drop folder.
CLAIMS = r"""
import hashlib, json, os, pathlib, random, shutil
ROOT = pathlib.Path("/claims/ingest")
def seed(files):
    destroy()
    rng = random.Random(9)
    for i in range(files):
        path = ROOT / "ingest" / "uploads" / f"case-{i % 7}" / f"synthetic upload {i}.bin"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(rng.randbytes(20_000 + i * 37))
    drop = ROOT / "ingest" / "drop" / "nightly"
    drop.mkdir(parents=True, exist_ok=True)
    (drop / "people.csv").write_text("id,name\n" + "".join(f"{i},Synthetic Person {i}\n" for i in range(500)))
def tree():
    found = []
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT).as_posix()
        if rel == "lost+found" or rel.startswith("lost+found/") or not path.is_file():
            continue
        found.append(rel + " " + hashlib.sha256(path.read_bytes()).hexdigest())
    return {"files": len(found), "sha256": hashlib.sha256("\n".join(found).encode()).hexdigest()}
def destroy():
    for entry in ROOT.iterdir():
        if entry.name == "lost+found":
            continue
        shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
def change(tag):
    path = ROOT / "ingest" / "uploads" / f"added after the set {tag}.bin"
    path.write_bytes(random.Random(tag).randbytes(30_000))
def leftovers():
    return sorted(p.name for p in ROOT.iterdir() if p.name.startswith(".osprey-"))
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "command",
        choices=[
            "render",
            "standin",
            "secrets",
            "patch",
            "seed",
            "backup",
            "destroy",
            "restore",
            "counts",
            "roundtrip",
            "reds",
            "osprey_sources",
            "osprey_bound_red",
            "restore_refused",
            "live_restore",
        ],
    )
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--namespace", default="ospreyflow-dev")
    parser.add_argument("--registry")
    parser.add_argument("--resolve", choices=["none", "registry"], default="none")
    parser.add_argument("--helm-script")
    parser.add_argument("--set")
    args = parser.parse_args()
    run = Run(args.state, args.namespace, args.helm_script)
    if args.command == "render":
        run.render(args.registry, args.resolve)
    elif args.command == "restore":
        print(run.restore(args.set or run.finished_sets()[-1]))
    elif args.command == "backup":
        sys.exit(0 if run.backup()[0] else 1)
    elif args.command in ("counts",):
        print(run.counts())
    else:
        getattr(run, args.command)()


if __name__ == "__main__":
    main()
