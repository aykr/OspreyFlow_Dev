"""`services/api/monitors.py`'s `MonitorStore` — direct, live-Postgres correctness, mirroring
`test_hotlists.py`/`test_pattern_store.py`'s own shape. `06_DECISIONS.md` ADR-036/037,
Phase 7 Stage 6b.
"""

from __future__ import annotations

import pytest
from services.api.config import PostgresConfig
from services.api.monitors import MonitorNotFoundError, MonitorStore
from services.api.pattern_store import PatternStore

from schemas.domain import PatternEdge, PatternNode, PatternQuery, Principal

OWNER = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
OTHER_ANALYST = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-1")


def _pattern() -> PatternQuery:
    return PatternQuery(
        nodes=[
            PatternNode(var="p", entity_type="Person"),
            PatternNode(var="e", entity_type="Endpoint"),
        ],
        edges=[PatternEdge(edge_type="USES", from_var="p", to_var="e")],
    )


@pytest.fixture
async def store():
    s = await MonitorStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


@pytest.fixture
async def pattern_store():
    s = await PatternStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


async def test_create_returns_a_monitor_owned_by_the_creating_principal(
    store: MonitorStore, pattern_store: PatternStore
) -> None:
    saved = await pattern_store.save(
        OWNER, pattern_id=None, name="Monitor fixture 1", definition=_pattern()
    )
    monitor = await store.create(OWNER, pattern_id=saved.pattern_id)
    assert monitor.owner_id == OWNER.id
    assert monitor.pattern_id == saved.pattern_id
    fetched = await store.get_authorized(monitor.id, OWNER)
    assert fetched == monitor


async def test_a_missing_monitor_id_raises_not_found(store: MonitorStore) -> None:
    with pytest.raises(MonitorNotFoundError):
        await store.get_authorized("no-such-monitor", OWNER)


async def test_a_monitor_owned_by_a_different_analyst_is_not_found_not_forbidden(
    store: MonitorStore, pattern_store: PatternStore
) -> None:
    saved = await pattern_store.save(
        OWNER, pattern_id=None, name="Monitor fixture 2", definition=_pattern()
    )
    monitor = await store.create(OWNER, pattern_id=saved.pattern_id)
    with pytest.raises(MonitorNotFoundError):
        await store.get_authorized(monitor.id, OTHER_ANALYST)


async def test_list_never_returns_another_analysts_monitor(
    store: MonitorStore, pattern_store: PatternStore
) -> None:
    saved = await pattern_store.save(
        OWNER, pattern_id=None, name="Monitor fixture 3", definition=_pattern()
    )
    await store.create(OWNER, pattern_id=saved.pattern_id)
    listed = await store.list_authorized(OTHER_ANALYST)
    assert listed == [] or all(m.owner_id != OWNER.id for m in listed)


async def test_list_all_active_returns_monitors_regardless_of_owner(
    store: MonitorStore, pattern_store: PatternStore
) -> None:
    mine_pattern = await pattern_store.save(
        OWNER, pattern_id=None, name="Monitor fixture 4", definition=_pattern()
    )
    theirs_pattern = await pattern_store.save(
        OTHER_ANALYST, pattern_id=None, name="Monitor fixture 5", definition=_pattern()
    )
    mine = await store.create(OWNER, pattern_id=mine_pattern.pattern_id)
    theirs = await store.create(OTHER_ANALYST, pattern_id=theirs_pattern.pattern_id)

    all_active = await store.list_all_active()
    ids = {m.id for m in all_active}
    assert mine.id in ids
    assert theirs.id in ids


async def test_turning_the_same_pattern_into_a_monitor_twice_is_rejected_not_duplicated(
    store: MonitorStore, pattern_store: PatternStore
) -> None:
    """`UNIQUE (pattern_id, owner_id)` (`monitors.py`'s own bootstrap SQL) — an upsert-shaped
    no-op error, not a silently doubled future alert stream for the same match."""
    saved = await pattern_store.save(
        OWNER, pattern_id=None, name="Monitor fixture 6", definition=_pattern()
    )
    await store.create(OWNER, pattern_id=saved.pattern_id)
    with pytest.raises(Exception):  # asyncpg.UniqueViolationError, not re-wrapped by this store
        await store.create(OWNER, pattern_id=saved.pattern_id)
