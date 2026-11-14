"""A screening list's refresh schedule (`06_DECISIONS.md` ADR-133 Amendment 3 item 4, built with
stage (d)'s scheduled trigger).

A list subscribed through its connector may be refreshed every day or every week, at an hour, read
in Europe/London. Each slot:
- **runs once**: the slot is claimed with Valkey `SET NX` and then marked on the list in Postgres,
  so neither a second replica nor a later tick runs it again; after downtime only the latest slot
  runs;
- **as the person who set the schedule**, resolved afresh, who must still hold
  `load_screening_lists` (ADR-112 L9) and still be cleared for the list's marking (ADR-146
  Amendment 7) — never as the system. Otherwise the slot is refused, recorded with the list's
  refreshes in words, and nothing is read;
- **through the one refresh** (`screening_refresh.refresh`), re-screening as each rule's deployer.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from valkey.asyncio import Valkey

from conduit_common.identity import new_id
from conduit_common.valkey_compat import reply
from ontology.handling import HandlingScheme
from principal_auth import (
    PEOPLE_SECTION,
    OwnerNotHeld,
    OwnerRecordUnavailable,
    PrincipalAccessOutOfDate,
    PrincipalRevoked,
    out_of_date_next,
    out_of_date_words,
)
from schemas.domain import Principal
from schemas.monitoring import ListSchedule
from schemas.rights import Right, rights_for
from schemas.screening import ScreeningListUpdate

from .rule_schedule import cron_of
from .scheduler import DEFAULT_TIMEZONE, due_slots
from .screening import ListClearance, ScheduledList

log = logging.getLogger(__name__)

_CLAIM_SECONDS = 7 * 86400


class ListScheduleRefused(ValueError):
    """A list schedule that cannot be kept, in words."""


def check_list_schedule(schedule: ListSchedule) -> None:
    """The checks a list schedule needs beyond its fields' own, said in the words a rule's schedule
    uses (`schemas.sentences.RuleSchedule`), so the route can answer them as words, not a bare
    422."""
    if schedule.every == "weekly" and schedule.weekday is None:
        raise ListScheduleRefused("a weekly schedule names the day of the week it runs on")
    if schedule.every == "daily" and schedule.weekday is not None:
        raise ListScheduleRefused("a daily schedule runs every day, so it names no day of the week")


class ScheduledLists(Protocol):
    async def scheduled_lists(self) -> list[ScheduledList]: ...
    async def mark_slot(self, list_name: str, slot: datetime) -> bool: ...
    async def record_update(self, update: ScreeningListUpdate) -> None: ...
    async def hidden(self, list_name: str, *, cleared: ListClearance) -> bool: ...


def owner_refusal_words(error: BaseException, owner_id: str) -> str:
    """Why a list's scheduled refresh may not run as its owner, in words: the one wording for both
    list schedulers, a subscribed list's (`ListRefreshExecutor`) and a deployment-wide list's
    (`app._deployment_list_scheduler`). On Entra ID each refusal says what happened (ADR-148
    Amendment 16): never "could not be reached", since Entra is not asked."""
    if isinstance(error, PrincipalRevoked):
        return f"the schedule's owner, {owner_id}, can no longer sign in"
    if isinstance(error, PrincipalAccessOutOfDate):
        return (
            f"the schedule's owner, {owner_id}, {out_of_date_words(error)}: "
            f"{out_of_date_next(error)}"
        )
    if isinstance(error, OwnerNotHeld):
        return f"the schedule's owner, {owner_id}, is not held in {PEOPLE_SECTION}"
    if isinstance(error, OwnerRecordUnavailable):
        return (
            f"the people store behind {PEOPLE_SECTION} could not be read to act as the "
            "schedule's owner"
        )
    return f"OspreyFlow could not act as the schedule's owner, {owner_id}"


@dataclass
class ListRefreshExecutor:
    lists: ScheduledLists
    valkey: Valkey
    #: `PrincipalResolver.resolve_for_owner_detailed`: raises, so the record can say why.
    resolve_owner: Callable[[str], Awaitable[Principal]]
    #: The one refresh, run as the given person, for the given slot.
    refresh: Callable[[str, Principal, datetime], Awaitable[ScreeningListUpdate]]
    #: The deployment's handling scheme, which the owner's clearance for the list is read in.
    scheme: HandlingScheme

    async def tick(self, now: datetime) -> None:
        for scheduled in await self.lists.scheduled_lists():
            try:
                await self._consider(scheduled, now)
            except Exception:  # noqa: BLE001 - one list's trouble never stops the others
                log.exception("the schedule of list %s could not be judged", scheduled.list_name)

    async def _consider(self, scheduled: ScheduledList, now: datetime) -> None:
        after = scheduled.last_slot or scheduled.set_at
        slots = due_slots(cron_of(scheduled.schedule), DEFAULT_TIMEZONE, after=after, until=now)
        if not slots:
            return
        latest = slots[-1]
        claim = f"list-schedule:claim:{scheduled.list_name}:{latest.isoformat()}"
        if not await reply(self.valkey.set(claim, "1", nx=True, ex=_CLAIM_SECONDS)):
            return
        if not await self.lists.mark_slot(scheduled.list_name, latest):
            return
        try:
            owner = await self.resolve_owner(scheduled.owner)
        except Exception as error:  # noqa: BLE001 - the exchange refused or unreachable: said, not raised
            await self._refused(scheduled, owner_refusal_words(error, scheduled.owner))
            return
        if Right.LOAD_SCREENING_LISTS not in rights_for(owner.roles):
            await self._refused(scheduled, f"the schedule's owner, {scheduled.owner}, no longer "
                                           "holds load_screening_lists")  # fmt: skip
            return
        # The list's marking may have been raised, or the schedule given to someone, since it was
        # set: a refresh runs only as an owner still cleared for the list (the orchestrator's
        # verification of e911b90, item 2). Recorded with the list's refreshes, which only a
        # reader cleared for the list is shown.
        if await self.lists.hidden(
            scheduled.list_name, cleared=ListClearance.of(owner, self.scheme)
        ):
            await self._refused(scheduled, f"the schedule's owner, {scheduled.owner}, is not "
                                           "cleared for the list")  # fmt: skip
            return
        await self.refresh(scheduled.list_name, owner, latest)

    async def _refused(self, scheduled: ScheduledList, why: str) -> None:
        await self.lists.record_update(
            ScreeningListUpdate(
                id=new_id(),
                list_name=scheduled.list_name,
                at=datetime.now(UTC),
                outcome="refused",
                words=f"The scheduled refresh was refused: {why}. The list was left as it was.",
                trigger="schedule",
            )  # fmt: skip
        )


__all__ = [
    "ListRefreshExecutor",
    "ListScheduleRefused",
    "check_list_schedule",
    "owner_refusal_words",
]
