"""`scripts.seed_target_models` at its real call site, `_main`, against real Postgres (`make
dev-up`, under the stack lease), in a schema of its own.

The dry run makes no table and writes no row. The real run gives each dataset its first model,
live, its packs only its own cases' choice. A second run changes nothing (ADR-126 Amendment 3).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
import pytest
from services.api.config import PostgresConfig
from services.api.target_models import CORE_TYPES_FOR_TESTS, PostgresTargetModelStore

from conduit_common.identity import new_id

_TABLES = """
CREATE TABLE investigations (id TEXT PRIMARY KEY, name TEXT, owning_unit TEXT NOT NULL,
                             domains TEXT[], removed_at TIMESTAMPTZ);
CREATE TABLE datasets (id TEXT PRIMARY KEY, name TEXT NOT NULL, owning_unit TEXT NOT NULL,
                       kind TEXT NOT NULL DEFAULT 'source');
CREATE TABLE investigation_datasets (investigation_id TEXT NOT NULL, dataset_id TEXT NOT NULL,
                                     position INTEGER NOT NULL);
INSERT INTO datasets VALUES ('bank', 'Bank', 'u', 'source'), ('prison', 'Prison', 'u', 'source'),
                            ('layer', 'A layer', 'u', 'analyst_layer');
INSERT INTO investigations VALUES ('kyc', 'KYC', 'u', ARRAY['fibo'], NULL),
                                  ('custody', 'Custody', 'u', ARRAY['niem'], NULL),
                                  ('gone', 'Removed', 'u', ARRAY['stix'], now()),
                                  ('old', 'Old pack', 'u', ARRAY['retired-pack'], NULL);
INSERT INTO investigation_datasets VALUES ('kyc', 'bank', 0), ('custody', 'prison', 0),
                                          ('gone', 'prison', 0), ('old', 'bank', 0);
"""


@pytest.fixture
async def dsn() -> AsyncIterator[str]:
    base = PostgresConfig.from_env().dsn
    schema = f"seed_models_{new_id().lower()}"
    admin = await asyncpg.connect(base)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    with_path = f"{base}{'&' if '?' in base else '?'}search_path={schema}"
    conn = await asyncpg.connect(with_path)
    await conn.execute(_TABLES)
    await conn.close()
    yield with_path
    await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
    await admin.close()


async def test_the_dry_run_then_the_real_run_then_nothing(
    dsn: str, capsys: pytest.CaptureFixture[str]
) -> None:
    import scripts.seed_target_models as seeding

    conn = await asyncpg.connect(dsn)
    try:
        assert await seeding._main(["--dry-run"], dsn=dsn) == 0  # noqa: SLF001
        dry = capsys.readouterr().out
        assert await conn.fetchval("SELECT to_regclass('target_models')") is None
        assert "Bank (bank): version 1, live, fibo" in dry and "6 writes planned" in dry
        # A pack a case chose that the ontology no longer carries is named, with its dataset.
        assert (
            "Bank (bank): its cases chose retired-pack, which this deployment's ontology does "
            "not carry: left out of its model"
        ) in dry
        assert "1 left a pack out that the ontology does not carry." in dry
        assert await seeding._main([], dsn=dsn) == 0  # noqa: SLF001
        assert "6 writes made" in capsys.readouterr().out
        store = await PostgresTargetModelStore.connect(dsn, core_types=CORE_TYPES_FOR_TESTS)
        try:
            bank, prison = await store.live("bank"), await store.live("prison")
            assert bank is not None and set(bank.packs) == {"fibo"}
            assert prison is not None and set(prison.packs) == {"niem"}
            assert await store.live("layer") is None
        finally:
            await store.close()
        assert await seeding._main([], dsn=dsn) == 0  # noqa: SLF001
        again = capsys.readouterr().out
        assert "0 given a first model, 2 already had one; 0 writes made" in again
    finally:
        await conn.close()


class _WithoutTheRemovedFilter:
    """`read_tables`' connection with the removed-case filter planted out of each query."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def fetch(self, query: str, *args: object) -> object:
        for planted in (" AND i.removed_at IS NULL", " WHERE removed_at IS NULL"):
            query = query.replace(planted, "")
        return await self._conn.fetch(query, *args)

    async def fetchval(self, query: str, *args: object) -> object:
        return await self._conn.fetchval(query, *args)


@pytest.mark.parametrize("planted_out", [False, True], ids=["held", "the-filter-removed"])
async def test_a_removed_cases_choice_counts_for_nothing(dsn: str, planted_out: bool) -> None:
    """The round-1 review's must-fix 9: the removed case chose STIX for the prison; it is no
    longer anyone's choice. Rule 15, red: with the filter planted out of the real queries, STIX
    reaches the prison's model."""
    from scripts.seed_target_models import packs_for, read_tables

    conn = await asyncpg.connect(dsn)
    try:
        _, chosen, domains, _ = await read_tables(
            _WithoutTheRemovedFilter(conn) if planted_out else conn  # type: ignore[arg-type]
        )
    finally:
        await conn.close()
    assert ("stix" in packs_for("prison", chosen, domains)) is planted_out
