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


#: How many ids of each kind of difference the report keeps; the counts are always exact.
DRIFT_IDS_KEPT = 1000


class DriftOrderError(RuntimeError):
    """A stream not in strictly ascending id order: the graph's order and the index's disagree for
    some id, so a merge would call everything after it missing. Raised, never compared wrongly."""


@dataclass
class Drift:
    graph_nodes: int = 0
    index_documents: int = 0
    #: The first `DRIFT_IDS_KEPT` ids of each kind, in id order; `*_count` is every one.
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    missing_count: int = 0
    extra_count: int = 0
    stale_count: int = 0
    #: Missing because OpenSearch refused them for good, each with its recorded reason (the first
    #: `DRIFT_IDS_KEPT`; `refused_count` is every one).
    refused: dict[str, str] = field(default_factory=dict)
    refused_count: int = 0
    #: The outboxes still held rows when the check ran: a change on its way shows as drift.
    pending: bool = False
    #: Documents in the index the streams never read: of another kind than node or text, or
    #: without the key they are sorted by (which OpenSearch sorts last). Counted, by the index's
    #: own count less the documents read, so none is passed over unsaid (rule 2).
    unread_count: int = 0

    @property
    def none(self) -> bool:
        return not (
            self.missing_count
            or self.extra_count
            or self.stale_count
            or self.refused_count
            or self.unread_count
        )

    def _note(self, kind: str, doc_id: str) -> None:
        setattr(self, f"{kind}_count", getattr(self, f"{kind}_count") + 1)
        kept = getattr(self, kind)
        if len(kept) < DRIFT_IDS_KEPT:
            kept.append(doc_id)


class _Stream:
    """One kind of the index's documents (`kind` node or text), sorted by `key`, a page at a time
    with `search_after`: (key, document id, fingerprint), strictly ascending or raised."""

    def __init__(self, client: AsyncOpenSearch, alias: str, kind: str, key: str, page: int) -> None:
        self._client, self._alias, self._kind, self._key, self._page = (
            client,
            alias,
            kind,
            key,
            page,
        )
        self._buffer: list[tuple[str, str, str]] = []
        self._after: str | None = None
        self._done = False
        self.seen = 0
        self.head: tuple[str, str, str] | None = None

    async def advance(self) -> None:
        if not self._buffer and not self._done:
            body: dict[str, Any] = {
                "query": {"term": {"kind": self._kind}},
                "sort": [{self._key: "asc"}],
            }
            if self._after is not None:
                body["search_after"] = [self._after]
            hits = (await self._client.search(index=self._alias, body=body, size=self._page))[
                "hits"
            ]["hits"]
            self._done = len(hits) < self._page
            # A document without the key is sorted after every one with it: it and every one
            # after it are left unread here, and counted as unread by the check.
            keyed = [h for h in hits if h["_source"].get(self._key) is not None]
            if len(keyed) < len(hits):
                self._done = True
            self._buffer = [
                (str(h["_source"][self._key]), str(h["_id"]), fingerprint(h["_source"]))
                for h in keyed
            ]
            self._buffer.reverse()
        before = self.head
        self.head = self._buffer.pop() if self._buffer else None
        if self.head is not None:
            self.seen += 1
            self._after = self.head[0]
            if before is not None and self.head[0] <= before[0]:
                raise DriftOrderError(
                    f"the index's {self._kind} documents are not in ascending {self._key} order "
                    f"at {self.head[0]!r}: the check stops rather than compare them wrongly"
                )


async def drift(
    source: IndexFeedSource,
    texts: TextFeedSource,
    client: AsyncOpenSearch,
    alias: str,
    schema: OntologySchema,
    *,
    page: int = 1000,
) -> Drift:
    """The graph's live nodes against the index, by id and fingerprint (ADR-150 decision 5),
    streamed: the graph's live ids, the index's node documents (by `id`) and its text documents (by
    `node_id`) merged a page at a time in one id order, so memory is bounded by `page`, not by the
    graph. A document missing is looked up in the refused index a page at a time."""
    pending = bool(await source.pending_index(1)) or bool(await texts.pending_text_index(1))
    await client.indices.refresh(index=alias)
    report = Drift(pending=pending)
    nodes_stream = _Stream(client, alias, "node", "id", page)
    texts_stream = _Stream(client, alias, "text", "node_id", page)
    await nodes_stream.advance()
    await texts_stream.advance()
    missing: list[str] = []
    after: str | None = None
    previous: str | None = None
    while True:
        ids = await source.live_node_ids(after=after, limit=page)
        if not ids:
            break
        report.graph_nodes += len(ids)
        nodes = await source.nodes_for_index(ids)
        held = await texts.texts_for_index(ids)
        for node_id in ids:
            if previous is not None and node_id <= previous:
                raise DriftOrderError(
                    f"the graph's live ids are not in ascending order at {node_id!r}: the check "
                    "stops rather than compare them wrongly"
                )
            previous = node_id
            node = nodes.get(node_id)
            expected_node = fingerprint(node_document(node, schema)) if node is not None else None
            expected_text = (
                fingerprint(text_document(node, *held[node_id], schema))
                if node is not None and node_id in held
                else None
            )
            for stream, expected, doc_id in (
                (nodes_stream, expected_node, node_id),
                (texts_stream, expected_text, text_document_id(node_id)),
            ):
                while stream.head is not None and stream.head[0] < node_id:
                    report._note("extra", stream.head[1])
                    await stream.advance()
                if stream.head is not None and stream.head[0] == node_id:
                    if expected is None:
                        report._note("extra", stream.head[1])
                    elif stream.head[2] != expected:
                        report._note("stale", doc_id)
                    await stream.advance()
                elif expected is not None:
                    missing.append(doc_id)
            if len(missing) >= page:
                await _sort_missing(client, alias, missing, report)
                missing = []
        after = ids[-1]
    for stream in (nodes_stream, texts_stream):
        while stream.head is not None:
            report._note("extra", stream.head[1])
            await stream.advance()
    await _sort_missing(client, alias, missing, report)
    report.index_documents = int((await client.count(index=alias))["count"])
    report.unread_count = report.index_documents - nodes_stream.seen - texts_stream.seen
    return report


async def _sort_missing(
    client: AsyncOpenSearch, alias: str, missing: list[str], report: Drift
) -> None:
    """Each missing document either refused (with its recorded reason) or missing."""
    if not missing:
        return
    index = refused_index(alias)
    reasons: dict[str, str] = {}
    if await client.indices.exists(index=index):
        found = await client.mget(index=index, body={"ids": missing})
        reasons = {
            str(d["_id"]): str(d["_source"].get("reason", ""))
            for d in found["docs"]
            if d.get("found")
        }
    for doc_id in missing:
        if doc_id in reasons:
            report.refused_count += 1
            if len(report.refused) < DRIFT_IDS_KEPT:
                report.refused[doc_id] = reasons[doc_id]
        else:
            report._note("missing", doc_id)


__all__ = [
    "DRIFT_IDS_KEPT",
    "Drift",
    "DriftOrderError",
    "Rebuilt",
    "drift",
    "rebuild",
    "text_document_id",
]
