"""ADR-124 Amendment 18, live: a load's time grows with its own size, not with the graph's.

The write path (`upsert_nodes`, `upsert_edges`, the bulk loader) looked each node up by
`g.V().has("id", …)`, which ArcadeDB answers by scanning every vertex (ADR-124 Amendment 2's
measure: 3.6 s for 1,000 ids at 200,000 vertices), so a load of n items into a graph of N cost n×N
and loading a client-size dataset grew with its square. It now resolves ids through each vertex
type's unique `id` index by SQL and starts every traversal from record ids.

The same load (200 nodes, then 200 links between them, the 200 nodes written again as a re-ingest
writes them, then 200 more links loaded in bulk) runs against
the graph padded with 2,000 other vertices and then with 102,000: fifty times the graph, and the
load must take less than one and a half times as long. Measured on the lane stack (14 November,
stack c): 6.63 s and 6.41 s at 2,000 and 22,000, flat. At 22,000 one scan per item adds only some
2 s to a 6.6 s load (Amendment 2: 11 ms a scan at 20,000), which no bound can tell from noise, so
the graph is made large enough that each scanning lookup put back (plants A9 to A11) costs more than
the whole load does. The offline stand-ins refuse the scanning shapes outright
(`tests/adapters/graph_arcadedb/edge_store.refuse_scans`); this is the measurement behind them.

**Counted always, timed only under a lease** (rule 14). The load's round trips to the store, SQL and
Gremlin, are counted at both sizes and must be the same: deterministic, so CI's conformance job
holds it. The time bound is asserted only in a run that names its lease (`stack_lease.sh remote`
writes the run's lease into `$OSPREY_RUN_TAG/lease`), since a time taken beside unknown work
measures nothing; elsewhere the times are printed and not judged. A scan put back (plants A9 to
A11) is one round trip, so only the timed run shows it at size; offline, the stand-ins refuse it.
"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.naming import physical_type_name
from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_edge_id, new_node_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import EdgeWrite, Handling, NodeWrite, Provenance, ProvenanceState, SourceRef

pytestmark = pytest.mark.asyncio

WHEN = datetime(2026, 1, 1, tzinfo=UTC)
SOURCE = SourceRef(document_id="files/people.csv", locator="row 1", excerpt_hash="e" * 64)
PROVENANCE = Provenance(state=ProvenanceState.ASSERTED, sources=[SOURCE], first_seen=WHEN)
HANDLING = Handling(classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1")
LOAD = 200


@pytest.fixture
async def graph() -> AsyncIterator[GraphArcadeDBAdapter]:
    async with arcadedb_adapter(load_default_ontology(), load_uk_le_scheme()) as adapter:
        yield adapter


async def _pad(graph: GraphArcadeDBAdapter, first: int, count: int) -> None:
    """`count` other vertices from number `first`, written straight in by SQL (the padding is not
    what is measured)."""
    client = graph._client  # noqa: SLF001
    for start in range(first, first + count, 1000):
        rows = [{"id": f"pad-{n:07d}"} for n in range(start, min(start + 1000, first + count))]
        await client.sql(
            f"INSERT INTO `{physical_type_name('Person')}` CONTENT :rows", params={"rows": rows}
        )


def _person(n: int) -> NodeWrite:
    return NodeWrite(
        id=new_node_id(), type="Person", properties={"family_name": f"Scale{n}"},
        provenance=PROVENANCE, handling=HANDLING, created_by="loader-1", created_at=WHEN,
        datasets=["Z2001ZZ"],
    )  # fmt: skip


def _link(source: str, target: str) -> EdgeWrite:
    return EdgeWrite(
        id=new_edge_id(), type="ASSOCIATE_OF", source=source, target=target, provenance=PROVENANCE,
        handling=HANDLING, created_by="loader-1", created_at=WHEN, datasets=["Z2001ZZ"],
    )  # fmt: skip


class _Counted:
    """The adapter's client, with each round trip to the store counted."""

    def __init__(self, client: object) -> None:
        self._client = client
        self.trips = 0

    def __getattr__(self, name: str) -> object:
        attr = getattr(self._client, name)
        if name not in ("sql", "gremlin"):
            return attr

        async def counted(*args: object, **kwargs: object) -> object:
            self.trips += 1
            return await attr(*args, **kwargs)

        return counted


def _lease() -> str | None:
    """The lease this run was taken under, where `stack_lease.sh remote` named one."""
    tag = os.environ.get("OSPREY_RUN_TAG")
    if not tag or not os.path.isfile(os.path.join(tag, "lease")):
        return None
    with open(os.path.join(tag, "lease"), encoding="utf-8") as f:
        return f.read().strip() or None


async def _load(graph: GraphArcadeDBAdapter) -> tuple[float, int]:
    """The load, with the round trips of the adapter's client and of its bulk loader's (built over
    the same client, ADR-058) both counted."""
    counted = _Counted(graph._client)
    transport = graph._bulk._transport
    graph._client = counted  # type: ignore[assignment]
    transport._client = counted  # type: ignore[attr-defined]
    try:
        return await _timed_load(graph), counted.trips
    finally:
        graph._client = counted._client  # type: ignore[assignment]
        transport._client = counted._client  # type: ignore[attr-defined]


async def _timed_load(graph: GraphArcadeDBAdapter) -> float:
    started = time.perf_counter()
    nodes = [_person(n) for n in range(LOAD)]
    tx = await graph.begin_transaction()
    ids = [str(i) for i in await graph.upsert_nodes(nodes, tx)]
    await graph.upsert_edges([_link(ids[n], ids[(n + 1) % LOAD]) for n in range(LOAD)], tx)
    await graph.commit_transaction(tx)
    # The same nodes written again, as a re-ingested load writes them: each now exists, so its
    # lookup of the existing node is measured too (plant A9).
    tx = await graph.begin_transaction()
    await graph.upsert_nodes(nodes, tx)
    await graph.commit_transaction(tx)
    await graph.bulk_load_edges([_link(ids[n], ids[(n + 7) % LOAD]) for n in range(LOAD)])
    return time.perf_counter() - started


PER_ROW = 50


async def _per_row(graph: GraphArcadeDBAdapter) -> float:
    """The ingest engine's shape (`services/ingest/engine.py`: one `upsert_nodes` call a row): each
    call asks every vertex type once (ADR-124 Amendment 18), so this is the per-row cost a load
    pays. Seconds a call."""
    nodes = [_person(n) for n in range(PER_ROW)]
    started = time.perf_counter()
    for node in nodes:
        tx = await graph.begin_transaction()
        await graph.upsert_nodes([node], tx)
        await graph.commit_transaction(tx)
    return (time.perf_counter() - started) / PER_ROW


async def test_a_loads_time_grows_with_the_load_not_the_graph(graph: GraphArcadeDBAdapter) -> None:
    await _pad(graph, 0, 2_000)
    await _load(graph)  # warm: scripts compiled, types read
    small, small_trips = await _load(graph)
    small_row = await _per_row(graph)
    await _pad(graph, 2_000, 100_000)
    large, large_trips = await _load(graph)
    large_row = await _per_row(graph)
    lease = _lease()
    print(
        f"ADR-124 Am 18: the load at 2,000 padding {small:.2f} s and {small_trips} round trips, "
        f"at 102,000 {large:.2f} s and {large_trips}; one node a call, {small_row * 1000:.1f} ms "
        f"and {large_row * 1000:.1f} ms; lease: {lease or 'none, so not timed'}"
    )
    assert large_trips == small_trips, (small_trips, large_trips)
    if lease is not None:
        assert large < 1.5 * small, (small, large)
        assert large_row < 1.5 * small_row, (small_row, large_row)


async def test_one_call_writing_one_node_twice_ends_as_one_node(graph: GraphArcadeDBAdapter) -> None:
    """ADR-124 Amendment 18: an id written earlier in the same call is found again by SQL through
    its type's index in the call's own transaction (the scan it replaces saw the transaction's
    uncommitted insert; the index lookup must too), so one `upsert_nodes` call that writes a node
    twice leaves one node, at revision 2, holding both writes' sources."""
    from schemas.domain import Principal

    first = _person(0)
    other_source = SourceRef(document_id="files/people.csv", locator="row 2", excerpt_hash="f" * 64)
    second = first.model_copy(
        update={"provenance": PROVENANCE.model_copy(update={"sources": [other_source]})}
    )
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([first, second], tx)
    await graph.commit_transaction(tx)
    reader = Principal(id="r", clearance="OFFICIAL", org_unit="unit-1", datasets=["Z2001ZZ"])
    (node,) = await graph.get_nodes([first.id], reader)
    assert node.audit.revision == 2
    assert {s.locator for s in node.provenance.sources} == {"row 1", "row 2"}
