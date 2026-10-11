"""`report-sync` (`06_DECISIONS.md` ADR-111 Amendment 2): dashboards fed from a reporting mart, never
from an OspreyFlow credential of their own. Real Postgres (the mart) and Valkey (the claim); the
identity provider and the Conduit are a small HTTP fixture that models their **refusals** (rule 15):
an expired or unknown token is 401, a client whose secret is wrong is refused a token, and a token is
issued with a short lifetime so renewal is exercised, not assumed.

What a mistake would do, and the case that catches it:
- a token used past its expiry — `test_the_token_is_renewed_before_it_expires`;
- a re-pull rewriting what did not change — `test_a_re_pull_changes_nothing_that_did_not_change`;
- a figure the feed no longer carries left in the mart — the same case;
- a revoked identity's rows silently refreshed or dropped — `test_a_refused_identity_leaves_its_rows_stale_and_says_so`;
- two sync instances pulling the same case twice — `test_one_pull_across_two_instances`;
- a deregistered dashboard's figures left behind — `test_a_dashboard_no_longer_configured_is_removed`;
- a BI tool able to write the mart — `test_the_readers_role_cannot_write`;
- a hung loop reported healthy — `test_health_needs_a_recent_pass`.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import asyncpg
import pytest
from services.api.config import PostgresConfig, ValkeyConfig
from services.report_sync.mart import Mart
from services.report_sync.sync import Dashboard, SyncRefused, TokenSource, sync_once
from valkey.asyncio import Valkey

from conduit_common.identity import new_id

CSV = "section,label,typology,week_start,value\ntotal,alerts,,,3\nopen_by_age,under a day,,,1\n"


class _World:
    def __init__(self) -> None:
        self.secret = "right-secret"
        self.lifetime = 2  # seconds: short, so renewal happens inside a test
        self.issued: dict[str, float] = {}
        self.revoked = False
        self.csv = CSV
        self.feeds = 0
        self.tokens = 0


def _handler(world: _World) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

        def _send(self, status: int, body: str, kind: str = "application/json") -> None:
            raw = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self) -> None:  # noqa: N802
            form = parse_qs(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode())
            if form.get("client_secret", [""])[0] != world.secret or world.revoked:
                return self._send(401, json.dumps({"error": "unauthorized_client"}))
            token = f"t-{new_id()}"
            world.issued[token] = time.time() + world.lifetime
            world.tokens += 1
            self._send(200, json.dumps({"access_token": token, "expires_in": world.lifetime}))

        def do_GET(self) -> None:  # noqa: N802
            token = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
            if world.issued.get(token, 0) < time.time():
                return self._send(401, json.dumps({"detail": "token expired or unknown"}))
            url = urlparse(self.path)
            if url.path == "/v1/investigations":
                return self._send(200, json.dumps([{"id": "case-1", "name": "Operation Ledger"}]))
            if url.path == "/v1/investigations/case-1/reports/feed":
                world.feeds += 1
                return self._send(200, world.csv, "text/csv")
            self._send(404, "{}")

    return Handler


@pytest.fixture
def world() -> Iterator[tuple[str, _World]]:
    state = _World()
    server = HTTPServer(("127.0.0.1", 0), _handler(state))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", state
    server.shutdown()


@pytest.fixture
async def stores() -> Iterator[tuple[Mart, Valkey]]:
    mart = await Mart.connect(PostgresConfig.from_env().dsn, schema=f"reports_{new_id().lower()}")
    cfg = ValkeyConfig.from_env()
    valkey = Valkey(host=cfg.host, port=cfg.port, db=cfg.db)
    yield mart, valkey  # type: ignore[misc]
    await mart.drop()
    await mart.close()
    await valkey.aclose()


def _dashboard(base: str, client_id: str | None = None, secret: str = "right-secret") -> Dashboard:
    # A fresh id per test: a claim in Valkey outlives the test that made it, as it should.
    client_id = client_id or f"osprey-dashboard-{new_id().lower()}"
    return Dashboard(client_id=client_id, secret=secret, token_url=f"{base}/token", conduit_url=base, weeks=12)


async def test_the_token_is_renewed_before_it_expires(world: tuple[str, _World]) -> None:
    base, state = world
    tokens = TokenSource(f"{base}/token", "osprey-dashboard-board", "right-secret", margin_seconds=1.0)
    first = await tokens.get()
    assert await tokens.get() == first, "reused while comfortably valid"
    time.sleep(1.2)  # inside the renewal margin of a 2 s token
    assert await tokens.get() != first
    assert state.tokens == 2
    await tokens.aclose()


async def test_a_re_pull_changes_nothing_that_did_not_change(world: tuple[str, _World], stores: tuple[Mart, Valkey]) -> None:
    base, state = world
    mart, valkey = stores
    board = _dashboard(base)
    await sync_once([board], mart, valkey, slot=1)
    before = await mart.figures(board.client_id)
    assert {(r["section"], r["label"], r["value"]) for r in before} == {("total", "alerts", 3), ("open_by_age", "under a day", 1)}
    await sync_once([board], mart, valkey, slot=2)
    after = await mart.figures(board.client_id)
    assert [r["changed_at"] for r in after] == [r["changed_at"] for r in before], "nothing changed, nothing rewritten"
    state.csv = "section,label,typology,week_start,value\ntotal,alerts,,,4\n"
    await sync_once([board], mart, valkey, slot=3)
    final = await mart.figures(board.client_id)
    assert {(r["section"], r["label"], r["value"]) for r in final} == {("total", "alerts", 4)}, "a figure no longer fed is removed"
    (pull,) = await mart.pulls(board.client_id)
    assert pull["last_failure"] is None and pull["last_pulled"] is not None


async def test_a_refused_identity_leaves_its_rows_stale_and_says_so(world: tuple[str, _World], stores: tuple[Mart, Valkey]) -> None:
    base, state = world
    mart, valkey = stores
    board = _dashboard(base)
    await sync_once([board], mart, valkey, slot=1)
    pulled = (await mart.pulls(board.client_id))[0]["last_pulled"]
    state.revoked = True
    summary = await sync_once([board], mart, valkey, slot=2)
    assert summary.failed == 1
    (pull,) = await mart.pulls(board.client_id)
    assert pull["last_pulled"] == pulled, "the rows keep the time they were last truly pulled"
    assert "refused" in pull["last_failure"]
    assert len(await mart.figures(board.client_id)) == 2, "left as they were, never refreshed from elsewhere"


async def test_one_pull_across_two_instances(world: tuple[str, _World], stores: tuple[Mart, Valkey]) -> None:
    base, state = world
    mart, valkey = stores
    board = _dashboard(base, client_id=f"osprey-dashboard-{new_id().lower()}")
    await sync_once([board], mart, valkey, slot=7)
    await sync_once([board], mart, valkey, slot=7)  # the second instance, same slot
    assert state.feeds == 1


async def test_a_dashboard_no_longer_configured_is_removed(world: tuple[str, _World], stores: tuple[Mart, Valkey]) -> None:
    base, _ = world
    mart, valkey = stores
    old, kept = _dashboard(base), _dashboard(base)
    await sync_once([old, kept], mart, valkey, slot=1)
    await sync_once([kept], mart, valkey, slot=2)
    assert await mart.figures(old.client_id) == []
    assert await mart.pulls(old.client_id) == []
    assert len(await mart.figures(kept.client_id)) == 2


async def test_a_wrong_secret_is_said_not_swallowed(world: tuple[str, _World]) -> None:
    base, _ = world
    tokens = TokenSource(f"{base}/token", "osprey-dashboard-board", "wrong", margin_seconds=1.0)
    with pytest.raises(SyncRefused, match="refused"):
        await tokens.get()
    await tokens.aclose()


async def test_the_readers_role_cannot_write(stores: tuple[Mart, Valkey]) -> None:
    mart, _ = stores
    reader = f"reader_{new_id().lower()}"
    await mart.ensure_reader(reader, "reader-pass")
    dsn = PostgresConfig.from_env().dsn
    conn = await asyncpg.connect(dsn.replace(dsn.split("//", 1)[1].split("@", 1)[0], f"{reader}:reader-pass"))
    try:
        await conn.fetch(f"SELECT * FROM {mart.schema}.figures")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(f"DELETE FROM {mart.schema}.figures")
    finally:
        await conn.close()
        await mart.drop_reader(reader)


def test_the_configuration_is_read_from_the_environment_and_refused_in_words() -> None:
    from services.report_sync.__main__ import dashboards_from_env

    env = {"REPORT_SYNC_TOKEN_URL": "http://kc/token", "REPORT_SYNC_CONDUIT_URL": "http://api:8000",
           "REPORT_SYNC_DASHBOARDS": '[{"client_id": "osprey-dashboard-board", "secret": "s", "weeks": 4}]'}  # fmt: skip
    (board,) = dashboards_from_env(env)
    assert (board.client_id, board.weeks, board.conduit_url) == ("osprey-dashboard-board", 4, "http://api:8000")
    with pytest.raises(SystemExit, match="osprey-dashboard-"):
        dashboards_from_env({**env, "REPORT_SYNC_DASHBOARDS": '[{"client_id": "osprey-conduit", "secret": "s"}]'})
    with pytest.raises(SystemExit, match="must both be set"):
        dashboards_from_env({"REPORT_SYNC_DASHBOARDS": "[]"})


def test_health_needs_a_recent_pass(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from services.report_sync.__main__ import healthy

    beat = tmp_path / "alive"
    assert not healthy(beat, 900, time.time()), "no pass yet is not healthy"
    beat.touch()
    now = beat.stat().st_mtime
    assert healthy(beat, 900, now + 1799)
    assert not healthy(beat, 900, now + 1800), "two intervals without a pass is a hung loop"
