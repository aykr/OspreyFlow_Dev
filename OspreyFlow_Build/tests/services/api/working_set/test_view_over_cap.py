"""A view pushed past the cap (ADR-124 decision 2, rules 2 and 3).

A reader's cap counts only their own view, so a less-cleared colleague's ordinary work, or a
restore that keeps what its restorer cannot read, can take a more-cleared reader's projected view
past it. Every path that would send that reader their view checks it first, counted from the
counted access index and never from bodies: `sync`'s full snapshot, its catch-up path and the live
forward. A view past a cap is answered with `DeltaViewOverCap` (the reader's own figures, the same
typed shape as `limit_exceeded`) in place of the snapshot or delta, and nothing further is sent on
that socket until a resync with no last sequence runs the full-snapshot path again. The server
keeps no state for a stuck reader beyond a flag on the open connection.

The caps are monkeypatched small, as `test_restore_and_remove.py` does.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any

import pytest
from services.api.app import _forward_notifications, _handle_resync_requests, _SocketState
from services.api.working_set import service as service_module
from services.api.working_set.models import (
    DeltaAdd,
    DeltaRemove,
    DeltaSnapshot,
    DeltaViewOverCap,
    RemovedElement,
    RemovedRecord,
    WorkingSetDeltaSent,
)
from services.api.working_set.service import WorkingSetService
from starlette.websockets import WebSocketDisconnect

from schemas.domain import Node, Subgraph

from .fakes import FakeGraphPort, FakeWorkingSetStore
from .test_visible_link import OFFICIAL_READER, SCHEME, edge, node

CASE = "inv-1"


@pytest.fixture(autouse=True)
def small_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    """Three nodes and two links."""
    monkeypatch.setattr(service_module, "MAX_NODES", 3)
    monkeypatch.setattr(service_module, "MAX_EDGES", 2)


def _service(store: FakeWorkingSetStore) -> WorkingSetService:
    return WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), store, SCHEME)


def _readable(count: int) -> list[Node]:
    return [node(f"n{i}") for i in range(count)]


async def _store(readable: int, hidden: int = 0, *, links: int = 0) -> FakeWorkingSetStore:
    store = FakeWorkingSetStore()
    await store.add_nodes(
        CASE, [*_readable(readable), *(node(f"h{i}", "SECRET") for i in range(hidden))]
    )
    if links:
        await store.add_edges(CASE, [edge(f"e{i}", "n0", "n1") for i in range(links)])
    return store


# --- (a) the full snapshot ----------------------------------------------------------------------


async def test_a_full_snapshot_over_the_node_cap_is_answered_with_the_readers_own_figures() -> None:
    """Violation caught (rule 2, decision 2): the reader sent a snapshot past the cap. They are sent
    `DeltaViewOverCap` with their own figure, the three options and nothing else."""
    store = await _store(4)

    sent = await _service(store).sync(CASE, OFFICIAL_READER, last_acknowledged_seq=None)

    assert [type(d) for d in sent] == [DeltaViewOverCap]
    over = sent[0]
    assert isinstance(over, DeltaViewOverCap)
    assert (over.would_be.cap_kind, over.would_be.cap, over.would_be.would_be) == ("nodes", 3, 4)
    assert set(over.would_be.options) == {"branch", "filter", "promote_to_batch"}
    assert set(over.model_dump()) == {"seq", "op", "would_be"}


async def test_a_full_snapshot_over_the_link_cap_names_the_link_cap() -> None:
    store = await _store(3, links=3)

    (over,) = await _service(store).sync(CASE, OFFICIAL_READER, last_acknowledged_seq=None)

    assert isinstance(over, DeltaViewOverCap)
    assert (over.would_be.cap_kind, over.would_be.cap, over.would_be.would_be) == ("edges", 2, 3)


async def test_a_view_within_the_cap_is_sent_as_it_always_was() -> None:
    store = await _store(3, links=2)

    (snapshot,) = await _service(store).sync(CASE, OFFICIAL_READER, last_acknowledged_seq=None)

    assert isinstance(snapshot, DeltaSnapshot) and len(snapshot.nodes) == 3


# --- (b) the catch-up path ----------------------------------------------------------------------


async def _catching_up(readable: int, hidden: int = 0) -> list[WorkingSetDeltaSent]:
    """A store that held two nodes at sequence 1 and now holds `readable` and `hidden`, a delta
    after the first; a reader at sequence 1 reconnects."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, _readable(2))
    await store.next_seq(CASE)
    await store.append_delta(CASE, DeltaAdd(seq=1, nodes=_readable(2)))
    more = [
        *(node(f"n{i}") for i in range(2, readable)),
        *(node(f"h{i}", "SECRET") for i in range(hidden)),
    ]
    await store.add_nodes(CASE, more)
    await store.next_seq(CASE)
    await store.append_delta(CASE, DeltaAdd(seq=2, nodes=more))
    return await _service(store).sync(CASE, OFFICIAL_READER, last_acknowledged_seq=1)


async def test_a_catch_up_that_leaves_the_view_over_the_cap_is_answered_with_the_figures() -> None:
    """Violation caught: the catch-up path replaying deltas that take the reader's view past the
    cap. The deltas are replaced by `DeltaViewOverCap`, stamped with the last sequence."""
    sent = await _catching_up(readable=4)

    assert [type(d) for d in sent] == [DeltaViewOverCap]
    over = sent[0]
    assert isinstance(over, DeltaViewOverCap)
    assert (over.seq, over.would_be.would_be) == (2, 4)


async def test_a_catch_up_within_the_cap_replays_its_deltas() -> None:
    sent = await _catching_up(readable=3)

    assert [type(d) for d in sent] == [DeltaAdd]


# --- rule 3: hidden stored items move neither the figure nor the outcome -------------------


async def test_hidden_stored_items_move_neither_the_figure_nor_the_outcome_on_any_path() -> None:
    """Violation caught (rule 3): a figure counted over the stored whole, so a reader could tell
    how much is hidden by when they are told they are over. Cases that differ only in stored items
    the reader may not read give the same answer by each path."""
    for hidden in (0, 5):
        full = await _service(await _store(4, hidden)).sync(
            CASE, OFFICIAL_READER, last_acknowledged_seq=None
        )
        fits = await _service(await _store(3, hidden)).sync(
            CASE, OFFICIAL_READER, last_acknowledged_seq=None
        )
        caught_up = await _catching_up(readable=4, hidden=hidden)
        assert [type(d) for d in full] == [DeltaViewOverCap]
        assert full[0].model_dump()["would_be"]["would_be"] == 4  # type: ignore[attr-defined]
        assert [type(d) for d in fits] == [DeltaSnapshot]
        assert caught_up[0].model_dump()["would_be"]["would_be"] == 4  # type: ignore[attr-defined]


# --- (c) the live forward ---------------------------------------------------------------------


class _Socket:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


class _Subscription:
    def __init__(self, messages: Sequence[str]) -> None:
        self._messages = messages

    async def listen(self) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "subscribe", "data": 1}
        for message in self._messages:
            yield {"type": "message", "data": message.encode()}


def _added(seq: int, *nodes: Node) -> str:
    return DeltaAdd(seq=seq, nodes=list(nodes)).model_dump_json()


async def _forwarded(
    service: WorkingSetService, messages: Sequence[str], state: _SocketState | None = None
) -> list[dict[str, Any]]:
    socket = _Socket()
    await _forward_notifications(
        _Subscription(messages),
        socket,
        service,
        CASE,
        OFFICIAL_READER,
        state,  # type: ignore[arg-type]
    )
    return socket.sent


async def test_the_live_forward_answers_a_delta_that_takes_the_view_over_the_cap() -> None:
    """Violation caught: a live push that takes the reader's view past the cap sent as it came. The
    reader is sent `DeltaViewOverCap` with their figures, and the socket is marked stuck."""
    store = await _store(4)  # the store holds the delta's node already
    state = _SocketState()

    sent = await _forwarded(_service(store), [_added(1, node("n3"))], state)

    assert [m["op"] for m in sent] == ["view_over_cap"]
    assert sent[0]["would_be"]["would_be"] == 4 and state.stuck is True


async def test_after_a_view_over_the_cap_the_forward_sends_nothing_more() -> None:
    """The server's only memory of a stuck reader is this flag: every later push on the socket is
    dropped until a resync with no last sequence."""
    store = await _store(4)
    state = _SocketState()

    sent = await _forwarded(
        _service(store),
        [_added(1, node("n3")), _added(2, node("n0")), _added(3, node("n1"))],
        state,
    )

    assert [m["op"] for m in sent] == ["view_over_cap"]


async def test_the_live_forward_within_the_cap_sends_every_delta() -> None:
    store = await _store(3)

    sent = await _forwarded(_service(store), [_added(1, node("n2")), _added(2, node("n1"))])

    assert [m["op"] for m in sent] == ["add", "add"]


async def test_hidden_stored_items_do_not_move_the_forwards_figure() -> None:
    sent_by_hidden = []
    for hidden in (0, 5):
        store = await _store(4, hidden)
        sent_by_hidden.append(await _forwarded(_service(store), [_added(1, node("n3"))]))

    assert sent_by_hidden[0] == sent_by_hidden[1]
    assert sent_by_hidden[0][0]["would_be"]["would_be"] == 4


def _counting(store: FakeWorkingSetStore) -> list[int]:
    reads: list[int] = []
    real = store.access_counts

    async def counted(investigation_id: str) -> Any:
        reads.append(1)
        return await real(investigation_id)

    store.access_counts = counted  # type: ignore[method-assign]
    return reads


async def test_the_forward_recounts_only_when_a_delta_adds_something_the_reader_can_read() -> None:
    """The cost on the live path (decision 2): a removal, and an addition of nothing the reader may
    read, are sent without a recount; an addition they can read costs one."""
    store = await _store(4, 1)  # over the cap already
    reads = _counting(store)
    removal = DeltaRemove(
        seq=1,
        node_ids=["n0"],
        removed=RemovedRecord(nodes={"n0": RemovedElement(handling=node("n0").handling)}),
    ).model_dump_json()
    hidden_addition = _added(2, node("h0", "SECRET"))

    sent = await _forwarded(_service(store), [removal, hidden_addition])

    assert [m["op"] for m in sent] == ["remove", "add"]
    assert reads == []  # not one count was read

    await _forwarded(_service(store), [_added(3, node("n3"))])
    assert len(reads) >= 1


# --- the resync: no last sequence runs the full-snapshot path again -----------------------------


class _ResyncSocket(_Socket):
    """Asks for resyncs in turn, running a hook before each, then disconnects."""

    def __init__(
        self, asks: Sequence[tuple[int | None, Callable[[], Awaitable[None]] | None]]
    ) -> None:
        super().__init__()
        self._asks = list(asks)

    async def receive_json(self) -> dict[str, Any]:
        if not self._asks:
            raise WebSocketDisconnect()
        last, before = self._asks.pop(0)
        if before is not None:
            await before()
        return {"last_acknowledged_seq": last}


async def _resynced(
    service: WorkingSetService,
    asks: Sequence[tuple[int | None, Callable[[], Awaitable[None]] | None]],
    state: _SocketState,
) -> list[dict[str, Any]]:
    socket = _ResyncSocket(asks)
    with pytest.raises(WebSocketDisconnect):
        await _handle_resync_requests(socket, service, CASE, OFFICIAL_READER, state)  # type: ignore[arg-type]
    return socket.sent


async def test_a_resync_with_no_last_sequence_rechecks_and_sends_the_snapshot_once_under() -> None:
    """Violation caught: a stuck reader never freed, or freed without a check. "Try again" is a
    resync with no last sequence: it runs the full-snapshot path, which is answered with
    `DeltaViewOverCap` again while the view is over, and with the snapshot once it is back under;
    the socket is then no longer stuck."""
    store = await _store(4)
    state = _SocketState(stuck=True)

    async def a_colleague_removes_one() -> None:
        await store.remove_nodes(CASE, ["n3"])

    sent = await _resynced(_service(store), [(None, None), (None, a_colleague_removes_one)], state)

    assert [m["op"] for m in sent] == ["view_over_cap", "snapshot"]
    assert len(sent[1]["nodes"]) == 3
    assert state.stuck is False


async def test_a_resync_with_a_last_sequence_while_stuck_sends_nothing() -> None:
    store = await _store(4)
    state = _SocketState(stuck=True)

    sent = await _resynced(_service(store), [(0, None), (5, None)], state)

    assert sent == [] and state.stuck is True


async def test_the_forward_resumes_after_a_resync_frees_the_socket() -> None:
    store = await _store(3)
    state = _SocketState(stuck=True)

    assert await _forwarded(_service(store), [_added(1, node("n0"))], state) == []
    await _resynced(_service(store), [(None, None)], state)
    sent = await _forwarded(_service(store), [_added(2, node("n1"))], state)

    assert [m["op"] for m in sent] == ["add"]


# --- the try-again race: the socket stays stuck while the full-snapshot path decides ----------


class _QueueSubscription:
    """A subscribed channel fed by the test while the tasks run."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[str] = asyncio.Queue()

    async def listen(self) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "subscribe", "data": 1}
        while True:
            yield {"type": "message", "data": (await self.queue.get()).encode()}


def _a_removal(seq: int) -> str:
    return DeltaRemove(
        seq=seq,
        node_ids=["n0"],
        removed=RemovedRecord(nodes={"n0": RemovedElement(handling=node("n0").handling)}),
    ).model_dump_json()


async def _try_again_while_a_push_arrives(readable: int) -> list[dict[str, Any]]:
    """The two tasks of a connection run together. A removal is published from inside the resync's
    own `sync`, before it returns, and the forward is given room to run."""
    store = await _store(readable)
    service = _service(store)
    subscription = _QueueSubscription()
    socket = _ResyncSocket([(None, None)])
    state = _SocketState(stuck=True)
    real_sync = service.sync

    async def sync_with_a_removal_arriving(*args: Any, **kwargs: Any) -> Any:
        await subscription.queue.put(_a_removal(1))
        for _ in range(10):
            await asyncio.sleep(0)
        return await real_sync(*args, **kwargs)

    service.sync = sync_with_a_removal_arriving  # type: ignore[method-assign]
    forward = asyncio.create_task(
        _forward_notifications(subscription, socket, service, CASE, OFFICIAL_READER, state)  # type: ignore[arg-type]
    )
    await asyncio.sleep(0)
    with pytest.raises(WebSocketDisconnect):
        await _handle_resync_requests(socket, service, CASE, OFFICIAL_READER, state)  # type: ignore[arg-type]
    await asyncio.sleep(0.01)
    forward.cancel()
    return socket.sent


async def test_nothing_reaches_the_socket_before_an_over_cap_answer_to_try_again() -> None:
    """Violation caught: the resync freed the socket before `sync` had decided, so a removal (which
    the forward sends without a recount) went out first, and live deltas could overtake the
    snapshot. The socket stays stuck while the full-snapshot path runs: the over-cap answer is the
    first and only thing sent, and a removal arriving meanwhile is not sent after it either."""
    sent = await _try_again_while_a_push_arrives(readable=4)

    assert [m["op"] for m in sent] == ["view_over_cap"]


async def test_nothing_reaches_the_socket_before_the_snapshot_answering_try_again() -> None:
    """Under the cap the snapshot is first, and the removal published during the window comes after
    it (buffered, then replayed), and the socket is free afterwards."""
    sent = await _try_again_while_a_push_arrives(readable=3)

    # The snapshot is first; the removal published during the window is replayed after it.
    assert [m["op"] for m in sent] == ["snapshot", "remove"]


# --- the snapshot's sequence is read before its bodies --------------------------------------------


async def test_a_write_between_the_snapshots_reads_cannot_mislabel_it() -> None:
    """Violation caught (before U6b, found in review): the full path read the bodies and then the
    sequence number, so a write landing between them labelled a snapshot with a sequence whose
    content it lacked, and the client skipped that delta for good. The number is read first: the
    snapshot either holds what the write added or carries a number below it."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, _readable(2))
    await store.next_seq(CASE)
    service = _service(store)
    real_nodes = store.source_fidelity_nodes
    written = False

    async def nodes_then_a_write(investigation_id: str) -> Any:
        nonlocal written
        found = await real_nodes(investigation_id)
        if not written:
            written = True
            await store.add_nodes(CASE, [node("late")])
            await store.next_seq(CASE)
        return found

    store.source_fidelity_nodes = nodes_then_a_write  # type: ignore[method-assign]

    (snapshot,) = await service.sync(CASE, OFFICIAL_READER, last_acknowledged_seq=None)

    assert isinstance(snapshot, DeltaSnapshot)
    assert snapshot.seq < 2 or "late" in {n.id for n in snapshot.nodes}


# --- a view that cannot be counted is logged and counted ------------------------------------------


async def test_a_view_that_cannot_be_counted_is_logged_and_counted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The broken-scheme state (a signature in use with a handling code the scheme no longer
    defines) skips the cap check, as it did before U6b. It is no longer silent: one warning per
    skip, and a counter, as an index rebuild is."""
    store = FakeWorkingSetStore()
    bad = node("a").model_copy(
        update={"handling": node("a").handling.model_copy(update={"handling_code": "NOT-A-CODE"})}
    )
    await store.add_nodes(CASE, [node("b")])
    await store.add_edges(
        CASE, [edge("dangling", "b", "gone").model_copy(update={"handling": bad.handling})]
    )
    service = _service(store)

    with caplog.at_level("WARNING", logger="services.api.working_set.service"):
        await service.sync(CASE, OFFICIAL_READER, last_acknowledged_seq=None)

    assert service.uncountable_views == 1
    assert [r.levelname for r in caplog.records] == ["WARNING"]
    assert "NOT-A-CODE" in caplog.records[0].getMessage()


async def test_a_write_after_the_try_again_snapshots_bodies_is_caught_up_not_lost() -> None:
    """Violation caught (found in review): the socket is held stuck while the full-snapshot path
    runs, so a write landing after the bodies were read has its delta dropped by the forward, and
    the client's gap check fires only when a later delta arrives; a case that goes quiet loses it.
    Once the snapshot frees the socket the handler runs the catch-up from the snapshot's own
    sequence and sends what it returns, so the client ends with the write. A duplicate is
    harmless."""
    store = await _store(2)
    await store.next_seq(CASE)  # sequence 1: what the snapshot will be labelled with
    service = _service(store)
    real_nodes = store.source_fidelity_nodes
    written = False

    async def nodes_then_a_write_and_nothing_after(investigation_id: str) -> Any:
        nonlocal written
        found = await real_nodes(investigation_id)
        if not written:
            written = True
            await store.add_nodes(CASE, [node("late")])
            seq = await store.next_seq(CASE)
            await store.append_delta(CASE, DeltaAdd(seq=seq, nodes=[node("late")]))
        return found

    store.source_fidelity_nodes = nodes_then_a_write_and_nothing_after  # type: ignore[method-assign]
    state = _SocketState(stuck=True)

    sent = await _resynced(service, [(None, None)], state)

    held: set[str] = set()
    for message in sent:
        if message["op"] == "snapshot":
            held = {n["id"] for n in message["nodes"]}
        elif message["op"] == "add":
            held |= {n["id"] for n in message["nodes"]}
    assert held == {"n0", "n1", "late"}
    assert state.stuck is False


async def test_a_catch_up_after_try_again_that_finds_the_view_over_the_cap_sticks_the_socket() -> (
    None
):
    """The catch-up path checks the cap too: if the write it brings takes the view past the cap, the
    answer is `DeltaViewOverCap` and the socket is stuck again."""
    store = await _store(3)
    await store.next_seq(CASE)
    service = _service(store)
    real_nodes = store.source_fidelity_nodes
    written = False

    async def nodes_then_a_write(investigation_id: str) -> Any:
        nonlocal written
        found = await real_nodes(investigation_id)
        if not written:
            written = True
            await store.add_nodes(CASE, [node("late")])
            seq = await store.next_seq(CASE)
            await store.append_delta(CASE, DeltaAdd(seq=seq, nodes=[node("late")]))
        return found

    store.source_fidelity_nodes = nodes_then_a_write  # type: ignore[method-assign]
    state = _SocketState(stuck=True)

    sent = await _resynced(service, [(None, None)], state)

    assert [m["op"] for m in sent] == ["snapshot", "view_over_cap"]
    assert state.stuck is True


# --- a delta published during the try-again window is buffered, not dropped -----------------------


def _an_addition(seq: int, node_id: str) -> str:
    return DeltaAdd(seq=seq, nodes=[node(node_id)]).model_dump_json()


async def _try_again_with_pushes_after_the_catch_up_read(
    store: FakeWorkingSetStore, pushes: Sequence[str], state: _SocketState
) -> list[dict[str, Any]]:
    """The connection's two tasks run together. The messages in `pushes` are published right after
    the catch-up's own read of the stream, so they are in neither the snapshot nor the catch-up."""
    service = _service(store)
    subscription = _QueueSubscription()
    socket = _ResyncSocket([(None, None)])
    real_after = store.deltas_after
    published = False

    async def read_then_publish(investigation_id: str, since_seq: int) -> Any:
        nonlocal published
        found = await real_after(investigation_id, since_seq)
        if not published:
            published = True
            for message in pushes:
                await subscription.queue.put(message)
            for _ in range(10):
                await asyncio.sleep(0)
        return found

    store.deltas_after = read_then_publish  # type: ignore[method-assign]
    forward = asyncio.create_task(
        _forward_notifications(subscription, socket, service, CASE, OFFICIAL_READER, state)  # type: ignore[arg-type]
    )
    await asyncio.sleep(0)
    with pytest.raises(WebSocketDisconnect):
        await _handle_resync_requests(socket, service, CASE, OFFICIAL_READER, state)  # type: ignore[arg-type]
    await asyncio.sleep(0.01)
    forward.cancel()
    return socket.sent


def _held_by_a_client(sent: Sequence[dict[str, Any]]) -> set[str]:
    held: set[str] = set()
    for message in sent:
        if message["op"] == "snapshot":
            held = {n["id"] for n in message["nodes"]}
        elif message["op"] == "add":
            held |= {n["id"] for n in message["nodes"]}
    return held


async def test_a_delta_published_after_the_catch_up_read_reaches_the_client_when_quiet() -> None:
    """Violation caught (found in review): between the catch-up's read and the moment the socket is
    freed, a delta is in neither the snapshot nor the catch-up, and the held forward dropped it; if
    no later delta arrives, the client's gap check never fires and the write is lost. During a
    try-again the forward buffers instead, and once the answer is sent the buffered messages above
    the last sequence sent are replayed, in order, projected as the forward would."""
    store = await _store(2)
    await store.next_seq(CASE)
    state = _SocketState(stuck=True)

    sent = await _try_again_with_pushes_after_the_catch_up_read(
        store, [_an_addition(2, "late")], state
    )

    assert _held_by_a_client(sent) == {"n0", "n1", "late"}
    assert [m["op"] for m in sent] == ["snapshot", "add"]
    assert state.stuck is False and state.buffer == []


async def test_buffered_messages_are_replayed_in_order_and_those_already_sent_are_skipped() -> None:
    store = await _store(2)
    await store.next_seq(CASE)
    state = _SocketState(stuck=True)

    sent = await _try_again_with_pushes_after_the_catch_up_read(
        store,
        [_an_addition(1, "already-in-the-snapshot"), _an_addition(2, "a"), _an_addition(3, "b")],
        state,
    )

    assert [m["seq"] for m in sent] == [1, 2, 3]  # the snapshot (1), then the two new, in order
    assert [n["id"] for m in sent[1:] for n in m["nodes"]] == ["a", "b"]


async def test_a_buffered_delta_that_takes_the_view_over_the_cap_is_answered_with_the_figure() -> (
    None
):
    """The replay includes the forward's recount: a buffered addition that takes the view past the
    cap is answered with `DeltaViewOverCap`, and the socket is stuck again."""
    store = await _store(3)
    await store.next_seq(CASE)
    await store.add_nodes(CASE, [node("late")])  # the write the buffered delta describes
    state = _SocketState(stuck=True)
    real_nodes = store.source_fidelity_nodes

    async def the_snapshot_before_the_write(investigation_id: str) -> Any:
        found = await real_nodes(investigation_id)
        found.pop("late", None)
        return found

    store.source_fidelity_nodes = the_snapshot_before_the_write  # type: ignore[method-assign]

    sent = await _try_again_with_pushes_after_the_catch_up_read(
        store, [_an_addition(2, "late")], state
    )

    assert [m["op"] for m in sent][-1] == "view_over_cap"
    assert state.stuck is True and state.buffer == []


async def test_an_over_cap_answer_discards_what_was_buffered() -> None:
    """When the outcome is `view_over_cap`, nothing is replayed: the reader sees the figure and
    nothing else, and the buffer is emptied (no memory kept for a reader who stays stuck)."""
    store = await _store(4)
    await store.next_seq(CASE)
    state = _SocketState(stuck=True)

    sent = await _try_again_with_pushes_after_the_catch_up_read(
        store, [_an_addition(2, "late"), _an_addition(3, "later")], state
    )

    assert [m["op"] for m in sent] == ["view_over_cap"]
    assert state.stuck is True and state.buffer == [] and state.buffering is False


async def test_the_buffer_is_bounded_and_an_overflow_falls_back_to_a_fresh_catch_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bound is the stream's own length (`DELTA_STREAM_MAXLEN`), here two. Past it everything
    buffered is dropped and, after the answer is sent, a fresh catch-up from the last sequence sent
    is run and sent: nothing is lost, and nothing is held without limit."""
    import services.api.app as app_module

    monkeypatch.setattr(app_module, "DELTA_STREAM_MAXLEN", 2)
    monkeypatch.setattr(service_module, "MAX_NODES", 50)  # room for the writes
    store = await _store(2)
    await store.next_seq(CASE)
    state = _SocketState(stuck=True)
    longest = 0

    class _Watched(list[str]):
        def append(self, item: str) -> None:
            nonlocal longest
            super().append(item)
            longest = max(longest, len(self))

    state.buffer = _Watched()
    service_nodes = [node(f"w{i}") for i in range(3)]

    async def the_writes_land_with_their_deltas() -> None:
        await store.add_nodes(CASE, service_nodes)
        for i, n in enumerate(service_nodes):
            seq = await store.next_seq(CASE)
            await store.append_delta(CASE, DeltaAdd(seq=seq, nodes=[n]))

    real_after = store.deltas_after
    done = False

    async def after_with_the_writes(investigation_id: str, since_seq: int) -> Any:
        nonlocal done
        found = await real_after(investigation_id, since_seq)
        if not done:
            done = True
            await the_writes_land_with_their_deltas()
        return found

    store.deltas_after = after_with_the_writes  # type: ignore[method-assign]

    sent = await _try_again_with_pushes_after_the_catch_up_read(
        store, [_an_addition(2 + i, f"w{i}") for i in range(3)], state
    )

    assert _held_by_a_client(sent) == {"n0", "n1", "w0", "w1", "w2"}
    assert state.stuck is False and state.buffer == []
    assert longest <= 2  # never more than the bound was held
