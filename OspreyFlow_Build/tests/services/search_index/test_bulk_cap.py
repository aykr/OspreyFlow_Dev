"""ADR-150 decision 2, offline: every `_bulk` request the indexer and the rebuild send is at most
`MAX_BULK_BYTES` (10 MiB, the smallest `http.max_content_length` of an Amazon OpenSearch instance),
measured in the bytes the client actually sends, with an action never parted from its document; one
action that alone is over the cap is set aside (returned as refused, the rest sent); and a 413 from
OpenSearch is raised, never swallowed, so the outbox keeps the batch (it is not cleared) and a
rebuild leaves nothing behind.

`FakeOpenSearch` refuses a body over its limit with the 413 OpenSearch answers (rule 15: the fake
models the refusal, not only the grant), serialising the body as the real client's `_bulk_body`
does.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import pytest
from opensearchpy import TransportError

from ontology.loader import load_default_ontology
from ports.index_feed import PendingIndex
from services.search_index import indexer as indexer_module
from services.search_index.indexer import SearchIndexer, building_alias, write_actions
from services.search_index.rebuild import rebuild
from tests.services.search_index.fake_opensearch import FakeOpenSearch

CAP = 4096


def _OpenSearch(limit: int) -> FakeOpenSearch:
    return FakeOpenSearch(limit=limit)


class _Source:
    """The graph's outbox and nodes: every node gone, so each is two deletes (its own and its text's)."""

    def __init__(self, ids: Sequence[str]) -> None:
        self.ids = list(ids)
        self.cleared: list[str] = []

    async def pending_index(self, limit: int) -> list[PendingIndex]:
        return [PendingIndex(ref=f"r{i}", node_id=n) for i, n in enumerate(self.ids[:limit])]

    async def clear_pending_index(self, refs: Sequence[str]) -> None:
        self.cleared += list(refs)

    async def nodes_for_index(self, node_ids: Sequence[str]) -> dict[str, Any]:
        return dict.fromkeys(node_ids)

    async def live_node_ids(self, *, after: str | None, limit: int) -> list[str]:
        start = 0 if after is None else self.ids.index(after) + 1
        return self.ids[start : start + limit]


class _Texts:
    async def pending_text_index(self, limit: int) -> list[tuple[int, str]]:
        return []

    async def clear_pending_text_index(self, refs: Sequence[int]) -> None:
        return None

    async def texts_for_index(self, document_ids: Sequence[str]) -> dict[str, tuple[str, str]]:
        return {}


def _lines(requests: list[bytes]) -> list[dict[str, Any]]:
    return [json.loads(line) for r in requests for line in r.decode().splitlines()]


def _index_pair(i: int, size: int) -> list[dict[str, Any]]:
    return [{"index": {"_index": "a", "_id": f"n{i}"}}, {"name": "x" * size}]


def test_the_cap_is_ten_mib() -> None:
    assert indexer_module.MAX_BULK_BYTES == 10 * 1024 * 1024


async def test_a_batch_over_the_cap_goes_as_several_requests_each_within_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(indexer_module, "MAX_BULK_BYTES", CAP)
    client = _OpenSearch(limit=CAP)
    body = [line for i in range(40) for line in _index_pair(i, 300)]
    body.append({"delete": {"_index": "a", "_id": "gone"}})
    await write_actions(client, body)  # type: ignore[arg-type]
    assert len(client.requests) > 1
    assert all(len(r) <= CAP for r in client.requests)
    assert _lines(client.requests) == body
    # An action is never parted from its document: each request starts with an action line.
    for r in client.requests:
        first = json.loads(r.decode().splitlines()[0])
        assert set(first) <= {"index", "delete"}
        assert all(len(json.loads(line)) for line in r.decode().splitlines())


async def test_a_batch_within_the_cap_is_one_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(indexer_module, "MAX_BULK_BYTES", CAP)
    client = _OpenSearch(limit=CAP)
    body = [line for i in range(3) for line in _index_pair(i, 100)]
    await write_actions(client, body)  # type: ignore[arg-type]
    assert len(client.requests) == 1 and _lines(client.requests) == body


async def test_the_cap_counts_bytes_not_characters(monkeypatch: pytest.MonkeyPatch) -> None:
    """A name in a script of three bytes a character: measured as characters, it fits; sent, it
    does not."""
    monkeypatch.setattr(indexer_module, "MAX_BULK_BYTES", CAP)
    client = _OpenSearch(limit=CAP)
    body = [line for i in range(6) for line in _index_pair(i, 0)]
    for i in range(1, len(body), 2):
        body[i] = {"name": "中" * 300}
    await write_actions(client, body)  # type: ignore[arg-type]
    assert all(len(r) <= CAP for r in client.requests)
    assert _lines(client.requests) == body


async def test_one_action_alone_over_the_cap_is_set_aside_and_the_rest_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It can never be sent: returned as refused, never dropped unsaid, and it holds nothing else
    back (the indexer records it, `test_refused.py`)."""
    monkeypatch.setattr(indexer_module, "MAX_BULK_BYTES", CAP)
    client = _OpenSearch(limit=CAP)
    body = _index_pair(0, 10) + _index_pair(1, CAP) + _index_pair(2, 10)
    refused = await write_actions(client, body)  # type: ignore[arg-type]
    assert [r.doc_id for r in refused] == ["n1"] and "over the" in refused[0].reason
    # The rest sent; then whatever the index held for n1 deleted (it fails closed).
    assert _lines(client.requests) == body[:2] + body[4:] + [{"delete": {"_index": "a", "_id": "n1"}}]


async def test_a_413_is_raised_and_the_outbox_keeps_the_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenSearch's limit below the cap (a smaller domain than assumed): the 413 reaches the
    caller and the outbox rows stay to be sent again."""
    monkeypatch.setattr(indexer_module, "MAX_BULK_BYTES", CAP)
    client = _OpenSearch(limit=CAP // 4)
    source = _Source([f"node-{i:04d}" for i in range(60)])
    indexer = SearchIndexer(source, _Texts(), client, "a", load_default_ontology())  # type: ignore[arg-type]
    await client.indices.create(index="a-initial", body={})
    await client.indices.put_alias(index="a-initial", name="a")
    with pytest.raises(TransportError) as raised:
        await indexer.drain_once()
    assert raised.value.status_code == 413
    assert source.cleared == []


async def test_the_indexer_drains_a_batch_over_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(indexer_module, "MAX_BULK_BYTES", CAP)
    client = _OpenSearch(limit=CAP)
    source = _Source([f"node-{i:04d}" for i in range(200)])
    indexer = SearchIndexer(source, _Texts(), client, "a", load_default_ontology())  # type: ignore[arg-type]
    await client.indices.create(index="a-initial", body={})
    await client.indices.put_alias(index="a-initial", name="a")
    assert await indexer.drain_once() == 200
    assert len(client.requests) > 1 and all(len(r) <= CAP for r in client.requests)
    assert len(source.cleared) == 200


async def test_the_rebuild_sends_within_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(indexer_module, "MAX_BULK_BYTES", CAP)
    client = _OpenSearch(limit=CAP)
    source = _Source([f"node-{i:04d}" for i in range(300)])
    built = await rebuild(source, _Texts(), client, "a", load_default_ontology(), page=300)  # type: ignore[arg-type]
    assert built.nodes == 300
    assert len(client.requests) > 1 and all(len(r) <= CAP for r in client.requests)
    assert "a" in client.aliases[built.index]


async def test_a_413_in_the_rebuild_is_raised_and_leaves_nothing_behind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(indexer_module, "MAX_BULK_BYTES", CAP)
    client = _OpenSearch(limit=CAP // 4)
    await client.indices.create(index="a-initial", body={})
    await client.indices.put_alias(index="a-initial", name="a")
    source = _Source([f"node-{i:04d}" for i in range(300)])
    with pytest.raises(TransportError) as raised:
        await rebuild(source, _Texts(), client, "a", load_default_ontology(), page=300)  # type: ignore[arg-type]
    assert raised.value.status_code == 413
    assert (await client.indices.get_alias(name="a")) == {"a-initial": {}}
    # Its own index is deleted, and the building alias with it: no change goes to a stray index.
    assert set(client.docs) == {"a-initial"}
    assert not await client.indices.exists_alias(name=building_alias("a"))


async def test_a_lone_surrogate_is_measured_as_the_client_sends_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """opensearch-py's transport encodes with `surrogatepass`; so does the cap's measure, and a
    property holding a lone surrogate is sent, not raised before it is (which would hold the
    outbox)."""
    monkeypatch.setattr(indexer_module, "MAX_BULK_BYTES", CAP)
    client = _OpenSearch(limit=CAP)
    body = [{"index": {"_index": "a", "_id": "n0"}}, {"name": "x\ud800y"}]
    assert await write_actions(client, body) == []  # type: ignore[arg-type]
    assert len(client.requests) == 1
