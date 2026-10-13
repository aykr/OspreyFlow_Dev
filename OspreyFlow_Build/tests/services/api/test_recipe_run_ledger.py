"""ADR-110 decision 6, through the one run path: `run_recipe_as` writes the ledger row for every run
it makes — succeeded with the load's counts, or failed with the failure in words, and the failure
still raised to whoever started the run. Against the throwaway Postgres; the load itself is
replaced, since what is under test is the ledger around it."""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
import services.api.app as app_module
from services.api.config import PostgresConfig
from services.api.recipe_runs import RecipeRunStore

from conduit_common.identity import new_id
from schemas.domain import Handling, Principal
from schemas.ingest import LoadReport

SOURCE = Handling(
    classification="OFFICIAL", handling_code="P", owning_unit="unit-1", originator="unit-1"
)
LOADER = Principal(id="loader-1", clearance="OFFICIAL", org_unit="unit-1")


@pytest.fixture
async def runs() -> AsyncIterator[RecipeRunStore]:
    store = await RecipeRunStore.connect(PostgresConfig.from_env().dsn)
    try:
        yield store
    finally:
        await store.close()


def _deps(runs: RecipeRunStore) -> app_module.RecipeRunDeps:
    names = [f.name for f in dataclasses.fields(app_module.RecipeRunDeps)]
    return app_module.RecipeRunDeps(
        **{n: (runs if n == "recipe_runs" else object()) for n in names}  # type: ignore[arg-type]
    )


async def _run(
    runs: RecipeRunStore, monkeypatch: pytest.MonkeyPatch, outcome: Any
) -> tuple[str, Any]:
    recipe_id = new_id()

    async def execute(deps: Any, **kwargs: Any) -> LoadReport:
        if isinstance(outcome, Exception):
            raise outcome
        return outcome.model_copy(update={"recipe_id": recipe_id})

    monkeypatch.setattr(app_module, "_execute_recipe_run", execute)
    monkeypatch.setattr(app_module, "resolve_source_handling", lambda recipe: SOURCE)
    recipe = SimpleNamespace(recipe_id=recipe_id, version=2)
    result: Any
    try:
        result = await app_module.run_recipe_as(
            _deps(runs),
            principal=LOADER,
            recipe=recipe,  # type: ignore[arg-type]
            investigation_id="case-1",
            source_location=None,
            trigger="manual",
        )
    except Exception as error:  # noqa: BLE001 — the test reads what was raised
        result = error
    return recipe_id, result


async def test_a_run_that_loads_is_recorded_succeeded_with_its_counts(
    runs: RecipeRunStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = LoadReport(
        load_id="load-9", recipe_id="x", recipe_version=2, rows_read=3, nodes_created=2
    )
    recipe_id, result = await _run(runs, monkeypatch, report)
    assert isinstance(result, LoadReport)
    (row,) = await runs.for_recipe(recipe_id)
    assert (row.outcome, row.rows_read, row.nodes_created, row.load_id) == (
        "succeeded",
        3,
        2,
        "load-9",
    )
    assert (row.trigger, row.run_as, row.recipe_version, row.source) == (
        "manual",
        "loader-1",
        2,
        SOURCE,
    )
    assert row.finished_at is not None and row.finished_at <= datetime.now(UTC)


async def test_a_run_that_fails_is_recorded_failed_and_the_failure_still_raised(
    runs: RecipeRunStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe_id, result = await _run(runs, monkeypatch, FileNotFoundError("no such file: a.csv"))
    assert isinstance(result, FileNotFoundError)
    (row,) = await runs.for_recipe(recipe_id)
    assert row.outcome == "failed"
    assert row.failure == "FileNotFoundError: no such file: a.csv"
