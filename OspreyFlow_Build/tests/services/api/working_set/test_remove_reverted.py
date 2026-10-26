"""ADR-127 decision 6 (B2-4c2): `WorkingSetService.remove_reverted`, a revert's removal from the
working sets, as against `remove`, which a reader makes.

`remove` is the reader's own act: it removes only ids whose stored body that reader may read, and
leaves a link standing after its end goes. A revert removes the load's own elements, which the
operator's principal may not be able to read, from **every case that holds any of them**, links
that end at a removed node included, and records what each was so that every connected reader is
sent the removal projected for them (ADR-124 decision 4). What a mistake would do, and the case
that catches it:

- a revert limited by a reader's clearance leaving a SECRET element on a canvas
  (`test_a_reverted_loads_elements_leave_every_case_holding_them_hidden_ones_included`);
- a case that holds none of the ids given a delta, or burning a sequence number
  (`test_a_case_holding_none_of_them_is_left_alone`);
- a link left to hang from a removed node, as `remove` leaves it
  (`test_a_link_that_ends_at_a_removed_node_goes_with_it`);
- a reader told a removal that names an element they may not read, or a different removal from the
  one a case without that element would give them
  (`test_each_reader_is_sent_the_removal_projected_for_them`);
- a reconnecting client restored what the revert removed, from the stored stream: a client one step
  behind replays the removal, and a client further back is sent a full snapshot
  (`test_the_stored_stream_no_longer_holds_what_was_removed`);
- a rerun that sends a second delta (`test_a_rerun_removes_nothing_and_sends_nothing`)."""

from __future__ import annotations

import pytest
from services.api.working_set.models import DeltaAdd, DeltaRemove, DeltaRemoveSent, DeltaSnapshot
from services.api.working_set.service import WorkingSetService

from schemas.domain import Subgraph

from .fakes import FakeGraphPort, FakeWorkingSetStore
from .test_visible_link import OFFICIAL_READER, SCHEME, SECRET_READER, edge, node


def _service(store: FakeWorkingSetStore) -> WorkingSetService:
    return WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), store, SCHEME)


async def _world() -> tuple[FakeWorkingSetStore, WorkingSetService]:
    """Three cases. `case-a` holds the load's nodes `n1`, `n-secret` (SECRET) and `keep`, its links
    `e1` and `e-secret`, and a link `e-other` of another load at `n1`. `case-b` holds `n1` only.
    `case-c` holds none of them."""
    store = FakeWorkingSetStore()
    await store.add_nodes("case-a", [node("n1"), node("n-secret", "SECRET"), node("keep")])
    await store.add_edges(
        "case-a",
        [
            edge("e1", "n1", "keep"),
            edge("e-secret", "n-secret", "keep", "SECRET"),
            edge("e-other", "n1", "keep"),
        ],
    )
    await store.add_nodes("case-b", [node("n1"), node("other")])
    await store.add_nodes("case-c", [node("unrelated")])
    return store, _service(store)


async def test_a_reverted_loads_elements_leave_every_case_holding_them_hidden_ones_included() -> (
    None
):
    store, service = await _world()
    removed = await service.remove_reverted(["n1", "n-secret"], ["e1", "e-secret"])

    assert sorted(r.investigation_id for r in removed) == ["case-a", "case-b"]
    assert set(await store.source_fidelity_nodes("case-a")) == {"keep"}
    assert set(await store.source_fidelity_nodes("case-b")) == {"other"}
    assert "e-secret" not in set(await store.source_fidelity_edges("case-a"))
    by_case = {r.investigation_id: r.delta for r in removed}
    delta_a = by_case["case-a"]
    assert isinstance(delta_a, DeltaRemove)
    assert set(delta_a.node_ids) == {"n1", "n-secret"}, "the SECRET node too: no reader's clearance"
    assert "e-secret" in delta_a.edge_ids
    assert set(by_case["case-b"].node_ids) == {"n1"} and by_case["case-b"].edge_ids == []
    # The record names what each was, whoever may read it.
    assert delta_a.removed is not None
    assert delta_a.removed.nodes["n-secret"].handling.classification == "SECRET"
    assert delta_a.removed.edges["e-secret"].handling.classification == "SECRET"
    assert (
        delta_a.removed.edges["e1"].source == "n1" and delta_a.removed.edges["e1"].target == "keep"
    )


async def test_a_case_holding_none_of_them_is_left_alone() -> None:
    store, service = await _world()
    seq_before = await store.current_seq("case-c")
    removed = await service.remove_reverted(["n1"], [])
    assert "case-c" not in {r.investigation_id for r in removed}
    assert await store.current_seq("case-c") == seq_before
    assert set(await store.source_fidelity_nodes("case-c")) == {"unrelated"}


async def test_a_link_that_ends_at_a_removed_node_goes_with_it() -> None:
    """`remove` leaves such a link stored, since every projected read leaves it out. A revert does
    not: nothing the load wrote, or hung from what it wrote, stays in a working set."""
    store, service = await _world()
    removed = await service.remove_reverted(["n1"], [])
    (in_a,) = [r for r in removed if r.investigation_id == "case-a"]
    assert set(in_a.delta.edge_ids) == {"e1", "e-other"}, "both links at n1, named or not"
    assert set(await store.source_fidelity_edges("case-a")) == {"e-secret"}
    assert in_a.delta.removed is not None and set(in_a.delta.removed.edges) == {"e1", "e-other"}


async def test_each_reader_is_sent_the_removal_projected_for_them() -> None:
    store, service = await _world()
    known = await store.source_fidelity_nodes("case-a")
    removed = await service.remove_reverted(["n1", "n-secret"], ["e1", "e-secret"])
    (in_a,) = [r.delta for r in removed if r.investigation_id == "case-a"]

    official = service.project_delta(in_a, OFFICIAL_READER, known)
    cleared = service.project_delta(in_a, SECRET_READER, known)
    assert isinstance(official, DeltaRemoveSent) and isinstance(cleared, DeltaRemoveSent)
    assert "n-secret" not in official.node_ids and "e-secret" not in official.edge_ids
    assert {"n-secret"} <= set(cleared.node_ids) and {"e-secret"} <= set(cleared.edge_ids)

    # What the OFFICIAL reader is sent equals what a case that never held the SECRET elements
    # would have sent them: the hidden ones leave no trace (rule 3).
    clean = FakeWorkingSetStore()
    await clean.add_nodes("case-a", [node("n1"), node("keep")])
    await clean.add_edges("case-a", [edge("e1", "n1", "keep"), edge("e-other", "n1", "keep")])
    clean_service = _service(clean)
    clean_known = await clean.source_fidelity_nodes("case-a")
    (without,) = await clean_service.remove_reverted(["n1"], ["e1"])
    expected = clean_service.project_delta(without.delta, OFFICIAL_READER, clean_known)
    assert isinstance(expected, DeltaRemoveSent)
    assert (sorted(official.node_ids), sorted(official.edge_ids)) == (
        sorted(expected.node_ids),
        sorted(expected.edge_ids),
    )


async def test_the_stored_stream_no_longer_holds_what_was_removed() -> None:
    """The delta stream keeps the bodies of what was added. A client behind the revert would replay
    them and be given the reverted elements back, so the stream is dropped and only the removal is
    stored: a client at the previous step replays the removal, anyone further back is sent a full
    snapshot, which is projected from the stores that no longer hold them."""
    store, service = await _world()
    before = await service.sync("case-a", SECRET_READER, last_acknowledged_seq=None)
    assert isinstance(before[0], DeltaSnapshot) and "n-secret" in {n.id for n in before[0].nodes}
    # A body added earlier is in the stored stream, and a client behind would replay it.
    added = await store.next_seq("case-a")
    await store.append_delta(
        "case-a", DeltaAdd(seq=added, nodes=[node("n-secret", "SECRET")], edges=[])
    )
    assert any("n-secret" in d.model_dump_json() for d in store._deltas["case-a"])
    await service.remove_reverted(["n1", "n-secret"], ["e1", "e-secret"])
    last = await store.current_seq("case-a")

    behind_by_one = await service.sync("case-a", SECRET_READER, last_acknowledged_seq=last - 1)
    assert [type(d).__name__ for d in behind_by_one] == ["DeltaRemoveSent"]
    far_behind = await service.sync("case-a", SECRET_READER, last_acknowledged_seq=0)
    (snapshot,) = far_behind
    assert isinstance(snapshot, DeltaSnapshot)
    assert {n.id for n in snapshot.nodes} == {"keep"}
    assert {e.id for e in snapshot.edges} == set()
    for delta in store._deltas["case-a"]:
        assert isinstance(delta, DeltaRemove), (
            "the only thing stored after the revert is the removal"
        )


async def test_a_rerun_removes_nothing_and_sends_nothing() -> None:
    store, service = await _world()
    await service.remove_reverted(["n1", "n-secret"], ["e1", "e-secret"])
    seqs = {c: await store.current_seq(c) for c in ("case-a", "case-b", "case-c")}
    again = await service.remove_reverted(["n1", "n-secret"], ["e1", "e-secret"])
    assert again == []
    assert {c: await store.current_seq(c) for c in seqs} == seqs


class _CrashesRightAfterTheRemoval(FakeWorkingSetStore):
    """A store whose process dies at the first call after the nodes are removed: the elements are
    gone and nothing more of the removal is stored."""

    def __init__(self) -> None:
        super().__init__()
        self._removed = False

    def _check(self) -> None:
        if self._removed:
            raise RuntimeError("the process died after the removal")

    async def remove_nodes(self, investigation_id: str, node_ids: object) -> None:
        await super().remove_nodes(investigation_id, node_ids)  # type: ignore[arg-type]
        self._removed = True

    async def next_seq(self, investigation_id: str) -> int:
        self._check()
        return await super().next_seq(investigation_id)

    async def append_delta(self, investigation_id: str, delta: object) -> None:
        self._check()
        await super().append_delta(investigation_id, delta)  # type: ignore[arg-type]


async def test_a_crash_after_the_removal_leaves_a_gap_so_every_client_is_sent_a_snapshot() -> None:
    """The removal is not rerun (nothing is held any more), so its delta can be lost. The sequence
    number is taken first, so the case's counter has moved past every client: a client that was up
    to date finds a stream with nothing after its number, which is a gap, and is sent a snapshot
    from the stores that no longer hold the elements, never `[]` (nothing to change)."""
    store = _CrashesRightAfterTheRemoval()
    await store.add_nodes("case-a", [node("n1"), node("n-secret", "SECRET"), node("keep")])
    service = _service(store)
    up_to_date_at = await store.current_seq("case-a")

    with pytest.raises(RuntimeError):
        await service.remove_reverted(["n1", "n-secret"], [])
    assert await store.node_ids("case-a") == {"keep"}, "the elements are gone"

    sent = await service.sync("case-a", SECRET_READER, last_acknowledged_seq=up_to_date_at)
    (snapshot,) = sent
    assert isinstance(snapshot, DeltaSnapshot)
    assert {n.id for n in snapshot.nodes} == {"keep"}
    # And nothing is left to find on a rerun: only the gap tells the clients.
    assert await service.remove_reverted(["n1", "n-secret"], []) == []


async def test_an_element_added_between_two_passes_is_removed_by_the_second() -> None:
    """A Conduit left running can add an element it read before the revert, after the first pass.
    The revert runs the removal again as its last step; the second pass finds only that element."""
    store, service = await _world()
    first = await service.remove_reverted(["n1"], [])
    assert {r.investigation_id for r in first} == {"case-a", "case-b"}
    await store.add_nodes("case-b", [node("n1")])  # an expand that had read the graph earlier
    second = await service.remove_reverted(["n1"], [])
    assert [r.investigation_id for r in second] == ["case-b"]
    assert second[0].delta.node_ids == ["n1"]
    assert await store.node_ids("case-b") == {"other"}
    assert await service.remove_reverted(["n1"], []) == []
