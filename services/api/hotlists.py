"""`HotlistStore` — `06_DECISIONS.md` ADR-038, Phase 7 Stage 6b. Same shape `sites.py`/
`investigations.py`/`pattern_store.py`/`alerts.py` already are: small, relational, control-plane
metadata, Postgres-backed. Owner-only, no sharing — `02_GLASS_FRONTEND.md` §3.3 names an owner and
a review date, nothing about a second viewer, and ADR-038's own "what a second analyst observes of
a hotlist they do not own" is settled as "nothing: no count, no ordering, no readable membership."

**`owner_id` filtered in the query itself, from the start** (`06_DECISIONS.md` ADR-041) —
`scripts/authorized_query_check.py` is what actually proves this, not this docstring's own claim
of it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import asyncpg

from conduit_common.identity import new_id
from schemas.domain import Hotlist, Principal, WatchStatus

#: `ADD COLUMN IF NOT EXISTS` — `alerts.py`'s own `_BOOTSTRAP_SQL` docstring has the full reasoning:
#: this codebase has no migration tooling, and `CREATE TABLE IF NOT EXISTS` alone is a no-op
#: against the persistent database Stage 6b's own bootstrap already ran on.
_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS hotlists (
    id TEXT PRIMARY KEY,
    identifier TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    review_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE hotlists ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
CREATE INDEX IF NOT EXISTS hotlists_owner_id_idx ON hotlists (owner_id);
CREATE INDEX IF NOT EXISTS hotlists_identifier_idx ON hotlists (identifier);
"""


class HotlistNotFoundError(Exception):
    """Also raised when the hotlist exists but `owner_id` does not match the calling principal —
    the same existence-leak discipline every other store in this codebase already establishes."""


def _row_to_hotlist(row: asyncpg.Record) -> Hotlist:
    return Hotlist(
        id=row["id"],
        identifier=row["identifier"],
        owner_id=row["owner_id"],
        review_date=row["review_date"],
        status=row["status"],
        created_at=row["created_at"],
    )


class HotlistStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> HotlistStore:
        # `min_size`/`max_size`, not `asyncpg.create_pool`'s own `min_size=10` default — Stage 6c
        # found the real cost of ten-plus stores in this file each defaulting to a ten-connection
        # floor: `app.py`'s own lifespan alone was already requesting ~100 connections against
        # Postgres's own `max_connections=100`, and adding this store (plus `monitors.py`/
        # `alerts.py`, this stage's other two) pushed a real `TestClient` lifespan over the ceiling,
        # reproduced directly as `asyncpg.exceptions.TooManyConnectionsError`. A small, low-traffic
        # control-plane store (a handful of hotlists per analyst) needs nowhere near ten idle
        # connections; bounded here rather than fixed by raising Postgres's own ceiling, which
        # would paper over every other store's identical unbounded default rather than this one's
        # own actual load.
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def create(
        self, principal: Principal, *, identifier: str, review_date: date
    ) -> Hotlist:
        hotlist = Hotlist(
            id=new_id(),
            identifier=identifier,
            owner_id=principal.id,
            review_date=review_date,
            created_at=datetime.now(UTC),
        )
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO hotlists (id, identifier, owner_id, review_date, status, created_at) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                hotlist.id,
                hotlist.identifier,
                hotlist.owner_id,
                hotlist.review_date,
                hotlist.status,
                hotlist.created_at,
            )
        return hotlist

    async def get_authorized(self, hotlist_id: str, principal: Principal) -> Hotlist:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, identifier, owner_id, review_date, status, created_at "
                "FROM hotlists WHERE id = $1 AND owner_id = $2",
                hotlist_id,
                principal.id,
            )
        if row is None:
            raise HotlistNotFoundError(hotlist_id)
        return _row_to_hotlist(row)

    async def list_authorized(self, principal: Principal) -> list[Hotlist]:
        """Never another principal's hotlists — `06_DECISIONS.md` ADR-038's own settled answer to
        "what does a second analyst observe of a hotlist they do not own": nothing."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, identifier, owner_id, review_date, status, created_at "
                "FROM hotlists WHERE owner_id = $1 ORDER BY created_at DESC",
                principal.id,
            )
        return [_row_to_hotlist(row) for row in rows]

    async def set_status(self, hotlist_id: str, status: WatchStatus) -> None:
        """Called only by the evaluator (`services/api/evaluation.py`), never a route — Stage 6c's
        own answer to ADR-036's "surfaced as stopped somewhere the analyst... can see it": written
        on every evaluation attempt that reaches this hotlist, not only on the first skip, so
        `status` reflects the *most recent* attempt (`active` again the next time a principal is
        resolved), not a one-way, permanently-tripped flag. No principal parameter and no
        `WHERE owner_id = ...` — the evaluator has no principal to filter by at this call site by
        construction (this is precisely the caller resolving one *failed*), and the row's own id is
        already the only thing identifying it; nothing here is a read a principal could leak
        through."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE hotlists SET status = $2 WHERE id = $1", hotlist_id, status
            )

    async def list_all_active(self) -> list[Hotlist]:
        """**Not principal-scoped — deliberately, and the one method on this store that isn't.**
        The evaluator (`services/api/evaluation.py`) is a system-level process with no principal
        of its own; it needs every hotlist that exists to decide which owner(s) a given
        change-stream entry might concern, the same "the trigger needs the whole population, not
        a caller-scoped view of it" shape `GraphPort.list_nodes` was built for in
        `06_DECISIONS.md` ADR-025. Never exposed through a route — `app.py` has no handler
        calling this, only the evaluator does — so this is not a second, unauthenticated read
        path for an analyst, only for the one system-level caller ADR-025's own precedent already
        established needs an unscoped population."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, identifier, owner_id, review_date, status, created_at FROM hotlists"
            )
        return [_row_to_hotlist(row) for row in rows]


__all__ = ["HotlistNotFoundError", "HotlistStore"]
