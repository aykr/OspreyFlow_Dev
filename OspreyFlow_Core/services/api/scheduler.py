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

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

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
