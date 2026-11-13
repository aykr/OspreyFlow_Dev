"""The analytics store a seed writes its events to: the deployment's own, as the Conduit opens it.

A seed that opened DuckDB by path whatever the deployment named wrote its events where no Conduit
reads them on a deployment whose `components.analytics_engine` is ClickHouse (every
`cloud-platform` one, and a local one set so): the graph half arrived, the events half went to a
file in the seed's own container and was lost with it, and the seed said "loaded" (rule 2). So the
store is the one `OSPREY_ANALYTICS_ENGINE` names, opened by `services.api.analytics_store`, the
Conduit's own opener: DuckDB at the path given, ClickHouse from its `CLICKHOUSE_*` settings, and an
engine it does not know refused in words (ADR-148 Amendment 14, the POC seed path).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from services.api import analytics_store

from ontology.handling import HandlingScheme
from ports.analytics import AnalyticsPort


@asynccontextmanager
async def seed_analytics(duckdb_path: str, scheme: HandlingScheme) -> AsyncIterator[AnalyticsPort]:
    """The deployment's analytics store, closed afterwards (`duckdb_path` is DuckDB's alone)."""
    engine = os.environ.get("OSPREY_ANALYTICS_ENGINE", "duckdb")
    analytics, close = await analytics_store.open_analytics(
        engine, duckdb_path=duckdb_path, handling_scheme=scheme
    )
    try:
        yield analytics
    finally:
        await close()
