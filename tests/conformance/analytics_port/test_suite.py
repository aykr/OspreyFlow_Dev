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

import duckdb
import pytest
from ulid import ULID

from schemas.analytics import (
    BaselineRequest,
    CrossFilterDimension,
    CrossFilterRequest,
    EventFilter,
    EventRecord,
    GeoBinRequest,
    GeometryKind,
    GeometryRecord,
    HistogramBucketing,
    HistogramRequest,
    SightingRequest,
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


def _geometry(
    *,
    geometry_ref: str = "geo-1",
    version: int = 1,
    lon: float = -0.1276,
    lat: float = 51.5072,
    source_crs: str = "EPSG:4326",
    source_x: float | None = None,
    source_y: float | None = None,
    classification: str = "OFFICIAL",
    handling_code: str = "P",
    owning_unit: str = "unit-1",
    originator: str = "unit-1",
) -> GeometryRecord:
    return GeometryRecord(
        geometry_ref=geometry_ref,
        version=version,
        lon=lon,
        lat=lat,
        source_crs=source_crs,
        source_x=source_x,
        source_y=source_y,
        handling=_handling(
            classification,
            handling_code=handling_code,
            owning_unit=owning_unit,
            originator=originator,
        ),
    )


def _polygon_wkb(wkt: str) -> bytes:
    """Builds real WKB the same way the DuckDB adapter itself would —
    through the `spatial` extension's own `ST_GeomFromText`/`ST_AsWKB` —
    rather than adding a shapely dependency just for test fixtures."""
    con = duckdb.connect(":memory:")
    try:
        con.install_extension("spatial")
        con.load_extension("spatial")
        return con.execute("SELECT ST_AsWKB(ST_GeomFromText(?))", [wkt]).fetchone()[0]
    finally:
        con.close()


_SQUARE_WKT = "POLYGON((-0.2 51.4, -0.2 51.6, 0.0 51.6, 0.0 51.4, -0.2 51.4))"


def _boundary(
    *,
    geometry_ref: str = "boundary-1",
    version: int = 1,
    wkt: str = _SQUARE_WKT,
    classification: str = "OFFICIAL",
    handling_code: str = "P",
    owning_unit: str = "unit-1",
    originator: str = "unit-1",
) -> GeometryRecord:
    return GeometryRecord(
        geometry_ref=geometry_ref,
        version=version,
        kind=GeometryKind.POLYGON,
        geometry_wkb=_polygon_wkb(wkt),
        handling=_handling(
            classification,
            handling_code=handling_code,
            owning_unit=owning_unit,
            originator=originator,
        ),
    )


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


# --- sightings (Stage 4f, B18's own snail trail) ---------------------------------


async def test_sightings_are_ordered_by_time_and_exclude_null_coordinates(
    factory: AnalyticsAdapterFactory,
) -> None:
    t0 = datetime(2026, 1, 1, 8, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 9, tzinfo=UTC)
    t2 = datetime(2026, 1, 1, 10, tzinfo=UTC)
    events = [
        _event(occurred_at=t2, lat=51.52, lon=-0.10),
        _event(occurred_at=t0, lat=51.50, lon=-0.12),
        _event(occurred_at=t1, lat=None, lon=None),  # no coordinates — excluded
        _event(occurred_at=t1, lat=51.51, lon=-0.11),
    ]
    async with factory.context(events) as adapter:
        req = SightingRequest(filter=_filter())
        sightings = await adapter.list_sightings(req, CLEARED)
        assert [s.occurred_at for s in sightings] == [t0, t1, t2]
        assert len(sightings) == 3


async def test_unauthorised_sighting_is_absent_not_a_gap_in_the_track(
    factory: AnalyticsAdapterFactory,
) -> None:
    """The existence-leak discipline applied to a track rather than a bucket count: an
    OFFICIAL-cleared analyst's own snail trail must be identical whether or not a SECRET sighting
    exists in the population — never a differently-shaped track, never a visible gap that would
    itself disclose that something was omitted."""
    t0 = datetime(2026, 1, 1, 8, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 9, tzinfo=UTC)
    visible = [_event(occurred_at=t0, lat=51.50, lon=-0.12, classification="OFFICIAL")]
    req = SightingRequest(filter=_filter())

    async with factory.context(visible) as adapter:
        before = await adapter.list_sightings(req, OFFICIAL)

    with_hidden = [*visible, _event(occurred_at=t1, lat=51.51, lon=-0.11, classification="SECRET")]
    async with factory.context(with_hidden) as adapter:
        after = await adapter.list_sightings(req, OFFICIAL)
        assert before == after

        authorised = await adapter.list_sightings(req, CLEARED)
        assert len(authorised) == 2


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


# --- the geometry reference partition (07_BUILD_PLAN.md Phase 5) ------------
#
# `load_geometries`/`get_geometry`/`get_geometries` are exercised directly —
# there is no shared "context seeds this" fixture the way `EventRecord`s are
# seeded through `factory.context(events)`, since geometry writes are a
# separate, non-principal-scoped operation on the same adapter instance
# (see the port's own docstring).


async def test_load_geometries_and_get_geometry_round_trips_the_reprojected_point(
    factory: AnalyticsAdapterFactory,
) -> None:
    record = _geometry(geometry_ref="geo-trafalgar", source_crs="EPSG:27700", source_x=532106.0,
                        source_y=181020.0)
    async with factory.context([]) as adapter:
        await adapter.load_geometries([record])
        stored = await adapter.get_geometry("geo-trafalgar", CLEARED)
        assert stored == record


async def test_get_geometry_defaults_to_the_latest_partition_version(
    factory: AnalyticsAdapterFactory,
) -> None:
    """A gazetteer refresh loads a new version of the whole partition
    rather than merging into the previous one (`00_ARCHITECTURE.md` §1.2) —
    every prior version's rows are retained, and an unpinned read resolves
    to the current (highest) version."""
    v1 = _geometry(geometry_ref="geo-1", version=1, lon=-0.1, lat=51.5)
    v2 = _geometry(geometry_ref="geo-1", version=2, lon=-0.2, lat=51.6)
    async with factory.context([]) as adapter:
        await adapter.load_geometries([v1, v2])
        assert (await adapter.get_geometry("geo-1", CLEARED)) == v2


async def test_get_geometry_can_pin_an_explicit_historical_version(
    factory: AnalyticsAdapterFactory,
) -> None:
    """An investigation records which gazetteer version was in force when
    a place name resolved (`00_ARCHITECTURE.md` §1.2) — that must remain
    resolvable after a later refresh, not silently move underneath it."""
    v1 = _geometry(geometry_ref="geo-1", version=1, lon=-0.1, lat=51.5)
    v2 = _geometry(geometry_ref="geo-1", version=2, lon=-0.2, lat=51.6)
    async with factory.context([]) as adapter:
        await adapter.load_geometries([v1, v2])
        assert (await adapter.get_geometry("geo-1", CLEARED, version=1)) == v1
        assert (await adapter.get_geometry("geo-1", CLEARED, version=2)) == v2


async def test_get_geometry_for_an_unknown_ref_returns_none_not_an_error(
    factory: AnalyticsAdapterFactory,
) -> None:
    async with factory.context([]) as adapter:
        assert (await adapter.get_geometry("does-not-exist", CLEARED)) is None


async def test_get_geometries_batch_returns_only_the_matching_refs(
    factory: AnalyticsAdapterFactory,
) -> None:
    geo_a = _geometry(geometry_ref="geo-a")
    geo_b = _geometry(geometry_ref="geo-b")
    async with factory.context([]) as adapter:
        await adapter.load_geometries([geo_a, geo_b])
        result = await adapter.get_geometries(["geo-a", "geo-b", "geo-missing"], CLEARED)
        assert {r.geometry_ref for r in result} == {"geo-a", "geo-b"}


async def test_unauthorised_get_geometry_cannot_distinguish_a_filtered_ref_from_a_missing_one(
    factory: AnalyticsAdapterFactory,
) -> None:
    """The existence-leak discipline (`00_ARCHITECTURE.md` §5) applies to
    the geometry partition exactly as it does to a graph node: a site's own
    control-point/grid geometry is not uniformly public reference data, and
    an unauthorised principal must get the same `None` for a `geometry_ref`
    that exists-but-is-hidden as for one that never existed at all."""
    hidden = _geometry(geometry_ref="geo-secret", classification="SECRET")
    async with factory.context([]) as adapter:
        await adapter.load_geometries([hidden])
        assert (await adapter.get_geometry("geo-secret", OFFICIAL)) is None
        assert (await adapter.get_geometry("geo-nonexistent", OFFICIAL)) is None
        # Proves the filter is real, not a no-op that would hide everything.
        assert (await adapter.get_geometry("geo-secret", CLEARED)) == hidden


async def test_unauthorised_get_geometries_batch_silently_omits_hidden_refs(
    factory: AnalyticsAdapterFactory,
) -> None:
    visible = _geometry(geometry_ref="geo-open", classification="OFFICIAL")
    hidden = _geometry(geometry_ref="geo-secret", classification="SECRET")
    async with factory.context([]) as adapter:
        await adapter.load_geometries([visible, hidden])
        result = await adapter.get_geometries(["geo-open", "geo-secret"], OFFICIAL)
        assert {r.geometry_ref for r in result} == {"geo-open"}


# --- polygon geometry storage (07_BUILD_PLAN.md Phase 5 known-gaps closure) -


async def test_load_geometries_and_get_geometry_round_trips_a_polygon(
    factory: AnalyticsAdapterFactory,
) -> None:
    boundary = _boundary(geometry_ref="boundary-trafalgar")
    async with factory.context([]) as adapter:
        await adapter.load_geometries([boundary])
        stored = await adapter.get_geometry("boundary-trafalgar", CLEARED)
        assert stored == boundary
        assert stored.kind is GeometryKind.POLYGON
        assert stored.lon is None
        assert stored.lat is None


async def test_get_geometries_batch_returns_points_and_polygons_together(
    factory: AnalyticsAdapterFactory,
) -> None:
    point = _geometry(geometry_ref="geo-point")
    boundary = _boundary(geometry_ref="boundary-1")
    async with factory.context([]) as adapter:
        await adapter.load_geometries([point, boundary])
        result = await adapter.get_geometries(["geo-point", "boundary-1"], CLEARED)
        assert {r.geometry_ref: r.kind for r in result} == {
            "geo-point": GeometryKind.POINT,
            "boundary-1": GeometryKind.POLYGON,
        }


async def test_list_boundaries_returns_only_polygon_rows(
    factory: AnalyticsAdapterFactory,
) -> None:
    point = _geometry(geometry_ref="geo-point")
    boundary_a = _boundary(geometry_ref="boundary-a")
    boundary_b = _boundary(geometry_ref="boundary-b")
    async with factory.context([]) as adapter:
        await adapter.load_geometries([point, boundary_a, boundary_b])
        result = await adapter.list_boundaries(CLEARED)
        assert {r.geometry_ref for r in result} == {"boundary-a", "boundary-b"}
        assert all(r.kind is GeometryKind.POLYGON for r in result)


async def test_list_boundaries_defaults_to_the_latest_partition_version(
    factory: AnalyticsAdapterFactory,
) -> None:
    v1 = _boundary(geometry_ref="boundary-1", version=1)
    v2 = _boundary(geometry_ref="boundary-1", version=2, wkt=_SQUARE_WKT)
    async with factory.context([]) as adapter:
        await adapter.load_geometries([v1, v2])
        result = await adapter.list_boundaries(CLEARED)
        assert [r.version for r in result] == [2]


async def test_unauthorised_list_boundaries_omits_a_hidden_boundary(
    factory: AnalyticsAdapterFactory,
) -> None:
    """The existence-leak discipline applies to `list_boundaries` exactly
    as it does to `get_geometries`: a hidden boundary must not appear, and
    must not be distinguishable from one that was never loaded at all
    (CLAUDE.md rule 3/4)."""
    visible = _boundary(geometry_ref="boundary-open", classification="OFFICIAL")
    hidden = _boundary(geometry_ref="boundary-secret", classification="SECRET")
    async with factory.context([]) as adapter:
        await adapter.load_geometries([visible, hidden])
        result = await adapter.list_boundaries(OFFICIAL)
        assert {r.geometry_ref for r in result} == {"boundary-open"}
        # Proves the filter is real, not a no-op that would hide everything.
        cleared_result = await adapter.list_boundaries(CLEARED)
        assert {r.geometry_ref for r in cleared_result} == {"boundary-open", "boundary-secret"}


# --- load_events (07_BUILD_PLAN.md Phase 5 Checkpoint 2) --------------------
#
# Every existing test above seeds events through `factory.context(events)`,
# which itself calls `load_events` internally (`analytics_duckdb/testing.py`)
# — so `load_events` is already exercised indirectly by this whole file. The
# tests below exercise it directly and explicitly, the same way
# `load_geometries` gets its own direct tests above rather than relying only
# on incidental coverage, since this is the method's first real conformance
# proof and the one place a future adapter's own `load_events` gets checked
# against the same contract.


async def test_load_events_and_histogram_round_trips_the_count(
    factory: AnalyticsAdapterFactory,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    events = [_event(occurred_at=now), _event(occurred_at=now)]
    async with factory.context([]) as adapter:
        await adapter.load_events(events)
        result = await adapter.histogram(
            HistogramRequest(
                filter=_filter(), bucketing=HistogramBucketing.FIXED_INTERVAL, interval_seconds=3600
            ),
            OFFICIAL,
        )
        assert result.total == 2


async def test_load_events_is_a_safe_no_op_on_an_empty_sequence(
    factory: AnalyticsAdapterFactory,
) -> None:
    async with factory.context([]) as adapter:
        await adapter.load_events([])
        result = await adapter.histogram(
            HistogramRequest(
                filter=_filter(), bucketing=HistogramBucketing.FIXED_INTERVAL, interval_seconds=3600
            ),
            OFFICIAL,
        )
        assert result.total == 0


async def test_unauthorised_histogram_after_load_events_matches_a_corpus_without_the_hidden_event(
    factory: AnalyticsAdapterFactory,
) -> None:
    """The existence-leak discipline applies to `load_events` itself, not
    only to a corpus a test fixture happened to seed some other way: an
    OFFICIAL-cleared principal's `histogram` total must be identical
    whether or not a SECRET-classified event was ever loaded."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    visible = _event(occurred_at=now, classification="OFFICIAL")
    hidden = _event(occurred_at=now, classification="SECRET")
    req = HistogramRequest(
        filter=_filter(), bucketing=HistogramBucketing.FIXED_INTERVAL, interval_seconds=3600
    )

    async with factory.context([]) as adapter:
        await adapter.load_events([visible])
        before = await adapter.histogram(req, OFFICIAL)

    async with factory.context([]) as adapter:
        await adapter.load_events([visible, hidden])
        after = await adapter.histogram(req, OFFICIAL)
        after_cleared = await adapter.histogram(req, CLEARED)

    assert before == after
    assert after_cleared.total == 2  # proves the filter is real, not a no-op
