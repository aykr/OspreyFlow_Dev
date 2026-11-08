"""ADR-110 Amendment 15's statement bound, on ClickHouse: setting a refresh's events aside and
restoring them sends no statement that grows with the events moved, or with the tables they move
between. Each statement the adapter sends is recorded. A statement may carry one list of ids, at
most one chunk long, and every `NOT IN` subquery must be limited to that list (`has(ids, …)`). A
subquery over a whole table is the shape the methods had before (red so,
`process/lanes/studio/L1.2a_RED_RECORD.md`).

The recording client refuses what the real client refuses (rule 15). It binds each statement with
the real `bind`, so a placeholder count that does not match is refused. And it encodes the bound
values as the real client sends them, in the request's query string, refusing one over httpx's
`MAX_URL_LENGTH` as httpx does (`InvalidURL`). That is the refusal a real ClickHouse run met when a
chunk's ids were bound twice. The ids are ULIDs, the shape the engine writes. What ClickHouse
itself returns is the conformance suite's to prove (`tests/conformance/analytics_port/test_suite.py`,
against a real ClickHouse)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import httpx
from adapters.analytics_clickhouse.adapter import (
    _WITHDRAW_CHUNK,
    AnalyticsClickHouseAdapter,
)
from adapters.analytics_clickhouse.client import bind
from httpx._urlparse import MAX_URL_LENGTH
from ontology.handling import load_uk_le_scheme
from ulid import ULID

IDS = sorted(str(ULID()) for _ in range(2_500))
LOAD = "load-refresh"


class Recording:
    """Stands in for `ClickHouseClient`: every statement kept with its values; `events` and
    `withdrawn_events` held as id sets so the counts and pages the adapter reads are real."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, list[object]]] = []
        self.events: set[str] = set(IDS)
        self.withdrawn: set[str] = set()

    def _keep(self, sql: str, params: Sequence[object]) -> None:
        _, values = bind(
            sql, params
        )  # refuses a placeholder count the real client refuses
        query = str(httpx.QueryParams(values))
        if len(query) > MAX_URL_LENGTH:  # as httpx refuses it, before anything is sent
            raise httpx.InvalidURL("URL component 'query' too long")
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
    """Each statement with more than one list of ids or a list over one chunk, and each `NOT IN`
    subquery not limited to the statement's own ids."""
    bad = []
    for sql, params in sent:
        lists = [p for p in params if isinstance(p, list)]
        if len(lists) > 1:
            bad.append(f"more than one list: {sql}")
        if any(len(p) > _WITHDRAW_CHUNK for p in lists):
            bad.append(f"over a chunk: {sql}")
        for sub in re.findall(
            r"NOT IN\s*\((SELECT [^()]*(?:\([^()]*\)[^()]*)*)\)", sql
        ):
            if not re.search(r"\bWHERE has\(ids, event_id\)", sub):
                bad.append(f"not limited to the chunk: {sub}")
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
