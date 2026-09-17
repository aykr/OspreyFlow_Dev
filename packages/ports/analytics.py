"""`AnalyticsPort` — `docs/00_ARCHITECTURE.md` §2.2, `docs/01_DOMAIN_MODEL.md` §9.

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
    EventRecord,
    GeoBin,
    GeoBinRequest,
    GeometryRecord,
    Histogram,
    HistogramRequest,
)
from schemas.domain import Principal


class AnalyticsPort(Protocol):
    async def histogram(self, req: HistogramRequest, principal: Principal) -> Histogram: ...
    async def geo_bins(self, req: GeoBinRequest, principal: Principal) -> list[GeoBin]: ...

    async def cross_filter(
        self, req: CrossFilterRequest, principal: Principal
    ) -> dict[str, Histogram]: ...

    async def baseline(self, req: BaselineRequest, principal: Principal) -> BaselineResult: ...

    # --- writes (07_BUILD_PLAN.md Phase 5) ----------------------------------
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
        """The "select an existing boundary" read path
        (`07_BUILD_PLAN.md`'s Phase 5 known-gaps list): every stored
        `GeometryKind.POLYGON` row at the resolved partition version — the
        server-backed counterpart to the transient, browser-only drawn-
        boundary filter (`apps/workspace/src/map/BoundaryFilterTool.tsx`).
        Access-filtered exactly like `get_geometry`/`get_geometries`: a
        boundary the given `principal` cannot view must not appear, count,
        or otherwise be detectable."""
        ...
