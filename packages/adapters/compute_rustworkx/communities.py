"""Louvain (`networkx`) plus a connected-components split — `docs/06_DECISIONS.md` ADR-029: Leiden
is unavailable on either `ComputePort` compute tier, and Louvain alone can merge two disconnected
components into one labelled community. The split pass closes that specific, named hazard without
restoring Leiden's own partition quality — a disclosed trade, not a free fix (ADR-029's own
wording). Kept in its own module, independent of `rustworkx`, because the split pass itself is
meant to be read and re-implemented identically in Tier 1's own JavaScript, not shared code.
"""

from __future__ import annotations

from collections.abc import Sequence

from schemas.domain import CommunityId, NodeId


def split_disconnected_communities(
    node_ids: Sequence[NodeId],
    edges: Sequence[tuple[NodeId, NodeId]],
    partition: dict[NodeId, int],
) -> dict[NodeId, CommunityId]:
    """For each label Louvain assigned, find the connected components of that label's own induced
    subgraph and give each one its own final id — O(n+m): one pass building same-label adjacency,
    one pass visiting every node exactly once via BFS. `partition` may name a superset of
    `node_ids` (harmless — only `node_ids`' own members are ever visited or returned)."""
    adjacency: dict[NodeId, list[NodeId]] = {n: [] for n in node_ids}
    for a, b in edges:
        if a in adjacency and b in adjacency and partition.get(a) == partition.get(b):
            adjacency[a].append(b)
            adjacency[b].append(a)

    result: dict[NodeId, CommunityId] = {}
    visited: set[NodeId] = set()
    next_id = 0
    for start in node_ids:
        if start in visited:
            continue
        component = [start]
        visited.add(start)
        frontier = [start]
        while frontier:
            current = frontier.pop()
            for neighbour in adjacency[current]:
                if neighbour not in visited:
                    visited.add(neighbour)
                    component.append(neighbour)
                    frontier.append(neighbour)
        community_id = str(next_id)
        next_id += 1
        for member in component:
            result[member] = community_id
    return result
