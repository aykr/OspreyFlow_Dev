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
- an element kept by another row, of any pipeline or case, or listed by another load's record,
  withdrawn under it (`test_the_elements_another_kept_row_holds_are_found_whoever_kept_it`,
  `test_the_elements_another_unreverted_loads_record_lists_are_found`);
- a run under a changed `deduplicate` let through while a withdrawn key under the old one waits to
  be restored (`test_a_withdrawn_keys_definition_still_counts`)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from services.api.config import PostgresConfig
from services.api.recipe_runs import RecipeRunStore

from conduit_common.identity import new_id
from schemas.ingest import LoadRecord, RowElements
from tests.services.api.test_recipe_runs import _keyed, _started

T0 = datetime(2026, 11, 6, 6, 0, tzinfo=UTC)


@pytest.fixture
async def runs() -> AsyncIterator[RecipeRunStore]:
    store = await RecipeRunStore.connect(PostgresConfig.from_env().dsn)
    try:
        yield store
    finally:
        await store.close()


def _elements(nodes: list[str], edges: list[str]) -> RowElements:
    return RowElements(node_ids=nodes, edge_ids=edges)


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
        row_elements={k1: _elements(["n1", "n2"], ["e1"]), k2: _elements(["n1"], [])},
    )
    # A key kept before Amendment 8 has no record: NULL, not an empty one.
    await runs.add_record(run_id, _keyed(new_id(), recipe, case), row_keys=[legacy])

    dropped = {d.row_key: d for d in await runs.dropped_row_keys(recipe, case, present={k2})}
    assert set(dropped) == {k1, legacy}
    assert dropped[k1].load_id == load
    assert dropped[k1].node_ids == ("n1", "n2") and dropped[k1].edge_ids == ("e1",)
    assert dropped[legacy].node_ids is None and dropped[legacy].edge_ids is None
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
        row_elements={k1: _elements(["n1"], ["e1"]), k2: _elements(["n2"], ["e2"])},
        row_key_fingerprint="fp",
    )
    await runs.add_record(run_id, _keyed(refresh, recipe, case), withdrawn_row_keys=[k1])

    assert await runs.kept_row_keys(recipe, case, [k1, k2]) == {k2}
    assert [d.row_key for d in await runs.dropped_row_keys(recipe, case, present=set())] == [k2]
    assert await runs.restore_withdrawn_row_keys(refresh) == 1
    assert await runs.restore_withdrawn_row_keys(refresh) == 0
    assert await runs.kept_row_keys(recipe, case, [k1]) == {k1}
    (back,) = [
        d for d in await runs.dropped_row_keys(recipe, case, present={k2}) if d.row_key == k1
    ]
    assert (back.load_id, back.node_ids, back.edge_ids) == (first, ("n1",), ("e1",))
    assert await runs.fingerprints(recipe, case) == {"fp": 1}


async def test_a_withdrawn_key_kept_again_is_counted_until_that_load_is_reverted(
    runs: RecipeRunStore,
) -> None:
    recipe, case = new_id(), new_id()
    first, refresh, back = new_id(), new_id(), new_id()
    k1 = new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _keyed(first, recipe, case), row_keys=[k1])
    await runs.add_record(run_id, _keyed(refresh, recipe, case), withdrawn_row_keys=[k1])
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
    await runs.add_record(run_id, _keyed(refresh, recipe, case), withdrawn_row_keys=[k1])
    assert await runs.release_row_keys([first]) == 2, "the withdrawn key is the load's too"
    assert await runs.restore_withdrawn_row_keys(refresh) == 0
    assert await runs.kept_row_keys(recipe, case, [k1, k2]) == set()


async def test_the_elements_another_kept_row_holds_are_found_whoever_kept_it(
    runs: RecipeRunStore,
) -> None:
    recipe, other_recipe, case, other_case = new_id(), new_id(), new_id(), new_id()
    dropped, kept_here, kept_there, withdrawn = new_id(), new_id(), new_id(), new_id()
    n_mine, n_shared, n_far, n_gone = new_id(), new_id(), new_id(), new_id()
    e_mine, e_shared = new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(
        run_id,
        _keyed(new_id(), recipe, case),
        row_keys=[dropped, kept_here, withdrawn],
        row_elements={
            dropped: _elements([n_mine, n_shared, n_far, n_gone], [e_mine, e_shared]),
            kept_here: _elements([n_shared], [e_shared]),
            withdrawn: _elements([n_gone], []),
        },
    )
    # Another pipeline, in another case, holds `n_far`.
    await runs.add_record(
        run_id,
        _keyed(new_id(), other_recipe, other_case),
        row_keys=[kept_there],
        row_elements={kept_there: _elements([n_far], [])},
    )
    # A withdrawn key holds nothing: `n_gone` is not kept by it.
    await runs.add_record(run_id, _keyed(new_id(), recipe, case), withdrawn_row_keys=[withdrawn])

    nodes, edges = await runs.elements_kept_by_other_rows(
        [n_mine, n_shared, n_far, n_gone],
        [e_mine, e_shared],
        recipe_id=recipe,
        case=case,
        excluding=[dropped],
    )
    assert nodes == {n_shared, n_far}
    assert edges == {e_shared}
    assert await runs.elements_kept_by_other_rows(
        [], [], recipe_id=recipe, case=case, excluding=[dropped]
    ) == (set(), set())


async def test_the_elements_another_unreverted_loads_record_lists_are_found(
    runs: RecipeRunStore,
) -> None:
    recipe, case = new_id(), new_id()
    mine, other, reverted = new_id(), new_id(), new_id()
    n_mine, n_other, n_merged, n_reverted = new_id(), new_id(), new_id(), new_id()
    e_touched = new_id()
    run_id = await _started(runs, recipe)

    def record(load: str, **ids: list[str]) -> LoadRecord:
        return _keyed(load, recipe, case).model_copy(
            update={"created_node_ids": [], "touched_edge_ids": [], "created_edge_ids": [], **ids}
        )

    await runs.add_record(run_id, record(mine, created_node_ids=[n_mine, n_other]))
    await runs.add_record(
        run_id,
        record(other, created_node_ids=[n_other], merged_node_ids=[n_merged],
               touched_edge_ids=[e_touched]),
    )  # fmt: skip
    await runs.add_record(run_id, record(reverted, created_node_ids=[n_reverted]))
    await runs.mark_reverted(reverted, reverted_by="admin-1", at=T0)

    nodes, edges = await runs.elements_in_other_records(
        [n_mine, n_other, n_merged, n_reverted], [e_touched], excluding_loads=[mine]
    )
    assert nodes == {n_other, n_merged}
    assert edges == {e_touched}


async def test_a_withdrawn_keys_definition_still_counts(runs: RecipeRunStore) -> None:
    """A run under another `deduplicate` is refused while keys under the old one are kept
    (ADR-127 decision 5); a withdrawn key waits to be restored by a revert, so it counts too."""
    recipe, case, first, refresh = new_id(), new_id(), new_id(), new_id()
    k1 = new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(
        run_id, _keyed(first, recipe, case), row_keys=[k1], row_key_fingerprint="old"
    )
    await runs.add_record(run_id, _keyed(refresh, recipe, case), withdrawn_row_keys=[k1])
    assert await runs.fingerprints(recipe, case) == {"old": 1}


async def test_the_record_lookups_are_indexed(runs: RecipeRunStore) -> None:
    """Which kept row holds an element is asked of a million keys' records: by a GIN index on each
    id list, never a scan."""
    rows = await runs._pool.fetch(
        "SELECT tablename, indexdef FROM pg_indexes "
        "WHERE tablename IN ('loaded_row_keys', 'withdrawn_row_keys')"
    )
    definitions = " ".join(f"{r['tablename']}: {r['indexdef']}" for r in rows)
    assert "USING gin (node_ids)" in definitions
    assert "USING gin (edge_ids)" in definitions
    assert (
        "withdrawn_row_keys: CREATE INDEX" in definitions and "(withdrawn_by_load)" in definitions
    )
