"""What a request reads and writes into (`06_DECISIONS.md` ADR-099 decisions 4 to 6).

What a mistake here would do, and the case that catches it:

- a request outside a case reading unlimited would search every dataset again, as the owner
  reported (`test_outside_a_case_a_request_reads_no_dataset`);
- a case's request reading another case's datasets
  (`test_a_case_request_reads_that_cases_datasets`);
- something the Conduit writes for a case vanishing from it as it is written
  (`test_a_write_made_for_a_case_belongs_to_its_dataset`);
- a write that names its datasets being restamped
  (`test_a_write_that_names_its_datasets_keeps_them`);
- a stored body of another dataset reaching a case through the working set's own projection,
  which is not a graph read
  (`test_the_working_sets_projection_leaves_out_another_datasets_node_and_link`).

These run the real `get_principal` through FastAPI, with only the token resolver and the dataset
store standing in, because the case's datasets reach the write through a context variable set in
that dependency: a test of the parts alone could not show it arrives.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from services.api.app import PrincipalDep
from services.api.dataset_scope import DatasetStampingGraph, case_datasets
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.working_set.models import DeltaAdd
from services.api.working_set.service import WorkingSetService

from schemas.domain import (
    AuditStub,
    Edge,
    EdgeWrite,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

from .working_set.fakes import FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "u",
    "owning_unit": "u",
}
PROVENANCE = Provenance(
    state=ProvenanceState.ASSERTED,
    sources=[SourceRef(document_id="d", locator="p.1", excerpt_hash="a" * 64)],
    first_seen=datetime(2026, 1, 1, tzinfo=UTC),
)


class _Resolver:
    def resolve(self, token: str) -> Principal:
        return ANALYST


class _RecordingGraph:
    def __init__(self) -> None:
        self.nodes: list[NodeWrite] = []
        self.edges: list[EdgeWrite] = []

    async def upsert_nodes(self, nodes: list[NodeWrite], tx: Any) -> list[str]:
        self.nodes.extend(nodes)
        return [n.id for n in nodes]

    async def upsert_edges(self, edges: list[EdgeWrite], tx: Any) -> list[str]:
        self.edges.extend(edges)
        return [e.id for e in edges]


def _write(node_id: str, datasets: list[str] | None = None) -> NodeWrite:
    return NodeWrite(
        id=node_id,
        type="Person",
        properties={"family_name": "X"},
        provenance=PROVENANCE,
        handling=HANDLING,  # type: ignore[arg-type]
        created_by="analyst-1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        datasets=datasets or [],
    )


@pytest.fixture
def probe() -> tuple[TestClient, _RecordingGraph]:
    store = InMemoryDatasetStore()
    for dataset_id in ("fixture", "enron"):
        store.add(
            Dataset(
                id=dataset_id,
                name=dataset_id,
                owning_unit="unit-1",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                created_by="seed",
            )
        )
    store.cases["case-f"] = ["fixture"]
    store.cases["case-both"] = ["enron", "fixture"]
    inner = _RecordingGraph()
    graph = DatasetStampingGraph(inner)  # type: ignore[arg-type]

    app = FastAPI()
    app.state.principal_resolver = _Resolver()
    app.state.datasets = store

    @app.get("/v1/investigations/{investigation_id}/probe")
    async def in_a_case(investigation_id: str, principal: PrincipalDep) -> dict[str, Any]:
        return {"datasets": principal.datasets, "writes_into": case_datasets()}

    @app.post("/v1/investigations/{investigation_id}/probe")
    async def write_in_a_case(investigation_id: str, principal: PrincipalDep) -> dict[str, Any]:
        await graph.upsert_nodes([_write("plain"), _write("named", ["enron"])], "tx")
        return {}

    @app.get("/v1/probe")
    async def outside(principal: PrincipalDep) -> dict[str, Any]:
        return {"datasets": principal.datasets, "writes_into": case_datasets()}

    @app.post("/v1/probe")
    async def write_outside(principal: PrincipalDep) -> dict[str, Any]:
        await graph.upsert_nodes([_write("outside")], "tx")
        return {}

    client = TestClient(app, headers={"Authorization": "Bearer token"})
    return client, inner


def test_outside_a_case_a_request_reads_no_dataset(probe) -> None:  # type: ignore[no-untyped-def]
    client, _ = probe
    assert client.get("/v1/probe").json() == {"datasets": [], "writes_into": None}


def test_a_case_request_reads_that_cases_datasets(probe) -> None:  # type: ignore[no-untyped-def]
    client, _ = probe
    assert client.get("/v1/investigations/case-f/probe").json()["datasets"] == ["fixture"]
    both = client.get("/v1/investigations/case-both/probe").json()
    assert both == {"datasets": ["enron", "fixture"], "writes_into": ["enron", "fixture"]}
    # A case with no datasets recorded reads nothing, not everything.
    assert client.get("/v1/investigations/case-unknown/probe").json()["datasets"] == []


def test_a_write_made_for_a_case_belongs_to_its_dataset(probe) -> None:  # type: ignore[no-untyped-def]
    client, inner = probe
    client.post("/v1/investigations/case-f/probe")
    assert {n.id: n.datasets for n in inner.nodes}["plain"] == ["fixture"]


def test_a_write_that_names_its_datasets_keeps_them(probe) -> None:  # type: ignore[no-untyped-def]
    client, inner = probe
    client.post("/v1/investigations/case-f/probe")
    assert {n.id: n.datasets for n in inner.nodes}["named"] == ["enron"]


def test_a_write_outside_any_case_is_not_stamped(probe) -> None:  # type: ignore[no-untyped-def]
    client, inner = probe
    client.post("/v1/probe")
    assert {n.id: n.datasets for n in inner.nodes}["outside"] == []


def _node(node_id: str, datasets: list[str]) -> Node:
    return Node(
        id=node_id,
        type="Person",
        provenance=PROVENANCE,
        handling=HANDLING,  # type: ignore[arg-type]
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="loader"),
        datasets=datasets,
    )


def _edge(edge_id: str, source: str, target: str, datasets: list[str]) -> Edge:
    return Edge(
        id=edge_id,
        type="ASSOCIATE_OF",
        source=source,
        target=target,
        provenance=PROVENANCE,
        handling=HANDLING,  # type: ignore[arg-type]
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="loader"),
        datasets=datasets,
    )


def test_the_working_sets_projection_leaves_out_another_datasets_node_and_link() -> None:
    """The delta stream and a reconnect re-project stored bodies without a graph read, so the
    third axis is applied there too (`ontology.handling.principal_may_read`)."""
    service = WorkingSetService(None, FakeWorkingSetStore(), SCHEME)  # type: ignore[arg-type]
    both = ["enron", "fixture"]
    delta = DeltaAdd(
        seq=1,
        nodes=[_node("shared", both), _node("mine", ["fixture"]), _node("theirs", ["enron"])],
        edges=[
            _edge("e-mine", "shared", "mine", ["fixture"]),
            _edge("e-to-theirs", "shared", "theirs", ["fixture"]),
            _edge("e-theirs", "shared", "mine", ["enron"]),
        ],
    )
    in_fixture = ANALYST.model_copy(update={"datasets": ["fixture"]})
    projected, hidden = service.project_delta(delta, in_fixture)
    assert isinstance(projected, DeltaAdd)
    assert {n.id for n in projected.nodes} == {"shared", "mine"}
    assert {e.id for e in projected.edges} == {"e-mine"}
    assert hidden == 3
    unlimited, _ = service.project_delta(delta, ANALYST)
    assert isinstance(unlimited, DeltaAdd) and len(unlimited.nodes) == 3


async def test_what_the_conduit_writes_onto_a_canvas_is_in_the_cases_dataset_there_too() -> None:
    """Seen on the owner's deployment: emails put on the canvas were in the Enron dataset in the
    graph but in none in the working set's copy, which the canvas is drawn from, so a reload or a
    live push held them back as hidden. `add_written` is the one way a Conduit write reaches a
    canvas, so it stamps the copy as `DatasetStampingGraph` stamps the write."""
    from services.api.dataset_scope import set_case_datasets

    store = FakeWorkingSetStore()
    service = WorkingSetService(None, store, SCHEME)  # type: ignore[arg-type]
    set_case_datasets(["enron", "fixture"])
    try:
        await service.add_written(
            "case-e",
            [_node("email:1", []), _node("named", ["fixture"])],
            [_edge("m1", "email:1", "named", [])],
        )
    finally:
        set_case_datasets(None)
    nodes = await store.source_fidelity_nodes("case-e")
    assert {n.id: n.datasets for n in nodes.values()} == {
        "email:1": ["enron"],
        "named": ["fixture"],
    }
    (link,) = (await store.source_fidelity_edges("case-e")).values()
    assert link.datasets == ["enron"]
    in_enron = ANALYST.model_copy(update={"datasets": ["enron"]})
    visible, _ = await service.visible_membership("case-e", in_enron)
    assert "email:1" in {n.id for n in visible}
