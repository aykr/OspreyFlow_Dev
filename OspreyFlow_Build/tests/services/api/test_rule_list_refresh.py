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

    async def rule_runs(self, rule_id: str, *, limit: int = 20) -> list[Any]:
        return [r for r in self.runs if r.rule_id == rule_id][-limit:]

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


def _executor(
    rules: _Rules, judged: list[str], *, refuse: str | None = None, reads: set[str] | None = None
) -> RuleScheduleExecutor:
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

    async def reads_list(rule: TypologyRule, list_id: str, owner: str) -> bool:
        """The rule reads that owner's list: here, a rule of `reads` (all, if None) and the
        deployment's lists alone."""
        return owner == "deployment" and (reads is None or rule.id in reads)

    return RuleScheduleExecutor(rules=rules, valkey=_Valkey(), resolve_owner=resolve,  # type: ignore[arg-type]
                                check_case=check_case, judge=judge, judge_on_refresh=on_refresh,
                                reads_list=reads_list)  # fmt: skip


async def test_a_new_version_of_a_list_runs_each_rule_that_names_it() -> None:
    rules = _Rules(_rule("r-uk", "l-uk"), _rule("r-other", "l-other"), _rule("r-uk-2", "l-uk"))
    judged: list[str] = []
    ran = await _executor(rules, judged).on_list_refreshed("l-uk", "deployment", NOW)
    assert (ran, judged) == (2, ["r-uk", "r-uk-2"])
    assert [(r.rule_id, r.outcome, r.alerts) for r in rules.runs] == [("r-uk", "ran", 2), ("r-uk-2", "ran", 2)]
    assert "as its screening list refreshed" in rules.runs[0].words


async def test_a_rule_whose_author_cannot_act_is_recorded_refused_never_run() -> None:
    rules = _Rules(_rule("r-gone", "l-uk", owner="gone"))
    judged: list[str] = []
    assert await _executor(rules, judged, refuse="gone").on_list_refreshed("l-uk", "deployment", NOW) == 0
    assert judged == []
    assert [(r.rule_id, r.outcome) for r in rules.runs] == [("r-gone", "refused")]


async def test_a_refresh_that_kept_nothing_new_starts_no_rule() -> None:
    started: list[str] = []

    class _Executor:
        async def on_list_refreshed(self, list_id: str, owner: str, now: datetime) -> int:
            started.append(f"{owner}/{list_id}")
            return 1

    state = SimpleNamespace(monitoring_schedules=SimpleNamespace(rules=_Executor()))
    for outcome in ("unchanged", "refused", "failed"):
        await _rules_on_list_refresh(state, ListImport(list_id="l-uk", outcome=outcome, words="…"), "deployment")
    assert started == []
    await _rules_on_list_refresh(state, ListImport(list_id="l-uk", outcome="updated", version=2, words="…"), "ds-a")
    assert started == ["ds-a/l-uk"]


async def test_another_datasets_list_of_the_same_id_starts_no_rule() -> None:
    """List ids repeat across datasets (the lane-reviewer's item 6): a refresh starts a rule only
    when its dataset reads *that* owner's list. Red with the owner not asked."""
    rules = _Rules(_rule("r-mine", "visitors"), _rule("r-theirs", "visitors"))
    judged: list[str] = []
    ran = await _executor(rules, judged, reads={"r-mine"}).on_list_refreshed("visitors", "deployment", NOW)
    assert (ran, judged) == (1, ["r-mine"])
    assert await _executor(rules, judged).on_list_refreshed("visitors", "ds-other", NOW) == 0


async def test_three_refusals_in_a_row_stop_a_refresh_rule_as_they_stop_a_schedule() -> None:
    rules = _Rules(_rule("r-gone", "l-uk", owner="gone"))
    judged: list[str] = []
    for minute in range(4):
        await _executor(rules, judged, refuse="gone").on_list_refreshed(
            "l-uk", "deployment", NOW.replace(minute=minute))
    assert [r.outcome for r in rules.runs] == ["refused", "refused", "refused"]


# --- each place a list keeps a new version starts its rules (rule 15: red with any one removed) ---


class _Started:
    def __init__(self) -> None:
        self.started: list[str] = []

    async def on_list_refreshed(self, list_id: str, owner: str, now: datetime) -> int:
        self.started.append(f"{owner}/{list_id}")
        return 1


class _Audit:
    async def record(self, **_: Any) -> None:
        return None


def _updated(list_id: str) -> ListImport:
    return ListImport(list_id=list_id, outcome="updated", version=2, words="now version 2")


async def test_refresh_now_on_a_deployment_list_starts_its_rules(monkeypatch: Any) -> None:
    from services.api import app as app_module

    async def imported(list_id: str, **_: Any) -> ListImport:
        return _updated(list_id)

    monkeypatch.setattr(app_module, "import_list", imported)
    executor = _Started()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        monitoring_schedules=SimpleNamespace(rules=executor))))  # fmt: skip
    await app_module.refresh_deployment_list("l-uk", request, AUTHOR, None, None, _Audit())  # type: ignore[arg-type]
    assert executor.started == ["deployment/l-uk"]


async def test_a_deployment_lists_scheduled_refresh_starts_its_rules(monkeypatch: Any) -> None:
    from services.api import app as app_module

    async def imported(list_id: str, **_: Any) -> ListImport:
        return _updated(list_id)

    async def resolve(owner_id: str) -> Principal:
        return AUTHOR

    monkeypatch.setattr(app_module, "import_list", imported)
    monkeypatch.setattr(app_module, "_owner_with_custom_roles", lambda app_, r: resolve)
    executor = _Started()
    state = SimpleNamespace(
        principal_resolver=SimpleNamespace(resolve_for_owner_detailed=resolve), list_store=None,
        list_rows=None, audit=_Audit(), valkey=None, monitoring_schedules=SimpleNamespace(rules=executor),
    )  # fmt: skip
    scheduler = app_module._deployment_list_scheduler(SimpleNamespace(state=state))  # type: ignore[arg-type]
    await scheduler.run("l-uk", "author")
    assert executor.started == ["deployment/l-uk"]


async def test_a_datasets_own_list_import_starts_the_rules_reading_that_datasets_list(monkeypatch: Any) -> None:
    from schemas.dataset_model import ReferenceList
    from services.api import app as app_module

    monkeypatch.setattr(app_module, "list_source_files",
                        lambda datasets: SimpleNamespace(files=[SimpleNamespace(source_location="/x.csv")]))  # fmt: skip
    class _File:
        """The file the import reads, as `app.py`'s own `Path` (never pytest's)."""

        def __init__(self, location: str) -> None:
            self.location = location

        def stat(self) -> Any:
            return SimpleNamespace(st_size=10)

        def read_bytes(self) -> bytes:
            return b"ref\nA\n"

    monkeypatch.setattr(app_module, "Path", _File)
    reference = ReferenceList(id="visitors", dataset_id="ds-a", name="Visitors", kind="screening",
                              key_column="ref", version=2)  # fmt: skip
    monkeypatch.setattr(app_module, "import_own_list", lambda *a, **k: (reference, "updated"))

    class _Models:
        async def live(self, dataset_id: str) -> Any:
            return None

    executor = _Started()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        monitoring_schedules=SimpleNamespace(rules=executor))))  # fmt: skip
    body = SimpleNamespace(location="/x.csv", name="Visitors", key_column="ref")
    await app_module.import_dataset_own_list(
        "ds-a", "visitors", body, request, AUTHOR, None, _Models(), _Audit())  # type: ignore[arg-type]
    assert executor.started == ["ds-a/visitors"]


async def test_a_refresh_judges_the_rule_over_the_last_day_against_the_new_version(monkeypatch: Any) -> None:
    """`run_on_list_refresh` itself, not a stand-in: a rule with no schedule is judged over the last
    day (red with the refresh read as a schedule: "the rule has no schedule to run on")."""
    from datetime import timedelta

    from schemas.sentences import SentenceRuleParams
    from services.api import sentence_rules

    windows: list[Any] = []

    class _Gate:
        ontology = None

        async def seen(self, finding: Any) -> bool:
            return False

        async def raise_committed(self, finding: Any) -> None:
            return None

        class graph:  # noqa: N801 - the gate's graph, as the judge reads it
            @staticmethod
            async def match_count(*a: Any, **k: Any) -> int:
                return 0

    async def context(rule: Any, deployer: Any, gate: Any) -> Any:
        assert isinstance(rule.params, SentenceRuleParams)
        return rule.params, None, None

    async def hits(subjects: Any, sentence: Any, deployer: Any, ctx: Any, **k: Any) -> list[Any]:
        windows.append(k["window"])
        return ["hit"]

    monkeypatch.setattr(sentence_rules, "_context", context)
    monkeypatch.setattr(sentence_rules, "judge_subjects", hits)
    monkeypatch.setattr(sentence_rules, "_findings", lambda rule, d, found, words: list(found))
    raised = await sentence_rules.run_on_list_refresh(_rule("r-uk", "l-uk"), AUTHOR, _Gate(), now=NOW)  # type: ignore[arg-type]
    assert raised == 1
    (window,) = windows
    assert (window.valid_from, window.valid_to) == (NOW - timedelta(days=1), NOW)
