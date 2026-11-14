"""Step 4's stack (v0.5.2, ADR-149 Amendment 2): what a measurement needs beside B's stores, on the
leased stack's own host, removed after the run. Stack d holds only the stores, so this gives it:

1. an ephemeral Keycloak (the tests' image, `--features=token-exchange`), its containers labelled
   with the lane and the run (`tests/harness/run_owned.py`), its realm made through the admin API
   (no realm file), holding step 4's subjects (`SUBJECTS`: the four R-owning units' controls,
   `m10-part` and `m10-measure`, as rules granted them on B's cases) and one probe that holds no
   grant (`PROBE`);
2. the Conduit and the worker, from their own images, at the poc manifest's own limits (read from
   `harness/cloud_platform/poc_manifest.yaml`, never typed here), on the host's network bound to
   127.0.0.1, against the stores the lease's environment names;
3. each subject's token, minted by the Conduit client's token exchange (ADR-043), put into the
   environment of the command it runs and nowhere else: never an argument, never a file;
4. before the command, the preflight: `m10-measure` reads its case, and the probe's token is
   refused it (a token for a subject with no grant is refused). Either way round, the command does
   not run.

Run on the stack's host, from the worktree root, with the case given:

    OspreyFlow_Build/scripts/stack_lease.sh remote <lane> -- OspreyFlow_Core/.venv/bin/python \\
      OspreyFlow_Build/process/lanes/platform/v052-measure/step4_stack.py --case <id> \\
      -- <command...>

The command sees OSPREY_MEASURE_BASE, _CASE, _TOKEN (m10-measure's), _PART_TOKEN (m10-part's) and
_CONTROLS (a JSON object of the controls' tokens by subject). Neither a token nor a password is
printed. Everything it started is removed at its end, on TERM and at exit, by its run's label.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]
CORE = ROOT / "OspreyFlow_Core"
BUILD = ROOT / "OspreyFlow_Build"
KEYCLOAK_IMAGE = "quay.io/keycloak/keycloak:26.0"
REALM = "osprey"
#: How long the realm's tokens live, and the least a minted token must live for the run to start.
#: Each token is minted once, before the command, and handed to it in its environment alone (no
#: password reaches the child to mint again), so every token must outlive the whole command: the
#: deployment's rendered realm sets no lifespan, Keycloak's 300 s applied, and step 4's rerun on d
#: (14 November 2026) was refused from about five minutes in. Step 2 takes about eight minutes.
TOKEN_LIFE_S = 4 * 3600
TOKEN_LIFE_NEEDED_S = 3600
LANE = os.environ.get("OSPREY_LANE", "platform")

#: Step 4's subjects as rules granted them on stack d (14 November 2026): one cleared control per
#: unit owning an R source (a restricted code is read only in its own unit), the part-cleared
#: principal M10 asks as, and the principal M1 to M6 measure as (an editor, for M6's draws).
SUBJECTS: tuple[dict[str, Any], ...] = (
    *(
        {"username": f"m10-cleared-{unit}", "clearance": "SECRET", "org_unit": unit,
         "codes": ["P", "C", "R"], "use": "control"}
        for unit in ("unit-fiu", "unit-intel-covert", "unit-covert", "unit-border")
    ),
    {"username": "m10-part", "clearance": "OFFICIAL-SENSITIVE", "org_unit": "unit-records",
     "codes": ["P", "C"], "use": "part"},
    {"username": "m10-measure", "clearance": "OFFICIAL-SENSITIVE", "org_unit": "unit-intel",
     "codes": ["P", "C"], "use": "measure"},
)  # fmt: skip
#: A subject granted nothing: its token must be refused the case, or the preflight stops the run.
PROBE = {"username": "m10-ungranted", "clearance": "SECRET", "org_unit": "unit-intel",
         "codes": ["P", "C"], "use": "probe"}  # fmt: skip
#: What the Conduit and the worker are given from the lease's environment, by name alone (the
#: value never on a command line): the stores' addresses, ports and passwords, and our settings.
PASSED_THROUGH = ("ARCADEDB_", "POSTGRES_", "VALKEY_", "CLICKHOUSE_", "OPENSEARCH_", "OSPREY_",
                  "ANALYTICS_")  # fmt: skip


#: The poc's Conduit settings step 4 does not use, each for a reason: Entra's (the realm here is
#: Keycloak's, whose claims are the fixed names), AWS's (the stack's object store and OpenSearch
#: answer unsigned on the host), a cluster's (one ArcadeDB, one ClickHouse), and the poc's own
#: index alias (the stack's index is the one its load built: `STEP4_SEARCH_INDEX_ALIAS`, else the
#: default a rebuild makes).
DROPPED = frozenset({
    "OSPREY_CLAIM_MAPPING", "OSPREY_IDENTITY_PROVIDER", "OSPREY_FIRST_ADMINISTRATORS",
    "SUPERSET_SIGN_IN", "OSPREY_DASHBOARDS_ORIGIN", "MINIO_CREDENTIALS", "MINIO_REGION",
    "OPENSEARCH_REGION", "OSPREY_SEARCH_INDEX_ALIAS", "CLICKHOUSE_CLUSTER", "ARCADEDB_HA",
    "OIDC_ISSUER", "OIDC_JWKS_URL", "OIDC_AUDIENCE",  # the realm's, set by the run
})  # fmt: skip
#: Where the poc's own directories are, made writable for the run (a tmpfs, the image's user's):
#: its data, ingest and state folders, and its map and model settings.
DATA_ROOT = "/var/lib/osprey"
WRITABLE = (DATA_ROOT, "/run/osprey")


def poc_environment() -> dict[str, str]:
    """The poc's own Conduit environment, as the render gives it (never typed here)."""
    return {k: str(v) for k, v in poc_values()["environment"].items()}


def workload_settings(values: dict[str, Any], workload: str) -> dict[str, str]:
    """A workload's own plain settings in the render (`env` entries with a value; those from a
    Secret are the stack's, from the lease), empty ones left out."""
    found = next(w for w in values["workloads"] if w["name"] == workload)
    return {e["name"]: str(e["value"]) for e in found.get("env", []) if e.get("value")}


def workload_files(values: dict[str, Any], workload: str) -> list[tuple[str, str, str]]:
    """(key, where the chart mounts it, its text) for each of a workload's files: osprey.yaml
    among them, the poc's own configuration, which the Conduit reads at start (the fourth proof)."""
    found = next(w for w in values["workloads"] if w["name"] == workload)
    return [(f["key"], f["mountPath"], values["files"][f["key"]]) for f in found.get("files") or []]


def poc_values() -> dict[str, Any]:
    """The poc's own render, values.yaml as the chart is given it."""
    import yaml
    from harness.render import render
    from tools.cp_policy_check import FIXTURES, _resolver

    from schemas.deployment import OspreyConfig

    os.environ.setdefault("OSPREY_PLATFORM_FOLDERS", str(FIXTURES / "platforms"))
    raw = yaml.safe_load((FIXTURES / "poc.yaml").read_text(encoding="utf-8"))
    values = yaml.safe_load(
        render(OspreyConfig.model_validate(raw), resolver=_resolver).artefacts["values.yaml"]
    )
    found: dict[str, Any] = values
    return found


def conduit_environment(poc: dict[str, str], lease: dict[str, str]) -> dict[str, str]:
    """The poc's own settings, less `DROPPED`, with the leased stack's in their place: its stores
    on the host's loopback at the lease's ports, unsigned and without TLS; the ceiling B's data
    needs (SECRET, ADR-148 Am 14's ruling); the origins this host's own."""
    env = {k: v for k, v in poc.items() if k not in DROPPED}
    loopback = "127.0.0.1"
    env |= {
        "ARCADEDB_HOST": loopback, "CLICKHOUSE_HOST": loopback, "OPENSEARCH_HOST": loopback,
        "VALKEY_HOST": loopback, "POSTGRES_HOST": loopback,
        "OPENSEARCH_SIGNING": "none", "POSTGRES_SSLMODE": "disable", "VALKEY_TLS": "false",
        "MINIO_USE_SSL": "false", "OSPREY_HIGHEST_MARKING": "SECRET",
        "CORS_ALLOWED_ORIGINS": "http://127.0.0.1", "OSPREY_GLASS_ORIGIN": "http://127.0.0.1",
    }  # fmt: skip
    for name in ("CLICKHOUSE_HTTP_PORT", "OPENSEARCH_PORT", "MINIO_ENDPOINT"):
        if lease.get(name):
            env[name] = lease[name]
    if lease.get("STEP4_SEARCH_INDEX_ALIAS"):
        env["OSPREY_SEARCH_INDEX_ALIAS"] = lease["STEP4_SEARCH_INDEX_ALIAS"]
    return env


def poc_limits(workload: str) -> tuple[str, str]:
    """The poc manifest's own limits for `workload`, as Docker's --cpus and --memory."""
    import yaml

    manifest = yaml.safe_load(
        (CORE / "harness/cloud_platform/poc_manifest.yaml").read_text(encoding="utf-8")
    )
    limits = manifest["workloads"][workload]["limits"]
    memory = str(limits["memory"])
    units = {"Gi": "g", "Mi": "m"}
    for suffix, docker_suffix in units.items():
        if memory.endswith(suffix):
            memory = memory[: -len(suffix)] + docker_suffix
            break
    return str(limits["cpu"]), memory


def slug(run: str) -> str:
    """The run as Docker allows a name or tag ([a-z0-9][a-z0-9_.-]*): its last path part, as
    `stack_lease.sh` gives OSPREY_RUN_TAG as the run's folder. The label keeps the run whole."""
    import re

    last = run.rstrip("/").rsplit("/", 1)[-1].lower()
    return re.sub(r"[^a-z0-9_.-]", "-", last).lstrip("-_.") or "run"


def run_labels(run: str) -> list[str]:
    return ["--label", f"osprey.lane={LANE}", "--label", f"osprey.run={run}"]


def passed_through(environment: dict[str, str]) -> list[str]:
    """`-e NAME` for each setting the stores' clients read: by name, so Docker reads its value
    from its own environment and no value is on the command line."""
    names = sorted(
        n for n in environment
        if n.startswith(PASSED_THROUGH) and not n.startswith("OSPREY_MEASURE_")
    )  # fmt: skip
    return [arg for n in names for arg in ("-e", n)]


def build_argv(dockerfile: str, tag: str) -> list[str]:
    """A workload's image built from the checkout's Core, whatever directory the runner is started
    from: docker reads `-f` from the process's own directory, not from the context (14 November
    2026, rules' first run on d, started at the repository root: "lstat services: no such file or
    directory")."""
    return ["build", "-q", "-f", str(CORE / dockerfile), "-t", tag, str(CORE)]


def keycloak_argv(run: str, name: str, port: int) -> list[str]:
    return [
        "run", "-d", "--name", name, *run_labels(run), "--network", "host",
        "-e", "KC_BOOTSTRAP_ADMIN_USERNAME", "-e", "KC_BOOTSTRAP_ADMIN_PASSWORD",
        KEYCLOAK_IMAGE, "start-dev", "--features=token-exchange",
        f"--http-port={port}", "--http-host=127.0.0.1", f"--hostname=http://127.0.0.1:{port}",
    ]  # fmt: skip


def service_argv(
    run: str, name: str, image: str, workload: str, environment: dict[str, str],
    command: Sequence[str], settings: Sequence[str] = (),
    mounts: Sequence[tuple[str, str]] = (),
) -> list[str]:  # fmt: skip
    """`settings`: the Conduit's own (`conduit_environment`'s names), passed by name as the
    lease's are, their values in Docker's environment alone."""
    cpus, memory = poc_limits(workload)
    named = sorted({*settings, "OIDC_ISSUER", "OIDC_JWKS_URL", "OIDC_AUDIENCE",
                    "OSPREY_WORKER_NAME"})  # fmt: skip
    passed = passed_through({k: v for k, v in environment.items() if k not in named})
    return [
        "run", "-d", "--name", name, *run_labels(run), "--network", "host",
        f"--cpus={cpus}", f"--memory={memory}", f"--memory-swap={memory}",
        *(a for w in WRITABLE for a in ("--tmpfs", f"{w}:rw,uid=10001,gid=10001,mode=0700")),
        *(a for host, at in mounts for a in ("-v", f"{host}:{at}:ro")),
        *passed, *(arg for n in named for arg in ("-e", n)),
        "--entrypoint", command[0], image, *command[1:],
    ]  # fmt: skip


def conduit_command(port: int) -> list[str]:
    """The image's own server, bound to the host's loopback alone (never 0.0.0.0, nothing
    reachable from outside the host)."""
    return ["uvicorn", "services.api.app:app", "--host", "127.0.0.1", "--port", str(port)]


WORKER_COMMAND = ["python", "-m", "services.api.worker_main"]


def realm_users() -> list[dict[str, Any]]:
    """Each subject a user whose id is its name: the Conduit's principal id is the token's `sub`
    (`principal_auth`), which Keycloak sets from the user's id, and B's cases are granted to the
    names (rules, 14 November). A generated id would match no grant."""
    return [
        {
            "id": s["username"],
            "username": s["username"],
            "enabled": True,
            "email": f"{s['username']}@ospreyflow.invalid",
            "emailVerified": True,
            "firstName": "Step 4",
            "lastName": s["username"],
            "attributes": {
                "clearance": [s["clearance"]],
                "org_unit": [s["org_unit"]],
                "receivable_handling_codes": list(s["codes"]),
                "roles": ["analyst"],
            },
        }
        for s in (*SUBJECTS, PROBE)
    ]


def measure_environment(tokens: dict[str, str], base: str, case: str) -> dict[str, str]:
    """What the command is given: the door, the case, and each use's token."""
    by_use: dict[str, list[str]] = {}
    for subject in SUBJECTS:
        by_use.setdefault(subject["use"], []).append(subject["username"])
    return {
        "OSPREY_MEASURE_BASE": base,
        "OSPREY_MEASURE_CASE": case,
        "OSPREY_MEASURE_TOKEN": tokens[by_use["measure"][0]],
        "OSPREY_MEASURE_PART_TOKEN": tokens[by_use["part"][0]],
        "OSPREY_MEASURE_CONTROLS": json.dumps({u: tokens[u] for u in by_use["control"]}),
    }


def preflight(base: str, case: str, measure_token: str, probe_token: str) -> str:
    """'' when `m10-measure` reads the case and the probe's token is refused it; else why not."""

    def status(token: str) -> int:
        request = urllib.request.Request(
            f"{base}/v1/investigations/{case}", headers={"Authorization": f"Bearer {token}"}
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as answer:
                return int(answer.status)
        except urllib.error.HTTPError as error:
            return int(error.code)
        except (urllib.error.URLError, OSError):
            return 0

    measured, probed = status(measure_token), status(probe_token)
    if measured != 200:
        return f"m10-measure is not granted the case (HTTP {measured}): nothing to measure as"
    if probed == 200:
        return "a subject granted nothing read the case: the grants are not what is measured"
    if probed not in (403, 404):
        return f"the probe's refusal was not a refusal (HTTP {probed})"
    return ""


def mask(text: str, values: Sequence[str]) -> str:
    """`text` with each secret value (a password, a token) replaced, longest first."""
    for value in sorted((v for v in values if len(v) >= 6), key=len, reverse=True):
        text = text.replace(value, "<masked>")
    return text


def secret_values(environment: dict[str, str]) -> list[str]:
    """The environment's values that are secrets, by their names."""
    marks = ("PASSWORD", "SECRET", "TOKEN", "KEY")
    return [v for n, v in environment.items() if any(m in n for m in marks) and v]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait(url: str, seconds: int, what: str, alive: Callable[[], bool] | None = None) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as answer:
                if answer.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass
        if alive is not None and not alive():
            raise SystemExit(f"step4: {what} exited before it was ready")
        time.sleep(2)
    raise SystemExit(f"step4: {what} not ready in {seconds} s")


def _post(url: str, data: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), method="POST")
    with urllib.request.urlopen(request, timeout=30) as answer:
        result: dict[str, Any] = json.loads(answer.read())
        return result


def token_life(token: str) -> int:
    """A token's own life as the IdP granted it, `exp - iat`, read from its payload (no check of
    the signature: the Conduit checks that; this reads only what was granted)."""
    import base64

    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    return int(claims["exp"]) - int(claims["iat"])


def short_lived(tokens: dict[str, str]) -> str | None:
    """Why the run must not start, if any minted token dies before the run could end: what the IdP
    granted counts, not what the realm asked for."""
    short = {name: token_life(t) for name, t in tokens.items()}
    short = {name: life for name, life in short.items() if life < TOKEN_LIFE_NEEDED_S}
    if not short:
        return None
    named = ", ".join(f"{name} {life} s" for name, life in sorted(short.items()))
    return (
        f"the IdP granted tokens shorter than the run's {TOKEN_LIFE_NEEDED_S} s ({named}): they "
        "would be refused mid-measure and void every figure after"
    )


def mint(issuer: str, secret: str, subject: str) -> str:
    """The Conduit client's own token, exchanged for `subject`'s (RFC 8693, `subject_token`
    present: ADR-043's 24 September finding)."""
    url = f"{issuer}/protocol/openid-connect/token"
    client = {"client_id": "osprey-conduit", "client_secret": secret}
    own = _post(url, {"grant_type": "client_credentials", **client})
    exchanged = _post(url, {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange", **client,
        "subject_token": own["access_token"],
        "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "requested_subject": subject,
        "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
    })  # fmt: skip
    return str(exchanged["access_token"])


class Stack:
    """What one run started, removed by its label whatever happens."""

    def __init__(self, run: str) -> None:
        self.run = run
        self.images: list[str] = []
        self.folders: list[Path] = []

    def docker(self, *argv: str, env: dict[str, str] | None = None) -> str:
        done = subprocess.run(
            ["docker", *argv], capture_output=True, text=True, env=env or os.environ.copy(),
            check=False,
        )  # fmt: skip
        if done.returncode != 0:
            raise SystemExit(f"step4: docker {argv[0]} failed: {done.stderr.strip()[-500:]}")
        return done.stdout.strip()

    def logs(self, name: str, secrets_: Sequence[str]) -> str:
        """The last of a container's log, every secret value in it masked."""
        done = subprocess.run(
            ["docker", "logs", "--tail", "80", name], capture_output=True, text=True, check=False
        )
        return mask(done.stdout + done.stderr, secrets_)

    def remove(self) -> None:
        found = subprocess.run(
            ["docker", "ps", "-aq", "--filter", f"label=osprey.run={self.run}"],
            capture_output=True, text=True, check=False,
        ).stdout.split()  # fmt: skip
        if found:
            subprocess.run(["docker", "rm", "-f", *found], capture_output=True, check=False)
        for image in self.images:
            subprocess.run(["docker", "rmi", "-f", image], capture_output=True, check=False)
        import shutil

        for folder in self.folders:
            shutil.rmtree(folder, ignore_errors=True)


def realm_document() -> dict[str, Any]:
    """The deployment's own rendered realm (its Conduit client, claim mappers and audience), its
    users step 4's subjects and the probe alone. No secret in it: the client's is set after."""
    from harness.realm import render_realm

    from schemas.deployment import OspreyConfig

    realm = render_realm(OspreyConfig.model_validate({"profile": "local-lite"}), realm_name=REALM)
    realm["users"] = realm_users()
    # A user session's idle and maximum life cap a token's own, so they are raised with it.
    realm |= {
        "accessTokenLifespan": TOKEN_LIFE_S,
        "ssoSessionIdleTimeout": TOKEN_LIFE_S,
        "ssoSessionMaxLifespan": TOKEN_LIFE_S,
    }
    return realm


def _realm(origin: str, admin_password: str, secret: str) -> None:
    from harness import keycloak_admin as kc

    realm = realm_document()
    token = kc.admin_token(issuer=origin, admin_user="admin", admin_password=admin_password)
    request = urllib.request.Request(
        f"{origin}/admin/realms", data=json.dumps(realm).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )  # fmt: skip
    with urllib.request.urlopen(request, timeout=60):
        pass
    kc.ensure_unmanaged_attributes(issuer=origin, realm=REALM, token=token)
    kc.ensure_conduit_client_secret(issuer=origin, realm=REALM, token=token, client_secret=secret)
    kc.ensure_service_account_roles(issuer=origin, realm=REALM, token=token)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="step4_stack.py", description=__doc__)
    parser.add_argument("--case", required=True, help="the case M1 to M6 and M10 measure")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = [c for c in args.command if c != "--"] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("no command to run with the stack (after --)")
    run = os.environ.get("OSPREY_RUN_TAG") or f"step4-{secrets.token_hex(4)}"
    stack = Stack(run)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        return _run(stack, args.case, command)
    finally:
        stack.remove()


def _run(stack: Stack, case: str, command: list[str]) -> int:
    sys.path[:0] = [str(CORE), str(CORE / "packages"), str(BUILD)]
    env = os.environ.copy()
    admin_password = secrets.token_urlsafe(16)
    env |= {"KC_BOOTSTRAP_ADMIN_USERNAME": "admin", "KC_BOOTSTRAP_ADMIN_PASSWORD": admin_password}
    kp = _free_port()
    stack.docker(*keycloak_argv(stack.run, f"osprey-step4-idp-{slug(stack.run)}", kp), env=env)
    origin = f"http://127.0.0.1:{kp}"
    _wait(f"{origin}/realms/master/.well-known/openid-configuration", 240, "Keycloak")
    secret = secrets.token_urlsafe(24)
    _realm(origin, admin_password, secret)
    issuer = f"{origin}/realms/{REALM}"
    print("step4: the realm is up with its subjects", flush=True)

    images = {}
    for workload, dockerfile in (("api", "services/api/Dockerfile"),
                                 ("worker", "services/worker/Dockerfile")):  # fmt: skip
        given = os.environ.get(f"STEP4_{workload.upper()}_IMAGE")
        if given:
            images[workload] = given
            continue
        tag = f"ospreyflow/{workload}:step4-{slug(stack.run)}"
        stack.docker(*build_argv(dockerfile, tag))
        stack.images.append(tag)
        images[workload] = tag
    cp = _free_port()
    import tempfile

    values = poc_values()
    conduit = conduit_environment(
        {k: str(v) for k, v in values["environment"].items()}, dict(os.environ)
    )
    own = {w: workload_settings(values, w) for w in ("api", "worker")}
    folder = Path(tempfile.mkdtemp(prefix="step4-files-"))
    stack.folders.append(folder)
    mounts = {}
    for workload in ("api", "worker"):
        mounts[workload] = []
        for key, at, text in workload_files(values, workload):
            (folder / key).write_text(text, encoding="utf-8")
            (folder / key).chmod(0o644)
            mounts[workload].append((str(folder / key), at))
    env |= conduit | own["api"] | own["worker"]
    env |= {
        "OIDC_ISSUER": issuer,
        "OIDC_JWKS_URL": f"{issuer}/protocol/openid-connect/certs",
        "OIDC_AUDIENCE": "osprey-conduit",
        "OSPREY_WORKER_NAME": f"step4-{slug(stack.run)}",
    }
    name = slug(stack.run)
    api = service_argv(
        stack.run, f"osprey-step4-api-{name}", images["api"], "api", env, conduit_command(cp),
        settings=[*conduit, *own["api"]], mounts=mounts["api"],
    )  # fmt: skip
    worker = service_argv(
        stack.run, f"osprey-step4-worker-{name}", images["worker"], "worker", env,
        WORKER_COMMAND, settings=[*conduit, *own["worker"]], mounts=mounts["worker"],
    )  # fmt: skip
    stack.docker(*api, env=env)
    stack.docker(*worker, env=env)
    base = f"http://127.0.0.1:{cp}"
    try:
        _wait(f"{base}/healthz", 240, "the Conduit")
    except SystemExit:
        for part in ("api", "worker"):
            print(f"== the last of the {part}'s log", flush=True)
            print(stack.logs(f"osprey-step4-{part}-{name}", secret_values(env)), flush=True)
        raise
    print(f"step4: the Conduit and the worker are up at the poc's limits {poc_limits('api')}",
          flush=True)  # fmt: skip

    tokens = {s["username"]: mint(issuer, secret, s["username"]) for s in (*SUBJECTS, PROBE)}
    short = short_lived(tokens)
    if short:
        print(f"step4: preflight refused: {short}; the command was not run", flush=True)
        return 2
    refused = preflight(base, case, tokens["m10-measure"], tokens[PROBE["username"]])
    if refused:
        print(f"step4: preflight refused: {refused}; the command was not run", flush=True)
        return 2
    print("step4: preflight: m10-measure reads the case; a subject granted nothing is refused",
          flush=True)  # fmt: skip
    child = {**os.environ, **measure_environment(tokens, base, case)}
    return subprocess.run(command, env=child, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
