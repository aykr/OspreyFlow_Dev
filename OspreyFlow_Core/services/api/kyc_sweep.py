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

**One failure never stops the sweep (L2.10's carry).** Each case's rules, and each customer of a
rule, are judged inside their own catch: a failure (an alert that cannot be written in a composite
case's layer, a read refused) is logged, counted in the report's `failures`, and written to the
rule's own audit (`rule_evaluation_failed`, with how many documents went unjudged), which the rule's
*Changes* lists, so a person sees it; the rest of the day's sweep goes on, and the day is closed.
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
from principal_auth import ACCESS_OUT_OF_DATE_WORDS, PrincipalAccessOutOfDate
from schemas.domain import Principal

from .alerts import AlertStore
from .audit import AuditWriter
from .dataset_scope import scope_a_monitor, set_case_datasets
from .datasets import DatasetStore
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
    datasets: DatasetStore | None = None,
    deployer_of: Callable[[str], Awaitable[Principal]] | None = None,
) -> SweepReport:
    """`deployer_of` (`resolve_for_owner_detailed`), when given, is how each rule's deployer is
    acted as, so a refusal can say why: on Entra ID, a deployer not signed in within 24 hours is
    said so (ADR-148 Amendment 16). Without it, `principal_for_owner`'s `None` is the one answer."""
    raw = await reply(valkey.get(_LAST_SWEPT))
    last = date.fromisoformat(raw.decode() if isinstance(raw, bytes) else raw) if raw else None
    report = SweepReport(day=day)
    by_case: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for lapse in await expiries.lapsed(after=last, before=day):
        by_case[lapse.investigation_id][lapse.customer_id].append(lapse.document_id)
        report.lapses += 1
    for case, customers in by_case.items():
        try:
            active = await rules.list_active_for_case(case)
        except Exception as error:  # noqa: BLE001 - one case's trouble never stops the next
            log.exception("KYC sweep: the rules of case %s could not be read", case)
            report.failures.append(f"case {case}: {type(error).__name__}")
            continue
        for rule in active:
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
            unjudged_all = sum(len(d) for d in customers.values())
            why = "its deployer could not be resolved, so it could not run as them"
            try:
                if deployer_of is None:
                    deployer = await principal_for_owner(rule.owner_id)
                else:
                    try:
                        deployer = await deployer_of(rule.owner_id)
                    except PrincipalAccessOutOfDate:
                        deployer = None
                        why = f"its deployer, {rule.owner_id}, {ACCESS_OUT_OF_DATE_WORDS}"
                    except Exception:  # noqa: BLE001 - refused or unreachable: as the None answer
                        deployer = None
                if deployer is not None and datasets is not None:
                    # As a request is, by what the case reads: in a case reading a composite its
                    # alert goes into the case's layer (ADR-099 Amendment 15 item 2).
                    deployer = await scope_a_monitor(deployer, case, rule.dataset_id, datasets)
                elif deployer is not None and rule.dataset_id is not None:
                    deployer = deployer.model_copy(update={"datasets": [rule.dataset_id]})
            except Exception as error:  # noqa: BLE001 - said, audited, and swept past
                log.exception("KYC sweep: rule %s, case %s, could not be scoped", rule.id, case)
                deployer = None
                why = f"it could not be run as its deployer ({type(error).__name__})"
            if deployer is None:
                report.failures.append(f"rule {rule.id} in case {case}: {why}")
                await _say_unjudged(audit, sweeper, case, rule.id, day, 0, unjudged_all, why)
                continue
            context = KycContext(
                graph=graph, scheme=scheme, screening=None, compute=None, today=day
            )
            raised = 0
            unjudged = 0
            try:
                for customer_id, documents in customers.items():
                    # One customer's trouble never stops the rest, nor the next case: the sweep
                    # claimed its day, and stopping here would stop at the same point every day.
                    try:
                        for finding in await judge_lapsed(
                            rule, deployer, customer_id, documents, context
                        ):
                            if not await gate.seen(finding):
                                await gate.raise_committed(finding)
                                raised += 1
                    except Exception as error:  # noqa: BLE001 - said, audited, and swept past
                        log.exception("KYC sweep: rule %s, case %s", rule.id, case)
                        unjudged += len(documents)
                        report.failures.append(
                            f"rule {rule.id} in case {case}: {type(error).__name__}"
                        )
            finally:
                set_case_datasets(None)
            report.alerts += raised
            if unjudged:
                await _say_unjudged(audit, sweeper, case, rule.id, day, raised, unjudged, None)
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


FAILED_WORDS_WITHOUT_COUNTS = (
    "The daily KYC sweep could not judge some lapsed documents for this rule; the rest of the "
    "sweep went on."
)


async def _say_unjudged(
    audit: AuditWriter,
    sweeper: Principal,
    case: str,
    rule_id: str,
    day: date,
    raised: int,
    unjudged: int,
    why: str | None,
) -> None:
    """A failure a person sees: in the rule's own audit, which *Changes* lists
    (`RULE_AUDIT_ACTIONS`). The day is closed all the same, so the lapses not judged are said here,
    by count, and are not judged again: a document that lapsed stays lapsed, and the rule's next
    load judges its customers afresh."""
    because = f": {why}" if why else ""
    await audit.record(
        principal=sweeper,
        action="rule_evaluation_failed",
        investigation_id=case,
        resolved_query={
            "rule_id": rule_id, "trigger": "daily_sweep", "day": day.isoformat(),
            "findings": raised, "documents_not_judged": unjudged,
            "words": (f"The daily KYC sweep could not judge {unjudged} lapsed document(s) for this "
                      f"rule{because}; the rest of the sweep went on."),
            # What every reader of the rule audit is told (rule 7): the documents not judged are
            # counted across every customer, not the reader's, so the number is kept for the
            # record alone (`rule_holds.readable_rule_audit`).
            "words_without_counts": FAILED_WORDS_WITHOUT_COUNTS,
        },
        result_cardinality=raised,
    )  # fmt: skip


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
