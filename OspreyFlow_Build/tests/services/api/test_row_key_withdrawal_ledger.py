"""ADR-110 Amendment 8 points 2 to 5, in the run ledger: each kept key's record of what its row
wrote, the keys a full snapshot withdrew, and the questions its withdrawal and its revert ask.

Against the throwaway Postgres (`POSTGRES_PORT`). What a mistake would do, and the case that
catches it:

- a key's record lost on the way in, so its row's elements could never be withdrawn
  (`test_a_keys_record_is_kept_with_it_and_a_key_kept_before_records_none`);
- a withdrawn key still read as kept, so the row that comes back is skipped for good, or still
  offered as dropped, so a second snapshot withdraws it twice
  (`test_a_withdrawn_key_is_not_kept_nor_dropped_again_and_its_restore_puts_it_back_whole`);
- the refresh's revert restoring a row that a later load has kept again, so the row is held twice
  (`test_a_withdrawn_key_kept_again_is_counted_until_that_load_is_reverted`);
- the revert of the load that kept a key leaving it to be restored later
  (`test_reverting_the_load_that_kept_a_withdrawn_key_leaves_nothing_to_restore`);
- a key's events lost on the way in or back, or a row recorded before Amendment 15 read as one that
  wrote no events (`test_a_keys_record_is_kept_with_it_and_a_key_kept_before_records_none`,
  `test_a_key_recorded_before_its_events_reads_as_none`);
- the events a refresh sets aside taken from another load's withdrawn rows, or the withdrawal
  asking anything about another row, case or load (Amendment 15;
  `test_a_refreshs_withdrawn_events_are_its_own_rows_alone`);
- a run under a changed `deduplicate` let through while a withdrawn key under the old one waits to
  be restored (`test_a_withdrawn_keys_definition_still_counts`)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from conduit_common.identity import new_id
from schemas.ingest import RowElements
from services.api.config import PostgresConfig
from services.api.recipe_runs import RecipeRunStore

from tests.services.api.test_recipe_runs import _keyed, _started

T0 = datetime(2026, 11, 6, 6, 0, tzinfo=UTC)


@pytest.fixture
async def runs() -> AsyncIterator[RecipeRunStore]:
    store = await RecipeRunStore.connect(PostgresConfig.from_env().dsn)
    try:
        yield store
    finally:
        await store.close()


def _elements(
    nodes: list[str], edges: list[str], events: list[str] | None = None
) -> RowElements:
    return RowElements(node_ids=nodes, edge_ids=edges, event_ids=events or [])


async def test_a_keys_record_is_kept_with_it_and_a_key_kept_before_records_none(
    runs: RecipeRunStore,
) -> None:
    recipe, case, load = new_id(), new_id(), new_id()
    k1, k2, legacy = new_id(), new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(
        run_id,
        _keyed(load, recipe, case),
        row_keys=[k1, k2],
        row_elements={
            k1: _elements(["n1", "n2"], ["e1"], ["v1"]),
            k2: _elements(["n1"], []),
        },
    )
    # A key kept before Amendment 8 has no record: NULL, not an empty one.
    await runs.add_record(run_id, _keyed(new_id(), recipe, case), row_keys=[legacy])

    dropped = {
        d.row_key: d for d in await runs.dropped_row_keys(recipe, case, present={k2})
    }
    assert set(dropped) == {k1, legacy}
    assert dropped[k1].load_id == load
    assert dropped[k1].node_ids == ("n1", "n2") and dropped[k1].edge_ids == ("e1",)
    assert dropped[k1].event_ids == ("v1",)
    assert (dropped[legacy].node_ids, dropped[legacy].edge_ids, dropped[legacy].event_ids) == (
        None, None, None,
    )  # fmt: skip
    # Per recipe and case (rule 3): another case drops nothing of these.
    assert await runs.dropped_row_keys(recipe, new_id(), present=set()) == []


async def test_a_withdrawn_key_is_not_kept_nor_dropped_again_and_its_restore_puts_it_back_whole(
    runs: RecipeRunStore,
) -> None:
    recipe, case, first, refresh = new_id(), new_id(), new_id(), new_id()
    k1, k2 = new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(
        run_id,
        _keyed(first, recipe, case),
        row_keys=[k1, k2],
        row_elements={
            k1: _elements(["n1"], ["e1"], ["v1"]),
            k2: _elements(["n2"], ["e2"]),
        },
        row_key_fingerprint="fp",
    )
    await runs.add_record(
        run_id, _keyed(refresh, recipe, case), withdrawn_row_keys=[k1]
    )

    assert await runs.kept_row_keys(recipe, case, [k1, k2]) == {k2}
    assert [
        d.row_key for d in await runs.dropped_row_keys(recipe, case, present=set())
    ] == [k2]
    assert await runs.restore_withdrawn_row_keys(refresh) == 1
    assert await runs.restore_withdrawn_row_keys(refresh) == 0
    assert await runs.kept_row_keys(recipe, case, [k1]) == {k1}
    (back,) = [
        d
        for d in await runs.dropped_row_keys(recipe, case, present={k2})
        if d.row_key == k1
    ]
    assert (back.load_id, back.node_ids, back.edge_ids, back.event_ids) == (
        first, ("n1",), ("e1",), ("v1",),
    )  # fmt: skip
    assert await runs.fingerprints(recipe, case) == {"fp": 1}


async def test_a_withdrawn_key_kept_again_is_counted_until_that_load_is_reverted(
    runs: RecipeRunStore,
) -> None:
    recipe, case = new_id(), new_id()
    first, refresh, back = new_id(), new_id(), new_id()
    k1 = new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _keyed(first, recipe, case), row_keys=[k1])
    await runs.add_record(
        run_id, _keyed(refresh, recipe, case), withdrawn_row_keys=[k1]
    )
    assert await runs.withdrawn_keys_kept_again(refresh) == 0
    # The row comes back in a later snapshot: loaded again, its key kept by that load.
    await runs.add_record(run_id, _keyed(back, recipe, case), row_keys=[k1])
    assert await runs.kept_row_keys(recipe, case, [k1]) == {k1}
    assert await runs.withdrawn_keys_kept_again(refresh) == 1
    await runs.release_row_keys([back])
    assert await runs.withdrawn_keys_kept_again(refresh) == 0
    assert await runs.restore_withdrawn_row_keys(refresh) == 1


async def test_reverting_the_load_that_kept_a_withdrawn_key_leaves_nothing_to_restore(
    runs: RecipeRunStore,
) -> None:
    recipe, case, first, refresh = new_id(), new_id(), new_id(), new_id()
    k1, k2 = new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _keyed(first, recipe, case), row_keys=[k1, k2])
    await runs.add_record(
        run_id, _keyed(refresh, recipe, case), withdrawn_row_keys=[k1]
    )
    assert await runs.release_row_keys([first]) == 2, (
        "the withdrawn key is the load's too"
    )
    assert await runs.restore_withdrawn_row_keys(refresh) == 0
    assert await runs.kept_row_keys(recipe, case, [k1, k2]) == set()


async def test_another_cases_withdrawal_of_the_same_key_is_never_ours(
    runs: RecipeRunStore,
) -> None:
    """Rules 3 and 4: a row key does not depend on the case, so another case of the same pipeline
    can hold the very key withdrawn. Neither question about a withdrawn key may see it: ours is not
    `withdrawn_before`, and not among `withdrawn_row_keys_among`, while theirs is. Red with either
    query's `investigation_id` condition removed (`L1.2a_RED_RECORD.md`)."""
    recipe, ours, theirs = new_id(), new_id(), new_id()
    our_load, their_load, their_refresh = new_id(), new_id(), new_id()
    k1 = new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _keyed(our_load, recipe, ours), row_keys=[k1],
                          row_elements={k1: _elements(["n1"], ["e1"], ["v1"])})  # fmt: skip
    await runs.add_record(run_id, _keyed(their_load, recipe, theirs), row_keys=[k1],
                          row_elements={k1: _elements(["n1"], ["e1"], ["v9"])})  # fmt: skip
    await runs.add_record(
        run_id, _keyed(their_refresh, recipe, theirs), withdrawn_row_keys=[k1]
    )

    (dropped,) = await runs.dropped_row_keys(recipe, ours, present=set())
    assert dropped.withdrawn_before is False
    assert await runs.withdrawn_row_keys_among(recipe, ours, [k1]) == set()
    assert await runs.withdrawn_row_keys_among(recipe, theirs, [k1]) == {k1}

    # Ours is moved aside when our own refresh drops it: their entry never blocks the move.
    our_refresh = new_id()
    await runs.add_record(
        run_id, _keyed(our_refresh, recipe, ours), withdrawn_row_keys=[k1]
    )
    assert await runs.kept_row_keys(recipe, ours, [k1]) == set(), "ours was moved"
    assert await runs.withdrawn_event_ids(our_refresh) == ["v1"]


async def test_another_cases_key_never_blocks_or_takes_a_refreshs_revert(
    runs: RecipeRunStore,
) -> None:
    """Rules 3 and 4, the revert's reads: our case keeping the same key their refresh withdrew does
    not count as "kept again" (their revert is not refused because of us, which would tell them our
    row exists), and their revert moves their key back though ours stays kept. Red with either
    query's `investigation_id` condition removed (`L1.2a_RED_RECORD.md`)."""
    recipe, ours, theirs = new_id(), new_id(), new_id()
    our_load, their_load, their_refresh = new_id(), new_id(), new_id()
    k1 = new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _keyed(their_load, recipe, theirs), row_keys=[k1],
                          row_elements={k1: _elements(["n1"], ["e1"], ["v9"])})  # fmt: skip
    await runs.add_record(
        run_id, _keyed(their_refresh, recipe, theirs), withdrawn_row_keys=[k1]
    )
    await runs.add_record(run_id, _keyed(our_load, recipe, ours), row_keys=[k1],
                          row_elements={k1: _elements(["n1"], ["e1"], ["v1"])})  # fmt: skip

    assert await runs.withdrawn_keys_kept_again(their_refresh) == 0
    assert await runs.restore_withdrawn_row_keys(their_refresh) == 1
    assert await runs.kept_row_keys(recipe, theirs, [k1]) == {k1}
    assert await runs.kept_row_keys(recipe, ours, [k1]) == {k1}


async def test_the_unit_files_fake_moves_keys_as_the_ledger_does(
    runs: RecipeRunStore,
) -> None:
    """Rule 15's fixture rule, both ways: `test_snapshot_withdrawal.py`'s `WithdrawalLedger` stands
    in for this store, so the same records go to both and what each then keeps and has withdrawn
    must match. That covers a key kept, withdrawn, kept again, named withdrawn again (the guard
    skips it), and named withdrawn though never kept (nothing moves), with no error from either.
    Two cases hold the same keys, interleaved, and every answer is compared for each: a fake
    that ignored the case would answer one case with the other's."""
    from schemas.ingest import LoadReport

    from tests.ingest.test_snapshot_withdrawal import WithdrawalLedger

    recipe, k1, k2, never = new_id(), new_id(), new_id(), new_id()
    ours, theirs = new_id(), new_id()
    loads = [new_id() for _ in range(7)]
    steps: list[tuple[str, str, list[str], list[str]]] = [
        (ours, loads[0], [k1, k2], []),
        (theirs, loads[1], [k1, k2], []),
        (ours, loads[2], [], [k1]),
        (theirs, loads[3], [], [k2]),
        (ours, loads[4], [k1], []),
        (ours, loads[5], [], [k1, never]),
        (theirs, loads[6], [], [k1]),
    ]
    fake = WithdrawalLedger()
    run_id = await _started(runs, recipe)
    for case, load, kept, withdrawn in steps:
        elements = {
            k: _elements([f"n-{k}"], [f"e-{k}"], [f"v-{load}-{k}"]) for k in kept
        }
        await runs.add_record(run_id, _keyed(load, recipe, case), row_keys=kept,
                              row_elements=elements, withdrawn_row_keys=withdrawn)  # fmt: skip
        fake.case = case
        await fake.committed(
            LoadReport.model_construct(recipe_id=recipe, load_id=load, kept_row_keys=kept,
                                       kept_row_elements=elements, withdrawn_row_keys=withdrawn),
            source="cash.csv",
        )  # fmt: skip

    def told(dropped: list[Any]) -> dict[str, tuple[bool, Any]]:
        return {d.row_key: (d.withdrawn_before, d.event_ids) for d in dropped}

    keys = [k1, k2, never]
    for load in loads:
        assert await runs.withdrawn_event_ids(load) == await fake.withdrawn_event_ids(
            load
        ), load
    for case in (ours, theirs):
        kept = await runs.kept_row_keys(recipe, case, keys)
        assert kept == await fake.kept(recipe, case, keys), case
        real = told(await runs.dropped_row_keys(recipe, case, present=set()))
        assert real == told(await fake.dropped_row_keys(recipe, case, present=set())), (
            case
        )
        among = await runs.withdrawn_row_keys_among(recipe, case, keys)
        assert among == await fake.withdrawn_row_keys_among(recipe, case, keys), case
    # What each case holds, so the comparison is over something different for each.
    assert await runs.kept_row_keys(recipe, ours, keys) == {k1, k2}
    assert await runs.kept_row_keys(recipe, theirs, keys) == set()
    assert told(await runs.dropped_row_keys(recipe, ours, present=set()))[k1][0] is True
    assert await runs.withdrawn_row_keys_among(recipe, theirs, keys) == {k2, k1}


async def test_withdrawn_row_keys_among_reads_more_keys_than_one_statement_holds(
    runs: RecipeRunStore,
) -> None:
    """Asked in chunks of `_KEY_CHUNK`, as `kept_row_keys` is. Every statement it sends to Postgres
    is recorded, and none may carry more than one chunk of keys, while every withdrawn key past the
    first chunk is still found. Red with the query unchunked (one `ANY` of every key), and with the
    loop stopped after one chunk (`L1.2a_RED_RECORD.md`)."""
    from contextlib import asynccontextmanager

    from services.api.recipe_runs import _KEY_CHUNK

    recipe, case, first, refresh = new_id(), new_id(), new_id(), new_id()
    keys = [f"key-{n:06d}" for n in range(_KEY_CHUNK + 5)]
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _keyed(first, recipe, case), row_keys=keys)
    await runs.add_record(
        run_id, _keyed(refresh, recipe, case), withdrawn_row_keys=keys
    )

    sent: list[list[Any]] = []
    pool = runs._pool

    class Recording:
        """The real pool's connection, every `fetch` kept with its values."""

        def __init__(self, conn: Any) -> None:
            self._conn = conn

        async def fetch(self, sql: str, *values: Any) -> Any:
            sent.append(list(values))
            return await self._conn.fetch(sql, *values)

    class RecordingPool:
        @asynccontextmanager
        async def acquire(self) -> Any:
            async with pool.acquire() as conn:
                yield Recording(conn)

    runs._pool = RecordingPool()  # type: ignore[assignment]
    try:
        found = await runs.withdrawn_row_keys_among(recipe, case, keys)
    finally:
        runs._pool = pool
    assert found == set(keys)
    lists = [len(v) for values in sent for v in values if isinstance(v, list)]
    assert lists and max(lists) <= _KEY_CHUNK, f"keys per statement: {lists}"
    assert sum(lists) == len(keys)


async def test_a_row_dropped_after_coming_back_is_told_as_withdrawn_before(
    runs: RecipeRunStore,
) -> None:
    """A row that comes back after a withdrawal, then is dropped again: its key is still in
    `withdrawn_row_keys` (neither revert can clear it under Amendment 15), so moving it aside again
    would collide. `dropped_row_keys` says so (`withdrawn_before`), and the withdrawal leaves it in
    place; no unique violation after the graph has committed."""
    recipe, case = new_id(), new_id()
    first, refresh, back = new_id(), new_id(), new_id()
    k1, k2 = new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _keyed(first, recipe, case), row_keys=[k1, k2],
                          row_elements={k1: _elements(["n1"], ["e1"], ["v1"]),
                                        k2: _elements(["n2"], ["e2"], ["v3"])})  # fmt: skip
    await runs.add_record(
        run_id, _keyed(refresh, recipe, case), withdrawn_row_keys=[k1]
    )
    await runs.add_record(run_id, _keyed(back, recipe, case), row_keys=[k1],
                          row_elements={k1: _elements(["n1"], ["e1"], ["v2"])})  # fmt: skip

    dropped = {
        d.row_key: d for d in await runs.dropped_row_keys(recipe, case, present=set())
    }

    assert (dropped[k1].withdrawn_before, dropped[k2].withdrawn_before) == (True, False)
    assert dropped[k1].event_ids == ("v2",)
    # The ledger's own guard: a record that names it withdrawn anyway leaves it kept, no violation.
    await runs.add_record(
        run_id, _keyed(new_id(), recipe, case), withdrawn_row_keys=[k1]
    )
    assert await runs.kept_row_keys(recipe, case, [k1]) == {k1}
    assert await runs.withdrawn_event_ids(refresh) == ["v1"]


async def test_a_key_recorded_before_its_events_reads_as_none(
    runs: RecipeRunStore,
) -> None:
    """A key kept under Amendment 8 has its nodes and links but no events (the column is NULL): it
    reads as `None`, which the withdrawal leaves in place, never as a row that wrote none."""
    recipe, case = new_id(), new_id()
    k1 = new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(
        run_id, _keyed(new_id(), recipe, case), row_keys=[k1],
        row_elements={k1: _elements(["n1"], ["e1"], ["v1"])},
    )  # fmt: skip
    await runs._pool.execute(
        "UPDATE loaded_row_keys SET event_ids = NULL WHERE recipe_id = $1 AND row_key = $2",
        recipe,
        k1,
    )
    (dropped,) = await runs.dropped_row_keys(recipe, case, present=set())
    assert (dropped.node_ids, dropped.edge_ids, dropped.event_ids) == (
        ("n1",),
        ("e1",),
        None,
    )


async def test_a_refreshs_withdrawn_events_are_its_own_rows_alone(
    runs: RecipeRunStore,
) -> None:
    """Amendment 15: the events a refresh sets aside are those its withdrawn keys record, and no
    other: not another refresh's, in this case or another, nor a kept row's on the same link. The
    two reads that asked about other rows and loads are gone."""
    recipe, case, other_case = new_id(), new_id(), new_id()
    first, refresh, theirs, their_refresh = new_id(), new_id(), new_id(), new_id()
    dropped, kept, their_dropped = new_id(), new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(
        run_id, _keyed(first, recipe, case), row_keys=[dropped, kept],
        row_elements={dropped: _elements(["n1"], ["e1"], ["v1", "v2"]),
                      kept: _elements(["n1"], ["e1"], ["v3"])},
    )  # fmt: skip
    await runs.add_record(
        run_id, _keyed(theirs, recipe, other_case), row_keys=[their_dropped],
        row_elements={their_dropped: _elements(["n1"], ["e1"], ["v9"])},
    )  # fmt: skip
    await runs.add_record(
        run_id, _keyed(refresh, recipe, case), withdrawn_row_keys=[dropped]
    )
    await runs.add_record(
        run_id,
        _keyed(their_refresh, recipe, other_case),
        withdrawn_row_keys=[their_dropped],
    )

    assert await runs.withdrawn_event_ids(refresh) == ["v1", "v2"]
    assert await runs.withdrawn_event_ids(their_refresh) == ["v9"]
    assert await runs.withdrawn_event_ids(first) == []
    assert not hasattr(runs, "elements_kept_by_other_rows")
    assert not hasattr(runs, "elements_in_other_records")


async def test_a_withdrawn_keys_definition_still_counts(runs: RecipeRunStore) -> None:
    """A run under another `deduplicate` is refused while keys under the old one are kept
    (ADR-127 decision 5); a withdrawn key waits to be restored by a revert, so it counts too."""
    recipe, case, first, refresh = new_id(), new_id(), new_id(), new_id()
    k1 = new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(
        run_id, _keyed(first, recipe, case), row_keys=[k1], row_key_fingerprint="old"
    )
    await runs.add_record(
        run_id, _keyed(refresh, recipe, case), withdrawn_row_keys=[k1]
    )
    assert await runs.fingerprints(recipe, case) == {"old": 1}


async def test_the_record_lookups_are_indexed(runs: RecipeRunStore) -> None:
    """`withdrawn_event_ids` reads by `withdrawn_by_load`, indexed. The GIN indexes on the id lists
    served the questions about which other row held an element, which Amendment 15 removed; they
    stay until a migration drops them (the studio REPORT's request), and are asserted so that one
    is not dropped by accident first."""
    rows = await runs._pool.fetch(
        "SELECT tablename, indexdef FROM pg_indexes "
        "WHERE tablename IN ('loaded_row_keys', 'withdrawn_row_keys')"
    )
    definitions = " ".join(f"{r['tablename']}: {r['indexdef']}" for r in rows)
    assert "USING gin (node_ids)" in definitions
    assert "USING gin (edge_ids)" in definitions
    assert (
        "withdrawn_row_keys: CREATE INDEX" in definitions
        and "(withdrawn_by_load)" in definitions
    )


async def test_a_records_own_key_merges_round_trip_and_no_run_view_carries_them(
    runs: RecipeRunStore,
) -> None:
    """ADR-110 Amendment 16: the prior state a returning row's load kept comes back from the real
    ledger exactly as written, for the revert; and the run's row, as `GET …/runs` shows it, carries
    none of it (rule 3, `test_link_prior_state_never_told.py` for the report and its views)."""
    import services.api.app as app_module
    from schemas.domain import Handling, Principal
    from schemas.ingest import LinkPriorState

    from tests.services.api.test_link_prior_state_never_told import SCHEME, SENTINEL

    recipe, case, load = new_id(), new_id(), new_id()
    prior = LinkPriorState(
        edge_id=new_id(), edge_type="TRANSACTED", revision=1, load_id=new_id(),
        handling=Handling(classification="SECRET", handling_code="P", originator="unit-1",
                          owning_unit="unit-1"),
        stored={"properties": {"memo": SENTINEL}},
    )  # fmt: skip
    run_id = await _started(runs, recipe)
    record = _keyed(load, recipe, case).model_copy(
        update={"own_key_merges": [prior], "merged_edge_ids": [prior.edge_id]}
    )
    await runs.add_record(run_id, record)

    held = await runs.load_record(load)
    assert held is not None and held.own_key_merges == [prior]
    assert held.own_key_merges[0].handling.classification == "SECRET"
    (row,) = [r for r in await runs.for_recipe(recipe, limit=5) if r.run_id == run_id]
    reader = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1")
    assert SENTINEL not in app_module._schedule_run_view(row, reader, SCHEME).model_dump_json()


async def test_withdrawn_row_links_answers_this_recipe_and_case_alone(
    runs: RecipeRunStore,
) -> None:
    """ADR-110 Amendment 16, rules 3 and 4: the links a returning row's own withdrawn key recorded,
    asked of this pipeline in this case. Another case's withdrawal of the same key, and another
    pipeline's in this case, are never this one's: a returning row would otherwise read and later
    restore a link that is not its own. Red with either condition removed (`L1.2a_RED_RECORD.md`)."""
    recipe, other_recipe, ours, theirs = new_id(), new_id(), new_id(), new_id()
    k1 = new_id()
    run_id = await _started(runs, recipe)
    other_run = await _started(runs, other_recipe)
    for rec, case, run, edge in (
        (recipe, ours, run_id, "e-ours"),
        (recipe, theirs, run_id, "e-theirs"),
        (other_recipe, ours, other_run, "e-other-pipeline"),
    ):
        load, refresh = new_id(), new_id()
        await runs.add_record(run, _keyed(load, rec, case), row_keys=[k1],
                              row_elements={k1: RowElements(node_ids=["n1"], edge_ids=[edge],
                                                            event_ids=["v1"],
                                                            edge_types={edge: "TRANSACTED"})})  # fmt: skip
        await runs.add_record(run, _keyed(refresh, rec, case), withdrawn_row_keys=[k1])

    assert await runs.withdrawn_row_links(recipe, ours, [k1]) == {k1: {"e-ours": "TRANSACTED"}}
    assert await runs.withdrawn_row_links(recipe, theirs, [k1]) == {
        k1: {"e-theirs": "TRANSACTED"}
    }
    assert await runs.withdrawn_row_links(other_recipe, ours, [k1]) == {
        k1: {"e-other-pipeline": "TRANSACTED"}
    }
    assert await runs.withdrawn_row_links(recipe, ours, [new_id()]) == {}


async def test_a_key_kept_before_link_types_were_recorded_reads_back_with_none(
    runs: RecipeRunStore,
) -> None:
    """ADR-110 Amendment 18: the `edge_types` column added by the store's own start-up DDL is NULL
    for a row kept before it. Such a key, once withdrawn, reads back from `withdrawn_row_links` with
    no links, so a returning row's merge into its link is never captured. A key kept since reads
    back with each link's type."""
    recipe, case, first, refresh = new_id(), new_id(), new_id(), new_id()
    old, new = new_id(), new_id()
    run_id = await _started(runs, recipe)
    elements = {
        old: RowElements(node_ids=["n1"], edge_ids=["e-old"], edge_types={"e-old": "TRANSACTED"}),
        new: RowElements(node_ids=["n2"], edge_ids=["e-new"], edge_types={"e-new": "TRANSACTED"}),
    }
    await runs.add_record(run_id, _keyed(first, recipe, case), row_keys=[old, new],
                          row_elements=elements)  # fmt: skip
    async with runs._pool.acquire() as conn:  # as the row was before the column held anything
        await conn.execute(
            "UPDATE loaded_row_keys SET edge_types = NULL WHERE recipe_id = $1 AND row_key = $2",
            recipe, old,
        )  # fmt: skip
    await runs.add_record(run_id, _keyed(refresh, recipe, case), withdrawn_row_keys=[old, new])

    assert await runs.withdrawn_row_links(recipe, case, [old, new]) == {
        old: {},
        new: {"e-new": "TRANSACTED"},
    }
