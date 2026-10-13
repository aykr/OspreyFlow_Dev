"""ADR-110 decisions 2 and 7: when a schedule is due. A schedule names wall-clock times in a named
time zone (Europe/London by default), so the two daylight-saving changes are where it can go wrong.

Measured on croniter 6.2.4 before this was written: across the October change a daily 01:30 comes
out twice (01:30 BST, then 01:30 GMT). The rule kept here is classic cron's: a schedule that names
its hours runs a repeated wall-clock time once; one that runs every hour runs in both real hours. In
March a time that does not exist runs at the end of the gap, once.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from services.api.scheduler import ScheduleRefused, describe, due_slots, validate_schedule

LONDON = ZoneInfo("Europe/London")


def _local(*args: int) -> datetime:
    return datetime(*args, tzinfo=LONDON)


def test_a_daily_schedule_is_due_once_a_day_and_slots_are_utc() -> None:
    slots = due_slots("0 6 * * *", "Europe/London", after=_local(2026, 6, 1, 12),
                      until=_local(2026, 6, 4, 12))  # fmt: skip
    assert slots == [_local(2026, 6, d, 6).astimezone(UTC) for d in (2, 3, 4)]
    assert all(s.tzinfo is UTC for s in slots)


def test_the_window_is_after_exclusive_and_until_inclusive() -> None:
    at_six = _local(2026, 6, 2, 6)
    assert due_slots("0 6 * * *", "Europe/London", after=at_six, until=at_six) == []
    assert due_slots(
        "0 6 * * *", "Europe/London", after=at_six - timedelta(seconds=1), until=at_six
    ) == [at_six.astimezone(UTC)]


def test_a_daily_time_in_the_repeated_october_hour_runs_once() -> None:
    slots = due_slots("30 1 * * *", "Europe/London", after=_local(2026, 10, 24, 12),
                      until=_local(2026, 10, 26, 12))  # fmt: skip
    assert slots == [
        datetime(2026, 10, 25, 0, 30, tzinfo=UTC),  # 01:30 BST, the first of the two
        datetime(2026, 10, 26, 1, 30, tzinfo=UTC),  # 01:30 GMT
    ]


def test_an_hourly_schedule_runs_in_both_real_hours_of_the_october_change() -> None:
    after = datetime(2026, 10, 24, 23, 30, tzinfo=UTC)
    until = datetime(2026, 10, 25, 2, 30, tzinfo=UTC)
    slots = due_slots("0 * * * *", "Europe/London", after=after, until=until)
    assert slots == [datetime(2026, 10, 25, h, tzinfo=UTC) for h in (0, 1, 2)]


def test_a_daily_time_in_the_missing_march_hour_runs_once_at_the_end_of_the_gap() -> None:
    slots = due_slots("30 1 * * *", "Europe/London", after=_local(2026, 3, 28, 12),
                      until=_local(2026, 3, 30, 12))  # fmt: skip
    assert slots == [
        datetime(2026, 3, 29, 1, 0, tzinfo=UTC),  # 02:00 BST: 01:30 GMT never happened
        datetime(2026, 3, 30, 0, 30, tzinfo=UTC),  # 01:30 BST
    ]


def test_an_hourly_schedule_has_no_slot_in_the_missing_march_hour() -> None:
    after = datetime(2026, 3, 28, 23, 30, tzinfo=UTC)
    until = datetime(2026, 3, 29, 2, 30, tzinfo=UTC)
    slots = due_slots("0 * * * *", "Europe/London", after=after, until=until)
    assert slots == [datetime(2026, 3, 29, h, tzinfo=UTC) for h in (0, 1, 2)]


def test_a_weekday_schedule_skips_the_weekend() -> None:
    slots = due_slots("0 6 * * 1-5", "Europe/London", after=_local(2026, 6, 5, 12),
                      until=_local(2026, 6, 9, 12))  # fmt: skip
    assert [s.astimezone(LONDON).day for s in slots] == [8, 9]


@pytest.mark.parametrize(
    ("cron", "zone", "words"),
    [
        ("61 * * * *", "Europe/London", "not a schedule"),
        ("every day", "Europe/London", "not a schedule"),
        ("", "Europe/London", "not a schedule"),
        ("0 6 * * *", "Mars/Olympus", "not a time zone"),
        ("* * * * *", "Europe/London", "more often than every 15 minutes"),
        ("*/5 * * * *", "Europe/London", "more often than every 15 minutes"),
    ],
)
def test_a_schedule_it_cannot_keep_is_refused_in_words(cron: str, zone: str, words: str) -> None:
    with pytest.raises(ScheduleRefused, match=words):
        validate_schedule(cron, zone)


@pytest.mark.parametrize(
    ("cron", "words"),
    [
        ("0 6 * * *", "every day at 06:00"),
        ("30 7 * * 1-5", "every weekday at 07:30"),
        ("0 * * * *", "every hour, on the hour"),
        ("15 9 * * 1", "every Monday at 09:15"),
        ("0 6 1 * *", "on the cron schedule `0 6 1 * *`"),
    ],
)
def test_a_schedule_is_explained_in_words(cron: str, words: str) -> None:
    assert describe(cron, "Europe/London") == f"{words} (Europe/London)"
