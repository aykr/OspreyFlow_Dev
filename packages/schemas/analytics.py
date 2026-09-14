"""`AnalyticsPort` request and response shapes — `docs/00_ARCHITECTURE.md` §2.2,
`docs/01_DOMAIN_MODEL.md` §3 and the new §9 it gained alongside this module.

Columnar aggregation over event-shaped data. `EventRecord` is the row the
staging pipeline writes to Parquet (`01_DOMAIN_MODEL.md` §3: "the analytics
store holds the event rows") — one per call, message, transaction or
sighting, summarised in the graph as a single weighted edge. Every read
method takes an `EventFilter` the adapter injects into its `WHERE` clause
before aggregating; there is no `raw_sql` escape hatch, deliberately
(`00_ARCHITECTURE.md` §2.2) — an arbitrary SQL string cannot be
access-filtered, the same reason `GraphPort` never accepts free-form
Gremlin (ADR-003).

TypeScript types are generated from these (`generate_ts.py`); a drift
between the two fails the build (`scripts/schemas_check.py`).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from schemas.domain import EdgeId, Handling, Interval, NodeId

# --- The event record (01_DOMAIN_MODEL.md §3) ---------------------------


class EventRecord(BaseModel):
    """One row in the analytics store. `edge_id` ties it back to the
    summarised graph edge it is one occurrence of; `handling` is carried
    per row (not looked up via `edge_id`) so a filtered query never has to
    join back to the graph store to know what it may not show."""

    event_id: str
    edge_id: EdgeId
    edge_type: str
    source_id: NodeId
    target_id: NodeId
    occurred_at: datetime
    duration_s: float | None = None
    cell_site: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    direction: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    investigation_scope: str
    handling: Handling

    @model_validator(mode="after")
    def _lat_lon_travel_together(self) -> EventRecord:
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat and lon must be both present or both null")
        return self


# --- The geometry reference partition (03_CONDUIT_MIDDLEWARE.md §5.1) ---


class GeometryRecord(BaseModel):
    """One row in the analytics store's geometry reference partition —
    `03_CONDUIT_MIDDLEWARE.md` §5.1: "the geometry column lives in the
    analytics store where spatial predicates are cheap, and the graph
    holds the Location node with a reference to it." `geometry_ref` is
    that reference's value, produced by the `geometry_ref`/`grid_ref`
    Knowledge Adapters (`01_DOMAIN_MODEL.md` §7.1) as a deterministic hash
    of `(source_crs, source_x, source_y)` — the same source coordinate
    always yields the same ref, so a recipe re-run never mints a second
    row for the same point.

    Never written on a graph `Location` node directly — putting geometry
    on the graph node would make spatial filtering a traversal, the wrong
    shape of query. A `Location.geometry_ref` property (a plain string)
    points at exactly one row here; the row itself carries the reprojected
    WGS84 point and the retained original, the same `value_raw` discipline
    every other Knowledge Adapter follows.

    No `investigation_scope`/`handling` here, unlike `EventRecord`:
    reference/gazetteer data is versioned as a whole rather than scoped
    per investigation (`03_CONDUIT_MIDDLEWARE.md` §5.1's "reference
    partition"), and the full versioning/access-control story for that
    partition is Phase 5 scope (`07_BUILD_PLAN.md`), the same phase that
    builds the geospatial connectors and the site grid this table also
    serves. Phase 2 establishes the correct storage tier and shape; it
    does not build a read path with its own access control for it."""

    geometry_ref: str
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    source_crs: str
    source_x: float | None = None
    source_y: float | None = None


# --- Shared scoping for every read method --------------------------------


class EventFilter(BaseModel):
    """Restricts the event population a method aggregates over. Every
    field here is a predicate the adapter applies inside its own `WHERE`
    clause before aggregation, never after (`03_CONDUIT_MIDDLEWARE.md`
    §6) — `04_VAULT_BACKEND.md` §2 partitions the event tables by
    `(investigation_scope, month)`, which is why scope is required rather
    than optional."""

    investigation_scope: str
    window: Interval | None = None
    node_ids: list[NodeId] = Field(default_factory=list)
    edge_types: list[str] = Field(default_factory=list)


class HistogramBucketing(StrEnum):
    """`02_GLASS_FRONTEND.md` §3.4: the timeline's two temporal modes.
    `CATEGORICAL` is what lets `cross_filter` bucket a dimension that
    isn't time at all — an item type or a cell identifier."""

    FIXED_INTERVAL = "fixed_interval"
    WEEKDAY_HOUR = "weekday_hour"
    CATEGORICAL = "categorical"


class HistogramRequest(BaseModel):
    filter: EventFilter
    bucketing: HistogramBucketing = HistogramBucketing.FIXED_INTERVAL
    interval_seconds: int | None = Field(default=None, gt=0)
    field: str | None = None  # the `EventRecord`/`properties` field to bucket by; CATEGORICAL only

    @model_validator(mode="after")
    def _bucketing_needs_its_own_parameter(self) -> HistogramRequest:
        if self.bucketing is HistogramBucketing.FIXED_INTERVAL and self.interval_seconds is None:
            raise ValueError("interval_seconds is required for fixed_interval bucketing")
        if self.bucketing is HistogramBucketing.CATEGORICAL and self.field is None:
            raise ValueError("field is required for categorical bucketing")
        return self


class HistogramBucket(BaseModel):
    """Exactly one label shape is populated, matching the request's
    `bucketing`: `start`/`end` for `fixed_interval`, `weekday`/`hour` for
    `weekday_hour`, `label` for `categorical`."""

    start: datetime | None = None
    end: datetime | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)  # 0 = Monday
    hour: int | None = Field(default=None, ge=0, le=23)
    label: str | None = None
    count: int = Field(ge=0)


class Histogram(BaseModel):
    bucketing: HistogramBucketing
    buckets: list[HistogramBucket]
    total: int = Field(ge=0)


class GeoBinRequest(BaseModel):
    """`precision` sets the bin size — higher is finer, each step halving
    the latitude span a bin covers (not a geohash: no base-32 cell-id
    encoding, and bins are equal-*area* via a sinusoidal projection, not
    equal-degree — see `adapters/analytics_duckdb`). Binning happens here,
    server-side, so a heat map never ships a million raw points to the
    Glass (`00_ARCHITECTURE.md` §1.1)."""

    filter: EventFilter
    precision: int = Field(ge=1, le=12)


class GeoBin(BaseModel):
    cell_id: str
    centroid_lon: float = Field(ge=-180, le=180)
    centroid_lat: float = Field(ge=-90, le=90)
    count: int = Field(ge=0)


class BaselineRequest(BaseModel):
    """Compares a comparison window against a baseline window over the
    same filter and bucketing. The HMP finding — four cells at ~52% of
    incidents — is a baseline comparison, not a raw count."""

    filter: EventFilter
    baseline_window: Interval
    comparison_window: Interval
    bucketing: HistogramBucketing = HistogramBucketing.FIXED_INTERVAL
    interval_seconds: int | None = Field(default=None, gt=0)
    field: str | None = None


class BaselineResult(BaseModel):
    baseline_count: int = Field(ge=0)
    comparison_count: int = Field(ge=0)
    baseline_rate_per_bucket: float = Field(ge=0)
    comparison_rate_per_bucket: float = Field(ge=0)
    ratio: float | None = None  # null when baseline_count is 0 — never divide to guess


class CrossFilterDimension(BaseModel):
    """One entry in a `CrossFilterRequest` — a named histogram computed
    against the same filter, so the timeline, the map and the histogram
    panel restrict in lockstep (`08_ACCEPTANCE_SCENARIOS.md` A3)."""

    name: str
    bucketing: HistogramBucketing
    interval_seconds: int | None = Field(default=None, gt=0)
    field: str | None = None

    @model_validator(mode="after")
    def _bucketing_needs_its_own_parameter(self) -> CrossFilterDimension:
        if self.bucketing is HistogramBucketing.FIXED_INTERVAL and self.interval_seconds is None:
            raise ValueError("interval_seconds is required for fixed_interval bucketing")
        if self.bucketing is HistogramBucketing.CATEGORICAL and self.field is None:
            raise ValueError("field is required for categorical bucketing")
        return self


class CrossFilterRequest(BaseModel):
    filter: EventFilter
    dimensions: list[CrossFilterDimension] = Field(min_length=1)


ALL_MODELS: tuple[type[BaseModel], ...] = (
    EventRecord,
    GeometryRecord,
    EventFilter,
    HistogramRequest,
    HistogramBucket,
    Histogram,
    GeoBinRequest,
    GeoBin,
    BaselineRequest,
    BaselineResult,
    CrossFilterDimension,
    CrossFilterRequest,
)
