"""ADR-127 decision 7(a): what a run's change-stream entry carries.

A hotlist, and a monitor, are shown the nodes a run *touched*. The entry carried only the nodes the
run created, so a hotlisted number a run linked to (an `Endpoint` another load had already written)
raised nothing. The entry now carries the nodes the run matched by reference as well. What a mistake
would do, and the case that catches it:

- a referenced node left out of the entry, so the coordinator's number loaded in R5 and linked by
  R6 raises no alert (`test_a_second_load_reports_the_nodes_it_matched_by_reference`,
  `test_the_pipeline_path_reports_the_nodes_its_branches_referenced`,
  `test_the_route_publishes_created_and_referenced_nodes_to_the_change_stream`);
- a node the load itself created listed as referenced as well, or twice
  (`test_a_node_this_load_created_is_not_also_referenced`);
- what the case's rules wrote into the load read as touched by the recipe, which ADR-127
  decision 6 keeps out (`test_what_the_rules_wrote_is_not_in_the_entry`);
- the ids reaching a route's answer (rules 3 and 7: `test_no_route_answer_carries_the_referenced_ids`);
- a run that created nothing publishing nothing, so a monitor never wakes for it
  (`test_a_run_that_only_referenced_nodes_still_publishes_an_entry`).
"""

from __future__ import annotations

import ast
import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from services.api.change_stream import ChangeStreamWriter, touched_node_ids
from services.api.load_records import report_view
from services.api.pipeline_run import run_published_pipeline
from services.api.studio_publish import load_with_rules, run_published_recipe, serialise_recipe

from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Principal
from schemas.ingest import (
    LoadReport,
    PipelineRunReport,
    StudioRecipeDraft,
    StudioRecipeStatus,
)
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)
from tests.ingest.test_load_record_created_and_merged import _recipe

ONTOLOGY = load_default_ontology()
SCHEME = load_uk_le_scheme()
LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1")
NOW = datetime(2026, 10, 26, tzinfo=UTC)
CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"

ROWS = [
    {"payer": "SYN-1", "payee": "SYN-2", "paid_at": "2026-03-01T09:00:00+00:00", "memo": ""},
    {"payer": "SYN-3", "payee": "SYN-2", "paid_at": "2026-03-02T09:00:00+00:00", "memo": ""},
]


async def _load(graph: MergingGraph, rows: list[dict[str, str]], load_id: str, **kw: Any) -> LoadReport:
    report, _events, _held = await load_with_rules(
        kw.pop("recipe", None) or _recipe(),
        rows,
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id=load_id,
        investigation_scope="case-1",
        source="private_cash.csv",
        media=InMemoryMediaStore(),
        rules=kw.pop("rules", None),
        scheme=SCHEME,
    )
    assert report.rejections == [], report.rejections
    return report


async def test_a_second_load_reports_the_nodes_it_matched_by_reference() -> None:
    graph = MergingGraph(ONTOLOGY)
    first = await _load(graph, ROWS, "load-1")
    second = await _load(graph, ROWS, "load-2")
    assert first.referenced_node_ids == [] and len(first.created_node_ids) == 3
    assert second.created_node_ids == []
    assert sorted(second.referenced_node_ids) == sorted(first.created_node_ids)
    assert len(second.referenced_node_ids) == len(set(second.referenced_node_ids)), "each once"


async def test_a_node_this_load_created_is_not_also_referenced() -> None:
    """SYN-2 is created by the first row and matched again by the second row of the same load: it is
    this load's own, found again, not a node the load merely touched."""
    graph = MergingGraph(ONTOLOGY)
    report = await _load(graph, ROWS, "load-1")
    assert report.nodes_referenced >= 1, "the second row did match SYN-2 again"
    assert report.referenced_node_ids == []
    assert set(report.created_node_ids).isdisjoint(report.referenced_node_ids)


async def test_what_the_rules_wrote_is_not_in_the_entry() -> None:
    """ADR-127 decision 6 keeps what a rule writes (an alert, its links) out of the lists the change
    stream reads, so a monitor never sees its own alert as a new node; this is the same for the
    referenced list, which is built from what the recipe matched and never from `rule_node_ids`."""
    graph = MergingGraph(ONTOLOGY)
    first = await _load(graph, ROWS, "load-1")
    second = await _load(graph, ROWS, "load-2")
    second.rule_node_ids.append("alert-node-1")
    ids = touched_node_ids(second)
    assert "alert-node-1" not in ids
    assert ids == second.referenced_node_ids
    assert set(ids) == set(first.created_node_ids)


def test_the_entry_is_the_created_then_the_referenced_nodes_each_once() -> None:
    load = LoadReport(
        load_id="l", recipe_id="r", recipe_version=1,
        created_node_ids=["a", "b"], referenced_node_ids=["b", "c", "c"],
    )  # fmt: skip
    assert touched_node_ids(load) == ["a", "b", "c"]
    pipeline = PipelineRunReport(
        load_id="l", recipe_id="r", recipe_version=1,
        created_node_ids=["x"], referenced_node_ids=["y", "x"],
    )  # fmt: skip
    assert touched_node_ids(pipeline) == ["x", "y"]
    assert touched_node_ids(LoadReport(load_id="l", recipe_id="r", recipe_version=1)) == []


class _Valkey:
    def __init__(self) -> None:
        self.added: list[dict[str, str]] = []

    async def xadd(self, key: str, fields: dict[str, str], **options: object) -> bytes:
        self.added.append(fields)
        return b"1-0"


async def test_a_run_that_only_referenced_nodes_still_publishes_an_entry() -> None:
    """Before, a run that created no node published nothing, so no hotlist and no monitor woke for
    it however many nodes it touched."""
    graph = MergingGraph(ONTOLOGY)
    await _load(graph, ROWS, "load-1")
    second = await _load(graph, ROWS, "load-2")
    assert second.created_node_ids == []
    valkey = _Valkey()
    entry = await ChangeStreamWriter(valkey).publish(  # type: ignore[arg-type]
        "ingest", node_ids=touched_node_ids(second), investigation_id="case-1"
    )
    assert entry is not None
    assert sorted(entry.node_ids) == sorted(second.referenced_node_ids)
    assert valkey.added[0]["node_ids"].split(",") == entry.node_ids


def _published(tmp_path: Path) -> tuple[Path, StudioRecipeDraft]:
    repo = tmp_path / "repo"
    (repo / "recipes").mkdir(parents=True)
    (repo / "recipes" / "private-cash.yaml").write_text(serialise_recipe(_recipe()))
    source = tmp_path / "cash.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ROWS[0]))
        writer.writeheader()
        writer.writerows(ROWS)
    draft = StudioRecipeDraft(
        recipe_id="private-cash", version=1, status=StudioRecipeStatus.PUBLISHED,
        label="Private cash", connector_profile="generic-csv", source_location=str(source),
        owning_unit="unit-1", created_by="analyst-1", created_at=NOW,
        git_path="recipes/private-cash.yaml",
    )  # fmt: skip
    return repo, draft


async def test_the_pipeline_path_reports_the_nodes_its_branches_referenced(tmp_path: Path) -> None:
    repo, draft = _published(tmp_path)
    graph = MergingGraph(ONTOLOGY)

    async def run(load_id: str) -> PipelineRunReport:
        return await run_published_pipeline(
            draft, LOADER, graph=graph,  # type: ignore[arg-type]
            ontology=ONTOLOGY, scheme=SCHEME, load_id=load_id, investigation_scope="case-1",
            repo_root=repo, recogniser_for=lambda name: None, media=InMemoryMediaStore(),
        )  # fmt: skip

    first = await run("p-1")
    second = await run("p-2")
    assert first.referenced_node_ids == [] and len(first.created_node_ids) == 3
    assert second.created_node_ids == []
    assert sorted(second.referenced_node_ids) == sorted(first.created_node_ids)
    assert second.branches[0].report.referenced_node_ids == second.referenced_node_ids
    assert touched_node_ids(second) == second.referenced_node_ids


async def test_a_plain_published_run_reports_them_too(tmp_path: Path) -> None:
    repo, draft = _published(tmp_path)
    graph = MergingGraph(ONTOLOGY)

    async def run(load_id: str) -> LoadReport:
        return await run_published_recipe(
            draft, LOADER, graph=graph,  # type: ignore[arg-type]
            ontology=ONTOLOGY, load_id=load_id, investigation_scope="case-1", repo_root=repo,
            media=InMemoryMediaStore(), scheme=SCHEME,
        )  # fmt: skip

    first = await run("r-1")
    second = await run("r-2")
    assert sorted(second.referenced_node_ids) == sorted(first.created_node_ids)


def test_the_route_publishes_created_and_referenced_nodes_to_the_change_stream() -> None:
    """Rule 12: the sentence is about the route, so the test reads the route. `run_studio_recipe`
    publishes the entry the watches are evaluated against; its `node_ids` must come from
    `touched_node_ids(report)`, not from `report.created_node_ids` alone. (The route needs the whole
    dev stack to run, which `test_phase7_stage6c_watch_routes.py`'s two S7 cases do.)"""
    tree = ast.parse((CORE / "services/api/app.py").read_text())
    published: list[ast.Call] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "publish"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "ingest"
        ):
            published.append(node)
    assert len(published) == 1, "one producer publishes ingest entries"
    (keyword,) = [k for k in published[0].keywords if k.arg == "node_ids"]
    value = keyword.value
    assert isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
    assert value.func.id == "touched_node_ids"


def test_no_route_answer_carries_the_referenced_ids() -> None:
    """Rules 3 and 7: the ids are for the change stream and the load's own bookkeeping; a loader is
    never told which existing nodes their file matched."""
    load = LoadReport(
        load_id="l", recipe_id="r", recipe_version=1, referenced_node_ids=["secret-node-id"]
    )
    assert "secret-node-id" not in report_view(load).model_dump_json()
    pipeline = PipelineRunReport(
        load_id="l", recipe_id="r", recipe_version=1, referenced_node_ids=["secret-node-id"],
        branches=[],
    )  # fmt: skip
    assert "secret-node-id" not in report_view(pipeline).model_dump_json()


# --- decision 8: the alert names the source file through the matched node's provenance ----------


async def test_a_node_a_plain_recipe_creates_names_its_source_file_in_its_provenance(
    tmp_path: Path,
) -> None:
    """ADR-127 decision 8: the alert's matched node is the node the run wrote, and it names the file
    it was loaded from in `provenance.sources[*].document_id`, with the row in the locator. No
    `Document` node is written for a plain recipe: the file is the provenance, not a node."""
    repo, draft = _published(tmp_path)
    graph = MergingGraph(ONTOLOGY)
    report = await run_published_recipe(
        draft, LOADER, graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY, load_id="r-1", investigation_scope="case-1", repo_root=repo,
        media=InMemoryMediaStore(), scheme=SCHEME,
    )  # fmt: skip
    source = draft.source_location
    assert source is not None and source.endswith("cash.csv")
    created = [n for n in graph.committed_nodes if n.id in report.created_node_ids]
    assert len(created) == 3
    for node in created:
        assert [s.document_id for s in node.provenance.sources] == [source]
        assert node.provenance.sources[0].locator.startswith("row ")
    assert [n for n in graph.committed_nodes if n.type == "Document"] == []
