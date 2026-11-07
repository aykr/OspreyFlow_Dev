"""Where a case's writes land (ADR-143 Amendment 1, ADR-099 Amendment 14; the owner's rulings of
7 November 2026).

Each write is driven through its real call site: the principal scoped by `scope_to_case` over a real
`InMemoryDatasetStore`, as `app.get_principal` scopes every request, and the service writing
through the stamping graph the Conduit gives it.

What a mistake here would do, and the case that catches it:

- an entity marked by hand (ADR-098) landing in the source dataset, so promotion and every other
  case reading that source would see it: `test_an_entity_marked_by_hand_is_written_into_the_layer`;
- an analyst's `SAME_AS` or `NOT_SAME_AS` landing in the source:
  `test_a_manual_link_and_a_manual_split_are_written_into_the_layer`;
- accepted proposals and extractions following the analyst's writes into the layer, each through
  its real accept path: `test_an_accepted_extraction_lands_in_the_source_not_the_layer`,
  `test_an_entity_accepted_from_an_email_lands_in_the_source`,
  `test_an_accepted_question_proposal_lands_in_the_source`;
- a composite case's added data landing in one member, which every case reading that member
  would then see: `test_a_composite_cases_write_lands_under_the_composite_id`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from services.api.dataset_scope import (
    analyst_layer,
    made_in,
    outside_any_case,
    scope_to_case,
    set_case_datasets,
    stamping,
)
from services.api.datasets import COMPOSITE, Dataset, InMemoryDatasetStore
from services.api.document_reader import Designation, DocumentReaderService
from services.api.email_extraction import EmailExtractionService, email_document_id
from services.api.questions import InMemoryQuestionStore, QuestionsService
from services.api.review import accept_candidate
from services.api.working_set.service import WorkingSetService
from services.extract.candidates import ExtractionCandidate

from schemas.domain import (
    AuditStub,
    Handling,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
)

from .test_dataset_egress import ADMIN, _as, client  # noqa: F401 (`client` is a fixture)
from .test_email_extraction import (
    ANALYST,
    ONTOLOGY,
    TEXT,
    FakeRecogniser,
    FixedModel,
    InMemoryCandidates,
    RecordingAnalytics,
    WritingGraph,
    _event,
)
from .test_questions import ANSWER
from .test_questions_graph_facts import TrendAnalytics
from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, edge, node

CASE = "inv-1"
UNIT = ANALYST.org_unit
HANDLING = Handling(classification="OFFICIAL", handling_code="P", originator=UNIT, owning_unit=UNIT)


def _dataset(dataset_id: str, **kind: object) -> Dataset:
    return Dataset(
        id=dataset_id,
        name=dataset_id,
        owning_unit=UNIT,
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
        created_by="seed",
        **kind,  # type: ignore[arg-type]
    )


async def _case_reading(store: InMemoryDatasetStore, dataset_id: str) -> Principal:
    await store.set_for_case(CASE, [dataset_id], ANALYST, case_name="Case one")
    return await scope_to_case(ANALYST, CASE, store)


@pytest.fixture(autouse=True)
def _no_case_left_in_scope() -> object:
    yield
    set_case_datasets(None)


@pytest.fixture
def store() -> InMemoryDatasetStore:
    held = InMemoryDatasetStore()
    for dataset_id in ("src", "other"):
        held.add(_dataset(dataset_id))
    held.add(_dataset("both", kind=COMPOSITE, members=["src", "other"]))
    return held


def _in(dataset_id: str, element: Node) -> Node:
    return element.model_copy(update={"datasets": [dataset_id]})


def _document(document_id: str) -> Node:
    return Node(
        id=document_id,
        type="Document",
        properties={"title": "Dabhol", "event_id": "ev-1"},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="m", locator="event:x", excerpt_hash="")],
            first_seen=datetime(2001, 5, 14, tzinfo=UTC),
        ),
        handling=HANDLING,
        audit=AuditStub(created_at=datetime(2001, 5, 14, tzinfo=UTC), created_by="seed"),
        datasets=["src"],
    )


async def test_the_layer_is_held_for_the_request_and_only_inside_a_case(
    store: InMemoryDatasetStore,
) -> None:
    await _case_reading(store, "src")
    layer = await store.layer_of_case(CASE)
    assert layer is not None and analyst_layer() == layer
    outside_any_case(ANALYST)
    assert analyst_layer() is None


async def test_an_entity_marked_by_hand_is_written_into_the_layer(
    store: InMemoryDatasetStore,
) -> None:
    principal = await _case_reading(store, "src")
    layer = await store.layer_of_case(CASE)
    doc = _document(email_document_id("ev-1"))
    working = FakeWorkingSetStore()
    await working.add_nodes(CASE, [_in("src", node("a")), _in("src", node("b")), doc])
    await working.add_edges(CASE, [edge("e1", "a", "b").model_copy(update={"datasets": ["src"]})])
    written = WritingGraph()
    graph = stamping(written)
    reader = DocumentReaderService(
        WorkingSetService(graph, working, SCHEME),
        RecordingAnalytics([_event("ev-1")]),  # type: ignore[arg-type]
        graph,
        InMemoryCandidates(),  # type: ignore[arg-type]
    )
    start = TEXT.index("Dana MERCER")
    result = await reader.designate(
        CASE,
        doc.id,
        Designation(entity_type="Person", text="Dana MERCER", start=start, end=start + 11),
        principal,
    )
    assert written.nodes[result.node_id].datasets == [layer]
    (mention,) = [e for e in written.committed_edges if e.source == result.node_id]
    assert mention.datasets == [layer]
    # The canvas's copy is the stored one, so a reader of the case is sent it.
    assert [n.datasets for n in result.delta.nodes] == [[layer]]


@pytest.mark.parametrize("assertion", ["manual_link", "manual_split"])
async def test_a_manual_link_and_a_manual_split_are_written_into_the_layer(
    store: InMemoryDatasetStore, assertion: str
) -> None:
    principal = await _case_reading(store, "src")
    layer = await store.layer_of_case(CASE)
    people = [_in("src", node("n1")), _in("src", node("n2"))]
    inner = FakeGraphPort(Subgraph(nodes=people, edges=[]))
    working = FakeWorkingSetStore()
    await working.add_nodes(CASE, people)
    service = WorkingSetService(stamping(inner), working, SCHEME)
    await getattr(service, assertion)(CASE, "n1", "n2", principal)
    (written,) = inner.committed_edges
    assert written.datasets == [layer]


async def test_an_accepted_extraction_lands_in_the_source_not_the_layer(
    store: InMemoryDatasetStore,
) -> None:
    """ADR-143 Amendment 1 item 2, through `review.accept_candidate`, the one write every accept
    path shares (`POST .../ingest/candidates/{id}/accept`)."""
    principal = await _case_reading(store, "src")
    candidates = InMemoryCandidates()
    (pending,) = await candidates.store(
        [
            ExtractionCandidate(
                id="cand-1",
                document_id="doc-1",
                entity_type="Person",
                properties={"family_name": "MERCER", "given_names": "Dana"},
                confidence=0.9,
                model="local-model",
                locator="char span 0-11",
                excerpt_hash="",
                handling=HANDLING,
            )
        ],
        principal,
    )
    inner = WritingGraph()
    node_id = await accept_candidate(candidates, stamping(inner), pending.id, principal)  # type: ignore[arg-type]
    assert inner.nodes[node_id].datasets == ["src"]
    assert made_in(principal) == "src"


async def test_the_source_check_fails_with_unnamed_writes_stamped_into_the_layer(
    store: InMemoryDatasetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: the defect in its real shape (the stamping graph giving a write that names no
    dataset the layer, as "all four into the layer" would) is caught by the same check."""
    from services.api import dataset_scope

    monkeypatch.setattr(dataset_scope.DatasetStampingGraph, "_into", lambda self: analyst_layer())
    principal = await _case_reading(store, "src")
    candidates = InMemoryCandidates()
    (pending,) = await candidates.store(
        [
            ExtractionCandidate(
                id="cand-1",
                document_id="doc-1",
                entity_type="Person",
                properties={"family_name": "MERCER", "given_names": "Dana"},
                confidence=0.9,
                model="local-model",
                locator="char span 0-11",
                excerpt_hash="",
                handling=HANDLING,
            )
        ],
        principal,
    )
    inner = WritingGraph()
    node_id = await accept_candidate(candidates, stamping(inner), pending.id, principal)  # type: ignore[arg-type]
    assert inner.nodes[node_id].datasets != ["src"]


async def test_an_entity_accepted_from_an_email_lands_in_the_source(
    store: InMemoryDatasetStore,
) -> None:
    """The same, through `EmailExtractionService.accept` (`.../links/{edge}/events/{event}/extract`
    and its candidate's `accept`)."""
    principal = await _case_reading(store, "src")
    working = FakeWorkingSetStore()
    await working.add_nodes(CASE, [_in("src", node("a")), _in("src", node("b"))])
    await working.add_edges(CASE, [edge("e1", "a", "b").model_copy(update={"datasets": ["src"]})])
    inner = WritingGraph()
    graph = stamping(inner)
    service = EmailExtractionService(
        WorkingSetService(graph, working, SCHEME),
        RecordingAnalytics([_event("ev-1")]),  # type: ignore[arg-type]
        graph,
        ONTOLOGY,
        InMemoryCandidates(),  # type: ignore[arg-type]
        FixedModel(
            {"Person": [{"family_name": "MERCER", "given_names": "Dana", "confidence": 0.9}]}
        ),  # type: ignore[arg-type]
        "local-model",
        recogniser=FakeRecogniser(),
    )
    extracted = await service.extract(CASE, "e1", "ev-1", principal)
    accepted = await service.accept(CASE, "e1", "ev-1", extracted.candidates[0].id, principal)
    assert inner.nodes[accepted.node_id].datasets == ["src"]
    (mention,) = [e for e in inner.committed_edges if e.source == accepted.node_id]
    assert mention.datasets == ["src"]


async def test_an_accepted_question_proposal_lands_in_the_source(
    store: InMemoryDatasetStore,
) -> None:
    """The same, through `QuestionsService.accept` (`.../questions/candidates/{id}/accept`)."""
    principal = await _case_reading(store, "src")
    doc = _document(email_document_id("ev-1"))
    working = FakeWorkingSetStore()
    await working.add_nodes(CASE, [_in("src", node("a")), _in("src", node("b")), doc])
    await working.add_edges(CASE, [edge("e1", "a", "b").model_copy(update={"datasets": ["src"]})])
    inner = WritingGraph()
    graph = stamping(inner)
    candidates = InMemoryCandidates()
    working_set = WorkingSetService(graph, working, SCHEME)
    service = QuestionsService(
        working_set,
        DocumentReaderService(
            working_set,
            RecordingAnalytics([_event("ev-1")]),  # type: ignore[arg-type]
            graph,
            candidates,  # type: ignore[arg-type]
        ),
        graph,
        FixedModel(ANSWER),  # type: ignore[arg-type]
        ONTOLOGY,
        candidates,  # type: ignore[arg-type]
        InMemoryQuestionStore(),
        default_model="local-model",
        analytics=TrendAnalytics([]),  # type: ignore[arg-type]
        datasets=store,
        investigations=None,
    )
    answered = await service.ask(CASE, "Who?", principal)
    person = next(c for c in answered.candidates if c.entity_type == "Person")
    accepted = await service.accept(CASE, person.id, principal)
    assert inner.nodes[accepted.node_id].datasets == ["src"]


async def test_a_composite_cases_write_lands_under_the_composite_id(
    store: InMemoryDatasetStore,
) -> None:
    principal = await _case_reading(store, "both")
    layer = await store.layer_of_case(CASE)
    assert principal.datasets == ["both", "src", "other", layer]
    inner = WritingGraph()
    graph = stamping(inner)
    tx = await graph.begin_transaction()
    (written_id,) = await graph.upsert_nodes([_write("p1")], tx)
    await graph.commit_transaction(tx)
    assert inner.nodes[written_id].datasets == ["both"]
    # A record made in the case (a watch, a saved pattern) belongs to the composite too.
    assert made_in(principal) == "both"


def _write(node_id: str) -> NodeWrite:
    return NodeWrite(
        id=node_id,
        type="Person",
        properties={"family_name": "MERCER", "given_names": "Dana"},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="d", locator="l", excerpt_hash="")],
            first_seen=datetime(2026, 11, 7, tzinfo=UTC),
        ),
        handling=HANDLING,
        created_by=ANALYST.id,
        created_at=datetime(2026, 11, 7, tzinfo=UTC),
    )


# --- a branch shares its parent's layer (the owner's ruling on finding 8, 7 November 2026) -------


async def test_a_branch_of_a_selection_holding_layer_items_still_reads_them(
    store: InMemoryDatasetStore,
) -> None:
    """A branch reads and writes its parent case's layer, not one of its own: what the analyst drew
    in the parent and branched with is still read in the branch. Through the real branch-by-filter
    route, with the real dataset store."""
    from services.api.app import (
        app,
        get_audit,
        get_datasets,
        get_history,
        get_investigations,
        get_principal,
        get_valkey,
        get_working_set,
    )

    from .working_set.test_branch_by_filter import (
        ALICE,
        _FakeInvestigations,
        _Recorder,
        _service,
        _typed,
    )

    await store.set_for_case(CASE, ["src"], ALICE, case_name="Parent")
    layer = await store.layer_of_case(CASE)
    assert layer is not None
    working = FakeWorkingSetStore()
    await working.add_nodes(
        CASE,
        [
            _typed("loaded", "Person").model_copy(update={"datasets": ["src"]}),
            _typed("drawn", "Person").model_copy(update={"datasets": [layer]}),
        ],
    )
    reader = await scope_to_case(ALICE, CASE, store)
    recorder = _Recorder()
    investigations = _FakeInvestigations()
    app.dependency_overrides[get_datasets] = lambda: store
    app.dependency_overrides[get_principal] = lambda: reader
    app.dependency_overrides[get_working_set] = lambda: _service(working)
    app.dependency_overrides[get_audit] = lambda: recorder
    app.dependency_overrides[get_history] = lambda: recorder
    app.dependency_overrides[get_investigations] = lambda: investigations
    app.dependency_overrides[get_valkey] = lambda: recorder
    try:
        from fastapi.testclient import TestClient

        response = TestClient(app).post(
            f"/v1/investigations/{CASE}/branch-by-filter", json={"entity_types": ["Person"]}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 201, response.json()
    branch = response.json()["id"]
    import json

    (published,) = recorder.published
    assert {n["id"] for n in json.loads(published[1])["nodes"]} == {"loaded", "drawn"}
    # The branch reads the parent's layer, so the drawn person it holds is in its world ...
    assert await store.layer_of_case(branch) == layer
    assert await store.ids_of_case(branch) == ["src", layer]
    # ... and writes there: the analyst's own writes in the branch name the parent's layer.
    await scope_to_case(ALICE, branch, store)
    assert analyst_layer() == layer
    # No second layer was made for it.
    assert sum(d.kind == "analyst_layer" for d in store.datasets.values()) == 1


# --- a case with no layer yet (the owner's ruling on finding 7, 7 November 2026) ---------------


async def test_a_case_with_no_layer_is_given_one_and_never_writes_its_marks_in_the_source(
    store: InMemoryDatasetStore,
) -> None:
    """A case the migration has not reached reads its dataset and has no layer. Its analyst's own
    writes go into a layer made for it then, never into the source."""
    store.cases[CASE] = ["src"]  # as a case stood before the layer, with no layer
    assert await store.layer_of_case(CASE) is None
    principal = await scope_to_case(ANALYST, CASE, store)
    layer = await store.layer_of_case(CASE)
    assert layer is not None and store.datasets[layer].owning_unit == UNIT
    assert principal.datasets == ["src", layer]
    people = [_in("src", node("n1")), _in("src", node("n2"))]
    inner = FakeGraphPort(Subgraph(nodes=people, edges=[]))
    working = FakeWorkingSetStore()
    await working.add_nodes(CASE, people)
    await WorkingSetService(stamping(inner), working, SCHEME).manual_link(
        CASE, "n1", "n2", principal
    )
    (written,) = inner.committed_edges
    assert written.datasets == [layer]


# --- a layer's egress cannot be set (ADR-136 Amendment 1) -----------------------------------


def test_an_administrator_setting_a_layers_egress_is_refused_as_a_missing_dataset(
    client: TestClient,  # noqa: F811 (the fixture imported above)
) -> None:
    """ADR-136 Amendment 1: a layer has no egress of its own to set, and the refusal is the one a
    dataset that does not exist gets, so it says nothing of the layer (ADR-143 decision 1)."""
    import asyncio

    _as(ADMIN)
    store: InMemoryDatasetStore = client.store  # type: ignore[attr-defined]
    layer = asyncio.run(store.ensure_layer("case-x", unit=ADMIN.org_unit, created_by="t"))
    as_layer = client.put(f"/v1/admin/datasets/{layer}/egress", json={"egress": "any"})
    as_missing = client.put("/v1/admin/datasets/nobody/egress", json={"egress": "any"})
    assert (as_layer.status_code, as_layer.json()) == (as_missing.status_code, as_missing.json())
    assert as_layer.status_code == 404
    assert store.datasets[layer].egress == "none"
    assert client.audit.records == []  # type: ignore[attr-defined]
