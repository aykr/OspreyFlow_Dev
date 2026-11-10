"""*Admin › System*'s count of cases made from another that became views (`06_DECISIONS.md` ADR-144
decision 6; `AdminPeopleStore.converted_views`) on real Postgres, a lane's leased test stack. A schema
of its own, dropped in teardown whether the test passes or fails.

Counted in SQL within the administrator's own unit, open cases only (rule 7: the Glass never sees
an unfiltered count). Shown red with the unit clause planted out
(`process/lanes/admin/L2.5b_RED_RECORD.md`).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import asyncpg
import pytest
from services.api.admin_people import AdminPeopleStore
from services.api.case_views import PostgresCaseViewStore
from services.api.config import PostgresConfig
from services.api.investigations import InvestigationStore

T0 = datetime(2026, 11, 10, tzinfo=UTC)


@pytest.fixture
async def world() -> AsyncIterator[tuple[asyncpg.Connection, AdminPeopleStore]]:
    name = "l25b_cv_" + uuid.uuid4().hex[:10]
    base = PostgresConfig.from_env().dsn
    conn = await asyncpg.connect(dsn=base)
    await conn.execute(f'CREATE SCHEMA "{name}"')
    await conn.close()
    dsn = f"{base}{'&' if '?' in base else '?'}search_path={name}"
    held: list[object] = []
    try:
        for store in (InvestigationStore, PostgresCaseViewStore):
            held.append(await store.connect(dsn))  # type: ignore[attr-defined]
        people = await AdminPeopleStore.connect(dsn)
        held.append(people)
        raw = await asyncpg.connect(dsn=dsn)
        try:
            yield raw, people
        finally:
            await raw.close()
    finally:
        for store in held:
            await store.close()  # type: ignore[attr-defined]
        conn = await asyncpg.connect(dsn=base)
        await conn.execute(f'DROP SCHEMA "{name}" CASCADE')
        await conn.close()


async def _case(raw: asyncpg.Connection, case_id: str, unit: str, *, removed: bool = False) -> None:
    await raw.execute(
        "INSERT INTO investigations (id, created_at, created_by, owning_unit, name, removed_at) "
        "VALUES ($1, $2, 'seed', $3, $1, $4)",
        case_id, T0, unit, T0 if removed else None,
    )  # fmt: skip


async def _converted(raw: asyncpg.Connection, case_id: str, from_case: str | None) -> None:
    await raw.execute(
        "INSERT INTO case_views (id, case_id, name, created_by, created_at, lens, "
        "converted_from_case) VALUES ($1, $2, 'v', 'ana', $3, '{}'::jsonb, $4)",
        f"v-{uuid.uuid4().hex[:8]}", case_id, T0, from_case,
    )  # fmt: skip


async def test_the_count_is_of_the_administrators_unit_and_open_cases_only(
    world: tuple[asyncpg.Connection, AdminPeopleStore],
) -> None:
    raw, people = world
    await _case(raw, "c-1", "unit-1")
    await _case(raw, "c-2", "unit-1")
    await _case(raw, "c-gone", "unit-1", removed=True)
    await _case(raw, "c-far", "unit-2")
    for case_id in ("c-1", "c-1", "c-2", "c-gone", "c-far", "c-far"):
        await _converted(raw, case_id, "old-branch")
    await _converted(raw, "c-1", None)  # saved by hand, not converted

    counted = await people.converted_views("unit-1")
    assert (counted.views, counted.cases) == (3, 2)
    other = await people.converted_views("unit-2")
    assert (other.views, other.cases) == (2, 1)

