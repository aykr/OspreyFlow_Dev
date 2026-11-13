"""The rebuild from the graph and the drift check (ADR-150 decisions 4 and 5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from opensearchpy import AsyncOpenSearch

from ports.index_feed import IndexFeedSource
from schemas.domain import OntologySchema

from .document import fingerprint, node_document, text_document, text_document_id
from .indexer import SearchIndexer, TextFeedSource, building_alias
from .mapping import index_body


@dataclass(frozen=True)
class Rebuilt:
    index: str
    nodes: int
    documents: int


async def rebuild(
    source: IndexFeedSource,
    texts: TextFeedSource,
    client: AsyncOpenSearch,
    alias: str,
    schema: OntologySchema,
    *,
    page: int = 1000,
) -> Rebuilt:
    """Every live node into a new index named with its build time, then the alias moved onto it and
    the old indexes deleted, so a reader never sees a half-built index. The outboxes are left alone:
    their rows are re-applied after the move, idempotently."""
    index = f"{alias}-{datetime.now(UTC).strftime('%Y%m%dt%H%M%S%f')}"
    await client.indices.create(index=index, body=index_body())
    await client.indices.put_alias(index=index, name=building_alias(alias))
    indexer = SearchIndexer(source, texts, client, alias, schema)
    nodes, after = 0, None
    while True:
        ids = await source.live_node_ids(after=after, limit=page)
        if not ids:
            break
        await indexer.index_nodes(ids, index=index)
        nodes += len(ids)
        after = ids[-1]
    await client.indices.refresh(index=index)
    old = (
        list((await client.indices.get_alias(name=alias)).keys())
        if await client.indices.exists_alias(name=alias)
        else []
    )
    actions: list[dict[str, Any]] = [{"remove": {"index": o, "alias": alias}} for o in old]
    actions += [
        {"add": {"index": index, "alias": alias}},
        {"remove": {"index": index, "alias": building_alias(alias)}},
    ]
    await client.indices.update_aliases(body={"actions": actions})
    for o in old:
        if o != index:
            await client.indices.delete(index=o)
    documents = int((await client.count(index=index))["count"])
    return Rebuilt(index=index, nodes=nodes, documents=documents)


@dataclass
class Drift:
    graph_nodes: int = 0
    index_documents: int = 0
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)

    @property
    def none(self) -> bool:
        return not (self.missing or self.extra or self.stale)


async def _indexed(client: AsyncOpenSearch, alias: str) -> dict[str, str]:
    """Every document in the index: id -> fingerprint of its source."""
    found: dict[str, str] = {}
    answer = await client.search(
        index=alias, body={"query": {"match_all": {}}, "sort": ["_doc"]}, scroll="2m", size=1000
    )
    scroll = answer.get("_scroll_id")
    try:
        while answer["hits"]["hits"]:
            for hit in answer["hits"]["hits"]:
                found[hit["_id"]] = fingerprint(hit["_source"])
            answer = await client.scroll(scroll_id=scroll, scroll="2m")
            scroll = answer.get("_scroll_id")
    finally:
        if scroll:
            await client.clear_scroll(scroll_id=scroll)
    return found


async def drift(
    source: IndexFeedSource,
    texts: TextFeedSource,
    client: AsyncOpenSearch,
    alias: str,
    schema: OntologySchema,
    *,
    page: int = 1000,
) -> Drift:
    """The graph's live nodes against the index, by id and fingerprint (ADR-150 decision 5)."""
    await client.indices.refresh(index=alias)
    indexed = await _indexed(client, alias)
    report = Drift(index_documents=len(indexed))
    expected: set[str] = set()
    after = None
    while True:
        ids = await source.live_node_ids(after=after, limit=page)
        if not ids:
            break
        report.graph_nodes += len(ids)
        nodes = await source.nodes_for_index(ids)
        held = await texts.texts_for_index(ids)
        for node_id in ids:
            node = nodes.get(node_id)
            if node is None:
                continue  # changed since it was listed; the next check sees it
            documents = [node_document(node, schema)]
            if node_id in held:
                documents.append(text_document(node, *held[node_id]))
            for document in documents:
                expected.add(document["id"])
                if document["id"] not in indexed:
                    report.missing.append(document["id"])
                elif indexed[document["id"]] != fingerprint(document):
                    report.stale.append(document["id"])
        after = ids[-1]
    report.extra = sorted(set(indexed) - expected)
    report.missing.sort()
    report.stale.sort()
    return report


__all__ = ["Drift", "Rebuilt", "drift", "rebuild", "text_document_id"]
