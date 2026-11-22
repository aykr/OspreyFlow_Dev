"""A saved view's `missing` counts the deletions its reader could see, and nothing else (SE9;
ADR-144 Amendment 7; rules 3, 4, 7, 12, 15).

The store now records a deletion: the revert and the withdraw writes set `reverted_at` and
`reverted_by` with `reverted`, in the same statement. `CaseViewOpened.missing` is what the graph port
counts, for the reader's own principal, of the view's chosen nodes that are **deleted** and that the
reader's access step **would pass if they were live** (`GraphPort.count_deleted_visible`). The wire
keeps its shape: a number, 0 where nothing the reader could see is gone.

The world is `test_case_views.py`'s: five chosen ids (`open`, `near`, `secret`, `elsewhere`,
`never-held`), of which Alice (SECRET, the creator) may read three and Bob (OFFICIAL) two; `secret`
is above Bob; `elsewhere` is in a dataset the case does not read; `never-held` is held by nobody. A
deletion here is `FakeGraphPort.revert_elements`, which sets the flag and records the time and the
person as the adapter does. The routes are the real ones, through the real `get_principal`.

Folders read: none walked. The module imports `tests/services/api/test_case_views.py`,
`working_set/fakes.py`, and drives `services/api`
through the app in process; it opens no repository folder, so it needs no scan row.

What a mistake here would do, and the case that fails for it (each also shown red, rule 15, by the
`*_fails_*` plant beside it, planted at the shape the real call site has: the port method the
Conduit calls, or the Conduit function `open_view` calls):

1. a deletion the reader could see, not counted:
   `test_a_deleted_item_the_reader_could_see_is_counted`, red with `missing_for` returning 0
   (`test_the_counted_check_fails_with_nothing_counted`);
2. an item never visible to the reader, then deleted, counted:
   `test_an_item_never_visible_then_deleted_is_counted_nowhere`, red with the port counting every
   deletion (`test_the_never_visible_check_fails_with_every_deletion_counted`);
3. an item hidden by a clearance or a dataset after the save, then deleted, counted:
   `test_an_item_hidden_by_clearance_or_dataset_then_deleted_is_counted_nowhere`, red with the
   port's record read without the reader's access step
   (`test_the_hidden_check_fails_with_the_record_read_without_the_access_step`);
4. an item deleted and written again, counted as missing:
   `test_a_deleted_then_recreated_item_is_not_missing`, red with the deletion's record read
   without the flag's clear (`test_the_recreated_check_fails_with_the_record_read_without_its_clear`);
5. a reader's own deletion unseen by them, or another person's deletion of something they may not
   see told to them: `test_a_reader_sees_their_own_deletion_and_not_one_they_could_not_see`, red with
   the creator's own count told to everyone (`test_the_own_check_fails_with_the_deleters_count_for_all`);
6. one count for every reader of a shared view:
   `test_a_shared_view_counts_each_readers_own_visibility`, red with the creator's principal asked
   for every reader (`test_the_shared_check_fails_with_one_count_for_all_readers`);
7. a missing id and a hidden deleted one answering differently, which lets a saver of views probe
   the store: `test_a_missing_id_and_a_hidden_deleted_one_answer_alike`, red with an existence
   lookup on the record (`test_the_probe_check_fails_with_an_existence_lookup_on_the_record`).

And: a superseded node is not a deletion, and a deletion with no time counts
(`test_a_supersession_is_not_a_deletion`, `test_a_deletion_written_before_the_store_kept_a_time_counts`);
the port is asked for the creator's choice and for the reader (`test_the_port_is_asked_for_the_readers_own_count_of_the_creators_choice`);
no response, log line or audit row carries a count of what the reader may not see, and the stored
count never reaches the wire (`test_no_response_log_or_audit_row_carries_what_the_reader_may_not_see`).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from services.api import case_views as case_views_module

from schemas.domain import Principal

from . import test_case_views as views_world
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

ASKERS = ("alice", "bob", "rita")


def _delete(world: _World, node_id: str, *, by: str = "alice") -> None:
    """The store's revert of one node, as the adapter records it (the flag, the time, the person)."""
    asyncio.run(world.graph.revert_elements([node_id], [], "tx", by=by))


def _opened(who: str, view_id: str) -> dict[str, Any]:
    answer = _as(who).get(f"{VIEWS}/{view_id}")
    assert answer.status_code == 200, answer.json()
    body: dict[str, Any] = answer.json()
    return body


def _missing(who: str, view_id: str) -> int:
    return int(_opened(who, view_id)["missing"])


def _shape(answer: dict[str, Any]) -> dict[str, Any]:
    """An opened answer without what differs by construction (the view's id, name and time)."""
    view = {k: v for k, v in answer["view"].items() if k not in ("id", "name", "created_at")}
    return {**answer, "view": view}


# --- 1: a deletion the reader could see is counted --------------------------------------------


def test_a_deleted_item_the_reader_could_see_is_counted(world: _World) -> None:
    """`near` is OFFICIAL, in the case's dataset: Bob, Alice and Rita could each see it. It is
    deleted: each is told of one, and the items shown and `chosen` are what they may still see."""
    view_id = _saved(shared=True)
    assert [_missing(who, view_id) for who in ASKERS] == [0, 0, 0]
    _delete(world, "near")
    for who in ASKERS:
        opened = _opened(who, view_id)
        assert opened["missing"] == 1, who
        assert "near" not in [n["id"] for n in opened["nodes"]]
        assert opened["view"]["chosen"] == len(opened["nodes"])  # `chosen` is still what is shown


def test_the_counted_check_fails_with_nothing_counted(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, at `open_view`'s call site: `missing_for` planted with the old body (0)."""

    async def nothing(*_: Any, **__: Any) -> int:
        return 0

    monkeypatch.setattr(case_views_module, "missing_for", nothing)
    view_id = _saved(shared=True)
    _delete(world, "near")
    assert _missing("bob", view_id) == 0  # the case above asserts 1


# --- 2: never visible, then deleted: counted nowhere ------------------------------------------


def test_an_item_never_visible_then_deleted_is_counted_nowhere(world: _World) -> None:
    """`secret` is above Bob from the start. It is deleted: Bob is told nothing of it, and his
    answer is the one he was given before (Alice, who could see it, is told of one)."""
    view_id = _saved(shared=True)
    before = _opened("bob", view_id)
    _delete(world, "secret")
    after = _opened("bob", view_id)
    assert after["missing"] == 0
    assert _shape(after) == _shape(before)
    assert _missing("alice", view_id) == 1
    assert _missing("rita", view_id) == 1


def test_the_never_visible_check_fails_with_every_deletion_counted(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, at the port's own method: a count that takes every deletion, the reader's access
    step left out. Bob is then told of the SECRET node."""

    async def every_deletion(self: FakeGraphPort, node_ids: Any, principal: Principal) -> int:
        held = self._world_nodes()
        return sum(1 for i in set(node_ids) if i in held and held[i].audit.reverted)

    monkeypatch.setattr(FakeGraphPort, "count_deleted_visible", every_deletion)
    view_id = _saved(shared=True)
    _delete(world, "secret")
    assert _missing("bob", view_id) == 1  # the case above asserts 0


# --- 3: hidden by a clearance or a dataset after the save, then deleted -----------------------


def _re_marked_then_deleted(world: _World) -> None:
    """`near` is re-marked SECRET after the save, then deleted: above Bob, not above Alice or Rita."""
    world.graph._graph_nodes["near"] = _in("src", node("near", "SECRET"))
    _delete(world, "near")


def _moved_then_deleted(world: _World) -> None:
    """`near` is moved to a dataset the case does not read, then deleted."""
    world.graph._graph_nodes["near"] = _in("other", node("near"))
    _delete(world, "near")


def _elsewhere_deleted(world: _World) -> None:
    """`elsewhere` (in a dataset the case never read) is deleted."""
    _delete(world, "elsewhere")


HIDDEN_THEN_DELETED = {
    "re_marked_above_bob_then_deleted": _re_marked_then_deleted,
    "moved_to_a_dataset_the_case_does_not_read_then_deleted": _moved_then_deleted,
    "never_in_the_cases_datasets_then_deleted": _elsewhere_deleted,
}
#: Each change and the askers it leaves nothing to tell: the marking is above Bob alone; a dataset
#: the case does not read is out of everyone's world.
LEAVES_NOTHING_FOR = {
    "re_marked_above_bob_then_deleted": ("bob",),
    "moved_to_a_dataset_the_case_does_not_read_then_deleted": ASKERS,
    "never_in_the_cases_datasets_then_deleted": ASKERS,
}
HIDDEN_PAIRS = [(c, who) for c in sorted(HIDDEN_THEN_DELETED) for who in LEAVES_NOTHING_FOR[c]]


@pytest.mark.parametrize(("change", "who"), HIDDEN_PAIRS)
def test_an_item_hidden_by_clearance_or_dataset_then_deleted_is_counted_nowhere(
    world: _World, change: str, who: str
) -> None:
    view_id = _saved(shared=True)
    HIDDEN_THEN_DELETED[change](world)
    assert _missing(who, view_id) == 0


def test_an_item_re_marked_above_one_reader_is_still_counted_for_those_who_may_see_it(
    world: _World,
) -> None:
    """The filter is the reader's own: `near` re-marked SECRET and deleted is nothing to Bob, and
    one deletion to Alice and Rita, who can read SECRET."""
    view_id = _saved(shared=True)
    _re_marked_then_deleted(world)
    assert [_missing(who, view_id) for who in ASKERS] == [1, 0, 1]


def test_a_lowered_clearance_then_a_deletion_is_counted_nowhere(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Alice's own clearance is lowered to OFFICIAL after she saved; `secret` is then deleted. It is
    above her now: she is told nothing of it (and she is not told of `near`, still live)."""
    view_id = _saved(shared=True)
    lowered = views_world.PEOPLE["alice"].model_copy(update={"clearance": "OFFICIAL"})
    monkeypatch.setitem(views_world.PEOPLE, "alice", lowered)
    _delete(world, "secret")
    assert _missing("alice", view_id) == 0


@pytest.mark.parametrize(("change", "who"), HIDDEN_PAIRS)
def test_the_hidden_check_fails_with_the_record_read_without_the_access_step(
    world: _World, monkeypatch: pytest.MonkeyPatch, change: str, who: str
) -> None:
    """Rule 15, at the port's own method: the deletion record read with a principal wider than the
    reader's (the shape the `count_visible` plant uses). Every reader is told of the hidden node."""
    real = FakeGraphPort.count_deleted_visible

    async def wide(self: FakeGraphPort, node_ids: Any, principal: Principal) -> int:
        everyone = principal.model_copy(update={"datasets": None, "clearance": "SECRET"})
        return await real(self, node_ids, everyone)

    monkeypatch.setattr(FakeGraphPort, "count_deleted_visible", wide)
    view_id = _saved(shared=True)
    HIDDEN_THEN_DELETED[change](world)
    assert _missing(who, view_id) != 0  # the case above asserts 0


# --- 4: deleted, then written again --------------------------------------------------------------


def test_a_deleted_then_recreated_item_is_not_missing(world: _World) -> None:
    """`near` is deleted, then written again under its own id (ADR-127 Amendment 6): it is live, it
    is shown, and nothing is missing. Written again and deleted once more, it is missing once."""
    view_id = _saved(shared=True)
    _delete(world, "near")
    assert _missing("bob", view_id) == 1
    world.graph.recreate(_in("src", node("near")))
    opened = _opened("bob", view_id)
    assert opened["missing"] == 0
    assert sorted(n["id"] for n in opened["nodes"]) == ["near", "open"]
    _delete(world, "near")
    assert _missing("bob", view_id) == 1


def test_the_recreated_check_fails_with_the_record_read_without_its_clear(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: the deletion's own record (its time and person, which the fake keeps beside the
    flag) read without the flag, so a node once deleted is missing for good, written again or not."""
    view_id = _saved(shared=True)
    ever_deleted: set[str] = set()
    real_delete = FakeGraphPort.revert_elements

    async def remembering(
        self: FakeGraphPort, node_ids: Any, edge_ids: Any, tx: Any, **kw: Any
    ) -> None:
        ever_deleted.update(node_ids)
        await real_delete(self, node_ids, edge_ids, tx, **kw)

    async def by_the_record(self: FakeGraphPort, node_ids: Any, principal: Principal) -> int:
        return sum(1 for i in set(node_ids) if i in ever_deleted)

    monkeypatch.setattr(FakeGraphPort, "revert_elements", remembering)
    monkeypatch.setattr(FakeGraphPort, "count_deleted_visible", by_the_record)
    _delete(world, "near")
    world.graph.recreate(_in("src", node("near")))
    assert _missing("bob", view_id) == 1  # the case above asserts 0


# --- 5: a reader sees their own deletion, and not one they could not see ------------------------


def test_a_reader_sees_their_own_deletion_and_not_one_they_could_not_see(world: _World) -> None:
    """Bob deletes `near`, which he could see: he is told of one. Alice deletes `secret`, which he
    could not: Bob is still told of one (his own), and Alice of two (the node she deleted, and the
    one Bob did, which she could see too)."""
    view_id = _saved(shared=True)
    _delete(world, "near", by="bob")
    assert _missing("bob", view_id) == 1
    _delete(world, "secret", by="alice")
    assert _missing("bob", view_id) == 1  # Alice's deletion is above him: nothing of it reaches him
    assert _missing("alice", view_id) == 2
    assert world.graph.deletion_records["near"][1] == "bob"
    assert world.graph.deletion_records["secret"][1] == "alice"


def test_the_own_check_fails_with_the_deleters_count_for_all(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, at `open_view`'s call site: `missing_for` planted to tell every reader what the
    view's creator is told. Bob is then told of a node he could not see."""
    real = case_views_module.missing_for

    async def creators(graph: Any, view: Any, principal: Principal) -> int:
        return int(await real(graph, view, views_world.PEOPLE[view.created_by]))

    monkeypatch.setattr(case_views_module, "missing_for", creators)
    view_id = _saved(shared=True)
    _delete(world, "secret", by="alice")
    assert _missing("bob", view_id) == 1  # the case above asserts 0 for the same deletion


# --- 6: a shared view counts each reader's own visibility ---------------------------------------


def test_a_shared_view_counts_each_readers_own_visibility(world: _World) -> None:
    """One shared view; `near` and `secret` deleted. Alice (SECRET) and Rita (SECRET, a Viewer) are
    told of two, Bob (OFFICIAL) of one; a reader whose clearance is lowered after is told of one."""
    view_id = _saved(shared=True)
    _delete(world, "near")
    _delete(world, "secret")
    assert {who: _missing(who, view_id) for who in ASKERS} == {"alice": 2, "bob": 1, "rita": 2}
    # The same answer from the list: `chosen` is theirs too, and no list entry carries `missing`.
    for who, sees in (("alice", 1), ("bob", 1), ("rita", 1)):
        (listed,) = _as(who).get(VIEWS).json()
        assert listed["chosen"] == sees
        assert "missing" not in listed


def test_the_shared_check_fails_with_one_count_for_all_readers(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, at the port's own method: the count made for one principal (the view's creator)
    whoever opens. Bob is then told what Alice is."""
    real = FakeGraphPort.count_deleted_visible

    async def for_the_creator(self: FakeGraphPort, node_ids: Any, principal: Principal) -> int:
        return await real(self, node_ids, views_world.PEOPLE["alice"])

    monkeypatch.setattr(FakeGraphPort, "count_deleted_visible", for_the_creator)
    view_id = _saved(shared=True)
    _delete(world, "near")
    _delete(world, "secret")
    assert _missing("bob", view_id) == 2  # the case above asserts 1


# --- 7: a missing id and a hidden deleted one answer alike -------------------------------------


@pytest.mark.parametrize("who", ["alice", "bob"])
def test_a_missing_id_and_a_hidden_deleted_one_answer_alike(world: _World, who: str) -> None:
    """The probe, as `test_case_view_counts.py`'s, with a deletion: two views differ in one id,
    `never-held` (nobody holds it) in one and `elsewhere` (held, in a dataset the case does not read,
    then deleted) in the other. Whoever asks, the open answer and the list's count are the same, so a
    saved id cannot ask the store whether a hidden node ever existed (rule 3)."""
    absent = _saved(shared=True, node_ids=["open", "never-held"], name="Absent")
    hidden = _saved(shared=True, node_ids=["open", "elsewhere"], name="Hidden")
    _delete(world, "elsewhere")
    assert _shape(_opened(who, absent)) == _shape(_opened(who, hidden))
    counts = {v["id"]: v["chosen"] for v in _as(who).get(VIEWS).json()}
    assert counts[absent] == counts[hidden] == 1
    # And the same for a node above the reader (Bob), deleted: the answer is that of an absent id.
    secret = _saved(shared=True, node_ids=["open", "secret"], name="Secret")
    _delete(world, "secret")
    if who == "bob":
        assert _shape(_opened(who, secret)) == _shape(_opened(who, absent))


def test_the_probe_check_fails_with_an_existence_lookup_on_the_record(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: the port's count planted as an existence lookup on the record (the ids the store
    holds that are not readable live now, deleted or hidden alike). The hidden id then answers
    differently from the one nobody holds."""

    async def held_but_not_live(self: FakeGraphPort, node_ids: Any, principal: Principal) -> int:
        held = self._world_nodes()
        live = {n.id for n in await self.get_nodes(list(node_ids), principal)}
        return sum(1 for i in set(node_ids) if i in held and i not in live)

    monkeypatch.setattr(FakeGraphPort, "count_deleted_visible", held_but_not_live)
    absent = _saved(shared=True, node_ids=["open", "never-held"], name="Absent")
    hidden = _saved(shared=True, node_ids=["open", "elsewhere"], name="Hidden")
    _delete(world, "elsewhere")
    assert _missing("alice", absent) != _missing("alice", hidden)  # the case above asserts alike


# --- what is deleted, and what is not ------------------------------------------------------------


def test_a_supersession_is_not_a_deletion(world: _World) -> None:
    """A correction replaces `near` with a revision of its own: the old node keeps `superseded_by`
    and is not reverted. It is not missing; and one that is superseded and also reverted is not
    counted either (a supersession is a correction, never a deletion)."""
    view_id = _saved(shared=True)
    old = world.graph._graph_nodes["near"]
    audit = old.audit.model_copy(update={"superseded_by": "near-2"})
    world.graph._graph_nodes["near"] = old.model_copy(update={"audit": audit})
    assert _missing("bob", view_id) == 0
    _delete(world, "near")
    assert _missing("bob", view_id) == 0


def test_a_deletion_written_before_the_store_kept_a_time_counts(world: _World) -> None:
    """A node reverted before this slice carries no `reverted_at` and no `reverted_by`: it counts
    for a reader who could see it. The time is for the record, not for the count."""
    view_id = _saved(shared=True)
    _delete(world, "near")
    world.graph.deletion_records["near"] = (None, None)
    assert _missing("bob", view_id) == 1
    del world.graph.deletion_records["near"]  # not even a record: the flag alone
    assert _missing("bob", view_id) == 1


def test_a_filtered_view_and_a_view_of_nothing_have_no_missing(world: _World) -> None:
    _delete(world, "near")
    filtered = _as("alice").post(
        VIEWS, json={"name": "People", "filter": {"entity_types": ["Person"]}}
    )
    assert filtered.status_code == 201, filtered.json()
    assert _missing("alice", filtered.json()["id"]) == 0
    assert world.graph.count_deleted_visible_requests == []  # no chosen ids: no question asked


def test_the_port_is_asked_for_the_readers_own_count_of_the_creators_choice(
    world: _World,
) -> None:
    """`missing` is the port's count for the opener's principal over the creator's choice: a merged
    drawing's added nodes are not in it, and neither is the stored count anywhere in the question."""
    view_id = _saved(shared=True, node_ids=["open", "near", "secret", "elsewhere"])
    held = world.views.views[view_id]
    world.views.views[view_id] = held.model_copy(update={"merged_added": ["near"]})
    _delete(world, "near")  # a drawn node the merge added: never counted, whoever may see it
    world.graph.count_deleted_visible_requests.clear()
    assert _missing("bob", view_id) == 0
    ((asked, who),) = world.graph.count_deleted_visible_requests
    assert who.id == "bob"
    assert sorted(asked) == ["elsewhere", "open", "secret"]


# --- nothing of what the reader may not see, anywhere --------------------------------------------


def test_no_response_log_or_audit_row_carries_what_the_reader_may_not_see(
    world: _World, caplog: pytest.LogCaptureFixture
) -> None:
    """Bob opens, lists, saves and shares around a view in which a node above him and a node outside
    the case have been deleted: no answer names them or a number that counts them, the view's stored
    count (five) is on no answer, and no log line or audit row of the call says more."""
    caplog.set_level(logging.DEBUG)
    view_id = _saved(shared=True)
    for hidden in ("secret", "elsewhere"):
        _delete(world, hidden)
    audited = len(world.audit.records)
    answers = [_as("bob").get(f"{VIEWS}/{view_id}"), _as("bob").get(VIEWS)]
    for answer in answers:
        assert answer.status_code == 200, answer.json()
        for hidden in ("secret", "elsewhere", "never-held"):
            assert hidden not in answer.text
    assert [v["chosen"] for v in answers[1].json()] == [2]  # the list: what he may see, not five
    opened = answers[0].json()
    assert opened["missing"] == 0
    assert opened["view"]["chosen"] == 2  # what he may see, not the stored five
    assert len(world.audit.records) == audited  # opening a view writes no audit row
    for line in caplog.messages:
        for hidden in ("secret", "elsewhere", "never-held"):
            assert hidden not in line
    assert world.graph.count_deleted_visible_requests, "the count was made through the port"
    assert all(who.id == "bob" for _, who in world.graph.count_deleted_visible_requests)
