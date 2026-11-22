"""The reporting mart (`06_DECISIONS.md` ADR-111 Amendment 2): the figures dashboards read, in a
Postgres schema the sync service owns — never the Conduit's tables, never graph content.

`figures`: one row per figure, keyed by dashboard, case, period, section, label, typology and week —
the feed's own CSV columns — upserted so a re-pull changes only what changed (`changed_at` moves
only then), and a figure the feed no longer carries is removed. `pulls`: per dashboard and case,
when it was last truly pulled and the last failure in words, so the Admin area can say a feed is
stale. A BI tool reads through `ensure_reader`'s role, which may select and nothing else.

`removed_dashboards` is not in that schema. It lives in a schema of its own (`CONTROL_SCHEMA`) that
`ensure_reader` never grants, so a BI tool cannot read it. It holds the **removal stamp**: when an
identity was removed in the Admin. The stamp is what makes a removed identity's rows unreadable, and
it is committed before anything else is done (`services/api/report_freshness.py`):

- a BI tool's role reads the mart tables behind row-level security whose one policy asks
  `dashboard_is_current` (a function that runs as the table's owner and reads the stamp), so a
  stamped identity's rows are not returned to it, at once, whether or not they have been deleted
  yet (`hiding_statements`; the owner, which writes, is not subject to it);
- every write refuses a stamped identity, whenever its pull began and whether it succeeded or was
  refused: `replace` and `record_failure` raise `DashboardRemoved` and write nothing;
- the sync pass deletes the rows of every stamped identity (`purge_removed`), so a purge the Conduit
  could not finish costs nothing and needs no person;
- the stamp is lifted by one act only: the Admin registering the identity again, which the identity
  provider has accepted (`ReportFreshness.reopen`, which also takes the earlier identity's rows out
  in the same transaction, so they never appear beside its own). It is never lifted by a pull,
  however late the pull began or however good its token: an identity whose deletion at the identity
  provider failed is still registered there with a working secret, and looks to a pull exactly like
  one registered again.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import asyncpg

FigureRow = tuple[str, str, str, str, int]  # section, label, typology, week_start, value
#: Every table `_bootstrap` makes, each holding a `dashboard` column. A dashboard's rows are removed
#: from all of them, by `prune` here and by the Conduit when an identity is removed
#: (`services/api/report_freshness.py`): a table added to the schema is added here, and
#: `tests/services/api/test_removed_identity_mart_rows.py` fails if it is not.
DASHBOARD_TABLES = ("pulls", "figures")
#: Where a removal is recorded: beside the mart, never in it and never granted to a reader.
CONTROL_SCHEMA = "osprey_report_control"
_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _identifier(name: str) -> str:
    if not _NAME.match(name):
        raise ValueError(f"not a plain identifier: {name!r}")
    return name


class DashboardRemoved(Exception):
    """The identity was removed in the Admin (it has a removal stamp): nothing is written for it."""


async def lock_dashboard(conn: Any, dashboard: str) -> None:
    """Held to the end of the transaction. A removal and a write for one dashboard take it in turn,
    so a write either lands before the removal (which then deletes it) or sees the removal."""
    await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", dashboard)


async def ensure_control(conn: Any) -> None:
    await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {CONTROL_SCHEMA}")
    await conn.execute(
        f"""CREATE TABLE IF NOT EXISTS {CONTROL_SCHEMA}.removed_dashboards (
            dashboard TEXT NOT NULL, removed_at TIMESTAMPTZ NOT NULL, PRIMARY KEY (dashboard))"""
    )


def rows_in(status: object) -> int:
    """The row count of a command tag (`DELETE 3`); 0 when it carries none."""
    tail = str(status).rsplit(" ", 1)[-1]
    return int(tail) if tail.isdigit() else 0


async def delete_dashboard_rows(
    conn: Any, schema: str, dashboard: str, tables: Sequence[str] = DASHBOARD_TABLES
) -> int:
    """Every row naming `dashboard`, in each of `tables`; with the dashboard's lock held. Returns
    how many rows went."""
    removed = 0
    for table in tables:
        done = await conn.execute(f"DELETE FROM {schema}.{table} WHERE dashboard = $1", dashboard)
        removed += rows_in(done)
    return removed


async def stamp_removed(conn: Any, dashboard: str) -> None:
    """The removal stamp, by the database's own clock; with the dashboard's lock held and the
    control schema made. Stamping again moves it forward."""
    await conn.execute(
        f"""INSERT INTO {CONTROL_SCHEMA}.removed_dashboards (dashboard, removed_at)
            VALUES ($1, clock_timestamp()) ON CONFLICT (dashboard)
            DO UPDATE SET removed_at = EXCLUDED.removed_at""",
        dashboard,
    )  # fmt: skip


async def refuse_if_removed(conn: Any, dashboard: str) -> None:
    """Called with the dashboard's lock held; a stamped identity is never written for.

    Every write refuses one that has a stamp, whatever moment its pull began (an identity removed in
    the Admin may still be in the environment's list, its token granted, if its deletion at the
    identity provider failed). Only a registration lifts the stamp (`ReportFreshness.reopen`)."""
    removed_at = await conn.fetchval(
        f"SELECT removed_at FROM {CONTROL_SCHEMA}.removed_dashboards WHERE dashboard = $1",
        dashboard,
    )
    if removed_at is not None:
        raise DashboardRemoved(dashboard)


#: The function a reader's policy asks, in the mart's own schema (which a reader may use).
HIDING_FUNCTION = "dashboard_is_current"


def hiding_statements(schema: str) -> list[str]:
    """What hides a stamped identity's rows from a BI tool's role, at once: a function that answers
    whether a dashboard has no removal stamp, and row-level security on every table with a policy
    that asks it. The function runs as its owner (`SECURITY DEFINER`) because the reader's role is
    never granted the control schema; the owner of the tables, which writes, bypasses the policy."""
    function = f"{schema}.{HIDING_FUNCTION}"
    statements = [
        f"""CREATE OR REPLACE FUNCTION {function}(d text) RETURNS boolean LANGUAGE sql STABLE
            SECURITY DEFINER SET search_path = pg_catalog AS $$
            SELECT NOT EXISTS (SELECT 1 FROM {CONTROL_SCHEMA}.removed_dashboards r
                               WHERE r.dashboard = d) $$"""
    ]
    for table in DASHBOARD_TABLES:
        statements += [
            f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY",
            f"DROP POLICY IF EXISTS hide_removed ON {schema}.{table}",
            f"""CREATE POLICY hide_removed ON {schema}.{table} FOR SELECT
                USING ({function}(dashboard))""",
        ]
    return [" ".join(s.split()) for s in statements]


class Mart:
    def __init__(self, pool: asyncpg.Pool, schema: str) -> None:
        self._pool = pool
        self.schema = _identifier(schema)

    @classmethod
    async def connect(cls, dsn: str, *, schema: str = "osprey_reports") -> Mart:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        mart = cls(pool, schema)
        await mart._bootstrap()
        return mart

    async def close(self) -> None:
        await self._pool.close()

    async def _bootstrap(self) -> None:
        s = self.schema
        async with self._pool.acquire() as conn:
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {s}")
            await conn.execute(
                f"""CREATE TABLE IF NOT EXISTS {s}.figures (
                    dashboard TEXT NOT NULL, case_id TEXT NOT NULL, case_name TEXT NOT NULL,
                    period_weeks INTEGER NOT NULL, section TEXT NOT NULL, label TEXT NOT NULL,
                    typology TEXT NOT NULL, week_start TEXT NOT NULL, value BIGINT NOT NULL,
                    changed_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (dashboard, case_id, period_weeks, section, label, typology,
                                 week_start))"""
            )
            await conn.execute(
                f"""CREATE TABLE IF NOT EXISTS {s}.pulls (
                    dashboard TEXT NOT NULL, case_id TEXT NOT NULL, last_pulled TIMESTAMPTZ,
                    last_failure TEXT, failed_at TIMESTAMPTZ, PRIMARY KEY (dashboard, case_id))"""
            )
            await ensure_control(conn)
            for statement in hiding_statements(s):
                await conn.execute(statement)

    async def replace(
        self,
        dashboard: str,
        case_id: str,
        case_name: str,
        weeks: int,
        rows: Sequence[FigureRow],
        at: datetime,
    ) -> int:
        """The case's figures for this dashboard and period, as the feed now has them: changed rows
        updated, new ones added, rows no longer fed removed — in one transaction. Returns how many
        rows changed or were added. A stamped (removed) identity raises `DashboardRemoved` and
        nothing is written."""
        s = self.schema
        changed = 0
        async with self._pool.acquire() as conn, conn.transaction():
            await lock_dashboard(conn, dashboard)
            await refuse_if_removed(conn, dashboard)
            for section, label, typology, week, value in rows:
                result = await conn.execute(
                    f"""INSERT INTO {s}.figures VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                        ON CONFLICT (dashboard, case_id, period_weeks, section, label, typology,
                                     week_start)
                        DO UPDATE SET value = EXCLUDED.value, changed_at = EXCLUDED.changed_at,
                                      case_name = EXCLUDED.case_name
                        WHERE {s}.figures.value IS DISTINCT FROM EXCLUDED.value""",
                    dashboard, case_id, case_name, weeks, section, label, typology, week, value, at,
                )  # fmt: skip
                changed += int(result.split()[-1])
            keep = [(r[0], r[1], r[2], r[3]) for r in rows]
            await conn.execute(
                f"""DELETE FROM {s}.figures
                    WHERE dashboard = $1 AND case_id = $2 AND period_weeks = $3
                    AND (section, label, typology, week_start) NOT IN
                        (SELECT * FROM unnest($4::text[], $5::text[], $6::text[], $7::text[]))""",
                dashboard, case_id, weeks,
                *([k[i] for k in keep] for i in range(4)),
            )  # fmt: skip
            await conn.execute(
                f"""INSERT INTO {s}.pulls (dashboard, case_id, last_pulled, last_failure, failed_at)
                    VALUES ($1, $2, $3, NULL, NULL)
                    ON CONFLICT (dashboard, case_id) DO UPDATE
                    SET last_pulled = EXCLUDED.last_pulled, last_failure = NULL,
                        failed_at = NULL""",
                dashboard, case_id, at,
            )  # fmt: skip
        return changed

    async def record_failure(self, dashboard: str, case_id: str, words: str, at: datetime) -> None:
        """A pull that failed, in words; the rows and their last good pull are left as they were.
        A refusal never makes a removed identity's row, whenever its pull began: a stamped identity
        raises `DashboardRemoved` and writes nothing (its rows already there are hidden from a
        reader by the stamp and deleted by the next sync pass)."""
        async with self._pool.acquire() as conn, conn.transaction():
            await lock_dashboard(conn, dashboard)
            await refuse_if_removed(conn, dashboard)
            await conn.execute(
                f"""INSERT INTO {self.schema}.pulls (dashboard, case_id, last_failure, failed_at)
                    VALUES ($1, $2, $3, $4) ON CONFLICT (dashboard, case_id) DO UPDATE
                    SET last_failure = EXCLUDED.last_failure, failed_at = EXCLUDED.failed_at""",
                dashboard, case_id, words[:500], at,
            )  # fmt: skip

    async def prune(self, configured: Sequence[str]) -> int:
        """Removes every dashboard no longer configured: its rows in every table it has one in.
        Returns how many rows went."""
        removed = 0
        async with self._pool.acquire() as conn, conn.transaction():
            for table in DASHBOARD_TABLES:
                result = await conn.execute(
                    f"DELETE FROM {self.schema}.{table} WHERE NOT (dashboard = ANY($1::text[]))",
                    list(configured),
                )
                removed += int(result.split()[-1])
        return removed

    async def purge_removed(self) -> int:
        """Deletes every row of every stamped identity, in every table: what finishes a removal
        whose purge the Conduit could not complete. The stamp stays, so a refusal cannot write the
        identity again. One registered again and written for since has no stamp and is left alone
        (the stamp is looked at again under the lock). Returns how many rows went."""
        async with self._pool.acquire() as conn:
            stamped = [
                str(r["dashboard"])
                for r in await conn.fetch(
                    f"SELECT dashboard FROM {CONTROL_SCHEMA}.removed_dashboards ORDER BY dashboard"
                )
            ]
        purged = 0
        for dashboard in stamped:
            async with self._pool.acquire() as conn, conn.transaction():
                await lock_dashboard(conn, dashboard)
                still = await conn.fetchval(
                    f"SELECT removed_at FROM {CONTROL_SCHEMA}.removed_dashboards "
                    "WHERE dashboard = $1",
                    dashboard,
                )
                if still is not None:
                    purged += await delete_dashboard_rows(conn, self.schema, dashboard)
        return purged

    async def figures(self, dashboard: str) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM {self.schema}.figures WHERE dashboard = $1 "
                "ORDER BY section, label, typology, week_start",
                dashboard,
            )
        return [dict(r) for r in rows]

    async def pulls(self, dashboard: str) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM {self.schema}.pulls WHERE dashboard = $1 ORDER BY case_id",
                dashboard,
            )
        return [dict(r) for r in rows]

    async def ensure_reader(self, role: str, password: str) -> None:
        """A login role that may read the mart and nothing else — what a BI tool connects as."""
        role = _identifier(role)
        async with self._pool.acquire() as conn:
            exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", role)
            escaped = password.replace("'", "''")
            if exists:
                await conn.execute(f"ALTER ROLE {role} WITH LOGIN PASSWORD '{escaped}'")
            else:
                await conn.execute(f"CREATE ROLE {role} WITH LOGIN PASSWORD '{escaped}'")
            await conn.execute(f"GRANT USAGE ON SCHEMA {self.schema} TO {role}")
            await conn.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {self.schema} TO {role}")
            await conn.execute(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA {self.schema} GRANT SELECT ON TABLES TO {role}"
            )

    async def drop_reader(self, role: str) -> None:
        role = _identifier(role)
        async with self._pool.acquire() as conn:
            await conn.execute(f"DROP OWNED BY {role}")
            await conn.execute(f"DROP ROLE IF EXISTS {role}")

    async def drop(self) -> None:
        """Tests only: the whole schema."""
        async with self._pool.acquire() as conn:
            await conn.execute(f"DROP SCHEMA IF EXISTS {self.schema} CASCADE")
