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
STANDIN_NS = "platform-managed"
STANDIN_HOST = f"s3-standin.{STANDIN_NS}.svc.cluster.local"
STANDIN_PORT = 9443
STANDIN = f"https://{STANDIN_HOST}:{STANDIN_PORT}"
TOKEN_DIR = "/var/run/secrets/eks.amazonaws.com/serviceaccount"
CA_DIR = "/etc/standin-ca"
KEPT = ("arcadedb", "clickhouse", "clickhouse-keeper")
#: Memory on kind's 8 GB (the render's are the platform's): enough to run, not to measure speed by.
KIND_MEMORY = {"arcadedb": "2Gi", "clickhouse": "2Gi", "clickhouse-keeper": "512Mi"}
SEED_VERTICES = 5000
SEED_EDGES = 1000
SEED_ROWS = 200_000


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

        resolver = (
            (lambda ref: registry_digest_resolver(in_kind(ref)))
            if resolve == "registry"
            else (lambda ref: None)
        )
        result = render(config, resolver=resolver, allow_unpinned=resolve != "registry")
        values = yaml.safe_load(result.artefacts["values.yaml"])
        if "backups" not in values:  # P9_render.diff not applied: the same call it makes
            assert config.cloud_platform is not None
            platform = load_platform(config.cloud_platform.platform)
            values["backups"] = backups.backups_values(
                config, platform, values["workloads"], values["environment"]
            )
        values["workloads"] = [w for w in values["workloads"] if w["name"] in KEPT]
        values["jobs"] = []
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
        bucket_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from harness import cloud_platform_backups as backups

        arn = f"arn:aws:s3:::{self.bucket()}"
        jwks = json.loads(kubectl("get", "--raw", "/openid/v1/jwks"))
        issuer = json.loads(kubectl("get", "--raw", "/.well-known/openid-configuration"))["issuer"]
        return {
            "region": REGION,
            "roles": [
                {
                    "arn": ROLE_ARN,
                    "issuer_secret": "unused: the cluster's keys are the trust",
                    "subject": f"system:serviceaccount:{self.ns}:{backups.SERVICE_ACCOUNT}",
                    "jwks": jwks,
                    "issuer": issuer,
                    "policies": [role_policy or backups.role_policy(arn, KEY_ARN)],
                }
            ],
            "buckets": [
                {
                    "name": self.bucket(),
                    "kms_key": KEY_ARN,
                    "policy": bucket_policy or backups.bucket_policy(arn, KEY_ARN, ROLE_ARN),
                }
            ],
        }

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
            (ca / "san").write_text(f"subjectAltName=DNS:{STANDIN_HOST}")
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
                        "ports": [{"port": STANDIN_PORT, "targetPort": STANDIN_PORT}],
                    },
                },
            ]
        )
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
        apply(
            [
                {
                    "apiVersion": "v1",
                    "kind": "Secret",
                    "metadata": {"name": "ospreyflow-secrets", "namespace": self.ns},
                    "data": encode(data),
                },
                # What the namespace's backups.tf writes (OUTPUT_SECRET), and its service account.
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
                {
                    "apiVersion": "v1",
                    "kind": "ServiceAccount",
                    "metadata": {
                        "name": backups.SERVICE_ACCOUNT,
                        "namespace": self.ns,
                        "annotations": {"eks.amazonaws.com/role-arn": ROLE_ARN},
                    },
                },
            ]
        )

    def irsa(self, pod: dict[str, Any], image: str) -> None:
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
            {"name": "AWS_ROLE_ARN", "value": ROLE_ARN},
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
                {"name": "aws-iam-token", "mountPath": TOKEN_DIR, "readOnly": True},
                {"name": "standin-ca", "mountPath": CA_DIR, "readOnly": True},
            ]

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
        if not any(v["name"] == "p9-ca" for v in pod.get("volumes", [])):
            pod.setdefault("volumes", []).extend(
                [
                    {"name": "p9-ca", "secret": {"secretName": "standin-ca"}},
                    {"name": "p9-ca-config", "configMap": {"name": "p9-clickhouse-ca"}},
                ]
            )
            container = next(c for c in pod["containers"] if c["name"] == "clickhouse")
            container.setdefault("volumeMounts", []).extend(
                [
                    {"name": "p9-ca", "mountPath": CA_DIR, "readOnly": True},
                    {
                        "name": "p9-ca-config",
                        "mountPath": "/etc/clickhouse-server/config.d/standin-ca.xml",
                        "subPath": "standin-ca.xml",
                        "readOnly": True,
                    },
                ]
            )
            kubectl("replace", "-f", "-", stdin=json.dumps(sts))
        print("patched: the backup CronJob's IRSA; ClickHouse's trust of the stand-in's CA")

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

    def seed(self) -> dict[str, Any]:
        out = self.probe(
            f"seed({SEED_VERTICES}, {SEED_EDGES}, {SEED_ROWS}); print(json.dumps(counts()))"
        )
        found: dict[str, Any] = json.loads(out.strip().splitlines()[-1])
        print("seeded:", found)
        return found

    def counts(self) -> dict[str, Any]:
        found: dict[str, Any] = json.loads(
            self.probe("print(json.dumps(counts()))").strip().splitlines()[-1]
        )
        return found

    def destroy(self) -> dict[str, Any]:
        self.probe("destroy()")
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

    def job_from_cron(self, name: str, command: list[str] | None = None) -> tuple[bool, str]:
        kubectl("-n", self.ns, "delete", "job", name, "--ignore-not-found", "--wait=true")
        if command is None:
            kubectl("-n", self.ns, "create", "job", name, "--from=cronjob/ospreyflow-backup")
        else:
            cron = json.loads(
                kubectl("-n", self.ns, "get", "cronjob", "ospreyflow-backup", "-o", "json")
            )
            spec = copy.deepcopy(cron["spec"]["jobTemplate"]["spec"])
            spec["backoffLimit"] = 0
            spec["template"]["spec"]["containers"][0]["command"] = command
            apply(
                {
                    "apiVersion": "batch/v1",
                    "kind": "Job",
                    "metadata": {"name": name, "namespace": self.ns},
                    "spec": spec,
                }
            )
        return self.wait_job(name)

    def backup(self, name: str = "p9-backup") -> tuple[bool, str]:
        ok, logs = self.job_from_cron(name)
        print(f"{name}: {'succeeded' if ok else 'FAILED'}\n{logs}")
        return ok, logs

    def restore(self, set_id: str) -> dict[str, float]:
        """ArcadeDB stopped, the restore Job (rendered as an operator does) run, ArcadeDB started:
        each phase timed."""
        assert self.helm_script
        times: dict[str, float] = {}
        start = time.monotonic()
        kubectl("-n", self.ns, "scale", "statefulset/arcadedb", "--replicas=0")
        kubectl(
            "-n", self.ns, "wait", "--for=delete", "pod/arcadedb-0", "--timeout=300s", check=False
        )
        times["arcadedb_stopped"] = round(time.monotonic() - start, 1)
        documents = [
            d for d in yaml.safe_load_all(sh("bash", self.helm_script, "restore-job", set_id)) if d
        ]
        job = next(d for d in documents if d["kind"] == "Job")
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
        ok, logs = self.wait_job(job["metadata"]["name"])
        times["restore_job"] = round(time.monotonic() - start - times["arcadedb_stopped"], 1)
        print(f"restore job: {'succeeded' if ok else 'FAILED'}\n{logs}")
        if not ok:
            raise SystemExit("the restore Job failed")
        restarted = time.monotonic()
        kubectl("-n", self.ns, "scale", "statefulset/arcadedb", "--replicas=1")
        kubectl("-n", self.ns, "rollout", "status", "statefulset/arcadedb", "--timeout=900s")
        kubectl("-n", self.ns, "wait", "--for=condition=Ready", "pod/arcadedb-0", "--timeout=900s")
        times["arcadedb_ready"] = round(time.monotonic() - restarted, 1)
        times["total"] = round(time.monotonic() - start, 1)
        return times

    # -- the runs ---------------------------------------------------------------------------------

    def lease(self) -> dict[str, str]:
        """The lease this run is under, as the environment names it (rule 14); none is said so."""
        named = {
            k: v
            for k, v in os.environ.items()
            if any(w in k for w in ("LEASE", "STACK", "OSPREY_LANE"))
        }
        return named or {"lease": "none: not a timing run"}

    def save(self, run: str) -> None:
        self.record["at"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        self.record["host"] = os.uname().nodename
        self.record["lease"] = self.lease()
        path = self.state / f"p9_{run}.json"
        path.write_text(json.dumps(self.record, indent=2))
        print(f"== record ({path})\n{json.dumps(self.record, indent=2)}")

    def roundtrip(self) -> None:
        seeded = self.seed()
        before = set(self.finished_sets())
        ok, logs = self.backup("p9-backup")
        if not ok:
            raise SystemExit("the backup failed")
        new = sorted(set(self.finished_sets()) - before)
        assert len(new) == 1, f"one finished set expected, found {new}"
        set_id = new[0]
        objects = [o for o in self.bucket_objects() if o["key"].startswith(f"sets/{set_id}/")]
        unencrypted = [o["key"] for o in objects if o.get("kms_key") != KEY_ARN]
        self.record["backup"] = {
            "set": set_id,
            "objects": len(objects),
            "bytes": sum(o["size"] for o in objects),
            "not_under_the_key": unencrypted,
            "log": [line for line in logs.splitlines() if "backup:" in line],
        }
        left = self.destroy()
        self.record["destroyed"] = left
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
        print(f"PASS round trip: set {set_id} restored in {times['total']} s, counts equal")

    def reds(self) -> None:
        from harness import cloud_platform_backups as backups

        arn = f"arn:aws:s3:::{self.bucket()}"
        good = self.standin_config()
        results: list[dict[str, Any]] = []

        def expect(
            name: str,
            config: dict[str, Any] | None,
            words: tuple[str, ...],
            command: list[str] | None = None,
        ) -> None:
            if config is not None:
                self.configure(config)
            before = self.finished_sets()
            try:
                ok, logs = self.job_from_cron(f"p9-red-{name}", command)
            finally:
                self.configure(good)
            said = [line for line in logs.splitlines() if "refused" in line or "REFUSED" in line]
            red = (
                (not ok)
                and all(any(w in line for line in said) for w in words)
                and self.finished_sets() == before
            )
            results.append(
                {
                    "red": name,
                    "refused": not ok,
                    "words": said,
                    "no_new_set": self.finished_sets() == before,
                    "as_expected": red,
                }
            )
            print(f"{'PASS' if red else 'FAIL'} {name}: {said or logs[-800:]}")

        # 1. The bucket's policy written for another role: the backup role is refused by the bucket.
        expect(
            "bucket-policy",
            self.standin_config(bucket_policy=backups.bucket_policy(arn, KEY_ARN, OTHER_ROLE_ARN)),
            ("arcadedb", "AccessDenied"),
        )
        # 2. The role without kms:GenerateDataKey: S3 refuses the encrypted write, naming the action.
        policy = backups.role_policy(arn, KEY_ARN)
        for statement in policy["Statement"]:
            statement["Action"] = [a for a in statement["Action"] if a != "kms:GenerateDataKey"]
        expect(
            "kms-generate",
            self.standin_config(role_policy=policy),
            ("AccessDenied", "kms:GenerateDataKey"),
        )
        # 3. The session expired between taking its credentials and ClickHouse's BACKUP, by the
        # runner's own calls (an hour on the platform; the stand-in's lever here).
        expect(
            "expired-role",
            None,
            ("clickhouse", "ExpiredToken"),
            ["/app/.venv/bin/python", "-c", EXPIRED],
        )
        self.record["reds"] = results
        self.save("reds")
        if not all(r["as_expected"] for r in results):
            raise SystemExit("FAIL: a refusal did not happen as the platform would give it")


#: The stores' own HTTP, run in the probe pod (the deployment's own network), with the runner's names.
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
"""

#: The runner's own calls, the session expired between them (the third red).
EXPIRED = r"""
import ssl, sys, urllib.request
from services.api.platform_backup import Bucket, BackupRefused, Settings, Stores
settings = Settings.from_env()
bucket, stores = Bucket(settings), Stores(settings)
credentials = bucket.credentials()
bucket.client.list_objects_v2(Bucket=settings.bucket, MaxKeys=1)  # accepted while the session lives
print("the role's session accepted by S3")
context = ssl.create_default_context(cafile=__import__("os").environ["AWS_CA_BUNDLE"])
urllib.request.urlopen(urllib.request.Request(settings.s3_endpoint + "/_standin/expire", data=b"", method="POST"), context=context)
try:
    stores.clickhouse_backup(f"{settings.s3_base}/sets/expired-probe/clickhouse/", credentials)
except BackupRefused as refusal:
    print(f"expired-role refused: {refusal}", file=sys.stderr)
    sys.exit(1)
print("FAIL: ClickHouse's BACKUP was accepted on an expired session")
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
