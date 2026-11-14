"""ADR-150 decision 5, offline: the drift check streams. It compares the graph's live ids, the
index's node documents and its text documents a page at a time, in one id order, so its memory is
bounded by the page, not by the graph: run on step B's load (tens of millions of documents), a
check that held every id and fingerprint would fail on memory on the very load it is meant to
check. Its counts are exact and its id lists keep the first `DRIFT_IDS_KEPT` of each kind, the
count beside them (rule 2: never cut short unsaid). A stream out of that order is raised, never
compared wrongly."""

from __future__ import annotations

import tracemalloc
from collections.abc import Sequence
from typing import Any

import pytest

from ontology.loader import load_default_ontology
from services.search_index import rebuild as rebuild_module
from services.search_index.document import node_document, text_document
from services.search_index.indexer import ensure_index
from services.search_index.rebuild import drift
from tests.services.search_index.fake_opensearch import FakeOpenSearch
from tests.services.search_index.test_document import _node

SCHEMA = load_default_ontology()
ALIAS = "a"
PAGE = 100


def _person(i: int) -> Any:
    node = _node("Person", {"family_name": f"Name{i}", "given_names": "Ada"}, ["ds-1"])
    return node.model_copy(update={"id": f"p-{i:07d}"})


class _Graph:
    def __init__(self, nodes: Sequence[Any]) -> None:
        self.nodes = {n.id: n for n in nodes}
        self.ids = sorted(self.nodes)

    async def pending_index(self, limit: int) -> list[Any]:
        return []

    async def nodes_for_index(self, node_ids: Sequence[str]) -> dict[str, Any]:
        return {n: self.nodes.get(n) for n in node_ids}

    async def live_node_ids(self, *, after: str | None, limit: int) -> list[str]:
        import bisect

        start = 0 if after is None else bisect.bisect_right(self.ids, after)
        return self.ids[start : start + limit]


class _Texts:
    def __init__(self, texts: dict[str, tuple[str, str]] | None = None) -> None:
        self.texts = texts or {}

    async def pending_text_index(self, limit: int) -> list[tuple[int, str]]:
        return []

    async def texts_for_index(self, document_ids: Sequence[str]) -> dict[str, tuple[str, str]]:
        return {d: self.texts[d] for d in document_ids if d in self.texts}


async def _world(n: int, texts: dict[str, tuple[str, str]] | None = None) -> tuple[Any, ...]:
    client = FakeOpenSearch()
    await ensure_index(client, ALIAS)  # type: ignore[arg-type]
    graph = _Graph([_person(i) for i in range(n)])
    (index,) = client.resolve(ALIAS)
    for node in graph.nodes.values():
        client.docs[index][node.id] = node_document(node, SCHEMA)
        if texts and node.id in texts:
            client.docs[index][f"text:{node.id}"] = text_document(node, *texts[node.id], SCHEMA)
    return client, graph, _Texts(texts)


async def _peak(n: int) -> int:
    """Every other node with a text (the text stream pages too), and half the documents missing,
    some of them refused (so the missing ids and the refused index's lookups page too)."""
    texts_of = {f"p-{i:07d}": ("He met Ada.", "unit-1") for i in range(0, n, 2)}
    client, graph, texts = await _world(n, texts_of)
    (index,) = client.resolve(ALIAS)
    for i in range(0, n, 2):
        del client.docs[index][f"p-{i:07d}"]
    await client.index(index=f"{ALIAS}-refused", id="p-0000000", body={"doc_id": "p-0000000",
                                                                     "reason": "400 x"})  # fmt: skip
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        before = tracemalloc.get_traced_memory()[0]
        report = await drift(graph, texts, client, ALIAS, SCHEMA, page=PAGE)  # type: ignore[arg-type]
        peak = tracemalloc.get_traced_memory()[1] - before
    finally:
        tracemalloc.stop()
    assert report.graph_nodes == n and report.missing_count == n // 2 - 1
    assert report.refused_count == 1 and report.index_documents == n // 2 + n // 2
    return peak


async def test_its_memory_is_bounded_by_the_page_not_the_graph() -> None:
    """Ten times the graph, about the same peak: a check holding every id and fingerprint grows
    with it (about 150 bytes a document)."""
    small, large = await _peak(1_000), await _peak(10_000)
    assert large < 2 * small, (small, large)


async def test_each_difference_is_found_while_streaming() -> None:
    texts = {"p-0000003": ("He met Ada.", "unit-1"), "p-0000007": ("A letter.", "unit-1")}
    client, graph, source_texts = await _world(10, texts)
    (index,) = client.resolve(ALIAS)
    del client.docs[index]["p-0000002"]  # missing
    client.docs[index]["p-0000005"] = {**client.docs[index]["p-0000005"], "names": ["Other"]}  # stale
    client.docs[index]["p-9999999"] = {"kind": "node", "id": "p-9999999"}  # extra, past the end
    client.docs[index]["p-0000004x"] = {"kind": "node", "id": "p-0000004x"}  # extra, in between
    del client.docs[index]["text:p-0000003"]  # a text missing
    client.docs[index]["text:p-0000001"] = {"kind": "text", "id": "text:p-0000001",
                                           "node_id": "p-0000001"}  # a text extra  # fmt: skip
    report = await drift(graph, source_texts, client, ALIAS, SCHEMA, page=3)  # type: ignore[arg-type]
    assert sorted(report.missing) == ["p-0000002", "text:p-0000003"]
    assert report.stale == ["p-0000005"]
    assert sorted(report.extra) == ["p-0000004x", "p-9999999", "text:p-0000001"]
    assert (report.missing_count, report.stale_count, report.extra_count) == (2, 1, 3)
    assert report.graph_nodes == 10 and not report.none


async def test_the_counts_are_exact_and_the_lists_say_they_are_cut(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rebuild_module, "DRIFT_IDS_KEPT", 5)
    client, graph, texts = await _world(30)
    (index,) = client.resolve(ALIAS)
    client.docs[index].clear()
    report = await drift(graph, texts, client, ALIAS, SCHEMA, page=7)  # type: ignore[arg-type]
    assert report.missing_count == 30 and len(report.missing) == 5
    assert report.missing == [f"p-{i:07d}" for i in range(5)]


async def test_an_index_stream_out_of_order_is_raised() -> None:
    from services.search_index.rebuild import DriftOrderError

    client, graph, texts = await _world(6)
    client.unordered = True
    with pytest.raises(DriftOrderError, match="node documents"):
        await drift(graph, texts, client, ALIAS, SCHEMA, page=3)  # type: ignore[arg-type]


async def test_an_extra_before_the_first_id_and_a_node_listed_but_not_live() -> None:
    """A document sorting before the graph's first id is extra; a node the graph lists live but
    reads back as not live (changed since it was listed) has its documents counted extra."""
    texts = {"p-0000001": ("A letter.", "unit-1")}
    client, graph, source_texts = await _world(3, texts)
    (index,) = client.resolve(ALIAS)
    client.docs[index]["a-first"] = {"kind": "node", "id": "a-first"}
    real = graph.nodes_for_index

    async def changed(node_ids: Sequence[str]) -> dict[str, Any]:
        found = await real(node_ids)
        return {**found, "p-0000001": None}

    graph.nodes_for_index = changed  # type: ignore[method-assign]
    report = await drift(graph, source_texts, client, ALIAS, SCHEMA, page=2)  # type: ignore[arg-type]
    assert sorted(report.extra) == ["a-first", "p-0000001", "text:p-0000001"]
    assert report.missing == [] and report.stale == []


def test_the_command_says_an_order_fault_and_exits_3_never_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 1 is drift, which a rebuild mends; an order fault is not, so it never exits 1."""
    import contextlib

    from scripts import search_index_drift
    from services.search_index.rebuild import DriftOrderError

    @contextlib.asynccontextmanager
    async def resources() -> Any:
        yield type("R", (), {"source": None, "texts": None, "client": None, "alias": "a",
                             "schema": None})()  # fmt: skip

    async def disordered(*_: Any, **__: Any) -> Any:
        raise DriftOrderError("the graph's live ids are not in ascending order at 'x'")

    monkeypatch.setattr(search_index_drift, "feed_resources", resources)
    monkeypatch.setattr(search_index_drift, "drift", disordered)
    assert search_index_drift.main([]) == search_index_drift.ORDER_FAULT == 3
    assert "a rebuild cannot mend this" in capsys.readouterr().err


async def test_a_stream_out_of_order_is_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    """The graph's order and the index's must agree; where they do not (an id whose order differs
    between the two), the check stops rather than calling every document after it missing."""
    from services.search_index.rebuild import DriftOrderError

    client, graph, texts = await _world(5)
    graph.ids = list(reversed(graph.ids))
    with pytest.raises(DriftOrderError):
        await drift(graph, texts, client, ALIAS, SCHEMA, page=2)  # type: ignore[arg-type]
