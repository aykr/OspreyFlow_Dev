"""The seeds' events through the live ClickHouse (ADR-148 Amendment 14; rule 15: the real
server, never a fake of it): B18's sightings and HMP's events and places, the same cases
`test_seed_scenarios.py` and `test_seed_analytics.py` run on DuckDB, given ClickHouse's own adapter.
Needs the live ClickHouse (`CLICKHOUSE_HTTP_PORT`), so it is a live file (the `test` job ignores
it)."""

from __future__ import annotations

import pytest

from adapters.analytics_clickhouse.testing import clickhouse_adapter
from tests import test_seed_analytics, test_seed_scenarios


async def test_b18_through_the_live_clickhouse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(test_seed_scenarios.STORES, "clickhouse", clickhouse_adapter)
    b18 = test_seed_scenarios.test_b18_the_seeded_sightings_are_the_ones_the_glass_trail_reads
    await b18("clickhouse")


async def test_hmps_events_and_places_through_the_live_clickhouse() -> None:
    await test_seed_analytics.test_hmps_events_and_places_go_through_each_store("clickhouse")
