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
- everything else (accepted proposals and extractions, a Studio load) following the analyst's
  writes into the layer: `test_a_write_naming_no_dataset_still_lands_in_the_source`;
- a composite case's added data landing in one member, which every case reading that member
  would then see: `test_a_composite_cases_write_lands_under_the_composite_id`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
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
from services.api.email_extraction import email_document_id
from services.api.working_set.service import WorkingSetService

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

from .test_email_extraction import (
    ANALYST,
    TEXT,
    InMemoryCandidates,
    RecordingAnalytics,
    WritingGraph,
    _event,
)
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


async def test_a_write_naming_no_dataset_still_lands_in_the_source(
    store: InMemoryDatasetStore,
) -> None:
    """Accepted question proposals, accepted extractions and loads name no dataset; the ruling keeps
    them in the source, the case's first."""
    principal = await _case_reading(store, "src")
    inner = WritingGraph()
    graph = stamping(inner)
    tx = await graph.begin_transaction()
    (written_id,) = await graph.upsert_nodes([_write("p1")], tx)
    await graph.commit_transaction(tx)
    assert inner.nodes[written_id].datasets == ["src"]
    assert made_in(principal) == "src"


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
