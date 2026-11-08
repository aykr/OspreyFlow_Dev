"""An alert resting on a case's analyst layer goes into that layer (rule 3; the orchestrator's
ruling of 7 November 2026, the final L3.1 review's first blocker).

Two cases, A and B, read the same source. A subject drawn or hand-marked in A lives in A's layer
alone. Before this, an alert on it named nothing outside a composite case, so the stamping graph
put its node and `ALERTED_ON` into A's first dataset, the source. The node's words begin with the
subject's name, so B saw that name, and one more `Alert` in its counts.

Each of the monitors that can hit such a subject is driven through its real entry, then read back
as case B is scoped:

- a scheduled rule's slot, through the executor the Conduit builds (`app._rule_schedule_executor`);
- a screening list's re-screening for a legacy rule naming no dataset (`scope_a_monitor`'s case
  branch);
- a deployment-wide sentence rule raised in A's load, its deployer reading the loader's datasets
  (`RuleGate._deployer`).

Each is red with `_alert_datasets` planted back to name the layer only in a composite case. An alert
resting on nothing of a layer still goes to the source (`test_an_alert_on_the_source_alone_still_
goes_to_the_source`). In a branch resting on its original's layer, the node is withheld and the row
raised (`test_a_branch_alert_on_its_originals_layer_withholds_its_node`).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from services.api import rule_evaluation
from services.api.dataset_scope import (
    reads_a_composite,
    scope_to_case,
    set_case_datasets,
    stamping,
)
from services.api.datasets import ANALYST_LAYER, Dataset, InMemoryDatasetStore
from services.api.rule_evaluation import Finding, RuleGate
from services.api.screening import ListDiff, ScreeningEntry
from services.api.screening_refresh import Rescreener

from schemas.domain import KycScreeningParams, Principal, TypologyRule
from schemas.sentences import RuleSentence, SentenceRuleParams

from .test_screening_refresh import SCHEME, _customer, _Graph, _Queue, _Rules

SOURCE = "shared-source"
OFFICER = Principal(id="kyc-officer", clearance="OFFICIAL", org_unit="verify")
COLLEAGUE = Principal(id="colleague", clearance="OFFICIAL", org_unit="verify")
NOW = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
NAME = "Elena Petrova"


@pytest.fixture(autouse=True)
def _no_case_left_in_scope() -> object:
    yield
    set_case_datasets(None)


def _dataset(dataset_id: str) -> Dataset:
    return Dataset(
        id=dataset_id, name=dataset_id, owning_unit="verify",
        created_at=datetime(2026, 11, 1, tzinfo=UTC), created_by="seed",
    )  # fmt: skip


async def _two_cases(*, in_the_layer: bool = True) -> tuple[InMemoryDatasetStore, _Graph, str]:
    """Cases A and B on one source; the subject in A's layer (marked by hand there), or in the
    source when `in_the_layer` is false."""
    store = InMemoryDatasetStore()
    store.add(_dataset(SOURCE))
    await store.set_for_case("case-a", [SOURCE], OFFICER, case_name="A")
    await store.set_for_case("case-b", [SOURCE], COLLEAGUE, case_name="B")
    layer = await store.layer_of_case("case-a")
    assert layer is not None
    where = [layer] if in_the_layer else [SOURCE]
    subject = _customer("p-1", "Elena", "Petrova", dob="1980-01-01", datasets=where)
    return store, _Graph([subject]), layer


async def _what_b_sees(store: InMemoryDatasetStore, graph: _Graph) -> list[Any]:
    """Every node case B's reader is shown: the Alert nodes and anything carrying the name."""
    reader = await scope_to_case(COLLEAGUE, "case-b", store)
    set_case_datasets(None)
    return [
        n
        for n in graph.nodes.values()
        if graph._sees(reader, n)  # noqa: SLF001
        and (n.type == "Alert" or NAME in str(n.properties.get("words", "")))
    ]


def _the_old_alert_datasets(monkeypatch: pytest.MonkeyPatch) -> None:
    """The rule as it was at 0cd76bb: the layer only in a composite case, else nothing named."""

    async def as_it_was(graph: Any, scheme: Any, finding: Any) -> list[str]:
        if await reads_a_composite():
            return await rule_evaluation.analyst_writes_into()
        return []

    monkeypatch.setattr(rule_evaluation, "_alert_datasets", as_it_was)


def _finding(rule: TypologyRule, deployer: Principal) -> Finding:
    return Finding(
        rule=rule, deployer=deployer, typology=rule.params.typology, subject="p-1", refs=("p-1",),
        words=f"{NAME}: judged", node_ids=["p-1"],
    )  # fmt: skip


def _rule(**more: Any) -> TypologyRule:
    fields: dict[str, Any] = {
        "id": "rule-1", "investigation_id": "case-a", "owner_id": OFFICER.id, "name": "Screening",
        "params": KycScreeningParams(), "trigger": "post_commit", "created_at": NOW,
    }  # fmt: skip
    return TypologyRule(**{**fields, **more})


# --- the three monitors -----------------------------------------------------------------------


async def _scheduled(store: InMemoryDatasetStore, graph: _Graph, monkeypatch: Any) -> _Queue:
    """One slot of a scheduled rule in case A, through the executor the Conduit builds: its
    `check_case` scopes it as a request is; `judge` builds the gate and calls
    `run_scheduled_rule`, whose matching is stood in for by its last step."""
    import services.api.app as app_module
    from services.api.investigations import AccessLevel

    queue = _Queue()

    class _Investigations:
        async def get_authorized(self, *args: Any, **kwargs: Any) -> object:
            return object()

    async def run_scheduled_rule(
        rule: TypologyRule, deployer: Principal, gate: RuleGate, *, now: datetime
    ) -> int:
        await gate.raise_committed(_finding(rule, deployer))
        return 1

    monkeypatch.setattr(app_module, "run_scheduled_rule", run_scheduled_rule)
    state = SimpleNamespace(
        investigations=_Investigations(), datasets=store,
        graph=stamping(graph, registry=store), analytics=None, handling_scheme=SCHEME,  # type: ignore[arg-type]
        alerts_store=queue, audit=queue, valkey=queue, compute=None, patterns_store=None,
        screening_lists=None, hotlists_store=None, ontology=None, strength_influencers=None,
        typology_rules=None, principal_resolver=SimpleNamespace(resolve_for_owner_detailed=None),
    )  # fmt: skip
    executor = app_module._rule_schedule_executor(SimpleNamespace(state=state))  # type: ignore[arg-type]  # noqa: SLF001
    author = await executor.check_case(OFFICER, "case-a", AccessLevel.EDITOR)
    assert await executor.judge(_rule(), author, NOW) == 1
    return queue


async def _rescreened(store: InMemoryDatasetStore, graph: _Graph, monkeypatch: Any) -> _Queue:
    """A screening list's re-screening for a legacy rule of case A's, naming no dataset."""
    queue = _Queue()
    entry = ScreeningEntry(
        id="e-1", list_name="Synthetic list", listing="sanction", entity_type="Person",
        name=NAME, date_of_birth=date(1980, 1, 1),
    )  # fmt: skip
    diff = ListDiff(
        list_name="Synthetic list", previous_version="1", version="2", added=(entry,),
        changed=(), removed=(), unchanged=0,
    )  # fmt: skip

    async def principal_for_owner(owner_id: str) -> Principal | None:
        return OFFICER if owner_id == OFFICER.id else None

    rescreen = Rescreener(
        rules=_Rules([_rule(dataset_id=None)]), datasets=store,
        graph=stamping(graph, registry=store),  # type: ignore[arg-type]
        scheme=SCHEME, alert_store=queue, audit=queue, valkey=queue,  # type: ignore[arg-type]
        principal_for_owner=principal_for_owner, runner=OFFICER,
    )  # fmt: skip
    report = await rescreen(diff)
    assert report.failures == [] and report.alerts == 1, report
    return queue


async def _deployment_wide(store: InMemoryDatasetStore, graph: _Graph, monkeypatch: Any) -> _Queue:
    """A deployment-wide sentence rule raised in case A's load: its deployer reads the loader's
    datasets (`RuleGate._deployer`), the case's source and layer."""
    queue = _Queue()
    loader = await scope_to_case(OFFICER, "case-a", store)
    sentence = RuleSentence.model_validate({"subject": "Person", "scope": "deployment"})
    rule = _rule(params=SentenceRuleParams(pattern_id="pattern-1", sentence=sentence))

    async def principal_for_owner(owner_id: str) -> Principal | None:
        return OFFICER if owner_id == OFFICER.id else None

    gate = RuleGate(
        rules=[rule], investigation_id="case-a", graph=stamping(graph, registry=store),  # type: ignore[arg-type]
        analytics=None, scheme=SCHEME, alert_store=queue, audit=queue, valkey=queue,  # type: ignore[arg-type]
        principal_for_owner=principal_for_owner, loader=loader,
    )  # fmt: skip
    deployer = await gate._deployer(rule)  # noqa: SLF001
    assert deployer is not None and deployer.datasets == loader.datasets
    await gate.raise_committed(_finding(rule, deployer))
    return queue


MONITORS = [_scheduled, _rescreened, _deployment_wide]
IDS = ["scheduled", "rescreening-legacy-rule", "deployment-wide"]


@pytest.mark.parametrize("monitor", MONITORS, ids=IDS)
async def test_an_alert_on_a_layer_subject_is_not_seen_from_another_case(
    monitor: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, graph, layer = await _two_cases()
    queue = await monitor(store, graph, monkeypatch)
    assert len(queue.alerts) == 1  # the alert is raised, for case A
    (alert,) = [w for w in graph.written_nodes if w.type == "Alert"]
    assert alert.datasets == [layer]
    assert {w.type: w.datasets for w in graph.written_edges if w.type == "ALERTED_ON"} == {
        "ALERTED_ON": [layer]
    }
    # Case B, on the same source: no Alert node, so no name and no count.
    assert await _what_b_sees(store, graph) == []


@pytest.mark.parametrize("monitor", MONITORS, ids=IDS)
async def test_case_b_sees_the_name_with_the_old_rule_back(
    monitor: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, red: `_alert_datasets` as it was, the alert stamped into the source."""
    _the_old_alert_datasets(monkeypatch)
    store, graph, _layer = await _two_cases()
    await monitor(store, graph, monkeypatch)
    (seen,) = await _what_b_sees(store, graph)
    assert seen.type == "Alert" and NAME in seen.properties["words"]
    assert seen.datasets == [SOURCE]


async def test_an_alert_on_the_source_alone_still_goes_to_the_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, graph, _layer = await _two_cases(in_the_layer=False)
    await _scheduled(store, graph, monkeypatch)
    (alert,) = [w for w in graph.written_nodes if w.type == "Alert"]
    assert alert.datasets == [SOURCE]
    layers = {d.id for d in store.datasets.values() if d.kind == ANALYST_LAYER}
    assert not layers & set(alert.datasets)


async def test_a_branch_alert_on_its_originals_layer_withholds_its_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A branch reads its original's layer and writes into none (ADR-144 Amendment 1 decision 2):
    an alert resting on that layer has no place that is not a leak, so its node is withheld and the
    row raised, as for a marking that is not safe."""
    store, graph, layer = await _two_cases()
    await store.copy_case("case-a", "branch", case_name="Branch")
    assert await store.read_only_layer_of("branch") == layer
    queue = _Queue()
    deployer = await scope_to_case(OFFICER, "branch", store)
    gate = RuleGate(
        rules=[], investigation_id="branch", graph=stamping(graph, registry=store),  # type: ignore[arg-type]
        analytics=None, scheme=SCHEME, alert_store=queue, audit=queue, valkey=queue,  # type: ignore[arg-type]
        principal_for_owner=None, loader=deployer,  # type: ignore[arg-type]
    )  # fmt: skip
    await gate.raise_committed(_finding(_rule(investigation_id="branch"), deployer))
    assert len(queue.alerts) == 1 and queue.alerts[0].alert_node_id is None
    assert graph.written_nodes == [] and graph.written_edges == []


async def _a_branch_gate() -> tuple[RuleGate, _Queue, _Graph, Principal]:
    store, graph, _layer = await _two_cases()
    await store.copy_case("case-a", "branch", case_name="Branch")
    queue = _Queue()
    deployer = await scope_to_case(OFFICER, "branch", store)

    async def principal_for_owner(owner_id: str) -> Principal | None:
        return deployer

    rule = _rule(investigation_id="branch", trigger="pre_commit")
    gate = RuleGate(
        rules=[rule], investigation_id="branch", graph=stamping(graph, registry=store),  # type: ignore[arg-type]
        analytics=None, scheme=SCHEME, alert_store=queue, audit=queue, valkey=queue,  # type: ignore[arg-type]
        principal_for_owner=principal_for_owner, loader=deployer,
    )  # fmt: skip
    return gate, queue, graph, deployer


async def _raised_in_a_branch(path: str, monkeypatch: pytest.MonkeyPatch) -> _Queue:
    """The branch's alert on its original's layer, raised on `path`: a load's (`pre_commit`, then
    `after_commit`, its matching stood in for by the finding it returns) or outside a load
    (`raise_committed`, as a schedule, a re-screening or the sweep raises)."""
    gate, queue, graph, deployer = await _a_branch_gate()
    finding = _finding(gate.rules[0], deployer)
    if path == "load":

        async def judged(*_args: Any) -> list[Finding]:
            return [finding]

        monkeypatch.setattr(gate, "_judge_rule", judged)
        verdict = await gate.pre_commit([], "tx", load_id="load-1", unseen=None)
        await gate.after_commit(verdict)
    else:
        await gate.raise_committed(finding)
    assert graph.written_nodes == [] and len(queue.alerts) == 1
    return queue


def _withheld_reason(queue: _Queue) -> str:
    (entry,) = [e for e in queue.audit if e.get("action") == "alert_node_withheld"]
    return str(entry["resolved_query"]["reason"])


@pytest.mark.parametrize("path", ["load", "committed"])
async def test_a_branch_alert_withheld_for_its_originals_layer_says_so(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-146 decision 10's reasons, one more: the audit says the node was withheld because the
    alert rests on the original case's layer, on a load's path and outside one."""
    queue = await _raised_in_a_branch(path, monkeypatch)
    assert _withheld_reason(queue) == rule_evaluation.WITHHELD_WORDS["originals_layer"]


@pytest.mark.parametrize("path", ["load", "committed"])
async def test_the_reason_is_the_units_one_with_the_withholding_swallowed_as_it_was(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, red: the node withheld inside `write_alert_node` with no reason of its own, as it
    was before the rebase onto L2.8, and the audit gives the units' words, which are false here."""
    real = rule_evaluation.write_alert_node

    async def swallowed(*args: Any, **kwargs: Any) -> tuple[str | None, Any]:
        try:
            return await real(*args, **kwargs)
        except rule_evaluation._AlertInAReadOnlyLayer:  # noqa: SLF001
            return None, args[2]  # no node, the finding as given (`write_alert_node`'s shape)

    monkeypatch.setattr(rule_evaluation, "write_alert_node", swallowed)
    queue = await _raised_in_a_branch(path, monkeypatch)
    assert _withheld_reason(queue) == rule_evaluation.WITHHELD_WORDS["units"]
