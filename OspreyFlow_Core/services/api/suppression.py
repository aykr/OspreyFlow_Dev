"""Marking a node for suppression — owner ruling R7, 27 September 2026, **TENTATIVE**.

The owner is revisiting this after their own usability walkthrough; `06_DECISIONS.md` ADR-046's
addendum carries the ruling in that state, and this module is written to be easy to change.

**Retraction becomes two steps, and this is the first.** R7, verbatim: "In the Glass an analyst
marks a node for suppression — immediate, reversible, shown as a marker on the node and in the
inspector. The suppression takes effect only when its evidence is supplied through the Ingest
Studio: a retraction record ingested and mapped to the node like any other source, so every
suppression is evidence-backed and auditable."

**Why a mark is not a graph write.** A mark is an *intent*, reversible in a click, and the graph
is append-only by design (`01_DOMAIN_MODEL.md` §2.4: nodes are versioned, never overwritten). If
marking wrote to the graph, every mark and un-mark would mint a revision, and the node's own
history — the thing supersession exists to keep honest — would fill with records of an analyst
changing their mind. So marks live here, in their own table, and the graph is touched exactly once:
when step two supplies the evidence and the suppression actually takes effect.

**What this is not.** Not a hiding mechanism: a marked node is still returned by every read, still
exportable, still cited normally. The mark is a *signal to the analyst*, rendered on the node and
in the inspector, that someone has proposed suppressing it. Nothing about access control changes —
`CLAUDE.md` rule 3's filter is unaffected and this module never touches it.

**Access control (`CLAUDE.md` rules 2 and 4).** The same principal rule retraction already uses:
you may mark what you can see. Enforced by asking `GraphPort.get_node` with the caller's own
principal before writing anything — never by filtering a result afterwards — and
`tests/services/api/test_suppression.py` has the refusal case.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import asyncpg

from ports.graph import GraphPort
from schemas.domain import NodeId, Principal

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS suppression_marks (
    node_id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    marked_by TEXT NOT NULL,
    marked_at TIMESTAMPTZ NOT NULL,
    reason TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS suppression_marks_by_investigation
    ON suppression_marks (investigation_id);
"""


class NodeNotVisibleError(PermissionError):
    """Raised rather than returning `False`, and it names nothing about the node.

    A principal who cannot see a node must not learn from this route whether it exists — the same
    existence-leak collapse `get_authorized_investigation` already makes, and the reason the
    message below carries the id the *caller supplied* rather than anything read from the graph.
    """

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        super().__init__(f"{node_id} is not visible to this principal")


@dataclass(frozen=True)
class SuppressionMark:
    node_id: NodeId
    investigation_id: str
    marked_by: str
    marked_at: datetime
    reason: str


class SuppressionMarkStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> SuppressionMarkStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def mark(
        self,
        node_id: NodeId,
        investigation_id: str,
        principal: Principal,
        graph: GraphPort,
        *,
        reason: str,
    ) -> SuppressionMark:
        """**Visibility is checked against the caller's own principal, before the write.** Rule 2:
        never mark first and filter later. Re-marking an already-marked node replaces the reason
        and the author rather than erroring — an analyst correcting their own note is not a
        conflict, and a second mark by a *different* analyst is a real thing that happens and
        should record who holds it now."""
        if await graph.get_node(node_id, principal) is None:
            raise NodeNotVisibleError(node_id)
        record = SuppressionMark(
            node_id=node_id,
            investigation_id=investigation_id,
            marked_by=principal.id,
            marked_at=datetime.now(UTC),
            reason=reason,
        )
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO suppression_marks "
                "(node_id, investigation_id, marked_by, marked_at, reason) "
                "VALUES ($1, $2, $3, $4, $5) "
                "ON CONFLICT (node_id) DO UPDATE SET marked_by = EXCLUDED.marked_by, "
                "marked_at = EXCLUDED.marked_at, reason = EXCLUDED.reason, "
                "investigation_id = EXCLUDED.investigation_id",
                record.node_id,
                record.investigation_id,
                record.marked_by,
                record.marked_at,
                record.reason,
            )
        return record

    async def unmark(self, node_id: NodeId, principal: Principal, graph: GraphPort) -> bool:
        """Reversible, per R7's own word — and the same visibility check, for the same reason: a
        principal who cannot see the node must not be able to probe for a mark on it by watching
        whether this returns `True` or `False`."""
        if await graph.get_node(node_id, principal) is None:
            raise NodeNotVisibleError(node_id)
        async with self._pool.acquire() as conn:
            deleted = await conn.execute(
                "DELETE FROM suppression_marks WHERE node_id = $1", node_id
            )
        # asyncpg returns the command tag, e.g. `DELETE 1` / `DELETE 0`.
        return str(deleted).endswith("1")

    async def marked_among(self, node_ids: list[NodeId]) -> dict[NodeId, SuppressionMark]:
        """The marks on a set of nodes the caller has **already** been shown.

        Deliberately takes no principal: every caller passes ids from a working set that
        `WorkingSetService` has already filtered for that principal, so re-checking here would be
        a second, redundant access decision in a place that does not own one — exactly the
        "filtered afterwards" shape rule 2 warns about, inverted. Callers that have not already
        filtered must not use this.
        """
        if not node_ids:
            return {}
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT node_id, investigation_id, marked_by, marked_at, reason "
                "FROM suppression_marks WHERE node_id = ANY($1)",
                node_ids,
            )
        return {
            row["node_id"]: SuppressionMark(
                node_id=row["node_id"],
                investigation_id=row["investigation_id"],
                marked_by=row["marked_by"],
                marked_at=row["marked_at"],
                reason=row["reason"],
            )
            for row in rows
        }


__all__ = [
    "NodeNotVisibleError",
    "SuppressionMark",
    "SuppressionMarkStore",
]
