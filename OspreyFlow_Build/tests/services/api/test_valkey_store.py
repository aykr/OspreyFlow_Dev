"""`ValkeyWorkingSetStore` against a live Valkey — `make dev-up`.

`test_service.py` already proves `WorkingSetService`'s own logic (the cap
check, the reconnect decision) against a fast in-memory
fake, deliberately without needing Valkey. This file is the other half:
does the *real* store's Valkey mechanics — Streams (`XADD` with an explicit
`{seq}-0` id, `XRANGE (since_seq-0 +`, `MAXLEN ~` trimming) and the access index
(one transaction with each write, its version and epoch, the `WATCH`ed rebuild) —
actually behave the way `FakeWorkingSetStore` was written to model them.
"""

from __future__ import annotations

import random
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import msgpack
import pytest
from services.api.working_set.access_index import (
    ABSENT,
    encode_signature,
    signature_id,
    signature_of,
)
from services.api.working_set.access_scripts import ADD_NODES
from services.api.working_set.models import DeltaAdd
from services.api.working_set.service import WorkingSetService
from services.api.working_set.store import ValkeyWorkingSetStore
from valkey.asyncio import Valkey
from valkey.exceptions import ResponseError

from schemas.domain import (
    AuditStub,
    Edge,
    Handling,
    Node,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
)

from .working_set.access_index_ops import (
    apply_random_operation,
    assert_index_matches_bodies,
    random_edge,
    random_node,
)
from .working_set.fakes import FakeGraphPort
from .working_set.test_access_index import READERS, _world
from .working_set.test_visible_link import OFFICIAL_READER, SCHEME, SECRET_READER, edge, node
from .working_set.test_visible_link import edge as index_edge
from .working_set.test_visible_link import node as index_node


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


# --- the access index (ADR-124 Amendment 4) ----------------------------------------------------
#
# `working_set/test_access_index.py` holds the in-memory fake to the index's rules. These are the
# real store's half, running the real Lua scripts: that every write is one atomic script with its
# counts, entries and adjacency, that the keys are cleared and expire with the case, that a case
# written before the index existed is indexed on first read, that the figures the service computes
# from the counts are the projection's, and that the rebuild is safe against a write landing
# meanwhile.


@pytest.fixture
async def indexed_store() -> AsyncIterator[tuple[ValkeyWorkingSetStore, Valkey, str]]:
    client = Valkey(host="localhost", port=6379, db=0)
    case = f"test-index-{datetime.now(UTC).timestamp()}"
    working_store = ValkeyWorkingSetStore(client)
    yield working_store, client, case
    await working_store.clear(case)
    await client.aclose()


async def test_every_structure_equals_what_the_bodies_say_after_any_run_of_operations(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    """Violation caught: a script that changes the bodies and not the counts (a remove that leaves
    its count, a replacement that keeps the old triple, a node's removal that does not move its
    links' triples, a signature change that does not). Ten seeded runs of thirty operations; the
    keys are read directly (not through `access_counts`, which rebuilds and so would heal the very
    fault) and compared with the bodies' oracle after every one."""
    working_store, _, case = indexed_store
    for seed in range(10):
        rng = random.Random(seed)
        await working_store.clear(case)
        for step in range(30):
            kind = await apply_random_operation(working_store, case, rng)
            await assert_index_matches_bodies(
                working_store, case, f"seed {seed} step {step} {kind}"
            )
    assert working_store.access_index_rebuilds == 0


async def test_ids_with_any_characters_go_through_the_scripts_whole(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    """Violation caught: an encoding that an id can break (a separator in an id, one node's id the
    start of another's, an id that looks like a length prefix)."""
    working_store, _, case = indexed_store
    awkward = ["a", "ab", "a:b", "1:a", "a\x1fb", 'q"uo', "ünï", "10:aaaaaaaaaa", "aaaaaaaaaa"]
    await working_store.add_nodes(case, [index_node(i) for i in awkward[:6]])
    await working_store.add_edges(
        case,
        [
            index_edge(f"e:{i}", a, b)
            for i, (a, b) in enumerate(zip(awkward, awkward[1:], strict=False))
        ],
    )
    await working_store.remove_nodes(case, ["a:b"])
    await working_store.add_nodes(case, [index_node("1:a", "SECRET")])
    await assert_index_matches_bodies(working_store, case, "awkward ids")


async def test_a_case_written_before_the_index_existed_is_indexed_on_first_read(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    """The bodies alone, as an upgrade leaves a live case: the first read builds the index from
    them, writes it, and the second reads it back without building."""
    working_store, client, case = indexed_store
    nodes, edges = await _bodies_without_an_index(client, case)
    assert await client.hlen(f"ws:{case}:access_nodes") == 0

    first = await working_store.access_counts(case)

    assert working_store.access_index_rebuilds == 1
    assert first.epoch and sum(first.node_counts.values()) == len(nodes)
    assert sum(first.edge_counts.values()) == len(edges)
    await assert_index_matches_bodies(working_store, case, "after the first read")
    again = await working_store.access_counts(case)
    assert working_store.access_index_rebuilds == 1 and again.epoch == first.epoch


async def test_the_index_keys_expire_with_the_case_and_clear_removes_them(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    working_store, client, case = indexed_store
    await working_store.add_nodes(case, [index_node("a"), index_node("b")])
    await working_store.add_edges(case, [index_edge("ab", "a", "b")])
    parts = (
        "access_nodes",
        "access_edges",
        "access_signatures",
        "sig_numbers",
        "access_meta",
        "node_counts",
        "edge_counts",
        "adjacency",
    )
    for part in parts:
        assert await client.ttl(f"ws:{case}:{part}") > 0, part

    await working_store.clear(case)

    for part in parts:
        assert await client.exists(f"ws:{case}:{part}") == 0, part


async def test_the_counts_are_small_and_the_entries_are_looked_up_by_id_only(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    working_store, _, case = indexed_store
    await working_store.add_nodes(case, [index_node("a"), index_node("s", "SECRET")])
    await working_store.add_edges(case, [index_edge("as", "a", "s"), index_edge("gone", "a", "x")])

    counts = await working_store.access_counts(case)
    entries = await working_store.access_entries(case, ["a", "zzz"], ["as", "nope"])

    assert sum(counts.node_counts.values()) == 2 and len(counts.signatures) == 2
    assert any(ABSENT in triple for triple in counts.edge_counts)
    assert set(entries.nodes) == {"a"} and set(entries.edges) == {"as"}
    assert set(entries.ends) == {"a", "s"}
    assert set(await working_store.stored_node_signatures(case)) == {"a", "s"}


@pytest.mark.parametrize("reader", READERS)
async def test_the_readers_counts_and_membership_are_the_projections(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str], reader: str
) -> None:
    working_store, _, case = indexed_store
    nodes, edges = _world()
    await working_store.add_nodes(case, nodes)
    await working_store.add_edges(case, edges)
    service = WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), working_store, SCHEME)
    principal = READERS[reader]

    counts = await service._reader_counts(case, principal)

    projected_nodes, projected_edges, _ = service._project(nodes, edges, principal)
    assert (counts.nodes, counts.edges) == (len(projected_nodes), len(projected_edges))
    entries = await working_store.access_entries(
        case, [n.id for n in nodes] + ["gone"], [e.id for e in edges] + ["unknown"]
    )
    visible_nodes, visible_edges = counts.visibly_stored(entries)
    assert visible_nodes == {n.id for n in projected_nodes}
    assert visible_edges == {e.id for e in projected_edges}
    assert await counts.visible_node_ids() == {n.id for n in projected_nodes}
    # The figures came from the counts as the scripts wrote them: a rebuild would have mended a
    # fault in them silently, which is what this guards against.
    assert working_store.access_index_rebuilds == 0


async def test_after_random_operations_the_counts_are_the_projections_for_each_reader(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    """The core property, against the real scripts: after each of thirty random operations the
    reader's counts equal the projection's for six readers."""
    working_store, _, case = indexed_store
    service = WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), working_store, SCHEME)
    rng = random.Random(11)
    for step in range(30):
        kind = await apply_random_operation(working_store, case, rng)
        nodes = list((await working_store.source_fidelity_nodes(case)).values())
        edges = list((await working_store.source_fidelity_edges(case)).values())
        for name, reader in READERS.items():
            counts = await service._reader_counts(case, reader)
            projected_nodes, projected_edges, _ = service._project(nodes, edges, reader)
            where = (step, kind, name)
            assert (counts.nodes, counts.edges) == (
                len(projected_nodes),
                len(projected_edges),
            ), where
    assert working_store.access_index_rebuilds == 0  # nothing was mended behind the figures


async def test_restore_through_the_service_leaves_the_index_equal_to_the_bodies(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    working_store, _, case = indexed_store
    await working_store.add_nodes(case, [node("old-1"), node("old-2"), node("keep")])
    await working_store.add_edges(case, [edge("old-edge", "old-1", "keep")])
    service = WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), working_store, SCHEME)

    await service.restore(
        case,
        [node("new-1"), node("keep", "SECRET")],
        [edge("new-edge", "new-1", "keep")],
        SECRET_READER,
    )

    await assert_index_matches_bodies(working_store, case, "after restore")
    assert set((await working_store.access_counts(case)).node_counts)


async def test_the_versions_count_up_and_the_epoch_is_new_after_a_clear(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    """Violation caught: a cache key that a write, a new signature or a case starting again does not
    move. The version is counted up by every write, the signatures version when a signature is first
    stored, and the epoch is set by the first write and deleted by `clear`; none takes a sequence
    number."""
    working_store, client, case = indexed_store
    empty = await working_store.access_counts(case)
    assert (empty.epoch, empty.version, empty.sigs_version) == ("", 0, 0)

    await working_store.add_nodes(case, [index_node("a")])
    first = await working_store.access_counts(case)
    assert first.epoch and (first.version, first.sigs_version) == (1, 1)
    await working_store.add_nodes(case, [index_node("b")])  # the same signature
    await working_store.add_edges(case, [index_edge("ab", "a", "b", "SECRET")])  # a new one
    await working_store.remove_edges(case, ["ab"])
    after = await working_store.access_counts(case)
    assert after.epoch == first.epoch and (after.version, after.sigs_version) == (4, 2)
    assert await client.get(f"ws:{case}:seq") is None, "none of that took a sequence number"

    await working_store.clear(case)
    await working_store.add_nodes(case, [index_node("a")])
    again = await working_store.access_counts(case)
    assert again.epoch and again.epoch != first.epoch
    assert (again.version, again.sigs_version) == (1, 1)


async def test_a_cleared_and_re_added_case_is_counted_afresh_by_the_service(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    """Violation caught: a readable-set memo not keyed by the epoch. `clear` drops the signature
    numbers, which start again at 1, so signature 1 is another signature: here OFFICIAL before the
    clear and SECRET after it, asked of the same OFFICIAL reader, who was told 1 is readable."""
    working_store, _, case = indexed_store
    service = WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), working_store, SCHEME)
    await working_store.add_nodes(case, [index_node("a")])
    first = await service._reader_counts(case, OFFICIAL_READER)

    await working_store.clear(case)
    await working_store.add_nodes(case, [index_node("x", "SECRET"), index_node("y", "SECRET")])
    second = await service._reader_counts(case, OFFICIAL_READER)
    third = await service._reader_counts(case, SECRET_READER)

    assert first.nodes == 1 and second.nodes == 0 and third.nodes == 2


async def _bodies_without_an_index(client: Valkey, case: str, seed: int = 3) -> tuple[list, list]:
    """Bodies written straight to the hashes, as an upgrade leaves a live case: no index."""
    rng = random.Random(seed)
    nodes = [random_node(rng, f"n{i}") for i in range(6)]
    edges = [random_edge(rng, f"e{i}") for i in range(5)]
    await client.hset(
        f"ws:{case}:nodes",
        mapping={n.id: msgpack.packb(n.model_dump(mode="json"), use_bin_type=True) for n in nodes},
    )
    await client.hset(
        f"ws:{case}:edges",
        mapping={e.id: msgpack.packb(e.model_dump(mode="json"), use_bin_type=True) for e in edges},
    )
    return nodes, edges


async def test_a_write_between_the_rebuilds_read_and_its_write_ends_with_a_consistent_index(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    """Violation caught: a rebuild that reads the bodies, builds, and writes without noticing a
    write in between, which leaves an index that does not cover the new body. Both body hashes are
    `WATCH`ed, so the transaction fails and the rebuild starts over, reading the new body."""
    working_store, _, case = indexed_store
    await _bodies_without_an_index(working_store._client, case)
    landed: list[str] = []

    async def write_in_the_gap(investigation_id: str) -> None:
        if not landed:  # once: the first attempt's gap
            landed.append(investigation_id)
            await working_store.add_nodes(investigation_id, [index_node("late", "SECRET")])

    working_store._between_rebuild_read_and_write = write_in_the_gap

    counts = await working_store.access_counts(case)

    assert landed == [case], "the write landed in the first attempt's gap"
    assert sum(counts.node_counts.values()) == 7
    await assert_index_matches_bodies(working_store, case, "after the race")
    assert working_store.access_index_rebuilds == 1


async def test_a_rebuild_that_is_never_left_in_peace_raises_rather_than_serve_a_wrong_index(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    working_store, client, case = indexed_store
    await _bodies_without_an_index(client, case)
    counter = iter(range(1_000))

    async def always_write(investigation_id: str) -> None:
        await working_store.add_nodes(investigation_id, [index_node(f"w{next(counter)}")])

    working_store._between_rebuild_read_and_write = always_write

    with pytest.raises(RuntimeError, match="could not be rebuilt"):
        await working_store.access_counts(case)


async def test_each_rebuild_is_logged_and_counted(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A planted mismatch (bodies and no index) is rebuilt with a warning that names the case and
    its size, and the store counts it; a second read, with the index in place, logs nothing."""
    working_store, client, case = indexed_store
    nodes, _ = await _bodies_without_an_index(client, case)

    with caplog.at_level("WARNING", logger="services.api.working_set.store"):
        await working_store.access_counts(case)

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert case in warnings[0].getMessage() and f"{len(nodes)} nodes" in warnings[0].getMessage()
    assert working_store.access_index_rebuilds == 1

    caplog.clear()
    with caplog.at_level("WARNING", logger="services.api.working_set.store"):
        await working_store.access_counts(case)
    assert caplog.records == [] and working_store.access_index_rebuilds == 1


_DAMAGES = [
    "a signature definition lost",
    "a signature number lost",
    "a count lost",
    "a node entry lost",
    "a link entry lost",
    "sig_counter lost",
    "sigs_version lost",
    "the adjacency lost",
    "the scalar hash lost",
    "the epoch lost",
]


@pytest.mark.parametrize("damage", _DAMAGES)
async def test_an_index_that_does_not_add_up_is_rebuilt_and_never_miscounts(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str], damage: str
) -> None:
    """Violation caught (rule 3): a structure that lost a key (an expiry of one, an eviction, an
    operator's `HDEL`) served as it is. Each of the ways the index can lose something is noticed
    by a check that does not read an element, the index is rebuilt, and afterwards a hidden
    signature is never counted for an OFFICIAL reader: the case holds one node above them and a
    link to it, and their figures are one node and no link."""
    working_store, client, case = indexed_store
    await working_store.add_nodes(case, [index_node("a"), index_node("b", "SECRET")])
    await working_store.add_edges(case, [index_edge("ab", "a", "b")])
    counts = await working_store.access_counts(case)
    key = next(iter(counts.node_counts))
    meta = f"ws:{case}:access_meta"
    if damage == "a signature definition lost":
        await client.hdel(f"ws:{case}:access_signatures", key)
    elif damage == "a signature number lost":
        await client.hdel(
            f"ws:{case}:sig_numbers", next(iter(await client.hkeys(f"ws:{case}:sig_numbers")))
        )
    elif damage == "a count lost":
        await client.hdel(f"ws:{case}:node_counts", key)
    elif damage == "a node entry lost":
        await client.hdel(f"ws:{case}:access_nodes", "a")
    elif damage == "a link entry lost":
        await client.hdel(f"ws:{case}:access_edges", "ab")
    elif damage == "sig_counter lost":
        await client.hdel(meta, "sig_counter")
    elif damage == "sigs_version lost":
        await client.hdel(meta, "sigs_version")
    elif damage == "the adjacency lost":
        await client.delete(f"ws:{case}:adjacency")
    elif damage == "the scalar hash lost":
        await client.delete(meta)
    else:
        await client.hdel(meta, "epoch")

    healed = await working_store.access_counts(case)

    assert working_store.access_index_rebuilds == 1, damage
    assert sum(healed.node_counts.values()) == 2 and sum(healed.edge_counts.values()) == 1
    await assert_index_matches_bodies(working_store, case, f"after {damage}")
    service = WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), working_store, SCHEME)
    official = await service._reader_counts(case, OFFICIAL_READER)
    cleared = await service._reader_counts(case, SECRET_READER)
    assert (official.nodes, official.edges) == (1, 0), damage
    assert (cleared.nodes, cleared.edges) == (2, 1), damage


async def test_a_signature_number_whose_definition_is_lost_makes_the_next_write_rebuild(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    """Violation caught (rule 3): a write that reuses a signature number whose definition is gone
    and files an element under a signature nothing can judge. The script refuses it, and the
    store rebuilds and writes again, so the index is whole when the write returns."""
    working_store, client, case = indexed_store
    await working_store.add_nodes(case, [index_node("a")])
    key = next(iter((await working_store.access_counts(case)).node_counts))
    await client.hdel(f"ws:{case}:access_signatures", key)

    await working_store.add_nodes(case, [index_node("b")])  # the same signature as `a`

    assert working_store.access_index_rebuilds == 1
    await assert_index_matches_bodies(working_store, case, "after the write that found the loss")


async def test_a_script_that_meets_a_missing_link_entry_refuses_and_the_write_rebuilds(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    """Violation caught: a script that reads a link's entry blindly. A node's removal moves the
    triples of the links at it; one whose entry is gone is not a thing to count out of, so the
    script stops before it changes anything, and the store rebuilds and removes again."""
    working_store, client, case = indexed_store
    await working_store.add_nodes(case, [index_node("a"), index_node("b"), index_node("c")])
    await working_store.add_edges(case, [index_edge("ab", "a", "b"), index_edge("ac", "a", "c")])
    await client.hdel(f"ws:{case}:access_edges", "ab")  # adjacency still names it

    await working_store.remove_nodes(case, ["a"])

    assert working_store.access_index_rebuilds == 1
    await assert_index_matches_bodies(working_store, case, "after the refused removal")


async def test_every_write_is_chunked_and_each_chunk_leaves_the_index_whole(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    """Violation caught: a script that does the work of a branch or a restore (tens of thousands of
    elements) in one go, which holds Valkey for as long as it takes. Each script takes at most a
    thousand elements, and the bodies and the index agree after every one."""
    working_store, client, case = indexed_store
    seen: list[tuple[str, int]] = []

    async def whole_after_each_chunk(name: str, size: int) -> None:
        seen.append((name, size))
        await assert_index_matches_bodies(working_store, case, f"after chunk {len(seen)}")

    working_store._after_script = whole_after_each_chunk
    await working_store.add_nodes(case, [index_node(f"n{i}") for i in range(2_500)])
    await working_store.add_edges(
        case, [index_edge(f"e{i}", f"n{i}", f"n{i + 1}") for i in range(2_100)]
    )
    await working_store.remove_nodes(case, [f"n{i}" for i in range(1_500)])
    await working_store.remove_edges(case, [f"e{i}" for i in range(1_001)])

    sizes = {name: [n for nm, n in seen if nm == name] for name in {nm for nm, _ in seen}}
    assert sizes == {
        "add_nodes": [1_000, 1_000, 500],
        "add_edges": [1_000, 1_000, 100],
        "remove_nodes": [1_000, 500],
        "remove_edges": [1_000, 1],
    }
    assert all(seconds >= 0 for _, _, seconds in working_store.script_runs)
    assert max(n for _, n in seen) <= 1_000


async def test_a_rebuild_never_changes_an_existing_signatures_number(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    """Violation caught: a rebuild that numbers the signatures afresh. A reader that holds a
    signature's number (a readable set kept for it, a script running alongside) would be given
    another signature's. The rebuild keeps every existing number and only appends. The signatures
    here are created in the reverse of the order their ids sort in, so a renumbering by id moves
    them."""
    working_store, client, case = indexed_store
    held = [
        index_node(f"n{i}", c).model_copy(update={"datasets": [d]})
        for i, (c, d) in enumerate([("OFFICIAL", "x"), ("SECRET", "y"), ("OFFICIAL", "z")])
    ]
    by_id = sorted(held, key=lambda n: signature_id(signature_of(n.handling, n.datasets)))
    for n in reversed(by_id):
        await working_store.add_nodes(case, [n])
    before = await client.hgetall(f"ws:{case}:sig_numbers")
    assert sorted(before.values()) == [b"1", b"2", b"3"]

    await client.hdel(f"ws:{case}:access_nodes", "n0")  # something a rebuild must mend
    await working_store.add_nodes(case, [index_node("late").model_copy(update={"datasets": ["w"]})])
    await working_store.access_counts(case)

    assert working_store.access_index_rebuilds == 1
    after = await client.hgetall(f"ws:{case}:sig_numbers")
    assert all(after[sid] == number for sid, number in before.items())
    assert len(after) == 4  # the new signature appended
    await assert_index_matches_bodies(working_store, case, "after the rebuild")


async def test_a_write_sets_every_keys_expiry_in_its_own_script_and_needs_no_second_trip(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    """Violation caught: a write followed by a separate pipeline to refresh the TTLs, a round trip
    for each write and a window in which the keys the script did not touch are not refreshed. The
    script takes the sequence, delta and threshold keys too."""
    working_store, client, case = indexed_store
    await working_store.add_nodes(case, [index_node("a")])
    await working_store.next_seq(case)
    await working_store.set_threshold(case, 0.9)
    for part in ("seq", "threshold"):
        await client.expire(f"ws:{case}:{part}", 100)
    pipelines: list[int] = []
    real = client.pipeline

    def counting(*args: object, **kwargs: object) -> object:
        pipelines.append(1)
        return real(*args, **kwargs)

    client.pipeline = counting  # type: ignore[method-assign]
    try:
        await working_store.add_nodes(case, [index_node("b")])
    finally:
        client.pipeline = real  # type: ignore[method-assign]

    assert pipelines == [], "the write needed no pipeline of its own for the TTLs"
    for part in ("seq", "threshold", "nodes", "access_nodes", "node_counts", "access_meta"):
        assert await client.ttl(f"ws:{case}:{part}") > 1_000, part


def _add_nodes_args(*nodes: Node) -> list[object]:
    """What `add_nodes` sends a script for these nodes, for a test that runs the script itself."""
    args: list[object] = []
    for n in nodes:
        signature = signature_of(n.handling, n.datasets)
        args += [
            n.id,
            msgpack.packb(n.model_dump(mode="json"), use_bin_type=True),
            signature_id(signature),
            encode_signature(signature),
        ]
    return args


async def test_a_new_signature_never_takes_the_number_of_one_that_is_defined(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    """Violation caught (rule 3): the scalar hash lost, so the signature counter starts again at 1
    and a new SECRET signature is given number 1, overwriting the definition of the OFFICIAL
    signature that number names. A request in flight that judged the number by the old table
    would count a SECRET element as OFFICIAL. The script refuses before it writes the definition,
    and the old number's definition is what it was."""
    working_store, client, case = indexed_store
    await working_store.add_nodes(case, [index_node("a")])
    definitions = f"ws:{case}:access_signatures"
    before = await client.hgetall(definitions)
    await client.delete(f"ws:{case}:access_meta")

    with pytest.raises(ResponseError, match="access index damaged"):
        await working_store._run_once(
            "add_nodes", ADD_NODES, case, _add_nodes_args(index_node("s", "SECRET")), 1
        )

    assert await client.hgetall(definitions) == before


async def test_a_new_signature_after_the_scalar_hash_is_lost_is_never_counted_as_official(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    """The same loss through `add_nodes`: one rebuild, and an OFFICIAL reader's figures exclude
    the new SECRET node whatever number it was filed under."""
    working_store, client, case = indexed_store
    await working_store.add_nodes(case, [index_node("a")])
    await client.delete(f"ws:{case}:access_meta")

    await working_store.add_nodes(case, [index_node("s", "SECRET")])

    assert working_store.access_index_rebuilds == 1
    await assert_index_matches_bodies(working_store, case, "after the refused write")
    service = WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), working_store, SCHEME)
    official = await service._reader_counts(case, OFFICIAL_READER)
    cleared = await service._reader_counts(case, SECRET_READER)
    assert official.nodes == 1 and cleared.nodes == 2


async def test_a_script_that_stops_on_a_damaged_entry_has_not_written_the_body(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    """Violation caught: `ADD_NODES` writing a node's body before it moves the counts of the links
    at the node, which can stop the script. The body of `a` is then the new one with the counts
    and the entry still the old one's. Nothing of the node is written until the move has
    succeeded."""
    working_store, client, case = indexed_store
    await working_store.add_nodes(case, [index_node("a"), index_node("b")])
    await working_store.add_edges(case, [index_edge("ab", "a", "b")])
    await client.hdel(f"ws:{case}:access_edges", "ab")  # adjacency still names it

    with pytest.raises(ResponseError, match="access index damaged"):
        await working_store._run_once(
            "add_nodes", ADD_NODES, case, _add_nodes_args(index_node("a", "SECRET")), 1
        )

    stored = await working_store.get_node(case, "a")
    assert stored is not None and stored.handling.classification == "OFFICIAL"


async def test_a_renumbering_between_the_counts_read_and_the_entries_read_gives_the_right_figures(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    """Violation caught (rule 3): a request that read the signature table, then a rebuild that
    renumbered the signatures, then the entries of the ids it asks about: the entry's number now
    names the other signature, so a hidden SECRET node is judged by the OFFICIAL definition the
    old table gave that number. The entries carry the epoch they were read at, and a difference
    from the counts' makes the request read the counts again and start over. Here the two
    signatures swap numbers in a rebuild that lands between the reads, and the OFFICIAL reader
    must be told the SECRET node is not in their view (one node new, one in view)."""
    working_store, client, case = indexed_store
    held = [index_node("x", "SECRET"), index_node("y")]
    by_id = sorted(held, key=lambda n: signature_id(signature_of(n.handling, n.datasets)))
    for n in reversed(by_id):  # created in the reverse of the order a renumbering gives
        await working_store.add_nodes(case, [n])
    service = WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), working_store, SCHEME)
    real = working_store.access_counts
    fired: list[int] = []

    async def counts_then_a_renumbering(case_id: str) -> object:
        result = await real(case_id)
        if not fired:
            fired.append(1)
            await client.delete(f"ws:{case}:access_meta")
            await real(case_id)  # the rebuild: numbered afresh, a new epoch
        return result

    working_store.access_counts = counts_then_a_renumbering  # type: ignore[method-assign]
    view = await service._reader_counts(case, OFFICIAL_READER)
    new_nodes, new_edges, _ = await view.would_add(["x"], ())

    assert working_store.access_index_rebuilds == 1
    assert (new_nodes, new_edges) == (1, 0), "x is SECRET: not in the OFFICIAL reader's view"
    assert view.nodes == 1


async def test_the_entries_carry_the_epoch_they_were_read_at(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    working_store, client, case = indexed_store
    await working_store.add_nodes(case, [index_node("a"), index_node("b")])
    await working_store.add_edges(case, [index_edge("ab", "a", "b")])
    counts = await working_store.access_counts(case)

    entries = await working_store.access_entries(case, ["a"], ["ab"])

    assert entries.epoch == counts.epoch != ""


async def test_a_branch_that_fails_at_a_chunk_leaves_no_half_built_case(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    """Violation caught: a branch of several chunks that fails part-way and leaves the first
    chunks as a new case that looks like a branch. The new case's working set is cleared before
    the failure is raised."""
    working_store, client, case = indexed_store
    new_case = f"{case}-branch"
    await working_store.add_nodes(case, [index_node(f"n{i}") for i in range(2_500)])
    service = WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), working_store, SCHEME)
    runs: list[str] = []

    async def fail_at_the_second_chunk(name: str, size: int) -> None:
        runs.append(name)
        if runs.count("add_nodes") == 2 and name == "add_nodes":
            raise RuntimeError("injected failure at chunk 2")

    working_store._after_script = fail_at_the_second_chunk
    with pytest.raises(RuntimeError, match="injected failure"):
        await service.branch(case, new_case, SECRET_READER)

    for part in ("nodes", "edges", "access_nodes", "node_counts", "access_meta", "seq", "deltas"):
        assert not await client.exists(f"ws:{new_case}:{part}"), part
    assert await working_store.node_ids(new_case) == set()


async def test_a_restore_that_fails_part_way_has_lost_nothing_it_held(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    """Violation caught: a restore that removes what the target lacks before it adds the target,
    so that a failure part-way leaves the case smaller than it was. The adds come first and the
    removes last (links before nodes), so a failure at any add chunk leaves a superset of what
    the case held. (Only what the restorer may read is ever removed: decision 6, unit U6.)"""
    working_store, client, case = indexed_store
    held = [index_node(f"n{i}") for i in range(1_500)]
    await working_store.add_nodes(case, held)
    target = [index_node(f"n{i}") for i in range(1_000, 3_500)]
    service = WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), working_store, SCHEME)
    runs: list[str] = []

    async def fail_at_the_second_add(name: str, size: int) -> None:
        runs.append(name)
        if runs.count("add_nodes") == 2 and name == "add_nodes":
            raise RuntimeError("injected failure at chunk 2")

    working_store._after_script = fail_at_the_second_add
    with pytest.raises(RuntimeError, match="injected failure"):
        await service.restore(case, target, [], SECRET_READER)

    assert {n.id for n in held} <= await working_store.node_ids(case)


async def test_a_restore_adds_before_it_removes_and_removes_links_before_nodes(
    indexed_store: tuple[ValkeyWorkingSetStore, Valkey, str],
) -> None:
    working_store, client, case = indexed_store
    await working_store.add_nodes(case, [index_node("a"), index_node("b"), index_node("c")])
    await working_store.add_edges(case, [index_edge("ab", "a", "b"), index_edge("bc", "b", "c")])
    service = WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), working_store, SCHEME)
    working_store.script_runs.clear()

    await service.restore(
        case, [index_node("a"), index_node("b")], [index_edge("ab", "a", "b")], SECRET_READER
    )

    assert [name for name, _, _ in working_store.script_runs] == [
        "add_nodes",
        "add_edges",
        "remove_edges",
        "remove_nodes",
    ]
    await assert_index_matches_bodies(working_store, case, "after the restore")
