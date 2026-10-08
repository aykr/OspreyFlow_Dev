"""The Explore panel's routes (`06_DECISIONS.md` ADR-100): what the case's data holds, and its most
connected nodes, read under the case.

That every count and degree is the principal's own is proven where it is computed, in the store
(the conformance suite's ADR-100 cases). What these prove is the route's half of it: the store is
asked with the principal the real `get_principal` builds for this case, carrying exactly the case's
datasets (rule 4, and the gap `CLAUDE.md` rule 12 names: a stand-in principal would prove the
route's logic but not the scope its real caller depends on). So `get_principal` is not replaced
here; only the token resolver, the case's datasets and the graph stand in.

What a mistake would do, and the case that catches it:

- a route asking the store with an unscoped principal would count and rank every dataset
  (`test_the_counts_are_asked_with_the_cases_datasets`,
  `test_the_ranking_is_asked_with_the_cases_datasets_and_what_was_asked_for`);
- a case that reads no dataset counting everything (`test_a_case_reading_no_dataset_asks_for_none`);
- a ranking page with no bound, or one past the store's own (`test_the_page_is_bounded`);
- a ranking that loses its total, so a "top 10" no longer says of how many
  (`test_the_ranking_keeps_its_total_and_offset`);
- an answer without a principal (`test_neither_route_answers_without_a_principal`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import app, get_audit, get_graph, get_investigations
from services.api.datasets import Dataset, InMemoryDatasetStore

from schemas.domain import Principal
from schemas.explore import RankedNode, RankedNodes, TypeCounts
from tests.services.api.any_case import AnyCase
from tests.services.api.test_search_route import _FakeAudit, _node

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


class _Resolver:
    def resolve(self, token: str) -> Principal:
        return ANALYST


class _FakeGraph:
    def __init__(self) -> None:
        self.counts: list[Principal] = []
        self.ranked: list[tuple[Principal, str | None, int, int]] = []

    async def type_counts(self, principal: Principal) -> TypeCounts:
        self.counts.append(principal)
        return TypeCounts(nodes={"Person": 5}, edges={"ASSOCIATE_OF": 4})

    async def most_connected(
        self,
        principal: Principal,
        *,
        entity_type: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> RankedNodes:
        self.ranked.append((principal, entity_type, limit, offset))
        return RankedNodes(nodes=[RankedNode(node=_node("hub"), degree=7)], total=42, offset=offset)


@pytest.fixture
def client() -> Any:
    store = InMemoryDatasetStore()
    store.add(
        Dataset(
            id="enron",
            name="Enron",
            owning_unit="unit-1",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by="seed",
        )
    )
    store.cases["case-e"] = ["enron"]
    saved = {k: getattr(app.state, k, None) for k in ("principal_resolver", "datasets")}
    app.state.principal_resolver = _Resolver()
    app.state.datasets = store
    graph = _FakeGraph()
    audit = _FakeAudit()
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_investigations] = AnyCase
    app.dependency_overrides[get_audit] = lambda: audit
    yield TestClient(app, headers={"Authorization": "Bearer token"}), graph, audit
    app.dependency_overrides.clear()
    for key, value in saved.items():
        setattr(app.state, key, value)


def test_the_counts_are_asked_with_the_cases_datasets(client) -> None:  # type: ignore[no-untyped-def]
    http, graph, audit = client
    response = http.get("/v1/investigations/case-e/explore/counts")
    assert response.status_code == 200
    assert response.json() == {"nodes": {"Person": 5}, "edges": {"ASSOCIATE_OF": 4}}
    assert [p.datasets for p in graph.counts] == [["enron"]]
    assert audit.records[-1]["action"] == "explore_counts"


def test_the_ranking_is_asked_with_the_cases_datasets_and_what_was_asked_for(client) -> None:  # type: ignore[no-untyped-def]
    http, graph, audit = client
    response = http.get(
        "/v1/investigations/case-e/explore/most-connected",
        params={"entity_type": "Person", "limit": 5, "offset": 10},
    )
    assert response.status_code == 200
    ((principal, entity_type, limit, offset),) = graph.ranked
    assert principal.datasets == ["enron"]
    assert (entity_type, limit, offset) == ("Person", 5, 10)
    assert audit.records[-1]["action"] == "explore_most_connected"
    assert audit.records[-1]["result_cardinality"] == 1


def test_the_ranking_defaults_to_the_top_ten_of_every_type(client) -> None:  # type: ignore[no-untyped-def]
    http, graph, _ = client
    http.get("/v1/investigations/case-e/explore/most-connected")
    assert [(t, lim, off) for _, t, lim, off in graph.ranked] == [(None, 10, 0)]


def test_the_ranking_keeps_its_total_and_offset(client) -> None:  # type: ignore[no-untyped-def]
    http, _, _ = client
    body = http.get(
        "/v1/investigations/case-e/explore/most-connected", params={"offset": 10}
    ).json()
    assert body["total"] == 42 and body["offset"] == 10
    assert body["nodes"][0]["degree"] == 7 and body["nodes"][0]["node"]["id"] == "hub"


def test_a_case_reading_no_dataset_asks_for_none(client) -> None:  # type: ignore[no-untyped-def]
    http, graph, _ = client
    http.get("/v1/investigations/case-unknown/explore/counts")
    http.get("/v1/investigations/case-unknown/explore/most-connected")
    assert [p.datasets for p in graph.counts] == [[]]
    assert [p.datasets for p, *_ in graph.ranked] == [[]]


def test_the_page_is_bounded(client) -> None:  # type: ignore[no-untyped-def]
    http, graph, _ = client
    path = "/v1/investigations/case-e/explore/most-connected"
    for bad in ({"limit": 0}, {"limit": 51}, {"offset": -1}):
        assert http.get(path, params=bad).status_code == 422, bad
    assert graph.ranked == []
    assert http.get(path, params={"limit": 50}).status_code == 200


def test_neither_route_answers_without_a_principal(client) -> None:  # type: ignore[no-untyped-def]
    _, graph, _ = client
    anonymous = TestClient(app)
    for path in ("counts", "most-connected"):
        response = anonymous.get(f"/v1/investigations/case-e/explore/{path}")
        assert response.status_code in (401, 403)
    assert graph.counts == [] and graph.ranked == []
