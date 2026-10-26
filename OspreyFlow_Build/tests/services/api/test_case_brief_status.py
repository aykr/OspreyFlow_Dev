"""Rule 5 for the case brief — ADR-128 decision 3: "No model path sets a status: only a person's
request through the route does."

A prose sentence is not a test (`CLAUDE.md` rule 12). Which test fails if the sentence is violated:
the walks below, over the real source, fail when anything but the person's own route reaches the
transition that marks a requirement answered. They are pure: they parse files and open no
connection. Rule 15: each walk is also run over a planted violation, in the shape the real code
would take, to show it can fail.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[4] / "OspreyFlow_Core"
SERVICES = CORE / "services"
APP = SERVICES / "api" / "app.py"
MODULE = SERVICES / "api" / "case_brief.py"
STATUS_ROUTE = "set_brief_requirement_status_route"

#: The files that may name the brief at all: the module itself, its title resolvers (which import
#: only the resolver type), the Conduit's routes, and the seed that writes the PID's own brief (which
#: sets no status: asserted below).
MAY_NAME_THE_BRIEF = {
    MODULE,
    SERVICES / "api" / "case_brief_resolvers.py",
    APP,
    CORE / "scripts" / "seed_pid.py",
}


def _python_files() -> list[Path]:
    return sorted(
        p
        for root in (SERVICES, CORE / "scripts", CORE / "packages")
        for p in root.rglob("*.py")
        if "__pycache__" not in p.parts
    )


def _names_the_brief(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (
            (node.module or "").endswith("case_brief")
            or any(a.name == "case_brief" for a in node.names)
        ):
            return True
        if isinstance(node, ast.Import) and any(a.name.endswith("case_brief") for a in node.names):
            return True
    return False


def files_naming_the_brief(files: list[Path]) -> list[Path]:
    return [p for p in files if _names_the_brief(ast.parse(p.read_text()))]


def _calls(tree: ast.AST, match: Callable[[ast.Call], bool]) -> list[tuple[str, ast.Call]]:
    """Each call the predicate accepts, with the function it sits in (module level: '')."""
    found: list[tuple[str, ast.Call]] = []

    def walk(node: ast.AST, inside: str) -> None:
        for child in ast.iter_child_nodes(node):
            here = (
                child.name if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef) else inside
            )
            if isinstance(child, ast.Call) and match(child):
                found.append((inside, child))
            walk(child, here)

    walk(tree, "")
    return found


def _method(attribute: str) -> Callable[[ast.Call], bool]:
    return lambda call: isinstance(call.func, ast.Attribute) and call.func.attr == attribute


def _function(name: str) -> Callable[[ast.Call], bool]:
    return lambda call: isinstance(call.func, ast.Name) and call.func.id == name


def _receiver(call: ast.Call) -> str:
    target = call.func.value  # type: ignore[attr-defined]
    return target.id if isinstance(target, ast.Name) else ast.dump(target)


def status_callers_in_app(source: str) -> set[str]:
    """The functions of `app.py` that call `.set_status` on the brief service (the dependency is
    named `case_brief`; `hotlist_store.set_status` and `monitor_store.set_status` are other things)."""
    return {
        inside
        for inside, call in _calls(ast.parse(source), _method("set_status"))
        if _receiver(call) == "case_brief"
    }


def test_only_the_modules_that_own_the_brief_name_it() -> None:
    """No module that talks to a model (questions, the explorer, the extraction pipeline, the
    jobs) imports the brief, so none can reach its status."""
    assert set(files_naming_the_brief(_python_files())) <= MAY_NAME_THE_BRIEF


def test_the_status_is_set_from_one_route_and_it_is_the_persons() -> None:
    assert status_callers_in_app(APP.read_text()) == {STATUS_ROUTE}


def test_the_transition_is_reached_only_from_the_services_set_status() -> None:
    callers = {
        inside for inside, _ in _calls(ast.parse(MODULE.read_text()), _function("with_status"))
    }
    assert callers == {"set_status"}
    for path in _python_files():
        if path != MODULE:
            assert "with_status" not in path.read_text(), path


def test_the_seed_writes_a_priority_and_requirements_and_sets_no_status() -> None:
    seed = (CORE / "scripts" / "seed_pid.py").read_text()
    assert ".set_status(" not in seed
    assert "with_status" not in seed


def test_the_status_route_takes_a_person_and_the_other_bodies_have_no_status_field() -> None:
    from services.api.case_brief import BriefAttachmentBody, BriefStatusBody, BriefTextBody

    assert "status" not in BriefTextBody.model_fields
    assert "status" not in BriefAttachmentBody.model_fields
    assert set(BriefStatusBody.model_fields) == {"status"}
    assert BriefTextBody.model_config.get("extra") == "forbid"


# --- each walk, shown red over a planted violation (rule 15) ---------------------------------


def test_the_app_walk_finds_a_second_caller_planted_in_another_route() -> None:
    planted = (
        "async def set_brief_requirement_status_route(case_brief):\n"
        "    await case_brief.set_status('i', 'r', p, 'answered')\n"
        "async def ask_model_route(case_brief):\n"
        "    answer = await model.answer()\n"
        "    await case_brief.set_status('i', 'r', p, 'answered')\n"
    )
    assert status_callers_in_app(planted) == {STATUS_ROUTE, "ask_model_route"}


def test_the_app_walk_ignores_other_stores_that_happen_to_have_a_set_status() -> None:
    other = "async def f(hotlist_store):\n    await hotlist_store.set_status('h', 'stopped')\n"
    assert status_callers_in_app(other) == set()


def test_the_import_walk_finds_a_model_module_that_names_the_brief(tmp_path: Path) -> None:
    planted = tmp_path / "questions.py"
    planted.write_text("from .case_brief import CaseBriefService\n")
    assert files_naming_the_brief([planted]) == [planted]
    assert planted not in MAY_NAME_THE_BRIEF


@pytest.mark.parametrize(
    "source",
    ["import services.api.case_brief\n", "from services.api import case_brief\n"],
)
def test_the_import_walk_finds_each_spelling_of_the_import(tmp_path: Path, source: str) -> None:
    """The second spelling imports the module by name from its package, which `module.endswith`
    alone would miss; this case is why the walk also reads the imported names."""
    planted = tmp_path / "x.py"
    planted.write_text(source)
    assert files_naming_the_brief([planted]) == [planted]
