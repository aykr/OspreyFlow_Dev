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

## `--reapply`: a changed `osprey.yaml` on an installed deployment (ADR-137)

What `ospreyflow apply` runs: step 1 as above, through the same staging folder and with every secret
kept; preflight, with the deployment's own published ports not bind-tested (`reapply`'s docstring);
then the files moved into place and only the services whose rendered files changed started again
(`services_to_restart`). No build, no seed, no grants, no demo passwords, no verify, no volume.

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
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from demo_fixtures.datasets import domains_for
from harness import tls_check
from harness.keycloak_admin import (
    grant_service_account_roles,
    set_demo_admin_password,
    set_demo_analyst_password,
)
from harness.keycloak_theme import login_theme_options, write_login_theme
from harness.preflight import ALL_CHECKS, PreflightContext
from harness.preflight.result import Status
from harness.realm import (
    CONDUIT_CLIENT_ID,
    DEMO_ADMIN_SUBJECT,
    DEMO_ANALYST_SUBJECT,
    generate_client_secret,
    render_realm_json,
)
from harness.render import (
    BUILD_CONTEXT_FROM_OUTPUT_DIR,
    DEFAULT_CONFIG_PATH,
    DEFAULT_OUT_ROOT,
    REPO_ROOT,
    SECRETS_FILE,
    build_context_for,
    load_config,
    render,
    render_litellm_config,
    write_config_copy,
    write_private,
)
from harness.render import write as write_artefacts
from harness.reporting import reporting_secrets
from harness.site import (
    TLS_FINGERPRINT_FILE,
    answer_localhost_with_loopback,
    answer_the_deployment_here,
    sites,
)
from schemas.deployment import OspreyConfig, Profile, generated_folder

#: How long any one service gets to become healthy. Generous because the Conduit applies the graph
#: schema at startup and Keycloak imports a realm, and because a timeout that fires on a slow
#: machine teaches an operator to raise it rather than to read it.
DEFAULT_HEALTH_TIMEOUT_SECONDS = 300

#: A prompt whose answer is not shown as it is typed (`getpass.getpass`): a provider's key.
AskSecret = Callable[[str], str]


class ApplyFailed(RuntimeError):
    """A stage failed. Carries the stage name so the caller reports *where*, not only *that*."""

    def __init__(self, stage: str, detail: str) -> None:
        self.stage = stage
        self.detail = detail
        super().__init__(f"{stage}: {detail}")


def move_into_place(stage: Path, out_dir: Path) -> None:
    """The staged files copied over the deployment's folder, which keeps its own mode: `copytree`
    also copies the stage folder's mode onto it, so a named deployment's folder, made `700` by the
    command because it holds `deployment.env` (ADR-138), became `755` (found at step 11b)."""
    mode = out_dir.stat().st_mode & 0o777 if out_dir.is_dir() else None
    shutil.copytree(stage, out_dir, dirs_exist_ok=True)
    if mode is not None:
        out_dir.chmod(mode)


def analytics_secret_lines(config: OspreyConfig) -> str:
    """ClickHouse's password, minted here once and written under both names — the server's
    (`OSPREY_CLICKHOUSE_PASSWORD`, read by the compose file) and the Conduit's
    (`CLICKHOUSE_PASSWORD`, read by the adapter) — so the two cannot drift, as ArcadeDB's once did.
    Nothing for a DuckDB deployment (ADR-114 decision 9)."""
    if config.components.analytics_engine.value != "clickhouse":
        return ""
    password = generate_client_secret()
    return f"OSPREY_CLICKHOUSE_PASSWORD={password}\nCLICKHOUSE_PASSWORD={password}\n"


def provider_secret_lines(
    config: OspreyConfig, environ: Mapping[str, str], *, previous: str = ""
) -> str:
    """Each enabled model provider's key (ADR-114 Amendment 6 point 4, ADR-135 decision 2), carried
    from the installer's environment (`OSPREY_MODEL_KEY_<NAME>`; `OSPREY_MODEL_PROVIDER_KEY` for the
    single `models.provider`) into the deployment's secrets file only — read there by the LiteLLM
    gateway alone, never by the Conduit, never in `osprey.yaml` or a generated file, never printed.

    A key the deployment's earlier `deployment.env` (`previous`) already holds is not asked for
    again (ADR-132 ruling 6; `keep_existing_secrets` then keeps the earlier value, and `ospreyflow
    models key` is how one is changed). An enabled provider with neither stops the install here, in
    words naming the variable."""
    held = _env_pairs(previous)
    lines: list[str] = []
    for provider in config.models.enabled_providers:
        variable = config.models.key_variable(provider.name)
        key = environ.get(variable, "") or held.get(variable, "")
        if not key:
            raise ApplyFailed(
                "render",
                f"models enables the provider {provider.name}, and {variable} is not set. Set it "
                "in this terminal (it is kept only in the deployment's own secrets file) and run "
                "the install (or ospreyflow apply) again, or remove the provider from osprey.yaml.",
            )
        lines.append(f"{variable}={key}\n")
    return "".join(lines)


def _env_pairs(text: str) -> dict[str, str]:
    return {
        name: value
        for name, sep, value in (line.partition("=") for line in text.splitlines())
        if sep and name and not name.startswith("#")
    }


def mail_secret_lines(config: OspreyConfig, environ: Mapping[str, str]) -> str:
    """The mail server's password, carried from the installer's own environment into the
    deployment's secrets file (ADR-114 Amendment 5) — never into `osprey.yaml`, never printed. A
    server that needs
    signing in to, installed without it, stops the install here rather than leaving invitations that
    fail later."""
    if config.mail is None or not config.mail.username:
        return ""
    password = environ.get("OSPREY_SMTP_PASSWORD", "")
    if not password:
        raise ApplyFailed(
            "render",
            f"the mail server signs in as {config.mail.username}, and OSPREY_SMTP_PASSWORD is not "
            "set. Set it in this terminal (it is kept only in the deployment's own secrets file) "
            "and run the install again.",
        )
    return f"OSPREY_SMTP_PASSWORD={password}\n"


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


def _workspace_url(config: OspreyConfig) -> str:
    """The Glass, by name through the front proxy (ADR-114 Amendment 4)."""
    return sites(config).glass


def _conduit_url(args: argparse.Namespace, config: OspreyConfig) -> str:
    """Where the *host* can reach the Conduit.

    Not the same question as where the Conduit listens. With `network.expose_conduit` off — the
    default since 25 September 2026 — nothing on the host can reach port 8000 at all, and the only
    route in is the workspace's own nginx proxying `/v1`. With it on, the direct port is preferred
    because it takes the proxy out of whatever the operator is diagnosing.
    """
    if config.network.expose_conduit:
        return f"http://127.0.0.1:{args.api_port}"
    return _workspace_url(config)


def create_investigation(
    issuer: str,
    realm: str,
    secret: str,
    api_url: str,
    *,
    datasets: Sequence[str] | None = None,
) -> str:
    """Creates the investigation the seed tags its data with, and returns its id.

    **`datasets`** (ADR-126 decision 2) are the seeds the case is about to hold. The POST then
    sends `domains`, the union of their packs (`demo_fixtures.datasets.domains_for`), so the case
    is `[fibo, niem]` whenever HMP is seeded: its Author is this identity, as which no demo person
    signs in, and its case holds HMP's custody links. Left out, nothing is sent and the case is
    never chosen.

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

    # Before any request, and outside the `try` below: an unknown seed is the operator's own typing,
    # refused by name, not a `KeyError` taken for a missing field of the token response.
    try:
        case_domains = None if datasets is None else domains_for(datasets)
    except KeyError as unknown:
        raise ApplyFailed("seed", f"{unknown.args[0]!r} is not a seed dataset") from unknown

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
        headers = {"Authorization": f"Bearer {exchanged['access_token']}"}
        body: bytes | None = None
        if case_domains is not None:
            body = _json.dumps({"domains": case_domains}).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{api_url}/v1/investigations", data=body, headers=headers, method="POST"
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
        # Round 13cb: `scenarios` joins the other two under owner ruling R8 — every acceptance
        # row must be performable through the analyst's own door, and eleven were not because the
        # deployment was never seeded with what they need. A `KeyError` here is the right failure
        # for an unknown dataset: it names the dataset, and `--seed` is an operator's own typing.
        script = {
            "hmp": "scripts.seed_hmp_fixture",
            "fixture-corp": "scripts.seed_fixture_corp",
            "scenarios": "scripts.seed_scenarios",
        }[dataset]
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
                # The synthetic generators the seeds call live in `packages/demo_fixtures/`, which
                # the image carries, so the seed no longer needs the test tree mounted (it used to
                # import them from `tests/`, which is why seeding was checkout-only;
                # `spec/06_DECISIONS.md` ADR-054).
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


def object_store_lines(user: str, password: str) -> str:
    """Where the services find the object store, and its credentials (ADR-114 Amendment 9: the
    store is SeaweedFS, its S3 face on 8333; the `MINIO_*` names the services read are kept)."""
    return (
        f"OSPREY_MINIO_USER={user}\n"
        f"OSPREY_MINIO_PASSWORD={password}\n"
        "MINIO_ENDPOINT=objectstore:8333\n"
        f"MINIO_ACCESS_KEY={user}\n"
        f"MINIO_SECRET_KEY={password}\n"
    )


class ApplyRefused(ApplyFailed):
    """Apply cannot go on, said in words: what is missing and where it comes from."""

    def __init__(self, detail: str) -> None:
        super().__init__("render", detail)


def _needed(environ: Mapping[str, str], name: str, why: str) -> str:
    value = environ.get(name)
    if not value:
        raise ApplyRefused(
            f"{name} is not set: {why}. On a cloud server the first boot reads it from the cloud's "
            "secret store; by hand, export it before running the install"
        )
    return value


def managed_service_lines(
    config: OspreyConfig,
    *,
    environ: Mapping[str, str],
    minted: str,
    object_store_password: str,
    object_store_user: str = "ospreyflow",
) -> str:
    """Where the services find Postgres and the object stores (`05_DEPLOYMENT.md` §3a): the
    deployment's own containers, or what `external:` names — a managed server's password and a Blob
    key read from `environ` (the first boot put them there from the cloud's secret store), never
    minted and never in `osprey.yaml`."""
    external = config.external
    pg = external.postgres
    if pg is not None:
        password = _needed(environ, "OSPREY_POSTGRES_PASSWORD", "the managed database's password")
        host, port, user, database = pg.host, pg.port, pg.user, pg.database
    else:
        password, host, port, user, database = minted, "postgres", 5432, "osprey", "ospreyflow"
    lines = [
        f"OSPREY_POSTGRES_PASSWORD={password}",
        # **Every one of these, not just the host**: `services/api/config.py` defaults the port to
        # 5433 (the developer stack's), and the containers read `OSPREY_POSTGRES_*` while the
        # Conduit reads `POSTGRES_*` — both names carry one value or they silently disagree.
        f"POSTGRES_HOST={host}",
        f"POSTGRES_PORT={port}",
        f"POSTGRES_USER={user}",
        f"POSTGRES_PASSWORD={password}",
        f"POSTGRES_DB={database}",
        f"OSPREY_POSTGRES_USER={user}",
        f"OSPREY_POSTGRES_DB={database}",
    ]
    if pg is not None:
        lines.append(f"POSTGRES_SSLMODE={pg.sslmode}")
    store = external.object_store
    if store is not None:
        lines += [
            f"MINIO_ENDPOINT={store.endpoint}",
            "MINIO_USE_SSL=true",
            f"MINIO_REGION={store.region}",
            f"MINIO_BUCKET_PREFIX={store.bucket_prefix}",
            f"MINIO_CREDENTIALS={store.credentials}",
        ]
        if store.credentials == "keys":
            lines += [
                "MINIO_ACCESS_KEY="
                + _needed(environ, "OSPREY_S3_ACCESS_KEY", "the object store's access key"),
                "MINIO_SECRET_KEY="
                + _needed(environ, "OSPREY_S3_SECRET_KEY", "the object store's secret key"),
            ]
        text = "\n".join(lines) + "\n"
    else:
        own_store = object_store_lines(object_store_user, object_store_password)
        text = "\n".join(lines) + "\n" + own_store
    media = external.media
    if media is not None:
        key = _needed(environ, "AZURE_STORAGE_KEY", "the Blob storage account's key")
        text += (
            "OSPREY_MEDIA_STORE=blob\n"
            f"AZURE_STORAGE_ACCOUNT={media.blob_account}\n"
            f"AZURE_MEDIA_CONTAINER={media.blob_container}\n"
            f"AZURE_STORAGE_KEY={key}\n"
        )
    return text


def release_registry(lock_text: str) -> str:
    """Where a release's owned images live (ADR-114 Amendment 8 point 10): the Conduit's repository
    in the release's lock, without its name — a user repository's own `ghcr.io/<owner>`."""
    entries = (yaml.safe_load(lock_text) or {}).get("images") or []
    api = [e for e in entries if isinstance(e, dict) and e.get("service") == "api"]
    if not api:
        raise ApplyFailed("release", "the release's lock names no image of the Conduit (api)")
    return str(api[0]["repository"]).rsplit("/", 1)[0]


def pin_release_images(out_dir: Path, lock_path: Path) -> None:
    """Every image the verified lock names, pinned by its digest before anything starts."""
    from harness.update import pin_images

    pin_images(out_dir, lock_path.read_text(encoding="utf-8"))


#: A `deployment.env` key that holds a secret (ADR-132, the owner's ruling 6), a model provider's
#: key among them (ADR-135 decision 2).
_SECRET_KEY = re.compile(
    r"(PASSWORD|SECRET|SECRET_KEY|ACCESS_KEY)$|^OSPREY_MODEL_KEY_[A-Z0-9_]+$|^OSPREY_MODEL_PROVIDER_KEY$"
)


def keep_existing_secrets(new: str, previous: str) -> str:
    """`new` with every secret `previous` already held put back. A deployment's stores and identity
    provider keep the secrets they started with, so a re-render that mints fresh ones (and then
    stops, at preflight or anywhere) leaves the file and the running stack disagreeing, and the
    deployment cannot sign in to its own stores (found 31 October 2026). A secret only `previous`
    holds (`register_sign_in` adds some after the render) is carried over too."""
    held: dict[str, str] = {}
    for line in previous.splitlines():
        key, sep, value = line.partition("=")
        if sep and value and not line.startswith("#") and _SECRET_KEY.search(key):
            held[key] = value
    lines: list[str] = []
    seen: set[str] = set()
    for line in new.splitlines():
        key, sep, _value = line.partition("=")
        if sep and not line.startswith("#"):
            seen.add(key)
            if key in held:
                line = f"{key}={held[key]}"
        lines.append(line)
    carried = [f"{key}={value}" for key, value in held.items() if key not in seen]
    if carried:
        lines += ["# Kept from the deployment's earlier render (ADR-132, ruling 6).", *carried]
    return "\n".join(lines) + "\n"


def render_deployment(config: OspreyConfig, out_dir: Path, *, images_from: Path | None) -> Any:
    """Step 1: the deployment's files, and — for an install from a release — its images pinned to
    the verified lock before anything can start them."""
    # ADR-138: rendered outside a checkout, the images are built from the checkout by its own path.
    context = build_context_for(out_dir, config.components.source_path)
    rendered = render(config, allow_unpinned=True, build_context=context)
    write_artefacts(rendered, out_dir)
    if images_from is not None:
        pin_release_images(out_dir, images_from)
    return rendered


def preflight(context: PreflightContext) -> None:
    """Step 2: every check, before anything is built, started or moved into place. Raises with each
    failure in words."""
    failures = []
    for module in ALL_CHECKS:
        check = module.check(context)
        if check.status is Status.FAIL:
            failures.append(f"{check.check}: {check.what_is_wrong} — {check.what_to_do}")
    if failures:
        raise ApplyFailed("preflight", "\n  ".join(failures))


# ---- `--reapply`: a changed osprey.yaml on an installed deployment (ADR-137 decision 1) --------


def own_published_ports(compose_file: Path) -> set[int]:
    """The host ports the deployment's own running containers publish, as Compose itself reports
    them (`ps --format json`, each container's `Publishers`). Empty when nothing of it runs, or
    when Docker cannot be asked — then every port is checked as on a first install."""
    try:
        out = _run(_compose(compose_file) + ["ps", "--format", "json"], stage="preflight")
    except ApplyFailed:
        return set()
    stripped = out.strip()
    if not stripped:
        return set()
    if stripped.startswith("["):  # an older Compose prints one array
        rows = json.loads(stripped)
    else:
        rows = [json.loads(line) for line in stripped.splitlines() if line.strip()]
    found: set[int] = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("State") != "running":
            continue
        for publisher in row.get("Publishers") or []:
            port = int(publisher.get("PublishedPort") or 0)
            if port:
                found.add(port)
    return found


def _services(folder: Path) -> dict[str, Any]:
    path = folder / "compose.yaml"
    if not path.is_file():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    services = loaded.get("services") if isinstance(loaded, dict) else None
    return services if isinstance(services, dict) else {}


def _files(folder: Path) -> dict[str, bytes]:
    return {
        path.relative_to(folder).as_posix(): path.read_bytes()
        for path in folder.rglob("*")
        if path.is_file()
    }


def _reads_the_env_file(service: Mapping[str, Any]) -> bool:
    named = service.get("env_file") or []
    entries = [named] if isinstance(named, (str, dict)) else list(named)
    for entry in entries:
        path = entry.get("path") if isinstance(entry, dict) else entry
        if Path(str(path)).name == SECRETS_FILE:
            return True
    return False


def _own_environment(service: Mapping[str, Any]) -> set[str]:
    environment = service.get("environment") or {}
    if isinstance(environment, dict):
        return {str(k) for k in environment}
    return {str(item).partition("=")[0] for item in environment}


def _mounted_sources(service: Mapping[str, Any]) -> list[str]:
    """The deployment-folder paths a service mounts (`./litellm.yaml`, `./keycloak-theme/x`)."""
    sources: list[str] = []
    for volume in service.get("volumes") or []:
        source = volume.get("source") if isinstance(volume, dict) else str(volume).split(":")[0]
        if isinstance(source, str) and source.startswith("./"):
            sources.append(os.path.normpath(source))
    return sources


def is_run_once_job(service: Mapping[str, Any]) -> bool:
    """A run-once batch job (`render.py`'s `ingest`: `restart: "no"`, behind a profile), which `up`
    never starts. Named in an `up`, Compose starts it anyway; it exits (the loader exits 2 without
    its arguments), and `--wait` reads that as a failed start."""
    return service.get("restart") == "no" or bool(service.get("profiles"))


def services_to_restart(old: Path, new: Path) -> set[str]:
    """The services whose rendered configuration differs between the deployment as it is (`old`)
    and as rendered now (`new`), and nothing else (ADR-137 decision 1):
    - its own definition in `compose.yaml` differs, or it is new;
    - a `deployment.env` variable whose value changed reaches it — through `env_file`, unless its
      own `environment` sets that variable (which wins over the file), or by `${...}` in its
      definition;
    - a file it mounts from the deployment's folder changed.

    A run-once job (`is_run_once_job`) is never among them, though its files change with the rest:
    nothing of it is running to restart, and its next `compose run` reads the new files. Started and
    waited on, it failed the apply with every service healthy (step 2e's follow-up)."""
    before, after = _services(old), _services(new)
    old_files, new_files = _files(old), _files(new)
    changed_files = {
        name for name, content in new_files.items()
        if name not in (SECRETS_FILE, "compose.yaml") and old_files.get(name) != content
    }  # fmt: skip
    old_env = _env_pairs(old_files.get(SECRETS_FILE, b"").decode("utf-8"))
    new_env = _env_pairs(new_files.get(SECRETS_FILE, b"").decode("utf-8"))
    changed_vars = {k for k in old_env.keys() | new_env.keys() if old_env.get(k) != new_env.get(k)}
    restart: set[str] = set()
    for name, service in after.items():
        if not isinstance(service, dict) or is_run_once_job(service):
            continue
        if before.get(name) != service:
            restart.add(name)
            continue
        text = yaml.safe_dump(service)
        interpolated = {
            v for v in changed_vars if re.search(rf"\$\{{?{re.escape(v)}(?![A-Za-z0-9_])", text)
        }
        through_file = (
            changed_vars - _own_environment(service) if _reads_the_env_file(service) else set()
        )
        mounted = any(
            changed == source or changed.startswith(f"{source}/")
            for source in _mounted_sources(service)
            for changed in changed_files
        )
        if interpolated or through_file or mounted:
            restart.add(name)
    return restart


def _invalid(config_path: Path, error: Exception) -> ApplyFailed:
    if isinstance(error, ValidationError):
        said = "; ".join(
            f"{'.'.join(str(part) for part in e['loc']) or 'the file'}: {e['msg']}"
            for e in error.errors()
        )
    elif isinstance(error, yaml.YAMLError):
        said = f"it is not readable YAML ({str(error).splitlines()[0]})"
    else:
        said = str(error)
    return ApplyFailed(
        "validate",
        f"{config_path} is not valid, so nothing was changed: {said}. Correct it and run "
        "ospreyflow apply again.",
    )


def _keys_for_new_providers(
    config: OspreyConfig,
    environ: Mapping[str, str],
    held: Mapping[str, str],
    ask_secret: AskSecret | None,
) -> dict[str, str]:
    """A newly enabled provider's key (ADR-137 decision 1): from `OSPREY_MODEL_KEY_<NAME>` in the
    terminal, else a hidden prompt — never a visible one, and never asked for a key the deployment
    already holds (`ospreyflow models key` changes one). Returned by the variable it is kept in."""
    found: dict[str, str] = {}
    for provider in config.models.enabled_providers:
        variable = config.models.key_variable(provider.name)
        terminal = f"OSPREY_MODEL_KEY_{provider.name.upper()}"
        if held.get(variable):
            continue
        key = (environ.get(terminal) or environ.get(variable) or "").strip()
        if not key and ask_secret is not None:
            label = provider.label or provider.name
            key = ask_secret(f"Key for {label} ({terminal}; not shown): ").strip()
        if key and any(ch.isspace() for ch in key):
            raise ApplyFailed(
                "render", "a key has no spaces or line breaks in it; nothing was changed"
            )
        if key:
            found[variable] = key
    return found


def _held_as_environ(held: Mapping[str, str]) -> dict[str, str]:
    """What an install took from its terminal and the deployment's `deployment.env` holds, under
    the names the install read them by, so an apply needs none of them typed again (each is then
    kept as it was by `keep_existing_secrets`)."""
    found = {k: v for k, v in held.items() if _SECRET_KEY.search(k)}
    for kept, asked in (("MINIO_ACCESS_KEY", "OSPREY_S3_ACCESS_KEY"),
                        ("MINIO_SECRET_KEY", "OSPREY_S3_SECRET_KEY")):  # fmt: skip
        if held.get(kept):
            found[asked] = held[kept]
    return found


def _like_the_installed(config: OspreyConfig, out_dir: Path) -> tuple[OspreyConfig, Path | None]:
    """Rendered as the deployment was installed: from this checkout's source when its compose file
    builds (`--build`), or pinned to its own lock when its images are pinned by digest (a release,
    ADR-114 Amendment 8 point 10). The version is not changed here: `start --build` and `update`
    move it."""
    services = _services(out_dir)
    builds = any(isinstance(s, dict) and "build" in s for s in services.values())
    if builds and config.components.source_path is None:
        components = config.components.model_copy(update={"source_path": str(REPO_ROOT)})
        return config.model_copy(update={"components": components}), None
    lock = out_dir / "versions.lock"
    pinned = any(
        isinstance(s, dict) and s.get("image") and "@sha256:" in str(s["image"])
        and name in ("api", "workspace")
        for name, s in services.items()
    )  # fmt: skip
    if not builds and pinned and lock.is_file():
        os.environ["OSPREY_IMAGE_REGISTRY"] = release_registry(lock.read_text(encoding="utf-8"))
        return config, lock
    return config, None


def _keep_the_version(stage: Path, out_dir: Path, previous: Mapping[str, str]) -> None:
    """The deployment's version is what it runs, whatever this checkout has moved to since:
    `versions.lock` and `OSPREY_RELEASE_VERSION` are kept as they are."""
    lock = out_dir / "versions.lock"
    if lock.is_file():
        shutil.copyfile(lock, stage / "versions.lock")
    version = previous.get("OSPREY_RELEASE_VERSION")
    if version:
        env = stage / SECRETS_FILE
        lines = [
            f"OSPREY_RELEASE_VERSION={version}"
            if line.startswith("OSPREY_RELEASE_VERSION=")
            else line
            for line in env.read_text(encoding="utf-8").splitlines()
        ]
        write_private(env, "\n".join(lines) + "\n")


def reapply(
    config_path: Path,
    out_root: Path,
    *,
    environ: Mapping[str, str],
    ask_secret: AskSecret | None,
    realm: str = "osprey",
) -> set[str]:
    """ADR-137 decision 1: the deployment installed from `config_path` re-rendered from it, through
    the staging folder, with every secret kept; then only the services whose rendered files changed
    are started again (`services_to_restart`). Returns them. Never builds, seeds, makes accounts or
    a first administrator, adds a demo pack, or removes a container's data: `up --force-recreate`
    keeps every volume.

    **Preflight's port check and a running deployment.** The deployment's own containers hold its
    published ports, so on a first install's terms its own apply would always be refused (as the
    re-run install was, 31 October 2026). Ports that Compose reports the deployment's own running
    containers publishing are not bind-tested; every other declared port is, so a port another
    program holds still refuses the apply, with nothing changed."""
    try:
        if not config_path.is_file():
            raise FileNotFoundError(f"there is no {config_path.name} at {config_path}")
        config = load_config(config_path)
    except (OSError, yaml.YAMLError, ValidationError) as invalid:
        raise _invalid(config_path, invalid) from invalid
    out_dir = out_root / generated_folder(config)
    compose_file = out_dir / "compose.yaml"
    if not compose_file.is_file():
        raise ApplyFailed(
            "validate",
            f"nothing is installed at {out_dir}, the deployment {config_path} names; nothing was "
            "changed. Install it with ospreyflow install (a changed deployment.name is a new "
            "deployment).",
        )
    previous_env = (out_dir / SECRETS_FILE).read_text(encoding="utf-8")
    held = _env_pairs(previous_env)
    config, images_from = _like_the_installed(config, out_dir)
    keys = _keys_for_new_providers(config, environ, held, ask_secret)
    stage = out_dir.parent / f".{out_dir.name}.staging"
    try:
        stage_deployment(
            config,
            config_path,
            stage,
            realm=realm,
            demo_analyst=bool(held.get("OSPREY_DEMO_ANALYST_PASSWORD")),
            images_from=images_from,
            previous_env=previous_env,
            environ={**_held_as_environ(held), **environ, **keys},
        )
        _keep_the_version(stage, out_dir, held)
        preflight(
            PreflightContext(
                config=config, out_dir=stage, own_ports=frozenset(own_published_ports(compose_file))
            )
        )
        restart = services_to_restart(out_dir, stage)
        removed = set(_services(out_dir)) - set(_services(stage))
        # `copytree` copies each file's mode with it, so `deployment.env` arrives `600` (ADR-137
        # decision 2) over a file that was looser.
        move_into_place(stage, out_dir)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    if restart or removed:
        _run(
            _compose(compose_file)
            + ["up", "-d", "--no-deps", "--force-recreate", "--wait"]
            + (["--remove-orphans"] if removed else [])
            + sorted(restart),
            stage="up",
        )
    return restart


def reapply_main(
    args: argparse.Namespace, *, environ: Mapping[str, str], ask_secret: AskSecret | None
) -> int:
    answer_localhost_with_loopback()
    try:
        restarted = reapply(
            args.config, args.out_root, environ=environ, ask_secret=ask_secret, realm=args.realm
        )
    except ApplyFailed as failure:
        print(f"\napply: FAILED at stage '{failure.stage}'\n  {failure.detail}", file=sys.stderr)
        return 1
    if restarted:
        print(f"apply: the settings are applied; started again: {', '.join(sorted(restarted))}.")
    else:
        print("apply: Nothing changed that a service reads; nothing was started again.")
    return 0


def own_certificate(config: OspreyConfig) -> tuple[str, str] | None:
    """ADR-114 Amendment 33 decision 3, before anything is rendered: the organisation's certificate
    checked (`harness.tls_check`), refused in words with nothing changed. Returns its fingerprint
    and the `deployment.env` lines naming the account that owns the key, which the proxy runs as
    (so the key can stay `600`); None without `network.tls`."""
    tls = config.network.tls
    if tls is None:
        return None
    report = tls_check.check_deployment(config)
    if not report.ok:
        raise ApplyFailed(
            "certificate",
            "the organisation's certificate is refused, so nothing was changed:\n  - "
            + "\n  - ".join(report.refusals),
        )
    for warning in report.warnings:
        print(f"apply: warning: {warning}", file=sys.stderr)
    owner = Path(tls.key).stat()
    lines = (
        "# The account that owns network.tls.key; the proxy runs as it (ADR-114 Amendment 33).\n"
        f"OSPREY_PROXY_UID={owner.st_uid}\nOSPREY_PROXY_GID={owner.st_gid}\n"
    )
    assert report.fingerprint is not None
    return report.fingerprint, lines


@dataclass
class Staged:
    """A deployment rendered into its staging folder, and the secrets its `deployment.env` holds
    there — the ones it already had, where it had them (ADR-132 ruling 6), else fresh."""

    rendered: Any
    env_path: Path
    client_secret: str
    admin_password: str
    demo_analyst_password: str | None
    demo_admin_password: str | None


def stage_deployment(
    config: OspreyConfig,
    config_path: Path,
    stage: Path,
    *,
    realm: str,
    demo_analyst: bool,
    images_from: Path | None,
    previous_env: str,
    environ: Mapping[str, str],
) -> Staged:
    """Step 1, shared by an install and by `--reapply` (ADR-137): every file of the deployment
    rendered into `stage`, a folder beside the deployment's own at the same depth (so a relative
    storage path reads the same, ADR-054 Amendment 6), with `deployment.env` written `600` and
    every secret `previous_env` already held put back (ADR-132, the owner's ruling 6). Nothing here
    touches the deployment's own folder."""
    certificate = own_certificate(config)
    shutil.rmtree(stage, ignore_errors=True)
    env_path = stage / SECRETS_FILE
    rendered = render_deployment(config, stage, images_from=images_from)
    proxy_lines = ""
    if certificate is not None:
        fingerprint, proxy_lines = certificate
        # ADR-114 Amendment 33 decision 3: a renewed certificate changes this one file, which only
        # the proxy mounts, so `services_to_restart` starts the proxy alone. Not `deployment.env`:
        # every owned service reads that whole, and would be restarted with it.
        (stage / TLS_FINGERPRINT_FILE).write_text(fingerprint + "\n", encoding="utf-8")
    write_config_copy(config_path, stage)
    (stage / "realm.json").write_text(
        render_realm_json(config, demo_analyst=demo_analyst), encoding="utf-8"
    )
    # Round 13cda — the LiteLLM proxy's routing table, written the same way and for the same
    # reason as the realm above: a generated *service config*, mounted by the compose file,
    # rather than one of `05_DEPLOYMENT.md` §2.1's four operator-facing artefacts.
    (stage / "litellm.yaml").write_text(render_litellm_config(config), encoding="utf-8")
    # The sign-in page's look, beside the compose file that mounts it
    # (harness/keycloak_theme.py).
    write_login_theme(stage, **login_theme_options(config))
    secret = generate_client_secret()
    admin_password = generate_client_secret()
    # ADR-114 Amendment 5: Keycloak's own login on the deployment's Postgres.
    keycloak_db_password = generate_client_secret()
    arcadedb_password = generate_client_secret()
    postgres_password = generate_client_secret()
    # Only minted when asked for, like every other secret here — never derived from anything
    # in the repository, never printed except in the one-time summary at the very end
    # (06_DECISIONS.md ADR-050 objection 3's resolution).
    demo_analyst_password = generate_client_secret() if demo_analyst else None
    # The second demo subject (ADR-051) exists exactly when the first does, and has its own
    # password: two people, two credentials.
    demo_admin_password = generate_client_secret() if demo_analyst else None
    minio_user = "ospreyflow"
    minio_password = generate_client_secret()
    # Both minted here and written only into generated, gitignored output — 05_DEPLOYMENT.md
    # §2.5 ("never sees a secret… records where to look, never what it found") and §7
    # ("never in osprey.yaml, never in an image"). Neither is derived from anything in the
    # repository, and neither is printed.
    text = (
        env_path.read_text(encoding="utf-8")
        + "\n# Generated at apply time, never version-controlled (05_DEPLOYMENT.md §2.5/§7).\n"
        + f"OSPREY_OIDC_CLIENT_SECRET={secret}\n"
        + f"OSPREY_KEYCLOAK_ADMIN_PASSWORD={admin_password}\n"
        + f"OSPREY_KEYCLOAK_DB_PASSWORD={keycloak_db_password}\n"
        # One value, two names: the compose file sets the server's own root password from
        # `OSPREY_ARCADEDB_PASSWORD`, and the Conduit's adapter reads `ARCADEDB_ROOT_PASSWORD`.
        # They were generated separately at first, and the Conduit died on a 403 "User/Password
        # not valid" that named neither variable.
        + f"OSPREY_ARCADEDB_PASSWORD={arcadedb_password}\n"
        + f"ARCADEDB_ROOT_PASSWORD={arcadedb_password}\n"
        # The Conduit reads these at startup and refuses to start without the first, which is
        # its own deliberate fail-fast. Pointed at the Keycloak this same deploy renders.
        + f"OIDC_JWKS_URL=http://keycloak:8080/realms/{realm}"
        + "/protocol/openid-connect/certs\n"
        + f"OIDC_TOKEN_EXCHANGE_URL=http://keycloak:8080/realms/{realm}"
        + "/protocol/openid-connect/token\n"
        + f"OIDC_TOKEN_EXCHANGE_CLIENT_ID={CONDUIT_CLIENT_ID}\n"
        + f"OIDC_TOKEN_EXCHANGE_CLIENT_SECRET={secret}\n"
        + f"OIDC_ADMIN_USERS_URL=http://keycloak:8080/admin/realms/{realm}/users\n"
        # ADR-111 Amendment 2: the reporting components' secrets, only for what is switched on.
        + reporting_secrets(config)
        + analytics_secret_lines(config)
        + proxy_lines
        + mail_secret_lines(config, environ)
        + provider_secret_lines(config, environ, previous=previous_env)
        + "ARCADEDB_HOST=arcadedb\nVALKEY_HOST=valkey\n"
        # Postgres and the object stores: the deployment's own, or the cloud's (05 §3a).
        + managed_service_lines(
            config,
            environ=environ,
            minted=postgres_password,
            object_store_password=minio_password,
            object_store_user=minio_user,
        )
        + (
            f"OSPREY_DEMO_ANALYST_PASSWORD={demo_analyst_password}\n"
            if demo_analyst_password is not None
            else ""
        )
        + (
            f"OSPREY_DEMO_ADMIN_PASSWORD={demo_admin_password}\n"
            if demo_admin_password is not None
            else ""
        )
    )
    write_private(env_path, keep_existing_secrets(text, previous_env))
    # What the file now holds, not what this run minted: where a secret was kept, the stores and
    # the identity provider still have the kept one.
    held = _env_pairs(env_path.read_text(encoding="utf-8"))
    return Staged(
        rendered=rendered,
        env_path=env_path,
        client_secret=held["OSPREY_OIDC_CLIENT_SECRET"],
        admin_password=held["OSPREY_KEYCLOAK_ADMIN_PASSWORD"],
        demo_analyst_password=held.get("OSPREY_DEMO_ANALYST_PASSWORD") if demo_analyst else None,
        demo_admin_password=held.get("OSPREY_DEMO_ADMIN_PASSWORD") if demo_analyst else None,
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m harness.apply",
        description="The scripted golden-path deploy — spec/05_DEPLOYMENT.md §2.3.",
    )
    parser.add_argument("--profile", default=None, help="Overrides osprey.yaml's own profile.")
    parser.add_argument(
        "--build",
        action="store_true",
        help=(
            "Build owned images from this checkout's own source rather than pulling them by "
            "digest — the developer/CI path (round 07). Equivalent to declaring "
            "components.source_path in osprey.yaml, using this checkout's own root. Never set "
            "for a real customer deployment, which has no checkout to build from."
        ),
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--seed", default="", help="Comma-separated: hmp,fixture-corp,scenarios")
    parser.add_argument(
        "--health-timeout", type=int, default=DEFAULT_HEALTH_TIMEOUT_SECONDS, metavar="SECONDS"
    )
    parser.add_argument(
        "--keycloak-url",
        default=None,
        help=(
            "Where the rendered Keycloak is reachable, for the post-launch verify. Default: the "
            "deployment's identity origin, through the front proxy."
        ),
    )
    parser.add_argument("--realm", default="osprey")
    parser.add_argument(
        "--images-from",
        type=Path,
        default=None,
        help=(
            "A release's verified versions.lock (ADR-114 Amendment 8 point 10): run exactly its "
            "images, pinned by digest, and build nothing. `ospreyflow install` passes it on a "
            "release tag, after verifying the release."
        ),
    )
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
    parser.add_argument(
        "--reapply",
        action="store_true",
        help=(
            "Apply a changed osprey.yaml to the deployment already installed from it (ADR-137, "
            "what `ospreyflow apply` runs): render it again, keep every secret, ask for a newly "
            "enabled provider's key, and restart only the services whose files changed. Runs no "
            "install step and touches no data."
        ),
    )
    parser.add_argument(
        "--demo-analyst",
        action="store_true",
        help=(
            "Render a disposable analyst subject that can sign in interactively, with an "
            "apply-time password written into the deployment's own environment file and printed "
            "once. Absent by default. 06_DECISIONS.md ADR-050 objection 3."
        ),
    )
    return parser.parse_args(argv)


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    ask_secret: AskSecret | None = None,
) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    environ = os.environ if environ is None else environ
    if args.reapply:
        if ask_secret is None and sys.stdin.isatty():
            ask_secret = getpass.getpass
        return reapply_main(args, environ=environ, ask_secret=ask_secret)
    config = load_config(args.config)
    if args.profile:
        # `model_copy(update=...)` does not validate, so a bare string would sail through and fail
        # several lines later on `.value` with a message naming neither the flag nor the profile.
        # Coercing through the enum makes an unknown profile fail here, by name.
        config = config.model_copy(update={"profile": Profile(args.profile)})
    if args.build:
        components = config.components.model_copy(update={"source_path": str(REPO_ROOT)})
        config = config.model_copy(update={"components": components})
    if args.images_from is not None:
        # The release's own registry, so the render names the images the lock pins.
        os.environ["OSPREY_IMAGE_REGISTRY"] = release_registry(
            args.images_from.read_text(encoding="utf-8")
        )
        args.no_build = True
    out_dir = args.out_root / generated_folder(config)
    result = ApplyResult(profile=config.profile.value)
    # ADR-114 Amendment 4 decision 7: the deployment's names reach the proxy on this machine
    # whatever the operating system's resolver does with `*.localhost`; Amendment 33 decision 2:
    # and a server's own names, with its own certificate trusted, before the organisation's DNS.
    answer_localhost_with_loopback()
    answer_the_deployment_here(config)
    if args.keycloak_url is None:
        args.keycloak_url = sites(config).identity

    try:
        # 1. Render. The secrets a deployment already has are read first and kept (ADR-132, the
        # owner's ruling 6): its stores still hold them, whatever this run mints. Everything is
        # rendered into a staging folder beside the deployment's own, at the same depth so a
        # relative storage path reads the same (ADR-054 Amendment 6), checked there, and moved into
        # place only once preflight passes: a refused run writes nothing to the deployment.
        previous_path = out_dir / SECRETS_FILE
        previous_env = previous_path.read_text(encoding="utf-8") if previous_path.is_file() else ""
        stage = out_dir.parent / f".{out_dir.name}.staging"
        staged = stage_deployment(
            config,
            args.config,
            stage,
            realm=args.realm,
            demo_analyst=args.demo_analyst,
            images_from=args.images_from,
            previous_env=previous_env,
            environ=environ,
        )
        rendered, env_path = staged.rendered, out_dir / SECRETS_FILE
        secret, admin_password = staged.client_secret, staged.admin_password
        demo_analyst_password = staged.demo_analyst_password
        demo_admin_password = staged.demo_admin_password
        result.record("render", f"{len(rendered.artefacts) + 1} artefact(s) → {out_dir}")

        # 2. Preflight, before anything is built or started, and before the deployment's own folder
        # is touched (ADR-132, ruling 6).
        try:
            preflight(PreflightContext(config=config, out_dir=stage))
            move_into_place(stage, out_dir)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
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
            _run(_compose(compose_file) + ["build", "--pull"], stage="build")
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

        # 4c. The demo analyst's password — a realm import cannot carry it (harness/realm.py's own
        # "Not in" paragraph), so it is set the same way the client secret is: after import, with
        # the apply-time value this process just minted.
        if demo_analyst_password is not None:
            set_demo_analyst_password(
                issuer=args.keycloak_url,
                realm=args.realm,
                admin_user="admin",
                admin_password=admin_password,
                password=demo_analyst_password,
            )
            result.record("demo-analyst", "password set on the disposable analyst subject")
        if demo_admin_password is not None:
            set_demo_admin_password(
                issuer=args.keycloak_url,
                realm=args.realm,
                admin_user="admin",
                admin_password=admin_password,
                password=demo_admin_password,
            )
            result.record("demo-admin", "password set on the disposable admin subject")

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
                args.keycloak_url,
                args.realm,
                secret,
                _conduit_url(args, config),
                datasets=datasets,
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
    glass_url = f"{_workspace_url(config)}/"
    if investigation_id:
        glass_url += f"?investigation={investigation_id}"
    print(f"\n  the Glass:   {glass_url}")
    if config.network.expose_conduit:
        print(f"  the Conduit: http://127.0.0.1:{args.api_port}/healthz")
    else:
        print(f"  the Conduit: {_conduit_url(args, config)}/healthz (through the workspace proxy)")
    # Printed once, here, and nowhere else — never echoed by a later command.
    # `06_DECISIONS.md` ADR-050 objection 3's resolution.
    if demo_analyst_password is not None:
        print(f"\n  sign in as {DEMO_ANALYST_SUBJECT} with the password in {env_path}")
        print(f"  the Admin console account is {DEMO_ADMIN_SUBJECT}, same file")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
