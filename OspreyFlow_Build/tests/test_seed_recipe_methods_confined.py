"""ADR-127 Amendment 23 (B2-10a, B2-10c): three methods of `StudioRecipeStore` write what no route
may.

- `enter_published_for_seed` enters a committed recipe as published, keeping its id, with no
  verify, no approver and no publish route in between;
- `restore_to_draft` sets a recipe's latest version, whatever its status, to superseded and writes a
  draft in its place;
- `enter_draft_for_seed` writes the reports recipe's first, unmapped draft at its own id and version
  (a recipe the seed has never entered has no row to restore from).

Each skips the gates a route puts on a publish and a new version (the roles, the unit check, the
verify), so a route that called any would let a caller past them. `scripts/seed_pid.py` (the
seed, the reset and the fallback publication, each run by an operator with the Conduit stopped or
beside it) is the one module that may, and `test_the_seed_module_names_each_of_them` holds that it
does: a confinement to a module that never calls the method would confine nothing.

The scan is `test_unfiltered_node_lookup_confined.callers`: an attribute access of the name, or a
string equal to it (which is how `getattr(store, "enter_published_for_seed")` would reach it). It is
shown red on planted cases (`test_the_check_flags_*`), and against the tree itself."""

from __future__ import annotations

import ast
from pathlib import Path

from tests.test_unfiltered_node_lookup_confined import callers

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
SEED_MODULE = "scripts/seed_pid.py"
CONFINED = {
    "enter_published_for_seed": {SEED_MODULE},
    "restore_to_draft": {SEED_MODULE},
    "enter_draft_for_seed": {SEED_MODULE},
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


def test_the_seed_module_names_each_of_them() -> None:
    for name in CONFINED:
        assert callers(CORE / "scripts", CORE, name) == {SEED_MODULE}, name


def test_the_store_defines_each_and_a_definition_is_not_a_use() -> None:
    store = CORE / "services/api/studio_recipes.py"
    text = store.read_text(encoding="utf-8")
    for name in CONFINED:
        assert f"async def {name}(" in text, name
    # the definitions are in the one module that is not the seed's, and the scan does not count them
    for name in CONFINED:
        assert "services/api/studio_recipes.py" not in callers(CORE / "services", CORE, name)


# --- the two reads the seed's reset and its reseed make (ADR-127 Amendment 30) -------------------
#
# `load_revert.links_resting_on` answers whatever the caller may read (every live link outside a set
# of loads that rests on their nodes), and `RecipeRunStore.unreverted_loads` is the case's loads
# without their id lists, which no route has a use for. Each is for an operator's command, so each
# is named by the seed module alone. `callers` above looks only for an attribute or a string, so it
# would miss `from services.ingest.load_revert import links_resting_on` and the bare call that
# follows; `names_of` looks for those too. A definition (`def links_resting_on`) is not a use.

NAME_CONFINED = {
    "links_resting_on": {SEED_MODULE},
    "unreverted_loads": {SEED_MODULE},
}


def names_of(root: Path, relative_to: Path, name: str) -> set[str]:
    """The files under `root` that use `name` in any way: an attribute, a bare name, an imported
    name (`import x as name` too), or a string equal to it. Not a function's own definition."""
    found: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        if ".venv" in path.parts or "node_modules" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            used = (
                (isinstance(node, ast.Attribute) and node.attr == name)
                or (isinstance(node, ast.Name) and node.id == name)
                or (isinstance(node, ast.alias) and name in (node.name, node.asname))
                or (isinstance(node, ast.Constant) and node.value == name)
            )
            if used:
                found.add(str(path.relative_to(relative_to)))
                break
    return found


def test_only_the_seed_module_names_the_two_reads() -> None:
    for name, allowed in NAME_CONFINED.items():
        offenders = {
            f for root in ROOTS for f in names_of(CORE / root, CORE, name) if f not in allowed
        }
        assert offenders == set(), f"these name {name}: {sorted(offenders)}"


def test_the_seed_module_names_each_of_the_two_reads() -> None:
    """A confinement to a module that never uses the read would confine nothing."""
    for name, allowed in NAME_CONFINED.items():
        assert {f for root in ROOTS for f in names_of(CORE / root, CORE, name)} == allowed, name


def test_the_check_flags_every_shape_of_use_outside_the_seed_module(tmp_path: Path) -> None:
    shapes = {
        "attribute.py": "async def f(ledger):\n    return await ledger.{n}('c', [])\n",
        "imported.py": "from services.ingest.load_revert import {n}\n",
        "bare_call.py": "async def f(x, g):\n    return await {n}(x, g)\n",
        "renamed.py": "from somewhere import thing as {n}\n",
        "by_string.py": "def f(o):\n    return getattr(o, '{n}')\n",
        "module_attribute.py": "import m\n\ndef f():\n    return m.{n}\n",
    }
    for name in NAME_CONFINED:
        for filename, text in shapes.items():
            (tmp_path / filename).write_text(text.format(n=name))
        (tmp_path / "quiet.py").write_text("def f(o):\n    return o.get('x')\n")
        assert names_of(tmp_path, tmp_path, name) == set(shapes), name


def test_a_definition_is_not_a_use(tmp_path: Path) -> None:
    for name in NAME_CONFINED:
        (tmp_path / "defines.py").write_text(f"async def {name}(records, graph):\n    return []\n")
        assert names_of(tmp_path, tmp_path, name) == set(), name


def test_the_modules_that_define_the_two_reads_do_not_count_as_users() -> None:
    """`load_revert.py` and `recipe_runs.py` define them and are not in the allowed set: the scan
    must not name them, or the confinement above would already be failing for them."""
    for name in NAME_CONFINED:
        used_in = {f for root in ROOTS for f in names_of(CORE / root, CORE, name)}
        assert "services/ingest/load_revert.py" not in used_in
        assert "services/api/recipe_runs.py" not in used_in
