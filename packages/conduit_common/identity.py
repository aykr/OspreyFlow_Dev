"""`NodeId`/`EdgeId` and `AuditStub.created_at` assignment — Conduit-owned,
never a source system's or an adapter's (`01_DOMAIN_MODEL.md` §2,
`07_BUILD_PLAN.md` Phase 3's carry-forward from Phase 1). Every caller that
builds a `NodeWrite`/`EdgeWrite` — `services/api`'s Working-Set Service and
`services/ingest`'s load path alike — mints through here, so there is one
place that generates identifiers rather than each adapter inventing its own.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from schemas.domain import EdgeId, NodeId


def new_id() -> str:
    """A bare ULID, for identifiers this module has no more specific
    helper for — an investigation id (`services/api/investigations.py`),
    a job id, and the like. `new_node_id`/`new_edge_id` exist alongside it
    rather than everything collapsing to this one function, since a
    `NodeId`/`EdgeId`-typed return catches "passed a node id where an edge
    id belongs" at the type checker instead of at runtime."""
    return str(ULID())


def new_node_id() -> NodeId:
    return new_id()


def new_edge_id() -> EdgeId:
    return new_id()


def now_utc() -> datetime:
    return datetime.now(UTC)
