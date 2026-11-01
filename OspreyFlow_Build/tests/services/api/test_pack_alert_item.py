"""An alert in a report pack (`spec/06_DECISIONS.md` ADR-134 decision 1): a fifth item kind carrying
the alert's explanation, the entity it matched, its evidence, and its outcome and reason if closed.
It rests on the handlings of every node, link and transaction it cites, and is withheld — as a yes
or no — from a reader who may not view all of them. The routes as each reader sees them, against the
real pack, alert and export-ledger stores in Postgres; the graph and the analytics are fakes that
refuse what the adapters refuse (rule 15): a node, a link or an event the reader may not view is
absent from their answer, judged by the scheme's own rule.

What a mistake would do, and the case that catches it (each of ADR-134's own tests is named):
- an alert item shown to a reader who may not see a node it cites, or the pack saying how many or
  which — `test_an_alert_item_citing_a_node_the_reader_may_not_see_is_withheld_as_a_yes_or_no`;
- the same through a link or a transaction it cites, not only a node —
  `test_an_alert_item_resting_on_a_link_or_a_transaction_the_reader_may_not_see_is_withheld`;
- an exporter who may not see the evidence getting it, or a ledger entry recorded for a refused
  export — `test_an_exporter_who_may_not_see_the_evidence_is_refused_and_nothing_is_recorded`;
- an open alert presented as decided, or a match nobody confirmed presented as confirmed (rule 5) —
  `test_an_open_alert_says_it_is_open_and_an_inferred_match_says_inferred`;
- a closed alert's outcome or reason lost — `test_a_closed_alert_carries_its_outcome_and_reason`;
- an alert added that the adder cannot see in their queue — `test_an_alert_outside_the_adders_queue_is_not_found`;
- the item shown after what it cites is hidden from the reader since —
  `test_an_alert_item_is_withheld_when_what_it_cites_is_hidden_since`;
- adding without Editor, or by a Reports Viewer (rule 4) — `test_adding_an_alert_needs_editor_and_record_assessment`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.alerts import AlertStore
from services.api.app import app, get_alerts_store, get_config, get_export_ledger
from services.api.config import PostgresConfig
from services.api.export import ExportLedgerEntry, ExportLedgerStore
from services.api.packs import item_visible

from conduit_common.identity import new_id
from schemas.analytics import EventFilter, EventListRequest, EventListResult, EventRecord
from schemas.domain import (
    Alert,
    AlertMode,
    AuditStub,
    Edge,
    Handling,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from tests.services.api.test_packs import (
    CASE,
    CLEARED_READER,
    EDITOR,
    LOW_EDITOR,
    NO_LEVEL,
    NOW,
    READER,
    SCHEME,
    VIEWER,
    World,
    _handling,
    _new_pack,
    _publish,
    world,  # noqa: F401 — the fixtures below wrap it
)


def _provenance(state: ProvenanceState = ProvenanceState.ASSERTED) -> Provenance:
    return Provenance(state=state, first_seen=NOW,
                      sources=[SourceRef(document_id="d1", locator="p1", excerpt_hash="h")])  # fmt: skip


class _AlertGraph:
    """`test_packs.py`'s graph, with the reads an alert's explanation makes: every node and link is
    judged by the scheme's rule as the reader, and a hidden one is absent, never an error."""

    def __init__(self, base: Any) -> None:
        self.base = base
        self.edges: dict[str, Edge] = {}

    def node(self, node_id: str, name: str, classification: str = "OFFICIAL", *, node_type: str = "Person",
             state: ProvenanceState = ProvenanceState.ASSERTED) -> str:  # fmt: skip
        self.base.add(node_id, _handling(classification), name)
        made = self.base.nodes[node_id]
        self.base.nodes[node_id] = made.model_copy(update={"type": node_type, "provenance": _provenance(state)})
        return node_id

    def edge(self, edge_id: str, source: str, target: str, classification: str = "OFFICIAL", *,
             edge_type: str = "TRANSACTED", state: ProvenanceState = ProvenanceState.ASSERTED) -> str:  # fmt: skip
        self.edges[edge_id] = Edge(
            id=edge_id, type=edge_type, source=source, target=target, basis="direct",
            provenance=_provenance(state), handling=_handling(classification),
            audit=AuditStub(created_at=NOW, created_by="ed", revision=1),
        )  # fmt: skip
        return edge_id

    async def get_node(self, node_id: str, principal: Principal, **_: object) -> Node | None:
        return await self.base.get_node(node_id, principal)

    async def get_nodes(self, node_ids: Any, principal: Principal) -> list[Node]:
        return [n for i in sorted(set(node_ids)) if (n := await self.get_node(i, principal)) is not None]

    async def edges_among(self, node_ids: Any, principal: Principal, **_: object) -> list[Edge]:
        ids = set(node_ids)
        return [e for e in self.edges.values()
                if e.source in ids and e.target in ids and item_visible([e.handling], principal, SCHEME)]  # fmt: skip

    async def get_edges(self, edge_ids: Any, principal: Principal) -> list[Edge]:
        return [e for i in edge_ids if (e := self.edges.get(i)) and item_visible([e.handling], principal, SCHEME)]


class _Events:
    """The analytics fake, with the events an alert cites: a hidden event is neither listed nor
    counted (`AnalyticsPort.list_events`)."""

    def __init__(self, base: Any) -> None:
        self.base = base
        self.events: list[EventRecord] = []

    async def trend(self, *a: Any, **k: Any) -> Any:
        return await self.base.trend(*a, **k)

    async def list_events(self, req: EventListRequest, principal: Principal) -> EventListResult:
        wanted = set(req.filter.event_ids or [])
        found = [e for e in self.events if e.event_id in wanted and item_visible([e.handling], principal, SCHEME)]
        return EventListResult(events=found, total=len(found))


class AlertWorld:
    def __init__(self, w: World) -> None:
        self.w = w
        self.graph = _AlertGraph(w.graph)
        self.events = _Events(w.analytics)
        w.graph = self.graph  # type: ignore[assignment]
        w.analytics = self.events  # type: ignore[assignment]
        self.ledger_entries: list[ExportLedgerEntry] = []

    async def raise_alert(self, **fields: Any) -> str:
        values: dict[str, Any] = dict(
            id=new_id(), rule_id=f"typology:{new_id()}", owner_id=EDITOR.id, mode=AlertMode.FULL,
            referent_node_ids=[], investigation_id="case-1", created_at=NOW, typology="structuring",
            words="Rapid in-and-out through one account",
        )  # fmt: skip
        values.update(fields)
        store = await AlertStore.connect(PostgresConfig.from_env().dsn)
        try:
            await store.save(Alert(**values))
        finally:
            await store.close()
        return str(values["id"])

    def as_(self, who: Principal) -> TestClient:
        return self.w.as_(who)


async def _alerts_store() -> AsyncIterator[AlertStore]:
    store = await AlertStore.connect(PostgresConfig.from_env().dsn)
    try:
        yield store
    finally:
        await store.close()


class _Config:
    export_manifest_policy = "disclose"


@pytest.fixture
def aw(world: World) -> Iterator[AlertWorld]:  # noqa: F811
    made = AlertWorld(world)

    class _Ledger:
        async def record(self, entry: ExportLedgerEntry) -> None:
            made.ledger_entries.append(entry)

    app.dependency_overrides.update({
        get_alerts_store: _alerts_store, get_export_ledger: lambda: _Ledger(), get_config: lambda: _Config(),
    })  # fmt: skip
    yield made


def _add_alert(aw: AlertWorld, pack: str, alert_id: str, who: Principal = EDITOR) -> Any:
    return aw.as_(who).post(f"{CASE}/packs/{pack}/items", json={"kind": "alert", "alert_id": alert_id})


async def _plain_alert(aw: AlertWorld, classification: str = "OFFICIAL", **fields: Any) -> str:
    a = aw.graph.node(f"n-{new_id()}", "Halcyon Marine Ltd")
    b = aw.graph.node(f"n-{new_id()}", "Ardent Freight", classification)
    return await aw.raise_alert(referent_node_ids=[a, b], **fields)


def _without_times(body: dict[str, Any]) -> dict[str, Any]:
    """The draft as served, less what differs between any two packs (their ids, titles, times)."""
    out = dict(body)
    out["pack"] = {k: v for k, v in out["pack"].items() if k not in ("updated_at", "created_at", "id", "title")}
    out["items"] = [{k: v for k, v in i.items() if k not in ("id", "added_at")} for i in out["items"]]
    return out


# --- ADR-134's tests ---------------------------------------------------------------------------------


async def test_an_alert_item_citing_a_node_the_reader_may_not_see_is_withheld_as_a_yes_or_no(aw: AlertWorld) -> None:
    hidden = await _plain_alert(aw, "SECRET")
    other_hidden = await _plain_alert(aw, "SECRET")
    one, two = _new_pack(aw.w), _new_pack(aw.w)
    for pack, alerts in ((one, [hidden]), (two, [hidden, other_hidden])):
        aw.as_(EDITOR).post(f"{CASE}/packs/{pack}/items", json={"kind": "note", "text": "Opening", "classification": "OFFICIAL"})
        for alert_id in alerts:
            added = _add_alert(aw, pack, alert_id)
            assert added.status_code == 201, added.text
            assert added.json()["marking"] == "SECRET"
    low_one = aw.as_(LOW_EDITOR).get(f"{CASE}/packs/{one}")
    low_two = aw.as_(LOW_EDITOR).get(f"{CASE}/packs/{two}")
    assert low_one.status_code == 200, low_one.text
    assert low_one.json()["withheld"] is True
    assert [i["kind"] for i in low_one.json()["items"]] == ["note"]
    assert hidden not in low_one.text and "Ardent" not in low_one.text
    assert _without_times(low_one.json()) == _without_times(low_two.json()), (
        "one withheld alert or two: the reader is told the same yes, never how many")
    high = aw.as_(VIEWER).get(f"{CASE}/packs/{one}").json()
    assert high["withheld"] is False and [i["kind"] for i in high["items"]] == ["note", "alert"]


async def test_an_alert_item_resting_on_a_link_or_a_transaction_the_reader_may_not_see_is_withheld(
    aw: AlertWorld,
) -> None:
    a, b = aw.graph.node(f"n-{new_id()}", "A"), aw.graph.node(f"n-{new_id()}", "B")
    link = aw.graph.edge(f"e-{new_id()}", a, b, "SECRET")
    on_link = await aw.raise_alert(referent_node_ids=[a, b], edge_ids=[link])
    event = EventRecord(event_id=f"ev-{new_id()}", edge_id="x", edge_type="TRANSACTED", source_id=a, target_id=b,
                        occurred_at=NOW, properties={"amount": 9500}, investigation_scope="case-1",
                        handling=_handling("SECRET"))  # fmt: skip
    aw.events.events.append(event)
    on_event = await aw.raise_alert(referent_node_ids=[a, b], event_ids=[event.event_id])
    pack = _new_pack(aw.w)
    for alert_id in (on_link, on_event):
        assert _add_alert(aw, pack, alert_id).status_code == 201
    low = aw.as_(LOW_EDITOR).get(f"{CASE}/packs/{pack}").json()
    assert (low["withheld"], low["items"]) == (True, [])
    high = aw.as_(VIEWER).get(f"{CASE}/packs/{pack}").json()
    items = high["items"]
    assert [i["alert"]["links"][0]["type"] for i in items[:1]] == ["TRANSACTED"]
    assert items[1]["alert"]["transactions"][0]["amount"] == 9500.0


async def test_an_exporter_who_may_not_see_the_evidence_is_refused_and_nothing_is_recorded(aw: AlertWorld) -> None:
    pack = _new_pack(aw.w)
    assert _add_alert(aw, pack, await _plain_alert(aw, "SECRET")).status_code == 201
    _publish(aw.w, pack)
    refused = aw.as_(LOW_EDITOR).post(f"{CASE}/packs/{pack}/export", json={})
    assert refused.status_code == 403, refused.text
    assert "Ardent" not in refused.text
    assert aw.ledger_entries == [], "a refused export records nothing"
    allowed = aw.as_(EDITOR).post(f"{CASE}/packs/{pack}/export", json={})
    assert allowed.status_code == 200, allowed.text
    assert [i["kind"] for i in allowed.json()["items"]] == ["alert"] and len(aw.ledger_entries) == 1


async def test_an_open_alert_says_it_is_open_and_an_inferred_match_says_inferred(aw: AlertWorld) -> None:
    own = aw.graph.node(f"n-{new_id()}", "Structuring", node_type="Alert", state=ProvenanceState.INFERRED)
    a = aw.graph.node(f"n-{new_id()}", "Halcyon Marine Ltd")
    alert_id = await aw.raise_alert(referent_node_ids=[a], alert_node_id=own)
    pack = _new_pack(aw.w)
    added = _add_alert(aw, pack, alert_id)
    assert added.status_code == 201, added.text
    snapshot = added.json()["alert"]
    assert (snapshot["status"], snapshot["outcome"], snapshot["match"]) == ("open", None, "inferred")
    assert [e["name"] for e in snapshot["entities"]] == ["Halcyon Marine Ltd"], "its own node is not an entity"
    assert snapshot["explanation"] == "Rapid in-and-out through one account"
    assert (snapshot["kind"], snapshot["severity"], snapshot["typology"]) == ("typology", "medium", "structuring")


async def test_a_closed_alert_carries_its_outcome_and_reason(aw: AlertWorld) -> None:
    own = aw.graph.node(f"n-{new_id()}", "Structuring", node_type="Alert", state=ProvenanceState.ASSERTED)
    a = aw.graph.node(f"n-{new_id()}", "Halcyon Marine Ltd")
    alert_id = await aw.raise_alert(referent_node_ids=[a], alert_node_id=own, status="closed",
                                    disposition="true_positive", disposition_reason="Confirmed with the bank",
                                    decided_by=EDITOR.id)  # fmt: skip
    snapshot = _add_alert(aw, _new_pack(aw.w), alert_id).json()["alert"]
    assert (snapshot["status"], snapshot["outcome"], snapshot["reason"], snapshot["match"]) == (
        "closed", "true_positive", "Confirmed with the bank", "confirmed")


async def test_a_hotlist_alert_names_the_entry_it_matched(aw: AlertWorld) -> None:
    phone = aw.graph.node(f"n-{new_id()}", "+447700900310", node_type="Phone")
    alert_id = await aw.raise_alert(rule_id=f"hotlist:{new_id()}", typology=None, words=None,
                                    referent_node_ids=[phone])  # fmt: skip
    snapshot = _add_alert(aw, _new_pack(aw.w), alert_id).json()["alert"]
    assert (snapshot["kind"], snapshot["hotlist_entry"], snapshot["severity"]) == ("hotlist", "+447700900310", "high")
    assert snapshot["match"] == "inferred", "a match nobody has decided is not confirmed (rule 5)"


async def test_an_alert_outside_the_adders_queue_is_not_found(aw: AlertWorld) -> None:
    pack = _new_pack(aw.w)
    elsewhere = await _plain_alert(aw, investigation_id="case-2")
    hidden_from_low = await _plain_alert(aw, "SECRET")
    someone_elses = await _plain_alert(aw, rule_id=f"hotlist:{new_id()}", typology=None, words=None,
                                       owner_id="someone-else")  # fmt: skip
    for alert_id, who in ((elsewhere, EDITOR), (hidden_from_low, LOW_EDITOR), (someone_elses, EDITOR),
                          ("no-such-alert", EDITOR)):  # fmt: skip
        refused = _add_alert(aw, pack, alert_id, who)
        assert refused.status_code == 404, (alert_id, refused.text)
    assert aw.as_(EDITOR).get(f"{CASE}/packs/{pack}").json()["items"] == []


async def test_an_alert_item_is_withheld_when_what_it_cites_is_hidden_since(aw: AlertWorld) -> None:
    alert_id = await _plain_alert(aw)
    pack = _new_pack(aw.w)
    item = _add_alert(aw, pack, alert_id).json()
    assert item["marking"] == "OFFICIAL"
    node_id = item["alert"]["entities"][1]["node_id"]
    aw.w.graph.base.nodes[node_id] = aw.w.graph.base.nodes[node_id].model_copy(update={"handling": _handling("SECRET")})
    low = aw.as_(LOW_EDITOR).get(f"{CASE}/packs/{pack}").json()
    assert (low["withheld"], low["items"]) == (True, []), "checked again as the reader, against the graph now"


def test_adding_an_alert_needs_editor_and_record_assessment(aw: AlertWorld) -> None:
    import asyncio

    alert_id = asyncio.run(_plain_alert(aw))
    pack = _new_pack(aw.w)
    no_level = NO_LEVEL.model_copy(update={"roles": ["analyst"]})
    for who, status in ((VIEWER, 403), (READER, 403), (CLEARED_READER, 403), (no_level, 404)):
        refused = _add_alert(aw, pack, alert_id, who)
        assert refused.status_code == status, (who.id, refused.text)
    assert _add_alert(aw, pack, alert_id).status_code == 201
