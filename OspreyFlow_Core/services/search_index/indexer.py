"""The indexer (ADR-150 decision 2): drains the graph's outbox and the text outbox into the index.

Each batch: the outbox rows, each node read as stored (`IndexFeedSource.nodes_for_index`), each
text (`TextFeedSource.texts_for_index`), then the bulk requests, none over `MAX_BULK_BYTES`. A
node that is not live is deleted, its text's document with it; a live node is indexed, and its
text's document indexed or deleted.
The rows are removed only once OpenSearch has acknowledged every action, so delivery is at least
once and each write is idempotent (a document is its node's current state, keyed by id)."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from opensearchpy import AsyncOpenSearch

from ports.index_feed import IndexFeedSource
from schemas.domain import Node, OntologySchema

from .document import node_document, text_document, text_document_id
from .mapping import index_body

log = logging.getLogger(__name__)


class TextFeedSource(Protocol):
    async def pending_text_index(self, limit: int) -> list[tuple[int, str]]: ...

    async def clear_pending_text_index(self, refs: Sequence[int]) -> None: ...

    async def texts_for_index(self, document_ids: Sequence[str]) -> dict[str, tuple[str, str]]: ...


class IndexWriteError(RuntimeError):
    """OpenSearch refused part of a batch for a passing reason (a 429, a 5xx, the request's own
    413): nothing of the batch is cleared, so it is sent again."""


def actions_for(
    index: str,
    node_ids: Sequence[str],
    nodes: dict[str, Node | None],
    texts: dict[str, tuple[str, str]],
    schema: OntologySchema,
    *,
    require_alias: bool = False,
) -> list[dict[str, Any]]:
    """The bulk request's lines for these nodes: a document for each live node and its text, a
    delete for each one not live and for a live node's text that is no longer there. Written to an
    alias, each write says `require_alias`, so an alias that is gone is a refusal, never a new
    unmapped index of its name."""
    body: list[dict[str, Any]] = []

    def write(doc_id: str) -> dict[str, Any]:
        meta: dict[str, Any] = {"_index": index, "_id": doc_id}
        if require_alias:
            meta["require_alias"] = True
        return {"index": meta}

    for node_id in dict.fromkeys(node_ids):
        node = nodes.get(node_id)
        if node is None:
            body.append({"delete": {"_index": index, "_id": node_id}})
            body.append({"delete": {"_index": index, "_id": text_document_id(node_id)}})
            continue
        document = node_document(node, schema)
        body += [write(node_id), document]
        if node_id in texts:
            text, unit = texts[node_id]
            body += [
                write(text_document_id(node_id)),
                text_document(node, text, unit, schema),
            ]
        else:
            body.append({"delete": {"_index": index, "_id": text_document_id(node_id)}})
    return body


#: The most one `_bulk` request carries, in the bytes the client sends: the smallest
#: `http.max_content_length` of an Amazon OpenSearch instance (10 MiB), so no domain refuses a
#: request the indexer or the rebuild builds. A larger batch goes as several requests.
MAX_BULK_BYTES = 10 * 1024 * 1024

#: The longest reason kept with a refused document's record.
_REASON_CHARS = 2000


@dataclass(frozen=True)
class Refused:
    """One document OpenSearch can never take as it is (ADR-150 decision 2): set aside, recorded
    in `refused_index` and logged, so it never holds the outbox behind it."""

    doc_id: str
    reason: str
    index: str


def _encoded(text: str) -> bytes:
    # As the client sends the body (opensearch-py's transport encodes with `surrogatepass`), so a
    # lone surrogate in a property is measured, not raised.
    return text.encode("utf-8", "surrogatepass")


def _requests(
    client: AsyncOpenSearch, body: list[dict[str, Any]]
) -> tuple[list[str], list[Refused]]:
    """The body as the client's own serialiser writes it, cut into requests of at most
    `MAX_BULK_BYTES` encoded, each action kept with its document (an `index` is two lines, a
    `delete` one); and each action over the cap on its own, set aside."""
    dumps = client.transport.serializer.dumps
    actions: list[tuple[str, str, str]] = []
    i = 0
    while i < len(body):
        ((op, meta),) = body[i].items()
        width = 2 if op in ("index", "create", "update") else 1
        lines = "".join(dumps(line) + "\n" for line in body[i : i + width])
        actions.append((str(meta.get("_id")), str(meta.get("_index")), lines))
        i += width
    requests: list[str] = []
    refused: list[Refused] = []
    current, size = "", 0
    for doc_id, index, lines in actions:
        n = len(_encoded(lines))
        if n > MAX_BULK_BYTES:
            refused.append(
                Refused(
                    doc_id,
                    f"{n} bytes, over the {MAX_BULK_BYTES}-byte request cap on its own",
                    index,
                )
            )
            continue
        if size + n > MAX_BULK_BYTES:
            requests.append(current)
            current, size = "", 0
        current += lines
        size += n
    if current:
        requests.append(current)
    return requests, refused


#: The refusals a document earns by its own content, which sending it again cannot change: its
#: shape against the mapping, or a term over Lucene's limit. Every other refusal, whatever its
#: status (a write block's 403, a closed index's 400, an alias over two indexes, a 429, a 5xx), is
#: the cluster's state, not the document's: raised, and the batch sent again.
_DOCUMENT_REFUSALS = frozenset(
    {
        "mapper_parsing_exception",
        "strict_dynamic_mapping_exception",
        "document_parsing_exception",
        "max_bytes_length_exceeded_exception",
    }
)
_FIELD = re.compile(
    r'field \[([\w.]{1,200})\]|field="([\w.]{1,200})"|introduction of \[([\w.]{1,200})\]'
)


def _permanent(op: str, error: Any) -> bool:
    """Only a write (never a delete: a document that should be gone is never left set aside), and
    only for the document's own content."""
    if op not in ("index", "create", "update") or not isinstance(error, dict):
        return False
    caused = error.get("caused_by")
    kinds = {error.get("type"), caused.get("type") if isinstance(caused, dict) else None}
    return bool(kinds & _DOCUMENT_REFUSALS)


def _reason(status: int, error: dict[str, Any]) -> str:
    """The refusal's type and the field it names, never its words: OpenSearch's reason quotes the
    value (a preview of the field, a term's bytes), which is a record's content."""
    kinds = [str(error.get("type"))]
    caused = error.get("caused_by")
    if isinstance(caused, dict) and caused.get("type"):
        kinds.append(str(caused["type"]))
    found = _FIELD.search(str(error.get("reason", "")))
    field = next((g for g in found.groups() if g), None) if found else None
    return f"{status} {' / '.join(kinds)}" + (f" in field {field}" if field else "")


async def write_actions(client: AsyncOpenSearch, body: list[dict[str, Any]]) -> list[Refused]:
    """The body in requests of at most `MAX_BULK_BYTES`; a delete of a document that was never
    there is not a failure. A document refused for good (over the cap alone, or refused for its own
    content) is returned for the caller to record, and whatever that index already held for it is
    deleted in the same pass, so an older version never stays searchable with older access fields
    (it fails closed). Any other refusal is raised, a 413 for the whole request too (never
    swallowed), so the caller clears nothing of the batch and sends it again."""
    if not body:
        return []
    requests, refused = _requests(client, body)
    for request in requests:
        refused += await _write_one(client, request)
    if refused:
        removal = [{"delete": {"_index": r.index, "_id": r.doc_id}} for r in refused]
        removed, still_refused = _requests(client, removal)
        assert not still_refused  # a delete line is never over the cap
        for request in removed:
            if await _write_one(client, request):
                raise IndexWriteError("a refused document's older version could not be deleted")
    return refused


async def _write_one(client: AsyncOpenSearch, request: str) -> list[Refused]:
    answer = await client.bulk(body=request)
    if not answer.get("errors"):
        return []
    refused: list[Refused] = []
    passing = []
    for item in answer["items"]:
        for op, result in item.items():
            status = int(result.get("status", 200))
            if status < 300 or (op == "delete" and status == 404):
                continue
            error = result.get("error")
            if _permanent(op, error):
                refused.append(
                    Refused(
                        str(result.get("_id")), _reason(status, error), str(result.get("_index"))
                    )
                )
            else:
                passing.append(
                    (op, status, error.get("type") if isinstance(error, dict) else error)
                )
    if passing:
        raise IndexWriteError(f"{len(passing)} of the batch's writes were refused: {passing[:3]}")
    return refused


def refused_index(alias: str) -> str:
    """The deployment's record of the documents set aside (ADR-150 decision 2), outside the alias
    so no search reads it; the drift check reports it, and a later write or delete of the same
    document removes its record."""
    return f"{alias}-refused"


_REFUSED_BODY: dict[str, Any] = {
    "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
    "mappings": {
        "dynamic": "strict",
        "properties": {
            "doc_id": {"type": "keyword"},
            "reason": {"type": "keyword", "index": False, "doc_values": False},
            "at": {"type": "date"},
        },
    },
}


async def record_refused(client: AsyncOpenSearch, alias: str, refused: Sequence[Refused]) -> None:
    """Each refused document's record, and an error in the log naming it (never silent, rule 2)."""
    if not refused:
        return
    index = refused_index(alias)
    if not await client.indices.exists(index=index):
        await client.indices.create(index=index, body=_REFUSED_BODY)
    at = datetime.now(UTC).isoformat()
    for r in refused:
        log.error("search index: %s set aside, refused for good: %s", r.doc_id, r.reason)
        await client.index(
            index=index, id=r.doc_id, body={"doc_id": r.doc_id, "reason": r.reason, "at": at}
        )


async def clear_refused(client: AsyncOpenSearch, alias: str, doc_ids: Sequence[str]) -> None:
    """The records of documents now written or deleted: a record names only what is still set
    aside."""
    index = refused_index(alias)
    if not doc_ids or not await client.indices.exists(index=index):
        return
    requests, _ = _requests(client, [{"delete": {"_index": index, "_id": d}} for d in doc_ids])
    for request in requests:
        await _write_one(client, request)


async def ensure_index(client: AsyncOpenSearch, alias: str) -> None:
    """The alias's index, made with the mapping if there is none yet (a first start); the rebuild
    replaces it under the alias."""
    if await client.indices.exists_alias(name=alias):
        return
    index = f"{alias}-initial"
    if not await client.indices.exists(index=index):
        await client.indices.create(index=index, body=index_body())
    await client.indices.put_alias(index=index, name=alias)


def building_alias(alias: str) -> str:
    """The alias a rebuild's new index holds until it is complete (ADR-150 decision 4)."""
    return f"{alias}-building"


class SearchIndexer:
    def __init__(
        self,
        source: IndexFeedSource,
        texts: TextFeedSource,
        client: AsyncOpenSearch,
        alias: str,
        schema: OntologySchema,
        *,
        batch: int = 500,
    ) -> None:
        self._source = source
        self._texts = texts
        self._client = client
        self._alias = alias
        self._schema = schema
        self._batch = batch

    @property
    def client(self) -> AsyncOpenSearch:
        return self._client

    @property
    def alias(self) -> str:
        return self._alias

    async def index_nodes(self, node_ids: Sequence[str], *, index: str | None = None) -> None:
        """These nodes' documents as the graph and the texts hold them now."""
        nodes = await self._source.nodes_for_index(node_ids)
        texts = await self._texts.texts_for_index(list(node_ids))
        targets = [index] if index else [self._alias]
        # While a rebuild fills its new index (`building_alias`), each change goes there too, so
        # a node changed after the rebuild read it is not left at its older state when the alias
        # moves.
        if index is None and await self._client.indices.exists_alias(
            name=building_alias(self._alias)
        ):
            targets.append(building_alias(self._alias))
        refused: dict[str, Refused] = {}
        sent: set[str] = set()
        for target in targets:
            body = actions_for(
                target, node_ids, nodes, texts, self._schema, require_alias=index is None
            )
            sent |= {
                str(meta["_id"])
                for line in body
                for op, meta in line.items()
                if op in ("index", "delete")
            }
            refused.update((r.doc_id, r) for r in await write_actions(self._client, body))
        await record_refused(self._client, self._alias, list(refused.values()))
        await clear_refused(self._client, self._alias, sorted(sent - set(refused)))

    async def drain_once(self) -> int:
        """One batch of each outbox; the number of outbox rows it cleared."""
        rows = await self._source.pending_index(self._batch)
        text_rows = await self._texts.pending_text_index(self._batch)
        if not rows and not text_rows:
            return 0
        ids = [r.node_id for r in rows] + [document_id for _, document_id in text_rows]
        await self.index_nodes(ids)
        if rows:
            await self._source.clear_pending_index([r.ref for r in rows])
        if text_rows:
            await self._texts.clear_pending_text_index([ref for ref, _ in text_rows])
        return len(rows) + len(text_rows)
