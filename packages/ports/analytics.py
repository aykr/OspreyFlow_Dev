"""`AnalyticsPort` — `docs/00_ARCHITECTURE.md` §2.2.

Columnar aggregation over event-shaped data: temporal histograms, geospatial
binning, baseline statistics, cross-filter counts. SQL, not traversal. Results
are Arrow tables end to end.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

import pyarrow

from schemas._pending_port_placeholders import (
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
    async def baseline(self, req: BaselineRequest) -> BaselineResult: ...
    async def cross_filter(self, req: CrossFilterRequest) -> dict[str, Histogram]: ...
    async def raw_sql(self, sql: str, params: Mapping[str, object]) -> pyarrow.Table: ...
