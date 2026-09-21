"""`MonitorStore` — `06_DECISIONS.md` ADR-036/037, Phase 7 Stage 6b. Same shape every other
control-plane store in this codebase already is. References a `SavedPattern` by `pattern_id`,
never copies its own definition (`schemas.domain.Monitor`'s own docstring has the full reasoning).

**`owner_id` filtered in the query itself, from the start** (`06_DECISIONS.md` ADR-041) —
`scripts/authorized_query_check.py` is what actually proves this.
"""

from __future__ import annotations

from datetime import UTC, datetime

import asyncpg

from conduit_common.identity import new_id
from schemas.domain import Monitor, Principal

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS monitors (
    id TEXT PRIMARY KEY,
    pattern_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (pattern_id, owner_id)
);
CREATE INDEX IF NOT EXISTS monitors_owner_id_idx ON monitors (owner_id);
"""


class MonitorNotFoundError(Exception):
    """Also raised when the monitor exists but `owner_id` does not match the calling principal —
    the same existence-leak discipline every other store in this codebase already establishes."""


def _row_to_monitor(row: asyncpg.Record) -> Monitor:
    return Monitor(
        id=row["id"],
        pattern_id=row["pattern_id"],
        owner_id=row["owner_id"],
        created_at=row["created_at"],
    )


class MonitorStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> MonitorStore:
        pool = await asyncpg.create_pool(dsn=dsn)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def create(self, principal: Principal, *, pattern_id: str) -> Monitor:
        """The caller (a future route, or this stage's own tests) is responsible for proving
        `pattern_id` is a pattern `principal` actually owns first — via `PatternStore.
        get_authorized`, the same store `06_DECISIONS.md` ADR-036's own owning-principal
        reference already lives on — not re-derived here from a second, independent check
        against `SavedPattern.owner_id`. `UNIQUE (pattern_id, owner_id)` makes turning the same
        pattern into a monitor twice an upsert-shaped no-op error, not a duplicate row silently
        doubling every future alert."""
        monitor = Monitor(
            id=new_id(), pattern_id=pattern_id, owner_id=principal.id, created_at=datetime.now(UTC)
        )
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO monitors (id, pattern_id, owner_id, created_at) "
                "VALUES ($1, $2, $3, $4)",
                monitor.id,
                monitor.pattern_id,
                monitor.owner_id,
                monitor.created_at,
            )
        return monitor

    async def get_authorized(self, monitor_id: str, principal: Principal) -> Monitor:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, pattern_id, owner_id, created_at FROM monitors "
                "WHERE id = $1 AND owner_id = $2",
                monitor_id,
                principal.id,
            )
        if row is None:
            raise MonitorNotFoundError(monitor_id)
        return _row_to_monitor(row)

    async def list_authorized(self, principal: Principal) -> list[Monitor]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, pattern_id, owner_id, created_at FROM monitors "
                "WHERE owner_id = $1 ORDER BY created_at DESC",
                principal.id,
            )
        return [_row_to_monitor(row) for row in rows]

    async def list_all_active(self) -> list[Monitor]:
        """Not principal-scoped — the evaluator's own system-level population read, the identical
        reasoning `HotlistStore.list_all_active`'s own docstring gives; never exposed through a
        route."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, pattern_id, owner_id, created_at FROM monitors")
        return [_row_to_monitor(row) for row in rows]


__all__ = ["MonitorNotFoundError", "MonitorStore"]
