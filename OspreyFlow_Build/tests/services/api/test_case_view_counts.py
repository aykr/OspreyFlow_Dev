"""A shared view's count never includes items its reader may not see (C045; rules 3, 4, 7, 12, 15).

A view's `chosen` (every answer that carries a `CaseView`) is the count of its chosen nodes **this
reader may see now**, never the count its creator stored: a stored count tells a reader how many
nodes a shared view holds above their clearance. `CaseViewOpened.missing` follows the boards' rule
(`test_boards.py`, `missing` counts only what was lost): it is told to the view's creator, who
chose each item seeing it, and is never told to anyone else, so a number of hidden items is told to
no one who was not allowed to see them.

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
- `missing` handing a reader the hidden number: `test_a_reader_is_never_told_how_many_are_hidden`,
  red with `missing_for` returning the hidden number
  (`test_the_missing_check_fails_with_the_hidden_number_returned`);
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
from .test_case_views import CHOSEN, VIEWS, _as, _saved, _World, world  # noqa: F401  (a fixture)
from .working_set.fakes import FakeGraphPort

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
    assert _opened("alice", view_id)["view"]["chosen"] == BOB_SEES


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


def test_the_creator_is_told_what_they_can_no_longer_read(world: _World) -> None:
    """The boards' rule: `missing` is told to the creator, who chose each item seeing it. Alice,
    who may read three of her five, is told two; the two are not named."""
    view_id = _saved(shared=True)
    opened = _opened("alice", view_id)
    assert opened["missing"] == len(CHOSEN) - ALICE_SEES
    for hidden in ("elsewhere", "never-held"):
        assert hidden not in str(opened)


def test_the_missing_check_fails_with_the_hidden_number_returned(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, at the real call site's shape: `open_view` asks `missing_for` with the view, the
    reader and the nodes shown. Planted to hand back the hidden number, Bob is told three."""

    def hidden(view: StoredCaseView, reader: str, shown: Any) -> int:
        added = set(view.merged_added)
        return len(set(view.node_ids or []) - added) - sum(1 for n in shown if n.id not in added)

    monkeypatch.setattr(case_views_module, "missing_for", hidden)
    view_id = _saved(shared=True)
    assert _opened("bob", view_id)["missing"] == len(CHOSEN) - BOB_SEES


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
