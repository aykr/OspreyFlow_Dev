"""`datetime` — `01_DOMAIN_MODEL.md` §7. Mixed formats and local times
collapse to UTC; a value with no recoverable offset is rejected, never
guessed — and so is an ambiguous date order. `03/04/2026` is April in the
UK and March in the US, and with both in scope (ADR-017) there is no safe
default: a wrong order is silent, looks like ordinary data, and shifts
every temporal finding built on it (peak hours, weekend elevation, convoy
tolerances). The connector profile declares `date_order` (`dmy` or `mdy`);
a value that needs it and finds it unset is rejected, named and counted,
exactly like a missing offset.

Parsing tries strict ISO 8601 first (`2014-03-11T19:42:01Z` and its
variants are unambiguous by construction — year-month-day, never
reordered) — no `date_order` is needed for these regardless of whether one
is configured. Only the fallback, locale-flexible parse for a non-ISO
format actually consults it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil import parser as _dateutil_parser

from .errors import NormalisationError

DateOrder = Literal["dmy", "mdy"]


@dataclass(frozen=True)
class DatetimeResult:
    utc: datetime
    #: The UTC offset actually in force for the original value, e.g.
    #: "+01:00" during British Summer Time, "+00:00" outside it — computed
    #: from the resolved zone at that specific date, not a fixed constant,
    #: so it is correct either side of a DST boundary.
    original_offset: str


def _offset_string(value: datetime) -> str:
    offset = value.utcoffset()
    assert offset is not None
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    return f"{sign}{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _try_iso(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _try_locale_flexible(raw: str, *, date_order: DateOrder) -> datetime | None:
    try:
        return _dateutil_parser.parse(raw, dayfirst=(date_order == "dmy"))
    except (ValueError, OverflowError, TypeError):
        return None


def datetime_adapter(
    raw: str, *, tz: str | None = None, date_order: DateOrder | None = None
) -> DatetimeResult:
    stripped = raw.strip()
    parsed = _try_iso(stripped)
    if parsed is None:
        if date_order is None:
            raise NormalisationError(
                "datetime",
                raw,
                "ambiguous date order — the connector profile must declare "
                "date_order (dmy or mdy) before a non-ISO date can be parsed",
            )
        parsed = _try_locale_flexible(stripped, date_order=date_order)
        if parsed is None:
            raise NormalisationError("datetime", raw, "unrecognised datetime format")

    if parsed.tzinfo is not None:
        return DatetimeResult(utc=parsed.astimezone(UTC), original_offset=_offset_string(parsed))

    if tz is None:
        raise NormalisationError(
            "datetime", raw, "no timezone offset in the value and no default `tz` configured"
        )
    try:
        zone: tzinfo = ZoneInfo(tz)
    except ZoneInfoNotFoundError as exc:
        raise NormalisationError("datetime", raw, f"unknown timezone {tz!r}") from exc
    localised = parsed.replace(tzinfo=zone)
    return DatetimeResult(utc=localised.astimezone(UTC), original_offset=_offset_string(localised))
