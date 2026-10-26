"""R16, `pid-number-owners` (ADR-127 decision 12): the one outside number each visitor owns, on Brief
1's real file, loaded after R11, R1 and R3 (the visitors are R3's, found here by their NINO). Every
expectation comes from `pid_plan`. The number is read through `msisdn` and the `Endpoint` matched on
its normalised form, so the same number written in any form is one node. Brief 1 writes this file
with every number in its national form (the other forms are in the call file), so the collapse is
proven here by loading the same numbers again, owned by other visitors and written the plan's other
ways. What a mistake would do, and the case that catches it:

- a number not normalised, so it is not the plan's `value_normalised`, or its raw form not kept
  (`test_every_number_is_one_endpoint_as_the_plan_holds_it`);
- an owner not joined to their number, or joined the wrong way round
  (`test_every_owner_uses_their_number`);
- a number in another form making a second `Endpoint`
  (`test_a_number_written_in_any_other_form_is_the_same_endpoint`);
- an `Endpoint` or link at a marking other than the plan's
  (`test_every_endpoint_and_link_carries_the_plans_marking`);
- a re-run adding anything (`test_a_second_run_creates_nothing`)."""

from __future__ import annotations

from typing import Any

import pytest
from demo_fixtures.pid_files import _written

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

FILE = "pid_number_owners.csv"
BEFORE = ("pid_establishment_plan.csv", "pid_nomis_prisoners.csv", "pid_nomis_visits.csv")


@pytest.fixture(scope="module")
async def owners() -> tuple[MergingGraph, KeyStore, Any, list[Any]]:
    graph, store, _ = await loaded(*BEFORE)
    report, events = await load(graph, FILE, Sink(store, CASE))
    assert report.rejections == [], report.rejections[:3]
    return graph, store, report, events


def _planned() -> list[Any]:
    _, link_keys = keys_in(FILE)
    wanted = set(link_keys)
    return [lk for lk in PLAN.links if lk.key in wanted]


def _endpoints(graph: MergingGraph) -> dict[str, Any]:
    return {
        str(n.properties["value_normalised"]): n
        for n in graph.committed_nodes
        if n.type == "Endpoint"
    }


async def test_every_number_is_one_endpoint_as_the_plan_holds_it(
    owners: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, report, _events = owners
    stored = _endpoints(graph)
    planned = [PLAN.entity(lk.target) for lk in _planned()]
    assert len(planned) == len(rows_of(FILE)) == len(stored) == report.nodes_created == 591
    assert set(stored) == {str(e.properties["value_normalised"]) for e in planned}
    for entity in planned:
        node = stored[str(entity.properties["value_normalised"])]
        assert node.properties == dict(entity.properties), entity.key
        assert node.properties["endpoint_kind"] == "msisdn", entity.key
        assert str(node.properties["value_normalised"]).startswith("+44"), entity.key


async def test_every_owner_uses_their_number(
    owners: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, report, _events = owners
    visitors = {
        n.id: str(n.properties["nino"])
        for n in graph.committed_nodes
        if n.type == "Person" and "nino" in n.properties
    }
    endpoints = {
        n.id: str(n.properties["value_normalised"])
        for n in graph.committed_nodes
        if n.type == "Endpoint"
    }
    stored = {
        (visitors[e.source], endpoints[e.target]): e
        for e in graph.committed_edges
        if e.type == "USES"
    }
    planned = {
        (
            str(PLAN.entity(lk.source).properties["nino"]),
            str(PLAN.entity(lk.target).properties["value_normalised"]),
        ): lk
        for lk in _planned()
    }
    assert set(stored) == set(planned) and len(planned) == report.edges_created
    for pair, lk in planned.items():
        assert stored[pair].properties == dict(lk.properties) == {}, pair
        assert stored[pair].occurrences == lk.occurrences == 1, pair
    assert ("QQ336199B", "+447700900640") in stored, "the coordinator owns the principal's number"


async def test_a_number_written_in_any_other_form_is_the_same_endpoint(
    owners: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, store, _report, _events = owners
    rows = list(rows_of(FILE))
    extra = []
    for form, (number_row, owner_row) in enumerate(zip(rows[0:3], rows[10:13], strict=True)):
        extra.append({**owner_row, "number": _written(number_row["number"], form)})
    assert len({r["number"] for r in extra}) == 3
    assert all(r["number"] != n["number"] for r, n in zip(extra, rows[0:3], strict=True))
    before = len(_endpoints(graph))
    edges_before = len([e for e in graph.committed_edges if e.type == "USES"])
    report, _events = await load(graph, FILE, Sink(store, CASE), "load-forms", rows=extra)
    assert report.rejections == [], report.rejections[:3]
    assert report.nodes_created == 0
    assert len(_endpoints(graph)) == before, "a form made a second Endpoint"
    assert len([e for e in graph.committed_edges if e.type == "USES"]) == edges_before + 3
    raws = [str(n.properties["value_raw"]) for n in _endpoints(graph).values()]
    for number_row, written in zip(rows[0:3], extra, strict=True):
        assert raws.count(number_row["number"]) == 1, "the first form stays the raw value"
        assert written["number"] not in raws, "a later form was kept as a second Endpoint"


async def test_every_endpoint_and_link_carries_the_plans_marking(
    owners: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, _store, _report, _events = owners
    stored = _endpoints(graph)
    units = set()
    for lk in _planned():
        entity = PLAN.entity(lk.target)
        node = stored[str(entity.properties["value_normalised"])]
        assert marking(node.handling) == marking(entity.handling) == marking(lk.handling), lk.key
        units.add(node.handling.owning_unit)
    assert units == {"fenwick-moor-security", "regional-intel-unit"}


async def test_a_second_run_creates_nothing(
    owners: tuple[MergingGraph, KeyStore, Any, list[Any]],
) -> None:
    graph, store, _report, _events = owners
    before = (len(graph.committed_nodes), len(graph.committed_edges))
    second, events = await load(graph, FILE, Sink(store, CASE), "load-2")
    assert second.rows_already_loaded == len(rows_of(FILE))
    assert (second.nodes_created, second.edges_created, events) == (0, 0, [])
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == before
