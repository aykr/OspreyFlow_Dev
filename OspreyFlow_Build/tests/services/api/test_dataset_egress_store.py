"""Each dataset's egress (`06_DECISIONS.md` ADR-136 decision 2), on real Postgres and in memory
alike: `none` until an administrator changes it, a dataset made before ADR-136 included.

What a mistake would do, and the case that catches it (rule 12):
- a new dataset, or one a seed registers, starting anywhere but `none`, so material leaves before
  anyone decided it may — `test_a_dataset_starts_at_none_and_a_change_is_kept`;
- a dataset made before ADR-136 read as anything but `none` once the column arrives —
  `test_a_dataset_made_before_the_column_reads_as_none`;
- a change to a dataset that does not exist silently succeeding —
  `test_setting_egress_on_a_dataset_that_does_not_exist_is_refused`;
- the routing told about a dataset it was not asked about —
  `test_egress_of_answers_only_for_the_ids_asked_and_held`.

The Postgres half needs the test database (`POSTGRES_PORT`); the in-memory half runs anywhere.
"""

from __future__ import annotations

from datetime import UTC, datetime

import asyncpg
import pytest
from services.api.config import PostgresConfig
from services.api.datasets import (
    Dataset,
    InMemoryDatasetStore,
    PostgresDatasetStore,
    UnknownDatasetEgressError,
)

from conduit_common.identity import new_id
from schemas.domain import Principal

NOW = datetime(2026, 11, 1, tzinfo=UTC)


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


async def test_a_dataset_starts_at_none_and_a_change_is_kept(store) -> None:  # type: ignore[no-untyped-def]
    unit = f"unit-{new_id()}"
    made = await store.create(_analyst(unit), "Made here")
    seeded = await store.register(
        Dataset(id=f"seed-{new_id()}", name="Seeded", owning_unit=unit, created_at=NOW,
                created_by="seed")  # fmt: skip
    )
    assert (made.egress, seeded.egress) == ("none", "none")
    before, after = await store.set_egress(seeded.id, "contracted")
    assert (before, after.egress, after.name) == ("none", "contracted", "Seeded")
    before, after = await store.set_egress(seeded.id, "any")
    assert (before, after.egress) == ("contracted", "any")
    listed = {d.id: d.egress for d in await store.list_all() if d.owning_unit == unit}
    assert listed == {made.id: "none", seeded.id: "any"}


async def test_setting_egress_on_a_dataset_that_does_not_exist_is_refused(store) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(UnknownDatasetEgressError):
        await store.set_egress(f"nobody-{new_id()}", "any")


async def test_egress_of_answers_only_for_the_ids_asked_and_held(store) -> None:  # type: ignore[no-untyped-def]
    unit = f"unit-{new_id()}"
    one = await store.create(_analyst(unit), "One")
    two = await store.create(_analyst(unit), "Two")
    await store.set_egress(two.id, "any")
    held = await store.egress_of([two.id, f"nobody-{new_id()}"])
    assert {k: v.egress for k, v in held.items()} == {two.id: "any"}
    assert one.id not in held
    assert await store.egress_of([]) == {}


async def test_a_dataset_made_before_the_column_reads_as_none() -> None:
    """As a deployment made before ADR-136 holds it: the table has no `egress` column, and its rows
    gain `none` when the store connects."""
    dsn = PostgresConfig.from_env().dsn
    conn = await asyncpg.connect(dsn)
    unit = f"unit-{new_id()}"
    try:
        # The table exists, whatever ran before.
        await (await PostgresDatasetStore.connect(dsn)).close()
        await conn.execute("ALTER TABLE datasets DROP COLUMN IF EXISTS egress")
        await conn.execute(
            "INSERT INTO datasets (id, name, owning_unit, created_at, created_by) "
            "VALUES ($1, 'Before', $2, $3, 't')",
            f"old-{unit}",
            unit,
            NOW,
        )
        store = await PostgresDatasetStore.connect(dsn)
        (held,) = [d for d in await store.list_all() if d.owning_unit == unit]
        assert held.egress == "none"
        assert (await store.egress_of([f"old-{unit}"]))[f"old-{unit}"].egress == "none"
        await store.close()
    finally:
        await conn.execute("DELETE FROM datasets WHERE owning_unit = $1", unit)
        await conn.close()


async def test_the_promotion_policy_starts_at_author_promotes_and_a_change_is_kept(store) -> None:  # type: ignore[no-untyped-def]
    """ADR-145 decision 8 (L2.4 part 2): every dataset, a seeded one included, starts at *Author
    promotes*; a change returns what it was; a layer or no dataset is refused."""
    unit = f"unit-{new_id()}"
    made = await store.create(_analyst(unit), "Made here")
    assert made.promotion_policy == "author_promotes"
    before, after = await store.set_promotion_policy(made.id, "second_person_reviews")
    assert (before, after.promotion_policy, after.egress) == (
        "author_promotes", "second_person_reviews", "none",
    )  # fmt: skip
    listed = {d.id: d.promotion_policy for d in await store.list_all() if d.owning_unit == unit}
    assert listed == {made.id: "second_person_reviews"}
    layer = await store.ensure_layer(f"case-{new_id()}", unit=unit, created_by="seed")
    for refused in (layer, f"nobody-{new_id()}"):
        with pytest.raises(UnknownDatasetEgressError):
            await store.set_promotion_policy(refused, "author_promotes")
