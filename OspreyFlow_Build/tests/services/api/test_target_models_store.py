"""`PostgresTargetModelStore` against real Postgres (`make dev-up`, under the stack lease).

The rules of `test_target_models.py` run on the real store, each test in a schema of its own so no
other test's rows decide them. Then the half memory cannot prove: two requests at once cannot both
open a draft, and the one-live and one-draft indexes refuse a second row written past the store
(ADR-140 decision 5, R12).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest
from services.api.config import PostgresConfig
from services.api.target_models import (
    CORE_TYPES_FOR_TESTS,
    PostgresTargetModelStore,
    TargetModelRefused,
)

from conduit_common.identity import new_id
from schemas.dataset_model import ModelExtension, TargetModelDraftInput
from schemas.domain import Principal

ENGINEER = Principal(id="d.engineer", clearance="OFFICIAL", org_unit="unit-1")


@pytest.fixture
async def dsn() -> AsyncIterator[str]:
    """A schema of its own (asyncpg passes `search_path` on as a server setting)."""
    base = PostgresConfig.from_env().dsn
    schema = f"target_models_{new_id().lower()}"
    admin = await asyncpg.connect(base)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    yield f"{base}{'&' if '?' in base else '?'}search_path={schema}"
    await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
    await admin.close()


@pytest.fixture
async def store(dsn: str) -> AsyncIterator[PostgresTargetModelStore]:
    held = await PostgresTargetModelStore.connect(dsn, core_types=CORE_TYPES_FOR_TESTS)
    yield held
    await held.close()


def _vessel(added_in: int, retired_in: int | None = None) -> ModelExtension:
    return ModelExtension(
        name="Vessel", kind="entity_type", added_in=added_in, retired_in=retired_in
    )


async def test_the_versions_on_postgres(store: PostgresTargetModelStore) -> None:
    """Version 1 bare POLE; a draft copies live; making it live makes the old previous; a revert
    is N+2; an extension is retired, never deleted; a core type is refused."""
    dataset = new_id()
    first = await store.open_draft(dataset, ENGINEER)
    assert (first.version, first.packs) == (1, {})
    await store.save_draft(
        dataset, TargetModelDraftInput(packs={"fibo": 3}, extensions=[_vessel(1)]), ENGINEER
    )
    await store.make_live(dataset, 1, ENGINEER)
    await store.open_draft(dataset, ENGINEER)
    with pytest.raises(TargetModelRefused, match="already has a draft"):
        await store.open_draft(dataset, ENGINEER)
    with pytest.raises(TargetModelRefused, match="retired, never deleted"):
        await store.save_draft(dataset, TargetModelDraftInput(packs={"fibo": 3}), ENGINEER)
    with pytest.raises(TargetModelRefused, match="POLE core type"):
        await store.save_draft(
            dataset,
            TargetModelDraftInput(
                extensions=[_vessel(1), ModelExtension(name="Person", kind="entity_type",
                                                       added_in=2)]),
            ENGINEER,
        )  # fmt: skip
    await store.save_draft(
        dataset, TargetModelDraftInput(packs={"fibo": 3, "stix": 1}, extensions=[_vessel(1)]),
        ENGINEER,
    )  # fmt: skip
    live, before = await store.make_live(dataset, 2, ENGINEER)
    assert (live.state, live.packs) == ("live", {"fibo": 3, "stix": 1})
    assert before is not None and before.state == "previous"
    reverted = await store.revert(dataset, 1, ENGINEER)
    assert (reverted.version, reverted.reverted_from, reverted.packs) == (3, 1, {"fibo": 3})
    states = [(m.version, m.state) for m in await store.versions(dataset)]
    assert states == [(1, "previous"), (2, "live"), (3, "draft")]
    (one,) = [m for m in await store.versions(dataset) if m.version == 1]
    assert one.packs == {"fibo": 3} and one.extensions == [_vessel(1)]
    await store.discard_draft(dataset)
    assert await store.draft(dataset) is None


def _all_at_once(monkeypatch: pytest.MonkeyPatch, *, locked: bool, callers: int) -> None:
    """Every caller waits, its transaction open, until all have one: only then is the lock taken
    (or, planted out, not), so the calls truly overlap rather than running one after another as
    the pool's connections open."""
    real = PostgresTargetModelStore._locked
    met = asyncio.Barrier(callers)

    async def at_once(self: Any, conn: Any, dataset_id: str) -> None:
        await asyncio.wait_for(met.wait(), 20)
        if locked:
            await real(self, conn, dataset_id)

    monkeypatch.setattr(PostgresTargetModelStore, "_locked", at_once)


async def test_two_drafts_opened_at_once_one_is_refused(
    store: PostgresTargetModelStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    _all_at_once(monkeypatch, locked=True, callers=4)
    dataset = new_id()
    results = await asyncio.gather(
        *(store.open_draft(dataset, ENGINEER) for _ in range(4)), return_exceptions=True
    )
    opened = [r for r in results if not isinstance(r, BaseException)]
    refused = [r for r in results if isinstance(r, TargetModelRefused)]
    assert len(opened) == 1 and len(refused) == 3, results
    assert [m.state for m in await store.versions(dataset)] == ["draft"]


async def test_the_drafts_race_fails_with_the_lock_removed(
    store: PostgresTargetModelStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, red (the round-1 review's must-fix 8): the same four drafts at once, the advisory
    lock planted out. They race past the store's own check to the indexes, which refuse with a raw
    unique violation (a 500 at the route), not in words."""
    _all_at_once(monkeypatch, locked=False, callers=4)
    dataset = new_id()
    results = await asyncio.gather(
        *(store.open_draft(dataset, ENGINEER) for _ in range(4)), return_exceptions=True
    )
    refused_in_words = [r for r in results if isinstance(r, TargetModelRefused)]
    raw = [r for r in results if isinstance(r, asyncpg.UniqueViolationError)]
    assert len(refused_in_words) < 3 and raw, results


async def test_two_make_lives_at_once_one_is_refused_in_words(
    store: PostgresTargetModelStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two *Make live*s of the same draft at once: one makes it live, the other is refused in
    words (the draft it names is gone), and there is one live version."""
    dataset = new_id()
    await store.open_draft(dataset, ENGINEER)
    _all_at_once(monkeypatch, locked=True, callers=2)
    results = await asyncio.gather(
        *(store.make_live(dataset, 1, ENGINEER) for _ in range(2)), return_exceptions=True
    )
    made = [r for r in results if not isinstance(r, BaseException)]
    refused = [r for r in results if isinstance(r, TargetModelRefused)]
    assert len(made) == 1 and len(refused) == 1, results
    assert [m.state for m in await store.versions(dataset)] == ["live"]


async def test_the_indexes_refuse_a_second_live_or_draft_written_past_the_store(
    store: PostgresTargetModelStore, dsn: str
) -> None:
    """The indexes are the last word: a row written straight into the table, past the store's
    rules, is refused for a second draft and a second live version."""
    dataset = new_id()
    await store.open_draft(dataset, ENGINEER)
    await store.make_live(dataset, 1, ENGINEER)
    await store.open_draft(dataset, ENGINEER)
    conn = await asyncpg.connect(dsn)
    try:
        for state, version in (("draft", 9), ("live", 10)):
            with pytest.raises(asyncpg.UniqueViolationError):
                await conn.execute(
                    "INSERT INTO target_models (dataset_id, version, state, content, created_at, "
                    "created_by) VALUES ($1, $2, $3, '{}'::jsonb, now(), 'x')",
                    dataset,
                    version,
                    state,
                )
    finally:
        await conn.close()


async def test_the_index_check_fails_with_the_indexes_dropped(
    store: PostgresTargetModelStore, dsn: str
) -> None:
    """Rule 15, red: with the two indexes dropped, the second rows go in."""
    dataset = new_id()
    await store.open_draft(dataset, ENGINEER)
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("DROP INDEX target_models_one_live; DROP INDEX target_models_one_draft")
        await conn.execute(
            "INSERT INTO target_models (dataset_id, version, state, content, created_at, "
            "created_by) VALUES ($1, 9, 'draft', '{}'::jsonb, now(), 'x')",
            dataset,
        )
        assert await conn.fetchval(
            "SELECT count(*) FROM target_models WHERE dataset_id = $1 AND state = 'draft'", dataset
        ) == 2  # fmt: skip
    finally:
        await conn.close()


async def test_two_link_types_added_at_once_both_land_in_the_draft(
    store: PostgresTargetModelStore,
) -> None:
    """ADR-143 decision 9 (L3.5): two data engineers accepting two proposed link types at once. Each
    `add_extension` reads and writes the draft under the dataset's lock, so neither is lost and only
    one draft is opened (red with the lock removed: both open a draft, and the one-draft index
    refuses the second)."""
    dataset = f"ds-{new_id()}"
    await asyncio.gather(
        store.add_extension(dataset, "BRIBED", "link_type", ENGINEER),
        store.add_extension(dataset, "SMUGGLED_FOR", "link_type", ENGINEER),
    )
    draft = await store.draft(dataset)
    assert draft is not None and draft.version == 1
    assert sorted(e.name for e in draft.extensions) == ["BRIBED", "SMUGGLED_FOR"]
    assert all(e.added_in == 1 and e.kind == "link_type" for e in draft.extensions)
    with pytest.raises(TargetModelRefused, match="already in the draft"):
        await store.add_extension(dataset, "BRIBED", "link_type", ENGINEER)
