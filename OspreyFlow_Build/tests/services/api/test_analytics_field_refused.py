"""A field name that is not one is refused in words over the wire (spec 08's A7).

The adapters refuse a field name that is not a plain identifier before building any SQL, since a
field name is interpolated where values are parameterised (`analytics_port` conformance:
`test_a_field_name_that_is_not_one_is_refused_in_the_ports_words`). Until this change the refusal
was a bare `ValueError` no route caught, so a caller got a 500 with no words; A7's over-the-wire
case accepted that, since it asked only for a status of 400 or more.

Here the routes run against the real DuckDB adapter, seeded with one event, so the refusal is the
adapter's own and not a fake's. What a mistake would do, and the case that catches it:

- a hostile name answered as a 500, or as anything but the port's words
  (`test_a_hostile_field_name_is_refused_with_the_rule_not_the_name`);
- the refusal echoing what was sent (the same case: the name and its SQL are not in the answer);
- the guard passing a name through, so the event table is touched (the same case reads it after).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from adapters.analytics_duckdb.testing import duckdb_adapter
from ontology.handling import load_uk_le_scheme
from ports.analytics import FIELD_NAME_RULE
from services.api.app import (
    app,
    get_analytics,
    get_audit,
    get_investigations,
    get_principal,
    get_working_set,
)

from schemas.analytics import EventRecord
from schemas.domain import Handling

from .test_analytics_case_routes import ANALYST, _Audit, _WorkingSet
from .test_link_events import _Cases

HOSTILE = "item_type'); DROP TABLE events; --"
CASE = {"investigation_scope": "inv-1"}
HOSTILE_FILTER = {**CASE, "value_filters": {HOSTILE: ["x"]}}
CATEGORICAL = [{"name": "c", "field": "item_type", "bucketing": "categorical"}]

#: Each analytics route a caller names a field through, with the field where it sends it.
BODIES: dict[str, tuple[str, dict[str, Any]]] = {
    "histogram value_filters": (
        "/v1/analytics/histogram",
        {"filter": HOSTILE_FILTER, "interval_seconds": 3600},
    ),
    "histogram field": (
        "/v1/analytics/histogram",
        {"filter": CASE, "bucketing": "categorical", "field": HOSTILE},
    ),
    "cross-filter value_filters": (
        "/v1/analytics/cross-filter",
        {"filter": HOSTILE_FILTER, "dimensions": CATEGORICAL},
    ),
    "cross-filter dimension field": (
        "/v1/analytics/cross-filter",
        {"filter": CASE, "dimensions": [{**CATEGORICAL[0], "field": HOSTILE}]},
    ),
    "first-seen value_filters": ("/v1/analytics/first-seen", {"filter": HOSTILE_FILTER}),
    "geobins value_filters": ("/v1/analytics/geobins", {"filter": HOSTILE_FILTER, "precision": 4}),
    "sightings value_filters": ("/v1/analytics/sightings", {"filter": HOSTILE_FILTER}),
}


def _seeded() -> EventRecord:
    return EventRecord(
        event_id="01JEVENT000000000000000001",
        edge_id="e1",
        edge_type="COMMUNICATED_WITH",
        source_id="a",
        target_id="b",
        occurred_at=datetime(2026, 4, 2, tzinfo=UTC),
        lat=51.5,
        lon=-0.12,
        properties={"item_type": "bicycle"},
        investigation_scope="inv-1",
        handling=Handling(
            classification="OFFICIAL", handling_code="P", owning_unit="unit-1", originator="unit-1"
        ),
    )


@pytest.fixture
def overrides() -> Iterator[None]:
    app.dependency_overrides[get_principal] = lambda: ANALYST
    app.dependency_overrides[get_audit] = lambda: _Audit()
    app.dependency_overrides[get_investigations] = lambda: _Cases({"inv-1"})
    app.dependency_overrides[get_working_set] = lambda: _WorkingSet()
    yield
    app.dependency_overrides.clear()


async def _ask(route: str, body: dict[str, Any]) -> tuple[httpx.Response, httpx.Response]:
    async with duckdb_adapter([_seeded()], load_uk_le_scheme()) as analytics:
        app.dependency_overrides[get_analytics] = lambda: analytics
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            refused = await client.post(route, json=body)
            after = await client.post(
                "/v1/analytics/cross-filter", json={"filter": CASE, "dimensions": CATEGORICAL}
            )
    return refused, after


@pytest.mark.parametrize("case", sorted(BODIES))
def test_a_hostile_field_name_is_refused_with_the_rule_not_the_name(
    overrides: None, case: str
) -> None:
    route, body = BODIES[case]
    refused, after = asyncio.run(_ask(route, body))
    assert refused.status_code == 422, (refused.status_code, refused.text[:200])
    assert refused.json() == {"error": "field_name_refused", "detail": FIELD_NAME_RULE}
    assert "DROP" not in refused.text and "item_type'" not in refused.text
    assert after.status_code == 200, after.text
    assert after.json()["c"]["total"] == 1
