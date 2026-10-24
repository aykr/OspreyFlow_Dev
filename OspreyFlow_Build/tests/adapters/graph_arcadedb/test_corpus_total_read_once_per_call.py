"""The corpus total behind an edge's weight is read once per `upsert_edges` call, not once per edge
(ADR-056 Amendment 22).

Seen, 1 October 2026, loading the Enron corpus (233,890 links): every edge written asked the store
for the total weight of every edge of its type, a query that visits the whole corpus. The cost of
a write therefore grew with everything already loaded: 146 s per 1,000 links at the start and 230 s
per 1,000 at 82,000 links, a projected 17 hours. The total only has to be read once per call and
carried forward, because the call's own writes are the only change it can see.

The store below answers as the real one does where it matters here: it refuses a query it does not
recognise, and it computes every answer from the edges actually written, so a total that is carried
forward wrongly changes the stored components and fails the comparison with the one-at-a-time
result. It changes the weight too only under weights version 1: from version 2 gamma is 0 and the
counts move no weight (ADR-123), so the comparison is made on the components, which `weights()`
includes.
"""

from __future__ import annotations

import asyncio

from schemas.domain import EdgeWrite

from tests.adapters.graph_arcadedb.edge_store import (
    CountingStore,
    make_adapter,
    make_edge,
    weights,
)


def _batch() -> list[EdgeWrite]:
    """Forty writes, with the pair a to b recurring so the merge path is exercised too."""
    writes = [make_edge(f"n{i}", f"n{i + 1}", i) for i in range(37)]
    writes += [make_edge("a", "b", 100), make_edge("a", "b", 101), make_edge("b", "a", 102)]
    return writes


def test_a_batch_reads_the_corpus_total_once() -> None:
    """Catches the corpus total being asked for once per edge: forty writes would cost forty
    whole-corpus traversals, the quadratic load that took 17 hours projected on Enron."""
    store = CountingStore()
    asyncio.run(make_adapter(store).upsert_edges(_batch(), "tx"))
    assert store.corpus_total_queries() == 1


def test_a_batch_weighs_each_edge_as_if_written_one_at_a_time() -> None:
    """Catches the carried-forward total drifting from the stored one: skipping the call's own
    delta, adding it twice, or not adding it for a merge into an existing pair would each change a
    stored component (and the weight, under version 1 only), so the batch and the one-at-a-time
    loads would disagree."""
    batched = CountingStore()
    asyncio.run(make_adapter(batched).upsert_edges(_batch(), "tx"))

    one_by_one = CountingStore()
    graph = make_adapter(one_by_one)
    for write in _batch():
        asyncio.run(graph.upsert_edges([write], "tx"))

    assert one_by_one.corpus_total_queries() == len(_batch())  # the unchanged behaviour per call
    assert weights(batched) == weights(one_by_one)


def test_nothing_is_carried_from_one_call_to_the_next() -> None:
    """Catches the total being kept on the adapter between calls: a second call must read the
    store again, because anything else may have written or reverted since the first."""
    store = CountingStore()
    graph = make_adapter(store)
    asyncio.run(graph.upsert_edges(_batch()[:5], "tx"))
    asyncio.run(graph.upsert_edges(_batch()[5:10], "tx"))
    assert store.corpus_total_queries() == 2
