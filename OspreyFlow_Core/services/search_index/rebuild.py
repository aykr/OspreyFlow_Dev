"""The rebuild from the graph and the drift check (ADR-150 decisions 4 and 5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from opensearchpy import AsyncOpenSearch, TransportError

from ports.index_feed import IndexFeedSource
from schemas.domain import OntologySchema

from .document import fingerprint, node_document, text_document, text_document_id
from .indexer import SearchIndexer, TextFeedSource, building_alias, refused_index
from .mapping import index_body


class RebuildRunning(RuntimeError):
    """Another rebuild of the same alias holds the lock: said in words, never run beside it (two
    under one building alias would refuse every write, and one would delete the other's index)."""


def rebuild_lock(alias: str) -> str:
    return f"{alias}-rebuild-lock"


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
    # One rebuild at a time: the lock is an index, made atomically (a second create is refused).
    lock = rebuild_lock(alias)
    try:
        await client.indices.create(index=lock, body={"settings": {"number_of_shards": 1}})
    except TransportError as e:
        if e.status_code == 400 and "resource_already_exists" in str(e.error):
            raise RebuildRunning(
                f"a rebuild of {alias} is already running (the index {lock} holds it); if none is "
                f"(one that crashed), delete that index and run the rebuild again"
            ) from e
        raise
    try:
        return await _rebuild(source, texts, client, alias, schema, page=page)
    finally:
        await client.indices.delete(index=lock, ignore_unavailable=True)


async def _rebuild(
    source: IndexFeedSource,
    texts: TextFeedSource,
    client: AsyncOpenSearch,
    alias: str,
    schema: OntologySchema,
    *,
    page: int,
) -> Rebuilt:
    # An index a rebuild that crashed left under the building alias would take every change too,
    # and a second one under it refuses every write (an alias of two indexes with no write index).
    building = building_alias(alias)
    if await client.indices.exists_alias(name=building):
        for left in (await client.indices.get_alias(name=building)).keys():
            await client.indices.delete(index=left, ignore_unavailable=True)
    index = f"{alias}-{datetime.now(UTC).strftime('%Y%m%dt%H%M%S%f')}"
    await client.indices.create(index=index, body=index_body())
    try:
        await client.indices.put_alias(index=index, name=building)
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
            {"remove": {"index": index, "alias": building}},
        ]
        await client.indices.update_aliases(body={"actions": actions})
    except BaseException:
        # A failed rebuild leaves nothing behind: its index, and the building alias with it, go;
        # the alias stays on the index it was on.
        await client.indices.delete(index=index, ignore_unavailable=True)
        raise
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
    #: Missing because OpenSearch refused them for good, each with its recorded reason.
    refused: dict[str, str] = field(default_factory=dict)
    #: The outboxes still held rows when the check ran: a change on its way shows as drift.
    pending: bool = False

    @property
    def none(self) -> bool:
        return not (self.missing or self.extra or self.stale or self.refused)


async def _refused(client: AsyncOpenSearch, alias: str) -> dict[str, str]:
    """The record of documents set aside (`indexer.refused_index`): id -> reason."""
    index = refused_index(alias)
    if not await client.indices.exists(index=index):
        return {}
    await client.indices.refresh(index=index)
    found: dict[str, str] = {}
    answer = await client.search(
        index=index, body={"query": {"match_all": {}}, "sort": ["_doc"]}, scroll="2m", size=1000
    )
    scroll = answer.get("_scroll_id")
    try:
        while answer["hits"]["hits"]:
            for hit in answer["hits"]["hits"]:
                found[hit["_id"]] = str(hit["_source"].get("reason", ""))
            answer = await client.scroll(scroll_id=scroll, scroll="2m")
            scroll = answer.get("_scroll_id")
    finally:
        if scroll:
            await client.clear_scroll(scroll_id=scroll)
    return found


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
    """The graph's live nodes against the index, by id and fingerprint (ADR-150 decision 5). It
    holds every indexed id and fingerprint, and every expected id, in memory: about 150 bytes a
    document, so some 4.5 GB at thirty million documents (a streaming check is CARRIES' row)."""
    pending = bool(await source.pending_index(1)) or bool(await texts.pending_text_index(1))
    await client.indices.refresh(index=alias)
    indexed = await _indexed(client, alias)
    set_aside = await _refused(client, alias)
    report = Drift(index_documents=len(indexed), pending=pending)
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
                documents.append(text_document(node, *held[node_id], schema))
            for document in documents:
                expected.add(document["id"])
                if document["id"] not in indexed:
                    report.missing.append(document["id"])
                elif indexed[document["id"]] != fingerprint(document):
                    report.stale.append(document["id"])
        after = ids[-1]
    report.extra = sorted(set(indexed) - expected)
    report.refused = {d: set_aside[d] for d in sorted(report.missing) if d in set_aside}
    report.missing = [d for d in report.missing if d not in report.refused]
    report.missing.sort()
    report.stale.sort()
    return report


__all__ = ["Drift", "Rebuilt", "drift", "rebuild", "text_document_id"]
