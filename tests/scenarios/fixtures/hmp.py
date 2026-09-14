"""Synthetic HMP-shaped incident fixture — `08_ACCEPTANCE_SCENARIOS.md`
Scenario A's own statistical finding, reduced to its event-table shape.
Phase 2 builds this shape and proves it against `AnalyticsPort` directly;
the site-grid/control-point geospatial mechanism Scenario A actually walks
through (uploading an aerial image, placing control points, drawing a
10×10 grid) is Phase 5's, built on `Location` entities the analyst places
by hand, not on this fixture's raw lat/lon. Building the statistical shape
now means Scenario A inherits a fixture already known to carry it, rather
than discovering only in Phase 5 that "~52%"/"~34%" were never actually
true of the generated data.

The three properties `08_ACCEPTANCE_SCENARIOS.md` A2/A4 assert:

- **Four hotspot yards account for ~52% of incidents** — assertable via a
  `CATEGORICAL` histogram bucketed by the `yard` property.
- **Two intra-day peaks are visible** — via a `WEEKDAY_HOUR` histogram.
- **Saturday and Sunday together are ~34% of the total** — same histogram.

Built as an exact multiset (yard, weekday, hour) rather than drawn from
weighted random choice: a fixture's own claimed statistics must be exactly
what generating it produces, not merely their expectation over many
draws — 262 weighted coin-flips can land anywhere near 52%, but 262 items
built from a 136/262 split cannot land anywhere else. Each of the three
dimensions is independently shuffled before being zipped together, so no
spurious correlation between yard, weekday and hour is introduced by
construction.

**A stated limitation: these `EventRecord`s are analytics-only, with no
graph side.** `edge_id`/`source_id`/`target_id` are synthetic strings with
no corresponding `GraphPort` node or edge — `01_DOMAIN_MODEL.md` §3 says
`edge_id` "ties it back to the summarised graph edge it is one occurrence
of," which is not true here. This is the right scope cut for what Phase 2
needs (proving the statistical shape against `AnalyticsPort` alone), but
it means this fixture cannot stand in for anything that needs graph/
analytics consistency, unlike the CDR fixture, which builds both sides
together through the real recipe engine. `07_BUILD_PLAN.md`'s Phase 5
scope records giving this fixture a graph side as its own item, rather
than leaving the gap implicit.
"""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, time, timedelta

from schemas.analytics import EventRecord
from schemas.domain import Handling

TOTAL_INCIDENTS = 262

#: Four hotspot yards summing to 136/262 ≈ 51.9% of incidents; six other
#: yards each with fewer incidents than every hotspot yard, so "the four
#: hotspot cells are the top four by count" is unambiguous.
_YARD_COUNTS: tuple[tuple[str, int], ...] = (
    ("A", 36),
    ("B", 35),
    ("C", 35),
    ("D", 30),
    ("E", 21),
    ("F", 21),
    ("G", 21),
    ("H", 21),
    ("I", 21),
    ("J", 21),
)
HOTSPOT_YARDS = frozenset({"A", "B", "C", "D"})

#: Two intra-day peak windows (morning exercise, evening association),
#: four hours total each running well above the off-peak baseline.
PEAK_HOURS = (8, 9, 18, 19)
_PEAK_HOUR_COUNT = 36  # each of the four peak hours
_OFF_PEAK_HOURS = tuple(h for h in range(24) if h not in PEAK_HOURS)  # 20 hours
_OFF_PEAK_BASE_COUNT = 6
_OFF_PEAK_HOURS_AT_BASE = 18  # the other 2 off-peak hours get one fewer

#: 0 = Monday … 6 = Sunday, matching `HistogramBucket.weekday`. Saturday
#: and Sunday together are 89/262 ≈ 34.0% of the total.
_WEEKDAY_COUNTS: tuple[tuple[int, int], ...] = (
    (0, 35),
    (1, 35),
    (2, 35),
    (3, 35),
    (4, 33),
    (5, 45),  # Saturday
    (6, 44),  # Sunday
)

_ITEM_TYPES = ("mobile_phone", "tobacco", "blade", "synthetic_drugs", "alcohol")

#: One small fixed site — coordinates are illustrative only (Scenario A's
#: real geospatial mechanism is the Phase 5 site grid, not these lat/lons),
#: kept far enough apart that they are at least distinguishable, never
#: intended to be binned by `geo_bins`.
_YARD_COORDINATES: dict[str, tuple[float, float]] = {
    yard: (51.5 + 0.0007 * i, -0.6 + 0.0009 * i)
    for i, (yard, _count) in enumerate(_YARD_COUNTS)
}

_WINDOW_START = date(2026, 1, 5)  # a Monday
_WINDOW_END = date(2026, 3, 6)  # 61 days later — "a two-month window"


def _hour_multiset() -> list[int]:
    hours = [h for h in PEAK_HOURS for _ in range(_PEAK_HOUR_COUNT)]
    for i, hour in enumerate(_OFF_PEAK_HOURS):
        count = _OFF_PEAK_BASE_COUNT if i < _OFF_PEAK_HOURS_AT_BASE else _OFF_PEAK_BASE_COUNT - 1
        hours.extend([hour] * count)
    assert len(hours) == TOTAL_INCIDENTS
    return hours


def _yard_multiset() -> list[str]:
    yards = [yard for yard, count in _YARD_COUNTS for _ in range(count)]
    assert len(yards) == TOTAL_INCIDENTS
    return yards


def _weekday_multiset() -> list[int]:
    weekdays = [weekday for weekday, count in _WEEKDAY_COUNTS for _ in range(count)]
    assert len(weekdays) == TOTAL_INCIDENTS
    return weekdays


def _dates_by_weekday() -> dict[int, list[date]]:
    by_weekday: dict[int, list[date]] = {i: [] for i in range(7)}
    current = _WINDOW_START
    while current <= _WINDOW_END:
        by_weekday[current.weekday()].append(current)
        current += timedelta(days=1)
    return by_weekday


def generate_hmp_events(
    seed: int = 42, *, investigation_scope: str = "case-hmp-fixture"
) -> list[EventRecord]:
    rng = random.Random(seed)

    yards = _yard_multiset()
    weekdays = _weekday_multiset()
    hours = _hour_multiset()
    rng.shuffle(yards)
    rng.shuffle(weekdays)
    rng.shuffle(hours)

    dates_by_weekday = _dates_by_weekday()
    # A per-weekday cursor, so incidents on the same weekday spread across
    # every date that weekday actually occurs on in the window rather than
    # all landing on its first occurrence.
    cursor = dict.fromkeys(dates_by_weekday, 0)

    handling = Handling(
        classification="OFFICIAL",
        handling_code="P",
        originator="hmp-hollywood",
        owning_unit="hmp-hollywood",
    )

    events: list[EventRecord] = []
    for i in range(TOTAL_INCIDENTS):
        yard = yards[i]
        weekday = weekdays[i]
        hour = hours[i]

        available = dates_by_weekday[weekday]
        incident_date = available[cursor[weekday] % len(available)]
        cursor[weekday] += 1

        minute = rng.randrange(60)
        second = rng.randrange(60)
        occurred_at = datetime.combine(
            incident_date, time(hour=hour, minute=minute, second=second), tzinfo=UTC
        )
        lat, lon = _YARD_COORDINATES[yard]
        item_type = _ITEM_TYPES[i % len(_ITEM_TYPES)]

        events.append(
            EventRecord(
                event_id=f"hmp-incident-{i:04d}",
                edge_id=f"hmp-edge-{i:04d}",
                edge_type="PRESENT_AT",
                source_id=f"hmp-subject-{i:04d}",
                target_id=f"hmp-location-{yard}",
                occurred_at=occurred_at,
                lat=lat,
                lon=lon,
                properties={"yard": yard, "item_type": item_type},
                investigation_scope=investigation_scope,
                handling=handling,
            )
        )
    return events
