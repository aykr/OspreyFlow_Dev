"""ADR-052 stage 1: a case has a name, per-account grants and a unit-wide level, and every read of
a case names the level it needs. Real Postgres, like the other stores' own tests (`test_alerts.py`);
a fresh schema per test so none of them sees another's cases."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
from services.api.config import PostgresConfig
from services.api.investigations import (
    AccessLevel,
    InsufficientAccessError,
    InvestigationNotFoundError,
    InvestigationStore,
)

from schemas.domain import Principal

AUTHOR = Principal(id="alice", clearance="OFFICIAL", org_unit="unit-1")
COLLEAGUE = Principal(id="bob", clearance="OFFICIAL", org_unit="unit-1")
OUTSIDER = Principal(id="carol", clearance="OFFICIAL", org_unit="unit-2")


@pytest.fixture
async def schema() -> AsyncIterator[str]:
    name = "acc_" + uuid.uuid4().hex[:10]
    conn = await asyncpg.connect(dsn=PostgresConfig.from_env().dsn)
    await conn.execute(f'CREATE SCHEMA "{name}"')
    await conn.close()
    yield name
    conn = await asyncpg.connect(dsn=PostgresConfig.from_env().dsn)
    await conn.execute(f'DROP SCHEMA "{name}" CASCADE')
    await conn.close()


@pytest.fixture
async def store(schema: str) -> AsyncIterator[InvestigationStore]:
    dsn = f"{PostgresConfig.from_env().dsn}?search_path={schema}"
    opened = await InvestigationStore.connect(dsn)
    yield opened
    await opened.close()


async def test_the_creator_is_the_first_author_and_the_case_has_its_name(
    store: InvestigationStore,
) -> None:
    case = await store.create(AUTHOR, name="Fixture vs Enron")

    assert case.name == "Fixture vs Enron"
    assert await store.effective_level(case.id, AUTHOR) is AccessLevel.AUTHOR
    assert (await store.get_authorized(case.id, AUTHOR, need=AccessLevel.AUTHOR)).id == case.id


async def test_a_new_case_is_invisible_to_the_rest_of_the_unit_until_shared(
    store: InvestigationStore,
) -> None:
    case = await store.create(AUTHOR, name="Private")

    with pytest.raises(InvestigationNotFoundError):
        await store.get_authorized(case.id, COLLEAGUE, need=AccessLevel.VIEWER)
    assert await store.effective_level(case.id, COLLEAGUE) is None


async def test_a_blank_name_is_refused(store: InvestigationStore) -> None:
    with pytest.raises(ValueError, match="name"):
        await store.create(AUTHOR, name="   ")


async def test_each_level_includes_the_one_below_it_and_no_more(
    store: InvestigationStore,
) -> None:
    case = await store.create(AUTHOR, name="Shared")
    await store.set_grant(case.id, "bob", AccessLevel.EDITOR, by=AUTHOR)

    await store.get_authorized(case.id, COLLEAGUE, need=AccessLevel.VIEWER)
    await store.get_authorized(case.id, COLLEAGUE, need=AccessLevel.EDITOR)
    with pytest.raises(InsufficientAccessError):
        await store.get_authorized(case.id, COLLEAGUE, need=AccessLevel.AUTHOR)


async def test_a_viewer_cannot_do_what_needs_an_editor(store: InvestigationStore) -> None:
    case = await store.create(AUTHOR, name="Read only")
    await store.set_grant(case.id, "bob", AccessLevel.VIEWER, by=AUTHOR)

    await store.get_authorized(case.id, COLLEAGUE, need=AccessLevel.VIEWER)
    with pytest.raises(InsufficientAccessError):
        await store.get_authorized(case.id, COLLEAGUE, need=AccessLevel.EDITOR)


async def test_a_grant_never_widens_the_unit_check(store: InvestigationStore) -> None:
    """ADR-041's rule survives: a grant to an account in another unit opens nothing, and gets the
    same not-found as a case that does not exist."""
    case = await store.create(AUTHOR, name="Unit one only")
    await store.set_grant(case.id, "carol", AccessLevel.AUTHOR, by=AUTHOR)

    with pytest.raises(InvestigationNotFoundError):
        await store.get_authorized(case.id, OUTSIDER, need=AccessLevel.VIEWER)


async def test_the_unit_wide_level_applies_to_everyone_in_the_unit_and_only_them(
    store: InvestigationStore,
) -> None:
    case = await store.create(AUTHOR, name="Whole unit")
    await store.set_unit_level(case.id, AccessLevel.VIEWER, by=AUTHOR)

    await store.get_authorized(case.id, COLLEAGUE, need=AccessLevel.VIEWER)
    with pytest.raises(InsufficientAccessError):
        await store.get_authorized(case.id, COLLEAGUE, need=AccessLevel.EDITOR)
    with pytest.raises(InvestigationNotFoundError):
        await store.get_authorized(case.id, OUTSIDER, need=AccessLevel.VIEWER)


async def test_the_higher_of_a_grant_and_the_unit_wide_level_wins(
    store: InvestigationStore,
) -> None:
    case = await store.create(AUTHOR, name="Both")
    await store.set_unit_level(case.id, AccessLevel.EDITOR, by=AUTHOR)
    await store.set_grant(case.id, "bob", AccessLevel.VIEWER, by=AUTHOR)

    assert await store.effective_level(case.id, COLLEAGUE) is AccessLevel.EDITOR


async def test_removing_a_grant_removes_the_access(store: InvestigationStore) -> None:
    case = await store.create(AUTHOR, name="Revoked")
    await store.set_grant(case.id, "bob", AccessLevel.EDITOR, by=AUTHOR)
    await store.remove_grant(case.id, "bob", by=AUTHOR)

    with pytest.raises(InvestigationNotFoundError):
        await store.get_authorized(case.id, COLLEAGUE, need=AccessLevel.VIEWER)


async def test_a_case_that_does_not_exist_is_not_found_at_every_level(
    store: InvestigationStore,
) -> None:
    for need in AccessLevel:
        with pytest.raises(InvestigationNotFoundError):
            await store.get_authorized("no-such-case", AUTHOR, need=need)


async def test_cases_from_before_this_change_keep_their_creator_as_author_and_the_unit_as_viewers(
    schema: str,
) -> None:
    """ADR-052 §5. The old table has no name and no grants; connecting migrates it once."""
    dsn = f"{PostgresConfig.from_env().dsn}?search_path={schema}"
    conn = await asyncpg.connect(dsn=dsn)
    await conn.execute(
        "CREATE TABLE investigations (id TEXT PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL, "
        "created_by TEXT NOT NULL, owning_unit TEXT NOT NULL, branched_from TEXT "
        "REFERENCES investigations (id))"
    )
    await conn.execute(
        "INSERT INTO investigations VALUES ('old-case', now(), 'alice', 'unit-1', NULL)"
    )
    await conn.close()

    store = await InvestigationStore.connect(dsn)
    try:
        assert await store.effective_level("old-case", AUTHOR) is AccessLevel.AUTHOR
        assert await store.effective_level("old-case", COLLEAGUE) is AccessLevel.VIEWER
        assert await store.effective_level("old-case", OUTSIDER) is None
        # Migrated once: an Author who removes the creator's grant is not undone by a restart.
        await store.remove_grant("old-case", "alice", by=AUTHOR)
    finally:
        await store.close()
    again = await InvestigationStore.connect(dsn)
    try:
        assert await again.effective_level("old-case", AUTHOR) is AccessLevel.VIEWER
    finally:
        await again.close()


async def test_every_change_of_access_is_recorded_with_who_what_to_whom(
    store: InvestigationStore,
) -> None:
    case = await store.create(AUTHOR, name="Audited")
    await store.set_grant(case.id, "bob", AccessLevel.VIEWER, by=AUTHOR)
    await store.set_grant(case.id, "bob", AccessLevel.EDITOR, by=AUTHOR)
    await store.set_unit_level(case.id, AccessLevel.VIEWER, by=AUTHOR)
    await store.set_unit_level(case.id, None, by=AUTHOR)
    await store.remove_grant(case.id, "bob", by=AUTHOR)

    history = await store.access_history(case.id)

    assert [(h.action, h.subject, h.level) for h in history] == [
        ("create", "alice", "author"),
        ("grant", "bob", "viewer"),
        ("grant", "bob", "editor"),
        ("unit_level", "unit-1", "viewer"),
        ("unit_level", "unit-1", None),
        ("revoke", "bob", None),
    ]
    assert all(h.changed_by == "alice" for h in history)


# --- stage 2: listing, renaming, reading who holds what ----------------------------------------


async def test_the_list_holds_only_the_cases_the_account_holds_a_level_on(
    store: InvestigationStore,
) -> None:
    mine = await store.create(AUTHOR, name="Mine")
    shared = await store.create(AUTHOR, name="Shared with bob")
    await store.set_grant(shared.id, "bob", AccessLevel.VIEWER, by=AUTHOR)
    whole_unit = await store.create(AUTHOR, name="Whole unit")
    await store.set_unit_level(whole_unit.id, AccessLevel.EDITOR, by=AUTHOR)
    await store.create(AUTHOR, name="Private")

    bobs = {c.name: level for c, level in await store.list_for(COLLEAGUE)}
    alices = {c.name: level for c, level in await store.list_for(AUTHOR)}

    assert bobs == {
        "Shared with bob": AccessLevel.VIEWER,
        "Whole unit": AccessLevel.EDITOR,
    }
    assert set(alices) == {"Mine", "Shared with bob", "Whole unit", "Private"}
    assert alices["Mine"] is AccessLevel.AUTHOR
    assert mine.name in alices
    # Another unit sees nothing, whatever grants exist.
    await store.set_grant(shared.id, "carol", AccessLevel.AUTHOR, by=AUTHOR)
    assert await store.list_for(OUTSIDER) == []


async def test_an_author_can_rename_a_case_and_the_rename_is_recorded(
    store: InvestigationStore,
) -> None:
    case = await store.create(AUTHOR, name="Old")

    await store.rename(case.id, "  New name ", by=AUTHOR)

    assert (await store.get(case.id)).name == "New name"
    assert [(h.action, h.subject) for h in await store.access_history(case.id)][-1] == (
        "rename",
        "New name",
    )
    with pytest.raises(ValueError, match="name"):
        await store.rename(case.id, " ", by=AUTHOR)


async def test_the_grants_and_the_unit_wide_level_can_be_read_back(
    store: InvestigationStore,
) -> None:
    case = await store.create(AUTHOR, name="Read back")
    await store.set_grant(case.id, "bob", AccessLevel.EDITOR, by=AUTHOR)
    await store.set_unit_level(case.id, AccessLevel.VIEWER, by=AUTHOR)

    grants = await store.list_grants(case.id)

    assert grants == {"alice": AccessLevel.AUTHOR, "bob": AccessLevel.EDITOR}
    assert await store.unit_level(case.id) is AccessLevel.VIEWER


async def test_the_administrator_lookup_finds_a_case_in_the_unit_without_any_level(
    store: InvestigationStore,
) -> None:
    """The safety net for a case whose Authors have left (ADR-052 §4). It confirms the case exists
    in the account's own unit and returns nothing of its contents; another unit gets nothing."""
    case = await store.create(AUTHOR, name="Stranded")
    admin = Principal(id="root", clearance="OFFICIAL", org_unit="unit-1")

    found = await store.get_for_access_admin(case.id, admin)

    assert found.id == case.id
    assert await store.effective_level(case.id, admin) is None  # still cannot read it
    with pytest.raises(InvestigationNotFoundError):
        await store.get_for_access_admin(case.id, OUTSIDER)


# --- removing a case (ADR-052 Amendment 7): a soft remove, never a hard delete ---


async def test_a_removed_case_is_the_same_not_found_as_one_that_never_existed(
    store: InvestigationStore,
) -> None:
    """The existence-leak rule (ADR-041): every read of a removed case, at every level, by anyone
    holding any grant, is `InvestigationNotFoundError`, not a 403 and not a special message."""
    case = await store.create(AUTHOR, name="To go")
    await store.set_grant(case.id, "bob", AccessLevel.EDITOR, by=AUTHOR)
    await store.set_unit_level(case.id, AccessLevel.VIEWER, by=AUTHOR)

    await store.remove(case.id, by=AUTHOR)

    for who in (AUTHOR, COLLEAGUE):
        with pytest.raises(InvestigationNotFoundError):
            await store.get_authorized(case.id, who, need=AccessLevel.VIEWER)
        assert await store.effective_level(case.id, who) is None
    with pytest.raises(InvestigationNotFoundError):
        await store.get(case.id)
    with pytest.raises(InvestigationNotFoundError):
        await store.get_for_access_admin(case.id, AUTHOR)


async def test_a_removed_case_leaves_the_list_and_the_others_stay(
    store: InvestigationStore,
) -> None:
    kept = await store.create(AUTHOR, name="Kept")
    gone = await store.create(AUTHOR, name="Gone")

    await store.remove(gone.id, by=AUTHOR)

    assert [case.id for case, _ in await store.list_for(AUTHOR)] == [kept.id]


async def test_removing_keeps_the_record_and_says_who_and_when_in_the_history(
    store: InvestigationStore, schema: str
) -> None:
    """Catches a hard delete: the row and its grants must still be there, and the removal must be
    in the history with the account that did it."""
    case = await store.create(AUTHOR, name="Recorded")

    await store.remove(case.id, by=AUTHOR)

    conn = await asyncpg.connect(dsn=PostgresConfig.from_env().dsn)
    try:
        row = await conn.fetchrow(
            f'SELECT removed_by, removed_at FROM "{schema}".investigations WHERE id = $1', case.id
        )
        grants = await conn.fetchval(
            f'SELECT count(*) FROM "{schema}".investigation_grants WHERE investigation_id = $1',
            case.id,
        )
        history = await conn.fetch(
            f'SELECT action, changed_by FROM "{schema}".investigation_access_history '
            "WHERE investigation_id = $1 ORDER BY id",
            case.id,
        )
    finally:
        await conn.close()
    assert row is not None and row["removed_by"] == "alice" and row["removed_at"] is not None
    assert grants == 1
    assert [(h["action"], h["changed_by"]) for h in history][-1] == ("remove", "alice")


async def test_removing_a_case_twice_is_not_found_the_second_time(
    store: InvestigationStore,
) -> None:
    case = await store.create(AUTHOR, name="Once")
    await store.remove(case.id, by=AUTHOR)
    with pytest.raises(InvestigationNotFoundError):
        await store.remove(case.id, by=AUTHOR)


async def test_a_case_branched_from_a_removed_case_keeps_working(
    store: InvestigationStore,
) -> None:
    """The branch points at its source; removing the source must not break or remove the branch."""
    source = await store.create(AUTHOR, name="Source")
    branch = await store.create(AUTHOR, name="Branch", branched_from=source.id)

    await store.remove(source.id, by=AUTHOR)

    assert (await store.get_authorized(branch.id, AUTHOR, need=AccessLevel.AUTHOR)).id == branch.id
