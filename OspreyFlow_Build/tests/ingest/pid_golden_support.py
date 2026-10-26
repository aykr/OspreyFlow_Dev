"""What the PID recipes' golden tests share: the plan, the real files, the committed recipes and the
load. A golden test derives every expectation from `pid_plan` (never typed), loads the real file
through `load_with_rules` against the graph stand-in with the deployment ontology, and loads the
recipes it depends on first, from the committed files, in the seed's order (R11, then R1, then the
rest). Not a test module."""

from __future__ import annotations

import csv
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from services.api.studio_publish import load_with_rules

from adapters.media_objectstore.testing import InMemoryMediaStore
from demo_fixtures import pid_files, pid_plan
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.domain import Principal
from schemas.ingest import Recipe
from tests.ingest.recipe_test_support import MergingGraph
from tests.ingest.test_row_keys import KeyStore, Sink

ONTOLOGY = load_deployment_ontology()
SCHEME = load_uk_le_scheme()
LOADER = Principal(id="data-engineer-1", clearance="SECRET", org_unit="fenwick-moor-security")
FIXTURES = Path(__file__).resolve().parents[3] / "OspreyFlow_Core/packages/demo_fixtures"
CASE = "pid-case"
PLAN = pid_plan.build_plan("demo")

#: file -> recipe file, for every recipe a golden test may need first.
RECIPE_OF = {
    "pid_establishment_plan.csv": "pid_establishment_plan_recipe.yaml",
    "pid_nomis_prisoners.csv": "pid_nomis_prisoners_recipe.yaml",
    "pid_nomis_cell_stays.csv": "pid_nomis_cell_stays_recipe.yaml",
    "pid_nomis_cell_shares.csv": "pid_nomis_cell_shares_recipe.yaml",
    "pid_nomis_visits.csv": "pid_nomis_visits_recipe.yaml",
    "pid_nomis_incidents.csv": "pid_nomis_incidents_recipe.yaml",
}


def recipe_for(file: str) -> Recipe:
    text = (FIXTURES / RECIPE_OF[file]).read_text(encoding="utf-8")
    return Recipe.model_validate(yaml.safe_load(text))


@lru_cache(maxsize=1)
def _folder() -> Path:
    folder = Path(tempfile.mkdtemp(prefix="pid-golden-"))
    pid_files.write_files(PLAN, folder)
    return folder


@lru_cache(maxsize=None)
def rows_of(file: str) -> tuple[dict[str, str], ...]:
    with (_folder() / file).open(newline="", encoding="utf-8") as handle:
        return tuple(csv.DictReader(handle))


def keys_in(file: str) -> tuple[list[str], list[str]]:
    """The plan's entity keys and link keys the file's rows write (`pid_plan.rows_for`)."""
    entities: dict[str, None] = {}
    links: dict[str, None] = {}
    for row in pid_plan.rows_for(PLAN, file):
        entities.update(dict.fromkeys(row.entities))
        links.update(dict.fromkeys(row.links))
    return list(entities), list(links)


async def load(
    graph: MergingGraph,
    file: str,
    sink: Sink | None,
    load_id: str | None = None,
    rows: list[dict[str, str]] | None = None,
    recipe: Recipe | None = None,
) -> tuple[Any, list[Any]]:
    report, events, _held = await load_with_rules(
        recipe or recipe_for(file),
        rows if rows is not None else list(rows_of(file)),
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id=load_id or f"load-{file}",
        investigation_scope=CASE,
        source=file,
        media=InMemoryMediaStore(),
        rules=None,
        scheme=SCHEME,
        sink=sink,  # type: ignore[arg-type]
    )
    return report, events


async def loaded(*files: str) -> tuple[MergingGraph, KeyStore, dict[str, Any]]:
    """A graph with each file loaded in the order given, through its committed recipe, as the seed
    runs them, and the row keys kept as the case keeps them. Returns the reports by file."""
    graph = MergingGraph(ONTOLOGY)
    store = KeyStore()
    reports: dict[str, Any] = {}
    for file in files:
        report, _events = await load(graph, file, Sink(store, CASE))
        assert report.rejections == [], (file, report.rejections[:3])
        reports[file] = report
    return graph, store, reports


def marking(handling: Any) -> tuple[Any, ...]:
    """A handling as the tuple the tests compare: the six parts, whichever type holds them."""
    return (
        handling.classification,
        handling.handling_code,
        getattr(handling, "action_code", None),
        getattr(handling, "sanitisation_code", None),
        handling.originator,
        handling.owning_unit,
    )
