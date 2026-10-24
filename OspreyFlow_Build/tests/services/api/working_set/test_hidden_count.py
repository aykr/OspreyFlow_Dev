"""What the working set drops for a reader whose handling does not clear it, and that it tells them
nothing of how much (`spec/02_GLASS_FRONTEND.md` §2 rule 4; `03_CONDUIT_MIDDLEWARE.md` §4; ADR-124
decision 1 removed the figure and the notice this file once asserted on).

Seen on the owner's deployment, 9 October 2026: after *Clear view* and a reload, an OFFICIAL case of
OFFICIAL data said "124 hidden by handling". Removing a node leaves its links in the store by design
(`WorkingSetStore.remove_edges`'s docstring), and `_project` counted every link it left out as
hidden, so a link whose end had left the view was reported as withheld. The same rule judged a
replayed or live-pushed delta's links against that delta's own nodes only, so a link from a new node
to one already on the canvas was dropped, though the reader may see both ends. The figure is gone,
but the projection it was counted by is what decides what the reader is sent, so the cases stay.

What a mistake would do, and the case that catches it:

- a link whose end has left the working set sent or kept
  (`test_a_link_whose_end_has_left_the_view_is_not_sent`);
- the projection made lax to fix it, so a link to a node the reader may not see is shown
  (`test_a_link_to_a_hidden_node_is_still_withheld`);
- a replayed link to a node already on the canvas dropped
  (`test_a_replayed_link_to_a_node_already_in_the_view_is_kept`), and the same on a live push
  (`test_a_live_push_judges_a_links_ends_against_the_working_set`);
- the replay made lax, so a link to an earlier node the reader may not see is sent
  (`test_a_replayed_link_to_an_earlier_hidden_node_is_withheld`);
- a catch-up that ends with a notice of how much it withheld
  (`test_a_catch_up_that_withheld_something_sends_no_notice_and_no_figure`).
"""

from __future__ import annotations

from services.api.working_set.models import DeltaAdd, DeltaSnapshot
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


async def test_a_link_whose_end_has_left_the_view_is_not_sent() -> None:
    service, store = await _service(
        DeltaAdd(seq=1, nodes=[node("a"), node("b")], edges=[edge("ab", "a", "b")])
    )
    await store.remove_nodes(CASE, ["b"])
    (snapshot,) = await service.sync(CASE, OFFICIAL_READER, last_acknowledged_seq=None)
    assert isinstance(snapshot, DeltaSnapshot)
    assert [n.id for n in snapshot.nodes] == ["a"]
    assert snapshot.edges == []


async def test_a_link_to_a_hidden_node_is_still_withheld() -> None:
    service, _ = await _service(
        DeltaAdd(seq=1, nodes=[node("a"), node("s", "SECRET")], edges=[edge("as", "a", "s")])
    )
    (snapshot,) = await service.sync(CASE, OFFICIAL_READER, last_acknowledged_seq=None)
    assert isinstance(snapshot, DeltaSnapshot)
    assert [n.id for n in snapshot.nodes] == ["a"]
    assert snapshot.edges == []


async def test_a_replayed_link_to_a_node_already_in_the_view_is_kept() -> None:
    service, _ = await _service(
        DeltaAdd(seq=1, nodes=[node("a")], edges=[]),
        DeltaAdd(seq=2, nodes=[node("b")], edges=[edge("ab", "a", "b")]),
    )
    replayed = await service.sync(CASE, OFFICIAL_READER, last_acknowledged_seq=1)
    (add,) = replayed
    assert isinstance(add, DeltaAdd)
    assert [e.id for e in add.edges] == ["ab"]


async def test_a_replayed_link_to_an_earlier_hidden_node_is_withheld() -> None:
    service, _ = await _service(
        DeltaAdd(seq=1, nodes=[node("s", "SECRET")], edges=[]),
        DeltaAdd(seq=2, nodes=[node("b")], edges=[edge("sb", "s", "b")]),
    )
    replayed = await service.sync(CASE, OFFICIAL_READER, last_acknowledged_seq=1)
    (add,) = replayed
    assert isinstance(add, DeltaAdd) and add.edges == []


async def test_a_catch_up_that_withheld_something_sends_no_notice_and_no_figure() -> None:
    """Violation caught (ADR-124 decision 1): a catch-up that ends with a notice, or any delta
    carrying a number for what it left out, which is what a reader could subtract from. The
    catch-up for a reader the hidden link withheld from is the same one-delta answer as for a
    reader with nothing withheld."""
    withheld, _ = await _service(
        DeltaAdd(seq=1, nodes=[node("s", "SECRET")], edges=[]),
        DeltaAdd(seq=2, nodes=[node("b")], edges=[edge("sb", "s", "b")]),
    )
    plain, _ = await _service(
        DeltaAdd(seq=1, nodes=[node("a")], edges=[]),
        DeltaAdd(seq=2, nodes=[node("b")], edges=[]),
    )
    hidden_catch_up = await withheld.sync(CASE, OFFICIAL_READER, last_acknowledged_seq=1)
    plain_catch_up = await plain.sync(CASE, OFFICIAL_READER, last_acknowledged_seq=1)

    assert [d.op for d in hidden_catch_up] == [d.op for d in plain_catch_up] == ["add"]
    assert "count" not in hidden_catch_up[0].model_dump()


async def test_a_live_push_judges_a_links_ends_against_the_working_set() -> None:
    later = DeltaAdd(seq=2, nodes=[node("b")], edges=[edge("ab", "a", "b"), edge("sb", "s", "b")])
    service, _ = await _service(
        DeltaAdd(seq=1, nodes=[node("a"), node("s", "SECRET")], edges=[]), later
    )
    pushed = await service.project_live(CASE, later, OFFICIAL_READER)
    assert isinstance(pushed, DeltaAdd)
    assert [e.id for e in pushed.edges] == ["ab"]
