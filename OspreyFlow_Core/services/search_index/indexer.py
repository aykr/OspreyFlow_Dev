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

from opensearchpy import AsyncOpenSearch, NotFoundError

from ports.index_feed import IndexFeedSource
from schemas.domain import Node, OntologySchema

from .document import node_document, text_document, text_document_id
from .mapping import MAPPING, MAPPING_FINGERPRINT, index_body

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


def _mapped(properties: dict[str, Any], prefix: str = "") -> set[str]:
    out: set[str] = set()
    for name, spec in properties.items():
        out.add(prefix + name)
        out |= _mapped(spec.get("fields", {}), f"{prefix}{name}.")
    return out


_MAPPED_FIELDS = frozenset(_mapped(MAPPING["properties"]))


def _reason(status: int, error: dict[str, Any]) -> str:
    """The refusal's type and the field it names, never its words: OpenSearch's reason quotes the
    value (a preview of the field, a term's bytes), which is a record's content."""
    kinds = [str(error.get("type"))]
    caused = error.get("caused_by")
    if isinstance(caused, dict) and caused.get("type"):
        kinds.append(str(caused["type"]))
    found = _FIELD.search(str(error.get("reason", "")))
    field = next((g for g in found.groups() if g), None) if found else None
    if field is None:
        return f"{status} {' / '.join(kinds)}"
    # Kept only when it is one of the mapping's own fields: a value shaped like a field name, or a
    # field the mapping does not hold, is never copied out.
    named = field if field in _MAPPED_FIELDS else "a field the mapping does not hold"
    return f"{status} {' / '.join(kinds)} in {'field ' if named == field else ''}{named}"


#: A refusal by a block the cluster keeps until someone lifts it (a write block, an ISM read-only
#: state, the flood-stage watermark, a security refusal): unlike a 429's rejection, no retry soon
#: ends it, so the document's older version is deleted where the cluster still takes deletes.
_LASTING = frozenset({"cluster_block_exception", "security_exception"})


@dataclass(frozen=True)
class _Passing:
    op: str
    status: int
    kind: str
    doc_id: str
    index: str


async def write_actions(client: AsyncOpenSearch, body: list[dict[str, Any]]) -> list[Refused]:
    """The body in requests of at most `MAX_BULK_BYTES`; a delete of a document that is not there
    (`not_found`, no error) is done. A document refused for good (over the cap alone, or refused
    for its own content) is returned for the caller to record, and whatever that index already held
    for it is deleted in the same pass, so an older version never stays searchable with older
    access fields (it fails closed). Any other refusal is raised, a 413 for the whole request too
    (never swallowed), so the caller clears nothing of the batch and sends it again; a write refused
    by a lasting block first has its older version deleted, where the cluster still takes deletes,
    so a narrowing change is never left unapplied while the block lasts."""
    if not body:
        return []
    requests, refused = _requests(client, body)
    passing: list[_Passing] = []
    for request in requests:
        done, still = await _write_one(client, request)
        refused += done
        passing += still
    if refused:
        removal = [{"delete": {"_index": r.index, "_id": r.doc_id}} for r in refused]
        for request in _requests(client, removal)[0]:
            if any(await _write_one(client, request)):
                raise IndexWriteError("a refused document's older version could not be deleted")
    if passing:
        lasting = [p for p in passing if p.op != "delete" and p.kind in _LASTING]
        if lasting:
            removal = [{"delete": {"_index": p.index, "_id": p.doc_id}} for p in lasting]
            for request in _requests(client, removal)[0]:
                await _write_one(client, request)  # where deletes are refused too, nothing more
        said = [(p.op, p.status, p.kind) for p in passing[:3]]
        raise IndexWriteError(f"{len(passing)} of the batch's writes were refused: {said}")
    return refused


async def _write_one(client: AsyncOpenSearch, request: str) -> tuple[list[Refused], list[_Passing]]:
    answer = await client.bulk(body=request)
    if not answer.get("errors"):
        return [], []
    refused: list[Refused] = []
    passing: list[_Passing] = []
    for item in answer["items"]:
        for op, result in item.items():
            status = int(result.get("status", 200))
            error = result.get("error")
            # A delete of a document that is not there is done; one whose index is not there (an
            # alias moved or gone between reading it and writing) is not: its document may be
            # wherever the alias now points.
            if status < 300 or (op == "delete" and status == 404 and error is None):
                continue
            doc_id, index = str(result.get("_id")), str(result.get("_index"))
            if _permanent(op, error):
                refused.append(Refused(doc_id, _reason(status, error), index))
            else:
                kind = str(error.get("type")) if isinstance(error, dict) else str(error)
                passing.append(_Passing(op, status, kind, doc_id, index))
    return refused, passing


class MappingOutOfDate(IndexWriteError):
    """The index was made for another mapping than this code's (`mapping.MAPPING_FINGERPRINT`):
    nothing is written to it, the outbox is kept, and a rebuild is needed."""


async def check_mapping(client: AsyncOpenSearch, target: str) -> None:
    """Every index behind `target` made for this code's mapping, or `MappingOutOfDate`."""
    try:
        found = await client.indices.get_mapping(index=target)
    except NotFoundError as e:
        raise IndexWriteError(f"the search index {target} is not there: nothing is written") from e
    for index, held in found.items():
        meta = (held.get("mappings") or {}).get("_meta") or {}
        if meta.get("mapping_fingerprint") != MAPPING_FINGERPRINT:
            raise MappingOutOfDate(
                f"the search index {index} was made for another mapping than this version's: "
                "nothing is written to it until python -m scripts.rebuild_search_index rebuilds it"
            )


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
        await _write_one(client, request)  # a record left behind is reported, never harmful


async def ensure_index(client: AsyncOpenSearch, alias: str) -> None:
    """The alias's index, made with the mapping if there is none yet (a first start); the rebuild
    replaces it under the alias. An existing one made for another mapping is `MappingOutOfDate`."""
    if await client.indices.exists_alias(name=alias):
        await check_mapping(client, alias)
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
        if index is None:
            for target in targets:
                try:
                    await check_mapping(self._client, target)
                except MappingOutOfDate:
                    await self._withdraw_all(target, node_ids)
                    raise
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

    async def _withdraw_all(self, target: str, node_ids: Sequence[str]) -> None:
        """An index made for another mapping is never written, but a delete does not depend on the
        mapping: every document of the batch is deleted from it, so a node withdrawn, reverted or
        narrowed in place is missing from search until the rebuild, never left at its older facts.
        Best effort: where the cluster refuses the deletes too, the outbox still holds the batch."""
        body: list[dict[str, Any]] = []
        for node_id in dict.fromkeys(node_ids):
            body.append({"delete": {"_index": target, "_id": node_id}})
            body.append({"delete": {"_index": target, "_id": text_document_id(node_id)}})
        try:
            await write_actions(self._client, body)
        except IndexWriteError:
            log.exception("search index: the batch's deletes from %s were refused too", target)

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
