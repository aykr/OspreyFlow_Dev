"""ADR-052 stage 1: a case has a name, per-account grants and a unit-wide level, and every read of
a case names the level it needs. Real Postgres, like the other stores' own tests (`test_alerts.py`);
a fresh schema per test so none of them sees another's cases."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import asyncpg
import pytest
from services.api.config import PostgresConfig
from services.api.investigations import (
    AccessLevel,
    InsufficientAccessError,
    InvestigationNotFoundError,
    InvestigationStore,
)

from schemas.domain import Interval, Principal

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


# --- ADR-128 decision 2: the window a branch made from what is lit was made with ----------------
# Live (Postgres). The route tests use a stand-in store; these show the window is stored with the
# case and comes back from every read that builds a case, and that a database from before the
# change gains the columns on start with its cases reading no window.


async def test_a_branchs_window_is_stored_and_read_back_by_every_read(
    store: InvestigationStore,
) -> None:
    window = Interval(
        valid_from=datetime(2026, 1, 5, tzinfo=UTC), valid_to=datetime(2026, 4, 30, tzinfo=UTC)
    )
    source = await store.create(AUTHOR, name="Source")
    held = await store.create(AUTHOR, name="Lit", branched_from=source.id, branch_window=window)
    plain = await store.create(AUTHOR, name="Plain", branched_from=source.id)

    assert held.branch_window == window
    assert (await store.get(held.id)).branch_window == window
    assert (await store.get_authorized(held.id, AUTHOR, need=AccessLevel.VIEWER)).branch_window == (
        window
    )
    listed = {c.id: c.branch_window for c, _ in await store.list_for(AUTHOR)}
    assert listed[held.id] == window
    assert listed[plain.id] is None and listed[source.id] is None


async def test_a_database_from_before_the_window_gains_the_columns_and_reads_none(
    schema: str,
) -> None:
    dsn = f"{PostgresConfig.from_env().dsn}?search_path={schema}"
    first = await InvestigationStore.connect(dsn)
    case = await first.create(AUTHOR, name="Old")
    await first.close()
    conn = await asyncpg.connect(dsn=dsn)
    await conn.execute("ALTER TABLE investigations DROP COLUMN branch_valid_from")
    await conn.execute("ALTER TABLE investigations DROP COLUMN branch_valid_to")
    await conn.close()

    reopened = await InvestigationStore.connect(dsn)
    try:
        assert (await reopened.get(case.id)).branch_window is None
    finally:
        await reopened.close()


# --- ADR-084: which case tabs an account has closed -----------------------------------------------
# The route tests (`test_branch_tabs_routes.py`) use a stand-in store, so they cannot show that the
# database keeps one row per account and case, or that one account's rows are invisible to another.
# These do, against real Postgres.


async def test_a_new_case_has_an_open_tab(store: InvestigationStore) -> None:
    await store.create(AUTHOR, name="Fixture Corp")

    assert await store.hidden_tab_ids(AUTHOR) == set()


async def test_hiding_a_tab_is_remembered_and_reopening_it_forgets_it(
    store: InvestigationStore,
) -> None:
    case = await store.create(AUTHOR, name="Fixture Corp")

    await store.set_tab_hidden(AUTHOR, case.id, True)
    assert await store.hidden_tab_ids(AUTHOR) == {case.id}

    await store.set_tab_hidden(AUTHOR, case.id, False)
    assert await store.hidden_tab_ids(AUTHOR) == set()


async def test_hiding_a_tab_twice_is_one_row_not_an_error(store: InvestigationStore) -> None:
    case = await store.create(AUTHOR, name="Fixture Corp")

    await store.set_tab_hidden(AUTHOR, case.id, True)
    await store.set_tab_hidden(AUTHOR, case.id, True)

    assert await store.hidden_tab_ids(AUTHOR) == {case.id}


async def test_one_accounts_closed_tabs_are_not_another_accounts(
    store: InvestigationStore,
) -> None:
    """The database, not the route, keeps the flags apart: the account is in the `WHERE`."""
    case = await store.create(AUTHOR, name="Fixture Corp")

    await store.set_tab_hidden(AUTHOR, case.id, True)

    assert await store.hidden_tab_ids(COLLEAGUE) == set()
    await store.set_tab_hidden(COLLEAGUE, case.id, False)  # Bob reopening his own (absent) flag...
    assert await store.hidden_tab_ids(AUTHOR) == {case.id}  # ...never touches Alice's.


async def test_a_flag_cannot_be_written_for_a_case_that_does_not_exist(
    store: InvestigationStore,
) -> None:
    """The row references the case, so the database refuses a flag on an id with no case."""
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await store.set_tab_hidden(AUTHOR, "no-such-case", True)


# --- ADR-126 unit D1: a case's domain packs ---------------------------------------------------


async def _raw_domains(store: InvestigationStore, case_id: str) -> list[str] | None:
    """The column as stored, not as the model reads it: NULL must stay distinguishable from {}."""
    async with store._pool.acquire() as conn:
        value = await conn.fetchval("SELECT domains FROM investigations WHERE id = $1", case_id)
    return None if value is None else list(value)


async def test_the_packs_are_stored_and_read_back_through_every_read(
    store: InvestigationStore,
) -> None:
    """The plant is a column list without `domains`: each read below builds its own."""
    case = await store.create(AUTHOR, name="Mixed", domains=["niem", "fibo", "niem"])

    assert case.domains == ["fibo", "niem"], "sorted, without repeats"
    assert await _raw_domains(store, case.id) == ["fibo", "niem"]
    assert (await store.get(case.id)).domains == ["fibo", "niem"]
    authorised = await store.get_authorized(case.id, AUTHOR, need=AccessLevel.VIEWER)
    assert authorised.domains == ["fibo", "niem"]
    listed = [c for c, _ in await store.list_for(AUTHOR)]
    assert [(c.id, c.domains) for c in listed] == [(case.id, ["fibo", "niem"])]
    found = await store.effective_level(case.id, AUTHOR)
    assert found is AccessLevel.AUTHOR


async def test_null_reads_as_empty_and_an_empty_choice_is_not_null(
    store: InvestigationStore,
) -> None:
    never = await store.create(AUTHOR, name="Never chosen")
    pole = await store.create(AUTHOR, name="POLE chosen", domains=[])

    assert never.domains == [] and pole.domains == []
    assert await _raw_domains(store, never.id) is None
    assert await _raw_domains(store, pole.id) == []
    read = await store.get_authorized(never.id, AUTHOR, need=AccessLevel.VIEWER)
    assert read.domains == []


async def test_an_unknown_pack_is_refused_on_the_way_in(store: InvestigationStore) -> None:
    case = await store.create(AUTHOR, name="Fine", domains=["fibo"])

    with pytest.raises(ValueError, match="domains"):
        await store.create(AUTHOR, name="Bad", domains=["fibo", "gone"])
    with pytest.raises(ValueError, match="domains"):
        await store.set_domains(case.id, ["gone"], by=AUTHOR)
    with pytest.raises(ValueError, match="domains"):
        await store.set_domains_if_unset(case.id, ["gone"], by=AUTHOR)

    assert [c.name for c, _ in await store.list_for(AUTHOR)] == ["Fine"], "no case was left behind"
    assert await _raw_domains(store, case.id) == ["fibo"]


async def test_a_stored_pack_the_model_does_not_know_is_dropped_with_a_warning(
    store: InvestigationStore, caplog: pytest.LogCaptureFixture
) -> None:
    """Written by hand, or left by a removed pack. It must never fail the read: every case-scoped
    route reads the case through `get_authorized`. The plant is strict validation on read."""
    case = await store.create(AUTHOR, name="Odd", domains=["fibo"])
    async with store._pool.acquire() as conn:
        await conn.execute(
            "UPDATE investigations SET domains = ARRAY['fibo','gone'] WHERE id = $1", case.id
        )

    with caplog.at_level(logging.WARNING, logger="services.api.investigations"):
        authorised = await store.get_authorized(case.id, AUTHOR, need=AccessLevel.VIEWER)
        raw = await store.get(case.id)
        listed = [c for c, _ in await store.list_for(AUTHOR)]

    assert authorised.domains == ["fibo"]
    assert raw.domains == ["fibo"]
    assert [c.domains for c in listed] == [["fibo"]]
    warned = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warned, "a dropped value is logged, not silent"
    assert all("gone" in r.getMessage() and case.id in r.getMessage() for r in warned)


async def test_set_domains_changes_the_packs_and_is_in_the_access_history(
    store: InvestigationStore,
) -> None:
    case = await store.create(AUTHOR, name="Case", domains=["fibo"])

    await store.set_domains(case.id, ["stix", "niem"], by=AUTHOR)
    await store.set_domains(case.id, [], by=AUTHOR)

    assert await _raw_domains(store, case.id) == []
    history = await store.access_history(case.id)
    assert [(h.action, h.subject, h.changed_by) for h in history if h.action == "domains"] == [
        ("domains", "niem,stix", "alice"),
        ("domains", "pole", "alice"),
    ]


async def test_set_domains_on_a_case_that_does_not_exist_is_not_found(
    store: InvestigationStore,
) -> None:
    with pytest.raises(InvestigationNotFoundError):
        await store.set_domains("no-such-case", ["fibo"], by=AUTHOR)


async def test_set_domains_if_unset_sets_only_while_null_and_never_overwrites(
    store: InvestigationStore,
) -> None:
    unset = await store.create(AUTHOR, name="Unset")
    chosen = await store.create(AUTHOR, name="Chosen", domains=["stix"])
    pole = await store.create(AUTHOR, name="POLE", domains=[])

    assert await store.set_domains_if_unset(unset.id, ["fibo"], by=AUTHOR) is True
    assert await store.set_domains_if_unset(unset.id, ["niem"], by=AUTHOR) is False
    assert await store.set_domains_if_unset(chosen.id, ["fibo"], by=AUTHOR) is False
    assert await store.set_domains_if_unset(pole.id, ["fibo"], by=AUTHOR) is False

    assert await _raw_domains(store, unset.id) == ["fibo"]
    assert await _raw_domains(store, chosen.id) == ["stix"]
    assert await _raw_domains(store, pole.id) == [], "a choice of POLE is a choice"
    only_one = [h for h in await store.access_history(unset.id) if h.action == "domains"]
    assert [(h.subject, h.changed_by) for h in only_one] == [("fibo", "alice")]
    assert [h for h in await store.access_history(chosen.id) if h.action == "domains"] == []


async def test_two_seeds_racing_set_the_packs_once(store: InvestigationStore) -> None:
    """The `UPDATE ... WHERE domains IS NULL` is one statement, so exactly one caller wins."""
    case = await store.create(AUTHOR, name="Raced")

    results = await asyncio.gather(
        *(store.set_domains_if_unset(case.id, [pack], by=AUTHOR) for pack in ("fibo", "niem"))
    )

    assert sorted(results) == [False, True]
    assert len([h for h in await store.access_history(case.id) if h.action == "domains"]) == 1


async def test_the_column_is_added_to_a_database_from_before_the_change(
    schema: str,
) -> None:
    """`_DOMAIN_SQL` runs every start, so an older database gains the column, and a start with the
    column already there is not an error."""
    dsn = f"{PostgresConfig.from_env().dsn}?search_path={schema}"
    first = await InvestigationStore.connect(dsn)
    case = await first.create(AUTHOR, name="Older")
    async with first._pool.acquire() as conn:
        await conn.execute("ALTER TABLE investigations DROP COLUMN domains")
    await first.close()

    second = await InvestigationStore.connect(dsn)
    third = await InvestigationStore.connect(dsn)
    try:
        read = await second.get_authorized(case.id, AUTHOR, need=AccessLevel.VIEWER)
        assert read.domains == []
        assert await _raw_domains(second, case.id) is None
    finally:
        await second.close()
        await third.close()


async def test_a_case_says_whether_anyone_chose_so_a_branch_can_inherit_the_stored_value(
    store: InvestigationStore,
) -> None:
    """ADR-126 decision 2. The read-side list is `[]` for NULL and for `{}`; `domains_chosen` is
    what tells them apart, through every read, and a case created from `domains_to_inherit()`
    stores exactly what its parent did. The plant is inheriting the read-side list."""
    never = await store.create(AUTHOR, name="Never")
    pole = await store.create(AUTHOR, name="POLE", domains=[])
    mixed = await store.create(AUTHOR, name="Mixed", domains=["niem"])

    for case, chosen in ((never, False), (pole, True), (mixed, True)):
        authorised = await store.get_authorized(case.id, AUTHOR, need=AccessLevel.VIEWER)
        listed = {c.id: c for c, _ in await store.list_for(AUTHOR)}[case.id]
        assert case.domains_chosen is chosen
        assert (await store.get(case.id)).domains_chosen is chosen
        assert authorised.domains_chosen is chosen
        assert listed.domains_chosen is chosen

    stored: dict[str, list[str] | None] = {}
    for parent in (never, pole, mixed):
        read = await store.get_authorized(parent.id, AUTHOR, need=AccessLevel.VIEWER)
        branch = await store.create(
            AUTHOR,
            name=f"Branch of {parent.name}",
            branched_from=parent.id,
            domains=read.domains_to_inherit(),
        )
        stored[parent.name] = await _raw_domains(store, branch.id)
    assert stored == {"Never": None, "POLE": [], "Mixed": ["niem"]}


async def test_change_applies_the_name_and_the_packs_together_and_records_both(
    store: InvestigationStore,
) -> None:
    case = await store.create(AUTHOR, name="Old", domains=["fibo"])

    await store.change(case.id, name=" New ", domains=["niem"], by=AUTHOR)

    read = await store.get_authorized(case.id, AUTHOR, need=AccessLevel.VIEWER)
    assert (read.name, read.domains) == ("New", ["niem"])
    actions = [(h.action, h.subject) for h in await store.access_history(case.id)]
    assert ("rename", "New") in actions and ("domains", "niem") in actions


async def test_change_of_a_removed_case_writes_and_records_nothing(
    store: InvestigationStore,
) -> None:
    """The case is removed before the change lands: neither field is written, nothing recorded."""
    case = await store.create(AUTHOR, name="Old", domains=["fibo"])
    await store.remove(case.id, by=AUTHOR)
    before = await store.access_history(case.id)

    with pytest.raises(InvestigationNotFoundError):
        await store.change(case.id, name="New", domains=["niem"], by=AUTHOR)

    assert await store.access_history(case.id) == before
    async with store._pool.acquire() as conn:
        row = await conn.fetchrow("SELECT name, domains FROM investigations WHERE id = $1", case.id)
    assert (row["name"], list(row["domains"])) == ("Old", ["fibo"])


async def test_change_refuses_a_blank_name_or_an_unknown_pack_before_writing(
    store: InvestigationStore,
) -> None:
    case = await store.create(AUTHOR, name="Old", domains=["fibo"])

    with pytest.raises(ValueError, match="name"):
        await store.change(case.id, name="  ", domains=["niem"], by=AUTHOR)
    with pytest.raises(ValueError, match="domains"):
        await store.change(case.id, name="New", domains=["gone"], by=AUTHOR)

    read = await store.get_authorized(case.id, AUTHOR, need=AccessLevel.VIEWER)
    assert (read.name, read.domains) == ("Old", ["fibo"])
