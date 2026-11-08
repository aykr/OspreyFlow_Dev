"""A case made from another since L3.1 (a branch, in the words of the time), until the upgrade turns it
into a view, reads its original case's layer and writes nothing into it (ADR-144 Amendment 1
decision 2). No route makes one since L3.2; `unconverted.made_before_l3_2` makes one as the data
holds it.

What a mistake here would do, and the case that catches it:

- a manual link made in a branch going into the original case's layer, so the original's analysts
  see work done somewhere else: `test_a_manual_link_in_a_branch_is_refused_and_nothing_written`;
- any other write naming that layer, or correcting what is in it, getting past the services: the
  stamping graph's last word, `test_a_write_into_the_layer_a_branch_reads_is_refused`, red with that
  check alone removed in `test_the_branch_check_fails_with_it_alone_removed`;
- the store making the branch a layer of its own when asked:
  `test_the_store_makes_no_layer_for_a_branch`;
- a member of the branch alone, holding no level on the original, reading the original's hand marks
  and manual links (the orchestrator's call, on rule 3, as for the alert jump):
  `test_a_branch_member_with_no_level_on_the_original_reads_none_of_its_layer`, red with the link
  applied to every reader;
- a correction of the layer's element getting past the last word with its check removed:
  `test_a_correction_of_that_layer_goes_through_with_the_check_alone_removed`.

That a branch holds no layer and reads its original's, and that a case opened from an alert keeps
one of its own, is in `test_analyst_layer.py`.
"""

from __future__ import annotations

from typing import Any

import pytest
from services.api.dataset_scope import (
    DatasetStampingGraph,
    analyst_writes_into,
    scope_to_case,
    set_case_datasets,
    stamping,
)
from services.api.datasets import InMemoryDatasetStore, ReadOnlyLayerError
from services.api.working_set.service import WorkingSetService

from schemas.domain import Principal, ProvenanceState, Subgraph

from .test_composite_read_only import MEMBER, _composite_store, _member_node, _NodeGraph, _write
from .test_email_extraction import WritingGraph
from .unconverted import made_before_l3_2
from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


@pytest.fixture(autouse=True)
def _no_case_left_in_scope() -> object:
    yield
    set_case_datasets(None)


async def _holds(principal: Principal, investigation_id: str) -> bool:
    """The analyst holds a level on the original, as its maker; nobody else does."""
    return principal.id == ANALYST.id


async def _in_a_branch(
    reader: Principal = ANALYST, holds: Any = _holds
) -> tuple[InMemoryDatasetStore, str, Principal]:
    """A case reading the member, and its branch, scoped as a request under the branch is."""
    store = await _composite_store()
    await store.set_for_case("original", [MEMBER], ANALYST, case_name="Original")
    layer = await made_before_l3_2(store, "original", "branch")
    return store, layer, await scope_to_case(reader, "branch", store, holds_a_level=holds)


async def test_a_manual_link_in_a_branch_is_refused_and_nothing_written() -> None:
    store, layer, principal = await _in_a_branch()
    assert layer in (principal.datasets or [])  # the branch reads the original's layer
    people = [_member_node(ProvenanceState.ASSERTED, n) for n in ("n1", "n2")]
    inner = FakeGraphPort(Subgraph(nodes=people, edges=[]))
    working = FakeWorkingSetStore()
    await working.add_nodes("branch", people)
    with pytest.raises(ReadOnlyLayerError, match="mark or link in that case"):
        await WorkingSetService(stamping(inner, registry=store), working, SCHEME).manual_link(
            "branch", "n1", "n2", principal
        )
    assert inner.committed_edges == []
    assert await store.layer_of_case("branch") is None


async def _write_into(layer: str, store: InMemoryDatasetStore) -> WritingGraph:
    inner = WritingGraph()
    graph = stamping(inner, registry=store)
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([_write("p9").model_copy(update={"datasets": [layer]})], tx)
    await graph.commit_transaction(tx)
    return inner


async def test_a_write_into_the_layer_a_branch_reads_is_refused() -> None:
    store, layer, _ = await _in_a_branch()
    with pytest.raises(ReadOnlyLayerError):
        await _write_into(layer, store)


async def test_a_correction_of_what_is_in_that_layer_is_refused() -> None:
    store, layer, _ = await _in_a_branch()
    theirs = _member_node(ProvenanceState.INFERRED, "theirs").model_copy(
        update={"datasets": [layer]}
    )
    inner = FakeGraphPort(Subgraph(nodes=[theirs], edges=[]))
    with pytest.raises(ReadOnlyLayerError):
        await stamping(inner, registry=store).supersede_node("theirs", _write("next"), "tx")


async def test_the_branch_check_fails_with_it_alone_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule 15, red: the stamping graph's check removed alone, the write lands in the original's
    layer."""

    async def allowed(self: Any, datasets: Any) -> None:
        return None

    monkeypatch.setattr(DatasetStampingGraph, "_refuse_into_a_read_only_layer", allowed)
    store, layer, _ = await _in_a_branch()
    inner = await _write_into(layer, store)
    assert inner.nodes["p9"].datasets == [layer]


async def test_the_store_makes_no_layer_for_a_branch() -> None:
    store, _layer, _ = await _in_a_branch()
    with pytest.raises(ReadOnlyLayerError):
        await store.ensure_layer("branch", unit="unit-1", created_by=ANALYST.id)
    # Choosing another dataset for the branch makes none either.
    await store.set_for_case("branch", [MEMBER], ANALYST)
    assert await store.layer_of_case("branch") is None


async def test_a_correction_of_that_layer_goes_through_with_the_check_alone_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule 15, red, for the correction above: with only the stamping graph's read-only-layer
    check removed, the branch supersedes the original's layer's element."""

    async def allowed(self: Any, datasets: Any) -> None:
        return None

    monkeypatch.setattr(DatasetStampingGraph, "_refuse_into_a_read_only_layer", allowed)
    store, layer, _ = await _in_a_branch()
    theirs = _member_node(ProvenanceState.INFERRED, "theirs").model_copy(
        update={"datasets": [layer]}
    )
    inner = _NodeGraph(theirs)
    await stamping(inner, registry=store).supersede_node("theirs", _write("next"), "tx")
    assert inner.superseded == ["theirs"]


#: A member of the branch who holds no level on the original.
STRANGER = Principal(id="branch-only", clearance="OFFICIAL", org_unit="unit-1")


def _marks_and_links(layer: str) -> Subgraph:
    """The original's layer: a node marked by hand there and a manual link between two of the
    member's people, both the layer's alone."""
    from .test_dataset_scope import _edge as an_edge

    marked = _member_node(ProvenanceState.ASSERTED, "marked").model_copy(
        update={"datasets": [layer]}
    )
    people = [_member_node(ProvenanceState.ASSERTED, n) for n in ("n1", "n2")]
    link = an_edge("manual", "n1", "n2", [layer])
    return Subgraph(nodes=[marked, *people], edges=[link])


def _read(principal: Principal, held: Subgraph) -> tuple[list[str], list[str]]:
    """What the adapter returns `principal`: elements in one of its datasets (rule 3)."""
    reach = set(principal.datasets or [])
    return (
        [n.id for n in held.nodes if set(n.datasets) & reach],
        [e.id for e in held.edges if set(e.datasets) & reach],
    )


async def test_a_branch_member_with_no_level_on_the_original_reads_none_of_its_layer() -> None:
    store, layer, member = await _in_a_branch(STRANGER)
    assert layer not in (member.datasets or [])
    nodes, links = _read(member, _marks_and_links(layer))
    assert "marked" not in nodes and links == []
    # And writes nothing into it, as for every reader of the branch.
    with pytest.raises(ReadOnlyLayerError):
        await analyst_writes_into()
    # The original's own analyst, in the same branch, reads it.
    _s, theirs, maker = await _in_a_branch(ANALYST)
    nodes, links = _read(maker, _marks_and_links(theirs))
    assert "marked" in nodes and links == ["manual"]


async def test_the_branch_member_reads_the_layer_with_the_link_applied_to_everyone() -> None:
    """Rule 15, red: the link applied to every reader of the branch, as it was at 0cd76bb."""

    async def everyone(principal: Principal, investigation_id: str) -> bool:
        return True

    _store, layer, member = await _in_a_branch(STRANGER, holds=everyone)
    nodes, links = _read(member, _marks_and_links(layer))
    assert "marked" in nodes and links == ["manual"]
