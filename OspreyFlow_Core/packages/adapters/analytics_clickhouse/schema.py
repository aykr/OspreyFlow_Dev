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
    originator String,
    load_id Nullable(String)
) ENGINE = MergeTree
PARTITION BY (investigation_scope, toYYYYMM(occurred_at))
ORDER BY (edge_id, occurred_at)
"""

#: A store made before `load_id` existed has `events` without it, and `CREATE TABLE IF NOT EXISTS`
#: leaves it so. `create_tables` adds the column to such a store, and only to such a store
#: (ADR-127 decision 6): on a `Replicated` database even a no-op `ALTER` goes through the replicated
#: DDL queue and can block while a replica is down, and this runs at every start, so
#: `system.columns` is asked first. On a cluster the change reaches every node.
ADD_EVENTS_LOAD_ID = "ALTER TABLE events ADD COLUMN IF NOT EXISTS load_id Nullable(String)"

#: The columns of an event, named, so a move between `events` and `withdrawn_events` never rests on
#: the order a store's columns were added in.
EVENT_COLUMNS = (
    "event_id, edge_id, edge_type, source_id, target_id, occurred_at, duration_s, cell_site, lat, "
    "lon, direction, properties, investigation_scope, handling_classification, handling_code, "
    "owning_unit, originator, load_id"
)

#: ADR-110 Amendment 8 point 1: the events of links a full snapshot withdrew, set aside with the
#: withdrawing load so its revert can put back exactly those. No read touches this table.
CREATE_WITHDRAWN_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS withdrawn_events (
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
    originator String,
    load_id Nullable(String),
    withdrawn_by_load String
) ENGINE = MergeTree
ORDER BY (withdrawn_by_load, edge_id)
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


#: ADR-134 decision 3: the DuckDB store's alert facts, column for column
#: (`adapters/analytics_duckdb/schema.py` has why). A `MergeTree` keeps no uniqueness, so
#: `load_alert_facts` deletes an alert's rows (a waited-for mutation) before it writes them again.
CREATE_ALERT_FACTS_TABLE = """
CREATE TABLE IF NOT EXISTS alert_facts (
    alert_id String,
    investigation_scope Nullable(String),
    kind String,
    rule String,
    typology Nullable(String),
    severity String,
    outcome String,
    raised_at DateTime64(6, 'UTC'),
    owner_id String,
    audience String,
    team Nullable(String),
    dataset_id Nullable(String),
    known UInt8,
    fact_id String DEFAULT alert_id
) ENGINE = MergeTree ORDER BY (alert_id)
"""

CREATE_ALERT_FACT_HANDLINGS_TABLE = """
CREATE TABLE IF NOT EXISTS alert_fact_handlings (
    alert_id String,
    handling_classification String,
    handling_code String,
    owning_unit String,
    originator String,
    fact_id String DEFAULT alert_id,
    grp UInt8 DEFAULT 0
) ENGINE = MergeTree ORDER BY (alert_id)
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


#: ADR-146 Amendment 7 (the orchestrator's review, item 6), as the DuckDB store's
#: (`adapters/analytics_duckdb/schema.py`): an alert with citations kept as one row per set of
#: them, each citation outside the set a group of handling rows. A new store is made with them; one
#: made before them is brought forward, reading its one row per alert as its own set, group 0. Each
#: `ALTER` only where `system.columns` finds its column missing, as `load_id`'s (ADR-127 decision 6:
#: a no-op `ALTER` on a `Replicated` database still goes through the DDL queue, at every start).
ADD_ALERT_FACT_SETS = (
    ("alert_facts", "fact_id",
     "ALTER TABLE alert_facts ADD COLUMN IF NOT EXISTS fact_id String DEFAULT alert_id"),
    ("alert_fact_handlings", "fact_id",
     "ALTER TABLE alert_fact_handlings ADD COLUMN IF NOT EXISTS fact_id String DEFAULT alert_id"),
    ("alert_fact_handlings", "grp",
     "ALTER TABLE alert_fact_handlings ADD COLUMN IF NOT EXISTS grp UInt8 DEFAULT 0"),
)  # fmt: skip


async def _has_column(client: ClickHouseClient, table: str, column: str) -> bool:
    (present,) = await client.rows(
        "SELECT count() FROM system.columns WHERE database = ? AND table = ? AND name = ?",
        [client.database, table, column],
    )
    return int(present[0]) > 0


async def create_tables(client: ClickHouseClient) -> None:
    for statement in (
        CREATE_EVENTS_TABLE,
        CREATE_WITHDRAWN_EVENTS_TABLE,
        CREATE_GEOMETRIES_TABLE,
        CREATE_ALERT_FACTS_TABLE,
        CREATE_ALERT_FACT_HANDLINGS_TABLE,
    ):
        if client.cluster:
            statement = statement.replace("ENGINE = MergeTree", "ENGINE = ReplicatedMergeTree")
        await client.command(statement)
    (present,) = await client.rows(
        "SELECT count() FROM system.columns "
        "WHERE database = ? AND table = 'events' AND name = 'load_id'",
        [client.database],
    )
    if int(present[0]) == 0:
        await client.command(ADD_EVENTS_LOAD_ID)
    for table, column, statement in ADD_ALERT_FACT_SETS:
        if not await _has_column(client, table, column):
            await client.command(statement)
