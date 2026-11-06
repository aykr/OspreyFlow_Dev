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


#: A deployment as it stood before dataset kinds: no `kind`, `layer_of` or `composite_members`.
_BEFORE_KINDS = """
CREATE TABLE investigations (
    id TEXT PRIMARY KEY, name TEXT, owning_unit TEXT NOT NULL, branched_from TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), removed_at TIMESTAMPTZ
);
CREATE TABLE datasets (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, owning_unit TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL, created_by TEXT NOT NULL,
    egress TEXT NOT NULL DEFAULT 'none'
);
CREATE UNIQUE INDEX datasets_unit_name_unique
    ON datasets (owning_unit, lower(regexp_replace(btrim(name), '\\s+', ' ', 'g')));
CREATE TABLE investigation_datasets (
    investigation_id TEXT NOT NULL, dataset_id TEXT NOT NULL REFERENCES datasets (id),
    position INTEGER NOT NULL, PRIMARY KEY (investigation_id, dataset_id)
);
INSERT INTO investigations (id, name, owning_unit) VALUES ('one', 'One', 'u'), ('two', 'Two', 'u');
INSERT INTO investigations (id, name, owning_unit, removed_at) VALUES ('gone', 'Gone', 'u', now());
INSERT INTO datasets (id, name, owning_unit, created_at, created_by) VALUES
    ('a', 'A', 'u', now(), 't'), ('b', 'B', 'u', now(), 't');
INSERT INTO investigation_datasets VALUES
    ('one', 'a', 0), ('two', 'a', 0), ('two', 'b', 1), ('gone', 'a', 0), ('gone', 'b', 1),
    ('nobody', 'a', 0), ('nobody', 'b', 1);
"""

_SHAPE = """
SELECT
  (SELECT string_agg(table_name || '.' || column_name, ',' ORDER BY table_name, column_name)
     FROM information_schema.columns WHERE table_schema = current_schema()),
  (SELECT string_agg(indexdef, ',' ORDER BY indexdef)
     FROM pg_indexes WHERE schemaname = current_schema()),
  (SELECT string_agg(investigation_id || dataset_id, ',' ORDER BY investigation_id, dataset_id)
     FROM investigation_datasets),
  (SELECT string_agg(id || name, ',' ORDER BY id) FROM datasets)
"""


async def _old_deployment() -> tuple[asyncpg.Connection, str, str]:
    base = PostgresConfig.from_env().dsn
    schema = f"migrate_main_{new_id().lower()}"
    admin = await asyncpg.connect(base)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    dsn = f"{base}{'&' if '?' in base else '?'}search_path={schema}"
    conn = await asyncpg.connect(dsn)
    await conn.execute(_BEFORE_KINDS)
    await conn.close()
    return admin, schema, dsn


async def test_the_dry_run_at_its_real_call_site_changes_no_table_column_index_or_row() -> None:
    """`_main(["--dry-run"])` over a deployment made before kinds: the schema and every row are
    exactly as before, and it still reports what it would do, a removed case and a row with no
    case record among them."""
    import scripts.migrate_cases_to_one_dataset as migration

    admin, schema, dsn = await _old_deployment()
    try:
        conn = await asyncpg.connect(dsn)
        before = await conn.fetchrow(_SHAPE)
        code = await migration._main(["--dry-run"], dsn=dsn)
        assert await conn.fetchrow(_SHAPE) == before
        assert code == 1  # the row with no case record is reported
        await conn.close()
    finally:
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


async def test_the_dry_run_check_fails_with_the_bootstrapping_store_opened(monkeypatch) -> None:
    """Rule 15, at `_main`: the dry run handed the real store's `connect`, as it was before this
    fix, is caught by the same comparison."""
    import scripts.migrate_cases_to_one_dataset as migration

    async def bootstrapping(conn: asyncpg.Connection, dsn: str) -> PostgresDatasetStore:
        return await PostgresDatasetStore.connect(dsn)

    monkeypatch.setattr(migration, "dry_run_store", bootstrapping)
    admin, schema, dsn = await _old_deployment()
    try:
        conn = await asyncpg.connect(dsn)
        before = await conn.fetchrow(_SHAPE)
        await migration._main(["--dry-run"], dsn=dsn)
        assert await conn.fetchrow(_SHAPE) != before
        await conn.close()
    finally:
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


async def test_the_real_run_places_a_removed_case_and_reports_rows_with_no_case() -> None:
    """A removed case naming two would keep the one-row index from being built, so it is placed
    like any other; rows with no case record are reported, and the index then waits for them."""
    import scripts.migrate_cases_to_one_dataset as migration

    admin, schema, dsn = await _old_deployment()
    try:
        code = await migration._main([], dsn=dsn)
        assert code == 1
        store = await PostgresDatasetStore.connect(dsn)
        try:
            for case in ("one", "two", "gone"):
                assert len(await store.chosen_of_case(case)) == 1
                assert await store.layer_of_case(case) is not None
        finally:
            await store.close()
        conn = await asyncpg.connect(dsn)
        assert await index_one_dataset_per_case(conn) is False  # 'nobody' still names two
        await conn.execute("DELETE FROM investigation_datasets WHERE investigation_id = 'nobody'")
        assert await index_one_dataset_per_case(conn) is True
        await conn.close()
    finally:
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()
