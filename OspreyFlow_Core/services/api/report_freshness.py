"""How fresh each dashboard's figures are (`06_DECISIONS.md` ADR-111 Amendment 2): read from the
reporting mart's `pulls` table, which `report-sync` writes, for the Admin area's Dashboards screen.

Only aggregates per dashboard leave here — when it last truly pulled, its latest failure in words
and when, and how many cases it pulls — never a case id, so the Admin screen says a feed is stale
without saying which cases a dashboard may read. A deployment with reporting off has no mart, and
every dashboard is then simply "never pulled".

The one thing the Conduit writes to the mart is a removal. When an administrator removes a dashboard
identity, Superset's Admin and Alpha read the whole mart (ADR-148 Amendment 21) and `report-sync`
prunes only against its own configured list, which nothing updates, so the removal is made in an
order in which no step's failure can leave the identity's rows readable:

1. `stamp`: the removal is stamped and committed in a transaction of its own, before the identity
   provider is called and never rolled back with anything after it. The stamp is what makes the
   rows unreadable: a reader's role sees none of a stamped identity's rows, and every write refuses
   it (`services/report_sync/mart.py`).
2. The identity provider deletes the identity (the route's step; if it fails the identity is still
   listed, its rows stay hidden, and removing it again is idempotent).
3. `purge`: the rows go from every table the sync writes, and the stamp is made again. It is
   repeatable, and the sync pass finishes it (`Mart.purge_removed`) if it fails here.

The Conduit uses the connection it already has, as the same database role `report-sync` writes as.
"""

from __future__ import annotations

from datetime import datetime

import asyncpg
from pydantic import BaseModel
from services.report_sync.mart import (
    DASHBOARD_TABLES,
    delete_dashboard_rows,
    ensure_control,
    lock_dashboard,
    stamp_removed,
)

#: The schema `report-sync` owns (`services/report_sync/mart.py`).
MART_SCHEMA = "osprey_reports"


class Freshness(BaseModel):
    last_pulled: datetime | None = None
    last_failure: str | None = None
    failed_at: datetime | None = None
    cases_pulled: int = 0


class MartUnreachable(Exception):
    """The mart could not be read or written, so a removal step did not reach it; carries the
    reason."""


class ReportFreshness:
    def __init__(self, pool: asyncpg.Pool, schema: str = MART_SCHEMA) -> None:
        self._pool = pool
        self._schema = schema

    @classmethod
    async def connect(cls, dsn: str, *, schema: str = MART_SCHEMA) -> ReportFreshness:
        return cls(await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2), schema)

    async def close(self) -> None:
        await self._pool.close()

    async def by_dashboard(self) -> dict[str, Freshness]:
        """Each dashboard the mart has pulled for. A case's failure is still standing until that
        case's next good pull clears it (`report-sync` clears it), so a failure here is current."""
        s = self._schema
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""SELECT dashboard, max(last_pulled) AS last_pulled, count(*) AS cases,
                               (array_agg(last_failure ORDER BY failed_at DESC NULLS LAST))[1]
                                   AS last_failure,
                               max(failed_at) AS failed_at
                        FROM {s}.pulls GROUP BY dashboard"""
                )
        except (asyncpg.UndefinedTableError, asyncpg.InvalidSchemaNameError):
            return {}
        return {
            str(r["dashboard"]): Freshness(
                last_pulled=r["last_pulled"],
                last_failure=r["last_failure"] if r["failed_at"] else None,
                failed_at=r["failed_at"],
                cases_pulled=int(r["cases"]),
            )
            for r in rows
        }

    async def holds_rows(self, client_id: str) -> bool:
        """Whether the mart holds a row naming this identity, in any table. A deployment with no
        mart holds none."""
        try:
            async with self._pool.acquire() as conn:
                for table in DASHBOARD_TABLES:
                    if await conn.fetchval(
                        f"SELECT EXISTS (SELECT 1 FROM {self._schema}.{table} "
                        "WHERE dashboard = $1)",
                        client_id,
                    ):
                        return True
        except (asyncpg.UndefinedTableError, asyncpg.InvalidSchemaNameError):
            return False
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError) as e:
            raise MartUnreachable(str(e) or type(e).__name__) from e
        return False

    async def stamp(self, client_id: str) -> bool:
        """Step 1: the removal stamp, committed on its own (a transaction of its own, under the
        dashboard's lock) before the identity provider is called. From here a reader sees none
        of the identity's rows. Returns False, stamping nothing, when the deployment has no mart;
        any other failure is `MartUnreachable`, never a quiet success."""
        try:
            async with self._pool.acquire() as conn, conn.transaction():
                made = await conn.fetchval(
                    "SELECT to_regclass($1)", f"{self._schema}.{DASHBOARD_TABLES[0]}"
                )
                if made is None:
                    return False
                await lock_dashboard(conn, client_id)
                await ensure_control(conn)
                await stamp_removed(conn, client_id)
                return True
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError) as e:
            raise MartUnreachable(str(e) or type(e).__name__) from e

    async def purge(self, client_id: str) -> int:
        """Step 3: the rows go from every table the sync writes, and the stamp is made again (a pull
        that began after the first stamp and before the provider's deletion may not write either).
        One transaction, under the dashboard's lock: all of it or none. A failure is
        `MartUnreachable`; the stamp already committed keeps the rows hidden and the sync pass
        deletes them. Returns how many rows went; a deployment with no mart has none."""
        try:
            async with self._pool.acquire() as conn, conn.transaction():
                await lock_dashboard(conn, client_id)
                try:
                    purged = await delete_dashboard_rows(
                        conn, self._schema, client_id, DASHBOARD_TABLES
                    )
                except (asyncpg.UndefinedTableError, asyncpg.InvalidSchemaNameError):
                    raise _NoMart from None
                await ensure_control(conn)
                await stamp_removed(conn, client_id)
                return purged
        except _NoMart:
            return 0
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError) as e:
            raise MartUnreachable(str(e) or type(e).__name__) from e


class _NoMart(Exception):
    """Nothing to remove: the reporting mart was never made."""
