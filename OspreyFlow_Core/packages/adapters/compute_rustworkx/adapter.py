"""`ComputePort` over `rustworkx` — `spec/00_ARCHITECTURE.md` §2.3, Tier 2 (≤ 2M nodes).

Stateless from the adapter's own point of view — no store connection, no schema, exactly like
`adapters/model_litellm`'s own "stateless" shape (`tests/conformance/registry.py`'s
`ModelAdapterFactory` docstring). Every method's only input is the request's own `Subgraph`
(`01_DOMAIN_MODEL.md` §10) — this adapter cannot reach any node it was not handed, which is what
makes `ComputePort`'s own lack of a `Principal` argument safe by construction (the same section's
own reasoning).
"""

from __future__ import annotations

from collections.abc import Sequence

import networkx as nx
import rustworkx as rx

from schemas.compute import (
    CentralityRequest,
    CliqueMetricRequest,
    CommunityRequest,
    MotifMatch,
    MotifRequest,
    OwnershipRequest,
    OwnershipTrace,
    PropagationRequest,
    PropagationResult,
)
from schemas.domain import CliqueScore, CommunityId, NodeId, Path, PathRequest, Subgraph

from .communities import split_disconnected_communities
from .ownership import trace_ownership
from .propagation import propagate


def _build_undirected(
    subgraph: Subgraph,
) -> tuple[rx.PyGraph, dict[NodeId, int], dict[int, NodeId]]:
    graph = rx.PyGraph()
    node_ids = [n.id for n in subgraph.nodes]
    indices = list(graph.add_nodes_from(node_ids))
    index_of = dict(zip(node_ids, indices, strict=True))
    id_of = dict(zip(indices, node_ids, strict=True))
    graph.add_edges_from_no_data(
        [
            (index_of[e.source], index_of[e.target])
            for e in subgraph.edges
            if e.source in index_of and e.target in index_of
        ]
    )
    return graph, index_of, id_of


def _build_directed_both_ways(subgraph: Subgraph) -> tuple[rx.PyDiGraph, dict[NodeId, int]]:
    """PageRank needs a `PyDiGraph` — confirmed empirically, a `PyGraph` raises `TypeError`
    (`06_DECISIONS.md` ADR-028's own addendum was measured against exactly this shape). Each
    undirected edge becomes a reciprocal pair, matching an undirected graph's own PageRank
    semantics rather than introducing a direction the domain model never declared."""
    graph = rx.PyDiGraph()
    node_ids = [n.id for n in subgraph.nodes]
    indices = list(graph.add_nodes_from(node_ids))
    index_of = dict(zip(node_ids, indices, strict=True))
    di_edges: list[tuple[int, int]] = []
    for e in subgraph.edges:
        if e.source in index_of and e.target in index_of:
            di_edges.append((index_of[e.source], index_of[e.target]))
            di_edges.append((index_of[e.target], index_of[e.source]))
    graph.add_edges_from_no_data(di_edges)
    return graph, index_of


def _weighted_degree(subgraph: Subgraph) -> dict[NodeId, float]:
    totals: dict[NodeId, float] = {n.id: 0.0 for n in subgraph.nodes}
    for e in subgraph.edges:
        if e.source in totals:
            totals[e.source] += e.weight
        if e.target in totals:
            totals[e.target] += e.weight
    return totals


def _local_density_and_degree(graph: rx.PyGraph, index: int) -> tuple[float, int]:
    """`density(v) = internal(v) / possible(v)` — `01_DOMAIN_MODEL.md` §6.2's own formula,
    identical to the standard local clustering coefficient. Shared by `clustering_coefficient`
    and `clique_metric` rather than computed twice."""
    neighbours = list(graph.neighbors(index))
    k = len(neighbours)
    if k < 2:
        return 0.0, k
    internal = 0
    for i, u in enumerate(neighbours):
        for v in neighbours[i + 1 :]:
            if graph.has_edge(u, v):
                internal += 1
    possible = k * (k - 1) / 2
    return internal / possible, k


def _dispersion(graph: rx.PyGraph, index: int, neighbours: Sequence[int]) -> float:
    """`external(v) / Σ degree(u)` — `01_DOMAIN_MODEL.md` §6.2."""
    within = set(neighbours) | {index}
    external = 0
    degree_sum = 0
    for u in neighbours:
        degree_sum += graph.degree(u)
        for w in graph.neighbors(u):
            if w not in within:
                external += 1
    if degree_sum == 0:
        return 0.0
    return external / degree_sum


def _saturate(n: int, k_min: int, k_max: int) -> float:
    """`01_DOMAIN_MODEL.md` §6.2 states the two boundaries ("below k_min the score is zero, above
    k_max it plateaus") but not the interpolation between them — silent on this specific point,
    so filled here rather than left unstated: linear from 0 at `k_min` to 1 at `k_max`, the
    simplest monotonic choice consistent with both stated boundaries."""
    if n <= k_min:
        return 0.0
    if n >= k_max:
        return 1.0
    return (n - k_min) / (k_max - k_min)


class ComputeRustworkxAdapter:
    async def centrality(self, req: CentralityRequest) -> dict[NodeId, float]:
        if req.metric == "pagerank":
            digraph, index_of = _build_directed_both_ways(req.subgraph)
            values = rx.pagerank(digraph, alpha=0.85, tol=1e-10, max_iter=1000)
            return {node_id: values[idx] for node_id, idx in index_of.items()}

        graph, index_of, _id_of = _build_undirected(req.subgraph)

        if req.metric == "degree":
            return {node_id: float(graph.degree(idx)) for node_id, idx in index_of.items()}
        if req.metric == "weighted_degree":
            return _weighted_degree(req.subgraph)
        if req.metric == "betweenness":
            values = rx.betweenness_centrality(graph, normalized=True)
            return {node_id: values[idx] for node_id, idx in index_of.items()}
        if req.metric == "eigenvector":
            values = rx.eigenvector_centrality(graph, tol=1e-10, max_iter=1000)
            return {node_id: values[idx] for node_id, idx in index_of.items()}
        if req.metric == "clustering_coefficient":
            return {
                node_id: _local_density_and_degree(graph, idx)[0]
                for node_id, idx in index_of.items()
            }
        raise ValueError(f"unsupported centrality metric: {req.metric!r}")

    async def communities(self, req: CommunityRequest) -> dict[NodeId, CommunityId]:
        node_ids, edges = req.ids_and_ends()

        nx_graph: nx.Graph[NodeId] = nx.Graph()
        nx_graph.add_nodes_from(node_ids)
        nx_graph.add_edges_from(edges)
        raw_partition: dict[NodeId, int] = {}
        louvain = nx.algorithms.community.louvain_communities(nx_graph, seed=42)
        for label, members in enumerate(louvain):
            for member in members:
                raw_partition[member] = label

        return split_disconnected_communities(node_ids, edges, raw_partition)

    async def clique_metric(self, req: CliqueMetricRequest) -> dict[NodeId, CliqueScore]:
        graph, index_of, _id_of = _build_undirected(req.subgraph)
        result: dict[NodeId, CliqueScore] = {}
        for node_id, idx in index_of.items():
            neighbours = list(graph.neighbors(idx))
            density, k = _local_density_and_degree(graph, idx)
            dispersion = _dispersion(graph, idx, neighbours)
            saturation = _saturate(k, req.k_min, req.k_max)
            result[node_id] = density * (1 - dispersion) * saturation
        return result

    async def shortest_paths(self, req: PathRequest) -> list[Path]:
        raise NotImplementedError(
            "ComputePort.shortest_paths has no caller yet (Phase 7 Stage 5, the pathfinder) — "
            "the interactive pathfinder is built on GraphPort.paths directly "
            "(01_DOMAIN_MODEL.md §6.3's own implementation note), not this method"
        )

    async def temporal_motifs(self, req: MotifRequest) -> list[MotifMatch]:
        raise NotImplementedError(
            "convoy/relay/burst detection is unclaimed by any phase's own bullet list "
            "(a disclosed gap) — MotifRequest/MotifMatch exist as real "
            "schemas because _pending_port_placeholders.py's retirement needed them, not because "
            "the algorithm has an owning phase yet, the same disclosed shape "
            "TranscribeRequest.diarize's own NotImplementedError already established"
        )

    async def ownership(self, req: OwnershipRequest) -> OwnershipTrace:
        """ADR-109 phase C — `ownership.py` has the walk and its fixed order."""
        return trace_ownership(req)

    async def propagate(self, req: PropagationRequest) -> PropagationResult:
        """ADR-109 phase E — `propagation.py` has the walk and its fixed order."""
        return propagate(req)

