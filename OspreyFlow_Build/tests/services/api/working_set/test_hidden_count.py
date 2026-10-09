"""What the working set counts as hidden by handling, and what it drops (`spec/02_GLASS_FRONTEND.md`
§2 rule 4, "the status bar never lies"; `03_CONDUIT_MIDDLEWARE.md` §4).

Seen on the owner's deployment, 9 October 2026: after *Clear view* and a reload, an OFFICIAL case of
OFFICIAL data said "124 hidden by handling". Removing a node leaves its links in the store by design
(`WorkingSetStore.remove_edges`'s docstring), and `_project` counted every link it left out as
hidden, so a link whose end had left the view was reported as withheld. The same rule judged a
replayed or live-pushed delta's links against that delta's own nodes only, so a link from a new node
to one already on the canvas was dropped and counted hidden, though the reader may see both ends.

What a mistake would do, and the case that catches it:

- a link whose end has left the working set counted as hidden
  (`test_a_link_whose_end_has_left_the_view_is_not_counted_hidden`);
- the projection made lax to fix it, so a link to a node the reader may not see is shown
  (`test_a_link_to_a_hidden_node_is_still_withheld_and_counted`);
- a replayed link to a node already on the canvas dropped and counted hidden
  (`test_a_replayed_link_to_a_node_already_in_the_view_is_kept`), and the same on a live push
  (`test_a_live_push_judges_a_links_ends_against_the_working_set`);
- the replay made lax, so a link to an earlier node the reader may not see is sent
  (`test_a_replayed_link_to_an_earlier_hidden_node_is_withheld`).
"""

from __future__ import annotations

from services.api.working_set.models import DeltaAdd, DeltaNotice, DeltaSnapshot
from services.api.working_set.service import WorkingSetService

from .fakes import FakeWorkingSetStore
from .test_visible_link import OFFICIAL_READER, SCHEME, edge, node

CASE = "case-1"


async def _service(*deltas: DeltaAdd) -> tuple[WorkingSetService, FakeWorkingSetStore]:
    store = FakeWorkingSetStore()
    for delta in deltas:
        await store.add_nodes(CASE, delta.nodes)
        await store.add_edges(CASE, delta.edges)
        await store.next_seq(CASE)
        await store.append_delta(CASE, delta)
    return WorkingSetService(None, store, SCHEME), store  # type: ignore[arg-type]


async def test_a_link_whose_end_has_left_the_view_is_not_counted_hidden() -> None:
    service, store = await _service(
        DeltaAdd(seq=1, nodes=[node("a"), node("b")], edges=[edge("ab", "a", "b")])
    )
    await store.remove_nodes(CASE, ["b"])
    (snapshot,) = await service.sync(CASE, OFFICIAL_READER, last_acknowledged_seq=None)
    assert isinstance(snapshot, DeltaSnapshot)
    assert [n.id for n in snapshot.nodes] == ["a"]
    assert snapshot.edges == []
    assert snapshot.filtered_count == 0


async def test_a_link_to_a_hidden_node_is_still_withheld_and_counted() -> None:
    service, _ = await _service(
        DeltaAdd(seq=1, nodes=[node("a"), node("s", "SECRET")], edges=[edge("as", "a", "s")])
    )
    (snapshot,) = await service.sync(CASE, OFFICIAL_READER, last_acknowledged_seq=None)
    assert isinstance(snapshot, DeltaSnapshot)
    assert [n.id for n in snapshot.nodes] == ["a"]
    assert snapshot.edges == []
    assert snapshot.filtered_count == 2


async def test_a_replayed_link_to_a_node_already_in_the_view_is_kept() -> None:
    service, _ = await _service(
        DeltaAdd(seq=1, nodes=[node("a")], edges=[]),
        DeltaAdd(seq=2, nodes=[node("b")], edges=[edge("ab", "a", "b")]),
    )
    replayed = await service.sync(CASE, OFFICIAL_READER, last_acknowledged_seq=1)
    (add,) = replayed
    assert isinstance(add, DeltaAdd)
    assert [e.id for e in add.edges] == ["ab"]
    assert not any(isinstance(d, DeltaNotice) for d in replayed)


async def test_a_replayed_link_to_an_earlier_hidden_node_is_withheld() -> None:
    service, _ = await _service(
        DeltaAdd(seq=1, nodes=[node("s", "SECRET")], edges=[]),
        DeltaAdd(seq=2, nodes=[node("b")], edges=[edge("sb", "s", "b")]),
    )
    replayed = await service.sync(CASE, OFFICIAL_READER, last_acknowledged_seq=1)
    add, notice = replayed
    assert isinstance(add, DeltaAdd) and add.edges == []
    assert isinstance(notice, DeltaNotice) and notice.count == 1


async def test_a_live_push_judges_a_links_ends_against_the_working_set() -> None:
    later = DeltaAdd(seq=2, nodes=[node("b")], edges=[edge("ab", "a", "b"), edge("sb", "s", "b")])
    service, _ = await _service(
        DeltaAdd(seq=1, nodes=[node("a"), node("s", "SECRET")], edges=[]), later
    )
    pushed, hidden = await service.project_live(CASE, later, OFFICIAL_READER)
    assert isinstance(pushed, DeltaAdd)
    assert [e.id for e in pushed.edges] == ["ab"]
    assert hidden == 1
