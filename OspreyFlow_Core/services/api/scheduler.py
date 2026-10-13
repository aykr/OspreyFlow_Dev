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
import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from valkey.asyncio import Valkey

from conduit_common.identity import new_id
from conduit_common.valkey_compat import reply
from ontology.handling import HandlingScheme, principal_may_view
from principal_auth import PrincipalExchangeUnavailable, PrincipalRevoked
from schemas.domain import Alert, AlertMode, Principal
from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus
from schemas.rights import Right, rights_for

from .investigations import InsufficientAccessError, InvestigationNotFoundError
from .recipe_runs import NotRunOutcome, RecipeRunStore, RunTrigger
from .studio_map import resolve_source_handling

if TYPE_CHECKING:
    from .folder_watch import WatchedFile

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


def next_slots(cron: str, timezone: str, *, after: datetime, count: int = 5) -> list[datetime]:
    """The next `count` slots after `after`, as the executor will keep them (October's repeated
    wall-clock time once), in UTC — what the Studio shows before a schedule is saved."""
    slots: list[datetime] = []
    window = timedelta(days=8)
    start = after
    while len(slots) < count:
        found = due_slots(cron, timezone, after=start, until=start + window)
        slots.extend(found)
        start = found[-1] if found else start + window
    return slots[:count]


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


def schedule_notice(
    owner_id: str, recipe: StudioRecipeDraft, words: str, now: datetime
) -> Alert:
    """Decision 10's notice (Amendment 3, point 1): an alert in the owner's own inbox, carrying its
    words and no referent, and no typology — so the case team's queue, which reads typology alerts
    only, never shows it. `rule_id` names the recipe as `schedule:<recipe id>`."""
    return Alert(
        id=new_id(),
        rule_id=f"{NOTICE_RULE_PREFIX}{recipe.recipe_id}",
        owner_id=owner_id,
        mode=AlertMode.FULL,
        referent_node_ids=[],
        investigation_id=recipe.schedule_case,
        created_at=now,
        words=words,
    )


#: The `rule_id` prefix of a schedule notice; the Glass's inbox reads it as a notice, not a match.
NOTICE_RULE_PREFIX = "schedule:"


# --- the executor --------------------------------------------------------------------------------

#: A claimed slot is remembered a week; a run of one recipe holds its lock at most six hours.
_CLAIM_SECONDS = 7 * 86400
_LOCK_SECONDS = 6 * 3600
#: Decision 3: this many refused runs in a row pause the schedule.
REFUSALS_BEFORE_PAUSE = 3


class ScheduledRecipes(Protocol):
    async def scheduled(self) -> list[StudioRecipeDraft]: ...
    async def set_paused(self, recipe_id: str, *, paused: bool, reason: str | None) -> None: ...


class RunAs(Protocol):
    """`run_recipe_as` with the deployment's dependencies, as the owner: trigger `schedule` for a
    slot, `manual` for the Admin area's *Run now* (`slot` `None`), `watch` for a file
    (`source_file`, read from its location)."""

    async def __call__(
        self,
        owner: Principal,
        recipe: StudioRecipeDraft,
        case: str,
        slot: datetime | None,
        source_file: WatchedFile | None = None,
    ) -> Any: ...


class ScheduleRunRefused(ValueError):
    """The Admin area's *Run now* refused, in words (ADR-110 Amendment 3, point 2)."""


class _Refused(Exception):
    """A slot that may not run, and why, in words for the ledger. `about_the_owner` is false for a
    refusal that says nothing about the owner (Amendment 3), which never pauses the schedule."""

    def __init__(self, why: str, *, about_the_owner: bool = True) -> None:
        super().__init__(why)
        self.about_the_owner = about_the_owner


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

    A recipe's **folder watch** (decision 5, Amendment 4) is judged in the same tick: the earliest
    waiting file it has not taken is claimed (Valkey `SET NX`, then the ledger), under the recipe's
    lock, and run as the owner with the same checks; one file a tick; a file that waits while a run
    is going is not taken; a flagged recipe's files wait; a refused or failed file is not retried.
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
    run: RunAs
    #: Decision 10: a notice in the owner's own inbox when a scheduled run fails or is refused.
    notify: Callable[[str, StudioRecipeDraft, str], Awaitable[None]] | None = None
    #: Amendment 4: the files waiting in the recipe's folder (`folder_watch.waiting_files`).
    watch_files: Callable[[StudioRecipeDraft, datetime], Awaitable[list[WatchedFile]]] | None = None

    async def tick(self, now: datetime) -> None:
        for recipe in await self.recipes.scheduled():
            try:
                await self._consider(recipe, now)
            except Exception:  # noqa: BLE001 - one recipe's trouble never stops the others
                log.exception("schedule of recipe %s could not be judged", recipe.recipe_id)

    async def _consider(self, recipe: StudioRecipeDraft, now: datetime) -> None:
        if recipe.schedule_paused:
            return
        if recipe.schedule_cron is not None:
            await self._consider_slot(recipe, now)
        if recipe.schedule_watch is not None and self.watch_files is not None:
            await self._consider_watch(recipe, now)

    async def _consider_slot(self, recipe: StudioRecipeDraft, now: datetime) -> None:
        assert recipe.schedule_cron is not None
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
            await self._not_run(
                recipe, latest, "refused", str(refused), counts=refused.about_the_owner
            )
            await self._tell_owner(recipe, f"{self._due(recipe, latest)} was refused: {refused}")
            await self._pause_if_refused_again(recipe, refused)
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
        except Exception as error:  # noqa: BLE001 - the ledger has it as failed, in words
            log.exception("scheduled run of recipe %s failed", recipe.recipe_id)
            await self._tell_owner(recipe, f"{self._due(recipe, latest)} failed: {error}")
        finally:
            await self._release(lock, token)

    async def _consider_watch(self, recipe: StudioRecipeDraft, now: datetime) -> None:
        if recipe.status is StudioRecipeStatus.FLAGGED:
            return  # its files wait until it is published again (Amendment 4, point 6)
        assert self.watch_files is not None
        taken = await self.runs.watched_files(recipe.recipe_id)
        waiting = [f for f in await self.watch_files(recipe, now) if f.identity not in taken]
        if not waiting:
            return
        lock = f"schedule:lock:{recipe.recipe_id}"
        token = uuid4().hex
        if not await reply(self.valkey.set(lock, token, nx=True, ex=_LOCK_SECONDS)):
            return  # a run is going; the file waits, untaken
        try:
            file = waiting[0]
            digest = hashlib.sha256(file.identity.encode()).hexdigest()
            claim = f"schedule:watch:{recipe.recipe_id}:{digest}"
            if not await reply(self.valkey.set(claim, "1", nx=True, ex=_CLAIM_SECONDS)):
                return
            words = f"The run of {recipe.label} on the file {file.name}"
            try:
                owner, case = await self._owner(recipe)
                if recipe.dataset_id not in (owner.datasets or []):
                    # Rule 4: the folder is the dataset's, read only through a case that has it.
                    raise _Refused(
                        f"the recipe's dataset, {recipe.dataset_id}, is no longer in the case the "
                        "watch was set in"
                    )
            except _Refused as refused:
                await self._not_run(
                    recipe, None, "refused", str(refused), counts=refused.about_the_owner,
                    trigger="watch", source_file=file.identity,
                )  # fmt: skip
                await self._tell_owner(recipe, f"{words} was refused: {refused}")
                await self._pause_if_refused_again(recipe, refused)
                return
            try:
                await self.run(owner, recipe, case, None, file)
            except Exception as error:  # noqa: BLE001 - the ledger has it as failed, in words
                log.exception("watched run of recipe %s failed", recipe.recipe_id)
                await self._tell_owner(recipe, f"{words} failed: {error}")
        finally:
            await self._release(lock, token)

    async def _release(self, lock: str, token: str) -> None:
        held = await reply(self.valkey.get(lock))
        if held in (token, token.encode()):
            await reply(self.valkey.delete(lock))

    async def _pause_if_refused_again(self, recipe: StudioRecipeDraft, refused: _Refused) -> None:
        in_a_row = await self.runs.refusals_in_a_row(recipe.recipe_id)
        if refused.about_the_owner and in_a_row >= REFUSALS_BEFORE_PAUSE:
            await self.recipes.set_paused(
                recipe.recipe_id,
                paused=True,
                reason=f"paused after three refused runs in a row; the last: {refused}",
            )

    async def run_now(self, recipe: StudioRecipeDraft) -> Any:
        """The Admin area's *Run now* (Amendment 3, point 2): at once, as the schedule's owner, with
        every check a scheduled slot gets — refused in words if the owner may not run it, or while
        a run of the recipe is still going."""
        try:
            owner, case = await self._owner(recipe)
        except _Refused as refused:
            raise ScheduleRunRefused(str(refused)) from refused
        lock = f"schedule:lock:{recipe.recipe_id}"
        token = uuid4().hex
        if not await reply(self.valkey.set(lock, token, nx=True, ex=_LOCK_SECONDS)):
            raise ScheduleRunRefused("the previous run of this recipe is still going")
        try:
            return await self.run(owner, recipe, case, None)
        finally:
            await self._release(lock, token)

    @staticmethod
    def _due(recipe: StudioRecipeDraft, slot: datetime) -> str:
        zone = _zone(recipe.schedule_timezone or DEFAULT_TIMEZONE)
        due = slot.astimezone(zone).strftime("%-d %B %Y at %H:%M")
        return f"The scheduled run of {recipe.label} due {due}"

    async def _tell_owner(self, recipe: StudioRecipeDraft, words: str) -> None:
        if self.notify is None or recipe.schedule_owner is None:
            return
        try:
            await self.notify(recipe.schedule_owner, recipe, words)
        except Exception:  # noqa: BLE001 - a notice that cannot be written is logged, not raised
            log.exception("could not tell the owner of recipe %s", recipe.recipe_id)

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
                "the identity provider could not be reached to act as the schedule's owner",
                about_the_owner=False,
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
        self,
        recipe: StudioRecipeDraft,
        slot: datetime | None,
        outcome: NotRunOutcome,
        why: str,
        *,
        counts: bool = True,
        trigger: RunTrigger = "schedule",
        source_file: str | None = None,
    ) -> None:
        await self.runs.record_not_run(
            recipe_id=recipe.recipe_id,
            recipe_version=recipe.version,
            investigation_id=recipe.schedule_case or "",
            trigger=trigger,
            source_file=source_file,
            slot=slot,
            run_as=recipe.schedule_owner or "",
            source=resolve_source_handling(recipe),
            outcome=outcome,
            failure=why,
            now=datetime.now(UTC),
            counts_toward_pause=counts,
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
