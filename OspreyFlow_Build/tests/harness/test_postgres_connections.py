"""A deployment's own PostgreSQL allows what its services may hold (ADR-114 Amendment 43).

Rule 12, each invariant and the test that fails without it:

- **The Conduit's share is measured, not counted from the source.** A real Conduit is started with
  `asyncpg.create_pool` wrapped (a `sitecustomize` on its path), so every pool the process opens is
  recorded with its sizes, two stores opened twice included. The sum of their `max_size`, with Entra
  ID's people store (opened only when Entra is configured), must fit `CONDUIT_POOL_CEILING`; and the
  connections the process adds to the server at rest must equal the sum of their `min_size`, so a
  connection opened outside the recorded pools would show.
- **Every profile with a PostgreSQL of its own renders the number** (Lite and Small, sized or not),
  and the gateway's and Keycloak's pools are rendered as the number counts them.
- **The rendered number holds two Conduits at the ceiling, every other client and the reserve, at
  once** (docker): `postgres:16.4` started with exactly the rendered command; two real Conduits
  started against it; then, standing in for what their pools may still open (raw connections, not
  their own pools grown), each Conduit's room up to `CONDUIT_POOL_CEILING` and its running loads'
  allowance, the other clients' allowances, and the operator's reserve: the whole number, less one
  connection for the test's own question. None may be refused, so a number lower than the formula
  fails. Reds against the image's own command (100), at 250 (the second Conduit cannot start) and
  near the formula (the reserve): `gates/pg_two_conduits_red*.txt`. The at-rest check sees a missed
  pool only when its `min_size` is above 0.

Every store and service address the Conduits read is pinned to the throwaway PostgreSQL, the
ArcadeDB stand-in or a port checked closed first; the rest of the environment is the run's own (on
the test server, `stack_lease.sh offline`'s: the committed `osprey.yaml`, the closed store ports).
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import http.server
import json
import secrets
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import asyncpg
import pytest
import yaml
from harness.profiles import (
    CONDUIT_POOL_CEILING,
    CONDUITS_ALLOWED,
    GATEWAY_POOL_MAX,
    KEYCLOAK_POOL_MAX,
    POSTGRES_MAX_CONNECTIONS,
    RUNNING_LOADS_ALLOWED,
    SUPERSET_AND_REPORT_SYNC_MAX,
    postgres_command,
)
from harness.render import POSTGRES_IMAGE, render, render_litellm_config
from tools.layout import CORE

from schemas.deployment import OspreyConfig

from .tls_fixtures import docker

SMALL = {"profile": "small", "network": {"public_origin": "https://demo.example.org"}}
#: Closed ports for every service the Conduit may reach that this test does not stand in for.
CLOSED = {"VALKEY": 59993, "CLICKHOUSE": 59994, "MINIO": 59996, "LITELLM": 59997, "OIDC": 59998}


def _rendered(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    config = OspreyConfig.model_validate(raw)
    artefacts = render(config, resolver=lambda _image: "sha256:" + "0" * 64).artefacts
    return (
        yaml.safe_load(artefacts["compose.yaml"])["services"],
        yaml.safe_load(render_litellm_config(config)),
    )


@pytest.mark.parametrize(
    "raw",
    [{"profile": "local-lite"}, SMALL, {**SMALL, "resources": {"memory_gib": 64}}],
    ids=["lite", "small", "small-sized"],
)
def test_every_owned_postgres_is_rendered_with_the_products_number(raw: dict[str, Any]) -> None:
    command = _rendered(raw)[0]["postgres"]["command"]
    assert command[:3] == ["postgres", "-c", f"max_connections={POSTGRES_MAX_CONNECTIONS}"]


def test_the_gateway_and_keycloak_are_rendered_with_the_pools_the_number_counts() -> None:
    services, gateway = _rendered(SMALL)
    assert services["keycloak"]["environment"]["KC_DB_POOL_MAX_SIZE"] == str(KEYCLOAK_POOL_MAX)
    assert gateway["general_settings"]["database_connection_pool_limit"] == GATEWAY_POOL_MAX
    # One gateway worker: the render gives LiteLLM no `--num_workers`.
    assert "--num_workers" not in json.dumps(services["litellm"].get("command", []))


def _entra_people_pool_max() -> int:
    """Entra ID's people store's pool (`services/api/entra_people.py`), opened only when Entra is
    configured, so a Conduit started here does not open it: read from its one `create_pool` call."""
    tree = ast.parse((CORE / "services/api/entra_people.py").read_text(encoding="utf-8"))
    sizes = [
        k.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "create_pool"
        for k in node.keywords
        if k.arg == "max_size" and isinstance(k.value, ast.Constant)
    ]
    assert len(sizes) == 1, sizes
    return int(str(sizes[0]))


def test_an_existing_deployment_restarts_postgres_keycloak_and_the_gateway_on_apply(
    tmp_path: Path,
) -> None:
    """A deployed Small picks the number up on `ospreyflow apply` of a release that carries it: the
    definitions of PostgreSQL (its command), Keycloak (its pool) and the gateway (its pool) differ
    from those rendered before, so apply restarts those three and nothing else (ADR-137's
    `services_to_restart`)."""
    from harness.apply import services_to_restart
    from harness.render import write

    config = OspreyConfig.model_validate(SMALL)
    resolver = lambda _image: "sha256:" + "0" * 64  # noqa: E731
    write(render(config, resolver=resolver), tmp_path / "after")
    # `litellm.yaml` is written beside the render by apply itself (`harness/apply.py`).
    (tmp_path / "after" / "litellm.yaml").write_text(
        render_litellm_config(config), encoding="utf-8"
    )
    old = render(config, resolver=resolver)
    compose = yaml.safe_load(old.artefacts["compose.yaml"])
    del compose["services"]["postgres"]["command"]
    del compose["services"]["keycloak"]["environment"]["KC_DB_POOL_MAX_SIZE"]
    old.artefacts["compose.yaml"] = yaml.safe_dump(compose)
    write(old, tmp_path / "before")
    gateway = yaml.safe_load(render_litellm_config(config))
    del gateway["general_settings"]["database_connection_pool_limit"]
    (tmp_path / "before" / "litellm.yaml").write_text(
        yaml.safe_dump(gateway, sort_keys=False), encoding="utf-8"
    )
    assert services_to_restart(tmp_path / "before", tmp_path / "after") == {
        "postgres", "keycloak", "litellm",
    }  # fmt: skip


@pytest.mark.parametrize(
    ("before", "after"),
    [
        # Rendered before Amendment 43: the image's own command.
        (None, ["postgres", "-c", "max_connections={n}"]),
        # Sized (Amendment 33): the memory settings kept, after the number.
        (
            ["postgres", "-c", "shared_buffers=2048MB", "-c", "effective_cache_size=6144MB"],
            ["postgres", "-c", "max_connections={n}", "-c", "shared_buffers=2048MB",
             "-c", "effective_cache_size=6144MB"],
        ),
        # A number set by hand on the command: the product's, as `apply` would render it.
        (
            ["postgres", "-c", "max_connections=400", "-c", "shared_buffers=1024MB"],
            ["postgres", "-c", "max_connections={n}", "-c", "shared_buffers=1024MB"],
        ),
    ],
    ids=["unsized", "sized", "hand-set"],
)  # fmt: skip
def test_update_brings_an_existing_compose_file_to_the_number(
    before: list[str] | None, after: list[str]
) -> None:
    """`ospreyflow update` and `start --build` keep an existing compose file
    (`scripts/refresh.py`, `refresh-pg-update.diff`): this is what they apply to it."""
    from harness.profiles import postgres_connections_up_to_date

    services: dict[str, Any] = {
        "postgres": {"image": POSTGRES_IMAGE, **({"command": before} if before else {})},
        "keycloak": {"environment": {"KC_DB": "postgres"}},
    }
    assert postgres_connections_up_to_date(services) is True
    wanted = [part.format(n=POSTGRES_MAX_CONNECTIONS) for part in after]
    assert services["postgres"]["command"] == wanted
    assert services["keycloak"]["environment"]["KC_DB_POOL_MAX_SIZE"] == str(KEYCLOAK_POOL_MAX)
    # Safe to repeat, and what it writes is what the render writes for an unsized Small.
    assert postgres_connections_up_to_date(services) is False
    if before is None:
        assert services["postgres"]["command"] == _rendered(SMALL)[0]["postgres"]["command"]


# --- real Conduits against the rendered PostgreSQL (docker) --------------------------------------

#: Wraps `asyncpg.create_pool` in the Conduit's own process, before anything imports it.
_RECORD_POOLS = """
import json, os
import asyncpg

_real = asyncpg.create_pool


def create_pool(*args, **kwargs):
    with open(os.environ["OSPREY_TEST_POOL_LOG"], "a", encoding="utf-8") as out:
        sizes = {"min": kwargs.get("min_size", 10), "max": kwargs.get("max_size", 10)}
        out.write(json.dumps(sizes) + "\\n")
    return _real(*args, **kwargs)


asyncpg.create_pool = create_pool
"""


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class _EmptyArcadeDB(http.server.BaseHTTPRequestHandler):
    """Start-up asks the graph store first; this answers every command with nothing."""

    def _answer(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        body = json.dumps(
            {"result": ["ospreyflow"]} if "server" in self.path else {"result": []}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = _answer

    def log_message(self, *_args: object) -> None:
        pass


@contextlib.contextmanager
def _postgres(command: list[str]) -> Iterator[tuple[int, str]]:
    name = f"osprey-test-pgconn-{uuid.uuid4().hex[:8]}"
    port, password = _free_port(), secrets.token_urlsafe(12)
    docker("run", "-d", "--name", name, "-p", f"127.0.0.1:{port}:5432",
           "-e", "POSTGRES_USER=osprey", "-e", f"POSTGRES_PASSWORD={password}",
           "-e", "POSTGRES_DB=ospreyflow", POSTGRES_IMAGE, *command)  # fmt: skip
    try:
        deadline = time.monotonic() + 90
        # Over TCP: the image's set-up server answers on its socket alone, and is then restarted.
        ready = ("exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "osprey")
        while docker(*ready, check=False).returncode != 0:
            assert time.monotonic() < deadline, docker("logs", name, check=False).stderr[-1500:]
            time.sleep(1)
        yield port, password
    finally:
        docker("rm", "-f", "-v", name, check=False)


class _Clients:
    """Connections standing for clients' pools grown, held until the end."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.opened: list[asyncpg.Connection] = []

    async def held_by_the_server(self) -> int:
        """Client connections the server holds, this question's own left out."""
        conn = await asyncpg.connect(self.dsn)
        try:
            sql = "SELECT count(*) FROM pg_stat_activity WHERE backend_type = 'client backend'"
            return int(await conn.fetchval(sql)) - 1
        finally:
            await conn.close()

    async def open(self, n: int, what: str) -> None:
        for _ in range(n):
            try:
                self.opened.append(await asyncpg.connect(self.dsn))
            except asyncpg.exceptions.TooManyConnectionsError as refused:
                raise AssertionError(f"refused while {what}: {refused}") from refused

    async def close(self) -> None:
        await asyncio.gather(*(c.close() for c in self.opened), return_exceptions=True)


def _pools(log: Path) -> list[dict[str, int]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _the_product_at_once(
    command: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> list[str]:
    """Two Conduits and the other clients at their numbers, against `command`, step by step.
    Returns what was measured; raises at the first refusal, naming its step."""
    from tests.services.api.test_statelessness import _ConduitInstance

    for service, closed in CLOSED.items():
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", closed)) != 0, (
                f"{service}'s port {closed} is open"
            )
    (tmp_path / "hook").mkdir()
    (tmp_path / "hook" / "sitecustomize.py").write_text(_RECORD_POOLS, encoding="utf-8")
    arcade = http.server.ThreadingHTTPServer(("127.0.0.1", _free_port()), _EmptyArcadeDB)
    threading.Thread(target=arcade.serve_forever, daemon=True).start()
    conduits: list[Any] = []
    said: list[str] = []
    try:
        with _postgres(command) as (port, password):
            oidc = f"http://127.0.0.1:{CLOSED['OIDC']}"
            pinned = {
                "POSTGRES_HOST": "127.0.0.1", "POSTGRES_PORT": str(port), "POSTGRES_USER": "osprey",
                "POSTGRES_PASSWORD": password, "POSTGRES_DB": "ospreyflow",
                "POSTGRES_SSLMODE": "disable",
                "ARCADEDB_HOST": "127.0.0.1", "ARCADEDB_HTTP_PORT": str(arcade.server_address[1]),
                "VALKEY_HOST": "127.0.0.1", "VALKEY_PORT": str(CLOSED["VALKEY"]),
                "CLICKHOUSE_HOST": "127.0.0.1", "CLICKHOUSE_HTTP_PORT": str(CLOSED["CLICKHOUSE"]),
                "MINIO_ENDPOINT": f"127.0.0.1:{CLOSED['MINIO']}",
                "LITELLM_HOST": "127.0.0.1", "LITELLM_PORT": str(CLOSED["LITELLM"]),
                "OIDC_ISSUER": f"{oidc}/realms/osprey", "OIDC_ADMIN_USERS_URL": f"{oidc}/admin",
                "OIDC_TOKEN_EXCHANGE_URL": f"{oidc}/token", "OSPREY_ANALYTICS_ENGINE": "duckdb",
                "PYTHONPATH": str(tmp_path / "hook"),
            }  # fmt: skip
            for name, value in pinned.items():
                monkeypatch.setenv(name, value)
            clients = _Clients(f"postgresql://osprey:{password}@127.0.0.1:{port}/ospreyflow")
            try:
                for n in range(1, CONDUITS_ALLOWED + 1):
                    log = tmp_path / f"pools-{n}.jsonl"
                    monkeypatch.setenv("OSPREY_TEST_POOL_LOG", str(log))
                    before = asyncio.run(clients.held_by_the_server())
                    try:
                        conduits.append(_ConduitInstance(f"{oidc}/jwks"))
                    except TimeoutError as exc:
                        raise AssertionError(f"Conduit {n} did not come up: {exc}"[-800:]) from exc
                    pools = _pools(log)
                    at_rest = sum(p["min"] for p in pools)
                    ceiling = sum(p["max"] for p in pools)
                    added = asyncio.run(clients.held_by_the_server()) - before
                    said.append(
                        f"Conduit {n}: {len(pools)} pools opened, {at_rest} connections at their "
                        f"min, {ceiling} at their max; it added {added} to the server"
                    )
                    assert added == at_rest, said
                    entra = _entra_people_pool_max()
                    assert ceiling + entra <= CONDUIT_POOL_CEILING, (
                        f"one Conduit's pools reach {ceiling} (+{entra} with Entra ID), past "
                        f"CONDUIT_POOL_CEILING ({CONDUIT_POOL_CEILING}): raise it in profiles.py"
                    )
                    asyncio.run(
                        clients.open(
                            CONDUIT_POOL_CEILING - at_rest,
                            f"Conduit {n}'s pools grew to CONDUIT_POOL_CEILING",
                        )
                    )
                    asyncio.run(clients.open(RUNNING_LOADS_ALLOWED, f"Conduit {n}'s loads ran"))
                others = KEYCLOAK_POOL_MAX + GATEWAY_POOL_MAX + SUPERSET_AND_REPORT_SYNC_MAX
                asyncio.run(
                    clients.open(others, "Keycloak, the gateway, Superset and the report sync grew")
                )
                held = asyncio.run(clients.held_by_the_server())
                asyncio.run(
                    clients.open(
                        POSTGRES_MAX_CONNECTIONS - held - 1,
                        "the operator's reserve was used (the whole number, less one)",
                    )
                )
                total = asyncio.run(clients.held_by_the_server())
                said.append(
                    f"all at once: {total} client connections, of {POSTGRES_MAX_CONNECTIONS}"
                )
                assert total == POSTGRES_MAX_CONNECTIONS - 1, said
            finally:
                asyncio.run(clients.close())
        return said
    finally:
        for conduit in conduits:
            conduit.kill()
        arcade.shutdown()


def test_the_rendered_number_holds_two_conduits_at_the_ceiling_every_other_client_and_the_reserve(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    command = _rendered(SMALL)[0]["postgres"]["command"]
    assert command == postgres_command()
    print("\n".join(_the_product_at_once(command, monkeypatch, tmp_path)))
