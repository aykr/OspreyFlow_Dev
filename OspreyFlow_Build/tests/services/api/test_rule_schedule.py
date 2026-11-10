"""The scheduled trigger for rules (`spec/06_DECISIONS.md` ADR-133 decision 1, stage (d)): a rule
written as a sentence runs every day or every week, at an hour, as its own author — resolved afresh,
never as the system — over what was stored in the last day or week; each slot is recorded in words.

The rule store and its run record are the real ones on Postgres (a throwaway one). The claim on a
slot is Valkey `SET NX`; `_Valkey` below models its refusal (a second `SET NX` of a held key is
refused, as the real one refuses it; rule 15). The graph is `test_rule_sentences._Graph` grown to
take an `Alert` node (`test_sentence_rules._WritingGraph`), applying the adapters' access predicate
to every read as the principal asking, and recording which principal read.

What a mistake would do, and the case that catches it:
- a scheduled rule judged as the system, or as someone other than its author —
  `test_a_scheduled_rule_runs_as_its_principal_and_its_run_is_recorded`;
- a slot run twice — `test_a_slot_is_run_once`;
- an author who may no longer act, run anyway, or refused silently —
  `test_an_author_who_can_no_longer_act_is_refused_in_words`;
- a schedule that will not run, saying nothing — `test_a_stopped_schedule_is_said_in_words`,
  `test_three_refusals_in_a_row_stop_the_schedule_in_words`;
- an invalid schedule stored — `test_an_invalid_schedule_is_refused_in_words`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from principal_auth import PrincipalRevoked
from pydantic import ValidationError
from services.api.config import PostgresConfig
from services.api.investigations import InsufficientAccessError
from services.api.rule_evaluation import RuleGate
from services.api.rule_schedule import RuleScheduleExecutor, schedule_view
from services.api.rule_sentences import compile_pattern
from services.api.scheduler import next_slot
from services.api.sentence_rules import run_scheduled_rule
from services.api.typology_rules import TypologyRuleStore

from conduit_common.identity import new_id
from schemas.domain import Principal, TypologyRule, TypologyRuleInput
from schemas.sentences import RuleSentence, SentenceRuleParams
from tests.services.api.test_rule_sentences import ONTOLOGY, SCHEME, _node
from tests.services.api.test_sentence_rules import _Patterns, _Recorder, _WritingGraph

AUTHOR = Principal(id="sched-author", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"],
                   datasets=["ds-1"])  # fmt: skip
DAILY = {"subject": "Person", "conditions": [{"op": "one_of", "property": "listing", "values": ["sanction", "pep"]}],
         "runs": "schedule", "schedule": {"every": "daily", "hour": 6}, "severity": "high"}  # fmt: skip


class _Valkey:
    """`SET NX` as Valkey keeps it: a held key refuses a second `SET NX`."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool | None:
        if nx and key in self.keys:
            return None
        self.keys[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.keys.get(key)

    async def delete(self, key: str) -> int:
        return int(self.keys.pop(key, None) is not None)


class _Watching(_WritingGraph):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.readers: set[str] = set()

    async def get_nodes(self, node_ids: Any, principal: Principal) -> Any:
        self.readers.add(principal.id)
        return await super().get_nodes(node_ids, principal)

    async def match_count(self, pattern: Any, principal: Principal, *, ceiling: int) -> int:
        self.readers.add(principal.id)
        return await super().match_count(pattern, principal, ceiling=ceiling)

    async def match(self, pattern: Any, principal: Principal) -> Any:
        self.readers.add(principal.id)
        return await super().match(pattern, principal)


@pytest.fixture
async def rules() -> AsyncIterator[TypologyRuleStore]:
    store = await TypologyRuleStore.connect(PostgresConfig.from_env().dsn)
    yield store
    await store.close()


class _World:
    def __init__(self, rules: TypologyRuleStore, sentence: dict[str, Any] = DAILY) -> None:
        self.rules = rules
        self.sentence = RuleSentence.model_validate(sentence)
        self.case = f"case-{new_id()}"
        self.graph = _Watching([_node("p1", "Person", family_name="Okafor", listing="pep"),
                                _node("p2", "Person", "SECRET", family_name="Hidden", listing="pep")])  # fmt: skip
        self.recorder = _Recorder()
        self.valkey = _Valkey()
        self.owner: Principal | None = AUTHOR
        self.owner_error: Exception | None = None
        self.case_refused = False

    async def deploy(self) -> TypologyRule:
        params = SentenceRuleParams(pattern_id="pat-1", sentence=self.sentence)
        return await self.rules.create(AUTHOR, self.case,
                                       TypologyRuleInput(name="Listed people", params=params, trigger="schedule"))  # fmt: skip

    async def resolve_owner(self, owner_id: str) -> Principal:
        if self.owner_error is not None:
            raise self.owner_error
        assert self.owner is not None and owner_id == self.owner.id
        return self.owner

    async def check_case(self, owner: Principal, case: str, scope: str) -> Principal:
        if self.case_refused or case != self.case:
            raise InsufficientAccessError("no longer an Author of the case")
        return owner.model_copy(update={"datasets": ["ds-1"]})

    async def judge(self, rule: TypologyRule, deployer: Principal, now: datetime) -> int:
        async def principal_for_owner(owner_id: str) -> Principal | None:
            return deployer if owner_id == deployer.id else None

        gate = RuleGate(rules=[rule], investigation_id=rule.investigation_id, graph=self.graph,  # type: ignore[arg-type]
                        analytics=None, scheme=SCHEME, alert_store=self.recorder, audit=self.recorder,  # type: ignore[arg-type]
                        valkey=self.recorder, principal_for_owner=principal_for_owner, loader=deployer,  # type: ignore[arg-type]
                        ontology=ONTOLOGY, patterns=_Patterns(compile_pattern(self.sentence, ONTOLOGY), AUTHOR.id))  # type: ignore[arg-type]  # fmt: skip
        return await run_scheduled_rule(rule, deployer, gate, now=now)

    def executor(self) -> RuleScheduleExecutor:
        return RuleScheduleExecutor(rules=_OneCase(self.rules, self.case), valkey=self.valkey,  # type: ignore[arg-type]
                                    resolve_owner=self.resolve_owner, check_case=self.check_case,
                                    judge=self.judge)  # fmt: skip


class _OneCase:
    """The real store, its scheduled rules kept to this test's case: the database is shared by the
    whole run, and another test's rules are not this test's to tick."""

    def __init__(self, store: TypologyRuleStore, case: str) -> None:
        self.store, self.case = store, case

    async def scheduled_rules(self) -> list[TypologyRule]:
        return [r for r in await self.store.scheduled_rules() if r.investigation_id == self.case]

    def __getattr__(self, name: str) -> Any:
        return getattr(self.store, name)


def _after_first_slot(rule: TypologyRule) -> datetime:
    """A minute after the rule's first slot (06:00 Europe/London, or Monday's for a weekly rule)."""
    return next_slot("0 6 * * *", "Europe/London", after=rule.created_at) + timedelta(minutes=1)


async def test_a_scheduled_rule_runs_as_its_principal_and_its_run_is_recorded(rules: TypologyRuleStore) -> None:
    w = _World(rules)
    rule = await w.deploy()
    await w.executor().tick(_after_first_slot(rule))
    # Judged as the author, resolved afresh; the one other read is the alert node's own marking,
    # which `write_alert_node` reads as the service (`test_sentence_rules.py` shows the same).
    assert {r for r in w.graph.readers if not r.startswith("system:")} == {AUTHOR.id}
    (alert,) = w.recorder.alerts
    assert (alert.rule_id, alert.severity, alert.owner_id) == (f"typology:{rule.id}", "high", AUTHOR.id)
    assert alert.referent_node_ids == ["p1"]  # the SECRET person is beyond the author: not judged
    fired = [e for e in w.recorder.audit if e["action"] == "rule_fired"]
    assert fired and all(e["principal"].id == AUTHOR.id for e in fired)
    (run,) = await rules.rule_runs(rule.id)
    assert (run.outcome, run.run_as, run.alerts, run.rule_version) == ("ran", AUTHOR.id, 1, 1)
    assert run.words.startswith(f"Ran as {AUTHOR.id}")


async def test_a_slot_is_run_once(rules: TypologyRuleStore) -> None:
    w = _World(rules)
    rule = await w.deploy()
    at = _after_first_slot(rule)
    await w.executor().tick(at)
    await w.executor().tick(at + timedelta(minutes=1))
    assert len(await rules.rule_runs(rule.id)) == 1


async def test_after_downtime_the_latest_slot_runs_and_the_rest_are_missed(rules: TypologyRuleStore) -> None:
    w = _World(rules)
    rule = await w.deploy()
    await w.executor().tick(_after_first_slot(rule) + timedelta(days=2))
    outcomes = [r.outcome for r in await rules.rule_runs(rule.id)]
    assert sorted(outcomes) == ["missed", "missed", "ran"]


async def test_an_author_who_can_no_longer_act_is_refused_in_words(rules: TypologyRuleStore) -> None:
    w = _World(rules)
    rule = await w.deploy()
    w.owner_error = PrincipalRevoked(AUTHOR.id)
    await w.executor().tick(_after_first_slot(rule))
    (run,) = await rules.rule_runs(rule.id)
    assert run.outcome == "refused"
    assert run.words == f"Refused: the rule's author, {AUTHOR.id}, can no longer sign in."
    assert w.recorder.alerts == [] and w.graph.readers == set()


async def test_an_author_without_the_right_or_the_case_is_refused_in_words(rules: TypologyRuleStore) -> None:
    w = _World(rules)
    rule = await w.deploy()
    w.owner = AUTHOR.model_copy(update={"roles": ["reports_viewer"]})
    await w.executor().tick(_after_first_slot(rule))
    w.owner, w.case_refused = AUTHOR, True
    await w.executor().tick(_after_first_slot(rule) + timedelta(days=1))
    words = sorted(r.words for r in await rules.rule_runs(rule.id))
    assert words == [
        f"Refused: the rule's author, {AUTHOR.id}, is no longer an Author of its case.",
        f"Refused: the rule's author, {AUTHOR.id}, no longer holds author_rules or deploy_rules.",
    ]


async def test_three_refusals_in_a_row_stop_the_schedule_in_words(rules: TypologyRuleStore) -> None:
    w = _World(rules)
    rule = await w.deploy()
    w.owner_error = PrincipalRevoked(AUTHOR.id)
    at = _after_first_slot(rule)
    for day in range(4):
        await w.executor().tick(at + timedelta(days=day))
    runs = await rules.rule_runs(rule.id)
    assert [r.outcome for r in runs] == ["refused"] * 3  # the fourth slot is not attempted
    view = schedule_view(rule, runs, now=at + timedelta(days=4))
    assert view.state == "stopped" and view.next_run is None
    assert view.words == (f"Stopped after three refused runs in a row; the last: the rule's author, "
                          f"{AUTHOR.id}, can no longer sign in. Change the rule to start it again.")  # fmt: skip


async def test_a_stopped_schedule_is_said_in_words(rules: TypologyRuleStore) -> None:
    w = _World(rules)
    rule = await w.deploy()
    view = schedule_view(rule, [], now=rule.created_at)
    assert (view.state, view.schedule) == ("scheduled", "every day at 06:00 (Europe/London)")
    assert view.next_run is not None
    retired = await rules.retire(rule.id, w.case, AUTHOR)
    view = schedule_view(retired, [], now=rule.created_at)
    assert view.state == "stopped" and view.next_run is None
    assert view.words is not None and view.words.startswith("Stopped: the rule was retired on ")
    await w.executor().tick(_after_first_slot(rule))
    assert await rules.rule_runs(rule.id) == []


def test_an_invalid_schedule_is_refused_in_words() -> None:
    refusals = {
        "a rule that runs on a schedule needs one": {**DAILY, "schedule": None},
        "only a rule that runs on a schedule takes a schedule": {**DAILY, "runs": "post_commit"},
        "a weekly schedule names the day of the week it runs on": {**DAILY, "schedule": {"every": "weekly", "hour": 6}},
        "a daily schedule runs every day, so it names no day of the week": {**DAILY, "schedule": {"every": "daily", "weekday": 2}},
        "a schedule runs within one case": {**DAILY, "scope": "deployment"},
    }  # fmt: skip
    for words, sentence in refusals.items():
        with pytest.raises(ValidationError, match=words):
            RuleSentence.model_validate(sentence)
    with pytest.raises(ValidationError):
        RuleSentence.model_validate({**DAILY, "schedule": {"every": "daily", "hour": 24}})
    weekly = RuleSentence.model_validate({**DAILY, "schedule": {"every": "weekly", "hour": 7, "weekday": 1}})
    assert weekly.schedule is not None and weekly.schedule.weekday == 1


async def test_a_weekly_rule_judges_the_last_week(rules: TypologyRuleStore) -> None:
    w = _World(rules, {**DAILY, "schedule": {"every": "weekly", "hour": 6, "weekday": 1}})
    rule = await w.deploy()
    view = schedule_view(rule, [], now=rule.created_at)
    assert view.schedule == "every Monday at 06:00 (Europe/London)"
    assert view.next_run is not None and view.next_run.astimezone(UTC).weekday() == 0


async def test_a_scheduled_rule_never_runs_at_a_load(rules: TypologyRuleStore) -> None:
    w = _World(rules)
    rule = await w.deploy()
    assert rule.trigger == "schedule"
    gate = RuleGate(rules=[rule], investigation_id=w.case, graph=w.graph, analytics=None, scheme=SCHEME,  # type: ignore[arg-type]
                    alert_store=w.recorder, audit=w.recorder, valkey=w.recorder,  # type: ignore[arg-type]
                    principal_for_owner=w.resolve_owner, loader=AUTHOR)  # type: ignore[arg-type]  # fmt: skip
    assert await gate.post_commit([], load_id="l1") == []
    assert (await gate.pre_commit([], "tx", load_id="l1", unseen=None)).findings == []
    assert w.recorder.alerts == []


def test_only_a_sentence_runs_on_a_schedule() -> None:
    with pytest.raises(ValidationError, match="only a rule written as a sentence runs on a schedule"):
        TypologyRuleInput.model_validate({"name": "n", "trigger": "schedule",
                                          "params": {"typology": "structuring", "threshold": 10000,
                                                     "window_days": 7, "minimum_count": 3}})  # fmt: skip

