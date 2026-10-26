"""R14, `pid-nomis-cell-stays` (ADR-127 decision 12, decision 11): where each prisoner slept, as spans,
on Brief 1's real file, loaded after R11 (the cells) and R1 (the prisoners) as the seed loads them.
Every expectation comes from `pid_plan`. What a mistake would do, and the case that catches it:

- a stay that is not a link between that prisoner and that cell, or a prisoner or cell made here when
  they should be found (`test_every_stay_is_a_present_at_link_between_the_prisoner_and_the_cell`);
- a stay's start or end other than the plan's, or a running stay closed, or a closed one left open
  (`test_every_stay_has_the_plans_interval`);
- a stay at a marking other than the plan's (`test_every_stay_carries_the_plans_marking`);
- a stay's link event not at its start (`test_each_stay_has_one_event_at_its_start`);
- a re-run adding anything (`test_a_second_run_creates_nothing`)."""

from __future__ import annotations

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

FILE = "pid_nomis_cell_stays.csv"
BEFORE = ("pid_establishment_plan.csv", "pid_nomis_prisoners.csv")


@pytest.fixture
async def stays() -> tuple[MergingGraph, KeyStore, Any, Any, tuple[int, int]]:
    graph, store, _ = await loaded(*BEFORE)
    before = (len(graph.committed_nodes), len(graph.committed_edges))
    report, events = await load(graph, FILE, Sink(store, CASE))
    assert report.rejections == [], report.rejections[:3]
    return graph, store, report, events, before


def _planned() -> list[Any]:
    _, link_keys = keys_in(FILE)
    wanted = set(link_keys)
    return [lk for lk in PLAN.links if lk.key in wanted]


def _ref(entity: Any) -> str:
    return str(entity.properties.get("prison_number", entity.properties.get("site_ref")))


def _stored(graph: MergingGraph) -> dict[tuple[str, str], Any]:
    names = {
        n.id: str(n.properties.get("prison_number", n.properties.get("site_ref")))
        for n in graph.committed_nodes
    }
    return {
        (names[e.source], names[e.target]): e for e in graph.committed_edges if e.type == "PRESENT_AT"
    }


async def test_every_stay_is_a_present_at_link_between_the_prisoner_and_the_cell(
    stays: tuple[MergingGraph, KeyStore, Any, Any, tuple[int, int]],
) -> None:
    graph, _store, report, _events, before = stays
    planned = {(_ref(PLAN.entity(lk.source)), _ref(PLAN.entity(lk.target))) for lk in _planned()}
    assert len(planned) == len(_planned()) == len(rows_of(FILE)), "one row per stay"
    assert set(_stored(graph)) == planned
    assert report.edges_created == len(planned)
    assert len(graph.committed_nodes) == before[0], "both ends are found, never made here"
    assert report.nodes_created == 0


async def test_every_stay_has_the_plans_interval(
    stays: tuple[MergingGraph, KeyStore, Any, Any, tuple[int, int]],
) -> None:
    graph, _store, _report, _events, _before = stays
    stored = _stored(graph)
    running = 0
    for lk in _planned():
        edge = stored[(_ref(PLAN.entity(lk.source)), _ref(PLAN.entity(lk.target)))]
        assert edge.occurrences == lk.occurrences == 1, lk.key
        assert edge.interval is not None
        assert edge.interval.valid_from == _start_of(lk.first_seen), lk.key
        want_end = None if lk.last_seen is None else _end_of(lk.last_seen)
        assert edge.interval.valid_to == want_end, lk.key
        running += want_end is None
    assert 0 < running < len(stored), "the plan has stays running and stays that ended"


async def test_every_stay_carries_the_plans_marking(
    stays: tuple[MergingGraph, KeyStore, Any, Any, tuple[int, int]],
) -> None:
    graph, _store, _report, _events, _before = stays
    stored = _stored(graph)
    seen = set()
    for lk in _planned():
        edge = stored[(_ref(PLAN.entity(lk.source)), _ref(PLAN.entity(lk.target)))]
        assert marking(edge.handling) == marking(lk.handling), lk.key
        seen.add(edge.handling.owning_unit)
    assert len(seen) > 1, "more than one marking in the file"


async def test_each_stay_has_one_event_at_its_start(
    stays: tuple[MergingGraph, KeyStore, Any, Any, tuple[int, int]],
) -> None:
    graph, _store, _report, events, _before = stays
    assert sorted(ev.occurred_at for ev in events) == sorted(
        e.interval.valid_from for e in _stored(graph).values() if e.interval
    )


async def test_a_second_run_creates_nothing(
    stays: tuple[MergingGraph, KeyStore, Any, Any, tuple[int, int]],
) -> None:
    graph, store, _report, _events, _before = stays
    before = (len(graph.committed_nodes), len(graph.committed_edges))
    second, events = await load(graph, FILE, Sink(store, CASE), "load-2")
    assert second.rows_already_loaded == len(rows_of(FILE))
    assert (second.nodes_created, second.edges_created, events) == (0, 0, [])
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == before
