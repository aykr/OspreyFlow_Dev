"""The daily KYC expiry sweep (`06_DECISIONS.md` ADR-109 phase F, ruling 7) — the deployment's
first periodic pass (ADR-037 is delta-only: a document lapsing is the clock passing, never a write
the change stream could carry).

**Bounded.** It reads only what `kyc_expiries` says lapsed since the last sweep (one date range),
and for each case with an active `document_verification` rule, re-checks those customers through
the store as the rule's deployer (`kyc_rules.judge_lapsed`), raising a review alert where no valid
verifying document remains. **Once a day, one replica:** the Conduit's lifespan task claims the day
with a Valkey `SET NX` before sweeping, so two replicas never sweep the same day. **Disclosed:** a
day the deployment is down is swept the next time it runs, since the range runs from the last
sweep's day, not from yesterday.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from valkey.asyncio import Valkey

from conduit_common.valkey_compat import reply
from ontology.handling import HandlingScheme
from ports.graph import GraphPort
from schemas.domain import Principal

from .alerts import AlertStore
from .audit import AuditWriter
from .kyc_expiries import KycExpiryStore
from .kyc_rules import KycContext, judge_lapsed
from .rule_evaluation import RuleGate
from .typology_rules import TypologyRuleStore

_LAST_SWEPT = "kyc:sweep:last"
_CLAIM = "kyc:sweep:claimed:"
log = logging.getLogger(__name__)


@dataclass
class SweepReport:
    day: date
    lapses: int = 0
    alerts: int = 0
    failures: list[str] = field(default_factory=list)


async def sweep(
    *,
    day: date,
    expiries: KycExpiryStore,
    rules: TypologyRuleStore,
    graph: GraphPort,
    scheme: HandlingScheme,
    alert_store: AlertStore,
    audit: AuditWriter,
    valkey: Valkey,
    principal_for_owner: Callable[[str], Awaitable[Principal | None]],
    sweeper: Principal,
) -> SweepReport:
    raw = await reply(valkey.get(_LAST_SWEPT))
    last = date.fromisoformat(raw.decode() if isinstance(raw, bytes) else raw) if raw else None
    report = SweepReport(day=day)
    by_case: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for lapse in await expiries.lapsed(after=last, before=day):
        by_case[lapse.investigation_id][lapse.customer_id].append(lapse.document_id)
        report.lapses += 1
    for case, customers in by_case.items():
        for rule in await rules.list_active_for_case(case):
            if rule.params.typology != "document_verification":
                continue
            gate = RuleGate(
                rules=[rule],
                investigation_id=case,
                graph=graph,
                analytics=None,
                scheme=scheme,
                alert_store=alert_store,
                audit=audit,
                valkey=valkey,
                principal_for_owner=principal_for_owner,
                loader=sweeper,
            )
            deployer = await principal_for_owner(rule.owner_id)
            if deployer is None:
                report.failures.append(f"rule {rule.id}: its deployer could not be resolved")
                continue
            if rule.dataset_id is not None:
                deployer = deployer.model_copy(update={"datasets": [rule.dataset_id]})
            context = KycContext(
                graph=graph, scheme=scheme, screening=None, compute=None, today=day
            )
            raised = 0
            for customer_id, documents in customers.items():
                for finding in await judge_lapsed(rule, deployer, customer_id, documents, context):
                    if not await gate.seen(finding):
                        await gate.raise_committed(finding)
                        raised += 1
            report.alerts += raised
            await audit.record(
                principal=sweeper,
                action="rule_evaluated",
                investigation_id=case,
                resolved_query={"rule_id": rule.id, "trigger": "daily_sweep",
                                "day": day.isoformat(), "findings": raised},
                result_cardinality=raised,
            )  # fmt: skip
    await reply(valkey.set(_LAST_SWEPT, day.isoformat()))
    return report


async def run_daily(
    claim_valkey: Valkey,
    run: Callable[[date], Awaitable[SweepReport]],
    *,
    every_seconds: float = 3600,
) -> None:
    """The lifespan task: each hour, claim today (one replica wins) and, if won, sweep it."""
    while True:
        today = datetime.now(UTC).date()
        try:
            claimed = await reply(
                claim_valkey.set(f"{_CLAIM}{today.isoformat()}", "1", nx=True, ex=2 * 86400)
            )
            if claimed:
                done = await run(today)
                log.info("KYC sweep %s: %s lapses, %s alerts", today, done.lapses, done.alerts)
        except Exception:  # noqa: BLE001 - a failed sweep is logged and retried tomorrow
            log.exception("KYC sweep for %s failed", today)
        await asyncio.sleep(every_seconds)


__all__ = ["SweepReport", "run_daily", "sweep"]
