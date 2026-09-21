"""`services/api/pattern_store.py`'s `PatternStore` — direct, live-Postgres correctness, the
same "own its access-control proof rather than only through route-level fakes" discipline
`test_sites_store.py` already established for `SiteStore`. `06_DECISIONS.md` ADR-032/036/040,
`docs/02_GLASS_FRONTEND.md` §3.3.
"""

from __future__ import annotations

import pytest
from services.api.config import PostgresConfig
from services.api.pattern_store import PatternNotFoundError, PatternStore

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
    s = await PatternStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


async def test_a_first_save_starts_at_version_one(store: PatternStore) -> None:
    saved = await store.save(OWNER, pattern_id=None, name="Common contacts", definition=_pattern())
    assert saved.version == 1
    assert saved.owner_id == OWNER.id
    fetched = await store.get(saved.pattern_id)
    assert fetched == saved


async def test_saving_again_under_the_same_pattern_id_adds_a_version_not_an_overwrite(
    store: PatternStore,
) -> None:
    first = await store.save(OWNER, pattern_id=None, name="Common contacts", definition=_pattern())
    widened = _pattern().model_copy(update={"limit": 500})
    second = await store.save(
        OWNER, pattern_id=first.pattern_id, name="Common contacts", definition=widened
    )

    assert second.version == 2
    assert second.pattern_id == first.pattern_id
    # The first version is not overwritten — still loadable by its own version number.
    reloaded_v1 = await store.get(first.pattern_id, version=1)
    assert reloaded_v1 == first
    reloaded_latest = await store.get(first.pattern_id)
    assert reloaded_latest == second


async def test_list_returns_the_latest_version_only_once_per_pattern(store: PatternStore) -> None:
    # Assertions below only ever inspect rows matching `first.pattern_id` — the store is real
    # Postgres, shared across test runs with no per-test reset (matching `test_sites_store.py`'s
    # own discipline of scoping each assertion to the object it just created), so `list_authorized`
    # may legitimately also return patterns other tests in this session saved under `OWNER`.
    first = await store.save(OWNER, pattern_id=None, name="Common contacts", definition=_pattern())
    await store.save(OWNER, pattern_id=first.pattern_id, name="Common contacts", definition=_pattern())

    listed = await store.list_authorized(OWNER)
    matching = [s for s in listed if s.pattern_id == first.pattern_id]
    assert len(matching) == 1  # one row per pattern_id, not one row per version
    assert matching[0].version == 2  # the latest version, not the first


async def test_a_missing_pattern_id_raises_not_found(store: PatternStore) -> None:
    with pytest.raises(PatternNotFoundError):
        await store.get("no-such-pattern")


async def test_a_pattern_owned_by_a_different_analyst_is_not_found_not_forbidden(
    store: PatternStore,
) -> None:
    """Existence-leak discipline, matching `InvestigationNotFoundError`'s own doc comment: a
    different owner and no-such-pattern collapse to the same error rather than a distinguishable
    403 — the same shape ADR-036/040 require for a saved pattern specifically, since it names no
    share target at all yet, not merely a narrower one."""
    saved = await store.save(OWNER, pattern_id=None, name="Common contacts", definition=_pattern())
    with pytest.raises(PatternNotFoundError):
        await store.get_authorized(saved.pattern_id, OTHER_ANALYST)


async def test_a_different_analyst_cannot_save_a_new_version_of_someone_elses_pattern(
    store: PatternStore,
) -> None:
    saved = await store.save(OWNER, pattern_id=None, name="Common contacts", definition=_pattern())
    with pytest.raises(PatternNotFoundError):
        await store.save(
            OTHER_ANALYST, pattern_id=saved.pattern_id, name="Hijacked", definition=_pattern()
        )


async def test_list_never_returns_another_analysts_pattern(store: PatternStore) -> None:
    await store.save(OWNER, pattern_id=None, name="Common contacts", definition=_pattern())
    listed = await store.list_authorized(OTHER_ANALYST)
    assert listed == []
