"""ADR-130 Amendment 2: what the working set sends a reader holds an element's sources only when
every dataset the element belongs to is one the reader's case reads. The stored bodies keep the
full record; the projection for each reader is where it is applied, on every path that sends one:
the first snapshot, a replay of what a reconnect missed (`sync`), a live push (`project_live`) and
a link's replacement.

Hermetic: `FakeWorkingSetStore` round-trips what it stores as the real stream does, and the
projection under test is the real `WorkingSetService`. The adapter's own half is held by
`tests/adapters/graph_arcadedb/test_sources_withheld_live.py`.
"""

from __future__ import annotations

from services.api.working_set.models import (
    DeltaAdd,
    DeltaReplaceEdge,
    DeltaReplaceEdgeSent,
    DeltaSnapshot,
    RemovedElement,
)
from services.api.working_set.service import WorkingSetService

from schemas.domain import Edge, Node, Principal, Subgraph

from .fakes import FakeGraphPort, FakeWorkingSetStore
from .test_visible_link import SCHEME, edge, node

CASE = "inv-1"
TWO = ["Z1001ZZ", "Z1002ZZ"]
ONE_DATASET_READER = Principal(
    id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", datasets=[TWO[0]]
)
BOTH_DATASETS_READER = Principal(
    id="analyst-2", clearance="OFFICIAL", org_unit="unit-1", datasets=TWO
)


def _service(store: FakeWorkingSetStore) -> WorkingSetService:
    return WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), store, SCHEME)


def _shared_node(node_id: str) -> Node:
    return node(node_id).model_copy(update={"datasets": list(TWO)})


def _shared_edge(edge_id: str, source: str, target: str) -> Edge:
    return edge(edge_id, source, target).model_copy(update={"datasets": list(TWO)})


async def _seeded() -> tuple[FakeWorkingSetStore, WorkingSetService]:
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [_shared_node("a"), _shared_node("b")])
    await store.add_edges(CASE, [_shared_edge("ab", "a", "b")])
    seq = await store.next_seq(CASE)
    await store.append_delta(
        CASE,
        DeltaAdd(
            seq=seq,
            nodes=[_shared_node("a"), _shared_node("b")],
            edges=[_shared_edge("ab", "a", "b")],
        ),
    )
    return store, _service(store)


def _nothing_said(elements: list[Node] | list[Edge]) -> bool:
    return bool(elements) and all(
        e.provenance.sources == [] and e.provenance.sources_withheld for e in elements
    )


def _all_named(elements: list[Node] | list[Edge]) -> bool:
    return bool(elements) and all(
        len(e.provenance.sources) == 1 and not e.provenance.sources_withheld for e in elements
    )


async def test_a_replay_to_a_reader_of_one_dataset_carries_no_sources() -> None:
    store, service = await _seeded()
    (sent,) = await service.sync(CASE, ONE_DATASET_READER, last_acknowledged_seq=0)
    assert isinstance(sent, DeltaAdd)
    assert _nothing_said(sent.nodes) and _nothing_said(sent.edges)
    assert "doc-1" not in sent.model_dump_json()


async def test_a_replay_to_a_reader_of_both_datasets_names_them() -> None:
    _, service = await _seeded()
    (sent,) = await service.sync(CASE, BOTH_DATASETS_READER, last_acknowledged_seq=0)
    assert isinstance(sent, DeltaAdd)
    assert _all_named(sent.nodes) and _all_named(sent.edges)


async def test_a_first_snapshot_to_a_reader_of_one_dataset_carries_no_sources() -> None:
    _, service = await _seeded()
    (sent,) = await service.sync(CASE, ONE_DATASET_READER, last_acknowledged_seq=None)
    assert isinstance(sent, DeltaSnapshot)
    assert _nothing_said(sent.nodes) and _nothing_said(sent.edges)
    assert "doc-1" not in sent.model_dump_json()


async def test_a_live_delta_to_a_reader_of_one_dataset_carries_no_sources() -> None:
    store, service = await _seeded()
    (stored,) = await store.deltas_after(CASE, 0) or []
    sent = await service.project_live(CASE, stored, ONE_DATASET_READER)
    assert isinstance(sent, DeltaAdd)
    assert _nothing_said(sent.nodes) and _nothing_said(sent.edges)


async def test_a_replacement_link_sent_to_a_reader_of_one_dataset_carries_no_sources() -> None:
    """Violation caught: `_project_replacement` sends the new link as the delta holds it, past
    `_project`, so both its rows that send a link (the replace and the plain add) skipped it."""
    store, service = await _seeded()
    old = _shared_edge("ab", "a", "b")
    delta = DeltaReplaceEdge(
        seq=2,
        old_edge_id="ab",
        edge=_shared_edge("ab2", "a", "b"),
        removed=RemovedElement(
            handling=old.handling, datasets=old.datasets, source="a", target="b"
        ),
    )
    sent = await service.project_live(CASE, delta, ONE_DATASET_READER)
    assert isinstance(sent, DeltaReplaceEdgeSent)
    assert _nothing_said([sent.edge])
    whole = await service.project_live(CASE, delta, BOTH_DATASETS_READER)
    assert isinstance(whole, DeltaReplaceEdgeSent) and _all_named([whole.edge])


async def test_the_stored_bodies_and_deltas_keep_their_sources() -> None:
    """The projection is a copy for one reader: the next reader, of both datasets, is still named
    the sources, and so is what is stored."""
    store, service = await _seeded()
    await service.sync(CASE, ONE_DATASET_READER, last_acknowledged_seq=0)
    await service.sync(CASE, ONE_DATASET_READER, last_acknowledged_seq=None)
    bodies = await store.source_fidelity_nodes(CASE)
    assert all(len(n.provenance.sources) == 1 for n in bodies.values())
    assert all(not n.provenance.sources_withheld for n in bodies.values())
    (stored,) = await store.deltas_after(CASE, 0) or []
    assert isinstance(stored, DeltaAdd)
    assert all(len(n.provenance.sources) == 1 for n in stored.nodes)
    (again,) = await service.sync(CASE, BOTH_DATASETS_READER, last_acknowledged_seq=0)
    assert isinstance(again, DeltaAdd) and _all_named(again.nodes)
