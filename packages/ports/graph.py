"""`GraphPort` — `docs/00_ARCHITECTURE.md` §2.1.

Persistent property graph: write, traverse, subgraph extraction, schema
management. Wire protocol is Gremlin/TinkerPop 3.8 over WebSocket (GraphBinary);
Gremlin never leaves the Vault — nothing above this port may see it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from schemas._phase0_placeholders import (
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
    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: TxId) -> list[NodeId]: ...
    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: TxId) -> list[EdgeId]: ...
    async def get_node(self, node_id: NodeId, principal: Principal) -> Node | None: ...
    async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph: ...
    async def paths(self, req: PathRequest, principal: Principal) -> list[Path]: ...
    async def match(self, pattern: PatternQuery, principal: Principal) -> Subgraph: ...
    async def neighbourhood_stats(self, node_id: NodeId) -> NeighbourhoodStats: ...
    async def apply_schema(self, schema: OntologySchema) -> SchemaReport: ...
