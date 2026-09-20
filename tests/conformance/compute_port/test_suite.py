"""`ComputePort` conformance suite (`docs/07_BUILD_PLAN.md` Phase 7, `00_ARCHITECTURE.md` §2.3,
`01_DOMAIN_MODEL.md` §10).

Parametrised over `COMPUTE_PORT_ADAPTERS` in `tests/conformance/registry.py` — real from Stage 3:
`adapters/compute_rustworkx` (Tier 2) and `adapters/compute_graphology_tier1` (Tier 1, a
subprocess-driven Node script per `06_DECISIONS.md` ADR-028), so the cross-tier agreement case
below actually runs rather than collecting zero. Tier 3 (deferred to Phase 8a's `cluster`
profile, ADR-028 / ADR-022's third addendum) is still not registered — the same
"structurally unable to pass vacuously" discipline Phase 0 established for every other port
covered its own absence until Tier 1 joined.

**What this suite does not, and cannot, prove — named rather than left to be assumed covered.**
`ComputePort` takes no `Principal` (`01_DOMAIN_MODEL.md` §10): every request below carries an
explicit `Subgraph`, so `test_centrality_never_returns_a_node_outside_the_requested_subgraph` is
the structural half of `CLAUDE.md` rule 3's concern — an adapter cannot leak a node it was never
given. It is *not* the composed claim that a real caller always assembles that `Subgraph` through
an access-filtered `GraphPort.expand`/`match` first; that is
`tests/services/api/working_set/test_compute_access_control.py`'s own shape of test (real
`GraphPort` adapter, two principals, one hidden node), built once the metrics panel exists as a
real caller (Phase 7 Stage 3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import get_args

import pytest

from conduit_common.identity import new_edge_id, new_node_id, now_utc
from schemas.compute import (
    CentralityMetric,
    CentralityRequest,
    CliqueMetricRequest,
    CommunityRequest,
)
from schemas.domain import (
    AuditStub,
    Edge,
    Handling,
    Node,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
)
from tests.conformance.registry import COMPUTE_PORT_ADAPTERS, ComputeAdapterFactory

_per_adapter = pytest.mark.parametrize("factory", COMPUTE_PORT_ADAPTERS, ids=str)


def _provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="fixture", locator="p.1", excerpt_hash="a" * 64)],
        first_seen=datetime.now(UTC),
    )


def _handling() -> Handling:
    return Handling(
        classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
    )


def _node(node_id: str, node_type: str = "Person") -> Node:
    return Node(
        id=node_id,
        type=node_type,
        provenance=_provenance(),
        handling=_handling(),
        audit=AuditStub(created_at=now_utc(), created_by="loader-1"),
    )


def _edge(source: str, target: str, edge_type: str = "ASSOCIATE_OF") -> Edge:
    return Edge(
        id=new_edge_id(),
        type=edge_type,
        source=source,
        target=target,
        provenance=_provenance(),
        handling=_handling(),
        audit=AuditStub(created_at=now_utc(), created_by="loader-1"),
    )


def _small_subgraph() -> tuple[Subgraph, str, str]:
    """Two nodes, one edge — just enough to prove containment, not a
    realistic algorithm input."""
    a, b = new_node_id(), new_node_id()
    return Subgraph(nodes=[_node(a), _node(b)], edges=[_edge(a, b)]), a, b


def _insular_cluster_vs_broad_hub_subgraph() -> tuple[Subgraph, str, str]:
    """A small, purpose-built fixture for this suite's own structural claim — distinct from, and
    simpler than, `tests/scenarios/fixtures/hmp_graph.py`'s full 400-person population (whose own
    8-person relay group is the real insular-cluster substrate `hmp_population.py`'s own docstring
    names as "the substrate the Clique Metric needs"). That fixture has no matching high-degree,
    low-clique "hub" counterpart built into it; this one is self-contained and needs no live
    `GraphPort` round trip, appropriate for a pure conformance case. Phase 7's own exit criterion
    ("the Clique Metric ranks the insular-cluster fixture node above the broad-hub fixture node")
    is proven against the real HMP population separately, in that scenario's own closing pass.

    Insular cluster: 8 nodes, each `ASSOCIATE_OF` every other (a full 8-clique, density 1.0) plus
    one external bridge each to a shared `bridge` node — the same shape
    `test_hmp_graph.py` already confirms for the real relay group.
    Broad hub: one node connected to 12 distinct leaves that share no edges with each other at all
    (a star — high degree, density 0.0)."""
    cluster_ids = [new_node_id() for _ in range(8)]
    bridge_id = new_node_id()
    hub_id = new_node_id()
    leaf_ids = [new_node_id() for _ in range(12)]

    nodes = [_node(n) for n in (*cluster_ids, bridge_id, hub_id, *leaf_ids)]
    edges = [_edge(a, b) for i, a in enumerate(cluster_ids) for b in cluster_ids[i + 1 :]]
    edges += [_edge(member, bridge_id) for member in cluster_ids]
    edges += [_edge(hub_id, leaf) for leaf in leaf_ids]

    return Subgraph(nodes=nodes, edges=edges), cluster_ids[0], hub_id


@_per_adapter
async def test_centrality_never_returns_a_node_outside_the_requested_subgraph(
    factory: ComputeAdapterFactory,
) -> None:
    subgraph, a, b = _small_subgraph()
    request = CentralityRequest(subgraph=subgraph, metric="degree")
    async with factory.context() as adapter:
        result = await adapter.centrality(request)
    assert set(result.keys()) == {a, b}


@_per_adapter
@pytest.mark.parametrize("metric", get_args(CentralityMetric))
async def test_centrality_metric_selector_covers_every_declared_literal(
    factory: ComputeAdapterFactory, metric: str
) -> None:
    """One case per `CentralityMetric` value — a future addition to the enum with no adapter
    support is caught structurally here rather than silently at the metrics panel."""
    subgraph, a, b = _small_subgraph()
    request = CentralityRequest(subgraph=subgraph, metric=metric)  # type: ignore[arg-type]
    async with factory.context() as adapter:
        result = await adapter.centrality(request)
    assert set(result.keys()) == {a, b}
    assert all(isinstance(v, float) for v in result.values())


@_per_adapter
async def test_communities_assigns_every_node_a_cluster_including_singletons(
    factory: ComputeAdapterFactory,
) -> None:
    subgraph, a, b = _small_subgraph()
    isolated = new_node_id()
    subgraph = subgraph.model_copy(update={"nodes": [*subgraph.nodes, _node(isolated)]})
    request = CommunityRequest(subgraph=subgraph)
    async with factory.context() as adapter:
        result = await adapter.communities(request)
    assert set(result.keys()) == {a, b, isolated}
    assert result[a] == result[b]
    assert result[isolated] != result[a]


@_per_adapter
async def test_communities_never_returns_a_disconnected_group(
    factory: ComputeAdapterFactory,
) -> None:
    """A coarse end-to-end sanity check on the composed pipeline, not a rigorous proof of the
    split fix — checked directly, not assumed: `networkx.algorithms.community.louvain_communities`
    already separates two disjoint edges into two communities on a trivial graph with nothing else
    in it, so this case would pass identically whether or not `split_disconnected_communities`
    existed at all. It stays because it proves the adapter's `communities()` wiring produces the
    right *shape* of answer end to end (`Subgraph` in, correctly-keyed `dict[NodeId, CommunityId]`
    out), which the unit test below does not touch. The actual adversarial proof of ADR-029's own
    hazard — a partition that is deliberately wrong regardless of what any real Louvain run would
    produce — lives in `tests/adapters/compute_rustworkx/test_communities.py`, against the
    `split_disconnected_communities` function directly, per rule 12."""
    a, b, c, d = (new_node_id() for _ in range(4))
    subgraph = Subgraph(
        nodes=[_node(a), _node(b), _node(c), _node(d)],
        edges=[_edge(a, b), _edge(c, d)],
    )
    request = CommunityRequest(subgraph=subgraph)
    async with factory.context() as adapter:
        result = await adapter.communities(request)
    assert result[a] == result[b]
    assert result[c] == result[d]
    assert result[a] != result[c]


@_per_adapter
async def test_clique_metric_ranks_the_insular_cluster_above_the_broad_hub(
    factory: ComputeAdapterFactory,
) -> None:
    subgraph, cluster_member_id, hub_id = _insular_cluster_vs_broad_hub_subgraph()
    request = CliqueMetricRequest(subgraph=subgraph)
    async with factory.context() as adapter:
        result = await adapter.clique_metric(request)
    assert result[cluster_member_id] > result[hub_id]


# --- cross-tier agreement — the exit criterion's own clause, honestly zero until two tiers exist -

_TIER_SETS = [COMPUTE_PORT_ADAPTERS] if len(COMPUTE_PORT_ADAPTERS) >= 2 else []


@pytest.mark.parametrize("factories", _TIER_SETS, ids=lambda _: "all-registered-tiers")
async def test_all_registered_tiers_agree_within_tolerance(
    factories: list[ComputeAdapterFactory],
) -> None:
    """`07_BUILD_PLAN.md` Phase 7's own exit criterion: registered compute tiers return identical
    values within tolerance. The per-adapter cases above only prove each tier's own internal
    correctness in isolation — this is the only case that actually proves agreement, and it is
    deliberately parametrised (not a plain function) so it collects zero rather than vacuously
    passing with zero or one tier registered, the same discipline `_TIER_SETS` names in its own
    definition. Tolerance is `06_DECISIONS.md` ADR-028's own measured figure for exact/closed-form
    metrics (max observed relative divergence `1.17e-14`; `rel=1e-9` leaves five orders of
    headroom) — the Clique Metric is exact arithmetic, not iterative, so it belongs in this class,
    not PageRank/eigenvector's own looser `rel=1e-4`."""
    subgraph, _, _ = _insular_cluster_vs_broad_hub_subgraph()
    request = CliqueMetricRequest(subgraph=subgraph)
    results = []
    for factory in factories:
        async with factory.context() as adapter:
            results.append(await adapter.clique_metric(request))
    baseline = results[0]
    for other in results[1:]:
        assert baseline.keys() == other.keys()
        for node_id, value in baseline.items():
            assert other[node_id] == pytest.approx(value, rel=1e-9)
