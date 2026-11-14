"""`services/api/hotlists.py`'s `HotlistStore` — direct, live-Postgres correctness, the same
"own its access-control proof rather than only through route-level fakes" discipline
`test_pattern_store.py`/`test_alerts.py` already establish. `06_DECISIONS.md` ADR-038,
Phase 7 Stage 6b.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from services.api.config import PostgresConfig
from services.api.hotlists import HotlistNotFoundError, HotlistStore

from conduit_common.identity import new_id

from schemas.domain import Principal

OWNER = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
OTHER_ANALYST = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-1")


@pytest.fixture
async def store():
    s = await HotlistStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


async def test_create_returns_a_hotlist_owned_by_the_creating_principal(
    store: HotlistStore,
) -> None:
    hotlist = await store.create(OWNER, identifier="+44-fixture-1", review_date=date(2027, 1, 1))
    assert hotlist.owner_id == OWNER.id
    assert hotlist.identifier == "+44-fixture-1"
    fetched = await store.get_authorized(hotlist.id, OWNER)
    assert fetched == hotlist


async def test_a_missing_hotlist_id_raises_not_found(store: HotlistStore) -> None:
    with pytest.raises(HotlistNotFoundError):
        await store.get_authorized("no-such-hotlist", OWNER)


async def test_a_hotlist_owned_by_a_different_analyst_is_not_found_not_forbidden(
    store: HotlistStore,
) -> None:
    """Existence-leak discipline, matching `PatternNotFoundError`'s own precedent: a different
    owner and no-such-hotlist collapse to the same error, per `06_DECISIONS.md` ADR-038's own
    "what a second analyst observes of a hotlist they do not own": nothing, not a 403."""
    hotlist = await store.create(OWNER, identifier="+44-fixture-2", review_date=date(2027, 1, 1))
    with pytest.raises(HotlistNotFoundError):
        await store.get_authorized(hotlist.id, OTHER_ANALYST)


async def test_list_never_returns_another_analysts_hotlist(store: HotlistStore) -> None:
    await store.create(OWNER, identifier="+44-fixture-3", review_date=date(2027, 1, 1))
    listed = await store.list_authorized(OTHER_ANALYST)
    assert listed == [] or all(h.owner_id != OWNER.id for h in listed)


async def test_list_all_active_returns_hotlists_regardless_of_owner(store: HotlistStore) -> None:
    """The evaluator's own unscoped population read (`HotlistStore.list_all_active`'s own
    docstring) — not exposed through any route, but proven here to actually return across
    owners, the property the evaluator depends on to find a match for *any* owner's hotlist."""
    mine = await store.create(OWNER, identifier="+44-fixture-4", review_date=date(2027, 1, 1))
    theirs = await store.create(
        OTHER_ANALYST, identifier="+44-fixture-5", review_date=date(2027, 1, 1)
    )
    all_active = await store.list_all_active()
    ids = {h.id for h in all_active}
    assert mine.id in ids
    assert theirs.id in ids


async def test_review_date_and_created_at_round_trip(store: HotlistStore) -> None:
    review_date = date(2028, 6, 15)
    hotlist = await store.create(OWNER, identifier="+44-fixture-6", review_date=review_date)
    assert hotlist.review_date == review_date
    assert hotlist.created_at.tzinfo is not None
    assert hotlist.created_at <= datetime.now(UTC)


# --- ADR-127 decision 7(b): the identifier is canonical, the typed form kept for display ---------


def _drama_number() -> tuple[str, str]:
    """An Ofcom drama-range number, unique to the call, as typed (national form) and as stored. Drawn
    from 07700 900300-900399: the PID reserves 900600-900899 and the two numbers its search relies on,
    and no other file may write them (`test_pid_plan.py`'s J2)."""
    import random

    last = random.randint(300, 399)
    return f"07700 900{last:03d}", f"+447700900{last:03d}"


async def test_a_number_typed_in_national_form_is_stored_in_e164_and_the_typed_form_is_kept(
    store: HotlistStore,
) -> None:
    typed, canonical = _drama_number()
    hotlist = await store.create(OWNER, identifier=typed, review_date=date(2027, 1, 1))
    assert hotlist.identifier == canonical
    assert hotlist.identifier_typed == typed
    assert hotlist.identifier_canonical is True
    assert await store.get_authorized(hotlist.id, OWNER) == hotlist
    assert [h for h in await store.list_authorized(OWNER) if h.id == hotlist.id] == [hotlist]


async def test_a_text_the_adapter_refuses_is_kept_as_written(store: HotlistStore) -> None:
    hotlist = await store.create(OWNER, identifier="+44-refused-x1", review_date=date(2027, 1, 1))
    assert hotlist.identifier == "+44-refused-x1" == hotlist.identifier_typed
    assert hotlist.identifier_canonical is False, "a text kept as written says so"
    assert (await store.get_authorized(hotlist.id, OWNER)).identifier == "+44-refused-x1"


async def _legacy(store: HotlistStore, identifier: str) -> str:
    """A row as the store wrote it before ADR-127: no typed form and no canonical flag."""
    hotlist_id = new_id()
    async with store._pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO hotlists (id, identifier, owner_id, review_date, status, created_at) "
            "VALUES ($1, $2, $3, $4, 'active', now())",
            hotlist_id,
            identifier,
            OWNER.id,
            date(2027, 1, 1),
        )
        await conn.execute(
            "UPDATE hotlists SET identifier_typed = NULL, identifier_canonical = NULL WHERE id = $1",
            hotlist_id,
        )
    return hotlist_id


async def _row(store: HotlistStore, hotlist_id: str) -> tuple[str, str | None, bool | None]:
    async with store._pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT identifier, identifier_typed, identifier_canonical FROM hotlists WHERE id = $1",
            hotlist_id,
        )
    assert row is not None
    return row["identifier"], row["identifier_typed"], row["identifier_canonical"]


async def test_an_existing_raw_row_is_canonicalised_when_the_store_connects_and_a_second_connect_changes_nothing(
    store: HotlistStore,
) -> None:
    typed, canonical = _drama_number()
    raw_id = await _legacy(store, typed)
    refused_id = await _legacy(store, "+44-legacy-refused")
    assert await _row(store, raw_id) == (typed, None, None)

    dsn = PostgresConfig.from_env().dsn
    first = await HotlistStore.connect(dsn)
    try:
        assert await _row(first, raw_id) == (canonical, typed, True)
        by_id = {h.id: h for h in await first.list_all_active()}
        assert by_id[raw_id].identifier_canonical is True
        assert by_id[refused_id].identifier_canonical is False
        # A refused row is kept as written, marked so, and counted.
        assert await _row(first, refused_id) == ("+44-legacy-refused", "+44-legacy-refused", False)
        assert first.not_canonical >= 1
    finally:
        await first.close()

    before = (await _row(store, raw_id), await _row(store, refused_id))
    second = await HotlistStore.connect(dsn)
    try:
        assert (await _row(second, raw_id), await _row(second, refused_id)) == before
    finally:
        await second.close()


async def test_connecting_says_how_many_rows_it_could_not_canonicalise(
    store: HotlistStore, caplog: pytest.LogCaptureFixture
) -> None:
    await _legacy(store, "+44-legacy-refused-2")
    import logging

    with caplog.at_level(logging.WARNING):
        again = await HotlistStore.connect(PostgresConfig.from_env().dsn)
    try:
        assert again.not_canonical >= 1
        assert any("hotlist" in r.message.lower() and "canonical" in r.message.lower() for r in caplog.records)
        assert "+44-legacy-refused-2" not in caplog.text, "the identifier is not written to the log"
    finally:
        await again.close()


# --- ADR-044 Amendment 1: a stopped hotlist says why ----------------------------------------------


async def test_a_stopped_hotlist_keeps_why_until_it_is_active_again(store) -> None:  # type: ignore[no-untyped-def]
    from services.api.watch_status import STOPPED_WHY

    hotlist = await store.create(OWNER, identifier="07700900188", review_date=date(2027, 1, 1))
    assert (await store.get_authorized(hotlist.id, OWNER)).stopped_why is None
    await store.set_status(hotlist.id, "stopped", "out_of_date")
    stopped = await store.get_authorized(hotlist.id, OWNER)
    assert (stopped.status, stopped.status_detail, stopped.stopped_why) == (
        "stopped", "out_of_date", STOPPED_WHY["out_of_date"])  # fmt: skip
    listed = [h for h in await store.list_authorized(OWNER) if h.id == hotlist.id]
    assert listed and listed[0].stopped_why == STOPPED_WHY["out_of_date"]
    await store.set_status(hotlist.id, "active")
    active = await store.get_authorized(hotlist.id, OWNER)
    assert (active.status, active.status_detail, active.stopped_why) == ("active", None, None)
    # Set active with a reason given by mistake: an active row never carries one, in the column itself
    # (not only as served: the read hides an active row's reason too, so each is held on its own).
    await store.set_status(hotlist.id, "active", "revoked")
    assert (await store.get_authorized(hotlist.id, OWNER)).status_detail is None
    import asyncpg

    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        assert await conn.fetchval("SELECT status_detail FROM hotlists WHERE id = $1", hotlist.id) is None
    finally:
        await conn.close()
    # A later stop with no reason given is served with none, never the one before it.
    await store.set_status(hotlist.id, "stopped")
    assert (await store.get_authorized(hotlist.id, OWNER)).status_detail is None
    # A reason this release does not know (a later one's) is served as none, never guessed.
    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        await conn.execute("UPDATE hotlists SET status_detail = 'a-later-release-s' WHERE id = $1", hotlist.id)
    finally:
        await conn.close()
    unknown = await store.get_authorized(hotlist.id, OWNER)
    assert (unknown.status, unknown.status_detail, unknown.stopped_why) == ("stopped", None, None)


# --- ADR-044 Amendment 2: three unreachable loads in a row, counted in the row ------------------


async def test_the_unreachable_count_outlives_a_restart_and_any_status_puts_it_back(store) -> None:  # type: ignore[no-untyped-def]
    """The real column: one statement adds one and answers the count; a new store over the same database (a
    restarted Conduit) reads what the last left; the row is served the count and its words while active;
    and `set_status`, any status, puts it back to 0 in the column itself."""
    from services.api.watch_status import active_note

    hotlist = await store.create(OWNER, identifier="07700900189", review_date=date(2027, 1, 1))
    assert (await store.get_authorized(hotlist.id, OWNER)).unreachable_in_a_row == 0
    first = await HotlistStore.connect(PostgresConfig.from_env().dsn)
    assert await first.count_unreachable(hotlist.id) == 1
    assert await first.count_unreachable(hotlist.id) == 2
    await first.close()  # the Conduit that counted it gone; a new one reads what it left
    restarted = await HotlistStore.connect(PostgresConfig.from_env().dsn)
    try:
        read = await restarted.get_authorized(hotlist.id, OWNER)
        assert (read.status, read.unreachable_in_a_row, read.status_note) == ("active", 2, active_note(2))
        assert await restarted.count_unreachable(hotlist.id) == 3
        await restarted.set_status(hotlist.id, "stopped", "unreachable")
        stopped = await restarted.get_authorized(hotlist.id, OWNER)
        assert (stopped.unreachable_in_a_row, stopped.status_note) == (0, None)  # stopped: its reason, no note
        await restarted.count_unreachable(hotlist.id)
        await restarted.set_status(hotlist.id, "active")
        async with restarted._pool.acquire() as conn:
            assert await conn.fetchval("SELECT unreachable_in_a_row FROM hotlists WHERE id = $1", hotlist.id) == 0
    finally:
        await restarted.close()


async def test_two_evaluators_counting_at_once_never_read_the_same_count(store) -> None:  # type: ignore[no-untyped-def]
    """ADR-044 Amendment 2, decision 2: the count is added and read in one statement, so two evaluators counting
    the same hotlist at once get 1 and 2, never both 1 (which would let three unreachable loads pass as two)."""
    import asyncio

    hotlist = await store.create(OWNER, identifier="07700900190", review_date=date(2027, 1, 1))
    other = await HotlistStore.connect(PostgresConfig.from_env().dsn)
    try:
        counts = await asyncio.gather(*(s.count_unreachable(hotlist.id) for s in (store, other, store, other)))
        assert sorted(counts) == [1, 2, 3, 4]
    finally:
        await other.close()


async def test_a_stopped_hotlist_is_still_listed_for_evaluation(store) -> None:  # type: ignore[no-untyped-def]
    """ADR-044 Amendment 2, decision 3: one stopped `unreachable` is evaluated again at each load, so the first load
    that can act as its owner makes it active again ("It is tried again at the next")."""
    hotlist = await store.create(OWNER, identifier="07700900191", review_date=date(2027, 1, 1))
    await store.set_status(hotlist.id, "stopped", "unreachable")
    assert hotlist.id in {h.id for h in await store.list_all_active()}
