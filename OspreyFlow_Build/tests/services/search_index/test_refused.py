"""ADR-150 decisions 2, 4 and 5, offline: a document OpenSearch refuses for good never holds the
outbox behind it. It is set aside (recorded in the deployment's refused index, an error logged), the
rest of the batch is written and the outbox cleared, and the drift check reports it as refused, not
missing; a passing refusal (a 429) is raised and the batch kept. A rebuild that fails leaves no index
behind, a rebuild finds and removes one a crashed rebuild left, and a rebuild that completes keeps
only its own refusal records. A keyword value over Lucene's term limit is indexed (`ignore_above`),
never refused.

Against `FakeOpenSearch`, which refuses what OpenSearch refuses (its docstring lists them).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import pytest

from ontology.loader import load_default_ontology
from ports.index_feed import PendingIndex
from schemas.domain import Node
from services.search_index import indexer as indexer_module
from services.search_index.indexer import (
    IndexWriteError,
    SearchIndexer,
    building_alias,
    ensure_index,
    refused_index,
    write_actions,
)
from services.search_index.mapping import index_body
from services.search_index.rebuild import drift, rebuild
from tests.services.search_index.fake_opensearch import FakeOpenSearch
from tests.services.search_index.test_document import _node

SCHEMA = load_default_ontology()
CAP = 4096
ALIAS = "a"


def _person(node_id: str, family_name: str) -> Node:
    node = _node("Person", {"family_name": family_name, "given_names": "Ada"}, ["ds-1"])
    return node.model_copy(update={"id": node_id})


class _Graph:
    """The outbox and the nodes: `nodes` live, `pending` queued."""

    def __init__(self, nodes: Sequence[Node]) -> None:
        self.nodes = {n.id: n for n in nodes}
        self.pending = list(self.nodes)
        self.cleared: list[str] = []

    async def pending_index(self, limit: int) -> list[PendingIndex]:
        return [PendingIndex(ref=n, node_id=n) for n in self.pending[:limit]]

    async def clear_pending_index(self, refs: Sequence[str]) -> None:
        self.cleared += list(refs)
        self.pending = [n for n in self.pending if n not in refs]

    async def nodes_for_index(self, node_ids: Sequence[str]) -> dict[str, Any]:
        return {n: self.nodes.get(n) for n in node_ids}

    async def live_node_ids(self, *, after: str | None, limit: int) -> list[str]:
        ids = sorted(self.nodes)
        start = 0 if after is None else ids.index(after) + 1
        return ids[start : start + limit]


class _Texts:
    async def pending_text_index(self, limit: int) -> list[tuple[int, str]]:
        return []

    async def clear_pending_text_index(self, refs: Sequence[int]) -> None:
        return None

    async def texts_for_index(self, document_ids: Sequence[str]) -> dict[str, tuple[str, str]]:
        return {}


async def _setup(
    nodes: Sequence[Node], limit: int = CAP
) -> tuple[FakeOpenSearch, _Graph, SearchIndexer]:
    client = FakeOpenSearch(limit=limit)
    graph = _Graph(nodes)
    await ensure_index(client, ALIAS)  # type: ignore[arg-type]
    return client, graph, SearchIndexer(graph, _Texts(), client, ALIAS, SCHEMA)  # type: ignore[arg-type]


def _indexed(client: FakeOpenSearch) -> set[str]:
    return {d for i in client.resolve(ALIAS) for d in client.docs[i]}


async def test_a_document_over_the_cap_is_set_aside_and_the_outbox_moves_on(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(indexer_module, "MAX_BULK_BYTES", CAP)
    client, graph, indexer = await _setup(
        [_person("p-1", "Lovelace"), _person("p-2", "x" * CAP), _person("p-3", "Byron")]
    )
    with caplog.at_level(logging.ERROR):
        assert await indexer.drain_once() == 3
    assert graph.pending == []
    assert {"p-1", "p-3"} <= _indexed(client) and "p-2" not in _indexed(client)
    assert set(client.docs[refused_index(ALIAS)]) == {"p-2"}
    assert "p-2" in caplog.text and "set aside" in caplog.text

    report = await drift(graph, _Texts(), client, ALIAS, SCHEMA)  # type: ignore[arg-type]
    assert list(report.refused) == ["p-2"] and "over the" in report.refused["p-2"]
    assert "p-2" not in report.missing
    assert not report.none and not report.pending


async def test_a_permanent_refusal_of_one_item_is_set_aside() -> None:
    """A 400 for one item (here the strict mapping refusing a field it does not hold)."""
    client = FakeOpenSearch()
    await ensure_index(client, ALIAS)  # type: ignore[arg-type]
    body = [
        {"index": {"_index": ALIAS, "_id": "good"}},
        {"kind": "node", "id": "good"},
        {"index": {"_index": ALIAS, "_id": "bad"}},
        {"kind": "node", "id": "bad", "not_in_the_mapping": 1},
    ]
    refused = await write_actions(client, body)  # type: ignore[arg-type]
    assert [r.doc_id for r in refused] == ["bad"]
    assert "strict_dynamic_mapping_exception" in refused[0].reason
    assert "good" in _indexed(client)


async def test_a_passing_refusal_is_raised_and_the_outbox_kept() -> None:
    client, graph, indexer = await _setup([_person("p-1", "Lovelace")])
    client.busy = True
    with pytest.raises(IndexWriteError, match="429"):
        await indexer.drain_once()
    assert graph.pending == ["p-1"] and graph.cleared == []
    assert not await client.indices.exists(index=refused_index(ALIAS))


async def test_a_keyword_over_the_term_limit_is_indexed_not_refused() -> None:
    """`ignore_above`: Lucene refuses a term over 32,766 bytes, and with it the whole document."""
    client, graph, indexer = await _setup([_person("p-1", "名" * 12000)], limit=1024 * 1024)
    assert await indexer.drain_once() == 1
    assert "p-1" in _indexed(client)
    assert not await client.indices.exists(index=refused_index(ALIAS))


async def test_a_rebuild_removes_the_index_a_crashed_rebuild_left() -> None:
    client, graph, indexer = await _setup([_person("p-1", "Lovelace")])
    await client.indices.create(index="a-crashed", body=index_body())
    await client.indices.put_alias(index="a-crashed", name=building_alias(ALIAS))
    built = await rebuild(graph, _Texts(), client, ALIAS, SCHEMA)  # type: ignore[arg-type]
    assert "a-crashed" not in client.docs
    assert client.resolve(ALIAS) == [built.index]
    # A second rebuild then a drain: no alias over two indexes refuses the writes.
    await rebuild(graph, _Texts(), client, ALIAS, SCHEMA)  # type: ignore[arg-type]
    graph.pending = ["p-1"]
    assert await indexer.drain_once() == 1


async def test_a_rebuild_that_fails_leaves_nothing_and_keeps_the_refusal_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(indexer_module, "MAX_BULK_BYTES", CAP)
    client, graph, indexer = await _setup([_person("p-1", "Lovelace"), _person("p-2", "x" * CAP)])
    await indexer.drain_once()
    before = set(client.docs)
    client.busy = True
    with pytest.raises(IndexWriteError):
        await rebuild(graph, _Texts(), client, ALIAS, SCHEMA)  # type: ignore[arg-type]
    assert set(client.docs) == before
    assert not await client.indices.exists_alias(name=building_alias(ALIAS))
    assert set(client.docs[refused_index(ALIAS)]) == {"p-2"}


async def test_a_rebuild_keeps_only_its_own_refusal_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(indexer_module, "MAX_BULK_BYTES", CAP)
    client, graph, indexer = await _setup([_person("p-1", "Lovelace"), _person("p-2", "x" * CAP)])
    await indexer.drain_once()
    # p-2 mended in the graph; p-3 now refused.
    graph.nodes["p-2"] = _person("p-2", "Babbage")
    graph.nodes["p-3"] = _person("p-3", "y" * CAP)
    await rebuild(graph, _Texts(), client, ALIAS, SCHEMA)  # type: ignore[arg-type]
    assert set(client.docs[refused_index(ALIAS)]) == {"p-3"}
    assert {"p-1", "p-2"} <= _indexed(client)


async def test_the_drift_check_says_the_outboxes_still_hold_changes() -> None:
    client, graph, indexer = await _setup([_person("p-1", "Lovelace")])
    report = await drift(graph, _Texts(), client, ALIAS, SCHEMA)  # type: ignore[arg-type]
    assert report.pending and report.missing == ["p-1"]
    await indexer.drain_once()
    report = await drift(graph, _Texts(), client, ALIAS, SCHEMA)  # type: ignore[arg-type]
    assert report.none and not report.pending
