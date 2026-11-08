"""Phase 7's exit (the build plan's phase 7; ADR-140 Amendment 12): the prototype's "Visits and
contacts" pipeline, minus its two expert steps, built in the Studio and run on the synthetic data,
with every created element traceable to its source rows.

The pipeline and its map are the ones the keyboard walk builds by keys (`ingest-studio.spec.ts`,
"phase 7's exit"), read from the same fixture, which `test_visits_pipeline_fixture.py` holds to the
server's own build of the exit recipe. Here the draft is published through `build_recipe`, as the
publish route builds it (its steps taken from the pipeline's nodes), committed, and run through
`run_published_pipeline`, the run route's path: each source read by a load of its own, the list
read from its version's file. Every element's every `SourceRef` must name a row of a file that
exists: a source row in its load's `raw.parquet`, or a list row in the list's version file. Shown
red by dropping the refs at the Join (`L1.4_RED_RECORD.md`, X1) and by staging a source's raw rows
under another load (X2).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import pyarrow.parquet as pq
import pytest
from services.api.pipeline_run import run_published_pipeline
from services.api.studio_publish import build_recipe, write_and_commit_recipe
from services.ingest.reference_list_import import import_list
from services.ingest.staging import ObjectStorageConfig

from schemas.domain import Principal
from schemas.ingest import (
    PipelineGraph,
    RowTemplate,
    StudioRecipeDraft,
    StudioRecipeStatus,
    UnmappedField,
)
from tests.ingest.recipe_test_support import LocalStore, ValidatingGraph
from tests.ingest.test_staged_run import ESTABLISHMENTS, FIXTURES, ONTOLOGY, SCHEME
from tests.ingest.test_visits_pipeline_fixture import FIXTURE
from tests.services.api.test_studio_staging_routes import _Models

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


async def _built_and_published(tmp_path: Path) -> tuple[StudioRecipeDraft, Path]:
    walked = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pipeline = PipelineGraph.model_validate(walked["pipeline"])
    for node in pipeline.nodes:
        if node.kind == "source":
            copy = tmp_path / f"{node.id}.csv"
            shutil.copy(FIXTURES / f"{node.id}.csv", copy)
            node.config = {**node.config, "source_location": str(copy)}
    draft = StudioRecipeDraft(
        recipe_id="visits-and-contacts", version=1, status=StudioRecipeStatus.DRAFT,
        label="Visits and contacts", connector_profile="generic-csv",
        source_location=str(tmp_path / "visit_bookings.csv"), handling=HANDLING,
        legal_basis="Synthetic demonstration data", owning_unit="unit-1", created_by="author-1",
        created_at=datetime(2026, 11, 8, tzinfo=UTC), ready_for_profile=True,
        row_template=RowTemplate.model_validate(walked["row_template"]),
        unmapped_fields=[UnmappedField.model_validate(f) for f in walked["unmapped_fields"]],
        pipeline=pipeline, dataset_id="pid",
    )  # fmt: skip
    recipe = build_recipe(
        draft, ontology_version=ONTOLOGY.version, pack_versions={},
        schedule_cron=None, schedule_watch=None,
    )  # fmt: skip
    assert recipe.staging and [s.id for s in recipe.staging] == [
        "with_establishment", "with_owner", "titled",
    ]  # fmt: skip
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    git_path = await write_and_commit_recipe(recipe, repo_root=repo)
    published = draft.model_copy(
        update={"status": StudioRecipeStatus.PUBLISHED, "git_path": git_path, "pack_versions": {}}
    )
    return published, repo


def _raw_row(store: Path, load_id: str, source: str, row: int) -> dict[str, str] | None:
    path = store / "staging" / "loads" / quote(load_id, safe="") / "raw.parquet"
    if not path.exists():
        return None
    for held in pq.read_table(path).to_pylist():
        if held["source"] == source and held["row_index"] == row:
            return json.loads(held["fields_json"])
    return None


def _list_row(store: Path, ref: str, row: int) -> bool:
    name, version = ref.removeprefix("reference_list:").split("@v")
    kept = f"{quote(name, safe='')}@v{version}.parquet"
    path = store / "staging" / "reference_lists" / "pid" / kept
    return path.exists() and 0 <= row < pq.read_table(path).num_rows


async def test_visits_and_contacts_runs_with_every_element_traceable(
    tmp_path: Path, store: Path
) -> None:
    draft, repo = await _built_and_published(tmp_path)
    graph = ValidatingGraph(ONTOLOGY)
    report = await run_published_pipeline(
        draft,
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        scheme=SCHEME,
        load_id="exit-run",
        investigation_scope="case-1",
        repo_root=repo,
        recogniser_for=lambda *_: None,  # type: ignore[arg-type,return-value]
        target_models=_Models([ESTABLISHMENTS.id]),  # type: ignore[arg-type]
        staging_storage=STORAGE,
    )
    [branch] = report.branches
    assert branch.report.rows_read == 10
    assert [(s.step, s.rows_out) for s in branch.report.staging_steps] == [
        ("with_establishment", 6), ("with_owner", 5), ("titled", 5),
    ]  # fmt: skip
    written = [*graph.committed_nodes, *graph.committed_edges]
    types = {e.type for e in written}
    assert {"Document", "Endpoint", "Person", "MENTIONED_IN", "USES"} <= types
    for element in written:
        sources = element.provenance.sources
        assert sources, element
        for ref in sources:
            row = int(ref.locator.removeprefix("row "))
            if ref.document_id.startswith("reference_list:"):
                assert ref.load_id is None
                assert _list_row(store, ref.document_id, row), ref
            else:
                assert ref.load_id == f"exit-run:{ref.document_id}", ref
                assert _raw_row(store, ref.load_id, ref.document_id, row) is not None, ref
    # A link the Join made names the booking that gave the number and the owner row that said whose
    # it is, each in its own source's load.
    uses = [e for e in graph.committed_edges if e.type == "USES"]
    assert uses
    for link in uses:
        tables = {r.document_id for r in link.provenance.sources}
        assert {"visit_bookings", "number_owners"} <= tables, tables
