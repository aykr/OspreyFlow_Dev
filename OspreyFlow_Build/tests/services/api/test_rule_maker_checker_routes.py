"""Maker–checker's routes (`spec/06_DECISIONS.md` ADR-133 decision 7, stage (d)): a whole-deployment
rule deployed, changed or retired through the routes waits for a second administrator-author, who
approves or rejects it; the person who proposed it cannot approve it; its versions are read by the
case team. Rule 4: each new route is refused without the right, outside the case and below its level.

The rule store is the real one on Postgres (a throwaway one), connected inside the app's own event
loop; the patterns store and case store are `test_rule_sentence_routes.py`'s stand-ins (the case's
levels applied as the real store applies them).

What a mistake would do, and the case that catches it:
- a whole-deployment rule going live through the route on one person's say —
  `test_a_deployment_scope_rule_deployed_by_one_person_is_pending_until_a_second_approves`;
- self-approval through the route — `test_the_author_cannot_approve_their_own_rule`;
- approval by someone without the administrator's right — `test_approving_needs_the_administrators_right`;
- a data engineer writing an analyst's rule — `test_an_engineer_cannot_author_an_analyst_rule`;
- a waiting change naming its proposer by an identity-provider id (step 9d finding 1), or the
  directory asked for anyone but the proposers of the rules served (ADR-106 decision 3) —
  `test_a_waiting_change_names_its_proposer_and_asks_only_for_proposers_served`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_investigations,
    get_ontology,
    get_patterns_store,
    get_principal,
    get_principal_names,
    get_typology_rules,
)
from services.api.config import PostgresConfig
from services.api.investigations import AccessLevel
from services.api.typology_rules import TypologyRuleStore

from conduit_common.identity import new_id
from schemas.domain import Principal
from tests.services.api.test_rule_sentence_routes import _Audit, _Patterns
from tests.services.api.test_rule_sentences import ONTOLOGY
from tests.services.api.test_monitoring_routes import _Case, _Names

LISTED = {"subject": "Person", "conditions": [{"op": "equals", "property": "family_name", "value": "Okafor"}]}


@asynccontextmanager
async def _no_lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield


class _World:
    def __init__(self) -> None:
        self.case = f"case-{new_id()}"

        def who(name: str, *roles: str) -> Principal:
            return Principal(id=f"{name}-{new_id()}", clearance="OFFICIAL", org_unit="unit-1",
                             roles=list(roles), datasets=["ds-1"])  # fmt: skip

        self.maker = who("maker", "analyst", "osprey-admin")
        self.checker = who("checker", "analyst", "osprey-admin")
        self.analyst = who("analyst", "analyst")
        # A data engineer who also opens Rules and Monitoring (ADR-146 Amendment 2: one who does not
        # is refused at the place's gate before any rule check), so the rule's own check is what refuses.
        self.engineer = who("engineer", "data_engineer", "rule_author")
        self.viewer = who("viewer", "analyst")
        self.outsider = who("outsider", "analyst", "osprey-admin")
        self.as_ = self.maker
        self.investigations = _Case(self.case, {
            self.maker.id: AccessLevel.AUTHOR, self.checker.id: AccessLevel.AUTHOR,
            self.analyst.id: AccessLevel.AUTHOR, self.engineer.id: AccessLevel.AUTHOR,
            self.viewer.id: AccessLevel.VIEWER,
        })  # fmt: skip
        self.audit = _Audit()
        self.patterns = _Patterns()
        self.rules: TypologyRuleStore | None = None

    async def rules_store(self) -> TypologyRuleStore:
        if self.rules is None:
            self.rules = await TypologyRuleStore.connect(PostgresConfig.from_env().dsn)
        return self.rules


@pytest.fixture
def world() -> Iterator[tuple[_World, TestClient]]:
    w = _World()
    previous = app.router.lifespan_context
    app.router.lifespan_context = _no_lifespan
    app.dependency_overrides.update({
        get_principal: lambda: w.as_, get_investigations: lambda: w.investigations,
        get_ontology: lambda: ONTOLOGY, get_patterns_store: lambda: w.patterns,
        get_typology_rules: w.rules_store, get_audit: lambda: w.audit,
        get_principal_names: lambda: _Names(),
    })  # fmt: skip
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield w, client
            if w.rules is not None:
                client.portal.call(w.rules.close)  # type: ignore[union-attr]
    finally:
        app.dependency_overrides.clear()
        app.router.lifespan_context = previous


def _base(w: _World) -> str:
    return f"/v1/investigations/{w.case}/rules"


def _deploy(w: _World, client: TestClient, scope: str = "deployment", **sentence: Any) -> dict[str, Any]:
    made = client.post(f"{_base(w)}/sentence", json={"name": "Okafor", "sentence": {**LISTED, "scope": scope, **sentence}})
    assert made.status_code == 201, made.text
    return made.json()  # type: ignore[no-any-return]


def _active_ids(w: _World, client: TestClient) -> set[str]:
    return {r["id"] for r in client.get(_base(w)).json() if r["status"] == "active"}


def test_a_deployment_scope_rule_deployed_by_one_person_is_pending_until_a_second_approves(
    world: tuple[_World, TestClient],
) -> None:
    w, client = world
    rule = _deploy(w, client)
    assert (rule["status"], rule["pending_action"], rule["pending_by"]) == ("pending", "deploy", w.maker.id)
    assert rule["id"] not in _active_ids(w, client)
    assert w.audit.actions[-1] == "rule_change_proposed"
    w.as_ = w.checker
    approved = client.post(f"{_base(w)}/{rule['id']}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "active"
    assert rule["id"] in _active_ids(w, client)
    assert w.audit.actions[-1] == "rule_change_approved"


def test_the_author_cannot_approve_their_own_rule(world: tuple[_World, TestClient]) -> None:
    w, client = world
    rule = _deploy(w, client)
    refused = client.post(f"{_base(w)}/{rule['id']}/approve")
    assert refused.status_code == 403
    assert refused.json()["detail"]["error"] == "own_change"
    assert "second person" in refused.json()["detail"]["message"]
    assert rule["id"] not in _active_ids(w, client)


def test_approving_needs_the_administrators_right(world: tuple[_World, TestClient]) -> None:
    w, client = world
    rule = _deploy(w, client)
    w.as_ = w.analyst  # an Author of the case without the administrator's right
    refused = client.post(f"{_base(w)}/{rule['id']}/approve")
    assert refused.status_code == 403 and refused.json()["detail"]["right"] == "administer_system"
    refused = client.post(f"{_base(w)}/{rule['id']}/reject", json={"reason": "no"})
    assert refused.status_code == 403 and refused.json()["detail"]["right"] == "administer_system"


def test_a_change_and_a_retirement_of_a_deployment_rule_wait_and_are_kept_as_versions(
    world: tuple[_World, TestClient],
) -> None:
    w, client = world
    rule = _deploy(w, client)
    w.as_ = w.checker
    client.post(f"{_base(w)}/{rule['id']}/approve")
    changed = client.post(f"{_base(w)}/{rule['id']}/change",
                          json={"name": "Okafor, low", "sentence": {**LISTED, "scope": "deployment", "severity": "low"}})  # fmt: skip
    assert changed.status_code == 200, changed.text
    assert (changed.json()["pending_action"], changed.json()["name"]) == ("change", "Okafor")
    w.as_ = w.maker
    assert client.post(f"{_base(w)}/{rule['id']}/approve").json()["name"] == "Okafor, low"
    retiring = client.post(f"{_base(w)}/{rule['id']}/retire")
    assert retiring.status_code == 200 and retiring.json()["pending_action"] == "retire"
    w.as_ = w.checker
    rejected = client.post(f"{_base(w)}/{rule['id']}/reject", json={"reason": "still needed"})
    assert rejected.status_code == 200 and rejected.json()["status"] == "active"
    w.as_ = w.viewer
    versions = client.get(f"{_base(w)}/{rule['id']}/versions")
    assert versions.status_code == 200
    assert [(v["action"], v["status"], v["proposed_by_name"] is not None) for v in versions.json()] == [
        ("deploy", "approved", True), ("change", "approved", True), ("retire", "rejected", True)]  # fmt: skip
    assert versions.json()[-1]["words"] == "still needed"


def test_a_case_rule_is_live_at_once(world: tuple[_World, TestClient]) -> None:
    w, client = world
    w.as_ = w.analyst
    rule = _deploy(w, client, scope="this_case")
    assert rule["status"] == "active" and rule["pending_action"] is None
    assert w.audit.actions[-1] == "rule_deployed"


def test_an_engineer_cannot_author_an_analyst_rule(world: tuple[_World, TestClient]) -> None:
    w, client = world
    w.as_ = w.engineer
    for scope in ("just_me", "this_case"):
        refused = client.post(f"{_base(w)}/sentence", json={"name": "n", "sentence": {**LISTED, "scope": scope}})
        assert refused.status_code == 403, refused.text
        assert refused.json()["detail"]["right"] == "keep_watches"
    assert w.patterns.saved == []
    assert [r for r in client.get(_base(w)).json() if r["investigation_id"] == w.case] == []


def test_the_new_rule_routes_need_the_right_the_case_and_their_level(world: tuple[_World, TestClient]) -> None:
    w, client = world
    rule = _deploy(w, client)
    rid = rule["id"]
    writes = [("approve", None), ("reject", {"reason": "no"}),
              ("change", {"name": "n", "sentence": {**LISTED, "scope": "deployment"}})]  # fmt: skip
    for path, body in writes:
        w.as_ = w.outsider
        assert client.post(f"{_base(w)}/{rid}/{path}", json=body).status_code == 404, path
        w.as_ = w.viewer
        assert client.post(f"{_base(w)}/{rid}/{path}", json=body).status_code == 403, path
    for path in ("versions", "runs"):
        w.as_ = w.outsider
        assert client.get(f"{_base(w)}/{rid}/{path}").status_code == 404, path
        w.as_ = w.viewer.model_copy(update={"roles": []})
        refused = client.get(f"{_base(w)}/{rid}/{path}")
        assert refused.status_code == 403 and refused.json()["detail"]["error"] == "right_required", path
    saved = app.dependency_overrides.pop(get_principal)
    try:
        assert client.get(f"{_base(w)}/{rid}/versions").status_code in (401, 403)
    finally:
        app.dependency_overrides[get_principal] = saved


class _Directory:
    """As `test_alert_close_approval._Directory`: names for known accounts, a record of what was
    asked."""

    def __init__(self, known: dict[str, str]) -> None:
        self.known = known
        self.asked: list[str] = []

    async def display_names(self, ids: Any) -> dict[str, str]:
        wanted = list(ids)
        self.asked += wanted
        return {i: self.known[i] for i in wanted if i in self.known}


def test_a_waiting_change_names_its_proposer_and_asks_only_for_proposers_served(
    world: tuple[_World, TestClient],
) -> None:
    """Step 9d finding 1: the rules list said who proposed a waiting change by their identity-
    provider id. It serves the proposer's name beside the id, asking only for proposers it serves."""
    w, client = world
    rule = _deploy(w, client)
    w.as_ = w.analyst
    _deploy(w, client, scope="this_case")  # live at once: nobody to name
    directory = _Directory({w.maker.id: "Maker Name", w.checker.id: "Checker Name"})
    app.dependency_overrides[get_principal_names] = lambda: directory
    w.as_ = w.checker
    listed = client.get(_base(w))
    assert listed.status_code == 200, listed.text
    served = {r["id"]: r for r in listed.json()}
    assert (served[rule["id"]]["pending_by"], served[rule["id"]]["pending_by_name"]) == (
        w.maker.id, "Maker Name")  # fmt: skip
    assert all(r["pending_by_name"] is None for r in served.values() if r["pending_by"] is None)
    assert set(directory.asked) == {r["pending_by"] for r in served.values() if r["pending_by"]}
