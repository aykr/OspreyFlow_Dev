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
                             domains TEXT[]);
CREATE TABLE datasets (id TEXT PRIMARY KEY, name TEXT NOT NULL, owning_unit TEXT NOT NULL,
                       kind TEXT NOT NULL DEFAULT 'source');
CREATE TABLE investigation_datasets (investigation_id TEXT NOT NULL, dataset_id TEXT NOT NULL,
                                     position INTEGER NOT NULL);
INSERT INTO datasets VALUES ('bank', 'Bank', 'u', 'source'), ('prison', 'Prison', 'u', 'source'),
                            ('layer', 'A layer', 'u', 'analyst_layer');
INSERT INTO investigations VALUES ('kyc', 'KYC', 'u', ARRAY['fibo']),
                                  ('custody', 'Custody', 'u', ARRAY['niem']);
INSERT INTO investigation_datasets VALUES ('kyc', 'bank', 0), ('custody', 'prison', 0);
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
