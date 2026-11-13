"""`POST /v1/investigations/{id}/search` with the search service (ADR-149, reserved): the route
passes the reader's own access filter, the case's datasets and its threshold to `search_page`,
refuses a caller's mistake with 422, and audits as today with what was asked. The service itself
is `test_search_service.py`; the live leak test is
`tests/services/search_index/test_search_leak_live.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_graph,
    get_investigations,
    get_principal,
    get_search_index,
)
from services.api.search_access import index_access_filter
from services.api.search_service import SearchIndexSetup

from ontology.handling import load_handling_scheme
from schemas.domain import Principal
from tests.services.api.any_case import AnyCase
from tests.services.api.test_search_route import _FakeAudit, _FakeGraph

READER = Principal(
    id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"], datasets=["ds-1"]
)
SCHEME = load_handling_scheme(
    Path(__file__).parents[4] / "OspreyFlow_Core/packages/ontology/handling/uk-le.yaml"
)
EMPTY = {
    "hits": {"hits": []},
    "aggregations": {
        "by_type": {"types": {"buckets": []}},
        "mentions": {"doc_count": 0},
        "datasets": {"buckets": []},
        "earliest": {"value": None},
        "latest": {"value": None},
    },
}


class _Searcher:
    def __init__(self) -> None:
        self.bodies: list[dict[str, Any]] = []

    async def __call__(self, body: dict[str, Any]) -> dict[str, Any]:
        self.bodies.append(body)
        return EMPTY


@pytest.fixture
def client() -> Iterator[TestClient]:
    graph = _FakeGraph()
    audit = _FakeAudit()
    searcher = _Searcher()
    app.dependency_overrides[get_principal] = lambda: READER
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_investigations] = AnyCase
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_search_index] = lambda: SearchIndexSetup(
        searcher=searcher, types=["Person"], scheme=SCHEME
    )
    test_client = TestClient(app)
    test_client.audit = audit  # type: ignore[attr-defined]
    test_client.searcher = searcher  # type: ignore[attr-defined]
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def test_the_index_is_asked_with_the_readers_own_access_filter(client: TestClient) -> None:
    response = client.post("/v1/investigations/inv-1/search", json={"query": "Smyth"})
    assert response.status_code == 200, response.text
    assert response.json()["source"] == "index"
    (body,) = client.searcher.bodies  # type: ignore[attr-defined]
    assert body["query"]["bool"]["filter"][0] == index_access_filter(SCHEME, READER)


def test_the_search_is_audited_with_what_was_asked_and_where_it_was_answered(
    client: TestClient,
) -> None:
    client.post(
        "/v1/investigations/inv-1/search",
        json={"query": "Smyth", "group": "Person", "page": 2, "page_size": 10},
    )
    record = client.audit.records[-1]  # type: ignore[attr-defined]
    assert record["action"] == "search"
    assert record["resolved_query"] == {
        "query": "Smyth",
        "group": "Person",
        "filters": {"datasets": None, "date_from": None, "date_to": None},
        "page": 2,
        "page_size": 10,
        "source": "index",
    }


@pytest.mark.parametrize(
    "body",
    [
        {"query": "x", "filters": {"datasets": ["ds-elsewhere"]}},
        {"query": "x" * 201},
        {"query": "x", "page": 60, "page_size": 20},
        {"query": "x", "filters": {"date_from": "13/11/2026"}},
    ],
)
def test_a_callers_mistake_is_refused_with_422(client: TestClient, body: dict[str, Any]) -> None:
    response = client.post("/v1/investigations/inv-1/search", json=body)
    assert response.status_code == 422, response.text
    assert client.searcher.bodies == []  # type: ignore[attr-defined]


def test_with_no_index_configured_the_route_falls_back_and_says_so(client: TestClient) -> None:
    app.dependency_overrides[get_search_index] = lambda: None
    response = client.post("/v1/investigations/inv-1/search", json={"query": "AB123456C"})
    assert response.status_code == 200
    payload = response.json()
    assert (payload["source"], payload["limited"]) == ("fallback", True)
    assert [n["id"] for n in payload["nodes"]] == ["hit-1"]
