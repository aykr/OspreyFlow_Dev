"""The POC seed path's case unit against the real people store (ADR-148 Amendment 14; rules 3, 4,
15): the first administrator's own unit as their sign-in recorded it, in this tenant alone; one
never signed in, or another tenant's row of the same object id, refused. Needs the live
PostgreSQL."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
from scripts import seed_poc
from services.api.config import PostgresConfig
from services.api.entra_people import EntraPeopleStore

from principal_auth import SeenPerson

TENANT = "00000000-1111-4222-8333-444444444444"
OTHER_TENANT = "99999999-8888-4777-8666-555555555555"
ADMIN = "50000000-0000-4000-8000-000000000001"
SEEN = SeenPerson(
    name="Synthetic Administrator",
    username="admin@example.test",
    email=None,
    clearance="OFFICIAL-SENSITIVE",
    org_unit="unit-7",
    receivable_handling_codes=(),
)


@pytest.fixture
async def stores() -> AsyncIterator[tuple[EntraPeopleStore, EntraPeopleStore]]:
    name = "seedpoc_" + uuid.uuid4().hex[:10]
    base = PostgresConfig.from_env().dsn
    conn = await asyncpg.connect(dsn=base)
    await conn.execute(f'CREATE SCHEMA "{name}"')
    await conn.close()
    dsn = f"{base}?search_path={name}"
    mine = await EntraPeopleStore.connect(dsn, TENANT)
    other = await EntraPeopleStore.connect(dsn, OTHER_TENANT)
    try:
        yield mine, other
    finally:
        await mine.close()
        await other.close()
        conn = await asyncpg.connect(dsn=base)
        await conn.execute(f'DROP SCHEMA "{name}" CASCADE')
        await conn.close()


async def test_the_unit_is_the_one_the_first_administrators_sign_in_recorded(
    stores,
) -> None:  # type: ignore[no-untyped-def]
    mine, _ = stores
    await mine.person(TENANT, ADMIN, SEEN)
    assert await seed_poc.author_unit(mine, ADMIN) == "unit-7"


async def test_one_never_signed_in_is_refused(stores) -> None:  # type: ignore[no-untyped-def]
    mine, _ = stores
    with pytest.raises(seed_poc.SeedRefused, match="has not signed in"):
        await seed_poc.author_unit(mine, ADMIN)


async def test_another_tenants_row_of_the_same_object_id_is_not_theirs(stores) -> None:  # type: ignore[no-untyped-def]
    mine, other = stores
    await other.person(OTHER_TENANT, ADMIN, SEEN)
    with pytest.raises(seed_poc.SeedRefused, match="has not signed in"):
        await seed_poc.author_unit(mine, ADMIN)
