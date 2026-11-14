"""User guide §5.2's line for ADR-124 Amendment 20, held to the code (rule 12): the links among a set are found a
thousand records at a time (`_ID_CHUNK`, each chunk from record ids, so no id is written into the query), and the
three things a user sees that read them, the batch job's result, a view opening and *Show links among all*, each
read the graph's `edges_among`."""

from __future__ import annotations

import ast
import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"


def read(path: str) -> str:
    return (CORE / path).read_text(encoding="utf-8")


def function(path: str, name: str) -> str:
    source = read(path)
    node = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    return re.sub(r"\s+", " ", ast.get_source_segment(source, node) or "")


def test_the_links_among_are_found_a_thousand_records_at_a_time() -> None:
    adapter = read("packages/adapters/graph_arcadedb/adapter.py")
    assert re.search(r"^_ID_CHUNK = 1000$", adapter, re.MULTILINE)
    among = function("packages/adapters/graph_arcadedb/adapter.py", "edges_among")
    assert "for chunk in _id_chunks(sorted(wanted)):" in among
    assert "rids = await self._record_ids(types, chunk)" in among
    assert "query = render_edges_among_gremlin(rids, self._access, principal, edge_types)" in among
    builder = function("packages/adapters/graph_arcadedb/builders.py", "render_edges_among_gremlin")
    code = re.sub(r'""".*?"""', "", builder)  # its code, not its docstring's account of the old query
    assert "record_ids: Sequence[str]" in code and "within(" not in code, "the ids are records, not a literal list"
    assert "g.V(" in code


def test_what_a_user_sees_reads_edges_among() -> None:
    assert "links = await graph.edges_among(node_ids, scoped)" in function("services/api/batch_expansion.py", "_expand_and_save")
    assert "edges = await graph.edges_among([n.id for n in nodes], principal)" in function("services/api/case_views.py", "_read_selection")
    assert "among = await self._graph.edges_among(sorted(ids), principal)" in function("services/api/working_set/service.py", "links_among")
    guide = re.sub(r"\s+", " ", read("docs/user-guide.md"))
    assert ("The links among the records are found a thousand records at a time, so a result up to that limit is saved "
            "with its links and its view opens with them, and **Show links among all** on a large canvas keeps working "
            "as it grows.") in guide  # fmt: skip
