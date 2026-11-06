"""ADR-110 Amendment 6 point 1, in the run ledger: the watermark an incremental refresh reads from
is the latest one a succeeded run's unreverted load reached, per source, pipeline and case; and the
revert of a load is told how many later refreshes read past it.

Against the throwaway Postgres (`POSTGRES_PORT`). What a mistake would do, and the case that
catches it:

- a failed run's watermark kept, so the rows it did not finish are never read again
  (`test_the_watermark_is_the_latest_a_succeeded_unreverted_load_reached`);
- a reverted load's watermark kept, so the rows it took back are never read again (the same case);
- one pipeline's, case's or source's watermark read by another
  (`test_a_watermark_is_per_source_pipeline_and_case`);
- a load reverted while a later refresh read past it, so its rows are lost for good
  (`test_the_later_loads_that_read_past_a_load_are_counted`)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from itertools import count

import pytest
from services.api.config import PostgresConfig
from services.api.recipe_runs import RecipeRunStore

from conduit_common.identity import new_id
from schemas.ingest import LoadReport, SourceWatermark
from tests.services.api.test_recipe_runs import SOURCE, _keyed

T0 = datetime(2026, 11, 6, 6, 0, tzinfo=UTC)
#: Each refresh starts after the one before, as the executor's lock makes them.
_MINUTES = count()


@pytest.fixture
async def runs() -> AsyncIterator[RecipeRunStore]:
    store = await RecipeRunStore.connect(PostgresConfig.from_env().dsn)
    try:
        yield store
    finally:
        await store.close()


def _mark(value: str, source: str = "src-1") -> SourceWatermark:
    return SourceWatermark(source_id=source, column="seq", kind="number", value=value)


async def _run(
    runs: RecipeRunStore,
    recipe: str,
    case: str,
    value: str | None,
    *,
    outcome: str = "succeeded",
    source: str = "src-1",
) -> str:
    """One refresh's run and its load's record, as `run_recipe_as` writes them."""
    run_id = await runs.start(
        recipe_id=recipe, recipe_version=3, investigation_id=case, trigger="source_refresh",
        slot=None, run_as="owner-1", source=SOURCE, now=T0 + timedelta(minutes=next(_MINUTES)),
    )  # fmt: skip
    load = new_id()
    record = _keyed(load, recipe, case).model_copy(
        update={"watermark": None if value is None else _mark(value, source)}
    )
    await runs.add_record(run_id, record)
    if outcome == "succeeded":
        report = LoadReport(load_id=load, recipe_id=recipe, recipe_version=3)
        await runs.finish(run_id, report=report, now=T0)
    else:
        await runs.fail(run_id, failure="the events could not be written", now=T0)
    return load


async def test_the_watermark_is_the_latest_a_succeeded_unreverted_load_reached(
    runs: RecipeRunStore,
) -> None:
    recipe, case = new_id(), new_id()
    assert await runs.watermark(recipe, case, "src-1") is None
    await _run(runs, recipe, case, "10")
    second = await _run(runs, recipe, case, "20")
    assert await runs.watermark(recipe, case, "src-1") == _mark("20")

    await _run(runs, recipe, case, "30", outcome="failed")
    assert await runs.watermark(recipe, case, "src-1") == _mark("20"), "only a succeeded run"

    await runs.mark_reverted(second, reverted_by="admin-1", at=T0)
    assert await runs.watermark(recipe, case, "src-1") == _mark("10"), "a reverted load's goes"


async def test_a_watermark_is_per_source_pipeline_and_case(runs: RecipeRunStore) -> None:
    recipe, other_recipe, case, other_case = new_id(), new_id(), new_id(), new_id()
    await _run(runs, recipe, case, "10")
    await _run(runs, other_recipe, case, "99")
    await _run(runs, recipe, other_case, "98")
    await _run(runs, recipe, case, "97", source="src-2")
    await _run(runs, recipe, case, None)  # a run that read no source incrementally
    assert await runs.watermark(recipe, case, "src-1") == _mark("10")
    assert await runs.watermark(recipe, case, "src-2") == _mark("97", "src-2")


async def test_the_later_loads_that_read_past_a_load_are_counted(runs: RecipeRunStore) -> None:
    recipe, case = new_id(), new_id()
    first = await _run(runs, recipe, case, "10")
    second = await _run(runs, recipe, case, "20")
    await _run(runs, recipe, case, "5", source="src-2")  # another source
    await _run(runs, new_id(), case, "30")  # another pipeline
    assert await runs.reads_past(first) == 1
    assert await runs.reads_past(second) == 0
    await runs.mark_reverted(second, reverted_by="admin-1", at=T0)
    assert await runs.reads_past(first) == 0, "a reverted later load read nothing past it"
    assert await runs.reads_past(new_id()) == 0, "a load the ledger has no record of"
