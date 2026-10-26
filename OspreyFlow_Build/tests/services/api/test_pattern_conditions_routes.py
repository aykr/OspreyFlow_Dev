"""ADR-121: a condition on a pattern node, at the routes that take a pattern (preview, run, save).

The refusal is typed and made before anything is counted, run or stored (the condition is checked
against the ontology the Conduit serves); a condition that is allowed reaches the graph port inside
the pattern, so it is counted first through the same preview and run routes. What the store makes of
the condition (the narrowing, and no trace of a node the reader cannot see) is the conformance
suite's, against the real store; the fake graph here refuses nothing about access and says so.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_graph,
    get_investigations,
    get_jobs,
    get_ontology,
    get_patterns_store,
    get_principal,
)

from ontology.loader import load_default_ontology
from schemas.domain import PatternQuery, Principal, SavedPattern, Subgraph
from tests.services.api.any_case import AnyCase

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
BASE = "/v1/investigations/inv-1/patterns"


class _Graph:
    def __init__(self) -> None:
        self.counted: list[PatternQuery] = []
        self.matched: list[PatternQuery] = []

    async def match_count(
        self, pattern: PatternQuery, principal: Principal, *, ceiling: int
    ) -> int:
        self.counted.append(pattern)
        return 0

    async def match(self, pattern: PatternQuery, principal: Principal) -> Subgraph:
        self.matched.append(pattern)
        return Subgraph(nodes=[], edges=[])


class _Audit:
    async def record(self, **kwargs: object) -> None:
        return None


class _Jobs:
    async def submit(self, job_type: str, payload: dict[str, object]) -> str:
        return "job-1"


class _Store:
    def __init__(self) -> None:
        self.saved: list[PatternQuery] = []

    async def save(
        self, principal: Principal, *, pattern_id: str | None, name: str, definition: PatternQuery
    ) -> SavedPattern:
        self.saved.append(definition)
        return SavedPattern(
            id="s1", pattern_id="p1", version=1, name=name, owner_id=principal.id,
            created_at=datetime(2026, 1, 1, tzinfo=UTC), definition=definition,
        )  # fmt: skip


@pytest.fixture
def client() -> Iterator[TestClient]:
    graph, store = _Graph(), _Store()
    app.dependency_overrides[get_principal] = lambda: PRINCIPAL
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_investigations] = AnyCase
    app.dependency_overrides[get_audit] = _Audit
    app.dependency_overrides[get_jobs] = _Jobs
    app.dependency_overrides[get_ontology] = load_default_ontology
    app.dependency_overrides[get_patterns_store] = lambda: store
    test_client = TestClient(app)
    test_client.graph = graph  # type: ignore[attr-defined]
    test_client.store = store  # type: ignore[attr-defined]
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def _body(where: dict[str, object]) -> dict[str, object]:
    return {
        "nodes": [{"var": "p", "entity_type": "Person", "where": where}],
        "edges": [],
    }


def test_an_allowed_condition_is_counted_first_through_the_preview_route(
    client: TestClient,
) -> None:
    response = client.post(f"{BASE}/preview", json=_body({"family_name": "Smith"}))
    assert response.status_code == 200
    counted = client.graph.counted  # type: ignore[attr-defined]
    assert [n.where for p in counted for n in p.nodes] == [{"family_name": "Smith"}]


def test_an_allowed_condition_is_counted_then_run_through_the_run_route(
    client: TestClient,
) -> None:
    response = client.post(f"{BASE}/run", json=_body({"family_name": "Smith"}))
    assert response.status_code == 200
    graph = client.graph  # type: ignore[attr-defined]
    assert len(graph.counted) == 1 and len(graph.matched) == 1
    assert graph.matched[0].nodes[0].where == {"family_name": "Smith"}


@pytest.mark.parametrize("route", ["preview", "run", "save"])
@pytest.mark.parametrize(
    ("where", "reason", "name"),
    [
        ({"date_of_birth": "1990-01-01"}, "sensitive", "date_of_birth"),
        ({"aliases": "x"}, "not_indexed", "aliases"),
        ({"no_such": "x"}, "unknown_property", "no_such"),
    ],
    ids=["sensitive", "not_indexed", "unknown"],
)
def test_a_refused_condition_is_a_typed_refusal_naming_the_property_and_nothing_is_run(
    client: TestClient, route: str, where: dict[str, str], reason: str, name: str
) -> None:
    body: dict[str, object] = _body(where)
    if route == "save":
        body = {"name": "A pattern", "definition": body}
    response = client.post(f"{BASE}/{route}", json=body)
    assert response.status_code == 422
    refusal = response.json()
    assert refusal["error"] == "pattern_condition_refused"
    assert refusal["reason"] == reason and refusal["property"] == name and refusal["var"] == "p"
    assert name in refusal["detail"]
    assert client.graph.counted == [] and client.graph.matched == []  # type: ignore[attr-defined]
    assert client.store.saved == []  # type: ignore[attr-defined]


def test_more_than_three_conditions_is_refused_before_anything_is_run(client: TestClient) -> None:
    four = {"family_name": "a", "given_names": "b", "x": "c", "y": "d"}
    response = client.post(f"{BASE}/preview", json=_body(four))
    assert response.status_code == 422
    assert client.graph.counted == []  # type: ignore[attr-defined]


@pytest.mark.parametrize("value", [{"$gt": "a"}, ["a", "b"], 3], ids=["range", "several", "number"])
def test_a_condition_that_is_not_one_text_value_is_refused(
    client: TestClient, value: object
) -> None:
    response = client.post(f"{BASE}/preview", json=_body({"family_name": value}))
    assert response.status_code == 422
    assert client.graph.counted == []  # type: ignore[attr-defined]


def test_a_saved_pattern_carries_its_condition(client: TestClient) -> None:
    body = {"name": "Smiths", "definition": _body({"family_name": "Smith"})}
    response = client.post(f"{BASE}/save", json=body)
    assert response.status_code == 201
    assert response.json()["definition"]["nodes"][0]["where"] == {"family_name": "Smith"}
    assert client.store.saved[0].nodes[0].where == {"family_name": "Smith"}  # type: ignore[attr-defined]


async def test_a_typology_rule_replays_the_saved_patterns_condition() -> None:
    """ADR-109 stores a drawn pattern as a rule by its saved pattern, read afresh at each
    evaluation; ADR-121 says the rule carries the condition, so what the rule counts and runs is
    the conditioned pattern, not the pattern as it was before conditions existed."""
    from services.api.pattern_rules import judge_pattern

    from schemas.domain import PatternRuleParams, TypologyRule

    definition = PatternQuery.model_validate(_body({"family_name": "Smith"}))
    saved = SavedPattern(
        id="s1", pattern_id="p1", version=1, name="Smiths", owner_id=PRINCIPAL.id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC), definition=definition,
    )  # fmt: skip

    class _Patterns:
        async def get_authorized(self, pattern_id: str, principal: Principal) -> SavedPattern:
            return saved

    rule = TypologyRule(
        id="r1", investigation_id="inv-1", owner_id=PRINCIPAL.id, name="Smiths",
        params=PatternRuleParams(pattern_id="p1"), created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )  # fmt: skip
    graph = _Graph()
    await judge_pattern(rule, PRINCIPAL, [], graph=graph, patterns=_Patterns())  # type: ignore[arg-type]
    assert [n.where for p in graph.counted for n in p.nodes] == [{"family_name": "Smith"}]
