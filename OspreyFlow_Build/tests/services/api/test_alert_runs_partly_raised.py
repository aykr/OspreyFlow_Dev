"""A run outside a load that fails part-way keeps, and counts, the alerts it raised before failing
(L2.10's carries, `process/07_BUILD_PLAN.md` row L2.10): "a scheduled slot's failure does not count
the alerts it raised before the error, and a screening re-screen's failure drops the rule's raised
count". Both now carry `rule_evaluation.PartlyRaised` from the raise loop to the record.

- a scheduled slot: `RuleScheduleExecutor` records the slot `failed`, with the alerts it raised and
  the failure in words — `test_a_slot_failing_part_way_records_the_alerts_it_raised`; and the raise
  loop itself (`sentence_rules.run_scheduled_rule`'s) wraps a failure after a raise —
  `test_the_raise_loop_says_how_many_it_raised_before_failing`;
- a re-screening: `Rescreener` counts the rule's alerts raised before the failure, and says the
  failure — `test_a_rescreening_failing_part_way_counts_what_it_raised`.

Each is red with the `PartlyRaised` catch removed at its real call site (RED_RECORD §carries).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from services.api.rule_evaluation import PartlyRaised, RuleGate
from services.api.rule_schedule import RuleScheduleExecutor

from schemas.domain import Principal, TypologyRule
from schemas.monitoring import RuleRun
from schemas.sentences import RuleSchedule, RuleSentence, SentenceRuleParams

from .test_composite_monitors import MEMBER, OFFICER, _diff, _rule, _store
from .test_screening_refresh import _customer, _Graph, _Queue, _Rules

NOW = datetime(2026, 11, 9, 7, 5, tzinfo=UTC)
AUTHOR = Principal(id="author", clearance="OFFICIAL", org_unit="u", roles=["analyst"])


def _scheduled_rule() -> TypologyRule:
    sentence = RuleSentence.model_validate(
        {"subject": "Person", "runs": "schedule", "schedule": RuleSchedule().model_dump()}
    )
    return TypologyRule(
        id="rule-s", investigation_id="case-1", owner_id=AUTHOR.id, name="Daily",
        created_at=NOW - timedelta(days=2), trigger="schedule",
        params=SentenceRuleParams(pattern_id="pat-1", sentence=sentence),
    )  # fmt: skip


class _Runs:
    def __init__(self, rule: TypologyRule) -> None:
        self.rule, self.recorded = rule, []  # type: ignore[var-annotated]

    async def scheduled_rules(self) -> list[TypologyRule]:
        return [self.rule]

    async def rule_runs(self, rule_id: str, *, limit: int = 20) -> list[RuleRun]:
        return []

    async def last_rule_slot(self, rule_id: str) -> datetime | None:
        return NOW - timedelta(days=1, hours=1)

    async def record_rule_run(self, run: RuleRun) -> None:
        self.recorded.append(run)


class _Valkey:
    async def set(self, *a: Any, **k: Any) -> bool:
        return True


async def test_a_slot_failing_part_way_records_the_alerts_it_raised() -> None:
    runs = _Runs(_scheduled_rule())

    async def resolve(owner: str) -> Principal:
        return AUTHOR.model_copy(update={"roles": ["analyst", "single:deploy_rules"]})

    async def check(author: Principal, case: str, level: Any) -> Principal:
        return author

    async def judge(rule: TypologyRule, author: Principal, slot: datetime) -> int:
        raise PartlyRaised(2, RuntimeError("the graph went away"))

    executor = RuleScheduleExecutor(rules=runs, valkey=_Valkey(), resolve_owner=resolve,  # type: ignore[arg-type]
                                    check_case=check, judge=judge)  # fmt: skip
    await executor.tick(NOW)
    (run,) = runs.recorded
    assert (run.outcome, run.alerts) == ("failed", 2)
    assert run.words == "Failed after 2 alert(s) raised: the graph went away."


async def test_the_raise_loop_says_how_many_it_raised_before_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`run_scheduled_rule`'s loop over its findings: the second raise fails after the first."""
    from services.api import sentence_rules

    raised: list[str] = []

    class _Gate:
        ontology = None

        async def seen(self, finding: Any) -> bool:
            return False

        async def raise_committed(self, finding: Any) -> None:
            if raised:
                raise RuntimeError("the queue refused")
            raised.append(finding)

        class graph:  # noqa: N801 - the gate's graph, as `run_scheduled_rule` reads it
            @staticmethod
            async def match_count(*a: Any, **k: Any) -> int:
                return 0

    async def context(rule: Any, deployer: Any, gate: Any) -> Any:
        assert isinstance(rule.params, SentenceRuleParams)
        # A context as the real `_context` always returns one: its subjects matched to a screening
        # entry (`screened`, ADR-146 Amendment 7) read by the raise (none here).
        return rule.params, None, SimpleNamespace(screened={})

    monkeypatch.setattr(sentence_rules, "_context", context)

    async def two_hits(*a: Any, **k: Any) -> list[Any]:
        return ["hit-1", "hit-2"]

    monkeypatch.setattr(sentence_rules, "judge_subjects", two_hits)
    monkeypatch.setattr(sentence_rules, "_findings", lambda rule, d, hits, words, screened=None: list(hits))
    with pytest.raises(PartlyRaised) as failed:
        await sentence_rules.run_scheduled_rule(_scheduled_rule(), AUTHOR, _Gate(), now=NOW)  # type: ignore[arg-type]
    assert failed.value.raised == 1 and "the queue refused" in str(failed.value)


async def test_a_rescreening_failing_part_way_counts_what_it_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.api.dataset_scope import stamping
    from services.api.screening_refresh import Rescreener

    store = await _store()
    graph = _Graph([
        _customer("p-1", "Elena", "Petrova", dob="1980-01-01", datasets=[MEMBER]),
        _customer("p-2", "Elena", "Petrova", dob="1980-01-01", datasets=[MEMBER]),
    ])  # fmt: skip
    queue = _Queue()
    real = RuleGate.raise_committed
    calls: list[int] = []

    async def raise_committed(self: RuleGate, finding: Any, **kwargs: Any) -> Any:
        calls.append(1)
        if len(calls) > 1:
            raise RuntimeError("the queue refused")
        return await real(self, finding, **kwargs)

    monkeypatch.setattr(RuleGate, "raise_committed", raise_committed)

    async def principal_for_owner(owner_id: str) -> Principal | None:
        return OFFICER

    rescreen = Rescreener(
        rules=_Rules([_rule(dataset_id=MEMBER)]), datasets=store,
        graph=stamping(graph, registry=store),  # type: ignore[arg-type]
        scheme=__import__("tests.services.api.test_screening_refresh", fromlist=["SCHEME"]).SCHEME,
        alert_store=queue, audit=queue, valkey=queue,  # type: ignore[arg-type]
        principal_for_owner=principal_for_owner, runner=OFFICER,
    )  # fmt: skip
    report = await rescreen(_diff())
    assert report.alerts == 1 and len(queue.alerts) == 1, "the alert raised before the failure counts"
    (failure,) = report.failures
    assert "after 1 alert(s) raised: the queue refused" in failure
