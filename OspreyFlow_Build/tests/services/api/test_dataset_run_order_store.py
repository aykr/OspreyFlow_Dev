"""`PostgresRunOrderStore` against real Postgres (slice IS6a, round 2; a lane's leased test stack; ADR-141 Amendment 2
point 6; the owner's rulings of 24 November 2026, item 6 under "IS6"). Each test in a schema of its own, dropped in teardown
whether it passes or fails.

Why this file exists. `test_dataset_run_order.py` proves the rules on `InMemoryRunOrderStore`, which the lifespan does not
wire in; the store the Conduit really runs on is this one, and its own refusal of a stale number, its advisory lock, its
primary key and the JSONB round trip had no test (the round-1 verifier, rules 12 and 15). What a mistake would do, and the
case that catches it (each shown red with the fault planted at the call the store really makes):

- the stale-number check dropped from `save`: a save made from a number *ahead* of the stored one writes a version nobody
  made (7 against a stored 1 writes 8), and one made from a number *behind* surfaces as the database's own unique
  violation (a 500) rather than the 409 in words: `test_a_*`, `test_b_*`; planted: `test_planted_*_check_removed_*`;
- the advisory lock dropped: two saves of one number both read "none stored", both pass the check, and the second is
  refused by the key alone, with the database's words, not ours: `test_d_*`; planted: `test_planted_lock_removed_*`;
- the JSONB round trip losing a link, its order, who saved or when: `test_c_*`.

The plants are made on the store as it is, in the test: the check by setting the module's `refuse_a_stale_number` to a
function that refuses nothing (the call site looks the name up at the call, so this is the call removed); the lock by a
pool whose connections send `SELECT 1` where the store sends its `pg_advisory_xact_lock` statement. The race is made
certain, not left to chance: `_Slow` holds each `SELECT` of the stored order for a moment after it has read, so that two
saves that are not serialised by the lock both read before either writes. With the lock in place the pause is inside it
and changes nothing; without it, the second save always meets the key.

THE FOLDERS THIS TEST WALKS (the conductor's scan-map row): none. It imports the store and reads no folder.

Run under a lane's own lease, from `OspreyFlow_Core`, with the stack's ports pinned:
`OspreyFlow_Build/scripts/stack_lease.sh remote <lane> -- uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q
../OspreyFlow_Build/tests/services/api/test_dataset_run_order_store.py`.
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

from conduit_common.identity import new_id
from schemas.domain import Principal

#: Every case here reaches Postgres (the one that checks the plant's statement does not, and is marked with them).
pytestmark = pytest.mark.store

ALICE = Principal(id="alice-1", clearance="SECRET", org_unit="unit-1", roles=["data_engineer"])
BOB = Principal(id="bob-2", clearance="SECRET", org_unit="unit-1", roles=["data_engineer"])

#: The statement the store sends to take the dataset's lock, as `save` sends it (its first word is what the plant matches).
LOCK_STATEMENT = "SELECT pg_advisory_xact_lock(hashtext('dataset_run_orders:' || $1))"


@pytest.fixture
async def dsn() -> AsyncIterator[str]:
    base = PostgresConfig.from_env().dsn
    schema = f"run_orders_{new_id().lower()}"
    admin = await asyncpg.connect(base)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        yield f"{base}{'&' if '?' in base else '?'}search_path={schema}"
    finally:
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


@pytest.fixture
async def store(dsn: str) -> AsyncIterator[PostgresRunOrderStore]:
    held = await PostgresRunOrderStore.connect(dsn)
    try:
        yield held
    finally:
        await held.close()


@pytest.fixture
def dataset() -> str:
    """One dataset per test: the advisory lock's key is the dataset's id, and is held across schemas, so tests sharing an id
    would block one another under pytest-xdist."""
    return f"ds-{new_id().lower()}"


# --- a pool that can pause after the stored order is read, and can send nothing where the lock statement goes ----------------


class _Conn:
    """The connection the store acquired, with two things changed, each only when asked: the lock statement sent as
    `SELECT 1`, and a pause once the stored order has been read. Everything else is the real connection's."""

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
        # The read `save` makes before it writes (`current` reads the same way, and is paused too: nothing waits on it).
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
    store: PostgresRunOrderStore, *, lock: bool = True, pause: float = 0.3
) -> PostgresRunOrderStore:
    """The same store, its connections pausing after the stored order is read (`pause`), and, with `lock=False`, sending
    nothing where it takes the dataset's lock."""
    store._pool = _Pool(store._pool, lock=lock, pause=pause)  # type: ignore[assignment]
    return store


def _no_check(current: object, expected_version: int) -> None:
    """`refuse_a_stale_number` with the call removed: refuses nothing."""


# --- (a) two saves from one number ------------------------------------------------------------------------------------------


async def test_a_two_saves_from_one_number_one_is_refused_in_words_never_both_written(
    store: PostgresRunOrderStore, dataset: str
) -> None:
    first = await store.save(dataset, {"p-b": ["p-a"]}, ALICE, expected_version=0)
    assert first.version == 1

    # Bob read the order before Alice saved it, and saves from the number he read.
    with pytest.raises(RunOrderRefused) as refused:
        await store.save(dataset, {"p-c": ["p-a"]}, BOB, expected_version=0)

    assert refused.value.status == 409 and refused.value.error == "run_order_refused"
    assert "you meant version 0 of the run order, but it is now version 1" in str(refused.value)
    assert "saved by alice-1" in str(refused.value)
    assert "p-c" not in str(refused.value), "the refusal carries nothing of what the order holds"
    # Never both written: one version, Alice's, and Bob's links nowhere.
    assert [v.version for v in await store.versions(dataset)] == [1]
    current = await store.current(dataset)
    assert (
        current is not None
        and current.runs_after == {"p-b": ["p-a"]}
        and current.saved_by == "alice-1"
    )


async def test_a_a_save_from_a_number_behind_is_refused_when_several_versions_are_stored(
    store: PostgresRunOrderStore, dataset: str
) -> None:
    await store.save(dataset, {"p-b": ["p-a"]}, ALICE, expected_version=0)
    await store.save(dataset, {"p-c": ["p-a"]}, ALICE, expected_version=1)
    with pytest.raises(RunOrderRefused) as refused:
        await store.save(dataset, {"p-d": ["p-a"]}, BOB, expected_version=1)
    assert refused.value.status == 409 and "it is now version 2" in str(refused.value)
    assert [v.version for v in await store.versions(dataset)] == [1, 2]


# --- (b) a save from a number ahead -----------------------------------------------------------------------------------------


async def test_b_a_save_from_a_number_ahead_is_refused_and_nothing_is_written(
    store: PostgresRunOrderStore, dataset: str
) -> None:
    await store.save(dataset, {"p-b": ["p-a"]}, ALICE, expected_version=0)

    with pytest.raises(RunOrderRefused) as refused:
        await store.save(dataset, {"p-c": ["p-a"]}, BOB, expected_version=7)

    assert refused.value.status == 409
    assert "you meant version 7 of the run order, but it is now version 1" in str(refused.value)
    # Nothing written: no version 8, and the stored order is as it was.
    assert [v.version for v in await store.versions(dataset)] == [1]
    current = await store.current(dataset)
    assert current is not None and current.version == 1 and current.runs_after == {"p-b": ["p-a"]}


async def test_b_a_save_from_a_number_ahead_of_nothing_is_refused_and_nothing_is_written(
    store: PostgresRunOrderStore, dataset: str
) -> None:
    with pytest.raises(RunOrderRefused) as refused:
        await store.save(dataset, {"p-b": ["p-a"]}, ALICE, expected_version=3)
    assert refused.value.status == 409
    assert "none has been saved (it is now version 0)" in str(refused.value)
    assert await store.current(dataset) is None and await store.versions(dataset) == []


# --- (c) what is read back --------------------------------------------------------------------------------------------------


async def test_c_runs_after_who_when_and_every_version_read_back(
    store: PostgresRunOrderStore, dataset: str
) -> None:
    before = datetime.now(UTC) - timedelta(seconds=1)
    # Order inside a pipeline's list is kept (JSONB keeps array order); a pipeline with two links; a name with a quote in it.
    one = {"p-enrich": ["p-ingest", "p-clean"], "p-report": ["p-enrich"], 'p-"odd"': ["p-ingest"]}
    saved_one = await store.save(dataset, one, ALICE, expected_version=0)
    saved_two = await store.save(dataset, {"p-report": ["p-ingest"]}, BOB, expected_version=1)
    after = datetime.now(UTC) + timedelta(seconds=1)

    assert (saved_one.version, saved_two.version) == (1, 2)
    read = await store.versions(dataset)
    assert [(v.version, v.saved_by) for v in read] == [(1, "alice-1"), (2, "bob-2")]
    assert read[0].runs_after == one and read[1].runs_after == {"p-report": ["p-ingest"]}
    assert [v.dataset_id for v in read] == [dataset, dataset]
    for v in read:
        assert v.saved_at.tzinfo is not None and before <= v.saved_at <= after
    # What the save returned is what is stored, to the microsecond Postgres keeps.
    assert read == [saved_one, saved_two]
    assert read[0].saved_at <= read[1].saved_at

    current = await store.current(dataset)
    assert current == read[1]


async def test_c_an_empty_order_round_trips_and_is_a_version_of_its_own(
    store: PostgresRunOrderStore, dataset: str
) -> None:
    await store.save(dataset, {"p-b": ["p-a"]}, ALICE, expected_version=0)
    cleared = await store.save(dataset, {}, BOB, expected_version=1)
    assert cleared.version == 2 and cleared.runs_after == {}
    current = await store.current(dataset)
    assert current is not None and current.version == 2 and current.runs_after == {}
    assert [v.version for v in await store.versions(dataset)] == [1, 2]


async def test_c_one_datasets_order_is_never_read_as_anothers(
    store: PostgresRunOrderStore, dataset: str
) -> None:
    other = f"{dataset}-other"
    await store.save(dataset, {"p-b": ["p-a"]}, ALICE, expected_version=0)
    assert await store.current(other) is None and await store.versions(other) == []
    # And the number is per dataset: the other dataset's first save is from 0.
    saved = await store.save(other, {"p-y": ["p-x"]}, BOB, expected_version=0)
    assert saved.version == 1
    current = await store.current(dataset)
    assert current is not None and current.runs_after == {"p-b": ["p-a"]}


# --- (d) the advisory lock --------------------------------------------------------------------------------------------------


async def _race(store: PostgresRunOrderStore, dataset: str, n: int) -> list[object]:
    saves = [
        store.save(dataset, {f"p-{i}": ["p-root"]}, ALICE if i % 2 else BOB, expected_version=0)
        for i in range(n)
    ]
    return list(await asyncio.gather(*saves, return_exceptions=True))


async def test_d_concurrent_saves_from_one_number_exactly_one_wins_the_rest_are_refused_in_words(
    store: PostgresRunOrderStore, dataset: str
) -> None:
    # Each connection pauses once it has read, so that saves not held one behind another by the lock would all have read
    # "nothing stored" before the first writes. The pool holds four connections: four saves race, the rest queue for one.
    outcomes = await _race(_slow(store), dataset, 4)

    winners = [o for o in outcomes if not isinstance(o, BaseException)]
    refused = [o for o in outcomes if isinstance(o, RunOrderRefused)]
    strangers = [
        o for o in outcomes if isinstance(o, BaseException) and not isinstance(o, RunOrderRefused)
    ]
    assert not strangers, f"a refusal that is the database's own words, not ours: {strangers!r}"
    assert len(winners) == 1 and len(refused) == 3
    assert all(r.status == 409 and "it is now version 1" in str(r) for r in refused)
    versions = await store.versions(dataset)
    assert [v.version for v in versions] == [1]
    assert versions[0] == winners[0]


async def test_d_a_save_waits_for_the_datasets_lock_and_then_makes_its_check(
    store: PostgresRunOrderStore, dataset: str, dsn: str
) -> None:
    """The lock is what holds it: while another connection holds the dataset's lock, a save waits, and once it is let go the
    save goes on and, its number now stale, is refused in words. (A lock on another dataset does not hold it.)"""
    holder = await asyncpg.connect(dsn)
    try:
        tx = holder.transaction()
        await tx.start()
        await holder.execute(LOCK_STATEMENT, dataset)
        waiting = asyncio.ensure_future(
            store.save(dataset, {"p-b": ["p-a"]}, ALICE, expected_version=0)
        )
        done, _ = await asyncio.wait({waiting}, timeout=1.0)
        assert not done, "the save went on while the dataset's lock was held elsewhere"

        # A write by the holder's own hand, as an earlier save would have made, then the lock is let go.
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
            store.save(dataset, {"p-c": ["p-a"]}, BOB, expected_version=1), timeout=10
        )
        assert saved.version == 2
        await tx.rollback()
    finally:
        await holder.close()


# --- rule 15: each plant, at the call the store really makes ------------------------------------------------------------------


async def test_planted_check_removed_a_save_from_a_number_ahead_writes_a_version_nobody_made(
    store: PostgresRunOrderStore, dataset: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the call, (b) goes red: 7 against a stored 1 writes version 8, the silent overwrite the brief forbids."""
    await store.save(dataset, {"p-b": ["p-a"]}, ALICE, expected_version=0)
    monkeypatch.setattr(run_order_module, "refuse_a_stale_number", _no_check)

    saved = await store.save(dataset, {"p-c": ["p-a"]}, BOB, expected_version=7)

    assert saved.version == 8
    assert [v.version for v in await store.versions(dataset)] == [1, 8]


async def test_planted_check_removed_a_save_from_a_number_behind_is_the_databases_own_error(
    store: PostgresRunOrderStore, dataset: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the call, (a) goes red: the second save is stopped only by the key, as a unique violation (a 500), not as a
    `RunOrderRefused` (the 409 in words)."""
    await store.save(dataset, {"p-b": ["p-a"]}, ALICE, expected_version=0)
    monkeypatch.setattr(run_order_module, "refuse_a_stale_number", _no_check)

    with pytest.raises(asyncpg.UniqueViolationError):
        await store.save(dataset, {"p-c": ["p-a"]}, BOB, expected_version=0)
    assert [v.version for v in await store.versions(dataset)] == [1]


async def test_planted_lock_removed_concurrent_saves_meet_the_key_and_not_our_words(
    store: PostgresRunOrderStore, dataset: str
) -> None:
    """Without the lock, (d) goes red: all four read "none stored", all pass the check, one writes, and the other three are
    stopped by the primary key alone, with the database's words."""
    outcomes = await _race(_slow(store, lock=False), dataset, 4)

    strangers = [o for o in outcomes if isinstance(o, asyncpg.UniqueViolationError)]
    assert len(strangers) == 3, outcomes
    assert not [o for o in outcomes if isinstance(o, RunOrderRefused)]
    assert [v.version for v in await store.versions(dataset)] == [1]


async def test_planted_lock_removed_a_save_does_not_wait_for_the_datasets_lock(
    store: PostgresRunOrderStore, dataset: str, dsn: str
) -> None:
    """Without the lock, the waiting test goes red: the save goes on while another connection holds the lock."""
    _slow(store, lock=False, pause=0)
    holder = await asyncpg.connect(dsn)
    try:
        tx = holder.transaction()
        await tx.start()
        await holder.execute(LOCK_STATEMENT, dataset)
        saved = await asyncio.wait_for(
            store.save(dataset, {"p-b": ["p-a"]}, ALICE, expected_version=0), timeout=10
        )
        assert saved.version == 1
        await tx.rollback()
    finally:
        await holder.close()


def test_the_plant_sends_select_1_where_the_lock_statement_goes() -> None:
    """The plant is only a plant if it replaces the statement the store really sends: the store's own `save` sends exactly
    the statement this file takes the lock with."""
    import inspect

    source = " ".join(inspect.getsource(PostgresRunOrderStore.save).split())
    assert "SELECT pg_advisory_xact_lock(hashtext('dataset_run_orders:' || $1))" in source
    assert LOCK_STATEMENT.startswith("SELECT pg_advisory_xact_lock")
