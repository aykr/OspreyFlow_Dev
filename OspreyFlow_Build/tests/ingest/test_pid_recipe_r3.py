"""R3, `pid-nomis-visits` (ADR-127 decision 12): who visited whom, one row per visit, on Brief 1's
real file, loaded after R11 and R1 as the seed loads them. Every expectation comes from `pid_plan`.
As in R2 the graph stand-in keeps a pair's first link, so a link's occurrences are asserted as the
events its rows wrote. What a mistake would do, and the case that catches it:

- a visitor made twice, or not made, or one National Insurance number matched to another person
  (`test_every_visitor_is_made_once_as_the_plan_holds_them`);
- a visitor's date of birth or aliases lost, or an empty alias written, which is the coordinator's
  nickname `Mo` appearing on those who have none (`test_only_the_visitors_with_an_alias_carry_one`);
- a visit not linked to the prisoner visited, or a channel other than the plan's
  (`test_every_visitor_prisoner_pair_is_one_visited_link_with_its_channel`);
- a visit lost or counted twice, or its time wrong (`test_a_pairs_events_are_its_visits_from_the_first_to_the_last`);
- a visitor or a link at a marking other than the plan's (`test_every_visitor_and_link_carries_the_plans_marking`);
- a re-run adding anything (`test_a_second_run_creates_nothing`)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pytest
from demo_fixtures.pid_plan import _end_of, _start_of

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

FILE = "pid_nomis_visits.csv"
BEFORE = ("pid_establishment_plan.csv", "pid_nomis_prisoners.csv")


@pytest.fixture(scope="module")
async def visits() -> tuple[MergingGraph, KeyStore, Any, list[Any]]:
    graph, store, _ = await loaded(*BEFORE)
    report, events = await load(graph, FILE, Sink(store, CASE))
    assert report.rejections == [], report.rejections[:3]
    return graph, store, report, events


def _visitors() -> list[Any]:
    keys, _ = keys_in(FILE)
    return [PLAN.entity(k) for k in keys]


def _planned() -> list[Any]:
    _, link_keys = keys_in(FILE)
    wanted = set(link_keys)
    return [lk for lk in PLAN.links if lk.key in wanted]


def _people(graph: MergingGraph) -> dict[str, Any]:
    return {
        str(n.properties["nino"]): n
        for n in graph.committed_nodes
        if n.type == "Person" and "nino" in n.properties
    }


def _name_of(graph: MergingGraph) -> dict[str, str]:
    return {
        n.id: str(n.properties.get("nino", n.properties.get("prison_number")))
        for n in graph.committed_nodes
        if n.type == "Person"
    }


async def test_every_visitor_is_made_once_as_the_plan_holds_them(
    visits: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, report, _events = visits
    visitors = _visitors()
    stored = _people(graph)
    assert set(stored) == {str(v.properties["nino"]) for v in visitors}
    assert report.nodes_created == len(visitors), "the prisoners are found, never made here"
    for visitor in visitors:
        node = stored[str(visitor.properties["nino"])]
        for name in ("nino", "family_name", "given_names"):
            assert node.properties[name] == visitor.properties[name], (visitor.key, name)
        assert str(node.properties["date_of_birth"]) == str(visitor.properties["date_of_birth"])


async def test_only_the_visitors_with_an_alias_carry_one(
    visits: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, report, _events = visits
    stored = _people(graph)
    with_alias = [v for v in _visitors() if v.properties.get("aliases")]
    assert with_alias and len(with_alias) < len(stored) / 2
    for visitor in _visitors():
        node = stored[str(visitor.properties["nino"])]
        if visitor.properties.get("aliases"):
            assert node.properties["aliases"] == list(visitor.properties["aliases"]), visitor.key
        else:
            assert "aliases" not in node.properties, visitor.key
    assert report.rejections == []


async def test_every_visitor_prisoner_pair_is_one_visited_link_with_its_channel(
    visits: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, report, _events = visits
    names = _name_of(graph)
    stored = {
        (names[e.source], names[e.target]): e for e in graph.committed_edges if e.type == "VISITED"
    }
    planned = {
        (str(PLAN.entity(lk.source).properties["nino"]), str(PLAN.entity(lk.target).properties["prison_number"])): lk
        for lk in _planned()
    }
    assert set(stored) == set(planned) and report.edges_created == len(planned)
    for pair, lk in planned.items():
        assert stored[pair].properties == dict(lk.properties), pair
        assert stored[pair].occurrences == lk.occurrences, pair
    # The channel the plan gives a pair is the channel on every one of its rows, so the merge (the
    # latest write's properties win) leaves exactly that.
    channels: dict[tuple[str, str], set[str]] = {}
    for row in rows_of(FILE):
        channels.setdefault((row["visitor_nino"], row["nomis_id"]), set()).add(row["channel"])
    for pair, lk in planned.items():
        assert channels[pair] == {str(lk.properties["channel"])}, f"{pair}: the channel varies"


async def test_a_pairs_events_are_its_visits_from_the_first_to_the_last(
    visits: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, _report, events = visits
    names = _name_of(graph)
    by_pair: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for event in events:
        by_pair[(names[event.source_id], names[event.target_id])].append(event.occurred_at)
    assert len(events) == sum(lk.occurrences for lk in _planned()) == len(rows_of(FILE))
    for lk in _planned():
        key = (
            str(PLAN.entity(lk.source).properties["nino"]),
            str(PLAN.entity(lk.target).properties["prison_number"]),
        )
        visited = sorted(by_pair[key])
        assert len(visited) == lk.occurrences, lk.key
        assert _start_of(lk.first_seen) <= visited[0], lk.key
        if lk.occurrences > 1:
            assert visited[0] == _start_of(lk.first_seen), lk.key
        assert visited[-1] <= _end_of(lk.last_seen), lk.key
        assert visited[-1].date() == _end_of(lk.last_seen).date(), lk.key
        interval = {(names[e.source], names[e.target]): e.interval for e in graph.committed_edges if e.type == "VISITED"}[key]
        assert interval is not None
        assert (interval.valid_from, interval.valid_to) == (visited[0], visited[-1]), lk.key


async def test_every_visitor_and_link_carries_the_plans_marking(
    visits: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    """A visitor is made by the first of their rows; the plan's marking for them is that row's."""
    graph, _store, _report, _events = visits
    stored = _people(graph)
    for visitor in _visitors():
        node = stored[str(visitor.properties["nino"])]
        assert marking(node.handling) == marking(visitor.handling), visitor.key
    names = _name_of(graph)
    edges = {(names[e.source], names[e.target]): e for e in graph.committed_edges if e.type == "VISITED"}
    units = set()
    for lk in _planned():
        pair = (
            str(PLAN.entity(lk.source).properties["nino"]),
            str(PLAN.entity(lk.target).properties["prison_number"]),
        )
        assert marking(edges[pair].handling) == marking(lk.handling), lk.key
        units.add(edges[pair].handling.owning_unit)
    assert len(units) > 1


async def test_a_second_run_creates_nothing(
    visits: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, store, _report, _events = visits
    before = (len(graph.committed_nodes), len(graph.committed_edges))
    second, events = await load(graph, FILE, Sink(store, CASE), "load-2")
    assert second.rows_already_loaded == len(rows_of(FILE))
    assert (second.nodes_created, second.edges_created, events) == (0, 0, [])
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == before
