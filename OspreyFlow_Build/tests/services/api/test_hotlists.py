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
