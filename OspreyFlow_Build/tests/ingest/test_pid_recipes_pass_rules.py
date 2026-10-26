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
- a recipe whose pins are not the ones a publish would stamp, which the seed refuses
  (`test_the_recipe_is_pinned_to_the_ontology_and_pack_the_deployment_carries`);
- a recipe with no legal basis, so a row of it is not `ready_for_profile`
  (`test_the_recipe_declares_its_legal_basis`);
- a probabilistic link written as if a source recorded it
  (`test_the_recipe_writes_no_probabilistic_type_and_no_resolution_link`);
- a `deduplicate` key naming a column the file lacks, or none at all
  (`test_the_recipe_deduplicates_on_columns_the_file_has`);
- an element that leaves a declared handling column unbound, so its rows load at the default marking
  whatever the cell says, which is rule 3 (`test_every_element_binds_every_declared_handling_part`);
- a file holding some of the six handling columns and not all, which would pass for the exempt
  file of none (`test_a_file_holds_all_six_handling_columns_or_none`);
- an element of an exempt file (no handling columns) that the plan marks other than at the recipe's
  defaults, which is the marking the file's elements take
  (`test_the_declared_units_cover_every_unit_the_file_holds`);
- the old demo's name in a recipe, or a unit that is not the PID's (`test_the_recipe_names_nothing_of_the_older_demo`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from services.api.studio_publish import pack_versions_for, serialise_recipe
from services.ingest.engine import check_recipe_pins
from services.ingest.recipe_rules import (
    deduplicate_problems,
    recipe_rule_violations,
    template_elements,
)

from demo_fixtures import pid_files, pid_plan
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.connectors import load_connector_profiles
from schemas.ingest import CONNECTORS_DIR, Recipe
from tools.pid_naming_check import scan_recipes

FIXTURES = Path(__file__).resolve().parents[3] / "OspreyFlow_Core/packages/demo_fixtures"
ONTOLOGY = load_deployment_ontology()
SCHEME = load_uk_le_scheme()

#: (recipe file, the source file it reads). A later PID recipe is one more line.
PID_RECIPES = [
    ("pid_nomis_prisoners_recipe.yaml", "pid_nomis_prisoners.csv"),
    ("pid_establishment_plan_recipe.yaml", "pid_establishment_plan.csv"),
    ("pid_nomis_cell_stays_recipe.yaml", "pid_nomis_cell_stays.csv"),
    ("pid_nomis_cell_shares_recipe.yaml", "pid_nomis_cell_shares.csv"),
    ("pid_nomis_visits_recipe.yaml", "pid_nomis_visits.csv"),
    ("pid_nomis_incidents_recipe.yaml", "pid_nomis_incidents.csv"),
    ("pid_soc_nominals_recipe.yaml", "pid_soc_nominals.csv"),
    ("pid_family_and_associates_recipe.yaml", "pid_family_and_associates.csv"),
    ("pid_codefendants_recipe.yaml", "pid_codefendants.csv"),
    ("pid_conflicts_recipe.yaml", "pid_conflicts.csv"),
    ("pid_number_owners_recipe.yaml", "pid_number_owners.csv"),
    ("pid_pin_calls_recipe.yaml", "pid_pin_calls.csv"),
    ("pid_seized_comms_recipe.yaml", "pid_seized_comms_batch1.csv"),
    ("pid_prisoner_money_recipe.yaml", "pid_prisoner_money.csv"),
    ("pid_throwover_log_recipe.yaml", "pid_throwover_log.csv"),
    ("pid_intel_reports_recipe.yaml", "pid_intel_reports.csv"),
    ("pid_report_incidents_recipe.yaml", "pid_report_incidents.csv"),
]


HANDLING_PARTS = (
    "classification", "handling_code", "action_code", "sanitisation_code", "originator",
    "owning_unit",
)  # fmt: skip


def _handling_held(source: str) -> set[str]:
    """Which of the six handling columns the file's header holds."""
    return set(pid_files.header_for(source)) & set(HANDLING_PARTS)


def _carries_handling(source: str) -> bool:
    """Whether the file holds the six handling columns. A file with none is exempt from binding
    them (the throw-over log: its recipe declares none and binds none, so every element takes the
    recipe's defaults). A file with some and not all is neither: it fails here, so no check below
    can take it for exempt (ADR-127 Amendment 18)."""
    held = _handling_held(source)
    assert held in (set(), set(HANDLING_PARTS)), (
        f"{source} holds some of the six handling columns but not all: {sorted(held)}"
    )
    return bool(held)


REPORTS_RECIPE = "pid_intel_reports_recipe.yaml"
PID_UNITS = {"fenwick-moor-security", "regional-intel-unit"}
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
    # Exactly what a Studio publish would stamp (ADR-127 Amendment 25): a pack the recipe neither
    # names nor writes a type of is not pinned, so a pack's version change flags only what it affects.
    # R9's file is the exception, open with the coordinator: it writes core types only, but its
    # draft's pipeline names NIEM 3, which is what a publish of that draft stamps.
    if file != REPORTS_RECIPE:
        assert recipe.pack_versions == pack_versions_for(
            recipe.pipeline, recipe.row_template, ONTOLOGY
        )
    check_recipe_pins(
        recipe, ONTOLOGY
    )  # raises StaleRecipeError if the pins are not the ones carried


@pytest.mark.parametrize(("file", "source"), PID_RECIPES)
def test_the_recipe_declares_its_legal_basis(file: str, source: str) -> None:
    assert load(file).defaults.legal_basis == "Synthetic demonstration data"


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
def test_a_file_holds_all_six_handling_columns_or_none(file: str, source: str) -> None:
    """The exemption from binding the handling columns is for a file with none of them. A file with
    some but not all is a defect in the file or the recipe, not an exemption."""
    assert _handling_held(source) in (set(), set(HANDLING_PARTS)), sorted(_handling_held(source))


@pytest.mark.parametrize(("file", "source"), PID_RECIPES)
def test_every_element_binds_every_declared_handling_part(file: str, source: str) -> None:
    recipe = load(file)
    if not _carries_handling(source):
        assert recipe.defaults.handling_columns == {}, "declares columns the file does not have"
        for element in template_elements(recipe.row_template):
            assert not any(isinstance(v, dict) for v in (element.handling or {}).values())
        return
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
def test_the_recipe_names_a_connector_profile_the_deployment_carries(
    file: str, source: str
) -> None:
    """The profile a recipe names must be a file in `connectors/`: a name no file answers to is
    `connector_not_available` at the first run."""
    assert load(file).connector.profile in load_connector_profiles(CONNECTORS_DIR)


def test_the_pin_calls_layout_is_a_profile_file_with_iso_instants_and_no_date_order() -> None:
    """ADR-127 / Brief 2 section 3.1: a new layout is a file. ISO-8601 instants carry their offset,
    so the profile declares no `date_order` (as the seizure profile), and no source CRS."""
    profile = load_connector_profiles(CONNECTORS_DIR)["pin-calls-csv"]
    assert (profile.reader, profile.delimiter, profile.header_rows) == ("csv", ",", 1)
    assert profile.date_order is None and profile.source_crs is None
    assert profile.available and profile.structured
    assert load("pid_pin_calls_recipe.yaml").connector.profile == "pin-calls-csv"
    assert not any(p.suffix == ".py" for p in CONNECTORS_DIR.iterdir()), "a profile needs no Python"


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
    # A column only the duplicate key reads (a visit's own reference) is read all the same.
    if recipe.deduplicate is not None:
        for binding in recipe.deduplicate.key:
            take(binding)
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
    """A file with the handling columns: every unit its rows name is a unit the recipe declares. A
    file with none: every element the plan writes from it is at the recipe's defaults."""
    import csv

    with (written / source).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    recipe = load(file)
    if _carries_handling(source):
        held = {r[c] for r in rows for c in ("originator", "owning_unit") if r[c]}
        assert held and held <= set(recipe.defaults.units), held - set(recipe.defaults.units)
        return
    # No handling columns: every element the plan writes from the file must be at the recipe's
    # defaults, since that is the marking every element of the file takes.
    declared = recipe.defaults.handling
    default = (
        declared["classification"],
        declared["handling_code"],
        None,
        None,
        declared["originator"],
        declared["owning_unit"],
    )
    plan = pid_plan.build_plan("demo")

    def mark(handling: Any) -> tuple[Any, ...]:
        return (
            handling.classification,
            handling.handling_code,
            handling.action_code,
            handling.sanitisation_code,
            handling.originator,
            handling.owning_unit,
        )

    entity_keys: dict[str, None] = {}
    link_keys: dict[str, None] = {}
    for row in pid_plan.rows_for(plan, source):
        entity_keys.update(dict.fromkeys(row.entities))
        link_keys.update(dict.fromkeys(row.links))
    assert entity_keys, "the plan writes nothing from the file, so this proves nothing"
    assert {mark(plan.entity(k).handling) for k in entity_keys} == {default}
    by_key = {lk.key: lk for lk in plan.links}
    assert {mark(by_key[k].handling) for k in link_keys} == {default}
    assert {declared["originator"], declared["owning_unit"]} <= set(recipe.defaults.units)


def test_the_list_names_every_pid_recipe_file() -> None:
    """A recipe file added without a line here is not held to these checks."""
    on_disk: set[Any] = {p.name for p in FIXTURES.glob("pid_*_recipe.yaml")}
    assert on_disk == {file for file, _ in PID_RECIPES}
