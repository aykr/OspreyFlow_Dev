"""Investigation metadata — `spec/03_CONDUIT_MIDDLEWARE.md` §3.1.

Neither the graph itself (the Vault's job) nor ephemeral working-set state
(Valkey's job, `working_set/store.py`) — an investigation record is small,
relational, control-plane metadata: who created it, when, and (for a
branch) what it was forked from. Postgres already exists in this phase for
the audit stream, so investigation metadata lives in the same database
rather than inventing a fourth store for a handful of columns.

**`owning_unit` is the investigation-level authorization boundary** —
the divergence-review fix: every investigation-scoped route in `app.py`
now checks `principal.org_unit == investigation.owning_unit` before doing
anything else. Deliberately shaped like `Handling.owning_unit`
(`01_DOMAIN_MODEL.md` §2.2) rather than a new concept, and deliberately
*not* `clearance`-gated — a shared investigation is exactly the case this
column exists to allow, with node/edge-level visibility still governed
separately by the handling filter on every read
(`working_set/service.py`'s `_project`).
"""

from __future__ import annotations

from datetime import UTC, datetime

import asyncpg
from pydantic import BaseModel

from conduit_common.identity import new_id
from schemas.domain import Principal

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS investigations (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    created_by TEXT NOT NULL,
    owning_unit TEXT NOT NULL,
    branched_from TEXT REFERENCES investigations (id)
);
"""


class Investigation(BaseModel):
    id: str
    created_at: datetime
    created_by: str
    owning_unit: str
    branched_from: str | None = None


class InvestigationNotFoundError(Exception):
    """Also raised — deliberately, not a 403 — when the investigation
    exists but `principal.org_unit` does not match `owning_unit`: the
    existence-leak discipline `00_ARCHITECTURE.md` §5 already applies at
    node/edge level extends to the investigation id itself. An
    unauthorised principal must not be able to tell "wrong unit" apart
    from "no such investigation" from outside."""


class InvestigationStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> InvestigationStore:
        # `min_size`/`max_size` — `hotlists.py::HotlistStore.connect`'s own comment has the full
        # Stage 6c connection-ceiling reasoning. Sized larger than the control-plane stores: every
        # investigation-scoped route depends on this one via `AuthorizedInvestigationDep`.
        pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=8)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def create(
        self, principal: Principal, *, branched_from: str | None = None
    ) -> Investigation:
        """`owning_unit` is always the *acting* principal's own `org_unit`
        — for a branch, that is the branching principal, never inherited
        from the source investigation (`app.py`'s `branch_investigation`
        already authorised the branching principal against the source
        before calling this)."""
        investigation = Investigation(
            id=new_id(),
            created_at=datetime.now(UTC),
            created_by=principal.id,
            owning_unit=principal.org_unit,
            branched_from=branched_from,
        )
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO investigations "
                "(id, created_at, created_by, owning_unit, branched_from) "
                "VALUES ($1, $2, $3, $4, $5)",
                investigation.id,
                investigation.created_at,
                investigation.created_by,
                investigation.owning_unit,
                investigation.branched_from,
            )
        return investigation

    async def get(self, investigation_id: str) -> Investigation:
        """No authorization check here — this is the raw record lookup.
        `app.py`'s `get_authorized_investigation` dependency is what wraps
        this with the `owning_unit` check every route actually uses."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, created_at, created_by, owning_unit, branched_from "
                "FROM investigations WHERE id = $1",
                investigation_id,
            )
        if row is None:
            raise InvestigationNotFoundError(investigation_id)
        return Investigation(**dict(row))

    async def get_authorized(self, investigation_id: str, principal: Principal) -> Investigation:
        """The one method every route should call. `owning_unit` filtered in the query itself,
        not after fetch — `06_DECISIONS.md` ADR-041's own fix, the same shape `review.py`'s
        `get_authorized`/`get_document_text` and `pattern_store.py`'s `get_authorized` already
        use. A hazard, not a leak, before this fix: the Python-side check below it replaced
        correctly rejected a mismatched principal (checked directly — no caller of `get()`
        elsewhere bypasses it), it just pulled the full row into process memory first. Both
        failures still collapse to the same `InvestigationNotFoundError` (§ existence-leak
        discipline above)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, created_at, created_by, owning_unit, branched_from "
                "FROM investigations WHERE id = $1 AND owning_unit = $2",
                investigation_id,
                principal.org_unit,
            )
        if row is None:
            raise InvestigationNotFoundError(investigation_id)
        return Investigation(**dict(row))
