"""`POST /v1/paths` route wiring — `spec/03_CONDUIT_MIDDLEWARE.md` §3.3, `spec/06_DECISIONS.md`
ADR-033. `GraphPort.paths`'s own access-filtering, existence-leak and hydration behaviour is
proven by the conformance suite (`tests/conformance/graph_port/test_suite.py`); this file only
proves the route calls it with the right arguments, passes the result straight through with no
post-processing, and audits — the same shape `test_search_route.py` already establishes for the
identical class of bare, non-investigation-scoped query route.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from services.api.app import app, get_audit, get_graph, get_principal

from schemas.domain import (
    AuditStub,
    Edge,
    Node,
    Path,
    PathRequest,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


def _node(node_id: str, node_type: str = "Person") -> Node:
    return Node(
        id=node_id,
        type=node_type,
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


def _edge(edge_id: str, source: str, target: str) -> Edge:
    return Edge(
        id=edge_id,
        type="USES",
        source=source,
        target=target,
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
    def __init__(self, *, found: list[Path]) -> None:
        self._found = found
        self.calls: list[tuple[PathRequest, Principal]] = []

    async def paths(self, req: PathRequest, principal: Principal) -> list[Path]:
        self.calls.append((req, principal))
        return self._found


class _FakeAudit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


@pytest.fixture
def client() -> TestClient:
    found = [
        Path(
            nodes=[_node("a"), _node("b", "Endpoint")],
            edges=[_edge("e1", "a", "b")],
            length=1,
        )
    ]
    graph = _FakeGraph(found=found)
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


def test_paths_route_passes_the_request_through_and_returns_the_hydrated_result(
    client: TestClient,
) -> None:
    response = client.post(
        "/v1/paths", json={"source": "a", "target": "b", "max_hops": 3, "k": 1}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert [n["id"] for n in body[0]["nodes"]] == ["a", "b"]
    assert [n["type"] for n in body[0]["nodes"]] == ["Person", "Endpoint"]
    assert body[0]["edges"][0]["id"] == "e1"

    (req, principal) = client.graph.calls[0]  # type: ignore[attr-defined]
    assert (req.source, req.target, req.max_hops, req.k) == ("a", "b", 3, 1)
    assert principal == PRINCIPAL
    assert client.audit.records[-1]["action"] == "paths"  # type: ignore[attr-defined]
    assert client.audit.records[-1]["result_cardinality"] == 1  # type: ignore[attr-defined]


def test_paths_route_rejects_a_max_hops_above_the_schema_ceiling(client: TestClient) -> None:
    response = client.post(
        "/v1/paths", json={"source": "a", "target": "b", "max_hops": 20, "k": 1}
    )

    assert response.status_code == 422
    assert client.graph.calls == []  # type: ignore[attr-defined]


def test_paths_route_with_no_match_returns_an_empty_list_not_an_error(client: TestClient) -> None:
    client.graph._found = []  # type: ignore[attr-defined]
    response = client.post(
        "/v1/paths", json={"source": "a", "target": "z", "max_hops": 3, "k": 1}
    )

    assert response.status_code == 200
    assert response.json() == []
