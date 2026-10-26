"""`AnalyticsClickHouseAdapter` — full `AnalyticsPort` over ClickHouse (the Enterprise profile,
ADR-114 decision 9: the analytics store a cluster of Conduits shares, where DuckDB is in-process).

The DuckDB adapter's queries, method for method, in ClickHouse's SQL: every method compiles an
`EventFilter` plus the same access predicate (`analytics_duckdb/access_filter.py`, unchanged — it
is plain SQL both engines read) into one `WHERE` clause before it aggregates, never filtering a
result afterwards (`00_ARCHITECTURE.md` §2.2). Values travel as typed parameters (`client.py`).

Where ClickHouse differs, and what is done about it:

- A JSON property absent or `null` reads as `NULL`, a string as itself, anything else as its JSON
  text — what DuckDB's `json_extract_string` gives (`_field_expression`).
- `ST_Covers` is `pointInPolygon` plus an explicit test for a point on a ring (`_COVERED`).
- An update is a mutation, run synchronously (`mutations_sync = 2`), so a read straight after a
  `geocode_events` sees what it wrote, as it does on DuckDB.
- `MAX` over no rows is `0` in ClickHouse, not `NULL`; `maxOrNull` keeps "no partition yet".
"""

from __future__ import annotations

import json
import math
import struct
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any, cast

from adapters.analytics_duckdb.access_filter import AccessFilter, SqlPredicate
from ontology.handling import HandlingScheme
from ports.analytics import TrendLimitExceeded
from schemas.analytics import (
    BaselineRequest,
    BaselineResult,
    CountedHandling,
    CrossFilterRequest,
    EventFilter,
    EventListRequest,
    EventListResult,
    EventRecord,
    FirstSeenRequest,
    FirstSeenResult,
    GeoBin,
    GeoBinRequest,
    GeocodedEvent,
    GeocodeRequest,
    GeometryKind,
    GeometryRecord,
    Histogram,
    HistogramBucket,
    HistogramBucketing,
    HistogramRequest,
    Sighting,
    SightingRequest,
    TrendInterval,
    TrendMeasure,
    TrendPoint,
    TrendRequest,
    TrendResult,
)
from schemas.domain import Handling, Interval, Principal

from .client import ClickHouseClient, utc_text

#: The same columns a `CATEGORICAL` dimension may bucket by directly as the DuckDB adapter's.
_TOP_LEVEL_FIELDS = frozenset({"edge_type", "source_id", "target_id", "cell_site", "direction"})

_EVENT_COLUMNS = (
    "event_id, edge_id, edge_type, source_id, target_id, occurred_at, duration_s, cell_site, "
    "lat, lon, direction, properties, investigation_scope, handling_classification, "
    "handling_code, owning_unit, originator, load_id"
)

_SYNC = " SETTINGS mutations_sync = 2"


def _safe_field_name(field: str) -> str:
    if not field.replace("_", "").isalnum() or not field:
        raise ValueError(f"not a safe field name for a SQL literal: {field!r}")
    return field


def _property(name: str) -> str:
    """A JSON property as DuckDB's `json_extract_string` reads it."""
    return (
        f"multiIf(JSONType(properties, '{name}') = 'String', "
        f"JSONExtractString(properties, '{name}'), "
        f"JSONType(properties, '{name}') = 'Null', NULL, "
        f"JSONExtractRaw(properties, '{name}'))"
    )


def _field_expression(field: str) -> str:
    name = _safe_field_name(field)
    if name in _TOP_LEVEL_FIELDS:
        return name
    return _property(name)


def _time(value: object) -> datetime:
    """ClickHouse's JSON gives a `DateTime64` as `YYYY-MM-DD hh:mm:ss.ffffff`, in the column's
    zone (UTC), and a `Date` as `YYYY-MM-DD`."""
    text = cast(str, value)
    if len(text) == 10:
        return datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=UTC)
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def _row_to_event(row: Sequence[Any]) -> EventRecord:
    (
        event_id, edge_id, edge_type, source_id, target_id, occurred_at, duration_s, cell_site,
        lat, lon, direction, properties, investigation_scope, classification, handling_code,
        owning_unit, originator, load_id,
    ) = row
    return EventRecord(
        event_id=event_id,
        edge_id=edge_id,
        edge_type=edge_type,
        source_id=source_id,
        target_id=target_id,
        occurred_at=_time(occurred_at),
        duration_s=duration_s,
        cell_site=cell_site,
        lat=lat,
        lon=lon,
        direction=direction,
        properties=json.loads(properties) if properties else {},
        investigation_scope=investigation_scope,
        handling=Handling(
            classification=classification,
            handling_code=handling_code,
            owning_unit=owning_unit,
            originator=originator,
        ),
        load_id=load_id,
    )


def as_multipolygon(wkb: bytes) -> bytes:
    """A Polygon's WKB as a MultiPolygon of one; a MultiPolygon's unchanged. Anything else is not
    a boundary a cell can be, and is refused rather than stored unreadable."""
    if len(wkb) < 5 or wkb[0] not in (0, 1):
        raise ValueError("not WKB: no byte order mark")
    order = "<" if wkb[0] == 1 else ">"
    (kind,) = struct.unpack(f"{order}I", wkb[1:5])
    if kind == 6:
        return wkb
    if kind == 3:
        return bytes([wkb[0]]) + struct.pack(f"{order}II", 6, 1) + wkb
    raise ValueError(f"a boundary must be a Polygon or MultiPolygon, not WKB type {kind}")


_X, _Y = "assumeNotNull(ev.lon)", "assumeNotNull(ev.lat)"


def _on_ring(ring: str) -> str:
    """The point on one of the ring's segments: collinear with it (cross product nought, within
    rounding) and between its ends."""
    a, b = f"{ring}[i]", f"{ring}[i + 1]"
    cross = f"(({b}.1 - {a}.1) * ({_Y} - {a}.2) - ({b}.2 - {a}.2) * ({_X} - {a}.1))"
    length2 = f"(pow({b}.1 - {a}.1, 2) + pow({b}.2 - {a}.2, 2))"
    dot = f"(({_X} - {a}.1) * ({b}.1 - {a}.1) + ({_Y} - {a}.2) * ({b}.2 - {a}.2))"
    return (
        f"arrayExists(i -> abs({cross}) <= 1e-12 * greatest(1, {length2}) "
        f"AND {dot} >= 0 AND {dot} <= {length2}, range(1, length({ring})))"
    )


#: `ST_Covers`: each event's point inside or on some polygon's outer ring, and strictly inside
#: none of its holes. `pointInPolygon` alone is not enough — whether it counts a point on the ring
#: depends on the edge (measured, ClickHouse 25.8: a point on a cell's east edge at lon -0.1 was
#: outside it), so the ring is tested for the point explicitly.
_COVERED = (
    f"arrayExists(p -> (pointInPolygon(({_X}, {_Y}), p[1]) OR {_on_ring('p[1]')}) AND NOT "
    f"arrayExists(h -> pointInPolygon(({_X}, {_Y}), h) AND NOT {_on_ring('h')}, "
    "arrayPopFront(p)), cell.shape)"
)


class AnalyticsClickHouseAdapter:
    def __init__(self, client: ClickHouseClient, handling_scheme: HandlingScheme) -> None:
        self._ch = client
        self._access = AccessFilter(handling_scheme)

    # --- shared predicate compilation ------------------------------------

    def _event_filter_predicate(self, event_filter: EventFilter) -> SqlPredicate:
        clauses = ["investigation_scope = ?"]
        params: list[object] = [event_filter.investigation_scope]
        inherited = event_filter.inherited
        if inherited is not None and inherited.scopes and inherited.edge_ids:
            # ADR-084 Amendment 2: a branch's parents' events, on the links the branch holds only.
            scopes = ",".join("?" for _ in inherited.scopes)
            edges = ",".join("?" for _ in inherited.edge_ids)
            # ADR-128 decision 2: a branch made from what is lit reads its parents' events inside
            # its window only, ends included; its own events are not held to it.
            held = ""
            held_params: list[object] = []
            if inherited.window is not None:
                held = " AND occurred_at >= ?"
                held_params.append(inherited.window.valid_from)
                if inherited.window.valid_to is not None:
                    held += " AND occurred_at <= ?"
                    held_params.append(inherited.window.valid_to)
            clauses = [
                f"(investigation_scope = ? OR (investigation_scope IN ({scopes}) "
                f"AND edge_id IN ({edges}){held}))"
            ]
            params.extend(inherited.scopes)
            params.extend(inherited.edge_ids)
            params.extend(held_params)
        if event_filter.window is not None:
            clauses.append("occurred_at >= ?")
            params.append(event_filter.window.valid_from)
            if event_filter.window.valid_to is not None:
                clauses.append("occurred_at <= ?")
                params.append(event_filter.window.valid_to)
        if event_filter.node_ids:
            placeholders = ",".join("?" for _ in event_filter.node_ids)
            clauses.append(f"(source_id IN ({placeholders}) OR target_id IN ({placeholders}))")
            params.extend(event_filter.node_ids)
            params.extend(event_filter.node_ids)
        for column, values in (
            ("edge_type", event_filter.edge_types),
            ("edge_id", event_filter.edge_ids),
            ("event_id", event_filter.event_ids),
        ):
            if values:
                clauses.append(f"{column} IN ({','.join('?' for _ in values)})")
                params.extend(values)
        # An empty value list does not restrict (the DuckDB adapter's reasoning, unchanged).
        for field, values in sorted(event_filter.value_filters.items()):
            if not values:
                continue
            placeholders = ",".join("?" for _ in values)
            clauses.append(f"{_field_expression(field)} IN ({placeholders})")
            params.extend(values)
        return SqlPredicate(" AND ".join(clauses), params)

    def _predicate(self, event_filter: EventFilter, principal: Principal) -> SqlPredicate:
        filter_pred = self._event_filter_predicate(event_filter)
        access_pred = self._access.predicate(principal)
        return SqlPredicate(
            f"({filter_pred.where}) AND ({access_pred.where})",
            [*filter_pred.params, *access_pred.params],
        )

    async def _count(self, predicate: SqlPredicate) -> int:
        rows = await self._ch.rows(
            f"SELECT count() FROM events WHERE {predicate.where}", predicate.params
        )
        return int(rows[0][0]) if rows else 0

    # --- histogram ---------------------------------------------------------

    async def histogram(self, req: HistogramRequest, principal: Principal) -> Histogram:
        predicate = self._predicate(req.filter, principal)
        if req.bucketing is HistogramBucketing.FIXED_INTERVAL:
            return await self._fixed_interval_histogram(predicate, req.interval_seconds)
        if req.bucketing is HistogramBucketing.WEEKDAY_HOUR:
            return await self._weekday_hour_histogram(predicate)
        assert req.field is not None  # enforced by HistogramRequest's own validator
        return await self._categorical_histogram(predicate, req.field)

    # --- trend (ADR-113) ----------------------------------------------------------------------

    async def trend(self, req: TrendRequest, principal: Principal) -> TrendResult:
        predicate = self._predicate(req.filter, principal)
        # ISO weeks start on Monday, as DuckDB's `date_trunc('week', …)` does.
        period = (
            "toMonday(occurred_at)"
            if req.interval is TrendInterval.WEEK
            else "toStartOfMonth(occurred_at)"
        )
        series = "NULL" if req.group_by is None else _field_expression(req.group_by)
        # The bounds on what the reader can see, before anything is aggregated (as DuckDB's).
        bounds = await self._ch.rows(
            f"SELECT uniqExact({period}), count(DISTINCT {series}) FROM events "
            f"WHERE {predicate.where}",
            predicate.params,
        )
        periods, groups = (int(bounds[0][0]), int(bounds[0][1])) if bounds else (0, 0)
        if periods > req.max_periods:
            raise TrendLimitExceeded("periods", req.max_periods, periods)
        if groups > req.max_series:
            raise TrendLimitExceeded("series", req.max_series, groups)
        if req.measure is TrendMeasure.SUM:
            assert req.measure_field is not None  # enforced by TrendRequest's own validator
            number = f"toFloat64OrNull({_field_expression(req.measure_field)})"
            value, unvalued = f"coalesce(sum({number}), 0)", f"count() - count({number})"
        else:
            value, unvalued = "count()", "0"
        rows = await self._ch.rows(
            f"SELECT {period} AS period, {series} AS series, {value} AS value, count() AS n, "
            f"{unvalued} AS unvalued FROM events WHERE {predicate.where} "
            "GROUP BY period, series ORDER BY period, series ASC NULLS FIRST",
            predicate.params,
        )
        classifications = [
            str(c)
            for (c,) in await self._ch.rows(
                f"SELECT DISTINCT handling_classification FROM events WHERE {predicate.where} "
                "ORDER BY 1",
                predicate.params,
            )
        ]
        handlings = [
            CountedHandling(
                classification=str(c), handling_code=str(h), owning_unit=str(u), originator=str(o)
            )
            for c, h, u, o in await self._ch.rows(
                "SELECT DISTINCT handling_classification, handling_code, owning_unit, originator "
                f"FROM events WHERE {predicate.where} ORDER BY 1, 2, 3, 4",
                predicate.params,
            )
        ]
        points = [
            TrendPoint(
                period_start=_time(p), series=None if g is None else str(g), value=float(v)
            )
            for p, g, v, _, _ in rows
        ]
        return TrendResult(
            interval=req.interval,
            measure=req.measure,
            points=points,
            series=sorted({pt.series for pt in points if pt.series is not None}),
            total=float(sum(pt.value for pt in points)),
            events=int(sum(r[3] for r in rows)),
            unvalued=int(sum(r[4] for r in rows)),
            classifications=classifications,
            handlings=handlings,
        )

    async def _fixed_interval_histogram(
        self, predicate: SqlPredicate, interval_seconds: int | None
    ) -> Histogram:
        assert interval_seconds is not None
        rows = await self._ch.rows(
            "SELECT toInt64(floor(toUnixTimestamp64Micro(occurred_at) / 1000000 / ?)) AS bucket, "
            f"count() AS cnt FROM events WHERE {predicate.where} GROUP BY bucket ORDER BY bucket",
            [interval_seconds, *predicate.params],
        )
        buckets = [
            HistogramBucket(
                start=datetime.fromtimestamp(bucket * interval_seconds, tz=UTC),
                end=datetime.fromtimestamp((bucket + 1) * interval_seconds, tz=UTC),
                count=count,
            )
            for bucket, count in rows
        ]
        return Histogram(
            bucketing=HistogramBucketing.FIXED_INTERVAL,
            buckets=buckets,
            total=sum(b.count for b in buckets),
        )

    async def _weekday_hour_histogram(self, predicate: SqlPredicate) -> Histogram:
        rows = await self._ch.rows(
            "SELECT toInt32(toDayOfWeek(occurred_at)) - 1 AS weekday, "
            "toInt32(toHour(occurred_at)) AS hour, count() AS cnt "
            f"FROM events WHERE {predicate.where} GROUP BY weekday, hour "
            "ORDER BY weekday, hour",
            predicate.params,
        )
        buckets = [
            HistogramBucket(weekday=weekday, hour=hour, count=count)
            for weekday, hour, count in rows
        ]
        return Histogram(
            bucketing=HistogramBucketing.WEEKDAY_HOUR,
            buckets=buckets,
            total=sum(b.count for b in buckets),
        )

    async def _categorical_histogram(self, predicate: SqlPredicate, field: str) -> Histogram:
        expr = _field_expression(field)
        rows = await self._ch.rows(
            f"SELECT {expr} AS label, count() AS cnt FROM events "
            f"WHERE {predicate.where} GROUP BY label ORDER BY label",
            predicate.params,
        )
        buckets = [HistogramBucket(label=label, count=count) for label, count in rows]
        return Histogram(
            bucketing=HistogramBucketing.CATEGORICAL,
            buckets=buckets,
            total=sum(b.count for b in buckets),
        )

    # --- geo_bins ------------------------------------------------------------

    async def geo_bins(self, req: GeoBinRequest, principal: Principal) -> list[GeoBin]:
        """The DuckDB adapter's sinusoidal (equal-area) binning; its docstring has why."""
        predicate = self._predicate(req.filter, principal)
        step = 180.0 / (2**req.precision)
        rows = await self._ch.rows(
            "SELECT toInt64(floor(lat / ?)) AS lat_bin, "
            "toInt64(floor(lon / (? / cos(radians(lat))))) AS lon_bin, count() AS cnt "
            f"FROM events WHERE ({predicate.where}) AND lat IS NOT NULL AND lon IS NOT NULL "
            "GROUP BY lat_bin, lon_bin ORDER BY lat_bin, lon_bin",
            [step, step, *predicate.params],
        )
        result = []
        for lat_bin, lon_bin, count in rows:
            center_lat = max(min((lat_bin + 0.5) * step, 90.0), -90.0)
            lon_step = step / max(math.cos(math.radians(center_lat)), 1e-6)
            result.append(
                GeoBin(
                    cell_id=f"{req.precision}:{lat_bin}:{lon_bin}",
                    centroid_lat=center_lat,
                    centroid_lon=max(min((lon_bin + 0.5) * lon_step, 180.0), -180.0),
                    count=count,
                )
            )
        return result

    # --- sightings -----------------------------------------------------------

    #: The DuckDB adapter's defensive cap, for the same reason (its comment has it).
    _MAX_SIGHTINGS = 5000

    async def list_sightings(self, req: SightingRequest, principal: Principal) -> list[Sighting]:
        predicate = self._predicate(req.filter, principal)
        rows = await self._ch.rows(
            "SELECT occurred_at, lat, lon FROM events "
            f"WHERE ({predicate.where}) AND lat IS NOT NULL AND lon IS NOT NULL "
            "ORDER BY occurred_at ASC LIMIT ?",
            [*predicate.params, self._MAX_SIGHTINGS],
        )
        return [Sighting(occurred_at=_time(t), lat=lat, lon=lon) for t, lat, lon in rows]

    # --- containment ---------------------------------------------------------

    async def geocode_events(
        self, req: GeocodeRequest, principal: Principal
    ) -> list[GeocodedEvent]:
        if req.filter.inherited is not None:
            raise ValueError("geocode_events writes a case's own events; it takes no inherited")
        prop = _safe_field_name(req.property)
        resolved_version = (
            req.version if req.version is not None else await self._current_partition_version()
        )
        if resolved_version is None:
            return []
        event_pred = self._predicate(req.filter, principal)
        geometry_access = self._access.predicate(principal)
        refs = sorted(req.cells)
        ref_placeholders = ",".join("?" for _ in refs)
        # Covering, and `min` over the covering refs, as the DuckDB adapter (its comment has why).
        rows = await self._ch.rows(
            "WITH ev AS ("
            "  SELECT event_id, edge_id, edge_type, source_id, target_id, occurred_at, lat, lon, "
            "         handling_classification, handling_code, owning_unit, originator, properties, "
            f"         {_property(prop)} AS previous "
            f"  FROM events WHERE ({event_pred.where}) AND lat IS NOT NULL AND lon IS NOT NULL"
            "), cell AS ("
            "  SELECT geometry_ref, "
            "         readWKBMultiPolygon(unhex(assumeNotNull(multi_wkb_hex))) AS shape "
            "  FROM geometries "
            f"  WHERE kind = ? AND version = ? AND geometry_ref IN ({ref_placeholders}) "
            f"  AND ({geometry_access.where}) AND multi_wkb_hex IS NOT NULL"
            "), hit AS ("
            "  SELECT ev.event_id AS event_id, min(cell.geometry_ref) AS geometry_ref "
            f"  FROM ev CROSS JOIN cell WHERE {_COVERED} GROUP BY ev.event_id"
            ") "
            "SELECT ev.event_id, ev.edge_id, ev.edge_type, ev.source_id, ev.target_id, "
            "       ev.occurred_at, hit.geometry_ref, ev.previous, ev.handling_classification, "
            "       ev.handling_code, ev.owning_unit, ev.originator, ev.properties "
            "FROM ev LEFT JOIN hit ON ev.event_id = hit.event_id ORDER BY ev.event_id "
            "SETTINGS join_use_nulls = 1",
            [
                *event_pred.params,
                GeometryKind.POLYGON.value,
                resolved_version,
                *refs,
                *geometry_access.params,
            ],
        )

        values = set(req.cells.values())
        geocoded: list[GeocodedEvent] = []
        rewritten: dict[str, str] = {}
        for row in rows:
            event_id, edge_id, edge_type, source_id, target_id, occurred_at, ref, previous = row[:8]
            properties = json.loads(row[12]) if row[12] else {}
            if ref is None:
                # Not covered: only a value this call owns is cleared (the DuckDB adapter's rule).
                if previous in values:
                    properties.pop(prop, None)
                    rewritten[event_id] = json.dumps(properties)
                continue
            value = req.cells[ref]
            if previous != value:
                properties[prop] = value
                rewritten[event_id] = json.dumps(properties)
            geocoded.append(
                GeocodedEvent(
                    event_id=event_id,
                    edge_id=edge_id,
                    edge_type=edge_type,
                    source_id=source_id,
                    target_id=target_id,
                    occurred_at=_time(occurred_at),
                    geometry_ref=ref,
                    value=value,
                    previous_value=previous,
                    handling=Handling(
                        classification=row[8],
                        handling_code=row[9],
                        owning_unit=row[10],
                        originator=row[11],
                    ),
                )
            )
        if rewritten:
            ids = sorted(rewritten)
            # One mutation for the lot: each event's whole new properties, chosen by its id.
            await self._ch.command(
                "ALTER TABLE events UPDATE properties = transform(event_id, ?, ?, properties) "
                "WHERE investigation_scope = ? AND has(?, event_id)" + _SYNC,
                [ids, [rewritten[i] for i in ids], req.filter.investigation_scope, ids],
            )
        return geocoded

    # --- baseline ------------------------------------------------------------

    @staticmethod
    def _bucket_seconds(bucketing: HistogramBucketing, interval_seconds: int | None) -> float:
        if bucketing is HistogramBucketing.FIXED_INTERVAL:
            assert interval_seconds is not None
            return float(interval_seconds)
        if bucketing is HistogramBucketing.WEEKDAY_HOUR:
            return 3600.0
        raise ValueError("categorical bucketing has no fixed bucket size")

    @classmethod
    def _bucket_count(
        cls, window: Interval, bucketing: HistogramBucketing, interval_seconds: int | None
    ) -> int:
        if bucketing is HistogramBucketing.CATEGORICAL:
            return 1
        end = window.valid_to or window.valid_from
        duration = max((end - window.valid_from).total_seconds(), 0.0)
        seconds = cls._bucket_seconds(bucketing, interval_seconds)
        return max(math.ceil(duration / seconds), 1)

    async def baseline(self, req: BaselineRequest, principal: Principal) -> BaselineResult:
        baseline_filter = req.filter.model_copy(update={"window": req.baseline_window})
        comparison_filter = req.filter.model_copy(update={"window": req.comparison_window})
        baseline_count = await self._count(self._predicate(baseline_filter, principal))
        comparison_count = await self._count(self._predicate(comparison_filter, principal))
        baseline_buckets = self._bucket_count(
            req.baseline_window, req.bucketing, req.interval_seconds
        )
        comparison_buckets = self._bucket_count(
            req.comparison_window, req.bucketing, req.interval_seconds
        )
        return BaselineResult(
            baseline_count=baseline_count,
            comparison_count=comparison_count,
            baseline_rate_per_bucket=baseline_count / baseline_buckets,
            comparison_rate_per_bucket=comparison_count / comparison_buckets,
            ratio=None if baseline_count == 0 else comparison_count / baseline_count,
        )

    # --- cross_filter --------------------------------------------------------

    async def cross_filter(
        self, req: CrossFilterRequest, principal: Principal
    ) -> dict[str, Histogram]:
        predicate = self._predicate(req.filter, principal)
        result: dict[str, Histogram] = {}
        for dimension in req.dimensions:
            if dimension.bucketing is HistogramBucketing.FIXED_INTERVAL:
                result[dimension.name] = await self._fixed_interval_histogram(
                    predicate, dimension.interval_seconds
                )
            elif dimension.bucketing is HistogramBucketing.WEEKDAY_HOUR:
                result[dimension.name] = await self._weekday_hour_histogram(predicate)
            else:
                assert dimension.field is not None
                result[dimension.name] = await self._categorical_histogram(
                    predicate, dimension.field
                )
        return result

    # --- list_events (ADR-089) -------------------------------------------------

    async def list_events(self, req: EventListRequest, principal: Principal) -> EventListResult:
        predicate = self._predicate(req.filter, principal)
        total = await self._count(predicate)
        rows = await self._ch.rows(
            f"SELECT {_EVENT_COLUMNS} FROM events WHERE {predicate.where} "
            "ORDER BY occurred_at DESC, event_id DESC LIMIT ? OFFSET ?",
            [*predicate.params, req.limit, req.offset],
        )
        return EventListResult(total=total, events=[_row_to_event(row) for row in rows])

    # --- first_seen (ADR-087) --------------------------------------------------

    async def first_seen(self, req: FirstSeenRequest, principal: Principal) -> FirstSeenResult:
        predicate = self._predicate(req.filter, principal)
        node_rows = await self._ch.rows(
            "SELECT id, min(occurred_at) AS first FROM ("
            f"  SELECT source_id AS id, occurred_at FROM events WHERE {predicate.where}"
            "  UNION ALL "
            f"  SELECT target_id AS id, occurred_at FROM events WHERE {predicate.where}"
            ") GROUP BY id",
            [*predicate.params, *predicate.params],
        )
        edge_rows = await self._ch.rows(
            "SELECT edge_id, min(occurred_at) FROM events "
            f"WHERE {predicate.where} GROUP BY edge_id",
            predicate.params,
        )
        return FirstSeenResult(
            nodes={node_id: _time(first) for node_id, first in node_rows},
            edges={edge_id: _time(first) for edge_id, first in edge_rows},
        )

    # --- writes -------------------------------------------------------------

    async def load_events(self, records: Sequence[EventRecord]) -> None:
        await self._ch.insert(
            "events",
            [
                {
                    "event_id": r.event_id,
                    "edge_id": r.edge_id,
                    "edge_type": r.edge_type,
                    "source_id": r.source_id,
                    "target_id": r.target_id,
                    "occurred_at": utc_text(r.occurred_at),
                    "duration_s": r.duration_s,
                    "cell_site": r.cell_site,
                    "lat": r.lat,
                    "lon": r.lon,
                    "direction": r.direction,
                    "properties": json.dumps(r.properties),
                    "investigation_scope": r.investigation_scope,
                    "handling_classification": r.handling.classification,
                    "handling_code": r.handling.handling_code,
                    "owning_unit": r.handling.owning_unit,
                    "originator": r.handling.originator,
                    "load_id": r.load_id,
                }
                for r in records
            ],
        )

    async def retract_load(self, load_id: str) -> int:
        """`AnalyticsPort.retract_load`: the rows this load wrote, by its id alone. A row with no
        `load_id` is `NULL`, which `= ?` never matches, so unattributed events stay. The mutation
        is waited for (`_SYNC`), so a read straight after sees none of them."""
        (row,) = await self._ch.rows("SELECT count() FROM events WHERE load_id = ?", [load_id])
        removed = int(row[0])
        if removed:
            await self._ch.command("ALTER TABLE events DELETE WHERE load_id = ?" + _SYNC, [load_id])
        return removed

    async def events_of_load_among(self, load_id: str, event_ids: Sequence[str]) -> set[str]:
        """`AnalyticsPort.events_of_load_among`: by `event_id` and `load_id`, no access step.
        Unproven on a real ClickHouse: the coordinator's live run is its first."""
        ids = list(dict.fromkeys(event_ids))
        if not ids:
            return set()
        rows = await self._ch.rows(
            "SELECT DISTINCT event_id FROM events WHERE load_id = ? AND has(?, event_id)",
            [load_id, ids],
        )
        return {str(row[0]) for row in rows}

    # --- the geometry reference partition -----------------------------------

    async def load_geometries(self, records: Sequence[GeometryRecord]) -> None:
        await self._ch.insert(
            "geometries",
            [
                {
                    "geometry_ref": r.geometry_ref,
                    "version": r.version,
                    "kind": r.kind.value,
                    "lon": r.lon,
                    "lat": r.lat,
                    "source_crs": r.source_crs,
                    "source_x": r.source_x,
                    "source_y": r.source_y,
                    "wkb_hex": r.geometry_wkb.hex() if r.geometry_wkb is not None else None,
                    "multi_wkb_hex": (
                        as_multipolygon(r.geometry_wkb).hex()
                        if r.geometry_wkb is not None and r.kind is GeometryKind.POLYGON
                        else None
                    ),
                    "handling_classification": r.handling.classification,
                    "handling_code": r.handling.handling_code,
                    "owning_unit": r.handling.owning_unit,
                    "originator": r.handling.originator,
                }
                for r in records
            ],
        )

    async def retract_geometries(self, geometry_refs: Sequence[str], *, version: int) -> int:
        """`AnalyticsPort.retract_geometries`: these refs at this version, whatever their marking.
        Counted first (a mutation reports no count), then deleted; the delete is waited for
        (`_SYNC`), so a read straight after sees none of them. Unproven here: no ClickHouse was
        available to run it, so the coordinator's live run is its first."""
        refs = list(dict.fromkeys(geometry_refs))
        if not refs:
            return 0
        (row,) = await self._ch.rows(
            "SELECT count() FROM geometries WHERE version = ? AND has(?, geometry_ref)",
            [version, refs],
        )
        removed = int(row[0])
        if removed:
            await self._ch.command(
                "ALTER TABLE geometries DELETE WHERE version = ? AND has(?, geometry_ref)" + _SYNC,
                [version, refs],
            )
        return removed

    async def _current_partition_version(self) -> int | None:
        rows = await self._ch.rows("SELECT maxOrNull(version) FROM geometries")
        return None if not rows or rows[0][0] is None else int(rows[0][0])

    _GEOMETRY_SELECT_COLUMNS = (
        "geometry_ref, version, kind, lon, lat, source_crs, source_x, source_y, wkb_hex, "
        "handling_classification, handling_code, owning_unit, originator"
    )

    @staticmethod
    def _row_to_geometry(row: Sequence[Any]) -> GeometryRecord:
        return GeometryRecord(
            geometry_ref=row[0],
            version=row[1],
            kind=GeometryKind(row[2]),
            lon=row[3],
            lat=row[4],
            source_crs=row[5],
            source_x=row[6],
            source_y=row[7],
            geometry_wkb=bytes.fromhex(row[8]) if row[8] is not None else None,
            handling=Handling(
                classification=row[9],
                handling_code=row[10],
                owning_unit=row[11],
                originator=row[12],
            ),
        )

    async def _geometry_rows(
        self, geometry_refs: Sequence[str], principal: Principal, version: int | None
    ) -> list[GeometryRecord]:
        resolved_version = (
            version if version is not None else await self._current_partition_version()
        )
        if resolved_version is None or not geometry_refs:
            return []
        placeholders = ",".join("?" for _ in geometry_refs)
        access_pred = self._access.predicate(principal)
        rows = await self._ch.rows(
            f"SELECT {self._GEOMETRY_SELECT_COLUMNS} FROM geometries "
            f"WHERE geometry_ref IN ({placeholders}) AND version = ? AND ({access_pred.where})",
            [*geometry_refs, resolved_version, *access_pred.params],
        )
        return [self._row_to_geometry(row) for row in rows]

    async def get_geometry(
        self, geometry_ref: str, principal: Principal, *, version: int | None = None
    ) -> GeometryRecord | None:
        rows = await self._geometry_rows([geometry_ref], principal, version)
        return rows[0] if rows else None

    async def get_geometries(
        self, geometry_refs: Sequence[str], principal: Principal, *, version: int | None = None
    ) -> list[GeometryRecord]:
        return await self._geometry_rows(list(geometry_refs), principal, version)

    async def list_boundaries(
        self, principal: Principal, *, version: int | None = None
    ) -> list[GeometryRecord]:
        resolved_version = (
            version if version is not None else await self._current_partition_version()
        )
        if resolved_version is None:
            return []
        access_pred = self._access.predicate(principal)
        rows = await self._ch.rows(
            f"SELECT {self._GEOMETRY_SELECT_COLUMNS} FROM geometries "
            f"WHERE kind = ? AND version = ? AND ({access_pred.where})",
            [GeometryKind.POLYGON.value, resolved_version, *access_pred.params],
        )
        return [self._row_to_geometry(row) for row in rows]
