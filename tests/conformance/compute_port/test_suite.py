"""`ComputePort` conformance suite (`docs/07_BUILD_PLAN.md` Phase 7 Stage 2, `00_ARCHITECTURE.md`
§2.3, `01_DOMAIN_MODEL.md` §10).

Parametrised over `COMPUTE_PORT_ADAPTERS` in `tests/conformance/registry.py` — empty through
Stage 2 (standing rule 1: schemas and this suite come before any adapter), so every case below
collects zero, the same "structurally unable to pass vacuously" discipline Phase 0 established for
every other port. A later stage registers `adapters/compute_rustworkx` (and, per `06_DECISIONS.md`
ADR-028, eventually a `graphology`-over-Node Tier 1 entry) and these same cases start running for
real — the parametrisation itself does not change.

**What this suite does not, and cannot, prove — named rather than left to be assumed covered.**
`ComputePort` takes no `Principal` (`01_DOMAIN_MODEL.md` §10): every request below carries an
explicit `Subgraph`, so `test_centrality_never_returns_a_node_outside_the_requested_subgraph` is
the structural half of `CLAUDE.md` rule 3's concern — an adapter cannot leak a node it was never
given. It is *not* the composed claim that a real caller always assembles that `Subgraph` through
an access-filtered `GraphPort.expand`/`match` first; that is `test_projection_access_control.py`'s
own shape of test (real `GraphPort` adapter, two principals, one hidden node), owed by whichever
stage builds `ComputePort`'s first real caller (the metrics panel), not built here because no
caller exists yet.
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
from tests.conformance.registry import COMPUTE_PORT_ADAPTERS

_per_adapter = pytest.mark.parametrize("adapter", COMPUTE_PORT_ADAPTERS, ids=str)


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
    names as "the substrate the Clique Metric needs... A12/the metric itself is not verified here").
    That fixture has no matching high-degree, low-clique "hub" counterpart built into it; this one
    is self-contained and needs no live `GraphPort` round trip, appropriate for a pure conformance
    case. Phase 7's own exit criterion ("the Clique Metric ranks the insular-cluster fixture node
    above the broad-hub fixture node") is proven against the real HMP population separately, once
    an adapter and a caller exist to run that closing pass.

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
    edges = [
        _edge(a, b) for i, a in enumerate(cluster_ids) for b in cluster_ids[i + 1 :]
    ]
    edges += [_edge(member, bridge_id) for member in cluster_ids]
    edges += [_edge(hub_id, leaf) for leaf in leaf_ids]

    return Subgraph(nodes=nodes, edges=edges), cluster_ids[0], hub_id


@_per_adapter
async def test_centrality_never_returns_a_node_outside_the_requested_subgraph(
    adapter: object,
) -> None:
    subgraph, a, b = _small_subgraph()
    request = CentralityRequest(subgraph=subgraph, metric="degree")
    result = await adapter.centrality(request)  # type: ignore[attr-defined]
    assert set(result.keys()) == {a, b}


@_per_adapter
@pytest.mark.parametrize("metric", get_args(CentralityMetric))
async def test_centrality_metric_selector_covers_every_declared_literal(
    adapter: object, metric: str
) -> None:
    """One case per `CentralityMetric` value — a future addition to the enum with no adapter
    support is caught structurally here rather than silently at the metrics panel."""
    subgraph, a, b = _small_subgraph()
    request = CentralityRequest(subgraph=subgraph, metric=metric)  # type: ignore[arg-type]
    result = await adapter.centrality(request)  # type: ignore[attr-defined]
    assert set(result.keys()) == {a, b}
    assert all(isinstance(v, float) for v in result.values())


@_per_adapter
async def test_communities_assigns_every_node_a_cluster_including_singletons(
    adapter: object,
) -> None:
    subgraph, a, b = _small_subgraph()
    isolated = new_node_id()
    subgraph = subgraph.model_copy(update={"nodes": [*subgraph.nodes, _node(isolated)]})
    request = CommunityRequest(subgraph=subgraph)
    result = await adapter.communities(request)  # type: ignore[attr-defined]
    assert set(result.keys()) == {a, b, isolated}
    assert result[a] == result[b]
    assert result[isolated] != result[a]


@_per_adapter
async def test_clique_metric_ranks_the_insular_cluster_above_the_broad_hub(
    adapter: object,
) -> None:
    subgraph, cluster_member_id, hub_id = _insular_cluster_vs_broad_hub_subgraph()
    request = CliqueMetricRequest(subgraph=subgraph)
    result = await adapter.clique_metric(request)  # type: ignore[attr-defined]
    assert result[cluster_member_id] > result[hub_id]


# --- cross-tier agreement — the exit criterion's own clause, honestly zero until two tiers exist -

_TIER_SETS = [COMPUTE_PORT_ADAPTERS] if len(COMPUTE_PORT_ADAPTERS) >= 2 else []


@pytest.mark.parametrize("adapters", _TIER_SETS, ids=lambda _: "all-registered-tiers")
async def test_all_registered_tiers_agree_within_tolerance(adapters: list[object]) -> None:
    """`07_BUILD_PLAN.md` Phase 7's own exit criterion: "all three compute tiers return identical
    values within tolerance." The per-adapter cases above only prove each tier's own internal
    correctness in isolation — this is the only case that actually proves agreement, and it is
    deliberately parametrised (not a plain function) so it collects zero rather than vacuously
    passing with zero or one tier registered, the same discipline `_TIER_SETS` names in its own
    definition."""
    subgraph, _, _ = _insular_cluster_vs_broad_hub_subgraph()
    request = CliqueMetricRequest(subgraph=subgraph)
    results = [await a.clique_metric(request) for a in adapters]  # type: ignore[attr-defined]
    baseline = results[0]
    for other in results[1:]:
        assert baseline.keys() == other.keys()
        for node_id, value in baseline.items():
            assert other[node_id] == pytest.approx(value, abs=1e-6)
