"""A shared view's count never includes items its reader may not see (C045; rules 3, 4, 7, 12, 15).

A view's `chosen` (every answer that carries a `CaseView`) is the count of its chosen nodes **this
reader may see now**, never the count its creator stored: a stored count tells a reader how many
nodes a shared view holds above their clearance. `CaseViewOpened.missing` counts only the chosen
nodes **deleted since, that this reader could have seen** (SE9, ADR-144 Amendment 7; the cases for a
deletion are `test_case_view_missing.py`'s): the owner's rule (the boards' rule, `test_boards.py`) is
that `missing` counts only what was lost, and anything hidden by a marking is counted nowhere. It is
never the chosen ids less the nodes shown, which counts every hidden node too, nor an existence
lookup, which is an oracle (rule 3). Here, with nothing deleted, `missing` is 0 for everyone whatever
is hidden from them (`spec/01_DOMAIN_MODEL.md`, §2.2c).

The world is `test_case_views.py`'s: five chosen ids, of which Alice (SECRET, the creator) may read
three (`open`, `near`, `secret`) and Bob (OFFICIAL) two (`open`, `near`); `elsewhere` is in a dataset
the case does not read and `never-held` is held by nobody. Both routes are the real ones, through
the real `get_principal`, over a graph whose access step judges each node by its own body.

What a mistake here would do, and the case that fails for it (each also shown red, rule 15, by the
`*_fails_*` plant beside it, at the shape the real call site has):

- the list route counting the stored ids: `test_the_list_counts_what_the_reader_may_see`, red with
  `visible_chosen` returning the stored length (`test_the_list_check_fails_with_the_stored_length`)
  and with the port's count read without the reader's scope
  (`test_the_count_check_fails_with_the_port_counting_without_the_reader`);
- the open route, or the save and share answers, counting the stored ids:
  `test_open_save_and_share_count_what_the_reader_may_see`, red with the wire's old body
  (`test_the_wire_check_fails_with_the_stored_count_restored`);
- `missing` handing anyone, creator or reader, the hidden number (chosen less shown):
  `test_no_number_includes_what_the_asker_may_not_see` (a node re-marked above them after the save,
  one in a dataset the case does not read, one gone from the store, their own clearance lowered;
  each for the creator, a reader and a viewer), red with `missing_for` returning the difference
  (`test_the_missing_check_fails_with_the_difference_put_back`);
- `missing` telling an id that does not exist from one that exists and is hidden, which lets the
  creator probe for hidden nodes: `test_a_missing_id_and_a_hidden_one_answer_alike`, red with
  `missing_for` counting the ids the store does not hold
  (`test_the_probe_check_fails_with_an_existence_count`);
- a batch expansion's view counting what its requester could read when it was saved:
  `test_a_batch_view_counts_what_its_requester_may_see_now`, red with `visible_chosen` returning
  the stored length (`test_the_batch_check_fails_with_the_stored_length`).
"""

from __future__ import annotations

from typing import Any

import pytest
from services.api import case_views as case_views_module
from services.api.case_views import StoredCaseView

from schemas.domain import Principal

from . import test_case_views as views_world
from .test_batch_expansion import _started, _status
from .test_batch_expansion import world as batch_world  # noqa: F401  (a fixture)
from .test_case_views import (  # noqa: F401  (`world` is a fixture)
    CHOSEN,
    VIEWS,
    _as,
    _in,
    _saved,
    _World,
    world,
)
from .working_set.fakes import FakeGraphPort
from .working_set.test_visible_link import node

#: What each may read of `CHOSEN`: `secret` is SECRET, `elsewhere` is in a dataset the case does not
#: read, and `never-held` is held by nobody.
ALICE_SEES, BOB_SEES = 3, 2


def _listed(who: str) -> list[dict[str, Any]]:
    answer = _as(who).get(VIEWS)
    assert answer.status_code == 200, answer.json()
    return answer.json()


def _opened(who: str, view_id: str) -> dict[str, Any]:
    answer = _as(who).get(f"{VIEWS}/{view_id}")
    assert answer.status_code == 200, answer.json()
    return answer.json()


# --- the list ---------------------------------------------------------------------------------


def test_the_list_counts_what_the_reader_may_see(world: _World) -> None:
    """Bob lists Alice's shared view of five: he is told two. Alice, listing her own, is told three
    (what she may read of it)."""
    _saved(shared=True)
    (bobs,) = _listed("bob")
    (alices,) = _listed("alice")
    assert bobs["chosen"] == BOB_SEES
    assert alices["chosen"] == ALICE_SEES


def test_a_view_of_only_hidden_nodes_counts_none_to_the_reader(world: _World) -> None:
    _saved(shared=True, node_ids=["secret", "elsewhere", "never-held"])
    assert _listed("bob")[0]["chosen"] == 0


def test_a_filtered_view_has_no_count(world: _World) -> None:
    body = {"name": "People", "filter": {"entity_types": ["Person"]}}
    response = _as("alice").post(VIEWS, json=body)
    assert response.status_code == 201, response.json()
    assert response.json()["chosen"] is None
    assert _listed("alice")[0]["chosen"] is None


def test_a_merged_drawings_added_nodes_are_not_counted(world: _World) -> None:
    """The nodes a merge added to a selection are not its creator's choice (L3.9): not counted, even
    when the reader may see them."""
    view_id = _saved(shared=True, node_ids=["open", "near", "secret", "elsewhere"])
    held = world.views.views[view_id]
    world.views.views[view_id] = held.model_copy(update={"merged_added": ["near"]})
    assert _listed("bob")[0]["chosen"] == 1  # `open`; not `near`, though Bob may read it
    assert _opened("bob", view_id)["view"]["chosen"] == 1


def test_the_list_check_fails_with_the_stored_length(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, at the real call site's shape: the list route asks `visible_chosen` for each view.
    Planted to count the stored ids, Bob is told five."""

    async def stored(graph: Any, view: StoredCaseView, principal: Principal) -> int | None:
        return None if view.node_ids is None else len(set(view.node_ids) - set(view.merged_added))

    monkeypatch.setattr(case_views_module, "visible_chosen", stored)
    _saved(shared=True)
    assert _listed("bob")[0]["chosen"] == len(CHOSEN)


def test_the_count_check_fails_with_the_port_counting_without_the_reader(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: the port's count read with a principal wider than the reader's (the `get_nodes`
    plant's shape). Bob is told every chosen node the store holds: the SECRET one, and the one in a
    dataset the case does not read."""
    real = FakeGraphPort.count_visible

    async def wide(self: FakeGraphPort, node_ids: Any, principal: Principal) -> int:
        everyone = principal.model_copy(update={"datasets": None, "clearance": "SECRET"})
        return await real(self, node_ids, everyone)

    monkeypatch.setattr(FakeGraphPort, "count_visible", wide)
    _saved(shared=True)
    assert _listed("bob")[0]["chosen"] == len(CHOSEN) - 1  # all but `never-held`


# --- opening, saving and sharing --------------------------------------------------------------


def test_open_save_and_share_count_what_the_reader_may_see(world: _World) -> None:
    """The creator's save and share answers, and every open, carry what that reader may read."""
    saved = _as("alice").post(VIEWS, json={"name": "Mine", "node_ids": CHOSEN})
    assert saved.status_code == 201, saved.json()
    assert saved.json()["chosen"] == ALICE_SEES
    shared = _as("alice").post(f"{VIEWS}/{saved.json()['id']}/share")
    assert shared.status_code == 200, shared.json()
    assert shared.json()["chosen"] == ALICE_SEES

    for who, sees in (("alice", ALICE_SEES), ("bob", BOB_SEES)):
        opened = _opened(who, saved.json()["id"])
        assert opened["view"]["chosen"] == sees
        assert len(opened["nodes"]) == sees  # the count and the items shown are the same number


def test_the_wire_check_fails_with_the_stored_count_restored(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: `StoredCaseView.wire` planted with its old body (the stored count, whoever asks).
    Every route that answers a `CaseView` then tells Bob five."""

    def stored(self: StoredCaseView, *, chosen: int | None) -> Any:
        from schemas.case_views import CaseView

        held = None if self.node_ids is None else len(set(self.node_ids) - set(self.merged_added))
        shown = self.model_dump(exclude={"node_ids", "layout", "merged_added"})
        return CaseView(**shown, chosen=held)

    monkeypatch.setattr(StoredCaseView, "wire", stored)
    view_id = _saved(shared=True)
    assert _opened("bob", view_id)["view"]["chosen"] == len(CHOSEN)
    assert _listed("bob")[0]["chosen"] == len(CHOSEN)


def test_a_creators_count_follows_their_clearance_now(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Alice's clearance drops to OFFICIAL after she saved a view of nodes she then read: her list
    and her open tell her two, not what she once saw."""
    view_id = _saved(shared=True)
    assert _listed("alice")[0]["chosen"] == ALICE_SEES
    lowered = views_world.PEOPLE["alice"].model_copy(update={"clearance": "OFFICIAL"})
    monkeypatch.setitem(views_world.PEOPLE, "alice", lowered)
    assert _listed("alice")[0]["chosen"] == BOB_SEES
    opened = _opened("alice", view_id)
    assert opened["view"]["chosen"] == BOB_SEES
    # The SECRET node she can no longer read is in no number she is told: not `missing` either.
    assert opened["missing"] == 0


# --- the hidden number, told to no one who may not see ----------------------------------------


def test_a_reader_is_never_told_how_many_are_hidden(world: _World) -> None:
    """Two shared views Bob sees alike (`open` and `near`), one with three more chosen nodes above
    or beyond him: every number he is given, in the list and on opening, is the same for both, and
    `missing` is nothing. The hidden three leave no trace in a count."""
    wide = _saved(shared=True, name="Wide")
    narrow = _saved(shared=True, node_ids=["open", "near"], name="Narrow")
    listed = {v["id"]: v for v in _listed("bob")}
    assert listed[wide]["chosen"] == listed[narrow]["chosen"] == BOB_SEES
    opened = {i: _opened("bob", i) for i in (wide, narrow)}
    for answer in opened.values():
        assert answer["missing"] == 0
        assert answer["view"]["chosen"] == BOB_SEES
    assert sorted(n["id"] for n in opened[wide]["nodes"]) == sorted(
        n["id"] for n in opened[narrow]["nodes"]
    )


def _re_marked(world: _World, _who: str, _mp: pytest.MonkeyPatch) -> None:
    """`near` is re-marked above everyone's clearance after the view was saved."""
    world.graph._graph_nodes["near"] = _in("src", node("near", "TOP SECRET"))


def _moved_elsewhere(world: _World, _who: str, _mp: pytest.MonkeyPatch) -> None:
    """`near` is now in a dataset the case does not read."""
    world.graph._graph_nodes["near"] = _in("other", node("near"))


def _deleted(world: _World, _who: str, _mp: pytest.MonkeyPatch) -> None:
    """`near` is gone from the store."""
    del world.graph._graph_nodes["near"]


def _lowered(world: _World, who: str, mp: pytest.MonkeyPatch) -> None:
    """The asker's own clearance is lowered to OFFICIAL: every SECRET node leaves their number."""
    lowered = views_world.PEOPLE[who].model_copy(update={"clearance": "OFFICIAL"})
    mp.setitem(views_world.PEOPLE, who, lowered)


#: What can happen to a chosen node after a view is saved, and to its asker: each leaves a node the
#: asker cannot read now, and none is a deletion the asker could have seen, which is all `missing`
#: counts (a node reverted while the asker could see it is counted: `test_case_view_missing.py`).
CHANGES = {
    "re_marked_above_them": _re_marked,
    "moved_to_a_dataset_the_case_does_not_read": _moved_elsewhere,
    "deleted": _deleted,
    "their_own_clearance_lowered": _lowered,
}
#: The creator, a reader (Editor) and a Viewer who may read what the creator may.
ASKERS = ("alice", "bob", "rita")


def _after_a_change(
    world: _World, change: str, who: str, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    """Alice saves and shares her five; `change` happens; `who` opens the view."""
    view_id = _saved(shared=True)
    CHANGES[change](world, who, monkeypatch)
    return _opened(who, view_id)


@pytest.mark.parametrize("who", ASKERS)
@pytest.mark.parametrize("change", sorted(CHANGES))
def test_no_number_includes_what_the_asker_may_not_see(
    world: _World, monkeypatch: pytest.MonkeyPatch, change: str, who: str
) -> None:
    """For the creator and for each reader alike, `missing` is nothing (the boards' rule: only an
    item lost is counted, and none was deleted here; a node hidden by a marking is counted nowhere),
    and `chosen` is exactly the nodes shown. Told "5 chosen, 3 shown, 2 missing" the creator would
    learn how many of the view's nodes are above their clearance or outside the case (C045)."""
    opened = _after_a_change(world, change, who, monkeypatch)
    assert opened["missing"] == 0
    assert opened["view"]["chosen"] == len(opened["nodes"])
    # The list agrees with the open answer: one number for what this person may see.
    assert _listed(who)[0]["chosen"] == opened["view"]["chosen"]


@pytest.mark.parametrize("who", ASKERS)
@pytest.mark.parametrize("change", sorted(CHANGES))
def test_the_missing_check_fails_with_the_difference_put_back(
    world: _World, monkeypatch: pytest.MonkeyPatch, change: str, who: str
) -> None:
    """Rule 15, at the real call site's shape: `open_view` asks `missing_for` with the graph, the
    view and the reader's principal. Planted with round 1's body (the chosen ids less the nodes the
    reader may see), every case that asserts a reader is told nothing fails."""

    async def difference(graph: Any, view: StoredCaseView, principal: Principal) -> int:
        ids = view.creators_choice() or []
        return len(set(ids)) - await graph.count_visible(ids, principal)

    monkeypatch.setattr(case_views_module, "missing_for", difference)
    opened = _after_a_change(world, change, who, monkeypatch)
    assert opened["missing"] != 0


def _shape(answer: dict[str, Any]) -> dict[str, Any]:
    """An opened answer without what differs by construction (the view's id, name and time)."""
    view = {k: v for k, v in answer["view"].items() if k not in ("id", "name", "created_at")}
    return {**answer, "view": view}


@pytest.mark.parametrize("who", ["alice", "bob"])
def test_a_missing_id_and_a_hidden_one_answer_alike(world: _World, who: str) -> None:
    """The probe: Alice saves two views that differ only in one id, `never-held` (which no one
    holds) in one and `elsewhere` (which exists, in a dataset the case does not read) in the other.
    Whoever asks, the open answer and the list's count are the same, so a saved id cannot be used
    to ask the store whether a hidden node exists (rule 3)."""
    absent = _saved(shared=True, node_ids=["open", "never-held"], name="Absent")
    hidden = _saved(shared=True, node_ids=["open", "elsewhere"], name="Hidden")
    assert _shape(_opened(who, absent)) == _shape(_opened(who, hidden))
    counts = {v["id"]: v["chosen"] for v in _listed(who)}
    assert counts[absent] == counts[hidden] == 1


def test_the_probe_check_fails_with_an_existence_count(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: `missing_for` planted to count the chosen ids the store does not hold (an existence
    lookup, the shape of `existing_node_ids`, which no route may call). Alice is then told one for
    the view with the absent id and nothing for the one with the hidden id: the answers differ."""
    held = world.graph._world_nodes()

    async def by_existence(graph: Any, view: StoredCaseView, principal: Principal) -> int:
        return sum(1 for i in set(view.node_ids or []) if i not in held)

    monkeypatch.setattr(case_views_module, "missing_for", by_existence)
    absent = _saved(shared=True, node_ids=["open", "never-held"], name="Absent")
    hidden = _saved(shared=True, node_ids=["open", "elsewhere"], name="Hidden")
    assert _opened("alice", absent)["missing"] != _opened("alice", hidden)["missing"]


# --- a batch expansion's view -----------------------------------------------------------------


def _batch_view_after_a_clearance_drop(batch_world: Any, monkeypatch: pytest.MonkeyPatch) -> str:
    """Alice's batch expansion has saved three nodes; her clearance then drops to OFFICIAL."""
    job_id = _started("alice")
    batch_world.run_queued()
    assert _status(job_id, "alice")["view"]["chosen"] == ALICE_SEES
    lowered = views_world.PEOPLE["alice"].model_copy(update={"clearance": "OFFICIAL"})
    monkeypatch.setitem(views_world.PEOPLE, "alice", lowered)
    return job_id


def test_a_batch_view_counts_what_its_requester_may_see_now(
    batch_world: Any, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """The view a finished batch expansion reports is counted as any other: after the job saved
    three nodes, Alice's clearance drops, and its status tells her two."""
    job_id = _batch_view_after_a_clearance_drop(batch_world, monkeypatch)
    assert _status(job_id, "alice")["view"]["chosen"] == BOB_SEES


def test_the_batch_check_fails_with_the_stored_length(
    batch_world: Any, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """Rule 15: the batch status route's count is `visible_chosen`'s too; planted to count the
    stored ids, Alice is still told three after her clearance dropped."""
    job_id = _batch_view_after_a_clearance_drop(batch_world, monkeypatch)

    async def stored(graph: Any, view: StoredCaseView, principal: Principal) -> int | None:
        return None if view.node_ids is None else len(set(view.node_ids))

    monkeypatch.setattr(case_views_module, "visible_chosen", stored)
    assert _status(job_id, "alice")["view"]["chosen"] == ALICE_SEES
