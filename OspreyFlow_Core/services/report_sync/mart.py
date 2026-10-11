"""The reporting mart (`06_DECISIONS.md` ADR-111 Amendment 2): the figures dashboards read, in a
Postgres schema the sync service owns — never the Conduit's tables, never graph content.

`figures`: one row per figure, keyed by dashboard, case, period, section, label, typology and week —
the feed's own CSV columns — upserted so a re-pull changes only what changed (`changed_at` moves
only then), and a figure the feed no longer carries is removed. `pulls`: per dashboard and case,
when it was last truly pulled and the last failure in words, so the Admin area can say a feed is
stale. A BI tool reads through `ensure_reader`'s role, which may select and nothing else.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import asyncpg

FigureRow = tuple[str, str, str, str, int]  # section, label, typology, week_start, value
_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _identifier(name: str) -> str:
    if not _NAME.match(name):
        raise ValueError(f"not a plain identifier: {name!r}")
    return name


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
        rows changed or were added."""
        s = self.schema
        changed = 0
        async with self._pool.acquire() as conn, conn.transaction():
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
        """A pull that failed, in words; the rows and their last good pull are left as they were."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"""INSERT INTO {self.schema}.pulls (dashboard, case_id, last_failure, failed_at)
                    VALUES ($1, $2, $3, $4) ON CONFLICT (dashboard, case_id) DO UPDATE
                    SET last_failure = EXCLUDED.last_failure, failed_at = EXCLUDED.failed_at""",
                dashboard, case_id, words[:500], at,
            )  # fmt: skip

    async def prune(self, configured: Sequence[str]) -> int:
        """Removes every dashboard no longer configured — its figures and its pulls."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                f"DELETE FROM {self.schema}.pulls WHERE NOT (dashboard = ANY($1::text[]))",
                list(configured),
            )
            result = await conn.execute(
                f"DELETE FROM {self.schema}.figures WHERE NOT (dashboard = ANY($1::text[]))",
                list(configured),
            )
        return int(result.split()[-1])

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
