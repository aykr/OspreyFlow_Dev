"""*Show all on graph* under an Ask & Chat answer (v0.6.0 #5): `WorkingSetService.add_by_ids`
puts the nodes and links an answer's markers stand for on the case's working set by id alone, read
as `seed` reads them (rule 3), the cap counted as any add's (rule 2), and says how many of the ids
asked for are not on the canvas after it, never which.

Against the real `WorkingSetService` over `FakeGraphPort`, whose by-id reads hold only what a test
gives them and leave out an absent, unreadable or superseded id alike, as the adapter does (rule
15), so a hidden id and an absent one are refused the same way. What a mistake would do, and the
case that catches it:

- a node the reader may not see put on the canvas, or named
  (`test_a_node_the_reader_may_not_see_is_left_out_counted_and_never_named`);
- a hidden id told from an absent one by the count or the add
  (`test_a_hidden_id_and_an_absent_one_are_counted_alike`);
- a link whose two ends the reader cannot both see put on the canvas (the orchestrator's ruling)
  (`test_a_link_whose_ends_the_reader_cannot_both_see_is_left_out_and_counted`);
- the canvas cut to fit past its cap
  (`test_past_the_cap_it_is_refused_whole_with_the_readers_figure`).
"""

from __future__ import annotations

import pytest
from services.api.working_set import service as service_module
from services.api.working_set.models import LimitExceededError

from .fakes import FakeWorkingSetStore
from .test_seed_verifies_against_the_vault import CASE, _real, _service
from .test_visible_link import OFFICIAL_READER, edge


async def test_the_answers_nodes_and_links_are_put_on_the_canvas_and_none_is_left_out() -> None:
    store = FakeWorkingSetStore()
    service, _ = _service(store, [_real("a"), _real("b")], [edge("ab", "a", "b")])

    added = await service.add_by_ids(CASE, ["a", "b"], ["ab"], OFFICIAL_READER)

    assert [n.id for n in added.outcome.delta.nodes] == ["a", "b"]
    assert [e.id for e in added.outcome.delta.edges] == ["ab"]
    assert added.not_shown == 0
    assert set(await store.node_ids(CASE)) == {"a", "b"}


async def test_a_node_the_reader_may_not_see_is_left_out_counted_and_never_named() -> None:
    store = FakeWorkingSetStore()
    service, _ = _service(store, [_real("a"), _real("hidden", "SECRET")])

    added = await service.add_by_ids(CASE, ["a", "hidden"], [], OFFICIAL_READER)

    assert [n.id for n in added.outcome.delta.nodes] == ["a"]
    assert added.not_shown == 1
    assert "hidden" not in added.model_dump_json()
    assert set(await store.node_ids(CASE)) == {"a"}


async def test_a_hidden_id_and_an_absent_one_are_counted_alike() -> None:
    async def answer(asked: str) -> str:
        store = FakeWorkingSetStore()
        service, _ = _service(store, [_real("a"), _real("hidden", "SECRET")])
        added = await service.add_by_ids(CASE, ["a", asked], [], OFFICIAL_READER)
        return added.model_dump_json().replace(asked, "X")

    assert await answer("hidden") == await answer("never-held")


async def test_a_link_whose_ends_the_reader_cannot_both_see_is_left_out_and_counted() -> None:
    store = FakeWorkingSetStore()
    service, _ = _service(
        store,
        [_real("a"), _real("hidden", "SECRET"), _real("b")],
        [edge("a-hidden", "a", "hidden"), edge("ab", "a", "b")],
    )

    added = await service.add_by_ids(
        CASE, ["a", "b", "hidden"], ["a-hidden", "ab"], OFFICIAL_READER
    )

    assert [e.id for e in added.outcome.delta.edges] == ["ab"]
    # The hidden node and the link to it: two of the five ids asked for, neither named.
    assert added.not_shown == 2
    assert "a-hidden" not in added.model_dump_json()


async def test_a_link_to_a_node_neither_on_the_canvas_nor_in_the_add_is_left_out_and_counted() -> None:
    """The service's own check, past the Vault's: both ends readable, but one neither on the canvas nor
    asked for, so the link would hang from nothing."""
    store = FakeWorkingSetStore()
    service, _ = _service(store, [_real("a"), _real("b")], [edge("ab", "a", "b")])

    added = await service.add_by_ids(CASE, ["a"], ["ab"], OFFICIAL_READER)

    assert [n.id for n in added.outcome.delta.nodes] == ["a"]
    assert added.outcome.delta.edges == []
    assert added.not_shown == 1


async def test_repeated_ids_are_asked_and_counted_once() -> None:
    store = FakeWorkingSetStore()
    service, _ = _service(store, [_real("a")])

    added = await service.add_by_ids(CASE, ["a", "a", "missing", "missing"], [], OFFICIAL_READER)

    assert [n.id for n in added.outcome.delta.nodes] == ["a"]
    assert added.not_shown == 1


@pytest.fixture
def small_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "MAX_NODES", 3)


async def test_past_the_cap_it_is_refused_whole_with_the_readers_figure(small_cap: None) -> None:
    store = FakeWorkingSetStore()
    service, _ = _service(store, [_real(f"n{i}") for i in range(4)])

    with pytest.raises(LimitExceededError) as refused:
        await service.add_by_ids(CASE, [f"n{i}" for i in range(4)], [], OFFICIAL_READER)

    assert refused.value.detail.would_be == 4
    assert await store.node_ids(CASE) == set()
