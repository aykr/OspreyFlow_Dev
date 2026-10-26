"""ADR-127 Amendment 23 (B2-10a): the one run path lives in a module of its own,
`services/api/recipe_run.py`, that never imports `services.api.app`, so the seed (a script run with
the Conduit stopped) can call the same `run_recipe_as` the route and the scheduler call without
starting the application. What a mistake would do, and the case that catches it:

- the module importing the app, directly or through anything it imports
  (`test_the_run_module_imports_without_the_app`), and that check itself failing for a module that
  does (`test_the_check_flags_a_module_that_imports_the_app`);
- the route or the scheduler keeping a copy of what moved, so the seed and the route run different
  code (`test_the_app_uses_the_moved_code_and_holds_no_copy`)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

APP = "services.api.app"


def app_loaded_by(module: str, *, extra_path: Path | None = None) -> bool:
    """Whether importing `module` in a fresh interpreter puts the application in `sys.modules`."""
    paths = [str(p) for p in sys.path if p]
    if extra_path is not None:
        paths.insert(0, str(extra_path))
    code = (
        "import importlib, json, sys\n"
        f"importlib.import_module({module!r})\n"
        f"print(json.dumps({APP!r} in sys.modules))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(paths)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    answer = json.loads(done.stdout.strip().splitlines()[-1])
    assert isinstance(answer, bool)
    return answer


def test_the_run_module_imports_without_the_app() -> None:
    assert app_loaded_by("services.api.recipe_run") is False


def test_the_resource_builder_imports_without_the_app() -> None:
    """The seed calls it from a script with the Conduit stopped, so it too must not start the app."""
    assert app_loaded_by("services.api.run_resources") is False


def test_the_check_flags_a_module_that_imports_the_app(tmp_path: Path) -> None:
    (tmp_path / "leaky_run.py").write_text("from services.api import app  # noqa: F401\n")
    (tmp_path / "quiet_run.py").write_text("import json  # noqa: F401\n")
    assert app_loaded_by("leaky_run", extra_path=tmp_path) is True
    assert app_loaded_by("quiet_run", extra_path=tmp_path) is False


def test_the_app_uses_the_moved_code_and_holds_no_copy() -> None:
    from services.api import app as app_module
    from services.api import recipe_run

    for name in (
        "run_recipe_as",
        "RecipeRunDeps",
        "_rule_gate",
        "_owner_resolver",
        "_evaluate_watches_best_effort",
    ):
        assert getattr(app_module, name) is getattr(recipe_run, name), name
    # the application does not use `_execute_recipe_run` itself: it holds no copy of it either
    assert getattr(app_module, "_execute_recipe_run", recipe_run._execute_recipe_run) is (
        recipe_run._execute_recipe_run
    )


def test_the_moved_names_are_defined_in_the_run_module() -> None:
    from services.api import recipe_run

    for name in (
        "run_recipe_as",
        "RecipeRunDeps",
        "_execute_recipe_run",
        "_rule_gate",
        "_owner_resolver",
        "_evaluate_watches_best_effort",
    ):
        assert getattr(recipe_run, name).__module__ == "services.api.recipe_run", name
