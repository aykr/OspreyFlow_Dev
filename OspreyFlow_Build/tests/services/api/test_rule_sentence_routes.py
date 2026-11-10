"""The sentence builder's routes (`spec/06_DECISIONS.md` ADR-133 decisions 1 and 3, stage (b)):
compile a sentence to its drawn pattern, read a drawn pattern back as a sentence, preview a rule, and
deploy one — each with the case level and the right it needs (rule 4), the scope's own rule (just
me: Editor; this case: Author; the whole deployment: Author and the administrator's right), and a
preview that reveals nothing filtered (rules 3 and 7), refuses past the limit (rule 2) and writes no
alert.

The graph is `test_rule_sentences._Graph` (the adapters' access predicate on every read, every
write refused); the analytics store is the real DuckDB adapter.

What a mistake would do, and the case that catches it:
- a route reachable without the case or the right — `test_each_sentence_route_needs_the_case_and_its_right`;
- a rule deployed at a scope its author may not deploy at — `test_the_scope_decides_the_level_and_right_needed`;
- an undeclared name deployed — `test_a_sentence_naming_an_undeclared_property_is_refused_and_nothing_is_saved`;
- a sentence deployed around its checks through the typology route — `test_the_typology_route_refuses_a_sentence`;
- a preview naming or counting a filtered node — `test_a_preview_run_by_an_analyst_reveals_no_filtered_node`;
- a preview counted in part — `test_a_preview_over_the_limit_is_refused_with_limit_exceeded`;
- a preview that writes — `test_a_preview_writes_no_alert_rule_or_pattern`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import duckdb
import pytest
from fastapi.testclient import TestClient
from services.api import rule_sentences
from services.api.app import (
    app,
    get_alerts_store,
    get_analytics,
    get_audit,
    get_graph,
    get_hotlists_store,
    get_investigations,
    get_ontology,
    get_patterns_store,
    get_principal,
    get_screening_lists,
    get_typology_rules,
)
from services.api.investigations import (
    AccessLevel,
    InsufficientAccessError,
    Investigation,
    InvestigationNotFoundError,
)

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table, create_geometries_table
from schemas.domain import (
    PatternQuery,
    Principal,
    SavedPattern,
    TypologyRule,
    TypologyRuleInput,
)
from tests.services.api.test_rule_sentences import ONTOLOGY, SCHEME, _Graph, _node

CASE = Investigation(id="case-s", name="C", created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="a",
                     owning_unit="unit-1")  # fmt: skip
AUTHOR = Principal(id="au", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
ADMIN_AUTHOR = Principal(id="ad", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst", "osprey-admin"])
EDITOR = Principal(id="ed", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
VIEWER = Principal(id="vw", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
NO_LEVEL = Principal(id="none", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
READER = Principal(id="rv", clearance="OFFICIAL", org_unit="unit-1", roles=["reports_viewer"])

LISTED = {"subject": "Person", "conditions": [{"op": "equals", "property": "family_name", "value": "Okafor"}]}
BASE = f"/v1/investigations/{CASE.id}/rules"


class _Cases:
    levels = {"au": AccessLevel.AUTHOR, "ad": AccessLevel.AUTHOR, "ed": AccessLevel.EDITOR,
              "vw": AccessLevel.VIEWER, "rv": AccessLevel.VIEWER}  # fmt: skip

    async def get_authorized(self, investigation_id: str, principal: Principal, *, need: AccessLevel) -> Investigation:
        level = self.levels.get(principal.id)
        if investigation_id != CASE.id or level is None:
            raise InvestigationNotFoundError(investigation_id)
        if level.rank < need.rank:
            raise InsufficientAccessError("too low")
        return CASE


class _Refuses:
    """A store a route must not touch: any call is a failure."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __getattr__(self, attr: str) -> Any:
        raise AssertionError(f"the {self.name} was asked to {attr}")


class _Patterns:
    def __init__(self) -> None:
        self.saved: list[tuple[str, str, PatternQuery]] = []

    async def save(self, principal: Principal, *, pattern_id: str | None, name: str, definition: PatternQuery) -> SavedPattern:
        self.saved.append((principal.id, name, definition))
        return SavedPattern(id="sp", pattern_id="pat-new", version=1, name=name, owner_id=principal.id,
                            created_at=datetime(2026, 11, 1, tzinfo=UTC), definition=definition)  # fmt: skip


class _Rules:
    def __init__(self) -> None:
        self.created: list[TypologyRuleInput] = []

    async def create(self, principal: Principal, investigation_id: str, spec: TypologyRuleInput) -> TypologyRule:
        self.created.append(spec)
        return TypologyRule(**spec.model_dump(), id="rule-new", investigation_id=investigation_id,
                            owner_id=principal.id, created_at=datetime(2026, 11, 1, tzinfo=UTC))  # fmt: skip


class _Audit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, **entry: Any) -> None:
        self.actions.append(entry["action"])


class _Hotlists:
    async def list_authorized(self, principal: Principal) -> list[Any]:
        return []


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    con = duckdb.connect(":memory:")
    create_events_table(con)
    create_geometries_table(con)
    graph = _Graph([_node("v1", "Person", family_name="Okafor"),
                    _node("h1", "Person", "SECRET", family_name="Okafor", given_names="Hidden")])  # fmt: skip
    things: dict[str, Any] = {"graph": graph, "patterns": _Patterns(), "rules": _Rules(), "audit": _Audit()}
    app.dependency_overrides.update({
        get_investigations: _Cases, get_ontology: lambda: ONTOLOGY, get_graph: lambda: graph,
        get_analytics: lambda: AnalyticsDuckDBAdapter(con, SCHEME), get_hotlists_store: _Hotlists,
        get_screening_lists: lambda: _Refuses("screening store"), get_audit: lambda: things["audit"],
        get_patterns_store: lambda: things["patterns"], get_typology_rules: lambda: things["rules"],
        get_alerts_store: lambda: _Refuses("alert store"),
    })  # fmt: skip
    yield things
    app.dependency_overrides.clear()
    con.close()


def _as(who: Principal) -> TestClient:
    app.dependency_overrides[get_principal] = lambda: who
    return TestClient(app)


def _deploy(who: Principal, **sentence: Any) -> Any:
    return _as(who).post(f"{BASE}/sentence", json={"name": "Okafor", "sentence": {**LISTED, **sentence}})


def test_each_sentence_route_needs_the_case_and_its_right(world: dict[str, Any]) -> None:
    compiled = _as(VIEWER).post(f"{BASE}/sentence/compile", json=LISTED).json()
    calls = [
        ("sentence/compile", LISTED),
        ("sentence/read", {"pattern": compiled["pattern"], "sentence": LISTED}),
        ("preview", {"sentence": LISTED}),
        ("sentence", {"name": "Okafor", "sentence": {**LISTED, "scope": "just_me"}}),
    ]
    for path, body in calls:
        assert _as(NO_LEVEL).post(f"{BASE}/{path}", json=body).status_code == 404, path
        refused = _as(READER).post(f"{BASE}/{path}", json=body)
        assert refused.status_code == 403 and refused.json()["detail"]["error"] == "right_required", path
    for path, body in calls[:3]:
        assert _as(VIEWER).post(f"{BASE}/{path}", json=body).status_code == 200, path
    assert _as(VIEWER).post(f"{BASE}/sentence", json=calls[3][1]).status_code == 403  # Editor, at least


def test_the_scope_decides_the_level_and_right_needed(world: dict[str, Any]) -> None:
    """ADR-146 Amendment 6 (L2.11): this older form keeps rules just for their author; a rule for
    the case, or the whole deployment, is written in the rule editor, through draft, Test and Make
    live, and refused here in words whoever asks (the lane-reviewer's item 2)."""
    assert _deploy(EDITOR, scope="just_me").status_code == 201
    for who, scope in ((AUTHOR, "this_case"), (ADMIN_AUTHOR, "this_case"), (ADMIN_AUTHOR, "deployment")):
        refused = _deploy(who, scope=scope)
        assert (refused.status_code, refused.json()["error"]) == (409, "use_the_rule_editor"), (who.id, scope)
    scopes = [r.params.sentence.scope for r in world["rules"].created]  # type: ignore[union-attr]
    assert scopes == ["just_me"]


def test_a_deployed_sentence_saves_its_drawn_pattern_as_the_authors_and_points_at_it(world: dict[str, Any]) -> None:
    response = _deploy(AUTHOR, severity="high", scope="just_me")
    assert response.status_code == 201, response.text
    (owner, name, pattern), = world["patterns"].saved
    assert (owner, name) == ("au", "Rule: Okafor")
    assert pattern.nodes[0].where == {"family_name": "Okafor"}
    (rule,) = world["rules"].created
    assert (rule.params.typology, rule.params.pattern_id, rule.params.sentence.severity) == ("sentence", "pat-new", "high")  # type: ignore[union-attr]
    assert world["audit"].actions[-1] == "rule_deployed"


def test_a_sentence_naming_an_undeclared_property_is_refused_and_nothing_is_saved(world: dict[str, Any]) -> None:
    bad = {"subject": "Person", "conditions": [{"op": "equals", "property": "shoe_size", "value": "9"}]}
    for path, body in (("sentence/compile", bad), ("preview", {"sentence": bad}),
                       ("sentence", {"name": "n", "sentence": {**bad, "scope": "just_me"}})):  # fmt: skip
        response = _as(AUTHOR).post(f"{BASE}/{path}", json=body)
        assert response.status_code == 422, path
        assert response.json() == {"error": "sentence_refused", "blank": "conditions[0]", "reason": "unknown_property",
                                   "detail": "'Person' declares no property 'shoe_size'"}  # fmt: skip
    assert world["patterns"].saved == [] and world["rules"].created == []


def test_the_typology_route_refuses_a_sentence(world: dict[str, Any]) -> None:
    body = {"name": "n", "trigger": "post_commit",
            "params": {"typology": "sentence", "pattern_id": "anything", "sentence": LISTED}}  # fmt: skip
    response = _as(AUTHOR).post(BASE, json=body)
    assert response.status_code == 422
    assert "sentence builder" in response.json()["detail"]
    assert world["rules"].created == []


def test_a_drawn_pattern_reads_back_as_the_sentence(world: dict[str, Any]) -> None:
    compiled = _as(VIEWER).post(f"{BASE}/sentence/compile", json=LISTED).json()
    assert compiled["words"].startswith("When a Person whose family name is Okafor")
    compiled["pattern"]["nodes"][0]["where"] = {"family_name": "Adeyemi"}
    read = _as(VIEWER).post(f"{BASE}/sentence/read", json={"pattern": compiled["pattern"], "sentence": LISTED}).json()
    assert read["conditions"] == [{"op": "equals", "property": "family_name", "value": "Adeyemi"}]


def test_a_preview_run_by_an_analyst_reveals_no_filtered_node(world: dict[str, Any]) -> None:
    response = _as(VIEWER).post(f"{BASE}/preview", json={"sentence": LISTED})
    assert response.status_code == 200
    body = response.json()
    assert (body["would_raise"], [e["node_id"] for e in body["examples"]]) == (1, ["v1"])
    assert "h1" not in response.text and "Hidden" not in response.text


def test_a_preview_over_the_limit_is_refused_with_limit_exceeded(world: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    world["graph"].nodes.update({f"v{i}": _node(f"v{i}", "Person", family_name="Okafor") for i in range(2, 5)})
    defaults = dict(rule_sentences.preview_sentence.__kwdefaults__ or {})
    monkeypatch.setattr(rule_sentences.preview_sentence, "__kwdefaults__", {**defaults, "cap": 3})
    response = _as(VIEWER).post(f"{BASE}/preview", json={"sentence": LISTED})
    assert response.status_code == 409
    assert {k: response.json()[k] for k in ("error", "cap", "would_be")} == {"error": "limit_exceeded", "cap": 3, "would_be": 4}


def test_a_preview_writes_no_alert_rule_or_pattern(world: dict[str, Any]) -> None:
    world["patterns"] = _Refuses("pattern store")
    world["rules"] = _Refuses("rule store")
    response = _as(AUTHOR).post(f"{BASE}/preview", json={"sentence": {**LISTED, "severity": "high"}})
    assert response.status_code == 200 and response.json()["would_raise"] == 1
    assert world["audit"].actions == ["rule_previewed"]  # the read, recorded; nothing raised
