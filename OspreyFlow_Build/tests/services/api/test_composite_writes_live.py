"""ADR-099 Amendment 15 at a real call site, against real ArcadeDB (the third review of L3.1).

`EmailExtractionService` writes an email's Document by a fixed id (`email:{event_id}`). Under a case
reading a composite whose member already holds that Document (the seeded Enron and Fixture Corp
composite is exactly this), the composite case's write becomes the composite's own copy of it. The
links the service writes beside it, and the copy it puts on the canvas, must name that copy, not the
member's Document; and extracting again must add nothing (a fixed id is a promise of idempotence).

What a mistake here would do, and the case that catches it:

- the `MENTIONED_IN` links (or the canvas copy) naming the member's Document, so the member's
  Document gains links a member-only case then reads, or the canvas holds a node the case's write
  never made: `test_an_email_extracted_in_a_composite_case_is_written_as_the_composites_copy`;
- a second extraction making a second copy and a second `SAME_AS`:
  `test_extracting_the_same_email_again_adds_nothing`.

Both were red before this fix: the copy had a fresh id each time, and the writer used the id it
asked for.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from services.api.dataset_scope import scope_to_case, set_case_datasets, stamping
from services.api.datasets import COMPOSITE, Dataset, InMemoryDatasetStore
from services.api.email_extraction import EmailExtractionService, email_document_id
from services.api.working_set.service import WorkingSetService

from adapters.graph_arcadedb.testing import arcadedb_adapter
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Principal

from .test_email_extraction import (
    ANALYST,
    FakeRecogniser,
    FixedModel,
    InMemoryCandidates,
    RecordingAnalytics,
    _event,
)
from .working_set.fakes import FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, edge, node

CASE = "inv-1"  # the event fixture's case
MEMBER, OTHER, BOTH = "enron-like", "fixture-like", "both-like"
MEMBER_ONLY = Principal(
    id="member-reader", clearance="OFFICIAL", org_unit=ANALYST.org_unit, datasets=[MEMBER]
)
DOCUMENT = email_document_id("ev-1")


def _dataset(dataset_id: str, **kind: object) -> Dataset:
    return Dataset(
        id=dataset_id,
        name=dataset_id,
        owning_unit=ANALYST.org_unit,
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
        created_by="seed",
        **kind,  # type: ignore[arg-type]
    )


async def _composite_case() -> InMemoryDatasetStore:
    store = InMemoryDatasetStore()
    store.add(_dataset(MEMBER))
    store.add(_dataset(OTHER))
    store.add(_dataset(BOTH, kind=COMPOSITE, members=[MEMBER, OTHER]))
    await store.set_for_case(CASE, [BOTH], ANALYST, case_name="Both")
    return store


async def _service(adapter: Any) -> tuple[EmailExtractionService, Any]:
    """The service as the Conduit builds it, over the stamping graph, with the member already
    holding the email's Document and the two people the email is between."""
    graph = stamping(adapter, scheme=load_uk_le_scheme())
    working = FakeWorkingSetStore()
    await working.add_nodes(CASE, [_in(node("a")), _in(node("b"))])
    await working.add_edges(CASE, [edge("e1", "a", "b").model_copy(update={"datasets": [MEMBER]})])
    service = EmailExtractionService(
        WorkingSetService(graph, working, SCHEME),
        RecordingAnalytics([_event("ev-1")]),  # type: ignore[arg-type]
        graph,
        load_default_ontology(),
        InMemoryCandidates(),  # type: ignore[arg-type]
        FixedModel({"Person": []}),  # type: ignore[arg-type]
        "local-model",
        recogniser=FakeRecogniser(),
    )
    # What the member's own case wrote earlier: the people, and the Document by its fixed id.
    member_doc, _ = service._document_writes(_event("ev-1"), ANALYST, datetime.now(UTC))
    people = [node(n).model_copy(update={"datasets": [MEMBER]}) for n in ("a", "b")]
    tx = await adapter.begin_transaction()
    await adapter.upsert_nodes(
        [_as_write(p) for p in people] + [member_doc.model_copy(update={"datasets": [MEMBER]})],
        tx,
    )
    await adapter.commit_transaction(tx)
    return service, graph


def _in(element: Any) -> Any:
    return element.model_copy(update={"datasets": [MEMBER]})


def _as_write(person: Any) -> Any:
    from schemas.domain import NodeWrite

    return NodeWrite(
        id=person.id,
        type=person.type,
        properties={"family_name": person.id.upper()},
        provenance=person.provenance,
        handling=person.handling,
        created_by=person.audit.created_by,
        created_at=person.audit.created_at,
        datasets=person.datasets,
    )


async def _extract(service: EmailExtractionService, store: InMemoryDatasetStore) -> Any:
    principal = await scope_to_case(ANALYST, CASE, store)
    try:
        return await service.extract(CASE, "e1", "ev-1", principal, using="recogniser")
    finally:
        set_case_datasets(None)


async def test_an_email_extracted_in_a_composite_case_is_written_as_the_composites_copy() -> None:
    store = await _composite_case()
    async with arcadedb_adapter(load_default_ontology(), load_uk_le_scheme()) as adapter:
        service, _ = await _service(adapter)
        before = await adapter.neighbourhood_stats(DOCUMENT, MEMBER_ONLY)
        result = await _extract(service, store)

        copy = result.document_id
        assert copy != DOCUMENT
        reader = await scope_to_case(ANALYST, CASE, store)
        held = await adapter.get_node(copy, reader)
        assert held is not None and held.datasets == [BOTH]
        # The links the service wrote name the copy, and the canvas holds the copy.
        among = await adapter.edges_among(["a", "b", copy, DOCUMENT], reader)
        mentions = {(e.source, e.target) for e in among if e.type == "MENTIONED_IN"}
        assert mentions == {("a", copy), ("b", copy)}
        assert [(e.type, e.source, e.target) for e in among if e.type == "SAME_AS"] == [
            ("SAME_AS", copy, DOCUMENT)
        ]
        assert [n.id for n in result.delta.nodes] == [copy]
        # The member's Document is exactly as it was for a member-only case.
        assert await adapter.neighbourhood_stats(DOCUMENT, MEMBER_ONLY) == before
        member_doc = await adapter.get_node(DOCUMENT, MEMBER_ONLY)
        assert member_doc is not None and member_doc.datasets == [MEMBER]
        set_case_datasets(None)


async def test_extracting_the_same_email_again_adds_nothing() -> None:
    store = await _composite_case()
    async with arcadedb_adapter(load_default_ontology(), load_uk_le_scheme()) as adapter:
        service, _ = await _service(adapter)
        first = await _extract(service, store)
        reader = await scope_to_case(ANALYST, CASE, store)
        counted = await adapter.type_counts(reader)
        second = await _extract(service, store)
        assert second.document_id == first.document_id
        reader = await scope_to_case(ANALYST, CASE, store)
        assert await adapter.type_counts(reader) == counted
        set_case_datasets(None)
