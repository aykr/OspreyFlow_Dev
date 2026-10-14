"""The analytics store the deployment names (`components.analytics_engine`, carried to the Conduit
as `OSPREY_ANALYTICS_ENGINE`; ADR-114 decision 9), opened once at start by the Conduit and by the
prefetch job alike, so the two can never read different stores.

An engine this does not know is refused in words. Falling back to DuckDB would be the worst
failure available: on a cluster each Conduit replica would keep its own in-process events, and
each analyst would see whichever replica answered.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from pathlib import Path

import duckdb

from adapters.analytics_clickhouse.adapter import AnalyticsClickHouseAdapter
from adapters.analytics_clickhouse.client import ClickHouseClient, ClickHouseSettings
from adapters.analytics_clickhouse.schema import create_database, create_tables
from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table, create_geometries_table
from ontology.handling import HandlingScheme
from ports.analytics import AnalyticsPort

ENGINES = ("duckdb", "clickhouse")

#: The deployment's own ClickHouse database, unless `CLICKHOUSE_DATABASE` names another.
CLICKHOUSE_DATABASE = "ospreyflow"

Close = Callable[[], Awaitable[None]]


class UnknownAnalyticsEngine(ValueError):
    def __init__(self, engine: str) -> None:
        super().__init__(
            f"components.analytics_engine {engine!r} is not one this Conduit can open "
            f"(it knows {', '.join(ENGINES)})"
        )


async def open_analytics(
    engine: str, *, duckdb_path: str, handling_scheme: HandlingScheme
) -> tuple[AnalyticsPort, Close]:
    """The adapter, and how to close it. Tables are made if missing, so a first start and every
    later one are the same step."""
    if engine == "duckdb":
        # A persistent file, its parent made if missing (`services/api/config.py`'s comment on
        # `analytics_db_path` has why it is not yet Parquet in object storage).
        Path(duckdb_path).parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(duckdb_path)
        create_events_table(con)
        create_geometries_table(con)

        async def close_duckdb() -> None:
            con.close()

        return AnalyticsDuckDBAdapter(con, handling_scheme), close_duckdb
    if engine == "clickhouse":
        client = ClickHouseClient(ClickHouseSettings.from_env(CLICKHOUSE_DATABASE))
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", client.database):
            # The one name written into a statement rather than sent as a parameter.
            await client.aclose()
            raise ValueError(f"CLICKHOUSE_DATABASE {client.database!r} is not a plain name")
        if client.cluster is not None and not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*", client.cluster
        ):
            await client.aclose()
            raise ValueError(f"CLICKHOUSE_CLUSTER {client.cluster!r} is not a plain name")
        await client.command(create_database(client.database, client.cluster), database=None)
        await create_tables(client)
        return AnalyticsClickHouseAdapter(client, handling_scheme), client.aclose
    raise UnknownAnalyticsEngine(engine)

