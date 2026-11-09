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
method was given: never `None`, never a literal, never left out. (The orchestrator's review of P5
round 3, the lane review's defect 5.)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ADAPTER = (
    Path(__file__).resolve().parents[4]
    / "OspreyFlow_Core" / "packages" / "adapters" / "graph_arcadedb" / "adapter.py"
)  # fmt: skip
DESERIALISERS = {"node_from_element_map", "edge_from_element_map"}


def offending_calls(source: str) -> list[tuple[str, int, str]]:
    """Each deserialiser call inside a method that is not given that method's own `principal`, as
    (method, line, why)."""
    offences: list[tuple[str, int, str]] = []
    for function in ast.walk(ast.parse(source)):
        if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        params = {a.arg for a in (*function.args.args, *function.args.kwonlyargs)}
        for call in ast.walk(function):
            if not (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id in DESERIALISERS
            ):
                continue
            given = [*call.args[1:2], *(k.value for k in call.keywords if k.arg == "principal")]
            if not given:
                offences.append((function.name, call.lineno, "no principal"))
            elif not (isinstance(given[0], ast.Name) and given[0].id == "principal"):
                offences.append((function.name, call.lineno, ast.unparse(given[0])))
            elif "principal" not in params:
                offences.append((function.name, call.lineno, "a principal not its own"))
    return offences


def test_every_read_in_the_adapter_withholds_by_its_caller_s_principal() -> None:
    source = ADAPTER.read_text()
    calls = sum(
        1
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in DESERIALISERS
    )
    assert calls >= 20, "the adapter's reads were not found: the test would pass over nothing"
    assert offending_calls(source) == []


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
