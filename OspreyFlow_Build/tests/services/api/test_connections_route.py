"""ADR-116 decision 6: `POST /v1/investigations/{id}/connections` — the fewest degrees connecting
two nodes and the routes at that degree, or the routes at a degree asked for.

The access filtering itself is the adapter's and is proven against the real store by the conformance
suite (`test_no_route_passes_through_a_hidden_node_or_link_and_the_fewest_degrees_do_not_move`).
The graph here is a small in-memory one that refuses as the store does: a route never passes
through a node the reader cannot see, and a hidden end has no routes (rule 15: the fake models the
refusals, not only the grants).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from services.api.app import app, get_audit, get_graph, get_investigations, get_principal

from schemas.domain import (
    AuditStub,
    Edge,
    Node,
    Path,
    Principal,
    Provenance,
    ProvenanceState,
    RoutesAtLength,
    SourceRef,
)
from tests.services.api.any_case import AnyCase

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
URL = "/v1/investigations/inv-1/connections"

_PROVENANCE = Provenance(
    state=ProvenanceState.ASSERTED,
    sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
    first_seen=datetime(2026, 1, 1, tzinfo=UTC),
)
_HANDLING = {"classification": "OFFICIAL", "handling_code": "P", "originator": "u",
             "owning_unit": "u"}  # fmt: skip
_AUDIT = AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="loader-1")


def _node(node_id: str) -> Node:
    return Node(id=node_id, type="Person", provenance=_PROVENANCE, handling=_HANDLING,  # type: ignore[arg-type]
                audit=_AUDIT)  # fmt: skip


def _edge(source: str, target: str) -> Edge:
    return Edge(id=f"{source}-{target}", type="ASSOCIATE_OF", source=source, target=target,
                provenance=_PROVENANCE, handling=_HANDLING, audit=_AUDIT)  # type: ignore[arg-type]  # fmt: skip


class _Graph:
    """a—b—c—d, a—h—d through `h`, which the reader cannot see, m1..m12 each between p and q, and a
    chain s0—s1—…—s7."""

    HIDDEN = frozenset({"h"})

    def __init__(self) -> None:
        pairs = [("a", "b"), ("b", "c"), ("c", "d"), ("a", "h"), ("h", "d")]
        pairs += [(end, f"m{i}") for i in range(12) for end in ("p", "q")]
        pairs += [(f"s{i}", f"s{i + 1}") for i in range(7)]  # s0 to s7: seven links
        self.edges = [_edge(s, t) for s, t in pairs]
        self.asked: list[tuple[str, str, int, int, list[str] | None]] = []

    async def paths_at_length(
        self, source: str, target: str, length: int, limit: int, principal: Principal,
        *, edge_types: list[str] | None = None,
    ) -> RoutesAtLength:  # fmt: skip
        assert principal == PRINCIPAL
        self.asked.append((source, target, length, limit, edge_types))
        found: list[Path] = []

        def walk(at: str, nodes: list[str], edges: list[Edge]) -> None:
            if len(edges) == length:
                if at == target:
                    found.append(Path(nodes=[_node(n) for n in nodes], edges=edges, length=length))
                return
            for edge in self.edges:
                if at not in (edge.source, edge.target):
                    continue
                other = edge.target if edge.source == at else edge.source
                if other in self.HIDDEN or other in nodes:
                    continue
                walk(other, [*nodes, other], [*edges, edge])

        if source not in self.HIDDEN:
            walk(source, [source], [])
        return RoutesAtLength(length=length, paths=found[:limit], more=len(found) > limit)


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


@pytest.fixture
def client() -> Iterator[TestClient]:
    graph, audit = _Graph(), _Audit()
    app.dependency_overrides[get_principal] = lambda: PRINCIPAL
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_investigations] = AnyCase
    app.dependency_overrides[get_audit] = lambda: audit
    test_client = TestClient(app)
    test_client.graph = graph  # type: ignore[attr-defined]
    test_client.audit = audit  # type: ignore[attr-defined]
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def _routes(body: dict[str, object]) -> list[list[str]]:
    return [[n["id"] for n in p["nodes"]] for p in body["paths"]]  # type: ignore[index, union-attr]


def test_with_no_degree_asked_the_fewest_degrees_and_their_routes_are_given(
    client: TestClient,
) -> None:
    """The route through the hidden `h` (two degrees) does not exist for this reader: three."""
    response = client.post(URL, json={"source": "a", "target": "d"})
    assert response.status_code == 200
    body = response.json()
    assert body["degree"] == 3 and _routes(body) == [["a", "b", "c", "d"]]
    assert body["more"] is False
    assert [length for _, _, length, _, _ in client.graph.asked] == [1, 2, 3]  # type: ignore[attr-defined]
    record = client.audit.records[-1]  # type: ignore[attr-defined]
    assert record["action"] == "connections" and record["result_cardinality"] == 1


def test_a_degree_asked_for_gives_the_routes_at_exactly_that_degree(client: TestClient) -> None:
    body = client.post(URL, json={"source": "a", "target": "d", "degree": 4}).json()
    assert body["degree"] == 4 and body["paths"] == [] and body["searched_to"] == 4
    assert [length for _, _, length, _, _ in client.graph.asked] == [4]  # type: ignore[attr-defined]


def test_more_routes_than_are_shown_is_said(client: TestClient) -> None:
    """Twelve routes p—m—q at two degrees: ten shown and `more` (rule 2)."""
    body = client.post(URL, json={"source": "p", "target": "q"}).json()
    assert body["degree"] == 2 and len(body["paths"]) == 10 and body["more"] is True


def test_not_connected_within_six_degrees_is_said_with_how_far_was_looked(
    client: TestClient,
) -> None:
    body = client.post(URL, json={"source": "a", "target": "q"}).json()
    assert body == {"degree": None, "paths": [], "more": False, "searched_to": 6}


def test_six_degrees_is_looked_at_and_seven_only_when_asked_for(client: TestClient) -> None:
    assert client.post(URL, json={"source": "s0", "target": "s6"}).json()["degree"] == 6
    beyond = client.post(URL, json={"source": "s0", "target": "s7"}).json()
    assert beyond["degree"] is None and beyond["searched_to"] == 6
    asked = client.post(URL, json={"source": "s0", "target": "s7", "degree": 7}).json()
    assert _routes(asked) == [[f"s{i}" for i in range(8)]]


def test_a_hidden_end_answers_exactly_as_an_unknown_one(client: TestClient) -> None:
    hidden = client.post(URL, json={"source": "h", "target": "d"})
    unknown = client.post(URL, json={"source": "no-such-node", "target": "d"})
    assert hidden.status_code == unknown.status_code == 200
    assert hidden.json() == unknown.json()


@pytest.mark.parametrize("degree", [0, 9, 20])
def test_a_degree_outside_one_to_eight_is_refused(client: TestClient, degree: int) -> None:
    response = client.post(URL, json={"source": "a", "target": "d", "degree": degree})
    assert response.status_code == 422
    assert client.graph.asked == []  # type: ignore[attr-defined]


def test_the_same_node_at_both_ends_is_refused_in_words(client: TestClient) -> None:
    response = client.post(URL, json={"source": "a", "target": "a"})
    assert response.status_code == 422
    assert "the same" in response.text
    assert client.graph.asked == []  # type: ignore[attr-defined]


def test_link_types_asked_for_are_passed_to_every_degree_looked_at(client: TestClient) -> None:
    client.post(URL, json={"source": "a", "target": "d", "edge_types": ["ASSOCIATE_OF"]})
    asked = client.graph.asked  # type: ignore[attr-defined]
    assert asked and all(types == ["ASSOCIATE_OF"] for *_, types in asked)
    assert all(limit == 10 for _, _, _, limit, _ in asked)
