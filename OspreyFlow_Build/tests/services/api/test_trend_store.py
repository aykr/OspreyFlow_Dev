"""The saved trend definitions (`06_DECISIONS.md` ADR-113 decision 1), against real Postgres: a trend
belongs to its case and is found, read or removed only through it."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from services.api.config import PostgresConfig
from services.api.trends import TrendStore

from conduit_common.identity import new_id
from schemas.domain import Principal
from schemas.trends import TrendDefinitionInput, TrendFilter

BY = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


@pytest.fixture
async def store() -> AsyncIterator[TrendStore]:
    found = await TrendStore.connect(PostgresConfig.from_env().dsn)
    yield found
    await found.close()


async def test_a_saved_trend_round_trips_and_stays_in_its_own_case(store: TrendStore) -> None:
    case, other = f"case-{new_id()}", f"case-{new_id()}"
    defn = TrendDefinitionInput(title="Cash by week", event_types=["TRANSACTED"], measure="sum",
                                measure_field="amount", group_by="channel",
                                filters=[TrendFilter(field="channel", value="cash")])  # fmt: skip
    saved = await store.create(case, defn, BY)
    assert (saved.investigation_id, saved.created_by) == (case, "analyst-1")
    assert TrendDefinitionInput.model_validate(saved.model_dump(include=set(TrendDefinitionInput.model_fields))) == defn
    assert [t.id for t in await store.list_for_case(case)] == [saved.id]
    assert await store.list_for_case(other) == []
    assert await store.get(other, saved.id) is None, "found only through its own case"
    assert not await store.delete(other, saved.id)
    assert await store.delete(case, saved.id)
    assert await store.get(case, saved.id) is None
