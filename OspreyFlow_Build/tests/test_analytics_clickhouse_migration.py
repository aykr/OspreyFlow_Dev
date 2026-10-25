"""ADR-127 decision 6: `create_tables` brings a ClickHouse store made before events carried a
`load_id` forward, and does so *only when the column is missing*. On a `Replicated` database even
a no-op `ALTER` goes through the replicated DDL queue and can block while a replica is down, and
`create_tables` runs at every Conduit start, so it asks `system.columns` first.

A recording fake stands in for the client (pure: no server). It refuses what the real one does that
matters here: a `CREATE TABLE IF NOT EXISTS` leaves an existing table as it was, so an old store
stays without the column until an `ALTER` adds it; and `system.columns` answers for the database
asked about, not for any other. The live counterpart, against a real server and an old-shaped
table, is `test_analytics_clickhouse.py`."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from adapters.analytics_clickhouse.schema import CREATE_EVENTS_TABLE, create_tables


class RecordingClient:
    """The slice of `ClickHouseClient` `create_tables` uses, over a dict of table to columns."""

    def __init__(self, tables: dict[str, set[str]] | None = None, database: str = "osprey") -> None:
        self.database = database
        self.cluster: str | None = None
        self.tables = tables if tables is not None else {}
        self.statements: list[str] = []

    async def command(self, sql: str, params: Sequence[object] = (), *, database: str | None = "") -> None:
        self.statements.append(sql)
        text = " ".join(sql.split())
        if text.startswith("CREATE TABLE IF NOT EXISTS"):
            name = text.split()[5]
            if name not in self.tables:  # an existing table is left as it was
                body = sql[sql.index("(") + 1 : sql.rindex(") ENGINE")]
                self.tables[name] = {line.split()[0] for line in body.splitlines() if line.strip()}
        elif text.startswith("ALTER TABLE") and "ADD COLUMN IF NOT EXISTS" in text:
            parts = text.split()
            self.tables[parts[2]].add(parts[parts.index("EXISTS") + 1])

    async def rows(self, sql: str, params: Sequence[object] = ()) -> list[list[Any]]:
        self.statements.append(sql)
        assert "system.columns" in sql
        asked = params[0]
        if asked != self.database:
            return [[0]]
        wanted = [column for column in ("load_id",) if f"'{column}'" in sql]
        present = self.tables.get("events", set())
        return [[sum(1 for c in wanted if c in present)]]

    def alters(self) -> list[str]:
        return [s for s in self.statements if s.lstrip().startswith("ALTER")]


def _old_events() -> dict[str, set[str]]:
    old = CREATE_EVENTS_TABLE.replace(",\n    load_id Nullable(String)", "")
    body = old[old.index("(") + 1 : old.rindex(") ENGINE")]
    return {"events": {line.split()[0] for line in body.splitlines() if line.strip()}}


async def test_a_new_store_is_made_with_the_column_and_issues_no_alter() -> None:
    client = RecordingClient()
    await create_tables(client)  # type: ignore[arg-type]
    assert "load_id" in client.tables["events"]
    assert client.alters() == []


async def test_a_store_that_has_the_column_issues_no_alter_however_often_it_starts() -> None:
    client = RecordingClient()
    for _ in range(3):
        await create_tables(client)  # type: ignore[arg-type]
    assert client.alters() == []


async def test_an_old_store_issues_exactly_one_alter_and_then_none() -> None:
    client = RecordingClient(_old_events())
    assert "load_id" not in client.tables["events"]
    await create_tables(client)  # type: ignore[arg-type]
    assert len(client.alters()) == 1
    assert "load_id" in client.tables["events"]
    await create_tables(client)  # type: ignore[arg-type]
    assert len(client.alters()) == 1, "the second start finds the column and asks for nothing"


async def test_the_column_is_looked_for_in_the_clients_own_database() -> None:
    """A `load_id` column on another database's table must not make this store skip its `ALTER`."""
    client = RecordingClient(_old_events(), database="osprey")
    seen: list[object] = []
    real_rows = client.rows

    async def rows(sql: str, params: Sequence[object] = ()) -> list[list[Any]]:
        seen.extend(params)
        return await real_rows(sql, params)

    client.rows = rows  # type: ignore[method-assign]
    await create_tables(client)  # type: ignore[arg-type]
    assert seen == ["osprey"]
    assert len(client.alters()) == 1
