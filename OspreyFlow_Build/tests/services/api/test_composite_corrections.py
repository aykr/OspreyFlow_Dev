"""ADR-099 Amendment 15 (the owner's ruling of 7 November 2026 on corrections): in a case reading a
composite, a correction of a member's link is refused, in words ("correct this in a case that
reads that dataset"), so no member ever changes. A correction hides the old element from every
reader, and a composite cannot hide a member's element from its own readers alone.

Two call sites, each driven for real, each red before the refusal: `LinkChangeService.change`
(`POST .../links/{edge}/change`) here, and replacing or removing an entity's picture
(`EntityPictureService`) against ArcadeDB in `test_composite_writes_live.py`. The control: the
composite's own link (written in the case) may still be corrected.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.dataset_scope import (
    CorrectionInCompositeError,
    scope_to_case,
    set_case_datasets,
    stamping,
)
from services.api.datasets import COMPOSITE, Dataset, InMemoryDatasetStore
from services.api.link_changes import LinkChangeRequest, LinkChangeService
from services.api.working_set.service import WorkingSetService

from schemas.domain import Principal

from .test_link_changes import (
    ONTOLOGY,
    InMemoryChanges,
    MovedNotes,
    SupersedingGraph,
    _edge,
    _node,
)
from .working_set.fakes import FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME

CASE = "inv-1"
MEMBER, OTHER, BOTH = "member", "other-member", "both"
ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


@pytest.fixture(autouse=True)
def _no_case_left_in_scope() -> object:
    yield
    set_case_datasets(None)


def _dataset(dataset_id: str, **kind: object) -> Dataset:
    return Dataset(
        id=dataset_id,
        name=dataset_id,
        owning_unit="unit-1",
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
        created_by="seed",
        **kind,  # type: ignore[arg-type]
    )


async def _in_the_composite_case() -> tuple[LinkChangeService, SupersedingGraph, Principal]:
    """The service as the Conduit builds it (over the stamping graph), the case reading the
    composite, with a member's link `e1` and the composite's own link `own`."""
    store = InMemoryDatasetStore()
    store.add(_dataset(MEMBER))
    store.add(_dataset(OTHER))
    store.add(_dataset(BOTH, kind=COMPOSITE, members=[MEMBER, OTHER]))
    await store.set_for_case(CASE, [BOTH], ANALYST, case_name="Both")
    principal = await scope_to_case(ANALYST, CASE, store)
    working = FakeWorkingSetStore()
    ends = [_node("a").model_copy(update={"datasets": [MEMBER]})]
    ends.append(_node("b").model_copy(update={"datasets": [MEMBER]}))
    await working.add_nodes(CASE, ends)
    links = [
        _edge("e1", "a", "b").model_copy(update={"datasets": [MEMBER]}),
        _edge("own", "a", "b").model_copy(update={"datasets": [BOTH]}),
    ]
    await working.add_edges(CASE, links)
    graph = SupersedingGraph({e.id for e in links})
    stamped = stamping(graph)
    service = LinkChangeService(
        InMemoryChanges(), WorkingSetService(stamped, working, SCHEME), stamped, ONTOLOGY,
        MovedNotes(),
    )  # fmt: skip
    return service, graph, principal


async def test_a_members_link_is_not_corrected_in_a_composite_case() -> None:
    service, graph, principal = await _in_the_composite_case()
    with pytest.raises(CorrectionInCompositeError, match="correct this in a case that reads"):
        await service.change(
            CASE, "e1", principal, LinkChangeRequest(type="FAMILY_OF", reason="Told so")
        )
    assert graph.superseded == []


async def test_the_composites_own_link_may_still_be_corrected() -> None:
    service, graph, principal = await _in_the_composite_case()
    await service.change(
        CASE, "own", principal, LinkChangeRequest(type="FAMILY_OF", reason="Told so")
    )
    assert [old for old, _ in graph.superseded] == ["own"]
