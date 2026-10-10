"""Ultimate beneficial ownership, traced for the reader (`06_DECISIONS.md` ADR-109 phase C).

**The structure is read as the reader (rule 3).** Owners are walked up from the target one layer
at a time over `BENEFICIAL_OWNER_OF` and `CONTROLS` (FIBO, ADR-108 Amendment 4) with
`GraphPort.expand`, the access step in every traversal: a party or link the reader may not see is
not in the structure, and the trace is exactly what it would be were they absent. **Nothing is
traced in part (rule 2):** a structure with owners beyond `max_depth` layers, or more than
`MAX_PARTIES` parties, is refused in words (`OwnershipTooComplex`) rather than cut off. The maths is
`ComputePort.ownership` (ruling 9's defaults: 25%, a missing percentage unknown, control not a
share, circles traced once and flagged). **A trace is a view, never written** (ruling 9): no
conclusion it draws reaches the graph.
"""

from __future__ import annotations

from ports.compute import ComputePort
from ports.graph import GraphPort
from schemas.compute import (
    OwnershipLink,
    OwnershipRequest,
    OwnershipTooComplex,
    OwnershipView,
    StructureNode,
)
from schemas.domain import Edge, ExpandRequest, Node, Principal

from .suppression import NodeNotVisibleError

OWNERSHIP_EDGE_TYPES = ["BENEFICIAL_OWNER_OF", "CONTROLS"]

#: The most parties one trace reads. A guess, not a measurement: corporate structures in AML work
#: run to dozens of parties, rarely hundreds.
MAX_PARTIES = 500


def _percent(edge: Edge) -> float | None:
    value = edge.properties.get("percent")
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if 0 <= number <= 100 else None


async def read_structure(
    graph: GraphPort, target_id: str, reader: Principal, *, max_depth: int
) -> tuple[dict[str, Node], dict[str, Edge]]:
    target = await graph.get_node(target_id, reader)
    if target is None:
        raise NodeNotVisibleError(target_id)
    nodes: dict[str, Node] = {target.id: target}
    edges: dict[str, Edge] = {}
    frontier = [target.id]
    # One layer more than the trace may use, so that a chain longer than `max_depth` reaches
    # `ComputePort.ownership`, which refuses it whole — read only `max_depth` layers and a deeper
    # owner would be silently missing (rule 2).
    for _ in range(max_depth + 1):
        if not frontier:
            break
        found = await graph.expand(
            ExpandRequest(
                node_ids=frontier, depth=1, edge_types=OWNERSHIP_EDGE_TYPES, direction="in"
            ),
            reader,
        )
        fresh_edges = [e for e in found.edges if e.id not in edges and e.target in frontier]
        for edge in fresh_edges:
            edges[edge.id] = edge
        frontier = []
        for node in found.nodes:
            if node.id not in nodes:
                nodes[node.id] = node
                frontier.append(node.id)
        if len(nodes) > MAX_PARTIES:
            raise OwnershipTooComplex(
                f"more than {MAX_PARTIES} parties own or control this entity; the structure is "
                "not traced in part"
            )
    return nodes, edges


async def trace_for(
    graph: GraphPort,
    compute: ComputePort,
    target_id: str,
    reader: Principal,
    *,
    threshold: float = 25.0,
    max_depth: int = 10,
) -> OwnershipView:
    nodes, edges = await read_structure(graph, target_id, reader, max_depth=max_depth)
    request = OwnershipRequest(
        target=target_id,
        nodes=[StructureNode(id=n.id, type=n.type) for n in nodes.values()],
        links=[
            OwnershipLink(
                id=e.id,
                source=e.source,
                target=e.target,
                kind="controls" if e.type == "CONTROLS" else "owns",
                percent=None if e.type == "CONTROLS" else _percent(e),
            )
            for e in edges.values()
            if e.source in nodes and e.target in nodes
        ],
        threshold=threshold,
        max_depth=max_depth,
    )
    trace = await compute.ownership(request)
    return OwnershipView(trace=trace, nodes=list(nodes.values()), edges=list(edges.values()))


__all__ = ["MAX_PARTIES", "OWNERSHIP_EDGE_TYPES", "read_structure", "trace_for"]
