"""`POST /v1/search` route wiring — `docs/03_CONDUIT_MIDDLEWARE.md` §3.3,
v1 scope (`services/api/search.py`'s module docstring: graph-only, exact
identifier match, document/index federation deferred to when OpenSearch is
wired). `GraphPort.search_nodes`'s own access-filtering and existence-leak
behaviour is proven by the conformance suite
(`tests/conformance/graph_port/test_suite.py`); this file only proves the
route calls it with the right arguments and audits.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from services.api.app import app, get_audit, get_graph, get_principal

from schemas.domain import AuditStub, Node, Principal, Provenance, ProvenanceState, SourceRef

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


def _node(node_id: str) -> Node:
    return Node(
        id=node_id,
        type="Person",
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        handling={  # type: ignore[arg-type]
            "classification": "OFFICIAL",
            "handling_code": "P",
            "originator": "unit-1",
            "owning_unit": "unit-1",
        },
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="loader-1"),
    )


class _FakeGraph:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Principal, int]] = []

    async def search_nodes(
        self, query: str, principal: Principal, *, limit: int = 20
    ) -> list[Node]:
        self.calls.append((query, principal, limit))
        return [_node("hit-1")] if query == "AB123456C" else []


class _FakeAudit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


@pytest.fixture
def client() -> TestClient:
    graph = _FakeGraph()
    audit = _FakeAudit()
    app.dependency_overrides[get_principal] = lambda: PRINCIPAL
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_audit] = lambda: audit

    test_client = TestClient(app)
    test_client.graph = graph  # type: ignore[attr-defined]
    test_client.audit = audit  # type: ignore[attr-defined]
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def test_search_returns_hits_from_the_graph_port(client: TestClient) -> None:
    response = client.post("/v1/search", json={"query": "AB123456C"})

    assert response.status_code == 200
    assert [n["id"] for n in response.json()["nodes"]] == ["hit-1"]
    assert client.graph.calls == [("AB123456C", PRINCIPAL, 20)]  # type: ignore[attr-defined]
    assert client.audit.records[-1]["action"] == "search"  # type: ignore[attr-defined]


def test_search_with_no_match_returns_an_empty_list_not_an_error(client: TestClient) -> None:
    response = client.post("/v1/search", json={"query": "no-such-value"})

    assert response.status_code == 200
    assert response.json()["nodes"] == []
