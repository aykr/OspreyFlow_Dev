"""The demo-data generators belong to the product, and the product does not import from `tests/`.

Seen while planning the three-folder layout (ADR-054): the seeds, which are part of the product,
imported their synthetic data from the test tree, so a product without its tests could not seed a
demo. Each test below names what it would catch.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tools.layout import REPO as REPO_ROOT

PACKAGE = REPO_ROOT / "packages" / "demo_fixtures"

#: The generators the seeds call. Named, not discovered, so a generator that is deleted or moved
#: back is noticed.
GENERATORS = (
    "hmp",
    "hmp_graph",
    "hmp_population",
    "fixture_corp",
    "fixture_corp_resolution",
    "cdr",
    "sms",
    "seizure_record",
    "scenario_cohorts",
)
SEEDS = (
    "seed_hmp_fixture",
    "seed_fixture_corp",
    "seed_scenarios",
    "seed_ingest_folder",
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


@pytest.mark.parametrize("name", GENERATORS)
def test_each_generator_the_seeds_call_lives_in_the_product_package(name: str) -> None:
    assert (PACKAGE / f"{name}.py").is_file(), f"{name}.py is not in packages/demo_fixtures"


@pytest.mark.parametrize("name", GENERATORS)
def test_the_generators_do_not_import_from_the_test_tree(name: str) -> None:
    """Catches a generator that quietly reaches back into `tests/`."""
    modules = _imported_modules(PACKAGE / f"{name}.py")
    assert not {m for m in modules if m == "tests" or m.startswith("tests.")}


@pytest.mark.parametrize("name", SEEDS)
def test_the_seeds_do_not_import_from_the_test_tree(name: str) -> None:
    """The invariant itself: a seed is product code."""
    modules = _imported_modules(REPO_ROOT / "scripts" / f"{name}.py")
    assert not {m for m in modules if m == "tests" or m.startswith("tests.")}


def test_the_recipes_the_hmp_generator_loads_travel_with_it() -> None:
    """Catches a generator moved without its recipes: it would fail only when a seed ran."""
    from demo_fixtures import hmp_graph

    for recipe in (
        "hmp_yards_recipe.yaml",
        "hmp_persons_recipe.yaml",
        "hmp_families_recipe.yaml",
        "hmp_groups_recipe.yaml",
        "hmp_associates_recipe.yaml",
        "hmp_reports_recipe.yaml",
    ):
        assert (hmp_graph.FIXTURES / recipe).is_file(), recipe


def test_the_registry_names_the_real_locations_of_the_shipped_demos() -> None:
    """Shipped demos live in the tree, so their paths must exist. An internal dataset (PaySim,
    Enron) is absent from CI and from any other machine by design, so it is not asserted here; its
    own manifest test proves it is internal and refused by the packaging gate."""
    from scripts.demo_registry import shipped_manifests

    for manifest in shipped_manifests():
        for path in manifest.paths:
            assert (REPO_ROOT / path).is_file(), f"{manifest.id}: {path} does not exist"
