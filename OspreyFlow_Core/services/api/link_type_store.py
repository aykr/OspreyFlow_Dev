"""Where analyst-proposed relationship types are kept (ADR-090): the control-plane store, never
the shared ontology and never the graph. One row per proposal, and one row for the overlay's
revision, which rises at every promotion and retirement.

**Who sees a proposal.** An administrator reads and acts on the proposals of their own unit only
(`*_authorized`: `owning_unit = principal.org_unit` in the query, ADR-090 decision 5); one from
another unit is not found, exactly as a missing one. The reads with no principal are the Conduit's
own: composing the ontology at start-up and after a decision, and finding what a case may use,
whose callers have already checked the case.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import asyncpg

from schemas.domain import Principal

from .link_types import LinkTypeProposal, ProposalNotFoundError, ProposalStatus

__all__ = ["LinkTypeProposalStore", "ProposalNotFoundError"]

_SQL = """
CREATE TABLE IF NOT EXISTS link_type_proposals (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    label TEXT,
    from_types TEXT[] NOT NULL,
    to_types TEXT[] NOT NULL,
    directed BOOLEAN NOT NULL,
    colour TEXT,
    thickness INTEGER,
    investigation_id TEXT NOT NULL,
    owning_unit TEXT NOT NULL,
    proposed_by TEXT NOT NULL,
    proposed_at TIMESTAMPTZ NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN
        ('pending', 'promoted', 'rejected', 'withdrawn', 'merged', 'retired')),
    decided_by TEXT,
    decided_at TIMESTAMPTZ,
    decision_reason TEXT,
    basis TEXT CHECK (basis IS NULL OR basis IN ('direct', 'probabilistic')),
    promoted_name TEXT,
    direct_since TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS link_type_proposals_case_idx
    ON link_type_proposals (investigation_id, status);
CREATE INDEX IF NOT EXISTS link_type_proposals_name_idx ON link_type_proposals (name, status);
CREATE TABLE IF NOT EXISTS link_type_overlay (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    revision INTEGER NOT NULL
);
INSERT INTO link_type_overlay (singleton, revision) VALUES (TRUE, 0) ON CONFLICT DO NOTHING;
-- ADR-099 Amendment 3: the dataset a proposal belongs to; none for one made before it.
ALTER TABLE link_type_proposals ADD COLUMN IF NOT EXISTS dataset_id TEXT;
CREATE INDEX IF NOT EXISTS link_type_proposals_dataset_idx
    ON link_type_proposals (dataset_id, status);
"""

_COLUMNS = (
    "id, name, label, from_types, to_types, directed, colour, thickness, investigation_id, "
    "owning_unit, proposed_by, proposed_at, reason, status, decided_by, decided_at, "
    "decision_reason, basis, promoted_name, direct_since, dataset_id"
)


def _row(record: asyncpg.Record) -> LinkTypeProposal:
    data = dict(record)
    data["from_types"] = list(data["from_types"])
    data["to_types"] = list(data["to_types"])
    return LinkTypeProposal.model_validate(data)


class LinkTypeProposalStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> LinkTypeProposalStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(90090)")
            await conn.execute(_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def create(self, proposal: LinkTypeProposal) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO link_type_proposals ({_COLUMNS}) VALUES "
                "($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21)",
                *_values(proposal),
            )

    async def all(self) -> list[LinkTypeProposal]:
        """Every proposal, for composing the ontology in force (the Conduit's own read)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM link_type_proposals ORDER BY proposed_at, id"
            )
        return [_row(r) for r in rows]

    async def pending_for_cases(self, investigation_ids: Sequence[str]) -> list[LinkTypeProposal]:
        """Pending proposals made in these cases (a case and the cases it was branched from)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM link_type_proposals "
                "WHERE investigation_id = ANY($1::text[]) AND status = 'pending' "
                "ORDER BY proposed_at, id",
                list(investigation_ids),
            )
        return [_row(r) for r in rows]

    async def pending_for_datasets(self, dataset_ids: Sequence[str]) -> list[LinkTypeProposal]:
        """ADR-099 Amendment 3: the pending proposals of these datasets."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM link_type_proposals "
                "WHERE dataset_id = ANY($1::text[]) AND status = 'pending' "
                "ORDER BY proposed_at, id",
                list(dataset_ids),
            )
        return [_row(r) for r in rows]

    async def pending_named(self, names: Sequence[str]) -> list[LinkTypeProposal]:
        """Pending proposals of these names, for a case whose view holds one of their links."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM link_type_proposals "
                "WHERE name = ANY($1::text[]) AND status = 'pending' ORDER BY proposed_at, id",
                list(names),
            )
        return [_row(r) for r in rows]

    async def get(self, proposal_id: str) -> LinkTypeProposal:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM link_type_proposals WHERE id = $1", proposal_id
            )
        if row is None:
            raise ProposalNotFoundError(proposal_id)
        return _row(row)

    async def get_authorized(self, proposal_id: str, principal: Principal) -> LinkTypeProposal:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, name, label, from_types, to_types, directed, colour, thickness, "
                "investigation_id, owning_unit, proposed_by, proposed_at, reason, status, "
                "decided_by, decided_at, decision_reason, basis, promoted_name, direct_since, "
                "dataset_id "
                "FROM link_type_proposals WHERE id = $1 AND owning_unit = $2",
                proposal_id,
                principal.org_unit,
            )
        if row is None:
            raise ProposalNotFoundError(proposal_id)
        return _row(row)

    async def list_authorized(self, principal: Principal) -> list[LinkTypeProposal]:
        """The proposals of the administrator's own unit, newest first."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, name, label, from_types, to_types, directed, colour, thickness, "
                "investigation_id, owning_unit, proposed_by, proposed_at, reason, status, "
                "decided_by, decided_at, decision_reason, basis, promoted_name, direct_since, "
                "dataset_id "
                "FROM link_type_proposals WHERE owning_unit = $1 ORDER BY proposed_at DESC, id",
                principal.org_unit,
            )
        return [_row(r) for r in rows]

    async def decide(
        self,
        proposal_id: str,
        *,
        status: ProposalStatus,
        by: str,
        at: datetime,
        reason: str,
        basis: str | None = None,
        promoted_name: str | None = None,
        direct_since: datetime | None = None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE link_type_proposals SET status = $2, decided_by = $3, decided_at = $4, "
                "decision_reason = $5, basis = COALESCE($6, basis), "
                "promoted_name = COALESCE($7, promoted_name), "
                "direct_since = COALESCE($8, direct_since) WHERE id = $1",
                proposal_id,
                status.value,
                by,
                at,
                reason,
                basis,
                promoted_name,
                direct_since,
            )

    async def bump_revision(self) -> int:
        async with self._pool.acquire() as conn:
            value = await conn.fetchval(
                "UPDATE link_type_overlay SET revision = revision + 1 RETURNING revision"
            )
        return int(value)

    async def revision(self) -> int:
        async with self._pool.acquire() as conn:
            return int(await conn.fetchval("SELECT revision FROM link_type_overlay"))


def _values(p: LinkTypeProposal) -> tuple[object, ...]:
    return (
        p.id, p.name, p.label, p.from_types, p.to_types, p.directed, p.colour, p.thickness,
        p.investigation_id, p.owning_unit, p.proposed_by, p.proposed_at, p.reason, p.status.value,
        p.decided_by, p.decided_at, p.decision_reason, p.basis, p.promoted_name, p.direct_since,
        p.dataset_id,
    )  # fmt: skip
