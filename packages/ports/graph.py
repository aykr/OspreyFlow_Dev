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
    async def get_node(self, node_id: NodeId, principal: Principal) -> Node | None: ...
    async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph: ...
    async def paths(self, req: PathRequest, principal: Principal) -> list[Path]: ...
    async def match(self, pattern: PatternQuery, principal: Principal) -> Subgraph: ...

    async def neighbourhood_stats(
        self, node_id: NodeId, principal: Principal
    ) -> NeighbourhoodStats: ...

    async def apply_schema(self, schema: OntologySchema) -> SchemaReport: ...
    async def revert_schema(self, to_version: int) -> SchemaReport: ...
