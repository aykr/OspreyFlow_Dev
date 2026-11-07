"""A branch reads its original case's layer and writes nothing into it (ADR-144 Amendment 1 decision
2: the owner, 7 November 2026, no branches anywhere; L3.2 removes them).

What a mistake here would do, and the case that catches it:

- a manual link made in a branch going into the original case's layer, so the original's analysts
  see work done somewhere else: `test_a_manual_link_in_a_branch_is_refused_and_nothing_written`;
- any other write naming that layer, or correcting what is in it, getting past the services: the
  stamping graph's last word, `test_a_write_into_the_layer_a_branch_reads_is_refused`, red with that
  check alone removed in `test_the_branch_check_fails_with_it_alone_removed`;
- the store making the branch a layer of its own when asked:
  `test_the_store_makes_no_layer_for_a_branch`.

That a branch holds no layer and reads its original's, and that a case opened from an alert keeps
one of its own, is in `test_analyst_layer.py`.
"""

from __future__ import annotations

from typing import Any

import pytest
from services.api.dataset_scope import (
    DatasetStampingGraph,
    scope_to_case,
    set_case_datasets,
    stamping,
)
from services.api.datasets import BranchLayerError, InMemoryDatasetStore
from services.api.working_set.service import WorkingSetService

from schemas.domain import Principal, ProvenanceState, Subgraph

from .test_composite_read_only import MEMBER, _composite_store, _member_node, _write
from .test_email_extraction import WritingGraph
from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


@pytest.fixture(autouse=True)
def _no_case_left_in_scope() -> object:
    yield
    set_case_datasets(None)


async def _in_a_branch() -> tuple[InMemoryDatasetStore, str, Principal]:
    """A case reading the member, and its branch, scoped as a request under the branch is."""
    store = await _composite_store()
    await store.set_for_case("original", [MEMBER], ANALYST, case_name="Original")
    await store.copy_case("original", "branch", case_name="Branch")
    layer = await store.layer_of_case("original")
    assert layer is not None
    return store, layer, await scope_to_case(ANALYST, "branch", store)


async def test_a_manual_link_in_a_branch_is_refused_and_nothing_written() -> None:
    store, layer, principal = await _in_a_branch()
    assert layer in (principal.datasets or [])  # the branch reads the original's layer
    people = [_member_node(ProvenanceState.ASSERTED, n) for n in ("n1", "n2")]
    inner = FakeGraphPort(Subgraph(nodes=people, edges=[]))
    working = FakeWorkingSetStore()
    await working.add_nodes("branch", people)
    with pytest.raises(BranchLayerError, match="mark or link in the original case"):
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
    with pytest.raises(BranchLayerError):
        await _write_into(layer, store)


async def test_a_correction_of_what_is_in_that_layer_is_refused() -> None:
    store, layer, _ = await _in_a_branch()
    theirs = _member_node(ProvenanceState.INFERRED, "theirs").model_copy(
        update={"datasets": [layer]}
    )
    inner = FakeGraphPort(Subgraph(nodes=[theirs], edges=[]))
    with pytest.raises(BranchLayerError):
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
    with pytest.raises(BranchLayerError):
        await store.ensure_layer("branch", unit="unit-1", created_by=ANALYST.id)
    # Choosing another dataset for the branch makes none either.
    await store.set_for_case("branch", [MEMBER], ANALYST)
    assert await store.layer_of_case("branch") is None
