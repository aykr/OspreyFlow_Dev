"""`POST /v1/suggest` route wiring (ADR-059): the Glass search box as the analyst types.

`GraphPort.suggest_nodes`'s own access filtering and its `more` flag are proven where the query is
built and run (`tests/adapters/graph_arcadedb/test_suggest_nodes.py` and the conformance suite).
This file proves the route refuses a prefix too short to be worth a scan, forwards what it is
given, passes `more` through untouched, and audits.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from ports.graph import NodeSuggestions
from schemas.domain import Principal
from services.api.app import app, get_audit, get_graph, get_principal

from tests.services.api.test_search_route import PRINCIPAL, _FakeAudit, _node


class _FakeGraph:
    def __init__(self, more: bool = False) -> None:
        self.calls: list[tuple[str, Principal, int]] = []
        self.more = more

    async def suggest_nodes(
        self, prefix: str, principal: Principal, *, limit: int = 10
    ) -> NodeSuggestions:
        self.calls.append((prefix, principal, limit))
        return NodeSuggestions(nodes=[_node("hit-1"), _node("hit-2")], more=self.more)


def _client(graph: _FakeGraph) -> tuple[TestClient, _FakeAudit]:
    audit = _FakeAudit()
    app.dependency_overrides[get_principal] = lambda: PRINCIPAL
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_audit] = lambda: audit
    return TestClient(app), audit


@pytest.fixture(autouse=True)
def _clear() -> None:
    yield
    app.dependency_overrides.clear()


def test_suggest_forwards_the_prefix_the_principal_and_the_default_limit() -> None:
    graph = _FakeGraph()
    client, audit = _client(graph)
    response = client.post("/v1/suggest", json={"query": "C13"})
    assert response.status_code == 200
    assert [n["id"] for n in response.json()["nodes"]] == ["hit-1", "hit-2"]
    assert response.json()["more"] is False
    assert graph.calls == [("C13", PRINCIPAL, 10)]
    assert audit.records[-1]["action"] == "suggest"
    assert audit.records[-1]["result_cardinality"] == 2


def test_suggest_says_when_more_matched() -> None:
    """Rule 2: the Glass must be able to say 'more not shown'; the route never drops the flag."""
    client, _ = _client(_FakeGraph(more=True))
    assert client.post("/v1/suggest", json={"query": "C13"}).json()["more"] is True


def test_a_prefix_shorter_than_three_characters_is_refused_and_asks_the_graph_nothing() -> (
    None
):
    graph = _FakeGraph()
    client, audit = _client(graph)
    for short in ("", "C", "C1"):
        assert client.post("/v1/suggest", json={"query": short}).status_code == 422
    assert graph.calls == [] and audit.records == []


def test_the_limit_is_bounded() -> None:
    graph = _FakeGraph()
    client, _ = _client(graph)
    for bad in (0, 26):
        assert (
            client.post("/v1/suggest", json={"query": "C13", "limit": bad}).status_code
            == 422
        )
    assert (
        client.post("/v1/suggest", json={"query": "C13", "limit": 25}).status_code
        == 200
    )
    assert graph.calls[-1][2] == 25


def test_the_route_needs_a_principal() -> None:
    """Rule 4: every read path gets an access test. With no principal override the route must
    not answer; the filtering itself is the adapter's and is proven there."""
    graph = _FakeGraph()
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_audit] = lambda: _FakeAudit()
    response = TestClient(app).post("/v1/suggest", json={"query": "C13"})
    assert response.status_code in (401, 403)
    assert graph.calls == []
