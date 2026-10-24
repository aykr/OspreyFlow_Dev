"""The corpus total behind an edge's weight counts edges as a traversal reaches them, never by
scanning the edge type (ADR-056 Amendment 19).

Seen, 1 October 2026: ArcadeDB stores a few edges twice, and the second record is one a traversal
never reaches but a scan of the type finds. The adapter's corpus total was `g.E().hasLabel(…)`, a
scan, so every stray inflated the total stored with each edge written afterwards (and so its
weight, under weights version 1; from version 2 gamma is 0, ADR-123). The
store below answers the way the real one does about strays: a scan sees 13,076 records, a
traversal from the vertices reaches the 13,068 real edges. The test fails if the total comes from
the scan, whatever the query happens to look like.
"""

from __future__ import annotations

import asyncio
from typing import Any

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from ontology.handling import load_uk_le_scheme

SCAN_SEES = 13_076
TRAVERSAL_REACHES = 13_068


class _StoreWithStrays:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def gremlin(self, query: str, *, session_id: Any = None, **_: Any) -> list[Any]:
        self.queries.append(query)
        if query.startswith("g.E("):
            return [{"result": SCAN_SEES}]  # the stray records are in a scan
        if query.startswith('g.V().has("id",'):
            return [{"result": 3}]  # one vertex's own edge list
        if query.startswith("g.V()"):
            return [{"result": TRAVERSAL_REACHES}]  # reached from the vertices, once each
        raise AssertionError(f"unexpected query: {query}")


def _stats(store: _StoreWithStrays) -> tuple[int, int, int]:
    adapter = GraphArcadeDBAdapter(store, load_uk_le_scheme())  # type: ignore[arg-type]
    return asyncio.run(adapter._corpus_edge_stats("mx_TRANSACTED", "a", "b", session_id="tx"))


def test_the_corpus_total_does_not_count_records_only_a_scan_finds() -> None:
    """Catches a corpus total taken from a scan of the edge type: it would be 13,076, eight more
    than the edges that exist, and every later set of stored components would carry it."""
    _, _, total = _stats(_StoreWithStrays())
    assert total == TRAVERSAL_REACHES


def test_no_corpus_statistic_scans_the_edge_type() -> None:
    """Catches any of the three statistics (source degree, target degree, corpus total) coming from
    a scan: the degrees are traversals today, and must stay so."""
    store = _StoreWithStrays()
    _stats(store)
    assert len(store.queries) == 3 and not any(q.startswith("g.E(") for q in store.queries)


def test_the_total_still_leaves_out_reverted_edges() -> None:
    """Catches the traversal dropping the revert filter: retracted data must not weigh on the
    corpus statistics live edges are scored against (as the scan it replaces did)."""
    store = _StoreWithStrays()
    _stats(store)
    (total_query,) = [q for q in store.queries if not q.startswith('g.V().has("id",')]
    assert '.has("reverted",false)' in total_query and "mx_TRANSACTED" in total_query
