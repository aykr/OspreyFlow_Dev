"""How fresh each dashboard's figures are (`06_DECISIONS.md` ADR-111 Amendment 2): read from the
reporting mart's `pulls` table, which `report-sync` writes, for the Admin area's Dashboards screen.

Only aggregates per dashboard leave here — when it last truly pulled, its latest failure in words
and when, and how many cases it pulls — never a case id, so the Admin screen says a feed is stale
without saying which cases a dashboard may read. The Conduit only reads the table; a deployment with
reporting off has no mart, and every dashboard is then simply "never pulled".
"""

from __future__ import annotations

from datetime import datetime

import asyncpg
from pydantic import BaseModel

#: The schema `report-sync` owns (`services/report_sync/mart.py`).
MART_SCHEMA = "osprey_reports"


class Freshness(BaseModel):
    last_pulled: datetime | None = None
    last_failure: str | None = None
    failed_at: datetime | None = None
    cases_pulled: int = 0


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
