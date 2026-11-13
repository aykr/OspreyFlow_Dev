"""A deployment's own PostgreSQL allows what its services may hold (ADR-114 Amendment 43).

Rule 12, the invariant and the test that fails without it:

- **The number is the product's own, and cannot fall behind it.** `CONDUIT_POOL_CEILING` must cover
  the Conduit's stores' asyncpg pools at their `max_size`, summed from the source itself (every
  `asyncpg.create_pool` call under `services/api` and `packages`), so a pool added or grown tomorrow
  fails here rather than in production. A pool whose `max_size` is not a literal cannot be counted,
  and is refused in words. The scanner is shown red on a planted pool in the real call site's shape.
- **Every profile with a PostgreSQL of its own renders it** (Lite and Small, sized or not).
- **Two Conduits and their pools at the ceiling fit the rendered PostgreSQL** (docker): a real
  `postgres:16.4` started with exactly the rendered command, two real Conduits started against it
  (ArcadeDB a stand-in answering empty, as platform-b's probe did), and then the connections their
  pools and the other services may still open taken up to the product's number. Against the image's
  own default (100), the same is refused (the red).
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
    POSTGRES_MAX_CONNECTIONS,
    postgres_command,
)
from harness.render import POSTGRES_IMAGE, render
from tools.layout import CORE

from schemas.deployment import OspreyConfig

from .tls_fixtures import docker


def _pool_sizes(root: Path) -> list[tuple[str, int]]:
    """Every `create_pool(...)` call's `max_size` under `root`'s Conduit code, tests left out."""
    found: list[tuple[str, int]] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        if "/tests/" in f"/{relative}" or path.name.startswith("test_") or ".venv" in relative:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else getattr(node.func, "id", "")
            )
            if name != "create_pool":
                continue
            size = next((k.value for k in node.keywords if k.arg == "max_size"), None)
            if not isinstance(size, ast.Constant) or not isinstance(size.value, int):
                raise AssertionError(
                    f"{relative}:{node.lineno}: a pool whose max_size is not a number written "
                    "there cannot be counted against CONDUIT_POOL_CEILING (ADR-114 Amendment 43)"
                )
            found.append((f"{relative}:{node.lineno}", size.value))
    return found


def _conduit_pools() -> list[tuple[str, int]]:
    return [
        *(("services/api/" + w, n) for w, n in _pool_sizes(CORE / "services" / "api")),
        *(("packages/" + w, n) for w, n in _pool_sizes(CORE / "packages")),
    ]


def _over_the_ceiling(pools: list[tuple[str, int]]) -> str | None:
    total = sum(n for _, n in pools)
    if total <= CONDUIT_POOL_CEILING:
        return None
    return (
        f"the Conduit's {len(pools)} pools reach {total} connections, past CONDUIT_POOL_CEILING "
        f"({CONDUIT_POOL_CEILING}): raise it in harness/profiles.py (ADR-114 Amendment 43)"
    )


def test_the_conduits_pools_at_their_max_fit_the_ceiling() -> None:
    pools = _conduit_pools()
    assert len(pools) >= 40, "the scanner found almost no pools: it is not reading the Conduit"
    assert _over_the_ceiling(pools) is None, _over_the_ceiling(pools)


def test_a_pool_added_past_the_ceiling_is_caught_in_the_real_call_sites_shape(
    tmp_path: Path,
) -> None:
    """Rule 15: planted as the stores write it, `await asyncpg.create_pool(dsn=dsn, ...)`, one
    connection more than the ceiling leaves."""
    room = CONDUIT_POOL_CEILING - sum(n for _, n in _conduit_pools())
    (tmp_path / "new_store.py").write_text(
        "import asyncpg\n\nasync def open_pool(dsn):\n"
        f"    return await asyncpg.create_pool(dsn=dsn, min_size=1, max_size={room + 1})\n",
        encoding="utf-8",
    )
    planted = _pool_sizes(tmp_path)
    assert planted == [("new_store.py:4", room + 1)]
    assert _over_the_ceiling([*_conduit_pools(), *planted]) is not None
    (tmp_path / "unsized.py").write_text(
        "import asyncpg\nasync def p(dsn, n):\n"
        "    return await asyncpg.create_pool(dsn, max_size=n)\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="cannot be counted"):
        _pool_sizes(tmp_path)


def _rendered_postgres(raw: dict[str, Any]) -> dict[str, Any]:
    config = OspreyConfig.model_validate(raw)
    artefacts = render(config, resolver=lambda _image: "sha256:" + "0" * 64).artefacts
    return dict(yaml.safe_load(artefacts["compose.yaml"])["services"]["postgres"])


SMALL = {"profile": "small", "network": {"public_origin": "https://demo.example.org"}}


@pytest.mark.parametrize(
    "raw",
    [{"profile": "local-lite"}, SMALL, {**SMALL, "resources": {"memory_gib": 64}}],
    ids=["lite", "small", "small-sized"],
)
def test_every_owned_postgres_is_rendered_with_the_products_number(raw: dict[str, Any]) -> None:
    command = _rendered_postgres(raw)["command"]
    assert command[:3] == ["postgres", "-c", f"max_connections={POSTGRES_MAX_CONNECTIONS}"]
    assert POSTGRES_MAX_CONNECTIONS >= CONDUITS_ALLOWED * CONDUIT_POOL_CEILING + 100


def test_an_existing_deployment_restarts_its_postgres_alone_on_apply(tmp_path: Path) -> None:
    """A deployed Small picks the number up on `ospreyflow apply`: its PostgreSQL's definition
    differs from the one rendered before (no command, the image's 100), so apply restarts it, and
    nothing else (ADR-137's `services_to_restart`)."""
    from harness.apply import services_to_restart
    from harness.render import write

    config = OspreyConfig.model_validate(SMALL)
    resolver = lambda _image: "sha256:" + "0" * 64  # noqa: E731
    write(render(config, resolver=resolver), tmp_path / "after")
    # As rendered before Amendment 43: the same deployment, its PostgreSQL with no command.
    old = render(config, resolver=resolver)
    compose = yaml.safe_load(old.artefacts["compose.yaml"])
    del compose["services"]["postgres"]["command"]
    old.artefacts["compose.yaml"] = yaml.safe_dump(compose)
    write(old, tmp_path / "before")
    assert services_to_restart(tmp_path / "before", tmp_path / "after") == {"postgres"}


# --- two Conduits against the rendered PostgreSQL (docker) ---------------------------------------


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
        while docker("exec", name, "pg_isready", "-U", "osprey", check=False).returncode != 0:
            assert time.monotonic() < deadline, docker("logs", name, check=False).stderr[-1500:]
            time.sleep(1)
        time.sleep(2)  # the image's init restarts the server once after pg_isready first answers
        while docker("exec", name, "pg_isready", "-U", "osprey", check=False).returncode != 0:
            assert time.monotonic() < deadline
            time.sleep(1)
        yield port, password
    finally:
        docker("rm", "-f", "-v", name, check=False)


async def _take_up_to(port: int, password: str, target: int) -> tuple[int, str | None]:
    """Opens connections until the server holds `target` client backends, or it refuses one."""
    dsn = f"postgresql://osprey:{password}@127.0.0.1:{port}/ospreyflow"
    first = await asyncpg.connect(dsn)
    opened = [first]
    try:
        held = int(await first.fetchval(
            "SELECT count(*) FROM pg_stat_activity WHERE backend_type = 'client backend'"
        ))  # fmt: skip
        for _ in range(max(0, target - held)):
            try:
                opened.append(await asyncpg.connect(dsn))
            except asyncpg.exceptions.TooManyConnectionsError as refused:
                return held + len(opened) - 1, str(refused)
        held = int(await first.fetchval(
            "SELECT count(*) FROM pg_stat_activity WHERE backend_type = 'client backend'"
        ))  # fmt: skip
        return held, None
    finally:
        await asyncio.gather(*(c.close() for c in opened), return_exceptions=True)


def _two_conduits_then_the_ceiling(
    command: list[str], monkeypatch: pytest.MonkeyPatch
) -> tuple[int, str | None]:
    from tests.services.api.test_statelessness import _ConduitInstance

    arcade = http.server.ThreadingHTTPServer(("127.0.0.1", _free_port()), _EmptyArcadeDB)
    threading.Thread(target=arcade.serve_forever, daemon=True).start()
    conduits: list[Any] = []
    try:
        with _postgres(command) as (port, password):
            for name, value in {
                "POSTGRES_HOST": "127.0.0.1", "POSTGRES_PORT": str(port), "POSTGRES_USER": "osprey",
                "POSTGRES_PASSWORD": password, "POSTGRES_DB": "ospreyflow",
                "ARCADEDB_HOST": "127.0.0.1", "ARCADEDB_HTTP_PORT": str(arcade.server_address[1]),
            }.items():  # fmt: skip
                monkeypatch.setenv(name, value)
            for _ in range(CONDUITS_ALLOWED):
                conduits.append(_ConduitInstance(f"http://127.0.0.1:{_free_port()}/jwks.json"))
            # The pools as load grows them: every Conduit's to its ceiling, and the other services'.
            return asyncio.run(_take_up_to(port, password, POSTGRES_MAX_CONNECTIONS - 5))
    finally:
        for conduit in conduits:
            conduit.kill()
        arcade.shutdown()


def test_two_conduits_at_their_ceiling_fit_the_rendered_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = _rendered_postgres(SMALL)["command"]
    assert command == postgres_command()
    held, refused = _two_conduits_then_the_ceiling(command, monkeypatch)
    assert refused is None, f"refused at {held} client connections: {refused}"
    assert held >= POSTGRES_MAX_CONNECTIONS - 5
