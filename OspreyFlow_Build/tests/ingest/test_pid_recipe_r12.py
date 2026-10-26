"""R12, `pid-soc-nominals` (ADR-127 decision 12): the organised crime group and which prisoners are
members of it, on Brief 1's real file, loaded after R11 and R1 as the seed loads them. Every
expectation comes from `pid_plan`. What a mistake would do, and the case that catches it:

- the group made once per member, or its name or reference wrong
  (`test_the_group_is_made_once_with_its_name_and_reference`);
- a member not joined to the group, joined the wrong way round, or a prisoner made here instead of
  found (`test_every_member_is_a_member_of_link_to_the_group`);
- a link or the group at a marking other than the plan's
  (`test_the_group_and_every_link_carry_the_plans_marking`);
- a re-run adding anything (`test_a_second_run_creates_nothing`).

`role` is a column the file carries but `MEMBER_OF` has no property for, so the recipe names it
unmapped with a note; `test_the_role_column_is_unmapped_because_the_link_has_no_property_for_it`
holds that to the ontology, so a later `role` property on the edge makes it fail rather than go
unnoticed."""

from __future__ import annotations

from typing import Any

import pytest

from tests.ingest.pid_golden_support import (
    CASE,
    ONTOLOGY,
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

FILE = "pid_soc_nominals.csv"
BEFORE = ("pid_establishment_plan.csv", "pid_nomis_prisoners.csv")


@pytest.fixture(scope="module")
async def nominals() -> tuple[MergingGraph, KeyStore, Any, list[Any]]:
    graph, store, _ = await loaded(*BEFORE)
    report, events = await load(graph, FILE, Sink(store, CASE))
    assert report.rejections == [], report.rejections[:3]
    return graph, store, report, events


def _planned_links() -> list[Any]:
    _, link_keys = keys_in(FILE)
    wanted = set(link_keys)
    return [lk for lk in PLAN.links if lk.key in wanted]


def _names(graph: MergingGraph) -> dict[str, str]:
    return {
        n.id: str(n.properties.get("org_ref", n.properties.get("prison_number")))
        for n in graph.committed_nodes
    }


async def test_the_group_is_made_once_with_its_name_and_reference(
    nominals: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, report, _events = nominals
    keys, _ = keys_in(FILE)
    planned = [PLAN.entity(k) for k in keys]
    stored = {
        str(n.properties["org_ref"]): n for n in graph.committed_nodes if n.type == "Organisation"
    }
    assert len(planned) >= 1 and len(rows_of(FILE)) > len(planned), "one group, several members"
    assert set(stored) == {str(e.properties["org_ref"]) for e in planned}
    assert report.nodes_created == len(planned), "the prisoners are found, never made here"
    for entity in planned:
        node = stored[str(entity.properties["org_ref"])]
        assert node.properties == dict(entity.properties), entity.key


async def test_every_member_is_a_member_of_link_to_the_group(
    nominals: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, report, _events = nominals
    names = _names(graph)
    stored = {
        (names[e.source], names[e.target]): e
        for e in graph.committed_edges
        if e.type == "MEMBER_OF"
    }
    planned = {
        (
            str(PLAN.entity(lk.source).properties["prison_number"]),
            str(PLAN.entity(lk.target).properties["org_ref"]),
        ): lk
        for lk in _planned_links()
    }
    assert set(stored) == set(planned) and len(planned) == len(rows_of(FILE))
    assert report.edges_created == len(planned)
    for pair, lk in planned.items():
        assert stored[pair].properties == dict(lk.properties) == {}, pair
        assert stored[pair].occurrences == lk.occurrences == 1, pair
    assert {e.type for e in graph.committed_edges} >= {"MEMBER_OF"}


async def test_the_group_and_every_link_carry_the_plans_marking(
    nominals: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, _report, _events = nominals
    names = _names(graph)
    keys, _ = keys_in(FILE)
    for key in keys:
        entity = PLAN.entity(key)
        node = next(
            n
            for n in graph.committed_nodes
            if n.type == "Organisation" and n.properties["org_ref"] == entity.properties["org_ref"]
        )
        assert marking(node.handling) == marking(entity.handling), key
    stored = {
        (names[e.source], names[e.target]): e
        for e in graph.committed_edges
        if e.type == "MEMBER_OF"
    }
    for lk in _planned_links():
        pair = (
            str(PLAN.entity(lk.source).properties["prison_number"]),
            str(PLAN.entity(lk.target).properties["org_ref"]),
        )
        assert marking(stored[pair].handling) == marking(lk.handling), lk.key


async def test_the_role_column_is_unmapped_because_the_link_has_no_property_for_it() -> None:
    edge = next(t for t in ONTOLOGY.edge_types if t.name == "MEMBER_OF")
    assert [p.name for p in edge.properties] == [], "MEMBER_OF gained a property: bind `role`"
    recipe = recipe_for(FILE)
    assert {u.field: u.action for u in recipe.unmapped_fields} == {"role": "ignore"}
    assert all(r["role"] == "" for r in rows_of(FILE)), "the file now carries a role"


async def test_a_second_run_creates_nothing(
    nominals: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, store, _report, _events = nominals
    before = (len(graph.committed_nodes), len(graph.committed_edges))
    second, events = await load(graph, FILE, Sink(store, CASE), "load-2")
    assert second.rows_already_loaded == len(rows_of(FILE))
    assert (second.nodes_created, second.edges_created, events) == (0, 0, [])
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == before
