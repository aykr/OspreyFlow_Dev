"""The standing sentence's flag (ADR-124 decision 5): `DeltaSnapshot.withheld`, set only in the full
snapshot `sync` returns to a reader, `True` when the case's stored set holds any node or link whose
own stored handling that reader may not view, and `None` on every other delta there is.

It says nothing of how many or which. Datasets play no part: under ADR-099 an element outside the
case's datasets but readable by handling is not withheld from the case, it is outside the case's
world. Each element is judged on its own body: a readable link to a hidden node is not withheld
through the link (the node is, on its own). The flag is computed from the counted access index
(Amendment 4), not by reading bodies; the real-store equivalence is in `test_valkey_store.py`.

The remove and restore cases at the end are U5's own: they are written red for the right reason
(today's code deletes what the reader may not read) and marked for U6, which makes them pass.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    _handle_resync_requests,
    app,
    get_audit,
    get_history,
    get_investigations,
    get_principal,
    get_valkey,
    get_working_set,
)
from services.api.investigations import Investigation, InvestigationNotFoundError
from services.api.working_set.access_index import AccessCounts
from services.api.working_set.models import DeltaSnapshot, decode_delta
from services.api.working_set.service import WorkingSetService
from starlette.websockets import WebSocketDisconnect

from ontology.errors import HandlingSchemeError
from schemas.domain import Principal, Subgraph

from .fakes import FakeGraphPort, FakeWorkingSetStore
from .test_visible_link import OFFICIAL_READER, SCHEME, SECRET_READER, edge, node

CASE = "inv-1"
IN_FIXTURE = OFFICIAL_READER.model_copy(update={"datasets": ["fixture"]})
WHEN = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def _service(store: FakeWorkingSetStore) -> WorkingSetService:
    return WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), store, SCHEME)


async def _snapshot(service: WorkingSetService, reader: Principal) -> DeltaSnapshot:
    (snapshot,) = await service.sync(CASE, reader, last_acknowledged_seq=None)
    assert isinstance(snapshot, DeltaSnapshot)
    return snapshot


async def _flag(store: FakeWorkingSetStore, reader: Principal) -> bool | None:
    return (await _snapshot(_service(store), reader)).withheld


# --- (a) a node above the reader ----------------------------------------------------------------


async def test_a_reader_below_a_stored_nodes_marking_is_told_and_a_cleared_reader_is_not() -> None:
    """Violation caught: no flag at all, so the status bar can never say the case holds material
    the reader is not cleared to see. The reader below the marking gets `True`, a cleared one
    `False` (`False`, not `None`: a full snapshot always says)."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("sec", "SECRET")])

    assert await _flag(store, OFFICIAL_READER) is True
    assert await _flag(store, SECRET_READER) is False


async def test_a_case_with_nothing_above_the_reader_says_false() -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("a"), node("b")])
    await store.add_edges(CASE, [edge("ab", "a", "b")])

    assert await _flag(store, OFFICIAL_READER) is False


async def test_an_empty_case_says_false() -> None:
    assert await _flag(FakeWorkingSetStore(), OFFICIAL_READER) is False


# --- (b) a link above the reader, both ends readable -----------------------------------------


async def test_a_hidden_link_alone_sets_the_flag_with_both_ends_readable() -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("a"), node("b")])
    await store.add_edges(CASE, [edge("secret-link", "a", "b", "SECRET")])

    assert await _flag(store, OFFICIAL_READER) is True
    assert await _flag(store, SECRET_READER) is False


# --- (c) datasets play no part ------------------------------------------------------------------


async def test_an_element_outside_the_cases_datasets_but_readable_is_not_withheld() -> None:
    """Violation caught (ADR-099): the judgement folded datasets in, so material in another dataset,
    which the reader is cleared for and which is outside the case's world, said the case withholds
    something. Nothing here is above the reader's clearance."""
    store = FakeWorkingSetStore()
    await store.add_nodes(
        CASE,
        [
            node("mine").model_copy(update={"datasets": ["fixture"]}),
            node("theirs").model_copy(update={"datasets": ["enron"]}),
        ],
    )
    await store.add_edges(
        CASE, [edge("elsewhere", "mine", "theirs").model_copy(update={"datasets": ["enron"]})]
    )

    assert await _flag(store, IN_FIXTURE) is False


async def test_an_element_above_the_reader_in_another_dataset_still_counts() -> None:
    """The control: handling gates the flag whatever dataset the element is in."""
    store = FakeWorkingSetStore()
    await store.add_nodes(
        CASE,
        [
            node("mine").model_copy(update={"datasets": ["fixture"]}),
            node("theirs", "SECRET").model_copy(update={"datasets": ["enron"]}),
        ],
    )

    assert await _flag(store, IN_FIXTURE) is True


# --- (d) a readable link with a hidden end ------------------------------------------------------


async def test_a_readable_link_to_a_hidden_node_counts_through_the_node_and_not_the_link() -> None:
    """Each element is judged on its own body: the link is readable, the node is not, so the flag is
    `True` because of the node. Remove the node from the store (a node's removal leaves its links
    stored) and the link remains, readable, and the flag is `False`."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("a"), node("hidden", "SECRET")])
    await store.add_edges(CASE, [edge("a-hidden", "a", "hidden")])
    assert await _flag(store, OFFICIAL_READER) is True

    await store.remove_nodes(CASE, ["hidden"])

    assert set(await store.edge_ids(CASE)) == {"a-hidden"}  # the link is still stored
    assert await _flag(store, OFFICIAL_READER) is False


# --- (e) old entries parse as None; (3) nothing else carries it -------------------------------


def test_a_stored_snapshot_without_the_field_parses_as_none() -> None:
    delta = decode_delta({"seq": 4, "op": "snapshot", "nodes": [], "edges": []})

    assert isinstance(delta, DeltaSnapshot) and delta.withheld is None


async def test_a_snapshot_the_service_stores_carries_none() -> None:
    """Restore's snapshot is stored and replayed: the flag is the full-snapshot
    answer of `sync` alone."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("sec", "SECRET")])
    service = _service(store)

    restored = await service.restore(CASE, [node("pub"), node("sec", "SECRET")], [], SECRET_READER)

    assert restored.withheld is None
    stored = await store.deltas_after(CASE, 0)
    assert stored is not None and all(getattr(d, "withheld", None) is None for d in stored)


async def test_a_catch_up_sync_carries_no_true() -> None:
    """Violation caught: a replayed delta (a stored snapshot among them) sent with the flag, so a
    reader who reconnects a step behind is told again, or told something stale. Only a full
    snapshot says."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("sec", "SECRET")])
    service = _service(store)
    await service.restore(CASE, [node("pub"), node("sec", "SECRET")], [], SECRET_READER)
    await service.seed(CASE, [node("more")], [], OFFICIAL_READER)

    caught_up = await service.sync(CASE, OFFICIAL_READER, last_acknowledged_seq=0)

    assert len(caught_up) >= 2
    assert [d for d in caught_up if getattr(d, "withheld", None) is True] == []
    assert all(getattr(d, "withheld", None) is None for d in caught_up)


async def test_a_live_delta_projected_for_a_reader_carries_none() -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("sec", "SECRET")])
    service = _service(store)
    restored = await service.restore(CASE, [node("pub"), node("sec", "SECRET")], [], SECRET_READER)

    live = await service.project_live(CASE, restored, OFFICIAL_READER)

    assert isinstance(live, DeltaSnapshot) and live.withheld is None


# --- a stored snapshot's own flag never reaches a reader ---------------------------------------


async def test_a_stored_snapshot_with_the_flag_set_is_sent_without_it() -> None:
    """Violation caught: the projection of a stored snapshot copied its `withheld` through, so a
    value written to the stream (by any writer, or by an older build) reached every reader, by the
    catch-up and by the live push alike. Only `sync`'s full snapshot says; the stored one is
    `None` for everyone."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("sec", "SECRET")])
    await store.next_seq(CASE)
    await store.append_delta(CASE, DeltaSnapshot(seq=1, withheld=True))
    service = _service(store)

    (replayed,) = await service.sync(CASE, OFFICIAL_READER, last_acknowledged_seq=0)
    live = await service.project_live(CASE, DeltaSnapshot(seq=2, withheld=True), OFFICIAL_READER)

    assert isinstance(replayed, DeltaSnapshot) and replayed.withheld is None
    assert isinstance(live, DeltaSnapshot) and live.withheld is None


# --- a handling code the scheme does not define ------------------------------------------------


def _undefined(element: Any) -> Any:
    """`element`, its handling carrying a code the scheme does not define."""
    return element.model_copy(
        update={"handling": element.handling.model_copy(update={"handling_code": "NOT-A-CODE"})}
    )


async def test_a_link_with_an_absent_end_and_an_undefined_code_sets_the_flag() -> None:
    """The one place the flag's own judgement meets a code the scheme does not define: `sync`'s
    projection never judges a link whose end is not stored (it is skipped, nothing is withheld by
    it), so it does not raise, and the flag finds the link's signature unjudgeable. It cannot be
    shown not to be above the reader, so the sentence appears. Without the guard the snapshot
    raises `HandlingSchemeError`."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("a")])
    await store.add_edges(CASE, [_undefined(edge("dangling", "a", "gone"))])

    assert await _flag(store, OFFICIAL_READER) is True


async def test_a_stored_node_with_an_undefined_code_makes_sync_raise_today() -> None:
    """Pins existing behaviour, recorded and not decided here: `sync`'s projection judges every
    stored node, and one whose handling code the scheme does not define raises for a reader whose
    classification clears it. (For a reader below its classification the clearance check answers
    first and nothing raises.) It is the projection's, and the flag does not change it."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("a"), _undefined(node("odd"))])
    service = _service(store)

    with pytest.raises(HandlingSchemeError):
        await service.sync(CASE, OFFICIAL_READER, last_acknowledged_seq=None)


async def test_a_signature_the_table_does_not_define_sets_the_flag() -> None:
    """The index's own damage, as a store that did not rebuild would show it: a count naming a
    signature with no definition. It cannot be judged, so the flag is `True`. (The Valkey store
    rebuilds before it ever returns one; this is the service's own guard, shown on the fake.)"""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("a")])
    real = store.access_counts

    async def counts_naming_an_undefined_signature(investigation_id: str) -> AccessCounts:
        found = await real(investigation_id)
        return replace(found, node_counts={**found.node_counts, "no-such-signature": 1})

    store.access_counts = counts_naming_an_undefined_signature  # type: ignore[method-assign]

    assert await _service(store)._holds_what_the_reader_may_not_view(CASE, OFFICIAL_READER) is True


# --- (f) on the real wire -----------------------------------------------------------------------


class _Socket:
    """A WebSocket that asks once to be resynced from nothing and records what it is sent."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self._asked = False

    async def receive_json(self) -> dict[str, Any]:
        if self._asked:
            raise WebSocketDisconnect()
        self._asked = True
        return {"last_acknowledged_seq": None}

    async def send_text(self, text: str) -> None:
        self.sent.append(text)


async def _on_the_wire(reader: Principal) -> dict[str, Any]:
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("sec", "SECRET")])
    socket = _Socket()
    with pytest.raises(WebSocketDisconnect):
        await _handle_resync_requests(socket, _service(store), CASE, reader)  # type: ignore[arg-type]
    (text,) = socket.sent
    wire: dict[str, Any] = json.loads(text)
    return wire


async def test_the_flag_is_in_the_json_a_socket_receives_on_a_resync() -> None:
    """Violation caught: the field set in Python and left off the wire (excluded, renamed, or
    dropped by the dump). A resync is the real `sync` call site; the key is `withheld`, a boolean,
    and no number rides with it."""
    official = await _on_the_wire(OFFICIAL_READER)
    cleared = await _on_the_wire(SECRET_READER)

    assert official["op"] == "snapshot" and official["withheld"] is True
    assert cleared["withheld"] is False
    assert [n["id"] for n in official["nodes"]] == ["pub"]
    assert not {"filtered_count", "withheld_count", "unreadable_count"} & set(official)


# --- U5's own test: a reader's act never removes what they may not read (U6 passes it) ---


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


class _Publisher:
    async def publish(self, channel: str, message: str) -> int:
        return 1


@pytest.fixture
async def remove_route() -> AsyncIterator[tuple[TestClient, FakeWorkingSetStore]]:
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("sec", "SECRET")])
    editor = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
    app.dependency_overrides[get_principal] = lambda: editor
    app.dependency_overrides[get_working_set] = lambda: _service(store)
    app.dependency_overrides[get_audit] = lambda: _FakeAudit()
    app.dependency_overrides[get_history] = lambda: _FakeHistory()
    app.dependency_overrides[get_investigations] = lambda: _FakeInvestigations()
    app.dependency_overrides[get_valkey] = lambda: _Publisher()
    try:
        yield TestClient(app), store
    finally:
        app.dependency_overrides.clear()


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="ADR-124 U6: `remove` keeps what the reader may not read (decision 6)",
)
async def test_a_reader_removing_a_hidden_nodes_id_leaves_it_stored_and_the_flag_unchanged(
    remove_route: tuple[TestClient, FakeWorkingSetStore],
) -> None:
    """Violation, today and owned by U6: `remove` deletes any id it is given, so an analyst below a
    node's marking, naming its id, deletes a cleared colleague's work, and the flag for the next
    reader below that marking turns off. The route answers as it always did; the stored set and
    the flag do not move."""
    client, store = remove_route
    flag_before = await _flag(store, OFFICIAL_READER)
    assert flag_before is True
    own_view_before = {n.id for n in (await _snapshot(_service(store), OFFICIAL_READER)).nodes}

    response = client.request(
        "DELETE", f"/v1/investigations/{CASE}/nodes", json={"node_ids": ["sec"]}
    )

    assert response.status_code == 200
    assert set(await store.source_fidelity_nodes(CASE)) == {"pub", "sec"}
    assert await _flag(store, OFFICIAL_READER) is flag_before
    cleared = await _snapshot(_service(store), SECRET_READER)
    assert {n.id for n in cleared.nodes} == {"pub", "sec"}
    own_view = {n.id for n in (await _snapshot(_service(store), OFFICIAL_READER)).nodes}
    assert own_view == own_view_before == {"pub"}  # the uncleared reader's own view does not move


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="ADR-124 U6: a restore reconciles only what the restorer's view holds (decision 6)",
)
async def test_a_restore_past_a_hidden_nodes_id_leaves_it_stored_and_the_flag_unchanged() -> None:
    """Violation, today and owned by U6: a restore removes every stored node the step does not hold,
    including one the restorer may not read, so restoring a step recorded before a cleared
    colleague's node deletes it."""
    store = FakeWorkingSetStore()
    held = [node("pub"), node("sec", "SECRET")]
    await store.add_nodes(CASE, held)
    # The Vault holds both, as U6's restore will read it (`get_nodes`): so that when U6 judges the
    # step's members against the Vault and keeps the hidden one, this case passes and the marker
    # (strict) must come off, rather than failing for want of a Vault in the fake.
    graph = FakeGraphPort(Subgraph(nodes=[], edges=[]), graph_nodes=held)
    service = WorkingSetService(graph, store, SCHEME)
    flag_before = await _flag(store, OFFICIAL_READER)
    assert flag_before is True
    own_view_before = {n.id for n in (await _snapshot(service, OFFICIAL_READER)).nodes}

    await service.restore(CASE, [node("pub")], [], OFFICIAL_READER)

    assert set(await store.source_fidelity_nodes(CASE)) == {"pub", "sec"}
    assert await _flag(store, OFFICIAL_READER) is flag_before
    cleared = await _snapshot(service, SECRET_READER)
    assert {n.id for n in cleared.nodes} == {"pub", "sec"}
    own_view = {n.id for n in (await _snapshot(service, OFFICIAL_READER)).nodes}
    assert own_view == own_view_before == {"pub"}  # the uncleared reader's own view does not move
