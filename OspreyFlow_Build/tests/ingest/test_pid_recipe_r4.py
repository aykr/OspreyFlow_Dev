"""R4, `pid-nomis-incidents` (ADR-127 decision 12): incidents, one row per participant, on Brief 1's
real file, loaded after R11 (the areas) and R1 (the prisoners) as the seed loads them. Every
expectation comes from `pid_plan`. What a mistake would do, and the case that catches it:

- an incident made once per participant, or its category, name, time or item wrong, or an item
  written for an incident that has none (`test_every_incident_is_made_once_as_the_plan_holds_it`);
- a participant not linked to the incident with their own role, or the link not at the incident's time
  (`test_every_participant_is_a_role_in_link_with_their_role_at_the_incident_time`);
- an incident not joined to its area (`test_every_incident_occurred_at_its_area`);
- an incident, a role or an area link at a marking other than the plan's
  (`test_every_incident_and_link_carries_the_plans_marking`);
- a re-run adding anything (`test_a_second_run_creates_nothing`)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from demo_fixtures.pid_plan import _start_of

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

FILE = "pid_nomis_incidents.csv"
BEFORE = ("pid_establishment_plan.csv", "pid_nomis_prisoners.csv")


@pytest.fixture(scope="module")
async def incidents() -> tuple[MergingGraph, KeyStore, Any, list[Any]]:
    graph, store, _ = await loaded(*BEFORE)
    before = len(graph.committed_nodes)
    report, events = await load(graph, FILE, Sink(store, CASE))
    assert report.rejections == [], report.rejections[:3]
    assert len(graph.committed_nodes) - before == report.nodes_created
    return graph, store, report, events


def _planned_incidents() -> list[Any]:
    keys, _ = keys_in(FILE)
    return [PLAN.entity(k) for k in keys]


def _planned_links(link_type: str) -> list[Any]:
    _, link_keys = keys_in(FILE)
    wanted = set(link_keys)
    return [lk for lk in PLAN.links if lk.key in wanted and lk.link_type == link_type]


def _instant(value: Any) -> datetime:
    return value if isinstance(value, datetime) else _start_of(value)


def _node_names(graph: MergingGraph) -> dict[str, str]:
    return {
        n.id: str(
            n.properties.get(
                "incident_ref", n.properties.get("prison_number", n.properties.get("site_ref"))
            )
        )
        for n in graph.committed_nodes
    }


def _incident_nodes(graph: MergingGraph) -> dict[str, Any]:
    return {str(n.properties["incident_ref"]): n for n in graph.committed_nodes if n.type == "Incident"}


async def test_every_incident_is_made_once_as_the_plan_holds_them(
    incidents: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, report, _events = incidents
    planned = _planned_incidents()
    stored = _incident_nodes(graph)
    assert set(stored) == {str(e.properties["incident_ref"]) for e in planned}
    assert report.nodes_created == len(planned) < len(rows_of(FILE)), "one incident, several rows"
    for entity in planned:
        node = stored[str(entity.properties["incident_ref"])]
        for name in ("incident_ref", "category", "name"):
            assert node.properties[name] == entity.properties[name], (entity.key, name)
        if "item" in entity.properties:
            assert node.properties["item"] == entity.properties["item"], entity.key
        else:
            assert "item" not in node.properties, entity.key
        assert datetime.fromisoformat(str(node.properties["occurred_at"])) == _instant(
            entity.properties["occurred_at"]
        ), entity.key
    assert any("item" in e.properties for e in planned), "the plan has finds"


async def test_every_participant_is_a_role_in_link_with_their_role_at_the_incident_time(
    incidents: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, _report, _events = incidents
    names = _node_names(graph)
    stored = {
        (names[e.source], names[e.target]): e for e in graph.committed_edges if e.type == "ROLE_IN"
    }
    planned = {
        (
            str(PLAN.entity(lk.source).properties["prison_number"]),
            str(PLAN.entity(lk.target).properties["incident_ref"]),
        ): lk
        for lk in _planned_links("ROLE_IN")
    }
    assert set(stored) == set(planned) and len(planned) == len(rows_of(FILE))
    for pair, lk in planned.items():
        edge = stored[pair]
        assert edge.properties == dict(lk.properties), pair
        assert edge.occurrences == lk.occurrences == 1, pair
        assert edge.interval is not None
        assert edge.interval.valid_from == edge.interval.valid_to == _instant(lk.first_seen), pair


async def test_every_incident_occurred_at_its_area(
    incidents: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, report, events = incidents
    names = _node_names(graph)
    stored = {
        (names[e.source], names[e.target]): e
        for e in graph.committed_edges
        if e.type == "OCCURRED_AT"
    }
    planned = {
        (
            str(PLAN.entity(lk.source).properties["incident_ref"]),
            str(PLAN.entity(lk.target).properties["site_ref"]),
        ): lk
        for lk in _planned_links("OCCURRED_AT")
    }
    assert set(stored) == set(planned)
    assert report.edges_created == len(planned) + len(_planned_links("ROLE_IN"))
    participants: dict[str, int] = {}
    for row in rows_of(FILE):
        participants[row["incident_ref"]] = participants.get(row["incident_ref"], 0) + 1
    for pair, lk in planned.items():
        interval = stored[pair].interval
        assert interval is not None, pair
        assert interval.valid_from == interval.valid_to == _instant(lk.first_seen), pair
        # The plan counts a carried link by the rows that carry it (ADR-120 Amendment 9 decision 1):
        # an incident occurred at its area once for each participant row, so the link holds that
        # many occurrences, and no more than the rows it rides on.
        assert stored[pair].occurrences == lk.occurrences == participants[pair[0]], pair
    # Each row is an occurrence of both of its links: two events a row.
    assert len(events) == 2 * len(rows_of(FILE))


async def test_every_incident_and_link_carries_the_plans_marking(
    incidents: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, _report, _events = incidents
    stored = _incident_nodes(graph)
    for entity in _planned_incidents():
        node = stored[str(entity.properties["incident_ref"])]
        assert marking(node.handling) == marking(entity.handling), entity.key
    names = _node_names(graph)
    units = set()
    for link_type, end in (("ROLE_IN", "incident_ref"), ("OCCURRED_AT", "site_ref")):
        edges = {
            (names[e.source], names[e.target]): e
            for e in graph.committed_edges
            if e.type == link_type
        }
        for lk in _planned_links(link_type):
            source = PLAN.entity(lk.source).properties
            pair = (
                str(source.get("prison_number", source.get("incident_ref"))),
                str(PLAN.entity(lk.target).properties[end]),
            )
            assert marking(edges[pair].handling) == marking(lk.handling), lk.key
            units.add(edges[pair].handling.owning_unit)
    assert len(units) > 1


async def test_a_second_run_creates_nothing(
    incidents: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, store, _report, _events = incidents
    before = (len(graph.committed_nodes), len(graph.committed_edges))
    second, events = await load(graph, FILE, Sink(store, CASE), "load-2")
    assert second.rows_already_loaded == len(rows_of(FILE))
    assert (second.nodes_created, second.edges_created, events) == (0, 0, [])
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == before
