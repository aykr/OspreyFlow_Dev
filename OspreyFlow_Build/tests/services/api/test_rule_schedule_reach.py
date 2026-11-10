"""A scheduled rule judged within its declared dataset alone, as an author who may have written it
(`spec/06_DECISIONS.md` ADR-146 decision 3, Amendment 6 point 11 and decision 13; the
orchestrator's review of L2.11, items 1 and 3). Offline, through the Conduit's own executor
(`app._rule_schedule_executor`), the slot's judge captured where it reads (`run_scheduled_rule`).

What a mistake would do, and the case that catches it:
- a slot reading the author's whole case scope, the case's analyst layer with it (rule 3):
  `test_a_slot_reads_the_rules_dataset_alone_never_the_cases_layer`;
- a slot running on after the case stops reading the rule's dataset:
  `test_a_slot_is_refused_once_the_case_no_longer_reads_the_rules_dataset`;
- a Rule author's rule never running on its schedule (made live, it runs as them, who hold
  `author_rules` and not `deploy_rules`): `test_a_rule_authors_scheduled_rule_runs_as_them`;
- a slot run as someone with neither right to have written it:
  `test_a_slot_whose_author_holds_neither_writing_right_is_refused`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from schemas.domain import Principal, TypologyRule
from schemas.monitoring import RuleRun
from schemas.sentences import RuleSchedule, RuleSentence, SentenceRuleParams
from services.api import app as app_module
from services.api.datasets import ANALYST_LAYER, Dataset, InMemoryDatasetStore

NOW = datetime(2026, 11, 10, 7, 5, tzinfo=UTC)
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _rule() -> TypologyRule:
    sentence = RuleSentence.model_validate(
        {"subject": "Person", "scope": "this_case", "runs": "schedule",
         "schedule": RuleSchedule().model_dump()}
    )  # fmt: skip
    return TypologyRule(
        id="rule-s", investigation_id="case-1", owner_id="author", name="Daily",
        created_at=NOW - timedelta(days=2), trigger="schedule", dataset_id="ds-1",
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


class _Cases:
    async def get_authorized(self, case: str, principal: Principal, *, need: Any) -> object:
        return object()


def _datasets(*case_reads: str) -> InMemoryDatasetStore:
    store = InMemoryDatasetStore()
    for id_ in ("ds-1", "ds-2"):
        store.add(Dataset(id=id_, name=id_, owning_unit="unit-1", created_at=T0, created_by="e"))
    store.add(Dataset(id="layer-1", name="Analyst layer: case-1", owning_unit="unit-1",
                      created_at=T0, created_by="seed", kind=ANALYST_LAYER, layer_of="case-1"))  # fmt: skip
    store.cases["case-1"] = list(case_reads)
    return store


def _executor(datasets: InMemoryDatasetStore, roles: list[str]) -> tuple[Any, _Runs]:
    runs = _Runs(_rule())

    class _Resolver:
        async def resolve_for_owner_detailed(self, owner: str) -> Principal:
            return Principal(id=owner, clearance="OFFICIAL", org_unit="unit-1", roles=roles)

    state = SimpleNamespace(
        typology_rules=runs, valkey=_Valkey(), principal_resolver=_Resolver(),
        investigations=_Cases(), datasets=datasets,
        graph=None, analytics=None, handling_scheme=None, alerts_store=None, audit=None,
        screening_lists=None, compute=None, patterns_store=None, hotlists_store=None,
        ontology=None, strength_influencers=None,
    )  # fmt: skip
    return app_module._rule_schedule_executor(SimpleNamespace(state=state)), runs  # type: ignore[arg-type]


@pytest.fixture
def judged(monkeypatch: pytest.MonkeyPatch) -> list[Principal]:
    seen: list[Principal] = []

    async def run_scheduled_rule(rule: TypologyRule, author: Principal, gate: Any, *, now: datetime) -> int:
        seen.append(author)
        return 0

    monkeypatch.setattr(app_module, "run_scheduled_rule", run_scheduled_rule)
    return seen


async def test_a_slot_reads_the_rules_dataset_alone_never_the_cases_layer(judged: list[Principal]) -> None:
    """Red with the executor's `reach` removed: the slot read `["ds-1", "ds-2", "layer-1"]`, the
    author's whole case scope (`scope_to_case`), so a subject written only in the layer, or only in
    the case's other dataset, raised the rule's alert."""
    executor, runs = _executor(_datasets("ds-1", "ds-2"), ["analyst"])
    await executor.tick(NOW)
    (author,) = judged
    assert author.datasets == ["ds-1"]
    assert [r.outcome for r in runs.recorded] == ["ran"]


async def test_a_slot_is_refused_once_the_case_no_longer_reads_the_rules_dataset(
    judged: list[Principal],
) -> None:
    """Red with the executor's `reach` removed: the slot ran on over the case's new dataset."""
    executor, runs = _executor(_datasets("ds-2"), ["analyst"])
    await executor.tick(NOW)
    assert judged == []
    (run,) = runs.recorded
    assert run.outcome == "refused" and "no longer reads its dataset" in run.words


async def test_a_rule_authors_scheduled_rule_runs_as_them(judged: list[Principal]) -> None:
    """Make live sets the owner to the draft's author, who may hold `rule_author` alone
    (`author_rules`, not `deploy_rules`). Red with the executor asking `deploy_rules` alone, as it
    did: every such slot refused, so a Rule author's scheduled rule never ran."""
    executor, runs = _executor(_datasets("ds-1"), ["rule_author"])
    await executor.tick(NOW)
    assert [a.id for a in judged] == ["author"]
    assert [r.outcome for r in runs.recorded] == ["ran"]


async def test_a_slot_whose_author_holds_neither_writing_right_is_refused(judged: list[Principal]) -> None:
    executor, runs = _executor(_datasets("ds-1"), ["reports_viewer"])
    await executor.tick(NOW)
    assert judged == []
    (run,) = runs.recorded
    assert run.outcome == "refused" and "no longer holds author_rules or deploy_rules" in run.words
