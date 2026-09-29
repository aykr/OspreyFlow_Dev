"""Test-only database lifecycle for the `AnalyticsPort` conformance suite.

Not used by production code — the Conduit's own persistent DuckDB file is
opened in `services/api/app.py`'s lifespan instead (Phase 5 Checkpoint 2).
Every conformance test gets its own in-memory DuckDB connection, seeded
directly from a list of `EventRecord` fixtures, mirroring
`adapters/graph_arcadedb/testing.py`'s per-test-database pattern.

Seeds through the adapter's own `load_events` — not a raw-SQL bypass — the
same discipline `load_geometries` already established: a conformance test
exercises the real write path, so a bug in it would be caught here too, not
only in `load_events`'s own dedicated tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

import duckdb

from ontology.handling import HandlingScheme
from schemas.analytics import EventRecord

from .adapter import AnalyticsDuckDBAdapter
from .schema import create_events_table, create_geometries_table


@asynccontextmanager
async def duckdb_adapter(
    events: Sequence[EventRecord],
    handling_scheme: HandlingScheme,
) -> AsyncIterator[AnalyticsDuckDBAdapter]:
    con = duckdb.connect(":memory:")
    try:
        create_events_table(con)
        create_geometries_table(con)
        adapter = AnalyticsDuckDBAdapter(con, handling_scheme)
        await adapter.load_events(events)
        yield adapter
    finally:
        con.close()
