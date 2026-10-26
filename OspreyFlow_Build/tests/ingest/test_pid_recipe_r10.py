"""R10, `pid-throwover-log` (ADR-127 decision 12): one row per reported throw-over, on Brief 1's real
file, loaded after R11 (the yards) as the seed loads it. Every expectation comes from `pid_plan`.
The file's header holds no handling columns, so the recipe takes its marking from its defaults alone.
The incidents it makes are the ones R17 will link reports to, found by `incident_ref`. What a
mistake would do, and the case that catches it:

- an incident made twice, or its name, category, item or time wrong
  (`test_every_throw_over_is_one_incident_as_the_plan_holds_it`);
- a throw-over not joined to its yard, or the link without the position, yard and item the Trends
  report and the hotspot cells read (`test_every_throw_over_occurred_at_its_yard_with_its_position`);
- the per-yard counts not those the S2 spike's `cross_filter` needs, 136 of 262 in yards 03 to 06
  (`test_the_four_hotspot_yards_hold_136_of_262`), counted on the events by their yard node, which
  is what `cross_filter` groups by, and on the stored links by theirs;
- a handling column declared that the file lacks, or a marking other than the plan's
  (`test_the_marking_is_the_recipes_default_and_the_plans`);
- a re-run adding anything (`test_a_second_run_creates_nothing`)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

import pytest
from demo_fixtures import pid_plan

from tests.ingest.pid_golden_support import (
    CASE,
    PLAN,
    assert_loaded_markings,
    keys_in,
    load,
    loaded,
    marking,
    recipe_for,
    replay,
    rows_of,
)
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)
from tests.ingest.test_row_keys import KeyStore, Sink

FILE = "pid_throwover_log.csv"
BEFORE = ("pid_establishment_plan.csv",)
HOTSPOT_YARDS = {"03", "04", "05", "06"}


@pytest.fixture(scope="module")
async def throwovers() -> tuple[MergingGraph, KeyStore, Any, list[Any]]:
    graph, store, _ = await loaded(*BEFORE)
    report, events = await load(graph, FILE, Sink(store, CASE))
    assert report.rejections == [], report.rejections[:3]
    return graph, store, report, events


def _planned_links() -> list[Any]:
    _, link_keys = keys_in(FILE)
    wanted = set(link_keys)
    return [lk for lk in PLAN.links if lk.key in wanted]


def _incidents(graph: MergingGraph) -> dict[str, Any]:
    return {
        str(n.properties["incident_ref"]): n for n in graph.committed_nodes if n.type == "Incident"
    }


async def test_every_throw_over_is_one_incident_as_the_plan_holds_it(
    throwovers: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, report, _events = throwovers
    keys, _ = keys_in(FILE)
    planned = [PLAN.entity(k) for k in keys]
    stored = _incidents(graph)
    assert len(planned) == len(rows_of(FILE)) == len(stored) == report.nodes_created == 262
    assert set(stored) == {str(e.properties["incident_ref"]) for e in planned}
    for entity in planned:
        node = stored[str(entity.properties["incident_ref"])]
        for name in ("incident_ref", "category", "name", "item"):
            assert node.properties[name] == entity.properties[name], (entity.key, name)
        assert node.properties["category"] == "throw_over"
        assert (
            datetime.fromisoformat(str(node.properties["occurred_at"]))
            == entity.properties["occurred_at"]
        ), entity.key
        assert set(node.properties) == set(entity.properties), entity.key


async def test_every_throw_over_occurred_at_its_yard_with_its_position(
    throwovers: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, report, events = throwovers
    names = {
        n.id: str(n.properties.get("incident_ref", n.properties.get("site_ref")))
        for n in graph.committed_nodes
    }
    stored = {
        (names[e.source], names[e.target]): e
        for e in graph.committed_edges
        if e.type == "OCCURRED_AT" and names[e.source].startswith("pid:est1:inc:to:")
    }
    planned = {
        (
            str(PLAN.entity(lk.source).properties["incident_ref"]),
            str(PLAN.entity(lk.target).properties["site_ref"]),
        ): lk
        for lk in _planned_links()
    }
    assert set(stored) == set(planned) and len(planned) == report.edges_created == 262
    by_edge = {e.edge_id: e for e in events}
    assert len(events) == 262
    for pair, lk in planned.items():
        edge = stored[pair]
        assert edge.properties == dict(lk.properties), pair
        assert set(edge.properties) == {"lat", "lon", "yard", "item_type"}, pair
        assert edge.occurrences == lk.occurrences == 1, pair
        assert edge.interval is not None
        assert edge.interval.valid_from == edge.interval.valid_to == lk.first_seen, pair
        event = by_edge[edge.id]
        assert event.occurred_at == lk.first_seen, pair
        assert (event.lat, event.lon) == (lk.properties["lat"], lk.properties["lon"]), pair
        assert event.properties["yard"] == lk.properties["yard"], pair
        assert event.properties["item_type"] == lk.properties["item_type"], pair


async def test_the_four_hotspot_yards_hold_136_of_262(
    throwovers: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    """The S2 spike's per-yard `cross_filter` (decision 9): the four hotspot yards hold 136 of the
    262 throw-overs. `cross_filter` groups by an event's `target_id`, the yard node, and not by the
    link's `yard` property (a property a wrong target would leave untouched), so the loaded events
    are counted by their target: each yard node's count must be the plan's count for that yard, and
    the four hotspot nodes' must be 136. The live check is the coordinator's."""
    graph, _store, _report, events = throwovers
    yard_of = {
        n.id: str(n.properties["site_ref"])
        for n in graph.committed_nodes
        if n.type == "Location" and "site_ref" in n.properties
    }
    from_events = Counter(yard_of[e.target_id] for e in events)
    planned = _planned_links()
    from_plan = Counter(str(PLAN.entity(lk.target).properties["site_ref"]) for lk in planned)
    assert from_events == from_plan, "a throw-over's event is on another yard than the plan's"
    assert sum(from_events.values()) == 262
    hotspot_nodes = {
        str(PLAN.entity(lk.target).properties["site_ref"])
        for lk in planned
        if str(lk.properties["yard"]) in HOTSPOT_YARDS
    }
    assert len(hotspot_nodes) == len(HOTSPOT_YARDS)
    assert sum(from_events[ref] for ref in hotspot_nodes) == 136
    assert sum(1 for ref in from_events if ref not in hotspot_nodes) >= 1, "yards outside them"
    # The stored links name the same yard, by node, as the events do.
    from_links = Counter(
        yard_of[e.target]
        for e in graph.committed_edges
        if e.type == "OCCURRED_AT" and "yard" in e.properties
    )
    assert from_links == from_plan


async def test_the_marking_is_the_recipes_default_and_the_plans(
    throwovers: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, _report, _events = throwovers
    assert FILE not in pid_plan._COLUMN_FILES, "the plan gives this file no handling columns"
    assert not {"classification", "originator", "owning_unit"} & set(rows_of(FILE)[0])
    recipe = recipe_for(FILE)
    assert recipe.defaults.handling_columns == {}
    default = (
        recipe.defaults.handling["classification"],
        recipe.defaults.handling["handling_code"],
        None,
        None,
        recipe.defaults.handling["originator"],
        recipe.defaults.handling["owning_unit"],
    )
    keys, _ = keys_in(FILE)
    for key in keys:
        assert marking(PLAN.entity(key).handling) == default, key
    for lk in _planned_links():
        assert marking(lk.handling) == default, lk.key
    stored = [n for n in graph.committed_nodes if n.type == "Incident"]
    assert stored and all(marking(n.handling) == default for n in stored)
    assert all(
        marking(e.handling) == default
        for e in graph.committed_edges
        if e.type == "OCCURRED_AT" and e.properties.get("yard")
    )
    # And as the plan's rows replayed in the seed's order give it, for everything stored, the
    # estate's places included; none of this file's own elements is marked other than the plan
    # has it.
    differing = assert_loaded_markings(graph, replay(*BEFORE, FILE))
    keys, link_keys = keys_in(FILE)
    assert not set(keys) & set(differing.nodes)
    assert not set(link_keys) & set(differing.links)


async def test_a_second_run_creates_nothing(
    throwovers: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, store, _report, _events = throwovers
    before = (len(graph.committed_nodes), len(graph.committed_edges))
    second, events = await load(graph, FILE, Sink(store, CASE), "load-2")
    assert second.rows_already_loaded == len(rows_of(FILE))
    assert (second.nodes_created, second.edges_created, events) == (0, 0, [])
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == before
