"""`python -m harness.apply` — the scripted golden-path deploy.

`06_DECISIONS.md` ADR-049's Stage 2 §3. `05_DEPLOYMENT.md` §2.3's headless equivalent of clicking
Launch, and the thing Stage 2's exit test #2 measures: from a fresh clone, one command reaches a
health-checked stack on `local-lite`.

## The stages, in order, and why the order is the deliverable

1. **Render** (Stage 2 §1) — `deploy/generated/<profile>/`, plus the identity-provider realm.
2. **Preflight `--gate`** (Stage 2 §2) — exits non-zero while any check fails, **before** anything
   is built or started. A deploy that builds images and then discovers the ports are taken has
   wasted several minutes to tell you something it knew at the start.
3. **Build** — `docker compose build` for the OspreyFlow-owned images (Stage 2 §5a gave them
   `build:` contexts precisely so this needs no registry).
4. **Up, and wait** — `docker compose up -d --wait`, then a per-service health wait that **names
   the service that did not become healthy**. `--wait` on its own reports "container is unhealthy"
   without saying which, and on a twelve-container stack that is the difference between a diagnosis
   and a search.
5. **Seed**, when asked, under §2.4's **ordering guard** — below.
6. **Verify** — the three-sided token-exchange check ADR-043's amendment specifies. Part of what
   "health-checked" means: a stack whose principal resolution does not work is not a stack anyone
   can use.

## §2.4's ordering guard, and what it actually guards against

`DEMO_GUIDE.md` records the fault in its own words: "seeding needs the Conduit stopped (DuckDB takes
an exclusive lock the Conduit's own `AnalyticsPort` also holds a handle to) — so the Conduit starts
twice, not once, with seeding in between."

So when seeding is requested this module **resets the database, seeds while the Conduit is stopped,
and starts the Conduit afterwards** — and refuses outright if asked to seed into a running Conduit
rather than quietly working around it. A deploy that silently stopped the Conduit to seed would be
making a data-affecting decision on the operator's behalf.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.keycloak_admin import grant_service_account_roles
from harness.preflight import ALL_CHECKS, PreflightContext
from harness.preflight.result import Status
from harness.realm import (
    CONDUIT_CLIENT_ID,
    generate_client_secret,
    render_realm_json,
)
from harness.render import (
    BUILD_CONTEXT_FROM_OUTPUT_DIR,
    DEFAULT_CONFIG_PATH,
    DEFAULT_OUT_ROOT,
    load_config,
    render,
)
from harness.render import write as write_artefacts
from schemas.deployment import OspreyConfig, Profile

#: How long any one service gets to become healthy. Generous because the Conduit applies the graph
#: schema at startup and Keycloak imports a realm, and because a timeout that fires on a slow
#: machine teaches an operator to raise it rather than to read it.
DEFAULT_HEALTH_TIMEOUT_SECONDS = 300


class ApplyFailed(RuntimeError):
    """A stage failed. Carries the stage name so the caller reports *where*, not only *that*."""

    def __init__(self, stage: str, detail: str) -> None:
        self.stage = stage
        self.detail = detail
        super().__init__(f"{stage}: {detail}")


class SeedOrderingRefused(ApplyFailed):
    """§2.4's ordering guard, refusing rather than working around. See the module docstring."""


@dataclass
class ApplyResult:
    profile: str
    #: `(stage, outcome, seconds)`. The duration is recorded because `deploy/RUNBOOK.md` has to
    #: state a recovery time per path (`05_DEPLOYMENT.md` §6), and a total tells an operator
    #: nothing about which stage to plan a window around — on `local-lite` the answer is
    #: overwhelmingly container start-up rather than the data.
    stages: list[tuple[str, str, float]] = field(default_factory=list)
    started_at: float = field(default_factory=time.monotonic)
    _last: float = field(default_factory=time.monotonic)

    def record(self, stage: str, outcome: str) -> None:
        now = time.monotonic()
        self.stages.append((stage, outcome, now - self._last))
        self._last = now

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at


def _compose(compose_file: Path) -> list[str]:
    """Every compose call reads the deployment's own env file.

    Without `--env-file`, the secrets `apply` generates into `deployment.env` are invisible to
    compose — interpolation falls back to defaults, and a `${...:?}` variable aborts the command
    with a message about an unset variable rather than about a missing file. Found running the
    golden path: the env file was written correctly and then never used.
    """
    return [
        "docker",
        "compose",
        "--env-file",
        str(compose_file.parent / "deployment.env"),
        "-f",
        str(compose_file),
    ]


def _run(args: list[str], *, stage: str, cwd: Path | None = None, timeout: int = 1800) -> str:
    result = subprocess.run(
        args, capture_output=True, text=True, cwd=cwd, timeout=timeout, check=False
    )
    if result.returncode != 0:
        raise ApplyFailed(stage, f"{' '.join(args)} exited {result.returncode}\n{result.stderr}")
    return result.stdout


def compose_services(compose_file: Path) -> list[str]:
    out = _run(_compose(compose_file) + ["config", "--services"], stage="inspect")
    return [line.strip() for line in out.splitlines() if line.strip()]


def services_declaring_a_health_check(compose_file: Path) -> list[str]:
    """Only services with a declared health check can be waited on. The batch loader has none by
    design (`05_DEPLOYMENT.md` §3: a job that runs once and exits has no health to report), so
    waiting on everything would wait forever on something that is working correctly."""
    declared = []
    for service in compose_services(compose_file):
        inspected = _run(
            _compose(compose_file) + ["ps", "--format", "json", service],
            stage="inspect",
        )
        for line in inspected.splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("Health"):
                declared.append(service)
                break
    return declared


def wait_for_health(
    compose_file: Path, *, timeout_seconds: int = DEFAULT_HEALTH_TIMEOUT_SECONDS
) -> dict[str, str]:
    """Waits per service and **names the one that did not make it**.

    `docker compose up --wait` already fails on an unhealthy container, but its message does not
    say which — on a twelve-container stack that is a search rather than a diagnosis, which is why
    this exists alongside it rather than trusting it.
    """
    deadline = time.monotonic() + timeout_seconds
    final: dict[str, str] = {}
    pending = set(services_declaring_a_health_check(compose_file))
    while pending and time.monotonic() < deadline:
        for service in sorted(pending):
            rows = _run(
                _compose(compose_file) + ["ps", "--format", "json", service],
                stage="health",
            )
            health = ""
            for line in rows.splitlines():
                if line.strip():
                    health = json.loads(line).get("Health", "")
            final[service] = health
            if health == "healthy":
                pending.discard(service)
        if pending:
            time.sleep(3)
    if pending:
        named = ", ".join(f"{s} ({final.get(s) or 'no health reported'})" for s in sorted(pending))
        raise ApplyFailed(
            "health",
            f"after {timeout_seconds}s these service(s) were not healthy: {named}. "
            f"`docker compose -f {compose_file} logs <service>` has the reason.",
        )
    return final


def _conduit_is_running(compose_file: Path) -> bool:
    rows = _run(
        _compose(compose_file) + ["ps", "--format", "json", "api"],
        stage="seed",
    )
    return any(
        json.loads(line).get("State") == "running" for line in rows.splitlines() if line.strip()
    )


def _workspace_url() -> str:
    """The one surface a `local-lite` deployment publishes by default."""
    return f"http://127.0.0.1:{os.environ.get('OSPREY_WORKSPACE_PORT', '8080')}"


def _conduit_url(args: argparse.Namespace, config: OspreyConfig) -> str:
    """Where the *host* can reach the Conduit.

    Not the same question as where the Conduit listens. With `network.expose_conduit` off — the
    default since 25 September 2026 — nothing on the host can reach port 8000 at all, and the only
    route in is the workspace's own nginx proxying `/v1`. With it on, the direct port is preferred
    because it takes the proxy out of whatever the operator is diagnosing.
    """
    if config.network.expose_conduit:
        return f"http://127.0.0.1:{args.api_port}"
    return _workspace_url()


def create_investigation(issuer: str, realm: str, secret: str, api_url: str) -> str:
    """Creates the investigation the seed tags its data with, and returns its id.

    **This is why the Conduit starts twice.** `DEMO_GUIDE.md` states the constraint in its own
    words: creating an investigation is an HTTP call and needs the Conduit *running*; seeding needs
    it *stopped*, because DuckDB takes an exclusive lock the Conduit's own `AnalyticsPort` holds a
    handle to. So: up, create, stop, seed, up again.

    The bearer token is obtained by exchanging for the realm's own verify subject — the same
    mechanism the post-launch verify uses, rather than a second way of getting a token. That
    subject carries the clearance and org_unit claims a `Principal` needs, because the rendered
    realm gives it them for exactly this reason.
    """
    import json as _json
    import urllib.error
    import urllib.parse
    import urllib.request

    from harness.realm import CONDUIT_CLIENT_ID, VERIFY_SUBJECT

    token_url = f"{issuer}/realms/{realm}/protocol/openid-connect/token"

    def post(
        url: str, data: dict[str, str], headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            url, data=urllib.parse.urlencode(data).encode(), headers=headers or {}, method="POST"
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload: dict[str, Any] = _json.loads(response.read().decode())
            return payload

    try:
        own = post(
            token_url,
            {
                "grant_type": "client_credentials",
                "client_id": CONDUIT_CLIENT_ID,
                "client_secret": secret,
            },
        )
        exchanged = post(
            token_url,
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "client_id": CONDUIT_CLIENT_ID,
                "client_secret": secret,
                "subject_token": own["access_token"],
                "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
                "requested_subject": VERIFY_SUBJECT,
                "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
            },
        )
        request = urllib.request.Request(
            f"{api_url}/v1/investigations",
            headers={"Authorization": f"Bearer {exchanged['access_token']}"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return str(_json.loads(response.read().decode())["id"])
    except (urllib.error.HTTPError, urllib.error.URLError, KeyError, OSError) as error:
        detail = error.read().decode()[:300] if isinstance(error, urllib.error.HTTPError) else error
        raise ApplyFailed("seed", f"could not create an investigation to seed into: {detail}")


def seed(compose_file: Path, datasets: list[str], investigation_id: str) -> None:
    """§2.4's ordering guard, as behaviour rather than as a comment.

    Refuses if the Conduit is running. The alternative — stopping it silently — would be taking a
    data-affecting decision on the operator's behalf, and the whole point of the guard is that the
    ordering is made visible rather than worked around.

    **The seed runs inside the deployment's own network, not on the host.** `05_DEPLOYMENT.md` §7
    puts every store on an internal network with only the workspace and the Conduit exposed, so a
    host-side seed would need those ports published — a real security regression to make a demo
    convenient. Instead a one-shot container from the Conduit's own image runs the script, with
    `scripts/` and `packages/` mounted read-only: the image deliberately does not contain `scripts/`
    (a deployment does not ship its seeding tools), and mounting keeps it that way.
    """
    if _conduit_is_running(compose_file):
        raise SeedOrderingRefused(
            "seed",
            "the Conduit is running, and seeding needs it stopped — DuckDB takes an exclusive "
            "lock its AnalyticsPort also holds. Stop it first (`docker compose -f "
            f"{compose_file} stop api`), seed, then start it. Refusing rather than stopping it "
            "for you: that is a data-affecting decision and it is yours to make.",
        )
    root = compose_file.parent / BUILD_CONTEXT_FROM_OUTPUT_DIR
    for dataset in datasets:
        script = {"hmp": "scripts.seed_hmp_fixture", "fixture-corp": "scripts.seed_fixture_corp"}[
            dataset
        ]
        output = _run(
            _compose(compose_file)
            + [
                "run",
                "--rm",
                "--no-deps",
                "--entrypoint",
                "python",
                "-v",
                f"{root.resolve()}/scripts:/app/scripts:ro",
                # `scripts/seed_hmp_fixture.py` imports `tests.scenarios.fixtures.hmp_graph`
                # directly rather than duplicating the fixture — deliberately, per its own
                # docstring. So the seed needs the test tree as well, and the image does not carry
                # it (`.dockerignore` excludes `tests/`). **This is why seeding is a checkout-only
                # operation**: a distributed bundle has no fixtures to seed from, which is the
                # correct behaviour and not a limitation to work around.
                "-v",
                f"{root.resolve()}/tests:/app/tests:ro",
                "api",
                "-m",
                script,
                "--investigation-scope",
                investigation_id,
            ],
            stage="seed",
        )
        # **Every line, not the last one.** Each seed script reports its counts as it goes — the
        # HMP fixture's 400 Person nodes and 10 yards are printed before the event totals — and
        # taking only the final line discarded exactly the numbers an operator would check the
        # seed against. A seed that reports "done" is not evidence that it seeded anything.
        for line in output.splitlines():
            if line.strip():
                print(f"  seed[{dataset}]: {line.strip()}")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m harness.apply",
        description="The scripted golden-path deploy — docs/05_DEPLOYMENT.md §2.3.",
    )
    parser.add_argument("--profile", default=None, help="Overrides osprey.yaml's own profile.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--seed", default="", help="Comma-separated: hmp,fixture-corp")
    parser.add_argument(
        "--health-timeout", type=int, default=DEFAULT_HEALTH_TIMEOUT_SECONDS, metavar="SECONDS"
    )
    parser.add_argument(
        "--keycloak-url",
        default="http://127.0.0.1:8081",
        help="Where the rendered Keycloak is reachable, for the post-launch verify.",
    )
    parser.add_argument("--realm", default="osprey")
    parser.add_argument(
        "--no-build",
        action="store_true",
        help=(
            "Use the images already present rather than building them. For a registry-pull "
            "deployment, or a re-apply whose Dockerfiles have not changed."
        ),
    )
    parser.add_argument(
        "--api-port",
        default=os.environ.get("OSPREY_API_PORT", "8000"),
        help="Where the Conduit is published on this host, for the seed's investigation call.",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip the post-launch token-exchange verify. Reported in the summary when used.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    config = load_config(args.config)
    if args.profile:
        # `model_copy(update=...)` does not validate, so a bare string would sail through and fail
        # several lines later on `.value` with a message naming neither the flag nor the profile.
        # Coercing through the enum makes an unknown profile fail here, by name.
        config = config.model_copy(update={"profile": Profile(args.profile)})
    out_dir = args.out_root / config.profile.value
    result = ApplyResult(profile=config.profile.value)

    try:
        # 1. Render.
        rendered = render(config, allow_unpinned=True)
        write_artefacts(rendered, out_dir)
        (out_dir / "realm.json").write_text(render_realm_json(config), encoding="utf-8")
        secret = generate_client_secret()
        admin_password = generate_client_secret()
        arcadedb_password = generate_client_secret()
        postgres_password = generate_client_secret()
        postgres_user = "osprey"
        postgres_database = "ospreyflow"
        minio_user = "ospreyflow"
        minio_password = generate_client_secret()
        env_path = out_dir / "deployment.env"
        # Both minted here and written only into generated, gitignored output — 05_DEPLOYMENT.md
        # §2.5 ("never sees a secret… records where to look, never what it found") and §7
        # ("never in osprey.yaml, never in an image"). Neither is derived from anything in the
        # repository, and neither is printed.
        env_path.write_text(
            env_path.read_text(encoding="utf-8")
            + "\n# Generated at apply time, never version-controlled (05_DEPLOYMENT.md §2.5/§7).\n"
            + f"OSPREY_OIDC_CLIENT_SECRET={secret}\n"
            + f"OSPREY_KEYCLOAK_ADMIN_PASSWORD={admin_password}\n"
            + f"OSPREY_POSTGRES_PASSWORD={postgres_password}\n"
            + f"OSPREY_MINIO_USER={minio_user}\n"
            + f"OSPREY_MINIO_PASSWORD={minio_password}\n"
            # One value, two names: the compose file sets the server's own root password from
            # `OSPREY_ARCADEDB_PASSWORD`, and the Conduit's adapter reads `ARCADEDB_ROOT_PASSWORD`.
            # They were generated separately at first, and the Conduit died on a 403 "User/Password
            # not valid" that named neither variable.
            + f"OSPREY_ARCADEDB_PASSWORD={arcadedb_password}\n"
            + f"ARCADEDB_ROOT_PASSWORD={arcadedb_password}\n"
            # The Conduit reads these at startup and refuses to start without the first, which is
            # its own deliberate fail-fast. Pointed at the Keycloak this same deploy renders.
            + f"OIDC_JWKS_URL=http://keycloak:8080/realms/{args.realm}"
            + "/protocol/openid-connect/certs\n"
            + f"OIDC_TOKEN_EXCHANGE_URL=http://keycloak:8080/realms/{args.realm}"
            + "/protocol/openid-connect/token\n"
            + f"OIDC_TOKEN_EXCHANGE_CLIENT_ID={CONDUIT_CLIENT_ID}\n"
            + f"OIDC_TOKEN_EXCHANGE_CLIENT_SECRET={secret}\n"
            + f"OIDC_ADMIN_USERS_URL=http://keycloak:8080/admin/realms/{args.realm}/users\n"
            + "ARCADEDB_HOST=arcadedb\nVALKEY_HOST=valkey\n"
            # **Every one of these four, not just the host.** `services/api/config.py` defaults
            # `POSTGRES_PORT` to **5433** — a workaround for `deploy/compose/dev.yaml` publishing
            # there to dodge a native Postgres on 5432 — while a rendered container listens on
            # 5432 internally. Setting only the host left the Conduit dialling `postgres:5433` and
            # failing with a refused connection that named neither the port nor Postgres. The
            # database name and password diverge the same way: the container is configured from
            # `OSPREY_POSTGRES_*` and the Conduit reads `POSTGRES_*`, so both names carry one
            # value or they silently disagree.
            + "POSTGRES_HOST=postgres\nPOSTGRES_PORT=5432\n"
            + f"POSTGRES_USER={postgres_user}\nPOSTGRES_PASSWORD={postgres_password}\n"
            + f"POSTGRES_DB={postgres_database}\n"
            + f"OSPREY_POSTGRES_USER={postgres_user}\n"
            + f"OSPREY_POSTGRES_DB={postgres_database}\n"
            # **The third instance of one value under two names**, after ArcadeDB and Postgres
            # above. `MinIO` is configured from `OSPREY_MINIO_*` and `services/ingest/staging.py`
            # reads `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY`, falling back to `minioadmin`/`minioadmin`
            # — so the seed reached the staging bucket with the wrong credentials and MinIO answered
            # `ACCESS_DENIED during HeadBucket`, naming neither variable. Found running the seed.
            # `tests/harness/test_apply_env.py` is the case that fails if a fourth pair appears
            # and only one side of it is written.
            + "MINIO_ENDPOINT=minio:9000\n"
            + f"MINIO_ACCESS_KEY={minio_user}\n"
            + f"MINIO_SECRET_KEY={minio_password}\n",
            encoding="utf-8",
        )
        result.record("render", f"{len(rendered.artefacts) + 1} artefact(s) → {out_dir}")

        # 2. Preflight, before anything is built or started.
        context = PreflightContext(config=config, out_dir=out_dir)
        failures = []
        for module in ALL_CHECKS:
            check = module.check(context)
            if check.status is Status.FAIL:
                failures.append(f"{check.check}: {check.what_is_wrong} — {check.what_to_do}")
        if failures:
            raise ApplyFailed("preflight", "\n  ".join(failures))
        result.record("preflight", "all checks pass or skip")

        compose_file = out_dir / "compose.yaml"

        # 3. Build the owned images.
        #
        # `--no-build` exists for the two real cases where building here is wrong: a `cluster`
        # deployment pulls its images from a registry rather than building them on the node
        # (`05_DEPLOYMENT.md` §3), and a re-apply against a checkout whose Dockerfiles have not
        # changed should not spend minutes rebuilding them. It is not a way to deploy images that
        # do not exist — `up` fails immediately and by name if one is missing.
        if args.no_build:
            result.record("build", "skipped (--no-build): using the images already in the daemon")
        else:
            _run(_compose(compose_file) + ["build"], stage="build")
            result.record("build", "owned images built from this checkout")

        # 4. Up, then a per-service wait that names what did not make it.
        _run(_compose(compose_file) + ["up", "-d", "--wait"], stage="up")
        health = wait_for_health(compose_file, timeout_seconds=args.health_timeout)
        result.record("up", f"{len(health)} service(s) healthy")

        # 4b. The two service-account grants a realm import cannot express, because it would need
        # client ids that do not exist until the import has run. Separate grants on purpose: the
        # pre-check must not borrow the impersonation client's own authority.
        grant_service_account_roles(
            issuer=args.keycloak_url,
            realm=args.realm,
            admin_user="admin",
            admin_password=admin_password,
            client_secret=secret,
        )
        result.record("grants", "impersonation + view-users on the Conduit's service account")

        # 5. Seed, under the ordering guard.
        datasets = [d for d in args.seed.split(",") if d]
        investigation_id = ""
        if datasets:
            # Up, create, stop, seed, up again — the ordering the DuckDB lock forces.
            # **Through the workspace, not the Conduit's own port.** Since the owner's decision
            # of 25 September 2026 the Conduit is not published unless `osprey.yaml` asks
            # (05_DEPLOYMENT.md §2.6 item 1), so the host has exactly one way in — the same
            # same-origin proxy the Glass uses. Reaching for `--api-port` here would have made
            # the seed work only on a deployment configured the way it no longer is by default.
            investigation_id = create_investigation(
                args.keycloak_url, args.realm, secret, _conduit_url(args, config)
            )
            _run(_compose(compose_file) + ["stop", "api"], stage="seed")
            seed(compose_file, datasets, investigation_id)
            _run(_compose(compose_file) + ["start", "api"], stage="seed")
            wait_for_health(compose_file, timeout_seconds=args.health_timeout)
            result.record(
                "seed",
                f"{', '.join(datasets)} into investigation {investigation_id} "
                "(Conduit stopped for the seed, then restarted)",
            )

        # 6. Verify — the three assertions, against the running deployment.
        if args.skip_verify:
            result.record("verify", "SKIPPED — --skip-verify was passed")
        else:
            import asyncio

            from harness.verify import OPERATOR_FAILURE_MESSAGE, run_verify

            issuer = args.keycloak_url
            verified = asyncio.run(
                run_verify(
                    issuer=issuer,
                    realm=args.realm,
                    conduit_secret=secret,
                    unprivileged_secret=secret,
                )
            )
            bad = [v for v in verified if not v.ok]
            if bad:
                raise ApplyFailed(
                    "verify",
                    OPERATOR_FAILURE_MESSAGE
                    + "\n  "
                    + "\n  ".join(f"{v.assertion}: {v.detail}" for v in bad),
                )
            result.record("verify", f"{len(verified)}/3 assertions green")

    except ApplyFailed as failure:
        print(f"\napply: FAILED at stage '{failure.stage}'\n  {failure.detail}", file=sys.stderr)
        for stage, outcome, seconds in result.stages:
            print(f"  (completed) {stage} [{seconds:.0f}s]: {outcome}", file=sys.stderr)
        return 1

    print(f"apply: {result.profile} ready in {result.elapsed_seconds:.0f}s")
    for stage, outcome, seconds in result.stages:
        print(f"  {stage:<10} [{seconds:>3.0f}s]  {outcome}")
    # The two exposed surfaces, and nothing else — `05_DEPLOYMENT.md` §7 puts every store on an
    # internal network. The investigation id is carried in the query string because the Glass reads
    # it from there on first load; without it the workspace opens on an empty working set and the
    # seeded data looks as though it never arrived.
    glass_url = f"{_workspace_url()}/"
    if investigation_id:
        glass_url += f"?investigation={investigation_id}"
    print(f"\n  the Glass:   {glass_url}")
    if config.network.expose_conduit:
        print(f"  the Conduit: http://127.0.0.1:{args.api_port}/healthz")
    else:
        print(f"  the Conduit: {_conduit_url(args, config)}/healthz (through the workspace proxy)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
