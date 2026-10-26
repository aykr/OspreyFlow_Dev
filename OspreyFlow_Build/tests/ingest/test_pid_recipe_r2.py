"""R2, `pid-nomis-cell-shares` (ADR-127 decision 12): which prisoners shared a cell, one row per pair
per week, on Brief 1's real file, loaded after R11 and R1 as the seed loads them. Every expectation
comes from `pid_plan`. The graph stand-in keeps the first of a pair's links and does not add
occurrences (the adapter does, and the conformance suites prove it), so a link's occurrences are
asserted as the events its rows wrote, one per week, and its interval as the first and last of them.
What a mistake would do, and the case that catches it:

- a pair not linked, or linked twice, or a link of another kind or direction
  (`test_every_pair_is_one_shared_cell_with_link_between_the_two_prisoners`);
- a week lost or a duplicate week kept, so the occurrences are not the weeks the plan says
  (`test_a_pairs_events_are_its_weeks_from_the_first_to_the_last`);
- the cell not on the link (`test_the_link_names_the_cell`);
- a link at a marking other than the plan's (`test_every_link_carries_the_plans_marking`);
- a re-run adding anything (`test_a_second_run_creates_nothing`)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pytest
from demo_fixtures import pid_plan

from tests.ingest.pid_golden_support import (
    CASE,
    PLAN,
    assert_exact_instants,
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

FILE = "pid_nomis_cell_shares.csv"
BEFORE = ("pid_establishment_plan.csv", "pid_nomis_prisoners.csv")


@pytest.fixture(scope="module")
async def shares() -> tuple[MergingGraph, KeyStore, Any, list[Any]]:
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


def _names(graph: MergingGraph) -> dict[str, str]:
    return {n.id: str(n.properties["prison_number"]) for n in graph.committed_nodes if n.type == "Person"}


def _pair(a: str, b: str) -> frozenset[str]:
    return frozenset((a, b))


async def test_every_pair_is_one_shared_cell_with_link_between_the_two_prisoners(
    shares: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, report, _events = shares
    names = _names(graph)
    stored = [e for e in graph.committed_edges if e.type == "SHARED_CELL_WITH"]
    planned = {_pair(_number(lk.source), _number(lk.target)) for lk in _planned()}
    assert len(stored) == len(planned) == len(_planned()) == report.edges_created
    assert {_pair(names[e.source], names[e.target]) for e in stored} == planned
    assert report.nodes_created == 0, "both people are found, never made here"


async def test_a_pairs_events_are_its_weeks_from_the_first_to_the_last(
    shares: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, _report, events = shares
    names = _names(graph)
    by_pair: dict[frozenset[str], list[Any]] = defaultdict(list)
    for event in events:
        by_pair[_pair(names[event.source_id], names[event.target_id])].append(event.occurred_at)
    assert len(events) == sum(lk.occurrences for lk in _planned()) == len(rows_of(FILE))
    for lk in _planned():
        weeks = sorted(by_pair[_pair(_number(lk.source), _number(lk.target))])
        assert len(weeks) == lk.occurrences, lk.key
        assert len(set(weeks)) == len(weeks), f"{lk.key}: a week twice"
        # The plan's own instants for the link, exactly (not a bound on them).
        assert_exact_instants(lk, weeks)


async def test_every_link_has_the_plans_occurrences_interval_and_cell(
    shares: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    """The stand-in merges a repeated pair as the adapter does (`merge_*` in `schemas.merge`): the
    link holds every week as an occurrence and runs from the first week's row to the last. The cell
    the plan gives a pair is the cell on every one of its rows, so `merge_properties` (the latest
    write's properties win) leaves exactly that."""
    graph, _store, _report, events = shares
    names = _names(graph)
    stored = {
        _pair(names[e.source], names[e.target]): e
        for e in graph.committed_edges
        if e.type == "SHARED_CELL_WITH"
    }
    instants: dict[frozenset[str], list[Any]] = defaultdict(list)
    for event in events:
        instants[_pair(names[event.source_id], names[event.target_id])].append(event.occurred_at)
    cells: dict[frozenset[str], set[str]] = defaultdict(set)
    for row in rows_of(FILE):
        cells[_pair(row["nomis_id_a"], row["nomis_id_b"])].add(row["cell_ref"])
    for lk in _planned():
        pair = _pair(_number(lk.source), _number(lk.target))
        edge = stored[pair]
        assert edge.occurrences == lk.occurrences, lk.key
        assert edge.interval is not None
        assert edge.interval.valid_from == min(instants[pair]), lk.key
        assert edge.interval.valid_to == max(instants[pair]), lk.key
        planned_instants = pid_plan.link_instants(PLAN, lk)
        assert edge.interval.valid_from == min(planned_instants), lk.key
        assert edge.interval.valid_to == max(planned_instants), lk.key
        assert cells[pair] == {str(lk.properties["cell"])}, f"{lk.key}: the cell varies across rows"
        assert edge.properties == dict(lk.properties), lk.key


async def test_every_link_carries_the_plans_marking(
    shares: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, _report, _events = shares
    names = _names(graph)
    stored = {
        _pair(names[e.source], names[e.target]): e
        for e in graph.committed_edges
        if e.type == "SHARED_CELL_WITH"
    }
    units = set()
    for lk in _planned():
        edge = stored[_pair(_number(lk.source), _number(lk.target))]
        assert marking(edge.handling) == marking(lk.handling), lk.key
        units.add(edge.handling.owning_unit)
    assert len(units) > 1


async def test_a_second_run_creates_nothing(
    shares: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, store, _report, _events = shares
    before = (len(graph.committed_nodes), len(graph.committed_edges))
    second, events = await load(graph, FILE, Sink(store, CASE), "load-2")
    assert second.rows_already_loaded == len(rows_of(FILE))
    assert (second.nodes_created, second.edges_created, events) == (0, 0, [])
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == before
