"""ADR-127 decision 6: `GraphPort.existing_node_ids` answers by id alone, whatever the caller may
read, so that the recipe engine can tell a node it merged into from one it created. A route that
called it would let any caller ask whether an id exists, which the access step exists to prevent
(rules 3 and 4): a hidden node's existence would be readable by id. So the engine's write path is
the only caller, and this fails for any other.

The scan covers every Python module under `services/`, `scripts/` and `packages/`, except the port
and the graph adapters, which define it. It flags an attribute access named `existing_node_ids` and
also any string equal to the name, which is how `getattr(graph, "existing_node_ids")` or
`graph.__getattribute__("existing_node_ids")` would reach it without writing the attribute. It is
shown red on planted cases of each (`test_the_check_flags_...`), and against the tree itself."""

from __future__ import annotations

import ast
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
ALLOWED = {"services/ingest/engine.py"}
NAME = "existing_node_ids"
#: Where the method is defined, so where its name is not a use.
DEFINERS = ("packages/ports", "packages/adapters/graph_")


def _skipped(relative: str) -> bool:
    return relative.startswith(DEFINERS)


def callers(root: Path, relative_to: Path) -> set[str]:
    """The files under `root` that name `existing_node_ids`: as an attribute, or as a string."""
    found: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        if ".venv" in path.parts or "node_modules" in path.parts:
            continue
        relative = str(path.relative_to(relative_to))
        if _skipped(relative):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and node.attr == NAME) or (
                isinstance(node, ast.Constant) and node.value == NAME
            ):
                found.add(relative)
                break
    return found


def test_only_the_engines_write_path_names_the_unfiltered_lookup() -> None:
    offenders = {
        f
        for root in (CORE / "services", CORE / "scripts", CORE / "packages")
        for f in callers(root, CORE)
        if f not in ALLOWED
    }
    assert offenders == set(), f"these name GraphPort.existing_node_ids: {sorted(offenders)}"


def test_the_engine_does_call_it() -> None:
    assert callers(CORE / "services" / "ingest", CORE) == ALLOWED


def test_the_check_flags_a_call_outside_the_engine(tmp_path: Path) -> None:
    (tmp_path / "route.py").write_text(
        "async def route(graph, ids):\n    return await graph.existing_node_ids(ids)\n"
    )
    (tmp_path / "quiet.py").write_text("def f(graph):\n    return graph.get_nodes([], None)\n")
    assert callers(tmp_path, tmp_path) == {"route.py"}


def test_the_check_flags_a_lookup_reached_by_name_as_a_string(tmp_path: Path) -> None:
    (tmp_path / "sneaky.py").write_text(
        'def f(graph, ids):\n    return getattr(graph, "existing_node_ids")(ids)\n'
    )
    (tmp_path / "dunder.py").write_text(
        'def f(graph):\n    return graph.__getattribute__("existing_node_ids")\n'
    )
    assert callers(tmp_path, tmp_path) == {"sneaky.py", "dunder.py"}


def test_the_definitions_are_not_uses(tmp_path: Path) -> None:
    (tmp_path / "packages" / "ports").mkdir(parents=True)
    (tmp_path / "packages" / "adapters" / "graph_other").mkdir(parents=True)
    (tmp_path / "packages" / "ports" / "graph.py").write_text(
        "class P:\n    async def existing_node_ids(self, ids): ...\n"
    )
    (tmp_path / "packages" / "adapters" / "graph_other" / "a.py").write_text(
        "class A:\n    async def existing_node_ids(self, ids): ...\n"
    )
    (tmp_path / "packages" / "adapters" / "other_store").mkdir(parents=True)
    (tmp_path / "packages" / "adapters" / "other_store" / "b.py").write_text(
        'x = getattr(g, "existing_node_ids")\n'
    )
    assert callers(tmp_path, tmp_path) == {"packages/adapters/other_store/b.py"}
