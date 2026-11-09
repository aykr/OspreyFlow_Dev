"""`AnalyticsPort` conformance suite —
`spec/04_VAULT_BACKEND.md` §6, `spec/00_ARCHITECTURE.md` §2.2,
`spec/01_DOMAIN_MODEL.md` §9.

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

from ports.analytics import AnalyticsPort, TrendLimitExceeded
from schemas.analytics import (
    BaselineRequest,
    CrossFilterDimension,
    CrossFilterRequest,
    EventFilter,
    EventListRequest,
    EventRecord,
    FirstSeenRequest,
    GeoBinRequest,
    GeocodeRequest,
    GeometryKind,
    GeometryRecord,
    HistogramBucketing,
    HistogramRequest,
    InheritedEvents,
    SightingRequest,
    TrendInterval,
    TrendMeasure,
    TrendRequest,
    TrendResult,
    WeekdayHour,
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
    edge_id: str = "e1",
    load_id: str | None = None,
) -> EventRecord:
    return EventRecord(
        event_id=str(ULID()),
        edge_id=edge_id,
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
        load_id=load_id,
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


async def test_event_filter_value_filters_restrict_by_a_property_not_merely_aggregate_it(
    factory: AnalyticsAdapterFactory,
) -> None:
    """**A7's item-category half — round 13cdc.**

    `08_ACCEPTANCE_SCENARIOS.md` A7 filters reports "to one residential sub-unit and one item
    category". The sub-unit half is `node_ids`, already supported. The category half had nothing:
    `cross_filter`'s categorical dimensions *display* a field's distinct values but never let a
    caller restrict to one, and 08 carried a "Known gap" section saying so.

    The field here lives inside the JSON `properties` blob, which is the case that matters —
    `item_type` is not a declared event column, and a filter that only worked on the five
    top-level columns would not reach A7's row.
    """
    now = datetime(2026, 1, 1, tzinfo=UTC)
    events = [
        _event(occurred_at=now, properties={"item_type": "bicycle"}),
        _event(occurred_at=now, properties={"item_type": "bicycle"}),
        _event(occurred_at=now, properties={"item_type": "power tool"}),
        _event(occurred_at=now, properties={}),
    ]
    async with factory.context(events) as adapter:
        req = HistogramRequest(
            filter=_filter(value_filters={"item_type": ["bicycle"]}),
            bucketing=HistogramBucketing.FIXED_INTERVAL,
            interval_seconds=3600,
        )
        assert (await adapter.histogram(req, CLEARED)).total == 2

        # Values within one field are OR-ed: an item category is *one of* these.
        both = req.model_copy(
            update={"filter": _filter(value_filters={"item_type": ["bicycle", "power tool"]})}
        )
        assert (await adapter.histogram(both, CLEARED)).total == 3

        # An event with no such property is not matched, and does not error.
        missing = req.model_copy(
            update={"filter": _filter(value_filters={"item_type": ["kayak"]})}
        )
        assert (await adapter.histogram(missing, CLEARED)).total == 0


async def test_event_filter_value_filters_combine_with_everything_else_by_and(
    factory: AnalyticsAdapterFactory,
) -> None:
    """A7 asks for a sub-unit **and** a category. Fields are AND-ed, which is what a filter bar
    with several facets means; OR-ing them would silently widen the population an analyst
    believes they have narrowed."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    events = [
        _event(occurred_at=now, source_id="unit-a", properties={"item_type": "bicycle"}),
        _event(occurred_at=now, source_id="unit-b", properties={"item_type": "bicycle"}),
        _event(occurred_at=now, source_id="unit-a", properties={"item_type": "power tool"}),
    ]
    async with factory.context(events) as adapter:
        req = HistogramRequest(
            filter=_filter(node_ids=["unit-a"], value_filters={"item_type": ["bicycle"]}),
            bucketing=HistogramBucketing.FIXED_INTERVAL,
            interval_seconds=3600,
        )
        assert (await adapter.histogram(req, CLEARED)).total == 1

        # Two fields, also AND-ed.
        two = req.model_copy(
            update={
                "filter": _filter(
                    value_filters={"item_type": ["bicycle"], "direction": ["inbound"]}
                )
            }
        )
        assert (await adapter.histogram(two, CLEARED)).total == 0


async def test_event_filter_an_empty_value_list_does_not_restrict_and_does_not_error(
    factory: AnalyticsAdapterFactory,
) -> None:
    """A facet expanded with nothing ticked means "do not restrict by this field", not "match
    nothing" — and must not compile to `IN ()`, which is a syntax error the analyst would see as
    a 500."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    events = [_event(occurred_at=now, properties={"item_type": "bicycle"})]
    async with factory.context(events) as adapter:
        req = HistogramRequest(
            filter=_filter(value_filters={"item_type": []}),
            bucketing=HistogramBucketing.FIXED_INTERVAL,
            interval_seconds=3600,
        )
        assert (await adapter.histogram(req, CLEARED)).total == 1


async def test_event_filter_value_filters_cannot_smuggle_sql_through_a_field_name(
    factory: AnalyticsAdapterFactory,
) -> None:
    """**The field name is interpolated into SQL; the values are parameterised.**

    A value filter is the first place a caller names a *column*, so the identifier guard
    `cross_filter`'s dimensions already rely on has to hold here too. Asserted as a refusal rather
    than trusted: a name that is not a plain identifier must not reach the query at all.
    """
    now = datetime(2026, 1, 1, tzinfo=UTC)
    async with factory.context([_event(occurred_at=now)]) as adapter:
        req = HistogramRequest(
            filter=_filter(value_filters={"item_type'); DROP TABLE events; --": ["x"]}),
            bucketing=HistogramBucketing.FIXED_INTERVAL,
            interval_seconds=3600,
        )
        with pytest.raises(ValueError):
            await adapter.histogram(req, CLEARED)

        # The table is still there, which is the assertion that would matter if the guard failed.
        ok = HistogramRequest(
            filter=_filter(),
            bucketing=HistogramBucketing.FIXED_INTERVAL,
            interval_seconds=3600,
        )
        assert (await adapter.histogram(ok, CLEARED)).total == 1


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


# --- the cell brush (ADR-130 decision 2): EventFilter.weekday_hours ----------------
#
# A cell is (weekday, hour) with weekday 0 = Monday and the hour read in UTC, exactly the
# numbering the weekly histogram buckets by. 5 January 2026 is a Monday.


def _cell_corpus(classification: str = "OFFICIAL") -> list[EventRecord]:
    return [
        # Monday 09:00 twice, a fortnight apart; Saturday 15:00; Sunday 03:00 (with a point).
        _event(occurred_at=datetime(2026, 1, 5, 9, 0, tzinfo=UTC), lat=51.5, lon=-0.1),
        _event(occurred_at=datetime(2026, 1, 19, 9, 59, tzinfo=UTC), lat=51.5, lon=-0.1),
        _event(occurred_at=datetime(2026, 1, 10, 15, 0, tzinfo=UTC), lat=51.5, lon=-0.1),
        _event(
            occurred_at=datetime(2026, 1, 11, 3, 0, tzinfo=UTC),
            lat=51.5,
            lon=-0.1,
            classification=classification,
        ),
    ]


async def _total(
    adapter: AnalyticsPort, event_filter: EventFilter, who: Principal = CLEARED
) -> int:
    req = HistogramRequest(filter=event_filter, interval_seconds=3600)
    return (await adapter.histogram(req, who)).total


async def test_event_filter_weekday_hours_counts_only_events_in_the_chosen_cells(
    factory: AnalyticsAdapterFactory,
) -> None:
    async with factory.context(_cell_corpus()) as adapter:
        monday_nine = _filter(weekday_hours=[WeekdayHour(weekday=0, hour=9)])
        assert await _total(adapter, monday_nine) == 2
        two_cells = _filter(
            weekday_hours=[WeekdayHour(weekday=0, hour=9), WeekdayHour(weekday=5, hour=15)]
        )
        assert await _total(adapter, two_cells) == 3
        # The same hour on another day, and another hour on the same day, are not in the cell.
        assert await _total(adapter, _filter(weekday_hours=[WeekdayHour(weekday=1, hour=9)])) == 0
        assert await _total(adapter, _filter(weekday_hours=[WeekdayHour(weekday=0, hour=10)])) == 0


async def test_event_filter_weekday_hours_uses_the_weekly_histograms_own_cells(
    factory: AnalyticsAdapterFactory,
) -> None:
    """Whatever cell the weekly histogram puts an event in, choosing that cell finds it."""
    async with factory.context(_cell_corpus()) as adapter:
        weekly = await adapter.histogram(
            HistogramRequest(filter=_filter(), bucketing=HistogramBucketing.WEEKDAY_HOUR), CLEARED
        )
        assert weekly.total == 4
        for bucket in weekly.buckets:
            assert bucket.weekday is not None and bucket.hour is not None
            chosen = _filter(weekday_hours=[WeekdayHour(weekday=bucket.weekday, hour=bucket.hour)])
            assert await _total(adapter, chosen) == bucket.count


async def test_event_filter_weekday_hours_empty_set_matches_nothing_and_none_does_not_restrict(
    factory: AnalyticsAdapterFactory,
) -> None:
    async with factory.context(_cell_corpus()) as adapter:
        assert await _total(adapter, _filter(weekday_hours=[])) == 0
        assert await _total(adapter, _filter(weekday_hours=None)) == 4
        assert await _total(adapter, _filter()) == 4


async def test_event_filter_weekday_hours_combines_with_the_other_predicates_by_and(
    factory: AnalyticsAdapterFactory,
) -> None:
    async with factory.context(_cell_corpus()) as adapter:
        window = Interval(
            valid_from=datetime(2026, 1, 1, tzinfo=UTC), valid_to=datetime(2026, 1, 8, tzinfo=UTC)
        )
        cell = [WeekdayHour(weekday=0, hour=9)]
        assert await _total(adapter, _filter(weekday_hours=cell, window=window)) == 1


async def test_event_filter_weekday_hours_ranges_are_validated(
    factory: AnalyticsAdapterFactory,
) -> None:
    for weekday, hour in ((7, 0), (-1, 0), (0, 24), (0, -1)):
        with pytest.raises(ValueError):
            WeekdayHour(weekday=weekday, hour=hour)


async def test_event_filter_weekday_hours_is_de_duplicated_and_counts_the_same(
    factory: AnalyticsAdapterFactory,
) -> None:
    once = [WeekdayHour(weekday=0, hour=9), WeekdayHour(weekday=5, hour=15)]
    repeated = once + [WeekdayHour(weekday=0, hour=9)] * 3 + once
    assert _filter(weekday_hours=repeated).weekday_hours == once
    async with factory.context(_cell_corpus()) as adapter:
        assert await _total(adapter, _filter(weekday_hours=repeated)) == await _total(
            adapter, _filter(weekday_hours=once)
        )


async def test_event_filter_weekday_hours_all_168_cells_are_allowed_and_more_is_refused(
    factory: AnalyticsAdapterFactory,
) -> None:
    every = [WeekdayHour(weekday=d, hour=h) for d in range(7) for h in range(24)]
    assert len(_filter(weekday_hours=every).weekday_hours or []) == 168
    # The same 168 cells repeated is 336 entries: refused, not silently thinned, naming the cap.
    with pytest.raises(ValueError, match="168"):
        _filter(weekday_hours=every + every)
    with pytest.raises(ValueError, match="168"):
        _filter(weekday_hours=every + [WeekdayHour(weekday=0, hour=0)])


async def test_event_filter_weekday_hours_honoured_by_geo_bins_and_cross_filter(
    factory: AnalyticsAdapterFactory,
) -> None:
    async with factory.context(_cell_corpus()) as adapter:
        cells = _filter(weekday_hours=[WeekdayHour(weekday=0, hour=9)])
        bins = await adapter.geo_bins(GeoBinRequest(filter=cells, precision=4), CLEARED)
        assert sum(b.count for b in bins) == 2
        nothing = _filter(weekday_hours=[])
        assert await adapter.geo_bins(GeoBinRequest(filter=nothing, precision=4), CLEARED) == []

        result = await adapter.cross_filter(
            CrossFilterRequest(
                filter=cells,
                dimensions=[
                    CrossFilterDimension(
                        name="weekly", bucketing=HistogramBucketing.WEEKDAY_HOUR
                    ),
                    CrossFilterDimension(
                        name="temporal",
                        bucketing=HistogramBucketing.FIXED_INTERVAL,
                        interval_seconds=3600,
                    ),
                ],
            ),
            CLEARED,
        )
        assert result["weekly"].total == 2
        assert [(b.weekday, b.hour) for b in result["weekly"].buckets] == [(0, 9)]
        assert result["temporal"].total == 2


async def test_unauthorised_event_in_a_chosen_cell_is_not_counted_by_any_read(
    factory: AnalyticsAdapterFactory,
) -> None:
    """Rule 3: a SECRET event in a chosen cell moves nothing for an OFFICIAL reader."""
    visible = _cell_corpus()
    hidden = _event(
        occurred_at=datetime(2026, 1, 5, 9, 30, tzinfo=UTC),
        lat=51.5,
        lon=-0.1,
        classification="SECRET",
    )
    cells = _filter(weekday_hours=[WeekdayHour(weekday=0, hour=9)])
    geo = GeoBinRequest(filter=cells, precision=4)

    async with factory.context(visible) as adapter:
        before_total = await _total(adapter, cells, OFFICIAL)
        before_bins = await adapter.geo_bins(geo, OFFICIAL)

    async with factory.context([*visible, hidden]) as adapter:
        assert await _total(adapter, cells, OFFICIAL) == before_total == 2
        assert await adapter.geo_bins(geo, OFFICIAL) == before_bins
        assert await _total(adapter, cells, CLEARED) == 3  # the filter is real, not a no-op


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


# --- the events behind one link (ADR-089): a filter by link, and a paged listing ------------


async def test_event_filter_edge_ids_restricts_to_events_on_those_links(
    factory: AnalyticsAdapterFactory,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    events = [
        _event(occurred_at=now, edge_id="ab"),
        _event(occurred_at=now, edge_id="ab"),
        _event(occurred_at=now, edge_id="bc", source_id="b", target_id="c"),
    ]
    async with factory.context(events) as adapter:
        req = HistogramRequest(filter=_filter(edge_ids=["ab"]), interval_seconds=3600)
        assert (await adapter.histogram(req, CLEARED)).total == 2
        both = HistogramRequest(filter=_filter(edge_ids=["ab", "bc"]), interval_seconds=3600)
        assert (await adapter.histogram(both, CLEARED)).total == 3
        none = HistogramRequest(filter=_filter(edge_ids=["zz"]), interval_seconds=3600)
        assert (await adapter.histogram(none, CLEARED)).total == 0


async def test_event_filter_event_ids_restricts_to_those_events(
    factory: AnalyticsAdapterFactory,
) -> None:
    """The one email an analyst opened and asked to extract from (ADR-089 step 3). The defect this
    pins: the lookup was a `value_filters` entry on `event_id`, which the adapter reads as a key
    inside `properties`, so it matched nothing and every extraction answered "email not found"."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    wanted = _event(occurred_at=now, edge_id="ab")
    events = [wanted, _event(occurred_at=now, edge_id="ab"), _event(occurred_at=now, edge_id="cd")]
    async with factory.context(events) as adapter:
        page = await adapter.list_events(
            EventListRequest(
                filter=_filter(edge_ids=["ab"], event_ids=[wanted.event_id]), offset=0, limit=5
            ),
            CLEARED,
        )
        assert [e.event_id for e in page.events] == [wanted.event_id]
        assert page.total == 1
        none = await adapter.list_events(
            EventListRequest(filter=_filter(event_ids=["no-such-event"]), offset=0, limit=5),
            CLEARED,
        )
        assert none.total == 0


async def test_list_events_is_newest_first_paged_and_says_how_many_there_are(
    factory: AnalyticsAdapterFactory,
) -> None:
    """The emails behind a link are read newest first, fifty at a time, and the total is said so
    the list can page; the properties ride along whole (an email's subject and excerpt live
    there)."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    events = [
        _event(
            occurred_at=base.replace(hour=hour),
            edge_id="ab",
            properties={"subject": f"Subject {hour}", "excerpt": f"Body {hour}"},
        )
        for hour in range(5)
    ]
    async with factory.context(events) as adapter:
        page = await adapter.list_events(
            EventListRequest(filter=_filter(edge_ids=["ab"]), offset=0, limit=2), CLEARED
        )
        assert page.total == 5
        assert [e.occurred_at.hour for e in page.events] == [4, 3]
        assert page.events[0].properties == {"subject": "Subject 4", "excerpt": "Body 4"}
        assert page.events[0].edge_id == "ab"
        last = await adapter.list_events(
            EventListRequest(filter=_filter(edge_ids=["ab"]), offset=4, limit=2), CLEARED
        )
        assert [e.occurred_at.hour for e in last.events] == [0]
        beyond = await adapter.list_events(
            EventListRequest(filter=_filter(edge_ids=["ab"]), offset=10, limit=2), CLEARED
        )
        assert beyond.events == [] and beyond.total == 5


async def test_unauthorised_list_events_matches_a_corpus_without_the_hidden_event(
    factory: AnalyticsAdapterFactory,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    req = EventListRequest(filter=_filter(edge_ids=["e1"]), offset=0, limit=50)
    visible = [_event(occurred_at=now, classification="OFFICIAL")]
    async with factory.context(visible) as adapter:
        before = await adapter.list_events(req, OFFICIAL)
        assert before.total == 1

    with_hidden = [*visible, _event(occurred_at=now, classification="SECRET")]
    async with factory.context(with_hidden) as adapter:
        after = await adapter.list_events(req, OFFICIAL)
        assert after.total == before.total
        assert [e.event_id for e in after.events] == [e.event_id for e in before.events]
        assert (await adapter.list_events(req, CLEARED)).total == 2


# --- a branch's inherited events (ADR-084 Amendment 2) --------------------------------------
#
# A branch holds copies of some of its parent's links; the events behind them stay under the
# parent's scope. `EventFilter.inherited` lets a branch count them, but only on the links it holds.


def _inherited(scopes: list[str], edge_ids: list[str]) -> InheritedEvents:
    return InheritedEvents(scopes=scopes, edge_ids=edge_ids)


def _lineage_corpus(now: datetime) -> list[EventRecord]:
    return [
        _event(occurred_at=now, edge_id="own"),
        _event(occurred_at=now, edge_id="ab", investigation_scope="parent"),
        _event(occurred_at=now, edge_id="ab", investigation_scope="parent"),
        _event(occurred_at=now, edge_id="cd", investigation_scope="parent"),
        _event(occurred_at=now, edge_id="ab", investigation_scope="unrelated"),
    ]


async def test_inherited_events_count_only_on_the_links_the_branch_holds(
    factory: AnalyticsAdapterFactory,
) -> None:
    """The parent's two events on `ab` count; its event on `cd` (a link the branch did not take)
    and an unrelated case's event on `ab` do not."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    async with factory.context(_lineage_corpus(now)) as adapter:
        own_only = HistogramRequest(filter=_filter(), interval_seconds=3600)
        assert (await adapter.histogram(own_only, CLEARED)).total == 1
        branch = HistogramRequest(
            filter=_filter(inherited=_inherited(["parent"], ["ab"])), interval_seconds=3600
        )
        assert (await adapter.histogram(branch, CLEARED)).total == 3


async def test_inherited_events_with_no_links_held_add_nothing(
    factory: AnalyticsAdapterFactory,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    async with factory.context(_lineage_corpus(now)) as adapter:
        req = HistogramRequest(
            filter=_filter(inherited=_inherited(["parent"], [])), interval_seconds=3600
        )
        assert (await adapter.histogram(req, CLEARED)).total == 1


async def test_inherited_events_obey_every_other_predicate(
    factory: AnalyticsAdapterFactory,
) -> None:
    """The emails behind one link on a branch: `edge_ids` and the window narrow the inherited
    events as they narrow the case's own, and the listing pages over both together."""
    early = datetime(2026, 1, 1, 9, tzinfo=UTC)
    late = datetime(2026, 1, 1, 15, tzinfo=UTC)
    events = [
        _event(occurred_at=late, edge_id="ab", investigation_scope="parent"),
        _event(occurred_at=early, edge_id="ab", investigation_scope="parent"),
        _event(occurred_at=late, edge_id="cd", investigation_scope="parent"),
    ]
    inherited = _inherited(["parent"], ["ab", "cd"])
    async with factory.context(events) as adapter:
        on_ab = await adapter.list_events(
            EventListRequest(
                filter=_filter(edge_ids=["ab"], inherited=inherited), offset=0, limit=50
            ),
            CLEARED,
        )
        assert on_ab.total == 2
        assert [e.occurred_at for e in on_ab.events] == [late, early]
        windowed = HistogramRequest(
            filter=_filter(
                inherited=inherited,
                window=Interval(valid_from=datetime(2026, 1, 1, 12, tzinfo=UTC)),
            ),
            interval_seconds=3600,
        )
        assert (await adapter.histogram(windowed, CLEARED)).total == 2


async def test_inherited_events_are_held_to_the_branchs_window_ends_included(
    factory: AnalyticsAdapterFactory,
) -> None:
    """ADR-128 decision 2: a branch made from what is lit records its window, and the parent's
    events it reads are only those inside it, both ends included. The branch's own events are not
    held to it, and a branch with no window reads every inherited event, as before."""
    start = datetime(2026, 1, 5, tzinfo=UTC)
    end = datetime(2026, 4, 30, tzinfo=UTC)
    events = [
        _event(occurred_at=datetime(2026, 1, 4, tzinfo=UTC), edge_id="ab", investigation_scope="parent"),
        _event(occurred_at=start, edge_id="ab", investigation_scope="parent"),
        _event(occurred_at=datetime(2026, 3, 1, tzinfo=UTC), edge_id="ab", investigation_scope="parent"),
        _event(occurred_at=end, edge_id="ab", investigation_scope="parent"),
        _event(occurred_at=datetime(2026, 5, 1, tzinfo=UTC), edge_id="ab", investigation_scope="parent"),
        _event(occurred_at=datetime(2026, 12, 1, tzinfo=UTC), edge_id="own"),
    ]
    held = InheritedEvents(
        scopes=["parent"], edge_ids=["ab"], window=Interval(valid_from=start, valid_to=end)
    )
    plain = _inherited(["parent"], ["ab"])
    async with factory.context(events) as adapter:
        windowed = HistogramRequest(filter=_filter(inherited=held), interval_seconds=3600)
        # Three of the parent's five (start, mid, end) and the branch's own, outside the window.
        assert (await adapter.histogram(windowed, CLEARED)).total == 4
        unwindowed = HistogramRequest(filter=_filter(inherited=plain), interval_seconds=3600)
        assert (await adapter.histogram(unwindowed, CLEARED)).total == 6
        first = await adapter.first_seen(FirstSeenRequest(filter=_filter(inherited=held)), CLEARED)
        assert first.edges["ab"] == start


async def test_unauthorised_inherited_event_matches_a_corpus_without_it(
    factory: AnalyticsAdapterFactory,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    req = HistogramRequest(
        filter=_filter(inherited=_inherited(["parent"], ["ab"])), interval_seconds=3600
    )
    visible = [_event(occurred_at=now, edge_id="ab", investigation_scope="parent")]
    async with factory.context(visible) as adapter:
        before = await adapter.histogram(req, OFFICIAL)
        assert before.total == 1

    hidden = _event(
        occurred_at=now, edge_id="ab", investigation_scope="parent", classification="SECRET"
    )
    async with factory.context([*visible, hidden]) as adapter:
        after = await adapter.histogram(req, OFFICIAL)
        assert after.total == before.total
        assert after.buckets == before.buckets
        assert (await adapter.histogram(req, CLEARED)).total == 2


# --- first_seen (ADR-087): when each node and link first appears in a window ----------------


async def test_first_seen_gives_each_node_and_link_its_earliest_event_in_the_window(
    factory: AnalyticsAdapterFactory,
) -> None:
    """The timeline's playback lights a node or a link up at its first event inside the brush
    window, so the answer is the earliest event *in the window*, not the earliest ever, and a node
    is first seen at whichever end of whichever link it is on."""
    t1 = datetime(2026, 1, 1, 9, tzinfo=UTC)
    t2 = datetime(2026, 1, 1, 10, tzinfo=UTC)
    t3 = datetime(2026, 1, 1, 11, tzinfo=UTC)
    events = [
        _event(occurred_at=t1, source_id="a", target_id="b", edge_id="ab"),  # before the window
        _event(occurred_at=t2, source_id="a", target_id="b", edge_id="ab"),
        _event(occurred_at=t3, source_id="b", target_id="c", edge_id="bc"),
    ]
    async with factory.context(events) as adapter:
        result = await adapter.first_seen(
            FirstSeenRequest(filter=_filter(window=Interval(valid_from=t2, valid_to=t3))),
            CLEARED,
        )
        assert result.nodes == {"a": t2, "b": t2, "c": t3}
        assert result.edges == {"ab": t2, "bc": t3}


async def test_first_seen_with_no_event_in_the_window_is_empty_not_an_error(
    factory: AnalyticsAdapterFactory,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    async with factory.context([_event(occurred_at=now)]) as adapter:
        later = Interval(
            valid_from=datetime(2027, 1, 1, tzinfo=UTC), valid_to=datetime(2027, 1, 2, tzinfo=UTC)
        )
        result = await adapter.first_seen(FirstSeenRequest(filter=_filter(window=later)), CLEARED)
        assert result.nodes == {}
        assert result.edges == {}


async def test_unauthorised_first_seen_matches_a_corpus_without_the_hidden_event(
    factory: AnalyticsAdapterFactory,
) -> None:
    """A hidden earlier event must not pull a node's first appearance forward for someone who may
    not see it: that would tell them something happened before what they can see."""
    early = datetime(2026, 1, 1, 8, tzinfo=UTC)
    later = datetime(2026, 1, 1, 10, tzinfo=UTC)
    req = FirstSeenRequest(filter=_filter())
    visible = [_event(occurred_at=later, classification="OFFICIAL")]
    async with factory.context(visible) as adapter:
        before = await adapter.first_seen(req, OFFICIAL)

    with_hidden = [*visible, _event(occurred_at=early, classification="SECRET")]
    async with factory.context(with_hidden) as adapter:
        after = await adapter.first_seen(req, OFFICIAL)
        assert before == after
        assert after.nodes == {"a": later, "b": later}

        authorised = await adapter.first_seen(req, CLEARED)
        assert authorised.nodes == {"a": early, "b": early}


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


# --- the geometry reference partition ---------------------------------------
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


# --- polygon geometry storage (a disclosed known-gaps closure) -------------


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
    (access control lives in the adapter, and every read path is tested for it)."""
    visible = _boundary(geometry_ref="boundary-open", classification="OFFICIAL")
    hidden = _boundary(geometry_ref="boundary-secret", classification="SECRET")
    async with factory.context([]) as adapter:
        await adapter.load_geometries([visible, hidden])
        result = await adapter.list_boundaries(OFFICIAL)
        assert {r.geometry_ref for r in result} == {"boundary-open"}
        # Proves the filter is real, not a no-op that would hide everything.
        cleared_result = await adapter.list_boundaries(CLEARED)
        assert {r.geometry_ref for r in cleared_result} == {"boundary-open", "boundary-secret"}


# --- load_events --------------------------------------------------------
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


# --- containment: A1's "incidents geocode into cells" (owner rulings R9 (c) and R10, 13cf) -----

#: Two cells splitting `_SQUARE_WKT` down the meridian -0.1; the shared edge is lon -0.1.
_WEST_WKT = "POLYGON((-0.2 51.4, -0.2 51.6, -0.1 51.6, -0.1 51.4, -0.2 51.4))"
_EAST_WKT = "POLYGON((-0.1 51.4, -0.1 51.6, 0.0 51.6, 0.0 51.4, -0.1 51.4))"
_CELLS = {"cell-a-west": "node-west", "cell-b-east": "node-east"}
_T0 = datetime(2026, 1, 1, 12, tzinfo=UTC)


def _cells(classification: str = "OFFICIAL") -> list[GeometryRecord]:
    return [
        _boundary(geometry_ref="cell-a-west", wkt=_WEST_WKT, classification=classification),
        _boundary(geometry_ref="cell-b-east", wkt=_EAST_WKT),
    ]


async def _count_in(adapter: object, value: str, principal: Principal) -> int:
    req = HistogramRequest(
        filter=_filter(value_filters={"site_cell": [value]}),
        bucketing=HistogramBucketing.FIXED_INTERVAL,
        interval_seconds=3600,
    )
    return (await adapter.histogram(req, principal)).total  # type: ignore[attr-defined]


async def test_geocode_records_the_covering_cell_on_each_event_with_a_point(
    factory: AnalyticsAdapterFactory,
) -> None:
    """The row's own claim, made observable: each incident with a point inside a cell is
    returned with that cell and carries it afterwards. One outside every cell and one with no
    point at all are neither returned nor changed."""
    west = _event(occurred_at=_T0, lat=51.5, lon=-0.15)
    east = _event(occurred_at=_T0, lat=51.5, lon=-0.05)
    outside = _event(occurred_at=_T0, lat=52.5, lon=-0.15)
    pointless = _event(occurred_at=_T0)
    async with factory.context([west, east, outside, pointless]) as adapter:
        await adapter.load_geometries(_cells())
        result = await adapter.geocode_events(
            GeocodeRequest(filter=_filter(), cells=_CELLS), CLEARED
        )
        assert {(g.event_id, g.geometry_ref, g.value) for g in result} == {
            (west.event_id, "cell-a-west", "node-west"),
            (east.event_id, "cell-b-east", "node-east"),
        }
        assert [g.event_id for g in result] == sorted(g.event_id for g in result)
        assert all(g.previous_value is None for g in result)
        assert await _count_in(adapter, "node-west", CLEARED) == 1
        assert await _count_in(adapter, "node-east", CLEARED) == 1


async def test_geocode_a_point_on_a_shared_edge_lands_in_exactly_one_cell(
    factory: AnalyticsAdapterFactory,
) -> None:
    """Covering, not strict containment, so an incident on a cell boundary is still inside the
    site; the smallest ref wins, so which cell it lands in is deterministic."""
    on_edge = _event(occurred_at=_T0, lat=51.5, lon=-0.1)
    async with factory.context([on_edge]) as adapter:
        await adapter.load_geometries(_cells())
        result = await adapter.geocode_events(
            GeocodeRequest(filter=_filter(), cells=_CELLS), CLEARED
        )
        assert [(g.event_id, g.geometry_ref) for g in result] == [
            (on_edge.event_id, "cell-a-west")
        ]


async def test_geocode_twice_changes_nothing_the_second_time(
    factory: AnalyticsAdapterFactory,
) -> None:
    """What keeps a redraw idempotent: the second call reports each event's value unchanged,
    which is how the grid route knows to write no second edge."""
    west = _event(occurred_at=_T0, lat=51.5, lon=-0.15)
    async with factory.context([west]) as adapter:
        await adapter.load_geometries(_cells())
        request = GeocodeRequest(filter=_filter(), cells=_CELLS)
        await adapter.geocode_events(request, CLEARED)
        (again,) = await adapter.geocode_events(request, CLEARED)
        assert again.previous_value == again.value == "node-west"
        assert await _count_in(adapter, "node-west", CLEARED) == 1


async def test_geocode_clears_its_own_stale_value_and_leaves_other_sites_alone(
    factory: AnalyticsAdapterFactory,
) -> None:
    """An incident this set of cells no longer covers loses the cell it held; an incident
    geocoded into some other site's cell keeps that claim, because this call does not own it."""
    stale = _event(occurred_at=_T0, lat=52.5, lon=-0.15, properties={"site_cell": "node-west"})
    other = _event(occurred_at=_T0, lat=52.5, lon=-0.15, properties={"site_cell": "node-other"})
    async with factory.context([stale, other]) as adapter:
        await adapter.load_geometries(_cells())
        assert await adapter.geocode_events(
            GeocodeRequest(filter=_filter(), cells=_CELLS), CLEARED
        ) == []
        assert await _count_in(adapter, "node-west", CLEARED) == 0
        assert await _count_in(adapter, "node-other", CLEARED) == 1


async def test_geocode_neither_touches_nor_reveals_what_the_principal_cannot_see(
    factory: AnalyticsAdapterFactory,
) -> None:
    """Access control for this read path, as for every other. A SECRET incident inside a cell is
    not returned to an OFFICIAL caller and is **not geocoded** by that caller's draw, so a cleared
    analyst afterwards finds it ungeocoded rather than finding a trace of the OFFICIAL call. And a
    SECRET cell covers nothing for an OFFICIAL caller."""
    visible = _event(occurred_at=_T0, lat=51.5, lon=-0.05)
    hidden = _event(occurred_at=_T0, lat=51.5, lon=-0.05, classification="SECRET")
    in_secret_cell = _event(occurred_at=_T0, lat=51.5, lon=-0.15)
    async with factory.context([visible, hidden, in_secret_cell]) as adapter:
        await adapter.load_geometries(_cells(classification="SECRET"))
        result = await adapter.geocode_events(
            GeocodeRequest(filter=_filter(), cells=_CELLS), OFFICIAL
        )
        assert [g.event_id for g in result] == [visible.event_id]
        assert await _count_in(adapter, "node-east", CLEARED) == 1
        assert await _count_in(adapter, "node-west", CLEARED) == 0


async def test_geocode_uses_only_polygon_rows(factory: AnalyticsAdapterFactory) -> None:
    """A point row named in `cells` has no extent, so it covers nothing, even an event sitting
    exactly on it. This is what a pre-R9 cell's point row would do if a caller passed it."""
    on_point = _event(occurred_at=_T0, lat=51.5072, lon=-0.1276)
    async with factory.context([on_point]) as adapter:
        await adapter.load_geometries([_geometry(geometry_ref="point-cell")])
        assert await adapter.geocode_events(
            GeocodeRequest(filter=_filter(), cells={"point-cell": "node-p"}), CLEARED
        ) == []


async def test_geocode_refuses_an_inherited_filter(factory: AnalyticsAdapterFactory) -> None:
    """Geocoding writes a case's own events. A branch's parents' events are read-only to it
    (ADR-084 Amendment 2): an inherited filter would read them and then write nothing, silently."""
    on_parent = _event(occurred_at=_T0, lat=51.5072, lon=-0.1276, investigation_scope="parent")
    async with factory.context([on_parent]) as adapter:
        await adapter.load_geometries(_cells())
        with pytest.raises(ValueError, match="inherited"):
            await adapter.geocode_events(
                GeocodeRequest(
                    filter=_filter(inherited=_inherited(["parent"], ["e1"])), cells=_CELLS
                ),
                CLEARED,
            )


# --- trend (ADR-113 decisions 1 and 2) -------------------------------------------------------------


def _week(day: int) -> datetime:
    """A moment in the week of 5 January 2026 + `day` days (5 January 2026 is a Monday)."""
    return datetime(2026, 1, 5 + day, 12, tzinfo=UTC)


async def test_trend_counts_events_per_week(factory: AnalyticsAdapterFactory) -> None:
    events = [_event(occurred_at=_week(0)), _event(occurred_at=_week(3)), _event(occurred_at=_week(8))]
    async with factory.context(events) as adapter:
        result = await adapter.trend(TrendRequest(filter=_filter()), OFFICIAL)
    assert [(p.period_start.date().isoformat(), p.value) for p in result.points] == [
        ("2026-01-05", 2.0), ("2026-01-12", 1.0)]  # fmt: skip
    assert (result.total, result.events, result.series) == (3.0, 3, [])


async def test_trend_counts_per_month(factory: AnalyticsAdapterFactory) -> None:
    events = [_event(occurred_at=datetime(2026, 1, 30, tzinfo=UTC)), _event(occurred_at=datetime(2026, 2, 2, tzinfo=UTC))]
    async with factory.context(events) as adapter:
        result = await adapter.trend(TrendRequest(filter=_filter(), interval=TrendInterval.MONTH), OFFICIAL)
    assert [p.period_start.date().isoformat() for p in result.points] == ["2026-01-01", "2026-02-01"]


async def test_trend_over_the_links_named_counts_only_events_on_them_and_a_hidden_one_moves_nothing(
    factory: AnalyticsAdapterFactory,
) -> None:
    """ADR-129: a question's evidence brief counts events per month on the links in its scope, and
    only asks by link, because an event on a link the reader may not see is not theirs to count.
    The fake the question's tests use refuses what this refuses (rule 15): an event on a link
    outside the list counts for nothing, and an event the reader may not see, on a link in the
    list, moves no figure."""
    visible = [
        _event(occurred_at=_week(0), edge_id="ab"),
        _event(occurred_at=_week(1), edge_id="ab"),
    ]
    elsewhere = _event(occurred_at=_week(2), edge_id="bc", source_id="b", target_id="c")
    hidden = _event(occurred_at=_week(3), edge_id="ab", classification="SECRET")
    req = TrendRequest(filter=_filter(edge_ids=["ab"]), interval=TrendInterval.MONTH)
    async with factory.context(visible) as adapter:
        before = await adapter.trend(req, OFFICIAL)
    async with factory.context([*visible, elsewhere, hidden]) as adapter:
        after = await adapter.trend(req, OFFICIAL)
        cleared = await adapter.trend(req, CLEARED)
    assert before.events == 2
    assert after == before, "an event on another link, or one above the reader, moves nothing"
    assert cleared.events == 3


async def test_unauthorised_event_moves_no_trend_point_total_or_classification(
    factory: AnalyticsAdapterFactory,
) -> None:
    visible = [_event(occurred_at=_week(0), edge_type="TRANSACTED", properties={"amount": 10})]
    req = TrendRequest(filter=_filter(), measure=TrendMeasure.SUM, measure_field="amount", group_by="edge_type")
    async with factory.context(visible) as adapter:
        before = await adapter.trend(req, OFFICIAL)
    hidden = _event(occurred_at=_week(7), edge_type="WIRED", classification="SECRET", properties={"amount": 999})
    async with factory.context([*visible, hidden]) as adapter:
        after = await adapter.trend(req, OFFICIAL)
        cleared = await adapter.trend(req, CLEARED)
    assert after == before, "a hidden event adds no point, series, total or classification"
    assert before.classifications == ["OFFICIAL"]
    assert cleared.total == 1009.0 and set(cleared.classifications) == {"OFFICIAL", "SECRET"}
    assert cleared.series == ["TRANSACTED", "WIRED"]


async def test_trend_sums_a_property_and_says_what_it_could_not_sum(factory: AnalyticsAdapterFactory) -> None:
    events = [_event(occurred_at=_week(0), properties={"amount": 100.5}),
              _event(occurred_at=_week(1), properties={"amount": "200"}),
              _event(occurred_at=_week(2), properties={"amount": "not a number"}),
              _event(occurred_at=_week(2))]  # fmt: skip
    async with factory.context(events) as adapter:
        result = await adapter.trend(TrendRequest(filter=_filter(), measure=TrendMeasure.SUM, measure_field="amount"), OFFICIAL)
    assert result.total == 300.5 and result.events == 4 and result.unvalued == 2


async def test_trend_splits_series_by_a_property(factory: AnalyticsAdapterFactory) -> None:
    events = [_event(occurred_at=_week(0), properties={"channel": "cash"}),
              _event(occurred_at=_week(0), properties={"channel": "wire"}),
              _event(occurred_at=_week(7), properties={"channel": "cash"})]  # fmt: skip  — the next week
    async with factory.context(events) as adapter:
        result = await adapter.trend(TrendRequest(filter=_filter(), group_by="channel"), OFFICIAL)
    assert result.series == ["cash", "wire"]
    assert sorted((p.series, p.value) for p in result.points) == [("cash", 1.0), ("cash", 1.0), ("wire", 1.0)]


async def test_a_trend_past_its_bounds_is_refused_not_cut(factory: AnalyticsAdapterFactory) -> None:
    events = [_event(occurred_at=_week(7 * i), properties={"channel": f"c{i}"}) for i in range(4)]
    async with factory.context(events) as adapter:
        with pytest.raises(TrendLimitExceeded) as periods:
            await adapter.trend(TrendRequest(filter=_filter(), max_periods=3), OFFICIAL)
        with pytest.raises(TrendLimitExceeded) as series:
            await adapter.trend(TrendRequest(filter=_filter(), group_by="channel", max_series=3), OFFICIAL)
    assert (periods.value.cap_kind, periods.value.would_be) == ("periods", 4)
    assert (series.value.cap_kind, series.value.would_be) == ("series", 4)


async def test_the_trend_bound_counts_only_what_the_reader_sees(factory: AnalyticsAdapterFactory) -> None:
    """A hidden event in a fourth week must not tip a three-week trend over its bound."""
    events = [_event(occurred_at=_week(7 * i)) for i in range(3)]
    events.append(_event(occurred_at=_week(21), classification="SECRET"))
    async with factory.context(events) as adapter:
        result = await adapter.trend(TrendRequest(filter=_filter(), max_periods=3), OFFICIAL)
    assert result.events == 3


async def test_trend_says_the_handling_it_counted_and_only_what_the_reader_sees(
    factory: AnalyticsAdapterFactory,
) -> None:
    """A pack's snapshot is read by people other than its author (ADR-113 Amendment 1), so it must
    know every distinct handling it rests on — a restricted code and its units included, not only
    the classification — and a hidden event must add none."""
    events = [_event(occurred_at=_week(0)),
              _event(occurred_at=_week(1)),
              _event(occurred_at=_week(2), handling_code="R", owning_unit="unit-1", originator="unit-9"),
              _event(occurred_at=_week(3), classification="SECRET", handling_code="C")]  # fmt: skip
    receives_r = Principal(id="a-r", clearance="OFFICIAL", org_unit="unit-1", receivable_handling_codes=["R"])
    async with factory.context(events) as adapter:
        restricted = await adapter.trend(TrendRequest(filter=_filter()), receives_r)
        official = await adapter.trend(TrendRequest(filter=_filter()), OFFICIAL)
        cleared = await adapter.trend(TrendRequest(filter=_filter()), CLEARED)

    def seen(result: TrendResult) -> set[tuple[str, str, str, str]]:
        return {(h.classification, h.handling_code, h.owning_unit, h.originator) for h in result.handlings}

    assert seen(restricted) == {("OFFICIAL", "P", "unit-1", "unit-1"), ("OFFICIAL", "R", "unit-1", "unit-9")}
    assert len(restricted.handlings) == 2, "each distinct handling once"
    assert seen(official) == {("OFFICIAL", "P", "unit-1", "unit-1")}, "a hidden event adds no handling"
    assert ("SECRET", "C", "unit-1", "unit-1") in seen(cleared)


# --- retract_load (ADR-127 decision 6) --------------------------------------------------------
#
# A Studio load can be reverted, and its events must go with it: an event of a reverted load left in
# the store would still move a trend, a histogram and a first-seen, for a node the graph no longer
# holds. Every event a load wrote carries its `load_id`; `retract_load` removes those and nothing
# else. It is a write, but every read after it must answer as if the load had never been, for every
# principal, including for an event that principal could not read before.

LOAD_A = "load-a"
LOAD_B = "load-b"


def _a_and_b_and_unattributed() -> list[EventRecord]:
    """Load A: three events (one on a SECRET marking), load B: two, and one with no load at all.
    Distinct nodes and links per group, so a first-seen or a sighting says which group it came from;
    every one carries a position, so a geo bin counts it."""
    return [
        _event(occurred_at=_week(0), source_id="a1", target_id="a2", edge_id="ea", load_id=LOAD_A, lat=51.5, lon=-0.12),
        _event(occurred_at=_week(1), source_id="a1", target_id="a2", edge_id="ea", load_id=LOAD_A, lat=51.5, lon=-0.12),
        _event(occurred_at=_week(2), source_id="a3", target_id="a4", edge_id="ea2", load_id=LOAD_A, classification="SECRET", lat=51.5, lon=-0.12),
        _event(occurred_at=_week(3), source_id="b1", target_id="b2", edge_id="eb", load_id=LOAD_B, lat=51.5, lon=-0.12),
        _event(occurred_at=_week(4), source_id="b1", target_id="b2", edge_id="eb", load_id=LOAD_B, lat=51.5, lon=-0.12),
        _event(occurred_at=_week(5), source_id="u1", target_id="u2", edge_id="eu", lat=51.5, lon=-0.12),
    ]  # fmt: skip


_HOUR = HistogramRequest(
    filter=_filter(), bucketing=HistogramBucketing.FIXED_INTERVAL, interval_seconds=3600
)


#: Load A's events fall in the baseline window (days 0-2 of the week), load B's and the unattributed
#: event in the comparison window (days 3-5), so a retract moves both counts.
_BASELINE = BaselineRequest(
    filter=_filter(),
    baseline_window=Interval(valid_from=_week(0), valid_to=_week(3)),
    comparison_window=Interval(valid_from=_week(3), valid_to=_week(6)),
    bucketing=HistogramBucketing.FIXED_INTERVAL,
    interval_seconds=3600,
)
#: One cell around every event's point (51.5, -0.12), so `geocode_events` covers them all.
_GEOCODE = GeocodeRequest(filter=_filter(), cells={"cell-1": "node-1"})


async def _everything_a_reader_can_ask(adapter: object, principal: Principal) -> dict[str, object]:
    """Every read the suite has that counts or lists events, as plain data, so two stores can be
    compared whole."""
    a: AnalyticsPort = adapter  # type: ignore[assignment]
    return {
        "histogram": (await a.histogram(_HOUR, principal)).model_dump(),
        "cross_filter": {
            name: h.model_dump()
            for name, h in (
                await a.cross_filter(
                    CrossFilterRequest(
                        filter=_filter(),
                        dimensions=[
                            CrossFilterDimension(
                                name="hour",
                                bucketing=HistogramBucketing.FIXED_INTERVAL,
                                interval_seconds=3600,
                            ),
                            CrossFilterDimension(
                                name="kind", bucketing=HistogramBucketing.CATEGORICAL, field="edge_type"
                            ),
                        ],
                    ),
                    principal,
                )
            ).items()
        },
        "trend": (await a.trend(TrendRequest(filter=_filter()), principal)).model_dump(),
        "geo_bins": [b.model_dump() for b in await a.geo_bins(GeoBinRequest(filter=_filter(), precision=4), principal)],
        "first_seen": (await a.first_seen(FirstSeenRequest(filter=_filter()), principal)).model_dump(),
        "sightings": [s.model_dump() for s in await a.list_sightings(SightingRequest(filter=_filter()), principal)],
        "events": (await a.list_events(EventListRequest(filter=_filter(), limit=200), principal)).model_dump(),
        "baseline": (await a.baseline(_BASELINE, principal)).model_dump(),
        "geocode": [g.model_dump() for g in await a.geocode_events(_GEOCODE, principal)],
    }  # fmt: skip


async def test_an_event_keeps_the_load_that_wrote_it(factory: AnalyticsAdapterFactory) -> None:
    async with factory.context(_a_and_b_and_unattributed()) as adapter:
        page = await adapter.list_events(EventListRequest(filter=_filter(), limit=200), CLEARED)
    by_load = sorted(str(e.load_id) for e in page.events)
    assert by_load == sorted([LOAD_A] * 3 + [LOAD_B] * 2 + ["None"])


async def test_retract_load_removes_that_loads_events_from_every_read_and_says_how_many(
    factory: AnalyticsAdapterFactory,
) -> None:
    async with factory.context(_a_and_b_and_unattributed()) as adapter:
        assert (await adapter.histogram(_HOUR, CLEARED)).total == 6
        removed = await adapter.retract_load(LOAD_A)
        assert removed == 3, "the count includes the event on a marking nobody here may read"

        assert (await adapter.histogram(_HOUR, CLEARED)).total == 3
        crossed = await adapter.cross_filter(
            CrossFilterRequest(
                filter=_filter(),
                dimensions=[
                    CrossFilterDimension(
                        name="hour", bucketing=HistogramBucketing.FIXED_INTERVAL, interval_seconds=3600
                    )
                ],
            ),
            CLEARED,
        )
        assert crossed["hour"].total == 3
        trend = await adapter.trend(TrendRequest(filter=_filter()), CLEARED)
        assert trend.events == 3
        bins = await adapter.geo_bins(GeoBinRequest(filter=_filter(), precision=4), CLEARED)
        assert sum(b.count for b in bins) == 3
        first = await adapter.first_seen(FirstSeenRequest(filter=_filter()), CLEARED)
        assert sorted(first.nodes) == ["b1", "b2", "u1", "u2"]
        assert sorted(first.edges) == ["eb", "eu"]
        sightings = await adapter.list_sightings(SightingRequest(filter=_filter()), CLEARED)
        assert len(sightings) == 3
        page = await adapter.list_events(EventListRequest(filter=_filter(), limit=200), CLEARED)
        assert page.total == 3
        assert LOAD_A not in {e.load_id for e in page.events}


async def test_retract_load_leaves_other_loads_and_unattributed_events_untouched(
    factory: AnalyticsAdapterFactory,
) -> None:
    events = _a_and_b_and_unattributed()
    keepers = {e.event_id for e in events if e.load_id != LOAD_A}
    async with factory.context(events) as adapter:
        await adapter.retract_load(LOAD_A)
        page = await adapter.list_events(EventListRequest(filter=_filter(), limit=200), CLEARED)
        assert {e.event_id for e in page.events} == keepers
        assert sorted(str(e.load_id) for e in page.events) == ["None", LOAD_B, LOAD_B]
        # Retracting the other load too leaves exactly the unattributed event.
        assert await adapter.retract_load(LOAD_B) == 2
        page = await adapter.list_events(EventListRequest(filter=_filter(), limit=200), CLEARED)
        assert [e.load_id for e in page.events] == [None]


async def test_retract_load_is_idempotent_and_an_unknown_load_removes_nothing(
    factory: AnalyticsAdapterFactory,
) -> None:
    async with factory.context(_a_and_b_and_unattributed()) as adapter:
        assert await adapter.retract_load(LOAD_A) == 3
        assert await adapter.retract_load(LOAD_A) == 0
        assert await adapter.retract_load("never-written") == 0
        assert (await adapter.histogram(_HOUR, CLEARED)).total == 3


async def test_retract_load_on_an_empty_store_removes_nothing(factory: AnalyticsAdapterFactory) -> None:
    async with factory.context([]) as adapter:
        assert await adapter.retract_load(LOAD_A) == 0


async def test_after_a_retract_no_read_for_any_principal_returns_or_counts_a_retracted_event(
    factory: AnalyticsAdapterFactory,
) -> None:
    """Rule 4. A retract is a write, but it must not leave a trace a reader could use: after it,
    every read, for a principal who could read the retracted events and for ones who could not,
    answers exactly as a store that never held them. A retracted event on a marking the principal
    could not see must not count, list, move a first appearance or make a bucket exist."""
    events = _a_and_b_and_unattributed()
    survivors = [e for e in events if e.load_id != LOAD_A]
    receives_r = Principal(id="a-r", clearance="OFFICIAL", org_unit="unit-1", receivable_handling_codes=["R"])
    principals = [OFFICIAL, CLEARED, receives_r]

    async with factory.context(events) as adapter:
        await adapter.load_geometries([_boundary(geometry_ref="cell-1")])
        await adapter.retract_load(LOAD_A)
        after = {p.id: await _everything_a_reader_can_ask(adapter, p) for p in principals}
    async with factory.context(survivors) as adapter:
        await adapter.load_geometries([_boundary(geometry_ref="cell-1")])
        never = {p.id: await _everything_a_reader_can_ask(adapter, p) for p in principals}

    assert after == never


async def test_the_comparison_sees_a_missing_survivor_in_every_read(
    factory: AnalyticsAdapterFactory,
) -> None:
    """Rule 15 for the comparison above: it can only fail for a read it includes, and it includes
    one only if that read answers differently when a single event is missing. Each read here is
    shown to, so a retract that left an event visible to any of them would fail the comparison."""
    events = _a_and_b_and_unattributed()
    missing_one = [e for e in events if e.load_id != LOAD_A][1:]  # a survivor dropped
    async with factory.context([e for e in events if e.load_id != LOAD_A]) as adapter:
        await adapter.load_geometries([_boundary(geometry_ref="cell-1")])
        whole = await _everything_a_reader_can_ask(adapter, CLEARED)
    async with factory.context(missing_one) as adapter:
        await adapter.load_geometries([_boundary(geometry_ref="cell-1")])
        less = await _everything_a_reader_can_ask(adapter, CLEARED)
    same = sorted(name for name in whole if whole[name] == less[name])
    assert same == [], f"these reads do not notice a missing event: {same}"


async def test_a_retract_does_not_cross_investigations_it_was_not_asked_about(
    factory: AnalyticsAdapterFactory,
) -> None:
    """A `load_id` names one load, which writes one case; events of another case with another load
    stay. (A load id shared across cases is not a state the engine produces.)"""
    events = [
        _event(occurred_at=_week(0), load_id=LOAD_A),
        _event(occurred_at=_week(1), load_id=LOAD_B, investigation_scope="case-2"),
    ]
    async with factory.context(events) as adapter:
        assert await adapter.retract_load(LOAD_A) == 1
        other = EventFilter(investigation_scope="case-2")
        page = await adapter.list_events(EventListRequest(filter=other), CLEARED)
        assert page.total == 1


# --- withdraw_events_by_id (ADR-110 Amendments 8 point 1 and 15): a dropped row's own events -----
#
# A full snapshot's refresh withdraws a dropped row's own events, named by the ids its record keeps,
# so no trend, histogram or timeline counts a row the snapshot no longer carries. Never by link
# (Amendment 15): another row's event on the same link, of this load, another or another case, stays.
# The events are set aside, not deleted: reverting the refresh puts back exactly those. As
# `retract_load`, every read after a withdrawal answers, for every principal, as a store that never
# held the events.

REFRESH = "load-refresh"
REFRESH_2 = "load-refresh-2"


def _three_principals() -> list[Principal]:
    receives_r = Principal(id="a-r", clearance="OFFICIAL", org_unit="unit-1", receivable_handling_codes=["R"])
    return [OFFICIAL, CLEARED, receives_r]  # fmt: skip


async def _reads_of(factory: AnalyticsAdapterFactory, events: list[EventRecord]) -> dict[str, object]:
    async with factory.context(events) as adapter:
        await adapter.load_geometries([_boundary(geometry_ref="cell-1")])
        return {p.id: await _everything_a_reader_can_ask(adapter, p) for p in _three_principals()}


def _ids_on(events: list[EventRecord], *edge_ids: str) -> list[str]:
    return [e.event_id for e in events if e.edge_id in edge_ids]


async def test_withdraw_events_by_id_takes_exactly_those_events_out_of_every_read(
    factory: AnalyticsAdapterFactory,
) -> None:
    """Rule 4: the withdrawn events include one on a SECRET marking, counted in the answer and left
    out of every read for every principal, including those who could never read it. An id no event
    holds is not counted."""
    events = _a_and_b_and_unattributed()
    chosen = _ids_on(events, "ea", "ea2")
    async with factory.context(events) as adapter:
        await adapter.load_geometries([_boundary(geometry_ref="cell-1")])
        assert await adapter.withdraw_events_by_id([*chosen, "no-such-event"], REFRESH) == 3
        after = {p.id: await _everything_a_reader_can_ask(adapter, p) for p in _three_principals()}
    assert after == await _reads_of(factory, [e for e in events if e.event_id not in chosen])


async def test_withdraw_events_by_id_leaves_every_other_event_on_the_same_link(
    factory: AnalyticsAdapterFactory,
) -> None:
    """Amendment 15, rule 3: one of link `ea`'s two events is withdrawn; the other (the same load's
    other row), another load's event on `ea` and another case's event on `ea` all stay, for every
    principal. A withdrawal by link would take all four."""
    events = _a_and_b_and_unattributed()
    other_load = _event(occurred_at=_week(6), source_id="a1", target_id="a2", edge_id="ea", load_id=LOAD_B, lat=51.5, lon=-0.12)  # fmt: skip
    other_case = _event(occurred_at=_week(7), source_id="a1", target_id="a2", edge_id="ea", load_id="load-c", investigation_scope="case-2")  # fmt: skip
    events = [*events, other_load, other_case]
    dropped = events[0]
    async with factory.context(events) as adapter:
        await adapter.load_geometries([_boundary(geometry_ref="cell-1")])
        assert await adapter.withdraw_events_by_id([dropped.event_id], REFRESH) == 1
        after = {p.id: await _everything_a_reader_can_ask(adapter, p) for p in _three_principals()}
        theirs = await adapter.list_events(
            EventListRequest(filter=EventFilter(investigation_scope="case-2")), CLEARED
        )
    assert [e.event_id for e in theirs.events] == [other_case.event_id]
    assert after == await _reads_of(factory, events[1:])


async def test_withdraw_events_by_id_takes_more_ids_than_one_statement_holds(
    factory: AnalyticsAdapterFactory,
) -> None:
    """A refresh dropping many rows names many events: every one is set aside, in bounded
    statements (2,500 ids, over the adapters' chunk of 1,000), and the one left out stays."""
    events = [_event(occurred_at=_week(i % 7), edge_id=f"e{i}", load_id=LOAD_A) for i in range(2_501)]
    async with factory.context(events) as adapter:
        assert await adapter.withdraw_events_by_id([e.event_id for e in events[:-1]], REFRESH) == 2_500
        page = await adapter.list_events(EventListRequest(filter=_filter(), limit=10), CLEARED)
        assert [e.event_id for e in page.events] == [events[-1].event_id]
        assert await adapter.restore_withdrawn_events(REFRESH) == 2_500


async def test_restore_withdrawn_events_puts_back_exactly_what_that_load_withdrew(
    factory: AnalyticsAdapterFactory,
) -> None:
    events = _a_and_b_and_unattributed()
    async with factory.context(events) as adapter:
        await adapter.load_geometries([_boundary(geometry_ref="cell-1")])
        await adapter.withdraw_events_by_id(_ids_on(events, "ea", "ea2"), REFRESH)
        await adapter.withdraw_events_by_id(_ids_on(events, "eb"), REFRESH_2)
        assert await adapter.restore_withdrawn_events(REFRESH) == 3
        restored = {p.id: await _everything_a_reader_can_ask(adapter, p) for p in _three_principals()}
    # Each event comes back as it was, its id and its load included; the other refresh's stay out.
    assert restored == await _reads_of(factory, [e for e in events if e.edge_id != "eb"])


async def test_withdraw_and_restore_are_idempotent_and_ask_nothing_of_no_ids(
    factory: AnalyticsAdapterFactory,
) -> None:
    events = _a_and_b_and_unattributed()
    on_ea = _ids_on(events, "ea")
    async with factory.context(events) as adapter:
        assert await adapter.withdraw_events_by_id([], REFRESH) == 0
        assert await adapter.withdraw_events_by_id([*on_ea, *on_ea], REFRESH) == 2
        assert await adapter.withdraw_events_by_id(on_ea, REFRESH) == 0
        # An event already set aside stays with the load that set it aside.
        assert await adapter.withdraw_events_by_id(on_ea, REFRESH_2) == 0
        assert await adapter.restore_withdrawn_events(REFRESH_2) == 0
        assert await adapter.restore_withdrawn_events("never-withdrew") == 0
        assert (await adapter.histogram(_HOUR, CLEARED)).total == 4
        assert await adapter.restore_withdrawn_events(REFRESH) == 2
        assert await adapter.restore_withdrawn_events(REFRESH) == 0
        assert (await adapter.histogram(_HOUR, CLEARED)).total == 6


async def test_retracting_the_load_that_wrote_withdrawn_events_leaves_nothing_to_restore(
    factory: AnalyticsAdapterFactory,
) -> None:
    """Amendment 8 point 1, as Amendment 6 point 3 has it for the graph: reverting the load that
    created the events removes them wherever they are, so a later restore cannot bring back an event
    of a reverted load. The count includes the ones set aside."""
    events = _a_and_b_and_unattributed()
    async with factory.context(events) as adapter:
        await adapter.load_geometries([_boundary(geometry_ref="cell-1")])
        await adapter.withdraw_events_by_id(_ids_on(events, "ea"), REFRESH)
        assert await adapter.retract_load(LOAD_A) == 3
        assert await adapter.restore_withdrawn_events(REFRESH) == 0
        after = {p.id: await _everything_a_reader_can_ask(adapter, p) for p in _three_principals()}
    assert after == await _reads_of(factory, [e for e in events if e.load_id != LOAD_A])


async def test_retracting_the_withdrawing_load_takes_its_own_events_and_no_other_loads(
    factory: AnalyticsAdapterFactory,
) -> None:
    """The refresh's own events (its new rows') carry its load id and go with its revert; the events
    it set aside belong to the loads that wrote them and are put back by the restore alone."""
    own = _event(occurred_at=_week(6), source_id="r1", target_id="r2", edge_id="er", load_id=REFRESH)
    events = _a_and_b_and_unattributed()
    async with factory.context([*events, own]) as adapter:
        await adapter.withdraw_events_by_id(_ids_on(events, "eb"), REFRESH)
        assert await adapter.retract_load(REFRESH) == 1
        assert await adapter.restore_withdrawn_events(REFRESH) == 2
        page = await adapter.list_events(EventListRequest(filter=_filter(), limit=200), CLEARED)
        assert sorted(str(e.load_id) for e in page.events) == sorted([LOAD_A] * 3 + [LOAD_B] * 2 + ["None"])


# --- retract_geometries (ADR-127 decision 6, B2-4c): taking back the points a load inserted ----
#
# A load records the refs of the points it inserted that were not already there, so a revert can
# remove exactly those from the geometry partition and leave every other row.


async def test_retract_geometries_removes_the_named_refs_at_that_version_and_nothing_else(
    factory: AnalyticsAdapterFactory,
) -> None:
    ours = _geometry(geometry_ref="geo-ours", version=1)
    ours_later = _geometry(geometry_ref="geo-ours", version=2, lon=-0.2)
    other = _geometry(geometry_ref="geo-other", version=1, lon=-0.3)
    async with factory.context([]) as adapter:
        await adapter.load_geometries([ours, ours_later, other])
        assert await adapter.retract_geometries(["geo-ours", "geo-missing"], version=1) == 1
        assert await adapter.get_geometry("geo-ours", CLEARED, version=1) is None
        assert await adapter.get_geometry("geo-ours", CLEARED, version=2) == ours_later
        assert await adapter.get_geometry("geo-other", CLEARED, version=1) == other
        found = await adapter.get_geometries(["geo-ours", "geo-other"], CLEARED, version=1)
        assert [g.geometry_ref for g in found] == ["geo-other"]


async def test_retract_geometries_is_idempotent_and_takes_no_refs_as_nothing(
    factory: AnalyticsAdapterFactory,
) -> None:
    async with factory.context([]) as adapter:
        await adapter.load_geometries([_geometry(geometry_ref="geo-ours")])
        assert await adapter.retract_geometries([], version=1) == 0
        assert await adapter.retract_geometries(["geo-ours"], version=1) == 1
        assert await adapter.retract_geometries(["geo-ours"], version=1) == 0
        assert await adapter.retract_geometries(["never-written"], version=1) == 0


async def test_retract_geometries_counts_and_removes_a_row_no_reader_here_may_read(
    factory: AnalyticsAdapterFactory,
) -> None:
    """Like `retract_load` it is a backend write, whatever the marking: a point above every reader
    in the test is removed and counted, and none of its detail is left for the cleared reader."""
    hidden = _geometry(geometry_ref="geo-hidden", classification="SECRET")
    async with factory.context([]) as adapter:
        await adapter.load_geometries([hidden])
        assert await adapter.get_geometry("geo-hidden", OFFICIAL) is None
        assert await adapter.get_geometry("geo-hidden", CLEARED) is not None
        assert await adapter.retract_geometries(["geo-hidden"], version=1) == 1
        assert await adapter.get_geometry("geo-hidden", CLEARED) is None


async def test_retract_geometries_leaves_a_polygon_of_the_same_ref_at_another_version(
    factory: AnalyticsAdapterFactory,
) -> None:
    point = _geometry(geometry_ref="geo-1", version=1)
    boundary = _boundary(geometry_ref="geo-b", version=2)
    async with factory.context([]) as adapter:
        await adapter.load_geometries([point, boundary])
        assert await adapter.retract_geometries(["geo-1", "geo-b"], version=1) == 1
        assert [b.geometry_ref for b in await adapter.list_boundaries(CLEARED, version=2)] == [
            "geo-b"
        ]


# --- events_of_load_among (ADR-127 Amendment 8, B2-4c2): which events an alert cites are a load's ----
#
# An alert names the events it rests on by id. When a revert retracts a load's events, an alert
# citing one of them must be closed; the revert asks which of the ids an alert names are the load's,
# among ids it already holds (never a list of the load's events, which can be millions).


async def test_events_of_load_among_names_only_that_loads_events_whatever_their_marking(
    factory: AnalyticsAdapterFactory,
) -> None:
    events = _a_and_b_and_unattributed()
    async with factory.context(events) as adapter:
        page = await adapter.list_events(EventListRequest(filter=_filter(), limit=200), CLEARED)
        by_load: dict[str | None, list[str]] = {}
        for e in page.events:
            by_load.setdefault(e.load_id, []).append(e.event_id)
        everything = [i for ids in by_load.values() for i in ids]
        found = await adapter.events_of_load_among(LOAD_A, [*everything, "no-such-event"])
        assert found == set(by_load[LOAD_A]) and len(found) == 3
        # The SECRET event of A is among them though OFFICIAL cannot read it.
        official = await adapter.list_events(EventListRequest(filter=_filter(), limit=200), OFFICIAL)
        assert len({e.event_id for e in official.events} & found) == 2
        assert await adapter.events_of_load_among(LOAD_B, by_load[LOAD_A]) == set()
        assert await adapter.events_of_load_among(LOAD_A, []) == set()
        assert await adapter.events_of_load_among("never-wrote", everything) == set()


async def test_events_of_load_among_is_not_what_it_was_after_a_retract(
    factory: AnalyticsAdapterFactory,
) -> None:
    """Asked before the retract it says which ids are the load's; after, none (they are gone), so
    the revert asks first and closes the alerts, in one step, before it retracts."""
    async with factory.context(_a_and_b_and_unattributed()) as adapter:
        page = await adapter.list_events(EventListRequest(filter=_filter(), limit=200), CLEARED)
        ids = [e.event_id for e in page.events]
        assert len(await adapter.events_of_load_among(LOAD_A, ids)) == 3
        assert await adapter.retract_load(LOAD_A) == 3
        assert await adapter.events_of_load_among(LOAD_A, ids) == set()


# --- alert trends (ADR-134 decision 3) --------------------------------------------------------------
#
# Written before either adapter had `alert_trend` (rule 1). An alert's visibility is all or nothing
# over every handling it rests on, its audience (the case for a typology alert; the owner, or the
# owner's team when shared, for a hotlist or monitor alert) and the reader's datasets — each decided
# in the query. Each "hidden" plant below is a fact that differs from a visible one in exactly the
# one respect under test, so a trend that ignored that respect would count it.

from schemas.analytics import AlertFact, AlertTrendRequest  # noqa: E402

COLLEAGUE = Principal(id="colleague", clearance="SECRET", org_unit="unit-1")
STRANGER = Principal(id="stranger", clearance="SECRET", org_unit="unit-2")
ALERT_WINDOW = Interval(valid_from=datetime(2026, 1, 1, tzinfo=UTC), valid_to=datetime(2026, 6, 30, tzinfo=UTC))


def _fact(
    *,
    raised_at: datetime,
    kind: str = "typology",
    rule: str = "typology:r1",
    typology: str | None = "structuring",
    severity: str = "medium",
    outcome: str = "open",
    owner_id: str = "analyst-official",
    audience: str = "case",
    team: str | None = None,
    dataset_id: str | None = None,
    investigation_scope: str | None = INVESTIGATION,
    handlings: list[Handling] | None = None,
    alert_id: str | None = None,
) -> AlertFact:
    return AlertFact(
        alert_id=alert_id or str(ULID()), investigation_scope=investigation_scope, kind=kind,  # type: ignore[arg-type]
        rule=rule, typology=typology if kind == "typology" else None, severity=severity,  # type: ignore[arg-type]
        outcome=outcome, raised_at=raised_at, owner_id=owner_id, audience=audience,  # type: ignore[arg-type]
        team=team, dataset_id=dataset_id,
        handlings=[_handling("OFFICIAL")] if handlings is None else handlings,
    )  # fmt: skip


def _alerts(**kwargs: object) -> AlertTrendRequest:
    return AlertTrendRequest(investigation_scope=INVESTIGATION, window=ALERT_WINDOW, **kwargs)  # type: ignore[arg-type]


async def _alert_trend(factory: AnalyticsAdapterFactory, facts: list[AlertFact], req: AlertTrendRequest,
                       *readers: Principal) -> list[TrendResult]:  # fmt: skip
    async with factory.context([]) as adapter:
        await adapter.load_alert_facts(facts)
        return [await adapter.alert_trend(req, reader) for reader in readers]


async def test_alert_trend_counts_alerts_raised_per_week_and_month(factory: AnalyticsAdapterFactory) -> None:
    facts = [_fact(raised_at=_week(0)), _fact(raised_at=_week(3)), _fact(raised_at=_week(8))]
    weekly, = await _alert_trend(factory, facts, _alerts(), OFFICIAL)
    assert [(p.period_start.date().isoformat(), p.value) for p in weekly.points] == [
        ("2026-01-05", 2.0), ("2026-01-12", 1.0)]  # fmt: skip
    assert (weekly.total, weekly.events, weekly.series) == (3.0, 3, [])
    monthly, = await _alert_trend(factory, facts, _alerts(interval=TrendInterval.MONTH), OFFICIAL)
    assert [(p.period_start.date().isoformat(), p.value) for p in monthly.points] == [("2026-01-01", 3.0)]


async def test_alert_trend_splits_by_rule_typology_severity_or_outcome(factory: AnalyticsAdapterFactory) -> None:
    facts = [
        _fact(raised_at=_week(0), rule="typology:r1", typology="structuring", severity="medium", outcome="open"),
        _fact(raised_at=_week(0), rule="typology:r2", typology="rapid_movement", severity="low",
              outcome="true_positive"),
        _fact(raised_at=_week(1), kind="hotlist", rule="hotlists", severity="high", outcome="claimed",
              audience="owner"),
        _fact(raised_at=_week(1), kind="monitor", rule="monitors", severity="medium", outcome="false_positive",
              audience="owner"),
    ]  # fmt: skip
    by = {}
    for field in ("rule", "typology", "severity", "outcome"):
        (by[field],) = await _alert_trend(factory, facts, _alerts(group_by=field), OFFICIAL)
    assert by["rule"].series == ["hotlists", "monitors", "typology:r1", "typology:r2"]
    assert by["typology"].series == ["rapid_movement", "structuring"], "a hotlist has no typology: no series"
    assert by["typology"].total == 4.0, "an alert with no typology still counts, under no series"
    assert by["severity"].series == ["high", "low", "medium"]
    assert by["outcome"].series == ["claimed", "false_positive", "open", "true_positive"]


async def test_alert_trend_filters_by_equalities(factory: AnalyticsAdapterFactory) -> None:
    facts = [_fact(raised_at=_week(0), severity="high"), _fact(raised_at=_week(0), severity="low"),
             _fact(raised_at=_week(0), severity="high", outcome="true_positive")]  # fmt: skip
    (high,) = await _alert_trend(factory, facts, _alerts(filters={"severity": ["high"]}), OFFICIAL)
    (both,) = await _alert_trend(
        factory, facts, _alerts(filters={"severity": ["high"], "outcome": ["open"]}), OFFICIAL)
    assert (high.events, both.events) == (2, 1)


async def test_an_alert_resting_on_a_handling_the_reader_may_not_view_moves_nothing(
    factory: AnalyticsAdapterFactory,
) -> None:
    """ADR-134's test: "an alert trend counted as a reader leaves out alerts on nodes they may not
    see". The hidden alert rests on one OFFICIAL and one SECRET handling, so a trend that checked
    any one handling, rather than every one, would count it."""
    visible = [_fact(raised_at=_week(0), severity="medium")]
    hidden = _fact(raised_at=_week(8), severity="high", handlings=[_handling("OFFICIAL"), _handling("SECRET")])
    req = _alerts(group_by="severity")
    (before,) = await _alert_trend(factory, visible, req, OFFICIAL)
    after, cleared = await _alert_trend(factory, [*visible, hidden], req, OFFICIAL, CLEARED)
    assert after == before, "a hidden alert adds no point, series, total, classification or handling"
    assert cleared.events == 2 and cleared.series == ["high", "medium"]
    assert set(cleared.classifications) == {"OFFICIAL", "SECRET"}


async def test_an_alert_on_a_restricted_handling_is_counted_only_within_its_units(
    factory: AnalyticsAdapterFactory,
) -> None:
    restricted = _handling("OFFICIAL", handling_code="R", owning_unit="unit-1", originator="unit-9")
    facts = [_fact(raised_at=_week(0), handlings=[restricted])]
    receives_r = Principal(id="r-in", clearance="OFFICIAL", org_unit="unit-1", receivable_handling_codes=["R"])
    elsewhere = Principal(id="r-out", clearance="SECRET", org_unit="unit-2", receivable_handling_codes=["R"])
    inside, cleared_only, outside = await _alert_trend(factory, facts, _alerts(), receives_r, CLEARED, elsewhere)
    assert (inside.events, cleared_only.events, outside.events) == (1, 0, 0)
    assert [(h.handling_code, h.originator) for h in inside.handlings] == [("R", "unit-9")]


async def test_an_alert_with_handlings_not_known_is_counted_for_no_one(factory: AnalyticsAdapterFactory) -> None:
    """Fail closed: an alert kept before its handlings were, counted by nobody — not its owner,
    not the most cleared reader. An alert citing nothing (a `notify` stub) is its owner's."""
    unknown = AlertFact.model_validate({**_fact(raised_at=_week(0)).model_dump(), "handlings": None})
    stub = _fact(raised_at=_week(0), kind="hotlist", rule="hotlists", audience="owner", owner_id="analyst-secret",
                 handlings=[])  # fmt: skip
    owner, official = await _alert_trend(factory, [unknown, stub], _alerts(), CLEARED, OFFICIAL)
    assert (owner.events, official.events) == (1, 0)


async def test_an_only_me_hotlist_alert_is_counted_for_its_owner_and_no_one_else(
    factory: AnalyticsAdapterFactory,
) -> None:
    """ADR-133 decision 5 through ADR-134 decision 2: kept "only me", a hotlist's alerts are its
    owner's alone — a colleague in the same unit, cleared higher, does not count them. Shared with
    the team, the colleague does; someone of another unit still does not."""
    mine = _fact(raised_at=_week(0), kind="hotlist", rule="hotlists", audience="owner", owner_id="analyst-official",
                 team="unit-1")  # fmt: skip
    shared = _fact(raised_at=_week(1), kind="monitor", rule="monitors", audience="team", owner_id="analyst-official",
                   team="unit-1")  # fmt: skip
    owner, colleague, stranger = await _alert_trend(
        factory, [mine, shared], _alerts(group_by="rule"), OFFICIAL, COLLEAGUE, STRANGER)
    assert owner.series == ["hotlists", "monitors"]
    assert colleague.series == ["monitors"] and colleague.events == 1
    assert stranger.events == 0


async def test_a_team_routed_alert_is_counted_for_the_teams_members_alone(
    factory: AnalyticsAdapterFactory,
) -> None:
    """ADR-146 decision 8: a rule's alert routed to a named team is counted in its case for the
    team's members alone (a member is whoever holds the team's role on this request). Not for a
    member of the case outside the team, not for the rule's deployer as its owner, and not for a
    team member reading another case. Red with the routed clause read as the case's audience, or
    with the owner clause left open to `routed`."""
    routed = _fact(raised_at=_week(0), audience="routed", team="team-1", owner_id="analyst-official")
    plain = _fact(raised_at=_week(0))
    member = STRANGER.model_copy(update={"roles": ["role:team-1"]})
    other_team = STRANGER.model_copy(update={"roles": ["role:team-2"]})
    in_team, outside, deployer, elsewhere = await _alert_trend(
        factory, [routed, plain], _alerts(), member, other_team, OFFICIAL, member)
    assert in_team.events == 2, "a member of the team counts the routed alert in its case"
    assert outside.events == 1, "a case member outside the team does not"
    assert deployer.events == 1, "the rule's deployer, outside the team, does not count it as its owner"
    (other_case,) = await _alert_trend(
        factory, [routed], AlertTrendRequest(investigation_scope="case-2", window=ALERT_WINDOW), member)
    assert other_case.events == 0, "a team member counts it only in the case it was raised in"


async def test_a_case_alert_is_counted_in_its_own_case_only(factory: AnalyticsAdapterFactory) -> None:
    facts = [_fact(raised_at=_week(0)), _fact(raised_at=_week(0), investigation_scope="case-2")]
    reader, = await _alert_trend(factory, facts, _alerts(), STRANGER)
    assert reader.events == 1, "a typology alert is its case's members', whoever deployed the rule"


async def test_an_alert_outside_the_readers_datasets_is_not_counted(factory: AnalyticsAdapterFactory) -> None:
    """ADR-099's third axis, as the queue reads it (`reach_clause`): an alert of another dataset is
    not in the case's world; one that names no dataset stays in reach."""
    facts = [_fact(raised_at=_week(0), dataset_id="ds-1"), _fact(raised_at=_week(0), dataset_id="ds-2"),
             _fact(raised_at=_week(0), dataset_id=None)]  # fmt: skip
    in_case = OFFICIAL.model_copy(update={"datasets": ["ds-1"]})
    no_datasets = OFFICIAL.model_copy(update={"datasets": []})
    scoped, nothing, unlimited = await _alert_trend(factory, facts, _alerts(), in_case, no_datasets, OFFICIAL)
    assert (scoped.events, nothing.events, unlimited.events) == (2, 1, 3)


async def test_an_alert_kept_twice_is_counted_once_as_it_now_is(factory: AnalyticsAdapterFactory) -> None:
    """Rule 12: the invariant "each write replaces what was kept for the alert" is exercised by
    writing the same alert twice — once open on an OFFICIAL handling, then closed and resting on a
    SECRET one. Kept as two rows, OFFICIAL would still count it, and CLEARED would count it twice."""
    first = _fact(raised_at=_week(0), alert_id="a-1", outcome="open")
    second = _fact(raised_at=_week(0), alert_id="a-1", outcome="true_positive", handlings=[_handling("SECRET")])
    async with factory.context([]) as adapter:
        await adapter.load_alert_facts([first])
        await adapter.load_alert_facts([second])
        official = await adapter.alert_trend(_alerts(), OFFICIAL)
        cleared = await adapter.alert_trend(_alerts(group_by="outcome"), CLEARED)
    assert official.events == 0
    assert (cleared.events, cleared.series) == (1, ["true_positive"])


async def test_an_alert_trend_past_its_bounds_is_refused_not_cut(factory: AnalyticsAdapterFactory) -> None:
    """ADR-134's test: bounded as event trends are (104 periods, 12 series by default), refused
    whole, counted from what the reader sees — a hidden alert in a fourth week tips nothing."""
    assert (AlertTrendRequest.model_fields["max_periods"].default, AlertTrendRequest.model_fields["max_series"].default) == (104, 12)
    facts = [_fact(raised_at=_week(7 * i), rule=f"typology:r{i}") for i in range(4)]
    hidden = _fact(raised_at=datetime(2026, 2, 2, 12, tzinfo=UTC), rule="typology:r9", handlings=[_handling("SECRET")])
    async with factory.context([]) as adapter:
        await adapter.load_alert_facts([*facts, hidden])
        with pytest.raises(TrendLimitExceeded) as periods:
            await adapter.alert_trend(_alerts(max_periods=3), OFFICIAL)
        with pytest.raises(TrendLimitExceeded) as series:
            await adapter.alert_trend(_alerts(group_by="rule", max_series=3), OFFICIAL)
        within = await adapter.alert_trend(_alerts(max_periods=4, group_by="rule", max_series=4), OFFICIAL)
    assert (periods.value.cap_kind, periods.value.would_be) == ("periods", 4)
    assert (series.value.cap_kind, series.value.would_be) == ("series", 4)
    assert within.events == 4


async def test_an_alert_trend_counts_only_within_its_window(factory: AnalyticsAdapterFactory) -> None:
    facts = [_fact(raised_at=_week(0)), _fact(raised_at=datetime(2025, 12, 1, tzinfo=UTC))]
    (result,) = await _alert_trend(factory, facts, _alerts(), OFFICIAL)
    assert result.events == 1


# --- event_frequency (ADR-133 decision 1, stage (b)): frequency and amount conditions -------------
#
# A rule's "N or more times in D days", "a total of an amount over X in D days" and "the first time
# ever", counted per subject as the rule's own author, the access step in the query (rule 3). Each
# hidden plant differs from a visible event in exactly the respect under test — its marking, its
# case, its link type — so a count that ignored that respect would include it.

from schemas.analytics import FrequencyRequest  # noqa: E402

FREQ_T0 = datetime(2026, 3, 2, 9, tzinfo=UTC)
FREQ_WINDOW = Interval(valid_from=datetime(2026, 3, 1, tzinfo=UTC), valid_to=datetime(2026, 5, 31, tzinfo=UTC))


def _day(n: float) -> datetime:
    from datetime import timedelta

    return FREQ_T0 + timedelta(days=n)


def _paid(day: float, amount: float | None = None, **kwargs: object) -> EventRecord:
    properties = {} if amount is None else {"amount": amount}
    return _event(occurred_at=_day(day), edge_type="TRANSACTED", source_id="acct-a",
                  target_id="acct-b", properties=properties, **kwargs)  # type: ignore[arg-type]  # fmt: skip


def _frequency(span_days: int, *, nodes: list[str] | None = None, amount: str | None = None,
               window: Interval | None = FREQ_WINDOW, edge_types: list[str] | None = None) -> FrequencyRequest:  # fmt: skip
    return FrequencyRequest(
        filter=_filter(node_ids=nodes or ["acct-a"], window=window, edge_types=edge_types or ["TRANSACTED"]),
        span_days=span_days, amount_property=amount,
    )  # fmt: skip


async def test_frequency_counts_the_most_events_in_any_span_of_the_days_asked(
    factory: AnalyticsAdapterFactory,
) -> None:
    events = [_paid(0), _paid(1), _paid(2), _paid(10)]
    async with factory.context(events) as adapter:
        two = await adapter.event_frequency(_frequency(2), OFFICIAL)
        one = await adapter.event_frequency(_frequency(1), OFFICIAL)
        thirty = await adapter.event_frequency(_frequency(30), OFFICIAL)
    assert two.nodes["acct-a"].most_in_span == 3  # days 0, 1 and 2, the span's ends included
    assert one.nodes["acct-a"].most_in_span == 2
    assert thirty.nodes["acct-a"].most_in_span == 4


@pytest.mark.parametrize(("past_the_edge", "largest"), [(1, 12.0), (-1, 18.0)])
async def test_frequency_over_a_span_past_twenty_five_days_keeps_its_edge_to_the_microsecond(
    factory: AnalyticsAdapterFactory, past_the_edge: int, largest: float,
) -> None:
    """A span of more than 2^31 ms (about 24.9 days) is counted, not refused, and its edge is exact.

    ClickHouse refuses a RANGE window offset of 2^31 or more, so the adapter once failed on any span
    past 24 days (L2.10's live run). A fix by whole seconds or milliseconds would move the edge: the
    column holds microseconds. Events at day 0 (5) and day 90 (7) are one span of 90 days, ends
    included. A third (11), one microsecond more than 90 days after day 90, is in no span with it
    (largest total 12); one microsecond less, it is (18)."""
    from datetime import timedelta

    off = timedelta(microseconds=500)  # off every second and millisecond, so no grid lands on an edge
    third = _day(180) + off + timedelta(microseconds=past_the_edge)
    events = [
        _event(occurred_at=_day(0) + off, edge_type="TRANSACTED", source_id="acct-a", target_id="acct-b",
               properties={"amount": 5.0}),
        _event(occurred_at=_day(90) + off, edge_type="TRANSACTED", source_id="acct-a", target_id="acct-b",
               properties={"amount": 7.0}),
        _event(occurred_at=third, edge_type="TRANSACTED", source_id="acct-a", target_id="acct-b",
               properties={"amount": 11.0}),
    ]  # fmt: skip
    wide = Interval(valid_from=FREQ_T0 - timedelta(days=1), valid_to=FREQ_T0 + timedelta(days=200))
    async with factory.context(events) as adapter:
        ninety = await adapter.event_frequency(_frequency(90, amount="amount", window=wide), OFFICIAL)
    assert ninety.nodes["acct-a"].most_in_span == 2  # 0 and 90, the span's far end included
    assert ninety.nodes["acct-a"].largest_total == largest


async def test_frequency_counts_events_at_one_instant_together(factory: AnalyticsAdapterFactory) -> None:
    """Ties: four events at one instant are each in every span that holds that instant, as a RANGE
    frame counts its peers, never one at a time in an arbitrary order. The tied four are the one
    largest span, so an undercount of them fails as an overcount elsewhere does."""
    events = [_paid(0), _paid(0), _paid(0), _paid(0), _paid(5), _paid(5.5), _paid(6)]
    async with factory.context(events) as adapter:
        three = await adapter.event_frequency(_frequency(3), OFFICIAL)
    assert three.nodes["acct-a"].most_in_span == 4


async def test_frequency_sums_amounts_as_decimals_and_skips_one_that_is_not(
    factory: AnalyticsAdapterFactory,
) -> None:
    """The total a rule compares is the same on every adapter: 0.1 and 0.2 make 0.3, not
    0.30000000000000004. An amount past a decimal of 38 digits, 9 after the point (1e30, inf), is no
    amount: the event is counted, its amount is not, and is never read as 0."""
    async with factory.context([_paid(0, 0.1), _paid(1, 0.2)]) as adapter:
        tenths = await adapter.event_frequency(_frequency(7, amount="amount"), OFFICIAL)
    async with factory.context([_paid(0, 1e30), _paid(1, "inf")]) as adapter:  # type: ignore[arg-type]
        huge = await adapter.event_frequency(_frequency(7, amount="amount"), OFFICIAL)
    # Past nine places an amount is rounded, on every adapter alike, never cut on one.
    async with factory.context([_paid(0, 0.1234567896), _paid(1, 1.0000000004)]) as adapter:
        tenth = await adapter.event_frequency(_frequency(7, amount="amount"), OFFICIAL)
    assert tenths.nodes["acct-a"].largest_total == 0.3
    assert tenth.nodes["acct-a"].largest_total == 1.12345679
    assert (huge.nodes["acct-a"].most_in_span, huge.nodes["acct-a"].largest_total) == (2, None)


async def test_frequency_counts_a_subject_at_either_end_and_each_event_once(
    factory: AnalyticsAdapterFactory,
) -> None:
    events = [_paid(0), _event(occurred_at=_day(1), edge_type="TRANSACTED", source_id="acct-b", target_id="acct-a"),
              _event(occurred_at=_day(1.5), edge_type="TRANSACTED", source_id="acct-a", target_id="acct-a")]  # fmt: skip
    async with factory.context(events) as adapter:
        result = await adapter.event_frequency(_frequency(7, nodes=["acct-a", "acct-b"]), OFFICIAL)
    assert result.nodes["acct-a"].most_in_span == 3  # out, in, and the one to itself counted once
    assert result.nodes["acct-b"].most_in_span == 2


async def test_frequency_totals_the_amount_named_in_the_largest_span(factory: AnalyticsAdapterFactory) -> None:
    events = [_paid(0, 4_000), _paid(1, 3_000), _paid(5, 9_000), _paid(6, 2_500), _paid(6.5)]
    async with factory.context(events) as adapter:
        result = await adapter.event_frequency(_frequency(2, amount="amount"), OFFICIAL)
        counted = await adapter.event_frequency(_frequency(2), OFFICIAL)
    assert result.nodes["acct-a"].largest_total == 11_500.0  # days 5, 6 and 6.5 (no amount adds nothing)
    assert counted.nodes["acct-a"].largest_total is None


async def test_frequency_says_the_first_event_ever_up_to_the_windows_end(factory: AnalyticsAdapterFactory) -> None:
    before = _event(occurred_at=datetime(2025, 6, 1, tzinfo=UTC), edge_type="TRANSACTED", source_id="acct-a", target_id="acct-z")
    after = _event(occurred_at=datetime(2026, 7, 1, tzinfo=UTC), edge_type="TRANSACTED", source_id="acct-c", target_id="acct-z")
    events = [before, _paid(3), after, _event(occurred_at=_day(4), edge_type="TRANSACTED", source_id="acct-c", target_id="acct-z")]
    async with factory.context(events) as adapter:
        result = await adapter.event_frequency(_frequency(7, nodes=["acct-a", "acct-c"]), OFFICIAL)
    assert result.nodes["acct-a"].first_at == datetime(2025, 6, 1, tzinfo=UTC)  # before the window: not a first
    assert result.nodes["acct-a"].most_in_span == 1  # the window bounds what is counted
    assert result.nodes["acct-c"].first_at == _day(4)  # one after the window's end is not earlier


async def test_an_event_the_author_may_not_see_adds_nothing_and_is_never_a_first(
    factory: AnalyticsAdapterFactory,
) -> None:
    """ADR-133's "a rule's frequency count leaves out a node its author may not see": the
    restricted events are what tie the subject to what is hidden. Planted in the shapes a store
    holds: SECRET, and OFFICIAL restricted to another unit."""
    hidden = [_paid(0.5, 50_000, classification="SECRET"),
              _paid(0.7, 50_000, handling_code="R", owning_unit="unit-2", originator="unit-2"),
              _event(occurred_at=datetime(2025, 1, 1, tzinfo=UTC), edge_type="TRANSACTED", source_id="acct-a",
                     target_id="acct-hidden", classification="SECRET"),
              # The same two shapes with the subject at the far end: the other branch's access step.
              _event(occurred_at=_day(0.6), edge_type="TRANSACTED", source_id="acct-b", target_id="acct-a",
                     classification="SECRET", properties={"amount": 50_000}),
              _event(occurred_at=_day(0.8), edge_type="TRANSACTED", source_id="acct-b", target_id="acct-a",
                     handling_code="R", owning_unit="unit-2", originator="unit-2", properties={"amount": 50_000})]  # fmt: skip
    events = [_paid(0, 100), _paid(1, 100), *hidden]
    async with factory.context(events) as adapter:
        official = await adapter.event_frequency(_frequency(7, amount="amount"), OFFICIAL)
        cleared = await adapter.event_frequency(_frequency(7, amount="amount"), CLEARED)
        only_hidden = await adapter.event_frequency(_frequency(7, nodes=["acct-hidden"]), OFFICIAL)
    assert (official.nodes["acct-a"].most_in_span, official.nodes["acct-a"].largest_total) == (2, 200.0)
    assert official.nodes["acct-a"].first_at == _day(0)
    assert cleared.nodes["acct-a"].most_in_span == 4  # the two SECRET ones, for a reader who may see them
    assert cleared.nodes["acct-a"].first_at == datetime(2025, 1, 1, tzinfo=UTC)
    assert only_hidden.nodes == {}  # a node reached only through what is hidden is not there at all


async def test_frequency_counts_only_this_case_and_the_link_types_named(factory: AnalyticsAdapterFactory) -> None:
    events = [_paid(0), _paid(1, investigation_scope="case-2"),
              _event(occurred_at=_day(1), edge_type="TRANSACTED", source_id="acct-b", target_id="acct-a",
                     investigation_scope="case-2"),
              _event(occurred_at=_day(1), edge_type="COMMUNICATED_WITH", source_id="acct-a", target_id="acct-b")]  # fmt: skip
    async with factory.context(events) as adapter:
        transacted = await adapter.event_frequency(_frequency(7), OFFICIAL)
        either = await adapter.event_frequency(_frequency(7, edge_types=["TRANSACTED", "COMMUNICATED_WITH"]), OFFICIAL)
    assert transacted.nodes["acct-a"].most_in_span == 1
    assert either.nodes["acct-a"].most_in_span == 2


def test_a_frequency_names_its_subjects_and_at_most_a_thousand(factory: AnalyticsAdapterFactory) -> None:
    with pytest.raises(ValueError, match="name at least one"):
        FrequencyRequest(filter=_filter(), span_days=7)
    with pytest.raises(ValueError, match="at most 1,000"):
        FrequencyRequest(filter=_filter(node_ids=[f"n{i}" for i in range(1001)]), span_days=7)
    with pytest.raises(ValueError):
        FrequencyRequest(filter=_filter(node_ids=["a"]), span_days=367)


# --- account_activity (ADR-133 decision 2, stage (c)): a dormant account, a rise in velocity --------
#
# The AML templates "a dormant account reactivated" and "a sudden rise in velocity" compare an
# account with its own past: its movements in a recent window against the days before it, and its
# last movement before the window. Counted as the rule's author, the access step in the query
# (rule 3); each hidden plant differs from a visible event only in the respect under test.

from datetime import timedelta  # noqa: E402

from schemas.analytics import ActivityRequest  # noqa: E402

ACT_WINDOW = Interval(valid_from=datetime(2026, 4, 1, tzinfo=UTC), valid_to=datetime(2026, 4, 8, tzinfo=UTC))


def _at(day: int, hour: int = 9) -> datetime:
    return datetime(2026, 4, 1, hour, tzinfo=UTC) + timedelta(days=day)


def _moved(at: datetime, amount: float | None = None, source: str = "acct-a", target: str = "acct-b",
           **kwargs: object) -> EventRecord:  # fmt: skip
    properties = {} if amount is None else {"amount": amount}
    return _event(occurred_at=at, edge_type="TRANSACTED", source_id=source, target_id=target,
                  properties=properties, **kwargs)  # type: ignore[arg-type]  # fmt: skip


def _activity(baseline_days: int = 28, *, nodes: list[str] | None = None, amount: str | None = None,
              edge_types: list[str] | None = None) -> ActivityRequest:  # fmt: skip
    return ActivityRequest(
        filter=_filter(node_ids=nodes or ["acct-a"], window=ACT_WINDOW, edge_types=edge_types or ["TRANSACTED"]),
        baseline_days=baseline_days, amount_property=amount,
    )  # fmt: skip


async def test_activity_counts_the_window_and_the_days_before_it(factory: AnalyticsAdapterFactory) -> None:
    events = [_moved(_at(0), 100), _moved(_at(3), 200), _moved(_at(7, 0), 300),   # in the window, its end included
              _moved(_at(-1), 1_000), _moved(_at(-28), 2_000),                     # the 28 days before
              _moved(_at(-29), 4_000), _moved(_at(8), 8_000)]                      # outside both  # fmt: skip
    async with factory.context(events) as adapter:
        counted = await adapter.account_activity(_activity(28, amount="amount"), OFFICIAL)
        plain = await adapter.account_activity(_activity(28), OFFICIAL)
    a = counted.nodes["acct-a"]
    assert (a.recent_count, a.recent_total) == (3, 600.0)
    assert (a.baseline_count, a.baseline_total) == (2, 3_000.0)
    assert plain.nodes["acct-a"].recent_total is None and plain.nodes["acct-a"].baseline_count == 2


async def test_activity_sums_amounts_as_decimals_and_skips_one_that_is_not(
    factory: AnalyticsAdapterFactory,
) -> None:
    """As event_frequency's: the totals a rule compares are the same on every adapter (0.1 and 0.2
    make 0.3, not 0.30000000000000004), and an amount past a decimal of 38 digits, 9 after the point
    (1e30, inf), is no amount, its event still counted."""
    events = [_moved(_at(0), 0.1), _moved(_at(1), 0.2),  # in the window
              _moved(_at(-1), 1e30), _moved(_at(-2), "inf")]  # type: ignore[arg-type]  # fmt: skip
    async with factory.context(events) as adapter:
        counted = await adapter.account_activity(_activity(28, amount="amount"), OFFICIAL)
    a = counted.nodes["acct-a"]
    assert (a.recent_count, a.recent_total) == (2, 0.3)
    assert (a.baseline_count, a.baseline_total) == (2, None)


@pytest.mark.parametrize("sign", [1, -1])
async def test_a_total_past_the_decimals_range_is_refused_never_wrapped(
    factory: AnalyticsAdapterFactory, sign: int
) -> None:
    """ADR-133 Amendment 10 (rule 2): two amounts of 9 × 10^28 each fit a decimal of 38 digits, 9
    after the point; their total does not. A frequency's span and an activity's window holding both
    are refused (`AmountTotalOutOfRange`) on every adapter, never wrapped (DuckDB's plain SUM of a
    decimal wraps silently to a negative) and never cut. Either sign."""
    from ports.analytics import AmountTotalOutOfRange

    big = sign * 9e28
    async with factory.context([_paid(0, big), _paid(1, big)]) as adapter:
        with pytest.raises(AmountTotalOutOfRange):
            await adapter.event_frequency(_frequency(7, amount="amount"), OFFICIAL)
    async with factory.context([_moved(_at(0), big), _moved(_at(1), big)]) as adapter:
        with pytest.raises(AmountTotalOutOfRange):
            await adapter.account_activity(_activity(28, amount="amount"), OFFICIAL)
    async with factory.context([_moved(_at(-1), big), _moved(_at(-2), big)]) as adapter:
        with pytest.raises(AmountTotalOutOfRange):  # the days before the window too
            await adapter.account_activity(_activity(28, amount="amount"), OFFICIAL)


async def test_activity_says_the_first_movement_in_the_window_and_the_last_before_it(
    factory: AnalyticsAdapterFactory,
) -> None:
    long_ago = datetime(2025, 9, 1, tzinfo=UTC)
    events = [_moved(long_ago), _moved(_at(2)), _moved(_at(5)), _moved(_at(9))]
    async with factory.context(events) as adapter:
        result = await adapter.account_activity(_activity(28), OFFICIAL)
    a = result.nodes["acct-a"]
    assert a.first_in_window == _at(2)
    assert a.last_before_window == long_ago  # however long ago: a dormant account's last movement
    assert a.baseline_count == 0  # long before the 28 days


async def test_a_movement_at_the_windows_start_is_in_the_window_not_before_it(
    factory: AnalyticsAdapterFactory,
) -> None:
    start = ACT_WINDOW.valid_from
    assert start is not None
    events = [_moved(start), _moved(datetime(2026, 3, 30, tzinfo=UTC))]
    async with factory.context(events) as adapter:
        a = (await adapter.account_activity(_activity(28), OFFICIAL)).nodes["acct-a"]
    assert (a.recent_count, a.first_in_window) == (1, start)
    assert (a.baseline_count, a.last_before_window) == (1, datetime(2026, 3, 30, tzinfo=UTC))


async def test_activity_counts_an_account_at_either_end_and_each_event_once(
    factory: AnalyticsAdapterFactory,
) -> None:
    events = [_moved(_at(0)), _moved(_at(1), source="acct-b", target="acct-a"),
              _moved(_at(2), source="acct-a", target="acct-a")]  # fmt: skip
    async with factory.context(events) as adapter:
        result = await adapter.account_activity(_activity(28, nodes=["acct-a", "acct-b", "acct-none"]), OFFICIAL)
    assert result.nodes["acct-a"].recent_count == 3  # out, in, and to itself once
    assert result.nodes["acct-b"].recent_count == 2
    assert "acct-none" not in result.nodes  # nothing visible: absent, not zero


async def test_an_event_the_rules_author_may_not_see_is_not_activity(factory: AnalyticsAdapterFactory) -> None:
    hidden = [_moved(_at(1), 50_000, classification="SECRET"),
              _moved(_at(-3), 50_000, handling_code="R", owning_unit="unit-2", originator="unit-2"),
              _moved(_at(-90), classification="SECRET"),
              _moved(_at(1), source="acct-hidden", target="acct-z", classification="SECRET")]  # fmt: skip
    events = [_moved(_at(0), 100), _moved(datetime(2025, 6, 1, tzinfo=UTC), 100), *hidden]
    async with factory.context(events) as adapter:
        official = await adapter.account_activity(_activity(28, amount="amount", nodes=["acct-a", "acct-hidden"]), OFFICIAL)
        cleared = await adapter.account_activity(_activity(28, amount="amount"), CLEARED)
    a = official.nodes["acct-a"]
    assert (a.recent_count, a.recent_total, a.baseline_count) == (1, 100.0, 0)
    assert a.last_before_window == datetime(2025, 6, 1, tzinfo=UTC)  # the hidden one at day -90 is no later movement
    assert "acct-hidden" not in official.nodes
    assert cleared.nodes["acct-a"].recent_count == 2 and cleared.nodes["acct-a"].last_before_window == _at(-90)


async def test_activity_counts_only_this_case_and_the_link_types_named(factory: AnalyticsAdapterFactory) -> None:
    events = [_moved(_at(0)), _moved(_at(1), investigation_scope="case-2"),
              _event(occurred_at=_at(1), edge_type="COMMUNICATED_WITH", source_id="acct-a", target_id="acct-b")]  # fmt: skip
    async with factory.context(events) as adapter:
        result = await adapter.account_activity(_activity(28), OFFICIAL)
    assert result.nodes["acct-a"].recent_count == 1


def test_an_activity_read_names_its_accounts_and_a_whole_window(factory: AnalyticsAdapterFactory) -> None:
    with pytest.raises(ValueError, match="name at least one"):
        ActivityRequest(filter=_filter(window=ACT_WINDOW), baseline_days=28)
    with pytest.raises(ValueError, match="at most 1,000"):
        ActivityRequest(filter=_filter(node_ids=[f"n{i}" for i in range(1001)], window=ACT_WINDOW), baseline_days=28)
    with pytest.raises(ValueError, match="window with both ends"):
        ActivityRequest(filter=_filter(node_ids=["a"]), baseline_days=28)
    with pytest.raises(ValueError):
        ActivityRequest(filter=_filter(node_ids=["a"], window=ACT_WINDOW), baseline_days=367)
