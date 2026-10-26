"""ADR-127 Amendment 19: an `EdgeWrite` carries `writes`, the count of writes it stands for.

The engine combines a run's writes to one link before it writes them, so the stored revision (which
counts the writes merged into a link, and which ADR-102 Amendment 4's choice among a pair's links
reads) is only what one-write-at-a-time leaves if the combined write says how many it stands for.
These are the pure cases of the port change; the same invariants against a real ArcadeDB are in
`tests/conformance/graph_port/test_suite.py` and `test_bulk_loader.py`, which need a live store. The
stand-in here is `CountingStore`, which models the adapter's own merge reads and writes.
"""

from __future__ import annotations

import asyncio

import pytest

from ontology.errors import OntologyError
from ontology.handling import audience_of, load_uk_le_scheme, merge_handling
from schemas.domain import EdgeWrite
from schemas.merge import aggregate_edge_writes
from tests.adapters.graph_arcadedb.edge_store import CountingStore, make_adapter, make_edge


def _writes(n: int, source: str = "a", target: str = "b", *, count: int = 1) -> EdgeWrite:
    return make_edge(source, target, n).model_copy(update={"writes": count})


def _fold(writes: list[EdgeWrite]) -> list[EdgeWrite]:
    scheme = load_uk_le_scheme()
    return [
        a.write
        for a in aggregate_edge_writes(
            writes,
            directed=lambda _: True,
            handling=lambda old, new: merge_handling(old, new, scheme),
            audience=lambda w: audience_of(w.handling, w.datasets, scheme),
        )
    ]


def test_a_link_created_with_writes_n_holds_revision_n() -> None:
    """Catches `upsert_edges` storing a new link at revision 1 whatever `writes` says."""
    store = CountingStore()
    asyncio.run(make_adapter(store).upsert_edges([_writes(1, count=3)], "tx"))
    assert store.edges[("a", "b")]["audit"]["revision"] == 3


def test_a_merge_adds_writes_to_the_stored_revision() -> None:
    """Catches a merge adding 1 whatever `writes` says: 2, then 4, then a plain write is 7."""
    store = CountingStore()
    graph = make_adapter(store)
    for write in (_writes(1, count=2), _writes(2, count=4)):
        asyncio.run(graph.upsert_edges([write], "tx"))
    assert store.edges[("a", "b")]["audit"]["revision"] == 6
    asyncio.run(graph.upsert_edges([_writes(3)], "tx"))
    assert store.edges[("a", "b")]["audit"]["revision"] == 7


def test_a_write_standing_for_fewer_than_one_is_refused_before_the_store_is_touched() -> None:
    """A link cannot be the product of no writes; nothing is read or written for the refusal."""
    store = CountingStore()
    with pytest.raises(OntologyError):
        asyncio.run(make_adapter(store).upsert_edges([_writes(1, count=0)], "tx"))
    assert store.queries == [] and store.links == []


def test_supersede_edge_refuses_a_write_standing_for_more_than_one() -> None:
    """Catches a replacement carrying a count the writer would silently ignore. The refusal comes
    before any read or write, so nothing is half-done."""
    store = CountingStore()
    with pytest.raises(OntologyError):
        asyncio.run(make_adapter(store).supersede_edge("edge-1", _writes(2, count=2), "tx"))
    assert store.queries == [] and store.links == []


def test_three_writes_folded_pairwise_give_three_and_the_fold_carries_its_count() -> None:
    """Catches the aggregate counting list items: folding one write into the held one, as the
    engine does for each row, must give the same as folding all three at once, and the folded
    write carries the count so the next fold starts from it."""
    one, two, three = _writes(1), _writes(2), _writes(3)
    (held,) = _fold([one, two])
    assert held.writes == 2
    (held,) = _fold([held, three])
    assert held.writes == 3
    (together,) = _fold([one, two, three])
    assert together.writes == 3


def test_the_aggregate_sums_each_writes_own_count_starting_from_the_firsts() -> None:
    """Catches `1 + 1` for a pair of writes that stand for 3 and 4, and a first write's own count
    being dropped: the revision of the combined link is 7."""
    (only,) = aggregate_edge_writes(
        [_writes(1, count=3), _writes(2, count=4)],
        directed=lambda _: True,
        handling=lambda old, new: merge_handling(old, new, load_uk_le_scheme()),
        audience=lambda w: audience_of(w.handling, w.datasets, load_uk_le_scheme()),
    )
    assert only.writes == 7 and only.write.writes == 7


def test_a_combined_write_leaves_the_revision_one_at_a_time_gives() -> None:
    """The invariant the engine relies on, through the adapter: five writes sent one at a time and
    the same five combined to one carrying `writes=5` leave one link with one revision."""
    singles = [_writes(n) for n in range(1, 6)]
    per_row = CountingStore()
    graph = make_adapter(per_row)
    for write in singles:
        asyncio.run(graph.upsert_edges([write], "tx"))
    combined = CountingStore()
    (folded,) = _fold(singles)
    asyncio.run(make_adapter(combined).upsert_edges([folded], "tx"))
    assert combined.edges[("a", "b")]["audit"]["revision"] == 5
    assert (
        combined.edges[("a", "b")]["audit"]["revision"]
        == per_row.edges[("a", "b")]["audit"]["revision"]
    )


def test_an_edge_write_standing_for_fewer_than_one_cannot_be_built() -> None:
    """Amendment 21: `writes` is at least 1 on the model itself, so a write of none is refused
    where it is made, before any writer sees it."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        EdgeWrite.model_validate({**make_edge("a", "b", 1).model_dump(), "writes": 0})
