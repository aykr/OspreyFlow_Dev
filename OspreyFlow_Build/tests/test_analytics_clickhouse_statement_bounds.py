"""ADR-110 Amendment 15's statement bound, on ClickHouse: setting a refresh's events aside and
restoring them sends no statement that grows with the events moved, or with the tables they move
between. Each statement the adapter sends is recorded. No list parameter may hold more than one
chunk, and every `NOT IN` subquery must be limited to the chunk's own ids. A subquery over a whole
table is the shape the methods had before (red so, `process/lanes/studio/L1.2a_RED_RECORD.md`).

The recording client binds each statement with the real client's `bind`, so it refuses a
placeholder count the real one refuses (rule 15). What ClickHouse itself returns is the conformance
suite's to prove (`tests/conformance/analytics_port/test_suite.py`, against a real ClickHouse)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from adapters.analytics_clickhouse.adapter import (
    _WITHDRAW_CHUNK,
    AnalyticsClickHouseAdapter,
)
from adapters.analytics_clickhouse.client import bind
from ontology.handling import load_uk_le_scheme

IDS = [f"ev-{n:05d}" for n in range(2_500)]
LOAD = "load-refresh"


class Recording:
    """Stands in for `ClickHouseClient`: every statement kept with its values; `events` and
    `withdrawn_events` held as id sets so the counts and pages the adapter reads are real."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, list[object]]] = []
        self.events: set[str] = set(IDS)
        self.withdrawn: set[str] = set()

    def _keep(self, sql: str, params: Sequence[object]) -> None:
        bind(sql, params)  # refuses a placeholder count the real client refuses
        self.sent.append((sql, list(params)))

    async def command(self, sql: str, params: Sequence[object] = ()) -> None:
        self._keep(sql, params)
        ids = next((p for p in params if isinstance(p, list)), [])
        if sql.startswith("INSERT INTO withdrawn_events"):
            self.withdrawn |= set(ids) & self.events
        elif sql.startswith("ALTER TABLE events DELETE"):
            self.events -= set(ids)
        elif sql.startswith("INSERT INTO events"):
            # By the load alone when no ids are named (the shape before the bound), else those ids.
            self.events |= (set(ids) if ids else self.withdrawn) & self.withdrawn
        elif sql.startswith("ALTER TABLE withdrawn_events DELETE"):
            self.withdrawn.clear()

    async def rows(self, sql: str, params: Sequence[object] = ()) -> list[list[Any]]:
        self._keep(sql, params)
        if sql.startswith("SELECT count() FROM events WHERE has("):
            return [[len(set(params[0]) & self.events)]]  # type: ignore[call-overload]
        if sql.startswith("SELECT count() FROM withdrawn_events"):
            return [[len(self.withdrawn)]]
        if sql.startswith("SELECT DISTINCT event_id FROM withdrawn_events"):
            _, after, limit = params
            page = sorted(e for e in self.withdrawn if e > str(after))[: int(limit)]  # type: ignore[call-overload]
            return [[e] for e in page]
        raise AssertionError(f"a read the test does not model: {sql}")


def _unbounded(sent: list[tuple[str, list[object]]]) -> list[str]:
    """Each statement holding more than one chunk of ids, or a `NOT IN` subquery over a whole table."""
    bad = []
    for sql, params in sent:
        if any(isinstance(p, list) and len(p) > _WITHDRAW_CHUNK for p in params):
            bad.append(f"over a chunk: {sql}")
        for sub in re.findall(
            r"NOT IN\s*\((SELECT [^()]*(?:\([^()]*\)[^()]*)*)\)", sql
        ):
            if " WHERE " not in f" {sub} ":
                bad.append(f"a whole table: {sub}")
    return bad


async def test_setting_events_aside_and_restoring_them_sends_only_bounded_statements() -> (
    None
):
    client = Recording()
    adapter = AnalyticsClickHouseAdapter(client, load_uk_le_scheme())  # type: ignore[arg-type]

    assert await adapter.withdraw_events_by_id(IDS, LOAD) == len(IDS)
    assert (client.events, client.withdrawn) == (set(), set(IDS))
    assert await adapter.restore_withdrawn_events(LOAD) == len(IDS)
    assert (client.events, client.withdrawn) == (set(IDS), set())

    assert _unbounded(client.sent) == []
    assert len(client.sent) > 6, "more than one chunk each way"
