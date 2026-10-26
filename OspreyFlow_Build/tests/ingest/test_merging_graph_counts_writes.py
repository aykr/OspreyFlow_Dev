"""ADR-127 Amendment 19, rule 15: the recipe tests' stand-in counts and refuses as the adapter does.

`MergingGraph` stores a new link at the revision its write's `writes` says and adds `writes` to a
stored link's revision on a merge, as `GraphArcadeDBAdapter.upsert_edges` does; and refuses a write
standing for fewer than one, as the adapter does.
`tests/adapters/graph_arcadedb/test_edge_write_count.py` holds the adapter to the same; this holds
the stand-in to it, so a run tested against the stand-in means what it does against the store.
"""

from __future__ import annotations

import pytest

from ontology.errors import OntologyError
from ontology.loader import load_default_ontology
from schemas.domain import EdgeWrite, NodeWrite
from tests.adapters.graph_arcadedb.edge_store import make_edge
from tests.ingest.recipe_test_support import MergingGraph

ONTOLOGY = load_default_ontology()


def _node(node_id: str) -> NodeWrite:
    edge = make_edge("a", "b", 1)
    return NodeWrite(
        id=node_id,
        type="Endpoint",
        properties={"value_raw": node_id, "value_normalised": node_id, "endpoint_kind": "handle"},
        provenance=edge.provenance,
        handling=edge.handling,
        created_by="test",
        created_at=edge.created_at,
    )


def _link(n: int, writes: int) -> EdgeWrite:
    write = make_edge("a", "b", n).model_copy(
        update={"type": "COMMUNICATED_WITH", "writes": writes}
    )
    return write


async def _graph() -> tuple[MergingGraph, object]:
    graph = MergingGraph(ONTOLOGY)
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([_node("a"), _node("b")], tx)
    return graph, tx


async def test_a_new_link_is_stored_at_the_revision_its_write_stands_for() -> None:
    graph, tx = await _graph()
    (link_id,) = await graph.upsert_edges([_link(1, 3)], tx)
    assert graph._revision[link_id] == 3


async def test_a_merge_adds_the_writes_it_stands_for_to_the_stored_revision() -> None:
    """Catches the stand-in adding one: 2, then a write for 4, then a plain write, is 7."""
    graph, tx = await _graph()
    (first,) = await graph.upsert_edges([_link(1, 2)], tx)
    assert await graph.upsert_edges([_link(2, 4)], tx) == [first]
    assert graph._revision[first] == 6
    await graph.upsert_edges([_link(3, 1)], tx)
    assert graph._revision[first] == 7


async def test_a_rollback_puts_back_the_revision_a_merge_changed() -> None:
    graph, tx = await _graph()
    (first,) = await graph.upsert_edges([_link(1, 2)], tx)
    await graph.commit_transaction(tx)
    tx = await graph.begin_transaction()
    await graph.upsert_edges([_link(2, 5)], tx)
    assert graph._revision[first] == 7
    await graph.rollback_transaction(tx)
    assert graph._revision[first] == 2


async def test_a_write_standing_for_fewer_than_one_is_refused() -> None:
    """The adapter refuses it (`test_edge_write_count.py`); a stand-in that took it would let a run
    through that the store would stop."""
    graph, tx = await _graph()
    with pytest.raises(OntologyError):
        await graph.upsert_edges([_link(1, 0)], tx)
