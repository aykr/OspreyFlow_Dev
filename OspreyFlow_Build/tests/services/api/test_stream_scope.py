"""The delta stream reads what the case reads (`06_DECISIONS.md` ADR-099 decision 4, on the
socket ADR-050 objection 8 opens).

Seen on the owner's deployment, 8 October 2026: after any reload the canvas came back empty and
the status bar said "285 hidden by handling", which was every node and link of the working set
(126 and 159). The ticket that opens the socket is minted by `POST /v1/ws-ticket`, a path outside
any case, so `get_principal` scoped its principal to no dataset; the stream redeemed that principal
and never scoped it to the case it streams. The snapshot, a reconnect's replay and every live push
were all projected for a reader of nothing. A client that sets the `Authorization` header had the
opposite fault: its principal was never scoped at all and read every dataset.

What a mistake would do, and the case that catches it:

- the socket's reader scoped to no dataset, so a reader's own working set arrives hidden
  (`test_a_ticket_reader_is_sent_the_cases_working_set`);
- the socket's reader unscoped, so a node of a dataset the case does not read reaches it
  (`test_a_header_reader_is_kept_to_the_cases_datasets`);
- the scoping applied to the first snapshot only, not to the live pushes and resync requests that
  follow on the same socket (`test_the_live_pushes_and_resyncs_are_read_as_the_case`).

The route runs for real, with the working set's own projection (`principal_may_read`); only the
socket, the ticket's redemption and the stores stand in.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from services.api.app import stream
from services.api.datasets import InMemoryDatasetStore
from services.api.working_set.service import WorkingSetService

from schemas.domain import Principal

from .test_dataset_scope import _edge, _node
from .working_set.fakes import FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME

CASE = "case-h"
#: What `POST /v1/ws-ticket` binds: `get_principal` outside a case reads no dataset.
TICKET_READER = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", datasets=[])
#: What the `Authorization` header path resolves: the token's identity, never scoped.
HEADER_READER = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


class _Granted:
    async def get_authorized(self, investigation_id: str, principal: Principal, need: Any) -> None:
        return None


class _Audit:
    async def record(self, **_: Any) -> None:
        return None


class _PubSub:
    async def subscribe(self, channel: str) -> None:
        return None

    async def unsubscribe(self, channel: str) -> None:
        return None

    async def aclose(self) -> None:
        return None


class _Valkey:
    def pubsub(self) -> _PubSub:
        return _PubSub()


class _Socket:
    def __init__(self, working_set: WorkingSetService, datasets: InMemoryDatasetStore) -> None:
        class _State:
            pass

        self.app = type("A", (), {"state": _State()})()
        self.app.state.investigations = _Granted()
        self.app.state.audit = _Audit()
        self.app.state.working_set = working_set
        self.app.state.valkey = _Valkey()
        self.app.state.datasets = datasets
        self.sent: list[dict[str, Any]] = []
        self.closed_with: int | None = None

    async def accept(self) -> None:
        return None

    async def close(self, code: int) -> None:
        self.closed_with = code

    async def receive_json(self) -> dict[str, Any]:
        return {"last_acknowledged_seq": None}

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


async def _case_with(*nodes_and_edges: Any) -> tuple[WorkingSetService, InMemoryDatasetStore]:
    store = FakeWorkingSetStore()
    nodes = [x for x in nodes_and_edges if x.__class__.__name__ == "Node"]
    edges = [x for x in nodes_and_edges if x.__class__.__name__ == "Edge"]
    await store.add_nodes(CASE, nodes)
    await store.add_edges(CASE, edges)
    datasets = InMemoryDatasetStore()
    datasets.cases[CASE] = ["hmp"]
    return WorkingSetService(None, store, SCHEME), datasets  # type: ignore[arg-type]


async def _open(socket: _Socket, reader: Principal) -> list[Principal]:
    """Runs the stream to its first snapshot; returns the principals the live-push and resync
    loops were started with."""
    started: list[Principal] = []

    async def _loop(*args: Any) -> None:
        started.append(args[-1])

    with (
        patch("services.api.app._authenticate_websocket", return_value=reader),
        patch("services.api.app._forward_notifications", _loop),
        patch("services.api.app._handle_resync_requests", _loop),
    ):
        await stream(socket, CASE)  # type: ignore[arg-type]
    return started


async def test_a_ticket_reader_is_sent_the_cases_working_set() -> None:
    working_set, datasets = await _case_with(
        _node("okafor", ["hmp"]), _node("yard-a", ["hmp"]), _edge("at", "okafor", "yard-a", ["hmp"])
    )
    socket = _Socket(working_set, datasets)
    await _open(socket, TICKET_READER)
    (snapshot,) = socket.sent
    assert snapshot["op"] == "snapshot"
    assert {n["id"] for n in snapshot["nodes"]} == {"okafor", "yard-a"}
    assert [e["id"] for e in snapshot["edges"]] == ["at"]
    assert snapshot["filtered_count"] == 0


async def test_a_header_reader_is_kept_to_the_cases_datasets() -> None:
    working_set, datasets = await _case_with(_node("okafor", ["hmp"]), _node("lay", ["enron"]))
    socket = _Socket(working_set, datasets)
    await _open(socket, HEADER_READER)
    (snapshot,) = socket.sent
    assert {n["id"] for n in snapshot["nodes"]} == {"okafor"}
    assert snapshot["filtered_count"] == 1


async def test_the_live_pushes_and_resyncs_are_read_as_the_case() -> None:
    working_set, datasets = await _case_with(_node("okafor", ["hmp"]))
    for reader in (TICKET_READER, HEADER_READER):
        started = await _open(_Socket(working_set, datasets), reader)
        assert [p.datasets for p in started] == [["hmp"], ["hmp"]], reader
