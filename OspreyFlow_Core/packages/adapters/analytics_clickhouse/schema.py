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

On a cluster (`client.cluster`; `05_DEPLOYMENT.md` §3b) both tables are `ReplicatedMergeTree`, with
no arguments: the server's default Keeper path and its `{replica}` macro. The database they are made
in is `Replicated` (`services/api/analytics_store.py`), which carries each definition to every node;
a plain `MergeTree` there would keep its rows on the node that took them.

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


def create_database(database: str, cluster: str | None) -> str:
    """On a cluster the database is made on every node at once (`ON CLUSTER`) and is `Replicated`,
    so each table definition reaches every node through Keeper."""
    if cluster is None:
        return f"CREATE DATABASE IF NOT EXISTS {database}"
    return (
        f"CREATE DATABASE IF NOT EXISTS {database} ON CLUSTER {cluster} ENGINE = "
        f"Replicated('/clickhouse/databases/{database}', '{{shard}}', '{{replica}}')"
    )


def drop_database(database: str, cluster: str | None) -> str:
    """From every node, on a cluster: dropped from one, the others would keep it."""
    on = f" ON CLUSTER {cluster}" if cluster else ""
    return f"DROP DATABASE IF EXISTS {database}{on}" + (" SYNC" if cluster else "")


async def create_tables(client: ClickHouseClient) -> None:
    for statement in (CREATE_EVENTS_TABLE, CREATE_GEOMETRIES_TABLE):
        if client.cluster:
            statement = statement.replace("ENGINE = MergeTree", "ENGINE = ReplicatedMergeTree")
        await client.command(statement)
