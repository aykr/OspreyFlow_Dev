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
