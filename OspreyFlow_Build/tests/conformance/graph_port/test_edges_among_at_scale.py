"""ADR-124 Amendment 20, live: `edges_among` answers past the size its query once failed to compile
at, exactly, and leaves no trace of what the reader may not see.

Measured on 14 November 2026 (`process/lanes/rules-b/v052batch-50k/findings.md`, stack b, the lease
rules-b took at 13:51:02Z): as built, `edges_among` took 9.9 s at 5,000 ids and 19.7 s at 10,000,
and at 25,000 ArcadeDB refused the script ("Class too large", a Groovy `ClassTooLargeException`). A
batch expansion (ADR-151) of 50,000 nodes therefore failed, and so would `open_view` on a view that
large. These cases are red against that query and green against the record-id one.

- Past the wall: 50,500 nodes (500 SECRET) and their links, asked about at 25,000, 30,000 and
  50,000 ids (a seeded shuffle, so a set is not one contiguous run of chunks). Each answer is the
  exact set of link ids the fixture says lie among those ids and are visible, compared both ways.
- A chunk boundary: links whose two ends fall in different chunks, both ways, are each found once.
- A SECRET far end: a link to it, or from it, is absent for an OFFICIAL reader, and asking about it
  costs the same round trips and gives the same answer as asking about an id the store does not
  hold (rule 3).

The times are printed, not judged: a time is a measurement only under a lease (rule 14).
"""

from __future__ import annotations

import random
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from adapters.graph_arcadedb.adapter import _ID_CHUNK, GraphArcadeDBAdapter
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

pytestmark = pytest.mark.asyncio

WHEN = datetime(2026, 1, 1, tzinfo=UTC)
SOURCE = SourceRef(document_id="files/people.csv", locator="row 1", excerpt_hash="e" * 64)
PROVENANCE = Provenance(state=ProvenanceState.ASSERTED, sources=[SOURCE], first_seen=WHEN)
DATASET = "Z2002ZZ"
READER = Principal(id="r", clearance="OFFICIAL", org_unit="unit-1", datasets=[DATASET])
CLEARED = Principal(id="s", clearance="SECRET", org_unit="unit-1", datasets=[DATASET])


def _handling(classification: str) -> Handling:
    return Handling(classification=classification, handling_code="P", originator="unit-1",
                    owning_unit="unit-1")  # fmt: skip


def _person(classification: str = "OFFICIAL") -> NodeWrite:
    return NodeWrite(
        id=new_node_id(), type="Person", properties={"family_name": "Among"}, provenance=PROVENANCE,
        handling=_handling(classification), created_by="loader-1", created_at=WHEN,
        datasets=[DATASET],
    )  # fmt: skip


def _link(source: str, target: str, classification: str = "OFFICIAL") -> EdgeWrite:
    return EdgeWrite(
        id=new_edge_id(), type="ASSOCIATE_OF", source=source, target=target, provenance=PROVENANCE,
        handling=_handling(classification), created_by="loader-1", created_at=WHEN,
        datasets=[DATASET],
    )  # fmt: skip


@pytest.fixture
async def graph() -> AsyncIterator[GraphArcadeDBAdapter]:
    async with arcadedb_adapter(load_default_ontology(), load_uk_le_scheme()) as adapter:
        yield adapter


async def _write_nodes(graph: GraphArcadeDBAdapter, nodes: list[NodeWrite]) -> None:
    for start in range(0, len(nodes), 2_000):
        tx = await graph.begin_transaction()
        await graph.upsert_nodes(nodes[start : start + 2_000], tx)
        await graph.commit_transaction(tx)


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


async def _counted_among(
    graph: GraphArcadeDBAdapter, ids: list[str], reader: Principal
) -> tuple[set[str], int]:
    counted = _Counted(graph._client)  # noqa: SLF001
    graph._client = counted  # type: ignore[assignment]  # noqa: SLF001
    try:
        return {e.id for e in await graph.edges_among(ids, reader)}, counted.trips
    finally:
        graph._client = counted._client  # type: ignore[assignment]  # noqa: SLF001


async def test_past_the_compile_wall_the_answer_is_exactly_the_fixture_s_links(
    graph: GraphArcadeDBAdapter,
) -> None:
    """50,000 OFFICIAL people in a chain, 1,000 long links across the chain, and 500 SECRET people
    each linked from and to an OFFICIAL one; one SECRET link between two OFFICIAL people besides.
    At each size the ids asked for are the first n of a seeded shuffle of every id, SECRET ones
    included (a caller may pass ids its reader cannot see)."""
    official = [_person() for _ in range(50_000)]
    secret = [_person("SECRET") for _ in range(500)]
    await _write_nodes(graph, official + secret)
    o = [n.id for n in official]
    links = [_link(o[i], o[i + 1]) for i in range(len(o) - 1)]
    links += [_link(o[i], o[(i + 25_013) % len(o)]) for i in range(0, len(o), 50)]
    links += [_link(o[i * 97], s.id) for i, s in enumerate(secret)]
    links += [_link(s.id, o[i * 89 + 1]) for i, s in enumerate(secret)]
    links += [_link(o[3], o[40_003], "SECRET")]
    await graph.bulk_load_edges(links)
    hidden = {s.id for s in secret}
    visible = [(e.id, e.source, e.target) for e in links
               if e.handling.classification == "OFFICIAL" and e.source not in hidden
               and e.target not in hidden]  # fmt: skip

    every = o + sorted(hidden)
    random.Random(20261114).shuffle(every)
    for size in (25_000, 30_000, 50_000, len(every)):
        asked = every[:size]
        wanted = set(asked)
        expected = {i for i, s, t in visible if s in wanted and t in wanted}
        started = time.perf_counter()
        among = await graph.edges_among(asked, READER)
        took = time.perf_counter() - started
        found = [e.id for e in among]
        print(f"ADR-124 Am 20: edges_among at {size:,} ids, {len(found):,} links in {took:.1f} s")
        assert len(found) == len(set(found)), "a link returned twice"
        assert set(found) - expected == set(), "a link the fixture does not put among these ids"
        assert expected - set(found) == set(), "a link among these ids left out"


async def test_links_across_a_chunk_boundary_are_each_found_once(
    graph: GraphArcadeDBAdapter,
) -> None:
    """Twice the chunk and a little more, so there are three chunks. Asked in the adapter's own
    order (sorted ids), so the boundaries are known: links from the first chunk into the third, from
    the third back into the first, from the second into both, inside each chunk, and a self-loop."""
    nodes = [_person() for _ in range(2 * _ID_CHUNK + 50)]
    await _write_nodes(graph, nodes)
    ids = sorted(n.id for n in nodes)
    first, second, third = ids[:_ID_CHUNK], ids[_ID_CHUNK : 2 * _ID_CHUNK], ids[2 * _ID_CHUNK :]
    pairs = [(first[-1], third[0]), (third[0], first[-1]), (first[0], third[-1]),
             (third[-1], first[0]), (second[0], first[1]), (second[-1], third[1]),
             (first[2], first[3]), (second[2], second[3]), (third[2], third[3]),
             (second[4], second[4])]  # fmt: skip
    links = [_link(s, t) for s, t in pairs]
    await graph.bulk_load_edges(links)
    among = [e.id for e in await graph.edges_among(ids, READER)]
    assert sorted(among) == sorted(e.id for e in links)
    without_second = [e.id for e in await graph.edges_among(first + third, READER)]
    assert sorted(without_second) == sorted(
        e.id for e in links if e.source not in second and e.target not in second
    )


async def test_a_secret_far_end_leaves_no_trace_in_the_answer_or_its_cost(
    graph: GraphArcadeDBAdapter,
) -> None:
    """Rule 3. A SECRET person linked from one OFFICIAL person and to another, in a set big enough
    to span chunks, so the SECRET end falls in a chunk other than its OFFICIAL partners'. For an
    OFFICIAL reader, asking with the SECRET id gives the same links and the same round trips as
    asking with an id the store does not hold; a SECRET-cleared reader sees both links."""
    nodes = [_person() for _ in range(_ID_CHUNK + 100)]
    hidden = _person("SECRET")
    await _write_nodes(graph, [*nodes, hidden])
    ids = sorted(n.id for n in nodes)
    to_it, from_it, plain = (
        _link(ids[0], hidden.id),
        _link(hidden.id, ids[-1]),
        _link(ids[0], ids[-1]),
    )
    await graph.bulk_load_edges([to_it, from_it, plain])
    absent = new_node_id()

    with_secret, secret_trips = await _counted_among(graph, [*ids, hidden.id], READER)
    with_absent, absent_trips = await _counted_among(graph, [*ids, absent], READER)
    assert with_secret == with_absent == {plain.id}
    assert secret_trips == absent_trips
    cleared, _ = await _counted_among(graph, [*ids, hidden.id], CLEARED)
    assert cleared == {plain.id, to_it.id, from_it.id}
