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

from adapters.analytics_clickhouse.schema import (
    ADD_ALERT_FACT_SETS,
    CREATE_ALERT_FACT_HANDLINGS_TABLE,
    CREATE_ALERT_FACTS_TABLE,
    CREATE_EVENTS_TABLE,
    create_tables,
)


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
        table, column = str(params[1]), str(params[2])  # each column asked about by name
        return [[1 if column in self.tables.get(table, set()) else 0]]

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
        seen.append(params[0])  # the database each question asks about
        return await real_rows(sql, params)

    client.rows = rows  # type: ignore[method-assign]
    await create_tables(client)  # type: ignore[arg-type]
    assert seen and set(seen) == {"osprey"}
    assert len(client.alters()) == 1


def _columns(create: str, *dropped: str) -> set[str]:
    body = create[create.index("(") + 1 : create.rindex(") ENGINE")]
    return {line.split()[0].rstrip(",") for line in body.splitlines() if line.strip()} - set(dropped)


async def test_a_store_made_before_the_alert_facts_sets_issues_their_three_alters_once() -> None:
    """ADR-146 Amendment 7 (the orchestrator's review, item 6): `fact_id` and `grp` added to a store
    made before them, each only where it is missing, and nothing at the next start. Red with the
    `ALTER`s issued unasked (the gate at 3511480: a store that had them altered at every start)."""
    client = RecordingClient({
        "events": _columns(CREATE_EVENTS_TABLE),
        "alert_facts": _columns(CREATE_ALERT_FACTS_TABLE, "fact_id"),
        "alert_fact_handlings": _columns(CREATE_ALERT_FACT_HANDLINGS_TABLE, "fact_id", "grp"),
    })  # fmt: skip
    await create_tables(client)  # type: ignore[arg-type]
    assert client.alters() == [statement for _, _, statement in ADD_ALERT_FACT_SETS]
    assert {"fact_id", "grp"} <= client.tables["alert_fact_handlings"]
    await create_tables(client)  # type: ignore[arg-type]
    assert len(client.alters()) == 3, "the second start finds the columns and asks for nothing"
