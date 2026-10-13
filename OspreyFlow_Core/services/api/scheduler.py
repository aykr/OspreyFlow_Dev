"""Scheduled pipeline runs (`06_DECISIONS.md` ADR-110, with Amendment 2).

**When a schedule is due.** A schedule is a cron expression read as wall-clock times in a named time
zone (Europe/London unless it names another; decision 7). `due_slots` lists the slots in a window,
in UTC. Across the daylight-saving changes it keeps classic cron's rule, measured against croniter
6.2.4 first (which by itself gives a daily 01:30 twice on the October change): a schedule that names
its hours runs a repeated wall-clock time once, at its first occurrence; one that runs every hour
runs in both real hours; and a time that does not exist in March runs once, at the end of the gap.

**The executor** is below `due_slots`; its docstring has the rules each slot is judged by.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from valkey.asyncio import Valkey

from conduit_common.valkey_compat import reply
from ontology.handling import HandlingScheme, principal_may_view
from principal_auth import PrincipalExchangeUnavailable, PrincipalRevoked
from schemas.domain import Principal
from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus
from schemas.rights import Right, rights_for

from .investigations import InsufficientAccessError, InvestigationNotFoundError
from .recipe_runs import NotRunOutcome, RecipeRunStore
from .studio_map import resolve_source_handling

log = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "Europe/London"
#: The most often a schedule may run *(mine)*: each run is a whole load, judged and resolved.
MIN_INTERVAL = timedelta(minutes=15)

_DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


class ScheduleRefused(ValueError):
    """A schedule that cannot be kept, said in words (rule 2)."""


def _zone(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ScheduleRefused(f"{timezone!r} is not a time zone (try Europe/London)") from error


def validate_schedule(cron: str, timezone: str) -> None:
    """Refuses, in words, a schedule the executor could not keep."""
    zone = _zone(timezone)
    if not cron.strip() or not croniter.is_valid(cron) or len(cron.split()) != 5:
        raise ScheduleRefused(
            f"{cron!r} is not a schedule: give five fields — minute, hour, day of month, month, "
            "day of week — such as `0 6 * * 1-5` for weekdays at 06:00"
        )
    start = datetime(2026, 1, 5, tzinfo=zone)  # a fixed Monday, so the check never varies
    it = croniter(cron, start)
    previous = it.get_next(datetime)
    for _ in range(200):
        following = it.get_next(datetime)
        if following - previous < MIN_INTERVAL:
            raise ScheduleRefused(
                f"{cron!r} would run more often than every 15 minutes; each run is a whole load"
            )
        previous = following


def _every_hour(cron: str) -> bool:
    return cron.split()[1] in ("*", "*/1")


def due_slots(cron: str, timezone: str, *, after: datetime, until: datetime) -> list[datetime]:
    """The schedule's slots in `(after, until]`, oldest first, in UTC."""
    zone = _zone(timezone)
    it = croniter(cron, after.astimezone(zone))
    slots: list[datetime] = []
    seen_wall_times: set[datetime] = set()
    every_hour = _every_hour(cron)
    while True:
        slot = it.get_next(datetime)
        if slot > until:
            return slots
        wall = slot.replace(tzinfo=None)
        if not every_hour and wall in seen_wall_times:
            continue  # the same wall-clock time again, in October's repeated hour
        seen_wall_times.add(wall)
        slots.append(slot.astimezone(UTC))


def next_slot(cron: str, timezone: str, *, after: datetime) -> datetime:
    """The first slot after `after`, in UTC — the *next run* the Admin area shows."""
    zone = _zone(timezone)
    return croniter(cron, after.astimezone(zone)).get_next(datetime).astimezone(UTC)  # type: ignore[no-any-return]


def describe(cron: str, timezone: str) -> str:
    """The schedule in words (decision 7), for the common shapes; otherwise the expression."""
    minute, hour, day, month, weekday = cron.split()
    words: str | None = None
    if minute.isdigit() and hour == "*" and day == month == weekday == "*":
        words = (
            "every hour, on the hour" if minute == "0" else f"every hour at {int(minute)} past"
        )
    elif minute.isdigit() and hour.isdigit() and day == month == "*":
        at = f"at {int(hour):02d}:{int(minute):02d}"
        if weekday == "*":
            words = f"every day {at}"
        elif weekday == "1-5":
            words = f"every weekday {at}"
        elif weekday.isdigit() and int(weekday) <= 7:
            words = f"every {_DAYS[int(weekday) % 7]} {at}"
    return f"{words or f'on the cron schedule `{cron}`'} ({timezone})"


# --- the executor --------------------------------------------------------------------------------

#: A claimed slot is remembered a week; a run of one recipe holds its lock at most six hours.
_CLAIM_SECONDS = 7 * 86400
_LOCK_SECONDS = 6 * 3600
#: Decision 3: this many refused runs in a row pause the schedule.
REFUSALS_BEFORE_PAUSE = 3


class ScheduledRecipes(Protocol):
    async def scheduled(self) -> list[StudioRecipeDraft]: ...
    async def set_paused(self, recipe_id: str, *, paused: bool, reason: str | None) -> None: ...


class _Refused(Exception):
    """A slot that may not run, and why, in words for the ledger."""


@dataclass
class ScheduleExecutor:
    """Each tick, every scheduled recipe with a slot due is judged and, if it may, run once
    (ADR-110 decisions 2–4, Amendment 2):

    - **one replica per slot**: the latest due slot is claimed with Valkey `SET NX`; whoever wins
      it records and runs it, every other replica leaves it alone;
    - **no catch-up storm**: after downtime only the latest due slot runs; the ones before it are
      recorded *missed*;
    - **flagged is blocked**: a recipe flagged by an ontology change is recorded *blocked*;
    - **as its owner, never as the system**: the owner is resolved afresh (ADR-043) and must still
      hold `schedule_pipelines`, still be an Editor of the schedule's case, and still be cleared for
      the source; otherwise the slot is *refused*, in words, and three refusals in a row pause it;
    - **no overlap**: while a run of the recipe is still going, a newly due slot is *skipped*.
    """

    recipes: ScheduledRecipes
    runs: RecipeRunStore
    valkey: Valkey
    scheme: HandlingScheme
    #: `PrincipalResolver.resolve_for_owner_detailed`: raises rather than collapsing to `None`,
    #: so the ledger can say which refusal it was.
    resolve_owner: Callable[[str], Awaitable[Principal]]
    #: The case's own Editor check (`InvestigationStore.get_authorized`) and `scope_to_case`.
    check_case: Callable[[Principal, str], Awaitable[Principal]]
    #: `run_recipe_as` with the deployment's dependencies, as the owner, trigger `schedule`.
    run: Callable[[Principal, StudioRecipeDraft, str, datetime], Awaitable[Any]]

    async def tick(self, now: datetime) -> None:
        for recipe in await self.recipes.scheduled():
            try:
                await self._consider(recipe, now)
            except Exception:  # noqa: BLE001 - one recipe's trouble never stops the others
                log.exception("schedule of recipe %s could not be judged", recipe.recipe_id)

    async def _consider(self, recipe: StudioRecipeDraft, now: datetime) -> None:
        if recipe.schedule_paused or recipe.schedule_cron is None:
            return
        after = await self.runs.last_slot(recipe.recipe_id) or recipe.schedule_set_at
        if after is None:
            return
        zone = recipe.schedule_timezone or DEFAULT_TIMEZONE
        slots = due_slots(recipe.schedule_cron, zone, after=after, until=now)
        if not slots:
            return
        latest = slots[-1]
        claim = f"schedule:claim:{recipe.recipe_id}:{latest.isoformat()}"
        if not await reply(self.valkey.set(claim, "1", nx=True, ex=_CLAIM_SECONDS)):
            return
        for missed in slots[:-1]:
            await self._not_run(
                recipe, missed, "missed",
                "the deployment was not running then; after downtime only the latest slot runs",
            )  # fmt: skip
        if recipe.status is StudioRecipeStatus.FLAGGED:
            await self._not_run(
                recipe, latest, "blocked",
                "the ontology changed since this recipe was published; publish it again to run it",
            )  # fmt: skip
            return
        try:
            owner, case = await self._owner(recipe)
        except _Refused as refused:
            await self._not_run(recipe, latest, "refused", str(refused))
            if await self.runs.refusals_in_a_row(recipe.recipe_id) >= REFUSALS_BEFORE_PAUSE:
                await self.recipes.set_paused(
                    recipe.recipe_id,
                    paused=True,
                    reason=f"paused after three refused runs in a row; the last: {refused}",
                )
            return
        lock = f"schedule:lock:{recipe.recipe_id}"
        token = uuid4().hex
        if not await reply(self.valkey.set(lock, token, nx=True, ex=_LOCK_SECONDS)):
            await self._not_run(
                recipe, latest, "skipped", "the previous run of this recipe was still going"
            )
            return
        try:
            await self.run(owner, recipe, case, latest)
        except Exception:  # noqa: BLE001 - the ledger has it as failed, in words
            log.exception("scheduled run of recipe %s failed", recipe.recipe_id)
        finally:
            held = await reply(self.valkey.get(lock))
            if held in (token, token.encode()):
                await reply(self.valkey.delete(lock))

    async def _owner(self, recipe: StudioRecipeDraft) -> tuple[Principal, str]:
        owner_id, case = recipe.schedule_owner, recipe.schedule_case
        if owner_id is None or case is None:
            raise _Refused("the schedule has no owner; set it again from the case it runs in")
        try:
            owner = await self.resolve_owner(owner_id)
        except PrincipalRevoked as error:
            raise _Refused(f"the schedule's owner, {owner_id}, can no longer sign in") from error
        except PrincipalExchangeUnavailable as error:
            raise _Refused(
                "the identity provider could not be reached to act as the schedule's owner"
            ) from error
        except Exception as error:  # noqa: BLE001 - any other refusal of the exchange
            raise _Refused(
                f"OspreyFlow could not act as the schedule's owner, {owner_id}"
            ) from error
        if Right.SCHEDULE_PIPELINES not in rights_for(owner.roles):
            raise _Refused(
                f"the schedule's owner, {owner_id}, no longer holds schedule_pipelines"
            )
        try:
            owner = await self.check_case(owner, case)
        except (InsufficientAccessError, InvestigationNotFoundError) as error:
            raise _Refused(
                f"the schedule's owner, {owner_id}, is no longer an Editor of its case"
            ) from error
        if not principal_may_view(resolve_source_handling(recipe), owner, self.scheme):
            raise _Refused(
                f"the source is marked above the clearance of the schedule's owner, {owner_id}"
            )
        return owner, case

    async def _not_run(
        self, recipe: StudioRecipeDraft, slot: datetime, outcome: NotRunOutcome, why: str
    ) -> None:
        await self.runs.record_not_run(
            recipe_id=recipe.recipe_id,
            recipe_version=recipe.version,
            investigation_id=recipe.schedule_case or "",
            trigger="schedule",
            slot=slot,
            run_as=recipe.schedule_owner or "",
            source=resolve_source_handling(recipe),
            outcome=outcome,
            failure=why,
            now=datetime.now(UTC),
        )


async def run_every_minute(executor: ScheduleExecutor) -> None:
    """The Conduit's lifespan task (decision 2): a tick at the start of every minute."""
    while True:
        now = datetime.now(UTC)
        await asyncio.sleep(60 - now.second - now.microsecond / 1e6)
        try:
            await executor.tick(datetime.now(UTC))
        except Exception:  # noqa: BLE001 - logged; the next minute tries again
            log.exception("scheduler tick failed")
