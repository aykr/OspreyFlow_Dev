"""ADR-110 Amendment 6 point 1, the wiring: a source refresh's read (its mode, what becomes of
dropped rows, its watermark column) reaches the load, through each hand it passes. The executor's
own hand is `test_schedule_executor.py`'s (`test_a_source_watch_runs_its_pipelines_in_the_sources_
mode`); the load's behaviour in each mode is `test_source_refresh_snapshot_live.py`'s and
`test_source_refresh_incremental_live.py`'s.

What a mistake would do, and the case that catches it: a hand that drops the read runs a full
snapshot that keeps every row, whatever the source says, and nothing else would notice.

- the deployment's `run` dropping it before `run_recipe_as`
  (`test_the_deployments_run_passes_the_read_to_run_recipe_as`);
- `run_recipe_as` or `_execute_recipe_run` dropping it before the load, for a recipe or a pipeline
  (`test_the_run_path_passes_the_read_to_the_load`);
- the stored sources' pairing dropping the policy's mode
  (`test_the_stored_watches_carry_the_policys_mode`)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
import services.api.app as app_module
import services.api.recipe_run as run_module
from services.api.folder_watch import WatchedFile
from services.api.source_refresh import StoredSourceWatches
from services.ingest.watermark import RefreshRead

from schemas.domain import Principal
from schemas.ingest import LoadReport, PipelineRunReport, StudioRecipeStatus
from schemas.sources import SourceRefresh, SourceTable

OWNER = Principal(id="owner-1", clearance="OFFICIAL", org_unit="unit-1")
READ = RefreshRead(
    source_id="src-1", mode="incremental", dropped_rows="keep", watermark_column="seq"
)
NOW = datetime(2026, 11, 6, 12, tzinfo=UTC)


async def test_the_deployments_run_passes_the_read_to_run_recipe_as(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    async def fake_run_recipe_as(deps: Any, **kwargs: Any) -> LoadReport:
        seen.update(kwargs)
        return LoadReport(load_id="l", recipe_id="r", recipe_version=1)

    monkeypatch.setattr(app_module, "run_recipe_as", fake_run_recipe_as)
    application = SimpleNamespace(state=MagicMock())
    executor = app_module._schedule_executor(application)  # type: ignore[arg-type]
    file = WatchedFile(
        name="calls-0601.csv",
        location="calls/calls-0601.csv",
        identity="calls-0601.csv:1:1",
        arrived_at=NOW,
    )
    recipe = SimpleNamespace(recipe_id="r", version=1)
    await executor.run(
        OWNER,
        recipe,
        "case-1",
        None,
        file,
        trigger="source_refresh",
        refresh=READ,  # type: ignore[arg-type]
    )
    assert seen["refresh"] == READ
    assert (seen["trigger"], seen["source_location"]) == ("source_refresh", "calls/calls-0601.csv")


@pytest.mark.parametrize("pipeline", [False, True])
async def test_the_run_path_passes_the_read_to_the_load(
    monkeypatch: pytest.MonkeyPatch, pipeline: bool
) -> None:
    seen: dict[str, Any] = {}

    async def fake_recipe(*args: Any, **kwargs: Any) -> LoadReport:
        seen.update(kwargs, ran="recipe")
        return LoadReport(load_id="l", recipe_id="r", recipe_version=1)

    async def fake_pipeline(*args: Any, **kwargs: Any) -> PipelineRunReport:
        seen.update(kwargs, ran="pipeline")
        return PipelineRunReport(load_id="l", recipe_id="r", recipe_version=1)

    async def no_rules(*args: Any, **kwargs: Any) -> None:
        return None

    async def nothing(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(run_module, "run_published_recipe", fake_recipe)
    monkeypatch.setattr(run_module, "run_published_pipeline", fake_pipeline)
    monkeypatch.setattr(run_module, "_rule_gate", no_rules)
    monkeypatch.setattr(
        run_module.resolution_trigger_module, "submit_post_ingest_resolution_jobs", nothing
    )
    monkeypatch.setattr(
        run_module, "ChangeStreamWriter", lambda valkey: SimpleNamespace(publish=nothing)
    )
    runs = MagicMock()

    async def started(**kwargs: Any) -> str:
        return "run-1"

    runs.start, runs.finish = started, nothing
    monkeypatch.setattr(run_module, "resolve_source_handling", lambda recipe: None)
    import dataclasses

    from adapters.media_objectstore.testing import InMemoryMediaStore

    stand_ins: dict[str, Any] = {
        "recipe_runs": runs,
        "audit": SimpleNamespace(record=nothing),
        "media": InMemoryMediaStore(),
        "config": SimpleNamespace(post_ingest_resolution=False),
        # ADR-141 decision 6: no quota here.
        "run_quotas": None,
    }
    names = [f.name for f in dataclasses.fields(run_module.RecipeRunDeps)]
    deps = run_module.RecipeRunDeps(**{n: stand_ins.get(n, object()) for n in names})
    recipe = SimpleNamespace(
        recipe_id="r", version=1, pipeline=object() if pipeline else None, row_template=None,
        dataset_id="ds-1", owning_unit="unit-1",
    )  # fmt: skip
    await run_module.run_recipe_as(
        deps,
        principal=OWNER,
        recipe=recipe,  # type: ignore[arg-type]
        investigation_id="case-1",
        source_location="calls/calls-0601.csv",
        trigger="source_refresh",
        refresh=READ,
    )
    assert seen["ran"] == ("pipeline" if pipeline else "recipe")
    assert seen["refresh"] == READ


async def test_the_stored_watches_carry_the_policys_mode() -> None:
    source = SourceTable(
        id="src-1", dataset_id="ds-1", connection_id="c-1", name="Calls", location="calls",
        connector_profile="generic-csv", created_by="admin-1", created_at=NOW,
        refresh=SourceRefresh(
            trigger="watch", pattern="calls-*.csv", mode="incremental",
            watermark_column="seq", owner="owner-1", set_at=NOW,
        ),
    )  # fmt: skip
    recipe = SimpleNamespace(status=StudioRecipeStatus.PUBLISHED)

    class Sources:
        async def watched(self) -> list[SourceTable]:
            return [source]

        async def set_refresh_paused(self, *args: Any, **kwargs: Any) -> None:
            return None

    class Readers:
        async def using_source(self, dataset_id: str, location: str) -> list[Any]:
            return [recipe]

    ((_, watch),) = await StoredSourceWatches(Sources(), Readers()).watching()
    assert watch.read == READ
