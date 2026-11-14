"""Every node and link the ArcadeDB adapter reads for a caller is deserialised with that caller's
principal, so every read path withholds what the principal may not be sent (rule 3, rule 4):
ADR-130 Amendment 2's sources, and ADR-147 Amendment 2's gazetteer copy identifiers (decision 3b).

The withholding is in one place: `serialization.node_from_element_map(record, principal)` and
`edge_from_element_map(record, principal)` call `withhold_sources` when given a principal. A system
read passes none. So one argument at one call site decides whether a read path leaks a copy's
`osm_id` and `uprn`. Five of those call sites (`get_node`, `get_nodes`, `search_nodes`,
`suggest_nodes`, `expand`) are shown red live, each with its principal replaced by `None`
(`process/lanes/platform/P5_RED_RECORD.md`). The others (`find_node`, `suggest_locations`,
`list_nodes`, `paths`, `match`, `most_connected`, `busiest_links`, `recently_confirmed`,
`shared_contacts`, and any read added later) take the same one-line fault. This test holds every
call site to it, structurally. Each call must pass, as its second argument, the principal its own
method was given: never `None`, never a literal, never left out. Every module of the adapter's
package is read, a call through a module (`serialization.node_from_element_map(…)`) is held the
same, and a deserialiser imported under another name or handed on as a value (`map(…)`) is refused,
since either would hide a call from this test. (The lane review's defect 5; the orchestrator's
re-review widened it.)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = (
    Path(__file__).resolve().parents[4]
    / "OspreyFlow_Core"
    / "packages"
    / "adapters"
    / "graph_arcadedb"
)
ADAPTER = PACKAGE / "adapter.py"
DESERIALISERS = {"node_from_element_map", "edge_from_element_map"}


def _named(node: ast.AST) -> str | None:
    """The deserialiser an expression names, as `name` or `module.name`."""
    if isinstance(node, ast.Name) and node.id in DESERIALISERS:
        return node.id
    if isinstance(node, ast.Attribute) and node.attr in DESERIALISERS:
        return node.attr
    return None


def offending_calls(source: str) -> list[tuple[str, int, str]]:
    """Each deserialiser call inside a function that is not given that function's own `principal`,
    each import of one under another name, and each use of one as a value, as (where, line, why)."""
    tree = ast.parse(source)
    offences: list[tuple[str, int, str]] = []
    called: set[int] = set()
    for imported in ast.walk(tree):
        if isinstance(imported, ast.ImportFrom):
            for alias in imported.names:
                if alias.name in DESERIALISERS and alias.asname not in (None, alias.name):
                    offences.append(("import", imported.lineno, f"imported as {alias.asname}"))
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        params = {a.arg for a in (*function.args.args, *function.args.kwonlyargs)}
        for call in ast.walk(function):
            if not (isinstance(call, ast.Call) and _named(call.func)):
                continue
            called.add(id(call.func))
            given = [*call.args[1:2], *(k.value for k in call.keywords if k.arg == "principal")]
            if not given:
                offences.append((function.name, call.lineno, "no principal"))
            elif not (isinstance(given[0], ast.Name) and given[0].id == "principal"):
                offences.append((function.name, call.lineno, ast.unparse(given[0])))
            elif "principal" not in params:
                offences.append((function.name, call.lineno, "a principal not its own"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Name | ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and _named(node)
            and id(node) not in called
        ):
            offences.append(("value", node.lineno, f"{_named(node)} used as a value"))
    return sorted(offences, key=lambda o: o[1])


def test_every_read_in_the_adapter_withholds_by_its_caller_s_principal() -> None:
    modules = sorted(PACKAGE.rglob("*.py"))
    calls = sum(
        1
        for module in modules
        for node in ast.walk(ast.parse(module.read_text()))
        if isinstance(node, ast.Call) and _named(node.func)
    )
    assert ADAPTER in modules and calls >= 20, (
        "the reads were not found: the test would pass over nothing"
    )
    found = {m.name: offending_calls(m.read_text()) for m in modules}
    # The one system read the adapter makes for a caller that is not a reader: the search index
    # feed's (ADR-150 decision 2), unfiltered by design and whole, through `IndexFeedSource`, which no
    # route reaches (`tests/services/search_index/test_index_feed_reach.py`). Named here by function, so any other
    # read that drops its principal is still refused.
    found["adapter.py"] = [o for o in found["adapter.py"] if o[0] != "nodes_for_index"]
    assert found == {m.name: [] for m in modules}


@pytest.mark.parametrize(
    ("call", "why"),
    [
        ("node_from_element_map(r, None)", "None"),
        ("node_from_element_map(r)", "no principal"),
        ("node_from_element_map(r, principal=None)", "None"),
        ("edge_from_element_map(r, SYSTEM)", "SYSTEM"),
    ],
)
def test_a_read_that_drops_its_principal_is_named(call: str, why: str) -> None:
    """A planted fault in the shape a call site really takes (`shared_contacts`' comprehension)."""
    source = f"""
class A:
    async def shared_contacts(self, ids, principal):
        contact_records = await self._q(ids)
        return {{n.id: n for n in ({call} for r in contact_records)}}
"""
    assert offending_calls(source) == [("shared_contacts", 5, why)]


def test_a_principal_from_outside_the_method_is_named() -> None:
    source = """
class A:
    async def find(self, element):
        return node_from_element_map(element, principal)
"""
    assert offending_calls(source) == [("find", 4, "a principal not its own")]


@pytest.mark.parametrize(
    ("source", "why"),
    [
        (
            "from . import serialization\nasync def f(r, principal):\n"
            "    return serialization.node_from_element_map(r, None)\n",
            ("f", 3, "None"),
        ),
        (
            "from .serialization import node_from_element_map as read\n",
            ("import", 1, "imported as read"),
        ),
        (
            "async def f(rs, principal):\n    return list(map(node_from_element_map, rs))\n",
            ("value", 2, "node_from_element_map used as a value"),
        ),
    ],
    ids=["through-the-module", "aliased-import", "handed-on"],
)
def test_a_read_hidden_from_a_plain_call_is_named(source: str, why: tuple[str, int, str]) -> None:
    assert offending_calls(source) == [why]
