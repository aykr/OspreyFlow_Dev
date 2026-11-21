"""A removed dashboard identity holds no rows in the reporting mart (backlog N19, slice SE6b;
`06_DECISIONS.md` ADR-111 Amendment 2, ADR-148 Amendments 10 and 21).

The invariant, in prose: once an administrator removes a dashboard identity, no row naming its
client id remains in any table `report-sync` writes, and an administrator who removes it is told in
words if the mart could not be reached. Superset's Admin and Alpha read the whole mart (ADR-148
Amendment 21), so a row left behind is a removed person's figures still readable.

Pure: no Postgres, no network. The mart is `FakeMartPool`, a stand-in for the asyncpg pool that
runs the **real** `Mart` and `ReportFreshness` code and answers only the statement shapes the real
mart issues. Like the real one it *refuses*: a table or schema that was not created is
`UndefinedTableError`, a statement it does not know is an error (never a quiet success), a
transaction that fails rolls back, and a fault can be planted on any statement. The tables are
whatever the real `Mart._bootstrap` creates (read from its own `CREATE TABLE` text), never a list
written here, so a table added to the mart later without the removal reaching it fails the first
test. It walks no folder.

What a mistake would do, and the case that catches it:
- the removal route never touches the mart (the fault on main) —
  `test_removing_a_dashboard_leaves_no_row_of_it_in_any_mart_table`;
- the removal reaches `figures` but not `pulls`, or any table added later —
  the same case, and `test_the_check_sees_a_removal_that_misses_a_table` shows it red;
- the removal deletes more than the one identity's rows — the same case (a neighbour's rows kept);
- the mart is down and the removal is reported as done —
  `test_a_removal_the_mart_refuses_is_a_refusal_the_administrator_sees`;
- a refused pull keeps a removed identity's rows —
  `test_a_refusal_never_keeps_a_removed_identitys_rows`;
- the next sync does not prune what is no longer configured, or prunes only one table, or prunes
  what is still configured — `test_the_next_sync_prunes_a_dashboard_no_longer_configured` and
  `test_the_sync_s_check_sees_each_planted_fault`;
- a prune that fails is swallowed or stops every other dashboard's pull —
  `test_a_failed_prune_is_said_in_words_and_the_pass_goes_on`.
"""

from __future__ import annotations

import copy
import re
import secrets
from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_handling_scheme,
    get_identity_admin,
    get_investigations,
    get_principal,
    get_report_freshness,
)
from services.api.identity_admin import PersonActionRefused
from services.api.report_freshness import ReportFreshness
from services.report_sync.mart import Mart
from services.report_sync.sync import Dashboard, SyncRefused, TokenSource, sync_once

from ontology.handling import load_uk_le_scheme
from schemas.admin import DashboardIdentity
from schemas.domain import Principal

SCHEMA = "osprey_reports"
ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="verify", roles=["osprey-admin"])
REMOVED = "osprey-dashboard-leaver"
KEPT = "osprey-dashboard-stayer"
NOW = datetime(2026, 11, 21, 9, 0, tzinfo=UTC)
FEED = [("total", "alerts", "", "", 3), ("open_by_age", "under a day", "", "", 1)]


# --- The mart's stand-in --------------------------------------------------------------------------


def _split_top_level(body: str) -> list[str]:
    parts, depth, current = [], 0, ""
    for ch in body:
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    return [*parts, current.strip()]


class FakeMartPool:
    """The asyncpg pool the mart and the Conduit's reader are given, answering the real mart's
    statement shapes and refusing the rest."""

    def __init__(self) -> None:
        self.schemas: set[str] = set()
        self.rows: dict[str, list[dict[str, Any]]] = {}
        self.columns: dict[str, list[tuple[str, str]]] = {}
        self.key: dict[str, list[str]] = {}
        self.faults: list[tuple[str, Exception]] = []
        self.deletes: list[str] = []

    # asyncpg's pool surface
    def acquire(self) -> Any:
        pool = self

        @asynccontextmanager
        async def held() -> Any:
            yield _Conn(pool)

        return held()

    async def close(self) -> None:
        return None

    def fail(self, containing: str, error: Exception) -> None:
        """A fault planted on every statement whose text contains `containing`."""
        self.faults.append((containing, error))

    def heal(self) -> None:
        self.faults.clear()

    # what a test asks
    def tables(self) -> list[str]:
        return sorted(self.rows)

    def rows_of(self, dashboard: str) -> dict[str, list[dict[str, Any]]]:
        return {
            t: [r for r in rs if r.get("dashboard") == dashboard] for t, rs in self.rows.items()
        }

    def left_for(self, dashboard: str) -> dict[str, int]:
        return {t: len(rs) for t, rs in self.rows_of(dashboard).items() if rs}

    def seed_every_table(self, dashboard: str) -> None:
        """A row for `dashboard` in each table that has none: whatever the real schema holds, so a
        table the removal does not know of is a table with a row left in it."""
        for table, rows in self.rows.items():
            if any(r.get("dashboard") == dashboard for r in rows):
                continue
            made: dict[str, Any] = {}
            for name, kind in self.columns[table]:
                made[name] = (
                    dashboard if name == "dashboard"
                    else NOW if kind.startswith("TIMESTAMP")
                    else 1 if kind in ("INTEGER", "BIGINT") else "x"
                )  # fmt: skip
            rows.append(made)

    # the statements
    def _table(self, schema: str, name: str) -> str:
        full = f"{schema}.{name}"
        if schema not in self.schemas:
            raise asyncpg.InvalidSchemaNameError(f'schema "{schema}" does not exist')
        if full not in self.rows:
            raise asyncpg.UndefinedTableError(f'relation "{full}" does not exist')
        return full

    def run(self, sql: str, args: tuple[Any, ...]) -> str:
        text = " ".join(sql.split())
        for needle, error in self.faults:
            if needle in text:
                raise error
        if m := re.fullmatch(r"CREATE SCHEMA IF NOT EXISTS (\w+)", text):
            self.schemas.add(m[1])
            return "CREATE SCHEMA"
        if m := re.fullmatch(r"CREATE TABLE IF NOT EXISTS (\w+)\.(\w+) \((.*)\)", text):
            full = f"{m[1]}.{m[2]}"
            columns, key = [], []
            for part in _split_top_level(m[3]):
                if part.startswith("PRIMARY KEY"):
                    key = [
                        c.strip() for c in part[part.index("(") + 1 : part.rindex(")")].split(",")
                    ]
                else:
                    name, kind = part.split()[:2]
                    columns.append((name, kind))
            self.rows.setdefault(full, [])
            self.columns[full], self.key[full] = columns, key
            return "CREATE TABLE"
        if m := re.match(r"INSERT INTO (\w+)\.figures VALUES \(\$1,", text):
            return self._upsert_figure(self._table(m[1], "figures"), args)
        if m := re.match(r"INSERT INTO (\w+)\.pulls \((.*?)\) VALUES", text):
            return self._upsert_pull(
                self._table(m[1], "pulls"), [c.strip() for c in m[2].split(",")], args
            )
        if m := re.fullmatch(
            r"DELETE FROM (\w+)\.(\w+) WHERE dashboard = \$1 AND case_id = \$2 "
            r"AND period_weeks = \$3 "
            r"AND \(section, label, typology, week_start\) NOT IN \(SELECT \* FROM unnest\(.*\)\)",
            text,
        ):
            table = self._table(m[1], m[2])
            keep = set(zip(*args[3:7], strict=True))
            doomed = [
                r for r in self.rows[table]
                if (r["dashboard"], r["case_id"], r["period_weeks"]) == args[:3]
                and (r["section"], r["label"], r["typology"], r["week_start"]) not in keep
            ]  # fmt: skip
            self.rows[table] = [r for r in self.rows[table] if r not in doomed]
            return f"DELETE {len(doomed)}"
        if m := re.fullmatch(
            r"DELETE FROM (\w+)\.(\w+) WHERE NOT \(dashboard = ANY\(\$1::text\[\]\)\)", text
        ):
            table = self._table(m[1], m[2])
            kept = set(args[0])
            doomed = [r for r in self.rows[table] if r["dashboard"] not in kept]
            self.rows[table] = [r for r in self.rows[table] if r["dashboard"] in kept]
            self.deletes.append(f"{table} not in {sorted(kept)}")
            return f"DELETE {len(doomed)}"
        if m := re.fullmatch(r"DELETE FROM (\w+)\.(\w+) WHERE dashboard = \$1", text):
            assert len(args) == 1 and isinstance(args[0], str), (
                "one client id, as the statement says"
            )
            table = self._table(m[1], m[2])
            doomed = [r for r in self.rows[table] if r["dashboard"] == args[0]]
            self.rows[table] = [r for r in self.rows[table] if r["dashboard"] != args[0]]
            self.deletes.append(f"{table} of {args[0]}")
            return f"DELETE {len(doomed)}"
        raise AssertionError(f"the fake mart does not model this statement: {text}")

    def _upsert_figure(self, table: str, args: tuple[Any, ...]) -> str:
        row = dict(zip((c for c, _ in self.columns[table]), args, strict=True))
        same = [r for r in self.rows[table] if all(r[k] == row[k] for k in self.key[table])]
        if not same:
            self.rows[table].append(row)
            return "INSERT 0 1"
        if same[0]["value"] == row["value"]:
            return "INSERT 0 0"  # the WHERE ... IS DISTINCT FROM clause: nothing rewritten
        same[0].update(value=row["value"], changed_at=row["changed_at"], case_name=row["case_name"])
        return "INSERT 0 1"

    def _upsert_pull(self, table: str, columns: list[str], args: tuple[Any, ...]) -> str:
        row = {c: None for c, _ in self.columns[table]}
        if "last_pulled" in columns:  # a good pull: the failure is cleared
            row.update(dashboard=args[0], case_id=args[1], last_pulled=args[2])
        else:  # a refusal: the last good pull is left as it was
            row.update(dashboard=args[0], case_id=args[1], last_failure=args[2], failed_at=args[3])
        same = [r for r in self.rows[table] if all(r[k] == row[k] for k in self.key[table])]
        if not same:
            self.rows[table].append(row)
        elif "last_pulled" in columns:
            same[0].update(last_pulled=row["last_pulled"], last_failure=None, failed_at=None)
        else:
            same[0].update(last_failure=row["last_failure"], failed_at=row["failed_at"])
        return "INSERT 0 1"

    def select(self, sql: str, args: tuple[Any, ...]) -> list[dict[str, Any]]:
        text = " ".join(sql.split())
        m = re.match(r"SELECT \* FROM (\w+)\.(\w+) WHERE dashboard = \$1 ORDER BY", text)
        if not m:
            raise AssertionError(f"the fake mart does not model this query: {text}")
        return [dict(r) for r in self.rows[self._table(m[1], m[2])] if r["dashboard"] == args[0]]


class _Conn:
    def __init__(self, pool: FakeMartPool) -> None:
        self._pool = pool

    async def execute(self, sql: str, *args: Any) -> str:
        return self._pool.run(sql, args)

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        return self._pool.select(sql, args)

    def transaction(self) -> Any:
        pool = self._pool

        @asynccontextmanager
        async def txn() -> Any:
            before = copy.deepcopy(pool.rows)
            try:
                yield
            except BaseException:
                pool.rows = before  # a failed transaction leaves nothing half done
                raise

        return txn()


async def _mart_with_two_identities() -> tuple[FakeMartPool, Mart]:
    pool = FakeMartPool()
    mart = Mart(pool, SCHEMA)  # type: ignore[arg-type]
    await mart._bootstrap()
    for client in (REMOVED, KEPT):
        await mart.replace(client, "case-1", "Operation Ledger", 12, FEED, NOW)
        await mart.record_failure(client, "case-2", "the feed was refused (403)", NOW)
        pool.seed_every_table(client)
    return pool, mart


# --- The route, as it is really called ------------------------------------------------------------


class _Identity:
    """The identity provider's side of the Admin: two registered dashboards. It refuses what
    the real one refuses: removing one that is not registered."""

    def __init__(self) -> None:
        self.registered = [
            DashboardIdentity(client_id=REMOVED, account_id="sa-leaver"),
            DashboardIdentity(client_id=KEPT, account_id="sa-stayer"),
        ]
        self.deleted: list[str] = []

    async def list_dashboards(self) -> list[DashboardIdentity]:
        return list(self.registered)

    async def delete_dashboard(self, client_id: str) -> None:
        if client_id not in {d.client_id for d in self.registered}:
            raise PersonActionRefused("no_such_dashboard", f"{client_id} is not registered.")
        self.registered = [d for d in self.registered if d.client_id != client_id]
        self.deleted.append(client_id)


class _Grants:
    async def revoke_everywhere(self, account_id: str, *, by: Principal) -> list[str]:
        return []


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


class _World:
    def __init__(self, pool: FakeMartPool) -> None:
        self.pool, self.identity, self.audit = pool, _Identity(), _Audit()
        self.client = TestClient(app, raise_server_exceptions=False)

    def remove(self, client_id: str = REMOVED) -> Any:
        return self.client.delete(f"/v1/admin/dashboards/{client_id}")


@pytest.fixture
async def world() -> Iterator[_World]:
    pool, _ = await _mart_with_two_identities()
    state = _World(pool)
    reader = ReportFreshness(pool, SCHEMA)  # type: ignore[arg-type]
    app.dependency_overrides[get_principal] = lambda: ADMIN
    app.dependency_overrides[get_audit] = lambda: state.audit
    app.dependency_overrides[get_identity_admin] = lambda: state.identity
    app.dependency_overrides[get_investigations] = _Grants
    app.dependency_overrides[get_report_freshness] = lambda: reader
    app.dependency_overrides[get_handling_scheme] = load_uk_le_scheme
    yield state  # type: ignore[misc]
    app.dependency_overrides.clear()


def test_the_fake_mart_holds_what_the_real_one_writes(world: _World) -> None:
    """The setup is not vacuous: both identities hold rows in every table the real mart creates,
    and the real schema has more than one table (so "any table" is a claim about something)."""
    assert len(world.pool.tables()) >= 2
    for client in (REMOVED, KEPT):
        assert set(world.pool.left_for(client)) == set(world.pool.tables())


def test_removing_a_dashboard_leaves_no_row_of_it_in_any_mart_table(world: _World) -> None:
    kept_before = world.pool.left_for(KEPT)
    assert world.remove().status_code == 204
    assert world.identity.deleted == [REMOVED]
    assert world.pool.left_for(REMOVED) == {}, "a removed identity's rows are still in the mart"
    assert world.pool.left_for(KEPT) == kept_before, "another identity's rows must be left alone"


def test_the_check_sees_a_removal_that_misses_a_table(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: the same observation, red on a removal that reaches one table only."""
    from services.api import report_freshness

    monkeypatch.setattr(report_freshness, "DASHBOARD_TABLES", ("figures",))
    assert world.remove().status_code == 204
    assert set(world.pool.left_for(REMOVED)) == set(world.pool.tables()) - {f"{SCHEMA}.figures"}


@pytest.mark.parametrize(
    "error",
    [
        OSError("the mart is unreachable"),
        asyncpg.InsufficientPrivilegeError("permission denied for table pulls"),
    ],
    ids=["unreachable", "the Conduit's role may not delete"],
)
def test_a_removal_the_mart_refuses_is_a_refusal_the_administrator_sees(
    world: _World, error: Exception
) -> None:
    world.pool.fail(f"DELETE FROM {SCHEMA}", error)
    before = world.pool.left_for(REMOVED)
    refused = world.remove()
    assert refused.status_code == 503, refused.text
    body = refused.json()["detail"]
    assert body["error"] == "reporting_mart_unreachable"
    assert "reporting mart" in body["detail"] and "removing it again" in body["detail"]
    assert world.identity.deleted == [], "not removed: it stays registered, so a retry finds it"
    assert not [r for r in world.audit.records if r["action"] == "remove_dashboard"]
    assert world.pool.left_for(REMOVED) == before
    world.pool.heal()
    assert world.remove().status_code == 204
    assert world.pool.left_for(REMOVED) == {}


def test_a_removal_that_fails_part_way_leaves_nothing_half_removed(world: _World) -> None:
    """One transaction: a refusal on the last table does not leave the others emptied alone."""
    from services.report_sync.mart import DASHBOARD_TABLES

    last = DASHBOARD_TABLES[-1]
    world.pool.fail(f"DELETE FROM {SCHEMA}.{last}", asyncpg.PostgresConnectionError("lost"))
    before = world.pool.left_for(REMOVED)
    assert world.remove().status_code == 503
    assert world.pool.left_for(REMOVED) == before


def test_a_deployment_with_no_mart_removes_a_dashboard_as_before() -> None:
    """Reporting off: there is no mart and nothing to remove, which is not a failure."""
    pool = FakeMartPool()  # no schema, no table
    state = _World(pool)
    app.dependency_overrides[get_principal] = lambda: ADMIN
    app.dependency_overrides[get_audit] = lambda: state.audit
    app.dependency_overrides[get_identity_admin] = lambda: state.identity
    app.dependency_overrides[get_investigations] = _Grants
    app.dependency_overrides[get_report_freshness] = lambda: ReportFreshness(pool, SCHEMA)  # type: ignore[arg-type]
    app.dependency_overrides[get_handling_scheme] = load_uk_le_scheme
    try:
        assert state.remove().status_code == 204
        assert state.identity.deleted == [REMOVED]
    finally:
        app.dependency_overrides.clear()


def test_one_not_registered_is_refused_and_touches_no_mart_row(world: _World) -> None:
    before = world.pool.left_for(KEPT)
    refused = world.remove("osprey-dashboard-gone")
    assert refused.status_code == 409
    assert world.pool.left_for(KEPT) == before and world.pool.left_for(REMOVED) != {}


# --- The sync side --------------------------------------------------------------------------------


def _board(client_id: str) -> Dashboard:
    """A configured dashboard. Its secret is made at run time; nothing is sent anywhere (see
    `the_identity_provider_refuses`)."""
    return Dashboard(client_id=client_id, secret=secrets.token_urlsafe(8),
                     token_url="http://idp.invalid/token",
                     conduit_url="http://api.invalid")  # fmt: skip


@pytest.fixture(autouse=True)
def the_identity_provider_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every configured dashboard's token is refused, as a removed identity's is (the identity
    provider no longer knows it) and as a revoked secret's is. The pass then reaches
    `record_failure`, which keeps the rows it finds. `TokenSource.get` raises exactly what its real
    refusal raises (`SyncRefused`, in words)."""

    async def refuse(self: TokenSource) -> str:
        raise SyncRefused(f"the identity provider refused {self._client_id} (401)")

    monkeypatch.setattr(TokenSource, "get", refuse)


class _NoValkey:
    async def set(self, *_: Any, **__: Any) -> bool:
        raise AssertionError("a refused identity never reaches the claim")


async def _sync_verdict(plant: Callable[[Mart], Callable[..., Any]] | None = None) -> list[str]:
    """One pass with only KEPT configured, after REMOVED has left the configured list: what is wrong
    afterwards, in words. Empty is right. `plant` swaps in a faulty `prune`."""
    pool, mart = await _mart_with_two_identities()
    if plant is not None:
        mart.prune = plant(mart)  # type: ignore[method-assign]
    summary = await sync_once([_board(KEPT)], mart, _NoValkey(), slot=1)  # type: ignore[arg-type]
    wrong = []
    if pool.left_for(REMOVED):
        wrong.append(
            f"a dashboard no longer configured kept rows in {sorted(pool.left_for(REMOVED))}"
        )
    if set(pool.left_for(KEPT)) != set(pool.tables()):
        wrong.append("a dashboard still configured lost its rows")
    if summary.failed != 1:
        wrong.append("the refused pull of the kept dashboard was not counted")
    return wrong


def _prune_never_called(mart: Mart) -> Callable[..., Any]:
    async def prune(configured: Any) -> int:
        return 0

    return prune


def _prune_one_table_only(mart: Mart) -> Callable[..., Any]:
    async def prune(configured: Any) -> int:
        async with mart._pool.acquire() as conn:
            await conn.execute(
                f"DELETE FROM {mart.schema}.pulls WHERE NOT (dashboard = ANY($1::text[]))",
                list(configured),
            )
        return 0

    return prune


def _prune_everything(mart: Mart) -> Callable[..., Any]:
    async def prune(configured: Any) -> int:
        return await Mart.prune(mart, [])  # what is still configured goes too

    return prune


async def test_the_next_sync_prunes_a_dashboard_no_longer_configured() -> None:
    """The one still listed keeps its rows (its pull is refused; `record_failure` leaves them)."""
    assert await _sync_verdict() == []


@pytest.mark.parametrize(
    ("plant", "said"),
    [
        (_prune_never_called, "no longer configured kept rows"),
        (_prune_one_table_only, "no longer configured kept rows"),
        (_prune_everything, "still configured lost its rows"),
    ],
)
async def test_the_sync_s_check_sees_each_planted_fault(
    plant: Callable[[Mart], Callable[..., Any]], said: str
) -> None:
    """Rule 15: the verdict is red for the prune call removed, for one table of two, and for a prune
    that takes what is still configured. `sync_once` calls `prune` with the configured client ids,
    as each plant is called."""
    assert any(said in wrong for wrong in await _sync_verdict(plant))


async def test_a_refusal_never_keeps_a_removed_identitys_rows(world: _World) -> None:
    """The configured list is the environment's, which a removal in the Admin does not change: the
    removed identity may still be listed, its pull refused. `record_failure` keeps the rows it
    finds, so the route must have left it none to keep (and the refusal writes none of its own)."""
    assert world.remove().status_code == 204
    mart = Mart(world.pool, SCHEMA)  # type: ignore[arg-type]
    summary = await sync_once([_board(REMOVED), _board(KEPT)], mart, _NoValkey(), slot=1)  # type: ignore[arg-type]
    assert summary.failed == 2
    assert world.pool.left_for(REMOVED) == {}
    assert set(world.pool.left_for(KEPT)) == set(world.pool.tables())


async def test_a_failed_prune_is_said_in_words_and_the_pass_goes_on() -> None:
    pool, mart = await _mart_with_two_identities()
    pool.fail("NOT (dashboard = ANY", OSError("the mart dropped the connection"))
    summary = await sync_once([_board(KEPT)], mart, _NoValkey(), slot=1)  # type: ignore[arg-type]
    pruning = [f for f in summary.failures if "removed dashboards" in f]
    assert len(pruning) == 1, summary.failures
    assert "could not be pruned" in pruning[0] and "dropped the connection" in pruning[0]
    assert summary.failed == 2, (
        "the failed prune is counted, and the kept dashboard was still tried"
    )
    assert pool.left_for(REMOVED) != {}, "nothing was pruned, and the words say so"
