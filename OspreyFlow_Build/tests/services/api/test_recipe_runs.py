"""ADR-110 decision 6: the run ledger. Every run, manual or scheduled, is a row in `recipe_runs`
with its outcome, its counts and the failure in words; a slot that did not run (refused, blocked,
skipped, missed) is a row too, so the history says what happened to every slot.

Against the throwaway Postgres (`POSTGRES_PORT`). The rows' readers (Admin, the Studio, the Glass's
*Data feeds*) are their routes' to filter (decisions 8 and 9); this store keeps each row's source
handling so they can."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from conduit_common.identity import new_id
from schemas.domain import Handling
from schemas.ingest import LoadRecord, LoadReport, RejectionRecord
from services.api.config import PostgresConfig
from services.api.recipe_runs import RecipeRunStore

SOURCE = Handling(
    classification="OFFICIAL", handling_code="P", owning_unit="unit-1", originator="unit-1"
)
T0 = datetime(2026, 10, 13, 6, 0, tzinfo=UTC)


@pytest.fixture
async def runs() -> AsyncIterator[RecipeRunStore]:
    store = await RecipeRunStore.connect(PostgresConfig.from_env().dsn)
    try:
        yield store
    finally:
        await store.close()


async def test_a_run_is_started_then_finished_with_its_counts(runs: RecipeRunStore) -> None:
    recipe = new_id()
    run_id = await runs.start(
        recipe_id=recipe, recipe_version=3, investigation_id="case-1", trigger="manual",
        slot=None, run_as="analyst-1", source=SOURCE, now=T0,
    )
    (running,) = await runs.for_recipe(recipe)
    assert running.outcome == "running" and running.finished_at is None
    report = LoadReport(
        load_id="load-1", recipe_id=recipe, recipe_version=3, rows_read=10, nodes_created=4,
        nodes_referenced=2, edges_created=5, rows_held=1,
        rejections=[RejectionRecord(row_index=7, reason="no date", sample="")],
    )
    await runs.finish(run_id, report=report, now=T0 + timedelta(seconds=9))
    (done,) = await runs.for_recipe(recipe)
    assert done.outcome == "succeeded"
    assert (done.rows_read, done.nodes_created, done.nodes_referenced, done.edges_created) == (
        10, 4, 2, 5,
    )
    assert (done.rows_rejected, done.rows_held, done.load_id) == (1, 1, "load-1")
    assert done.finished_at == T0 + timedelta(seconds=9)
    assert done.source == SOURCE and done.run_as == "analyst-1"


async def test_a_failed_run_keeps_the_failure_in_words(runs: RecipeRunStore) -> None:
    recipe = new_id()
    run_id = await runs.start(
        recipe_id=recipe, recipe_version=1, investigation_id="case-1", trigger="schedule",
        slot=T0, run_as="analyst-1", source=SOURCE, now=T0,
    )
    await runs.fail(run_id, failure="the source file is missing", now=T0)
    (row,) = await runs.for_recipe(recipe)
    assert (row.outcome, row.failure, row.slot) == ("failed", "the source file is missing", T0)


@pytest.mark.parametrize("outcome", ["refused", "blocked", "skipped", "missed"])
async def test_a_slot_that_did_not_run_is_a_row_too(runs: RecipeRunStore, outcome: str) -> None:
    recipe = new_id()
    await runs.record_not_run(
        recipe_id=recipe, recipe_version=1, investigation_id="case-1", trigger="schedule",
        slot=T0, run_as="analyst-1", source=SOURCE, outcome=outcome,  # type: ignore[arg-type]
        failure=f"{outcome} for a reason", now=T0,
    )
    (row,) = await runs.for_recipe(recipe)
    assert row.outcome == outcome and row.started_at == row.finished_at == T0
    assert row.failure == f"{outcome} for a reason" and row.rows_read is None


async def test_an_outcome_it_does_not_know_is_refused(runs: RecipeRunStore) -> None:
    with pytest.raises(ValueError, match="outcome"):
        await runs.record_not_run(
            recipe_id=new_id(), recipe_version=1, investigation_id="case-1", trigger="schedule",
            slot=T0, run_as="analyst-1", source=SOURCE, outcome="succeeded",  # type: ignore[arg-type]
            failure=None, now=T0,
        )


async def test_history_is_newest_first(runs: RecipeRunStore) -> None:
    recipe = new_id()
    for minutes in (0, 2, 1):
        await runs.record_not_run(
            recipe_id=recipe, recipe_version=1, investigation_id="case-1", trigger="schedule",
            slot=T0 + timedelta(minutes=minutes), run_as="a", source=SOURCE, outcome="missed",
            failure=None, now=T0 + timedelta(minutes=minutes),
        )
    assert [r.slot for r in await runs.for_recipe(recipe)] == [
        T0 + timedelta(minutes=m) for m in (2, 1, 0)
    ]


async def test_refusals_in_a_row_are_counted_and_a_success_resets_them(
    runs: RecipeRunStore,
) -> None:
    """Decision 3: three refused scheduled runs in a row pause the schedule."""
    recipe = new_id()

    async def refuse(minute: int) -> None:
        await runs.record_not_run(
            recipe_id=recipe, recipe_version=1, investigation_id="case-1", trigger="schedule",
            slot=T0 + timedelta(minutes=minute), run_as="a", source=SOURCE, outcome="refused",
            failure="owner revoked", now=T0 + timedelta(minutes=minute),
        )

    await refuse(0)
    await refuse(1)
    assert await runs.refusals_in_a_row(recipe) == 2
    ok = await runs.start(
        recipe_id=recipe, recipe_version=1, investigation_id="case-1", trigger="schedule",
        slot=T0 + timedelta(minutes=2), run_as="a", source=SOURCE, now=T0 + timedelta(minutes=2),
    )
    await runs.finish(
        ok, report=LoadReport(load_id="l", recipe_id=recipe, recipe_version=1),
        now=T0 + timedelta(minutes=2),
    )
    assert await runs.refusals_in_a_row(recipe) == 0
    await refuse(3)
    assert await runs.refusals_in_a_row(recipe) == 1


async def test_a_refusal_that_does_not_count_is_skipped_over_not_counted(
    runs: RecipeRunStore,
) -> None:
    """ADR-110 Amendment 3: an unreachable identity provider neither counts nor resets."""
    recipe = new_id()
    for minute, counts in enumerate([True, False, True, False]):
        await runs.record_not_run(
            recipe_id=recipe, recipe_version=1, investigation_id="case-1", trigger="schedule",
            slot=T0 + timedelta(minutes=minute), run_as="a", source=SOURCE, outcome="refused",
            failure="x", now=T0 + timedelta(minutes=minute), counts_toward_pause=counts,
        )  # fmt: skip
    assert await runs.refusals_in_a_row(recipe) == 2


# --- ADR-127 decision 6, Amendment 5: the load's record, kept beside the run -------------------


def _record(load_id: str, recipe: str, **changes: object) -> LoadRecord:
    return LoadRecord(
        load_id=load_id, recipe_id=recipe, recipe_version=3, source="private_cash.csv",
        started_at=T0, completed_at=T0, created_by="analyst-1", investigation_id="case-1",
        created_node_ids=["n1", "n2"], merged_node_ids=["doc-shared"],
        created_edge_ids=["e-new"], merged_edge_ids=["e-old"],
        touched_edge_ids=["e-new", "e-old"], events_stamped=True, **changes,
    )  # fmt: skip


async def _started(runs: RecipeRunStore, recipe: str, trigger: str = "manual") -> str:
    return await runs.start(
        recipe_id=recipe, recipe_version=3, investigation_id="case-1", trigger=trigger,  # type: ignore[arg-type]
        slot=None, run_as="analyst-1", source=SOURCE, now=T0,
    )  # fmt: skip


async def test_a_runs_record_round_trips_with_created_and_merged_kept_apart(
    runs: RecipeRunStore,
) -> None:
    recipe = new_id()
    run_id = await _started(runs, recipe)
    load_id = new_id()
    await runs.add_record(run_id, _record(load_id, recipe))
    kept = await runs.load_record(load_id)
    assert kept is not None
    assert (kept.created_node_ids, kept.merged_node_ids) == (["n1", "n2"], ["doc-shared"])
    assert (kept.created_edge_ids, kept.merged_edge_ids) == (["e-new"], ["e-old"])
    assert kept.investigation_id == "case-1" and kept.events_stamped is True
    assert kept.released_from is None and (kept.recipe_id, kept.recipe_version) == (recipe, 3)


async def test_a_record_written_at_the_commit_is_there_when_the_run_then_fails(
    runs: RecipeRunStore,
) -> None:
    """The record is appended to a run that is still `running`; a failure after it leaves it."""
    recipe = new_id()
    run_id = await _started(runs, recipe)
    load_id = new_id()
    await runs.add_record(run_id, _record(load_id, recipe))
    await runs.fail(run_id, failure="the analytics store is down", now=T0)
    assert (await runs.load_record(load_id)) is not None
    (row,) = await runs.for_recipe(recipe)
    assert row.outcome == "failed"


async def test_a_pipeline_runs_branch_records_are_each_found_by_their_own_load_id(
    runs: RecipeRunStore,
) -> None:
    recipe, base = new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _record(f"{base}:s1", recipe))
    await runs.add_record(run_id, _record(f"{base}:s2", recipe).model_copy(update={"source": "two.csv"}))
    await runs.finish(
        run_id, report=LoadReport(load_id=base, recipe_id=recipe, recipe_version=3), now=T0
    )
    second = await runs.load_record(f"{base}:s2")
    assert second is not None and second.source == "two.csv"
    first = await runs.load_record(f"{base}:s1")
    assert first is not None and first.source == "private_cash.csv"
    assert await runs.load_record(base) is None


async def test_the_geometry_refs_a_load_inserted_are_added_to_its_own_record_only(
    runs: RecipeRunStore,
) -> None:
    recipe, base = new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _record(f"{base}:s1", recipe))
    await runs.add_record(run_id, _record(f"{base}:s2", recipe))
    await runs.add_geometries(run_id, f"{base}:s2", ["g1", "g2"])
    first, second = await runs.load_record(f"{base}:s1"), await runs.load_record(f"{base}:s2")
    assert first is not None and first.created_geometry_refs == []
    assert second is not None and second.created_geometry_refs == ["g1", "g2"]
    assert second.created_edge_ids == ["e-new"], "the rest of the record is as it was"


async def test_what_an_alert_after_the_commit_wrote_is_added_to_its_loads_record_only(
    runs: RecipeRunStore,
) -> None:
    recipe, base = new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _record(f"{base}:s1", recipe))
    await runs.add_record(run_id, _record(f"{base}:s2", recipe))
    await runs.add_rule_writes(
        run_id, f"{base}:s2", node_ids=["alert-1"], created_edge_ids=["l-new"], merged_edge_ids=["l-old"]
    )
    first, second = await runs.load_record(f"{base}:s1"), await runs.load_record(f"{base}:s2")
    assert first is not None and first.created_node_ids == ["n1", "n2"]
    assert second is not None
    assert second.created_node_ids == ["n1", "n2", "alert-1"]
    assert second.created_edge_ids == ["e-new", "l-new"] and second.merged_edge_ids == ["e-old", "l-old"]
    assert second.touched_edge_ids == ["e-new", "e-old", "l-new", "l-old"]
    assert second.source == "private_cash.csv", "the rest of the record is as it was"


async def test_a_load_a_stage_wrote_for_is_marked_uncovered_and_the_other_is_not(
    runs: RecipeRunStore,
) -> None:
    recipe, base = new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _record(f"{base}:s1", recipe))
    await runs.add_record(run_id, _record(f"{base}:s2", recipe))
    await runs.mark_uncovered(run_id, f"{base}:s1")
    first, second = await runs.load_record(f"{base}:s1"), await runs.load_record(f"{base}:s2")
    assert first is not None and first.uncovered_writes is True
    assert second is not None and second.uncovered_writes is False


async def test_a_release_keeps_where_it_was_released_from(runs: RecipeRunStore) -> None:
    recipe = new_id()
    run_id = await _started(runs, recipe, "release")
    load_id, original = new_id(), new_id()
    await runs.add_record(run_id, _record(load_id, recipe, released_from=original))
    kept = await runs.load_record(load_id)
    assert kept is not None and kept.released_from == original
    assert [r.trigger for r in await runs.for_recipe(recipe)] == ["release"]


async def test_a_run_with_no_record_has_none_and_an_unknown_load_has_none(
    runs: RecipeRunStore,
) -> None:
    recipe = new_id()
    run_id = await _started(runs, recipe)
    load_id = new_id()
    await runs.finish(
        run_id, report=LoadReport(load_id=load_id, recipe_id=recipe, recipe_version=3), now=T0
    )
    assert await runs.load_record(load_id) is None
    assert await runs.load_record(new_id()) is None


async def test_a_ledger_made_before_records_is_brought_forward_and_keeps_its_runs() -> None:
    """`CREATE TABLE IF NOT EXISTS` leaves an old `recipe_runs` as it was; connecting must add the
    column, or every later `finish` fails on it. Run in a schema of its own, so the shared ledger
    is not touched."""
    import asyncpg
    from services.api import recipe_runs as module

    schema = f"mig_{new_id().lower().replace('-', '')[:20]}"
    dsn = PostgresConfig.from_env().dsn
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(f"CREATE SCHEMA {schema}")
        await conn.execute(f"SET search_path TO {schema}")
        await conn.execute(module._BOOTSTRAP_SQL.replace(module._ADD_LOAD_RECORDS, ""))
        columns = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = $1 AND table_name = 'recipe_runs'", schema,
            )
        }  # fmt: skip
        assert "load_records" not in columns
        await conn.execute(
            "INSERT INTO recipe_runs (run_id, recipe_id, recipe_version, investigation_id, "
            "trigger, run_as, source_handling, started_at, outcome) VALUES "
            "('old', 'r', 1, 'case-1', 'manual', 'a', $1::jsonb, now(), 'succeeded')",
            SOURCE.model_dump_json(),
        )
        await conn.execute(module._BOOTSTRAP_SQL)
        await conn.execute(module._BOOTSTRAP_SQL)  # and again: a no-op on a ledger that has it
        assert await conn.fetchval("SELECT load_records FROM recipe_runs WHERE run_id = 'old'") is None
    finally:
        await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        await conn.close()
