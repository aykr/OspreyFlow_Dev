"""R8, `pid-codefendants` (ADR-127 decision 12): who was a co-defendant of whom, on Brief 1's real
file, loaded after R11 and R1. Every expectation comes from `pid_plan`. The label carries the
caveat the source has: the extract is partial, so a missing link here is not evidence of no link.
What a mistake would do, and the case that catches it:

- a pair not linked, linked twice, or without its case reference
  (`test_every_pair_is_one_co_defendant_link_with_its_case`);
- the caveat lost from the recipe's label (`test_the_label_carries_the_partial_caveat`);
- a link at a marking other than the plan's (`test_every_link_carries_the_plans_marking`);
- a re-run adding anything (`test_a_second_run_creates_nothing`)."""

from __future__ import annotations

from typing import Any

import pytest

from tests.ingest.pid_golden_support import (
    CASE,
    PLAN,
    keys_in,
    load,
    loaded,
    marking,
    recipe_for,
    rows_of,
)
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)
from tests.ingest.test_row_keys import KeyStore, Sink

FILE = "pid_codefendants.csv"
BEFORE = ("pid_establishment_plan.csv", "pid_nomis_prisoners.csv")
CAVEAT = "Co-defendants (court case extract). Partial: a missing link here does not mean no link."


@pytest.fixture(scope="module")
async def codefendants() -> tuple[MergingGraph, KeyStore, Any, list[Any]]:
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


def _stored(graph: MergingGraph) -> dict[frozenset[str], Any]:
    names = {
        n.id: str(n.properties["prison_number"])
        for n in graph.committed_nodes
        if n.type == "Person"
    }
    return {
        frozenset((names[e.source], names[e.target])): e
        for e in graph.committed_edges
        if e.type == "CO_DEFENDANT_OF"
    }


async def test_every_pair_is_one_co_defendant_link_with_its_case(
    codefendants: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, report, _events = codefendants
    stored = _stored(graph)
    planned = {frozenset((_number(lk.source), _number(lk.target))): lk for lk in _planned()}
    assert set(stored) == set(planned)
    assert len(stored) == len(planned) == report.edges_created == len(rows_of(FILE)) == 81
    assert report.nodes_created == 0, "both people are found, never made here"
    for pair, lk in planned.items():
        assert stored[pair].properties == dict(lk.properties), pair
        assert stored[pair].properties["case_ref"], pair
        assert stored[pair].occurrences == lk.occurrences == 1, pair
        assert stored[pair].interval is None, pair


async def test_the_label_carries_the_partial_caveat() -> None:
    assert recipe_for(FILE).label == CAVEAT


async def test_every_link_carries_the_plans_marking(
    codefendants: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, _report, _events = codefendants
    stored = _stored(graph)
    for lk in _planned():
        assert marking(stored[frozenset((_number(lk.source), _number(lk.target)))].handling) == (
            marking(lk.handling)
        ), lk.key


async def test_a_second_run_creates_nothing(
    codefendants: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, store, _report, _events = codefendants
    before = (len(graph.committed_nodes), len(graph.committed_edges))
    second, events = await load(graph, FILE, Sink(store, CASE), "load-2")
    assert second.rows_already_loaded == len(rows_of(FILE))
    assert (second.nodes_created, second.edges_created, events) == (0, 0, [])
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == before
