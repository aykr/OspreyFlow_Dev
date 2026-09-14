"""Table DDL for the analytics store — `01_DOMAIN_MODEL.md` §3's per-event
row, flattened for DuckDB: the `(event_id, edge_id, source_id, target_id,
ts, duration, cell_site, lat, lon, direction, properties)` tuple, plus
`investigation_scope` and the flattened `Handling` fields the access
filter runs against; and `geometries`, the reference partition
`03_CONDUIT_MIDDLEWARE.md` §5.1 and `schemas/analytics.py`'s
`GeometryRecord` describe — a `Location` node's `geometry_ref` points at
a row here, never carries the coordinates itself.
"""

from __future__ import annotations

import duckdb

CREATE_EVENTS_TABLE = """
CREATE TABLE events (
    event_id VARCHAR,
    edge_id VARCHAR,
    edge_type VARCHAR,
    source_id VARCHAR,
    target_id VARCHAR,
    occurred_at TIMESTAMP,
    duration_s DOUBLE,
    cell_site VARCHAR,
    lat DOUBLE,
    lon DOUBLE,
    direction VARCHAR,
    properties JSON,
    investigation_scope VARCHAR,
    handling_classification VARCHAR,
    handling_code VARCHAR,
    owning_unit VARCHAR,
    originator VARCHAR
)
"""

#: No `investigation_scope`/handling columns — `GeometryRecord`'s own
#: docstring records why: reference data is versioned as a whole, and the
#: full access-control story for this partition is Phase 5 scope.
CREATE_GEOMETRIES_TABLE = """
CREATE TABLE geometries (
    geometry_ref VARCHAR PRIMARY KEY,
    lon DOUBLE,
    lat DOUBLE,
    source_crs VARCHAR,
    source_x DOUBLE,
    source_y DOUBLE
)
"""


def create_events_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(CREATE_EVENTS_TABLE)


def create_geometries_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(CREATE_GEOMETRIES_TABLE)
