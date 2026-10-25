"""A delta on the wire, end to end without a server (ADR-124 decision 4, rules 3 and 4): the route
that removes nodes publishes the record of what it removed, and the live forward that every socket
runs turns the published message into only what that socket's reader may read.

Two real call sites, each driven with a fake at its edge: `DELETE .../nodes` through the test
client with a recording Valkey, and `_forward_notifications` with a pub/sub that yields what was
published. The projection rules themselves are `working_set/test_delta_projection.py`; the real
stream and Pub/Sub are `test_valkey_store.py`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    _forward_notifications,
    app,
    get_audit,
    get_history,
    get_investigations,
    get_principal,
    get_valkey,
    get_working_set,
)
from services.api.investigations import Investigation, InvestigationNotFoundError
from services.api.notify import notify_channel, publish_delta
from services.api.working_set.models import (
    DeltaRemove,
    DeltaRemoveSent,
    DeltaReplaceEdge,
    DeltaReplaceEdgeSent,
    RemovedElement,
)
from services.api.working_set.service import WorkingSetService

from schemas.domain import Principal, Subgraph

from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_visible_link import OFFICIAL_READER, SCHEME, SECRET_READER, edge, node

CASE = "inv-1"
EDITOR = Principal(id="analyst-1", clearance="SECRET", org_unit="unit-1", roles=["analyst"])
WHEN = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


class _RecordingValkey:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1


class _FakeAudit:
    async def record(self, **kwargs: object) -> None:
        return None


class _FakeHistory:
    async def record_step(self, investigation_id: str, **kwargs: object) -> object:
        return object()


class _FakeInvestigations:
    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: object = None
    ) -> Investigation:
        if investigation_id != CASE:
            raise InvestigationNotFoundError(investigation_id)
        return Investigation(id=CASE, created_at=WHEN, created_by="analyst-1", owning_unit="unit-1")


def _service(store: FakeWorkingSetStore) -> WorkingSetService:
    return WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), store, SCHEME)


# --- DELETE .../nodes: the route publishes the service's removal, record and all -----------------


@pytest.fixture
async def removal_route() -> AsyncIterator[tuple[TestClient, _RecordingValkey]]:
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("sec", "SECRET")])
    valkey = _RecordingValkey()
    app.dependency_overrides[get_principal] = lambda: EDITOR
    app.dependency_overrides[get_working_set] = lambda: _service(store)
    app.dependency_overrides[get_audit] = lambda: _FakeAudit()
    app.dependency_overrides[get_history] = lambda: _FakeHistory()
    app.dependency_overrides[get_investigations] = lambda: _FakeInvestigations()
    app.dependency_overrides[get_valkey] = lambda: valkey
    try:
        yield TestClient(app), valkey
    finally:
        app.dependency_overrides.clear()


def test_the_remove_route_publishes_the_removal_with_the_record_of_what_each_node_was(
    removal_route: tuple[TestClient, _RecordingValkey],
) -> None:
    """Violation caught (rule 3): a route that builds its own `DeltaRemove(node_ids=...)` from the
    request body, which carries no record, so every socket's projection has nothing to judge the
    ids by and they all go to every reader. The published message holds the record."""
    client, valkey = removal_route

    response = client.request(
        "DELETE", f"/v1/investigations/{CASE}/nodes", json={"node_ids": ["pub", "sec"]}
    )

    assert response.status_code == 200 and response.json() == {"seq": 1}
    [(channel, message)] = valkey.published
    assert channel == notify_channel(CASE)
    published = json.loads(message)
    assert published["op"] == "remove" and published["node_ids"] == ["pub", "sec"]
    assert {
        node_id: element["handling"]["classification"]
        for node_id, element in published["removed"]["nodes"].items()
    } == {"pub": "OFFICIAL", "sec": "SECRET"}


def test_the_remove_route_answers_with_a_sequence_number_and_no_record(
    removal_route: tuple[TestClient, _RecordingValkey],
) -> None:
    client, _ = removal_route

    response = client.request(
        "DELETE", f"/v1/investigations/{CASE}/nodes", json={"node_ids": ["sec"]}
    )

    assert set(response.json()) == {"seq"}


# --- the live forward: what a socket is sent of a published delta ------------------------------


class _Socket:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


class _Subscription:
    """Yields, as a subscribed channel does, what was published."""

    def __init__(self, messages: list[str]) -> None:
        self._messages = messages

    async def listen(self) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "subscribe", "data": 1}
        for message in self._messages:
            yield {"type": "message", "data": message.encode()}


async def _published(delta: DeltaRemove | DeltaReplaceEdge) -> str:
    valkey = _RecordingValkey()
    await publish_delta(valkey, CASE, delta)  # type: ignore[arg-type]
    return valkey.published[0][1]


async def _forwarded(
    service: WorkingSetService, message: str, reader: Principal
) -> list[dict[str, Any]]:
    socket = _Socket()
    await _forward_notifications(
        _Subscription([message]),
        socket,
        service,
        CASE,
        reader,  # type: ignore[arg-type]
    )
    return socket.sent


async def test_the_live_forward_sends_an_uncleared_socket_only_the_removed_ids_it_may_read() -> (
    None
):
    """Violation caught (rule 3): the live forward sending a published removal as it came, so the
    SECRET node's id and the record reached an OFFICIAL socket. The text the socket receives is the
    projection, and holds neither."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("sec", "SECRET")])
    service = _service(store)
    message = await _published(await service.remove(CASE, ["pub", "sec"]))

    official = await _forwarded(service, message, OFFICIAL_READER)
    cleared = await _forwarded(service, message, SECRET_READER)

    assert [m["node_ids"] for m in official] == [["pub"]]
    assert all("removed" not in m and "sec" not in json.dumps(m) for m in official)
    assert [m["node_ids"] for m in cleared] == [["pub", "sec"]]
    assert all("removed" not in m for m in cleared)


async def test_the_live_forward_gives_a_socket_a_snapshot_for_a_removal_with_no_record() -> None:
    """Violation caught: a removal stored before the record existed, published or replayed, sent as
    an empty removal (the reader's canvas then differs from a snapshot's) or as it came (ids they
    may not read). The socket is sent its own full snapshot instead, as a reconnect is."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("sec", "SECRET")])
    service = _service(store)
    message = json.dumps({"seq": 1, "op": "remove", "node_ids": ["sec"]})

    sent = await _forwarded(service, message, OFFICIAL_READER)

    assert [m["op"] for m in sent] == ["snapshot"]
    assert [n["id"] for n in sent[0]["nodes"]] == ["pub"]


async def test_the_live_forward_gives_a_socket_a_snapshot_for_a_replacement_with_no_record() -> (
    None
):
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("a"), node("b")])
    service = _service(store)
    old_form = DeltaReplaceEdge(seq=1, old_edge_id="old", edge=edge("new", "a", "b"))
    # The pre-U4 shape: no `removed` key at all, as a deployment built before this change wrote it.
    message = json.dumps(
        {k: v for k, v in json.loads(old_form.model_dump_json()).items() if k != "removed"}
    )

    sent = await _forwarded(service, message, OFFICIAL_READER)

    assert [m["op"] for m in sent] == ["snapshot"]


async def test_the_live_forward_still_projects_a_replacement_that_has_its_record() -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("a"), node("b")])
    service = _service(store)
    old = edge("old", "a", "b", "SECRET")
    message = await _published(
        DeltaReplaceEdge(
            seq=1,
            old_edge_id="old",
            edge=edge("new", "a", "b"),
            removed=RemovedElement(handling=old.handling, source="a", target="b"),
        )
    )

    official = await _forwarded(service, message, OFFICIAL_READER)

    assert [m["op"] for m in official] == ["add"]  # the old link was above them: only the new one
    assert official[0]["edges"][0]["id"] == "new"


# --- publish refuses a sent form: nothing can be projected from one -------------------------------


@pytest.mark.parametrize(
    "sent",
    [
        DeltaRemoveSent(seq=1, node_ids=["a"]),
        DeltaReplaceEdgeSent(seq=1, old_edge_id="o", edge=edge("n", "a", "b")),
    ],
    ids=["a removal", "a replacement"],
)
async def test_publish_refuses_the_sent_form_of_a_delta_for_it_has_no_record(sent: object) -> None:
    """Violation caught: a route publishing what it returns (the sent form), from which no reader's
    projection can be decided. Pure: the refusal comes before the client is touched."""
    valkey = _RecordingValkey()

    with pytest.raises(TypeError):
        await publish_delta(valkey, CASE, sent)  # type: ignore[arg-type]

    assert valkey.published == []
