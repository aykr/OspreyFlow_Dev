"""The Admin area's view of the reporting mart (`06_DECISIONS.md` ADR-111 Amendment 2), read from
the `pulls` table exactly as `report-sync`'s own `Mart` writes it — real Postgres, the real writer —
so the reader cannot drift from the shape the sync service produces (rule 12).

What a mistake would do, and the case that catches it:
- a feed that is failing shown as fine — `test_a_standing_failure_is_shown_and_a_later_success_clears_it`;
- the screen broken on a deployment with reporting off — `test_no_mart_means_never_pulled_not_an_error`;
- one dashboard's pulls counted for another — `test_each_dashboard_is_counted_on_its_own`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from services.api.config import PostgresConfig
from services.api.report_freshness import ReportFreshness
from services.report_sync.mart import Mart

from conduit_common.identity import new_id

ROW = [("total", "alerts", "", "", 3)]


@pytest.fixture
async def pair() -> AsyncIterator[tuple[Mart, ReportFreshness]]:
    schema = f"reports_{new_id().lower()}"
    mart = await Mart.connect(PostgresConfig.from_env().dsn, schema=schema)
    freshness = await ReportFreshness.connect(PostgresConfig.from_env().dsn, schema=schema)
    yield mart, freshness
    await freshness.close()
    await mart.drop()
    await mart.close()


async def test_each_dashboard_is_counted_on_its_own(pair: tuple[Mart, ReportFreshness]) -> None:
    mart, freshness = pair
    early, late = datetime(2026, 10, 11, 9, tzinfo=UTC), datetime(2026, 10, 11, 10, tzinfo=UTC)
    await mart.replace("osprey-dashboard-a", "case-1", "One", 12, ROW, early)
    await mart.replace("osprey-dashboard-a", "case-2", "Two", 12, ROW, late)
    await mart.replace("osprey-dashboard-b", "case-1", "One", 12, ROW, early)
    seen = await freshness.by_dashboard()
    assert (seen["osprey-dashboard-a"].cases_pulled, seen["osprey-dashboard-a"].last_pulled) == (2, late)
    assert (seen["osprey-dashboard-b"].cases_pulled, seen["osprey-dashboard-b"].last_pulled) == (1, early)
    assert seen["osprey-dashboard-a"].last_failure is None


async def test_a_standing_failure_is_shown_and_a_later_success_clears_it(pair: tuple[Mart, ReportFreshness]) -> None:
    mart, freshness = pair
    pulled, failed = datetime(2026, 10, 11, 9, tzinfo=UTC), datetime(2026, 10, 11, 10, tzinfo=UTC)
    await mart.replace("osprey-dashboard-a", "case-1", "One", 12, ROW, pulled)
    await mart.record_failure("osprey-dashboard-a", "case-1", "the identity provider refused it (401)", failed)
    shown = (await freshness.by_dashboard())["osprey-dashboard-a"]
    assert (shown.last_pulled, shown.last_failure, shown.failed_at) == (pulled, "the identity provider refused it (401)", failed)
    await mart.replace("osprey-dashboard-a", "case-1", "One", 12, ROW, datetime(2026, 10, 11, 11, tzinfo=UTC))
    cleared = (await freshness.by_dashboard())["osprey-dashboard-a"]
    assert (cleared.last_failure, cleared.failed_at) == (None, None)


async def test_no_mart_means_never_pulled_not_an_error() -> None:
    freshness = await ReportFreshness.connect(PostgresConfig.from_env().dsn, schema=f"absent_{new_id().lower()}")
    try:
        assert await freshness.by_dashboard() == {}
    finally:
        await freshness.close()
