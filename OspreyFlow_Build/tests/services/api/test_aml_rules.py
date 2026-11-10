"""The new AML transaction-monitoring templates (`spec/06_DECISIONS.md` ADR-133 decision 2, stage (c)):
a high-risk jurisdiction, large cash, a dormant account reactivated and a sudden rise in velocity —
each a typed typology (rule 8), judged through ADR-109's `RuleGate` as the rule's deployer.

The analytics store is the real DuckDB adapter, in memory, holding the accounts' past movements, so
"its own past" is read through `AnalyticsPort.account_activity` with the access step in its query;
the graph is a stand-in that reads each account through the access predicate, as the adapter does;
the queue, the audit and the signature set are recorders.

What a mistake would do, and the case that catches it:
- a cash amount under the threshold, or a transfer, alerted — `test_large_cash_alerts_at_or_over_the_threshold_only`;
- a jurisdiction read from an account the deployer may not see (rule 3) —
  `test_a_high_risk_jurisdiction_is_read_only_from_an_account_the_deployer_may_see`;
- a new account called dormant, or a movement the deployer may not see counted as one —
  `test_a_dormant_account_is_one_that_moved_before_and_not_for_the_days_given`;
- a rise judged against what the deployer may not see, or with no baseline —
  `test_a_rise_in_velocity_is_against_the_accounts_own_visible_baseline`;
- a movement the deployer may not see judged at all — `test_a_movement_the_deployer_may_not_see_is_not_judged`;
- the same finding alerted twice — `test_each_finding_alerts_once`;
- a template whose past is read before commit — `test_an_account_against_its_past_runs_after_commit_only`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import duckdb
import pytest
from pydantic import ValidationError
from services.api.rule_evaluation import RuleGate, handling_readable

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table
from ontology.handling import load_uk_le_scheme
from schemas.analytics import EventRecord
from schemas.domain import (
    Alert,
    AuditStub,
    Handling,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    TypologyRule,
    TypologyRuleInput,
)

SCHEME = load_uk_le_scheme()
CASE = "case-ledger"
NOW = datetime(2026, 9, 1, 12, tzinfo=UTC)
# Each holds a right to have written a rule (ADR-146 Amendment 6 decision 13): Analyst's deploy_rules.
AUTHOR = Principal(id="aml-author", clearance="OFFICIAL", org_unit="unit-a", roles=["analyst"])
CLEARED = Principal(id="aml-cleared", clearance="SECRET", org_unit="unit-a", roles=["analyst"])


def _handling(classification: str = "OFFICIAL") -> Handling:
    return Handling(classification=classification, handling_code="P", originator="unit-a", owning_unit="unit-a")


def _account(node_id: str, iban: str, marking: str = "OFFICIAL") -> Node:
    return Node(
        id=node_id, type="Account", properties={"account_number": iban},
        provenance=Provenance(state=ProvenanceState.ASSERTED, first_seen=NOW,
                              sources=[SourceRef(document_id="accounts.csv", locator="row 1", excerpt_hash="")]),
        handling=_handling(marking), audit=AuditStub(created_at=NOW, created_by="loader"),
    )  # fmt: skip


ACCOUNTS = [
    _account("acc-gb", "GB29 NWBK 6016 1331 9268 19"),
    _account("acc-gb2", "GB94 BARC 2003 5538 2998 12"),
    _account("acc-xa", "XA12 SYNT 0000 0000 0001"),
    _account("acc-xa-secret", "XA98 SYNT 0000 0000 0099", marking="SECRET"),
    _account("acc-new", "GB33 HBUK 4012 7612 3456 01"),
]

_n = 0


def _moved(source: str, target: str, at: datetime, amount: float, kind: str = "TRANSFER",
           marking: str = "OFFICIAL") -> EventRecord:  # fmt: skip
    global _n
    _n += 1
    return EventRecord(event_id=f"ev-{_n:04d}", edge_id=f"e-{source}-{target}-{_n}", edge_type="TRANSACTED",
                       source_id=source, target_id=target, occurred_at=at,
                       properties={"amount": amount, "transaction_type": kind},
                       investigation_scope=CASE, handling=_handling(marking))  # fmt: skip


class _Graph:
    """Reads an account as the adapter does: hidden from a reader it may not be seen by; writes the
    Alert node a case rule writes, recorded."""

    def __init__(self, nodes: Sequence[Node]) -> None:
        self.nodes = {n.id: n for n in nodes}
        self.written: list[Any] = []

    async def get_nodes(self, node_ids: Sequence[str], principal: Principal) -> list[Node]:
        return [self.nodes[i] for i in node_ids
                if i in self.nodes and handling_readable(SCHEME, principal, self.nodes[i].handling)]  # fmt: skip

    async def get_node(self, node_id: str, principal: Principal) -> Node | None:
        found = await self.get_nodes([node_id], principal)
        return found[0] if found else None

    async def get_edges(self, edge_ids: Sequence[str], principal: Principal) -> list[Any]:
        return []

    async def begin_transaction(self) -> str:
        return "tx"

    async def commit_transaction(self, tx: str) -> None:
        return None

    async def rollback_transaction(self, tx: str) -> None:
        return None

    async def upsert_nodes(self, nodes: Sequence[Any], tx: str) -> list[str]:
        self.written.extend(nodes)
        return [n.id for n in nodes]

    async def upsert_edges(self, edges: Sequence[Any], tx: str) -> list[str]:
        self.written.extend(edges)
        return [e.id for e in edges]


class _Recorder:
    def __init__(self) -> None:
        self.alerts: list[Alert] = []
        self.audit: list[dict[str, Any]] = []
        self.signatures: set[str] = set()

    async def save(self, alert: Alert, handlings: Any = None) -> None:
        self.alerts.append(alert)

    async def record(self, **entry: Any) -> None:
        self.audit.append(entry)

    async def sismember(self, key: str, value: str) -> int:
        return int(value in self.signatures)

    async def sadd(self, key: str, value: str) -> int:
        self.signatures.add(value)
        return 1


def _rule(params: dict[str, Any], owner: str = AUTHOR.id, trigger: str = "post_commit") -> TypologyRule:
    spec = TypologyRuleInput.model_validate({"name": params["typology"], "params": params, "trigger": trigger})
    return TypologyRule(**spec.model_dump(), id=f"rule-{params['typology']}", investigation_id=CASE,
                        owner_id=owner, created_at=NOW)  # fmt: skip


async def _judge(rule: TypologyRule, load: Sequence[EventRecord], past: Sequence[EventRecord] = (),
                 *, deployer: Principal = AUTHOR, recorder: _Recorder | None = None) -> list[Alert]:  # fmt: skip
    con = duckdb.connect(":memory:")
    create_events_table(con)
    analytics = AnalyticsDuckDBAdapter(con, SCHEME)
    await analytics.load_events([*past, *load])  # after commit, the load's events are stored too
    recorder = recorder or _Recorder()

    async def principal_for_owner(owner_id: str) -> Principal | None:
        return deployer if owner_id == rule.owner_id else None

    gate = RuleGate(rules=[rule], investigation_id=CASE, graph=_Graph(ACCOUNTS), analytics=analytics,  # type: ignore[arg-type]
                    scheme=SCHEME, alert_store=recorder, audit=recorder, valkey=recorder,  # type: ignore[arg-type]
                    principal_for_owner=principal_for_owner, loader=AUTHOR)  # fmt: skip
    notes = await gate.post_commit(list(load), load_id="load-1", written=[])
    assert not [n for n in notes if "could not run" in n], notes
    return recorder.alerts


# --- large cash ----------------------------------------------------------------------------------


async def test_large_cash_alerts_at_or_over_the_threshold_only() -> None:
    rule = _rule({"typology": "large_cash", "threshold": 10_000})
    load = [_moved("acc-gb", "acc-gb2", NOW, 12_500, "CASH_IN"),
            _moved("acc-gb", "acc-gb2", NOW, 10_000, "CASH_OUT"),
            _moved("acc-gb", "acc-gb2", NOW, 9_999, "CASH_IN"),
            _moved("acc-gb", "acc-gb2", NOW, 50_000, "TRANSFER")]  # fmt: skip
    alerts = await _judge(rule, load)
    assert len(alerts) == 2
    assert all(a.typology == "large_cash" for a in alerts)
    words = sorted(a.words or "" for a in alerts)
    assert words[0].startswith("Cash drawn out (CASH_OUT) of 10,000") and "at or over 10,000" in words[0]
    assert words[1].startswith("Cash paid in (CASH_IN) of 12,500")
    assert "GB29 NWBK 6016 1331 9268 19" in words[1]
    only_in = _rule({"typology": "large_cash", "threshold": 10_000, "cash_types": ["CASH_IN"]})
    assert len(await _judge(only_in, load)) == 1


# --- a high-risk jurisdiction --------------------------------------------------------------------


async def test_a_high_risk_jurisdiction_is_read_only_from_an_account_the_deployer_may_see() -> None:
    rule = _rule({"typology": "high_risk_jurisdiction", "jurisdictions": ["xa", "XC"]})
    load = [_moved("acc-gb", "acc-xa", NOW, 4_200),
            _moved("acc-gb", "acc-gb2", NOW, 4_200),
            _moved("acc-gb", "acc-xa-secret", NOW, 4_200)]  # fmt: skip
    (alert,) = await _judge(rule, load)
    assert alert.typology == "high_risk_jurisdiction"
    assert set(alert.referent_node_ids) == {"acc-gb", "acc-xa"}
    assert alert.words is not None and "held in XA, on this rule's list of high-risk jurisdictions" in alert.words
    # A reader cleared to see the SECRET account finds the second.
    assert len(await _judge(rule, load, deployer=CLEARED)) == 2


def test_a_jurisdiction_is_a_two_letter_code() -> None:
    with pytest.raises(ValidationError, match="“XAN” is not a two-letter country code"):
        _rule({"typology": "high_risk_jurisdiction", "jurisdictions": ["XAN"]})
    with pytest.raises(ValidationError):
        _rule({"typology": "high_risk_jurisdiction", "jurisdictions": []})


# --- a dormant account reactivated ---------------------------------------------------------------


async def test_a_dormant_account_is_one_that_moved_before_and_not_for_the_days_given() -> None:
    rule = _rule({"typology": "dormant_reactivated", "dormant_days": 180})
    past = [_moved("acc-gb", "acc-gb2", NOW - timedelta(days=243), 100),        # acc-gb: 243 days quiet
            _moved("acc-xa", "acc-gb2", NOW - timedelta(days=200), 100),
            _moved("acc-xa", "acc-xa-secret", NOW - timedelta(days=30), 100, marking="SECRET")]  # fmt: skip
    load = [_moved("acc-gb", "acc-new", NOW, 900), _moved("acc-xa", "acc-new", NOW, 900)]
    # acc-gb2 moved 243 and 200 days ago too, but it is not in the load: a load's accounts are judged.
    alerts = await _judge(rule, load, past)
    starts = sorted((a.words or "").split(" moved money")[0] for a in alerts)
    # acc-new has never moved before: new, not dormant.
    assert starts == ["GB29 NWBK 6016 1331 9268 19", "XA12 SYNT 0000 0000 0001"], [a.words for a in alerts]
    gb = next(a for a in alerts if (a.words or "").startswith("GB29"))
    assert gb.typology == "dormant_reactivated" and gb.words is not None
    assert "on 1 September 2026 after 243 days without a movement (dormant for 180 days or more)" in gb.words
    # acc-xa's SECRET movement 30 days ago, which its author may not see, does not wake it; a
    # reader who may see it finds acc-xa was never dormant.
    cleared = await _judge(rule, load, past, deployer=CLEARED)
    assert sorted((a.words or "").split(" moved money")[0] for a in cleared) == ["GB29 NWBK 6016 1331 9268 19"]


# --- a sudden rise in velocity -------------------------------------------------------------------


async def test_a_rise_in_velocity_is_against_the_accounts_own_visible_baseline() -> None:
    rule = _rule({"typology": "velocity_rise", "recent_days": 7, "baseline_days": 90, "factor": 3,
                  "min_recent": 5})  # fmt: skip
    # acc-gb: 9 movements over the 90 days before (0.1 a day), then 6 in the last 7 (0.86 a day).
    past = [_moved("acc-gb", "acc-gb2", NOW - timedelta(days=10 + 9 * i), 50) for i in range(9)]
    # acc-xa: steady — 90 over the 90 days before, then 7 in 7.
    past += [_moved("acc-xa", "acc-gb2", NOW - timedelta(days=8, hours=i * 21), 50) for i in range(90)]
    # acc-xa-secret's baseline is SECRET: its author sees no baseline, so judges no rise.
    past += [_moved("acc-xa-secret", "acc-gb2", NOW - timedelta(days=30), 50, marking="SECRET")]
    load = [_moved("acc-gb", "acc-gb2", NOW - timedelta(days=i), 50) for i in range(6)]
    load += [_moved("acc-xa", "acc-gb2", NOW - timedelta(days=i), 50) for i in range(7)]
    load += [_moved("acc-xa-secret", "acc-new", NOW - timedelta(days=i), 50) for i in range(6)]
    alerts = await _judge(rule, load, past)
    (alert,) = alerts
    assert alert.typology == "velocity_rise" and "acc-gb" in alert.referent_node_ids
    assert alert.words is not None and alert.words.startswith(
        "GB29 NWBK 6016 1331 9268 19: 6 movements in the 7 days to 1 September 2026")
    assert "8.6 times its own daily rate over the 90 days before (9 in those days)" in alert.words
    assert alert.words.endswith("the rule asks for 3 times or more")
    fewer = _rule({"typology": "velocity_rise", "recent_days": 7, "baseline_days": 90, "factor": 3, "min_recent": 7})
    assert await _judge(fewer, load, past) == []


# --- access, once, and when -----------------------------------------------------------------------


async def test_a_movement_the_deployer_may_not_see_is_not_judged() -> None:
    rule = _rule({"typology": "large_cash", "threshold": 10_000})
    assert await _judge(rule, [_moved("acc-gb", "acc-gb2", NOW, 90_000, "CASH_IN", marking="SECRET")]) == []


async def test_each_finding_alerts_once() -> None:
    rule = _rule({"typology": "large_cash", "threshold": 10_000})
    load = [_moved("acc-gb", "acc-gb2", NOW, 12_500, "CASH_IN")]
    recorder = _Recorder()
    await _judge(rule, load, recorder=recorder)
    await _judge(rule, load, recorder=recorder)
    assert len(recorder.alerts) == 1


def test_an_account_against_its_past_runs_after_commit_only() -> None:
    for typology in ("dormant_reactivated", "velocity_rise"):
        with pytest.raises(ValidationError, match="runs after each load commits"):
            _rule({"typology": typology}, trigger="pre_commit")
    assert _rule({"typology": "large_cash", "threshold": 1}, trigger="pre_commit").trigger == "pre_commit"
