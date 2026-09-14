"""Proves the HMP fixture (`tests/scenarios/fixtures/hmp.py`) actually
carries the statistical shape `08_ACCEPTANCE_SCENARIOS.md` A2/A4 assert,
against a real `AnalyticsPort` adapter — not a docstring claim nobody
checks. `08_ACCEPTANCE_SCENARIOS.md`'s own Scenario A (the site grid, the
control points, the 10×10 grid) is Phase 5's; this is the event-table
shape underneath it, built and verified now so Phase 5 inherits a fixture
already known to be correct.

No live service needed — DuckDB is in-process, seeded directly from the
generated `EventRecord`s, the same `duckdb_adapter` helper the
`AnalyticsPort` conformance suite uses.
"""

from __future__ import annotations

from tests.scenarios.fixtures.hmp import (
    HOTSPOT_YARDS,
    PEAK_HOURS,
    TOTAL_INCIDENTS,
    generate_hmp_events,
)

from adapters.analytics_duckdb.testing import duckdb_adapter
from ontology.handling import load_uk_le_scheme
from schemas.analytics import EventFilter, HistogramBucketing, HistogramRequest
from schemas.domain import Principal

CLEARED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="hmp-hollywood")


async def test_four_hotspot_yards_account_for_around_52_percent_of_incidents() -> None:
    events = generate_hmp_events()
    assert len(events) == TOTAL_INCIDENTS

    scheme = load_uk_le_scheme()
    async with duckdb_adapter(events, scheme) as analytics:
        hist = await analytics.histogram(
            HistogramRequest(
                filter=EventFilter(investigation_scope="case-hmp-fixture"),
                bucketing=HistogramBucketing.CATEGORICAL,
                field="yard",
            ),
            CLEARED,
        )

    assert hist.total == TOTAL_INCIDENTS
    by_yard = {b.label: b.count for b in hist.buckets}
    hotspot_total = sum(by_yard[y] for y in HOTSPOT_YARDS)
    hotspot_share = hotspot_total / hist.total

    assert 0.50 <= hotspot_share <= 0.54
    # "The four hotspot cells are the top four by count" — not merely
    # four yards that happen to sum close to 52%.
    ranked = sorted(by_yard.items(), key=lambda kv: kv[1], reverse=True)
    assert {yard for yard, _count in ranked[:4]} == HOTSPOT_YARDS


async def test_two_intra_day_peaks_are_visible() -> None:
    events = generate_hmp_events()
    scheme = load_uk_le_scheme()
    async with duckdb_adapter(events, scheme) as analytics:
        hist = await analytics.histogram(
            HistogramRequest(
                filter=EventFilter(investigation_scope="case-hmp-fixture"),
                bucketing=HistogramBucketing.WEEKDAY_HOUR,
            ),
            CLEARED,
        )

    by_hour: dict[int, int] = {}
    for bucket in hist.buckets:
        assert bucket.hour is not None
        by_hour[bucket.hour] = by_hour.get(bucket.hour, 0) + bucket.count

    peak_counts = [by_hour[h] for h in PEAK_HOURS]
    off_peak_counts = [count for hour, count in by_hour.items() if hour not in PEAK_HOURS]

    # Every peak hour clearly outruns every off-peak hour — "visible", not
    # a statistical technicality.
    assert min(peak_counts) > max(off_peak_counts) * 3


async def test_weekend_is_around_34_percent_of_the_total() -> None:
    events = generate_hmp_events()
    scheme = load_uk_le_scheme()
    async with duckdb_adapter(events, scheme) as analytics:
        hist = await analytics.histogram(
            HistogramRequest(
                filter=EventFilter(investigation_scope="case-hmp-fixture"),
                bucketing=HistogramBucketing.WEEKDAY_HOUR,
            ),
            CLEARED,
        )

    weekend_total = sum(b.count for b in hist.buckets if b.weekday in (5, 6))
    weekend_share = weekend_total / hist.total

    assert 0.32 <= weekend_share <= 0.36


async def test_the_fixture_is_deterministic_across_calls() -> None:
    """Seeded and deterministic (`CLAUDE.md` rule 9) — a re-run must
    reproduce the identical fixture, not merely the same statistics."""
    first = generate_hmp_events()
    second = generate_hmp_events()
    assert [e.model_dump() for e in first] == [e.model_dump() for e in second]
