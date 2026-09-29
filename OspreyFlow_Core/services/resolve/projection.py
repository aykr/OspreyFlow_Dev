"""The τ threshold projection — `01_DOMAIN_MODEL.md` §4: "At query time the Conduit applies a
resolution threshold τ from the analyst's session and collapses `SAME_AS` components with score
≥ τ into a single displayed entity. Changing τ re-projects the view; it does not touch storage."
Pure with respect to the graph, the same "one pure function over a bounded working set" shape
ADR-007 already established for the Working-Set Service's handling filter — `services/api/
working_set/service.py` is the caller, this module does no `GraphPort`/store I/O itself.

**Collapse, not merge (ADR-006).** Nothing here combines two `Node` objects into one. The output
is a `NodeId -> ClusterId` mapping a caller annotates onto `Node.resolution.cluster_id` — the
nodes themselves, their properties and their provenance are untouched. Whether/how the Glass
renders same-cluster nodes as one visual entity is a rendering question for that tier, the same
way "zoom-dependent clustering... happens in graphology, not the Conduit"
(`02_GLASS_FRONTEND.md`) already draws that line.

**`NOT_SAME_AS` always wins**, at any threshold, regardless of a `SAME_AS` score between the same
pair — `01_DOMAIN_MODEL.md` §4: "a manual split is a `NOT_SAME_AS` edge that the projection
always honours and no future resolution run may override." Excluding split pairs from the
union-find, rather than unioning first and splitting after, is what makes that true even when a
`SAME_AS` edge would otherwise chain two split nodes together through a third.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from schemas.domain import ClusterId, Edge, NodeId

#: The Glass's three labelled detents (`01_DOMAIN_MODEL.md` §4) — `Balanced` is the default a
#: session starts at absent an explicit `PUT /v1/resolution/threshold`.
THRESHOLD_STRICT = 0.99
THRESHOLD_BALANCED = 0.95
THRESHOLD_BROAD = 0.80
DEFAULT_THRESHOLD = THRESHOLD_BALANCED


@dataclass(frozen=True)
class ClusterDelta:
    """`01_DOMAIN_MODEL.md` §4's own example text: "3 entities merged, 1 split, 47 nodes
    affected." — `merged`/`split`/`nodes_affected` are the exact three numbers `DeltaReproject`
    (`services/api/working_set/models.py`) carries as its own summary counts.

    `affected_cluster_ids` is the same `affected` node set's own *new* cluster assignment
    (Phase 6a Stage 2) — bounded by `nodes_affected` and therefore the same order of magnitude a
    full snapshot already allows for, not a new unbounded case. It exists so a client holding the
    working set already can update just the nodes that moved rather than re-sync the whole set (up
    to the 50k cap) to learn a handful of new `cluster_id` values."""

    merged: int
    split: int
    nodes_affected: int
    affected_cluster_ids: dict[NodeId, ClusterId]


def compute_clusters(
    node_ids: Sequence[NodeId],
    same_as_edges: Sequence[Edge],
    not_same_as_edges: Sequence[Edge],
    tau: float,
) -> dict[NodeId, ClusterId]:
    """Union-find over `same_as_edges` with `properties["score"] >= tau`, excluding any pair that
    also has a direct `not_same_as_edges` entry between them. Every input `node_id` gets a
    cluster, including one with no `SAME_AS` edges at all (a singleton cluster of itself) — a
    caller can always look up `result[node_id]` without a membership check first."""
    split_pairs = {frozenset((e.source, e.target)) for e in not_same_as_edges}
    parent: dict[NodeId, NodeId] = {node_id: node_id for node_id in node_ids}

    def find(x: NodeId) -> NodeId:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: NodeId, b: NodeId) -> None:
        root_a, root_b = find(a), find(b)
        if root_a == root_b:
            return
        # Deterministic tie-break so cluster membership never depends on edge iteration order.
        if root_a > root_b:
            root_a, root_b = root_b, root_a
        parent[root_b] = root_a

    for edge in same_as_edges:
        score = edge.properties.get("score")
        if score is None or score < tau:
            continue
        if frozenset((edge.source, edge.target)) in split_pairs:
            continue
        if edge.source in parent and edge.target in parent:
            union(edge.source, edge.target)

    return {node_id: find(node_id) for node_id in node_ids}


def diff_clusters(before: dict[NodeId, ClusterId], after: dict[NodeId, ClusterId]) -> ClusterDelta:
    """Compares two cluster mappings over the *same* node-id set (a caller's job to guarantee —
    `services/api/working_set/service.py` always recomputes `before` and `after` from the same
    source-fidelity node list). "Merged" and "split" count *cluster-membership events*, not
    node-pair events: a three-node cluster collapsing into one when τ drops counts as one merge
    event with three nodes affected, not three separate pairwise merges — matching
    `01_DOMAIN_MODEL.md` §4's own phrasing ("3 entities merged... 47 nodes affected") as a summary
    of what moved, not a pairwise combinatorial count."""
    groups_before: dict[ClusterId, set[NodeId]] = {}
    for node_id, cluster_id in before.items():
        groups_before.setdefault(cluster_id, set()).add(node_id)
    groups_after: dict[ClusterId, set[NodeId]] = {}
    for node_id, cluster_id in after.items():
        groups_after.setdefault(cluster_id, set()).add(node_id)

    # A node is "affected" if its cluster's *membership* differs, not merely whether its own
    # cluster-id label changed — the deterministic tie-break in `compute_clusters` (the
    # numerically-smallest node id roots a cluster) means the node that happens to root a merged
    # cluster keeps its own id as the label even though three strangers just joined it, and that
    # node has visibly changed for the analyst every bit as much as the ones whose label moved.
    affected: set[NodeId] = {
        node_id
        for node_id in before
        if groups_before.get(before[node_id]) != groups_after.get(after[node_id])
    }

    # A "merge" is a before-cluster whose members ended up split across >1 after-cluster having
    # instead landed together — counted the other direction: an after-cluster with members drawn
    # from >1 distinct before-cluster is one merge event.
    merged = sum(
        1
        for members in groups_after.values()
        if len({before[m] for m in members}) > 1
    )
    # A "split" is symmetric: a before-cluster whose members landed in >1 distinct after-cluster.
    split = sum(
        1
        for members in groups_before.values()
        if len({after[m] for m in members}) > 1
    )

    return ClusterDelta(
        merged=merged,
        split=split,
        nodes_affected=len(affected),
        affected_cluster_ids={node_id: after[node_id] for node_id in affected},
    )
