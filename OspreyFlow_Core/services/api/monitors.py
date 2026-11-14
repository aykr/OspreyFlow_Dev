"""`MonitorStore` — `06_DECISIONS.md` ADR-036/037, Phase 7 Stage 6b. Same shape every other
control-plane store in this codebase already is. References a `SavedPattern` by `pattern_id`,
never copies its own definition (`schemas.domain.Monitor`'s own docstring has the full reasoning).

**`owner_id` filtered in the query itself, from the start** (`06_DECISIONS.md` ADR-041) —
`tools/authorized_query_check.py` is what actually proves this.
"""

from __future__ import annotations

from datetime import UTC, datetime

import asyncpg

from conduit_common.identity import new_id
from schemas.domain import (
    Monitor,
    MonitorScheduleInput,
    Principal,
    StoppedReason,
    WatchStatus,
)

from .dataset_scope import made_in, reach_clause
from .watch_status import stopped_why

#: `ADD COLUMN IF NOT EXISTS` — `alerts.py`'s own `_BOOTSTRAP_SQL` docstring has the full reasoning.
_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS monitors (
    id TEXT PRIMARY KEY,
    pattern_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (pattern_id, owner_id)
);
ALTER TABLE monitors ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
-- ADR-044 Amendment 1: why it is stopped, NULL while active.
ALTER TABLE monitors ADD COLUMN IF NOT EXISTS status_detail TEXT;
CREATE INDEX IF NOT EXISTS monitors_owner_id_idx ON monitors (owner_id);
ALTER TABLE monitors ADD COLUMN IF NOT EXISTS dataset_id TEXT;
-- ADR-146 decision 4 (G16): each watched pattern also runs on its own schedule, daily by default.
ALTER TABLE monitors ADD COLUMN IF NOT EXISTS every TEXT NOT NULL DEFAULT 'daily';
ALTER TABLE monitors ADD COLUMN IF NOT EXISTS hour INTEGER NOT NULL DEFAULT 6;
ALTER TABLE monitors ADD COLUMN IF NOT EXISTS weekday INTEGER;
ALTER TABLE monitors ADD COLUMN IF NOT EXISTS last_slot TIMESTAMPTZ;
"""


class MonitorNotFoundError(Exception):
    """Also raised when the monitor exists but `owner_id` does not match the calling principal —
    the same existence-leak discipline every other store in this codebase already establishes."""


def _detail(row: asyncpg.Record) -> StoppedReason | None:
    """ADR-044 Amendment 1: the stopped reason, only while stopped, and only one this release
    knows."""
    detail = row["status_detail"] if row["status"] == "stopped" else None
    return detail if stopped_why(detail) is not None else None  # type: ignore[return-value]


def _row_to_monitor(row: asyncpg.Record) -> Monitor:
    return Monitor(
        id=row["id"],
        pattern_id=row["pattern_id"],
        owner_id=row["owner_id"],
        status=row["status"],
        status_detail=_detail(row),
        stopped_why=stopped_why(_detail(row)),
        created_at=row["created_at"],
        dataset_id=row["dataset_id"],
        every=row["every"],
        hour=row["hour"],
        weekday=row["weekday"],
    )


_SELECT = (
    "SELECT id, pattern_id, owner_id, status, status_detail, created_at, dataset_id, every, hour, "
    "weekday FROM monitors"
)


class MonitorStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> MonitorStore:
        # `min_size`/`max_size` — `hotlists.py::HotlistStore.connect`'s own comment has the full
        # reasoning (the Stage 6c connection-ceiling finding).
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
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
            id=new_id(),
            pattern_id=pattern_id,
            owner_id=principal.id,
            created_at=datetime.now(UTC),
            dataset_id=made_in(principal),
        )
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO monitors (id, pattern_id, owner_id, status, created_at, dataset_id) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                monitor.id,
                monitor.pattern_id,
                monitor.owner_id,
                monitor.status,
                monitor.created_at,
                monitor.dataset_id,
            )
        return monitor

    async def get_authorized(self, monitor_id: str, principal: Principal) -> Monitor:
        reach, extra = reach_clause(principal, 3)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, pattern_id, owner_id, status, status_detail, created_at, dataset_id, "
                "every, hour, weekday "
                f"FROM monitors WHERE id = $1 AND owner_id = $2{reach}",
                monitor_id,
                principal.id,
                *extra,
            )
        if row is None:
            raise MonitorNotFoundError(monitor_id)
        return _row_to_monitor(row)

    async def list_authorized(self, principal: Principal) -> list[Monitor]:
        reach, extra = reach_clause(principal, 2)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, pattern_id, owner_id, status, status_detail, created_at, dataset_id, "
                "every, hour, weekday "
                f"FROM monitors WHERE owner_id = $1{reach} ORDER BY created_at DESC",
                principal.id,
                *extra,
            )
        return [_row_to_monitor(row) for row in rows]

    async def list_all_active(self) -> list[Monitor]:
        """Not principal-scoped — the evaluator's own system-level population read, the identical
        reasoning `HotlistStore.list_all_active`'s own docstring gives; never exposed through a
        route."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(_SELECT)
        return [_row_to_monitor(row) for row in rows]

    async def set_status(
        self, monitor_id: str, status: WatchStatus, detail: StoppedReason | None = None
    ) -> None:
        """`HotlistStore.set_status`'s own twin, identical reasoning — called only by the
        evaluator, written on every evaluation attempt so `status` reflects the most recent one."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE monitors SET status = $2, status_detail = CASE WHEN $2 = 'stopped' "
                "THEN $3 END WHERE id = $1",
                monitor_id,
                status,
                detail,
            )


    async def set_schedule(
        self, monitor_id: str, principal: Principal, schedule: MonitorScheduleInput
    ) -> Monitor:
        """ADR-146 decision 4: the watch's own schedule, set by its owner alone (in the query)."""
        reach, extra = reach_clause(principal, 6)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE monitors SET every = $3, hour = $4, weekday = $5 "
                f"WHERE id = $1 AND owner_id = $2{reach} "
                "RETURNING id, pattern_id, owner_id, status, status_detail, created_at, "
                "dataset_id, every, hour, weekday",
                monitor_id,
                principal.id,
                schedule.every,
                schedule.hour,
                schedule.weekday,
                *extra,
            )
        if row is None:
            raise MonitorNotFoundError(monitor_id)
        return _row_to_monitor(row)

    async def last_slot(self, monitor_id: str) -> datetime | None:
        async with self._pool.acquire() as conn:
            found = await conn.fetchval("SELECT last_slot FROM monitors WHERE id = $1", monitor_id)
        return found if isinstance(found, datetime) else None

    async def record_slot(self, monitor_id: str, slot: datetime) -> None:
        """The slot judged: the next tick looks for slots after it."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE monitors SET last_slot = $2 WHERE id = $1 "
                "AND (last_slot IS NULL OR last_slot < $2)",
                monitor_id,
                slot,
            )


__all__ = ["MonitorNotFoundError", "MonitorStore"]
