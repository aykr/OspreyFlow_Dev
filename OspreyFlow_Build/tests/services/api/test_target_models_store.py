"""`PostgresTargetModelStore` against real Postgres (`make dev-up`, under the stack lease).

The rules of `test_target_models.py` run on the real store, each test in a schema of its own so no
other test's rows decide them. Then the half memory cannot prove: two requests at once cannot both
open a draft, and the one-live and one-draft indexes refuse a second row written past the store
(ADR-140 decision 5, R12).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import pytest
from services.api import dataset_run_order as run_order_module
from services.api.config import PostgresConfig
from services.api.dataset_run_order import PostgresRunOrderStore, RunOrderRefused
from services.api.target_models import (
    CORE_TYPES_FOR_TESTS,
    PostgresTargetModelStore,
    TargetModelRefused,
)

from conduit_common.identity import new_id
from schemas.dataset_model import ModelExtension, TargetModelDraftInput
from schemas.domain import Principal

ENGINEER = Principal(id="d.engineer", clearance="OFFICIAL", org_unit="unit-1")
SECOND = Principal(id="d.second", clearance="OFFICIAL", org_unit="unit-1")


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
    await store.discard_draft(dataset, ENGINEER)
    assert await store.draft(dataset) is None


async def test_only_the_creator_saves_into_or_discards_a_draft_on_postgres(
    store: PostgresTargetModelStore,
) -> None:
    """C186 (OWED: needs the dev stack, not run in the slice that wrote it; the in-memory twin is
    `test_target_model_draft_owner.py`). A second principal's save or discard is refused under the
    lock, naming who holds the draft, and the stored row is unchanged; the creator's own save is
    confirmed against the version."""
    dataset = new_id()
    first = await store.open_draft(dataset, ENGINEER)
    mine = await store.save_draft(
        dataset, TargetModelDraftInput(packs={"fibo": 3}, extensions=[_vessel(1)]), ENGINEER
    )
    for confirmed in (None, first.version):
        with pytest.raises(TargetModelRefused, match="d.engineer"):
            await store.save_draft(
                dataset, TargetModelDraftInput(packs={"stix": 1}), SECOND,
                expected_version=confirmed,
            )  # fmt: skip
        with pytest.raises(TargetModelRefused, match="d.engineer"):
            await store.discard_draft(dataset, SECOND, expected_version=confirmed)
    assert await store.draft(dataset) == mine
    with pytest.raises(TargetModelRefused, match="version 1"):
        await store.save_draft(
            dataset, TargetModelDraftInput(packs={"stix": 1}), ENGINEER, expected_version=7
        )
    assert await store.draft(dataset) == mine
    await store.discard_draft(dataset, ENGINEER, expected_version=first.version)
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


async def test_a_copy_of_a_draft_is_known_by_its_revision_on_postgres(
    store: PostgresTargetModelStore, dsn: str
) -> None:
    """The draft's revision (OWED: needs the dev stack, not run in the slice that wrote it; the
    in-memory twin is `test_target_model_draft_owner.py`). A save changes it and keeps the
    version, a draft discarded and opened again at the same live version has another, a copy read
    before either is refused in words with the row unchanged, and a row written before the column
    existed is given one when the store connects."""
    dataset = new_id()
    first = await store.open_draft(dataset, ENGINEER)
    assert first.revision
    saved = await store.save_draft(
        dataset, TargetModelDraftInput(packs={"fibo": 1}), ENGINEER,
        expected_version=first.version, expected_revision=first.revision,
    )  # fmt: skip
    assert saved.version == first.version and saved.revision not in (None, first.revision)
    held = await store.draft(dataset)
    assert held is not None and held.revision == saved.revision
    with pytest.raises(TargetModelRefused, match="out of date"):
        await store.save_draft(
            dataset, TargetModelDraftInput(packs={"niem": 1}), ENGINEER,
            expected_version=first.version, expected_revision=first.revision,
        )  # fmt: skip
    with pytest.raises(TargetModelRefused, match="out of date"):
        await store.discard_draft(
            dataset, ENGINEER, expected_version=first.version, expected_revision=first.revision
        )
    assert await store.draft(dataset) == held  # neither changed the row
    await store.discard_draft(
        dataset, ENGINEER, expected_version=saved.version, expected_revision=saved.revision
    )
    again = await store.open_draft(dataset, ENGINEER)
    assert again.version == first.version
    assert again.revision not in (None, first.revision, saved.revision)
    with pytest.raises(TargetModelRefused, match="out of date"):
        await store.discard_draft(
            dataset, ENGINEER, expected_version=first.version, expected_revision=saved.revision
        )
    # A row from before the column: the store gives it a revision when it connects.
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "UPDATE target_models SET revision = NULL WHERE dataset_id = $1", dataset
        )
    finally:
        await conn.close()
    migrated = await PostgresTargetModelStore.connect(dsn, core_types=CORE_TYPES_FOR_TESTS)
    try:
        legacy = await migrated.draft(dataset)
        assert legacy is not None and legacy.revision and legacy.revision != again.revision
    finally:
        await migrated.close()


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
    store: PostgresTargetModelStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-143 decision 9 (L3.5): two data engineers accepting two proposed link types at once,
    their transactions truly overlapping (`_all_at_once`). Each `add_extension` reads and writes
    the draft under the dataset's lock, so neither is lost and only one draft is opened (red with
    the lock planted out of `_locked`: both open a draft, and the one-draft index refuses the
    second with a raw unique violation)."""
    _all_at_once(monkeypatch, locked=True, callers=2)
    dataset = f"ds-{new_id()}"
    await asyncio.gather(
        store.add_extension(dataset, "BRIBED", "link_type", ENGINEER),
        store.add_extension(dataset, "SMUGGLED_FOR", "link_type", ENGINEER),
    )
    draft = await store.draft(dataset)
    assert draft is not None and draft.version == 1
    assert sorted(e.name for e in draft.extensions) == ["BRIBED", "SMUGGLED_FOR"]
    assert all(e.added_in == 1 and e.kind == "link_type" for e in draft.extensions)
    monkeypatch.undo()
    with pytest.raises(TargetModelRefused, match="already in the draft"):
        await store.add_extension(dataset, "BRIBED", "link_type", ENGINEER)


# ==================================================================================================
# `PostgresRunOrderStore` against real Postgres (slice IS6a; a lane's leased test stack; ADR-141
# Amendment 2 point 6; the owner's rulings of 24 November 2026, item 6 under "IS6"). Written in
# round 2 as a file of its own and moved here in round 3, because no live-service job names a new
# file; the cases keep their names and content. Only what this file already uses is renamed:
# `store` is `order_store`, and `ALICE` and `BOB` are `RUN_ORDER_ALICE` and `RUN_ORDER_BOB`. Each
# test runs in the schema of its own that `dsn` makes and drops.
#
# Why these cases exist. `test_dataset_run_order.py` proves the rules on `InMemoryRunOrderStore`,
# which the lifespan does not wire in. The store the Conduit really runs on is this one, and its
# refusal of a stale number, its advisory lock, its primary key and the JSONB round trip had no
# test (the round-1 verifier, rules 12 and 15). What a mistake would do, and the case that catches
# it (each shown red with the fault planted at the call the store really makes):
#
# - the stale-number check dropped from `save`: a save made from a number *ahead* of the stored one
#   writes a version nobody made (7 against a stored 1 writes 8), and one made from a number
#   *behind* surfaces as the database's own unique violation (a 500) rather than the 409 in words:
#   `test_a_*`, `test_b_*`; planted: `test_planted_*_check_removed_*`;
# - the advisory lock dropped: two saves of one number both read "none stored", both pass the
#   check, and the second is refused by the key alone, with the database's words, not ours:
#   `test_d_*`; planted: `test_planted_lock_removed_*`;
# - the JSONB round trip losing a link, its order, who saved or when: `test_c_*`.
#
# The plants are made on the store as it is, in the test: the check by setting the module's
# `refuse_a_stale_number` to a function that refuses nothing (the call site looks the name up at
# the call, so this is the call removed); the lock by a pool whose connections send `SELECT 1`
# where the store sends its `pg_advisory_xact_lock` statement. The race is made certain, not left
# to chance: `_Pool` holds each `SELECT` of the stored order for a moment after it has read, so
# that two saves not serialised by the lock both read before either writes. With the lock in place
# the pause is inside it and changes nothing; without it, the second save always meets the key.
#
# Run under a lane's own lease, from `OspreyFlow_Core`, with the stack's ports pinned:
# `OspreyFlow_Build/scripts/stack_lease.sh remote <lane> -- uv run --frozen pytest -c
# ../OspreyFlow_Build/pytest.ini -q
# ../OspreyFlow_Build/tests/services/api/test_target_models_store.py`
# ==================================================================================================

RUN_ORDER_ALICE = Principal(
    id="alice-1", clearance="SECRET", org_unit="unit-1", roles=["data_engineer"]
)
RUN_ORDER_BOB = Principal(
    id="bob-2", clearance="SECRET", org_unit="unit-1", roles=["data_engineer"]
)

#: The statement the store sends to take the dataset's lock, as `save` sends it (its first word is
#: what the plant matches).
LOCK_STATEMENT = "SELECT pg_advisory_xact_lock(hashtext('dataset_run_orders:' || $1))"


@pytest.fixture
async def order_store(dsn: str) -> AsyncIterator[PostgresRunOrderStore]:
    held = await PostgresRunOrderStore.connect(dsn)
    try:
        yield held
    finally:
        await held.close()


@pytest.fixture
def dataset() -> str:
    """One dataset per test: the advisory lock's key is the dataset's id, and is held across
    schemas, so tests sharing an id would block one another under pytest-xdist."""
    return f"ds-{new_id().lower()}"


# --- a pool that can pause after the stored order is read, or send nothing for the lock -----------


class _Conn:
    """The connection the store acquired, with two things changed, each only when asked: the lock
    statement sent as `SELECT 1`, and a pause once the stored order has been read. Everything else
    is the real connection's."""

    def __init__(self, real: Any, *, lock: bool, pause: float) -> None:
        self._real, self._lock, self._pause = real, lock, pause

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    async def execute(self, sql: str, *args: Any, **kwargs: Any) -> Any:
        if sql.strip().startswith("SELECT pg_advisory_xact_lock") and not self._lock:
            return await self._real.execute("SELECT 1")
        return await self._real.execute(sql, *args, **kwargs)

    async def fetchrow(self, sql: str, *args: Any, **kwargs: Any) -> Any:
        row = await self._real.fetchrow(sql, *args, **kwargs)
        # The read `save` makes before it writes (`current` reads the same way, and is paused too:
        # nothing waits on it).
        if self._pause and "ORDER BY version DESC" in sql and sql.lstrip().startswith("SELECT"):
            await asyncio.sleep(self._pause)
        return row


class _Acquired:
    def __init__(self, ctx: Any, **how: Any) -> None:
        self._ctx, self._how = ctx, how

    async def __aenter__(self) -> _Conn:
        return _Conn(await self._ctx.__aenter__(), **self._how)

    async def __aexit__(self, *exc: Any) -> Any:
        return await self._ctx.__aexit__(*exc)


class _Pool:
    def __init__(self, real: Any, **how: Any) -> None:
        self._real, self._how = real, how

    def acquire(self) -> _Acquired:
        return _Acquired(self._real.acquire(), **self._how)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def _slow(
    order_store: PostgresRunOrderStore, *, lock: bool = True, pause: float = 0.3
) -> PostgresRunOrderStore:
    """The same store, its connections pausing after the stored order is read (`pause`) and, with
    `lock=False`, sending nothing where it takes the dataset's lock."""
    order_store._pool = _Pool(order_store._pool, lock=lock, pause=pause)
    return order_store


def _no_check(current: object, expected_version: int) -> None:
    """`refuse_a_stale_number` with the call removed: refuses nothing."""


# --- (a) two saves from one number ----------------------------------------------------------------


async def test_a_two_saves_from_one_number_one_is_refused_in_words_never_both_written(
    order_store: PostgresRunOrderStore, dataset: str
) -> None:
    first = await order_store.save(dataset, {"p-b": ["p-a"]}, RUN_ORDER_ALICE, expected_version=0)
    assert first.version == 1

    # Bob read the order before Alice saved it, and saves from the number he read.
    with pytest.raises(RunOrderRefused) as refused:
        await order_store.save(dataset, {"p-c": ["p-a"]}, RUN_ORDER_BOB, expected_version=0)

    assert refused.value.status == 409 and refused.value.error == "run_order_refused"
    assert "you meant version 0 of the run order, but it is now version 1" in str(refused.value)
    assert "saved by alice-1" in str(refused.value)
    assert "p-c" not in str(refused.value), "the refusal carries nothing of what the order holds"
    # Never both written: one version, Alice's, and Bob's links nowhere.
    assert [v.version for v in await order_store.versions(dataset)] == [1]
    current = await order_store.current(dataset)
    assert (
        current is not None
        and current.runs_after == {"p-b": ["p-a"]}
        and current.saved_by == "alice-1"
    )


async def test_a_a_save_from_a_number_behind_is_refused_when_several_versions_are_stored(
    order_store: PostgresRunOrderStore, dataset: str
) -> None:
    await order_store.save(dataset, {"p-b": ["p-a"]}, RUN_ORDER_ALICE, expected_version=0)
    await order_store.save(dataset, {"p-c": ["p-a"]}, RUN_ORDER_ALICE, expected_version=1)
    with pytest.raises(RunOrderRefused) as refused:
        await order_store.save(dataset, {"p-d": ["p-a"]}, RUN_ORDER_BOB, expected_version=1)
    assert refused.value.status == 409 and "it is now version 2" in str(refused.value)
    assert [v.version for v in await order_store.versions(dataset)] == [1, 2]


# --- (b) a save from a number ahead ---------------------------------------------------------------


async def test_b_a_save_from_a_number_ahead_is_refused_and_nothing_is_written(
    order_store: PostgresRunOrderStore, dataset: str
) -> None:
    await order_store.save(dataset, {"p-b": ["p-a"]}, RUN_ORDER_ALICE, expected_version=0)

    with pytest.raises(RunOrderRefused) as refused:
        await order_store.save(dataset, {"p-c": ["p-a"]}, RUN_ORDER_BOB, expected_version=7)

    assert refused.value.status == 409
    assert "you meant version 7 of the run order, but it is now version 1" in str(refused.value)
    # Nothing written: no version 8, and the stored order is as it was.
    assert [v.version for v in await order_store.versions(dataset)] == [1]
    current = await order_store.current(dataset)
    assert current is not None and current.version == 1 and current.runs_after == {"p-b": ["p-a"]}


async def test_b_a_save_from_a_number_ahead_of_nothing_is_refused_and_nothing_is_written(
    order_store: PostgresRunOrderStore, dataset: str
) -> None:
    with pytest.raises(RunOrderRefused) as refused:
        await order_store.save(dataset, {"p-b": ["p-a"]}, RUN_ORDER_ALICE, expected_version=3)
    assert refused.value.status == 409
    assert "none has been saved (it is now version 0)" in str(refused.value)
    assert await order_store.current(dataset) is None and await order_store.versions(dataset) == []


# --- (c) what is read back ------------------------------------------------------------------------


async def test_c_runs_after_who_when_and_every_version_read_back(
    order_store: PostgresRunOrderStore, dataset: str
) -> None:
    before = datetime.now(UTC) - timedelta(seconds=1)
    # Order inside a pipeline's list is kept (JSONB keeps array order); a pipeline with two links; a
    # name with a quote in it.
    one = {"p-enrich": ["p-ingest", "p-clean"], "p-report": ["p-enrich"], 'p-"odd"': ["p-ingest"]}
    saved_one = await order_store.save(dataset, one, RUN_ORDER_ALICE, expected_version=0)
    saved_two = await order_store.save(
        dataset, {"p-report": ["p-ingest"]}, RUN_ORDER_BOB, expected_version=1
    )
    after = datetime.now(UTC) + timedelta(seconds=1)

    assert (saved_one.version, saved_two.version) == (1, 2)
    read = await order_store.versions(dataset)
    assert [(v.version, v.saved_by) for v in read] == [(1, "alice-1"), (2, "bob-2")]
    assert read[0].runs_after == one and read[1].runs_after == {"p-report": ["p-ingest"]}
    assert [v.dataset_id for v in read] == [dataset, dataset]
    for v in read:
        assert v.saved_at.tzinfo is not None and before <= v.saved_at <= after
    # What the save returned is what is stored, to the microsecond Postgres keeps.
    assert read == [saved_one, saved_two]
    assert read[0].saved_at <= read[1].saved_at

    current = await order_store.current(dataset)
    assert current == read[1]


async def test_c_an_empty_order_round_trips_and_is_a_version_of_its_own(
    order_store: PostgresRunOrderStore, dataset: str
) -> None:
    await order_store.save(dataset, {"p-b": ["p-a"]}, RUN_ORDER_ALICE, expected_version=0)
    cleared = await order_store.save(dataset, {}, RUN_ORDER_BOB, expected_version=1)
    assert cleared.version == 2 and cleared.runs_after == {}
    current = await order_store.current(dataset)
    assert current is not None and current.version == 2 and current.runs_after == {}
    assert [v.version for v in await order_store.versions(dataset)] == [1, 2]


async def test_c_one_datasets_order_is_never_read_as_anothers(
    order_store: PostgresRunOrderStore, dataset: str
) -> None:
    other = f"{dataset}-other"
    await order_store.save(dataset, {"p-b": ["p-a"]}, RUN_ORDER_ALICE, expected_version=0)
    assert await order_store.current(other) is None and await order_store.versions(other) == []
    # And the number is per dataset: the other dataset's first save is from 0.
    saved = await order_store.save(other, {"p-y": ["p-x"]}, RUN_ORDER_BOB, expected_version=0)
    assert saved.version == 1
    current = await order_store.current(dataset)
    assert current is not None and current.runs_after == {"p-b": ["p-a"]}


# --- (d) the advisory lock ------------------------------------------------------------------------


async def _race(order_store: PostgresRunOrderStore, dataset: str, n: int) -> list[object]:
    saves = [
        order_store.save(
            dataset,
            {f"p-{i}": ["p-root"]},
            RUN_ORDER_ALICE if i % 2 else RUN_ORDER_BOB,
            expected_version=0,
        )
        for i in range(n)
    ]
    return list(await asyncio.gather(*saves, return_exceptions=True))


async def test_d_concurrent_saves_from_one_number_exactly_one_wins_the_rest_are_refused_in_words(
    order_store: PostgresRunOrderStore, dataset: str
) -> None:
    # Each connection pauses once it has read, so that saves not held one behind another by the
    # lock would all have read "nothing stored" before the first writes. The pool holds four
    # connections: four saves race, the rest queue for one.
    outcomes = await _race(_slow(order_store), dataset, 4)

    winners = [o for o in outcomes if not isinstance(o, BaseException)]
    refused = [o for o in outcomes if isinstance(o, RunOrderRefused)]
    strangers = [
        o for o in outcomes if isinstance(o, BaseException) and not isinstance(o, RunOrderRefused)
    ]
    assert not strangers, f"a refusal that is the database's own words, not ours: {strangers!r}"
    assert len(winners) == 1 and len(refused) == 3
    assert all(r.status == 409 and "it is now version 1" in str(r) for r in refused)
    versions = await order_store.versions(dataset)
    assert [v.version for v in versions] == [1]
    assert versions[0] == winners[0]


async def test_d_a_save_waits_for_the_datasets_lock_and_then_makes_its_check(
    order_store: PostgresRunOrderStore, dataset: str, dsn: str
) -> None:
    """The lock is what holds it: while another connection holds the dataset's lock, a save waits,
    and once it is let go the save goes on and, its number now stale, is refused in words. (A lock
    on another dataset does not hold it.)"""
    holder = await asyncpg.connect(dsn)
    try:
        tx = holder.transaction()
        await tx.start()
        await holder.execute(LOCK_STATEMENT, dataset)
        waiting = asyncio.ensure_future(
            order_store.save(dataset, {"p-b": ["p-a"]}, RUN_ORDER_ALICE, expected_version=0)
        )
        done, _ = await asyncio.wait({waiting}, timeout=1.0)
        assert not done, "the save went on while the dataset's lock was held elsewhere"

        # A write by the holder's own hand, as an earlier save would have made; then the lock is
        # let go.
        await holder.execute(
            "INSERT INTO dataset_run_orders (dataset_id, version, content, saved_by, saved_at) "
            "VALUES ($1, 1, '{\"runs_after\": {}}'::jsonb, 'earlier', now())",
            dataset,
        )
        await tx.commit()
        with pytest.raises(RunOrderRefused) as refused:
            await asyncio.wait_for(waiting, timeout=10)
        assert "it is now version 1, saved by earlier" in str(refused.value)
    finally:
        await holder.close()

    # Another dataset's lock never held this one: its own save is not made to wait.
    other = f"{dataset}-other"
    holder = await asyncpg.connect(dsn)
    try:
        tx = holder.transaction()
        await tx.start()
        await holder.execute(LOCK_STATEMENT, other)
        saved = await asyncio.wait_for(
            order_store.save(dataset, {"p-c": ["p-a"]}, RUN_ORDER_BOB, expected_version=1),
            timeout=10,
        )
        assert saved.version == 2
        await tx.rollback()
    finally:
        await holder.close()


# --- rule 15: each plant, at the call the store really makes --------------------------------------


async def test_planted_check_removed_a_save_from_a_number_ahead_writes_a_version_nobody_made(
    order_store: PostgresRunOrderStore, dataset: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the call, (b) goes red: 7 against a stored 1 writes version 8, the silent overwrite
    the brief forbids."""
    await order_store.save(dataset, {"p-b": ["p-a"]}, RUN_ORDER_ALICE, expected_version=0)
    monkeypatch.setattr(run_order_module, "refuse_a_stale_number", _no_check)

    saved = await order_store.save(dataset, {"p-c": ["p-a"]}, RUN_ORDER_BOB, expected_version=7)

    assert saved.version == 8
    assert [v.version for v in await order_store.versions(dataset)] == [1, 8]


async def test_planted_check_removed_a_save_from_a_number_behind_is_the_databases_own_error(
    order_store: PostgresRunOrderStore, dataset: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the call, (a) goes red: the second save is stopped only by the key, as a unique
    violation (a 500), not as a `RunOrderRefused` (the 409 in words)."""
    await order_store.save(dataset, {"p-b": ["p-a"]}, RUN_ORDER_ALICE, expected_version=0)
    monkeypatch.setattr(run_order_module, "refuse_a_stale_number", _no_check)

    with pytest.raises(asyncpg.UniqueViolationError):
        await order_store.save(dataset, {"p-c": ["p-a"]}, RUN_ORDER_BOB, expected_version=0)
    assert [v.version for v in await order_store.versions(dataset)] == [1]


async def test_planted_lock_removed_concurrent_saves_meet_the_key_and_not_our_words(
    order_store: PostgresRunOrderStore, dataset: str
) -> None:
    """Without the lock, (d) goes red: all four read "none stored", all pass the check, one writes,
    and the other three are stopped by the primary key alone, with the database's words."""
    outcomes = await _race(_slow(order_store, lock=False), dataset, 4)

    strangers = [o for o in outcomes if isinstance(o, asyncpg.UniqueViolationError)]
    assert len(strangers) == 3, outcomes
    assert not [o for o in outcomes if isinstance(o, RunOrderRefused)]
    assert [v.version for v in await order_store.versions(dataset)] == [1]


async def test_planted_lock_removed_a_save_does_not_wait_for_the_datasets_lock(
    order_store: PostgresRunOrderStore, dataset: str, dsn: str
) -> None:
    """Without the lock, the waiting test goes red: the save goes on while another connection holds
    the lock."""
    _slow(order_store, lock=False, pause=0)
    holder = await asyncpg.connect(dsn)
    try:
        tx = holder.transaction()
        await tx.start()
        await holder.execute(LOCK_STATEMENT, dataset)
        saved = await asyncio.wait_for(
            order_store.save(dataset, {"p-b": ["p-a"]}, RUN_ORDER_ALICE, expected_version=0),
            timeout=10,
        )
        assert saved.version == 1
        await tx.rollback()
    finally:
        await holder.close()


def test_the_plant_sends_select_1_where_the_lock_statement_goes() -> None:
    """The plant is only a plant if it replaces the statement the store really sends: the store's
    own `save` sends exactly the statement this file takes the lock with."""
    import inspect

    source = " ".join(inspect.getsource(PostgresRunOrderStore.save).split())
    assert "SELECT pg_advisory_xact_lock(hashtext('dataset_run_orders:' || $1))" in source
    assert LOCK_STATEMENT.startswith("SELECT pg_advisory_xact_lock")
