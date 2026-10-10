"""An event's time is the instant it was loaded with, whatever zone the machine is in.

Found building ADR-109 phase A (10 October 2026): the events table's `occurred_at` is a plain
`TIMESTAMP`, and DuckDB turned an aware UTC time into the connection's local time on insert, while
the read marked what came back as UTC — so on a machine an hour off UTC (this Mac in BST) every
event read back an hour late. The deployment's containers run in UTC, which hid it there; a rule
comparing a load's in-memory events with the same events read back saw two transactions an hour
apart. The adapter now fixes its connection's zone to UTC. The test sets a zone well away from UTC
first, so it fails on any machine, not only one in BST.
"""

from __future__ import annotations

from datetime import UTC, datetime

import duckdb

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table
from ontology.handling import load_uk_le_scheme
from schemas.analytics import EventFilter, EventListRequest, EventRecord
from schemas.domain import Handling, Interval, Principal

READER = Principal(id="p", clearance="OFFICIAL", org_unit="u")
AT = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


async def test_an_event_reads_back_at_the_instant_it_was_loaded() -> None:
    con = duckdb.connect(":memory:")
    con.execute("SET TimeZone = 'America/New_York'")
    create_events_table(con)
    adapter = AnalyticsDuckDBAdapter(con, load_uk_le_scheme())
    await adapter.load_events(
        [
            EventRecord(
                event_id="e1", edge_id="x", edge_type="TRANSACTED", source_id="a",
                target_id="b", occurred_at=AT, investigation_scope="case",
                handling=Handling(classification="OFFICIAL", handling_code="P",
                                  originator="u", owning_unit="u"),
            )  # fmt: skip
        ]
    )
    listed = await adapter.list_events(
        EventListRequest(filter=EventFilter(investigation_scope="case")), READER
    )
    assert [e.occurred_at for e in listed.events] == [AT]

    # A window drawn tight around the instant still finds it: the filter and the stored value
    # are read in the same zone.
    windowed = await adapter.list_events(
        EventListRequest(
            filter=EventFilter(investigation_scope="case", window=Interval(valid_from=AT, valid_to=AT))
        ),
        READER,
    )
    assert windowed.total == 1
