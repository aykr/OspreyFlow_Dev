"""Rule 4 for the analyst's own writes (ADR-143 Amendment 1), against real Postgres (`make dev-up`,
under the stack lease): an entity marked by hand in case A is in A's analyst layer, and nothing of
it reaches case B, which reads the same source in the same unit.

The lane-reviewer's blocker 1 on L3.1: `designate` keeps the marking as an accepted extraction
candidate (the marked words, the node's id, `analyst:<id>`), and the candidate store was scoped by
unit alone, so `GET /v1/investigations/{B}/ingest/candidates` handed case B what case A marked. Each
end is driven at its real call site: `DocumentReaderService.designate` with the Postgres candidate
store, and the store's two reads with a principal scoped by `scope_to_case`, as the route has it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from services.api.config import PostgresConfig
from services.api.dataset_scope import scope_to_case, set_case_datasets, stamping
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.document_reader import Designation, DocumentReaderService
from services.api.email_extraction import email_document_id
from services.api.review import ExtractionCandidateNotFoundError, ExtractionCandidateStore
from services.api.working_set.service import WorkingSetService

from conduit_common.identity import new_id
from schemas.domain import Principal

from .test_case_writes import _document, _in
from .test_email_extraction import ANALYST, TEXT, RecordingAnalytics, WritingGraph, _event
from .working_set.fakes import FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, edge, node

CASE_A, CASE_B = "inv-1", "case-b"  # the event fixture is scoped to "inv-1"
#: A member of case B only: same unit, same clearance, reading the same source.
B_MEMBER = Principal(id="analyst-b", clearance="OFFICIAL", org_unit=ANALYST.org_unit)


@pytest.fixture
async def candidates() -> AsyncIterator[ExtractionCandidateStore]:
    store = await ExtractionCandidateStore.connect(PostgresConfig.from_env().dsn)
    yield store
    await store.close()
    set_case_datasets(None)


async def _datasets() -> InMemoryDatasetStore:
    held = InMemoryDatasetStore()
    held.add(
        Dataset(
            id="src",
            name="src",
            owning_unit=ANALYST.org_unit,
            created_at=datetime(2026, 11, 1, tzinfo=UTC),
            created_by="seed",
        )
    )
    for case in (CASE_A, CASE_B):
        await held.set_for_case(case, ["src"], ANALYST, case_name=case)
    return held


async def test_a_mark_made_in_case_a_is_not_read_under_case_b(
    candidates: ExtractionCandidateStore,
) -> None:
    datasets = await _datasets()
    event = f"ev-{new_id()}"
    doc = _document(email_document_id(event))
    doc = doc.model_copy(update={"properties": {**doc.properties, "event_id": event}})
    working = FakeWorkingSetStore()
    await working.add_nodes(CASE_A, [_in("src", node("a")), _in("src", node("b")), doc])
    await working.add_edges(CASE_A, [edge("e1", "a", "b").model_copy(update={"datasets": ["src"]})])
    graph = stamping(WritingGraph())
    reader = DocumentReaderService(
        WorkingSetService(graph, working, SCHEME),
        RecordingAnalytics([_event(event)]),  # type: ignore[arg-type]
        graph,
        candidates,
    )
    as_a = await scope_to_case(ANALYST, CASE_A, datasets)
    start = TEXT.index("Dana MERCER")
    await reader.designate(
        CASE_A,
        doc.id,
        Designation(entity_type="Person", text="Dana MERCER", start=start, end=start + 11),
        as_a,
    )
    (mark,) = await candidates.list_for_document(doc.id, as_a)

    as_b = await scope_to_case(B_MEMBER, CASE_B, datasets)
    assert await candidates.list_for_document(doc.id, as_b) == []
    with pytest.raises(ExtractionCandidateNotFoundError):
        await candidates.get_authorized(mark.id, as_b)
    # The author of the mark, under case B, is refused alike: the case decides, not the person.
    as_a_in_b = await scope_to_case(ANALYST, CASE_B, datasets)
    assert await candidates.list_for_document(doc.id, as_a_in_b) == []
    # Kept with the layer it was written in.
    assert mark.dataset_id == await datasets.layer_of_case(CASE_A)
