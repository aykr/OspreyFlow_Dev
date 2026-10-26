"""R17, `pid-report-incidents` (ADR-127 Amendment 24): which reports mention which incidents, one
row per report and incident, on Brief 1's real file. The incident is found by reference on
`incident_ref`
(the plan's mentions are of R10's 262 throw-overs; R4's other incidents are loaded before and
not named here) and the report `Document` by reference
on `message_id` (R9 made it), so it loads last of the chapter-4 pair, in the seed's order (a
subsequence of `SEED_ORDER`: R11, R1, R3, R4, R16, R10, R9 with row 17's cell corrected, then R17).
Every expectation comes from `pid_plan`. What a mistake would do, and the case that catches it:

- an incident or a report made instead of found, or a link not the plan's, or a link of the wrong
  direction or kind (`test_every_incident_is_mentioned_in_its_reports_as_the_plan_has`);
- an element at a marking other than the first creating row's, or an extra link
  (`test_every_element_carries_the_marking_its_first_row_gives`);
- a re-run adding anything, or two rows of one pair writing two links
  (`test_a_second_run_creates_nothing`);
- a reference that finds nothing (an incident no recipe loaded, or a report none made) silently
  making a bare node
  (`test_a_reference_that_finds_nothing_is_made_bare_and_not_refused`: the engine does not refuse
  it, so the order is the only thing that stops it).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import pytest

from tests.ingest.pid_golden_support import (
    CASE,
    PLAN,
    Step,
    assert_loaded_markings,
    keys_in,
    load,
    loaded,
    replay,
    rows_of,
)
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)
from tests.ingest.test_pid_recipe_r9 import corrected_rows
from tests.ingest.test_row_keys import KeyStore, Sink

FILE = "pid_report_incidents.csv"
REPORTS = "pid_intel_reports.csv"
#: The loads before R17, in the seed's order: R11, R1, R3, R4, R16, R10, then R9 (on the file with
#: its one malformed cell corrected). R14, R2, R12, R13, R8, R15, R5, R7 and R6 are in the seed
#: between them; `test_pid_seed_order` shows they write no element R17 also writes.
BEFORE = (
    "pid_establishment_plan.csv",
    "pid_nomis_prisoners.csv",
    "pid_nomis_visits.csv",
    "pid_nomis_incidents.csv",
    "pid_number_owners.csv",
    "pid_throwover_log.csv",
    REPORTS,
)
IR = re.compile(r"IR \d+")


def _steps() -> tuple[Step | str, ...]:
    return (*BEFORE[:-1], Step(REPORTS, tuple(corrected_rows())))


@dataclass(frozen=True)
class Run:
    graph: MergingGraph
    store: KeyStore
    report: Any
    events: list[Any]
    before_nodes: frozenset[str]
    before_edges: frozenset[str]

    @property
    def new_edges(self) -> list[Any]:
        return [e for e in self.graph.committed_edges if e.id not in self.before_edges]


@pytest.fixture(scope="module")
async def mentions() -> Run:
    graph, store, _ = await loaded(*_steps())
    before_nodes = frozenset(n.id for n in graph.committed_nodes)
    before_edges = frozenset(e.id for e in graph.committed_edges)
    report, events = await load(graph, FILE, Sink(store, CASE), "load-r17")
    assert report.rejections == [], report.rejections[:3]
    return Run(graph, store, report, events, before_nodes, before_edges)


def _planned() -> list[Any]:
    _, link_keys = keys_in(FILE)
    wanted = set(link_keys)
    return [lk for lk in PLAN.links if lk.key in wanted]


def _ref(key: str) -> str:
    entity = PLAN.entity(key)
    if entity.entity_type == "Document":
        found = IR.match(PLAN.report_texts[key])
        assert found is not None, key
        return found.group()
    return str(entity.properties["incident_ref"])


def _stored_ref(node: Any) -> str:
    return str(node.properties.get("message_id", node.properties.get("incident_ref")))


async def test_every_incident_is_mentioned_in_its_reports_as_the_plan_has(mentions: Run) -> None:
    graph, report = mentions.graph, mentions.report
    planned = _planned()
    assert len(planned) == len(rows_of(FILE)) == len(mentions.new_edges) == 589
    assert report.edges_created == 589 and report.nodes_created == 0
    nodes = {n.id: n for n in graph.committed_nodes}
    for lk in planned:
        assert lk.link_type == "MENTIONED_IN" and not lk.properties, lk.key
        assert PLAN.entity(lk.source).entity_type == "Incident", lk.key
        assert PLAN.entity(lk.target).entity_type == "Document", lk.key
    stored = {
        (_stored_ref(nodes[e.source]), _stored_ref(nodes[e.target])): e for e in mentions.new_edges
    }
    assert set(stored) == {(_ref(lk.source), _ref(lk.target)) for lk in planned}
    for e in mentions.new_edges:
        assert nodes[e.source].type == "Incident" and nodes[e.target].type == "Document"
        assert e.type == "MENTIONED_IN" and e.properties == {} and e.occurrences == 1, e.id
    kinds = {
        "throw_over" if PLAN.entity(lk.source).properties["category"] == "throw_over" else "other"
        for lk in planned
    }
    assert kinds == {"throw_over"}, "the plan's report mentions are of R10's throw-overs only"


async def test_every_element_carries_the_marking_its_first_row_gives(mentions: Run) -> None:
    expected = replay(*_steps(), FILE)
    assert_loaded_markings(mentions.graph, expected)
    assert len(mentions.graph.committed_edges) == len(mentions.before_edges) + 589


async def test_a_second_run_creates_nothing(mentions: Run) -> None:
    graph = mentions.graph
    before = (len(graph.committed_nodes), len(graph.committed_edges))
    second, events = await load(graph, FILE, Sink(mentions.store, CASE), "load-r17-again")
    assert second.rows_already_loaded == len(rows_of(FILE))
    assert (second.nodes_created, second.edges_created, events) == (0, 0, [])
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == before



async def test_a_reference_that_finds_nothing_is_made_bare_and_not_refused() -> None:
    """What the engine does (measured 26 October 2026): a reference that finds nothing is not
    rejected. It makes a node holding only the property it was matched on, at the row's marking, and
    writes the link to it. So R17 run before R9 would make 350 bare reports with no title,
    time, kind or text, and nothing would say so; the seed's order is what prevents it."""
    graph, store, _ = await loaded(*_steps())
    row = dict(rows_of(FILE)[0])
    unknown_incident = {**row, "incident_ref": "pid:est1:inc:to:9999"}
    report, _events = await load(
        graph, FILE, Sink(store, CASE), "load-no-incident", rows=[unknown_incident]
    )
    assert report.rejections == [] and report.nodes_created == 1 and report.edges_created == 1
    (bare,) = [
        n for n in graph.committed_nodes
        if n.type == "Incident" and n.properties.get("incident_ref") == "pid:est1:inc:to:9999"
    ]  # fmt: skip
    assert dict(bare.properties) == {"incident_ref": "pid:est1:inc:to:9999"}
    unknown_report = {**row, "report_ref": "IR 9999"}
    report, _events = await load(
        graph, FILE, Sink(store, CASE), "load-no-report", rows=[unknown_report]
    )
    assert report.rejections == [] and report.nodes_created == 1 and report.edges_created == 1
    (empty,) = [
        n for n in graph.committed_nodes
        if n.type == "Document" and n.properties.get("message_id") == "IR 9999"
    ]  # fmt: skip
    assert dict(empty.properties) == {"message_id": "IR 9999"}
    # The same on the whole file with R9 left out: every report it names is made bare.
    without, store2, _ = await loaded(*(s for s in _steps() if _file_of(s) != REPORTS))
    report, _events = await load(without, FILE, Sink(store2, CASE), "load-no-r9")
    named = {r["report_ref"] for r in rows_of(FILE)}
    assert report.rejections == [] and report.nodes_created == len(named) > 0
    assert all(
        dict(n.properties) == {"message_id": n.properties["message_id"]}
        for n in without.committed_nodes
        if n.type == "Document"
    )


def _file_of(step: Step | str) -> str:
    return step.file if isinstance(step, Step) else step
