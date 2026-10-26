"""R6, `pid-seized-comms` (ADR-127 decision 12): one row per communication found on a seized handset,
on Brief 1's real files. One recipe serves both: batch 1 is loaded by the seed, batch 2 sits
unloaded until chapter 9. Loaded in the seed's order (ADR-127 Amendment 18): R11, R1, R3, R16 and R5,
then R6. R5's load is the rows of its file that call a number R6 names (every row to each of them,
so the first row that names each is the seed's), not all million: the stand-in cannot hold them, and
the rest of the file touches nothing R6 does. So the coordinator's number, which batch 2's SIM talks
to, is already a node, and a number R5 would have made first is the one R5 made. Every expectation
comes from `pid_plan`. What a mistake would do, and the case that catches it:

- a handset or SIM made twice, or not through `imei` / `imsi`, or a handset or SIM missing, or a
  handset's IMEI stored with its check digit (the plan holds 15 digits; the store holds the first
  14, `01_DOMAIN_MODEL.md` section 7)
  (`test_every_handset_and_sim_is_one_node_as_the_plan_holds_it`);
- a SIM not paired with its handset, a prisoner not linked to the handset found with them, or a link
  written for a handset found with no one (`test_every_sim_is_paired_and_every_found_handset_is_used`);
- a communication lost, folded into another, or not at its exact time, or not between the SIM and
  the other number (`test_every_communication_is_a_communicated_with_link_from_the_sim`);
- batch 1 making more than its own handsets and SIMs, or batch 2 adding more than its own handset,
  SIM and three links, or touching batch 1, or not finding the coordinator's number by reference
  (`test_batch_one_makes_only_its_own`, `test_batch_two_adds_only_its_own`);
- an element at a marking other than the first creating row's, as the plan's rows replayed in the
  seed's order give it (`test_every_element_carries_the_marking_its_first_row_gives`);
- a re-run of either batch adding anything (`test_a_second_run_of_each_batch_creates_nothing`)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pytest

from demo_fixtures import pid_plan
from tests.ingest.pid_golden_support import (
    CASE,
    COORDINATOR_NUMBER,
    PLAN,
    Step,
    assert_exact_instants,
    assert_loaded_markings,
    keys_in,
    load,
    loaded,
    msisdn,
    pin_calls_to_step,
    replay,
    rows_of,
)
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)
from tests.ingest.test_row_keys import Sink

BATCH_1 = "pid_seized_comms_batch1.csv"
BATCH_2 = "pid_seized_comms_batch2.csv"
BEFORE = (
    "pid_establishment_plan.csv",
    "pid_nomis_prisoners.csv",
    "pid_nomis_visits.csv",
    "pid_number_owners.csv",
)


def _before() -> tuple[str | Step, ...]:
    """The loads before R6, in the seed's order: R11, R1, R3, R16, then R5 (to R6's numbers)."""
    numbers = frozenset(msisdn(r["other_number"]) for f in (BATCH_1, BATCH_2) for r in rows_of(f))
    return (*BEFORE, pin_calls_to_step(numbers))


@pytest.fixture(scope="module")
async def seized() -> dict[str, Any]:
    graph, store, _ = await loaded(*_before())
    out: dict[str, Any] = {"graph": graph, "store": store}
    for file in (BATCH_1, BATCH_2):
        out[f"{file}:before"] = (
            {n.id for n in graph.committed_nodes},
            {e.id: (e.occurrences, dict(e.properties)) for e in graph.committed_edges},
        )
        report, events = await load(graph, file, Sink(store, CASE))
        assert report.rejections == [], (file, report.rejections[:3])
        out[file] = (report, events)
    return out


def _planned(file: str, kind: str | None = None) -> list[Any]:
    _, link_keys = keys_in(file)
    wanted = set(link_keys)
    return [lk for lk in PLAN.links if lk.key in wanted and (kind is None or lk.link_type == kind)]


def _label(graph: MergingGraph) -> dict[str, str]:
    out = {}
    for n in graph.committed_nodes:
        for name in ("imei", "imsi", "value_normalised", "prison_number", "nino"):
            if name in n.properties:
                out[n.id] = f"{n.type}:{n.properties[name]}"
                break
    assert len(set(out.values())) == len(out), "two nodes hold one name: a node made twice"
    return out


def _plan_label(key: str) -> str:
    """The plan's node as the store names it. The plan holds a handset's 15-digit IMEI with its Luhn
    check digit; the store holds the 14-digit body (ADR-127 Amendment 18), so the plan's value is
    cut to its first 14 digits here, and not run through the adapter the recipe uses."""
    entity = PLAN.entity(key)
    for name in ("imei", "imsi", "value_normalised", "prison_number", "nino"):
        if name in entity.properties:
            value = str(entity.properties[name])
            return f"{entity.entity_type}:{value[:14] if name == 'imei' else value}"
    raise AssertionError(key)


def _plan_properties(entity: Any) -> dict[str, Any]:
    props = dict(entity.properties)
    if "imei" in props:
        assert len(str(props["imei"])) == 15, "the plan holds a handset's 15-digit IMEI"
        props["imei"] = str(props["imei"])[:14]
    return props


def _stored(graph: MergingGraph, kind: str) -> dict[tuple[str, str], Any]:
    names = _label(graph)
    edges = [(names[e.source], names[e.target], e) for e in graph.committed_edges if e.type == kind]
    out = {(source, target): edge for source, target, edge in edges}
    assert len(out) == len(edges), f"two {kind} links between one pair collapsed by name"
    return out


def _planned_by_name(file: str, kind: str) -> dict[tuple[str, str], Any]:
    links = _planned(file, kind)
    out = {(_plan_label(lk.source), _plan_label(lk.target)): lk for lk in links}
    assert len(out) == len(links), f"two planned {kind} links between one pair collapsed by name"
    return out


@pytest.mark.parametrize("file", [BATCH_1, BATCH_2])
async def test_every_handset_and_sim_is_one_node_as_the_plan_holds_it(
    seized: dict[str, Any], file: str
) -> None:
    graph = seized["graph"]
    keys, _ = keys_in(file)
    planned = [PLAN.entity(k) for k in keys]
    assert {e.entity_type for e in planned} == {"Device", "Endpoint"}
    names = _label(graph)
    nodes = [n for n in graph.committed_nodes if n.type in ("Device", "Endpoint")]
    stored = {names[n.id]: n for n in nodes}
    assert len(stored) == len(nodes), "two nodes of one name collapsed"
    for entity in planned:
        node = stored[_plan_label(entity.key)]
        assert node.properties == _plan_properties(entity), entity.key
    devices = [stored[_plan_label(e.key)] for e in planned if e.entity_type == "Device"]
    assert devices and all(len(str(d.properties["imei"])) == 14 for d in devices), (
        "a handset's IMEI is stored as its 14-digit body"
    )
    sims = [e for e in planned if e.entity_type == "Endpoint"]
    assert all(e.properties["endpoint_kind"] == "imsi" for e in sims)
    # One handset and one SIM for each distinct pair of the file, however many rows name them.
    assert len(planned) == 2 * len({(r["imei"], r["imsi"]) for r in rows_of(file)})


@pytest.mark.parametrize("file", [BATCH_1, BATCH_2])
async def test_every_sim_is_paired_and_every_found_handset_is_used(
    seized: dict[str, Any], file: str
) -> None:
    graph = seized["graph"]
    paired = _stored(graph, "PAIRED_WITH")
    used = _stored(graph, "USES")
    for pair, lk in _planned_by_name(file, "PAIRED_WITH").items():
        edge = paired[pair]
        assert edge.properties == dict(lk.properties) == {}, lk.key
        assert edge.occurrences == lk.occurrences, lk.key
    planned_uses = _planned_by_name(file, "USES")
    handsets = {_plan_label(lk.target) for lk in _planned(file, "PAIRED_WITH")}
    found_with = {f"Device:{r['imei'][:14]}" for r in rows_of(file) if r["found_with_nomis_id"]}
    assert {t for _, t in planned_uses} == found_with
    assert len(handsets - found_with) >= (1 if file == BATCH_1 else 0), (
        "a handset found with no one"
    )
    for pair, lk in planned_uses.items():
        edge = used[pair]
        assert edge.occurrences == lk.occurrences, pair
        instants = pid_plan.link_instants(PLAN, lk)
        assert edge.interval is not None
        assert (edge.interval.valid_from, edge.interval.valid_to) == (
            min(instants),
            max(instants),
        ), pair
    for handset in handsets - found_with:
        assert not any(t == handset for _, t in used), handset


@pytest.mark.parametrize("file", [BATCH_1, BATCH_2])
async def test_every_communication_is_a_communicated_with_link_from_the_sim(
    seized: dict[str, Any], file: str
) -> None:
    graph = seized["graph"]
    _report, all_events = seized[file]
    events = [e for e in all_events if e.edge_type == "COMMUNICATED_WITH"]
    stored = _stored(graph, "COMMUNICATED_WITH")
    planned = _planned_by_name(file, "COMMUNICATED_WITH")
    names = _label(graph)
    instants: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for event in events:
        instants[(names[event.source_id], names[event.target_id])].append(event.occurred_at)
    assert len(events) == sum(lk.occurrences for lk in planned.values()) == len(rows_of(file))
    for pair, lk in planned.items():
        edge = stored[pair]
        assert edge.properties == dict(lk.properties) == {}, pair
        assert edge.occurrences == lk.occurrences == len(instants[pair]), pair
        seen = sorted(instants[pair])
        assert_exact_instants(lk, seen)
        assert edge.interval is not None
        assert (edge.interval.valid_from, edge.interval.valid_to) == (seen[0], seen[-1]), pair
    # Calls and texts to one number are the same kind of link: both are written, none folded.
    assert {r["kind"] for r in rows_of(file)} == {"call", "text"}


async def test_batch_one_makes_only_its_own(seized: dict[str, Any]) -> None:
    """Batch 1 makes exactly the handsets and SIMs the plan homes in it: the numbers it talks to,
    and the prisoners it finds handsets with, are the ones the loads before it made."""
    report, _events = seized[BATCH_1]
    keys, link_keys = keys_in(BATCH_1)
    assert report.nodes_created == len(keys) > 0
    assert report.nodes_created == 2 * len({(r["imei"], r["imsi"]) for r in rows_of(BATCH_1)})
    nodes_before, _edges = seized[f"{BATCH_1}:before"]
    assert set(report.created_node_ids).isdisjoint(nodes_before)
    assert len(link_keys) > 0
    others = {msisdn(r["other_number"]) for r in rows_of(BATCH_1)}
    found = {
        n.id
        for n in seized["graph"].committed_nodes
        if n.properties.get("value_normalised") in others
    } - set(report.created_node_ids)
    assert len(found) == len(others), "every number batch 1 talks to was there before"
    assert found <= set(report.referenced_node_ids), "and each is named as one it found"


async def test_batch_two_adds_only_its_own(seized: dict[str, Any]) -> None:
    graph = seized["graph"]
    nodes_before, edges_before = seized[f"{BATCH_2}:before"]
    report, _events = seized[BATCH_2]
    keys, link_keys = keys_in(BATCH_2)
    assert report.nodes_created == len(keys) == 2, "its handset and its SIM, and nothing else"
    assert report.edges_created == len(link_keys) == 3
    assert {n.id for n in graph.committed_nodes} - nodes_before == set(report.created_node_ids)
    # Everything batch 1 left is as it was: same nodes, and no link of batch 1 gained anything.
    now = {e.id: (e.occurrences, dict(e.properties)) for e in graph.committed_edges}
    for edge_id, state in edges_before.items():
        assert now[edge_id] == state, edge_id
    new_edges = set(now) - set(edges_before)
    assert len(new_edges) == 3
    coordinators = [
        n
        for n in graph.committed_nodes
        if n.properties.get("value_normalised") == COORDINATOR_NUMBER
    ]
    assert len(coordinators) == 1, "the coordinator's number is one node"
    coordinator = coordinators[0]
    assert coordinator.id in nodes_before, "the coordinator's number was there before batch 2"
    assert coordinator.id in {e.target for e in graph.committed_edges if e.id in new_edges}
    # Chapter 9, decision 7(a): the number is named by the load as one it found, and not made.
    assert coordinator.id in report.referenced_node_ids
    assert coordinator.id not in report.created_node_ids


async def test_every_element_carries_the_marking_its_first_row_gives(
    seized: dict[str, Any],
) -> None:
    """ADR-127 Amendment 18: an element several rows name is created at the marking of the first
    row, in the seed's load order, that creates it. The plan's own rows are replayed in that order
    (R11, R1, R3, R16, R5, then both batches), through the store's merge rule for a link, and every
    node and link stored is held to the result, the chapter-9 handset's among them."""
    assert_loaded_markings(seized["graph"], replay(*_before(), BATCH_1, BATCH_2))


async def test_a_second_run_of_each_batch_creates_nothing(seized: dict[str, Any]) -> None:
    graph, store = seized["graph"], seized["store"]
    before = (len(graph.committed_nodes), len(graph.committed_edges))
    for file in (BATCH_1, BATCH_2):
        second, events = await load(graph, file, Sink(store, CASE), f"again-{file}")
        assert second.rows_already_loaded == len(rows_of(file))
        assert (second.nodes_created, second.edges_created, events) == (0, 0, [])
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == before
