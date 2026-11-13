"""Rule 4, ADR-150 decision 2: the indexer's unfiltered reads are reached by the search index feed
alone. No route, no other service and no other script names `IndexFeedSource` or any of its reads
(or the text store's), so a request can never be answered from a read that carries no access step.
Read structurally, by every name in every module; a planted use is named."""

from __future__ import annotations

import ast
from pathlib import Path

CORE = Path(__file__).resolve().parents[4] / "OspreyFlow_Core"
NAMES = {
    "IndexFeedSource",
    "nodes_for_index",
    "live_node_ids",
    "pending_index",
    "clear_pending_index",
    "texts_for_index",
    "pending_text_index",
    "clear_pending_text_index",
}
#: The feed's own modules, and the two stores that implement its reads.
ALLOWED = {
    "packages/ports/index_feed.py",
    "packages/adapters/graph_arcadedb/adapter.py",
    "services/api/review.py",
    "scripts/rebuild_search_index.py",
    "scripts/search_index_drift.py",
}


def _named(source: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name) and node.id in NAMES:
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in NAMES:
            found.add(node.attr)
        elif isinstance(node, ast.alias) and node.name.split(".")[-1] in NAMES:
            found.add(node.name)
        elif isinstance(node, ast.Constant) and node.value in NAMES:
            found.add(str(node.value))  # getattr(graph, "nodes_for_index")
    return found


def offenders() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for root in ("services", "packages", "scripts", "cli"):
        for path in sorted((CORE / root).rglob("*.py")):
            rel = path.relative_to(CORE).as_posix()
            if rel in ALLOWED or rel.startswith("services/search_index/") or "/node_modules/" in rel:
                continue
            if names := _named(path.read_text(encoding="utf-8")):
                out[rel] = names
    return out


def test_no_route_or_other_module_reaches_the_indexers_reads() -> None:
    assert (CORE / "services/api/app.py").is_file(), "the routes were not found: nothing was read"
    assert offenders() == {}


def test_a_route_that_reads_through_the_feed_is_named() -> None:
    planted = """
async def search(request, graph):
    return await graph.nodes_for_index([request.query])
"""
    assert _named(planted) == {"nodes_for_index"}
    assert _named("x = getattr(store, 'texts_for_index')") == {"texts_for_index"}
    assert _named("from ports.index_feed import IndexFeedSource") == {"IndexFeedSource"}
