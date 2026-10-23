"""Nothing in `services/api` reads a recipe file or builds a `Recipe` except in three named places
(`06_DECISIONS.md` ADR-120 Amendment 2, decision 1). A run reads the committed file, and a file
committed before pinning has no pins, so a site that loads it directly would be refused by the
engine for a recipe whose registry row is pinned, or would run on no pins at all.

**The rule, exactly.** Within `OspreyFlow_Core/services/api`, a call to `load_recipe` (by its name,
under any alias given by `from ... import load_recipe as X`, or as `module.load_recipe`) or to
`Recipe.model_validate` is allowed only inside

- the function `load_published_recipe` defined in `services/api/studio_publish.py`, or
- the function `set_site_grid` defined in `services/api/app.py`, which loads the committed in-repo
  site-grid recipe by a fixed path (`_SITE_GRID_RECIPE_PATH`), never a registry row's `git_path`, or
- the function `recipe_reader` (and its inner `read`) in `services/api/studio_recipes.py`, the
  start-up backfill's reader: it reads a published row's committed file only to learn which packs
  the recipe names or writes, for a row that has no pins, so there is no row pin to fall back on.

`Recipe.model_validate_json` and `Recipe.model_construct` count as `Recipe.model_validate`.
Outside the check, on purpose: constructing `Recipe(...)` directly (how `build_recipe` and Verify
build a recipe in memory, not a load of a committed file) and dynamic `getattr` access.

Every other such call is a violation, whatever its argument looks like (a `git_path` in a variable,
a subscript, a conditional expression, a call argument, an alias, a hand-parsed document).

Rule 15: the check is shown red first, against planted sources in the shapes the code uses or could
take, before it is trusted against the real tree.

What each test checks, and the violation that fails it:
- `test_a_load_passed_straight_into_another_call_is_a_violation`: the check missing
  `release(load_recipe(repo_root / recipe.git_path), rows)`.
- `test_a_load_in_a_conditional_expression_is_a_violation`: the check missing
  `load_recipe(root / draft.git_path) if draft.git_path else None`.
- `test_a_load_through_a_variable_held_path_is_a_violation`: the check keying on the argument
  expression, so `path = root / d.git_path` then `load_recipe(path)` slips through.
- `test_a_load_through_a_subscript_is_a_violation`: `load_recipe(root / row["git_path"])` slipping
  through because it has no `.git_path` attribute.
- `test_an_aliased_load_is_a_violation`: `from ... import load_recipe as read` hiding the call.
- `test_a_hand_built_recipe_is_a_violation`: `Recipe.model_validate(yaml.safe_load(...))` building
  a recipe from a file without `load_recipe`.
- `test_a_recipe_built_from_json_is_a_violation` and
  `test_a_recipe_built_by_model_construct_is_a_violation`: `Recipe.model_validate_json` or
  `Recipe.model_construct` building a recipe from a file past the check.
- `test_a_load_published_recipe_defined_in_another_module_is_a_violation`: the allowance following
  the function's name instead of its place, so any module could define its own.
- `test_the_one_function_in_studio_publish_is_allowed`, `test_the_site_grid_loader_is_allowed` and
  `test_the_start_up_backfill_reader_is_allowed`: the check refusing a place meant to load.
- `test_no_site_in_the_api_loads_a_recipe_except_the_allowed_places`: a site in the real tree
  breaking the rule.
"""

from __future__ import annotations

import ast
from pathlib import Path

_API = Path(__file__).resolve().parents[4] / "OspreyFlow_Core" / "services" / "api"

#: The `Recipe` class methods that build a recipe from a document, treated like `load_recipe`.
_RECIPE_BUILDERS = ("model_validate", "model_validate_json", "model_construct")

#: (file relative to `OspreyFlow_Core`, qualified function name) pairs allowed to load a recipe.
_ALLOWED: frozenset[tuple[str, str]] = frozenset(
    {
        ("services/api/studio_publish.py", "load_published_recipe"),
        ("services/api/app.py", "set_site_grid"),
        ("services/api/studio_recipes.py", "recipe_reader"),
        ("services/api/studio_recipes.py", "recipe_reader.read"),
    }
)


def _aliases(tree: ast.AST, name: str) -> set[str]:
    """Every local name `name` is imported under (`from m import name as alias`)."""
    found = {name}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for imported in node.names:
                if imported.name == name:
                    found.add(imported.asname or imported.name)
    return found


def _violations(source: str, filename: str) -> list[str]:
    """Each call to `load_recipe` or `Recipe.model_validate`, under any alias, outside the allowed
    (file, function) pairs. `filename` is relative to `OspreyFlow_Core`."""
    tree = ast.parse(source, filename=filename)
    loaders = _aliases(tree, "load_recipe")
    recipe_names = _aliases(tree, "Recipe")
    found: list[str] = []

    def is_load(call: ast.Call) -> bool:
        function = call.func
        if isinstance(function, ast.Name):
            return function.id in loaders
        if isinstance(function, ast.Attribute):
            if function.attr == "load_recipe":
                return True
            return (
                function.attr in _RECIPE_BUILDERS
                and isinstance(function.value, ast.Name)
                and function.value.id in recipe_names
            )
        return False

    def visit(node: ast.AST, scope: tuple[str, ...]) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            scope = (*scope, node.name)
        if isinstance(node, ast.Call) and is_load(node):
            if (filename, ".".join(scope)) not in _ALLOWED:
                where = ".".join(scope) or "module level"
                found.append(f"{filename}:{node.lineno} loads a recipe in {where}")
        for child in ast.iter_child_nodes(node):
            visit(child, scope)

    visit(tree, ())
    return found


def _check(source: str, filename: str = "services/api/planted.py") -> list[str]:
    return _violations(source, filename)


def test_a_load_passed_straight_into_another_call_is_a_violation() -> None:
    source = (
        "async def release_route(recipe, repo_root, rows):\n"
        "    return await release(load_recipe(repo_root / recipe.git_path), rows)\n"
    )
    assert len(_check(source)) == 1


def test_a_load_in_a_conditional_expression_is_a_violation() -> None:
    source = (
        "def read(draft, root):\n"
        "    recipe = load_recipe(root / draft.git_path) if draft.git_path else None\n"
        "    return recipe\n"
    )
    assert len(_check(source)) == 1


def test_a_load_through_a_variable_held_path_is_a_violation() -> None:
    source = "def read(d, root):\n    path = root / d.git_path\n    return load_recipe(path)\n"
    assert len(_check(source)) == 1


def test_a_load_through_a_subscript_is_a_violation() -> None:
    source = 'def read(row, root):\n    return load_recipe(root / row["git_path"])\n'
    assert len(_check(source)) == 1


def test_an_aliased_load_is_a_violation() -> None:
    source = (
        "from services.ingest.recipe_loader import load_recipe as read_it\n"
        "def read(row, root):\n"
        "    return read_it(root / row.git_path)\n"
    )
    assert len(_check(source)) == 1


def test_a_module_qualified_load_is_a_violation() -> None:
    source = "def read(root, row):\n    return loader.load_recipe(root / row.git_path)\n"
    assert len(_check(source)) == 1


def test_a_hand_built_recipe_is_a_violation() -> None:
    source = "def read(path):\n    return Recipe.model_validate(yaml.safe_load(path.read_text()))\n"
    assert len(_check(source)) == 1


def test_a_recipe_built_from_json_is_a_violation() -> None:
    source = "def read(path):\n    return Recipe.model_validate_json(path.read_text())\n"
    assert len(_check(source)) == 1


def test_a_recipe_built_by_model_construct_is_a_violation() -> None:
    source = "def read(document):\n    return Recipe.model_construct(**document)\n"
    assert len(_check(source)) == 1


def test_a_load_published_recipe_defined_in_another_module_is_a_violation() -> None:
    source = (
        "def load_published_recipe(row, repo_root):\n"
        "    return load_recipe(repo_root / row.git_path)\n"
    )
    assert len(_check(source, "services/api/other.py")) == 1


def test_the_one_function_in_studio_publish_is_allowed() -> None:
    source = (
        "def load_published_recipe(row, repo_root):\n"
        "    recipe = load_recipe(repo_root / row.git_path)\n"
        "    return recipe\n"
    )
    assert _check(source, "services/api/studio_publish.py") == []


def test_the_site_grid_loader_is_allowed() -> None:
    source = (
        "async def set_site_grid(site_id):\n"
        "    recipe = load_recipe(_SITE_GRID_RECIPE_PATH)\n"
        "    return recipe\n"
    )
    assert _check(source, "services/api/app.py") == []


def test_the_start_up_backfill_reader_is_allowed() -> None:
    source = (
        "def recipe_reader(repo_root):\n"
        "    def read(git_path):\n"
        "        return load_recipe(repo_root / git_path)\n"
        "    return read\n"
    )
    assert _check(source, "services/api/studio_recipes.py") == []


def test_no_site_in_the_api_loads_a_recipe_except_the_allowed_places() -> None:
    files = sorted(_API.rglob("*.py"))
    assert files, "no source files were found under services/api, so nothing was checked"
    violations: list[str] = []
    for path in files:
        relative = path.relative_to(_API.parent.parent).as_posix()
        violations.extend(_violations(path.read_text(), relative))
    assert violations == []
