"""Alert trends (`spec/06_DECISIONS.md` ADR-134 decision 3): the trend builder's second source. A
definition over alerts counts them by week or month, split by rule, typology, severity or outcome,
narrowed by up to five equalities, read through the analytics port's `alert_trend` as the reader —
whose conformance suite proves the counting and the access control in the query. Here: the
definition's checks, the routes and their rights (rule 4), and an alert trend into a pack.

What a mistake would do, and the case that catches it:
- an alert trend asked as someone other than the reader, or of another case —
  `test_an_alert_trend_is_counted_as_the_reader_in_this_case`;
- an alert definition naming event types, a sum, or a field outside the closed list —
  `test_an_alert_definition_names_only_the_closed_fields`;
- a rule shown by its key rather than its name — `test_rules_are_shown_by_name_and_hotlists_and_monitors_together`;
- the builder offering what alerts cannot be split by — `test_the_builder_offers_the_alert_fields_and_the_cases_rules`;
- a trend past its bound cut rather than refused — `test_an_alert_trend_past_its_bound_is_refused`;
- reached without the rights its event twin needs (rule 4) — `test_alert_trends_need_the_same_rights_as_event_trends`;
- an alert trend's snapshot in a pack resting on less than what it counted —
  `test_pack_alert_item.py::test_an_alert_trend_goes_into_a_pack_resting_on_what_it_counted`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from services.api.app import (
    app,
    get_analytics,
    get_audit,
    get_handling_scheme,
    get_investigations,
    get_ontology,
    get_principal,
    get_trend_store,
    get_typology_rules,
    get_working_set,
)
from services.api.trends import TrendDefinitionRefused, validate_definition

from ontology.handling import load_uk_le_scheme
from ports.analytics import TrendLimitExceeded
from schemas.analytics import AlertTrendRequest, CountedHandling, TrendPoint, TrendResult
from schemas.domain import Principal, TypologyRule
from schemas.trends import TrendDefinitionInput, TrendFilter
from tests.services.api.test_trends import (
    CASE,
    EDITOR,
    NO_LEVEL,
    ONTOLOGY,
    READER,
    VIEWER,
    _Audit,
    _Cases,
    _Store,
)

NOW = datetime(2026, 11, 1, tzinfo=UTC)
ALERTS = {"title": "Alerts by rule", "source": "alerts", "group_by": "rule"}


def _defn(**kwargs: Any) -> TrendDefinitionInput:
    return TrendDefinitionInput(**{"title": "A", "source": "alerts", **kwargs})


class _Analytics:
    def __init__(self) -> None:
        self.asked: list[tuple[AlertTrendRequest, Principal]] = []
        self.refuse = False
        self.points = [TrendPoint(period_start=NOW, series="typology:r1", value=2.0),
                       TrendPoint(period_start=NOW, series="hotlists", value=1.0)]  # fmt: skip
        self.handlings = [CountedHandling(classification="OFFICIAL-SENSITIVE", handling_code="P",
                                          owning_unit="unit-1", originator="unit-1")]  # fmt: skip

    async def alert_trend(self, req: AlertTrendRequest, principal: Principal) -> TrendResult:
        self.asked.append((req, principal))
        if self.refuse:
            raise TrendLimitExceeded("series", 12, 14)
        return TrendResult(interval=req.interval, measure="count", points=self.points,
                           series=sorted({p.series for p in self.points if p.series}),
                           total=sum(p.value for p in self.points), events=3,
                           classifications=sorted({h.classification for h in self.handlings}),
                           handlings=self.handlings)  # fmt: skip

    async def trend(self, *a: Any, **k: Any) -> TrendResult:
        raise AssertionError("an alert trend is never read as an event trend")


class _Rules:
    async def list_for_case(self, investigation_id: str, principal: Principal) -> list[TypologyRule]:
        assert investigation_id == CASE.id
        return [TypologyRule.model_validate({
            "id": "r1", "name": "Rapid movement over £9,000", "investigation_id": CASE.id, "owner_id": "ed",
            "created_at": NOW, "params": {"typology": "rapid_movement", "within_hours": 48, "keep_fraction": 0.9}})]  # fmt: skip


@pytest.fixture
def world() -> Any:
    analytics, store = _Analytics(), _Store()
    app.dependency_overrides.update({
        get_investigations: _Cases, get_analytics: lambda: analytics, get_trend_store: lambda: store,
        get_ontology: lambda: ONTOLOGY, get_handling_scheme: load_uk_le_scheme, get_audit: _Audit,
        get_working_set: lambda: None, get_typology_rules: lambda: _Rules(),
    })  # fmt: skip
    yield analytics, store
    app.dependency_overrides.clear()


def _as(who: Principal) -> TestClient:
    app.dependency_overrides[get_principal] = lambda: who
    return TestClient(app)


def test_an_alert_trend_is_counted_as_the_reader_in_this_case(world: Any) -> None:
    analytics, _ = world
    reader = VIEWER.model_copy(update={"datasets": ["ds-case-1"]})  # as `get_principal` scopes it
    response = _as(reader).post(f"/v1/investigations/{CASE.id}/trends/preview",
                                json={**ALERTS, "filters": [{"field": "severity", "value": "high"}]})  # fmt: skip
    assert response.status_code == 200, response.text
    ((request, who),) = analytics.asked
    assert who == reader and request.investigation_scope == CASE.id, "the reader, datasets and all"
    assert (request.group_by, request.filters, request.max_periods, request.max_series) == (
        "rule", {"severity": ["high"]}, 104, 12)  # fmt: skip
    assert response.json()["marking"] == "OFFICIAL-SENSITIVE"


def test_rules_are_shown_by_name_and_hotlists_and_monitors_together(world: Any) -> None:
    body = _as(VIEWER).post(f"/v1/investigations/{CASE.id}/trends/preview", json=ALERTS).json()
    assert body["result"]["series"] == ["Hotlists", "Rapid movement over £9,000"]
    assert {p["series"] for p in body["result"]["points"]} == {"Hotlists", "Rapid movement over £9,000"}


def test_an_alert_definition_names_only_the_closed_fields() -> None:
    validate_definition(_defn(group_by="outcome", filters=[TrendFilter(field="severity", value="high")]), ONTOLOGY)
    for wrong in (
        _defn(event_types=["TRANSACTED"]),
        _defn(measure="sum", measure_field="amount"),
        _defn(group_by="channel"),
        _defn(filters=[TrendFilter(field="owner_id", value="x")]),
        _defn(filters=[TrendFilter(field="severity", value="urgent")]),
        _defn(filters=[TrendFilter(field="outcome", value="maybe")]),
    ):
        with pytest.raises(TrendDefinitionRefused):
            validate_definition(wrong, ONTOLOGY)
    with pytest.raises(ValidationError):
        TrendDefinitionInput(title="E", source="events")  # an event trend still needs its event types
    with pytest.raises(ValidationError):
        _defn(filters=[TrendFilter(field="severity", value="high")] * 6)


def test_the_builder_offers_the_alert_fields_and_the_cases_rules(world: Any) -> None:
    options = _as(VIEWER).get(f"/v1/investigations/{CASE.id}/trends/options").json()
    fields = {f["name"]: f for f in options["alert_fields"]}
    assert list(fields) == ["rule", "typology", "severity", "outcome"]
    assert fields["rule"]["values"] == ["typology:r1", "hotlists", "monitors"]
    assert fields["rule"]["labels"] == ["Rapid movement over £9,000", "Hotlists", "Monitors"]
    assert fields["typology"]["values"] == ["rapid_movement"]
    assert fields["severity"]["values"] == ["high", "medium", "low"]
    assert fields["outcome"]["values"] == ["open", "claimed", "true_positive", "false_positive", "closed"]


def test_an_alert_trend_past_its_bound_is_refused(world: Any) -> None:
    analytics, _ = world
    analytics.refuse = True
    over = _as(VIEWER).post(f"/v1/investigations/{CASE.id}/trends/preview", json=ALERTS)
    assert over.status_code == 409 and over.json()["cap_kind"] == "series"


def test_alert_trends_need_the_same_rights_as_event_trends(world: Any) -> None:
    assert _as(READER).post(f"/v1/investigations/{CASE.id}/trends/preview", json=ALERTS).status_code == 403
    assert _as(NO_LEVEL).post(f"/v1/investigations/{CASE.id}/trends/preview", json=ALERTS).status_code == 404
    assert _as(VIEWER).post(f"/v1/investigations/{CASE.id}/trends", json=ALERTS).status_code == 403
    saved = _as(EDITOR).post(f"/v1/investigations/{CASE.id}/trends", json=ALERTS)
    assert saved.status_code == 201, saved.text
    assert saved.json()["source"] == "alerts"
    figures = _as(VIEWER).get(f"/v1/investigations/{CASE.id}/trends/{saved.json()['id']}/figures")
    assert figures.status_code == 200 and figures.json()["result"]["events"] == 3
    assert _as(NO_LEVEL).get(f"/v1/investigations/{CASE.id}/trends/{saved.json()['id']}/figures").status_code == 404
