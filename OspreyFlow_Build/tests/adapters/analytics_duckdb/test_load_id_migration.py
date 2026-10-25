"""ADR-127 decision 6: a DuckDB analytics file made before events carried a `load_id` has the
`events` table without the column, and `CREATE TABLE IF NOT EXISTS` would leave it so — every later
`load_events` would then fail on the missing column. The Conduit runs `create_events_table` at every
start; it must bring such a file forward, keep its rows (read back with no load) and be a no-op on
a file that already has the column."""

from __future__ import annotations

from datetime import UTC, datetime

import duckdb

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import CREATE_EVENTS_TABLE, create_events_table
from ontology.handling import load_uk_le_scheme
from schemas.analytics import EventFilter, EventListRequest, EventRecord
from schemas.domain import Handling, Principal

READER = Principal(id="analyst", clearance="SECRET", org_unit="unit-1")
HANDLING = Handling(
    classification="OFFICIAL", handling_code="P", owning_unit="unit-1", originator="unit-1"
)


def _event(event_id: str, load_id: str | None = None) -> EventRecord:
    return EventRecord(
        event_id=event_id,
        edge_id="e1",
        edge_type="COMMUNICATED_WITH",
        source_id="a",
        target_id="b",
        occurred_at=datetime(2026, 1, 1, 12, tzinfo=UTC),
        investigation_scope="case-1",
        handling=HANDLING,
        load_id=load_id,
    )


def _old_file() -> duckdb.DuckDBPyConnection:
    """A file as the Conduit left it before this column: the current table, without `load_id`, and
    a row an earlier writer made."""
    con = duckdb.connect(":memory:")
    con.execute(CREATE_EVENTS_TABLE.replace(",\n    load_id VARCHAR", ""))
    columns = [r[1] for r in con.execute("PRAGMA table_info('events')").fetchall()]
    assert "load_id" not in columns
    con.execute(
        "INSERT INTO events VALUES ('old', 'e1', 'COMMUNICATED_WITH', 'a', 'b', "
        "'2026-01-01 12:00:00', NULL, NULL, NULL, NULL, NULL, '{}', 'case-1', 'OFFICIAL', 'P', "
        "'unit-1', 'unit-1')"
    )
    return con


async def test_an_old_file_gains_the_column_keeps_its_rows_and_takes_a_load() -> None:
    con = _old_file()
    create_events_table(con)
    adapter = AnalyticsDuckDBAdapter(con, load_uk_le_scheme())
    await adapter.load_events([_event("new", load_id="load-1")])
    page = await adapter.list_events(
        EventListRequest(filter=EventFilter(investigation_scope="case-1")), READER
    )
    assert {e.event_id: e.load_id for e in page.events} == {"old": None, "new": "load-1"}
    assert await adapter.retract_load("load-1") == 1
    page = await adapter.list_events(
        EventListRequest(filter=EventFilter(investigation_scope="case-1")), READER
    )
    assert [e.event_id for e in page.events] == ["old"]


def test_running_it_again_on_a_file_that_has_the_column_changes_nothing() -> None:
    con = duckdb.connect(":memory:")
    create_events_table(con)
    create_events_table(con)
    columns = [r[1] for r in con.execute("PRAGMA table_info('events')").fetchall()]
    assert columns.count("load_id") == 1
