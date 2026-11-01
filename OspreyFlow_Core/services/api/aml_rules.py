"""The new AML transaction-monitoring templates (`06_DECISIONS.md` ADR-133 decision 2, stage (c)):
four typed typologies (rule 8: parameters, never an expression), judged over a load's money
movements (`TRANSACTED` events) as the rule's deployer, through ADR-109's `RuleGate`.

- **`large_cash`** — a cash movement (`transaction_type` CASH_IN or CASH_OUT, as the rule chooses)
  at or over the threshold.
- **`high_risk_jurisdiction`** — a movement to or from an account held in a jurisdiction on the
  rule's own list. An account's jurisdiction is its IBAN's country code (ISO 13616: an IBAN's first
  two letters); an account whose number is not an IBAN has no jurisdiction here and is not judged.
- **`dormant_reactivated`** — an account in the load moving money for the first time in at least
  the rule's number of days. An account with no movement before is new, not dormant.
- **`velocity_rise`** — an account in the load whose movements (counted, or by amount) over the
  last N days run at the rule's factor or more times its own daily rate over the days before, with
  at least the rule's minimum in the last N days. An account with nothing in those days before has
  no rate to rise from and is not judged.

**As whom, and where it counts.** Only movements the deployer may read are judged
(`handling_readable`, rule 3), each transaction once however often its export was loaded. An
account's number is read through `GraphPort` as the deployer, so a jurisdiction is never read from
an account they may not see. An account's past — its last movement before, its movements in the days
before — is counted in the analytics store by `AnalyticsPort.account_activity`, with the access step
in the store's own query, so a movement the deployer may not see neither wakes an account nor sets
its baseline. Those two templates read the stored past, which holds the load's own movements only
once it has committed: they run after commit (`TypologyRuleInput`). Each finding cites the load's
movements, alerts once (`RuleGate`), and is a suggestion for a person to judge (rule 5).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime, timedelta

from ontology.handling import HandlingScheme
from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from schemas.analytics import ActivityRequest, EventFilter, EventRecord, NodeActivity
from schemas.domain import (
    DormantReactivatedParams,
    EdgeWrite,
    HighRiskJurisdictionParams,
    Interval,
    LargeCashParams,
    NodeWrite,
    Principal,
    TypologyRule,
    VelocityRiseParams,
)

from .rule_evaluation import (
    FLOW_EDGE_TYPE,
    Finding,
    _amount,
    handling_readable,
    one_per_transaction,
)

AML_TYPOLOGIES = frozenset(
    {"high_risk_jurisdiction", "large_cash", "dormant_reactivated", "velocity_rise"}
)
#: The most accounts one `account_activity` read names (`schemas.analytics.FREQUENCY_NODES_MAX`).
_CHUNK = 1000
_IBAN = re.compile(r"^([A-Z]{2})\d{2}[A-Z0-9]{1,30}$")
_CASH_WORDS = {"CASH_IN": "Cash paid in", "CASH_OUT": "Cash drawn out"}

Written = Sequence[NodeWrite | EdgeWrite]


def iban_country(value: object) -> str | None:
    """An IBAN's country code (its first two letters, ISO 13616), or `None` for a number that is
    not shaped as an IBAN. Check digits are the `iban` Knowledge Adapter's, at load."""
    if not isinstance(value, str):
        return None
    compact = re.sub(r"\s+", "", value).upper()
    found = _IBAN.match(compact)
    return found.group(1) if found else None


def _day(when: datetime) -> str:
    return f"{when.day} {when:%B %Y}"


def _money(value: float) -> str:
    return f"{value:,.0f}"


async def _accounts(
    ids: Sequence[str],
    written: Written,
    graph: GraphPort,
    scheme: HandlingScheme,
    deployer: Principal,
) -> dict[str, str]:
    """Each account's number as the deployer may read it: from the load's own writes, else the
    store. An account they may not read is absent."""
    numbers: dict[str, str] = {}
    for w in written:
        if (
            isinstance(w, NodeWrite)
            and w.id in ids
            and handling_readable(scheme, deployer, w.handling)
            and w.properties.get("account_number")
        ):
            numbers[w.id] = str(w.properties["account_number"])
    missing = [i for i in ids if i not in numbers]
    if missing:
        for node in await graph.get_nodes(missing, deployer):
            if node.properties.get("account_number"):
                numbers[node.id] = str(node.properties["account_number"])
    return numbers


def _finding(
    rule: TypologyRule,
    deployer: Principal,
    subject: str,
    refs: tuple[str, ...],
    words: str,
    events: Sequence[EventRecord],
) -> Finding:
    return Finding(
        rule=rule,
        deployer=deployer,
        typology=rule.params.typology,
        subject=subject,
        refs=refs,
        words=words,
        node_ids=sorted({e.source_id for e in events} | {e.target_id for e in events}),
        edge_ids=sorted({e.edge_id for e in events}),
        events=tuple(events),
    )


async def _activity(
    analytics: AnalyticsPort,
    deployer: Principal,
    accounts: Sequence[str],
    *,
    scope: str,
    window: Interval,
    baseline_days: int,
    amount: bool,
) -> dict[str, NodeActivity]:
    found: dict[str, NodeActivity] = {}
    for start in range(0, len(accounts), _CHUNK):
        result = await analytics.account_activity(
            ActivityRequest(
                filter=EventFilter(
                    investigation_scope=scope,
                    window=window,
                    node_ids=list(accounts[start : start + _CHUNK]),
                    edge_types=[FLOW_EDGE_TYPE],
                ),
                baseline_days=baseline_days,
                amount_property="amount" if amount else None,
            ),
            deployer,
        )
        found.update(result.nodes)
    return found


async def judge_aml(
    rule: TypologyRule,
    deployer: Principal,
    events: Sequence[EventRecord],
    written: Written,
    *,
    graph: GraphPort,
    analytics: AnalyticsPort | None,
    scheme: HandlingScheme,
    investigation_scope: str,
) -> list[Finding]:
    """The rule over this load's money movements, as `deployer`."""
    judged = list(
        one_per_transaction(
            e
            for e in events
            if e.edge_type == FLOW_EDGE_TYPE and handling_readable(scheme, deployer, e.handling)
        ).values()
    )
    if not judged:
        return []
    params = rule.params
    ends = sorted({e.source_id for e in judged} | {e.target_id for e in judged})
    names = await _accounts(ends, written, graph, scheme, deployer)

    def name(node_id: str) -> str:
        return names.get(node_id, node_id)

    if isinstance(params, LargeCashParams):
        findings = []
        for e in judged:
            kind = str(e.properties.get("transaction_type") or "")
            amount = _amount(e.properties.get("amount"))
            if kind in params.cash_types and amount is not None and amount >= params.threshold:
                words = (
                    f"{_CASH_WORDS[kind]} ({kind}) of {_money(amount)} between "
                    f"{name(e.source_id)} and {name(e.target_id)} on {_day(e.occurred_at)}, "
                    f"at or over {_money(params.threshold)}"
                )
                findings.append(
                    _finding(
                        rule, deployer, f"{e.source_id}->{e.target_id}", (e.event_id,), words, [e]
                    )
                )
        return findings

    if isinstance(params, HighRiskJurisdictionParams):
        listed = set(params.jurisdictions)
        findings = []
        for e in judged:
            flagged = [
                (end, country)
                for end in (e.source_id, e.target_id)
                if end in names and (country := iban_country(names[end])) in listed
            ]
            if not flagged:
                continue
            amount = _amount(e.properties.get("amount"))
            held = "; ".join(
                f"{name(end)} is held in {country}, on this rule's list of high-risk jurisdictions"
                for end, country in flagged
            )
            words = (
                f"A movement{f' of {_money(amount)}' if amount is not None else ''} from "
                f"{name(e.source_id)} to {name(e.target_id)} on {_day(e.occurred_at)}: {held}"
            )
            findings.append(
                _finding(rule, deployer, f"{e.source_id}->{e.target_id}", (e.event_id,), words, [e])
            )
        return findings

    if analytics is None:
        raise RuntimeError("this run has no analytics store to read the accounts' past")

    if isinstance(params, DormantReactivatedParams):
        times = [e.occurred_at for e in judged]
        activity = await _activity(
            analytics, deployer, ends, scope=investigation_scope,
            window=Interval(valid_from=min(times), valid_to=max(times)), baseline_days=1,
            amount=False,
        )  # fmt: skip
        findings = []
        for account in ends:
            found = activity.get(account)
            if found is None or found.first_in_window is None or found.last_before_window is None:
                continue  # no movement before: new, not dormant
            gap = found.first_in_window - found.last_before_window
            if gap < timedelta(days=params.dormant_days):
                continue
            own = [e for e in judged if account in (e.source_id, e.target_id)]
            words = (
                f"{name(account)} moved money on {_day(found.first_in_window)} after "
                f"{gap.days:,} days without a movement (dormant for {params.dormant_days:,} days "
                f"or more); its last movement before was on {_day(found.last_before_window)}"
            )
            findings.append(
                _finding(
                    rule,
                    deployer,
                    account,
                    (account, found.first_in_window.isoformat()),
                    words,
                    own,
                )  # fmt: skip
            )
        return findings

    assert isinstance(params, VelocityRiseParams)
    end = max(e.occurred_at for e in judged)
    window = Interval(valid_from=end - timedelta(days=params.recent_days), valid_to=end)
    by_amount = params.measure == "amount"
    activity = await _activity(
        analytics, deployer, ends, scope=investigation_scope, window=window,
        baseline_days=params.baseline_days, amount=by_amount,
    )  # fmt: skip
    findings = []
    for account in ends:
        found = activity.get(account)
        if found is None or found.baseline_count == 0 or found.recent_count < params.min_recent:
            continue
        recent = (found.recent_total or 0.0) if by_amount else float(found.recent_count)
        before = (found.baseline_total or 0.0) if by_amount else float(found.baseline_count)
        if before <= 0:
            continue
        ratio = (recent / params.recent_days) / (before / params.baseline_days)
        if ratio < params.factor:
            continue
        own = [
            e
            for e in judged
            if account in (e.source_id, e.target_id) and e.occurred_at >= window.valid_from
        ]
        if not own:
            continue  # nothing of this load's in the last days: not this load's finding
        measured = f"{_money(recent)} moved" if by_amount else f"{found.recent_count:,} movements"
        prior = _money(before) if by_amount else f"{found.baseline_count:,}"
        what = "amount" if by_amount else "rate"
        words = (
            f"{name(account)}: {measured} in the {params.recent_days} days to {_day(end)}, "
            f"{ratio:.1f} times its own daily {what} over the {params.baseline_days} days before "
            f"({prior} in those days) — the rule asks for {params.factor:g} times or more"
        )
        findings.append(
            _finding(rule, deployer, account, (account, end.date().isoformat()), words, own)
        )
    return findings


__all__ = ["AML_TYPOLOGIES", "iban_country", "judge_aml"]
