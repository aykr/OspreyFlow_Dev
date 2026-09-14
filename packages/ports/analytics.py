"""`AnalyticsPort` — `docs/00_ARCHITECTURE.md` §2.2, `docs/01_DOMAIN_MODEL.md` §9.

Columnar aggregation over event-shaped data: temporal histograms, geospatial
binning, baseline statistics, cross-filter counts. This is SQL, not
traversal. There is no `raw_sql` escape hatch, deliberately — an arbitrary
SQL string cannot be access-filtered, the same reason the Conduit never
accepts free-form Gremlin (ADR-003). Every method takes a `Principal`; the
adapter injects the filter into the `WHERE` clause before the query runs.
"""

from __future__ import annotations

from typing import Protocol

from schemas.analytics import (
    BaselineRequest,
    BaselineResult,
    CrossFilterRequest,
    GeoBin,
    GeoBinRequest,
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
