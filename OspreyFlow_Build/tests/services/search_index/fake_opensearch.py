"""An OpenSearch stand-in for the feed's offline tests (ADR-150 decisions 2, 4 and 5), at the client's
own surface (`AsyncOpenSearch`'s methods the indexer, the rebuild and the drift check call).

It keeps documents by index, resolves aliases, and refuses what OpenSearch refuses (rule 15: the
refusals, not only the grants):
- a `_bulk` body over `limit` bytes, as the client's `_bulk_body` encodes it, with a 413 for the
  whole request (`http.max_content_length`);
- an item whose document names a field a `dynamic: strict` mapping does not hold, with a 400
  `strict_dynamic_mapping_exception`;
- an item whose keyword value is over Lucene's 32,766-byte term, unless the field's `ignore_above`
  leaves it unindexed, with a 400 `illegal_argument_exception` ("immense term") caused by
  `max_bytes_length_exceeded_exception`, the shape OpenSearch answers;
- a write to an alias over two indexes with no write index, with a 400 `illegal_argument_exception`;
- every item with a 429 while `busy` is set, a 403 `cluster_block_exception` while `blocked` is
  set (a write block, an ISM read-only state), a 429 `cluster_block_exception` for a write but not
  a delete while `flood_stage` is set (`read_only_allow_delete`), and a 400
  `index_closed_exception` for an index in `closed` (each the cluster's state, not the document's);
- a write saying `require_alias` to a name that is no alias, with a 404 `index_not_found_exception`.
A write to an index that is not there otherwise makes it, unmapped, as `action.auto_create_index`
does; a delete there is a 404 and makes nothing. A refusal's reason quotes the value, as OpenSearch's does ("Preview of field's value").
It does not prove what a real cluster's analysers make of a document: `test_feed_live.py`'s.
"""

from __future__ import annotations

import heapq
import json
from typing import Any

from opensearchpy import NotFoundError, TransportError
from opensearchpy.client.utils import _bulk_body
from opensearchpy.serializer import JSONSerializer

#: Lucene's longest indexed term, in bytes.
MAX_TERM_BYTES = 32766


class _Indices:
    def __init__(self, store: FakeOpenSearch) -> None:
        self._s = store

    async def exists_alias(self, *, name: str) -> bool:
        return any(name in names for names in self._s.aliases.values())

    async def exists(self, *, index: str) -> bool:
        return index in self._s.docs

    async def create(self, *, index: str, body: Any) -> None:
        if index in self._s.docs:
            raise TransportError(400, "resource_already_exists_exception", {})
        self._s.docs[index] = {}
        self._s.aliases[index] = set()
        self._s.mappings[index] = (body or {}).get("mappings", {})

    async def delete(self, *, index: str, ignore_unavailable: bool = False) -> None:
        if index not in self._s.docs:
            if ignore_unavailable:
                return
            raise NotFoundError(404, "index_not_found_exception", {})
        for table in (self._s.docs, self._s.aliases, self._s.mappings):
            table.pop(index, None)

    async def get_mapping(self, *, index: str) -> dict[str, Any]:
        return {i: {"mappings": self._s.mappings[i]} for i in self._s.resolve(index)}

    async def put_alias(self, *, index: str, name: str) -> None:
        self._s.aliases[index].add(name)

    async def get_alias(self, *, name: str) -> dict[str, Any]:
        found = {i: {} for i, names in self._s.aliases.items() if name in names}
        if not found:
            raise NotFoundError(404, "aliases_not_found_exception", {})
        return found

    async def update_aliases(self, *, body: dict[str, Any]) -> None:
        for action in body["actions"]:
            for op, spec in action.items():
                names = self._s.aliases[spec["index"]]
                if op == "add":
                    names.add(spec["alias"])
                else:
                    names.discard(spec["alias"])

    async def refresh(self, *, index: str) -> None:
        self._s.resolve(index)


class FakeOpenSearch:
    def __init__(self, limit: int = 100 * 1024 * 1024) -> None:
        self.limit = limit
        self.busy = False
        self.blocked = False
        self.flood_stage = False
        self.max_result_window = 10_000
        #: Each sorted page's hits reversed: an order the caller must refuse, not compare.
        self.unordered = False
        self.closed: set[str] = set()
        self.transport = type("T", (), {"serializer": JSONSerializer()})()
        self.docs: dict[str, dict[str, dict[str, Any]]] = {}
        self.aliases: dict[str, set[str]] = {}
        self.mappings: dict[str, dict[str, Any]] = {}
        self.indices = _Indices(self)
        self.requests: list[bytes] = []

    def resolve(self, name: str) -> list[str]:
        if name in self.docs:
            return [name]
        found = [i for i, names in self.aliases.items() if name in names]
        if not found:
            raise NotFoundError(404, "index_not_found_exception", {"index": name})
        return found

    def _refusal(self, index: str, source: dict[str, Any]) -> dict[str, Any] | None:
        properties = self.mappings.get(index, {}).get("properties")
        if properties is None:
            return None
        for name, value in source.items():
            spec = properties.get(name)
            if spec is None:
                if self.mappings[index].get("dynamic") == "strict":
                    return {
                        "type": "strict_dynamic_mapping_exception",
                        "reason": f"mapping set to strict, dynamic introduction of [{name}] within "
                        f"[_doc] is not allowed. Preview of field's value: '{value!s:.30}'",
                    }
                continue
            if spec.get("type") != "keyword":
                continue
            for v in value if isinstance(value, list) else [value]:
                if not isinstance(v, str):
                    continue
                ignored = "ignore_above" in spec and len(v) > spec["ignore_above"]
                if len(v.encode("utf-8", "surrogatepass")) > MAX_TERM_BYTES and not ignored:
                    return {
                        "type": "illegal_argument_exception",
                        "reason": f'Document contains at least one immense term in field="{name}" '
                        f"(whose UTF8 encoding is longer than the max length 32766), all of which "
                        f"were skipped. The prefix of the first immense term is: '{v[:30]}...'",
                        "caused_by": {"type": "max_bytes_length_exceeded_exception"},
                    }
        return None

    async def bulk(self, *, body: Any) -> dict[str, Any]:
        sent = _bulk_body(self.transport.serializer, body)
        sent = sent if isinstance(sent, bytes) else sent.encode("utf-8", "surrogatepass")
        if len(sent) > self.limit:
            raise TransportError(413, "Request Entity Too Large", {})
        self.requests.append(sent)
        lines = [json.loads(line) for line in sent.decode("utf-8", "surrogatepass").splitlines()]
        items: list[dict[str, Any]] = []
        i = 0
        while i < len(lines):
            ((op, meta),) = lines[i].items()
            source = lines[i + 1] if op == "index" else None
            i += 2 if op == "index" else 1
            result: dict[str, Any] = {"_id": meta["_id"], "_index": meta["_index"]}
            items.append({op: result})
            if self.busy:
                result.update(status=429, error={"type": "es_rejected_execution_exception"})
                continue
            if self.blocked:
                result.update(status=403, error={"type": "cluster_block_exception",
                                                 "reason": "index [x] blocked by: [FORBIDDEN/8/index write (api)]"})  # fmt: skip
                continue
            if self.flood_stage and op != "delete":
                # `read_only_allow_delete`, set at the flood-stage disk watermark: deletes pass.
                result.update(status=429, error={"type": "cluster_block_exception",
                                                 "reason": "index [x] blocked by: [TOO_MANY_REQUESTS/12/disk usage exceeded flood-stage watermark, index has read-only-allow-delete block]"})  # fmt: skip
                continue
            if meta.get("require_alias") and not await self.indices.exists_alias(name=meta["_index"]):
                result.update(status=404, error={"type": "index_not_found_exception",
                                                 "reason": "[require_alias] request flag is [true]"})  # fmt: skip
                continue
            try:
                targets = self.resolve(meta["_index"])
            except NotFoundError:
                if op == "delete":
                    result.update(status=404, error={"type": "index_not_found_exception"})
                    continue
                # `action.auto_create_index`, on by default: a write makes the index, unmapped.
                await self.indices.create(index=meta["_index"], body={})
                targets = [meta["_index"]]
            if len(targets) > 1:
                result.update(status=400, error={"type": "illegal_argument_exception",
                                                 "reason": "no write index"})  # fmt: skip
                continue
            if targets[0] in self.closed:
                result.update(status=400, error={"type": "index_closed_exception"})
                continue
            held = self.docs[targets[0]]
            if op == "delete":
                if held.pop(meta["_id"], None) is not None:
                    result.update(status=200, result="deleted")
                else:
                    result.update(status=404, result="not_found")  # no error: done
                continue
            assert source is not None
            refusal = self._refusal(targets[0], source)
            if refusal:
                result.update(status=400, error=refusal)
                continue
            held[meta["_id"]] = source
            result["status"] = 201
        errors = any(r.get("status", 200) >= 300 for item in items for r in item.values())
        return {"errors": errors, "items": items}

    async def index(self, *, index: str, id: str, body: dict[str, Any]) -> None:
        if index not in self.docs:
            await self.indices.create(index=index, body={})
        self.docs[index][id] = body

    async def count(self, *, index: str) -> dict[str, int]:
        return {"count": sum(len(self.docs[i]) for i in self.resolve(index))}

    async def search(
        self, *, index: str, body: Any, size: int, scroll: str | None = None
    ) -> dict[str, Any]:
        """A `term` query on one field (or `match_all`), sorted ascending by one field, at most
        `size` hits after `search_after`, as OpenSearch pages a sorted search; a scroll gives every
        hit at once (the only use left is a test's)."""
        if size > self.max_result_window:
            # `index.max_result_window`, 10,000 by default: a page larger is refused, as OpenSearch
            # refuses it (search_after pages past it; a single page never does).
            raise TransportError(400, "illegal_argument_exception", {"reason": "Result window is too large"})
        if scroll is not None:
            hits = [{"_id": d, "_source": s} for i in self.resolve(index)
                    for d, s in self.docs[i].items()]  # fmt: skip
            return {"_scroll_id": "s", "hits": {"hits": hits}}
        term = (body.get("query") or {}).get("term")
        ((name, value),) = term.items() if term else ((None, None),)
        ((key, _),) = body["sort"][0].items()
        after = (body.get("search_after") or [None])[0]
        # The page alone is built (heapq), so the stand-in's own memory is the page's, as a client's
        # is against a real cluster: a test measuring the caller's memory measures the caller.
        chosen = heapq.nsmallest(
            size,
            (
                (s[key], d, s)
                for i in self.resolve(index)
                for d, s in self.docs[i].items()
                if (name is None or s.get(name) == value) and (after is None or s[key] > after)
            ),
            key=lambda t: t[0],
        )
        if self.unordered:
            chosen.reverse()
        return {"hits": {"hits": [{"_id": d, "_source": s, "sort": [k]} for k, d, s in chosen]}}

    async def mget(self, *, index: str, body: Any) -> dict[str, Any]:
        held = {d: s for i in self.resolve(index) for d, s in self.docs[i].items()}
        return {"docs": [{"_id": d, "found": d in held, **({"_source": held[d]} if d in held else {})}
                         for d in body["ids"]]}  # fmt: skip

    async def scroll(self, *, scroll_id: str, scroll: str) -> dict[str, Any]:
        return {"_scroll_id": scroll_id, "hits": {"hits": []}}

    async def clear_scroll(self, *, scroll_id: str) -> None:
        return None

    async def delete_by_query(self, *, index: str, body: Any, refresh: bool = False) -> None:
        before = body["query"]["range"]["at"]["lt"]
        for i in self.resolve(index):
            self.docs[i] = {d: s for d, s in self.docs[i].items() if s.get("at", "") >= before}
