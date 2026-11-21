"""How fresh each dashboard's figures are (`06_DECISIONS.md` ADR-111 Amendment 2): read from the
reporting mart's `pulls` table, which `report-sync` writes, for the Admin area's Dashboards screen.

Only aggregates per dashboard leave here — when it last truly pulled, its latest failure in words
and when, and how many cases it pulls — never a case id, so the Admin screen says a feed is stale
without saying which cases a dashboard may read. A deployment with reporting off has no mart, and
every dashboard is then simply "never pulled".

The one thing the Conduit writes to the mart is a removal: when an administrator removes a dashboard
identity its rows go from every table `report-sync` writes (`remove_dashboard`), because Superset's
Admin and Alpha read the whole mart (ADR-148 Amendment 21) and `report-sync` prunes only against its
own configured list, which nothing updates. The Conduit uses the connection it already has, as the
same database role `report-sync` writes as.
"""

from __future__ import annotations

from datetime import datetime

import asyncpg
from pydantic import BaseModel
from services.report_sync.mart import DASHBOARD_TABLES

#: The schema `report-sync` owns (`services/report_sync/mart.py`).
MART_SCHEMA = "osprey_reports"


class Freshness(BaseModel):
    last_pulled: datetime | None = None
    last_failure: str | None = None
    failed_at: datetime | None = None
    cases_pulled: int = 0


class MartUnreachable(Exception):
    """The mart could not be written, so a removal did not reach it; carries the reason."""


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

    async def remove_dashboard(self, client_id: str) -> int:
        """Every row of this dashboard identity, in every table the sync writes, in one transaction
        (all or none). Returns how many went. A deployment with no mart has nothing to remove; any
        other failure is `MartUnreachable`, never a quiet zero."""
        s = self._schema
        removed = 0
        try:
            async with self._pool.acquire() as conn, conn.transaction():
                for table in DASHBOARD_TABLES:
                    result = await conn.execute(
                        f"DELETE FROM {s}.{table} WHERE dashboard = $1", client_id
                    )
                    removed += int(result.split()[-1])
        except (asyncpg.UndefinedTableError, asyncpg.InvalidSchemaNameError):
            return 0
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError) as e:
            raise MartUnreachable(str(e) or type(e).__name__) from e
        return removed
