"""R13, `pid-family-and-associates` (ADR-127 decision 12): who is family of whom and who is an
associate of whom, on Brief 1's real file, loaded after R11 and R1. Every expectation comes from
`pid_plan`. The file's `kind` column holds the link type, so the recipe writes two edges, each
gated on one kind; `relation` is the property of `FAMILY_OF` only and is blank on an associate row.
What a mistake would do, and the case that catches it:

- a pair written as the wrong kind, both kinds, or neither
  (`test_every_pair_is_the_one_link_of_its_kind_the_plan_holds`);
- a family link without its relation, or an associate link with one
  (`test_a_family_link_carries_its_relation_and_an_associate_link_none`);
- a link or an end at a marking other than the plan's
  (`test_every_link_carries_the_plans_marking`);
- a re-run adding anything (`test_a_second_run_creates_nothing`)."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pytest

from tests.ingest.pid_golden_support import (
    CASE,
    PLAN,
    keys_in,
    load,
    loaded,
    marking,
    rows_of,
)
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)
from tests.ingest.test_row_keys import KeyStore, Sink

FILE = "pid_family_and_associates.csv"
BEFORE = ("pid_establishment_plan.csv", "pid_nomis_prisoners.csv")
KINDS = ("FAMILY_OF", "ASSOCIATE_OF")


@pytest.fixture(scope="module")
async def family() -> tuple[MergingGraph, KeyStore, Any, list[Any]]:
    graph, store, _ = await loaded(*BEFORE)
    report, events = await load(graph, FILE, Sink(store, CASE))
    assert report.rejections == [], report.rejections[:3]
    return graph, store, report, events


def _planned() -> list[Any]:
    _, link_keys = keys_in(FILE)
    wanted = set(link_keys)
    return [lk for lk in PLAN.links if lk.key in wanted]


def _number(key: str) -> str:
    return str(PLAN.entity(key).properties["prison_number"])


def _stored(graph: MergingGraph) -> dict[tuple[str, frozenset[str]], Any]:
    names = {
        n.id: str(n.properties["prison_number"])
        for n in graph.committed_nodes
        if n.type == "Person"
    }
    return {
        (e.type, frozenset((names[e.source], names[e.target]))): e
        for e in graph.committed_edges
        if e.type in KINDS
    }


async def test_every_pair_is_the_one_link_of_its_kind_the_plan_holds(
    family: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, report, _events = family
    stored = _stored(graph)
    planned = {
        (lk.link_type, frozenset((_number(lk.source), _number(lk.target)))): lk for lk in _planned()
    }
    assert set(stored) == set(planned)
    assert len(stored) == len(planned) == report.edges_created == len(rows_of(FILE))
    assert {k for k, _ in stored} == set(KINDS), "the plan has both kinds"
    assert Counter(k for k, _ in stored) == Counter(lk.link_type for lk in _planned())
    assert report.nodes_created == 0, "both people are found, never made here"
    for key, edge in stored.items():
        assert edge.occurrences == planned[key].occurrences == 1, key
        assert edge.interval is None, key


async def test_a_family_link_carries_its_relation_and_an_associate_link_none(
    family: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, _report, _events = family
    stored = _stored(graph)
    for lk in _planned():
        key = (lk.link_type, frozenset((_number(lk.source), _number(lk.target))))
        assert stored[key].properties == dict(lk.properties), lk.key
        if lk.link_type == "FAMILY_OF":
            assert stored[key].properties["relation"], lk.key
        else:
            assert stored[key].properties == {}, lk.key
    assert any(r["kind"] == "ASSOCIATE_OF" and r["relation"] == "" for r in rows_of(FILE))


async def test_a_pair_that_is_both_family_and_associates_is_both_links(
    family: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    """The real file holds no pair of both kinds, so the kind in the duplicate key is proved here
    with one row planted: an associate row for a pair already written as family. Without the kind in
    the key it would be taken for a repeat of the family row and dropped."""
    graph, store, _report, _events = family
    family_row = next(r for r in rows_of(FILE) if r["kind"] == "FAMILY_OF")
    planted = {**family_row, "kind": "ASSOCIATE_OF", "relation": ""}
    report, _events = await load(graph, FILE, Sink(store, CASE), "load-both", rows=[planted])
    assert (report.rows_already_loaded, report.edges_created) == (0, 1)
    pair = frozenset((family_row["nomis_id_a"], family_row["nomis_id_b"]))
    stored = _stored(graph)
    assert ("FAMILY_OF", pair) in stored and ("ASSOCIATE_OF", pair) in stored


async def test_every_link_carries_the_plans_marking(
    family: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, _report, _events = family
    stored = _stored(graph)
    for lk in _planned():
        key = (lk.link_type, frozenset((_number(lk.source), _number(lk.target))))
        assert marking(stored[key].handling) == marking(lk.handling), lk.key


async def test_a_second_run_creates_nothing(
    family: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, store, _report, _events = family
    before = (len(graph.committed_nodes), len(graph.committed_edges))
    second, events = await load(graph, FILE, Sink(store, CASE), "load-2")
    assert second.rows_already_loaded == len(rows_of(FILE))
    assert (second.nodes_created, second.edges_created, events) == (0, 0, [])
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == before
