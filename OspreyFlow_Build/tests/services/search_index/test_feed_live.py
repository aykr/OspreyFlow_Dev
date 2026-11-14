"""ADR-150 decisions 1 to 6, live: each event type written through the graph adapter's real method
reaches OpenSearch through the outbox and the indexer, a Document's text reaches it through its own
outbox, and the drift check finds each kind of difference the rebuild then mends.

Needs a lease: ArcadeDB, Postgres and OpenSearch of the leased stack, its ports pinned
(`stack_lease.sh remote`). Each case has its own ArcadeDB database and its own index alias, removed
after it, and sees only its own documents' rows of the shared text outbox (`CaseTexts`), removing
those alone.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from opensearchpy import AsyncOpenSearch, NotFoundError

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_edge_id, new_node_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    EdgeWrite,
    Handling,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from services.api.config import PostgresConfig
from services.api.review import ExtractionCandidateStore
from services.search_index.client import SearchIndexConfig, search_client
from services.search_index.indexer import SearchIndexer, building_alias, ensure_index
from services.search_index.rebuild import drift, rebuild

pytestmark = pytest.mark.store

ONTOLOGY = load_default_ontology()
WHEN = datetime(2026, 1, 1, tzinfo=UTC)
SOURCE = SourceRef(document_id="files/people.csv", locator="row 1", excerpt_hash="f" * 64)
PROVENANCE = Provenance(state=ProvenanceState.ASSERTED, sources=[SOURCE], first_seen=WHEN)
HANDLING = Handling(classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1")
DATASET = "Z3001ZZ"
WRITER = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-5")


class CaseTexts:
    """The real text store, its outbox seen only for this case's own documents: the shared
    Postgres's other rows (another case's, another test's) are neither drained nor removed. Every
    read and write is the store's own method; only the case's own rows are kept from it."""

    def __init__(self, store: ExtractionCandidateStore) -> None:
        self.store = store
        self.documents: set[str] = set()

    async def store_document_text(self, document_id: str, text: str, principal: Principal) -> None:
        self.documents.add(document_id)
        await self.store.store_document_text(document_id, text, principal)

    async def pending_text_index(self, limit: int) -> list[tuple[int, str]]:
        # The store's own read (rule 4: the read the indexer runs is the one tested), then this
        # case's rows of it; read deep enough that other cases' rows ahead never hide its own.
        rows = await self.store.pending_text_index(limit + 10_000)
        return [r for r in rows if r[1] in self.documents][:limit]

    async def clear_pending_text_index(self, refs: Sequence[int]) -> None:
        await self.store.clear_pending_text_index(refs)

    async def texts_for_index(self, document_ids: Sequence[str]) -> dict[str, tuple[str, str]]:
        return await self.store.texts_for_index(document_ids)

    async def remove_own(self) -> None:
        async with self.store._pool.acquire() as conn:  # noqa: SLF001
            await conn.execute(
                "DELETE FROM search_text_pending WHERE document_id = ANY($1)", sorted(self.documents)
            )


@dataclass
class World:
    graph: GraphArcadeDBAdapter
    texts: CaseTexts
    client: AsyncOpenSearch
    alias: str
    indexer: SearchIndexer

    async def drain(self) -> None:
        while await self.indexer.drain_once():
            pass
        await self.client.indices.refresh(index=self.alias)

    async def doc(self, doc_id: str) -> dict | None:
        try:
            return (await self.client.get(index=self.alias, id=doc_id))["_source"]
        except NotFoundError:
            return None


@pytest.fixture
async def world() -> AsyncIterator[World]:
    alias = f"test-feed-{uuid.uuid4().hex[:10]}"
    client = search_client(SearchIndexConfig.from_env({**os.environ, "OSPREY_SEARCH_INDEX_ALIAS": alias}))
    store = await ExtractionCandidateStore.connect(PostgresConfig.from_env().dsn)
    texts = CaseTexts(store)
    try:
        async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
            indexer = SearchIndexer(graph, texts, client, alias, ONTOLOGY)
            await ensure_index(client, alias)
            yield World(graph, texts, client, alias, indexer)
    finally:
        await texts.remove_own()
        await client.indices.delete(index=f"{alias}*", ignore_unavailable=True)
        await client.close()
        await store.close()


def _person(family_name: str, datasets: Sequence[str] = (DATASET,)) -> NodeWrite:
    return NodeWrite(
        id=new_node_id(), type="Person", properties={"family_name": family_name},
        provenance=PROVENANCE, handling=HANDLING, created_by="loader-1", created_at=WHEN,
        datasets=list(datasets),
    )  # fmt: skip


async def _written(graph: GraphArcadeDBAdapter, *nodes: NodeWrite) -> list[str]:
    tx = await graph.begin_transaction()
    ids = await graph.upsert_nodes(list(nodes), tx)
    await graph.commit_transaction(tx)
    return [str(i) for i in ids]


async def test_a_load_reaches_the_index(world: World) -> None:
    (a,) = await _written(world.graph, _person("Quillfeather"))
    await world.drain()
    doc = await world.doc(a)
    assert doc is not None and doc["names"] == ["Quillfeather"] and doc["datasets"] == [DATASET]
    assert (doc["handling_classification"], doc["owning_unit"]) == ("OFFICIAL", "unit-1")


async def test_a_merge_re_reads_both_ends_and_adds_no_cluster(world: World) -> None:
    a, b = await _written(world.graph, _person("Smith"), _person("Smyth"))
    await world.drain()
    await world.client.delete(index=world.alias, id=a)  # so the merge's re-read is what puts it back
    await world.client.delete(index=world.alias, id=b)
    tx = await world.graph.begin_transaction()
    await world.graph.upsert_edges(
        [EdgeWrite(id=new_edge_id(), type="SAME_AS", source=a, target=b, properties={"score": 1.0},
                   provenance=PROVENANCE, handling=HANDLING, created_by="loader-1", created_at=WHEN,
                   datasets=[DATASET])],
        tx,
    )  # fmt: skip
    await world.graph.commit_transaction(tx)
    await world.drain()
    for end in (a, b):
        doc = await world.doc(end)
        assert doc is not None and not {"cluster", "same_as"} & set(doc)


async def test_a_new_version_replaces_the_old_revisions_document(world: World) -> None:
    (old,) = await _written(world.graph, _person("Mohamad"))
    await world.drain()
    tx = await world.graph.begin_transaction()
    new = str(await world.graph.supersede_node(old, _person("Muhammad"), tx))
    await world.graph.commit_transaction(tx)
    await world.drain()
    assert await world.doc(old) is None
    doc = await world.doc(new)
    assert doc is not None and doc["names"] == ["Muhammad"]


async def test_a_promotion_and_its_revert_change_the_documents_datasets(world: World) -> None:
    (drawn,) = await _written(world.graph, _person("Drawn", datasets=("layer-9",)))
    await world.drain()
    tx = await world.graph.begin_transaction()
    await world.graph.promote_elements([drawn], [], DATASET, "promotion-9", tx)
    await world.graph.commit_transaction(tx)
    await world.drain()
    assert (await world.doc(drawn))["datasets"] == sorted([DATASET, "layer-9"])  # type: ignore[index]
    tx = await world.graph.begin_transaction()
    await world.graph.revert_promotion("promotion-9", DATASET, tx)
    await world.graph.commit_transaction(tx)
    await world.drain()
    assert (await world.doc(drawn))["datasets"] == ["layer-9"]  # type: ignore[index]


async def test_a_deletion_takes_the_document_and_its_text_out(world: World) -> None:
    doc_node = NodeWrite(
        id=new_node_id(), type="Document", properties={"title": "Statement"},
        provenance=PROVENANCE, handling=HANDLING, created_by="loader-1", created_at=WHEN,
        datasets=[DATASET],
    )  # fmt: skip
    (d,) = await _written(world.graph, doc_node)
    await world.drain()
    assert await world.doc(f"text:{d}") is None
    # The text alone, after its node is indexed: only the text's own outbox can bring it.
    await world.texts.store_document_text(d, "He met Mohamad at the docks.", WRITER)
    await world.drain()
    text = await world.doc(f"text:{d}")
    assert text is not None and text["text_owning_unit"] == "unit-5" and "Mohamad" in text["text"]
    assert "text" not in (await world.doc(d))  # type: ignore[operator]
    tx = await world.graph.begin_transaction()
    await world.graph.revert_elements([d], [], tx)
    await world.graph.commit_transaction(tx)
    await world.drain()
    assert await world.doc(d) is None and await world.doc(f"text:{d}") is None


async def test_the_drift_check_finds_each_difference_and_the_rebuild_mends_them(world: World) -> None:
    a, b, c = await _written(world.graph, _person("Ashdown"), _person("Blyth"), _person("Corrie"))
    await world.drain()
    clean = await drift(world.graph, world.texts, world.client, world.alias, ONTOLOGY)
    assert clean.none and clean.graph_nodes == 3 and clean.index_documents == 3
    # Planted: one missing, one stale, one extra.
    await world.client.delete(index=world.alias, id=a)
    await world.client.update(index=world.alias, id=b, body={"doc": {"handling_code": "R"}})
    await world.client.index(index=world.alias, id="ghost", body={"kind": "node", "id": "ghost"})
    found = await drift(world.graph, world.texts, world.client, world.alias, ONTOLOGY)
    assert (found.missing, found.stale, found.extra) == ([a], [b], ["ghost"])
    done = await rebuild(world.graph, world.texts, world.client, world.alias, ONTOLOGY)
    assert (done.nodes, done.documents) == (3, 3) and done.index.startswith(world.alias)
    assert list((await world.client.indices.get_alias(name=world.alias)).keys()) == [done.index]
    assert (await drift(world.graph, world.texts, world.client, world.alias, ONTOLOGY)).none
    assert c


async def test_a_change_during_a_rebuild_reaches_the_index_being_built_too(world: World) -> None:
    building = f"{world.alias}-next"
    from services.search_index.mapping import index_body

    await world.client.indices.create(index=building, body=index_body())
    await world.client.indices.put_alias(index=building, name=building_alias(world.alias))
    (a,) = await _written(world.graph, _person("Midway"))
    await world.drain()
    await world.client.indices.refresh(index=building)
    assert await world.doc(a) is not None
    assert (await world.client.get(index=building, id=a))["_source"]["names"] == ["Midway"]


async def test_a_throwaway_index_holds_exactly_the_nodes_given_and_is_gone_after() -> None:
    from schemas.domain import AuditStub, Node
    from services.search_index.testing import throwaway_index

    def node(node_id: str, name: str, type_: str = "Person") -> Node:
        return Node(id=node_id, type=type_, properties={"family_name": name, "title": name},
                    provenance=PROVENANCE, handling=HANDLING,
                    audit=AuditStub(created_at=WHEN, created_by="loader-1"), datasets=[DATASET])  # fmt: skip

    nodes = [node("p-1", "Smith"), node("d-1", "Statement", "Document")]
    async with throwaway_index(nodes, {"d-1": ("Mohamad at the docks", "unit-4")}) as (client, index):
        hits = await client.search(index=index, body={"query": {"match_all": {}}})
        assert {h["_id"] for h in hits["hits"]["hits"]} == {"p-1", "d-1", "text:d-1"}
        name = index
    gone = search_client()
    try:
        assert not await gone.indices.exists(index=name)
    finally:
        await gone.close()


async def test_a_long_typed_prefix_still_finds_the_name(world: World) -> None:
    """Up to `PREFIX_MAX_CHARS` (50): a name still being typed past 20 characters keeps matching."""
    from services.search_index.mapping import PREFIX_MAX_CHARS

    name = "Kestrel Holdings Limited Partnership Of Northern Wessex"
    (a,) = await _written(world.graph, _person(name))
    await world.drain()

    async def found(prefix: str) -> set[str]:
        hits = await world.client.search(
            index=world.alias, body={"query": {"match": {"names.prefix": prefix}}}
        )
        return {h["_id"] for h in hits["hits"]["hits"]}

    assert await found(name[:21]) == {a}
    assert await found(name[:PREFIX_MAX_CHARS]) == {a}
    assert await found(name[:21] + "x") == set()
