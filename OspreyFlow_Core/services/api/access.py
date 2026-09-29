"""The "narrow a candidate node-id set to what `principal` can actually see" pattern —
`services/api/working_set/service.py`'s `set_resolution_threshold` and `explain_cluster` each
inlined this independently (`explain_cluster`'s own docstring: "the same pattern as
`set_resolution_threshold`" — the same *pattern*, not the same *function*), and Phase 6a Stage 4's
own Dossier assembly needed the same narrowing a third time — fake-based tests already show three
independent instances of one repeated
defect shape in this codebase; a third independent copy of *this* pattern would have been the same
kind of finding again, just about duplication rather than a fake — closed here instead by
extracting one function and retrofitting both existing call sites to it.

`GraphPort.expand`'s own access-filtered seed query (`render_seed_nodes_gremlin`) returns exactly
the principal-visible subset of any seed list, including a seed with no matching edges at all —
`test_projection_access_control.py` proves this against the real adapter. That single property is
what every caller of this module actually depends on; nothing here does its own filtering.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ports.graph import GraphPort
from schemas.domain import Edge, ExpandRequest, Node, NodeId, Principal


@dataclass(frozen=True)
class VisibilityResult:
    #: Only the ids from the caller's own `node_ids` that came back visible — never a neighbour
    #: `expand` reached one hop out that was not itself a requested id.
    nodes: dict[NodeId, Node] = field(default_factory=dict)
    #: The same `expand` call's own edges, filtered by `edge_types` if given and narrowed to those
    #: whose source and target are both in `nodes` above — never an edge naming a neighbour this
    #: result's own `nodes` excluded (`tests/services/api/test_access.py`). Callers who need no
    #: edges (a plain visibility check) pass none and pay no extra traversal cost for them.
    edges: list[Edge] = field(default_factory=list)


async def narrow_to_visible(
    graph: GraphPort,
    node_ids: Sequence[NodeId],
    principal: Principal,
    *,
    edge_types: list[str] | None = None,
) -> VisibilityResult:
    """One `expand` call, not a second fetch bolted on afterwards — a caller that also needs
    edges (`set_resolution_threshold`'s own `SAME_AS`/`NOT_SAME_AS` traversal) gets them from the
    same round trip its own visibility check already needed, rather than two."""
    if not node_ids:
        return VisibilityResult()
    subgraph = await graph.expand(
        ExpandRequest(node_ids=list(node_ids), depth=1, edge_types=edge_types or []),
        principal,
    )
    requested = set(node_ids)
    nodes = {n.id: n for n in subgraph.nodes if n.id in requested}
    # `expand(depth=1)` returns edges reaching one hop past `requested` — an edge whose other
    # endpoint is a *visible* neighbour, not itself a requested id, can survive the node filter
    # above while referencing a node this result never includes (no classification is involved: a
    # hidden neighbour is already excluded by `expand` itself, before this line ever runs — checked
    # directly, `tests/services/api/test_access.py`'s own docstring has the full distinction). A
    # caller that feeds these edges onward (e.g. ComputePort, Phase 7 Stage 3) must never be handed
    # an edge naming a node it wasn't also given.
    edges = [e for e in subgraph.edges if e.source in nodes and e.target in nodes]
    return VisibilityResult(nodes=nodes, edges=edges)
