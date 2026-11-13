"""`POST /v1/investigations/{id}/search` and `…/suggest` with the search service (ADR-149, ADR-059
Amendment 1): the routes pass the reader's own access filter, the case's datasets, its threshold
and the pending nodes to the service; refuse a caller's mistake with 422 and a defect with a bare
500; and audit as today with what was asked and who answered. The service is
`test_search_service.py`; the live leak test is
`tests/services/search_index/test_search_leak_live.py`.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
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
    get_search_pending,
    get_search_working_set,
)
from services.api.search_access import index_access_filter
from services.api.search_service import SearchIndexSetup
from services.search_index.pending import PendingIds

from ontology.handling import load_handling_scheme
from ontology.loader import load_default_ontology
from schemas.domain import SAME_AS, Edge, Node, Principal
from tests.services.api.any_case import AnyCase
from tests.services.api.test_search_route import _FakeAudit, _node

READER = Principal(
    id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"], datasets=["ds-1"]
)
SCHEME = load_handling_scheme(
    Path(__file__).parents[4] / "OspreyFlow_Core/packages/ontology/handling/uk-le.yaml"
)
SCHEMA = load_default_ontology()


def _reply(hits: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "hits": {"hits": hits or []},
        "aggregations": {
            "by_type": {"types": {"buckets": []}},
            "mentions": {"doc_count": 0},
            "datasets": {"buckets": []},
            "earliest": {"value": None},
            "latest": {"value": None},
        },
    }


class _Searcher:
    def __init__(self, reply: dict[str, Any] | None = None) -> None:
        self.reply = reply or _reply()
        self.bodies: list[dict[str, Any]] = []

    async def __call__(self, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        self.bodies.append(body)
        return self.reply


class _Graph:
    def __init__(self, nodes: Sequence[Node] = (), links: Sequence[Edge] = ()) -> None:
        self.nodes = {n.id: n for n in nodes}
        self.links = list(links)

    async def get_nodes(self, node_ids: Sequence[str], principal: Principal) -> list[Node]:
        return [self.nodes[i] for i in node_ids if i in self.nodes]

    async def edges_among(
        self, node_ids: Sequence[str], principal: Principal, *, edge_types: Sequence[str]
    ) -> list[Edge]:
        ids = set(node_ids)
        return [e for e in self.links if e.source in ids and e.target in ids]

    async def search_nodes(
        self, query: str, principal: Principal, *, limit: int = 20
    ) -> list[Node]:
        return [_node("hit-1")] if query == "AB123456C" else []

    async def suggest_nodes(self, prefix: str, principal: Principal, **kwargs: Any) -> Any:
        from ports.graph import NodeSuggestions

        return NodeSuggestions(nodes=[], more=False)


class _WorkingSet:
    def __init__(self, tau: float) -> None:
        self.tau = tau
        self.asked: list[str] = []

    async def get_resolution_threshold(self, case_id: str) -> float:
        self.asked.append(case_id)
        return self.tau


@pytest.fixture
def client() -> Iterator[TestClient]:
    audit = _FakeAudit()
    searcher = _Searcher()
    app.dependency_overrides[get_principal] = lambda: READER
    app.dependency_overrides[get_graph] = lambda: _Graph()
    app.dependency_overrides[get_investigations] = AnyCase
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_search_pending] = lambda: PendingIds(
        ids=frozenset(), complete=True
    )
    app.dependency_overrides[get_search_index] = lambda: SearchIndexSetup(
        searcher=searcher, schema=SCHEMA, scheme=SCHEME
    )
    test_client = TestClient(app, raise_server_exceptions=False)
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


def test_another_cases_reader_on_the_same_unit_asks_with_their_own_datasets(
    client: TestClient,
) -> None:
    """Rule 4: a reader of another case, in the same unit, reading another dataset, is asked with
    their own case's datasets, never the first reader's."""
    other = READER.model_copy(update={"id": "analyst-2", "datasets": ["ds-2"]})
    app.dependency_overrides[get_principal] = lambda: other
    client.post("/v1/investigations/inv-2/search", json={"query": "Smyth"})
    (body,) = client.searcher.bodies  # type: ignore[attr-defined]
    access = body["query"]["bool"]["filter"][0]
    assert access == index_access_filter(SCHEME, other)
    assert access != index_access_filter(SCHEME, READER)
    assert "ds-1" not in repr(access)


def test_the_pending_ids_reach_only_the_querys_must_not(client: TestClient) -> None:
    """Rule 4 (rules' ask): the outbox's ids are read with no principal, so they may only ever
    exclude. They appear in the query's `must_not` and nowhere else, in the body or the reply."""
    app.dependency_overrides[get_search_pending] = lambda: PendingIds(
        ids=frozenset({"pending-node-7"}), complete=True
    )
    for route in ("search", "suggest"):
        response = client.post(
            f"/v1/investigations/inv-1/{route}", json={"query": "Smyth", "ignore_case": True}
        )
        body = client.searcher.bodies[-1]  # type: ignore[attr-defined]
        assert body["query"]["bool"]["must_not"] == [{"terms": {"node_id": ["pending-node-7"]}}]
        rest = {k: v for k, v in body["query"]["bool"].items() if k != "must_not"}
        assert "pending-node-7" not in repr(rest) + repr(
            {k: v for k, v in body.items() if k != "query"}
        )
        assert "pending-node-7" not in response.text
    assert response.json()["source"] == "index"


def test_a_pending_set_not_known_to_be_whole_answers_from_the_graph(client: TestClient) -> None:
    app.dependency_overrides[get_search_pending] = lambda: PendingIds(
        ids=frozenset(), complete=False
    )
    response = client.post("/v1/investigations/inv-1/search", json={"query": "AB123456C"})
    assert client.searcher.bodies == []  # type: ignore[attr-defined]
    assert "catching up" in response.json()["limited_reason"]


def test_the_cases_threshold_merges_through_the_working_set(client: TestClient) -> None:
    a, b = _node("a"), _node("b")
    link = Edge(
        id="s1",
        type=SAME_AS,
        source="a",
        target="b",
        properties={"score": 0.97},
        provenance=a.provenance,
        handling=a.handling,
        audit=a.audit,
    )
    working_set = _WorkingSet(0.95)
    app.dependency_overrides[get_graph] = lambda: _Graph([a, b], [link])
    app.dependency_overrides[get_search_working_set] = lambda: working_set
    hits = [
        {"_score": 3000, "_source": {"node_id": "a", "kind": "node"}},
        {"_score": 3000, "_source": {"node_id": "b", "kind": "node"}},
    ]
    app.dependency_overrides[get_search_index] = lambda: SearchIndexSetup(
        searcher=_Searcher(_reply(hits)), schema=SCHEMA, scheme=SCHEME
    )
    response = client.post("/v1/investigations/inv-1/search", json={"query": "AB123456C"})
    assert [r["node_ids"] for r in response.json()["results"]] == [["a", "b"]]
    assert working_set.asked == ["inv-1"]
    # The audit counts the records sent (two), as today, not the one merged result.
    assert client.audit.records[-1]["result_cardinality"] == 2  # type: ignore[attr-defined]


def test_the_search_is_audited_with_what_was_asked_and_who_answered(client: TestClient) -> None:
    client.post(
        "/v1/investigations/inv-1/search",
        json={
            "query": "Smyth",
            "group": "Person",
            "page": 2,
            "page_size": 10,
            "filters": {"date_from": "2026-01-01"},
        },
    )
    record = client.audit.records[-1]  # type: ignore[attr-defined]
    assert record["action"] == "search"
    assert record["resolved_query"] == {
        "query": "Smyth",
        "group": "Person",
        "filters": {"datasets": None, "date_from": "2026-01-01", "date_to": None},
        "page": 2,
        "page_size": 10,
        "source": "index",
    }
    assert record["result_cardinality"] == 0  # the records sent, as today


@pytest.mark.parametrize(
    "body",
    [
        {"query": "x", "filters": {"datasets": ["ds-elsewhere"]}},
        {"query": "x" * 201},
        {"query": "x", "page": 60, "page_size": 20},
        {"query": "x", "filters": {"date_from": "13/11/2026"}},
        {"query": "x", "filters": {"date_from": "2026-13-45"}},
        {"query": "x", "filters": {"date_from": "2026-02-01", "date_to": "2026-01-01"}},
    ],
)
def test_a_callers_mistake_is_refused_with_422(client: TestClient, body: dict[str, Any]) -> None:
    response = client.post("/v1/investigations/inv-1/search", json=body)
    assert response.status_code == 422, response.text
    assert client.searcher.bodies == []  # type: ignore[attr-defined]


def test_a_score_outside_the_bands_is_a_bare_500_naming_no_score(client: TestClient) -> None:
    hits = [{"_score": 2950.0, "_source": {"node_id": "a", "kind": "node"}}]
    app.dependency_overrides[get_search_index] = lambda: SearchIndexSetup(
        searcher=_Searcher(_reply(hits)), schema=SCHEMA, scheme=SCHEME
    )
    response = client.post("/v1/investigations/inv-1/search", json={"query": "x"})
    assert response.status_code == 500
    assert "2950" not in response.text


def test_with_no_index_configured_the_route_falls_back_and_says_so(client: TestClient) -> None:
    app.dependency_overrides[get_search_index] = lambda: None
    response = client.post("/v1/investigations/inv-1/search", json={"query": "AB123456C"})
    assert response.status_code == 200
    payload = response.json()
    assert (payload["source"], payload["limited"]) == ("fallback", True)
    assert "no search index" in payload["limited_reason"]
    assert [n["id"] for n in payload["nodes"]] == ["hit-1"]


# --- suggestions ----------------------------------------------------------------------------------


def test_a_suggestion_asks_the_index_with_the_readers_own_access_filter(client: TestClient) -> None:
    response = client.post(
        "/v1/investigations/inv-1/suggest", json={"query": "Smy", "ignore_case": True}
    )
    assert response.status_code == 200, response.text
    assert (response.json()["source"], response.json()["limited"]) == ("index", False)
    (body,) = client.searcher.bodies  # type: ignore[attr-defined]
    assert body["query"]["bool"]["filter"][0] == index_access_filter(SCHEME, READER)
    assert {"term": {"kind": "node"}} in body["query"]["bool"]["filter"]
    record = client.audit.records[-1]  # type: ignore[attr-defined]
    assert record["resolved_query"]["source"] == "index"


@pytest.mark.parametrize(
    "body",
    [
        {"query": "k" * 51},
        {"query": "Smy", "types": ["Nonsense"]},
    ],
)
def test_a_suggestion_the_index_cannot_ask_is_refused_with_422(
    client: TestClient, body: dict[str, Any]
) -> None:
    response = client.post("/v1/investigations/inv-1/suggest", json=body)
    assert response.status_code == 422, response.text
    assert client.searcher.bodies == []  # type: ignore[attr-defined]


def test_a_suggestion_with_no_index_says_it_is_limited(client: TestClient) -> None:
    app.dependency_overrides[get_search_index] = lambda: None
    response = client.post("/v1/investigations/inv-1/suggest", json={"query": "Smy"})
    assert (response.json()["source"], response.json()["limited"]) == ("graph", True)
