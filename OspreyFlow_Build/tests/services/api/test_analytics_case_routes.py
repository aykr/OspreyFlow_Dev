"""The timeline's reads are case reads (ADR-084 Amendment 2, ADR-052 §8).

The analytics routes carry their case in the request body (`EventFilter.investigation_scope`)
rather than the path, and until this change they checked no case level at all: any signed-in
account could ask for any case's histogram, and only the per-event handling filter stood between
it and the counts. They now take the same gate as every case route, at Viewer, and on a branch
they widen the read to the visible parents' events on the links the branch holds.

What a mistake here would do, and the case that catches it:

- a timeline read of a case the account has no level on would reveal its event counts
  (`test_a_case_the_account_cannot_see_answers_not_found_and_reads_nothing`);
- a branch's timeline would stay empty, because its events live under the original case
  (`test_a_branch_reads_its_parents_events_on_the_links_it_holds`);
- a request body could name another case's events into a read through `inherited`
  (`test_an_inherited_sent_by_the_caller_is_discarded`).

The adapter's own handling of `inherited` is the conformance suite's to prove.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_analytics,
    get_audit,
    get_investigations,
    get_principal,
    get_working_set,
)

from schemas.analytics import FirstSeenResult, Histogram, HistogramBucketing
from schemas.domain import Principal

from .test_link_events import _Cases
from .working_set.test_visible_link import edge, node

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")

FILTER = {"investigation_scope": "branch-1"}
BODIES: dict[str, dict[str, Any]] = {
    "/v1/analytics/histogram": {"filter": FILTER, "interval_seconds": 3600},
    "/v1/analytics/cross-filter": {
        "filter": FILTER,
        "dimensions": [{"name": "t", "bucketing": "fixed_interval", "interval_seconds": 3600}],
    },
    "/v1/analytics/first-seen": {"filter": FILTER},
    "/v1/analytics/geobins": {"filter": FILTER, "precision": 4},
    "/v1/analytics/sightings": {"filter": FILTER},
}


class _Analytics:
    def __init__(self) -> None:
        self.filters: list[Any] = []

    async def histogram(self, req: Any, principal: Principal) -> Histogram:
        self.filters.append(req.filter)
        return Histogram(bucketing=HistogramBucketing.FIXED_INTERVAL, buckets=[], total=0)

    async def cross_filter(self, req: Any, principal: Principal) -> dict[str, Histogram]:
        self.filters.append(req.filter)
        return {}

    async def first_seen(self, req: Any, principal: Principal) -> FirstSeenResult:
        self.filters.append(req.filter)
        return FirstSeenResult()

    async def geo_bins(self, req: Any, principal: Principal) -> list[Any]:
        self.filters.append(req.filter)
        return []

    async def list_sightings(self, req: Any, principal: Principal) -> list[Any]:
        self.filters.append(req.filter)
        return []


class _WorkingSet:
    async def current_membership(self, investigation_id: str) -> tuple[list[Any], list[Any]]:
        if investigation_id == "branch-1":
            return [node("a"), node("b")], [edge("e1", "a", "b"), edge("e2", "b", "a")]
        return [], []


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


@pytest.fixture
def client() -> Any:
    analytics = _Analytics()
    audit = _Audit()
    cases = _Cases({"inv-1", "branch-1"})
    app.dependency_overrides[get_principal] = lambda: ANALYST
    app.dependency_overrides[get_analytics] = lambda: analytics
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_investigations] = lambda: cases
    app.dependency_overrides[get_working_set] = lambda: _WorkingSet()
    test_client = TestClient(app)
    test_client.analytics = analytics  # type: ignore[attr-defined]
    test_client.audit = audit  # type: ignore[attr-defined]
    test_client.cases = cases  # type: ignore[attr-defined]
    yield test_client
    app.dependency_overrides.clear()


@pytest.mark.parametrize("route", sorted(BODIES))
def test_a_case_the_account_cannot_see_answers_not_found_and_reads_nothing(
    client: Any, route: str
) -> None:
    body = {**BODIES[route], "filter": {"investigation_scope": "another-units-case"}}
    response = client.post(route, json=body)
    assert response.status_code == 404
    assert client.analytics.filters == []
    assert any(r["action"] == "access_denied" for r in client.audit.records)


@pytest.mark.parametrize("route", sorted(BODIES))
def test_a_branch_reads_its_parents_events_on_the_links_it_holds(client: Any, route: str) -> None:
    response = client.post(route, json=BODIES[route])
    assert response.status_code == 200, response.text
    (sent,) = client.analytics.filters
    assert sent.investigation_scope == "branch-1"
    assert sent.inherited is not None
    assert sent.inherited.scopes == ["inv-1"]
    assert sorted(sent.inherited.edge_ids) == ["e1", "e2"]


def test_a_case_that_is_not_a_branch_reads_its_own_events_only(client: Any) -> None:
    body = {**BODIES["/v1/analytics/histogram"], "filter": {"investigation_scope": "inv-1"}}
    assert client.post("/v1/analytics/histogram", json=body).status_code == 200
    (sent,) = client.analytics.filters
    assert sent.inherited is None


def test_a_branch_whose_parent_the_account_cannot_see_reads_its_own_events_only(
    client: Any,
) -> None:
    client.cases.visible = {"branch-1"}
    assert (
        client.post("/v1/analytics/histogram", json=BODIES["/v1/analytics/histogram"]).status_code
        == 200
    )
    (sent,) = client.analytics.filters
    assert sent.inherited is None


def test_an_inherited_sent_by_the_caller_is_discarded(client: Any) -> None:
    body = {
        **BODIES["/v1/analytics/histogram"],
        "filter": {
            "investigation_scope": "inv-1",
            "inherited": {"scopes": ["another-units-case"], "edge_ids": ["e1"]},
        },
    }
    assert client.post("/v1/analytics/histogram", json=body).status_code == 200
    (sent,) = client.analytics.filters
    assert sent.inherited is None
