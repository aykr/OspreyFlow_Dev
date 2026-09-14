"""`AnalyticsDuckDBAdapter` — full `AnalyticsPort` over DuckDB (`local-lite`
profile, `docs/04_VAULT_BACKEND.md` §2).

Every method compiles an `EventFilter` plus the access predicate
(`access_filter.py`) into one `WHERE` clause before it aggregates — never
fetches broadly and filters after (`00_ARCHITECTURE.md` §2.2). There is no
`raw_sql` method; every dimension a caller can ask for is expressed through
`EventFilter`, `HistogramBucketing` and `CrossFilterDimension`.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import duckdb

from ontology.handling import HandlingScheme
from schemas.analytics import (
    BaselineRequest,
    BaselineResult,
    CrossFilterRequest,
    EventFilter,
    GeoBin,
    GeoBinRequest,
    Histogram,
    HistogramBucket,
    HistogramBucketing,
    HistogramRequest,
)
from schemas.domain import Interval, Principal

from .access_filter import AccessFilter, SqlPredicate

#: Event columns a `CATEGORICAL` dimension may bucket by directly. Anything
#: else is looked up inside the JSON `properties` column — validated as a
#: safe identifier first, the same defence-in-depth as the graph adapter's
#: `groovy_identifier`.
_TOP_LEVEL_FIELDS = frozenset(
    {"edge_type", "source_id", "target_id", "cell_site", "direction"}
)


def _safe_field_name(field: str) -> str:
    if not field.replace("_", "").isalnum() or not field:
        raise ValueError(f"not a safe field name for a SQL literal: {field!r}")
    return field


def _field_expression(field: str) -> str:
    name = _safe_field_name(field)
    if name in _TOP_LEVEL_FIELDS:
        return name
    return f"json_extract_string(properties, '$.{name}')"


class AnalyticsDuckDBAdapter:
    def __init__(self, con: duckdb.DuckDBPyConnection, handling_scheme: HandlingScheme) -> None:
        self._con = con
        self._access = AccessFilter(handling_scheme)

    # --- shared predicate compilation ------------------------------------

    def _event_filter_predicate(self, event_filter: EventFilter) -> SqlPredicate:
        clauses = ["investigation_scope = ?"]
        params: list[object] = [event_filter.investigation_scope]
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
