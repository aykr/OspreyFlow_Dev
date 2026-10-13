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
from schemas.ingest import LoadReport, RejectionRecord
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
