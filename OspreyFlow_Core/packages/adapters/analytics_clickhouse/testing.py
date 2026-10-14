"""Test-only database lifecycle for the `AnalyticsPort` conformance suite: a database of its own per
test on a live ClickHouse (`CLICKHOUSE_HTTP_PORT`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`),
dropped afterwards, seeded through the adapter's own `load_events` — the same discipline as
`adapters/analytics_duckdb/testing.py`, against the real server rather than a fake of it."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from ulid import ULID

from ontology.handling import HandlingScheme
from schemas.analytics import EventRecord

from .adapter import AnalyticsClickHouseAdapter
from .client import ClickHouseClient, ClickHouseSettings
from .schema import create_database, create_tables, drop_database


@asynccontextmanager
async def clickhouse_adapter(
    events: Sequence[EventRecord],
    handling_scheme: HandlingScheme,
) -> AsyncIterator[AnalyticsClickHouseAdapter]:
    database = f"conformance_{str(ULID()).lower()}"
    client = ClickHouseClient(ClickHouseSettings.from_env(database))
    await client.command(create_database(database, client.cluster), database=None)
    try:
        await create_tables(client)
        adapter = AnalyticsClickHouseAdapter(client, handling_scheme)
        await adapter.load_events(events)
        yield adapter
    finally:
        await client.command(drop_database(database, client.cluster), database=None)
        await client.aclose()
