"""The ClickHouse analytics adapter's own claims, beyond the `AnalyticsPort` suite it passes
unchanged (ADR-114 decision 9):

- a value never becomes SQL — every value is a typed parameter, so a quote, a backslash, a brace
  or a tab in an analyst's term is matched as itself (`client.bind`);
- a boundary with a hole covers what DuckDB's `ST_Covers` covers: the suite's cells have no holes,
  so this is checked against the DuckDB adapter over the same points rather than against numbers
  written by hand;
- a boundary that is neither Polygon nor MultiPolygon is refused at load, not stored unreadable.

Needs the live ClickHouse the conformance suite uses (`CLICKHOUSE_HTTP_PORT`).
"""

from __future__ import annotations

import struct
from datetime import UTC, datetime

import duckdb
import pytest
from ulid import ULID

from adapters.analytics_clickhouse.adapter import as_multipolygon
from adapters.analytics_clickhouse.client import bind
from adapters.analytics_clickhouse.testing import clickhouse_adapter
from adapters.analytics_duckdb.testing import duckdb_adapter
from ontology.handling import load_uk_le_scheme
from schemas.analytics import (
    EventFilter,
    EventRecord,
    GeocodeRequest,
    GeometryKind,
    GeometryRecord,
    HistogramBucketing,
    HistogramRequest,
)
from schemas.domain import Handling, Principal

SCHEME = load_uk_le_scheme()
READER = Principal(id="analyst", clearance="SECRET", org_unit="unit-1")
HANDLING = Handling(
    classification="OFFICIAL", handling_code="P", owning_unit="unit-1", originator="unit-1"
)
CASE = "case-1"


def _event(*, lat: float | None = None, lon: float | None = None, **props: object) -> EventRecord:
    return EventRecord(
        event_id=str(ULID()),
        edge_id="e1",
        edge_type="COMMUNICATED_WITH",
        source_id="a",
        target_id="b",
        occurred_at=datetime(2026, 1, 1, 12, tzinfo=UTC),
        lat=lat,
        lon=lon,
        properties=dict(props),
        investigation_scope=CASE,
        handling=HANDLING,
    )


def _wkb(wkt: str) -> bytes:
    con = duckdb.connect(":memory:")
    try:
        con.install_extension("spatial")
        con.load_extension("spatial")
        return bytes(con.execute("SELECT ST_AsWKB(ST_GeomFromText(?))", [wkt]).fetchone()[0])
    finally:
        con.close()


def test_bind_makes_each_placeholder_a_typed_parameter_and_keeps_values_out_of_the_text() -> None:
    sql, values = bind(
        "SELECT ? , ?, ?, ?", ["x' OR 1=1 --", 3, datetime(2026, 1, 1, tzinfo=UTC), ["a", "b'c"]]
    )
    assert sql == (
        "SELECT {p0:String} , {p1:Int64}, {p2:DateTime64(6, 'UTC')}, {p3:Array(String)}"
    )
    assert "OR 1=1" not in sql
    assert values["param_p0"] == "x' OR 1=1 --"
    assert values["param_p2"] == "2026-01-01 00:00:00.000000"


def test_bind_refuses_a_placeholder_count_that_does_not_match() -> None:
    with pytest.raises(ValueError):
        bind("SELECT ?, ?", ["one"])


@pytest.mark.parametrize(
    "term",
    ["it's", "back\\slash", "{p0:String}", "tab\there", "line\nbreak", "x' OR '1'='1"],
)
async def test_a_value_is_matched_as_itself_whatever_it_holds(term: str) -> None:
    """Over the wire: the event carrying the awkward value is counted, the other is not."""
    events = [_event(category=term), _event(category="ordinary")]
    async with clickhouse_adapter(events, SCHEME) as adapter:
        histogram = await adapter.histogram(
            HistogramRequest(
                filter=EventFilter(investigation_scope=CASE, value_filters={"category": [term]}),
                bucketing=HistogramBucketing.CATEGORICAL,
                field="category",
            ),
            READER,
        )
    assert [(b.label, b.count) for b in histogram.buckets] == [(term, 1)]


#: A 0.2-degree square with a 0.1-degree square hole in its middle.
_HOLED = (
    "POLYGON((-0.2 51.4, -0.2 51.6, 0.0 51.6, 0.0 51.4, -0.2 51.4), "
    "(-0.15 51.45, -0.05 51.45, -0.05 51.55, -0.15 51.55, -0.15 51.45))"
)
_POINTS = {
    "solid": (51.42, -0.18),
    "in the hole": (51.5, -0.1),
    "on the hole's edge": (51.5, -0.15),
    "on the outer edge": (51.5, -0.2),
    "a corner of the hole": (51.45, -0.05),
    "outside": (51.7, -0.1),
}


async def _geocoded(context: object, events: list[EventRecord]) -> set[str]:
    async with context as adapter:  # type: ignore[attr-defined]
        await adapter.load_geometries(
            [
                GeometryRecord(
                    geometry_ref="holed",
                    version=1,
                    kind=GeometryKind.POLYGON,
                    geometry_wkb=_wkb(_HOLED),
                    handling=HANDLING,
                )
            ]
        )
        result = await adapter.geocode_events(
            GeocodeRequest(
                filter=EventFilter(investigation_scope=CASE), cells={"holed": "node-holed"}
            ),
            READER,
        )
    return {g.event_id for g in result}


async def test_a_polygon_with_a_hole_covers_what_duckdb_covers() -> None:
    events = [_event(lat=lat, lon=lon) for lat, lon in _POINTS.values()]
    named = {e.event_id: name for e, name in zip(events, _POINTS, strict=True)}
    duck = {named[i] for i in await _geocoded(duckdb_adapter(events, SCHEME), events)}
    click = {named[i] for i in await _geocoded(clickhouse_adapter(events, SCHEME), events)}
    assert click == duck
    # And what that is, so the agreement is not two adapters agreeing on nothing.
    assert duck == {"solid", "on the hole's edge", "on the outer edge", "a corner of the hole"}


def test_a_polygon_becomes_a_multipolygon_of_one_in_either_byte_order() -> None:
    little = _wkb("POLYGON((0 0, 1 0, 1 1, 0 0))")
    assert as_multipolygon(little)[:9] == bytes([1]) + struct.pack("<II", 6, 1)
    assert as_multipolygon(little)[9:] == little
    big = bytes([0]) + struct.pack(">I", 3) + b"\x00" * 4
    assert as_multipolygon(big)[:9] == bytes([0]) + struct.pack(">II", 6, 1)
    multi = _wkb("MULTIPOLYGON(((0 0, 1 0, 1 1, 0 0)))")
    assert as_multipolygon(multi) == multi


@pytest.mark.parametrize("wkt", ["POINT(0 0)", "LINESTRING(0 0, 1 1)"])
def test_a_boundary_that_is_not_a_polygon_is_refused(wkt: str) -> None:
    with pytest.raises(ValueError, match="Polygon or MultiPolygon"):
        as_multipolygon(_wkb(wkt))


async def test_the_conduit_opens_clickhouse_when_the_deployment_names_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    """`open_analytics("clickhouse")` makes the deployment's database and tables if missing, and
    what it loads it reads back; opening a second time keeps what the first loaded."""
    from services.api.analytics_store import open_analytics

    from adapters.analytics_clickhouse.adapter import AnalyticsClickHouseAdapter

    database = f"conduit_{str(ULID()).lower()}"
    monkeypatch.setenv("CLICKHOUSE_DATABASE", database)
    request = HistogramRequest(
        filter=EventFilter(investigation_scope=CASE),
        bucketing=HistogramBucketing.CATEGORICAL,
        field="edge_type",
    )
    analytics, close = await open_analytics("clickhouse", duckdb_path="", handling_scheme=SCHEME)
    try:
        assert isinstance(analytics, AnalyticsClickHouseAdapter)
        await analytics.load_events([_event()])
        assert (await analytics.histogram(request, READER)).total == 1
    finally:
        await close()
    again, close_again = await open_analytics("clickhouse", duckdb_path="", handling_scheme=SCHEME)
    try:
        assert (await again.histogram(request, READER)).total == 1
    finally:
        client = again._ch  # type: ignore[attr-defined]  # noqa: SLF001
        await client.command(f"DROP DATABASE IF EXISTS {database}", database=None)
        await close_again()
