"""R1, `pid-nomis-prisoners` (ADR-127 decision 12): the template the other PID recipes copy, run on
Brief 1's real file.

The file is `pid_nomis_prisoners.csv` at the demo profile, written by `pid_files` into a temporary
folder; the recipe is the committed `pid_nomis_prisoners_recipe.yaml`; the run is `load_with_rules`
against the shared graph stand-in with the deployment ontology (the core and every shipped pack).
The establishments are made first, as R11 makes them in the seed. Every expected number comes from
`pid_plan`, never typed here. What a mistake would do, and the case that catches it:

- a prisoner or an establishment made twice, or one not made (`test_the_people_and_the_places_are_
  the_plans`);
- a custody that is not a link, or a link where the plan has none
  (`test_every_custody_is_one_held_at_link`);
- a custody still running read as ended, or a closed one as running, or a link's event not at its
  start (`test_a_running_custody_is_an_open_span_and_a_closed_one_has_its_end`);
- a row loaded at the recipe's default marking whatever its columns say, which is rule 3: the
  originator, owning unit and the rest of each link's marking are the plan's
  (`test_every_link_carries_the_marking_the_plan_gives_its_row`);
- a second run of the file adding anything, or not saying why
  (`test_a_second_run_of_the_file_into_the_same_case_creates_nothing`);
- a wrong time column or an interval that is not the plan's, even with the right counts of open and
  closed (`test_every_held_at_link_has_the_plans_interval`);
- a name, a date of birth or an alias bound to the wrong column, or dropped
  (`test_every_planned_person_is_stored_as_the_plan_holds_them`);
- a prisoner or establishment stored at a marking other than the plan's entity, which is rule 3
  (`test_every_stored_node_carries_the_marking_the_plan_gives_its_entity`);
- `aliases` rejecting the prisoners who have none, or writing an empty list for them
  (`test_a_prisoner_with_no_alias_is_not_rejected_and_carries_none`)."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml
from services.api.studio_publish import load_with_rules

from adapters.media_objectstore.testing import InMemoryMediaStore
from demo_fixtures import pid_files, pid_plan
from demo_fixtures.pid_plan import _end_of, _start_of
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.domain import NodeWrite, Principal
from schemas.ingest import Recipe
from tests.ingest.pid_golden_support import loaded as load_in_seed_order
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)
from tests.ingest.test_row_keys import KeyStore, Sink

ONTOLOGY = load_deployment_ontology()
SCHEME = load_uk_le_scheme()
LOADER = Principal(id="data-engineer-1", clearance="SECRET", org_unit="fenwick-moor-security")
FILE = "pid_nomis_prisoners.csv"
RECIPE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core/packages/demo_fixtures"
CASE = "pid-case"
PLAN = pid_plan.build_plan("demo")


def recipe() -> Recipe:
    return Recipe.model_validate(
        yaml.safe_load((RECIPE / "pid_nomis_prisoners_recipe.yaml").read_text(encoding="utf-8"))
    )


@pytest.fixture(scope="module")
def rows(tmp_path_factory: pytest.TempPathFactory) -> list[dict[str, str]]:
    folder = tmp_path_factory.mktemp("pid")
    pid_files.write_files(PLAN, folder)
    with (folder / FILE).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _held_at() -> list[Any]:
    return [lk for lk in PLAN.links if lk.link_type == "HELD_AT"]


#: The loads before R1, in the seed's order (`test_pid_seed_order` reads it).
BEFORE = ("pid_establishment_plan.csv",)


async def _graph() -> MergingGraph:
    """The establishments, made first as the seed makes them: by R11, the committed recipe."""
    graph, _store, _reports = await load_in_seed_order(*BEFORE)
    return graph


async def _run(
    graph: MergingGraph, rows: list[dict[str, str]], sink: Sink | None, load_id: str = "load-1"
) -> tuple[Any, list[Any]]:
    report, events, _held = await load_with_rules(
        recipe(),
        rows,
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id=load_id,
        investigation_scope=CASE,
        source=FILE,
        media=InMemoryMediaStore(),
        rules=None,
        scheme=SCHEME,
        sink=sink,  # type: ignore[arg-type]
    )
    return report, events


@pytest.fixture
async def loaded(rows: list[dict[str, str]]) -> tuple[Any, list[Any], MergingGraph]:
    graph = await _graph()
    report, events = await _run(graph, rows, Sink(KeyStore(), CASE))
    assert report.rejections == [], report.rejections[:3]
    return report, events, graph


def _people(graph: MergingGraph) -> dict[str, NodeWrite]:
    return {
        str(n.properties["prison_number"]): n
        for n in graph.committed_nodes
        if n.type == "Person"
    }


def _places(graph: MergingGraph) -> dict[str, NodeWrite]:
    return {
        str(n.properties["establishment_ref"]): n
        for n in graph.committed_nodes
        if n.type == "Establishment"
    }


def _plan_person_key(key: str) -> str:
    return str(PLAN.entity(key).properties["prison_number"])


def _plan_place_key(key: str) -> str:
    return str(PLAN.entity(key).properties["establishment_ref"])


async def test_the_file_is_the_plans_and_the_plan_expects_what_the_recipe_is_asked_for(
    rows: list[dict[str, str]],
) -> None:
    assert len(rows) == len(_held_at()) > 1_000, "one row per custody record"


async def test_the_people_and_the_places_are_the_plans(
    loaded: tuple[Any, list[Any], MergingGraph], rows: list[dict[str, str]]
) -> None:
    report, _events, graph = loaded
    prisoners = {lk.source for lk in _held_at()}
    places = {lk.target for lk in _held_at()}
    assert set(_people(graph)) == {_plan_person_key(k) for k in prisoners}
    assert report.nodes_created == len(prisoners), "the establishments were made before, not here"
    assert set(_places(graph)) == {_plan_place_key(k) for k in places}
    assert len([n for n in graph.committed_nodes if n.type == "Establishment"]) == len(places)
    # A transferred prisoner's second row finds the first row's person; every row finds its place.
    assert report.nodes_referenced == len(rows) + (len(rows) - len(prisoners))
    first = sorted(prisoners)[0]
    stored = _people(graph)[_plan_person_key(first)].properties
    planned = PLAN.entity(first).properties
    assert (stored["family_name"], stored["given_names"]) == (
        planned["family_name"],
        planned["given_names"],
    )


async def test_every_custody_is_one_held_at_link(
    loaded: tuple[Any, list[Any], MergingGraph],
) -> None:
    report, _events, graph = loaded
    links = [e for e in graph.committed_edges if e.type == "HELD_AT"]
    assert len(links) == len(_held_at()) == report.edges_created
    ends = {(lk.source, lk.target) for lk in _held_at()}
    people = {n.id: str(n.properties["prison_number"]) for n in graph.committed_nodes if n.type == "Person"}
    places = {n.id: str(n.properties["establishment_ref"]) for n in graph.committed_nodes if n.type == "Establishment"}
    expected = {(_plan_person_key(a), _plan_place_key(b)) for a, b in ends}
    assert {(people[e.source], places[e.target]) for e in links} == expected


async def test_a_running_custody_is_an_open_span_and_a_closed_one_has_its_end(
    loaded: tuple[Any, list[Any], MergingGraph],
) -> None:
    _report, events, graph = loaded
    held = _held_at()
    still_running = [lk for lk in held if lk.last_seen is None]
    closed = [lk for lk in held if lk.last_seen is not None]
    assert still_running and closed, "the plan has both"
    links = [e for e in graph.committed_edges if e.type == "HELD_AT"]
    assert sum(1 for e in links if e.interval and e.interval.valid_to is None) == len(still_running)
    assert sum(1 for e in links if e.interval and e.interval.valid_to is not None) == len(closed)
    for edge in links:
        assert edge.interval is not None
        if edge.interval.valid_to is not None:
            assert edge.interval.valid_to >= edge.interval.valid_from
    # The link's event is at its start, span or not.
    starts = Counter(e.interval.valid_from for e in links if e.interval)
    assert Counter(ev.occurred_at for ev in events) == starts
    assert len(events) == len(links)


async def test_every_link_carries_the_marking_the_plan_gives_its_row(
    loaded: tuple[Any, list[Any], MergingGraph],
) -> None:
    _report, _events, graph = loaded
    people = {n.id: str(n.properties["prison_number"]) for n in graph.committed_nodes if n.type == "Person"}
    places = {n.id: str(n.properties["establishment_ref"]) for n in graph.committed_nodes if n.type == "Establishment"}
    planned = {
        (_plan_person_key(lk.source), _plan_place_key(lk.target)): lk.handling for lk in _held_at()
    }
    seen = Counter()
    for edge in (e for e in graph.committed_edges if e.type == "HELD_AT"):
        want = planned[(people[edge.source], places[edge.target])]
        got = edge.handling
        assert (got.classification, got.handling_code, got.action_code, got.sanitisation_code) == (
            want.classification, want.handling_code, want.action_code, want.sanitisation_code,
        )  # fmt: skip
        assert (got.originator, got.owning_unit) == (want.originator, want.owning_unit)
        seen[(got.classification, got.originator)] += 1
    # The plan holds more than one marking in this file (the other establishments' prisoners are the
    # regional unit's), so a recipe that took one default for every row would not pass.
    assert len({unit for _, unit in seen}) > 1, seen
    assert seen == Counter(
        (h.classification, h.originator) for h in planned.values()
    )


async def test_a_second_run_of_the_file_into_the_same_case_creates_nothing(
    rows: list[dict[str, str]],
) -> None:
    graph = await _graph()
    store = KeyStore()
    sink = Sink(store, CASE)
    first, _ = await _run(graph, rows, sink, "load-1")
    before = (len(graph.committed_nodes), len(graph.committed_edges))
    second, events = await _run(graph, rows, sink, "load-2")
    assert first.rows_already_loaded == 0 and first.nodes_created > 0
    assert second.rows_already_loaded == len(rows)
    assert (second.nodes_created, second.edges_created, events) == (0, 0, [])
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == before


async def test_a_return_to_the_same_establishment_is_a_row_of_its_own(
    rows: list[dict[str, str]],
) -> None:
    """The key holds the custody's start, so a prisoner back at an establishment is a second custody
    and not a duplicate of the first (the plan has no such return, so the row is made here)."""
    first = next(r for r in rows if r["custody_to"] == "")
    back = {**first, "custody_from": "2026-09-30T00:00:00+00:00", "custody_to": ""}
    graph = await _graph()
    report, events = await _run(graph, [first, back], None)
    assert report.rejections == []
    assert report.rows_deduplicated == 0
    assert len(events) == 2, "two custodies, two events"


def _person_ids(graph: MergingGraph) -> dict[str, str]:
    return {n.id: str(n.properties["prison_number"]) for n in graph.committed_nodes if n.type == "Person"}


def _place_ids(graph: MergingGraph) -> dict[str, str]:
    return {
        n.id: str(n.properties["establishment_ref"])
        for n in graph.committed_nodes
        if n.type == "Establishment"
    }


async def test_every_held_at_link_has_the_plans_interval(
    loaded: tuple[Any, list[Any], MergingGraph],
) -> None:
    """Not only how many are open and how many closed: each link's start and end are the plan's."""
    _report, _events, graph = loaded
    people, places = _person_ids(graph), _place_ids(graph)
    planned = {
        (_plan_person_key(lk.source), _plan_place_key(lk.target)): lk for lk in _held_at()
    }
    stored = {
        (people[e.source], places[e.target]): e
        for e in graph.committed_edges
        if e.type == "HELD_AT"
    }
    assert stored.keys() == planned.keys()
    for pair, link in planned.items():
        interval = stored[pair].interval
        assert stored[pair].occurrences == link.occurrences == 1, pair
        assert interval is not None, pair
        assert interval.valid_from == _start_of(link.first_seen), pair
        want_end = None if link.last_seen is None else _end_of(link.last_seen)
        assert interval.valid_to == want_end, pair


async def test_every_planned_person_is_stored_as_the_plan_holds_them(
    loaded: tuple[Any, list[Any], MergingGraph],
) -> None:
    _report, _events, graph = loaded
    stored = _people(graph)
    planned = [e for e in PLAN.entities if e.entity_type == "Person" and "prison_number" in e.properties]
    held_by = {lk.source for lk in _held_at()}
    planned = [e for e in planned if e.key in held_by]
    assert {str(e.properties["prison_number"]) for e in planned} == set(stored)
    for entity in planned:
        node = stored[str(entity.properties["prison_number"])]
        for name in ("prison_number", "family_name", "given_names"):
            assert node.properties[name] == entity.properties[name], (entity.key, name)
        assert str(node.properties["date_of_birth"]) == str(entity.properties["date_of_birth"]), entity.key
        if entity.properties.get("aliases"):
            assert node.properties["aliases"] == list(entity.properties["aliases"]), entity.key
        else:
            assert "aliases" not in node.properties, entity.key


async def test_a_prisoner_with_no_alias_is_not_rejected_and_carries_none(
    loaded: tuple[Any, list[Any], MergingGraph], rows: list[dict[str, str]]
) -> None:
    report, _events, graph = loaded
    with_alias = {r["nomis_id"] for r in rows if r["aliases"]}
    assert with_alias, "the plan gives one prisoner a nickname"
    assert len(with_alias) < len(_people(graph)) / 2
    assert report.rejections == []
    for number, node in _people(graph).items():
        assert ("aliases" in node.properties) == (number in with_alias), number
    only = next(iter(with_alias))
    assert _people(graph)[only].properties["aliases"] == [
        next(r["aliases"] for r in rows if r["nomis_id"] == only)
    ]


async def test_every_stored_node_carries_the_marking_the_plan_gives_its_entity(
    loaded: tuple[Any, list[Any], MergingGraph],
) -> None:
    """A prisoner is made by the first of their rows (the row that creates the node), and an
    establishment was made first; each is stored at the plan's marking for that entity."""
    _report, _events, graph = loaded
    held = _held_at()
    people = {str(PLAN.entity(lk.source).properties["prison_number"]): PLAN.entity(lk.source) for lk in held}
    places = {str(PLAN.entity(lk.target).properties["establishment_ref"]): PLAN.entity(lk.target) for lk in held}
    for number, node in _people(graph).items():
        want = people[number].handling
        got = node.handling
        assert (got.classification, got.handling_code, got.action_code, got.sanitisation_code,
                got.originator, got.owning_unit) == (want.classification, want.handling_code,
                want.action_code, want.sanitisation_code, want.originator, want.owning_unit), number  # fmt: skip
    for ref, node in _places(graph).items():
        want = places[ref].handling
        assert (node.handling.classification, node.handling.originator, node.handling.owning_unit) == (
            want.classification, want.originator, want.owning_unit,
        ), ref  # fmt: skip
    # More than one marking among the prisoners, so one default for all would fail.
    assert len({n.handling.owning_unit for n in _people(graph).values()}) > 1
