"""A composite is read-only for now (ADR-099 Amendment 15; the owner's ruling of 7 November 2026),
against real ArcadeDB: two of its write paths, driven at their real call sites in the seeded Enron
and Fixture Corp shape (a case reading a composite whose member already holds the data).

- extracting an email: refused before anything is written, the member's Document exactly as it
  was (`test_an_email_is_not_extracted_in_a_composite_case_and_the_member_is_unchanged`);
- an entity's picture: neither replaced nor removed, and no file stored for the refused one
  (`test_a_picture_is_neither_replaced_nor_removed_in_a_composite_case`).

Each was a write that changed a member before the ruling (the fourth and fifth reviews). Each check
has its own red companion here, one check removed at a time (`_without`): the service's own check
alone holds the extraction against the last word, and the last word alone holds it against the
service; with both removed, the member's Document changes. A picture's service check is what keeps
the file from being stored at all: removed alone, the file is stored before the stamping graph
refuses the graph write; removed with the last word, the member's picture is replaced.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.dataset_scope import (
    CompositeReadOnlyError,
    DatasetStampingGraph,
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


def _without(monkeypatch: pytest.MonkeyPatch, *checks: str) -> None:
    """Only the named checks removed: a service's own (`email_extraction`, `entity_pictures`), or
    the stamping graph's `last-word`."""
    import importlib

    async def allowed(*args: object, **kwargs: object) -> None:
        return None

    for check in checks:
        if check == "last-word":
            monkeypatch.setattr(DatasetStampingGraph, "_refuse_into_a_composite", allowed)
        else:
            module = importlib.import_module(f"services.api.{check}")
            monkeypatch.setattr(module, "refuse_in_a_composite_case", allowed)


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


async def _extract_in_the_composite_case(*, refused: bool) -> tuple[bool, bool]:
    """Extracts the member's email in the composite case: whether the member's Document and its
    neighbourhood are exactly as they were, and whether anything was stored as a finding."""
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
        if refused:
            with pytest.raises(CompositeReadOnlyError, match="do this in a case that reads"):
                await service.extract(CASE, "e1", "ev-1", principal)
        else:
            await service.extract(CASE, "e1", "ev-1", principal)
        set_case_datasets(None)

        unchanged = (
            await adapter.neighbourhood_stats(DOCUMENT, MEMBER_ONLY) == before
            and await adapter.get_node(DOCUMENT, MEMBER_ONLY) == held
        )
        return unchanged, bool(candidates.records or candidates.texts)


async def test_an_email_is_not_extracted_in_a_composite_case_and_the_member_is_unchanged() -> None:
    assert await _extract_in_the_composite_case(refused=True) == (True, False)


@pytest.mark.parametrize("removed", [("email_extraction",), ("last-word",)])
async def test_each_extraction_check_holds_alone_live(
    removed: tuple[str, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    _without(monkeypatch, *removed)
    assert await _extract_in_the_composite_case(refused=True) == (True, False)


async def test_the_member_changes_with_both_extraction_checks_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _without(monkeypatch, "email_extraction", "last-word")
    unchanged, stored = await _extract_in_the_composite_case(refused=False)
    assert not unchanged and stored


async def _picture_in_the_composite_case(
    *, refused: bool, action: str = "replace"
) -> tuple[bool, int]:
    """Replaces (or removes) the member's picture from the composite case: whether the member's
    picture is as it was, and how many files were stored past the member's own."""
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
        replace = (
            service.set(
                CASE, "car-1", in_composite, name="side.png", data=png + b"2", handling=HANDLING
            )
            if action == "replace"
            else service.remove(CASE, "car-1", in_composite)
        )
        if refused:
            with pytest.raises(CompositeReadOnlyError, match="do this in a case that reads"):
                await replace
        else:
            await replace
        set_case_datasets(None)
        unchanged = await service.pictures("member-case", ["car-1"], MEMBER_ONLY) == before
        return unchanged, len(media.files) - stored


async def test_a_picture_is_neither_replaced_nor_removed_in_a_composite_case() -> None:
    """Set first in a case reading the member; in the composite case, replacing and removing it are
    refused before any file is stored, and the member's picture is exactly as it was."""
    assert await _picture_in_the_composite_case(refused=True) == (True, 0)


async def test_the_picture_check_alone_keeps_the_file_from_being_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The service's check removed alone: the last word still refuses the graph write, but only
    after the file was stored."""
    _without(monkeypatch, "entity_pictures")
    unchanged, stored = await _picture_in_the_composite_case(refused=True)
    assert unchanged and stored == 1


async def test_the_member_picture_is_replaced_with_both_checks_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _without(monkeypatch, "entity_pictures", "last-word")
    unchanged, stored = await _picture_in_the_composite_case(refused=False)
    assert not unchanged and stored == 1


@pytest.mark.parametrize("removed", [("entity_pictures",), ("last-word",)])
async def test_each_picture_removal_check_holds_alone(
    removed: tuple[str, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    _without(monkeypatch, *removed)
    assert await _picture_in_the_composite_case(refused=True, action="remove") == (True, 0)


async def test_the_member_picture_is_removed_with_both_checks_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _without(monkeypatch, "entity_pictures", "last-word")
    unchanged, _stored = await _picture_in_the_composite_case(refused=False, action="remove")
    assert not unchanged


async def test_a_picture_is_not_removed_in_a_composite_case() -> None:
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
