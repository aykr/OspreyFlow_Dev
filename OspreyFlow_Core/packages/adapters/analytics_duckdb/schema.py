"""Table DDL for the analytics store — `01_DOMAIN_MODEL.md` §3's per-event
row, flattened for DuckDB: the `(event_id, edge_id, source_id, target_id,
ts, duration, cell_site, lat, lon, direction, properties)` tuple, plus
`investigation_scope` and the flattened `Handling` fields the access
filter runs against; and `geometries`, the reference partition
`03_CONDUIT_MIDDLEWARE.md` §5.1 and `schemas/analytics.py`'s
`GeometryRecord` describe — a `Location` node's `geometry_ref` points at
a row here, never carries the coordinates itself.

Both `IF NOT EXISTS` — a conformance test's `:memory:` connection never has
either table already, but the Conduit's own persistent DuckDB file
(`services/api/app.py`'s lifespan, Phase 5 Checkpoint 2) does from its
second startup onward, and re-running this DDL against it must be a
no-op, not an error.

**`geometries.geometry` (Phase 5's known-gaps closure) is a real DuckDB `GEOMETRY` column, via
the `spatial` extension.** `load_extension` fetches the extension binary
over the network on first install unless it is already vendored/cached —
in tension with this platform's air-gapped posture — so a deployment
image must pre-install it at build time (`services/api/Dockerfile`) rather
than relying on `INSTALL` succeeding at runtime with no network reachable.
`load_extension` here is idempotent and side-effect-free once installed;
it is not itself what triggers a network fetch."""

from __future__ import annotations

import duckdb


def load_spatial_extension(con: duckdb.DuckDBPyConnection) -> None:
    """Shared with `services/api/prefetch.py`, which needs the same
    `ST_*` functions over a `GeometryRecord.geometry_wkb` it already
    fetched through `AnalyticsPort`, not a second table of its own."""
    con.install_extension("spatial")
    con.load_extension("spatial")


CREATE_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS events (
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
    originator VARCHAR,
    load_id VARCHAR
)
"""

#: A store made before `load_id` existed has the table without it, and `CREATE TABLE IF NOT EXISTS`
#: leaves it so. Run at every start, after the create, this adds the column to such a store and
#: does nothing to a store that has it (ADR-127 decision 6).
ADD_EVENTS_LOAD_ID = "ALTER TABLE events ADD COLUMN IF NOT EXISTS load_id VARCHAR"

#: No `investigation_scope` column — `GeometryRecord`'s own docstring
#: records why: reference data is versioned as a whole rather than scoped
#: per investigation. `handling_*` mirrors `events`' flattening exactly, so
#: `access_filter.py`'s predicate runs unchanged against either table. The
#: primary key is `(geometry_ref, version)`, not `geometry_ref` alone — a
#: gazetteer refresh loads a new version without deleting the old one, so
#: the same ref legitimately has one row per version it has ever appeared
#: in.
#: `kind`/`geometry` added in Phase 5's known-gaps closure: `kind` discriminates `point`/`polygon`
#: (`schemas.analytics.GeometryKind`); `geometry` is `NULL` for a point row
#: (which keeps carrying `lon`/`lat` as before) and a real `GEOMETRY` value
#: — written via `ST_GeomFromWKB`, read back via `ST_AsWKB` — for a polygon
#: row, which carries no `lon`/`lat`.
CREATE_GEOMETRIES_TABLE = """
CREATE TABLE IF NOT EXISTS geometries (
    geometry_ref VARCHAR,
    version INTEGER,
    kind VARCHAR,
    lon DOUBLE,
    lat DOUBLE,
    source_crs VARCHAR,
    source_x DOUBLE,
    source_y DOUBLE,
    geometry GEOMETRY,
    handling_classification VARCHAR,
    handling_code VARCHAR,
    owning_unit VARCHAR,
    originator VARCHAR,
    PRIMARY KEY (geometry_ref, version)
)
"""


def create_events_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(CREATE_EVENTS_TABLE)
    con.execute(ADD_EVENTS_LOAD_ID)


def create_geometries_table(con: duckdb.DuckDBPyConnection) -> None:
    load_spatial_extension(con)
    con.execute(CREATE_GEOMETRIES_TABLE)
