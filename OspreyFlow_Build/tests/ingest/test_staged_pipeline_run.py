"""A staged pipeline's run (ADR-140 Amendment 12): the run route feeds a pipeline's sources to the
staging engine, each source read by a load of its own, so no two runs share a raw file (L1.3's item
12: nothing locked the check-then-write of a raw file against two runs naming one source load).

What a mistake would do, and the case that catches it:

- a source read under a load that is not its run's own, so two runs of one source write, or
  check-then-write, one raw file (`test_two_concurrent_runs_of_one_source_never_share_a_raw_file`);
- an element naming a load of another run (the same test);
- the run's metering left *not measured* though its steps staged rows
  (`test_a_staged_run_meters_the_rows_its_steps_staged_and_their_parquet`);
- the meter not reaching `RunMetering`, or reading 0 for a run that staged nothing
  (`test_a_run_s_metering_carries_what_its_steps_staged_and_none_for_an_unstaged_run`);
- a refresh that withdraws or reads incrementally going ahead over joined sources
  (`test_a_withdrawing_refresh_of_a_staged_pipeline_is_refused_in_words`).
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import pytest
from services.api.pipeline_run import run_published_pipeline
from services.api.studio_publish import write_and_commit_recipe
from services.ingest.metering import StagingMeter
from services.ingest.recipe_rules import RecipeRuleError
from services.ingest.reference_list_import import import_list
from services.ingest.staging import ObjectStorageConfig

from schemas.domain import Principal
from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus
from tests.ingest.recipe_test_support import LocalStore, ValidatingGraph
from tests.ingest.test_staged_run import ESTABLISHMENTS, FIXTURES, ONTOLOGY, RECIPE, SCHEME
from tests.services.api.test_studio_staging_routes import _Models, _pipeline

STORAGE = ObjectStorageConfig(bucket="staging")
LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1", roles=["loader"])
HANDLING = {
    "classification": "OFFICIAL", "handling_code": "P", "originator": "unit-1",
    "owning_unit": "unit-1",
}  # fmt: skip


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from services.ingest import staging

    root = tmp_path / "store"
    root.mkdir()
    monkeypatch.setattr(staging, "filesystem", lambda config: LocalStore(root))
    import_list(ESTABLISHMENTS, FIXTURES / "establishments.csv", storage=STORAGE)
    return root


async def _published(tmp_path: Path) -> tuple[StudioRecipeDraft, Path]:
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    bookings = tmp_path / "visit_bookings.csv"
    shutil.copy(FIXTURES / "visit_bookings.csv", bookings)
    pipeline = _pipeline(tmp_path)
    recipe = RECIPE.model_copy(update={"id": "recipe-1", "pipeline": pipeline})
    git_path = await write_and_commit_recipe(recipe, repo_root=repo)
    from datetime import UTC, datetime

    draft = StudioRecipeDraft(
        recipe_id="recipe-1", version=1, status=StudioRecipeStatus.PUBLISHED, label="Visits",
        connector_profile="generic-csv", source_location=str(bookings), handling=HANDLING,
        legal_basis="Synthetic demonstration data", owning_unit="unit-1", created_by="author-1",
        created_at=datetime(2026, 11, 8, tzinfo=UTC), ready_for_profile=True,
        row_template=RECIPE.row_template, pipeline=pipeline, git_path=git_path,
        dataset_id="pid", pack_versions={},
    )  # fmt: skip
    return draft, repo


async def _run(draft: StudioRecipeDraft, repo: Path, load_id: str, **kwargs: Any) -> Any:
    graph = ValidatingGraph(ONTOLOGY)
    report = await run_published_pipeline(
        draft,
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        scheme=SCHEME,
        load_id=load_id,
        investigation_scope="case-1",
        repo_root=repo,
        recogniser_for=lambda *_: None,  # type: ignore[arg-type,return-value]
        target_models=_Models([ESTABLISHMENTS.id]),  # type: ignore[arg-type]
        staging_storage=STORAGE,
        **kwargs,
    )
    return report, graph


def _raw_loads(root: Path) -> set[str]:
    return {unquote(p.parent.name) for p in root.rglob("raw.parquet")}


async def test_two_concurrent_runs_of_one_source_never_share_a_raw_file(
    tmp_path: Path, store: Path
) -> None:
    draft, repo = await _published(tmp_path)
    (first, graph_1), (second, graph_2) = await asyncio.gather(
        _run(draft, repo, "run-a"), _run(draft, repo, "run-b")
    )
    assert _raw_loads(store) == {
        "run-a:visit_bookings", "run-a:number_owners",
        "run-b:visit_bookings", "run-b:number_owners",
    }  # fmt: skip
    for report, graph, own in ((first, graph_1, "run-a"), (second, graph_2, "run-b")):
        [branch] = report.branches
        assert branch.report.load_id == own
        assert [s.step for s in branch.report.staging_steps] == [
            "with_establishment", "with_owner", "titled",
        ]  # fmt: skip
        loads = {
            ref.load_id
            for element in [*graph.committed_nodes, *graph.committed_edges]
            for ref in element.provenance.sources
            if ref.load_id is not None
        }
        assert loads and all(load.startswith(f"{own}:") for load in loads), loads


async def test_a_staged_run_meters_the_rows_its_steps_staged_and_their_parquet(
    tmp_path: Path, store: Path
) -> None:
    draft, repo = await _published(tmp_path)
    meter = StagingMeter()
    await _run(draft, repo, "run-m", staging_meter=meter)
    assert meter.rows_staged == 6 + 5 + 5
    assert meter.parquet_bytes is not None and meter.parquet_bytes > 0


async def test_a_withdrawing_refresh_of_a_staged_pipeline_is_refused_in_words(
    tmp_path: Path, store: Path
) -> None:
    draft, repo = await _published(tmp_path)
    with pytest.raises(RecipeRuleError, match="joins its sources through staging steps"):
        await _run(draft, repo, "run-w", withdraw_dropped=True)
    assert _raw_loads(store) == set()


def test_a_run_s_metering_carries_what_its_steps_staged_and_none_for_an_unstaged_run() -> None:
    from services.ingest.metering import metering_of

    from schemas.ingest import LoadReport

    report = LoadReport(load_id="l", recipe_id="r", recipe_version=1)
    meter = StagingMeter()
    unstaged = metering_of(report, wall_seconds=0.1, object_store_bytes=0, staging=meter)
    assert (unstaged.rows_staged, unstaged.parquet_bytes) == (None, None)  # not measured, never 0
    meter.add(16, 2048)
    staged = metering_of(report, wall_seconds=0.1, object_store_bytes=0, staging=meter)
    assert (staged.rows_staged, staged.parquet_bytes) == (16, 2048)
