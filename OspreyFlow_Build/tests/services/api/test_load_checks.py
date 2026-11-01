"""The Ingest Studio's "Checks on load" step and Verify's would-be alerts (`spec/06_DECISIONS.md`
ADR-133 decision 6, stage (d); `spec/09_INGEST_STUDIO.md` §5): the data engineer chooses which
load-time rules (case or deployment scope) apply to a pipeline and what a hit does there; Verify
shows the alerts the sample would raise beside the rejection report, writing nothing; engineers
attach rules, they never write one.

Three layers. The store's record of a pipeline's checks is the real `TypologyRuleStore` on Postgres
(a throwaway one). The load path is `recipe_run._rule_gate` over that real store, judging with
`test_sentence_rules`'s recorders and access-filtering graph. The routes run on
`test_studio_recipe_routes.py`'s app with a rule store stand-in (`_Rules`) that answers only from the
rules it holds — reached through the case, within the reader's datasets, as the real one reads — and
stores that refuse every write (`_Refuses`), so a write anywhere in Verify fails the test.

What a mistake would do, and the case that catches it:
- an attached rule not run at load, or an unattached case rule still run —
  `test_an_attached_rule_runs_at_load_and_an_unattached_one_does_not`;
- a whole-deployment rule left off a pipeline — the same case;
- "hold" chosen at a pipeline not holding — `test_a_pipeline_that_holds_on_a_hit_holds_the_rows`;
- pipelines changed by the step before anyone chose — `test_with_no_checks_chosen_every_case_rule_judges_the_load`;
- Verify writing an alert, a row or a signature — `test_verify_shows_the_alerts_a_sample_would_raise_and_writes_nothing`;
- an engineer writing a rule through the step — `test_an_engineer_attaches_rules_but_cannot_write_one_here`;
- the step reachable without the case, the level or the right — `test_the_checks_routes_need_the_case_the_level_and_the_right`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_alerts_store,
    get_analytics,
    get_compute,
    get_held_rows,
    get_hotlists_store,
    get_investigations,
    get_patterns_store,
    get_principal,
    get_principal_resolver,
    get_screening_lists,
    get_typology_rules,
    get_valkey,
)
from services.api.config import PostgresConfig
from services.api.investigations import AccessLevel
from services.api.recipe_run import _rule_gate
from services.api.rule_sentences import compile_pattern
from services.api.typology_rules import TypologyRuleStore

from conduit_common.identity import new_id
from schemas.domain import Principal, TypologyRule, TypologyRuleInput
from schemas.ingest import FieldBinding, RecipeEntity, RowTemplate
from schemas.monitoring import LoadCheck
from schemas.sentences import RuleSentence, SentenceRuleParams
from tests.services.api.test_monitoring_routes import _Case
from tests.services.api.test_rule_sentence_routes import _Refuses
from tests.services.api.test_rule_sentences import ONTOLOGY, SCHEME, _node
from tests.services.api.test_sentence_rules import _Patterns, _Recorder, _write, _WritingGraph
from tests.services.api.test_studio_recipe_routes import (  # noqa: F401 - `client` is a fixture
    _ready_draft,
    _write_csv,
    client,
)

# ruff: noqa: F811  (the imported `client` fixture is extended below)

AUTHOR = Principal(id="author", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"], datasets=["ds-1"])
CHECKER = AUTHOR.model_copy(update={"id": "checker"})
ENGINEER = Principal(id="engineer", clearance="OFFICIAL", org_unit="unit-1", roles=["data_engineer"],
                     datasets=["ds-1"])  # fmt: skip
LISTED = {"subject": "Person", "conditions": [{"op": "one_of", "property": "listing", "values": ["sanction", "pep"]}]}


def _sentence_input(name: str, **sentence: Any) -> TypologyRuleInput:
    said = RuleSentence.model_validate({**LISTED, **sentence})
    return TypologyRuleInput(name=name, trigger=said.runs, params=SentenceRuleParams(pattern_id="pat-1", sentence=said))


# --- the store's record, on Postgres ------------------------------------------------------------


@pytest.fixture
async def rules() -> AsyncIterator[TypologyRuleStore]:
    store = await TypologyRuleStore.connect(PostgresConfig.from_env().dsn)
    yield store
    await store.close()


async def test_a_pipelines_checks_are_kept_with_who_set_them(rules: TypologyRuleStore) -> None:
    recipe = f"recipe-{new_id()}"
    assert await rules.load_checks(recipe) is None  # nobody has chosen
    await rules.set_load_checks(recipe, [LoadCheck(rule_id="r1", on_hit="hold")], ENGINEER)
    kept = await rules.load_checks(recipe)
    assert kept is not None
    assert ([c.model_dump() for c in kept.checks], kept.set_by) == ([{"rule_id": "r1", "on_hit": "hold"}], "engineer")
    await rules.set_load_checks(recipe, [], ENGINEER)
    emptied = await rules.load_checks(recipe)
    assert emptied is not None and emptied.checks == []  # chosen: none — not the same as unchosen


# --- at load: `_rule_gate` over the real store ---------------------------------------------------


async def _gate(rules: TypologyRuleStore, case: str, recipe: str, graph: Any, recorder: _Recorder) -> Any:
    class _Resolver:
        async def resolve_for_owner(self, owner_id: str) -> Principal | None:
            return {"author": AUTHOR, "checker": CHECKER}.get(owner_id)

    sentence = RuleSentence.model_validate(LISTED)
    return await _rule_gate(
        case, loader=AUTHOR, graph=graph, analytics=None, scheme=SCHEME, typology_rules=rules,  # type: ignore[arg-type]
        held_rows=recorder, alerts_store=recorder, audit=recorder, valkey=recorder,  # type: ignore[arg-type]
        principal_resolver=_Resolver(), screening=None, compute=None, expiries=None,  # type: ignore[arg-type]
        patterns=_Patterns(compile_pattern(sentence, ONTOLOGY)), ontology=ONTOLOGY, recipe_id=recipe,  # type: ignore[arg-type]
    )  # fmt: skip


async def _only_in_this_run(rules: TypologyRuleStore, case: str, keep: set[str]) -> None:
    """Whole-deployment rules from other tests in the shared database are not this test's."""
    for rule in await rules.list_active_for_case(case):
        if rule.id not in keep and rule.investigation_id != case:
            await rules.propose_retire(rule.id, rule.investigation_id, Principal(
                id="cleanup", clearance="OFFICIAL", org_unit="unit-1", datasets=None))  # fmt: skip
            try:
                await rules.approve(rule.id, rule.investigation_id, Principal(
                    id="cleanup-2", clearance="OFFICIAL", org_unit="unit-1", datasets=None))  # fmt: skip
            except Exception:  # noqa: BLE001 - already retired, or nothing waiting
                pass


async def test_an_attached_rule_runs_at_load_and_an_unattached_one_does_not(rules: TypologyRuleStore) -> None:
    case, recipe = f"case-{new_id()}", f"recipe-{new_id()}"
    attached = await rules.create(AUTHOR, case, _sentence_input("Attached", severity="high"))
    left_off = await rules.create(AUTHOR, case, _sentence_input("Left off", severity="low"))
    wide = await rules.create(AUTHOR, case, _sentence_input("Everywhere", scope="deployment"))
    await rules.approve(wide.id, case, CHECKER)
    await _only_in_this_run(rules, case, {attached.id, left_off.id, wide.id})
    await rules.set_load_checks(recipe, [LoadCheck(rule_id=attached.id)], ENGINEER)
    recorder = _Recorder()
    graph = _WritingGraph([_node("p1", "Person", family_name="Okafor", listing="pep")])
    gate = await _gate(rules, case, recipe, graph, recorder)
    assert {r.id for r in gate.rules} == {attached.id, wide.id}
    await gate.post_commit([], load_id="load-1", written=[_write("p1", listing="pep")])
    assert sorted(a.rule_id for a in recorder.alerts) == sorted([f"typology:{attached.id}", f"typology:{wide.id}"])


async def test_with_no_checks_chosen_every_case_rule_judges_the_load(rules: TypologyRuleStore) -> None:
    case, recipe = f"case-{new_id()}", f"recipe-{new_id()}"
    one = await rules.create(AUTHOR, case, _sentence_input("One"))
    two = await rules.create(AUTHOR, case, _sentence_input("Two"))
    await _only_in_this_run(rules, case, {one.id, two.id})
    gate = await _gate(rules, case, recipe, _WritingGraph([]), _Recorder())
    assert {r.id for r in gate.rules} == {one.id, two.id}


async def test_a_pipeline_that_holds_on_a_hit_holds_the_rows(rules: TypologyRuleStore) -> None:
    case, recipe = f"case-{new_id()}", f"recipe-{new_id()}"
    rule = await rules.create(AUTHOR, case, _sentence_input("Hold here", runs="pre_commit"))
    await _only_in_this_run(rules, case, {rule.id})
    await rules.set_load_checks(recipe, [LoadCheck(rule_id=rule.id, on_hit="hold")], ENGINEER)
    recorder = _Recorder()
    gate = await _gate(rules, case, recipe, _WritingGraph([]), recorder)
    verdict = await gate.pre_commit([], "tx-1", load_id="load-1", unseen=None,
                                     written=[_write("p1", listing="pep", family_name="A")])  # fmt: skip
    assert sorted(verdict.hold) == [1] and verdict.findings == []
    assert "held for review" in verdict.notes[0]


# --- the routes, and Verify ------------------------------------------------------------------------


class _Rules:
    """The rule store's reads the step and Verify make, over the rules it holds: `list_for_case`
    reaches a case's rules and every whole-deployment rule, within the reader's datasets, as the real
    one reads; `list_active_for_case` is the evaluator's. Anything else it is asked is refused."""

    def __init__(self, held: list[TypologyRule]) -> None:
        self.held = held
        self.checks: dict[str, Any] = {}

    def _reach(self, case: str, principal: Principal | None) -> list[TypologyRule]:
        def wide(r: TypologyRule) -> bool:
            return isinstance(r.params, SentenceRuleParams) and r.params.sentence.scope == "deployment"

        return [r for r in self.held if (r.investigation_id == case or wide(r)) and (
            principal is None or principal.datasets is None or r.dataset_id in (None, *principal.datasets))]  # fmt: skip

    async def list_for_case(self, case: str, principal: Principal) -> list[TypologyRule]:
        return self._reach(case, principal)

    async def list_active_for_case(self, case: str) -> list[TypologyRule]:
        return [r for r in self._reach(case, None) if r.status == "active"]

    async def load_checks(self, recipe_id: str) -> Any:
        return self.checks.get(recipe_id)

    async def set_load_checks(self, recipe_id: str, checks: list[LoadCheck], by: Principal) -> Any:
        from services.api.typology_rules import LoadChecksRecord

        self.checks[recipe_id] = LoadChecksRecord(checks=list(checks), set_by=by.id, set_at=datetime.now(UTC))
        return self.checks[recipe_id]

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the rule store was asked to {name}")


def _rule(rule_id: str, name: str, *, case: str = "inv-1", **sentence: Any) -> TypologyRule:
    spec = _sentence_input(name, **sentence)
    return TypologyRule(**spec.model_dump(), id=rule_id, investigation_id=case, owner_id="author",
                        created_at=datetime(2026, 11, 1, tzinfo=UTC), dataset_id="ds-1")  # fmt: skip


class _Resolver:
    async def resolve_for_owner(self, owner_id: str) -> Principal | None:
        return AUTHOR if owner_id == "author" else None


@pytest.fixture
def studio(client: TestClient, tmp_path: Path) -> Iterator[TestClient]:
    from tests.services.api.test_studio_verify_routes import _FakeGraphPort, _FakeRunKeys
    from services.api.app import get_graph, get_ontology, get_recipe_runs

    held = _Rules([
        _rule("r-case", "Listed people", severity="high"),
        _rule("r-pre", "Listed, before commit", runs="pre_commit"),
        _rule("r-mine", "Mine", scope="just_me"),
        _rule("r-other-case", "Another case's", case="inv-2"),
    ])  # fmt: skip
    graph = _FakeGraphPort()
    sentence = RuleSentence.model_validate(LISTED)
    app.dependency_overrides.update({
        get_principal: lambda: ENGINEER,
        get_investigations: lambda: _Case("inv-1", {ENGINEER.id: AccessLevel.EDITOR, "viewer": AccessLevel.VIEWER,
                                                    "analyst": AccessLevel.AUTHOR}),
        get_typology_rules: lambda: held, get_graph: lambda: graph, get_ontology: lambda: ONTOLOGY,
        get_recipe_runs: lambda: _FakeRunKeys(), get_analytics: lambda: None,
        get_patterns_store: lambda: _Patterns(compile_pattern(sentence, ONTOLOGY)),
        get_principal_resolver: lambda: _Resolver(), get_hotlists_store: lambda: _Refuses("hotlist store"),
        get_screening_lists: lambda: _Refuses("screening store"), get_compute: lambda: _Refuses("compute"),
        get_alerts_store: lambda: _Refuses("alert store"), get_held_rows: lambda: _Refuses("held-row store"),
        get_valkey: lambda: _Refuses("signature set"),
    })  # fmt: skip
    client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path,
        source_location=_write_csv(tmp_path, [{"name": "Okafor", "listing": "pep"}, {"name": "Adeyemi", "listing": "none"}]),
        row_template=RowTemplate(entities=[RecipeEntity(ref="p", pole_class="person", type="Person", on_match="create",
                                                        properties={"family_name": FieldBinding(field="name"),
                                                                    "listing": FieldBinding(field="listing")})]),
    )  # fmt: skip
    client.held = held  # type: ignore[attr-defined]
    yield client


CHECKS = "/v1/investigations/inv-1/ingest/recipes/recipe-1/checks"
VERIFY = "/v1/investigations/inv-1/ingest/recipes/recipe-1/verify"


def test_the_step_offers_the_case_and_deployment_rules_and_not_a_personal_one(studio: TestClient) -> None:
    shown = studio.get(CHECKS)
    assert shown.status_code == 200, shown.text
    body = shown.json()
    assert body["chosen"] is False
    offered = {r["rule_id"]: r for r in body["available"]}
    assert set(offered) == {"r-case", "r-pre"}  # not "just me", not another case's
    assert (offered["r-case"]["can_hold"], offered["r-pre"]["can_hold"]) == (False, True)
    assert offered["r-case"]["words"].startswith("When a Person whose listing is one of")


def test_an_engineer_attaches_rules_but_cannot_write_one_here(studio: TestClient) -> None:
    held = studio.held  # type: ignore[attr-defined]
    made = studio.put(CHECKS, json={"checks": [{"rule_id": "r-case"}, {"rule_id": "r-pre", "on_hit": "hold"}]})
    assert made.status_code == 200, made.text
    assert made.json()["chosen"] is True and len(made.json()["checks"]) == 2
    for body, words in (
        ({"checks": [{"rule_id": "r-case", "sentence": LISTED}]}, None),
        ({"checks": [], "rule": {"name": "n", "sentence": LISTED}}, None),
        ({"checks": [{"rule_id": "r-new"}]}, "There is no rule “r-new” in this case to attach."),
        ({"checks": [{"rule_id": "r-mine"}]}, "There is no rule “r-mine” in this case to attach."),
        ({"checks": [{"rule_id": "r-case", "on_hit": "hold"}]},
         "“Listed people” runs after the load commits, so a hit cannot hold its rows."),
    ):  # fmt: skip
        refused = studio.put(CHECKS, json=body)
        assert refused.status_code == 422, (body, refused.text)
        if words:
            assert refused.json()["detail"]["message"] == words
    assert [r.id for r in held.held] == ["r-case", "r-pre", "r-mine", "r-other-case"]  # nothing written


def test_verify_shows_the_alerts_a_sample_would_raise_and_writes_nothing(studio: TestClient) -> None:
    studio.put(CHECKS, json={"checks": [{"rule_id": "r-case"}, {"rule_id": "r-pre", "on_hit": "hold"}]})
    response = studio.post(VERIFY)
    assert response.status_code == 200, response.text
    body = response.json()
    raised = sorted((w["rule_id"], w["on_hit"], w["entity_name"], w["severity"]) for w in body["would_raise"])
    assert raised == [("r-case", "alert", "Okafor", "high"), ("r-pre", "hold", "Okafor", "medium")]
    assert body["checks_judged"] == 2 and body["checks_not_judged"] == []
    # Beside the rejection report, which is unchanged: Adeyemi's row names no listing the ontology
    # declares, is rejected, and so is judged by no rule.
    assert [(g["count"], g["reason"]) for g in body["rejections"]] == [(1, "Person.listing is not a valid enum")]
    # Every store that could be written to refuses every call (`_Refuses`): none was asked.


def test_a_check_a_dry_run_cannot_judge_is_said_in_words(studio: TestClient) -> None:
    held = studio.held  # type: ignore[attr-defined]
    held.held.append(_rule("r-link", "Linked", relationship={"kind": "linked", "link_type": "PRESENT_AT"}))
    studio.put(CHECKS, json={"checks": [{"rule_id": "r-link"}]})
    body = studio.post(VERIFY).json()
    assert body["would_raise"] == []
    assert body["checks_not_judged"] == [{"rule_id": "r-link", "rule_name": "Linked",
        "why": "It reads links from the stored graph, so it is judged only once the load has committed."}]  # fmt: skip


def test_the_checks_routes_need_the_case_the_level_and_the_right(studio: TestClient) -> None:
    for who, status in (
        (ENGINEER.model_copy(update={"id": "outsider"}), 404),
        (ENGINEER.model_copy(update={"id": "viewer"}), 403),
        (AUTHOR.model_copy(update={"id": "analyst"}), 403),  # an analyst holds no edit_pipelines
    ):  # fmt: skip
        app.dependency_overrides[get_principal] = lambda who=who: who
        assert studio.get(CHECKS).status_code == status, who.id
        assert studio.put(CHECKS, json={"checks": []}).status_code == status, who.id
    app.dependency_overrides[get_principal] = lambda: AUTHOR.model_copy(update={"id": "analyst"})
    refused = studio.get(CHECKS)
    assert refused.json()["detail"]["right"] == "edit_pipelines"
