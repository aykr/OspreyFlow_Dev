"""The rule editor's routes (`spec/06_DECISIONS.md` ADR-146 decision 3 and Amendment 6, L2.11), with
the real rule store on Postgres, connected inside the app's own event loop: a rule is saved as a
draft on one of the case's own datasets, never moved; it is tested over its dataset's last 30 days as
the person testing; it goes live only once tested and, under a second-person policy, only on another
Author's approval. Rule 4: every new route is refused without its right, outside the case and below
its level. The codec is a stand-in on `app.state.rule_files` (rules-b's own is ADR-146 Amendment 5).

What a mistake would do, and the case that catches it:
- an editor route open without its right, its place, its case or its level:
  `test_each_editor_route_needs_its_right_the_case_and_its_level`;
- a rule saved on a drawn dataset or another case's, moved after saving, or saved for the whole
  deployment: `test_a_rule_is_saved_only_on_the_cases_own_dataset_and_never_moved`;
- a draft saved without its files, or running: `test_a_saved_draft_keeps_its_rule_files_and_never_runs`;
- a rule live untested, a test counting what the tester may not see, or its count told to anyone
  else (rule 7): `test_a_rule_goes_live_only_once_tested_and_its_count_is_the_testers_alone`;
- a second-person policy ignored, or the author approving their own:
  `test_with_a_second_person_policy_it_goes_live_only_on_another_authors_approval`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import duckdb
import pytest
from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table, create_geometries_table
from conduit_common.identity import new_id
from fastapi import FastAPI
from fastapi.testclient import TestClient
from schemas.domain import Principal
from schemas.sentences import SentenceRuleInput
from services.api.app import (
    app,
    get_analytics,
    get_audit,
    get_datasets,
    get_graph,
    get_hotlists_store,
    get_investigations,
    get_ontology,
    get_patterns_store,
    get_principal,
    get_screening_lists,
    get_typology_rules,
)
from services.api.config import PostgresConfig
from services.api.datasets import DRAWN, Dataset, InMemoryDatasetStore
from services.api.investigations import AccessLevel
from services.api.typology_rules import RuleFiles, TypologyRuleStore

from tests.services.api.test_monitoring_routes import _Case
from tests.services.api.test_rule_sentence_routes import _Hotlists, _Patterns
from tests.services.api.test_rule_sentences import ONTOLOGY, SCHEME, _Graph, _node

T0 = datetime(2026, 11, 10, tzinfo=UTC)
LISTED = {"subject": "Person", "conditions": [{"op": "equals", "property": "family_name", "value": "Okafor"}]}


def _files(body: SentenceRuleInput) -> RuleFiles:
    return RuleFiles(bpmn=f"<bpmn>{body.name}</bpmn>".encode(), dmn=f"<dmn>{body.dataset_id}</dmn>".encode())


@asynccontextmanager
async def _no_lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield


class _NoScreeningLists:
    """The rule tested reads no screening list; the store is still asked for, so it is given."""

    async def entries(self, entity_type: str) -> list[Any]:
        return []


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def record(self, **entry: Any) -> None:
        self.entries.append(entry)


class _Cases(_Case):
    """Two cases, each with its own levels, applied as the real store applies them: a rule is
    reached only through its own case (rule 4, the lane-reviewer's item 12)."""

    def __init__(self, case_id: str, levels: dict[str, AccessLevel], other: str,
                 other_levels: dict[str, AccessLevel]) -> None:  # fmt: skip
        super().__init__(case_id, levels)
        self.other = _Case(other, other_levels)

    async def get_authorized(self, investigation_id: str, principal: Principal, *, need: AccessLevel) -> Any:
        if investigation_id == self.other.case_id:
            return await self.other.get_authorized(investigation_id, principal, need=need)
        return await super().get_authorized(investigation_id, principal, need=need)


class _World:
    def __init__(self, policy: str = "author_promotes") -> None:
        self.case = f"case-{new_id()}"
        self.other_case = f"case-{new_id()}"

        def who(name: str, *roles: str) -> Principal:
            return Principal(id=f"{name}-{new_id()}", clearance="OFFICIAL", org_unit="unit-1",
                             roles=list(roles), datasets=["ds-1"])  # fmt: skip

        self.author = who("author", "analyst", "rule_author")
        self.checker = who("checker", "analyst", "rule_author")
        self.viewer = who("viewer", "analyst", "rule_author")
        self.no_right = who("no-right", "analyst")
        self.outsider = who("outsider", "analyst", "rule_author")
        self.as_ = self.author
        # An Author of another case reading the same dataset: never this case's rules.
        self.elsewhere = who("elsewhere", "analyst", "rule_author")
        self.investigations = _Cases(self.case, {
            self.author.id: AccessLevel.AUTHOR, self.checker.id: AccessLevel.AUTHOR,
            self.viewer.id: AccessLevel.VIEWER, self.no_right.id: AccessLevel.AUTHOR,
        }, self.other_case, {self.elsewhere.id: AccessLevel.AUTHOR})  # fmt: skip
        self.datasets = InMemoryDatasetStore()
        for dataset in (
            Dataset(id="ds-1", name="Prison records", owning_unit="unit-1", created_at=T0,
                    created_by="eng", promotion_policy=policy),
            Dataset(id="ds-drawn", name="Drawn", owning_unit="unit-1", created_at=T0,
                    created_by="eng", kind=DRAWN),
            Dataset(id="ds-other", name="Elsewhere", owning_unit="unit-1", created_at=T0,
                    created_by="eng"),
        ):  # fmt: skip
            self.datasets.add(dataset)
        self.datasets.cases[self.case] = ["ds-1", "ds-drawn"]
        self.datasets.cases[self.other_case] = ["ds-1"]
        self.audit = _Audit()
        self.patterns = _Patterns()
        self.graph = _Graph([_node("v1", "Person", family_name="Okafor"),
                             _node("h1", "Person", "SECRET", family_name="Okafor")])  # fmt: skip
        self.rules: TypologyRuleStore | None = None

    async def rules_store(self) -> TypologyRuleStore:
        if self.rules is None:
            self.rules = await TypologyRuleStore.connect(PostgresConfig.from_env().dsn)
        return self.rules


def _world(policy: str) -> Iterator[tuple[_World, TestClient]]:
    w = _World(policy)
    con = duckdb.connect(":memory:")
    create_events_table(con)
    create_geometries_table(con)
    previous = app.router.lifespan_context
    app.router.lifespan_context = _no_lifespan
    app.state.rule_files = _files
    app.dependency_overrides.update({
        get_principal: lambda: w.as_, get_investigations: lambda: w.investigations,
        get_ontology: lambda: ONTOLOGY, get_patterns_store: lambda: w.patterns,
        get_typology_rules: w.rules_store, get_audit: lambda: w.audit,
        get_datasets: lambda: w.datasets, get_graph: lambda: w.graph,
        get_analytics: lambda: AnalyticsDuckDBAdapter(con, SCHEME), get_hotlists_store: _Hotlists,
        get_screening_lists: _NoScreeningLists,
    })  # fmt: skip
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield w, client
            if w.rules is not None:
                client.portal.call(w.rules.close)  # type: ignore[union-attr]
    finally:
        app.dependency_overrides.clear()
        app.router.lifespan_context = previous
        app.state.rule_files = None
        con.close()


@pytest.fixture
def world() -> Iterator[tuple[_World, TestClient]]:
    yield from _world("author_promotes")


@pytest.fixture
def strict() -> Iterator[tuple[_World, TestClient]]:
    yield from _world("second_person_reviews")


def _base(w: _World) -> str:
    return f"/v1/investigations/{w.case}/rules"


def _draft(w: _World, client: TestClient, dataset: str = "ds-1", **sentence: Any) -> Any:
    return client.post(f"{_base(w)}/drafts", json={
        "name": "Okafor", "dataset_id": dataset, "sentence": {**LISTED, **sentence}})  # fmt: skip


def _made(w: _World, client: TestClient) -> str:
    made = _draft(w, client)
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


def test_each_editor_route_needs_its_right_the_case_and_its_level(
    world: tuple[_World, TestClient],
) -> None:
    w, client = world
    rule_id = _made(w, client)
    body = {"name": "Okafor", "dataset_id": "ds-1", "sentence": LISTED}
    writes = [
        ("GET", "datasets", None), ("POST", "drafts", body), ("PUT", f"{rule_id}/draft", body),
        ("POST", f"{rule_id}/test", None),
    ]  # fmt: skip
    for method, path, payload in writes:
        url = f"{_base(w)}/{path}"
        w.as_ = w.outsider
        assert client.request(method, url, json=payload).status_code == 404, path
        w.as_ = w.no_right
        refused = client.request(method, url, json=payload)
        assert refused.status_code == 403, path
        assert refused.json()["detail"]["right"] == "author_rules", path
        w.as_ = w.viewer
        assert client.request(method, url, json=payload).status_code == 403, path
    w.as_ = w.viewer
    assert client.get(f"{_base(w)}/{rule_id}/draft").status_code == 200
    assert client.post(f"{_base(w)}/{rule_id}/make-live").status_code == 403
    w.as_ = w.outsider
    assert client.get(f"{_base(w)}/{rule_id}/draft").status_code == 404
    assert client.post(f"{_base(w)}/{rule_id}/make-live").status_code == 404
    w.as_ = w.author
    offers = client.get(f"{_base(w)}/datasets")
    assert offers.status_code == 200
    assert [o["id"] for o in offers.json()] == ["ds-1"]


def test_a_rule_is_saved_only_on_the_cases_own_dataset_and_never_moved(
    world: tuple[_World, TestClient],
) -> None:
    w, client = world
    for elsewhere in ("ds-drawn", "ds-other", "ds-missing"):
        refused = _draft(w, client, elsewhere)
        assert (refused.status_code, refused.json()["error"]) == (404, "dataset_not_found"), elsewhere
    nowhere = client.post(f"{_base(w)}/drafts", json={"name": "Okafor", "sentence": LISTED})
    assert (nowhere.status_code, nowhere.json()["detail"]["error"]) == (422, "dataset_required")
    wide = _draft(w, client, scope="deployment")
    assert wide.status_code == 422 and "converted per dataset" in wide.text
    rule_id = _made(w, client)
    moved = client.put(f"{_base(w)}/{rule_id}/draft", json={
        "name": "Okafor", "dataset_id": "ds-other", "sentence": LISTED})  # fmt: skip
    assert moved.status_code == 404  # another case's dataset is no dataset of this case's
    w.datasets.cases[w.case].append("ds-other")
    moved = client.put(f"{_base(w)}/{rule_id}/draft", json={
        "name": "Okafor", "dataset_id": "ds-other", "sentence": LISTED})  # fmt: skip
    assert (moved.status_code, moved.json()["error"]) == (409, "rule_dataset_fixed")


def test_a_saved_draft_keeps_its_rule_files_and_never_runs(world: tuple[_World, TestClient]) -> None:
    w, client = world
    rule_id = _made(w, client)
    draft = client.get(f"{_base(w)}/{rule_id}/draft").json()
    assert draft["status"] == "draft"
    store = client.portal.call(w.rules_store)  # type: ignore[union-attr]
    assert client.portal.call(store.rule_files, rule_id, draft["version"]) == RuleFiles(  # type: ignore[union-attr]
        bpmn=b"<bpmn>Okafor</bpmn>", dmn=b"<dmn>ds-1</dmn>")  # fmt: skip
    active = client.portal.call(store.list_active_for_case, w.case)  # type: ignore[union-attr]
    assert rule_id not in {r.id for r in active}
    assert "rule_draft_saved" in [e["action"] for e in w.audit.entries]


def test_a_rule_goes_live_only_once_tested_and_its_count_is_the_testers_alone(
    world: tuple[_World, TestClient],
) -> None:
    w, client = world
    rule_id = _made(w, client)
    untested = client.post(f"{_base(w)}/{rule_id}/make-live")
    assert (untested.status_code, untested.json()["error"]) == (409, "rule_untested")
    tested = client.post(f"{_base(w)}/{rule_id}/test")
    assert tested.status_code == 200, tested.text
    assert (tested.json()["would_raise"], tested.json()["days"]) == (1, 30)  # h1 is SECRET
    assert client.get(f"{_base(w)}/{rule_id}/draft").json()["would_raise"] == 1
    w.as_ = w.checker
    assert client.get(f"{_base(w)}/{rule_id}/draft").json()["would_raise"] is None
    # The versions route, too (the lane-reviewer's item 1): no reader but the tester is told.
    assert {v["would_raise"] for v in client.get(f"{_base(w)}/{rule_id}/versions").json()} == {None}
    (entry,) = [e for e in w.audit.entries if e["action"] == "rule_tested"]
    assert entry["result_cardinality"] == 0 and "would_raise" not in str(entry["resolved_query"])
    w.as_ = w.author
    live = client.post(f"{_base(w)}/{rule_id}/make-live")
    assert (live.status_code, live.json()["status"]) == (200, "active")


def test_with_a_second_person_policy_it_goes_live_only_on_another_authors_approval(
    strict: tuple[_World, TestClient],
) -> None:
    w, client = strict
    rule_id = _made(w, client)
    assert client.post(f"{_base(w)}/{rule_id}/test").status_code == 200
    waiting = client.post(f"{_base(w)}/{rule_id}/make-live")
    assert (waiting.json()["status"], waiting.json()["pending_action"]) == ("draft", "deploy")
    assert "rule_make_live_proposed" in [e["action"] for e in w.audit.entries]
    own = client.post(f"{_base(w)}/{rule_id}/approve")
    assert (own.status_code, own.json()["detail"]["error"]) == (403, "own_change")
    w.as_ = w.checker  # an Author with deploy_rules, not an administrator
    approved = client.post(f"{_base(w)}/{rule_id}/approve")
    assert (approved.status_code, approved.json()["status"]) == (200, "active")


def test_the_stored_files_are_the_codecs_at_every_saved_version(world: tuple[_World, TestClient]) -> None:
    """ADR-146 Amendment 5, rules' half: every save writes beside its version exactly what rules-b's
    codec writes for the rule as saved (`rule_standards.rule_files`), the real codec, not a stand-in;
    saving again rewrites them. Red with the save storing files from the sentence before it was
    normalised, or not rewriting them on a second save."""
    from rule_standards import rule_files

    w, client = world
    app.state.rule_files = None  # the real codec
    store = client.portal.call(w.rules_store)  # type: ignore[union-attr]
    first = {"name": "Okafor", "dataset_id": "ds-1", "sentence": LISTED}
    made = client.post(f"{_base(w)}/drafts", json=first)
    assert made.status_code == 201, made.text
    rule_id = made.json()["id"]
    again = {**first, "sentence": {**LISTED, "severity": "low"}}
    for body in (first, again):
        if body is again:
            assert client.put(f"{_base(w)}/{rule_id}/draft", json=body).status_code == 200
        draft = client.get(f"{_base(w)}/{rule_id}/draft").json()
        kept = client.portal.call(store.rule_files, rule_id, draft["version"])  # type: ignore[union-attr]
        expected = rule_files(SentenceRuleInput.model_validate(
            {**body, "sentence": draft["params"]["sentence"]}), dataset_id="ds-1")  # fmt: skip
        assert kept is not None and (kept.bpmn, kept.dmn) == (expected.bpmn, expected.dmn)



def test_neither_the_author_nor_the_asker_sends_a_make_live_back(strict: tuple[_World, TestClient]) -> None:
    """ADR-146 Amendment 6 point 4: another Author decides a waiting make-live, either way (the
    lane-reviewer's item 11). Red with send-back's own check removed."""
    w, client = strict
    rule_id = _made(w, client)
    assert client.post(f"{_base(w)}/{rule_id}/test").status_code == 200
    w.as_ = w.checker  # the checker asks; the author wrote it
    assert client.post(f"{_base(w)}/{rule_id}/make-live").status_code == 200
    for who in (w.author, w.checker):
        w.as_ = who
        refused = client.post(f"{_base(w)}/{rule_id}/reject", json={"reason": "mine"})
        assert (refused.status_code, refused.json()["detail"]["error"]) == (403, "own_change"), who.id
    assert client.get(f"{_base(w)}/{rule_id}/draft").json() is None  # still waiting, not sent back


def test_another_cases_author_reaches_none_of_this_cases_rule(world: tuple[_World, TestClient]) -> None:
    """Rule 4 at the store's own filter (the lane-reviewer's item 12): an Author of another case,
    reading the same dataset, asking through their own case for this case's rule, finds nothing,
    as a missing rule; and changes nothing."""
    w, client = world
    rule_id = _made(w, client)
    w.as_ = w.elsewhere
    there = f"/v1/investigations/{w.other_case}/rules/{rule_id}"
    for method, path, body in (("GET", "draft", None), ("GET", "versions", None), ("POST", "test", None),
                               ("POST", "make-live", None), ("POST", "approve", None),
                               ("POST", "reject", {"reason": "no"}),
                               ("PUT", "draft", {"name": "n", "dataset_id": "ds-1", "sentence": LISTED})):  # fmt: skip
        answer = client.request(method, f"{there}/{path}", json=body)
        assert (answer.status_code, answer.json().get("error")) == (404, "rule_not_found"), path
    w.as_ = w.author
    assert client.get(f"{_base(w)}/{rule_id}/draft").json()["name"] == "Okafor"


def test_a_save_naming_a_type_outside_the_datasets_live_model_is_refused(world: tuple[_World, TestClient]) -> None:
    """ADR-146 decision 3 at the save (rule 12; the lane-reviewer's item 18): the dataset's live
    model narrows what the sentence may name. Red with the save checked against the deployment's
    whole ontology."""
    from types import SimpleNamespace

    from services.api.app import get_target_models

    w, client = world

    class _Models:
        async def live(self, dataset_id: str) -> Any:
            return SimpleNamespace(packs=["finance"], reference_lists=[])

    app.dependency_overrides[get_ontology] = lambda: ONTOLOGY.model_copy(
        update={"type_packs": {**ONTOLOGY.type_packs, "Person": "prison"}})
    app.dependency_overrides[get_target_models] = lambda: _Models()
    refused = _draft(w, client)
    assert refused.status_code == 422, refused.text
    assert "Person" in refused.text
    assert w.patterns.saved == []
