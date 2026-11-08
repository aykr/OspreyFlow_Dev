"""`scripts.migrate_cases_to_one_dataset` against real Postgres (`make dev-up`, under the stack
lease): a deployment holding cases that name two datasets is placed, every case reads one dataset
plus its layer, the one-row index is then built, and a second run changes nothing (ADR-099
Amendment 12 item 9, ADR-143 decision 1)."""

from __future__ import annotations

import asyncpg
import pytest
from scripts.migrate_cases_to_one_dataset import migrate
from scripts.stamp_datasets import CaseRow
from services.api.config import PostgresConfig
from services.api.datasets import COMPOSITE, PostgresDatasetStore, index_one_dataset_per_case

from conduit_common.identity import new_id
from schemas.domain import Principal
from tests.services.api.unconverted import made_before_l3_2_on_postgres


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


def _writes_said(out: str) -> int:
    """The run's own count of its writes, from its last line ("…; n writes …")."""
    (last,) = [line for line in out.splitlines() if " writes" in line and "not placed;" in line]
    return int(last.split("not placed;")[1].split("writes")[0].strip().replace(",", ""))


async def test_a_branch_reading_its_originals_layer_is_given_none_and_a_rerun_changes_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The final L3.1 review's second blocker, at `_main`: once a branch made since L3.1 holds a
    `case_layer_reads` row, the migration called `ensure_layer` for it, which refuses a branch
    (`ReadOnlyLayerError`): the run stopped there, the one-row index was never built, and every
    re-run stopped at the same case. The dry run could not foresee it, reading no links. Now the
    branch is named and given none; the dry run says exactly the writes the real run makes; and a
    second run changes nothing. Red with the links unread (below)."""
    import scripts.migrate_cases_to_one_dataset as migration

    admin, schema, dsn = await _old_deployment()
    try:
        conn = await asyncpg.connect(dsn)
        await conn.execute("DELETE FROM investigation_datasets WHERE investigation_id = 'nobody'")
        assert await migration._main([], dsn=dsn) == 0  # the first run, as on the deployment
        # Then a branch made under L3.1's code: it reads 'one''s layer through a link.
        await conn.execute(
            "INSERT INTO investigations (id, name, owning_unit, branched_from) "
            "VALUES ('twig', 'Twig', 'u', 'one')"
        )
        store = await PostgresDatasetStore.connect(dsn)
        try:
            await made_before_l3_2_on_postgres(store, "one", "twig")
            assert await store.read_only_layer_of("twig") == await store.layer_of_case("one")
        finally:
            await store.close()
        await conn.execute("DROP INDEX IF EXISTS investigation_datasets_one_per_case")
        capsys.readouterr()
        assert await migration._main(["--dry-run"], dsn=dsn) == 0
        dry = capsys.readouterr().out
        assert await migration._main([], dsn=dsn) == 0
        real = capsys.readouterr().out
        assert _writes_said(dry) == _writes_said(real) == 0
        for said in (dry, real):
            assert "1 branch made since L3.1 reads its original's layer and is given none: " in said
            assert "Twig (twig)" in said
        assert "One dataset per case is now a rule of the store." in real
        assert await migration._main([], dsn=dsn) == 0
        assert _writes_said(capsys.readouterr().out) == 0
        assert await conn.fetchval(
            "SELECT count(*) FROM datasets WHERE layer_of = 'twig'"
        ) == 0  # fmt: skip
        await conn.close()
    finally:
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


async def test_the_branch_stops_the_migration_with_its_link_unread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule 15, red: the migration as it was, reading no link, asks `ensure_layer` for the branch
    and is refused."""
    import scripts.migrate_cases_to_one_dataset as migration
    from services.api.datasets import ReadOnlyLayerError

    class _LinksUnread:
        """The store as the migration read it before this fix: no link seen; every write still
        the real store's, which refuses a branch a layer."""

        def __init__(self, inner: object) -> None:
            self._inner = inner

        async def read_only_layer_of(self, investigation_id: str) -> None:
            return None

        def __getattr__(self, name: str) -> object:
            return getattr(self._inner, name)

    admin, schema, dsn = await _old_deployment()
    try:
        conn = await asyncpg.connect(dsn)
        await conn.execute("DELETE FROM investigation_datasets WHERE investigation_id = 'nobody'")
        assert await migration._main([], dsn=dsn) == 0
        await conn.execute(
            "INSERT INTO investigations (id, name, owning_unit, branched_from) "
            "VALUES ('twig', 'Twig', 'u', 'one')"
        )
        store = await PostgresDatasetStore.connect(dsn)
        try:
            await made_before_l3_2_on_postgres(store, "one", "twig")
        finally:
            await store.close()
        await conn.close()
        real = migration.migrate

        async def unread(store: object, cases: object, **kwargs: object) -> object:
            return await real(_LinksUnread(store), cases, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(migration, "migrate", unread)
        with pytest.raises(ReadOnlyLayerError):
            await migration._main([], dsn=dsn)
    finally:
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()
