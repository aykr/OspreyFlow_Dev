"""The overview service — `spec/06_DECISIONS.md` ADR-057, stage 1.

Reads the access-filtered graph of the vault the store is connected to, finds its communities
through `ComputePort`, and returns the largest as meta-nodes with exact figures for the rest. The
access filtering is the store's (`CLAUDE.md` rule 3); this module only sees what the principal
can, so a hidden node is in no cluster, size or total. A graph over the working set's caps is the
typed `limit_exceeded`, never a slice (rule 2). The result is cached per vault and per access
class.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Protocol

from ports.compute import ComputePort
from ports.graph import GraphPort, SubgraphTooLarge
from schemas.compute import CommunityRequest
from schemas.domain import Node, Principal, Subgraph
from schemas.overview import Overview, OverviewCluster, OverviewLink

from .working_set.models import MAX_EDGES, MAX_NODES, LimitExceeded, LimitExceededError

#: How many communities are drawn. The rest are counted, not shown.
TOP_CLUSTERS = 25
_SAMPLE = 5


class OverviewCache(Protocol):
    """`CachedQuery`'s shape: keyed by the query and the principal's access class."""

    async def get(self, query_signature: str, principal: Principal) -> Any | None: ...

    async def put(self, query_signature: str, principal: Principal, result: Any) -> None: ...


async def build_overview(
    *,
    graph: GraphPort,
    compute: ComputePort,
    cache: OverviewCache,
    principal: Principal,
    vault: str,
    top: int = TOP_CLUSTERS,
    max_nodes: int = MAX_NODES,
    max_edges: int = MAX_EDGES,
) -> Overview:
    signature = f"overview:v1:{vault}:{top}:{max_nodes}:{max_edges}"
    cached = await cache.get(signature, principal)
    if cached is not None:
        return Overview.model_validate(cached)

    try:
        subgraph = await graph.vault_subgraph(principal, max_nodes=max_nodes, max_edges=max_edges)
    except SubgraphTooLarge as too_large:
        raise LimitExceededError(
            _breach(too_large.nodes, too_large.edges, max_nodes, max_edges)
        ) from too_large
    # The port is meant to raise; a store that returns more than the cap must not get through as a
    # success, into the algorithm or the cache.
    if len(subgraph.nodes) > max_nodes or len(subgraph.edges) > max_edges:
        raise LimitExceededError(
            _breach(len(subgraph.nodes), len(subgraph.edges), max_nodes, max_edges)
        )

    labels = await compute.communities(CommunityRequest(subgraph=subgraph))
    overview = _summarise(vault, subgraph, labels, top)
    await cache.put(signature, principal, overview.model_dump(mode="json"))
    return overview


def _breach(nodes: int, edges: int | None, max_nodes: int, max_edges: int) -> LimitExceeded:
    """Counts are of what the principal can see: reporting what exists would disclose what is
    hidden."""
    if nodes > max_nodes:
        return LimitExceeded(cap_kind="nodes", cap=max_nodes, would_be=nodes)
    if edges is not None and edges > max_edges:
        return LimitExceeded(cap_kind="edges", cap=max_edges, would_be=edges)
    raise RuntimeError("the store reported a subgraph over a cap that is within both caps")


def _summarise(vault: str, subgraph: Subgraph, labels: dict[str, str], top: int) -> Overview:
    # A node the algorithm leaves unlabelled is its own community, never dropped.
    community_of = {n.id: labels.get(n.id) or f"singleton:{n.id}" for n in subgraph.nodes}
    members: dict[str, list[Node]] = defaultdict(list)
    for node in subgraph.nodes:
        members[community_of[node.id]].append(node)

    ranked = sorted(members, key=lambda c: (-len(members[c]), c))
    shown = ranked[:top]
    shown_set = set(shown)

    internal: Counter[str] = Counter()
    links: Counter[tuple[str, str]] = Counter()
    for edge in subgraph.edges:
        a, b = community_of.get(edge.source), community_of.get(edge.target)
        if a is None or b is None:
            continue
        if a == b:
            internal[a] += 1
        elif a in shown_set and b in shown_set:
            links[(min(a, b), max(a, b))] += 1

    clusters = []
    for community in shown:
        nodes = members[community]
        type_counts = Counter(n.type for n in nodes)
        clusters.append(
            OverviewCluster(
                id=community,
                size=len(nodes),
                node_type_counts=dict(type_counts),
                dominant_type=min(type_counts, key=lambda t: (-type_counts[t], t)),
                internal_edge_count=internal[community],
                sample_node_ids=sorted(n.id for n in nodes)[:_SAMPLE],
            )
        )
    shown_nodes = sum(c.size for c in clusters)
    return Overview(
        vault=vault,
        clusters=clusters,
        links=[
            OverviewLink(source_cluster=a, target_cluster=b, edge_count=n)
            for (a, b), n in sorted(links.items())
        ],
        total_nodes=len(subgraph.nodes),
        total_edges=len(subgraph.edges),
        total_clusters=len(members),
        not_shown_clusters=len(members) - len(shown),
        not_shown_nodes=len(subgraph.nodes) - shown_nodes,
    )
