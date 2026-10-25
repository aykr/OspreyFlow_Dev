"""ADR-127 decision 3: an element's handling can come per row from columns. What a mistake would do,
and the case that catches it:

- the `S2` row loaded unmarked, as the Studio did before
  (`test_the_row_with_s2_loads_as_s2_and_its_neighbours_do_not`);
- a column loosening a row's marking, so a cell hands a record to readers its source never meant
  (`test_a_looser_part_rejects_the_row_naming_the_part`, one case for each part, and the
  classification-alone check that `validate_handling_tightens` made is not enough: a looser
  handling code or action code passes it);
- a cell naming a unit the recipe does not declare, which a restricted code would then admit as a
  reader (`test_a_unit_the_recipe_does_not_declare_rejects_the_row`);
- a code the scheme does not define, which `merge_handling` would refuse mid-load
  (`test_a_code_the_scheme_does_not_define_rejects_the_row`);
- an empty cell treated as "none", which would loosen a default that has a value
  (`test_an_empty_cell_takes_the_elements_default`);
- a SECRET row readable by an OFFICIAL reader
  (`test_a_secret_row_is_invisible_to_an_official_reader`, rule 3).

The rows are Brief 1's real `pid_intel_reports.csv` (six handling columns, written by
`write_files`). The run is `load_with_rules` against the shared graph stand-in
(`recipe_test_support.py`). The live counterpart is `test_handling_from_columns_live.py`."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path
from typing import Any

import pytest
from services.api.document_reader import DocumentReaderService
from services.api.review import DocumentNotFoundError
from services.api.studio_publish import load_with_rules
from services.api.working_set.service import WorkingSetService
from services.ingest.recipe_rules import RecipeRuleError, recipe_rule_violations

from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import AuditStub, Node, NodeWrite, Principal
from schemas.ingest import Recipe
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    ValidatingGraph,
    local_staging,
)
from tests.services.api.test_email_extraction import (
    InMemoryCandidates,
    RecordingAnalytics,
    WritingGraph,
)
from tests.services.api.working_set.fakes import FakeWorkingSetStore
from tests.services.api.working_set.test_visible_link import SCHEME as READ_SCHEME

ONTOLOGY = load_default_ontology()
SCHEME = load_uk_le_scheme()
LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1")
FILE = "pid_intel_reports.csv"
FIELDS = (
    "classification",
    "handling_code",
    "action_code",
    "sanitisation_code",
    "originator",
    "owning_unit",
)
UNITS = ["unit-1", "unit-2"]


def real_rows() -> list[dict[str, str]]:
    from demo_fixtures import pid_files, pid_plan

    with tempfile.TemporaryDirectory(prefix="handling-columns-") as folder:
        pid_files.write_files(pid_plan.build_plan("demo"), Path(folder))
        with (Path(folder) / FILE).open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def reports() -> list[dict[str, str]]:
    return real_rows()


def _bound(*fields: str) -> dict[str, Any]:
    return {name: {"field": name} for name in fields}


def _recipe(
    handling: dict[str, Any] | None,
    *,
    defaults: dict[str, Any] | None = None,
    units: list[str] | None = None,
) -> Recipe:
    base = {
        "classification": "OFFICIAL",
        "handling_code": "P",
        "originator": "unit-1",
        "owning_unit": "unit-1",
    }
    document: dict[str, Any] = {
        "ref": "doc",
        "pole_class": "object",
        "type": "Document",
        "properties": {"title": {"field": "title"}},
        "content": {"kind": "document_text", "field": "report_text"},
    }
    if handling is not None:
        document["handling"] = handling
    return Recipe.model_validate(
        {
            "id": "pid-intel-reports",
            "version": 1,
            "label": "Intelligence reports",
            "connector": {"profile": "csv"},
            "ontology_version": ONTOLOGY.version,
            "pack_versions": {},
            "defaults": {
                "provenance": {"state": "asserted"},
                "handling": {**base, **(defaults or {})},
                **({"units": units} if units is not None else {}),
            },
            "row_template": {"entities": [document], "edges": []},
        }
    )


async def _run(
    recipe: Recipe, rows: list[dict[str, str]], graph: ValidatingGraph | None = None
) -> tuple[Any, ValidatingGraph]:
    graph = graph if graph is not None else ValidatingGraph(ONTOLOGY)
    report, _events, _held = await load_with_rules(
        recipe,
        rows,
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id="load-1",
        investigation_scope="case-1",
        source=FILE,
        media=InMemoryMediaStore(),
        rules=None,
        scheme=SCHEME,
    )
    return report, graph


def _row(title: str = "A report", **cells: str) -> dict[str, str]:
    row = {"title": title, "report_text": f"Text of {title}."}
    row.update({name: "" for name in FIELDS})
    row.update(cells)
    return row


def _documents(graph: ValidatingGraph) -> dict[str, NodeWrite]:
    return {str(n.properties["title"]): n for n in graph.committed_nodes if n.type == "Document"}


# --- the S4 outcome, on the real file ----------------------------------------------------


async def test_the_row_with_s2_loads_as_s2_and_its_neighbours_do_not(
    reports: list[dict[str, str]],
) -> None:
    plain = [r for r in reports if not r["action_code"] and not r["sanitisation_code"]][:2]
    s2 = next(r for r in reports if r["sanitisation_code"] == "S2")
    rows = [*plain, s2]
    units = sorted({r["originator"] for r in rows} | {r["owning_unit"] for r in rows})
    report, graph = await _run(_recipe(_bound(*FIELDS), units=units), rows)
    assert report.rejections == [], report.rejections
    documents = _documents(graph)
    assert {t: d.handling.sanitisation_code for t, d in documents.items()} == {
        plain[0]["title"]: None,
        plain[1]["title"]: None,
        s2["title"]: "S2",
    }
    for row in rows:
        marking = documents[row["title"]].handling
        assert (marking.originator, marking.owning_unit) == (row["originator"], row["owning_unit"])
        assert marking.action_code == (row["action_code"] or None)


# --- each of the six binds from a column -------------------------------------------------


@pytest.mark.parametrize(
    ("field", "cell"),
    [
        ("classification", "SECRET"),
        ("handling_code", "R"),
        ("action_code", "A1"),
        ("sanitisation_code", "S1"),
        ("originator", "unit-2"),
        ("owning_unit", "unit-2"),
    ],
)
async def test_each_field_binds_from_its_column(field: str, cell: str) -> None:
    rows = [_row("one", **{field: cell}), _row("two")]
    report, graph = await _run(_recipe(_bound(field), units=UNITS), rows)
    assert report.rejections == [], report.rejections
    documents = _documents(graph)
    assert getattr(documents["one"].handling, field) == cell
    default = {"classification": "OFFICIAL", "handling_code": "P", "originator": "unit-1"}
    assert getattr(documents["two"].handling, field) == default.get(
        field, "unit-1" if field == "owning_unit" else None
    )


# --- an empty cell takes the element's default -------------------------------------------


async def test_an_empty_cell_takes_the_elements_default() -> None:
    rows = [_row("empty"), _row("given", action_code="A1")]
    recipe = _recipe(_bound(*FIELDS), defaults={"action_code": "A2"}, units=UNITS)
    report, graph = await _run(recipe, rows)
    assert report.rejections == [], report.rejections
    documents = _documents(graph)
    marking = documents["empty"].handling
    assert (marking.classification, marking.handling_code) == ("OFFICIAL", "P")
    assert (marking.originator, marking.owning_unit) == ("unit-1", "unit-1")
    assert marking.action_code == "A2"  # the default's own, not "none"
    assert marking.sanitisation_code is None  # no default: none
    assert documents["given"].handling.action_code == "A1"


# --- tighten only, in every part ---------------------------------------------------------


@pytest.mark.parametrize(
    ("part", "default", "cell"),
    [
        ("classification", "SECRET", "OFFICIAL"),
        ("handling code", "R", "P"),
        ("action code", "A1", "A2"),
        ("sanitisation code", "S2", "S1"),
    ],
)
async def test_a_looser_part_rejects_the_row_naming_the_part(
    part: str, default: str, cell: str
) -> None:
    field = part.replace(" ", "_")
    rows = [_row("loose", **{field: cell}), _row("neighbour")]
    recipe = _recipe(_bound(field), defaults={field: default}, units=UNITS)
    report, graph = await _run(recipe, rows)
    (rejection,) = report.rejections
    assert part in rejection.reason and f"'{field}'" in rejection.reason
    assert f"'{cell}'" not in rejection.reason  # the part and column are named, never the cell
    assert sorted(_documents(graph)) == ["neighbour"]


# --- units -------------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["originator", "owning_unit"])
async def test_a_unit_the_recipe_does_not_declare_rejects_the_row(field: str) -> None:
    rows = [_row("stranger", **{field: "unit-9"}), _row("neighbour")]
    report, graph = await _run(_recipe(_bound(field), units=UNITS), rows)
    (rejection,) = report.rejections
    assert field.replace("_", " ") in rejection.reason and f"'{field}'" in rejection.reason
    assert "unit-9" not in rejection.reason
    assert sorted(_documents(graph)) == ["neighbour"]


# --- undefined codes ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "cell"),
    [
        ("classification", "TOP-SECRET"),
        ("handling_code", "Z"),
        ("action_code", "A9"),
        ("sanitisation_code", "S9"),
    ],
)
async def test_a_code_the_scheme_does_not_define_rejects_the_row(field: str, cell: str) -> None:
    rows = [_row("odd", **{field: cell}), _row("neighbour")]
    report, graph = await _run(_recipe(_bound(field), units=UNITS), rows)
    (rejection,) = report.rejections
    assert field.replace("_", " ") in rejection.reason and f"'{field}'" in rejection.reason
    assert cell not in rejection.reason and "does not define" in rejection.reason
    assert sorted(_documents(graph)) == ["neighbour"]


# --- a missing column at run -------------------------------------------------------------


async def test_a_bound_column_the_rows_do_not_have_rejects_them() -> None:
    rows = [{"title": "no column", "report_text": "Text."}]
    report, graph = await _run(_recipe(_bound("classification"), units=UNITS), rows)
    (rejection,) = report.rejections
    assert "classification" in rejection.reason and "column" in rejection.reason
    assert _documents(graph) == {}


# --- Map save ----------------------------------------------------------------------------


def test_a_binding_to_a_column_the_source_lacks_is_refused_at_save() -> None:
    recipe = _recipe(_bound("classification", "sanitisation_code"))
    problems = recipe_rule_violations(
        recipe.row_template, ONTOLOGY, source_columns=["title", "report_text", "classification"]
    )
    assert len(problems) == 1
    assert (
        "sanitisation_code" in problems[0] and "title, report_text, classification" in problems[0]
    )
    assert (
        recipe_rule_violations(recipe.row_template, ONTOLOGY) == []
    )  # columns unknown: not judged


@pytest.mark.parametrize("units", [None, []])
def test_a_unit_binding_without_a_units_list_is_refused_at_save(units: list[str] | None) -> None:
    recipe = _recipe(_bound("owning_unit"))
    problems = recipe_rule_violations(recipe.row_template, ONTOLOGY, units=units)
    assert len(problems) == 1 and "owning_unit" in problems[0] and "units" in problems[0]
    assert recipe_rule_violations(recipe.row_template, ONTOLOGY, units=UNITS) == []


async def test_a_unit_binding_without_a_units_list_is_refused_at_run() -> None:
    graph = ValidatingGraph(ONTOLOGY)
    with pytest.raises(RecipeRuleError, match="units"):
        await _run(_recipe(_bound("originator")), [_row("one", originator="unit-1")], graph)
    assert graph.commits == 0


# --- the schema --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "handling",
    [
        {"classification": {"column": "classification"}},
        {"classification": {"field": 3}},
        {"classification": {"field": "classification", "extra": "x"}},
        {"review_date": {"field": "review"}},
    ],
)
def test_only_a_field_binding_validates_and_only_for_the_six(handling: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="handling"):
        _recipe(handling, units=UNITS)


def test_a_binding_in_the_recipes_own_defaults_is_refused() -> None:
    """`defaults.handling` is the fallback a bound cell falls back to; it has none of its own."""
    with pytest.raises(ValueError, match="defaults"):
        _recipe(None, defaults={"classification": {"field": "classification"}})


def test_a_field_binding_validates() -> None:
    recipe = _recipe(_bound(*FIELDS), units=UNITS)
    (entity,) = recipe.row_template.entities
    assert entity.handling is not None and set(entity.handling) == set(FIELDS)


# --- rule 3: what a bound marking hides --------------------------------------------------


def _node(write: NodeWrite) -> Node:
    return Node(
        id=write.id,
        type=write.type,
        properties=write.properties,
        provenance=write.provenance,
        handling=write.handling,
        audit=AuditStub(created_at=write.created_at, created_by=write.created_by),
    )


async def test_a_secret_row_is_invisible_to_an_official_reader() -> None:
    rows = [_row("open"), _row("hidden", classification="SECRET")]
    media_graph = ValidatingGraph(ONTOLOGY)
    report, graph = await _run(_recipe(_bound("classification"), units=UNITS), rows, media_graph)
    assert report.rejections == []
    documents = _documents(graph)
    working = FakeWorkingSetStore()
    await working.add_nodes("case-1", [_node(n) for n in documents.values()])
    write_graph = WritingGraph()
    reader = DocumentReaderService(
        WorkingSetService(write_graph, working, READ_SCHEME),  # type: ignore[arg-type]
        RecordingAnalytics([]),  # type: ignore[arg-type]
        write_graph,  # type: ignore[arg-type]
        InMemoryCandidates(),  # type: ignore[arg-type]
    )
    official = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
    secret = Principal(id="analyst-2", clearance="SECRET", org_unit="unit-1")
    assert (await reader.read("case-1", documents["open"].id, official)).document_id
    assert (await reader.read("case-1", documents["hidden"].id, secret)).document_id
    with pytest.raises(DocumentNotFoundError) as refused:
        await reader.read("case-1", documents["hidden"].id, official)
    assert str(refused.value) == str(DocumentNotFoundError(documents["hidden"].id))
