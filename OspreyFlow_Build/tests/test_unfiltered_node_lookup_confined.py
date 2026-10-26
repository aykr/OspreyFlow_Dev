"""ADR-127 decision 6: `GraphPort.existing_node_ids` answers by id alone, whatever the caller may
read, so that the recipe engine can tell a node it merged into from one it created. A route that
called it would let any caller ask whether an id exists, which the access step exists to prevent
(rules 3 and 4): a hidden node's existence would be readable by id. So the engine's write path is
the only caller, and this fails for any other.

The revert (B2-4c, `services/ingest/load_revert.py`) has more of the same kind, each answering
whatever the caller may read, and each confined to that one module: `live_edges_touching` (does a
live link outside the load rest on a node it created), `live_nodes_naming_geometry` (does a live node
still name a point it inserted), `stored_writes` (which load last wrote a node, and is it reverted
or superseded) and `stored_link_states` (is a link reverted or superseded). The analytics port's
`events_of_load_among` (which of the events an alert cites are a load's) is confined the same way.

The scan covers every Python module under `services/`, `scripts/` and `packages/`, except the port
and the graph adapters, which define it. It flags an attribute access named `existing_node_ids` and
also any string equal to the name, which is how `getattr(graph, "existing_node_ids")` or
`graph.__getattribute__("existing_node_ids")` would reach it without writing the attribute. It is
shown red on planted cases of each (`test_the_check_flags_...`), and against the tree itself."""

from __future__ import annotations

import ast
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
#: Each unfiltered internal lookup, and the one module that may use it.
CONFINED = {
    "existing_node_ids": {"services/ingest/engine.py"},
    "live_edges_touching": {"services/ingest/load_revert.py"},
    "live_nodes_naming_geometry": {"services/ingest/load_revert.py"},
    "stored_writes": {"services/ingest/load_revert.py"},
    "stored_link_states": {"services/ingest/load_revert.py"},
    "events_of_load_among": {"services/ingest/load_revert.py"},
}
ALLOWED = CONFINED["existing_node_ids"]
NAME = "existing_node_ids"
#: Where the method is defined, so where its name is not a use.
DEFINERS = ("packages/ports", "packages/adapters/graph_", "packages/adapters/analytics_")


def _skipped(relative: str) -> bool:
    return relative.startswith(DEFINERS)


def callers(root: Path, relative_to: Path, name: str = NAME) -> set[str]:
    """The files under `root` that name `name`: as an attribute, or as a string."""
    found: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        if ".venv" in path.parts or "node_modules" in path.parts:
            continue
        relative = str(path.relative_to(relative_to))
        if _skipped(relative):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and node.attr == name) or (
                isinstance(node, ast.Constant) and node.value == name
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


def test_only_the_reverts_module_names_its_unfiltered_lookups() -> None:
    for name, allowed in CONFINED.items():
        offenders = {
            f
            for root in (CORE / "services", CORE / "scripts", CORE / "packages")
            for f in callers(root, CORE, name)
            if f not in allowed
        }
        assert offenders == set(), f"these name GraphPort.{name}: {sorted(offenders)}"


def test_the_module_each_lookup_is_confined_to_does_call_it() -> None:
    for name, allowed in CONFINED.items():
        if name == NAME:
            continue
        assert callers(CORE / "services", CORE, name) == allowed, name


def test_the_check_flags_each_confined_lookup_outside_its_module(tmp_path: Path) -> None:
    for name in CONFINED:
        (tmp_path / f"{name}.py").write_text(
            f"async def route(g, ids):\n    return await g.{name}(ids)\n"
        )
    for name in CONFINED:
        assert callers(tmp_path, tmp_path, name) == {f"{name}.py"}


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
