"""ADR-150 decisions 1 and 2, on real ArcadeDB: every adapter write records the nodes it touched in the
index outbox, in the write's own transaction, by event type (load, merge, new version, promotion,
deletion); a rolled-back write records nothing; and the indexer's narrow read (`IndexFeedSource`) gives
each node as stored, whole, or None for one that is not live.

Each case writes through the adapter's real method at its real call shape and reads the outbox through
the port the indexer uses. Plants: `process/lanes/rules/v052-index/plants.py` removes each method's
outbox write in turn and expects its case red.

Needs a live ArcadeDB (`make conformance` runs the directory); run alone under a lease with the stack's
ports pinned.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime

import pytest

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_edge_id, new_node_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ports.index_feed import IndexFeedSource
from schemas.domain import EdgeWrite, Handling, NodeWrite, Provenance, ProvenanceState, SourceRef

pytestmark = pytest.mark.asyncio

WHEN = datetime(2026, 1, 1, tzinfo=UTC)
SOURCE = SourceRef(document_id="files/people.csv", locator="row 1", excerpt_hash="e" * 64)
PROVENANCE = Provenance(state=ProvenanceState.ASSERTED, sources=[SOURCE], first_seen=WHEN)
HANDLING = Handling(classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1")
DATASET = "Z2001ZZ"


@pytest.fixture
async def graph() -> AsyncIterator[GraphArcadeDBAdapter]:
    async with arcadedb_adapter(load_default_ontology(), load_uk_le_scheme()) as adapter:
        yield adapter


def _person(family_name: str, datasets: Sequence[str] = (DATASET,), node_id: str | None = None) -> NodeWrite:
    return NodeWrite(
        id=node_id or new_node_id(),
        type="Person",
        properties={"family_name": family_name},
        provenance=PROVENANCE,
        handling=HANDLING,
        created_by="loader-1",
        created_at=WHEN,
        datasets=list(datasets),
    )


def _edge(kind: str, source: str, target: str) -> EdgeWrite:
    return EdgeWrite(
        id=new_edge_id(),
        type=kind,
        source=source,
        target=target,
        properties={"score": 1.0} if kind == "SAME_AS" else {},
        provenance=PROVENANCE,
        handling=HANDLING,
        created_by="loader-1",
        created_at=WHEN,
        datasets=[DATASET],
    )


async def _drain(feed: IndexFeedSource) -> set[str]:
    """The outbox's node ids, then emptied, so the next step's write is read alone."""
    rows = await feed.pending_index(10_000)
    await feed.clear_pending_index([r.ref for r in rows])
    return {r.node_id for r in rows}


async def _written(graph: GraphArcadeDBAdapter, *nodes: NodeWrite) -> list[str]:
    tx = await graph.begin_transaction()
    ids = await graph.upsert_nodes(list(nodes), tx)
    await graph.commit_transaction(tx)
    return [str(i) for i in ids]


async def test_the_adapter_is_the_index_feed_source(graph: GraphArcadeDBAdapter) -> None:
    assert isinstance(graph, IndexFeedSource)


async def test_a_load_records_each_node_it_wrote(graph: GraphArcadeDBAdapter) -> None:
    ids = await _written(graph, _person("Quillfeather"), _person("Ashdown"))
    assert await _drain(graph) == set(ids)


async def test_a_rolled_back_write_records_nothing(graph: GraphArcadeDBAdapter) -> None:
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([_person("Rolledback")], tx)
    await graph.rollback_transaction(tx)
    assert await _drain(graph) == set()


async def test_a_merge_records_both_ends_of_a_same_as_and_nothing_for_another_link(
    graph: GraphArcadeDBAdapter,
) -> None:
    a, b, c = await _written(graph, _person("Smith"), _person("Smyth"), _person("Other"))
    await _drain(graph)
    tx = await graph.begin_transaction()
    await graph.upsert_edges([_edge("ASSOCIATE_OF", a, c)], tx)
    await graph.commit_transaction(tx)
    assert await _drain(graph) == set(), "a link other than SAME_AS changes no node's document"
    tx = await graph.begin_transaction()
    await graph.upsert_edges([_edge("SAME_AS", a, b)], tx)
    await graph.commit_transaction(tx)
    assert await _drain(graph) == {a, b}


async def test_a_new_version_records_the_old_revision_and_the_new(graph: GraphArcadeDBAdapter) -> None:
    (old,) = await _written(graph, _person("Mohamad"))
    await _drain(graph)
    tx = await graph.begin_transaction()
    new = await graph.supersede_node(old, _person("Muhammad"), tx)
    await graph.commit_transaction(tx)
    assert await _drain(graph) == {old, str(new)}


async def test_a_promotion_and_its_revert_record_each_node(graph: GraphArcadeDBAdapter) -> None:
    (drawn,) = await _written(graph, _person("Drawn", datasets=("layer-1",)))
    await _drain(graph)
    tx = await graph.begin_transaction()
    await graph.promote_elements([drawn], [], DATASET, "promotion-1", tx)
    await graph.commit_transaction(tx)
    assert await _drain(graph) == {drawn}
    tx = await graph.begin_transaction()
    await graph.revert_promotion("promotion-1", DATASET, tx)
    await graph.commit_transaction(tx)
    assert await _drain(graph) == {drawn}


async def test_a_revert_records_each_node_it_took_back(graph: GraphArcadeDBAdapter) -> None:
    a, b = await _written(graph, _person("Reverted"), _person("Kept"))
    await _drain(graph)
    tx = await graph.begin_transaction()
    await graph.revert_elements([a], [], tx)
    await graph.commit_transaction(tx)
    assert await _drain(graph) == {a}


async def test_a_withdrawal_and_its_restore_record_each_node(graph: GraphArcadeDBAdapter) -> None:
    (a,) = await _written(graph, _person("Withdrawn"))
    await _drain(graph)
    tx = await graph.begin_transaction()
    await graph.withdraw_elements([a], [], "refresh-2", tx)
    await graph.commit_transaction(tx)
    assert await _drain(graph) == {a}
    tx = await graph.begin_transaction()
    await graph.restore_withdrawn("refresh-2", tx)
    await graph.commit_transaction(tx)
    assert await _drain(graph) == {a}


async def test_a_deleted_case_layer_records_each_node_it_withdrew(graph: GraphArcadeDBAdapter) -> None:
    (a,) = await _written(graph, _person("Layered", datasets=("layer-2",)))
    await _drain(graph)
    tx = await graph.begin_transaction()
    await graph.withdraw_layer("layer-2", "layer-deleted-1", tx)
    await graph.commit_transaction(tx)
    assert await _drain(graph) == {a}


async def test_the_indexers_read_gives_a_live_node_whole_and_none_for_one_not_live(
    graph: GraphArcadeDBAdapter,
) -> None:
    live, gone, old = await _written(graph, _person("Live"), _person("Gone"), _person("Old"))
    tx = await graph.begin_transaction()
    await graph.revert_elements([gone], [], tx)
    new = str(await graph.supersede_node(old, _person("New"), tx))
    await graph.commit_transaction(tx)
    read = await graph.nodes_for_index([live, gone, old, new, "absent-node"])
    assert read[gone] is None and read[old] is None and read["absent-node"] is None
    assert read[live] is not None and read[live].properties["family_name"] == "Live"
    assert read[live].provenance.sources == [SOURCE], "the indexer reads the record whole"
    assert read[new] is not None and read[new].properties["family_name"] == "New"


async def test_the_live_ids_are_paged_in_id_order(graph: GraphArcadeDBAdapter) -> None:
    ids = sorted(await _written(graph, *[_person(f"P{i}") for i in range(5)]))
    tx = await graph.begin_transaction()
    await graph.revert_elements([ids[2]], [], tx)
    await graph.commit_transaction(tx)
    first = await graph.live_node_ids(after=None, limit=2)
    rest = await graph.live_node_ids(after=first[-1], limit=10)
    assert first + rest == [i for i in ids if i != ids[2]]


async def test_a_merge_loaded_in_bulk_records_both_ends(graph: GraphArcadeDBAdapter) -> None:
    a, b, c = await _written(graph, _person("Bulk"), _person("Bulke"), _person("Other"))
    await _drain(graph)
    await graph.bulk_load_edges([_edge("ASSOCIATE_OF", a, c)])
    assert await _drain(graph) == set()
    await graph.bulk_load_edges([_edge("SAME_AS", a, b)])
    assert await _drain(graph) == {a, b}


async def test_a_merge_superseded_records_both_ends(graph: GraphArcadeDBAdapter) -> None:
    a, b = await _written(graph, _person("Split"), _person("Splitt"))
    tx = await graph.begin_transaction()
    (link,) = await graph.upsert_edges([_edge("SAME_AS", a, b)], tx)
    await graph.commit_transaction(tx)
    await _drain(graph)
    tx = await graph.begin_transaction()
    await graph.supersede_edge(link, _edge("SAME_AS", a, b), tx, old_type="SAME_AS")
    await graph.commit_transaction(tx)
    assert await _drain(graph) == {a, b}
