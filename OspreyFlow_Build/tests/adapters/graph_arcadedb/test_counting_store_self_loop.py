"""The shared in-memory store must answer a node's degree as the real store's `bothE(label)` does:
a link from a node to itself is read back twice from that node (ADR-120 Amendment 4), so it
contributes its occurrences twice. Catches a fake that counts it once, which would let a write
path that adds a self-loop's occurrences once pass every test that uses the fake (rule 15: a fake
standing in for a store must refuse and count as the store does)."""

from __future__ import annotations

import asyncio

from adapters.graph_arcadedb.gremlin_literals import groovy_string_literal
from tests.adapters.graph_arcadedb.edge_store import CountingStore


def _degree(store: CountingStore, node: str) -> int:
    query = (
        f'g.V().has("id",{groovy_string_literal(node)}).bothE({groovy_string_literal("L")})'
        '.has("reverted",false).values("occurrences").sum()'
    )
    (answer,) = asyncio.run(store.gremlin(query))
    return int(answer["result"])


def test_the_counting_store_counts_a_self_loop_twice_like_bothE() -> None:
    store = CountingStore()
    store.edges[("a", "b")] = {"occurrences": 7}
    store.edges[("a", "a")] = {"occurrences": 3}
    assert _degree(store, "a") == 7 + 2 * 3
    assert _degree(store, "b") == 7
