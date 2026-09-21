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
