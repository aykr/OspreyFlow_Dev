"""ADR-102 Amendment 3, the ordinary write path: `upsert_edges` merges a write into an existing link
of the same type between the same two nodes only when both have one audience, and otherwise stores a
link of its own, with its own id. The adapter runs here over the in-memory store of `edge_store.py`
(which holds several links per pair, as the real store now can); the same cases run against ArcadeDB
in `tests/conformance/graph_port/test_suite.py`. What a mistake would do, and the case that catches it:

- a SECRET write merged onto an OFFICIAL link, so the OFFICIAL reader's link vanishes and their path
  and degree move (`test_a_stricter_write_is_a_link_of_its_own`);
- a write for another unit absorbed into a link restricted to the first
  (`test_writes_under_two_restricted_units_are_two_links`);
- a write in another case's dataset absorbed, carrying its occurrences into this case's count
  (`test_writes_in_two_datasets_are_two_links`);
- an unrestricted write split by unit, a split nobody asked for
  (`test_two_unrestricted_codes_with_different_units_still_merge`)."""

from __future__ import annotations

import asyncio
from typing import Any

from schemas.domain import EdgeWrite
from tests.adapters.graph_arcadedb.edge_store import CountingStore, make_adapter, make_edge


def _write(n: int, **changes: Any) -> EdgeWrite:
    base = make_edge("a", "b", n)
    handling = base.handling.model_copy(
        update={k: changes.pop(k) for k in list(changes) if k in Handling_FIELDS}
    )
    return base.model_copy(update={"handling": handling, **changes})


Handling_FIELDS = ("classification", "handling_code", "originator", "owning_unit")


def _store_after(*writes: EdgeWrite) -> tuple[CountingStore, list[str]]:
    store = CountingStore()
    graph = make_adapter(store)
    ids: list[str] = []
    for write in writes:
        ids.extend(asyncio.run(graph.upsert_edges([write], "tx")))
    return store, ids


def test_two_writes_with_one_marking_make_one_link_with_two_occurrences() -> None:
    store, ids = _store_after(_write(1), _write(2))
    assert len(store.links) == 1 and ids[0] == ids[1]
    assert store.links[0]["occurrences"] == 2


def test_a_stricter_write_is_a_link_of_its_own() -> None:
    store, ids = _store_after(_write(1), _write(2, classification="SECRET"))
    assert len(store.links) == 2 and ids[0] != ids[1]
    assert [link["handling_classification"] for link in store.links] == ["OFFICIAL", "SECRET"]
    assert [link["occurrences"] for link in store.links] == [1, 1]


def test_a_laxer_write_is_a_link_of_its_own_too() -> None:
    store, ids = _store_after(_write(1, classification="SECRET"), _write(2))
    assert len(store.links) == 2 and ids[0] != ids[1]


def test_a_different_handling_code_is_a_link_of_its_own() -> None:
    store, _ = _store_after(_write(1), _write(2, handling_code="C"))
    assert len(store.links) == 2


def test_writes_under_two_restricted_units_are_two_links() -> None:
    store, ids = _store_after(
        _write(1, handling_code="R", owning_unit="unit-1", originator="unit-1"),
        _write(2, handling_code="R", owning_unit="unit-2", originator="unit-2"),
        _write(3, handling_code="R", owning_unit="unit-1", originator="unit-1"),
    )
    assert len(store.links) == 2
    assert ids[0] == ids[2] != ids[1], "the same restricted audience still merges"
    assert [(link["owning_unit"], link["occurrences"]) for link in store.links] == [
        ("unit-1", 2),
        ("unit-2", 1),
    ]


def test_two_unrestricted_codes_with_different_units_still_merge() -> None:
    for code in ("P", "C"):
        store, ids = _store_after(
            _write(1, handling_code=code, owning_unit="unit-1"),
            _write(2, handling_code=code, owning_unit="unit-2", originator="unit-3"),
        )
        assert len(store.links) == 1 and ids[0] == ids[1]


def test_writes_in_two_datasets_are_two_links() -> None:
    store, ids = _store_after(
        _write(1, datasets=["enron"]),
        _write(2, datasets=["fixture"]),
        _write(3, datasets=["enron"]),
        _write(4, datasets=["fixture", "enron"]),
    )
    assert len(store.links) == 3, "enron, fixture, and both"
    assert ids[0] == ids[2] and len({ids[0], ids[1], ids[3]}) == 3
    by_datasets = {tuple(link["datasets"]): link["occurrences"] for link in store.links}
    assert by_datasets == {("enron",): 2, ("fixture",): 1, ("enron", "fixture"): 1}


def test_a_write_merges_into_the_link_of_its_own_audience_among_several() -> None:
    store, ids = _store_after(
        _write(1), _write(2, classification="SECRET"), _write(3), _write(4, classification="SECRET")
    )
    assert len(store.links) == 2
    assert ids[0] == ids[2] and ids[1] == ids[3] and ids[0] != ids[1]
    assert [link["occurrences"] for link in store.links] == [2, 2]


def test_a_merge_still_never_lowers_the_parts_that_decide_no_audience() -> None:
    from schemas.domain import Handling

    first = _write(1)
    stricter_action = first.model_copy(
        update={"handling": Handling(**{**first.handling.model_dump(), "action_code": "A2"})}
    )
    store, _ = _store_after(stricter_action, _write(2))
    assert len(store.links) == 1
    assert store.links[0]["handling"]["action_code"] == "A2"


# --- a link id is unique, and some writers fix it ------------------------------------------------
#
# `HOLDS` (`{document}:held-by:{holder}`), a confirmed or an email mention and the seeders' pairs
# send an id derived from their ends. Edge `id` is UNIQUE per type, so when a link of another
# audience already holds the id the write cannot create under it: it is a link of its own under a new
# id, which the call returns. The in-memory store refuses a duplicate id as the real index does.


def test_a_fixed_id_write_in_another_audience_is_a_link_of_its_own_under_a_new_id() -> None:
    store, ids = _store_after(
        _write(1, id="doc:held-by:a"), _write(2, id="doc:held-by:a", classification="SECRET")
    )
    assert ids[0] == "doc:held-by:a" and ids[1] != "doc:held-by:a"
    assert len(store.links) == 2 and len({link["id"] for link in store.links}) == 2


def test_a_fixed_id_write_in_the_same_audience_merges_and_keeps_its_id() -> None:
    store, ids = _store_after(_write(1, id="doc:held-by:a"), _write(2, id="doc:held-by:a"))
    assert ids == ["doc:held-by:a", "doc:held-by:a"] and len(store.links) == 1
    assert store.links[0]["occurrences"] == 2


def test_a_fixed_id_write_after_the_link_was_reverted_gets_a_new_id() -> None:
    """A reverted link is not merged into, but it still holds its id."""
    store, _ = _store_after(_write(1, id="doc:held-by:a"))
    store.links[0]["reverted"] = True
    graph = make_adapter(store)
    (second,) = asyncio.run(graph.upsert_edges([_write(2, id="doc:held-by:a")], "tx"))
    assert second != "doc:held-by:a" and len(store.links) == 2


def test_a_superseded_link_is_not_merged_into() -> None:
    store, _ = _store_after(_write(1))
    store.links[0]["superseded_by"] = "replacement"
    graph = make_adapter(store)
    (second,) = asyncio.run(graph.upsert_edges([_write(2)], "tx"))
    assert second == "edge-2" and len(store.links) == 2


def _link_of(n: int, *, revision: int, created: str) -> dict[str, Any]:
    """A stored link as the store holds it, for a pair that already has one of the audience."""
    store, _ = _store_after(_write(n))
    link = dict(store.links[0])
    link["audit"] = {**link["audit"], "revision": revision, "created_at": created}
    return link


def test_with_two_links_of_one_audience_a_write_merges_into_the_newest_by_revision_then_creation() -> None:
    """`supersede_edge` can put a replacement beside a live link of the same audience, so the pair
    holds two. The write goes to one of them deterministically: the higher revision, then the later
    creation, then the id; never whichever the store happens to return first."""
    for order in ((0, 1), (1, 0)):
        store = CountingStore()
        graph = make_adapter(store)
        older = _link_of(1, revision=1, created="2026-01-01T00:00:00+00:00")
        newer = _link_of(2, revision=3, created="2026-01-01T00:00:00+00:00")
        for link in (older, newer):
            link["_src"], link["_tgt"] = "a", "b"
        store.links = [(older, newer)[i] for i in order]
        (merged_into,) = asyncio.run(graph.upsert_edges([_write(9)], "tx"))
        assert merged_into == "edge-2", order
    same_revision = [
        _link_of(1, revision=2, created="2026-01-01T00:00:00+00:00"),
        _link_of(2, revision=2, created="2026-03-01T00:00:00+00:00"),
    ]
    for order in ((0, 1), (1, 0)):
        store = CountingStore()
        graph = make_adapter(store)
        for link in same_revision:
            link["_src"], link["_tgt"] = "a", "b"
        store.links = [same_revision[i] for i in order]
        (merged_into,) = asyncio.run(graph.upsert_edges([_write(9)], "tx"))
        assert merged_into == "edge-2", order


def test_a_new_links_id_is_checked_against_the_types_unique_index_not_by_a_scan() -> None:
    """The adapter asks whether an id is held for every link it creates, so the question must be
    answered by the type's unique `id` index (`SELECT id FROM <type> WHERE id IN :ids`, as the
    by-id reads are) and not by a Gremlin traversal that may scan the type."""
    store, _ = _store_after(_write(1), _write(2, classification="SECRET"))
    assert store.sql_sent, "an id check was sent"
    for command, params in store.sql_sent:
        assert command == "SELECT id FROM `mx_TRANSACTED` WHERE id IN :ids"
        assert set(params) == {"ids"} and len(params["ids"]) == 1
    assert not [q for q in store.queries if 'has("id"' in q and "count()" in q]
