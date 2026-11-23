"""How fresh each dashboard's figures are (`06_DECISIONS.md` ADR-111 Amendment 2): read from the
reporting mart's `pulls` table, which `report-sync` writes, for the Admin area's Dashboards screen.

Only aggregates per dashboard leave here — when it last truly pulled, its latest failure in words
and when, and how many cases it pulls — never a case id, so the Admin screen says a feed is stale
without saying which cases a dashboard may read. For an identity whose removal is under way, not
even those: it is listed as pending and its rows are not read (`by_dashboard`). A deployment with
reporting off has no mart, and every dashboard is then simply "never pulled".

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

The stamp is lifted by one act only, `reopen`: the Admin registering the identity again, after the
identity provider has accepted the name. Never by a pull: an identity whose deletion at the provider
failed is still registered there with a working secret and looks to a pull exactly like one
registered again, so its rows must stay hidden until the removal is finished.

The Conduit uses the connection it already has, as the same database role `report-sync` writes as.
"""

from __future__ import annotations

from datetime import datetime

import asyncpg
from pydantic import BaseModel
from services.report_sync.mart import (
    CONTROL_SCHEMA,
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
    #: The identity's removal is under way (it has a removal stamp): no figure above is shown.
    removal_pending: bool = False


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
        case's next good pull clears it (`report-sync` clears it), so a failure here is current.

        A stamped identity (one whose removal is under way) has none of its figures here: the query
        runs as the tables' owner, which row security does not bind, so the stamp is asked in the
        query itself, and the identity is reported with its removal pending and nothing else. It is
        the same stamp the readers use. A deployment with no mart, or one whose record of removals
        was never made, lists nothing."""
        s = self._schema
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""SELECT dashboard, max(last_pulled) AS last_pulled, count(*) AS cases,
                               (array_agg(last_failure ORDER BY failed_at DESC NULLS LAST))[1]
                                   AS last_failure,
                               max(failed_at) AS failed_at
                        FROM {s}.pulls
                        WHERE NOT EXISTS (SELECT 1 FROM {CONTROL_SCHEMA}.removed_dashboards r
                                          WHERE r.dashboard = pulls.dashboard)
                        GROUP BY dashboard"""
                )
                # Read after the figures: a stamp made in between hides them as well.
                stamped = {
                    str(r["dashboard"])
                    for r in await conn.fetch(
                        f"SELECT dashboard FROM {CONTROL_SCHEMA}.removed_dashboards "
                        "ORDER BY dashboard"
                    )
                }
        except (asyncpg.UndefinedTableError, asyncpg.InvalidSchemaNameError):
            return {}
        listed = {
            str(r["dashboard"]): Freshness(
                last_pulled=r["last_pulled"],
                last_failure=r["last_failure"] if r["failed_at"] else None,
                failed_at=r["failed_at"],
                cases_pulled=int(r["cases"]),
            )
            for r in rows
            if str(r["dashboard"]) not in stamped
        }
        return {**listed, **{name: Freshness(removal_pending=True) for name in stamped}}

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

    async def reopen(self, client_id: str) -> bool:
        """The identity is registered again (the identity provider has accepted the name): the
        earlier identity's rows go from every table and the stamp is lifted, in one transaction
        under the dashboard's lock, so they are never readable beside the new identity's own.
        Returns True when a stamp was lifted, False when there was none (a name never removed here)
        or no mart. A failure is `MartUnreachable`, and nothing was changed: the stamp stays."""
        try:
            async with self._pool.acquire() as conn, conn.transaction():
                await lock_dashboard(conn, client_id)
                try:
                    stamped = await conn.fetchval(
                        f"SELECT removed_at FROM {CONTROL_SCHEMA}.removed_dashboards "
                        "WHERE dashboard = $1",
                        client_id,
                    )
                except (asyncpg.UndefinedTableError, asyncpg.InvalidSchemaNameError):
                    raise _NoMart from None
                if stamped is None:
                    return False
                try:
                    await delete_dashboard_rows(conn, self._schema, client_id, DASHBOARD_TABLES)
                except (asyncpg.UndefinedTableError, asyncpg.InvalidSchemaNameError):
                    raise _NoMart from None
                await conn.execute(
                    f"DELETE FROM {CONTROL_SCHEMA}.removed_dashboards WHERE dashboard = $1",
                    client_id,
                )
                return True
        except _NoMart:
            return False
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError) as e:
            raise MartUnreachable(str(e) or type(e).__name__) from e


class _NoMart(Exception):
    """Nothing to remove: the reporting mart was never made."""
