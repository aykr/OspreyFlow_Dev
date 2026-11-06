"""`scripts.migrate_cases_to_one_dataset` against real Postgres (`make dev-up`, under the stack
lease): a deployment holding cases that name two datasets is placed, every case reads one dataset
plus its layer, the one-row index is then built, and a second run changes nothing (ADR-099
Amendment 12 item 9, ADR-143 decision 1)."""

from __future__ import annotations

import asyncpg
from scripts.migrate_cases_to_one_dataset import migrate
from scripts.stamp_datasets import CaseRow
from services.api.config import PostgresConfig
from services.api.datasets import COMPOSITE, PostgresDatasetStore, index_one_dataset_per_case

from conduit_common.identity import new_id
from schemas.domain import Principal


async def test_the_migration_places_cases_naming_two_and_the_store_then_holds_the_rule() -> None:
    # A schema of its own: the one-row index is a check over the whole table, which rows other
    # tests left in the shared database would decide (asyncpg passes `search_path` on).
    base = PostgresConfig.from_env().dsn
    schema = f"migrate_test_{new_id().lower()}"
    admin = await asyncpg.connect(base)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    dsn = f"{base}{'&' if '?' in base else '?'}search_path={schema}"
    store = await PostgresDatasetStore.connect(dsn)
    conn = await asyncpg.connect(dsn)
    unit = f"unit-{new_id()}"
    seeder = Principal(id="seed", clearance="OFFICIAL", org_unit=unit, roles=["analyst"])
    try:
        first, second = await store.create(seeder, "First"), await store.create(seeder, "Second")
        one, two = new_id(), new_id()
        await conn.execute("DROP INDEX IF EXISTS investigation_datasets_one_per_case")
        await conn.executemany(
            "INSERT INTO investigation_datasets (investigation_id, dataset_id, position) "
            "VALUES ($1, $2, $3)",
            [(one, first.id, 0), (two, first.id, 0), (two, second.id, 1)],
        )
        cases = [CaseRow(one, "One", unit, None), CaseRow(two, "Two", unit, None)]

        before = await conn.fetchval("SELECT count(*) FROM investigation_datasets")
        dry = await migrate(store, cases, write=False, say=lambda _: None)
        assert dry.writes and await conn.fetchval(
            "SELECT count(*) FROM investigation_datasets"
        ) == before
        assert await store.layer_of_case(one) is None

        report = await migrate(store, cases, write=True, say=lambda _: None)
        assert report.unplaced == []
        (composite,) = await store.chosen_of_case(two)
        assert composite.kind == COMPOSITE and composite.members == [first.id, second.id]
        for case in (one, two):
            layer = await store.layer_of_case(case)
            assert layer is not None
            assert (await store.ids_of_case(case))[-1] == layer
        assert await store.ids_of_case(one) == [first.id, await store.layer_of_case(one)]
        assert await index_one_dataset_per_case(conn) is True

        again = await migrate(store, cases, write=True, say=lambda _: None)
        assert again.writes == []
    finally:
        await conn.close()
        await store.close()
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()
