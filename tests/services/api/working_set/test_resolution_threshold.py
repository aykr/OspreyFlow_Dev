"""`WorkingSetService.get_resolution_threshold`/`set_resolution_threshold` —
`spec/03_CONDUIT_MIDDLEWARE.md` §3.5/§4, `spec/01_DOMAIN_MODEL.md` §4. Same no-Valkey/no-ArcadeDB
discipline as `test_service.py`: `FakeWorkingSetStore`/`FakeGraphPort` exercise the service's own
logic, not a real adapter.
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.api.working_set.service import WorkingSetService
from services.resolve.projection import (
    DEFAULT_THRESHOLD,
    THRESHOLD_BALANCED,
    THRESHOLD_BROAD,
    THRESHOLD_STRICT,
)

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
        properties={"score": score},
        provenance=_provenance(),
        handling=_handling(),
        audit=_audit(),
    )


def _not_same_as(node_a: str, node_b: str) -> Edge:
    return Edge(
        id=f"{node_a}-{node_b}-split",
        type="NOT_SAME_AS",
        source=node_a,
        target=node_b,
        properties={},
        provenance=_provenance(),
        handling=_handling(),
        audit=_audit(),
    )


def _endpoint(node_id: str, endpoint_kind: str) -> Node:
    return Node(
        id=node_id,
        type="Endpoint",
        properties={"endpoint_kind": endpoint_kind},
        provenance=_provenance(),
        handling=_handling(),
        audit=_audit(),
    )


def _device(node_id: str) -> Node:
    return Node(
        id=node_id,
        type="Device",
        properties={},
        provenance=_provenance(),
        handling=_handling(),
        audit=_audit(),
    )


def _paired_with(sim_endpoint: str, device: str) -> Edge:
    return Edge(
        id=f"{sim_endpoint}-{device}",
        type="PAIRED_WITH",
        source=sim_endpoint,
        target=device,
        properties={},
        provenance=_provenance(),
        handling=_handling(),
        audit=_audit(),
    )


async def test_get_resolution_threshold_defaults_to_balanced_when_never_set() -> None:
    store = FakeWorkingSetStore()
    service = WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[]), 0), store, SCHEME)
    assert await service.get_resolution_threshold(INVESTIGATION) == DEFAULT_THRESHOLD


async def test_set_resolution_threshold_persists_and_get_reflects_it() -> None:
    store = FakeWorkingSetStore()
    graph = FakeGraphPort(Subgraph(nodes=[], edges=[]), 0)
    service = WorkingSetService(graph, store, SCHEME)
    await store.add_nodes(INVESTIGATION, [_person("n1"), _person("n2")])

    await service.set_resolution_threshold(INVESTIGATION, THRESHOLD_STRICT, PRINCIPAL)

    assert await service.get_resolution_threshold(INVESTIGATION) == THRESHOLD_STRICT


async def test_lowering_the_threshold_merges_and_reports_the_delta() -> None:
    store = FakeWorkingSetStore()
    same_as = _same_as("n1", "n2", 0.85)  # below Strict, above Broad
    graph = FakeGraphPort(Subgraph(nodes=[_person("n1"), _person("n2")], edges=[same_as]), 0)
    service = WorkingSetService(graph, store, SCHEME)
    await store.add_nodes(INVESTIGATION, [_person("n1"), _person("n2")])
    await store.set_threshold(INVESTIGATION, THRESHOLD_STRICT)  # starts strict: not merged

    delta = await service.set_resolution_threshold(INVESTIGATION, THRESHOLD_BROAD, PRINCIPAL)

    assert delta.op == "reproject"
    assert delta.merged == 1
    assert delta.split == 0
    assert delta.affected == 2

    nodes = await store.source_fidelity_nodes(INVESTIGATION)
    assert nodes["n1"].resolution.cluster_id == nodes["n2"].resolution.cluster_id


async def test_raising_the_threshold_splits_and_reports_the_delta() -> None:
    store = FakeWorkingSetStore()
    same_as = _same_as("n1", "n2", 0.85)
    graph = FakeGraphPort(Subgraph(nodes=[_person("n1"), _person("n2")], edges=[same_as]), 0)
    service = WorkingSetService(graph, store, SCHEME)
    await store.add_nodes(INVESTIGATION, [_person("n1"), _person("n2")])
    await store.set_threshold(INVESTIGATION, THRESHOLD_BROAD)  # starts broad: merged

    delta = await service.set_resolution_threshold(INVESTIGATION, THRESHOLD_STRICT, PRINCIPAL)

    assert delta.merged == 0
    assert delta.split == 1
    assert delta.affected == 2

    nodes = await store.source_fidelity_nodes(INVESTIGATION)
    assert nodes["n1"].resolution.cluster_id != nodes["n2"].resolution.cluster_id


async def test_a_manual_split_survives_even_at_a_broad_threshold() -> None:
    """`01_DOMAIN_MODEL.md` §4: "a manual split... the projection always honours and no future
    resolution run may override" — even a near-certain `SAME_AS` score never merges a pair with a
    `NOT_SAME_AS` edge between them, at any threshold this test tries."""
    store = FakeWorkingSetStore()
    edges = [_same_as("n1", "n2", 0.999), _not_same_as("n1", "n2")]
    graph = FakeGraphPort(Subgraph(nodes=[_person("n1"), _person("n2")], edges=edges), 0)
    service = WorkingSetService(graph, store, SCHEME)
    await store.add_nodes(INVESTIGATION, [_person("n1"), _person("n2")])

    await service.set_resolution_threshold(INVESTIGATION, THRESHOLD_BROAD, PRINCIPAL)

    nodes = await store.source_fidelity_nodes(INVESTIGATION)
    assert nodes["n1"].resolution.cluster_id != nodes["n2"].resolution.cluster_id


async def test_no_change_reports_a_zero_delta() -> None:
    store = FakeWorkingSetStore()
    graph = FakeGraphPort(Subgraph(nodes=[], edges=[]), 0)
    service = WorkingSetService(graph, store, SCHEME)
    await store.add_nodes(INVESTIGATION, [_person("n1"), _person("n2")])

    delta = await service.set_resolution_threshold(INVESTIGATION, DEFAULT_THRESHOLD, PRINCIPAL)

    assert delta.merged == 0
    assert delta.split == 0
    assert delta.affected == 0


async def test_msisdn_and_imsi_endpoints_cluster_together_the_device_does_not() -> None:
    """`08_ACCEPTANCE_SCENARIOS.md` B15 / `06_DECISIONS.md` ADR-023's own layering addendum:
    `compute_clusters` "collapses, never merges" — this proves the *cluster assignment* a `SAME_AS`
    between an `msisdn` `Endpoint` and its `imsi` `Endpoint` produces at the projection layer,
    which is as far as this layer's own claim goes. It is not a claim about what the Glass renders
    (`services/resolve/projection.py`'s own docstring: that's a rendering question for that tier,
    still Phase 6a's unbuilt work) — only that the two `Endpoint`s land in one `ClusterId` and the
    `Device` they're paired to, which carries no `SAME_AS` edge of its own, does not join it."""
    store = FakeWorkingSetStore()
    same_as = _same_as("sim-msisdn", "sim-imsi", 1.0)
    paired_with = _paired_with("sim-imsi", "device-1")
    graph = FakeGraphPort(
        Subgraph(
            nodes=[
                _endpoint("sim-msisdn", "msisdn"),
                _endpoint("sim-imsi", "imsi"),
                _device("device-1"),
            ],
            edges=[same_as, paired_with],
        ),
        0,
    )
    service = WorkingSetService(graph, store, SCHEME)
    await store.add_nodes(
        INVESTIGATION,
        [
            _endpoint("sim-msisdn", "msisdn"),
            _endpoint("sim-imsi", "imsi"),
            _device("device-1"),
        ],
    )

    await service.set_resolution_threshold(INVESTIGATION, THRESHOLD_BALANCED, PRINCIPAL)

    nodes = await store.source_fidelity_nodes(INVESTIGATION)
    assert nodes["sim-msisdn"].resolution.cluster_id == nodes["sim-imsi"].resolution.cluster_id
    assert nodes["device-1"].resolution.cluster_id != nodes["sim-imsi"].resolution.cluster_id
