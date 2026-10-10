"""`ComputePort` conformance suite (`00_ARCHITECTURE.md` §2.3,
`01_DOMAIN_MODEL.md` §10).

Parametrised over `COMPUTE_PORT_ADAPTERS` in `tests/conformance/registry.py` — real from Stage 3:
`adapters/compute_rustworkx` (Tier 2) and `adapters/compute_graphology_tier1` (Tier 1, a
subprocess-driven Node script per `06_DECISIONS.md` ADR-028), so the cross-tier agreement case
below actually runs rather than collecting zero. Tier 3 (deferred to Phase 8a's `cluster`
profile, ADR-028) is still not registered — the same
"structurally unable to pass vacuously" discipline Phase 0 established for every other port
covered its own absence until Tier 1 joined.

**What this suite does not, and cannot, prove — named rather than left to be assumed covered.**
`ComputePort` takes no `Principal` (`01_DOMAIN_MODEL.md` §10): every request below carries an
explicit `Subgraph`, so `test_centrality_never_returns_a_node_outside_the_requested_subgraph` is
the structural half of the access-control-in-the-adapter concern — an adapter cannot leak a
node it was never
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
    LinkStructure,
    StructureEdge,
    StructureNode,
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
    simpler than, `packages/demo_fixtures/hmp_graph.py`'s full 400-person population (whose own
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


def _structure_of(subgraph: Subgraph) -> LinkStructure:
    """The same graph as only its structure (ADR-100 Amendment 5): what the case's groups are found
    from, since reading every record of a large case in full is hundreds of megabytes."""
    return LinkStructure(
        nodes=[StructureNode(id=n.id, type=n.type) for n in subgraph.nodes],
        edges=[
            StructureEdge(id=e.id, source=e.source, target=e.target, weight=e.weight)
            for e in subgraph.edges
        ],
    )


@_per_adapter
async def test_communities_from_the_structure_alone_are_those_of_the_whole_records(
    factory: ComputeAdapterFactory,
) -> None:
    a, b, c, d = (new_node_id() for _ in range(4))
    isolated = new_node_id()
    subgraph = Subgraph(
        nodes=[_node(a), _node(b), _node(c), _node(d), _node(isolated)],
        edges=[_edge(a, b), _edge(c, d)],
    )
    async with factory.context() as adapter:
        whole = await adapter.communities(CommunityRequest(subgraph=subgraph))
        structure = await adapter.communities(CommunityRequest(structure=_structure_of(subgraph)))
    assert set(structure) == {a, b, c, d, isolated}
    assert structure[a] == structure[b] and structure[c] == structure[d]
    assert len({structure[a], structure[c], structure[isolated]}) == 3
    # The same partition either way, whatever the labels are called.
    def groups(labels: dict[str, str]) -> set[frozenset[str]]:
        found: dict[str, set[str]] = {}
        for node, label in labels.items():
            found.setdefault(label, set()).add(node)
        return {frozenset(g) for g in found.values()}

    assert groups(structure) == groups(whole)


def test_a_community_request_is_of_exactly_one_graph() -> None:
    subgraph, _, _ = _small_subgraph()
    with pytest.raises(ValueError):
        CommunityRequest()
    with pytest.raises(ValueError):
        CommunityRequest(subgraph=subgraph, structure=_structure_of(subgraph))


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
    """This phase's own exit criterion: registered compute tiers return identical
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


# --- ownership (ADR-109 phase C, ruling 9) — written before either adapter's code (rule 1) ----
#
# Every expected figure is worked by hand in the case's own docstring, so a reader can check the
# arithmetic without trusting either adapter.

from schemas.compute import OwnershipLink, OwnershipRequest, OwnershipTooComplex  # noqa: E402


def _ownership(
    target: str,
    people: list[str],
    companies: list[str],
    links: list[tuple[str, str, str, float | None]],
    threshold: float = 25.0,
    max_depth: int = 10,
) -> OwnershipRequest:
    return OwnershipRequest(
        target=target,
        nodes=[StructureNode(id=n, type="Person") for n in people]
        + [StructureNode(id=n, type="Organisation") for n in companies],
        links=[
            OwnershipLink(id=f"{s}->{t}", source=s, target=t, kind=kind, percent=pct)  # type: ignore[arg-type]
            for s, t, kind, pct in links
        ],
        threshold=threshold,
        max_depth=max_depth,
    )


def _owner(trace, node_id: str):  # type: ignore[no-untyped-def]
    found = [o for o in trace.owners if o.node_id == node_id]
    assert found, f"{node_id} has no chain to the target"
    return found[0]


@_per_adapter
async def test_ownership_through_a_chain_is_the_product_of_its_shares(
    factory: ComputeAdapterFactory,
) -> None:
    """P owns 60% of A, A owns 50% of T: P holds 0.6 × 0.5 = 30% of T, A 50%."""
    req = _ownership("T", ["P"], ["A", "T"], [("P", "A", "owns", 60), ("A", "T", "owns", 50)])
    async with factory.context() as compute:
        trace = await compute.ownership(req)
    assert round(_owner(trace, "P").cumulative_percent, 6) == 30.0
    assert round(_owner(trace, "A").cumulative_percent, 6) == 50.0
    assert _owner(trace, "P").beneficial_owner is True
    assert _owner(trace, "A").beneficial_owner is False, "a company is never a beneficial owner"
    assert [p.link_ids for p in _owner(trace, "P").paths] == [["P->A", "A->T"]]
    assert trace.cycles == []


@_per_adapter
async def test_ownership_sums_parallel_chains(factory: ComputeAdapterFactory) -> None:
    """P: 60% × 50% through A = 30%, plus 20% directly = 50%."""
    req = _ownership(
        "T", ["P"], ["A", "T"],
        [("P", "A", "owns", 60), ("A", "T", "owns", 50), ("P", "T", "owns", 20)],
    )  # fmt: skip
    async with factory.context() as compute:
        trace = await compute.ownership(req)
    owner = _owner(trace, "P")
    assert round(owner.cumulative_percent, 6) == 50.0
    assert len(owner.paths) == 2
    assert trace.owners[0].node_id == "A" or trace.owners[0].cumulative_percent >= 50.0


@_per_adapter
async def test_a_circle_of_cross_holdings_is_traced_once_and_flagged(
    factory: ComputeAdapterFactory,
) -> None:
    """A owns 50% of B and B 50% of A; P owns all of A; A owns 60% of T and B 40%.
    P: P→A→T = 1 × 0.6 = 60%; P→A→B→T = 1 × 0.5 × 0.4 = 20%; total 80% (P→A→B→A… never looped).
    A: A→T 60% + A→B→T 0.5 × 0.4 = 20% → 80%.  B: B→T 40% + B→A→T 0.5 × 0.6 = 30% → 70%."""
    req = _ownership(
        "T", ["P"], ["A", "B", "T"],
        [("A", "B", "owns", 50), ("B", "A", "owns", 50), ("P", "A", "owns", 100),
         ("A", "T", "owns", 60), ("B", "T", "owns", 40)],
    )  # fmt: skip
    async with factory.context() as compute:
        trace = await compute.ownership(req)
    assert round(_owner(trace, "P").cumulative_percent, 6) == 80.0
    assert round(_owner(trace, "A").cumulative_percent, 6) == 80.0
    assert round(_owner(trace, "B").cumulative_percent, 6) == 70.0
    assert [sorted(c) for c in trace.cycles] == [["A", "B"]]


@_per_adapter
async def test_a_link_without_a_percentage_is_unknown_never_assumed(
    factory: ComputeAdapterFactory,
) -> None:
    """P owns A by an unstated share; A owns all of T. P's share is unknown — not 100%, not 0%:
    its known share is 0, it is flagged, and as a person below the threshold it is a possible
    beneficial owner."""
    req = _ownership("T", ["P"], ["A", "T"], [("P", "A", "owns", None), ("A", "T", "owns", 100)])
    async with factory.context() as compute:
        trace = await compute.ownership(req)
    owner = _owner(trace, "P")
    assert owner.cumulative_percent == 0.0
    assert owner.share_unknown is True
    assert owner.beneficial_owner is False
    assert owner.possible_beneficial_owner is True
    assert [p.kind for p in owner.paths] == ["unknown"]


@_per_adapter
async def test_control_confers_control_not_a_share(factory: ComputeAdapterFactory) -> None:
    """P controls A (no share); A owns all of T. P controls T through A and holds no share of it;
    a natural person with control is a beneficial owner whatever the share."""
    req = _ownership("T", ["P"], ["A", "T"], [("P", "A", "controls", None), ("A", "T", "owns", 100)])
    async with factory.context() as compute:
        trace = await compute.ownership(req)
    owner = _owner(trace, "P")
    assert owner.cumulative_percent == 0.0
    assert owner.controls is True
    assert owner.beneficial_owner is True
    assert [p.kind for p in owner.paths] == ["control"]


@_per_adapter
async def test_the_threshold_is_inclusive(factory: ComputeAdapterFactory) -> None:
    """Q holds exactly 25% (a beneficial owner at the 25% threshold); R holds 24.99% (not)."""
    req = _ownership("T", ["Q", "R"], ["T"], [("Q", "T", "owns", 25), ("R", "T", "owns", 24.99)])
    async with factory.context() as compute:
        trace = await compute.ownership(req)
    assert _owner(trace, "Q").beneficial_owner is True
    assert _owner(trace, "R").beneficial_owner is False
    assert [o.node_id for o in trace.owners] == ["Q", "R"], "the largest known share first"


@_per_adapter
async def test_a_structure_deeper_than_the_limit_is_refused_not_traced_in_part(
    factory: ComputeAdapterFactory,
) -> None:
    """A chain of five links with `max_depth=4`: refused, rather than reporting the four nearest."""
    chain = ["P", "C1", "C2", "C3", "C4", "T"]
    req = _ownership(
        "T", ["P"], chain[1:],
        [(a, b, "owns", 100) for a, b in zip(chain, chain[1:], strict=False)], max_depth=4,
    )  # fmt: skip
    async with factory.context() as compute:
        with pytest.raises((OwnershipTooComplex, RuntimeError)):
            await compute.ownership(req)


@_per_adapter
async def test_a_party_with_no_chain_to_the_target_is_not_an_owner(
    factory: ComputeAdapterFactory,
) -> None:
    """X owns 90% of an unrelated company: not in the trace at all."""
    req = _ownership("T", ["P", "X"], ["T", "U"], [("P", "T", "owns", 100), ("X", "U", "owns", 90)])
    async with factory.context() as compute:
        trace = await compute.ownership(req)
    assert [o.node_id for o in trace.owners] == ["P"]


async def test_ownership_agrees_across_tiers() -> None:
    """The same layered structure through both tiers gives the same trace (ADR-028's agreement)."""
    req = _ownership(
        "T", ["P", "N"], ["A", "B", "T"],
        [("P", "A", "owns", 60), ("N", "A", "owns", 40), ("A", "B", "owns", 70),
         ("B", "T", "owns", 100), ("P", "T", "owns", 10), ("B", "A", "owns", 15),
         ("N", "T", "owns", None), ("N", "B", "controls", None)],
    )  # fmt: skip
    traces = []
    for factory in COMPUTE_PORT_ADAPTERS:
        async with factory.context() as compute:
            traces.append(await compute.ownership(req))
    first = traces[0].model_dump()
    for other in traces[1:]:
        assert other.model_dump() == first


# --- risk propagation (ADR-109 phase E) — written before either adapter's code (rule 1) -----

from schemas.compute import PropagationRequest  # noqa: E402


def _propagation(
    target: str,
    edges: list[tuple[str, str]],
    seeds: dict[str, float],
    *,
    max_hops: int = 2,
    decay: float = 0.5,
) -> PropagationRequest:
    names = sorted({target, *seeds, *(n for e in edges for n in e)})
    return PropagationRequest(
        target=target,
        nodes=[StructureNode(id=n, type="Person") for n in names],
        edges=[StructureEdge(id=f"{a}-{b}", source=a, target=b) for a, b in edges],
        seeds=seeds,
        max_hops=max_hops,
        decay=decay,
    )


@_per_adapter
async def test_risk_decays_by_half_per_hop_of_the_shortest_distance(
    factory: ComputeAdapterFactory,
) -> None:
    """T—A—B, A alerted twice (seed 2), B once (seed 1): A one hop, 2 × 0.5 = 1; B two hops,
    1 × 0.25 = 0.25; T itself holds nothing. Score 1.25."""
    req = _propagation("T", [("T", "A"), ("A", "B")], {"A": 2.0, "B": 1.0})
    async with factory.context() as compute:
        result = await compute.propagate(req)
    assert result.score == 1.25
    assert [(c.node_id, c.hops, c.contribution) for c in result.contributions] == [
        ("A", 1, 1.0),
        ("B", 2, 0.25),
    ]


@_per_adapter
async def test_a_seed_counts_once_at_its_nearest_however_many_paths_reach_it(
    factory: ComputeAdapterFactory,
) -> None:
    """T reaches S directly and through A: S is one hop away and counts once — 1 × 0.5."""
    req = _propagation("T", [("T", "S"), ("T", "A"), ("A", "S")], {"S": 1.0})
    async with factory.context() as compute:
        result = await compute.propagate(req)
    assert result.score == 0.5
    assert [c.hops for c in result.contributions] == [1]


@_per_adapter
async def test_a_seed_beyond_the_hops_contributes_nothing(factory: ComputeAdapterFactory) -> None:
    """T—A—B—C with C alerted: three hops, past the two counted."""
    req = _propagation("T", [("T", "A"), ("A", "B"), ("B", "C")], {"C": 5.0})
    async with factory.context() as compute:
        result = await compute.propagate(req)
    assert result.score == 0.0 and result.contributions == []


@_per_adapter
async def test_the_target_s_own_alerts_count_at_full_weight(factory: ComputeAdapterFactory) -> None:
    """Zero hops: decay^0 = 1."""
    req = _propagation("T", [("T", "A")], {"T": 3.0})
    async with factory.context() as compute:
        result = await compute.propagate(req)
    assert result.score == 3.0 and result.contributions[0].hops == 0


@_per_adapter
async def test_a_seed_not_connected_is_not_reached(factory: ComputeAdapterFactory) -> None:
    """X is alerted but nothing links it to T (as when the only path is hidden from the reader)."""
    req = _propagation("T", [("T", "A")], {"X": 4.0})
    async with factory.context() as compute:
        result = await compute.propagate(req)
    assert result.score == 0.0


async def test_propagation_agrees_across_tiers() -> None:
    req = _propagation(
        "T",
        [("T", "A"), ("A", "B"), ("T", "C"), ("C", "B"), ("B", "D"), ("D", "E")],
        {"A": 1.0, "B": 3.0, "D": 0.7, "E": 9.0, "T": 0.3},
        max_hops=3,
        decay=0.4,
    )
    results = []
    for factory in COMPUTE_PORT_ADAPTERS:
        async with factory.context() as compute:
            results.append(await compute.propagate(req))
    assert all(r.model_dump() == results[0].model_dump() for r in results[1:])
