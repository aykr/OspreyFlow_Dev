"""`GraphPort` — `docs/00_ARCHITECTURE.md` §2.1.

Persistent property graph: write, traverse, subgraph extraction, schema
management. Gremlin/TinkerPop 3.8 is the query language; the transport is
each adapter's own business (WebSocket/GraphBinary or an HTTP command
endpoint are both conformant). Gremlin never leaves the Vault — nothing
above this port may see it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from schemas.domain import (
    EdgeId,
    EdgeWrite,
    ExpandRequest,
    NeighbourhoodStats,
    Node,
    NodeId,
    NodeWrite,
    OntologySchema,
    Path,
    PathRequest,
    PatternQuery,
    Principal,
    SchemaReport,
    Subgraph,
    TxId,
)


class GraphPort(Protocol):
    #: Query dialects this adapter can render — `{"gremlin"}`,
    #: `{"gremlin", "opencypher"}`, `{"gql"}` — ADR-003's amendment. The
    #: Conduit selects a builder backend from what the configured adapter
    #: advertises; the conformance suite is parametrised by dialect.
    dialects: frozenset[str]

    # Transaction lifecycle. `upsert_nodes`/`upsert_edges` take a `TxId`
    # produced by `begin_transaction`; nothing is durable until
    # `commit_transaction`, and `rollback_transaction` discards every write
    # made under it — the conformance suite's transaction-rollback case
    # exercises exactly this.
    async def begin_transaction(self) -> TxId: ...
    async def commit_transaction(self, tx: TxId) -> None: ...
    async def rollback_transaction(self, tx: TxId) -> None: ...

    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: TxId) -> list[NodeId]: ...
    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: TxId) -> list[EdgeId]: ...

    async def get_node(
        self, node_id: NodeId, principal: Principal, *, include_superseded: bool = False
    ) -> Node | None:
        """`include_superseded=True` is the one way to retrieve a node
        `supersede_node` has replaced — otherwise excluded from every read
        by default (`01_DOMAIN_MODEL.md` §2.4). It only lifts *that*
        exclusion: classification and `handling_code` still apply
        underneath, so a principal who could not see the record cannot see
        its history either."""
        ...

    async def supersede_node(self, node_id: NodeId, replacement: NodeWrite, tx: TxId) -> NodeId:
        """`01_DOMAIN_MODEL.md` §2.4: "Nodes are versioned, not
        overwritten. A correction writes a new revision and points the old
        one forward." Writes `replacement` as a new node at
        `revision = node_id's current revision + 1`, sets `node_id`'s own
        `AuditStub.superseded_by` to the new node's id, and returns that
        new id. The old node is never deleted or edited otherwise — every
        prior revision, and the full `superseded_by` chain between them,
        remains individually retrievable via `get_node(...,
        include_superseded=True)`. Phase 6's retraction and Phase 8's
        judgement-review loop are the callers; the capability lands here,
        against the one adapter that exists, so both phases build on a
        conformance-tested primitive rather than each inventing their
        own. Repoints every edge incident to `node_id` onto the new node
        (cloned, not moved — an edge's endpoints are fixed at creation in
        every TinkerPop-family store), so a correction does not silently
        disconnect the corrected node from its own network. The
        superseded originals of those edges are excluded from ordinary
        reads the same way `node_id` itself now is."""
        ...

    async def supersede_edge(self, edge_id: EdgeId, replacement: EdgeWrite, tx: TxId) -> EdgeId:
        """The same operation as `supersede_node`, for an edge. `§3`:
        an edge carries `AuditStub` too, and `01_DOMAIN_MODEL.md` §5's
        `Judgement.supporting`/`contradicting` can name an `EdgeId`
        directly — a correction to the evidence itself must leave that
        reference resolvable to *something*, the same reason a corrected
        `Person` cannot just vanish. Unlike `supersede_node`, there is
        nothing to repoint: nothing in this domain model references an
        edge by id except an assessment's evidence list, which is a
        historical citation, not a live graph reference — it is expected
        to follow the `superseded_by` pointer, not be silently rewritten."""
        ...

    async def find_node(
        self, entity_type: str, identifier_field: str, value: str, principal: Principal
    ) -> Node | None:
        """`01_DOMAIN_MODEL.md` §7's `match_on`/`on_match` needs this: the
        recipe engine's `on_match: reference` looks an entity up by its
        declared identifier before deciding whether to create a new node,
        and there is no other way to express that query — `match()`'s
        `PatternQuery` has no property-value predicate, only an entity
        type. Added in Phase 2, without raising the gap first, the same way
        Phase 1 added transactions and schema management beyond
        `00_ARCHITECTURE.md` §2.1's illustrative snippet."""
        ...
    async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph: ...
    async def paths(self, req: PathRequest, principal: Principal) -> list[Path]: ...
    async def match(self, pattern: PatternQuery, principal: Principal) -> Subgraph: ...

    async def neighbourhood_stats(
        self, node_id: NodeId, principal: Principal
    ) -> NeighbourhoodStats: ...

    async def apply_schema(self, schema: OntologySchema) -> SchemaReport: ...
    async def revert_schema(self, to_version: int) -> SchemaReport: ...

    async def revert_elements(
        self, node_ids: Sequence[NodeId], edge_ids: Sequence[EdgeId], tx: TxId
    ) -> None:
        """Marks existing elements reverted (`AuditStub.reverted`,
        `01_DOMAIN_MODEL.md` §2.4) — `services/ingest`'s `revert_load` is
        the only caller. A reverted element is invisible to every read
        method afterwards, any principal, the same way a hidden record is
        invisible to an unauthorised one; it is never actually deleted, so
        the audit trail stays intact. No `principal` argument, matching
        `upsert_nodes`/`upsert_edges` — this is a backend write attributed
        by the caller's own audit trail (the load ledger), not a
        principal-scoped read."""
        ...
