"""`scripts.make_home_cases` at its real call site, `_main`, against real Postgres (`make dev-up`,
under the stack lease), in a schema of its own.

The dry run writes no row. The real run gives each dataset its home case, the person who made it as
its Author and a service account's dataset none. A second run changes nothing (ADR-145 Amendment 4
decision 2).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest
from services.api.config import PostgresConfig
from services.api.datasets import PostgresDatasetStore
from services.api.investigations import InvestigationStore

from conduit_common.identity import new_id
from schemas.domain import Principal


class _Names:
    async def people(self, ids: Any) -> set[str]:
        return {i for i in ids if i == "d.engineer"}


@pytest.fixture
async def dsn() -> AsyncIterator[str]:
    base = PostgresConfig.from_env().dsn
    schema = f"home_cases_{new_id().lower()}"
    admin = await asyncpg.connect(base)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    yield f"{base}{'&' if '?' in base else '?'}search_path={schema}"
    await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
    await admin.close()


async def test_the_dry_run_then_the_real_run_then_nothing(
    dsn: str, capsys: pytest.CaptureFixture[str]
) -> None:
    import scripts.make_home_cases as homes

    datasets = await PostgresDatasetStore.connect(dsn)
    cases = await InvestigationStore.connect(dsn)
    engineer = Principal(id="d.engineer", clearance="OFFICIAL", org_unit="u", roles=["analyst"])
    robot = Principal(id="service-account-loader", clearance="OFFICIAL", org_unit="u")
    try:
        prison = await datasets.create(engineer, "Prison records")
        bank = await datasets.create(robot, "Bank records")
        conn = await asyncpg.connect(dsn)
        try:
            rows_before = await conn.fetchval("SELECT count(*) FROM investigations")
            assert await homes._main(["--dry-run"], dsn=dsn, names=_Names()) == 0  # noqa: SLF001
            dry = capsys.readouterr().out
            assert await conn.fetchval("SELECT count(*) FROM investigations") == rows_before
            assert await conn.fetchval("SELECT count(*) FROM home_cases") == 0
            assert "8 writes planned" in dry and "1 home case needs an owner" in dry
            assert await homes._main([], dsn=dsn, names=_Names()) == 0  # noqa: SLF001
            assert "8 writes made" in capsys.readouterr().out
        finally:
            await conn.close()
        prison_home, bank_home = (
            await datasets.home_case_of(prison.id),
            await datasets.home_case_of(bank.id),
        )
        assert prison_home is not None and bank_home is not None
        assert await cases.list_grants(prison_home.investigation_id) == {"d.engineer": "author"}
        assert await cases.list_grants(bank_home.investigation_id) == {}
        assert [d.id for d in await datasets.chosen_of_case(prison_home.investigation_id)] == [
            prison.id
        ]
        assert await homes._main([], dsn=dsn, names=_Names()) == 0  # noqa: SLF001
        assert "0 home cases made, 0 needing an owner, 2 already had one; 0 writes made" in (
            capsys.readouterr().out
        )
    finally:
        await datasets.close()
        await cases.close()


async def test_two_runs_at_once_give_each_dataset_one_home_case(
    dsn: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """The round-1 review's must-fix 8: idempotent by the dataset's id, not by when the tables
    were read. Two runs at once each read "no home case yet"; the store's key on the dataset
    holds the claim, and the loser removes the case it made."""
    import asyncio

    import scripts.make_home_cases as homes

    datasets = await PostgresDatasetStore.connect(dsn)
    cases = await InvestigationStore.connect(dsn)
    engineer = Principal(id="d.engineer", clearance="OFFICIAL", org_unit="u", roles=["analyst"])
    try:
        made = [await datasets.create(engineer, f"Records {i}") for i in range(3)]
        assert await asyncio.gather(
            *(homes._main([], dsn=dsn, names=_Names()) for _ in range(2))  # noqa: SLF001
        ) == [0, 0]
        conn = await asyncpg.connect(dsn)
        try:
            per_dataset = await conn.fetch(
                "SELECT dataset_id, count(*) AS n FROM home_cases GROUP BY dataset_id"
            )
            live_homes = await conn.fetchval(
                "SELECT count(*) FROM investigations WHERE removed_at IS NULL"
            )
        finally:
            await conn.close()
        assert {r["dataset_id"]: r["n"] for r in per_dataset} == {d.id: 1 for d in made}
        assert live_homes == 3
        for dataset in made:
            home = await datasets.home_case_of(dataset.id)
            assert home is not None
            assert await cases.list_grants(home.investigation_id) == {"d.engineer": "author"}
    finally:
        await datasets.close()
        await cases.close()
