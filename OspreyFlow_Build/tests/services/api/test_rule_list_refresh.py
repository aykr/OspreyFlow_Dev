"""*When* a screening list refreshes (`spec/06_DECISIONS.md` ADR-146 decision 3, Amendment 6, L2.11):
a new version of a list starts every running rule that names it, each as its author resolved
afresh, and each run is recorded with the rule's runs in words, whatever became of it; a refresh
that kept nothing new starts none. Offline, over the executor's own seams.

What a mistake would do, and the case that catches it:
- a rule saved to run on its list's refresh never running (the orchestrator's condition: the worst
  case is a rule that silently never fires): `test_a_new_version_of_a_list_runs_each_rule_that_names_it`;
- a refresh that changed nothing raising alerts again: `test_a_refresh_that_kept_nothing_new_starts_no_rule`;
- a rule whose author can no longer act running as someone else, or silently:
  `test_a_rule_whose_author_cannot_act_is_recorded_refused_never_run`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from principal_auth import PrincipalRevoked
from schemas.domain import Principal, TypologyRule
from schemas.list_connector import ListImport
from services.api.app import _rules_on_list_refresh
from services.api.investigations import AccessLevel
from services.api.rule_schedule import RuleScheduleExecutor

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
AUTHOR = Principal(id="author", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"], datasets=["ds-1"])


def _rule(rule_id: str, list_id: str, owner: str = "author") -> TypologyRule:
    sentence = {"subject": "Person", "relationship": {"kind": "on_screening_list", "list_id": list_id},
                "runs": "list_refresh"}  # fmt: skip
    return TypologyRule.model_validate({
        "id": rule_id, "investigation_id": "case-1", "owner_id": owner, "name": rule_id,
        "params": {"typology": "sentence", "pattern_id": "p", "sentence": sentence},
        "trigger": "list_refresh", "budget_ms": 5000, "status": "active", "created_at": NOW,
        "dataset_id": "ds-1",
    })  # fmt: skip


class _Rules:
    def __init__(self, *rules: TypologyRule) -> None:
        self.rules = rules
        self.runs: list[Any] = []

    async def list_refresh_rules(self, list_id: str) -> list[TypologyRule]:
        return [r for r in self.rules if r.params.sentence.relationship.list_id == list_id]  # type: ignore[union-attr]

    async def record_rule_run(self, run: Any) -> None:
        self.runs.append(run)

    async def scheduled_rules(self) -> list[TypologyRule]:
        return []


class _Valkey:
    def __init__(self) -> None:
        self.claimed: set[str] = set()

    async def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool:
        if key in self.claimed:
            return False
        self.claimed.add(key)
        return True


def _executor(rules: _Rules, judged: list[str], *, refuse: str | None = None) -> RuleScheduleExecutor:
    async def resolve(owner: str) -> Principal:
        if owner == refuse:
            raise PrincipalRevoked(owner)
        return AUTHOR

    async def check_case(author: Principal, case: str, level: AccessLevel) -> Principal:
        return author

    async def judge(rule: TypologyRule, author: Principal, now: datetime) -> int:
        raise AssertionError("a refresh is not a schedule's slot")

    async def on_refresh(rule: TypologyRule, author: Principal, now: datetime) -> int:
        judged.append(rule.id)
        return 2

    return RuleScheduleExecutor(rules=rules, valkey=_Valkey(), resolve_owner=resolve,  # type: ignore[arg-type]
                                check_case=check_case, judge=judge, judge_on_refresh=on_refresh)  # fmt: skip


async def test_a_new_version_of_a_list_runs_each_rule_that_names_it() -> None:
    rules = _Rules(_rule("r-uk", "l-uk"), _rule("r-other", "l-other"), _rule("r-uk-2", "l-uk"))
    judged: list[str] = []
    ran = await _executor(rules, judged).on_list_refreshed("l-uk", NOW)
    assert (ran, judged) == (2, ["r-uk", "r-uk-2"])
    assert [(r.rule_id, r.outcome, r.alerts) for r in rules.runs] == [("r-uk", "ran", 2), ("r-uk-2", "ran", 2)]
    assert "as its screening list refreshed" in rules.runs[0].words


async def test_a_rule_whose_author_cannot_act_is_recorded_refused_never_run() -> None:
    rules = _Rules(_rule("r-gone", "l-uk", owner="gone"))
    judged: list[str] = []
    assert await _executor(rules, judged, refuse="gone").on_list_refreshed("l-uk", NOW) == 0
    assert judged == []
    assert [(r.rule_id, r.outcome) for r in rules.runs] == [("r-gone", "refused")]


async def test_a_refresh_that_kept_nothing_new_starts_no_rule() -> None:
    started: list[str] = []

    class _Executor:
        async def on_list_refreshed(self, list_id: str, now: datetime) -> int:
            started.append(list_id)
            return 1

    state = SimpleNamespace(monitoring_schedules=SimpleNamespace(rules=_Executor()))
    for outcome in ("unchanged", "refused", "failed"):
        await _rules_on_list_refresh(state, ListImport(list_id="l-uk", outcome=outcome, words="…"))
    assert started == []
    await _rules_on_list_refresh(state, ListImport(list_id="l-uk", outcome="updated", version=2, words="…"))
    assert started == ["l-uk"]
