"""ADR-150 decisions 2, 4 and 5, offline: a document OpenSearch refuses for good never holds the
outbox behind it. It is set aside (recorded in the deployment's refused index, an error logged), the
rest of the batch is written and the outbox cleared, and the drift check reports it as refused, not
missing; a passing refusal (a 429) is raised and the batch kept. A rebuild that fails leaves no index
behind, a rebuild finds and removes one a crashed rebuild left, and a rebuild that completes keeps
only its own refusal records. A name over Lucene's term limit is indexed (`ignore_above`), never
refused; an access field over it is refused, and the older document deleted (it fails closed). A
refusal by the cluster's own state, whatever its status, is raised; a refused delete is never set
aside; a write to a missing alias never makes an index of its name; one rebuild at a time.

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
    MappingOutOfDate,
    SearchIndexer,
    building_alias,
    ensure_index,
    refused_index,
    write_actions,
)
from services.search_index.mapping import index_body
from services.search_index.rebuild import RebuildRunning, drift, rebuild, rebuild_lock
from tests.services.search_index.fake_opensearch import FakeOpenSearch
from tests.services.search_index.test_document import _node

SCHEMA = load_default_ontology()
CAP = 4096
ALIAS = "a"


def _person(node_id: str, family_name: str, datasets: Sequence[str] = ("ds-1",)) -> Node:
    node = _node("Person", {"family_name": family_name, "given_names": "Ada"}, list(datasets))
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
    # Its type and the field, never the value OpenSearch's reason quotes.
    assert refused[0].reason == (
        "400 strict_dynamic_mapping_exception in a field the mapping does not hold"
    )
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


async def test_a_refused_update_deletes_the_older_version_so_it_fails_closed() -> None:
    """A node indexed, then changed so its document is refused (here an access field over Lucene's
    term limit, which no `ignore_above` hides): its older document, with its older access fields,
    is deleted, never left searchable; the drift check reports it refused."""
    client, graph, indexer = await _setup([_person("p-1", "Lovelace")], limit=1024 * 1024)
    await indexer.drain_once()
    assert "p-1" in _indexed(client)
    graph.nodes["p-1"] = _person("p-1", "Lovelace", datasets=["d" * 40000])
    graph.pending = ["p-1"]
    assert await indexer.drain_once() == 1
    assert "p-1" not in _indexed(client)
    record = client.docs[refused_index(ALIAS)]["p-1"]
    assert record["reason"] == (
        "400 illegal_argument_exception / max_bytes_length_exceeded_exception in field datasets"
    )
    assert "ddd" not in str(record)
    report = await drift(graph, _Texts(), client, ALIAS, SCHEMA)  # type: ignore[arg-type]
    assert list(report.refused) == ["p-1"]


@pytest.mark.parametrize("state", ["blocked", "closed", "busy", "flood_stage"])
async def test_the_clusters_own_refusal_is_raised_whatever_its_status(state: str) -> None:
    """A write block's 403, a closed index's 400, a 429, the flood-stage block that refuses writes
    and lets deletes through: the cluster's state, not the document's. Raised, the outbox kept,
    nothing set aside; once the cluster takes writes again, the document is indexed."""
    client, graph, indexer = await _setup([_person("p-1", "Lovelace")])
    await indexer.drain_once()
    graph.pending = ["p-1"]
    if state == "closed":
        client.closed = set(client.resolve(ALIAS))
    else:
        setattr(client, state, True)
    with pytest.raises(IndexWriteError):
        await indexer.drain_once()
    assert graph.pending == ["p-1"]
    assert not await client.indices.exists(index=refused_index(ALIAS))
    # A lasting block that still takes deletes (the flood stage): the older version is deleted, so a
    # narrowing change is never left unapplied while the block lasts; any other: left as it is.
    assert ("p-1" in _indexed(client)) is (state != "flood_stage")
    client.closed, client.blocked, client.busy, client.flood_stage = set(), False, False, False
    assert await indexer.drain_once() == 1 and "p-1" in _indexed(client)


async def test_a_refused_delete_is_raised_never_set_aside() -> None:
    """A node no longer live whose delete is refused (a write block): never cleared from the
    outbox, so its document cannot stay searchable unsaid."""
    client, graph, indexer = await _setup([_person("p-1", "Lovelace")])
    await indexer.drain_once()
    del graph.nodes["p-1"]
    graph.pending = ["p-1"]
    client.blocked = True
    with pytest.raises(IndexWriteError):
        await indexer.drain_once()
    assert graph.pending == ["p-1"] and "p-1" in _indexed(client)


async def test_an_alias_over_two_indexes_is_raised_not_set_aside() -> None:
    client, graph, indexer = await _setup([_person("p-1", "Lovelace")])
    await client.indices.create(index="a-second", body=index_body())
    await client.indices.put_alias(index="a-second", name=ALIAS)
    with pytest.raises(IndexWriteError, match="illegal_argument_exception"):
        await indexer.drain_once()
    assert graph.pending == ["p-1"]


async def test_a_write_to_a_missing_alias_makes_no_index_of_its_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`require_alias`: the alias gone, the write is refused and raised; no unmapped index named
    after the alias appears in its place. The mapping check, which would also stop it, is stepped
    past, so this holds `require_alias` itself (the alias can go between the check and the write)."""
    client, graph, indexer = await _setup([_person("p-1", "Lovelace")])
    monkeypatch.setattr(indexer_module, "check_mapping", _no_check)
    await client.indices.delete(index="a-initial")
    with pytest.raises(IndexWriteError):
        await indexer.drain_once()
    assert ALIAS not in client.docs and graph.pending == ["p-1"]


async def test_a_record_is_removed_once_its_document_is_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(indexer_module, "MAX_BULK_BYTES", CAP)
    client, graph, indexer = await _setup([_person("p-1", "x" * CAP)])
    await indexer.drain_once()
    assert set(client.docs[refused_index(ALIAS)]) == {"p-1"}
    graph.nodes["p-1"] = _person("p-1", "Lovelace")
    graph.pending = ["p-1"]
    await indexer.drain_once()
    assert client.docs[refused_index(ALIAS)] == {} and "p-1" in _indexed(client)


async def test_one_rebuild_at_a_time() -> None:
    client, graph, indexer = await _setup([_person("p-1", "Lovelace")])
    await client.indices.create(index=rebuild_lock(ALIAS), body={})
    with pytest.raises(RebuildRunning, match="already running"):
        await rebuild(graph, _Texts(), client, ALIAS, SCHEMA)  # type: ignore[arg-type]
    await client.indices.delete(index=rebuild_lock(ALIAS))
    await rebuild(graph, _Texts(), client, ALIAS, SCHEMA)  # type: ignore[arg-type]
    assert not await client.indices.exists(index=rebuild_lock(ALIAS))


async def test_a_delete_to_an_index_that_is_gone_is_raised_not_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The building alias read as there, then moved by the rebuild's swap before the delete reaches
    it: an `index_not_found_exception` 404 is not "already gone", so the withdrawn node's outbox
    row is kept and the delete is sent again to wherever the alias now points."""
    client, graph, indexer = await _setup([_person("p-1", "Lovelace")])
    await indexer.drain_once()
    del graph.nodes["p-1"]
    graph.pending = ["p-1"]
    real = client.indices.exists_alias

    async def building_seen(*, name: str) -> bool:
        return True if name == building_alias(ALIAS) else await real(name=name)

    monkeypatch.setattr(client.indices, "exists_alias", building_seen)
    monkeypatch.setattr(indexer_module, "check_mapping", _no_check)
    with pytest.raises(IndexWriteError, match="index_not_found_exception"):
        await indexer.drain_once()
    assert graph.pending == ["p-1"]


async def _no_check(client: Any, target: str) -> None:
    return None


async def test_an_index_made_for_another_mapping_is_never_written() -> None:
    """An upgrade that changed the mapping, not yet rebuilt (or an older replica in a rolling one):
    nothing is set aside or deleted, the outbox is kept, and a rebuild is asked for in words."""
    client = FakeOpenSearch()
    old = index_body()
    old["mappings"] = {**old["mappings"], "_meta": {"mapping_fingerprint": "an-older-mapping"}}
    await client.indices.create(index="a-old", body=old)
    await client.indices.put_alias(index="a-old", name=ALIAS)
    graph = _Graph([_person("p-1", "Lovelace")])
    indexer = SearchIndexer(graph, _Texts(), client, ALIAS, SCHEMA)  # type: ignore[arg-type]
    with pytest.raises(MappingOutOfDate, match="rebuild_search_index"):
        await ensure_index(client, ALIAS)  # type: ignore[arg-type]
    with pytest.raises(MappingOutOfDate):
        await indexer.drain_once()
    assert graph.pending == ["p-1"] and client.docs["a-old"] == {}
    assert not await client.indices.exists(index=refused_index(ALIAS))
    built = await rebuild(graph, _Texts(), client, ALIAS, SCHEMA)  # type: ignore[arg-type]
    assert client.resolve(ALIAS) == [built.index]
    assert await indexer.drain_once() == 1


@pytest.mark.parametrize(
    ("reason", "said"),
    [
        ("failed to parse field [date] of type [date] in document with id 'p-1'. Preview of "
         "field's value: 'Ada Lovelace 1815'", "400 mapper_parsing_exception in field date"),
        ("mapping set to strict, dynamic introduction of [x] within [_doc] is not allowed. "
         "Preview of field's value: '[secret value]'",
         "400 mapper_parsing_exception in a field the mapping does not hold"),
        ("Document contains at least one immense term in field=\"names\" (whose UTF8 encoding "
         "is longer than the max length 32766), all of which were skipped. The prefix of the "
         "first immense term is: '[Ada field [Lovelace]...'", "400 mapper_parsing_exception in field names"),
        ("the value 'field [Lovelace]' could not be read",
         "400 mapper_parsing_exception in a field the mapping does not hold"),
        ("no field named in it at all: 'Ada Lovelace'", "400 mapper_parsing_exception"),
    ],
)  # fmt: skip
def test_the_reason_keeps_the_type_and_field_never_the_value(reason: str, said: str) -> None:
    """The field is the first `field [..]`, `field="..."` or `introduction of [..]`, kept only when
    it is one of the mapping's own fields: a value shaped like a field name (the fourth case) is
    never copied out."""
    got = indexer_module._reason(400, {"type": "mapper_parsing_exception", "reason": reason})
    assert got == said
    assert not any(w in got for w in ("Ada", "secret", "1815", "Lovelace"))
