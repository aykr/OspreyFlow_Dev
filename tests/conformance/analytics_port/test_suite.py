"""`AnalyticsPort` conformance suite — `docs/07_BUILD_PLAN.md` Phase 2,
`docs/04_VAULT_BACKEND.md` §6, `docs/00_ARCHITECTURE.md` §2.2,
`docs/01_DOMAIN_MODEL.md` §9.

Parametrised over `ANALYTICS_PORT_ADAPTERS` in `tests/conformance/registry.py`
— each entry's `context(events)` seeds a fresh store from this test's own
`EventRecord` fixtures.

The existence-leak tests (`test_unauthorised_*`) follow the same shape as
`graph_port`'s: a "hidden" fixture — a SECRET-classified or unit-restricted
event an OFFICIAL-cleared analyst cannot see — must not shift a single
histogram bucket or geo-bin count. A leak here would mean the aggregate
differs only because the hidden event exists, which is exactly what must
never be observable.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ulid import ULID

from schemas.analytics import (
    BaselineRequest,
    CrossFilterDimension,
    CrossFilterRequest,
    EventFilter,
    EventRecord,
    GeoBinRequest,
    HistogramBucketing,
    HistogramRequest,
)
from schemas.domain import Handling, Interval, Principal
from tests.conformance.registry import ANALYTICS_PORT_ADAPTERS, AnalyticsAdapterFactory

pytestmark = pytest.mark.parametrize("factory", ANALYTICS_PORT_ADAPTERS, ids=str)

INVESTIGATION = "case-1"

OFFICIAL = Principal(id="analyst-official", clearance="OFFICIAL", org_unit="unit-1")
CLEARED = Principal(id="analyst-secret", clearance="SECRET", org_unit="unit-1")


def _handling(
    classification: str,
    *,
    handling_code: str = "P",
    owning_unit: str = "unit-1",
    originator: str = "unit-1",
) -> Handling:
    return Handling(
        classification=classification,
        handling_code=handling_code,
        owning_unit=owning_unit,
        originator=originator,
    )


def _event(
    *,
    occurred_at: datetime,
    edge_type: str = "COMMUNICATED_WITH",
    source_id: str = "a",
    target_id: str = "b",
    classification: str = "OFFICIAL",
    handling_code: str = "P",
    owning_unit: str = "unit-1",
    originator: str = "unit-1",
    lat: float | None = None,
    lon: float | None = None,
    cell_site: str | None = None,
    direction: str | None = None,
    properties: dict[str, object] | None = None,
    investigation_scope: str = INVESTIGATION,
) -> EventRecord:
    return EventRecord(
        event_id=str(ULID()),
        edge_id="e1",
        edge_type=edge_type,
        source_id=source_id,
        target_id=target_id,
        occurred_at=occurred_at,
        cell_site=cell_site,
        lat=lat,
        lon=lon,
        direction=direction,
        properties=properties or {},
        investigation_scope=investigation_scope,
        handling=_handling(
            classification,
            handling_code=handling_code,
            owning_unit=owning_unit,
            originator=originator,
        ),
    )


def _filter(**kwargs: object) -> EventFilter:
    return EventFilter(investigation_scope=INVESTIGATION, **kwargs)  # type: ignore[arg-type]


# --- EventFilter's own dimensions --------------------------------------------


async def test_event_filter_investigation_scope_isolates_other_investigations(
    factory: AnalyticsAdapterFactory,
) -> None:
    """`04_VAULT_BACKEND.md` §2 partitions the event tables by
    `(investigation_scope, month)` — the multi-tenancy boundary itself,
    untested until now. An event under a different scope must not count
    towards this one's histogram, the same way a different `owning_unit`
    must not."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    events = [
        _event(occurred_at=now, investigation_scope="case-1"),
        _event(occurred_at=now, investigation_scope="case-2"),
    ]
    async with factory.context(events) as adapter:
        req = HistogramRequest(
            filter=EventFilter(investigation_scope="case-1"),
            bucketing=HistogramBucketing.FIXED_INTERVAL,
            interval_seconds=3600,
        )
        hist = await adapter.histogram(req, CLEARED)
        assert hist.total == 1


async def test_event_filter_node_ids_restricts_to_events_touching_those_entities(
    factory: AnalyticsAdapterFactory,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    events = [
        _event(occurred_at=now, source_id="a", target_id="b"),
        _event(occurred_at=now, source_id="c", target_id="d"),
    ]
    async with factory.context(events) as adapter:
        req = HistogramRequest(
            filter=_filter(node_ids=["a"]),
            bucketing=HistogramBucketing.FIXED_INTERVAL,
            interval_seconds=3600,
        )
        hist = await adapter.histogram(req, CLEARED)
        assert hist.total == 1

        # Matches on either endpoint, not only source.
        req_target = req.model_copy(update={"filter": _filter(node_ids=["d"])})
        assert (await adapter.histogram(req_target, CLEARED)).total == 1

        req_neither = req.model_copy(update={"filter": _filter(node_ids=["z"])})
        assert (await adapter.histogram(req_neither, CLEARED)).total == 0


async def test_event_filter_edge_types_restricts_to_matching_edges(
    factory: AnalyticsAdapterFactory,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    events = [
        _event(occurred_at=now, edge_type="COMMUNICATED_WITH"),
        _event(occurred_at=now, edge_type="TRANSACTED"),
    ]
    async with factory.context(events) as adapter:
        req = HistogramRequest(
            filter=_filter(edge_types=["TRANSACTED"]),
            bucketing=HistogramBucketing.FIXED_INTERVAL,
            interval_seconds=3600,
        )
        hist = await adapter.histogram(req, CLEARED)
        assert hist.total == 1


async def test_histogram_categorical_buckets_by_cell_site(
    factory: AnalyticsAdapterFactory,
) -> None:
    """`direction` is exercised elsewhere; `cell_site` — also a declared
    top-level categorical field — was written and never read back through
    any aggregation until now."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    events = [
        _event(occurred_at=now, cell_site="CELL-001"),
        _event(occurred_at=now, cell_site="CELL-001"),
        _event(occurred_at=now, cell_site="CELL-002"),
    ]
    async with factory.context(events) as adapter:
        req = HistogramRequest(
            filter=_filter(), bucketing=HistogramBucketing.CATEGORICAL, field="cell_site"
        )
        hist = await adapter.histogram(req, CLEARED)
        by_label = {b.label: b.count for b in hist.buckets}
        assert by_label == {"CELL-001": 2, "CELL-002": 1}


# --- histogram: fixed_interval -----------------------------------------------


async def test_histogram_fixed_interval_returns_correct_counts(
    factory: AnalyticsAdapterFactory,
) -> None:
    events = [
        _event(occurred_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC)),
        _event(occurred_at=datetime(2026, 1, 1, 10, 30, tzinfo=UTC)),
        _event(occurred_at=datetime(2026, 1, 1, 11, 15, tzinfo=UTC)),
    ]
    async with factory.context(events) as adapter:
        req = HistogramRequest(
            filter=_filter(), bucketing=HistogramBucketing.FIXED_INTERVAL, interval_seconds=3600
        )
        hist = await adapter.histogram(req, CLEARED)
        assert hist.total == 3
        assert sorted(b.count for b in hist.buckets) == [1, 2]


async def test_histogram_empty_window_returns_zero_not_an_error(
    factory: AnalyticsAdapterFactory,
) -> None:
    events = [_event(occurred_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC))]
    async with factory.context(events) as adapter:
        window = Interval(
            valid_from=datetime(2020, 1, 1, tzinfo=UTC), valid_to=datetime(2020, 1, 2, tzinfo=UTC)
        )
        req = HistogramRequest(
            filter=_filter(window=window),
            bucketing=HistogramBucketing.FIXED_INTERVAL,
            interval_seconds=3600,
        )
        hist = await adapter.histogram(req, CLEARED)
        assert hist.total == 0
        assert hist.buckets == []


async def test_histogram_single_event_window_returns_one(
    factory: AnalyticsAdapterFactory,
) -> None:
    only = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    events = [_event(occurred_at=only)]
    async with factory.context(events) as adapter:
        req = HistogramRequest(
            filter=_filter(), bucketing=HistogramBucketing.FIXED_INTERVAL, interval_seconds=3600
        )
        hist = await adapter.histogram(req, CLEARED)
        assert hist.total == 1
        assert len(hist.buckets) == 1
        assert hist.buckets[0].count == 1


async def test_histogram_fixed_interval_counts_correctly_across_a_dst_boundary(
    factory: AnalyticsAdapterFactory,
) -> None:
    """Every timestamp here is UTC (`01_DOMAIN_MODEL.md` §7's datetime
    normaliser converts to UTC at ingest) and bucketing is epoch-second
    arithmetic, never a local-civil-time conversion — so a window
    spanning the UK's autumn clock change must count exactly as a window
    that does not, with no hour duplicated or dropped."""
    # 2026-10-25 01:30 UTC and 02:30 UTC straddle the moment UK clocks
    # went back (01:00 UTC) — a naive local-time bucketing would land
    # both of these in an ambiguous or duplicated local hour.
    events = [
        _event(occurred_at=datetime(2026, 10, 25, 1, 30, tzinfo=UTC)),
        _event(occurred_at=datetime(2026, 10, 25, 2, 30, tzinfo=UTC)),
    ]
    async with factory.context(events) as adapter:
        req = HistogramRequest(
            filter=_filter(), bucketing=HistogramBucketing.FIXED_INTERVAL, interval_seconds=3600
        )
        hist = await adapter.histogram(req, CLEARED)
        assert hist.total == 2
        assert len(hist.buckets) == 2
        assert all(b.count == 1 for b in hist.buckets)


# --- histogram: weekday_hour (the HMP cyclical view, 02_GLASS_FRONTEND.md §3.4) --


async def test_histogram_weekday_hour_folds_into_a_cyclical_grid(
    factory: AnalyticsAdapterFactory,
) -> None:
    same_hour_two_weeks_apart = [
        datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
        datetime(2026, 1, 12, 9, 0, tzinfo=UTC),
    ]
    a_different_day = datetime(2026, 1, 10, 15, 0, tzinfo=UTC)
    events = [_event(occurred_at=ts) for ts in (*same_hour_two_weeks_apart, a_different_day)]
    async with factory.context(events) as adapter:
        req = HistogramRequest(filter=_filter(), bucketing=HistogramBucketing.WEEKDAY_HOUR)
        hist = await adapter.histogram(req, CLEARED)
        by_cell = {(b.weekday, b.hour): b.count for b in hist.buckets}
        assert by_cell[(same_hour_two_weeks_apart[0].weekday(), 9)] == 2
        assert by_cell[(a_different_day.weekday(), 15)] == 1
        assert hist.total == 3


# --- histogram: categorical (cross_filter's non-temporal dimension) ----------


async def test_histogram_categorical_buckets_by_a_top_level_field(
    factory: AnalyticsAdapterFactory,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    events = [
        _event(occurred_at=now, direction="inbound"),
        _event(occurred_at=now, direction="inbound"),
        _event(occurred_at=now, direction="outbound"),
    ]
    async with factory.context(events) as adapter:
        req = HistogramRequest(
            filter=_filter(), bucketing=HistogramBucketing.CATEGORICAL, field="direction"
        )
        hist = await adapter.histogram(req, CLEARED)
        by_label = {b.label: b.count for b in hist.buckets}
        assert by_label == {"inbound": 2, "outbound": 1}


# --- geo_bins -----------------------------------------------------------------


async def test_geo_bins_server_side_bins_points_and_excludes_null_coordinates(
    factory: AnalyticsAdapterFactory,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    events = [
        _event(occurred_at=now, lat=51.5, lon=-0.1),
        _event(occurred_at=now, lat=51.5001, lon=-0.0999),  # same coarse cell
        _event(occurred_at=now, lat=None, lon=None),  # no coordinates at all
    ]
    async with factory.context(events) as adapter:
        req = GeoBinRequest(filter=_filter(), precision=4)
        bins = await adapter.geo_bins(req, CLEARED)
        assert sum(b.count for b in bins) == 2  # the null-coordinate event is excluded, not errored
        assert len(bins) == 1


async def test_geo_bins_are_equal_area_not_equal_degree(
    factory: AnalyticsAdapterFactory,
) -> None:
    """A degree of longitude at 55°N is about 57% the width, on the
    ground, of one at the equator — an equal-*degree* grid gives the UK
    materially narrower bins than the US at the same precision, which
    makes a cross-region density comparison wrong. Two points 15° of
    longitude apart at 55°N must land in the *same* bin at precision 4
    (bin width there is ~19.6°, `step / cos(55°)`) — an equal-degree grid
    (bin width 11.25° everywhere) would have split them into two."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    events = [
        _event(occurred_at=now, lat=55.0, lon=0.0),
        _event(occurred_at=now, lat=55.0, lon=15.0),  # 15 degrees of longitude east
    ]
    async with factory.context(events) as adapter:
        req = GeoBinRequest(filter=_filter(), precision=4)
        bins = await adapter.geo_bins(req, CLEARED)
        assert len(bins) == 1
        assert bins[0].count == 2


# --- baseline -------------------------------------------------------------------


async def test_baseline_compares_two_windows_and_never_divides_by_zero(
    factory: AnalyticsAdapterFactory,
) -> None:
    baseline_window = Interval(
        valid_from=datetime(2026, 1, 1, tzinfo=UTC), valid_to=datetime(2026, 1, 2, tzinfo=UTC)
    )
    comparison_window = Interval(
        valid_from=datetime(2026, 1, 8, tzinfo=UTC), valid_to=datetime(2026, 1, 9, tzinfo=UTC)
    )
    events = [
        _event(occurred_at=datetime(2026, 1, 1, 10, tzinfo=UTC)),
        *[_event(occurred_at=datetime(2026, 1, 8, h, tzinfo=UTC)) for h in range(4)],
    ]
    async with factory.context(events) as adapter:
        req = BaselineRequest(
            filter=_filter(),
            baseline_window=baseline_window,
            comparison_window=comparison_window,
            bucketing=HistogramBucketing.FIXED_INTERVAL,
            interval_seconds=3600,
        )
        result = await adapter.baseline(req, CLEARED)
        assert result.baseline_count == 1
        assert result.comparison_count == 4
        assert result.ratio == 4.0
        # Both windows are 24 hours, bucketed hourly — 24 buckets each, so
        # the per-bucket rate is the count divided by 24, not by the
        # window count directly. Computed and never checked until now.
        assert result.baseline_rate_per_bucket == pytest.approx(1 / 24)
        assert result.comparison_rate_per_bucket == pytest.approx(4 / 24)

        # An empty baseline window must report a null ratio, never raise
        # or silently divide by zero.
        empty_baseline = Interval(
            valid_from=datetime(2019, 1, 1, tzinfo=UTC), valid_to=datetime(2019, 1, 2, tzinfo=UTC)
        )
        req_empty = req.model_copy(update={"baseline_window": empty_baseline})
        empty_result = await adapter.baseline(req_empty, CLEARED)
        assert empty_result.baseline_count == 0
        assert empty_result.ratio is None


# --- cross_filter ---------------------------------------------------------------


async def test_cross_filter_returns_every_dimension_against_the_same_filter(
    factory: AnalyticsAdapterFactory,
) -> None:
    now = datetime(2026, 1, 1, 10, tzinfo=UTC)
    events = [
        _event(occurred_at=now, direction="inbound"),
        _event(occurred_at=now, direction="outbound"),
    ]
    async with factory.context(events) as adapter:
        req = CrossFilterRequest(
            filter=_filter(),
            dimensions=[
                CrossFilterDimension(
                    name="temporal", bucketing=HistogramBucketing.FIXED_INTERVAL,
                    interval_seconds=3600,
                ),
                CrossFilterDimension(
                    name="direction", bucketing=HistogramBucketing.CATEGORICAL, field="direction"
                ),
            ],
        )
        result = await adapter.cross_filter(req, CLEARED)
        assert set(result) == {"temporal", "direction"}
        assert result["temporal"].total == 2
        assert result["direction"].total == 2


# --- existence-leak assertions ------------------------------------------------


async def test_unauthorised_histogram_bucket_matches_a_corpus_without_the_hidden_event(
    factory: AnalyticsAdapterFactory,
) -> None:
    bucket_time = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    visible = [_event(occurred_at=bucket_time, classification="OFFICIAL")]
    async with factory.context(visible) as adapter:
        req = HistogramRequest(
            filter=_filter(), bucketing=HistogramBucketing.FIXED_INTERVAL, interval_seconds=3600
        )
        before = await adapter.histogram(req, OFFICIAL)

    with_hidden = [*visible, _event(occurred_at=bucket_time, classification="SECRET")]
    async with factory.context(with_hidden) as adapter:
        after = await adapter.histogram(req, OFFICIAL)
        # Adding a SECRET event in the same bucket must not move the
        # OFFICIAL-cleared count by even one.
        assert before.total == after.total
        assert before.buckets == after.buckets

        authorised = await adapter.histogram(req, CLEARED)
        assert authorised.total == 2  # proves the filter is real, not a no-op


async def test_unauthorised_geo_bin_count_matches_a_corpus_without_the_hidden_event(
    factory: AnalyticsAdapterFactory,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    visible = [_event(occurred_at=now, lat=51.5, lon=-0.1, classification="OFFICIAL")]
    req = GeoBinRequest(filter=_filter(), precision=4)

    async with factory.context(visible) as adapter:
        before = await adapter.geo_bins(req, OFFICIAL)

    with_hidden = [
        *visible,
        _event(occurred_at=now, lat=51.5, lon=-0.1, classification="SECRET"),
    ]
    async with factory.context(with_hidden) as adapter:
        after = await adapter.geo_bins(req, OFFICIAL)
        assert before == after

        authorised = await adapter.geo_bins(req, CLEARED)
        assert authorised[0].count == 2


async def test_unauthorised_baseline_matches_a_corpus_without_the_hidden_event(
    factory: AnalyticsAdapterFactory,
) -> None:
    """`baseline` and `cross_filter` had no existence-leak test of their
    own — Standing Rule 2 ("no feature ships without its access-control
    test") treats that as a compliance breach, not a coverage gap, since
    both share `_predicate()` with `histogram`/`geo_bins` but were never
    independently proven to actually apply it."""
    baseline_window = Interval(
        valid_from=datetime(2026, 1, 1, tzinfo=UTC), valid_to=datetime(2026, 1, 2, tzinfo=UTC)
    )
    comparison_window = Interval(
        valid_from=datetime(2026, 1, 8, tzinfo=UTC), valid_to=datetime(2026, 1, 9, tzinfo=UTC)
    )
    req = BaselineRequest(
        filter=_filter(),
        baseline_window=baseline_window,
        comparison_window=comparison_window,
        bucketing=HistogramBucketing.FIXED_INTERVAL,
        interval_seconds=3600,
    )
    visible = [_event(occurred_at=datetime(2026, 1, 8, 10, tzinfo=UTC), classification="OFFICIAL")]
    async with factory.context(visible) as adapter:
        before = await adapter.baseline(req, OFFICIAL)

    with_hidden = [
        *visible,
        _event(occurred_at=datetime(2026, 1, 8, 10, tzinfo=UTC), classification="SECRET"),
    ]
    async with factory.context(with_hidden) as adapter:
        after = await adapter.baseline(req, OFFICIAL)
        assert before == after

        authorised = await adapter.baseline(req, CLEARED)
        assert authorised.comparison_count == 2  # proves the filter is real, not a no-op


async def test_unauthorised_cross_filter_matches_a_corpus_without_the_hidden_event(
    factory: AnalyticsAdapterFactory,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    req = CrossFilterRequest(
        filter=_filter(),
        dimensions=[
            CrossFilterDimension(
                name="temporal", bucketing=HistogramBucketing.FIXED_INTERVAL, interval_seconds=3600
            ),
            CrossFilterDimension(
                name="direction", bucketing=HistogramBucketing.CATEGORICAL, field="direction"
            ),
        ],
    )
    visible = [_event(occurred_at=now, direction="inbound", classification="OFFICIAL")]
    async with factory.context(visible) as adapter:
        before = await adapter.cross_filter(req, OFFICIAL)

    with_hidden = [*visible, _event(occurred_at=now, direction="inbound", classification="SECRET")]
    async with factory.context(with_hidden) as adapter:
        after = await adapter.cross_filter(req, OFFICIAL)
        assert before == after

        authorised = await adapter.cross_filter(req, CLEARED)
        assert authorised["temporal"].total == 2
        assert authorised["direction"].total == 2


async def test_restricted_event_visible_only_to_the_owning_unit_and_receivable_set(
    factory: AnalyticsAdapterFactory,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    events = [
        _event(
            occurred_at=now,
            classification="OFFICIAL",
            handling_code="R",
            owning_unit="unit-restricted",
        )
    ]
    req = HistogramRequest(
        filter=_filter(), bucketing=HistogramBucketing.FIXED_INTERVAL, interval_seconds=3600
    )
    async with factory.context(events) as adapter:
        in_unit_and_receives_r = Principal(
            id="a1",
            clearance="OFFICIAL",
            org_unit="unit-restricted",
            receivable_handling_codes=["R"],
        )
        wrong_unit_but_receives_r = Principal(
            id="a2",
            clearance="OFFICIAL",
            org_unit="unit-elsewhere",
            receivable_handling_codes=["R"],
        )
        right_unit_but_does_not_receive_r = Principal(
            id="a3", clearance="OFFICIAL", org_unit="unit-restricted"
        )

        assert (await adapter.histogram(req, in_unit_and_receives_r)).total == 1
        assert (await adapter.histogram(req, wrong_unit_but_receives_r)).total == 0
        assert (await adapter.histogram(req, right_unit_but_does_not_receive_r)).total == 0
        # OFFICIAL's clearance dominates the event's classification — only
        # the unit scoping on the restricted `handling_code` hides it.
        assert (await adapter.histogram(req, OFFICIAL)).total == 0


async def test_an_unrecognised_clearance_sees_nothing_rather_than_everything(
    factory: AnalyticsAdapterFactory,
) -> None:
    events = [_event(occurred_at=datetime(2026, 1, 1, tzinfo=UTC), classification="OFFICIAL")]
    unknown = Principal(id="analyst-unknown", clearance="NOT-A-SCHEME-LEVEL", org_unit="u")
    async with factory.context(events) as adapter:
        req = HistogramRequest(
            filter=_filter(), bucketing=HistogramBucketing.FIXED_INTERVAL, interval_seconds=3600
        )
        assert (await adapter.histogram(req, unknown)).total == 0
