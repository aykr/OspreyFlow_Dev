"""Monitors keep working in a case reading a composite (ADR-099 Amendment 15 item 2), which is
read-only for now: an alert's own nodes and links, and what a finding writes alongside it, go into
the case's analyst layer, which the case reads. Before this, each failed without raising an alert,
every write refused by the stamping graph's last word, or wrote into a member (the final L3.1
review, fix 2, and the lane-reviewer's first two findings):

- a scheduled rule's slot, through the executor the Conduit builds (`app._rule_schedule_executor`:
  `check_case` scopes it as a request is, then `judge` builds the gate and calls
  `run_scheduled_rule`, its matching stood in for by its last step): one alert, its node and
  `ALERTED_ON` in the layer;
- a screening list's re-screening (`Rescreener`), for a rule naming the composite's own id, a
  member's (made before the case read a composite) or none: one alert, its node, `ALERTED_ON`, the
  listed party and its `SAME_AS` all in the layer, and no member changed;
- the daily KYC sweep (`kyc_sweep.sweep`), for a rule naming the composite or a member: one alert
  in the layer.

Each is shown red: `rule_evaluation._alert_datasets` planted to name nothing, so the writes fall to
the stamping graph's last word as before; and the monitors' scoping planted back to the rule's
dataset alone, when a rule naming the composite reads nothing and one naming a member writes into
it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from services.api import kyc_sweep, rule_evaluation, screening_refresh
from services.api.dataset_scope import (
    CompositeReadOnlyError,
    scope_to_case,
    set_case_datasets,
    stamping,
)
from services.api.datasets import ANALYST_LAYER, COMPOSITE, Dataset, InMemoryDatasetStore
from services.api.rule_evaluation import Finding, RuleGate
from services.api.screening import ListDiff, ScreeningEntry
from services.api.screening_refresh import Rescreener

from schemas.domain import KycScreeningParams, Principal, TypologyRule

from .test_screening_refresh import SCHEME, _customer, _Graph, _Queue, _Rules

CASE = "case-both"
MEMBER, OTHER, BOTH = "member", "other-member", "both"
OFFICER = Principal(id="kyc-officer", clearance="OFFICIAL", org_unit="verify")
NOW = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _no_case_left_in_scope() -> object:
    yield
    set_case_datasets(None)


def _dataset(dataset_id: str, **kind: object) -> Dataset:
    return Dataset(
        id=dataset_id,
        name=dataset_id,
        owning_unit="verify",
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
        created_by="seed",
        **kind,  # type: ignore[arg-type]
    )


async def _store() -> InMemoryDatasetStore:
    store = InMemoryDatasetStore()
    store.add(_dataset(MEMBER))
    store.add(_dataset(OTHER))
    store.add(_dataset(BOTH, kind=COMPOSITE, members=[MEMBER, OTHER]))
    await store.set_for_case(CASE, [BOTH], OFFICER, case_name="Both")
    return store


def _rule(**more: Any) -> TypologyRule:
    return TypologyRule(
        id="rule-1", investigation_id=CASE, owner_id=OFFICER.id, name="Screening",
        params=KycScreeningParams(), trigger="post_commit", created_at=NOW, **more,
    )  # fmt: skip


def _no_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    """The refusal back: the alert names nothing, as before, and the stamping graph judges it."""

    async def nothing() -> list[str]:
        return []

    monkeypatch.setattr(rule_evaluation, "_alert_datasets", nothing)


def _layer_of(store: InMemoryDatasetStore) -> str:
    (layer,) = [d.id for d in store.datasets.values() if d.kind == ANALYST_LAYER]
    return layer


# --- a scheduled rule's slot ------------------------------------------------------------------


async def _a_scheduled_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[InMemoryDatasetStore, _Graph, _Queue, Any]:
    """One slot of a scheduled rule in the composite case, through the executor the Conduit builds
    (`app._rule_schedule_executor`): its `check_case`, the case's level check and `scope_to_case`,
    then its `judge`, which builds the gate and calls `run_scheduled_rule`. The sentence's own
    matching (the drawn pattern's `match`, judged as `test_rule_schedule.py` does) is stood in for
    by its last step: the finding raised through the gate it was given."""
    from types import SimpleNamespace

    import services.api.app as app_module
    from services.api.investigations import AccessLevel

    store = await _store()
    customer = _customer("p-1", "Elena", "Petrova", datasets=[MEMBER])
    graph = _Graph([customer])
    queue = _Queue()

    class _Investigations:
        async def get_authorized(self, *args: Any, **kwargs: Any) -> object:
            return object()

    async def run_scheduled_rule(
        rule: TypologyRule, deployer: Principal, gate: RuleGate, *, now: datetime
    ) -> int:
        await gate.raise_committed(
            Finding(
                rule=rule,
                deployer=deployer,
                typology="kyc_screening",
                subject="p-1",
                refs=("p-1",),
                words="Elena Petrova: judged on the schedule",
                node_ids=["p-1"],
            )  # fmt: skip
        )
        return 1

    monkeypatch.setattr(app_module, "run_scheduled_rule", run_scheduled_rule)
    state = SimpleNamespace(
        investigations=_Investigations(), datasets=store,
        graph=stamping(graph, registry=store), analytics=None, handling_scheme=SCHEME,
        alerts_store=queue, audit=queue, valkey=queue, compute=None, patterns_store=None,
        screening_lists=None, hotlists_store=None, ontology=None, strength_influencers=None,
        typology_rules=None,
        principal_resolver=SimpleNamespace(resolve_for_owner_detailed=None),
    )  # fmt: skip
    executor = app_module._rule_schedule_executor(SimpleNamespace(state=state))  # type: ignore[arg-type]  # noqa: SLF001
    author = await executor.check_case(OFFICER, CASE, AccessLevel.EDITOR)
    return store, graph, queue, (executor, author)


async def test_a_scheduled_rule_in_a_composite_case_raises_its_alert_into_the_layer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, graph, queue, (executor, author) = await _a_scheduled_slot(monkeypatch)
    assert await executor.judge(_rule(dataset_id=BOTH), author, NOW) == 1
    layer = _layer_of(store)
    assert len(queue.alerts) == 1
    (alert,) = graph.written_nodes
    assert alert.type == "Alert" and alert.datasets == [layer]
    (alerted,) = graph.written_edges
    assert alerted.type == "ALERTED_ON" and alerted.target == "p-1"
    assert alerted.datasets == [layer]
    # The member's own node is as it was.
    assert graph.nodes["p-1"].datasets == [MEMBER]


async def test_the_scheduled_alert_is_refused_with_the_refusal_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_layer(monkeypatch)
    _store_, graph, queue, (executor, author) = await _a_scheduled_slot(monkeypatch)
    with pytest.raises(CompositeReadOnlyError):
        await executor.judge(_rule(dataset_id=BOTH), author, NOW)
    assert queue.alerts == [] and graph.written_nodes == []


# --- a screening list's re-screening ----------------------------------------------------------


def _diff() -> ListDiff:
    entry = ScreeningEntry(
        id="e-1", list_name="Synthetic list", listing="sanction", entity_type="Person",
        name="Elena Petrova", date_of_birth=date(1980, 1, 1),
    )  # fmt: skip
    return ListDiff(
        list_name="Synthetic list", previous_version="1", version="2", added=(entry,),
        changed=(), removed=(), unchanged=0,
    )  # fmt: skip


async def _rescreen(
    rule_dataset: str | None = BOTH,
) -> tuple[InMemoryDatasetStore, _Graph, _Queue, Any]:
    """A re-screening in the composite case, for a rule naming `rule_dataset`: the composite's own
    id (made in the case, `made_in`), a member's (made before the case read a composite: what the
    migration leaves a case it composes), or none."""
    store = await _store()
    graph = _Graph([_customer("p-1", "Elena", "Petrova", dob="1980-01-01", datasets=[MEMBER])])
    queue = _Queue()

    async def principal_for_owner(owner_id: str) -> Principal | None:
        return OFFICER if owner_id == OFFICER.id else None

    rescreen = Rescreener(
        rules=_Rules([_rule(dataset_id=rule_dataset)]), datasets=store,
        graph=stamping(graph, registry=store),  # type: ignore[arg-type]
        scheme=SCHEME, alert_store=queue, audit=queue, valkey=queue,  # type: ignore[arg-type]
        principal_for_owner=principal_for_owner, runner=OFFICER,
    )  # fmt: skip
    report = await rescreen(_diff())
    return store, graph, queue, report


@pytest.mark.parametrize("rule_dataset", [BOTH, MEMBER, None], ids=["composite", "member", "none"])
async def test_a_rescreening_in_a_composite_case_raises_its_alert_into_the_layer(
    rule_dataset: str | None,
) -> None:
    store, graph, queue, report = await _rescreen(rule_dataset)
    assert report.failures == []
    assert report.alerts == 1 and len(queue.alerts) == 1
    layer = _layer_of(store)
    assert {w.type: w.datasets for w in graph.written_nodes} == {
        "Person": [layer],  # the listed party, new, written with the alert
        "Alert": [layer],
    }
    assert {w.type for w in graph.written_edges} == {"SAME_AS", "ALERTED_ON"}
    assert all(w.datasets == [layer] for w in graph.written_edges)
    assert graph.nodes["p-1"].datasets == [MEMBER]


async def test_the_rescreening_fails_with_the_refusal_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_layer(monkeypatch)
    _s, graph, queue, report = await _rescreen()
    assert report.alerts == 0 and queue.alerts == []
    assert len(report.failures) == 1 and "read-only" in report.failures[0]
    assert graph.written_nodes == []


def _scoped_by_the_rules_dataset(monkeypatch: pytest.MonkeyPatch) -> None:
    """The scoping as it was: by the dataset the rule names, with no case in scope."""

    async def as_before(
        deployer: Principal, case: str, rule_dataset: str | None, store: Any
    ) -> Principal:
        if rule_dataset:
            set_case_datasets([rule_dataset])
            return deployer.model_copy(update={"datasets": [rule_dataset]})
        return await scope_to_case(deployer, case, store)

    monkeypatch.setattr(screening_refresh, "scope_a_monitor", as_before)
    monkeypatch.setattr(kyc_sweep, "scope_a_monitor", as_before)


async def test_a_member_named_rescreening_writes_into_the_member_scoped_as_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The final review's first finding, red: a rule naming a member, scoped by that dataset with
    no case in scope, wrote the alert, the listed party and its `SAME_AS` into the member."""
    _scoped_by_the_rules_dataset(monkeypatch)
    _s, graph, _queue, report = await _rescreen(MEMBER)
    assert report.alerts == 1
    assert {w.type: w.datasets for w in graph.written_nodes} == {
        "Person": [MEMBER],
        "Alert": [MEMBER],
    }


async def test_a_composite_named_rescreening_reads_nothing_scoped_as_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """And a rule naming the composite's own id, so scoped, read nothing: no customer, no alert,
    and nothing said."""
    _scoped_by_the_rules_dataset(monkeypatch)
    _s, _graph, queue, report = await _rescreen(BOTH)
    assert report.customers == 0 and queue.alerts == [] and report.failures == []


# --- the daily KYC sweep ----------------------------------------------------------------------


class _SweepGraph(_Graph):
    """The re-screening's graph, with the one more read the sweep makes: a customer's verifying
    documents, as the reader may see them."""

    def __init__(self, nodes: Any, edges: Any) -> None:
        super().__init__(nodes)
        self.edges = list(edges)

    async def expand(self, req: Any, principal: Principal) -> Any:
        from schemas.domain import Subgraph

        edges = [e for e in self.edges if e.source in req.node_ids and self._sees(principal, e)]
        nodes = [n for e in edges if (n := await self.get_node(e.target, principal)) is not None]
        return Subgraph(nodes=nodes, edges=edges)


async def _sweep(rule_dataset: str | None, *, with_the_store: bool = True) -> tuple[Any, ...]:
    from services.api.kyc_expiries import Lapse
    from services.api.kyc_sweep import sweep

    from schemas.domain import DocumentVerificationParams, Edge

    store = await _store()
    customer = _customer("p-1", "Elena", "Petrova", datasets=[MEMBER])
    passport = customer.model_copy(
        update={"id": "doc-1", "type": "Document",
                "properties": {"document_kind": "passport", "expires_on": "2026-11-01"}}
    )  # fmt: skip
    verified = Edge(
        id="v-1", type="VERIFIED_BY", source="p-1", target="doc-1",
        provenance=customer.provenance, handling=customer.handling, datasets=[MEMBER],
        audit={"created_at": NOW, "created_by": "loader", "revision": 1},
    )  # fmt: skip
    graph = _SweepGraph([customer, passport], [verified])
    queue = _Queue()
    rule = _rule(dataset_id=rule_dataset).model_copy(
        update={"params": DocumentVerificationParams(), "investigation_id": CASE}
    )

    class _Expiries:
        async def lapsed(self, *, after: Any, before: Any) -> list[Lapse]:
            return [Lapse(CASE, "doc-1", "p-1", date(2026, 11, 1))]

    class _CaseRules:
        async def list_active_for_case(self, case: str) -> list[TypologyRule]:
            return [rule]

    class _SweepValkey(_Queue):
        async def get(self, key: str) -> None:
            return None

        async def set(self, *args: Any, **kwargs: Any) -> bool:
            return True

    async def principal_for_owner(owner_id: str) -> Principal | None:
        return OFFICER

    report = await sweep(
        day=date(2026, 11, 7), expiries=_Expiries(), rules=_CaseRules(),  # type: ignore[arg-type]
        graph=stamping(graph, registry=store),  # type: ignore[arg-type]
        scheme=SCHEME, alert_store=queue, audit=queue, valkey=_SweepValkey(),  # type: ignore[arg-type]
        principal_for_owner=principal_for_owner, sweeper=OFFICER,
        datasets=store if with_the_store else None,
    )  # fmt: skip
    return store, graph, queue, report


@pytest.mark.parametrize("rule_dataset", [BOTH, MEMBER], ids=["composite", "member"])
async def test_the_daily_sweep_in_a_composite_case_raises_its_alert_into_the_layer(
    rule_dataset: str,
) -> None:
    store, graph, queue, report = await _sweep(rule_dataset)
    assert report.alerts == 1 and len(queue.alerts) == 1
    (alert,) = graph.written_nodes
    assert alert.type == "Alert" and alert.datasets == [_layer_of(store)]
    assert graph.nodes["p-1"].datasets == [MEMBER]


async def test_the_daily_sweep_finds_nothing_scoped_as_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Red: scoped by the rule's dataset alone, a rule naming the composite's own id reads no
    customer and raises nothing, silently; and one naming the member writes into the member."""
    _scoped_by_the_rules_dataset(monkeypatch)
    _s, _g, queue, report = await _sweep(BOTH)
    assert report.alerts == 0 and queue.alerts == []
    _s, graph, _q, _r = await _sweep(MEMBER)
    assert [w.datasets for w in graph.written_nodes] == [[MEMBER]]
