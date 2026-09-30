"""A demo dataset is loaded into a named case that the demo accounts can open.

Seen on the owner's deployment: the picker listed only blank cases, because the seeds tagged their
data with an id the seed itself was handed and no case with a name or grants existed for the demo
accounts. `scripts/case_seed.py` creates the named case (idempotently) and grants the demo accounts
their levels, in the Conduit's own Postgres, through the same store the routes use. Real Postgres,
like the other case-store tests; a fresh schema per test.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
from scripts.case_seed import ensure_case, parse_grant
from services.api.config import PostgresConfig
from services.api.investigations import AccessLevel, InvestigationStore

from schemas.domain import Principal

SEEDER = Principal(id="seed-worker", clearance="OFFICIAL", org_unit="verify")
ADMIN_SUB = "0b6f0f2e-admin"
ANALYST_SUB = "5d1c9a7c-analyst"
OTHER_UNIT = Principal(id=ADMIN_SUB, clearance="OFFICIAL", org_unit="unit-2")


@pytest.fixture
async def store() -> AsyncIterator[InvestigationStore]:
    name = "seed_" + uuid.uuid4().hex[:10]
    conn = await asyncpg.connect(dsn=PostgresConfig.from_env().dsn)
    await conn.execute(f'CREATE SCHEMA "{name}"')
    await conn.close()
    opened = await InvestigationStore.connect(f"{PostgresConfig.from_env().dsn}?search_path={name}")
    yield opened
    await opened.close()
    conn = await asyncpg.connect(dsn=PostgresConfig.from_env().dsn)
    await conn.execute(f'DROP SCHEMA "{name}" CASCADE')
    await conn.close()


async def test_the_named_case_exists_and_the_demo_accounts_hold_their_levels(
    store: InvestigationStore,
) -> None:
    case = await ensure_case(
        store,
        name="PaySim mobile money (internal)",
        seeder=SEEDER,
        grants={ADMIN_SUB: AccessLevel.AUTHOR, ANALYST_SUB: AccessLevel.EDITOR},
    )

    admin = Principal(id=ADMIN_SUB, clearance="OFFICIAL", org_unit="verify")
    analyst = Principal(id=ANALYST_SUB, clearance="OFFICIAL", org_unit="verify")
    assert case.name == "PaySim mobile money (internal)"
    assert await store.effective_level(case.id, admin) is AccessLevel.AUTHOR
    assert await store.effective_level(case.id, analyst) is AccessLevel.EDITOR
    assert [c.name for c, _ in await store.list_for(analyst)] == ["PaySim mobile money (internal)"]


async def test_loading_twice_reuses_the_case_and_does_not_make_a_second(
    store: InvestigationStore,
) -> None:
    """Catches a re-run that leaves two cases with the same name, one of them empty."""
    first = await ensure_case(
        store, name="Enron mail (internal)", seeder=SEEDER, grants={ADMIN_SUB: AccessLevel.AUTHOR}
    )
    second = await ensure_case(
        store, name="Enron mail (internal)", seeder=SEEDER, grants={ADMIN_SUB: AccessLevel.AUTHOR}
    )

    assert second.id == first.id
    admin = Principal(id=ADMIN_SUB, clearance="OFFICIAL", org_unit="verify")
    assert len(await store.list_for(admin)) == 1


async def test_a_case_removed_by_the_owner_is_not_silently_brought_back(
    store: InvestigationStore,
) -> None:
    """A removed case reads as not found (ADR-052 Amendment 7); a later load makes a fresh one
    rather than writing into a case the owner removed."""
    first = await ensure_case(
        store, name="Gone", seeder=SEEDER, grants={ADMIN_SUB: AccessLevel.AUTHOR}
    )
    await store.remove(first.id, by=SEEDER)

    second = await ensure_case(
        store, name="Gone", seeder=SEEDER, grants={ADMIN_SUB: AccessLevel.AUTHOR}
    )

    assert second.id != first.id


async def test_a_grant_never_opens_the_case_to_another_unit(store: InvestigationStore) -> None:
    """ADR-041 still holds for a seeded case: an account in another unit finds nothing."""
    case = await ensure_case(
        store, name="Unit only", seeder=SEEDER, grants={ADMIN_SUB: AccessLevel.AUTHOR}
    )
    assert await store.effective_level(case.id, OTHER_UNIT) is None


async def test_the_case_is_never_shared_with_the_whole_unit_unless_asked(
    store: InvestigationStore,
) -> None:
    case = await ensure_case(store, name="Private", seeder=SEEDER, grants={})
    bystander = Principal(id="someone", clearance="OFFICIAL", org_unit="verify")
    assert await store.effective_level(case.id, bystander) is None


def test_grants_are_written_account_equals_level_and_a_bad_one_is_refused() -> None:
    assert parse_grant("abc-123=editor") == ("abc-123", AccessLevel.EDITOR)
    for bad in ("", "abc", "abc=", "=editor", "abc=owner", "abc=editor=x"):
        with pytest.raises(ValueError, match="grant"):
            parse_grant(bad)


# --- the synthetic demos take a case name as PaySim does ---


def test_the_hmp_and_fixture_corp_seeds_take_a_case_name_or_a_scope_and_not_neither() -> None:
    """Catches the demos still needing a raw case id the owner cannot see."""
    from scripts import seed_fixture_corp, seed_hmp_fixture

    for module in (seed_hmp_fixture, seed_fixture_corp):
        with pytest.raises(SystemExit):
            module._parse_args([])
        with pytest.raises(SystemExit):
            module._parse_args(["--case-name", "x", "--investigation-scope", "y"])
        args = module._parse_args(["--case-name", "x", "--grant", "a=author"])
        assert args.case_name == "x" and args.grant == ["a=author"]
        assert module._parse_args(["--investigation-scope", "y"]).investigation_scope == "y"
