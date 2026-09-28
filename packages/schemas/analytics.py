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


class GeometryKind(StrEnum):
    """A known-gaps closure: `GeometryRecord` was
    point-only through Phase 2/5 Checkpoint 3c. `POLYGON` is the boundary/jurisdiction shape a
    `Location` with no single point (a ward, an administrative area — see
    `packages/ontology/default.yaml`'s own "a jurisdiction... must be able
    to carry none at all" allowance for `geometry_ref`) can now carry."""

    POINT = "point"
    POLYGON = "polygon"


class GeometryRecord(BaseModel):
    """One row in the analytics store's geometry reference partition —
    `03_CONDUIT_MIDDLEWARE.md` §5.1: "the geometry column lives in the
    analytics store where spatial predicates are cheap, and the graph
    holds the Location node with a reference to it." `geometry_ref` is
    that reference's value: for a `POINT` row, produced by the
    `geometry_ref`/`grid_ref` Knowledge Adapters (`01_DOMAIN_MODEL.md`
    §7.1) as a deterministic hash of `(source_crs, source_x, source_y)` —
    the same source coordinate always yields the same ref, so a recipe
    re-run never mints a second row for the same point.

    Never written on a graph `Location` node directly — putting geometry
    on the graph node would make spatial filtering a traversal, the wrong
    shape of query. A `Location.geometry_ref` property (a plain string)
    points at exactly one row here; the row itself carries the reprojected
    WGS84 point and the retained original, the same `value_raw` discipline
    every other Knowledge Adapter follows.

    No `investigation_scope` here, unlike `EventRecord`: reference/gazetteer
    data is versioned as a whole rather than scoped per investigation
    (`03_CONDUIT_MIDDLEWARE.md` §5.1's "reference partition") — a gazetteer
    refresh loads a new `version` of the *whole* partition rather than
    merging into the previous one, and every prior version's rows are
    retained (never overwritten) so an investigation can still resolve
    against the gazetteer version that was in force when a place name was
    matched. `AnalyticsPort.get_geometry`/`get_geometries` default to the
    partition's current version (the highest `version` present) and accept
    an explicit older one to pin a historical read.

    `handling` **is** carried per row, unlike the note this docstring used
    to make — this partition now has a real,
    access-controlled read path, and geometry is not uniformly public
    reference data: a site's own control-point/grid geometry (the HMP
    case) is exactly as sensitive as the `Location` entities it backs, so
    it needs the same per-row handling discipline `EventRecord` already
    has, checked by the same `AccessFilter` (`01_DOMAIN_MODEL.md` §2.2).

    **`kind` discriminates `POINT` from `POLYGON` (Phase 5's known-gaps closure).** A `POINT`
    row carries `lon`/`lat` (and, optionally, the retained original
    `source_crs`/`source_x`/`source_y`) and no `geometry_wkb`. A `POLYGON`
    row — a boundary with no single point — carries `geometry_wkb` (WKB
    bytes; the DuckDB adapter stores/reads these via its `spatial`
    extension's `ST_GeomFromWKB`/`ST_AsWKB`) and no `lon`/`lat`. The two
    shapes are mutually exclusive, enforced below, rather than a `POLYGON`
    row carrying a meaningless centroid or a `POINT` row carrying an unused
    WKB column."""

    geometry_ref: str
    version: int = Field(ge=1)
    kind: GeometryKind = GeometryKind.POINT
    lon: float | None = Field(default=None, ge=-180, le=180)
    lat: float | None = Field(default=None, ge=-90, le=90)
    source_crs: str | None = None
    source_x: float | None = None
    source_y: float | None = None
    geometry_wkb: bytes | None = None
    handling: Handling

    @model_validator(mode="after")
    def _kind_and_payload_agree(self) -> GeometryRecord:
        if self.kind is GeometryKind.POINT:
            if self.lon is None or self.lat is None:
                raise ValueError("a point GeometryRecord requires both lon and lat")
            if self.geometry_wkb is not None:
                raise ValueError("a point GeometryRecord must not carry geometry_wkb")
        else:
            if self.geometry_wkb is None:
                raise ValueError("a polygon GeometryRecord requires geometry_wkb")
            if self.lon is not None or self.lat is not None:
                raise ValueError("a polygon GeometryRecord must not carry lon/lat")
        return self


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
    #: **Restrict by a field's value, not merely aggregate over it — round 13cdc.**
    #:
    #: `08_ACCEPTANCE_SCENARIOS.md` A7 filters reports "to one residential sub-unit and one item
    #: category". The sub-unit half is `node_ids`; the item-category half had nothing — that
    #: document's own "Known gap" section recorded it. `cross_filter`'s categorical dimensions
    #: *display* a field's distinct values; they never let a caller restrict to one.
    #:
    #: `{field: [value, ...]}`. Values within one field are **OR**-ed (an item category is one of
    #: these), fields are **AND**-ed (this sub-unit *and* this category) — the shape a filter bar
    #: with several facets actually has. Equality only: nothing fuzzy, no ranges, no negation,
    #: because A7 needs none of them and each is a separate decision about what an analyst is
    #: asserting when they click a facet.
    #:
    #: A field may be a top-level event column or a key inside the JSON `properties` blob; the
    #: adapter resolves which and validates the name as a safe identifier first, the same
    #: defence-in-depth `cross_filter`'s own dimensions already use. The predicate is compiled
    #: **into** the adapter's `WHERE` clause alongside the access filter, never applied after
    #: retrieval (`03_CONDUIT_MIDDLEWARE.md` §6, `CLAUDE.md` rule 2).
    value_filters: dict[str, list[str]] = Field(default_factory=dict)


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


class SightingRequest(BaseModel):
    """B18's own backend dependency, found genuinely missing while building it, not assumed to
    exist — `AnalyticsPort` had `histogram`/`geo_bins`/`cross_filter`, all aggregate-shaped, and no
    method returning ordered, timestamped, per-entity points at all. `filter.node_ids` names the
    one entity; `filter.window` is the brush window `02_GLASS_FRONTEND.md` §3.5's own "Snail trail"
    row scopes the track to. Raw points, not server-side binned like `geo_bins` — deliberately: a
    snail trail is one entity's own sighting history inside an already-brushed window, not a
    corpus-wide density query, so the "never ship a million points" concern `geo_bins`'s own
    docstring names does not apply at this scale."""

    filter: EventFilter


class Sighting(BaseModel):
    occurred_at: datetime
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


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
    SightingRequest,
    Sighting,
    BaselineRequest,
    BaselineResult,
    CrossFilterDimension,
    CrossFilterRequest,
)
