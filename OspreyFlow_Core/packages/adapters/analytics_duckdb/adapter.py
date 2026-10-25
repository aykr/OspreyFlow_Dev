"""`AnalyticsDuckDBAdapter` — full `AnalyticsPort` over DuckDB (`local-lite`
profile, `spec/04_VAULT_BACKEND.md` §2).

Every method compiles an `EventFilter` plus the access predicate
(`access_filter.py`) into one `WHERE` clause before it aggregates — never
fetches broadly and filters after (`00_ARCHITECTURE.md` §2.2). There is no
`raw_sql` method; every dimension a caller can ask for is expressed through
`EventFilter`, `HistogramBucketing` and `CrossFilterDimension`.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

import duckdb

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

from .access_filter import AccessFilter, SqlPredicate

#: Event columns a `CATEGORICAL` dimension may bucket by directly. Anything
#: else is looked up inside the JSON `properties` column — validated as a
#: safe identifier first, the same defence-in-depth as the graph adapter's
#: `groovy_identifier`.
_TOP_LEVEL_FIELDS = frozenset({"edge_type", "source_id", "target_id", "cell_site", "direction"})


def _safe_field_name(field: str) -> str:
    if not field.replace("_", "").isalnum() or not field:
        raise ValueError(f"not a safe field name for a SQL literal: {field!r}")
    return field


def _field_expression(field: str) -> str:
    name = _safe_field_name(field)
    if name in _TOP_LEVEL_FIELDS:
        return name
    return f"json_extract_string(properties, '$.{name}')"


def _row_to_event(row: tuple[object, ...]) -> EventRecord:
    (
        event_id, edge_id, edge_type, source_id, target_id, occurred_at, duration_s, cell_site,
        lat, lon, direction, properties, investigation_scope, classification, handling_code,
        owning_unit, originator, load_id,
    ) = row
    raw = properties
    parsed = json.loads(raw) if isinstance(raw, str) else (raw or {})
    return EventRecord(
        event_id=cast(str, event_id),
        edge_id=cast(str, edge_id),
        edge_type=cast(str, edge_type),
        source_id=cast(str, source_id),
        target_id=cast(str, target_id),
        occurred_at=_as_utc(occurred_at),
        duration_s=cast(float | None, duration_s),
        cell_site=cast(str | None, cell_site),
        lat=cast(float | None, lat),
        lon=cast(float | None, lon),
        direction=cast(str | None, direction),
        properties=cast(dict[str, Any], parsed),
        investigation_scope=cast(str, investigation_scope),
        handling=Handling(
            classification=cast(str, classification),
            handling_code=cast(str, handling_code),
            owning_unit=cast(str, owning_unit),
            originator=cast(str, originator),
        ),
        load_id=cast(str | None, load_id),
    )


def _as_utc(value: object) -> datetime:
    """DuckDB hands a naive timestamp back for a TIMESTAMP column; events are written in UTC."""
    return cast(datetime, value).replace(tzinfo=UTC)


class AnalyticsDuckDBAdapter:
    def __init__(self, con: duckdb.DuckDBPyConnection, handling_scheme: HandlingScheme) -> None:
        # `occurred_at` is a plain TIMESTAMP holding UTC. DuckDB converts an aware time to the
        # connection's zone on the way in, so the zone is fixed to UTC here — otherwise a machine
        # off UTC stores every event shifted and reads it back as UTC, an hour (or more) out
        # (found building ADR-109 phase A; `test_event_time_zone.py`).
        con.execute("SET TimeZone = 'UTC'")
        self._con = con
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
            clauses = [
                f"(investigation_scope = ? OR (investigation_scope IN ({scopes}) "
                f"AND edge_id IN ({edges})))"
            ]
            params.extend(inherited.scopes)
            params.extend(inherited.edge_ids)
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
        if event_filter.edge_types:
            placeholders = ",".join("?" for _ in event_filter.edge_types)
            clauses.append(f"edge_type IN ({placeholders})")
            params.extend(event_filter.edge_types)
        if event_filter.edge_ids:
            placeholders = ",".join("?" for _ in event_filter.edge_ids)
            clauses.append(f"edge_id IN ({placeholders})")
            params.extend(event_filter.edge_ids)
        if event_filter.event_ids:
            placeholders = ",".join("?" for _ in event_filter.event_ids)
            clauses.append(f"event_id IN ({placeholders})")
            params.extend(event_filter.event_ids)
        # **A7's item-category half — round 13cdc.** Values are parameterised; only the *column*
        # is interpolated, and `_field_expression` validates it as a safe identifier first, which
        # is the same guard `cross_filter`'s own dimensions already rely on.
        #
        # An empty value list would compile to `IN ()`, which is a syntax error in DuckDB and
        # would otherwise surface as a 500 on an empty facet selection; it is skipped, so
        # "no values chosen for this field" means "do not restrict by this field" rather than
        # "match nothing". That is what a filter bar with a facet expanded and nothing ticked
        # means to an analyst.
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

    def _count(self, predicate: SqlPredicate) -> int:
        row = self._con.execute(
            f"SELECT COUNT(*) FROM events WHERE {predicate.where}", predicate.params
        ).fetchone()
        return int(row[0]) if row else 0

    # --- histogram ---------------------------------------------------------

    async def histogram(self, req: HistogramRequest, principal: Principal) -> Histogram:
        predicate = self._predicate(req.filter, principal)
        if req.bucketing is HistogramBucketing.FIXED_INTERVAL:
            return self._fixed_interval_histogram(predicate, req.interval_seconds)
        if req.bucketing is HistogramBucketing.WEEKDAY_HOUR:
            return self._weekday_hour_histogram(predicate)
        assert req.field is not None  # enforced by HistogramRequest's own validator
        return self._categorical_histogram(predicate, req.field)

    # --- trend (ADR-113) ----------------------------------------------------------------------

    async def trend(self, req: TrendRequest, principal: Principal) -> TrendResult:
        predicate = self._predicate(req.filter, principal)
        unit = "week" if req.interval is TrendInterval.WEEK else "month"
        period = f"date_trunc('{unit}', occurred_at)"
        series = (
            "NULL"
            if req.group_by is None
            else f"CAST({_field_expression(req.group_by)} AS VARCHAR)"
        )
        # The bounds are checked on what the reader can see, before anything is aggregated, so a
        # refusal is never a partial answer and a hidden event cannot tip a trend over its bound.
        periods, groups = self._con.execute(
            f"SELECT COUNT(DISTINCT {period}), COUNT(DISTINCT {series}) FROM events "
            f"WHERE {predicate.where}",
            predicate.params,
        ).fetchone() or (0, 0)
        if periods > req.max_periods:
            raise TrendLimitExceeded("periods", req.max_periods, int(periods))
        if groups > req.max_series:
            raise TrendLimitExceeded("series", req.max_series, int(groups))
        if req.measure is TrendMeasure.SUM:
            assert req.measure_field is not None  # enforced by TrendRequest's own validator
            number = f"TRY_CAST({_field_expression(req.measure_field)} AS DOUBLE)"
            value, unvalued = f"COALESCE(SUM({number}), 0)", f"COUNT(*) - COUNT({number})"
        else:
            value, unvalued = "COUNT(*)", "0"
        rows = self._con.execute(
            f"SELECT {period} AS period, {series} AS series, {value} AS value, COUNT(*) AS n, "
            f"{unvalued} AS unvalued FROM events WHERE {predicate.where} "
            "GROUP BY period, series ORDER BY period, series NULLS FIRST",
            predicate.params,
        ).fetchall()
        classifications = [
            str(c)
            for (c,) in self._con.execute(
                f"SELECT DISTINCT handling_classification FROM events WHERE {predicate.where} "
                "ORDER BY 1",
                predicate.params,
            ).fetchall()
        ]
        handlings = [
            CountedHandling(
                classification=str(c), handling_code=str(h), owning_unit=str(u), originator=str(o)
            )
            for c, h, u, o in self._con.execute(
                "SELECT DISTINCT handling_classification, handling_code, owning_unit, originator "
                f"FROM events WHERE {predicate.where} ORDER BY 1, 2, 3, 4",
                predicate.params,
            ).fetchall()
        ]
        points = [
            TrendPoint(
                period_start=(p if p.tzinfo else p.replace(tzinfo=UTC)),
                series=None if g is None else str(g),
                value=float(v),
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

    def _fixed_interval_histogram(
        self, predicate: SqlPredicate, interval_seconds: int | None
    ) -> Histogram:
        assert interval_seconds is not None
        rows = self._con.execute(
            "SELECT CAST(floor(epoch(occurred_at) / ?) AS BIGINT) AS bucket, COUNT(*) AS cnt "
            f"FROM events WHERE {predicate.where} GROUP BY bucket ORDER BY bucket",
            [interval_seconds, *predicate.params],
        ).fetchall()
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

    def _weekday_hour_histogram(self, predicate: SqlPredicate) -> Histogram:
        rows = self._con.execute(
            "SELECT CAST(isodow(occurred_at) AS INTEGER) - 1 AS weekday, "
            "CAST(hour(occurred_at) AS INTEGER) AS hour, COUNT(*) AS cnt "
            f"FROM events WHERE {predicate.where} GROUP BY weekday, hour "
            "ORDER BY weekday, hour",
            predicate.params,
        ).fetchall()
        buckets = [
            HistogramBucket(weekday=weekday, hour=hour, count=count)
            for weekday, hour, count in rows
        ]
        return Histogram(
            bucketing=HistogramBucketing.WEEKDAY_HOUR,
            buckets=buckets,
            total=sum(b.count for b in buckets),
        )

    def _categorical_histogram(self, predicate: SqlPredicate, field: str) -> Histogram:
        expr = _field_expression(field)
        rows = self._con.execute(
            f"SELECT {expr} AS label, COUNT(*) AS cnt FROM events "
            f"WHERE {predicate.where} GROUP BY label ORDER BY label",
            predicate.params,
        ).fetchall()
        buckets = [HistogramBucket(label=label, count=count) for label, count in rows]
        return Histogram(
            bucketing=HistogramBucketing.CATEGORICAL,
            buckets=buckets,
            total=sum(b.count for b in buckets),
        )

    # --- geo_bins ------------------------------------------------------------

    async def geo_bins(self, req: GeoBinRequest, principal: Principal) -> list[GeoBin]:
        """Sinusoidal-projection binning (`x = lon * cos(lat)`, gridded
        uniformly in `x`/`lat`): a degree of longitude at 55°N is about
        57% the width, on the ground, of one at the equator, so a plain
        equal-*degree* grid gives the UK materially narrower bins than the
        US at the same precision, and a cross-region density comparison —
        exactly what a heat map is for — reads wrong. Gridding uniformly
        in `lon / cos(lat)` instead of raw `lon` keeps bin *area*
        comparable across latitudes; each row's own latitude sets its
        longitude bin width, not a single global one."""
        predicate = self._predicate(req.filter, principal)
        step = 180.0 / (2**req.precision)
        rows = self._con.execute(
            "SELECT CAST(floor(lat / ?) AS BIGINT) AS lat_bin, "
            "CAST(floor(lon / (? / cos(radians(lat)))) AS BIGINT) AS lon_bin, COUNT(*) AS cnt "
            f"FROM events WHERE ({predicate.where}) AND lat IS NOT NULL AND lon IS NOT NULL "
            "GROUP BY lat_bin, lon_bin ORDER BY lat_bin, lon_bin",
            [step, step, *predicate.params],
        ).fetchall()
        result = []
        for lat_bin, lon_bin, count in rows:
            center_lat = max(min((lat_bin + 0.5) * step, 90.0), -90.0)
            # Clamped, not left to blow up: cos(lat) -> 0 approaching the
            # poles, which this platform's UK/US deployments never reach,
            # but a defensive floor keeps a stray point from producing an
            # infinite or nonsensical bin width instead of a wide one.
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

    # --- sightings (Stage 4f, B18's own snail trail) --------------------------

    #: A defensive cap, not a corpus-scale one — `list_sightings` is scoped to one entity's own
    #: `node_ids` restriction over an already-brushed window (`SightingRequest`'s own docstring),
    #: a population that practically never approaches this, unlike `geo_bins`'s genuine
    #: corpus-wide concern. Capped rather than left unbounded anyway — silently truncated here
    #: (documented, not typed as `limit_exceeded`): a partial
    #: snail trail is still a legible one, and the caller-scoped `EventFilter` this method requires
    #: makes reaching the cap itself the signal something is mis-scoped, not ordinary use.
    _MAX_SIGHTINGS = 5000

    async def list_sightings(self, req: SightingRequest, principal: Principal) -> list[Sighting]:
        predicate = self._predicate(req.filter, principal)
        rows = self._con.execute(
            "SELECT occurred_at, lat, lon FROM events "
            f"WHERE ({predicate.where}) AND lat IS NOT NULL AND lon IS NOT NULL "
            "ORDER BY occurred_at ASC LIMIT ?",
            [*predicate.params, self._MAX_SIGHTINGS],
        ).fetchall()
        # DuckDB returns naive `datetime`s regardless of the column's own TIMESTAMPTZ-shaped
        # storage — reattached here, the same `tz=UTC` fix-up `_fixed_interval_histogram` already
        # applies to its own `datetime.fromtimestamp` construction, above.
        return [
            Sighting(occurred_at=occurred_at.replace(tzinfo=UTC), lat=lat, lon=lon)
            for occurred_at, lat, lon in rows
        ]

    # --- containment (owner rulings R9 (c) and R10, round 13cf) -----------------

    async def geocode_events(
        self, req: GeocodeRequest, principal: Principal
    ) -> list[GeocodedEvent]:
        if req.filter.inherited is not None:
            # A write to the case's own events: a parent's events are read-only to a branch
            # (ADR-084 Amendment 2), and would otherwise be read here and silently left unwritten.
            raise ValueError("geocode_events writes a case's own events; it takes no inherited")
        prop = _safe_field_name(req.property)
        resolved_version = (
            req.version if req.version is not None else self._current_partition_version()
        )
        if resolved_version is None:
            return []
        event_pred = self._predicate(req.filter, principal)
        geometry_access = self._access.predicate(principal)
        refs = sorted(req.cells)
        ref_placeholders = ",".join("?" for _ in refs)
        # Covering, not `ST_Contains`: a point on an edge two cells share is inside the site, so it
        # must land somewhere, and `MIN` over the covering refs makes "somewhere" deterministic.
        rows = self._con.execute(
            "WITH ev AS ("
            "  SELECT event_id, edge_id, edge_type, source_id, target_id, occurred_at, lat, lon, "
            "         handling_classification, handling_code, owning_unit, originator, "
            f"         json_extract_string(properties, '$.{prop}') AS previous "
            f"  FROM events WHERE ({event_pred.where}) AND lat IS NOT NULL AND lon IS NOT NULL"
            "), cell AS ("
            "  SELECT geometry_ref, geometry FROM geometries "
            f"  WHERE kind = ? AND version = ? AND geometry_ref IN ({ref_placeholders}) "
            f"  AND ({geometry_access.where})"
            "), hit AS ("
            "  SELECT ev.event_id, MIN(cell.geometry_ref) AS geometry_ref FROM ev JOIN cell "
            "  ON ST_Covers(cell.geometry, ST_Point(ev.lon, ev.lat)) GROUP BY ev.event_id"
            ") "
            "SELECT ev.event_id, ev.edge_id, ev.edge_type, ev.source_id, ev.target_id, "
            "       ev.occurred_at, hit.geometry_ref, ev.previous, ev.handling_classification, "
            "       ev.handling_code, ev.owning_unit, ev.originator "
            "FROM ev LEFT JOIN hit USING (event_id) ORDER BY ev.event_id",
            [
                *event_pred.params,
                GeometryKind.POLYGON.value,
                resolved_version,
                *refs,
                *geometry_access.params,
            ],
        ).fetchall()

        values = set(req.cells.values())
        geocoded: list[GeocodedEvent] = []
        to_set: list[list[object]] = []
        to_clear: list[list[object]] = []
        for row in rows:
            event_id, edge_id, edge_type, source_id, target_id, occurred_at, ref, previous = row[:8]
            if ref is None:
                # Not covered. Only a value this call owns is cleared: an event geocoded into some
                # *other* site's cell keeps that claim.
                if previous in values:
                    to_clear.append([event_id, req.filter.investigation_scope])
                continue
            value = req.cells[ref]
            if previous != value:
                to_set.append([json.dumps({prop: value}), event_id, req.filter.investigation_scope])
            geocoded.append(
                GeocodedEvent(
                    event_id=event_id,
                    edge_id=edge_id,
                    edge_type=edge_type,
                    source_id=source_id,
                    target_id=target_id,
                    occurred_at=cast(datetime, occurred_at).replace(tzinfo=UTC),
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
        if to_set:
            self._con.executemany(
                "UPDATE events SET properties = json_merge_patch(COALESCE(properties, '{}'), ?) "
                "WHERE event_id = ? AND investigation_scope = ?",
                to_set,
            )
        if to_clear:
            self._con.executemany(
                "UPDATE events SET properties = json_merge_patch(properties, "
                f"'{{\"{prop}\": null}}') WHERE event_id = ? AND investigation_scope = ?",
                to_clear,
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
        baseline_count = self._count(self._predicate(baseline_filter, principal))
        comparison_count = self._count(self._predicate(comparison_filter, principal))

        baseline_buckets = self._bucket_count(
            req.baseline_window, req.bucketing, req.interval_seconds
        )
        comparison_buckets = self._bucket_count(
            req.comparison_window, req.bucketing, req.interval_seconds
        )
        baseline_rate = baseline_count / baseline_buckets
        comparison_rate = comparison_count / comparison_buckets
        ratio = None if baseline_count == 0 else comparison_count / baseline_count

        return BaselineResult(
            baseline_count=baseline_count,
            comparison_count=comparison_count,
            baseline_rate_per_bucket=baseline_rate,
            comparison_rate_per_bucket=comparison_rate,
            ratio=ratio,
        )

    # --- cross_filter --------------------------------------------------------

    async def cross_filter(
        self, req: CrossFilterRequest, principal: Principal
    ) -> dict[str, Histogram]:
        predicate = self._predicate(req.filter, principal)
        result: dict[str, Histogram] = {}
        for dimension in req.dimensions:
            if dimension.bucketing is HistogramBucketing.FIXED_INTERVAL:
                result[dimension.name] = self._fixed_interval_histogram(
                    predicate, dimension.interval_seconds
                )
            elif dimension.bucketing is HistogramBucketing.WEEKDAY_HOUR:
                result[dimension.name] = self._weekday_hour_histogram(predicate)
            else:
                assert dimension.field is not None
                result[dimension.name] = self._categorical_histogram(predicate, dimension.field)
        return result

    # --- list_events (ADR-089) -------------------------------------------------

    async def list_events(self, req: EventListRequest, principal: Principal) -> EventListResult:
        predicate = self._predicate(req.filter, principal)
        total = self._count(predicate)
        rows = self._con.execute(
            "SELECT event_id, edge_id, edge_type, source_id, target_id, occurred_at, duration_s, "
            "cell_site, lat, lon, direction, properties, investigation_scope, "
            "handling_classification, handling_code, owning_unit, originator, load_id "
            f"FROM events WHERE {predicate.where} "
            "ORDER BY occurred_at DESC, event_id DESC LIMIT ? OFFSET ?",
            [*predicate.params, req.limit, req.offset],
        ).fetchall()
        return EventListResult(total=total, events=[_row_to_event(row) for row in rows])

    # --- first_seen (ADR-087) --------------------------------------------------

    async def first_seen(self, req: FirstSeenRequest, principal: Principal) -> FirstSeenResult:
        predicate = self._predicate(req.filter, principal)
        node_rows = self._con.execute(
            "SELECT id, MIN(occurred_at) AS first FROM ("
            f"  SELECT source_id AS id, occurred_at FROM events WHERE {predicate.where}"
            "  UNION ALL "
            f"  SELECT target_id AS id, occurred_at FROM events WHERE {predicate.where}"
            ") GROUP BY id",
            [*predicate.params, *predicate.params],
        ).fetchall()
        edge_rows = self._con.execute(
            "SELECT edge_id, MIN(occurred_at) FROM events "
            f"WHERE {predicate.where} GROUP BY edge_id",
            predicate.params,
        ).fetchall()
        return FirstSeenResult(
            nodes={node_id: _as_utc(first) for node_id, first in node_rows},
            edges={edge_id: _as_utc(first) for edge_id, first in edge_rows},
        )

    # --- writes -------------------------------------------------------------

    async def load_events(self, records: Sequence[EventRecord]) -> None:
        if not records:
            return
        self._con.executemany(
            "INSERT INTO events (event_id, edge_id, edge_type, source_id, target_id, "
            "occurred_at, duration_s, cell_site, lat, lon, direction, properties, "
            "investigation_scope, handling_classification, handling_code, owning_unit, "
            "originator, load_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                [
                    r.event_id,
                    r.edge_id,
                    r.edge_type,
                    r.source_id,
                    r.target_id,
                    r.occurred_at,
                    r.duration_s,
                    r.cell_site,
                    r.lat,
                    r.lon,
                    r.direction,
                    json.dumps(r.properties),
                    r.investigation_scope,
                    r.handling.classification,
                    r.handling.handling_code,
                    r.handling.owning_unit,
                    r.handling.originator,
                    r.load_id,
                ]
                for r in records
            ],
        )

    async def retract_load(self, load_id: str) -> int:
        """`AnalyticsPort.retract_load`: the rows this load wrote, by its id alone. A row with no
        `load_id` is `NULL`, which `= ?` never matches, so unattributed events stay."""
        removed = self._con.execute(
            "DELETE FROM events WHERE load_id = ? RETURNING event_id", [load_id]
        ).fetchall()
        return len(removed)

    # --- the geometry reference partition -----------------------------------

    async def load_geometries(self, records: Sequence[GeometryRecord]) -> None:
        if not records:
            return
        self._con.executemany(
            "INSERT INTO geometries (geometry_ref, version, kind, lon, lat, source_crs, "
            "source_x, source_y, geometry, handling_classification, handling_code, "
            "owning_unit, originator) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ST_GeomFromWKB(?), ?, ?, ?, ?)",
            [
                [
                    r.geometry_ref,
                    r.version,
                    r.kind.value,
                    r.lon,
                    r.lat,
                    r.source_crs,
                    r.source_x,
                    r.source_y,
                    r.geometry_wkb,
                    r.handling.classification,
                    r.handling.handling_code,
                    r.handling.owning_unit,
                    r.handling.originator,
                ]
                for r in records
            ],
        )

    async def retract_geometries(self, geometry_refs: Sequence[str], *, version: int) -> int:
        """`AnalyticsPort.retract_geometries`: these refs at this version, whatever the marking."""
        if not geometry_refs:
            return 0
        placeholders = ",".join("?" for _ in geometry_refs)
        removed = self._con.execute(
            f"DELETE FROM geometries WHERE version = ? AND geometry_ref IN ({placeholders}) "
            "RETURNING geometry_ref",
            [version, *geometry_refs],
        ).fetchall()
        return len(removed)

    def _current_partition_version(self) -> int | None:
        row = self._con.execute("SELECT MAX(version) FROM geometries").fetchone()
        return None if row is None or row[0] is None else int(row[0])

    #: Shared by every geometry read below — `ST_AsWKB(geometry)` is `NULL`
    #: for a point row (whose `geometry` column is itself `NULL`), so
    #: `_row_to_geometry` below never has to branch on `kind` to know
    #: whether to read it.
    _GEOMETRY_SELECT_COLUMNS = (
        "geometry_ref, version, kind, lon, lat, source_crs, source_x, source_y, "
        "ST_AsWKB(geometry), handling_classification, handling_code, owning_unit, originator"
    )

    @staticmethod
    def _row_to_geometry(row: tuple[object, ...]) -> GeometryRecord:
        # `row` is `tuple[object, ...]` because DuckDB's own driver returns an untyped tuple —
        # these `cast`s assert what `_GEOMETRY_SELECT_COLUMNS`' own column order guarantees at
        # runtime, matching each field's real DuckDB column type; they change no behaviour, only
        # what mypy can see.
        return GeometryRecord(
            geometry_ref=cast(str, row[0]),
            version=cast(int, row[1]),
            kind=GeometryKind(cast(str, row[2])),
            lon=cast("float | None", row[3]),
            lat=cast("float | None", row[4]),
            source_crs=cast("str | None", row[5]),
            source_x=cast("float | None", row[6]),
            source_y=cast("float | None", row[7]),
            geometry_wkb=cast(bytes, row[8]) if row[8] is not None else None,
            handling=Handling(
                classification=cast(str, row[9]),
                handling_code=cast(str, row[10]),
                owning_unit=cast(str, row[11]),
                originator=cast(str, row[12]),
            ),
        )

    def _geometry_rows(
        self, geometry_refs: Sequence[str], principal: Principal, version: int | None
    ) -> list[GeometryRecord]:
        resolved_version = version if version is not None else self._current_partition_version()
        if resolved_version is None or not geometry_refs:
            return []
        placeholders = ",".join("?" for _ in geometry_refs)
        access_pred = self._access.predicate(principal)
        rows = self._con.execute(
            f"SELECT {self._GEOMETRY_SELECT_COLUMNS} FROM geometries "
            f"WHERE geometry_ref IN ({placeholders}) AND version = ? AND ({access_pred.where})",
            [*geometry_refs, resolved_version, *access_pred.params],
        ).fetchall()
        return [self._row_to_geometry(row) for row in rows]

    async def get_geometry(
        self, geometry_ref: str, principal: Principal, *, version: int | None = None
    ) -> GeometryRecord | None:
        rows = self._geometry_rows([geometry_ref], principal, version)
        return rows[0] if rows else None

    async def get_geometries(
        self, geometry_refs: Sequence[str], principal: Principal, *, version: int | None = None
    ) -> list[GeometryRecord]:
        return self._geometry_rows(list(geometry_refs), principal, version)

    async def list_boundaries(
        self, principal: Principal, *, version: int | None = None
    ) -> list[GeometryRecord]:
        """The "select an existing boundary" read path (Phase 5's known-gaps closure) — every
        `kind = polygon` row at the resolved partition version, access-
        filtered exactly like every other geometry read. `geometry_ref` is
        not known in advance the way `get_geometry`'s caller already has
        one, so this cannot reuse `_geometry_rows`'s `IN (...)` shape."""
        resolved_version = version if version is not None else self._current_partition_version()
        if resolved_version is None:
            return []
        access_pred = self._access.predicate(principal)
        rows = self._con.execute(
            f"SELECT {self._GEOMETRY_SELECT_COLUMNS} FROM geometries "
            f"WHERE kind = ? AND version = ? AND ({access_pred.where})",
            [GeometryKind.POLYGON.value, resolved_version, *access_pred.params],
        ).fetchall()
        return [self._row_to_geometry(row) for row in rows]
