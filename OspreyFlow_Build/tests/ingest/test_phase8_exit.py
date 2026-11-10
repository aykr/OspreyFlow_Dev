"""Phase 8's exit (the build plan's phase 8; ADR-140 decisions 12, 13 and 16): the prototype's full
"Visits and contacts" pipeline, its two expert steps included (`fixtures/visits_contacts_calls/`),
published through `build_recipe` as the publish route builds it, committed, and run through
`run_published_pipeline`, the run route's path, on the synthetic data. Its run report discloses both
expert steps, and its view discloses them to a reader the counts are withheld from.

What a mistake would do, and the case that catches it:

- an expert step run but not disclosed, or disclosed only when the counts are shown
  (`test_the_full_pipeline_runs_and_its_report_discloses_both_expert_steps`);
- the fuzzy match merging, or asserting, what it decided (the same case: two Persons, one inferred
  SAME_AS between them);
- the SQL step's aggregate losing the calls it counted from the element's provenance (the same case:
  the booking names its prisoner's PIN calls, each a row of a file that exists);
- the run's SQL step reading rows its runner may not read (`test_the_run_s_sql_step_reads_with_the_
  runner_s_principal`, the run route's own reader).
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
from services.api.load_records import report_view
from services.api.pipeline_run import run_published_pipeline
from services.api.studio_publish import build_recipe, write_and_commit_recipe
from services.api.studio_staging import SourceRows, row_reader
from services.ingest.pipeline import pipeline_with_staging
from services.ingest.recipe_loader import load_recipe
from services.ingest.reference_list_import import import_list
from services.ingest.staging import ObjectStorageConfig
from services.ingest.staging_catalogue import StagedRef

from schemas.domain import Principal, ProvenanceState
from schemas.ingest import (
    PipelineEdge,
    PipelineGraph,
    PipelineNode,
    PipelineNodeKind,
    StudioRecipeDraft,
    StudioRecipeStatus,
)
from tests.ingest.recipe_test_support import LocalStore, ValidatingGraph
from tests.ingest.test_staged_run import ESTABLISHMENTS, ONTOLOGY, SCHEME
from tests.ingest.test_staged_run import FIXTURES as PHASE7
from tests.services.api.test_studio_staging_routes import _Models

FIXTURES = Path(__file__).parent / "fixtures" / "visits_contacts_calls"
RECIPE = load_recipe(FIXTURES / "visits_contacts_calls_recipe.yaml")
STORAGE = ObjectStorageConfig(bucket="staging")
LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1", roles=["loader"])
OFFICIAL_ONLY = Principal(id="reader-1", clearance="OFFICIAL", org_unit="unit-1")
HANDLING = {
    "classification": "OFFICIAL", "handling_code": "P", "originator": "unit-1",
    "owning_unit": "unit-1",
}  # fmt: skip
SOURCES = ("visit_bookings", "number_owners", "pin_calls")


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from services.ingest import staging

    root = tmp_path / "store"
    root.mkdir()
    monkeypatch.setattr(staging, "filesystem", lambda config: LocalStore(root))
    # The same synthetic list as phase 7's, admitted by its SHA-256 (rule 9).
    import_list(ESTABLISHMENTS, PHASE7 / "establishments.csv", storage=STORAGE)
    return root


def _draft(tmp_path: Path, handling: dict[str, str] | None = None) -> StudioRecipeDraft:
    nodes = [PipelineNode(id="domain", kind=PipelineNodeKind.DOMAIN_MODEL, label="Domain model")]
    edges = []
    for name in SOURCES:
        copy = tmp_path / f"{name}.csv"
        shutil.copy(FIXTURES / f"{name}.csv", copy)
        nodes.append(
            PipelineNode(
                id=name, kind=PipelineNodeKind.SOURCE, label=name,
                config={"source_location": str(copy)},
            )  # fmt: skip
        )
        edges.append(PipelineEdge(source="domain", target=name))
    nodes += [
        PipelineNode(id="map", kind=PipelineNodeKind.MAP, label="Map"),
        PipelineNode(id="load", kind=PipelineNodeKind.LOAD, label="Load"),
    ]
    edges.append(PipelineEdge(source="map", target="load"))
    assert RECIPE.staging
    return StudioRecipeDraft(
        recipe_id="visits-contacts-calls", version=1, status=StudioRecipeStatus.DRAFT,
        label="Visits and contacts, with calls", connector_profile="generic-csv",
        source_location=str(tmp_path / "visit_bookings.csv"), handling=handling or HANDLING,
        legal_basis="Synthetic demonstration data", owning_unit="unit-1", created_by="author-1",
        created_at=datetime(2026, 11, 8, tzinfo=UTC), ready_for_profile=True,
        row_template=RECIPE.row_template, unmapped_fields=RECIPE.unmapped_fields,
        pipeline=pipeline_with_staging(PipelineGraph(nodes=nodes, edges=edges), RECIPE.staging),
        dataset_id="pid",
    )  # fmt: skip


async def _published(tmp_path: Path) -> tuple[StudioRecipeDraft, Path]:
    # SECRET, so a reader cleared to OFFICIAL is a reader the run's counts are withheld from.
    draft = _draft(tmp_path, {**HANDLING, "classification": "SECRET"})
    recipe = build_recipe(
        draft, ontology_version=ONTOLOGY.version, pack_versions={},
        schedule_cron=None, schedule_watch=None,
    )  # fmt: skip
    assert recipe.staging and [s.kind for s in recipe.staging] == [
        "lookup", "join", "derive", "sql", "fuzzy_match",
    ]  # fmt: skip
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    git_path = await write_and_commit_recipe(recipe, repo_root=repo)
    return draft.model_copy(
        update={"status": StudioRecipeStatus.PUBLISHED, "git_path": git_path, "pack_versions": {}}
    ), repo


def _raw_row(store: Path, load_id: str, source: str, row: int) -> dict[str, str] | None:
    path = store / "staging" / "loads" / quote(load_id, safe="") / "raw.parquet"
    if not path.exists():
        return None
    for held in pq.read_table(path).to_pylist():
        if held["source"] == source and held["row_index"] == row:
            return json.loads(held["fields_json"])
    return None


async def test_the_full_pipeline_runs_and_its_report_discloses_both_expert_steps(
    tmp_path: Path, store: Path
) -> None:
    draft, repo = await _published(tmp_path)
    graph = ValidatingGraph(ONTOLOGY)
    report = await run_published_pipeline(
        draft, LOADER, graph=graph, ontology=ONTOLOGY, scheme=SCHEME,  # type: ignore[arg-type]
        load_id="exit-8", investigation_scope="case-1", repo_root=repo,
        recogniser_for=lambda *_: None,  # type: ignore[arg-type,return-value]
        target_models=_Models([ESTABLISHMENTS.id]),  # type: ignore[arg-type]
        staging_storage=STORAGE,
    )  # fmt: skip
    [branch] = report.branches
    done = branch.report
    # The run report discloses both expert steps, in words.
    disclosed = {d.step: d for d in done.expert_steps}
    assert set(disclosed) == {"calls", "visitor_owner"}
    assert disclosed["calls"].summary and disclosed["calls"].select
    assert disclosed["visitor_owner"].threshold == 0.6
    assert disclosed["visitor_owner"].same_as == ["visitor", "matched"]
    counts = {c.step: c for c in done.staging_steps}
    # The call of a prisoner with no booking reaches no booking: counted, not lost (rule 2).
    assert counts["calls"].filtered_out == 1
    fuzzy = counts["visitor_owner"]
    assert fuzzy.matched + fuzzy.unmatched == fuzzy.rows_in == 5 and fuzzy.matched >= 1
    # Its view discloses them to a reader the counts are withheld from, and to one they are not.
    for reader, withheld in ((LOADER, False), (OFFICIAL_ONLY, True)):
        view = report_view(report, reader, SCHEME)
        assert {d.step for d in view.expert_steps} == {"calls", "visitor_owner"}
        assert view.withheld is withheld
    # Two Persons and one inferred SAME_AS for a matched visitor; never one node.
    persons = [n for n in graph.committed_nodes if n.type == "Person"]
    same_as = [e for e in graph.committed_edges if e.type == "SAME_AS"]
    assert len(same_as) == fuzzy.matched
    for link in same_as:
        assert link.source != link.target
        assert link.provenance.state is ProvenanceState.INFERRED
        assert {link.source, link.target} <= {p.id for p in persons}
    # Every element's every source row is a row of a file that exists; the booking names the
    # calls its SQL step counted.
    sources: set[str] = set()
    for element in [*graph.committed_nodes, *graph.committed_edges]:
        for ref in element.provenance.sources:
            if ref.document_id.startswith("reference_list:"):
                continue
            row = int(ref.locator.removeprefix("row "))
            assert ref.load_id and _raw_row(store, ref.load_id, ref.document_id, row) is not None
            sources.add(ref.document_id)
    assert sources == set(SOURCES)
    whitlow = next(
        n for n in graph.committed_nodes
        if n.type == "Document" and n.properties.get("message_id") == "VB-2605-001"
    )  # fmt: skip
    assert str(whitlow.properties["title"]).endswith("3 PIN calls")
    assert sum(1 for s in whitlow.provenance.sources if s.document_id == "pin_calls") == 3


def test_the_run_s_sql_step_reads_with_the_runner_s_principal(tmp_path: Path) -> None:
    """ADR-140 decision 12, at the run route's own reader (`pipeline_run._run_staged_branch` passes
    `row_reader(draft, read, principal, scheme)` to the steps): a source row above the runner's
    clearance is one the SQL step may not read. Red with the reader replaced by one that reads
    everything (the principal replaced by an unlimited one)."""
    secret = {**HANDLING, "classification": "SECRET"}
    read = SourceRows(tables={}, raw={"visit_bookings": [{"booking_id": "VB-1"}]})
    ref = StagedRef("visit_bookings", 0, "k", "L")
    assert row_reader(_draft(tmp_path, secret), read, LOADER, SCHEME)(ref) is True
    assert row_reader(_draft(tmp_path, secret), read, OFFICIAL_ONLY, SCHEME)(ref) is False
    assert row_reader(_draft(tmp_path), read, OFFICIAL_ONLY, SCHEME)(ref) is True
