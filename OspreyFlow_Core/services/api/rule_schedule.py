"""The scheduled trigger for rules (`06_DECISIONS.md` ADR-133 decision 1, stage (d)).

A rule written as a sentence may run "on a schedule (daily or weekly)" instead of as data loads. Its
slots are read as wall-clock times in Europe/London, with the pipeline scheduler's rules for the
clock changes (`scheduler.due_slots`, ADR-110 Amendment 2).

**Each slot, judged once, as the rule's author** (ADR-036, ADR-043 — never as the system):
- **one replica per slot**: the latest due slot is claimed with Valkey `SET NX`; the slots before
  it, after downtime, are recorded *missed*, not run;
- **as its author, resolved afresh**: the author must still be able to sign in, still hold
  `deploy_rules`, and still be an Author of the rule's case (an Editor, for a rule just for them);
  otherwise the slot is *refused*, in words;
- **three refusals in a row stop the schedule**, said in words on the rule (`schedule_view`) until
  the rule is changed (a new version starts the count again); an identity provider that cannot be
  reached is a *failure*, which says nothing about the author and never stops it;
- **a rule that is not running does not run**: pending approval or retired, its schedule says so.

Every slot's outcome is kept (`TypologyRuleStore.record_rule_run`), with how many alerts it raised.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from valkey.asyncio import Valkey

from conduit_common.identity import new_id
from conduit_common.valkey_compat import reply
from principal_auth import PrincipalExchangeUnavailable, PrincipalRevoked
from schemas.domain import Principal, TypologyRule
from schemas.monitoring import ListSchedule, RuleRun, RuleRunOutcome, RuleScheduleView
from schemas.rights import Right, rights_for
from schemas.sentences import WEEKDAYS, RuleSchedule, SentenceRuleParams

from .investigations import AccessLevel, InsufficientAccessError, InvestigationNotFoundError
from .rule_evaluation import PartlyRaised
from .scheduler import DEFAULT_TIMEZONE, describe, due_slots, next_slot

log = logging.getLogger(__name__)

#: A claimed slot is remembered a week.
_CLAIM_SECONDS = 7 * 86400
#: This many refused slots in a row stop a rule's schedule (as ADR-110 decision 3 pauses a
#: recipe's).
REFUSALS_BEFORE_STOP = 3


def cron_of(schedule: RuleSchedule | ListSchedule) -> str:
    """The schedule as the pipeline scheduler's five fields: on the hour, every day or one day a
    week (cron counts Sunday as 0)."""
    day = "*" if schedule.every == "daily" else str((schedule.weekday or 1) % 7)
    return f"0 {schedule.hour} * * {day}"


def schedule_words(schedule: RuleSchedule | ListSchedule) -> str:
    """ "every day at 06:00 (Europe/London)", "every Monday at 06:00 (Europe/London)"."""
    return describe(cron_of(schedule), DEFAULT_TIMEZONE)


def _schedule_of(rule: TypologyRule) -> RuleSchedule | None:
    params = rule.params
    return params.sentence.schedule if isinstance(params, SentenceRuleParams) else None


def _just_me(rule: TypologyRule) -> bool:
    return isinstance(rule.params, SentenceRuleParams) and rule.params.sentence.scope == "just_me"


def _refused_in_a_row(rule: TypologyRule, runs: Sequence[RuleRun]) -> list[RuleRun]:
    """The refusals of the rule's current version, newest first, up to the first run that was
    not."""
    current = [r for r in sorted(runs, key=lambda r: (r.slot, r.ran_at), reverse=True)
               if r.rule_version == rule.version]  # fmt: skip
    in_a_row: list[RuleRun] = []
    for run in current:
        if run.outcome != "refused":
            break
        in_a_row.append(run)
    return in_a_row


def _core(words: str) -> str:
    """ "Refused: the rule's author, X, can no longer sign in." → "the rule's author, X, can no
    longer sign in"."""
    return words.removeprefix("Refused: ").rstrip(".")


def schedule_view(
    rule: TypologyRule, runs: Sequence[RuleRun], *, now: datetime
) -> RuleScheduleView:
    """The rule's schedule as the rules list says it: in words, with its next run, or why it will
    not run."""
    schedule = _schedule_of(rule)
    if schedule is None:
        raise ValueError("this rule runs as data loads, not on a schedule")
    said = schedule_words(schedule)
    newest_first = sorted(runs, key=lambda r: (r.slot, r.ran_at), reverse=True)
    if rule.status == "pending":
        return RuleScheduleView(
            rule_id=rule.id, schedule=said, state="waiting_for_approval",
            words="Waits for a second person's approval; it has not run.", runs=newest_first,
        )  # fmt: skip
    if rule.status == "retired":
        when = rule.retired_at.strftime("%-d %B %Y") if rule.retired_at else "an earlier date"
        return RuleScheduleView(
            rule_id=rule.id, schedule=said, state="stopped",
            words=f"Stopped: the rule was retired on {when}.", runs=newest_first,
        )  # fmt: skip
    refusals = _refused_in_a_row(rule, runs)
    if len(refusals) >= REFUSALS_BEFORE_STOP:
        return RuleScheduleView(
            rule_id=rule.id, schedule=said, state="stopped",
            words=("Stopped after three refused runs in a row; the last: "
                   f"{_core(refusals[0].words)}. Change the rule to start it again."),
            runs=newest_first,
        )  # fmt: skip
    return RuleScheduleView(
        rule_id=rule.id, schedule=said, state="scheduled",
        next_run=next_slot(cron_of(schedule), DEFAULT_TIMEZONE, after=now), runs=newest_first,
    )  # fmt: skip


class ScheduledRules(Protocol):
    async def scheduled_rules(self) -> list[TypologyRule]: ...
    async def rule_runs(self, rule_id: str, *, limit: int = 20) -> list[RuleRun]: ...
    async def last_rule_slot(self, rule_id: str) -> datetime | None: ...
    async def record_rule_run(self, run: RuleRun) -> None: ...


class _Refused(Exception):
    def __init__(self, why: str, *, outcome: RuleRunOutcome = "refused") -> None:
        super().__init__(why)
        self.outcome = outcome


@dataclass
class RuleScheduleExecutor:
    """Each tick, every running scheduled rule with a slot due is judged once, as its author."""

    rules: ScheduledRules
    valkey: Valkey
    #: `PrincipalResolver.resolve_for_owner_detailed`: raises, so the record can say which refusal.
    resolve_owner: Callable[[str], Awaitable[Principal]]
    #: The case's own level check, and its datasets (`scope_to_case`), as the author.
    check_case: Callable[[Principal, str, AccessLevel], Awaitable[Principal]]
    #: Judges the slot as the author and raises what it finds; returns how many alerts it raised.
    judge: Callable[[TypologyRule, Principal, datetime], Awaitable[int]]

    async def tick(self, now: datetime) -> None:
        for rule in await self.rules.scheduled_rules():
            try:
                await self._consider(rule, now)
            except Exception:  # noqa: BLE001 - one rule's trouble never stops the others
                log.exception("the schedule of rule %s could not be judged", rule.id)

    async def _consider(self, rule: TypologyRule, now: datetime) -> None:
        schedule = _schedule_of(rule)
        if rule.status != "active" or schedule is None:
            return
        runs = await self.rules.rule_runs(rule.id, limit=REFUSALS_BEFORE_STOP + 1)
        if len(_refused_in_a_row(rule, runs)) >= REFUSALS_BEFORE_STOP:
            return  # stopped, and said so on the rule
        after = await self.rules.last_rule_slot(rule.id) or rule.created_at
        slots = due_slots(cron_of(schedule), DEFAULT_TIMEZONE, after=after, until=now)
        if not slots:
            return
        latest = slots[-1]
        claim = f"rule-schedule:claim:{rule.id}:{latest.isoformat()}"
        if not await reply(self.valkey.set(claim, "1", nx=True, ex=_CLAIM_SECONDS)):
            return
        for missed in slots[:-1]:
            await self._record(rule, missed, rule.owner_id, "missed",
                               "Missed: the deployment was not running then; after downtime only "
                               "the latest slot runs.")  # fmt: skip
        try:
            author = await self._author(rule)
        except _Refused as refused:
            prefix = "Refused" if refused.outcome == "refused" else "Not run"
            await self._record(
                rule, latest, rule.owner_id, refused.outcome, f"{prefix}: {refused}."
            )
            return
        try:
            raised = await self.judge(rule, author, latest)
        except PartlyRaised as partly:
            # The alerts it raised before failing stand, and are counted (L2.10's carry).
            log.exception("the scheduled run of rule %s failed part-way", rule.id)
            await self._record(
                rule, latest, author.id, "failed",
                f"Failed after {partly.raised:,} alert(s) raised: {partly.cause}.",
                alerts=partly.raised,
            )  # fmt: skip
            return
        except Exception as error:  # noqa: BLE001 - recorded as failed, in words
            log.exception("the scheduled run of rule %s failed", rule.id)
            await self._record(rule, latest, author.id, "failed", f"Failed: {error}.")
            return
        period = "day" if schedule.every == "daily" else "week"
        await self._record(
            rule, latest, author.id, "ran",
            f"Ran as {author.id} over the last {period}: {raised:,} alert(s) raised.",
            alerts=raised,
        )  # fmt: skip

    async def _author(self, rule: TypologyRule) -> Principal:
        owner = rule.owner_id
        try:
            author = await self.resolve_owner(owner)
        except PrincipalRevoked as error:
            raise _Refused(f"the rule's author, {owner}, can no longer sign in") from error
        except PrincipalExchangeUnavailable as error:
            raise _Refused(
                "the identity provider could not be reached to act as the rule's author",
                outcome="failed",
            ) from error
        except Exception as error:  # noqa: BLE001 - any other refusal of the exchange
            raise _Refused(f"OspreyFlow could not act as the rule's author, {owner}") from error
        if Right.DEPLOY_RULES not in rights_for(author.roles):
            raise _Refused(f"the rule's author, {owner}, no longer holds deploy_rules")
        level, said = (
            (AccessLevel.EDITOR, "an Editor")
            if _just_me(rule)
            else (AccessLevel.AUTHOR, "an Author")
        )
        try:
            return await self.check_case(author, rule.investigation_id, level)
        except (InsufficientAccessError, InvestigationNotFoundError) as error:
            raise _Refused(
                f"the rule's author, {owner}, is no longer {said} of its case"
            ) from error

    async def _record(
        self,
        rule: TypologyRule,
        slot: datetime,
        run_as: str,
        outcome: RuleRunOutcome,
        words: str,
        *,
        alerts: int = 0,
    ) -> None:
        await self.rules.record_rule_run(
            RuleRun(
                id=new_id(),
                rule_id=rule.id,
                rule_version=rule.version,
                slot=slot,
                ran_at=datetime.now(UTC),
                run_as=run_as,
                outcome=outcome,
                alerts=alerts,
                words=words,
            )  # fmt: skip
        )


__all__ = [
    "REFUSALS_BEFORE_STOP",
    "WEEKDAYS",
    "RuleScheduleExecutor",
    "cron_of",
    "schedule_view",
    "schedule_words",
]
