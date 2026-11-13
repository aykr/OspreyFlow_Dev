"""An OpenSearch stand-in for the feed's offline tests (ADR-150 decisions 2, 4 and 5), at the client's
own surface (`AsyncOpenSearch`'s methods the indexer, the rebuild and the drift check call).

It keeps documents by index, resolves aliases, and refuses what OpenSearch refuses (rule 15: the
refusals, not only the grants):
- a `_bulk` body over `limit` bytes, as the client's `_bulk_body` encodes it, with a 413 for the
  whole request (`http.max_content_length`);
- an item whose document names a field a `dynamic: strict` mapping does not hold, with a 400
  `strict_dynamic_mapping_exception`;
- an item whose keyword value is over Lucene's 32,766-byte term, unless the field's `ignore_above`
  leaves it unindexed, with a 400 `max_bytes_length_exceeded_exception`;
- a write to an alias over two indexes with no write index, with a 400 `illegal_argument_exception`;
- every item with a 429 while `busy` is set (a passing refusal).
A write to an index that is not there makes it, unmapped, as `action.auto_create_index` does.
It does not prove what a real cluster's analysers make of a document: `test_feed_live.py`'s.
"""

from __future__ import annotations

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
                    return {"type": "strict_dynamic_mapping_exception", "reason": name}
                continue
            if spec.get("type") != "keyword":
                continue
            for v in value if isinstance(value, list) else [value]:
                if not isinstance(v, str):
                    continue
                ignored = "ignore_above" in spec and len(v) > spec["ignore_above"]
                if len(v.encode("utf-8", "surrogatepass")) > MAX_TERM_BYTES and not ignored:
                    return {"type": "max_bytes_length_exceeded_exception", "reason": name}
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
            try:
                targets = self.resolve(meta["_index"])
            except NotFoundError:
                # `action.auto_create_index`, on by default: a write makes the index, unmapped.
                await self.indices.create(index=meta["_index"], body={})
                targets = [meta["_index"]]
            if len(targets) > 1:
                result.update(status=400, error={"type": "illegal_argument_exception",
                                                 "reason": "no write index"})  # fmt: skip
                continue
            held = self.docs[targets[0]]
            if op == "delete":
                result["status"] = 200 if held.pop(meta["_id"], None) is not None else 404
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

    async def search(self, *, index: str, body: Any, scroll: str, size: int) -> dict[str, Any]:
        hits = [{"_id": d, "_source": s} for i in self.resolve(index) for d, s in self.docs[i].items()]
        return {"_scroll_id": "s", "hits": {"hits": hits}}

    async def scroll(self, *, scroll_id: str, scroll: str) -> dict[str, Any]:
        return {"_scroll_id": scroll_id, "hits": {"hits": []}}

    async def clear_scroll(self, *, scroll_id: str) -> None:
        return None

    async def delete_by_query(self, *, index: str, body: Any, refresh: bool = False) -> None:
        before = body["query"]["range"]["at"]["lt"]
        for i in self.resolve(index):
            self.docs[i] = {d: s for d, s in self.docs[i].items() if s.get("at", "") >= before}
