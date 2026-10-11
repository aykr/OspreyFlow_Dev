"""Trend reports (`06_DECISIONS.md` ADR-113 decisions 1, 2 and 7): a definition names only what the
deployment's ontology declares; it is counted for the reader through the analytics port (whose own
conformance suite proves a hidden event moves nothing); saving needs Editor; a trend past its bound is
a typed refusal with its options, never a cut.

What a mistake would do, and the case that catches it:
- a sum over a category, or over a property one chosen type lacks — `test_a_definition_names_only_what_the_ontology_declares`;
- an aliased link's events left out, or counted under the old name — `test_aliases_are_read_with_their_type_and_shown_under_its_name`;
- a snapshot marked lower than something it counted — `test_the_marking_is_the_highest_counted_and_an_unknown_ranks_highest`;
- a Viewer saving to the case — `test_saving_needs_editor_and_reading_needs_viewer`;
- another case's trend read through this one — `test_another_cases_trend_is_not_found`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from ports.analytics import TrendLimitExceeded
from services.api.app import (
    app,
    get_analytics,
    get_audit,
    get_handling_scheme,
    get_investigations,
    get_ontology,
    get_principal,
    get_trend_store,
    get_working_set,
)
from services.api.investigations import (
    AccessLevel,
    InsufficientAccessError,
    Investigation,
    InvestigationNotFoundError,
)
from services.api.trends import (
    TrendDefinitionRefused,
    highest,
    name_series,
    to_request,
    trend_options,
    validate_definition,
)

from ontology.handling import load_uk_le_scheme
from schemas.analytics import TrendMeasure, TrendPoint, TrendRequest, TrendResult
from schemas.domain import EdgeTypeDef, OntologySchema, Principal, PropertyDef
from schemas.trends import TrendDefinition, TrendDefinitionInput, TrendFilter

ONTOLOGY = OntologySchema(
    version=1,
    entity_types=[],
    edge_types=[
        EdgeTypeDef(name="TRANSACTED", **{"from": ["Account"], "to": ["Account"]}, temporal=True,
                    basis="direct", aliases=["PAID"], label="Transacted", properties=[
            PropertyDef(name="amount", type="float"),
            PropertyDef(name="channel", type="enum", values=["cash", "wire"]),
            PropertyDef(name="note", type="string", sensitivity="high")]),
        EdgeTypeDef(name="CALLED", **{"from": ["Person"], "to": ["Person"]}, temporal=True, basis="direct",
                    properties=[PropertyDef(name="duration", type="integer")]),
        EdgeTypeDef(name="OWNS", **{"from": ["Person"], "to": ["Account"]}, basis="direct"),
    ],
)  # fmt: skip
CASE = Investigation(id="case-1", name="C", created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="a",
                     owning_unit="unit-1")  # fmt: skip
EDITOR = Principal(id="ed", clearance="SECRET", org_unit="unit-1", roles=["analyst"])
VIEWER = Principal(id="vw", clearance="SECRET", org_unit="unit-1", roles=["analyst"])
NO_LEVEL = Principal(id="none", clearance="SECRET", org_unit="unit-1", roles=["analyst"])
READER = Principal(id="rv", clearance="SECRET", org_unit="unit-1", roles=["reports_viewer"])


def _defn(**kwargs: Any) -> TrendDefinitionInput:
    return TrendDefinitionInput(**{"title": "T", "event_types": ["TRANSACTED"], **kwargs})


# --- the ontology check --------------------------------------------------------------------------


def test_the_builder_offers_only_temporal_types_and_never_a_high_sensitivity_property() -> None:
    options = trend_options(ONTOLOGY)
    assert [o.name for o in options.event_types] == ["TRANSACTED", "CALLED"]
    transacted = options.event_types[0]
    assert [(f.name, f.kind) for f in transacted.fields] == [("amount", "number"), ("channel", "category")]


def test_a_definition_names_only_what_the_ontology_declares() -> None:
    validate_definition(_defn(measure=TrendMeasure.SUM, measure_field="amount", group_by="channel"), ONTOLOGY)
    refusals = {
        "an unknown type": _defn(event_types=["OWNS"]),
        "a sum over a category": _defn(measure=TrendMeasure.SUM, measure_field="channel"),
        "a property one chosen type lacks": _defn(event_types=["TRANSACTED", "CALLED"], measure=TrendMeasure.SUM,
                                                  measure_field="amount"),
        "a count with a property": _defn(measure_field="amount"),
        "a value outside the enumeration": _defn(filters=[TrendFilter(field="channel", value="crypto")]),
        "a high-sensitivity property": _defn(group_by="note"),
    }  # fmt: skip
    for why, defn in refusals.items():
        with pytest.raises(TrendDefinitionRefused):
            validate_definition(defn, ONTOLOGY)
            pytest.fail(f"{why} was accepted")
    with pytest.raises(TrendDefinitionRefused, match="Called"):
        validate_definition(refusals["a property one chosen type lacks"], ONTOLOGY)


def test_aliases_are_read_with_their_type_and_shown_under_its_name() -> None:
    now = datetime(2026, 3, 2, tzinfo=UTC)
    request, start = to_request(_defn(group_by="event_type", weeks=4), ONTOLOGY, "case-1", now)
    assert request.filter.edge_types == ["PAID", "TRANSACTED"]
    assert request.group_by == "edge_type" and (now - start).days == 28
    week = datetime(2026, 2, 23, tzinfo=UTC)
    result = TrendResult(interval="week", measure="count", total=3, events=3, series=["PAID", "TRANSACTED"],
                         points=[TrendPoint(period_start=week, series="PAID", value=1),
                                 TrendPoint(period_start=week, series="TRANSACTED", value=2)])  # fmt: skip
    named = name_series(result, _defn(group_by="event_type"), ONTOLOGY)
    assert [(p.series, p.value) for p in named.points] == [("TRANSACTED", 3.0)] and named.series == ["TRANSACTED"]


def test_the_marking_is_the_highest_counted_and_an_unknown_ranks_highest() -> None:
    order = list(load_uk_le_scheme().classification)
    assert highest(["OFFICIAL", "SECRET", "PUBLIC"], order) == "SECRET"
    assert highest(["OFFICIAL", "SOMETHING-NEW"], order) == "SOMETHING-NEW"
    assert highest([], order) is None


# --- the routes ----------------------------------------------------------------------------------


class _Cases:
    levels = {"ed": AccessLevel.EDITOR, "vw": AccessLevel.VIEWER, "rv": AccessLevel.VIEWER}

    async def get_authorized(self, investigation_id: str, principal: Principal, *, need: AccessLevel) -> Investigation:
        level = self.levels.get(principal.id)
        if investigation_id != CASE.id or level is None:
            raise InvestigationNotFoundError(investigation_id)
        if level.rank < need.rank:
            raise InsufficientAccessError("too low")
        return CASE


class _Analytics:
    def __init__(self) -> None:
        self.asked: list[tuple[TrendRequest, str]] = []
        self.refuse = False

    async def trend(self, req: TrendRequest, principal: Principal) -> TrendResult:
        self.asked.append((req, principal.id))
        if self.refuse:
            raise TrendLimitExceeded("periods", 104, 130)
        return TrendResult(interval=req.interval, measure=req.measure, points=[], total=0, events=0,
                           classifications=["OFFICIAL", "OFFICIAL-SENSITIVE"])  # fmt: skip


class _Store:
    def __init__(self) -> None:
        self.saved: dict[str, TrendDefinition] = {}

    async def create(self, case_id: str, defn: TrendDefinitionInput, by: Principal) -> TrendDefinition:
        now = datetime(2026, 3, 1, tzinfo=UTC)
        saved = TrendDefinition(**defn.model_dump(), id=f"t{len(self.saved) + 1}", investigation_id=case_id,
                                created_by=by.id, created_at=now, updated_at=now)  # fmt: skip
        self.saved[saved.id] = saved
        return saved

    async def list_for_case(self, case_id: str) -> list[TrendDefinition]:
        return [t for t in self.saved.values() if t.investigation_id == case_id]

    async def get(self, case_id: str, trend_id: str) -> TrendDefinition | None:
        found = self.saved.get(trend_id)
        return found if found and found.investigation_id == case_id else None

    async def delete(self, case_id: str, trend_id: str) -> bool:
        return self.saved.pop(trend_id, None) is not None if await self.get(case_id, trend_id) else False


class _Audit:
    async def record(self, **kwargs: Any) -> None:
        return None


@pytest.fixture
def world() -> tuple[_Analytics, _Store]:
    analytics, store = _Analytics(), _Store()
    app.dependency_overrides.update({
        get_investigations: _Cases, get_analytics: lambda: analytics, get_trend_store: lambda: store,
        get_ontology: lambda: ONTOLOGY, get_handling_scheme: load_uk_le_scheme, get_audit: _Audit,
        get_working_set: lambda: None,
    })  # fmt: skip
    yield analytics, store
    app.dependency_overrides.clear()


def _as(who: Principal) -> TestClient:
    app.dependency_overrides[get_principal] = lambda: who
    return TestClient(app)


BODY = {"title": "Cash by week", "event_types": ["TRANSACTED"], "measure": "sum", "measure_field": "amount",
        "group_by": "channel"}  # fmt: skip


def test_a_preview_is_counted_as_the_reader_and_marked_at_the_highest_counted(world: tuple[_Analytics, _Store]) -> None:
    analytics, _ = world
    response = _as(VIEWER).post("/v1/investigations/case-1/trends/preview", json=BODY)
    assert response.status_code == 200, response.text
    assert response.json()["marking"] == "OFFICIAL-SENSITIVE"
    (request, who), = analytics.asked
    assert who == "vw" and request.filter.investigation_scope == "case-1", "counted as the reader, in this case"


def test_saving_needs_editor_and_reading_needs_viewer(world: tuple[_Analytics, _Store]) -> None:
    assert _as(VIEWER).post("/v1/investigations/case-1/trends", json=BODY).status_code == 403
    saved = _as(EDITOR).post("/v1/investigations/case-1/trends", json=BODY)
    assert saved.status_code == 201, saved.text
    trend = saved.json()["id"]
    assert [t["title"] for t in _as(VIEWER).get("/v1/investigations/case-1/trends").json()] == ["Cash by week"]
    assert _as(VIEWER).get(f"/v1/investigations/case-1/trends/{trend}/figures").status_code == 200
    assert _as(NO_LEVEL).get("/v1/investigations/case-1/trends").status_code == 404
    assert _as(VIEWER).delete(f"/v1/investigations/case-1/trends/{trend}").status_code == 403
    assert _as(EDITOR).delete(f"/v1/investigations/case-1/trends/{trend}").status_code == 204


def test_a_reports_viewer_cannot_build_trends(world: tuple[_Analytics, _Store]) -> None:
    assert _as(READER).post("/v1/investigations/case-1/trends/preview", json=BODY).status_code == 403


def test_another_cases_trend_is_not_found(world: tuple[_Analytics, _Store]) -> None:
    _, store = world
    store.saved["elsewhere"] = TrendDefinition(**_defn().model_dump(), id="elsewhere", investigation_id="case-2",
                                               created_by="x", created_at=datetime(2026, 1, 1, tzinfo=UTC),
                                               updated_at=datetime(2026, 1, 1, tzinfo=UTC))  # fmt: skip
    assert _as(VIEWER).get("/v1/investigations/case-1/trends/elsewhere/figures").status_code == 404


def test_a_refused_definition_and_a_trend_past_its_bound_are_said(world: tuple[_Analytics, _Store]) -> None:
    analytics, _ = world
    refused = _as(VIEWER).post("/v1/investigations/case-1/trends/preview", json={**BODY, "measure_field": "channel"})
    assert refused.status_code == 422 and refused.json()["error"] == "trend_refused"
    analytics.refuse = True
    over = _as(VIEWER).post("/v1/investigations/case-1/trends/preview", json=BODY)
    assert over.status_code == 409
    assert over.json() == {"error": "limit_exceeded", "cap_kind": "periods", "cap": 104, "would_be": 130,
                           "options": ["shorter_period", "monthly_interval", "fewer_series"]}  # fmt: skip
