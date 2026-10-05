"""The full-screen reader's text (ADR-092 decision 5). The service's own rule, against
`FakeWorkingSetStore` and the stand-ins `test_email_extraction.py` already keeps honest.

What a mistake here would do, and the case that catches it:

- a Document the caller cannot see would have its text read out
  (`test_a_hidden_document_and_a_missing_one_refuse_alike`);
- an email nobody had extracted from would open blank, its text being in the event, not the
  document store (`test_an_email_not_yet_extracted_reads_from_its_event`);
- an extracted document would lose its marked entities
  (`test_a_document_with_stored_text_reads_it_with_its_spans`).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.document_reader import DocumentReaderService
from services.api.email_extraction import email_document_id
from services.api.review import DocumentNotFoundError
from services.api.working_set.service import WorkingSetService

from schemas.domain import AuditStub, Node, Provenance, ProvenanceState, SourceRef

from .test_email_extraction import (
    ANALYST,
    HANDLING,
    TEXT,
    InMemoryCandidates,
    RecordingAnalytics,
    WritingGraph,
    _event,
)
from .working_set.fakes import FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, edge, node


def _document(document_id: str, classification: str = "OFFICIAL", **props: object) -> Node:
    return Node(
        id=document_id,
        type="Document",
        properties={"title": "Dabhol", **props},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="m", locator="event:x", excerpt_hash="")],
            first_seen=datetime(2001, 5, 14, tzinfo=UTC),
        ),
        handling=HANDLING.model_copy(update={"classification": classification}),
        audit=AuditStub(created_at=datetime(2001, 5, 14, tzinfo=UTC), created_by="analyst-1"),
    )


async def _reader(
    documents: list[Node], candidates: InMemoryCandidates | None = None
) -> DocumentReaderService:
    working = FakeWorkingSetStore()
    await working.add_nodes("inv-1", [node("a"), node("b"), *documents])
    await working.add_edges("inv-1", [edge("e1", "a", "b")])
    graph = WritingGraph()
    return DocumentReaderService(
        WorkingSetService(graph, working, SCHEME),
        RecordingAnalytics([_event("ev-1")]),  # type: ignore[arg-type]
        graph,
        candidates or InMemoryCandidates(),  # type: ignore[arg-type]
    )


async def test_an_email_not_yet_extracted_reads_from_its_event() -> None:
    doc = _document(email_document_id("ev-1"), event_id="ev-1")
    reader = await _reader([doc])
    view = await reader.read("inv-1", doc.id, ANALYST)
    assert view.text == TEXT
    assert view.spans == []
    # What *Extract entities* needs, from the event itself.
    assert (view.event_id, view.edge_id) == ("ev-1", "e1")
    assert (view.sender_id, view.recipient_id) == ("a", "b")
    assert view.title == "Dabhol"


async def test_a_document_with_stored_text_reads_it_with_its_spans() -> None:
    doc = _document("doc-1")
    candidates = InMemoryCandidates()
    candidates.texts["doc-1"] = ("Stored text of the report.", "unit-1")
    reader = await _reader([doc], candidates)
    view = await reader.read("inv-1", "doc-1", ANALYST)
    assert view.text == "Stored text of the report."
    assert view.event_id is None


async def test_a_document_with_no_text_reads_empty_rather_than_failing() -> None:
    reader = await _reader([_document("doc-1")])
    view = await reader.read("inv-1", "doc-1", ANALYST)
    assert view.text == ""


@pytest.mark.parametrize("document_id", ["secret-doc", "no-such-doc", "a"])
async def test_a_hidden_document_and_a_missing_one_refuse_alike(document_id: str) -> None:
    """A SECRET Document, one not in the case, and a node that is not a Document at all."""
    reader = await _reader([_document("secret-doc", "SECRET", event_id="ev-1")])
    with pytest.raises(DocumentNotFoundError) as refused:
        await reader.read("inv-1", document_id, ANALYST)
    assert str(refused.value) == str(DocumentNotFoundError(document_id))


async def test_another_units_stored_text_is_not_read() -> None:
    """The stored text answers only to its owning unit; the event still gives an email's text."""
    doc = _document(email_document_id("ev-1"), event_id="ev-1")
    candidates = InMemoryCandidates()
    candidates.texts[doc.id] = ("Another unit's copy.", "unit-9")
    reader = await _reader([doc], candidates)
    assert (await reader.read("inv-1", doc.id, ANALYST)).text == TEXT


async def test_an_inbound_email_is_from_the_far_end_as_the_inspector_says() -> None:
    """The event's link runs a→b; an inbound email on it was sent by b, as the Inspector's From
    reads it, so the reader must not say a."""
    doc = _document(email_document_id("ev-1"), event_id="ev-1")
    reader = await _reader([doc])
    reader._analytics.events = [  # type: ignore[attr-defined]
        _event("ev-1").model_copy(update={"direction": "inbound"})
    ]
    view = await reader.read("inv-1", doc.id, ANALYST)
    assert (view.sender_id, view.recipient_id) == ("b", "a")


async def test_a_held_text_document_reads_its_kept_text_and_says_its_kind() -> None:
    """ADR-094: a Document written from content an entity holds keeps its text in the media
    store."""
    from adapters.media_objectstore.testing import InMemoryMediaStore

    media = InMemoryMediaStore()
    ref = await media.put(b"Shopping list: tape, ten bags.", "text/plain")
    doc = _document("content:1", media_kind="text", object_ref=ref)
    reader = await _reader([doc])
    reader._media = media  # type: ignore[attr-defined]
    view = await reader.read("inv-1", "content:1", ANALYST)
    assert view.text == "Shopping list: tape, ten bags."
    assert (view.media_kind, view.has_file) == ("text", True)


async def test_an_image_document_says_it_has_a_file_and_no_text_until_extracted() -> None:
    from adapters.media_objectstore.testing import InMemoryMediaStore

    media = InMemoryMediaStore()
    ref = await media.put(b"\x89PNG", "image/png")
    reader = await _reader([_document("content:2", media_kind="image", object_ref=ref)])
    reader._media = media  # type: ignore[attr-defined]
    view = await reader.read("inv-1", "content:2", ANALYST)
    assert (view.media_kind, view.has_file, view.text) == ("image", True, "")
