"""A composite is read-only for now (ADR-099 Amendment 15; the owner's ruling of 7 November 2026),
against real ArcadeDB: two of its write paths, driven at their real call sites in the seeded Enron
and Fixture Corp shape (a case reading a composite whose member already holds the data).

- extracting an email: refused before anything is written, the member's Document exactly as it
  was (`test_an_email_is_not_extracted_in_a_composite_case_and_the_member_is_unchanged`);
- an entity's picture: neither replaced nor removed, and no file stored for the refused one
  (`test_a_picture_is_neither_replaced_nor_removed_in_a_composite_case`).

Each was a write that changed a member before the ruling (the fourth and fifth reviews); the
in-memory proofs, with each refusal planted out, are in `test_composite_read_only.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.dataset_scope import (
    CompositeReadOnlyError,
    scope_to_case,
    set_case_datasets,
    stamping,
)
from services.api.datasets import COMPOSITE, Dataset, InMemoryDatasetStore
from services.api.email_extraction import EmailExtractionService, email_document_id
from services.api.working_set.service import WorkingSetService

from adapters.graph_arcadedb.testing import arcadedb_adapter
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Handling, NodeWrite, Principal, Provenance, ProvenanceState, SourceRef

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
HANDLING = Handling(
    classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
)


@pytest.fixture(autouse=True)
def _no_case_left_in_scope() -> object:
    yield
    set_case_datasets(None)


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
    store.cases["member-case"] = [MEMBER]
    return store


def _held_by_the_member(node_id: str, node_type: str = "Person") -> NodeWrite:
    return NodeWrite(
        id=node_id,
        type=node_type,
        properties={"family_name": node_id.upper()} if node_type == "Person" else {},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="d", locator="l", excerpt_hash="")],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        handling=HANDLING,
        created_by="seed",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        datasets=[MEMBER],
    )


async def test_an_email_is_not_extracted_in_a_composite_case_and_the_member_is_unchanged() -> None:
    store = await _composite_case()
    async with arcadedb_adapter(load_default_ontology(), load_uk_le_scheme()) as adapter:
        graph = stamping(adapter, registry=store)
        working = FakeWorkingSetStore()
        people = [node(n).model_copy(update={"datasets": [MEMBER]}) for n in ("a", "b")]
        await working.add_nodes(CASE, people)
        await working.add_edges(
            CASE, [edge("e1", "a", "b").model_copy(update={"datasets": [MEMBER]})]
        )
        candidates = InMemoryCandidates()
        service = EmailExtractionService(
            WorkingSetService(graph, working, SCHEME),
            RecordingAnalytics([_event("ev-1")]),  # type: ignore[arg-type]
            graph,
            load_default_ontology(),
            candidates,  # type: ignore[arg-type]
            FixedModel({"Person": [{"family_name": "MERCER", "confidence": 0.9}]}),  # type: ignore[arg-type]
            "local-model",
            recogniser=FakeRecogniser(),
        )
        # What the member's own case wrote earlier: the people, and the email's Document.
        member_doc, _ = service._document_writes(_event("ev-1"), ANALYST, datetime.now(UTC))  # noqa: SLF001
        tx = await adapter.begin_transaction()
        await adapter.upsert_nodes(
            [
                _held_by_the_member("a"),
                _held_by_the_member("b"),
                member_doc.model_copy(update={"datasets": [MEMBER]}),
            ],
            tx,
        )
        await adapter.commit_transaction(tx)
        before = await adapter.neighbourhood_stats(DOCUMENT, MEMBER_ONLY)
        held = await adapter.get_node(DOCUMENT, MEMBER_ONLY)

        principal = await scope_to_case(ANALYST, CASE, store)
        with pytest.raises(CompositeReadOnlyError, match="do this in a case that reads"):
            await service.extract(CASE, "e1", "ev-1", principal)
        set_case_datasets(None)

        assert await adapter.neighbourhood_stats(DOCUMENT, MEMBER_ONLY) == before
        assert await adapter.get_node(DOCUMENT, MEMBER_ONLY) == held
        assert candidates.records == {} and candidates.texts == {}


async def test_a_picture_is_neither_replaced_nor_removed_in_a_composite_case() -> None:
    """Set first in a case reading the member; in the composite case, replacing and removing it are
    refused before any file is stored, and the member's picture is exactly as it was."""
    from services.api.entity_pictures import EntityPictureService

    from adapters.media_objectstore.testing import InMemoryMediaStore

    store = await _composite_case()
    async with arcadedb_adapter(load_default_ontology(), load_uk_le_scheme()) as adapter:
        tx = await adapter.begin_transaction()
        await adapter.upsert_nodes([_held_by_the_member("car-1", "Vehicle")], tx)
        await adapter.commit_transaction(tx)
        graph = stamping(adapter, registry=store)
        working = FakeWorkingSetStore()
        held_car = await adapter.get_node("car-1", MEMBER_ONLY)
        assert held_car is not None
        for case in ("member-case", CASE):
            await working.add_nodes(case, [held_car])
        media = InMemoryMediaStore()
        service = EntityPictureService(
            WorkingSetService(graph, working, SCHEME),
            graph,
            media,
            load_default_ontology(),
            scheme=load_uk_le_scheme(),
        )
        png = b"\x89PNG\r\n\x1a\n" + b"synthetic car"
        in_member = await scope_to_case(ANALYST, "member-case", store)
        await service.set(
            "member-case", "car-1", in_member, name="car.png", data=png, handling=HANDLING
        )
        set_case_datasets(None)
        stored = len(media.files)
        before = await service.pictures("member-case", ["car-1"], MEMBER_ONLY)

        in_composite = await scope_to_case(ANALYST, CASE, store)
        with pytest.raises(CompositeReadOnlyError, match="do this in a case that reads"):
            await service.set(
                CASE, "car-1", in_composite, name="side.png", data=png + b"2", handling=HANDLING
            )
        with pytest.raises(CompositeReadOnlyError):
            await service.remove(CASE, "car-1", in_composite)
        set_case_datasets(None)

        assert await service.pictures("member-case", ["car-1"], MEMBER_ONLY) == before
        assert len(media.files) == stored
