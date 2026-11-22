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
transaction that fails rolls back, a transaction-scoped lock taken outside a transaction is refused,
a write for a dashboard made without that dashboard's lock is refused, and a fault can be planted on
any statement. The tables are whatever the real `Mart._bootstrap` creates in the reporting schema
(read from its own `CREATE TABLE` text), never a list written here, so a table added to the mart
later without the removal reaching it fails the first test. The record of a removal lives in a
schema of its own, which a BI tool is never granted. It walks no folder; it reads one file by its
path (`apps/workspace/src/admin/api.ts`, to show the screen reads the words the route sends).

What a mistake would do, and the case that catches it:
- the removal route never touches the mart (the fault on main) —
  `test_removing_a_dashboard_leaves_no_row_of_it_in_any_mart_table`;
- the removal reaches `figures` but not `pulls`, or any table added later —
  the same case, and `test_the_check_sees_a_removal_that_misses_a_table` shows it red;
- the removal deletes more than the one identity's rows — the same case (a neighbour's rows kept);
- the mart is down and the removal is reported as done —
  `test_a_removal_the_mart_refuses_is_a_refusal_the_administrator_sees`, and its words reach the
  Admin screen — `test_the_refusal_is_in_the_shape_the_admin_screen_reads`;
- the identity provider refuses to delete the identity (step 2 fails): the rows must stay hidden
  and the Remove button must stay, and nothing may make them readable again before the retry —
  `test_a_provider_that_fails_after_the_stamp_leaves_the_rows_hidden_and_the_button_there`, and the
  pull that begins after the stamp, with a working secret, must not lift it —
  `test_a_pull_after_a_failed_provider_delete_does_not_make_the_rows_readable_again`;
- a pull that began after the stamp and was granted its token before the provider's delete, then a
  failed purge: the stamp must still be there for the sync to act on —
  `test_a_pull_begun_after_the_stamp_cannot_undo_a_removal_whose_purge_failed`;
- a refused token keeps a removed identity's rows —
  `test_a_refusal_never_keeps_a_removed_identitys_rows`;
- a pull already running when the identity is removed writes the rows back (a refused feed makes a
  `pulls` row, a fetched one `figures` and `pulls`), and they stay for good —
  `test_a_pull_running_during_the_removal_does_not_put_the_rows_back`, and
  `test_the_pull_race_check_sees_each_planted_fault` (check removed, removal never stamped, write
  without the lock);
- the record of removal blocks an identity registered again, or is lifted by anything but the
  registration itself (never by the timing of a pull) —
  `test_an_identity_registered_again_after_its_removal_is_written_for`,
  `test_registering_again_takes_the_earlier_identitys_rows_out_before_it_writes`,
  `test_registering_a_name_the_provider_still_holds_does_not_lift_the_stamp`,
  `test_a_registration_whose_mart_cannot_be_reopened_is_refused_and_undone`,
  `test_a_registration_that_cannot_be_undone_leaves_the_rows_hidden_and_says_so`, and
  `test_the_registration_check_sees_each_planted_fault`;
- a BI tool able to read the record of removals —
  `test_the_reader_role_is_never_given_the_record_of_removals`;
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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
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
from services.api.identity_admin import (
    DashboardExistsError,
    IdentityAdmin,
    IdentityAdminRefused,
    NoSuchDashboard,
    PersonActionRefused,
)
from services.api.report_freshness import ReportFreshness
from services.report_sync import mart as mart_module
from services.report_sync.mart import CONTROL_SCHEMA, Mart
from services.report_sync.sync import Dashboard, SyncRefused, TokenSource, sync_once

from ontology.handling import load_uk_le_scheme
from principal_auth import OidcResolverSettings
from schemas.admin import DashboardIdentity, RegisteredDashboard
from schemas.domain import Principal

# The driver's own exception classes, reached through the product's mart module (which imports the
# driver itself), so the fake raises the very classes the real mart and the route catch. This file
# imports no database driver of its own: `tools/test_file_coverage_check.py` reads an `asyncpg`
# import, at module or function level, as "needs a real Postgres", and this file never does.
_PG = mart_module.asyncpg

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
        self.ignored: list[str] = []  # statements planted to do nothing (a plant, never a grant)
        self.depth = 0  # transactions open
        self.locks: set[str] = set()  # dashboards locked in the open transaction
        self.clock = datetime(2026, 11, 21, 10, 0, tzinfo=UTC)  # the database's own clock
        # Row-level security, as a BI tool's role meets it (the owner, which writes, bypasses it).
        self.rls: set[str] = set()  # tables with row security enabled
        self.policies: dict[str, list[tuple[str, str]]] = {}  # table -> (name, function it calls)
        self.functions: dict[str, tuple[str, bool]] = {}  # name -> (body shape, security definer)

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

    def tick(self) -> datetime:
        """The database's clock, moving on every time it is read."""
        self.clock += timedelta(seconds=1)
        return self.clock

    # what a test asks: the *mart* is the reporting schema, the one a BI tool reads. The control
    # schema (where a removal is recorded) is not in it, and `ensure_reader` never grants it.
    def tables(self) -> list[str]:
        return sorted(t for t in self.rows if t.startswith(f"{SCHEMA}."))

    def rows_of(self, dashboard: str) -> dict[str, list[dict[str, Any]]]:
        return {
            t: [r for r in self.rows[t] if r.get("dashboard") == dashboard] for t in self.tables()
        }

    def removed_at(self, dashboard: str) -> datetime | None:
        found = [r for r in self.rows.get(f"{CONTROL_SCHEMA}.removed_dashboards", [])
                 if r["dashboard"] == dashboard]  # fmt: skip
        return found[0]["removed_at"] if found else None

    def left_for(self, dashboard: str) -> dict[str, int]:
        return {t: len(rs) for t, rs in self.rows_of(dashboard).items() if rs}

    def seed_every_table(self, dashboard: str) -> None:
        """A row for `dashboard` in each table that has none: whatever the real schema holds, so a
        table the removal does not know of is a table with a row left in it."""
        for table in self.tables():
            rows = self.rows[table]
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

    def stamp(self, dashboard: str) -> None:
        """A removal stamp written directly (a removal some earlier Conduit committed)."""
        table = f"{CONTROL_SCHEMA}.removed_dashboards"
        self.rows[table] = [r for r in self.rows[table] if r["dashboard"] != dashboard]
        self.rows[table].append({"dashboard": dashboard, "removed_at": self.tick()})

    # What a BI tool's login role reads. Not the owner, so row security applies to it: a table with
    # it enabled shows a row only if some policy on the table allows it, and none allows nothing.
    def reader_sees(self) -> dict[str, list[dict[str, Any]]]:
        seen = {}
        for table in self.tables():
            rows = self.rows[table]
            if table in self.rls:
                policies = self.policies.get(table, [])
                rows = [r for r in rows if any(self._allows(fn, r["dashboard"]) for _, fn in policies)]
            seen[table] = [dict(r) for r in rows]
        return seen

    def reader_left(self, dashboard: str) -> dict[str, int]:
        found = {
            t: len([r for r in rows if r["dashboard"] == dashboard])
            for t, rows in self.reader_sees().items()
        }
        return {t: n for t, n in found.items() if n}

    def _allows(self, function: str, dashboard: str) -> bool:
        body, definer = self.functions[function]
        if body == "true":
            return True
        # The body reads the control schema, which the reader's role is never granted: only a
        # function that runs as its owner may.
        if not definer:
            raise _PG.InsufficientPrivilegeError(
                f"permission denied for schema {CONTROL_SCHEMA}"
            )
        return all(r["dashboard"] != dashboard
                   for r in self.rows[f"{CONTROL_SCHEMA}.removed_dashboards"])  # fmt: skip

    # the statements
    def _table(self, schema: str, name: str) -> str:
        full = f"{schema}.{name}"
        if schema not in self.schemas:
            raise _PG.InvalidSchemaNameError(f'schema "{schema}" does not exist')
        if full not in self.rows:
            raise _PG.UndefinedTableError(f'relation "{full}" does not exist')
        return full

    def run(self, sql: str, args: tuple[Any, ...]) -> str:
        text = " ".join(sql.split())
        for needle, error in self.faults:
            if needle in text:
                raise error
        if any(needle in text for needle in self.ignored):
            return "INSERT 0 0"
        if re.fullmatch(r"SELECT pg_advisory_xact_lock\(hashtext\(\$1\)\)", text):
            # Released at the end of the transaction, so outside one it protects nothing: refused.
            assert self.depth > 0, "a transaction-scoped lock taken outside a transaction"
            self.locks.add(args[0])
            return "SELECT 1"
        if m := re.fullmatch(
            rf"INSERT INTO {CONTROL_SCHEMA}\.removed_dashboards \(dashboard, removed_at\) "
            r"VALUES \(\$1, clock_timestamp\(\)\) ON CONFLICT \(dashboard\) "
            r"DO UPDATE SET removed_at = EXCLUDED.removed_at",
            text,
        ):
            self._require_lock(args[0])
            table = self._table(CONTROL_SCHEMA, "removed_dashboards")
            self.rows[table] = [r for r in self.rows[table] if r["dashboard"] != args[0]]
            self.rows[table].append({"dashboard": args[0], "removed_at": self.tick()})
            return "INSERT 0 1"
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
        if m := re.fullmatch(
            r"CREATE OR REPLACE FUNCTION (\w+)\.(\w+)\(d text\) RETURNS boolean LANGUAGE sql "
            r"STABLE (SECURITY DEFINER )?SET search_path = pg_catalog AS \$\$ (.*) \$\$",
            text,
        ):
            if m[1] not in self.schemas:
                raise _PG.InvalidSchemaNameError(f'schema "{m[1]}" does not exist')
            if m[4] == "SELECT true":
                shape = "true"
            elif re.fullmatch(
                rf"SELECT NOT EXISTS \(SELECT 1 FROM {CONTROL_SCHEMA}\.removed_dashboards r "
                r"WHERE r\.dashboard = d\)",
                m[4],
            ):
                # A language-sql function's body is checked when it is made: its table must exist.
                self._table(CONTROL_SCHEMA, "removed_dashboards")
                shape = "not removed"
            else:
                raise AssertionError(f"the fake mart does not model this function body: {m[4]}")
            self.functions[f"{m[1]}.{m[2]}"] = (shape, bool(m[3]))
            return "CREATE FUNCTION"
        if m := re.fullmatch(r"ALTER TABLE (\w+)\.(\w+) ENABLE ROW LEVEL SECURITY", text):
            self.rls.add(self._table(m[1], m[2]))
            return "ALTER TABLE"
        if m := re.fullmatch(r"DROP POLICY IF EXISTS (\w+) ON (\w+)\.(\w+)", text):
            table = self._table(m[2], m[3])
            self.policies[table] = [p for p in self.policies.get(table, []) if p[0] != m[1]]
            return "DROP POLICY"
        if m := re.fullmatch(
            r"CREATE POLICY (\w+) ON (\w+)\.(\w+) FOR SELECT USING \((\w+\.\w+)\(dashboard\)\)", text
        ):
            table = self._table(m[2], m[3])
            if m[4] not in self.functions:
                raise _PG.UndefinedFunctionError(f"function {m[4]}(text) does not exist")
            if any(name == m[1] for name, _ in self.policies.get(table, [])):
                raise _PG.DuplicateObjectError(f'policy "{m[1]}" already exists')
            self.policies.setdefault(table, []).append((m[1], m[4]))
            return "CREATE POLICY"
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
            self._require_lock(args[0])
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
            self._require_lock(args[0])
            doomed = [r for r in self.rows[table] if r["dashboard"] == args[0]]
            self.rows[table] = [r for r in self.rows[table] if r["dashboard"] != args[0]]
            self.deletes.append(f"{table} of {args[0]}")
            return f"DELETE {len(doomed)}"
        raise AssertionError(f"the fake mart does not model this statement: {text}")

    def _require_lock(self, dashboard: str) -> None:
        """What the real mart's writers do and a bare fake would not notice: a write for a dashboard
        is made under that dashboard's lock, so it cannot slip between a removal's check and its
        commit."""
        assert dashboard in self.locks, (
            f"{dashboard} written or removed without its lock, so a removal could commit between "
            "the check and the write"
        )

    def _upsert_figure(self, table: str, args: tuple[Any, ...]) -> str:
        self._require_lock(args[0])
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
        self._require_lock(args[0])
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
        if text == f"SELECT dashboard FROM {CONTROL_SCHEMA}.removed_dashboards ORDER BY dashboard":
            table = self._table(CONTROL_SCHEMA, "removed_dashboards")
            return [{"dashboard": r["dashboard"]} for r in self.rows[table]]
        m = re.match(r"SELECT \* FROM (\w+)\.(\w+) WHERE dashboard = \$1 ORDER BY", text)
        if not m:
            raise AssertionError(f"the fake mart does not model this query: {text}")
        return [dict(r) for r in self.rows[self._table(m[1], m[2])] if r["dashboard"] == args[0]]

    def value(self, sql: str, args: tuple[Any, ...]) -> Any:
        text = " ".join(sql.split())
        if text == "SELECT clock_timestamp()":
            return self.tick()
        if text == "SELECT to_regclass($1)":
            return args[0] if args[0] in self.rows else None  # NULL for a table not made
        if m := re.fullmatch(r"SELECT EXISTS \(SELECT 1 FROM (\w+)\.(\w+) WHERE dashboard = \$1\)", text):
            return any(r["dashboard"] == args[0] for r in self.rows[self._table(m[1], m[2])])
        if text == (
            f"SELECT removed_at FROM {CONTROL_SCHEMA}.removed_dashboards WHERE dashboard = $1"
        ):
            self._require_lock(args[0])
            self._table(CONTROL_SCHEMA, "removed_dashboards")
            return self.removed_at(args[0])
        raise AssertionError(f"the fake mart does not model this value query: {text}")


class _Conn:
    def __init__(self, pool: FakeMartPool) -> None:
        self._pool = pool

    async def execute(self, sql: str, *args: Any) -> str:
        return self._pool.run(sql, args)

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        return self._pool.select(sql, args)

    async def fetchval(self, sql: str, *args: Any) -> Any:
        return self._pool.value(sql, args)

    def transaction(self) -> Any:
        pool = self._pool

        @asynccontextmanager
        async def txn() -> Any:
            before = copy.deepcopy(pool.rows)
            pool.depth += 1
            try:
                yield
            except BaseException:
                pool.rows = before  # a failed transaction leaves nothing half done
                raise
            finally:
                pool.depth -= 1
                if pool.depth == 0:
                    pool.locks.clear()  # a transaction-scoped lock goes with its transaction

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


#: What each identity provider answers for a dashboard it does not hold, and what the route answers
#: for one that is neither held nor left any row. Keycloak (the default) raises `NoSuchDashboard`, an
#: `IdentityAdminRefused` with no `error` attribute; Entra raises `PersonActionRefused` carrying
#: `no_such_dashboard`. Every route case that depends on the difference runs for both.
PROVIDERS = ["entra", "keycloak"]
UNKNOWN_STATUS = {"entra": 409, "keycloak": 502}


class _Identity:
    """The identity provider's side of the Admin: two registered dashboards. It refuses what
    the real one refuses: removing one that is not registered, in the provider's own words and
    type (`provider`)."""

    def __init__(self, provider: str = "entra") -> None:
        self.provider = provider
        self.registered = [
            DashboardIdentity(client_id=REMOVED, account_id="sa-leaver"),
            DashboardIdentity(client_id=KEPT, account_id="sa-stayer"),
        ]
        self.deleted: list[str] = []
        self.created: list[str] = []
        self.refuses: Exception | None = None  # the identity provider's own refusal, when planted
        self.at_delete: Callable[[str], None] = lambda client_id: None  # what the world is as it acts

    def not_held(self, client_id: str) -> Exception:
        if self.provider == "keycloak":
            return NoSuchDashboard("no such dashboard")
        return PersonActionRefused("no_such_dashboard", f"{client_id} is not registered.")

    async def list_dashboards(self) -> list[DashboardIdentity]:
        return list(self.registered)

    async def create_dashboard(
        self, name: str, *, clearance: str, org_unit: str, application_id: str | None = None
    ) -> RegisteredDashboard:
        """Registration as both providers do it: a client id already held is refused
        (`DashboardExistsError`, the 409), never made twice."""
        client_id = f"osprey-dashboard-{name}"
        if client_id in {d.client_id for d in self.registered}:
            raise DashboardExistsError(client_id)
        made = DashboardIdentity(client_id=client_id, account_id=f"sa-{name}-again")
        self.registered.append(made)
        self.created.append(client_id)
        return RegisteredDashboard(dashboard=made, secret=secrets.token_urlsafe(8))

    async def delete_dashboard(self, client_id: str) -> None:
        self.at_delete(client_id)
        if self.refuses is not None:
            raise self.refuses
        if client_id not in {d.client_id for d in self.registered}:
            raise self.not_held(client_id)
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


class _Freshness(ReportFreshness):
    """The real removal code; only the Admin list's freshness figures (a query this fake does not
    model, and not what any case here is about) are left out."""

    async def by_dashboard(self) -> dict[str, Any]:
        return {}


class _World:
    def __init__(self, pool: FakeMartPool, provider: str = "entra") -> None:
        self.pool, self.identity, self.audit = pool, _Identity(provider), _Audit()
        self.client = TestClient(app, raise_server_exceptions=False)

    def remove(self, client_id: str = REMOVED) -> Any:
        return self.client.delete(f"/v1/admin/dashboards/{client_id}")

    def register(self, name: str = "leaver") -> Any:
        """The same name again: `osprey-dashboard-leaver` is `REMOVED`'s client id."""
        return self.client.post(
            "/v1/admin/dashboards",
            json={"name": name, "clearance": "OFFICIAL", "org_unit": "verify"},
        )

    def registration_rows(self) -> list[dict[str, Any]]:
        return [r for r in self.audit.records if r["action"] == "register_dashboard"]

    def listed(self) -> list[str]:
        """What the Admin's Dashboards list offers a Remove button for: the provider's own list."""
        response = self.client.get("/v1/admin/dashboards")
        assert response.status_code == 200, response.text
        return [d["client_id"] for d in response.json()]

    def removal_rows(self) -> list[dict[str, Any]]:
        return [r for r in self.audit.records if r["action"] == "remove_dashboard"]


@pytest.fixture
def provider() -> str:
    return "entra"


@pytest.fixture
async def world(provider: str) -> Iterator[_World]:
    pool, _ = await _mart_with_two_identities()
    state = _World(pool, provider)
    reader = _Freshness(pool, SCHEMA)  # type: ignore[arg-type]
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
        _PG.InsufficientPrivilegeError("permission denied for table pulls"),
    ],
    ids=["unreachable", "the Conduit's role may not delete"],
)
def test_a_removal_the_mart_refuses_is_a_refusal_the_administrator_sees(
    world: _World, error: Exception
) -> None:
    """Step 1 fails: the stamp that hides the rows cannot be committed, so the identity provider is
    never called (a removal that could not hide the rows must not take the only Remove button
    away). Nothing completed, so nothing is audited; the identity stays registered and listed."""
    world.pool.fail(f"INSERT INTO {CONTROL_SCHEMA}.removed_dashboards", error)
    before = world.pool.left_for(REMOVED)
    refused = world.remove()
    assert refused.status_code == 503, refused.text
    body = refused.json()["detail"]
    assert body["error"] == "reporting_mart_unreachable"
    assert "reporting mart" in body["message"] and "removing it again" in body["message"]
    assert world.identity.deleted == [], "not removed: it stays registered, so a retry finds it"
    assert REMOVED in world.listed()
    assert world.removal_rows() == []
    assert world.pool.left_for(REMOVED) == before
    world.pool.heal()
    assert world.remove().status_code == 204
    assert world.pool.left_for(REMOVED) == {}


def test_a_purge_that_fails_part_way_leaves_nothing_half_removed(world: _World) -> None:
    """One transaction for the purge: a refusal on the last table does not leave the others emptied
    alone (and the stamp, committed before it, still hides every row)."""
    from services.report_sync.mart import DASHBOARD_TABLES

    last = DASHBOARD_TABLES[-1]
    world.pool.fail(f"DELETE FROM {SCHEMA}.{last}", _PG.PostgresConnectionError("lost"))
    before = world.pool.left_for(REMOVED)
    assert world.remove().status_code == 204
    assert world.pool.left_for(REMOVED) == before
    assert world.pool.reader_left(REMOVED) == {}


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


@pytest.mark.parametrize("provider", PROVIDERS)
def test_one_not_registered_is_refused_and_touches_no_mart_row(world: _World, provider: str) -> None:
    before = world.pool.left_for(KEPT)
    refused = world.remove("osprey-dashboard-gone")
    assert refused.status_code == UNKNOWN_STATUS[provider], refused.text
    assert world.pool.left_for(KEPT) == before and world.pool.left_for(REMOVED) != {}
    assert world.pool.removed_at("osprey-dashboard-gone") is None, "a mistyped id is not stamped"
    assert world.removal_rows() == []


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


# --- The sync pass finishes a purge the Conduit could not ------------------------------------------


async def _stamped_world() -> tuple[FakeMartPool, Mart]:
    """Both identities hold rows; REMOVED's removal was stamped and its purge never happened."""
    pool, mart = await _mart_with_two_identities()
    pool.stamp(REMOVED)
    return pool, mart


async def _stamped_sync_verdict(
    configured: list[str], plant: Callable[[Mart], Callable[..., Any]] | None = None
) -> list[str]:
    """One pass over `configured` with REMOVED stamped and not purged: what is wrong afterwards."""
    pool, mart = await _stamped_world()
    if plant is not None:
        mart.purge_removed = plant(mart)  # type: ignore[method-assign]
    await sync_once([_board(c) for c in configured], mart, _NoValkey(), slot=1)  # type: ignore[arg-type]
    wrong = []
    if pool.left_for(REMOVED):
        wrong.append(f"a stamped identity kept rows in {sorted(pool.left_for(REMOVED))}")
    if set(pool.left_for(KEPT)) != set(pool.tables()):
        wrong.append("an identity that was not removed lost its rows")
    if pool.removed_at(REMOVED) is None:
        wrong.append("the stamp was dropped by the purge, so a refused pull may write again")
    return wrong


def _purge_never_called(mart: Mart) -> Callable[..., Any]:
    async def purge_removed() -> int:
        return 0

    return purge_removed


def _purge_one_table_only(mart: Mart) -> Callable[..., Any]:
    async def purge_removed() -> int:
        async with mart._pool.acquire() as conn, conn.transaction():
            await mart_module.lock_dashboard(conn, REMOVED)
            await conn.execute(f"DELETE FROM {mart.schema}.pulls WHERE dashboard = $1", REMOVED)
        return 0

    return purge_removed


def _purge_every_dashboard(mart: Mart) -> Callable[..., Any]:
    async def purge_removed() -> int:
        async with mart._pool.acquire() as conn, conn.transaction():
            for client in (REMOVED, KEPT):
                await mart_module.lock_dashboard(conn, client)
                for table in mart_module.DASHBOARD_TABLES:
                    await conn.execute(f"DELETE FROM {mart.schema}.{table} WHERE dashboard = $1", client)
        return 0

    return purge_removed


@pytest.mark.parametrize(
    "configured", [[KEPT], [REMOVED, KEPT]], ids=["not configured", "still configured"]
)
async def test_a_stamped_identity_loses_its_rows_at_the_next_sync(configured: list[str]) -> None:
    """The identity is absent from the provider and stamped; the sync pass takes its rows out of every
    table whether or not the environment's list still names it (its pull is refused), and leaves the
    stamp, so a refusal cannot write it again. Another identity's rows are left alone."""
    assert await _stamped_sync_verdict(configured) == []


@pytest.mark.parametrize(
    ("plant", "said"),
    [
        (_purge_never_called, "stamped identity kept rows"),
        (_purge_one_table_only, "stamped identity kept rows"),
        (_purge_every_dashboard, "was not removed lost its rows"),
    ],
)
async def test_the_stamped_sync_check_sees_each_planted_fault(
    plant: Callable[[Mart], Callable[..., Any]], said: str
) -> None:
    """Rule 15: red for the purge call removed, a purge that takes one table of two, and a purge that
    takes an identity nobody removed. `sync_once` calls `purge_removed()` as each plant is called."""
    # REMOVED is still in the environment's list: `prune` takes nothing of it, so only the purge of
    # stamped identities can.
    assert any(said in w for w in await _stamped_sync_verdict([REMOVED, KEPT], plant))


async def test_a_failed_purge_in_the_sync_is_said_in_words_and_the_pass_goes_on() -> None:
    pool, mart = await _stamped_world()
    pool.fail("WHERE dashboard = $1", OSError("the mart dropped the connection"))
    boards = [_board(REMOVED), _board(KEPT)]  # still listed: `prune` takes nothing of it
    summary = await sync_once(boards, mart, _NoValkey(), slot=1)  # type: ignore[arg-type]
    purging = [f for f in summary.failures if "could not be purged" in f]
    assert len(purging) == 1 and "dropped the connection" in purging[0], summary.failures
    assert summary.failed == 3, "the failed purge is counted, and each dashboard was still tried"
    assert any("removed in the Admin" in f for f in summary.failures), "a refusal wrote nothing for it"
    assert pool.left_for(REMOVED) != {} and pool.reader_left(REMOVED) == {}, "still hidden"
    pool.heal()
    await sync_once(boards, mart, _NoValkey(), slot=2)  # type: ignore[arg-type]
    assert pool.left_for(REMOVED) == {}, "the next pass tries again"


async def test_a_refusal_never_writes_a_stamped_identitys_row() -> None:
    """`record_failure` keeps what it finds and writes what it is given; for a stamped identity it
    does neither, whenever its pull began: nothing about the pull's timing can make a stamped
    identity writable (a pull that began after the stamp and before the identity provider deleted
    the identity is still the removed identity's)."""
    pool, mart = await _mart_with_two_identities()
    pool.stamp(REMOVED)
    with pytest.raises(mart_module.DashboardRemoved):
        await mart.record_failure(REMOVED, "case-3", "refused", NOW)
    assert not [r for r in pool.rows_of(REMOVED)[f"{SCHEMA}.pulls"] if r["case_id"] == "case-3"]
    # an identity that was not removed is written as before
    await mart.record_failure(KEPT, "case-3", "refused", NOW)
    assert [r for r in pool.rows_of(KEPT)[f"{SCHEMA}.pulls"] if r["case_id"] == "case-3"]


async def test_a_write_with_no_pass_start_is_refused_for_a_stamped_identity() -> None:
    pool, mart = await _stamped_world()
    with pytest.raises(mart_module.DashboardRemoved):
        await mart.replace(REMOVED, "case-9", "Operation Nine", 12, FEED, NOW)


async def test_a_refused_pull_after_a_failed_purge_does_not_rewrite_the_rows(world: _World) -> None:
    """The consequence the earlier rounds' finding named: the purge failed, the identity is still in
    the environment's list, its token is refused. Nothing is rewritten, and the next pass purges."""
    world.pool.fail(f"DELETE FROM {SCHEMA}", OSError("the mart dropped the connection"))
    assert world.remove().status_code == 204
    world.pool.heal()
    mart = Mart(world.pool, SCHEMA)  # type: ignore[arg-type]
    summary = await sync_once([_board(REMOVED), _board(KEPT)], mart, _NoValkey(), slot=1)  # type: ignore[arg-type]
    assert summary.failed == 2
    assert world.pool.left_for(REMOVED) == {}
    assert set(world.pool.left_for(KEPT)) == set(world.pool.tables())


# --- What a reader can see: rule 4, the read path ---------------------------------------------------
#
# Superset's Admin and Alpha read the whole mart through one login role that is not the table's owner
# (ADR-148 Amendment 21), so row security on the tables is what they meet. A stamped identity's rows
# are not returned to them, at any step, and a present identity's rows still are.


def _reader_verdict(pool: FakeMartPool, *, hidden: tuple[str, ...], shown: tuple[str, ...]) -> list[str]:
    wrong = []
    tables = set(pool.tables())
    for client in hidden:
        if pool.reader_left(client):
            wrong.append(f"the reader still reads {client}'s rows in {sorted(pool.reader_left(client))}")
    for client in shown:
        if set(pool.reader_left(client)) != tables:
            wrong.append(f"the reader no longer reads all of {client}'s rows")
    return wrong


def test_every_mart_table_is_hidden_from_a_reader_behind_row_security(world: _World) -> None:
    """Rule 12: a table added to the mart that nobody told to hide a removed identity's rows would
    leave them readable. Every table the real bootstrap makes in the reporting schema has row
    security enabled and a policy calling the function that reads the stamp."""
    assert world.pool.tables()
    for table in world.pool.tables():
        assert table in world.pool.rls, f"{table} has no row security"
        assert world.pool.policies.get(table), f"{table} has no policy for a reader"
    assert f"{SCHEMA}.dashboard_is_current" in world.pool.functions
    assert world.pool.functions[f"{SCHEMA}.dashboard_is_current"] == ("not removed", True)


async def test_a_stamped_identitys_rows_are_not_returned_to_a_reader_at_any_step(
    world: _World,
) -> None:
    """Admin and Alpha, through the one reader role, at every point of a removal: before it (they read
    the rows), with the stamp committed and the provider refusing, with the provider done and the
    purge failing, and after the sync purged. Never the removed identity's; always the other's."""
    steps: list[tuple[str, list[str]]] = []
    both = (REMOVED, KEPT)
    steps.append(("before", _reader_verdict(world.pool, hidden=(), shown=both)))
    world.identity.refuses = PersonActionRefused("identity_provider_refused", "refused")
    world.remove()
    steps.append(("provider failed", _reader_verdict(world.pool, hidden=(REMOVED,), shown=(KEPT,))))
    world.identity.refuses = None
    world.pool.fail(f"DELETE FROM {SCHEMA}", OSError("the mart dropped the connection"))
    world.remove()
    steps.append(("purge failed", _reader_verdict(world.pool, hidden=(REMOVED,), shown=(KEPT,))))
    world.pool.heal()
    mart = Mart(world.pool, SCHEMA)  # type: ignore[arg-type]
    await sync_once([_board(KEPT)], mart, _NoValkey(), slot=1)  # type: ignore[arg-type]
    steps.append(("purged", _reader_verdict(world.pool, hidden=(REMOVED,), shown=(KEPT,))))
    assert all(not wrong for _, wrong in steps), steps


@pytest.mark.parametrize(
    ("plant", "said"),
    [
        ("no row security", "still reads"),
        ("a function that says yes", "still reads"),
        ("one table left out", "still reads"),
        ("a function that cannot read the stamp", "permission denied"),
    ],
)
async def test_the_reader_check_sees_each_planted_fault(
    monkeypatch: pytest.MonkeyPatch, plant: str, said: str
) -> None:
    """Rule 15: the verdict above is red for a bootstrap that never enables row security, a function
    that always allows, a table with no row security, and a function that runs as the reader (who is
    never granted the stamp's schema). Each is made by changing the real bootstrap's statements."""
    real = mart_module.hiding_statements

    def planted(schema: str) -> list[str]:
        statements = real(schema)
        if plant == "no row security":
            return [s for s in statements if "ROW LEVEL SECURITY" not in s and "POLICY" not in s]
        if plant == "a function that says yes":
            return [re.sub(r"\$\$ SELECT NOT EXISTS.*? \$\$", "$$ SELECT true $$", " ".join(s.split()))
                    for s in statements]  # fmt: skip
        if plant == "one table left out":
            return [s for s in statements if ".figures" not in s]
        return [s.replace("SECURITY DEFINER ", "") for s in statements]

    monkeypatch.setattr(mart_module, "hiding_statements", planted)
    pool, mart = await _mart_with_two_identities()
    pool.stamp(REMOVED)
    try:
        wrong = _reader_verdict(pool, hidden=(REMOVED,), shown=(KEPT,))
    except _PG.InsufficientPrivilegeError as refused:
        wrong = [str(refused)]
    assert any(said in w for w in wrong), wrong


# --- What the administrator sees ------------------------------------------------------------------

ADMIN_API = Path(__file__).parents[4] / "OspreyFlow_Core/apps/workspace/src/admin/api.ts"


def test_the_refusal_is_in_the_shape_the_admin_screen_reads(world: _World) -> None:
    """`apps/workspace/src/admin/api.ts` `failure()` shows an object `detail`'s `message` when it is a
    string (ADR-145 Amendment 5) and otherwise only "could not complete that (503)". The route's
    words are in `message`, so the screen shows them; under any other key they were never seen."""
    source = ADMIN_API.read_text(encoding="utf-8")
    assert 'typeof (detail as { message?: unknown }).message === "string"' in source, (
        "the Admin screen no longer reads an object detail's message: this test's premise is gone"
    )
    world.pool.fail(f"INSERT INTO {CONTROL_SCHEMA}", OSError("the mart is unreachable"))
    detail = world.remove().json()["detail"]
    assert isinstance(detail, dict) and isinstance(detail.get("message"), str), detail
    assert detail["message"].strip(), "the words are not empty"
    assert set(detail) == {"error", "message"}, "no second copy of the words under another key"


# --- The removal's order: stamp, then the identity provider, then the purge, audited once ---------
#
# Round 5's one design. The stamp (a row in the control schema, committed in a transaction of its own
# before the provider is called, never rolled back with the purge) is what makes a removed
# identity's rows unreadable; the purge is repeatable and the next sync pass finishes it. For every
# step that can fail, what a reader (Superset's role) can see afterwards is nothing of the removed
# identity's, and what the administrator sees is in words.

#: The identity provider's failures that are not "I hold no such identity": a refusal, and a
#: provider that cannot be reached; and the status the route has always answered each with.
PROVIDER_FAILURES = [
    pytest.param(
        lambda: PersonActionRefused("identity_provider_refused", "the provider refused"),
        409,
        id="refused",
    ),
    pytest.param(
        lambda: IdentityAdminRefused("the identity provider could not be reached"),
        502,
        id="unreachable",
    ),
]


def _steps_done(row: dict[str, Any]) -> list[str]:
    return list(row["resolved_query"]["completed"])


def test_the_removal_runs_stamp_then_provider_then_purge(world: _World) -> None:
    """The order itself: when the identity provider is asked, the removal is already stamped and the
    rows are already hidden from a reader, and none of them has been purged yet."""
    seen: dict[str, Any] = {}

    def at_delete(client_id: str) -> None:
        seen["stamped"] = world.pool.removed_at(client_id) is not None
        seen["reader sees"] = world.pool.reader_left(client_id)
        seen["still held"] = world.pool.left_for(client_id)

    world.identity.at_delete = at_delete
    held = world.pool.left_for(REMOVED)
    assert world.remove().status_code == 204
    assert seen == {"stamped": True, "reader sees": {}, "still held": held}
    assert world.pool.left_for(REMOVED) == {}


@pytest.mark.parametrize("fail, status", PROVIDER_FAILURES)
def test_a_provider_that_fails_after_the_stamp_leaves_the_rows_hidden_and_the_button_there(
    world: _World, fail: Callable[[], Exception], status: int
) -> None:
    """Step 2 fails. The stamp is committed and stays: the rows are hidden at once, the identity is
    still registered and so still listed (its Remove button is there), the refusal is in words, the
    removal is audited once with what completed, and removing it again finishes it."""
    world.identity.refuses = fail()
    held = world.pool.left_for(REMOVED)
    refused = world.remove()
    assert refused.status_code == status, refused.text
    detail = refused.json()["detail"]
    words = detail["message"] if isinstance(detail, dict) else detail
    assert "hidden" in words and "remove it again" in words.lower(), refused.text
    assert world.pool.removed_at(REMOVED) is not None, "the stamp was rolled back with the failure"
    assert world.pool.reader_left(REMOVED) == {}, "a reader can read the rows of an identity being removed"
    assert world.pool.left_for(REMOVED) == held, "the purge waits for the provider"
    assert REMOVED in world.listed(), "no Remove button would be left to retry with"
    (row,) = world.removal_rows()
    assert row["resolved_query"]["client_id"] == REMOVED
    assert row["resolved_query"]["mart_confirmed"] is False
    assert _steps_done(row) == ["case_grants_revoked", "rows_hidden"]
    assert world.pool.reader_left(KEPT), "a present identity's rows are still read"
    world.identity.refuses = None
    assert world.remove().status_code == 204, "a retry on a still-listed identity finishes it"
    assert world.pool.left_for(REMOVED) == {} and world.pool.reader_left(REMOVED) == {}
    assert REMOVED not in world.listed()
    assert len(world.removal_rows()) == 2
    assert world.removal_rows()[1]["resolved_query"] == {"client_id": REMOVED, "grants_revoked": 0}


@pytest.mark.parametrize("provider", PROVIDERS)
async def test_a_purge_that_fails_after_the_provider_is_a_warning_and_the_next_sync_finishes_it(
    world: _World, provider: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Step 3 fails. The identity is gone at the provider, so there is no button and none is
    needed: the rows are hidden (the stamp was committed first and is not undone), the failure is a
    logged and audited warning, never a 503 that tells a person to retry a button that is gone, and
    the next sync pass purges them."""
    world.pool.fail(f"DELETE FROM {SCHEMA}", OSError("the mart dropped the connection"))
    held = world.pool.left_for(REMOVED)
    with caplog.at_level("WARNING"):
        answer = world.remove()
    assert answer.status_code == 204, answer.text
    assert world.identity.deleted == [REMOVED]
    assert REMOVED not in world.listed()
    assert world.pool.removed_at(REMOVED) is not None, "the purge's rollback took the stamp with it"
    assert world.pool.reader_left(REMOVED) == {}
    assert world.pool.left_for(REMOVED) == held
    assert any(REMOVED in r.getMessage() and r.levelname == "WARNING" for r in caplog.records)
    (row,) = world.removal_rows()
    assert row["resolved_query"]["mart_confirmed"] is False
    assert _steps_done(row) == ["case_grants_revoked", "rows_hidden", "identity_removed"]
    world.pool.heal()
    mart = Mart(world.pool, SCHEMA)  # type: ignore[arg-type]
    await sync_once([_board(KEPT)], mart, _NoValkey(), slot=1)  # type: ignore[arg-type]
    assert world.pool.left_for(REMOVED) == {}, "the sync pass did not finish the purge"
    assert world.pool.reader_left(REMOVED) == {}
    assert len(world.removal_rows()) == 1, "audited once"


@pytest.mark.parametrize("provider", PROVIDERS)
def test_removing_it_again_after_a_failed_purge_also_finishes_it(world: _World, provider: str) -> None:
    """Not needed (the sync finishes it), but possible: an identity the provider no longer holds,
    with rows still in the mart, is answered done (204) in the provider's own way of saying "not
    registered", Keycloak's `NoSuchDashboard` and Entra's `PersonActionRefused`; and one the mart
    holds nothing of is still the provider's refusal."""
    world.pool.fail(f"DELETE FROM {SCHEMA}", OSError("the mart dropped the connection"))
    assert world.remove().status_code == 204
    world.pool.heal()
    kept_before = world.pool.left_for(KEPT)
    assert world.remove().status_code == 204
    assert world.pool.left_for(REMOVED) == {}
    assert world.pool.left_for(KEPT) == kept_before
    assert world.remove().status_code == UNKNOWN_STATUS[provider], "nothing left: not registered"
    assert world.pool.left_for(KEPT) == kept_before


@pytest.mark.parametrize("provider", PROVIDERS)
def test_an_identity_the_provider_does_not_hold_loses_leftover_rows_and_one_with_none_is_refused(
    world: _World, provider: str
) -> None:
    """Not registered and rows left in the mart (a removal that never finished): done, 204. Not
    registered and none left (a mistyped id): still the provider's refusal, as before, and no other
    identity's row is touched either way. Run for the error each provider raises: Keycloak's
    `NoSuchDashboard` has no `error` attribute, which the route must still read as "not held"."""
    world.identity.registered = [d for d in world.identity.registered if d.client_id != REMOVED]
    kept_before = world.pool.left_for(KEPT)
    assert world.remove().status_code == 204
    assert world.pool.left_for(REMOVED) == {}
    assert world.pool.reader_left(REMOVED) == {}
    assert world.pool.left_for(KEPT) == kept_before
    assert world.remove("osprey-dashboard-mistyped").status_code == UNKNOWN_STATUS[provider]
    assert world.pool.left_for(KEPT) == kept_before
    (row,) = world.removal_rows()
    assert row["resolved_query"]["client_id"] == REMOVED


def test_the_identity_provider_s_refusal_of_one_it_does_not_hold_is_told_apart_from_other_refusals(
    world: _World,
) -> None:
    """Only "not registered" finishes the removal: any other refusal (here a provider that cannot be
    reached) leaves the rows hidden and in place, and says so, so the removal that did not complete
    does not read as done."""
    world.identity.registered = [d for d in world.identity.registered if d.client_id != REMOVED]
    world.identity.refuses = IdentityAdminRefused("the identity provider could not be reached")
    held = world.pool.left_for(REMOVED)
    assert world.remove().status_code == 502
    assert world.pool.left_for(REMOVED) == held
    assert world.pool.reader_left(REMOVED) == {}
    assert world.pool.removed_at(REMOVED) is not None


async def test_the_keycloak_admin_says_not_registered_in_a_way_the_route_can_tell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real `IdentityAdmin.delete_dashboard` for an identity the realm does not hold raises
    `NoSuchDashboard` (still an `IdentityAdminRefused`, so it is answered as before)."""

    from services.api.identity_admin import NoSuchDashboard

    async def unknown(self: IdentityAdmin, client_id: str) -> None:
        return None

    monkeypatch.setattr(IdentityAdmin, "_uuid", unknown)
    admin = object.__new__(IdentityAdmin)
    with pytest.raises(NoSuchDashboard) as raised:
        await admin.delete_dashboard("osprey-dashboard-gone")
    assert isinstance(raised.value, IdentityAdminRefused)


# --- The real Keycloak adapter's step 2 (the identity provider deletes it) ------------------------
#
# Every route case above models a provider failure as a raised exception. The real Keycloak adapter
# raised none for a refused DELETE: `_call` raises only on a transport error or a 401/403, and
# `delete_dashboard` never read the status, so a 5xx, a 409 or a 404 from the realm came back as
# "removed": the route then audited a completed removal and answered 204 for an identity still
# registered, with its working secret, still listed. The stand-in below is the realm's HTTP, and the
# adapter and the route are the real ones, so what the route sees is what the adapter really emits.


class _Keycloak:
    """The realm's admin API for dashboard clients, with its refusals: no bearer or another is
    401, an unknown client is 404, and the answers a planted fault gives (`delete_status` for the
    DELETE of a client it holds, `lookup_status` for the exact lookup by client id)."""

    BEARER = "a-token-made-for-this-test"

    def __init__(self) -> None:
        self.held = {REMOVED: "uuid-leaver", KEPT: "uuid-stayer"}
        self.delete_status = 204
        self.lookup_status = 200
        self.deleted: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path.endswith("/token"):
            return httpx.Response(200, json={"access_token": self.BEARER})
        if request.headers.get("Authorization") != f"Bearer {self.BEARER}":
            return httpx.Response(401, json={"error": "HTTP 401 Unauthorized"})
        base = "/admin/realms/osprey/clients"
        assert path.startswith(base), path
        rest = path[len(base) :].strip("/")
        if request.method == "GET" and rest == "":
            wanted = request.url.params["clientId"]
            if request.url.params.get("search") == "true":
                found = [{"id": u, "clientId": c} for c, u in self.held.items() if wanted in c]
                return httpx.Response(200, json=found)
            if self.lookup_status != 200:
                return httpx.Response(self.lookup_status, text="<html>upstream error</html>")
            return httpx.Response(
                200, json=[{"id": u, "clientId": c} for c, u in self.held.items() if c == wanted]
            )
        uuid = rest.split("/")[0]
        if uuid not in self.held.values():
            return httpx.Response(404, json={"error": "Could not find client"})
        if request.method == "GET" and rest.endswith("/service-account-user"):
            return httpx.Response(200, json={"id": f"sa-{uuid}", "attributes": {}})
        assert request.method == "DELETE" and rest == uuid, (request.method, path)
        if self.delete_status != 204:
            return httpx.Response(self.delete_status, json={"error": "the realm refused"})
        gone = next(c for c, u in self.held.items() if u == uuid)
        del self.held[gone]
        self.deleted.append(gone)
        return httpx.Response(204)


def _keycloak_admin(realm: _Keycloak) -> IdentityAdmin:
    """The real adapter, its HTTP client the stand-in realm (nothing is sent anywhere)."""
    base = "http://keycloak.invalid"
    admin = IdentityAdmin(
        OidcResolverSettings(
            oidc_jwks_url=f"{base}/certs", oidc_issuer=base, oidc_audience="osprey-conduit",
            oidc_token_exchange_url=f"{base}/token", oidc_token_exchange_client_id="osprey-conduit",
            oidc_token_exchange_client_secret=secrets.token_urlsafe(8),
            oidc_admin_users_url=f"{base}/admin/realms/osprey/users",
        )  # fmt: skip
    )
    admin._http = httpx.AsyncClient(transport=httpx.MockTransport(realm.handler))  # noqa: SLF001
    return admin


@pytest.fixture
def keycloak(world: _World) -> _Keycloak:
    """The route's identity provider is the real Keycloak adapter over the stand-in realm."""
    realm = _Keycloak()
    app.dependency_overrides[get_identity_admin] = lambda: _keycloak_admin(realm)
    return realm


@pytest.mark.parametrize("status", [500, 502, 409, 400])
async def test_the_keycloak_adapter_refuses_a_delete_the_realm_did_not_make(status: int) -> None:
    """A DELETE the realm answers with anything but 204 is not a removal: the adapter raises an
    `IdentityAdminRefused` naming the status, and the client is still held."""
    realm = _Keycloak()
    realm.delete_status = status
    admin = _keycloak_admin(realm)
    with pytest.raises(IdentityAdminRefused) as raised:
        await admin.delete_dashboard(REMOVED)
    assert str(status) in str(raised.value), "the status is not in the words"
    assert REMOVED in realm.held, "the realm still holds it"


async def test_the_keycloak_adapter_says_not_registered_when_the_realm_answers_not_found() -> None:
    """A client that went between the lookup and the DELETE: 404 is `NoSuchDashboard`, as a lookup
    that finds nothing is, so the route reads one answer for "the provider holds no such one"."""
    realm = _Keycloak()
    realm.delete_status = 404
    with pytest.raises(NoSuchDashboard):
        await _keycloak_admin(realm).delete_dashboard(REMOVED)


async def test_the_keycloak_adapter_removes_when_the_realm_says_done() -> None:
    realm = _Keycloak()
    await _keycloak_admin(realm).delete_dashboard(REMOVED)
    assert REMOVED not in realm.held and realm.deleted == [REMOVED]


@pytest.mark.parametrize("status", [500, 502, 503])
async def test_the_keycloak_adapter_refuses_in_words_when_the_lookup_fails(status: int) -> None:
    """A realm answering the lookup of a client with an error page: said in words as an
    `IdentityAdminRefused`, not an `AttributeError` or a `JSONDecodeError` the route can only answer
    with a bare 500."""
    realm = _Keycloak()
    realm.lookup_status = status
    with pytest.raises(IdentityAdminRefused) as raised:
        await _keycloak_admin(realm).delete_dashboard(REMOVED)
    assert str(status) in str(raised.value)
    assert REMOVED in realm.held


def _keycloak_refusal_verdict(world: _World, realm: _Keycloak, held: dict[str, int]) -> list[str]:
    """What the removal must be when the realm refused step 2, as one list of what is wrong: a
    refusal in words, the identity still listed with its Remove button, its rows hidden and not
    purged, a neighbour's rows still read, the audit row naming what completed (once), and a retry
    that finishes it once the realm answers."""
    wrong: list[str] = []
    answer = world.remove()
    try:
        detail = answer.json().get("detail") if answer.status_code != 204 else None
    except ValueError:
        detail = answer.text  # a bare 500 carries no words at all
    words = detail.get("message", "") if isinstance(detail, dict) else str(detail)
    if answer.status_code != 502:
        wrong.append(f"answered {answer.status_code}, not a refusal in words (502)")
    elif "could not be removed" not in words or "hidden" not in words:
        wrong.append(f"the refusal's words say nothing of what happened: {words!r}")
    if REMOVED not in realm.held:
        wrong.append("the realm no longer holds it, though it refused")
    if REMOVED not in world.listed():
        wrong.append("the identity is not listed: no Remove button to retry with")
    if world.pool.reader_left(REMOVED) != {}:
        wrong.append("a reader can read the removed identity's rows")
    if world.pool.left_for(REMOVED) != held:
        wrong.append("the rows were purged although the identity provider still holds it")
    if not world.pool.reader_left(KEPT):
        wrong.append("a present identity's rows are no longer read")
    rows = world.removal_rows()
    if len(rows) != 1:
        wrong.append(f"{len(rows)} audit rows, not one")
    elif "completed" not in rows[0]["resolved_query"] or "identity_removed" in _steps_done(rows[0]):
        # the full success row (client id and grants only) names no step: it says all of it was done
        wrong.append("the audit row says the identity was removed")
    return wrong


@pytest.mark.parametrize("status", [500, 409])
def test_a_refused_delete_at_the_real_keycloak_adapter_is_a_refusal_in_words(
    world: _World, keycloak: _Keycloak, status: int
) -> None:
    """Step 2 on the default provider, at the shape it really emits: the realm answers the DELETE
    with an error, the adapter is the real one, the route is the real one. The administrator is
    told in words, the identity is still listed, its rows are hidden and still in the mart, the
    audit row does not say it was removed, and removing it again finishes it."""
    keycloak.delete_status = status
    held = world.pool.left_for(REMOVED)
    assert _keycloak_refusal_verdict(world, keycloak, held) == []
    keycloak.delete_status = 204
    assert world.remove().status_code == 204, "a retry on a still-listed identity finishes it"
    assert REMOVED not in keycloak.held and REMOVED not in world.listed()
    assert world.pool.left_for(REMOVED) == {} and world.pool.reader_left(REMOVED) == {}
    assert len(world.removal_rows()) == 2


@pytest.mark.parametrize("status", [500, 503])
def test_a_failed_lookup_at_the_real_keycloak_adapter_is_a_refusal_in_words(
    world: _World, keycloak: _Keycloak, status: int
) -> None:
    """The same step, failing earlier: the realm lists the identity (the Remove button is there) and
    then answers the exact lookup with an error page. A refusal in words, not a bare 500."""
    keycloak.lookup_status = status
    held = world.pool.left_for(REMOVED)
    assert _keycloak_refusal_verdict(world, keycloak, held) == []
    keycloak.lookup_status = 200
    assert world.remove().status_code == 204
    assert world.pool.left_for(REMOVED) == {} and world.pool.reader_left(REMOVED) == {}


def test_a_realm_that_loses_the_client_between_lookup_and_delete_finishes_the_removal(
    world: _World, keycloak: _Keycloak
) -> None:
    """404 on the DELETE: the identity is gone at the provider, whatever took it, and its rows are
    purged, as for any other "the provider holds no such identity"."""
    keycloak.delete_status = 404
    assert world.remove().status_code == 204
    assert world.pool.left_for(REMOVED) == {} and world.pool.reader_left(REMOVED) == {}


def _the_old_delete(self: IdentityAdmin, client_id: str) -> Any:
    async def run() -> None:
        uuid = await self._uuid(client_id)  # noqa: SLF001
        if uuid is None:
            raise NoSuchDashboard("no such dashboard")
        await self._call("DELETE", f"/clients/{uuid}")  # noqa: SLF001

    return run()


def _the_old_lookup(self: IdentityAdmin, client_id: str) -> Any:
    async def run() -> str | None:
        found = (await self._call("GET", "/clients", params={"clientId": client_id})).json()  # noqa: SLF001
        exact = [c for c in found if c.get("clientId") == client_id]
        return str(exact[0]["id"]) if exact else None

    return run()


@pytest.mark.parametrize(
    "plant, field, status",
    [
        pytest.param("delete_dashboard", "delete_status", 500, id="delete-status-unread"),
        pytest.param("_uuid", "lookup_status", 503, id="lookup-status-unread"),
    ],
)
def test_the_keycloak_check_sees_each_planted_fault(
    world: _World,
    keycloak: _Keycloak,
    monkeypatch: pytest.MonkeyPatch,
    plant: str,
    field: str,
    status: int,
) -> None:
    """Rule 15: the adapter as it was (the DELETE's status never read, the lookup's answer parsed
    as a list whatever it was) is run through the same verdict at the same shapes, and the verdict
    names what is wrong."""
    monkeypatch.setattr(
        IdentityAdmin, plant, _the_old_delete if plant == "delete_dashboard" else _the_old_lookup
    )
    setattr(keycloak, field, status)
    held = world.pool.left_for(REMOVED)
    assert _keycloak_refusal_verdict(world, keycloak, held), f"the {plant} plant was not caught"


# --- A pull already running when the identity is removed ------------------------------------------


class _AnyValkey:
    async def set(self, *_: Any, **__: Any) -> bool:
        return True  # every claim is ours


class _Conduit:
    """The Conduit's feed, as `report-sync` sees it: a case list, then a feed per case. `during`
    runs when the feed is asked for, which is where the Admin removes the identity in these cases."""

    def __init__(self, world: _World) -> None:
        self.world = world
        self.during: Callable[[], None] = lambda: None
        self.feed_status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/investigations":
            return httpx.Response(200, json=[{"id": "case-9", "name": "Operation Nine"}])
        assert request.url.path == "/v1/investigations/case-9/reports/feed", request.url.path
        self.during()
        if self.feed_status != 200:
            return httpx.Response(self.feed_status, text="refused")
        return httpx.Response(
            200, text="section,label,typology,week_start,value\ntotal,alerts,,,3\n"
        )


@pytest.fixture
def conduit(world: _World, monkeypatch: pytest.MonkeyPatch) -> _Conduit:
    """The identity provider grants a token (the pass gets as far as the feed), and the Conduit is
    the in-process `_Conduit`. Nothing is sent anywhere."""
    fake = _Conduit(world)
    real = httpx.AsyncClient

    def client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        return real(*args, **{**kwargs, "transport": httpx.MockTransport(fake.handler)})

    async def grant(self: TokenSource) -> str:
        return "a-token-made-for-this-test"

    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setattr(TokenSource, "get", grant)
    return fake


async def _pass_with_removal_during(
    world: _World, conduit: _Conduit, feed_status: int
) -> tuple[list[str], Any]:
    """One pass for the removed identity (and the kept one), the removal arriving in the middle of
    the removed identity's feed fetch. Returns what is wrong afterwards, and the summary."""
    conduit.feed_status = feed_status
    removed_once: list[int] = []

    def during() -> None:
        if not removed_once:  # the first feed asked for is the removed identity's
            removed_once.append(world.remove().status_code)

    conduit.during = during
    mart = Mart(world.pool, SCHEMA)  # type: ignore[arg-type]
    try:
        summary = await sync_once(
            [_board(REMOVED), _board(KEPT)],
            mart,
            _AnyValkey(),
            slot=1,  # type: ignore[arg-type]
        )
    except AssertionError as refused:  # the fake refusing a write made without its lock
        return [f"the mart refused the write: {refused}"], None
    wrong = []
    assert removed_once == [204], "the removal in the middle of the pass did not happen"
    if world.pool.left_for(REMOVED):
        wrong.append(f"a removed identity has rows again in {sorted(world.pool.left_for(REMOVED))}")
    return wrong, summary


@pytest.mark.parametrize("feed_status", [403, 200], ids=["feed refused", "feed fetched"])
async def test_a_pull_running_during_the_removal_does_not_put_the_rows_back(
    world: _World, conduit: _Conduit, feed_status: int
) -> None:
    """The finding this closes: the route deleted the rows once and nothing deleted them again, so a
    pull in flight wrote them back (a refusal made a `pulls` row naming the case; a fetched feed made
    `figures` and `pulls`) and they stayed, readable by Admin and Alpha in Superset, for good."""
    wrong, summary = await _pass_with_removal_during(world, conduit, feed_status)
    assert wrong == []
    assert any("removed in the Admin" in f for f in summary.failures), summary.failures
    assert summary.failed >= 1
    assert set(world.pool.left_for(KEPT)) == set(world.pool.tables()), (
        "the other identity is as it was"
    )


@pytest.mark.parametrize("feed_status", [200, 403], ids=["feed fetched", "feed refused"])
@pytest.mark.parametrize("fail, status", PROVIDER_FAILURES)
async def test_a_pull_after_a_failed_provider_delete_does_not_make_the_rows_readable_again(
    world: _World, conduit: _Conduit, fail: Callable[[], Exception], status: int, feed_status: int
) -> None:
    """The finding of round 5: the provider refused to delete the identity, so it is still registered
    with its working secret, still in the environment's list, and the Admin was told its figures are
    hidden. The next sync pass begins after the stamp and is granted a token. Nothing about that pull
    may lift the stamp: the rows stay hidden (and are purged by the pass), nothing is written for it,
    and the words say the removal did not finish. Only a retry that completes, or a registration,
    ends the stamp."""
    world.identity.refuses = fail()
    assert world.remove().status_code == status
    conduit.feed_status = feed_status
    mart = Mart(world.pool, SCHEMA)  # type: ignore[arg-type]
    summary = await sync_once([_board(REMOVED), _board(KEPT)], mart, _AnyValkey(), slot=2)  # type: ignore[arg-type]
    assert world.pool.removed_at(REMOVED) is not None, "a successful pull lifted the removal stamp"
    assert world.pool.reader_left(REMOVED) == {}, "a reader can read the rows of an identity being removed"
    assert world.pool.left_for(REMOVED) == {}, "the pass finishes the purge"
    assert REMOVED in world.listed(), "the Remove button is still there"
    assert any("removed in the Admin" in f and REMOVED in f for f in summary.failures), summary.failures
    assert world.pool.reader_left(KEPT), "a present identity's rows are still read"
    world.identity.refuses = None
    assert world.remove().status_code == 204, "the retry finishes it"
    assert world.pool.reader_left(REMOVED) == {} and REMOVED not in world.listed()


async def test_a_pull_begun_after_the_stamp_cannot_undo_a_removal_whose_purge_failed(
    world: _World, conduit: _Conduit
) -> None:
    """Round 5's smaller race, in the state it leaves: the stamp was committed (the provider refused
    the first attempt); a pull begins after it and is granted its token; the removal's later attempt
    deletes the identity at the provider but its purge fails, and a purge is one transaction, so it
    leaves the mart exactly as it was (the rows there, the stamp as old as before the pull began);
    the pull then writes. The stamp must still refuse the write: the rows stay hidden throughout and
    the next pass has a stamp to purge by."""
    world.identity.refuses = IdentityAdminRefused("the identity provider could not be reached")
    assert world.remove().status_code == 502
    stamped_at = world.pool.removed_at(REMOVED)
    assert stamped_at is not None
    deleted_meanwhile: list[bool] = []

    def provider_deletes_while_the_feed_is_fetched() -> None:
        if not deleted_meanwhile:
            world.identity.registered = [
                d for d in world.identity.registered if d.client_id != REMOVED
            ]
            deleted_meanwhile.append(True)  # the purge that followed it failed: nothing changed

    conduit.during = provider_deletes_while_the_feed_is_fetched
    mart = Mart(world.pool, SCHEMA)  # type: ignore[arg-type]
    await sync_once([_board(REMOVED), _board(KEPT)], mart, _AnyValkey(), slot=2)  # type: ignore[arg-type]
    assert deleted_meanwhile == [True]
    assert world.pool.removed_at(REMOVED) == stamped_at, "the pull's write lifted or moved the stamp"
    assert world.pool.reader_left(REMOVED) == {}, "a removed identity's rows are readable"
    await sync_once([_board(KEPT)], mart, _AnyValkey(), slot=3)  # type: ignore[arg-type]
    assert world.pool.left_for(REMOVED) == {}, "the next pass had no stamp to purge by"


def _no_check(*_: Any, **__: Any) -> Any:
    async def refuse_if_removed(*_: Any, **__: Any) -> None:
        return None

    return refuse_if_removed


def _lock_never_taken(*_: Any, **__: Any) -> Any:
    async def lock(*_: Any, **__: Any) -> None:
        return None

    return lock


@pytest.mark.parametrize("feed_status", [403, 200], ids=["feed refused", "feed fetched"])
@pytest.mark.parametrize(
    ("plant", "said"),
    [
        ("the check", "has rows again"),
        ("the stamp", "has rows again"),
        ("the lock", "refused the write"),
    ],
)
async def test_the_pull_race_check_sees_each_planted_fault(
    world: _World,
    conduit: _Conduit,
    monkeypatch: pytest.MonkeyPatch,
    plant: str,
    said: str,
    feed_status: int,
) -> None:
    """Rule 15: the verdict above is red for the removal check taken out of the writers, for a removal
    that is never stamped, and for a write made without the dashboard's lock. (There is no pull clock
    to plant any more: a stamped identity is refused whenever its pull began, which is stronger.)"""
    if plant == "the check":
        monkeypatch.setattr(mart_module, "refuse_if_removed", _no_check())
    elif plant == "the stamp":
        world.pool.ignored.append(f"INSERT INTO {CONTROL_SCHEMA}.removed_dashboards")
    else:
        monkeypatch.setattr(mart_module, "lock_dashboard", _lock_never_taken())
    wrong, _ = await _pass_with_removal_during(world, conduit, feed_status)
    assert any(said in w for w in wrong), wrong


async def test_an_identity_registered_again_after_its_removal_is_written_for(
    world: _World, conduit: _Conduit
) -> None:
    """The record of a removal must not outlive its purpose: the identity registered again under the
    same name (the register route, a deliberate act) is written for, and the removed one's rows do
    not come back with it."""
    assert world.remove().status_code == 204
    assert world.pool.removed_at(REMOVED) is not None
    made = world.register()
    assert made.status_code == 201, made.text
    assert world.pool.removed_at(REMOVED) is None, "the registration lifts the removal record"
    mart = Mart(world.pool, SCHEMA)  # type: ignore[arg-type]
    summary = await sync_once([_board(REMOVED)], mart, _AnyValkey(), slot=2)  # type: ignore[arg-type]
    assert summary.failed == 0 and summary.pulled == 1, summary.failures
    assert set(world.pool.left_for(REMOVED)) == set(world.pool.tables())
    assert world.pool.reader_left(REMOVED), "its own rows are read again"


async def test_registering_again_takes_the_earlier_identitys_rows_out_before_it_writes(
    world: _World,
) -> None:
    """The removal's purge failed and the sync has not yet run: the earlier identity's rows are still
    in the mart, hidden by the stamp. Registering the name again must not make them readable beside
    the new identity's own: they go in the same transaction that lifts the stamp."""
    world.pool.fail(f"DELETE FROM {SCHEMA}", OSError("the mart dropped the connection"))
    assert world.remove().status_code == 204
    world.pool.heal()
    assert world.pool.left_for(REMOVED) != {}
    assert world.register().status_code == 201
    assert world.pool.left_for(REMOVED) == {}, "the earlier identity's rows survived the registration"
    assert world.pool.removed_at(REMOVED) is None
    mart = Mart(world.pool, SCHEMA)  # type: ignore[arg-type]
    await mart.replace(REMOVED, "case-9", "Operation Nine", 12, FEED, NOW)
    assert {r["case_id"] for r in world.pool.rows_of(REMOVED)[f"{SCHEMA}.pulls"]} == {"case-9"}
    assert {r["case_id"] for r in world.pool.rows_of(REMOVED)[f"{SCHEMA}.figures"]} == {"case-9"}
    (row,) = world.registration_rows()
    assert row["resolved_query"]["client_id"] == REMOVED
    assert row["resolved_query"]["rows_cleared"] is True


async def test_registering_a_name_the_provider_still_holds_does_not_lift_the_stamp(
    world: _World,
) -> None:
    """A removal the provider refused: the identity is still registered at the provider, with its
    working secret. Registering the same name is refused (the provider holds it: 409), and that
    refusal must leave the stamp where it is: lifting it first would make a removed person's rows
    readable again."""
    world.identity.refuses = IdentityAdminRefused("the identity provider could not be reached")
    assert world.remove().status_code == 502
    refused = world.register()
    assert refused.status_code == 409, refused.text
    assert world.pool.removed_at(REMOVED) is not None
    assert world.pool.reader_left(REMOVED) == {}
    assert world.registration_rows() == []


def test_a_registration_whose_mart_cannot_be_reopened_is_refused_and_undone(
    world: _World,
) -> None:
    """The identity is created at the provider, then the mart refuses the step that lifts the stamp.
    Nothing is left half done: the identity is deleted again (so no secret exists that nobody was
    given), the stamp stays, the rows stay hidden, the refusal is in words the Admin screen shows, and
    the registration is audited once as undone."""
    assert world.remove().status_code == 204
    world.pool.fail(
        f"DELETE FROM {CONTROL_SCHEMA}.removed_dashboards", OSError("the mart is unreachable")
    )
    refused = world.register()
    assert refused.status_code == 503, refused.text
    detail = refused.json()["detail"]
    assert detail["error"] == "reporting_mart_unreachable"
    assert "not registered" in detail["message"] and "reporting mart" in detail["message"]
    assert REMOVED not in world.listed(), "the identity registered for nothing is still there"
    assert world.identity.created == [REMOVED]
    assert world.pool.removed_at(REMOVED) is not None
    assert world.pool.reader_left(REMOVED) == {}
    (row,) = world.registration_rows()
    assert row["resolved_query"]["undone"] is True and row["resolved_query"]["rows_cleared"] is False
    world.pool.heal()
    assert world.register().status_code == 201, "registering again, with the mart back, works"
    assert world.pool.removed_at(REMOVED) is None


def test_a_registration_that_cannot_be_undone_leaves_the_rows_hidden_and_says_so(
    world: _World,
) -> None:
    """Both the mart and the identity provider refuse: the identity exists and is listed (it has a
    Remove button), its rows stay hidden by the stamp, and the words say what to do."""
    assert world.remove().status_code == 204
    world.pool.fail(
        f"DELETE FROM {CONTROL_SCHEMA}.removed_dashboards", OSError("the mart is unreachable")
    )
    world.identity.refuses = IdentityAdminRefused("the identity provider could not be reached")
    refused = world.register()
    assert refused.status_code == 503, refused.text
    message = refused.json()["detail"]["message"]
    assert "remove it" in message and "register it again" in message, message
    assert REMOVED in world.listed(), "the identity exists, so it is listed with its Remove button"
    assert world.pool.removed_at(REMOVED) is not None
    assert world.pool.reader_left(REMOVED) == {}
    (row,) = world.registration_rows()
    assert row["resolved_query"]["undone"] is False


def test_a_deployment_with_no_mart_registers_a_dashboard_as_before() -> None:
    """Reporting off: no mart, no stamp to lift, and registering is not refused for want of one."""
    pool = FakeMartPool()
    state = _World(pool)
    state.identity.registered = []
    app.dependency_overrides[get_principal] = lambda: ADMIN
    app.dependency_overrides[get_audit] = lambda: state.audit
    app.dependency_overrides[get_identity_admin] = lambda: state.identity
    app.dependency_overrides[get_report_freshness] = lambda: ReportFreshness(pool, SCHEMA)  # type: ignore[arg-type]
    app.dependency_overrides[get_handling_scheme] = load_uk_le_scheme
    try:
        assert state.register().status_code == 201
        assert state.identity.created == [REMOVED]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("plant", "said"),
    [
        ("the registration never reopens", "still hidden"),
        ("the registration leaves the earlier rows", "earlier identity's rows"),
        ("the registration reopens before the provider is asked", "stamp was lifted"),
    ],
)
def test_the_registration_check_sees_each_planted_fault(
    world: _World, monkeypatch: pytest.MonkeyPatch, plant: str, said: str
) -> None:
    """Rule 15: red for a registration that never lifts the stamp (the new identity stays hidden), for
    one that lifts it and leaves the earlier identity's rows to be read beside its own, and for one
    that lifts it before the provider has accepted the name (a refused registration must not)."""
    real = ReportFreshness.reopen

    async def never(self: ReportFreshness, client_id: str) -> bool:
        return False

    async def leaves_rows(self: ReportFreshness, client_id: str) -> bool:
        async with self._pool.acquire() as conn, conn.transaction():
            await mart_module.lock_dashboard(conn, client_id)
            await conn.execute(
                f"DELETE FROM {CONTROL_SCHEMA}.removed_dashboards WHERE dashboard = $1", client_id
            )
        return True

    wrong: list[str] = []
    if plant == "the registration reopens before the provider is asked":
        # The provider refuses the removal, so it still holds the name; a registration that lifted
        # the stamp before asking the provider would unhide a removal still to be finished.
        world.identity.refuses = IdentityAdminRefused("the identity provider could not be reached")
        assert world.remove().status_code == 502
        world.identity.refuses = None
        asked = world.identity.create_dashboard

        async def lifts_first(name: str, **kwargs: Any) -> RegisteredDashboard:
            await real(ReportFreshness(world.pool, SCHEMA), f"osprey-dashboard-{name}")  # type: ignore[arg-type]
            return await asked(name, **kwargs)

        monkeypatch.setattr(world.identity, "create_dashboard", lifts_first)
    else:
        world.pool.fail(f"DELETE FROM {SCHEMA}", OSError("the mart dropped the connection"))
        assert world.remove().status_code == 204  # the purge fails: the rows stay, hidden
        world.pool.heal()
        monkeypatch.setattr(
            ReportFreshness, "reopen",
            never if plant == "the registration never reopens" else leaves_rows,
        )  # fmt: skip
    world.register()
    if plant == "the registration reopens before the provider is asked":
        if world.pool.removed_at(REMOVED) is None:
            wrong.append("the stamp was lifted though the provider refused the registration")
    else:
        if world.pool.removed_at(REMOVED) is not None:
            wrong.append("the registered identity is still hidden")
        if world.pool.left_for(REMOVED):
            wrong.append("the earlier identity's rows are still in the mart beside its own")
    assert any(said in w for w in wrong), wrong


async def test_the_removal_record_is_stamped_by_the_database_not_the_conduit(
    world: _World,
) -> None:
    """`removed_at` is the database's clock, the one a pull's start is read from: a Conduit and a
    sync service on different hosts could disagree about the time, never about the database's."""
    before = world.pool.clock
    assert world.remove().status_code == 204
    stamp = world.pool.removed_at(REMOVED)
    assert stamp is not None and stamp > before and stamp == world.pool.clock


# --- A BI tool cannot read the record of a removal ------------------------------------------------


class _Recorder:
    """Records what `ensure_reader` asks the database to do; it models no other statement."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def acquire(self) -> Any:
        recorder = self

        @asynccontextmanager
        async def held() -> Any:
            yield recorder

        return held()

    async def fetchval(self, sql: str, *_: Any) -> Any:
        return 1

    async def execute(self, sql: str, *_: Any) -> str:
        self.statements.append(" ".join(sql.split()))
        return "OK"


def _grants_reaching_the_control_schema(statements: list[str]) -> list[str]:
    return [s for s in statements if CONTROL_SCHEMA in s or "ALL SCHEMAS" in s.upper()]


async def test_the_reader_role_is_never_given_the_record_of_removals() -> None:
    """Rule 4 for the one new thing the mart's neighbour holds: which identities were removed is not
    readable by Superset's role (the mart's own schema is, and holds no row of a removed identity)."""
    recorder = _Recorder()
    await Mart(recorder, SCHEMA).ensure_reader("osprey_reports_reader", secrets.token_urlsafe(8))  # type: ignore[arg-type]
    assert any(f"IN SCHEMA {SCHEMA}" in s for s in recorder.statements), "the reader reads the mart"
    assert _grants_reaching_the_control_schema(recorder.statements) == []
    assert CONTROL_SCHEMA != SCHEMA


def test_the_reader_check_sees_a_grant_on_the_control_schema() -> None:
    """Rule 15: the same observation, red for a grant the real `ensure_reader` would never issue."""
    planted = [f"GRANT USAGE ON SCHEMA {CONTROL_SCHEMA} TO osprey_reports_reader"]
    assert _grants_reaching_the_control_schema(planted) == planted
