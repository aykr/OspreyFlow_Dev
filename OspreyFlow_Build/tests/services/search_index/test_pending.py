"""The query side's exclusion read (`services/search_index/pending.py`; ADR-150 decision 2, the
orchestrator's ruling of 13 November): every pending node's id, from both outboxes, ids alone; and
never claimed whole when an outbox holds more rows than the limit (a node can appear more than
once, so a set built from the first rows could miss one: it fails closed by saying so)."""

from __future__ import annotations

from collections.abc import Sequence

from ports.index_feed import PendingIndex
from services.search_index.pending import pending_node_ids


class _Graph:
    def __init__(self, ids: Sequence[str]) -> None:
        self.ids = list(ids)

    async def pending_index(self, limit: int) -> list[PendingIndex]:
        return [PendingIndex(ref=f"#1:{i}", node_id=n) for i, n in enumerate(self.ids[:limit])]


class _Texts:
    def __init__(self, ids: Sequence[str]) -> None:
        self.ids = list(ids)

    async def pending_text_index(self, limit: int) -> list[tuple[int, str]]:
        return list(enumerate(self.ids[:limit]))


async def test_both_outboxes_ids_alone_and_whole() -> None:
    found = await pending_node_ids(_Graph(["a", "b", "a"]), _Texts(["d"]), limit=10)  # type: ignore[arg-type]
    assert found.ids == frozenset({"a", "b", "d"}) and found.complete
    assert all(isinstance(i, str) for i in found.ids)


async def test_more_rows_than_the_limit_is_never_claimed_whole() -> None:
    """Ten rows of one node, then another: read to the limit, the second is not seen, and the set
    says so, though it holds fewer ids than the limit."""
    graph = _Graph(["a"] * 10 + ["b"])
    found = await pending_node_ids(graph, _Texts([]), limit=10)  # type: ignore[arg-type]
    assert found.ids == frozenset({"a"}) and not found.complete
    texts = _Texts([f"d{i}" for i in range(11)])
    assert not (await pending_node_ids(_Graph([]), texts, limit=10)).complete  # type: ignore[arg-type]
    assert (await pending_node_ids(_Graph(["a"] * 10), _Texts([]), limit=10)).complete  # type: ignore[arg-type]
