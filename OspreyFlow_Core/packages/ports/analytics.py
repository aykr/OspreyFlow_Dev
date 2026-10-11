"""`AnalyticsPort` — `spec/00_ARCHITECTURE.md` §2.2, `spec/01_DOMAIN_MODEL.md` §9.

Columnar aggregation over event-shaped data: temporal histograms, geospatial
binning, baseline statistics, cross-filter counts. This is SQL, not
traversal. There is no `raw_sql` escape hatch, deliberately — an arbitrary
SQL string cannot be access-filtered, the same reason the Conduit never
accepts free-form Gremlin (ADR-003). Every method takes a `Principal`; the
adapter injects the filter into the `WHERE` clause before the query runs.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from schemas.analytics import (
    BaselineRequest,
    BaselineResult,
    CrossFilterRequest,
    EventListRequest,
    EventListResult,
    EventRecord,
    FirstSeenRequest,
    FirstSeenResult,
    GeoBin,
    GeoBinRequest,
    GeocodedEvent,
    GeocodeRequest,
    GeometryRecord,
    Histogram,
    HistogramRequest,
    Sighting,
    SightingRequest,
    TrendRequest,
    TrendResult,
)
from schemas.domain import Principal


class TrendLimitExceeded(Exception):
    """A trend past its bound (ADR-113 decision 2, rule 2): refused, never cut. `would_be` counts
    only what the reader could see, so the refusal discloses nothing."""

    def __init__(self, cap_kind: str, cap: int, would_be: int) -> None:
        super().__init__(f"the trend would have {would_be} {cap_kind}; the bound is {cap}")
        self.cap_kind, self.cap, self.would_be = cap_kind, cap, would_be


class AnalyticsPort(Protocol):
    async def histogram(self, req: HistogramRequest, principal: Principal) -> Histogram: ...
    async def geo_bins(self, req: GeoBinRequest, principal: Principal) -> list[GeoBin]: ...

    async def list_sightings(self, req: SightingRequest, principal: Principal) -> list[Sighting]:
        """Phase 8 Stage 4f's own addition, found missing while building B18's snail trail —
        a disclosed gap. Ordered by `occurred_at` ascending; a row with
        no `lat`/`lon` is excluded, the same `lat IS NOT NULL AND lon IS NOT NULL` filter
        `geo_bins` already applies."""
        ...

    async def geocode_events(
        self, req: GeocodeRequest, principal: Principal
    ) -> list[GeocodedEvent]:
        """**A1's "incidents geocode into cells" — owner rulings R9 (c) and R10, round 13cf.**
        The one containment method: which of `req.cells`' polygons covers each admitted event's
        point, recorded on the event as `properties[req.property]` and returned.
        `GeocodeRequest`'s docstring has the full contract: covering rather than strict, ties to
        the smallest ref, stale values cleared, and access applied to events and polygons alike.
        Ordered by `event_id`."""
        ...

    async def cross_filter(
        self, req: CrossFilterRequest, principal: Principal
    ) -> dict[str, Histogram]: ...

    async def baseline(self, req: BaselineRequest, principal: Principal) -> BaselineResult: ...

    async def list_events(self, req: EventListRequest, principal: Principal) -> EventListResult:
        """A page of the events the filter describes, newest first, with the total (ADR-089).
        Access control is in the query: a hidden event is neither listed nor counted."""
        ...

    async def trend(self, req: TrendRequest, principal: Principal) -> TrendResult:
        """Events per week or month, optionally split into series by a field, as a count or the
        sum of a numeric property (ADR-113). Access control is in the query: a hidden event moves no
        point, no total, no series and no classification. Past `max_periods` or `max_series` it
        raises `TrendLimitExceeded` — never a partial trend."""
        ...

    async def first_seen(self, req: FirstSeenRequest, principal: Principal) -> FirstSeenResult:
        """The earliest event in `req.filter` per node (either end) and per link (ADR-087). Access
        control is in the query: an event the principal may not see cannot pull a first appearance
        forward, so the answer equals the one over a corpus without that event."""
        ...

    # --- writes --------------------------------------------------------------
    #
    # Not principal-scoped writes: an ingest/gazetteer load is a backend
    # operation attributed by the caller's own audit trail (the connector or
    # recipe run), the same shape as `GraphPort.revert_elements` — never a
    # principal-scoped read. Reads take a `Principal` and are filtered by
    # `handling` exactly like every `EventFilter`-based method above.
    #
    # `load_events` mirrors `load_geometries` exactly, and exists for the
    # same reason: before this, nothing implementing `AnalyticsPort` had a
    # real write path for `EventRecord`s at all — every event that ever
    # reached a conformance test went through `analytics_duckdb/testing.py`'s
    # own bypass SQL, never the adapter or the port. `run_recipe`
    # (`services/ingest/engine.py`) already returns the `EventRecord`s a
    # load produced; this is what a caller now has to actually persist them
    # through, the same way `load_geometries` is.

    async def load_events(self, records: Sequence[EventRecord]) -> None: ...

    async def load_geometries(self, records: Sequence[GeometryRecord]) -> None: ...

    async def get_geometry(
        self, geometry_ref: str, principal: Principal, *, version: int | None = None
    ) -> GeometryRecord | None: ...

    async def get_geometries(
        self, geometry_refs: Sequence[str], principal: Principal, *, version: int | None = None
    ) -> list[GeometryRecord]: ...

    async def list_boundaries(
        self, principal: Principal, *, version: int | None = None
    ) -> list[GeometryRecord]:
        """The "select an existing boundary" read path,
        a disclosed gap: every stored
        `GeometryKind.POLYGON` row at the resolved partition version — the
        server-backed counterpart to the transient, browser-only drawn-
        boundary filter (`apps/workspace/src/map/BoundaryFilterTool.tsx`).
        Access-filtered exactly like `get_geometry`/`get_geometries`: a
        boundary the given `principal` cannot view must not appear, count,
        or otherwise be detectable."""
        ...
