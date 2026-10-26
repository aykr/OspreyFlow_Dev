"""R11, `pid-establishment-plan` (ADR-127 decision 12): every place of the estate, on Brief 1's real
file, loaded first as the seed loads it. Every expectation comes from `pid_plan`. What a mistake would
do, and the case that catches it:

- a kind of place read as another, or a place made twice or not at all
  (`test_every_place_is_made_once_as_the_plan_holds_it`);
- a place at another marking than the plan's (`test_every_place_carries_the_plans_marking`);
- a place's point lost or invented (`test_a_place_has_a_geometry_reference_exactly_where_the_plan_has_a_point`);
- a place not joined to its parent, its zone, the wing it adjoins or the wing that uses it, or a link
  of the wrong kind or marking (`test_every_place_link_is_the_plans`);
- the zone, which a later row names before its own row, made bare so that it loses its name and point
  (`test_the_zone_has_its_name_and_point_though_other_rows_name_it`);
- a re-run adding anything (`test_a_second_run_creates_nothing`)."""

from __future__ import annotations

from typing import Any

import pytest

from knowledge_adapters import REGISTRY
from demo_fixtures import pid_plan
from tests.ingest.pid_golden_support import (
    PLAN,
    CASE,
    load,
    loaded,
    marking,
    rows_of,
    keys_in,
)
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)
from tests.ingest.test_row_keys import KeyStore, Sink

FILE = "pid_establishment_plan.csv"


@pytest.fixture
async def estate() -> tuple[MergingGraph, KeyStore, dict[str, Any]]:
    return await loaded(FILE)


def _ref(entity: Any) -> str:
    return str(entity.properties.get("establishment_ref", entity.properties.get("site_ref")))


def _planned_places() -> list[Any]:
    keys, _ = keys_in(FILE)
    return [PLAN.entity(k) for k in keys]


def _stored(graph: MergingGraph) -> dict[str, Any]:
    return {
        str(n.properties.get("establishment_ref", n.properties.get("site_ref"))): n
        for n in graph.committed_nodes
    }


async def test_every_place_is_made_once_as_the_plan_holds_it(
    estate: tuple[MergingGraph, KeyStore, dict[str, Any]],
) -> None:
    graph, _store, reports = estate
    places = _planned_places()
    stored = _stored(graph)
    assert len(graph.committed_nodes) == len(places) == reports[FILE].nodes_created
    assert set(stored) == {_ref(e) for e in places}
    for entity in places:
        node = stored[_ref(entity)]
        want_type = "Establishment" if entity.entity_type == "Establishment" else "Location"
        assert node.type == want_type, entity.key
        for name, value in entity.properties.items():
            assert node.properties[name] == value, (entity.key, name)


async def test_every_place_carries_the_plans_marking(
    estate: tuple[MergingGraph, KeyStore, dict[str, Any]],
) -> None:
    graph, _store, _reports = estate
    stored = _stored(graph)
    for entity in _planned_places():
        assert marking(stored[_ref(entity)].handling) == marking(entity.handling), entity.key
    assert len({n.handling.owning_unit for n in graph.committed_nodes}) > 1, "more than one marking"


async def test_a_place_has_a_geometry_reference_exactly_where_the_plan_has_a_point(
    estate: tuple[MergingGraph, KeyStore, dict[str, Any]],
) -> None:
    graph, _store, _reports = estate
    stored = _stored(graph)
    pointed = 0
    for entity in _planned_places():
        node = stored[_ref(entity)]
        point = pid_plan.PLACE_POINTS.get(entity.key)
        if point is None:
            assert "geometry_ref" not in node.properties, entity.key
            continue
        lat, lon = point
        want = REGISTRY["geometry_ref"]((repr(lon), repr(lat)), source_crs="EPSG:4326")
        assert node.properties["geometry_ref"] == want, entity.key
        pointed += 1
    assert pointed == len([e for e in _planned_places() if e.key in pid_plan.PLACE_POINTS]) > 0


async def test_the_zone_has_its_name_and_point_though_other_rows_name_it(
    estate: tuple[MergingGraph, KeyStore, dict[str, Any]],
) -> None:
    graph, _store, _reports = estate
    zone = next(e for e in _planned_places() if e.key.startswith("zone:"))
    node = _stored(graph)[_ref(zone)]
    assert node.properties["name"] == zone.properties["name"]
    assert "geometry_ref" in node.properties
    named_by = [r for r in rows_of(FILE) if r["parent_ref_2"] == _ref(zone)]
    assert named_by, "other rows do name the zone"


async def test_every_place_link_is_the_plans(
    estate: tuple[MergingGraph, KeyStore, dict[str, Any]],
) -> None:
    graph, _store, reports = estate
    _, link_keys = keys_in(FILE)
    planned = [lk for lk in PLAN.links if lk.key in set(link_keys)]
    by_id = {n.id: _ref(n) for n in graph.committed_nodes}
    stored = [
        (e.type, by_id[e.source], by_id[e.target], marking(e.handling), e.interval)
        for e in graph.committed_edges
    ]
    assert len(stored) == len(planned) == reports[FILE].edges_created

    def ends(link_type: str, a: str, b: str) -> tuple[str, ...]:
        return (link_type, *sorted((a, b))) if link_type == "ADJOINS" else (link_type, a, b)

    want = sorted(
        (*ends(lk.link_type, _ref(PLAN.entity(lk.source)), _ref(PLAN.entity(lk.target))), marking(lk.handling))
        for lk in planned
    )
    got = sorted((*ends(t, a, b), m) for t, a, b, m, _ in stored)
    assert got == want
    assert all(interval is None for *_, interval in stored), "a place link has no time"


async def test_a_second_run_creates_nothing(
    estate: tuple[MergingGraph, KeyStore, dict[str, Any]],
) -> None:
    graph, store, _reports = estate
    before = (len(graph.committed_nodes), len(graph.committed_edges))
    second, events = await load(graph, FILE, Sink(store, CASE), "load-2")
    assert second.rows_already_loaded == len(rows_of(FILE))
    assert (second.nodes_created, second.edges_created, events) == (0, 0, [])
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == before
