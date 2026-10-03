"""`ValkeyWorkingSetStore` against a live Valkey — `make dev-up`.

`test_service.py` already proves `WorkingSetService`'s own logic (the cap
check, `filtered_count`, the reconnect decision) against a fast in-memory
fake, deliberately without needing Valkey. This file is the other half:
does the *real* store's Valkey Streams mechanics — `XADD` with an explicit
`{seq}-0` id, `XRANGE (since_seq-0 +`, `MAXLEN ~` trimming — actually
behave the way `FakeWorkingSetStore` was written to model them.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.working_set.models import DeltaAdd
from services.api.working_set.store import ValkeyWorkingSetStore
from valkey.asyncio import Valkey

from schemas.domain import AuditStub, Edge, Handling, Node, Provenance, ProvenanceState, SourceRef


def _node(node_id: str) -> Node:
    return Node(
        id=node_id,
        type="Person",
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="loader-1"),
    )


def _edge(edge_id: str, source: str, target: str) -> Edge:
    return Edge(
        id=edge_id,
        type="ASSOCIATE_OF",
        source=source,
        target=target,
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="loader-1"),
    )


@pytest.fixture
async def store() -> ValkeyWorkingSetStore:
    client = Valkey(host="localhost", port=6379, db=0)
    investigation_id = f"test-{datetime.now(UTC).timestamp()}"
    working_store = ValkeyWorkingSetStore(client)
    yield working_store, investigation_id  # type: ignore[misc]
    await working_store.clear(investigation_id)
    await client.aclose()


async def test_nodes_round_trip_through_the_msgpack_encoded_hash(
    store: tuple[ValkeyWorkingSetStore, str],
) -> None:
    working_store, investigation_id = store
    await working_store.add_nodes(investigation_id, [_node("n1"), _node("n2")])

    fetched = await working_store.source_fidelity_nodes(investigation_id)

    assert set(fetched) == {"n1", "n2"}
    assert fetched["n1"].type == "Person"
    assert fetched["n1"].provenance.state == ProvenanceState.ASSERTED


async def test_node_ids_is_cheap_and_matches_source_fidelity_nodes(
    store: tuple[ValkeyWorkingSetStore, str],
) -> None:
    working_store, investigation_id = store
    await working_store.add_nodes(investigation_id, [_node("n1"), _node("n2"), _node("n3")])

    ids = await working_store.node_ids(investigation_id)

    assert ids == {"n1", "n2", "n3"}
    assert await working_store.node_count(investigation_id) == 3


async def test_remove_nodes_deletes_from_the_hash(
    store: tuple[ValkeyWorkingSetStore, str],
) -> None:
    working_store, investigation_id = store
    await working_store.add_nodes(investigation_id, [_node("n1"), _node("n2")])

    await working_store.remove_nodes(investigation_id, ["n1"])

    assert await working_store.node_ids(investigation_id) == {"n2"}


async def test_remove_edges_deletes_from_the_hash(
    store: tuple[ValkeyWorkingSetStore, str],
) -> None:
    working_store, investigation_id = store
    await working_store.add_nodes(investigation_id, [_node("n1"), _node("n2")])
    await working_store.add_edges(
        investigation_id, [_edge("e1", "n1", "n2"), _edge("e2", "n1", "n2")]
    )

    await working_store.remove_edges(investigation_id, ["e1"])

    assert await working_store.edge_ids(investigation_id) == {"e2"}


async def test_one_link_and_one_node_can_be_fetched_by_id_and_a_missing_one_is_none(
    store: tuple[ValkeyWorkingSetStore, str],
) -> None:
    """`get_edge`/`get_node` are the single-hash lookups link notes use for their access check
    (`WorkingSetService.visible_edge`); `None` — not an error — is what a missing id must give."""
    working_store, investigation_id = store
    await working_store.add_nodes(investigation_id, [_node("n1"), _node("n2")])
    await working_store.add_edges(investigation_id, [_edge("e1", "n1", "n2")])

    edge = await working_store.get_edge(investigation_id, "e1")
    node = await working_store.get_node(investigation_id, "n1")

    assert edge is not None and (edge.id, edge.source, edge.target) == ("e1", "n1", "n2")
    assert node is not None and node.id == "n1"
    assert await working_store.get_edge(investigation_id, "missing") is None
    assert await working_store.get_node(investigation_id, "missing") is None
    assert await working_store.get_edge("another-investigation", "e1") is None


async def test_seq_is_monotonic_and_per_investigation(
    store: tuple[ValkeyWorkingSetStore, str],
) -> None:
    working_store, investigation_id = store
    other_investigation = f"{investigation_id}-other"

    assert await working_store.next_seq(investigation_id) == 1
    assert await working_store.next_seq(investigation_id) == 2
    assert await working_store.next_seq(other_investigation) == 1  # independent counter

    await working_store.clear(other_investigation)


async def test_deltas_after_returns_exactly_the_missed_deltas_in_order(
    store: tuple[ValkeyWorkingSetStore, str],
) -> None:
    working_store, investigation_id = store
    for i in range(1, 4):
        seq = await working_store.next_seq(investigation_id)
        assert seq == i
        await working_store.append_delta(
            investigation_id, DeltaAdd(seq=seq, nodes=[_node(f"n{i}")], edges=[])
        )

    result = await working_store.deltas_after(investigation_id, 1)

    assert result is not None
    assert [d.seq for d in result] == [2, 3]


async def test_deltas_after_a_seq_already_caught_up_to_returns_empty(
    store: tuple[ValkeyWorkingSetStore, str],
) -> None:
    working_store, investigation_id = store
    seq = await working_store.next_seq(investigation_id)
    await working_store.append_delta(
        investigation_id, DeltaAdd(seq=seq, nodes=[_node("n1")], edges=[])
    )

    result = await working_store.deltas_after(investigation_id, seq)

    assert result == []


async def test_deltas_after_a_seq_with_no_stream_at_all_signals_a_gap(
    store: tuple[ValkeyWorkingSetStore, str],
) -> None:
    """Never recorded anything for this investigation, but `current_seq`
    still reports 0, so `since_seq >= current` (e.g. `since_seq=0`) is the
    "already caught up" case, not a gap — this test's `since_seq=1` with a
    `current_seq` that's advanced past it via a different mechanism is
    what actually exercises "nothing retained for what was asked"."""
    working_store, investigation_id = store
    # Advance the seq counter without ever appending a delta for it —
    # models a delta whose `append_delta` failed after `next_seq`
    # succeeded, the one place a real gap with a real counter mismatch
    # can occur.
    await working_store.next_seq(investigation_id)
    await working_store.next_seq(investigation_id)

    result = await working_store.deltas_after(investigation_id, 0)

    assert result is None
