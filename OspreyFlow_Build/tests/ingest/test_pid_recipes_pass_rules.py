"""The Prison Intelligence Dataset's recipes (ADR-127 decision 12) pass the Studio's own checks.

Every PID recipe is a file under `packages/demo_fixtures/`, loaded here and held to what the Studio
holds a published recipe to: the recipe rules at the deployment ontology (the core and every shipped
pack), the pinned ontology and pack versions, a `deduplicate` key whose columns the source has, every
declared handling column bound by every element, and no relationship the sources do not record
(a Probabilistic type, `SAME_AS`, `NOT_SAME_AS`). The list below is the whole list: a later recipe
joins by one line. What a mistake would do, and the case that catches it:

- a recipe the Studio would refuse at Map save, shipped anyway
  (`test_the_recipe_passes_the_recipe_rules`);
- a recipe pinned to another ontology or pack version than the deployment carries, which a run
  refuses as stale (`test_the_recipe_is_pinned_to_the_ontology_and_pack_the_deployment_carries`);
- a probabilistic link written as if a source recorded it
  (`test_the_recipe_writes_no_probabilistic_type_and_no_resolution_link`);
- a `deduplicate` key naming a column the file lacks, or none at all
  (`test_the_recipe_deduplicates_on_columns_the_file_has`);
- an element that leaves a declared handling column unbound, so its rows load at the default marking
  whatever the cell says, which is rule 3 (`test_every_element_binds_every_declared_handling_part`);
- the old demo's name in a recipe, or a unit that is not the PID's (`test_the_recipe_names_nothing_of_the_older_demo`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from services.api.studio_publish import serialise_recipe
from services.ingest.engine import check_recipe_pins
from services.ingest.recipe_rules import (
    deduplicate_problems,
    recipe_rule_violations,
    template_elements,
)

from demo_fixtures import pid_files, pid_plan
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.ingest import Recipe
from tools.pid_naming_check import scan_recipes

FIXTURES = Path(__file__).resolve().parents[3] / "OspreyFlow_Core/packages/demo_fixtures"
ONTOLOGY = load_deployment_ontology()
SCHEME = load_uk_le_scheme()

#: (recipe file, the source file it reads). A later PID recipe is one more line.
PID_RECIPES = [
    ("pid_nomis_prisoners_recipe.yaml", "pid_nomis_prisoners.csv"),
]
PID_UNITS = {"fenwick-moor-security", "regional-intel-unit"}
HANDLING_PARTS = (
    "classification", "handling_code", "action_code", "sanitisation_code", "originator",
    "owning_unit",
)  # fmt: skip
RESOLUTION_LINKS = {"SAME_AS", "NOT_SAME_AS"}


def load(file: str) -> Recipe:
    return Recipe.model_validate(yaml.safe_load((FIXTURES / file).read_text(encoding="utf-8")))


def violations(recipe: Recipe, source_file: str) -> list[str]:
    return recipe_rule_violations(
        recipe.row_template,
        ONTOLOGY,
        source_columns=pid_files.header_for(source_file),
        units=recipe.defaults.units,
        defaults_handling=recipe.defaults.handling,
        scheme=SCHEME,
        handling_columns=recipe.defaults.handling_columns,
        declared_columns=recipe.defaults.handling_columns,
    )


@pytest.mark.parametrize(("file", "source"), PID_RECIPES)
def test_the_recipe_passes_the_recipe_rules(file: str, source: str) -> None:
    assert violations(load(file), source) == []


@pytest.mark.parametrize(("file", "source"), PID_RECIPES)
def test_the_recipe_is_pinned_to_the_ontology_and_pack_the_deployment_carries(
    file: str, source: str
) -> None:
    recipe = load(file)
    assert recipe.ontology_version == 16 == ONTOLOGY.version
    assert recipe.pack_versions == {"niem": ONTOLOGY.packs["niem"]}
    check_recipe_pins(recipe, ONTOLOGY)  # raises StaleRecipeError if the pins are not the ones carried


@pytest.mark.parametrize(("file", "source"), PID_RECIPES)
def test_the_recipe_writes_no_probabilistic_type_and_no_resolution_link(
    file: str, source: str
) -> None:
    recipe = load(file)
    by_name = {t.name: t for t in ONTOLOGY.edge_types}
    for edge in recipe.row_template.edges or []:
        assert edge.type not in RESOLUTION_LINKS, edge.type
        assert by_name[edge.type].basis == "direct", edge.type


@pytest.mark.parametrize(("file", "source"), PID_RECIPES)
def test_the_recipe_deduplicates_on_columns_the_file_has(file: str, source: str) -> None:
    recipe = load(file)
    assert recipe.deduplicate is not None and recipe.deduplicate.key, "no deduplicate key"
    assert deduplicate_problems(recipe.deduplicate, pid_files.header_for(source)) == []


@pytest.mark.parametrize(("file", "source"), PID_RECIPES)
def test_every_element_binds_every_declared_handling_part(file: str, source: str) -> None:
    recipe = load(file)
    assert set(recipe.defaults.handling_columns) == set(HANDLING_PARTS)
    for element in template_elements(recipe.row_template):
        bound = {k: v for k, v in (element.handling or {}).items() if isinstance(v, dict)}
        assert {k: v["field"] for k, v in bound.items()} == recipe.defaults.handling_columns, (
            getattr(element, "ref", getattr(element, "type", element))
        )


@pytest.mark.parametrize(("file", "source"), PID_RECIPES)
def test_the_recipe_names_nothing_of_the_older_demo(file: str, source: str) -> None:
    # The naming gate's own scan of a recipe file (it names the words, so this file need not).
    assert scan_recipes([FIXTURES / file]) == []
    assert "ravenscar" not in (FIXTURES / file).read_text(encoding="utf-8").lower()
    recipe = load(file)
    assert set(recipe.defaults.units) == PID_UNITS
    assert recipe.defaults.handling["originator"] in PID_UNITS
    assert recipe.defaults.handling["owning_unit"] in PID_UNITS
    assert recipe.label[:1].isupper() and not recipe.label.isupper()


@pytest.mark.parametrize(("file", "source"), PID_RECIPES)
def test_the_recipe_survives_the_studios_own_serialisation(file: str, source: str) -> None:
    """What the Studio would commit for it reads back as the same recipe."""
    recipe = load(file)
    again = Recipe.model_validate(yaml.safe_load(serialise_recipe(recipe)))
    assert again == recipe


def _bound_columns(recipe: Recipe) -> set[str]:
    """Every source column a binding of the recipe reads, apart from the handling columns."""
    columns: set[str] = set()

    def take(binding: Any) -> None:
        if binding is None:
            return
        columns.update(binding.fields or ([binding.field] if binding.field else []))

    for element in template_elements(recipe.row_template):
        for binding in element.properties.values():
            take(binding)
        if element.when is not None:
            columns.add(element.when.field)
        if element.content is not None:
            columns.add(element.content.field)
    for edge in recipe.row_template.edges:
        if edge.temporal is not None:
            take(edge.temporal.at)
            take(edge.temporal.valid_to)
    return columns


@pytest.fixture(scope="module")
def written(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("pid-files")
    pid_files.write_files(pid_plan.build_plan("demo"), folder)
    return folder


@pytest.mark.parametrize(("file", "source"), PID_RECIPES)
def test_every_source_column_is_accounted_for(file: str, source: str) -> None:
    """The file's header is exactly: the columns the recipe binds, the declared handling columns,
    and the columns it names as unmapped, each unmapped one with a note saying why. A column the
    recipe forgot is a column whose values never reach the case."""
    recipe = load(file)
    unmapped = {u.field for u in recipe.unmapped_fields}
    bound = _bound_columns(recipe)
    handling = set(recipe.defaults.handling_columns.values())
    assert set(pid_files.header_for(source)) == bound | handling | unmapped
    assert bound.isdisjoint(unmapped), bound & unmapped
    for entry in recipe.unmapped_fields:
        assert (entry.note or "").strip(), f"{entry.field} is unmapped with no note"


@pytest.mark.parametrize(("file", "source"), PID_RECIPES)
def test_the_declared_units_cover_every_unit_the_file_holds(
    file: str, source: str, written: Path
) -> None:
    import csv

    with (written / source).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    held = {r[c] for r in rows for c in ("originator", "owning_unit") if r[c]}
    recipe = load(file)
    assert held and held <= set(recipe.defaults.units), held - set(recipe.defaults.units)


def test_the_list_names_every_pid_recipe_file() -> None:
    """A recipe file added without a line here is not held to these checks."""
    on_disk: set[Any] = {p.name for p in FIXTURES.glob("pid_*_recipe.yaml")}
    assert on_disk == {file for file, _ in PID_RECIPES}
