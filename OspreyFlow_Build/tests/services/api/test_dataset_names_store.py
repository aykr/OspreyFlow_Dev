"""Dataset names are unique within a unit, and the store says which ids it holds (ADR-099 Amendment
6), on real Postgres and in memory alike.

What a mistake would do, and the case that catches it:

- two datasets of one unit shown under one name, so an analyst ticks the wrong one
  (`test_a_second_dataset_of_the_same_name_is_refused_in_its_unit`, ignoring case and spacing);
- a case that cannot be made because the dataset it makes for itself is named like another
  (`test_a_cases_own_dataset_takes_a_suffix_rather_than_failing`);
- a deployment whose table already holds duplicate names failing to start when the index arrives
  (`test_names_already_duplicated_are_told_apart_when_the_index_arrives`);
- the stamping graph's registry saying it holds an id it does not
  (`test_known_is_exactly_the_held_ids`).
"""

from __future__ import annotations

from datetime import UTC, datetime

import asyncpg
import pytest
from services.api.config import PostgresConfig
from services.api.datasets import (
    Dataset,
    DatasetRefusedError,
    InMemoryDatasetStore,
    PostgresDatasetStore,
)

from conduit_common.identity import new_id
from schemas.domain import Principal

NOW = datetime(2026, 10, 8, tzinfo=UTC)


def _analyst(unit: str) -> Principal:
    return Principal(id=f"analyst-{new_id()}", clearance="OFFICIAL", org_unit=unit)


@pytest.fixture(params=["postgres", "memory"])
async def store(request):  # type: ignore[no-untyped-def]
    if request.param == "memory":
        yield InMemoryDatasetStore()
        return
    s = await PostgresDatasetStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


async def test_a_second_dataset_of_the_same_name_is_refused_in_its_unit(store) -> None:  # type: ignore[no-untyped-def]
    unit = f"unit-{new_id()}"
    await store.create(_analyst(unit), "Enron corpus")
    for same in ("Enron corpus", "enron  CORPUS", " Enron corpus "):
        with pytest.raises(DatasetRefusedError, match="already"):
            await store.create(_analyst(unit), same)
    # Another unit may use the name.
    await store.create(_analyst(f"unit-{new_id()}"), "Enron corpus")


async def test_a_cases_own_dataset_takes_a_suffix_rather_than_failing(store) -> None:  # type: ignore[no-untyped-def]
    unit = f"unit-{new_id()}"
    first = await store.create(_analyst(unit), "Branch of Enron", suffix_if_taken=True)
    second = await store.create(_analyst(unit), "Branch of Enron", suffix_if_taken=True)
    third = await store.create(_analyst(unit), "branch of enron", suffix_if_taken=True)
    assert [first.name, second.name, third.name] == [
        "Branch of Enron",
        "Branch of Enron (2)",
        "branch of enron (3)",
    ]
    assert len({first.id, second.id, third.id}) == 3


async def test_known_is_exactly_the_held_ids(store) -> None:  # type: ignore[no-untyped-def]
    unit = f"unit-{new_id()}"
    held = await store.create(_analyst(unit), "Held")
    assert await store.known([held.id, "ghost", held.id]) == {held.id}
    assert await store.known([]) == set()


async def test_a_registered_seed_dataset_named_like_another_takes_a_suffix(store) -> None:  # type: ignore[no-untyped-def]
    unit = f"unit-{new_id()}"
    await store.create(_analyst(unit), "Fixture Corp")
    seed = await store.register(
        Dataset(
            id=f"fixture-{new_id()}",
            name="Fixture Corp",
            owning_unit=unit,
            created_at=NOW,
            created_by="seed",
        )
    )
    assert seed.name == "Fixture Corp (2)"


async def test_names_already_duplicated_are_told_apart_when_the_index_arrives() -> None:
    dsn = PostgresConfig.from_env().dsn
    conn = await asyncpg.connect(dsn)
    unit = f"unit-{new_id()}"
    try:
        # As a deployment made before Amendment 6 may hold them: no unique index yet.
        await conn.execute("DROP INDEX IF EXISTS datasets_unit_name_unique")
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS datasets (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
            "owning_unit TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL, created_by TEXT NOT NULL)"
        )
        for i, when in enumerate((NOW, NOW.replace(day=9), NOW.replace(day=10))):
            await conn.execute(
                "INSERT INTO datasets VALUES ($1, $2, $3, $4, 't')",
                f"dup-{unit}-{i}",
                "Same name" if i < 2 else "same NAME",
                unit,
                when,
            )
        store = await PostgresDatasetStore.connect(dsn)
        names = [
            r["name"]
            for r in await conn.fetch(
                "SELECT name FROM datasets WHERE owning_unit = $1 ORDER BY created_at", unit
            )
        ]
        assert names == ["Same name", "Same name (2)", "same NAME (3)"]
        with pytest.raises(DatasetRefusedError):
            await store.create(_analyst(unit), "SAME NAME")
        await store.close()
    finally:
        await conn.execute("DELETE FROM datasets WHERE owning_unit = $1", unit)
        await conn.close()
