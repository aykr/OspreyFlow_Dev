"""R15, `pid-nomis-conflicts` (ADR-127 decision 12): which prisoners are in conflict, one row per
sighting, on Brief 1's real file, loaded after R11 and R1. Every expectation comes from `pid_plan`.
Every link is OFFICIAL (ADR-120 Amendment 16 removed the one conflict known from a covert source,
which was SECRET). The graph stand-in does not filter a read by access (the adapter does, and its
own tests prove it), so the access case below holds each stored link's marking to the plan's and
asks the same pure predicate the adapter compiles into its traversal (`principal_may_view`) whether
an OFFICIAL-cleared principal may see it. It is not a test of the adapter's filter. What a mistake
would do, and the case that catches it:

- a pair not linked, or linked twice, or with the wrong reason
  (`test_every_pair_is_one_in_conflict_with_link_with_its_reason`);
- a sighting lost, so the occurrences are not the plan's
  (`test_a_pairs_events_are_its_sightings_from_the_first_to_the_last`);
- a link loaded above OFFICIAL, so the demo analyst could not see it, or the removed covert-source
  link back in the file (`test_every_link_is_official_and_the_demo_analyst_sees_every_one`);
- a link at a marking other than the plan's (`test_every_link_carries_the_plans_marking`);
- a re-run adding anything (`test_a_second_run_creates_nothing`)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pytest

from ontology.handling import principal_may_view
from schemas.domain import Principal
from tests.ingest.pid_golden_support import (
    CASE,
    PLAN,
    SCHEME,
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

FILE = "pid_conflicts.csv"
BEFORE = ("pid_establishment_plan.csv", "pid_nomis_prisoners.csv")


@pytest.fixture(scope="module")
async def conflicts() -> tuple[MergingGraph, KeyStore, Any, list[Any]]:
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
    return {
        n.id: str(n.properties["prison_number"])
        for n in graph.committed_nodes
        if n.type == "Person"
    }


def _pair(a: str, b: str) -> frozenset[str]:
    return frozenset((a, b))


def _stored(graph: MergingGraph) -> dict[frozenset[str], Any]:
    names = _names(graph)
    return {
        _pair(names[e.source], names[e.target]): e
        for e in graph.committed_edges
        if e.type == "IN_CONFLICT_WITH"
    }


async def test_every_pair_is_one_in_conflict_with_link_with_its_reason(
    conflicts: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, report, _events = conflicts
    stored = _stored(graph)
    planned = {_pair(_number(lk.source), _number(lk.target)): lk for lk in _planned()}
    assert set(stored) == set(planned)
    assert len(stored) == len(planned) == report.edges_created
    assert len(rows_of(FILE)) > len(planned), "a pair seen more than once"
    assert report.nodes_created == 0, "both people are found, never made here"
    reasons: dict[frozenset[str], set[str]] = defaultdict(set)
    for row in rows_of(FILE):
        reasons[_pair(row["nomis_id_a"], row["nomis_id_b"])].add(row["reason"])
    for pair, lk in planned.items():
        assert stored[pair].properties == dict(lk.properties), pair
        assert reasons[pair] == {str(lk.properties["reason"])}, f"{pair}: the reason varies"


async def test_a_pairs_events_are_its_sightings_from_the_first_to_the_last(
    conflicts: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, _report, events = conflicts
    names = _names(graph)
    by_pair: dict[frozenset[str], list[Any]] = defaultdict(list)
    for event in events:
        by_pair[_pair(names[event.source_id], names[event.target_id])].append(event.occurred_at)
    stored = _stored(graph)
    assert len(events) == sum(lk.occurrences for lk in _planned()) == len(rows_of(FILE))
    for lk in _planned():
        pair = _pair(_number(lk.source), _number(lk.target))
        seen = sorted(by_pair[pair])
        assert len(seen) == lk.occurrences, lk.key
        assert_exact_instants(lk, seen)
        edge = stored[pair]
        assert edge.occurrences == lk.occurrences, lk.key
        assert edge.interval is not None
        assert edge.interval.valid_from == seen[0], lk.key
        assert edge.interval.valid_to == seen[-1], lk.key


async def test_every_link_is_official_and_the_demo_analyst_sees_every_one(
    conflicts: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, _report, _events = conflicts
    stored = _stored(graph)
    planned = _planned()
    assert planned and len(stored) == len(planned)
    assert {lk.handling.classification for lk in planned} == {"OFFICIAL"}
    assert "covert source" not in {lk.properties["reason"] for lk in planned}
    assert "covert source" not in {row["reason"] for row in rows_of(FILE)}
    official = Principal(
        id="analyst-official", clearance="OFFICIAL", org_unit="fenwick-moor-security",
        receivable_handling_codes=["P", "C"],
    )  # fmt: skip
    for pair, edge in stored.items():
        assert edge.handling.classification == "OFFICIAL", pair
        assert principal_may_view(edge.handling, official, SCHEME), pair


async def test_every_link_carries_the_plans_marking(
    conflicts: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, _report, _events = conflicts
    stored = _stored(graph)
    classes = set()
    for lk in _planned():
        edge = stored[_pair(_number(lk.source), _number(lk.target))]
        assert marking(edge.handling) == marking(lk.handling), lk.key
        classes.add(edge.handling.classification)
    assert classes == {"OFFICIAL"}


async def test_a_second_run_creates_nothing(
    conflicts: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, store, _report, _events = conflicts
    before = (len(graph.committed_nodes), len(graph.committed_edges))
    second, events = await load(graph, FILE, Sink(store, CASE), "load-2")
    assert second.rows_already_loaded == len(rows_of(FILE))
    assert (second.nodes_created, second.edges_created, events) == (0, 0, [])
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == before
