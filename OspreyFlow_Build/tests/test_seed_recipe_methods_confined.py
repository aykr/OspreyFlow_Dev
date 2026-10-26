"""ADR-127 Amendment 23 (B2-10a): two methods of `StudioRecipeStore` write what no route may.

- `enter_published_for_seed` enters a committed recipe as published, keeping its id, with no
  verify, no approver and no publish route in between;
- `restore_to_draft` sets a recipe's latest version, whatever its status, to superseded and writes a
  draft in its place.

Each skips the gates a route puts on a publish and a new version (the roles, the unit check, the
verify), so a route that called either would let a caller past them. `scripts/seed_pid.py` (the
seed, the reset and the fallback publication, each run by an operator with the Conduit stopped or
beside it) is the one module that may. That file is built in a later unit and does not exist yet:
it is allowed by name, and when it does, the check that it calls them is added beside this one.

The scan is `test_unfiltered_node_lookup_confined.callers`: an attribute access of the name, or a
string equal to it (which is how `getattr(store, "enter_published_for_seed")` would reach it). It is
shown red on planted cases (`test_the_check_flags_*`), and against the tree itself."""

from __future__ import annotations

from pathlib import Path

from tests.test_unfiltered_node_lookup_confined import callers

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
SEED_MODULE = "scripts/seed_pid.py"
CONFINED = {
    "enter_published_for_seed": {SEED_MODULE},
    "restore_to_draft": {SEED_MODULE},
}
ROOTS = ("services", "scripts", "packages", "cli", "harness")


def test_only_the_seed_module_names_the_seed_methods() -> None:
    for name, allowed in CONFINED.items():
        offenders = {f for root in ROOTS for f in callers(CORE / root, CORE, name) if f not in allowed}
        assert offenders == set(), f"these name StudioRecipeStore.{name}: {sorted(offenders)}"


def test_the_roots_are_every_product_folder_that_holds_python() -> None:
    """A caller in the `ospreyflow` command (`cli/`) or the harness would be as outside the seed as a
    route: every folder of the product that holds Python is scanned."""
    holding = {p.name for p in CORE.iterdir() if p.is_dir() and any(p.rglob("*.py"))}
    skipped = {"apps", "node_modules", ".venv", "providers", "config", "connectors", "data",
               "deploy", "recipes", "backups", "docs"}  # fmt: skip
    assert holding - skipped <= set(ROOTS), sorted(holding - skipped - set(ROOTS))


def test_no_route_names_them() -> None:
    app = CORE / "services/api/app.py"
    text = app.read_text(encoding="utf-8")
    for name in CONFINED:
        assert name not in text, name


def test_the_check_flags_a_call_outside_the_seed_module(tmp_path: Path) -> None:
    for name in CONFINED:
        (tmp_path / f"{name}.py").write_text(
            f"async def route(store, recipe):\n    return await store.{name}(recipe)\n"
        )
    (tmp_path / "quiet.py").write_text("def f(store):\n    return store.get('x')\n")
    for name in CONFINED:
        assert callers(tmp_path, tmp_path, name) == {f"{name}.py"}


def test_the_check_flags_a_method_reached_by_name_as_a_string(tmp_path: Path) -> None:
    (tmp_path / "sneaky.py").write_text(
        'def f(store, r):\n    return getattr(store, "enter_published_for_seed")(r)\n'
    )
    (tmp_path / "dunder.py").write_text(
        'def f(store):\n    return store.__getattribute__("restore_to_draft")\n'
    )
    assert callers(tmp_path, tmp_path, "enter_published_for_seed") == {"sneaky.py"}
    assert callers(tmp_path, tmp_path, "restore_to_draft") == {"dunder.py"}


def test_the_store_defines_both_and_a_definition_is_not_a_use() -> None:
    store = CORE / "services/api/studio_recipes.py"
    text = store.read_text(encoding="utf-8")
    for name in CONFINED:
        assert f"async def {name}(" in text, name
    # the definitions are in the one module that is not the seed's, and the scan does not count them
    for name in CONFINED:
        assert "services/api/studio_recipes.py" not in callers(CORE / "services", CORE, name)
