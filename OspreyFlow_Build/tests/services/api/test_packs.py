"""Case report packs (`06_DECISIONS.md` ADR-113 decisions 3 to 5 and 7, Amendment 1): the routes as
each reader sees them, against the real pack store in Postgres; the graph, the judgements, the saved
trends and the analytics are fakes.

What a mistake would do, and the case that catches it:
- a snapshot readable by someone below its marking, or the withheld item's place betrayed —
  `test_a_snapshot_is_marked_at_the_highest_counted_and_withheld_below_it_with_the_count_shown`;
- a restricted code counted but only the classification checked —
  `test_a_restricted_handling_withholds_a_snapshot_from_a_reader_outside_its_unit`;
- the published version read from the draft — `test_a_published_version_is_unchanged_after_the_draft_is_edited`;
- the published packs read without `read_reports`, or a case's existence said to someone with no level —
  `test_reading_published_packs_needs_read_reports_and_a_level`;
- assembling at Viewer, or by a Reports Viewer — `test_assembling_and_publishing_need_editor_and_record_assessment`;
- a refresh that loses the earlier snapshot — `test_a_refreshed_snapshot_keeps_the_old_one_in_history`;
- an entity the reader can no longer see still shown — `test_an_entity_item_is_withheld_when_the_reader_cannot_see_it_now`;
- a publisher publishing what they cannot see — `test_a_publisher_cannot_publish_what_they_cannot_see`;
- a note marked above its author, or below what they say — `test_a_note_is_marked_as_its_author_says_never_above_their_clearance`;
- a withdrawn version still served, the withdrawal unrecorded — `test_a_withdrawn_publication_is_not_read_and_the_withdrawal_is_recorded`;
- an assessment changing in the pack when the judgement is edited — `test_an_assessment_is_frozen_as_written`;
- a reorder that moves a withheld item — `test_reorder_moves_only_the_readers_own_slots`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_analytics,
    get_audit,
    get_graph,
    get_handling_scheme,
    get_investigations,
    get_judgements_store,
    get_ontology,
    get_pack_store,
    get_principal,
    get_trend_store,
    get_working_set,
)
from services.api.assessments import JudgementNotFoundError
from services.api.config import PostgresConfig
from services.api.investigations import (
    AccessLevel,
    InsufficientAccessError,
    Investigation,
    InvestigationNotFoundError,
)
from services.api.packs import PackStore, item_visible, reorder_visible

from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from schemas.analytics import CountedHandling, TrendRequest, TrendResult
from schemas.domain import (
    AuditStub,
    EdgeTypeDef,
    Handling,
    Judgement,
    Node,
    OntologySchema,
    Principal,
    PropertyDef,
    Provenance,
    SourceRef,
)
from schemas.trends import TrendDefinition

SCHEME = load_uk_le_scheme()
ONTOLOGY = OntologySchema(
    version=1, entity_types=[],
    edge_types=[EdgeTypeDef(name="TRANSACTED", **{"from": ["Account"], "to": ["Account"]}, temporal=True,
                            basis="direct", properties=[PropertyDef(name="amount", type="float")])],
)  # fmt: skip

EDITOR = Principal(id="ed", clearance="SECRET", org_unit="unit-1", roles=["analyst"],
                   receivable_handling_codes=["R"])  # fmt: skip
LOW_EDITOR = Principal(id="ed-low", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
VIEWER = Principal(id="vw", clearance="SECRET", org_unit="unit-1", roles=["analyst"])
READER = Principal(id="rv", clearance="OFFICIAL", org_unit="unit-1", roles=["reports_viewer"])
CLEARED_READER = Principal(id="rv-hi", clearance="SECRET", org_unit="unit-1", roles=["reports_viewer"])
OUTSIDER = Principal(id="rv-out", clearance="SECRET", org_unit="unit-2", roles=["reports_viewer"],
                     receivable_handling_codes=["R"])  # fmt: skip
ADMIN = Principal(id="adm", clearance="SECRET", org_unit="unit-1", roles=["osprey-admin"])
NO_LEVEL = Principal(id="none", clearance="SECRET", org_unit="unit-1", roles=["reports_viewer"])

LEVELS = {"ed": AccessLevel.EDITOR, "ed-low": AccessLevel.EDITOR, "vw": AccessLevel.VIEWER,
          "rv": AccessLevel.VIEWER, "rv-hi": AccessLevel.VIEWER, "rv-out": AccessLevel.VIEWER,
          "adm": AccessLevel.VIEWER}  # fmt: skip
NOW = datetime(2026, 3, 1, tzinfo=UTC)


def _handling(classification: str = "OFFICIAL", code: str = "P", unit: str = "unit-1",
              originator: str = "unit-1") -> Handling:  # fmt: skip
    return Handling(classification=classification, handling_code=code, owning_unit=unit, originator=originator)


# --- the pure rules --------------------------------------------------------------------------------


def test_an_item_is_read_only_by_someone_who_may_view_everything_it_rests_on() -> None:
    official, secret = _handling(), _handling("SECRET")
    restricted = _handling(code="R", unit="unit-1", originator="unit-9")
    assert item_visible([official], READER, SCHEME)
    assert not item_visible([official, secret], READER, SCHEME), "below one of its markings"
    assert item_visible([official, secret], CLEARED_READER, SCHEME)
    assert not item_visible([restricted], CLEARED_READER, SCHEME), "cleared, but does not receive R"
    assert not item_visible([restricted], OUTSIDER, SCHEME), "receives R, but in neither unit"
    assert item_visible([restricted], EDITOR, SCHEME)


def test_reorder_moves_only_the_readers_own_slots() -> None:
    current = ["a", "hidden", "b", "c"]
    assert reorder_visible(current, {"a", "b", "c"}, ["c", "a", "b"]) == ["c", "hidden", "a", "b"]
    for wrong in (["a", "b"], ["a", "b", "c", "hidden"], ["a", "a", "b", "c"], ["a", "b", "x"]):
        with pytest.raises(ValueError):
            reorder_visible(current, {"a", "b", "c"}, wrong)


# --- the fakes -------------------------------------------------------------------------------------


class _Cases:
    case = Investigation(id="case-1", name="C", created_at=NOW, created_by="ed", owning_unit="unit-1")

    async def get_authorized(self, investigation_id: str, principal: Principal, *, need: AccessLevel) -> Investigation:
        level = LEVELS.get(principal.id)
        if investigation_id != self.case.id or level is None:
            raise InvestigationNotFoundError(investigation_id)
        if level.rank < need.rank:
            raise InsufficientAccessError("too low")
        return self.case


class _Graph:
    """Nodes visible to a principal by the scheme's own rule, so a node is hidden exactly as the
    real adapter would hide it."""

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}

    def add(self, node_id: str, handling: Handling, name: str) -> None:
        self.nodes[node_id] = Node(
            id=node_id, type="Person", properties={"name": name}, handling=handling,
            provenance=Provenance(state="asserted", first_seen=NOW,
                                  sources=[SourceRef(document_id="d1", locator="p1", excerpt_hash="h")]),
            audit=AuditStub(created_at=NOW, created_by="ed", revision=1),
        )  # fmt: skip

    async def get_node(self, node_id: str, principal: Principal, *, include_superseded: bool = False) -> Node | None:
        node = self.nodes.get(node_id)
        if node is None or not item_visible([node.handling], principal, SCHEME):
            return None
        return node


class _Judgements:
    def __init__(self) -> None:
        self.saved: dict[str, Judgement] = {}

    async def get_authorized(self, judgement_id: str, principal: Principal) -> Judgement:
        if judgement_id not in self.saved:
            raise JudgementNotFoundError(judgement_id)
        return self.saved[judgement_id]


class _Trends:
    def __init__(self) -> None:
        self.saved: dict[str, TrendDefinition] = {}

    async def get(self, case_id: str, trend_id: str) -> TrendDefinition | None:
        found = self.saved.get(trend_id)
        return found if found and found.investigation_id == case_id else None


class _Analytics:
    """Answers with whatever handlings the test says the counted events carried."""

    def __init__(self) -> None:
        self.handlings = [CountedHandling(classification="OFFICIAL", handling_code="P", owning_unit="unit-1",
                                          originator="unit-1")]  # fmt: skip
        self.total = 10.0

    async def trend(self, req: TrendRequest, principal: Principal) -> TrendResult:
        return TrendResult(interval=req.interval, measure=req.measure, points=[], total=self.total, events=1,
                           classifications=sorted({h.classification for h in self.handlings}),
                           handlings=self.handlings)  # fmt: skip


class _Audit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, **kwargs: Any) -> None:
        self.actions.append(kwargs["action"])


class World:
    def __init__(self) -> None:
        self.graph, self.judgements = _Graph(), _Judgements()
        self.trends, self.analytics, self.audit = _Trends(), _Analytics(), _Audit()
        self.trends.saved["t1"] = TrendDefinition(
            title="Sum of amounts", event_types=["TRANSACTED"], measure="sum", measure_field="amount",
            id="t1", investigation_id="case-1", created_by="ed", created_at=NOW, updated_at=NOW)  # fmt: skip

    def as_(self, who: Principal) -> TestClient:
        app.dependency_overrides[get_principal] = lambda: who
        return TestClient(app)


async def _pack_store() -> AsyncIterator[PackStore]:
    """One store per request: an asyncpg pool belongs to the event loop it was made in, and each
    test client runs its own."""
    store = await PackStore.connect(PostgresConfig.from_env().dsn)
    try:
        yield store
    finally:
        await store.close()


@pytest.fixture
def world() -> Iterator[World]:
    w = World()
    app.dependency_overrides.update({
        get_investigations: _Cases, get_pack_store: _pack_store, get_graph: lambda: w.graph,
        get_judgements_store: lambda: w.judgements, get_trend_store: lambda: w.trends,
        get_analytics: lambda: w.analytics, get_ontology: lambda: ONTOLOGY,
        get_handling_scheme: lambda: SCHEME, get_audit: lambda: w.audit, get_working_set: lambda: None,
    })  # fmt: skip
    yield w
    app.dependency_overrides.clear()


CASE = "/v1/investigations/case-1"


def _new_pack(w: World, title: str = "Weekly review") -> str:
    response = w.as_(EDITOR).post(f"{CASE}/packs", json={"title": f"{title} {new_id()}"})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _add(w: World, pack: str, who: Principal = EDITOR, **body: Any) -> dict[str, Any]:
    response = w.as_(who).post(f"{CASE}/packs/{pack}/items", json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


def _publish(w: World, pack: str, who: Principal = EDITOR) -> dict[str, Any]:
    response = w.as_(who).post(f"{CASE}/packs/{pack}/publish")
    assert response.status_code == 201, response.text
    return dict(response.json())


# --- marking and withholding ------------------------------------------------------------------------


def test_a_snapshot_is_marked_at_the_highest_counted_and_withheld_below_it_with_the_count_shown(world: World) -> None:
    pack = _new_pack(world)
    _add(world, pack, kind="note", text="Opening note", classification="OFFICIAL")
    world.analytics.handlings = [
        CountedHandling(classification="OFFICIAL", handling_code="P", owning_unit="unit-1", originator="unit-1"),
        CountedHandling(classification="SECRET", handling_code="P", owning_unit="unit-1", originator="unit-1")]  # fmt: skip
    trend = _add(world, pack, kind="trend", trend_id="t1")
    assert trend["marking"] == "SECRET" and trend["trend"]["result"]["total"] == 10.0
    assert trend["added_by"] == "ed" and trend["trend"]["definition"]["title"] == "Sum of amounts"
    _add(world, pack, kind="note", text="Closing note", classification="OFFICIAL")
    _publish(world, pack)

    low = world.as_(READER).get(f"{CASE}/packs/{pack}/published")
    assert low.status_code == 200, low.text
    body = low.json()
    assert body["withheld"] == 1 and [i["note"] for i in body["items"]] == ["Opening note", "Closing note"]
    assert trend["id"] not in low.text, "never which item"
    assert "position" not in low.text, "no gap that says where it was"
    high = world.as_(CLEARED_READER).get(f"{CASE}/packs/{pack}/published").json()
    assert high["withheld"] == 0 and high["marking"] == "SECRET" and len(high["items"]) == 3
    assert "read_published_pack" in world.audit.actions, "every read is audited"


def test_a_restricted_handling_withholds_a_snapshot_from_a_reader_outside_its_unit(world: World) -> None:
    pack = _new_pack(world)
    world.analytics.handlings = [
        CountedHandling(classification="OFFICIAL", handling_code="R", owning_unit="unit-1", originator="unit-1")]
    item = _add(world, pack, kind="trend", trend_id="t1")
    assert item["marking"] == "OFFICIAL", "the banner says the classification"
    _publish(world, pack)
    assert world.as_(OUTSIDER).get(f"{CASE}/packs/{pack}/published").json()["withheld"] == 1
    assert world.as_(CLEARED_READER).get(f"{CASE}/packs/{pack}/published").json()["withheld"] == 1, \
        "cleared above it, but not a recipient of R"


def test_an_entity_item_is_withheld_when_the_reader_cannot_see_it_now(world: World) -> None:
    pack = _new_pack(world)
    world.graph.add("n1", _handling(), "Ada Okafor")
    item = _add(world, pack, kind="entity", node_id="n1", caption="The account holder")
    assert item["entity"] == {"node_id": "n1", "entity_type": "Person", "name": "Ada Okafor",
                              "caption": "The account holder"}  # fmt: skip
    _publish(world, pack)
    assert world.as_(READER).get(f"{CASE}/packs/{pack}/published").json()["withheld"] == 0
    world.graph.nodes["n1"] = world.graph.nodes["n1"].model_copy(update={"handling": _handling("SECRET")})
    assert world.as_(READER).get(f"{CASE}/packs/{pack}/published").json()["withheld"] == 1, \
        "reclassified since it was added: checked again as the reader"
    assert world.as_(EDITOR).post(f"{CASE}/packs/{pack}/items",
                                  json={"kind": "entity", "node_id": "nope", "caption": "x"}).status_code == 404


def test_an_assessment_is_frozen_as_written(world: World) -> None:
    pack = _new_pack(world)
    world.graph.add("n2", _handling("OFFICIAL-SENSITIVE"), "Brightwater Ltd")
    world.judgements.saved["j1"] = Judgement(id="j1", investigation_id="case-1", statement="Likely a mule account",
                                             probability_band="likely", supporting=["n2"], author="ed",
                                             created_at=NOW)  # fmt: skip
    item = _add(world, pack, kind="assessment", judgement_id="j1")
    assert item["marking"] == "OFFICIAL-SENSITIVE", "marked at what it rests on"
    world.judgements.saved["j1"] = world.judgements.saved["j1"].model_copy(update={"statement": "Edited later"})
    draft = world.as_(EDITOR).get(f"{CASE}/packs/{pack}").json()
    assert draft["items"][0]["assessment"]["statement"] == "Likely a mule account"
    _publish(world, pack)
    assert world.as_(READER).get(f"{CASE}/packs/{pack}/published").json()["withheld"] == 1


def test_a_note_is_marked_as_its_author_says_never_above_their_clearance(world: World) -> None:
    pack = _new_pack(world)
    assert _add(world, pack, kind="note", text="x", classification="OFFICIAL-SENSITIVE")["marking"] == "OFFICIAL-SENSITIVE"
    above = world.as_(LOW_EDITOR).post(f"{CASE}/packs/{pack}/items",
                                       json={"kind": "note", "text": "x", "classification": "SECRET"})  # fmt: skip
    assert above.status_code == 422
    unmarked = world.as_(EDITOR).post(f"{CASE}/packs/{pack}/items", json={"kind": "note", "text": "x"})
    assert unmarked.status_code == 422, "a note's marking is never assumed"


# --- versions -------------------------------------------------------------------------------------


def test_a_published_version_is_unchanged_after_the_draft_is_edited(world: World) -> None:
    pack = _new_pack(world)
    first = _add(world, pack, kind="note", text="First", classification="OFFICIAL")
    second = _add(world, pack, kind="note", text="Second", classification="OFFICIAL")
    assert _publish(world, pack)["version"] == 1
    editor = world.as_(EDITOR)
    assert editor.put(f"{CASE}/packs/{pack}/order", json={"item_ids": [second["id"], first["id"]]}).status_code == 200
    assert editor.delete(f"{CASE}/packs/{pack}/items/{first['id']}").status_code == 204
    _add(world, pack, kind="note", text="Third", classification="OFFICIAL")
    published = world.as_(READER).get(f"{CASE}/packs/{pack}/published").json()
    assert (published["version"], [i["note"] for i in published["items"]]) == (1, ["First", "Second"])
    assert [i["note"] for i in world.as_(EDITOR).get(f"{CASE}/packs/{pack}").json()["items"]] == ["Second", "Third"]
    assert _publish(world, pack)["version"] == 2
    assert [i["note"] for i in world.as_(READER).get(f"{CASE}/packs/{pack}/published").json()["items"]] == \
        ["Second", "Third"]


def test_a_refreshed_snapshot_keeps_the_old_one_in_history(world: World) -> None:
    pack = _new_pack(world)
    old = _add(world, pack, kind="trend", trend_id="t1")
    world.analytics.total = 25.0
    refreshed = world.as_(EDITOR).post(f"{CASE}/packs/{pack}/items/{old['id']}/refresh")
    assert refreshed.status_code == 201, refreshed.text
    new = refreshed.json()
    assert new["id"] != old["id"] and new["trend"]["result"]["total"] == 25.0
    draft = world.as_(EDITOR).get(f"{CASE}/packs/{pack}").json()
    assert [i["id"] for i in draft["items"]] == [new["id"]], "in the old one's place"
    history = world.as_(EDITOR).get(f"{CASE}/packs/{pack}/history").json()
    (earlier,) = history["earlier_snapshots"]
    assert (earlier["id"], earlier["trend"]["result"]["total"], earlier["replaced_by"]) == (old["id"], 10.0, new["id"])
    note = _add(world, pack, kind="note", text="n", classification="OFFICIAL")
    assert world.as_(EDITOR).post(f"{CASE}/packs/{pack}/items/{note['id']}/refresh").status_code == 422


def test_a_publisher_cannot_publish_what_they_cannot_see(world: World) -> None:
    pack = _new_pack(world)
    _add(world, pack, kind="note", text="secret", classification="SECRET")
    refused = world.as_(LOW_EDITOR).post(f"{CASE}/packs/{pack}/publish")
    assert refused.status_code == 409 and refused.json() == {"error": "pack_has_withheld_items", "withheld": 1}
    empty = _new_pack(world)
    assert world.as_(EDITOR).post(f"{CASE}/packs/{empty}/publish").status_code == 422, "nothing to publish"


def test_a_withdrawn_publication_is_not_read_and_the_withdrawal_is_recorded(world: World) -> None:
    pack = _new_pack(world)
    _add(world, pack, kind="note", text="v1", classification="OFFICIAL")
    _publish(world, pack)
    listed = world.as_(READER).get(f"{CASE}/published").json()
    assert pack in [p["pack_id"] for p in listed]
    withdrawn = world.as_(EDITOR).post(f"{CASE}/packs/{pack}/versions/1/withdraw", json={"reason": "superseded"})
    assert withdrawn.status_code == 200, withdrawn.text
    assert world.as_(READER).get(f"{CASE}/packs/{pack}/published").status_code == 404
    assert pack not in [p["pack_id"] for p in world.as_(READER).get(f"{CASE}/published").json()]
    (version,) = world.as_(EDITOR).get(f"{CASE}/packs/{pack}").json()["pack"]["versions"]
    assert (version["withdrawn_by"], version["withdrawal_reason"]) == ("ed", "superseded")
    assert "withdraw_pack" in world.audit.actions
    again = world.as_(EDITOR).post(f"{CASE}/packs/{pack}/versions/1/withdraw", json={"reason": "again"})
    assert again.status_code == 404, "withdrawn once"


# --- rights ---------------------------------------------------------------------------------------


def test_reading_published_packs_needs_read_reports_and_a_level(world: World) -> None:
    pack = _new_pack(world)
    _add(world, pack, kind="note", text="n", classification="OFFICIAL")
    _publish(world, pack)
    assert world.as_(ADMIN).get(f"{CASE}/packs/{pack}/published").status_code == 403, "Viewer, no read_reports"
    assert world.as_(ADMIN).get(f"{CASE}/published").status_code == 403
    assert world.as_(NO_LEVEL).get(f"{CASE}/packs/{pack}/published").status_code == 404, "read_reports, no level"
    assert world.as_(NO_LEVEL).get(f"{CASE}/published").status_code == 404


def test_assembling_and_publishing_need_editor_and_record_assessment(world: World) -> None:
    pack = _new_pack(world)
    note = {"kind": "note", "text": "n", "classification": "OFFICIAL"}
    for who in (VIEWER, READER):
        client = world.as_(who)
        assert client.post(f"{CASE}/packs", json={"title": "x"}).status_code == 403
        assert client.post(f"{CASE}/packs/{pack}/items", json=note).status_code == 403
        assert client.post(f"{CASE}/packs/{pack}/publish").status_code == 403
    assert world.as_(READER).get(f"{CASE}/packs/{pack}").status_code == 403, "a draft is not a Reports Viewer's"
    assert world.as_(VIEWER).get(f"{CASE}/packs/{pack}").status_code == 200
    assert world.as_(EDITOR).get(f"{CASE}/packs/{new_id()}").status_code == 404
