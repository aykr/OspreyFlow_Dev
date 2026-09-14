"""Test-only database lifecycle for the `AnalyticsPort` conformance suite.

Not used by production code — the Conduit is configured against Parquet in
object storage (`docs/07_BUILD_PLAN.md` Phase 2). Every conformance test
gets its own in-memory DuckDB connection, seeded directly from a list of
`EventRecord` fixtures, mirroring
`adapters/graph_arcadedb/testing.py`'s per-test-database pattern. Also
seeds `geometries` (`schemas/analytics.py`'s `GeometryRecord`) the same
way, and `read_geometry` is a plain lookup for test assertions — there is
no `AnalyticsPort` method for it yet, deliberately: the reference
partition's real read path, with its own access control, is Phase 5 scope
(`GeometryRecord`'s own docstring).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

import duckdb

from ontology.handling import HandlingScheme
from schemas.analytics import EventRecord, GeometryRecord

from .adapter import AnalyticsDuckDBAdapter
from .schema import create_events_table, create_geometries_table

_INSERT_EVENT = """
INSERT INTO events (
    event_id, edge_id, edge_type, source_id, target_id, occurred_at, duration_s,
    cell_site, lat, lon, direction, properties, investigation_scope,
    handling_classification, handling_code, owning_unit, originator
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERT_GEOMETRY = """
INSERT INTO geometries (geometry_ref, lon, lat, source_crs, source_x, source_y)
VALUES (?, ?, ?, ?, ?, ?)
"""


def _event_row(event: EventRecord) -> list[object]:
    return [
        event.event_id,
        event.edge_id,
        event.edge_type,
        event.source_id,
        event.target_id,
        event.occurred_at,
        event.duration_s,
        event.cell_site,
        event.lat,
        event.lon,
        event.direction,
        json.dumps(event.properties),
        event.investigation_scope,
        event.handling.classification,
        event.handling.handling_code,
        event.handling.owning_unit,
        event.handling.originator,
    ]


def _geometry_row(geometry: GeometryRecord) -> list[object]:
    return [
        geometry.geometry_ref,
        geometry.lon,
        geometry.lat,
        geometry.source_crs,
        geometry.source_x,
        geometry.source_y,
    ]


@asynccontextmanager
async def duckdb_adapter(
    events: Sequence[EventRecord],
    handling_scheme: HandlingScheme,
    *,
    geometries: Sequence[GeometryRecord] = (),
) -> AsyncIterator[AnalyticsDuckDBAdapter]:
    con = duckdb.connect(":memory:")
    try:
        create_events_table(con)
        create_geometries_table(con)
        if events:
            con.executemany(_INSERT_EVENT, [_event_row(e) for e in events])
        if geometries:
            con.executemany(_INSERT_GEOMETRY, [_geometry_row(g) for g in geometries])
        yield AnalyticsDuckDBAdapter(con, handling_scheme)
    finally:
        con.close()


def read_geometry(adapter: AnalyticsDuckDBAdapter, geometry_ref: str) -> GeometryRecord | None:
    row = adapter._con.execute(  # noqa: SLF001 — test-only lookup, no port method exists yet
        "SELECT geometry_ref, lon, lat, source_crs, source_x, source_y "
        "FROM geometries WHERE geometry_ref = ?",
        [geometry_ref],
    ).fetchone()
    if row is None:
        return None
    return GeometryRecord(
        geometry_ref=row[0], lon=row[1], lat=row[2], source_crs=row[3], source_x=row[4],
        source_y=row[5],
    )
