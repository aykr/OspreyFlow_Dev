"""Table DDL for the ClickHouse analytics store — the DuckDB store's two tables, column for column
(`adapters/analytics_duckdb/schema.py` has why each exists), in ClickHouse's types.

Two differences, both forced by the engine:

- `properties` is a `String` holding JSON, read with `JSONType`/`JSONExtract*` (the adapter's
  `_field_expression`), as DuckDB's `JSON` column is read with `json_extract_string`.
- A polygon has no `GEOMETRY` type here. Its WKB is kept as given (`wkb_hex`, so a read returns
  the same bytes it was given) and, beside it, the same shape as a MultiPolygon (`multi_wkb_hex`),
  which `readWKBMultiPolygon` turns into the rings `pointInPolygon` tests — one reader for both
  shapes, so no query has to branch on which one a row holds.

`MergeTree` keeps no primary-key uniqueness: `(geometry_ref, version)` orders the table but does
not refuse a repeat, where DuckDB's key does. A gazetteer load writes each version once
(`GeometryRecord`'s own docstring), so nothing relies on the refusal.

`events` is partitioned and ordered as `04_VAULT_BACKEND.md` §2 says: by `(investigation_scope,
month)`, and by `(edge_id, timestamp)` within a partition.
"""

from __future__ import annotations

from .client import ClickHouseClient

CREATE_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    event_id String,
    edge_id String,
    edge_type String,
    source_id String,
    target_id String,
    occurred_at DateTime64(6, 'UTC'),
    duration_s Nullable(Float64),
    cell_site Nullable(String),
    lat Nullable(Float64),
    lon Nullable(Float64),
    direction Nullable(String),
    properties String,
    investigation_scope String,
    handling_classification String,
    handling_code String,
    owning_unit String,
    originator String
) ENGINE = MergeTree
PARTITION BY (investigation_scope, toYYYYMM(occurred_at))
ORDER BY (edge_id, occurred_at)
"""

CREATE_GEOMETRIES_TABLE = """
CREATE TABLE IF NOT EXISTS geometries (
    geometry_ref String,
    version Int32,
    kind String,
    lon Nullable(Float64),
    lat Nullable(Float64),
    source_crs Nullable(String),
    source_x Nullable(Float64),
    source_y Nullable(Float64),
    wkb_hex Nullable(String),
    multi_wkb_hex Nullable(String),
    handling_classification String,
    handling_code String,
    owning_unit String,
    originator String
) ENGINE = MergeTree ORDER BY (geometry_ref, version)
"""


async def create_tables(client: ClickHouseClient) -> None:
    await client.command(CREATE_EVENTS_TABLE)
    await client.command(CREATE_GEOMETRIES_TABLE)
