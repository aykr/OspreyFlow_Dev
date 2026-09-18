"""`WorkingSetService.manual_link`/`manual_split`/`explain_cluster` —
`docs/03_CONDUIT_MIDDLEWARE.md` §3.5, `docs/01_DOMAIN_MODEL.md` §4. Same no-Valkey/no-ArcadeDB
discipline as `test_resolution_threshold.py`: `FakeWorkingSetStore`/`FakeGraphPort` exercise the
service's own logic, not a real adapter.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.working_set.models import (
    ClusterNotFoundError,
    NodeNotInWorkingSetError,
    SameNodeAssertionError,
)
from services.api.working_set.service import WorkingSetService
from services.resolve.projection import THRESHOLD_BALANCED, THRESHOLD_STRICT

from ontology.handling import load_uk_le_scheme
from schemas.domain import (
    AuditStub,
    Edge,
    Handling,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
)

from .fakes import FakeGraphPort, FakeWorkingSetStore

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
SCHEME = load_uk_le_scheme()
INVESTIGATION = "inv-1"


def _handling() -> Handling:
    return Handling(classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u")


def _provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="d", locator="l", excerpt_hash="")],
        first_seen=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _audit() -> AuditStub:
    return AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="analyst-1")


def _person(node_id: str) -> Node:
    return Node(
        id=node_id,
        type="Person",
        properties={},
        provenance=_provenance(),
        handling=_handling(),
        audit=_audit(),
    )


def _same_as(node_a: str, node_b: str, score: float) -> Edge:
    return Edge(
        id=f"{node_a}-{node_b}",
        type="SAME_AS",
        source=node_a,
        target=node_b,
        properties={"score": score, "model_version": "splink-3.9.9-config-1"},
        provenance=Provenance(
            state=ProvenanceState.INFERRED,
            sources=[SourceRef(document_id="d", locator="l", excerpt_hash="")],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
            extraction_confidence=score,
        ),
        handling=_handling(),
        audit=_audit(),
    )


async def test_manual_link_merges_two_nodes_and_writes_the_edge() -> None:
    store = FakeWorkingSetStore()
    graph = FakeGraphPort(Subgraph(nodes=[], edges=[]), 0)
    service = WorkingSetService(graph, store, SCHEME)
    await store.add_nodes(INVESTIGATION, [_person("n1"), _person("n2")])

    delta = await service.manual_link(INVESTIGATION, "n1", "n2", PRINCIPAL)

    assert delta.merged == 1
    assert delta.affected == 2
    nodes = await store.source_fidelity_nodes(INVESTIGATION)
    assert nodes["n1"].resolution.cluster_id == nodes["n2"].resolution.cluster_id

    assert len(graph.committed_edges) == 1
    written = graph.committed_edges[0]
    assert written.type == "SAME_AS"
    assert written.properties["score"] == 1.0
    assert written.provenance.state == ProvenanceState.ASSERTED
    assert "model_version" not in written.properties


async def test_manual_split_separates_two_nodes_even_at_a_broad_threshold() -> None:
    store = FakeWorkingSetStore()
    same_as = _same_as("n1", "n2", 0.999)
    graph = FakeGraphPort(Subgraph(nodes=[], edges=[same_as]), 0)
    service = WorkingSetService(graph, store, SCHEME)
    await store.add_nodes(INVESTIGATION, [_person("n1"), _person("n2")])
    await store.set_threshold(INVESTIGATION, THRESHOLD_STRICT)

    delta = await service.manual_split(INVESTIGATION, "n1", "n2", PRINCIPAL)

    assert delta.split == 1  # 0.999 >= Strict's 0.99: merged pre-split, split by the new edge
    nodes = await store.source_fidelity_nodes(INVESTIGATION)
    assert nodes["n1"].resolution.cluster_id != nodes["n2"].resolution.cluster_id

    written = graph.committed_edges[0]
    assert written.type == "NOT_SAME_AS"
    assert written.provenance.state == ProvenanceState.ASSERTED


async def test_manual_link_rejects_a_node_not_in_the_working_set() -> None:
    store = FakeWorkingSetStore()
    graph = FakeGraphPort(Subgraph(nodes=[], edges=[]), 0)
    service = WorkingSetService(graph, store, SCHEME)
    await store.add_nodes(INVESTIGATION, [_person("n1")])

    with pytest.raises(NodeNotInWorkingSetError):
        await service.manual_link(INVESTIGATION, "n1", "n2-not-present", PRINCIPAL)

    assert graph.committed_edges == []


async def test_manual_split_rejects_asserting_a_node_against_itself() -> None:
    store = FakeWorkingSetStore()
    graph = FakeGraphPort(Subgraph(nodes=[], edges=[]), 0)
    service = WorkingSetService(graph, store, SCHEME)
    await store.add_nodes(INVESTIGATION, [_person("n1")])

    with pytest.raises(SameNodeAssertionError):
        await service.manual_split(INVESTIGATION, "n1", "n1", PRINCIPAL)

    assert graph.committed_edges == []


async def test_explain_cluster_returns_the_direct_edges_between_current_members() -> None:
    store = FakeWorkingSetStore()
    same_as = _same_as("n1", "n2", 0.97)
    graph = FakeGraphPort(Subgraph(nodes=[], edges=[same_as]), 0)
    service = WorkingSetService(graph, store, SCHEME)
    await store.add_nodes(INVESTIGATION, [_person("n1"), _person("n2"), _person("n3")])
    await service.set_resolution_threshold(INVESTIGATION, THRESHOLD_BALANCED, PRINCIPAL)
    nodes = await store.source_fidelity_nodes(INVESTIGATION)
    cluster_id = nodes["n1"].resolution.cluster_id
    assert cluster_id is not None

    explanation = await service.explain_cluster(INVESTIGATION, cluster_id, PRINCIPAL)

    assert set(explanation.member_node_ids) == {"n1", "n2"}
    assert len(explanation.pairs) == 1
    pair = explanation.pairs[0]
    assert pair.score == 0.97
    assert pair.model_version == "splink-3.9.9-config-1"
    assert pair.manually_asserted is False
    assert pair.meets_threshold is True  # 0.97 >= Balanced's 0.95


async def test_explain_cluster_flags_a_manually_linked_pair() -> None:
    store = FakeWorkingSetStore()
    graph = FakeGraphPort(Subgraph(nodes=[], edges=[]), 0)
    service = WorkingSetService(graph, store, SCHEME)
    await store.add_nodes(INVESTIGATION, [_person("n1"), _person("n2")])
    await service.manual_link(INVESTIGATION, "n1", "n2", PRINCIPAL)
    nodes = await store.source_fidelity_nodes(INVESTIGATION)
    cluster_id = nodes["n1"].resolution.cluster_id
    assert cluster_id is not None
    # `manual_link` only committed the edge through the fake's transaction, not into the fake's
    # `expand` result — mirror what a real adapter's next `expand` would now return, as an `Edge`
    # (`Edge` and `EdgeWrite` are separate types; `committed_edges` holds the latter).
    written = graph.committed_edges[0]
    manual_edge = Edge(
        id=written.id,
        type=written.type,
        source=written.source,
        target=written.target,
        properties=written.properties,
        provenance=written.provenance,
        handling=written.handling,
        audit=_audit(),
    )
    graph.expand_result = Subgraph(nodes=[], edges=[manual_edge])

    explanation = await service.explain_cluster(INVESTIGATION, cluster_id, PRINCIPAL)

    assert len(explanation.pairs) == 1
    pair = explanation.pairs[0]
    assert pair.manually_asserted is True
    assert pair.score == 1.0
    assert pair.model_version is None


async def test_explain_cluster_raises_for_an_unknown_cluster_id() -> None:
    store = FakeWorkingSetStore()
    graph = FakeGraphPort(Subgraph(nodes=[], edges=[]), 0)
    service = WorkingSetService(graph, store, SCHEME)
    await store.add_nodes(INVESTIGATION, [_person("n1")])

    with pytest.raises(ClusterNotFoundError):
        await service.explain_cluster(INVESTIGATION, "no-such-cluster", PRINCIPAL)
