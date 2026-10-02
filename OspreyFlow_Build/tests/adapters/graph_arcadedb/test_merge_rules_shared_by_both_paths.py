"""One merge rule for a repeated pair, used by both write paths (ADR-058 D5).

`upsert_edges` merges a second write for the same (type, source, target) into the stored edge: the
occurrences add, the provenance sources are kept (de-duplicated by document and locator), the
interval widens, the latest write's own properties win, and the revision counts the writes. A bulk
load receives every write of a pair at once and must end with the same stored edge, so it
aggregates by the same rules. If the two were separate copies they would drift; the first test
below fails when they do, by writing the same list through `upsert_edges` one at a time and
comparing what the store holds with what the aggregator returns.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from schemas.domain import EdgeWrite, Interval, Provenance, ProvenanceState, SourceRef
from schemas.merge import aggregate_edge_writes, merge_interval, merge_provenance

from tests.adapters.graph_arcadedb.edge_store import CountingStore, make_adapter, make_edge

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _with_interval(write: EdgeWrite, start_days: int, end_days: int | None) -> EdgeWrite:
    return write.model_copy(
        update={
            "interval": Interval(
                valid_from=T0 + timedelta(days=start_days),
                valid_to=None if end_days is None else T0 + timedelta(days=end_days),
            )
        }
    )


def _writes() -> list[EdgeWrite]:
    """The pair a to b three times (distinct rows, widening intervals, differing occurrences), the
    pair b to a once, and two single pairs, in an order that interleaves them."""
    a_b_1 = _with_interval(make_edge("a", "b", 1), 5, 6).model_copy(update={"occurrences": 2})
    a_b_2 = _with_interval(make_edge("a", "b", 2), 1, 9)
    other = make_edge("c", "d", 3)
    b_a = make_edge("b", "a", 4)
    a_b_3 = _with_interval(make_edge("a", "b", 5), 3, None).model_copy(update={"occurrences": 4})
    return [a_b_1, other, a_b_2, b_a, a_b_3, make_edge("e", "f", 6)]


def _directed(_: str) -> bool:
    return True


def _sources(provenance: Provenance) -> list[tuple[str, str]]:
    return [(s.document_id, s.locator) for s in provenance.sources]


def test_the_aggregate_is_what_one_at_a_time_upserts_leave_in_the_store() -> None:
    """Catches the aggregator and `upsert_edges` disagreeing about a repeated pair: occurrences,
    provenance sources, interval, edge id, endpoints and revision must all match what the store
    holds after the same writes went in one at a time."""
    store = CountingStore()
    graph = make_adapter(store)
    for write in _writes():
        asyncio.run(graph.upsert_edges([write], "tx"))

    for aggregated in aggregate_edge_writes(_writes(), directed=_directed):
        stored = store.edges[(aggregated.write.source, aggregated.write.target)]
        assert stored["id"] == aggregated.write.id
        assert stored["occurrences"] == aggregated.write.occurrences
        assert [
            (s["document_id"], s["locator"]) for s in stored["provenance"]["sources"]
        ] == _sources(aggregated.write.provenance)
        interval = aggregated.write.interval
        assert interval is not None or "interval" not in stored
        if interval is not None:
            assert stored["interval"] == interval.model_dump(mode="json")
        assert stored["audit"]["revision"] == aggregated.writes


def test_a_repeated_pair_becomes_one_edge_with_everything_kept() -> None:
    """Catches a pair being dropped, duplicated, or losing a source row."""
    result = aggregate_edge_writes(_writes(), directed=_directed)
    assert [(r.write.source, r.write.target) for r in result] == [
        ("a", "b"),
        ("c", "d"),
        ("b", "a"),
        ("e", "f"),
    ]
    pair = result[0]
    assert pair.writes == 3 and pair.write.occurrences == 2 + 1 + 4
    assert _sources(pair.write.provenance) == [
        ("fixture", "row-1"),
        ("fixture", "row-2"),
        ("fixture", "row-5"),
    ]
    assert pair.write.interval == Interval(
        valid_from=T0 + timedelta(days=1), valid_to=T0 + timedelta(days=9)
    )


def test_an_undirected_pair_is_the_same_pair_either_way_round() -> None:
    """Catches `a to b` and `b to a` of an undirected type staying two edges: `upsert_edges` finds
    an undirected edge from either end, so it merges them, and the aggregate must too."""
    writes = [make_edge("a", "b", 1), make_edge("b", "a", 2)]
    assert len(aggregate_edge_writes(writes, directed=lambda _: False)) == 1
    assert len(aggregate_edge_writes(writes, directed=_directed)) == 2


def test_the_first_write_keeps_the_edge_identity_and_the_last_its_own_properties() -> None:
    """Catches the aggregate taking the wrong write's id (the stored edge keeps its first id) or
    the wrong write's properties (the latest write wins, as in `upsert_edges`)."""
    first = make_edge("a", "b", 1)
    last = make_edge("a", "b", 2).model_copy(update={"properties": {"note": "latest"}})
    (only,) = aggregate_edge_writes([first, last], directed=_directed)
    assert only.write.id == first.id and only.write.created_at == first.created_at
    assert only.write.properties == {"note": "latest"}


def test_merge_provenance_keeps_every_source_once() -> None:
    """Catches a source row being kept twice when the same document and locator recurs, or lost."""

    def provenance(*locators: str) -> Provenance:
        return Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="d", locator=x, excerpt_hash="") for x in locators],
            first_seen=T0,
        )

    merged = merge_provenance(provenance("1", "2"), provenance("2", "3"))
    assert [s.locator for s in merged.sources] == ["1", "2", "3"]
    assert merge_provenance(None, provenance("9")).sources[0].locator == "9"


def test_merge_interval_widens_and_tolerates_a_missing_one() -> None:
    """Catches the interval narrowing, or a missing interval erasing a present one."""
    early = Interval(valid_from=T0, valid_to=T0 + timedelta(days=1))
    late = Interval(valid_from=T0 + timedelta(days=5), valid_to=T0 + timedelta(days=6))
    assert merge_interval(early, late) == Interval(valid_from=T0, valid_to=T0 + timedelta(days=6))
    assert merge_interval(early, None) == early
    assert merge_interval(None, late) == late
    assert merge_interval(None, None) is None
