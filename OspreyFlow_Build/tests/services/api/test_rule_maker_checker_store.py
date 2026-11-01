"""Maker–checker for whole-deployment rules, in `TypologyRuleStore` against live Postgres
(`spec/06_DECISIONS.md` ADR-133 decision 7, stage (d)): deploying, changing or retiring a
whole-deployment rule waits for a second person; the person who proposed it cannot approve it; every
change is kept as a version with who made it and who decided it.

What a mistake would do, and the case that catches it:
- a whole-deployment rule live on one person's say —
  `test_a_deployment_scope_rule_deployed_by_one_person_is_pending_until_a_second_approves`;
- an author approving their own rule — `test_the_author_cannot_approve_their_own_rule`;
- a change or retirement taking effect before approval, or the old version stopping meanwhile —
  `test_a_change_to_a_deployment_rule_waits_and_the_rule_runs_as_it_stood_meanwhile`,
  `test_retiring_a_deployment_rule_waits_for_a_second_person`;
- a rejected rule running — `test_a_rejected_deploy_never_runs`;
- a case rule held up for approval, or changed with no record —
  `test_a_case_rule_needs_no_approval_and_keeps_its_versions_with_who_made_them`;
- a rule deployed live before approvals existed staying live unapproved (Amendment 2 item 7) —
  `test_a_deployment_rule_live_before_approvals_existed_is_made_pending`;
- a change approved from a case the approver cannot reach — `test_an_approver_outside_the_rules_reach_finds_no_change`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
import pytest
from services.api.config import PostgresConfig
from services.api.typology_rules import (
    OwnChangeRefused,
    RuleChangeRefused,
    TypologyRuleNotFoundError,
    TypologyRuleStore,
)

from conduit_common.identity import new_id
from schemas.domain import Principal, TypologyRuleInput
from schemas.sentences import RuleSentence, SentenceRuleParams

MAKER = Principal(id="maker", clearance="OFFICIAL", org_unit="unit-1", datasets=["ds-a"])
CHECKER = Principal(id="checker", clearance="OFFICIAL", org_unit="unit-1", datasets=["ds-a"])
OUTSIDER = Principal(id="outsider", clearance="OFFICIAL", org_unit="unit-2", datasets=["ds-z"])


@pytest.fixture
async def store() -> AsyncIterator[TypologyRuleStore]:
    rules = await TypologyRuleStore.connect(PostgresConfig.from_env().dsn)
    yield rules
    await rules.close()


def _input(scope: str, name: str, severity: str = "high") -> TypologyRuleInput:
    sentence = RuleSentence.model_validate({"subject": "Person", "scope": scope, "severity": severity})
    return TypologyRuleInput(name=name, params=SentenceRuleParams(pattern_id="p", sentence=sentence))


async def _active(store: TypologyRuleStore, case: str) -> set[str]:
    return {r.id for r in await store.list_active_for_case(case)}


async def test_a_deployment_scope_rule_deployed_by_one_person_is_pending_until_a_second_approves(
    store: TypologyRuleStore,
) -> None:
    case, elsewhere = new_id(), new_id()
    rule = await store.create(MAKER, case, _input("deployment", "Sanctioned people"))
    assert (rule.status, rule.pending_action, rule.pending_by) == ("pending", "deploy", "maker")
    assert rule.id not in await _active(store, case) | await _active(store, elsewhere)
    approved = await store.approve(rule.id, case, CHECKER)
    assert (approved.status, approved.pending_action) == ("active", None)
    assert rule.id in await _active(store, elsewhere)
    (version,) = await store.versions(rule.id, case, CHECKER)
    assert (version.action, version.status, version.proposed_by, version.decided_by) == (
        "deploy", "approved", "maker", "checker")  # fmt: skip


async def test_the_author_cannot_approve_their_own_rule(store: TypologyRuleStore) -> None:
    case = new_id()
    rule = await store.create(MAKER, case, _input("deployment", "Mine"))
    with pytest.raises(OwnChangeRefused, match="a second person"):
        await store.approve(rule.id, case, MAKER)
    assert rule.id not in await _active(store, case)
    (version,) = await store.versions(rule.id, case, MAKER)
    assert (version.status, version.decided_by) == ("pending", None)


async def test_a_change_to_a_deployment_rule_waits_and_the_rule_runs_as_it_stood_meanwhile(
    store: TypologyRuleStore,
) -> None:
    case = new_id()
    rule = await store.create(MAKER, case, _input("deployment", "Wide", severity="high"))
    await store.approve(rule.id, case, CHECKER)
    proposed = await store.propose_change(rule.id, case, CHECKER, _input("deployment", "Wide, lower", "low"))
    assert (proposed.status, proposed.pending_action, proposed.name, proposed.version) == (
        "active", "change", "Wide", 1)  # fmt: skip
    (running,) = [r for r in await store.list_active_for_case(case) if r.id == rule.id]
    assert running.params.sentence.severity == "high"  # type: ignore[union-attr]
    with pytest.raises(RuleChangeRefused, match="already waiting"):
        await store.propose_change(rule.id, case, MAKER, _input("deployment", "Again"))
    with pytest.raises(OwnChangeRefused):
        await store.approve(rule.id, case, CHECKER)
    changed = await store.approve(rule.id, case, MAKER)
    assert (changed.name, changed.version, changed.owner_id) == ("Wide, lower", 2, "checker")
    assert changed.params.sentence.severity == "low"  # type: ignore[union-attr]
    actions = [(v.version, v.action, v.status, v.proposed_by, v.decided_by)
               for v in await store.versions(rule.id, case, MAKER)]  # fmt: skip
    assert actions == [(1, "deploy", "approved", "maker", "checker"), (2, "change", "approved", "checker", "maker")]


async def test_retiring_a_deployment_rule_waits_for_a_second_person(store: TypologyRuleStore) -> None:
    case = new_id()
    rule = await store.create(MAKER, case, _input("deployment", "Wide"))
    await store.approve(rule.id, case, CHECKER)
    waiting = await store.propose_retire(rule.id, case, MAKER)
    assert (waiting.status, waiting.pending_action) == ("active", "retire")
    assert rule.id in await _active(store, case)
    retired = await store.approve(rule.id, case, CHECKER)
    assert retired.status == "retired" and retired.retired_at is not None
    assert rule.id not in await _active(store, case)


async def test_a_rejected_deploy_never_runs(store: TypologyRuleStore) -> None:
    case = new_id()
    rule = await store.create(MAKER, case, _input("deployment", "Rejected"))
    rejected = await store.reject(rule.id, case, CHECKER, "the threshold catches every customer")
    assert rejected.status == "retired"
    assert rule.id not in await _active(store, case)
    (version,) = await store.versions(rule.id, case, CHECKER)
    assert (version.status, version.decided_by, version.words) == (
        "rejected", "checker", "the threshold catches every customer")  # fmt: skip
    with pytest.raises(RuleChangeRefused, match="nothing waiting"):
        await store.approve(rule.id, case, CHECKER)


async def test_a_case_rule_needs_no_approval_and_keeps_its_versions_with_who_made_them(
    store: TypologyRuleStore,
) -> None:
    case = new_id()
    rule = await store.create(MAKER, case, _input("this_case", "Here"))
    assert (rule.status, rule.pending_action) == ("active", None)
    changed = await store.propose_change(rule.id, case, CHECKER, _input("this_case", "Here, medium", "medium"))
    assert (changed.status, changed.version, changed.name, changed.owner_id) == ("active", 2, "Here, medium", "checker")
    retired = await store.propose_retire(rule.id, case, MAKER)
    assert retired.status == "retired"
    history = [(v.version, v.action, v.status, v.proposed_by) for v in await store.versions(rule.id, case, MAKER)]
    assert history == [(1, "deploy", "applied", "maker"), (2, "change", "applied", "checker"),
                       (3, "retire", "applied", "maker")]  # fmt: skip


async def test_a_change_into_the_whole_deployment_waits_for_approval(store: TypologyRuleStore) -> None:
    case = new_id()
    rule = await store.create(MAKER, case, _input("this_case", "Here"))
    proposed = await store.propose_change(rule.id, case, MAKER, _input("deployment", "Everywhere"))
    assert (proposed.pending_action, proposed.name) == ("change", "Here")
    assert rule.id in await _active(store, case) and rule.id not in await _active(store, new_id())


async def test_an_approver_outside_the_rules_reach_finds_no_change(store: TypologyRuleStore) -> None:
    case = new_id()
    rule = await store.create(MAKER, case, _input("this_case", "Here"))
    await store.propose_change(rule.id, case, MAKER, _input("deployment", "Everywhere"))
    with pytest.raises(TypologyRuleNotFoundError):
        await store.approve(rule.id, case, OUTSIDER)


async def test_a_deployment_rule_live_before_approvals_existed_is_made_pending(store: TypologyRuleStore) -> None:
    case = new_id()
    old = await store.create(MAKER, case, _input("deployment", "Live since stage (b)"))
    async with store._pool.acquire() as conn:  # as stage (b) left it: live, and no version kept
        await conn.execute("UPDATE typology_rules SET status = 'active' WHERE id = $1", old.id)
        await conn.execute("DELETE FROM typology_rule_versions WHERE rule_id = $1", old.id)
    again = await TypologyRuleStore.connect(PostgresConfig.from_env().dsn)
    try:
        assert old.id not in await _active(again, case)
        (version,) = await again.versions(old.id, case, CHECKER)
        assert (version.action, version.status, version.proposed_by) == ("deploy", "pending", "maker")
        assert version.words is not None and "before a second person's approval" in version.words
        await again.approve(old.id, case, CHECKER)
        assert old.id in await _active(again, case)
    finally:
        await again.close()


async def test_versions_are_kept_in_their_own_table(store: TypologyRuleStore) -> None:
    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        columns = {r["column_name"] for r in await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'typology_rule_versions'")}  # fmt: skip
    finally:
        await conn.close()
    assert {"rule_id", "version", "action", "params", "proposed_by", "decided_by", "status"} <= columns
