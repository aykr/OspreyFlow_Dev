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
- a hung loop reported healthy — `test_health_needs_a_recent_pass`;
- a removed dashboard identity's rows (N19, slice SE6b) still returned to a BI tool's role, on a real
  Postgres, not on the pure fake's model of row-level security — `test_a_stamped_dashboards_rows_are_
  not_returned_to_the_readers_role`, `test_every_table_with_a_dashboard_column_hides_a_stamped_
  dashboard`, `test_a_restart_of_the_sync_keeps_a_stamped_dashboard_hidden`, and
  `test_the_live_reader_check_sees_each_planted_fault` (policy dropped, security disabled).
"""

from __future__ import annotations

import dataclasses
import json
import secrets
import threading
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import asyncpg
import pytest
from services.api.config import PostgresConfig, ValkeyConfig
from services.api.report_freshness import ReportFreshness
from services.report_sync.mart import CONTROL_SCHEMA, DASHBOARD_TABLES, Mart
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
        #: Entra ID's v2.0 endpoint (ADR-148 Amendment 10): a client-credentials request must name
        #: the API's `.default` scope, and one that does not is refused (AADSTS90014, a 400).
        self.scope: str | None = None


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
            if world.scope is not None and form.get("scope", [""])[0] != world.scope:
                return self._send(400, json.dumps({"error": "invalid_request"}))
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


# --- ADR-148 Amendment 10: the report sync on Entra ID ------------------------------------------------

API_SCOPE = "api://aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee/.default"
DASHBOARD_APP = "dddddddd-eeee-4fff-8000-111111111111"


async def test_on_entra_the_token_asks_for_the_api_s_scope(world: tuple[str, _World]) -> None:
    """Entra's v2.0 endpoint refuses a client-credentials request without the API's scope."""
    base, w = world
    w.scope = API_SCOPE
    asked = TokenSource(f"{base}/token", DASHBOARD_APP, "right-secret", scope=API_SCOPE)
    unasked = TokenSource(f"{base}/token", DASHBOARD_APP, "right-secret")
    try:
        assert (await asked.get()).startswith("t-")
        with pytest.raises(SyncRefused, match="400"):
            await unasked.get()
    finally:
        await asked.aclose()
        await unasked.aclose()


def test_on_entra_the_configuration_names_the_scope_and_an_application_id() -> None:
    from services.report_sync.__main__ import dashboards_from_env

    env = {"REPORT_SYNC_TOKEN_URL": "https://login.microsoftonline.com/t/oauth2/v2.0/token",
           "REPORT_SYNC_CONDUIT_URL": "http://api:8000", "REPORT_SYNC_SCOPE": API_SCOPE,
           "REPORT_SYNC_DASHBOARDS": f'[{{"client_id": "{DASHBOARD_APP}", "secret": "s"}}]'}  # fmt: skip
    (board,) = dashboards_from_env(env)
    assert (board.client_id, board.scope) == (DASHBOARD_APP, API_SCOPE)
    keycloak_named = '[{"client_id": "osprey-dashboard-board", "secret": "s"}]'
    with pytest.raises(SystemExit, match="application id"):
        dashboards_from_env({**env, "REPORT_SYNC_DASHBOARDS": keycloak_named})
    with pytest.raises(SystemExit, match="REPORT_SYNC_SCOPE"):
        dashboards_from_env({**env, "REPORT_SYNC_SCOPE": "api://aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"})
    # Without a scope, Keycloak's rule as before: an application id is no dashboard's client there.
    with pytest.raises(SystemExit, match="osprey-dashboard-"):
        dashboards_from_env({k: v for k, v in env.items() if k != "REPORT_SYNC_SCOPE"})


async def test_a_pass_on_entra_asks_with_the_scope(world: tuple[str, _World], stores: tuple[Mart, Valkey]) -> None:
    """Through `sync_once`: the dashboard's scope reaches the token request it makes, and one token
    serves the whole pass (the case list and the feed it really pulls).

    - The world's tokens last an hour here, as Entra's do. Its default of 2 seconds (for the renewal
      test) is inside `TokenSource`'s 30-second margin, so every request would ask again and two
      tokens would be right (CI run 43597467719).
    - The application id is fresh per run, as `_dashboard`'s are: a claim in Valkey outlives the test,
      so a fixed id on a reused Valkey skipped the feed and passed with one token, having pulled
      nothing. `pulled == 1` holds it to a pass that pulls."""
    base, w = world
    w.scope = API_SCOPE
    w.lifetime = 3600
    application = str(uuid.uuid4())  # an Entra application id, fresh per run
    board = Dashboard(client_id=application, secret="right-secret", token_url=f"{base}/token",
                      conduit_url=base, weeks=12, scope=API_SCOPE)  # fmt: skip
    mart, valkey = stores
    summary = await sync_once([board], mart, valkey, slot=1)
    assert summary.failed == 0 and summary.pulled == 1 and w.tokens == 1, (summary, w.tokens)


# --- N19 (slice SE6b): a removed identity's rows are not returned to a BI tool's role -----
#
# The pure tests in `tests/services/api/test_removed_identity_mart_rows.py` run the real `Mart` and
# `ReportFreshness` over a stand-in for the driver, whose model of row-level security is the
# author's reading of Postgres. These run the same statements on a real Postgres and read as a real
# login role that is not the tables' owner (what Superset connects as), so a refusal or a bypass the
# stand-in does not model (the policy not applying to that role, the function not executable by it,
# the policy not surviving a second bootstrap) fails here.


def _as_reader(role: str, password: str) -> str:
    return dataclasses.replace(PostgresConfig.from_env(), user=role, password=password).dsn


@pytest.fixture
async def reader(stores: tuple[Mart, Valkey]) -> Iterator[str]:
    """A login role that may read the mart and nothing else, and its DSN."""
    mart, _ = stores
    role, password = f"reader_{new_id().lower()}", secrets.token_urlsafe(12)
    await mart.ensure_reader(role, password)
    yield _as_reader(role, password)  # type: ignore[misc]
    await mart.drop_reader(role)


@pytest.fixture
async def removals(stores: tuple[Mart, Valkey]) -> Iterator[list[str]]:
    """The removal record is shared by every mart schema (its own schema), so a test that stamps a
    dashboard takes its stamp away again."""
    mart, _ = stores
    stamped: list[str] = []
    yield stamped  # type: ignore[misc]
    async with mart._pool.acquire() as conn:  # noqa: SLF001
        await conn.execute(
            f"DELETE FROM {CONTROL_SCHEMA}.removed_dashboards WHERE dashboard = ANY($1::text[])",
            stamped,
        )


async def _two_dashboards(mart: Mart) -> tuple[str, str]:
    """A dashboard to remove and one to keep, each with a figure row and a pull row of a refusal."""
    gone, kept = (f"osprey-dashboard-{new_id().lower()}" for _ in range(2))
    for board in (gone, kept):
        at = datetime.now(UTC)
        feed = [("total", "alerts", "", "", 3)]
        await mart.replace(board, "case-1", "Operation Ledger", 12, feed, at)
        await mart.record_failure(board, "case-2", "the feed was refused (403)", at)
    return gone, kept


async def _what_the_reader_returns(
    dsn: str, schema: str, *boards: str
) -> dict[str, dict[str, int]]:
    """Per dashboard, per table, how many rows a read by the reader's role returns; and, under the
    empty name, how many rows an unfiltered read returns (a hidden row is not counted there)."""
    conn = await asyncpg.connect(dsn)
    try:
        found = {
            board: {
                table: await conn.fetchval(
                    f"SELECT count(*) FROM {schema}.{table} WHERE dashboard = $1", board
                )
                for table in DASHBOARD_TABLES
            }
            for board in boards
        }
        found[""] = {
            table: await conn.fetchval(f"SELECT count(*) FROM {schema}.{table}")
            for table in DASHBOARD_TABLES
        }
        return found
    finally:
        await conn.close()


async def _reader_leaks(dsn: str, schema: str, hidden: str, shown: str) -> list[str]:
    """What is wrong with what the reader returns, as a list: a hidden dashboard's row in any table
    (counted, filtered or not), a shown one's missing."""
    got = await _what_the_reader_returns(dsn, schema, hidden, shown)
    wrong = [f"{hidden}: {n} row(s) read from {t}" for t, n in got[hidden].items() if n]
    wrong += [f"{shown}: no row read from {t}" for t, n in got[shown].items() if not n]
    if got[""] != got[shown]:
        wrong.append(f"an unfiltered read counts {got['']}, not {got[shown]}: a hidden row counts")
    return wrong


async def test_a_stamped_dashboards_rows_are_not_returned_to_the_readers_role(
    stores: tuple[Mart, Valkey], reader: str, removals: list[str]
) -> None:
    """Before the stamp the reader reads both dashboards in both tables. From the stamp, whether or
    not the rows are deleted yet, it reads none of the stamped one's (by name or in a count), the
    owner's own read still holds them (hidden, not deleted), the reader's grant on the control
    schema is nil, and a present identity's rows are still read (rule 4)."""
    mart, _ = stores
    gone, kept = await _two_dashboards(mart)
    freshness = ReportFreshness(mart._pool, mart.schema)  # noqa: SLF001
    before = await _what_the_reader_returns(reader, mart.schema, gone, kept)
    assert before[gone] == before[kept] == {"pulls": 2, "figures": 1}, before

    removals.append(gone)
    assert await freshness.stamp(gone) is True
    assert await _reader_leaks(reader, mart.schema, gone, kept) == []
    assert await mart.figures(gone) and await mart.pulls(gone), "the stamp hides, never deletes"

    conn = await asyncpg.connect(reader)
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.fetch(f"SELECT * FROM {CONTROL_SCHEMA}.removed_dashboards")
    finally:
        await conn.close()

    assert await freshness.purge(gone) > 0
    assert await _reader_leaks(reader, mart.schema, gone, kept) == []
    assert await mart.figures(gone) == [] and await mart.pulls(gone) == []
    assert await mart.purge_removed() == 0, "a second purge finds nothing and harms nothing"
    assert await _reader_leaks(reader, mart.schema, gone, kept) == []


class _ClaimsAlways:
    """The claim in Valkey is not what these cases are about: every claim is ours."""

    async def set(self, *_: object, **__: object) -> bool:
        return True


async def test_the_next_sync_pass_purges_a_stamped_dashboard_and_the_reader_never_sees_it(
    world: tuple[str, _World], stores: tuple[Mart, Valkey], reader: str, removals: list[str]
) -> None:
    """A stamped identity still in the environment's list (its deletion at the provider failed, its
    secret works): the pass writes nothing for it, deletes what the Conduit could not, and a reader
    reads none of its rows before, during or after."""
    base, _ = world
    mart, _ = stores
    valkey = _ClaimsAlways()
    board, kept = _dashboard(base), _dashboard(base)
    await sync_once([board, kept], mart, valkey, slot=1)  # type: ignore[arg-type]
    assert len(await mart.figures(board.client_id)) == 2
    removals.append(board.client_id)
    assert await ReportFreshness(mart._pool, mart.schema).stamp(board.client_id)  # noqa: SLF001
    assert await _reader_leaks(reader, mart.schema, board.client_id, kept.client_id) == []
    await sync_once([board, kept], mart, valkey, slot=2)  # type: ignore[arg-type]
    assert await mart.figures(board.client_id) == [] and await mart.pulls(board.client_id) == []
    assert len(await mart.figures(kept.client_id)) == 2
    assert await _reader_leaks(reader, mart.schema, board.client_id, kept.client_id) == []


async def test_every_table_with_a_dashboard_column_hides_a_stamped_dashboard(
    stores: tuple[Mart, Valkey],
) -> None:
    """From Postgres's own catalogue, not from the code's list: every table in the mart's schema
    that names a dashboard has row-level security on and the policy that asks the stamp, so a table
    added later without the hiding fails here."""
    mart, _ = stores
    async with mart._pool.acquire() as conn:  # noqa: SLF001
        found = await conn.fetch(
            """SELECT c.relname, c.relrowsecurity,
                      (SELECT count(*) FROM pg_policies p WHERE p.schemaname = $1
                       AND p.tablename = c.relname AND p.policyname = 'hide_removed') AS policies
               FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = $1 AND c.relkind = 'r' AND EXISTS (
                   SELECT 1 FROM information_schema.columns k WHERE k.table_schema = $1
                   AND k.table_name = c.relname AND k.column_name = 'dashboard')""",
            mart.schema,
        )
    assert {r["relname"] for r in found} == set(DASHBOARD_TABLES)
    assert [r["relname"] for r in found if not r["relrowsecurity"] or r["policies"] != 1] == []


async def test_a_restart_of_the_sync_keeps_a_stamped_dashboard_hidden(
    stores: tuple[Mart, Valkey], reader: str, removals: list[str]
) -> None:
    """`CREATE POLICY` is re-run on every bootstrap (every start of `report-sync` and of any process
    that opens the mart): it must not widen what the reader reads, nor fail on what exists."""
    mart, _ = stores
    gone, kept = await _two_dashboards(mart)
    removals.append(gone)
    assert await ReportFreshness(mart._pool, mart.schema).stamp(gone)  # noqa: SLF001
    await mart._bootstrap()  # noqa: SLF001
    again = await Mart.connect(PostgresConfig.from_env().dsn, schema=mart.schema)
    try:
        assert await _reader_leaks(reader, mart.schema, gone, kept) == []
    finally:
        await again.close()


@pytest.mark.parametrize("plant", ["drop the policy on figures", "switch security off on pulls"])
async def test_the_live_reader_check_sees_each_planted_fault(
    stores: tuple[Mart, Valkey], reader: str, removals: list[str], plant: str
) -> None:
    """Rule 15: the same check, with the hiding undone on one table at a time, names the rows the
    reader then reads. A check that stayed empty here could not have found a leak."""
    mart, _ = stores
    gone, kept = await _two_dashboards(mart)
    removals.append(gone)
    assert await ReportFreshness(mart._pool, mart.schema).stamp(gone)  # noqa: SLF001
    assert await _reader_leaks(reader, mart.schema, gone, kept) == []
    async with mart._pool.acquire() as conn:  # noqa: SLF001
        if plant.startswith("drop"):
            await conn.execute(f"DROP POLICY hide_removed ON {mart.schema}.figures")
            # With no policy, row security denies every row to a non-owner: the reader reads none of
            # `figures`, the shown dashboard's included. The check says so, from the other side.
            expected = f"{kept}: no row read from figures"
        else:
            await conn.execute(f"ALTER TABLE {mart.schema}.pulls DISABLE ROW LEVEL SECURITY")
            expected = f"{gone}: 2 row(s) read from pulls"
    assert expected in await _reader_leaks(reader, mart.schema, gone, kept)
