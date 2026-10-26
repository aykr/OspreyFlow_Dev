"""R9, `pid-intel-reports` (ADR-127 Amendment 22; ADR-120 Amendment 15): the 350
intelligence reports, on Brief 1's real file, loaded after R11, R1, R3 and R16, the loads whose
elements it finds by reference (the areas, the prisoners and the number, which R16 made from its
owner file). R5 is not
loaded: the number's raw form is first written by R16, so R5 would only add calls this recipe does
not read. Every expectation comes from `pid_plan`. The file as written carries row 17's malformed
number, so the golden load runs on the file with that one cell corrected to `07700 900603`, as the
engineer does live, and the file as written has its own case. What a mistake would do, and the case
that catches it:

- a report made twice, or not at all, or its title, time, kind or media kind wrong, or its text not
  its own (`test_every_report_is_one_document_as_the_plan_holds_it_with_its_own_text`);
- an area, a prisoner, the outside person or the number not joined to its report, or a second or
  third area, subject or number written for a row that has none, or the nodes and links not the
  plan's, 662, 89 and 1 by the kind of what is mentioned
  (`test_every_report_is_mentioned_in_by_what_the_plan_names`);
- the outside person made without their names, date of birth or National Insurance number, or made
  twice (`test_the_outside_person_is_made_with_their_names_date_of_birth_and_nino`);
- a prisoner slot that makes a `Person` from a National Insurance number, in the file as written or
  in a file that puts one in `subject_N` (`test_no_person_is_made_with_a_nino_as_a_prison_number`);
- an element at a marking other than the first creating row's
  (`test_every_element_carries_the_marking_its_first_row_gives`);
- the file as written accepted whole, or its one bad row refused for another reason, or more than
  that row refused
  (`test_the_file_as_written_rejects_row_17_alone_naming_the_number_and_the_cause`);
- a re-run adding anything (`test_a_second_run_creates_nothing`)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from adapters.media_objectstore.testing import InMemoryMediaStore
from demo_fixtures import pid_plan
from ontology.errors import OntologyError
from tests.ingest.pid_golden_support import (
    CASE,
    PLAN,
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
from tests.ingest.test_row_keys import KeyStore, Sink

FILE = "pid_intel_reports.csv"
#: The loads before R9, in the seed's order: R11 (the places), R1 (the prisoners), R3 (the visitors)
#: and R16 (the numbers). R9 is chapter 4's and runs after them all.
BEFORE = (
    "pid_establishment_plan.csv",
    "pid_nomis_prisoners.csv",
    "pid_nomis_visits.csv",
    "pid_number_owners.csv",
)
TEACHING_ROW = 17  # the 1-based data row whose phone cell is malformed as written
CORRECTED = "07700 900603"
IR = re.compile(r"IR \d+")
NINO = re.compile(r"[A-Z]{2}\d{6}[A-D]")
PRISON_NUMBER = re.compile(r"Z\d{4}ZZ")


@dataclass(frozen=True)
class Run:
    """A load of the corrected file after the loads before it: what it made is what is not in
    `before`."""

    graph: MergingGraph
    store: KeyStore
    report: Any
    events: list[Any]
    media: InMemoryMediaStore
    before_nodes: frozenset[str]
    before_edges: frozenset[str]

    @property
    def new_edges(self) -> list[Any]:
        return [e for e in self.graph.committed_edges if e.id not in self.before_edges]


def corrected_rows() -> list[dict[str, str]]:
    """The file's rows with the one malformed cell corrected, as the engineer does live."""
    rows = [dict(r) for r in rows_of(FILE)]
    assert rows[TEACHING_ROW - 1]["phone_mentioned"] == pid_plan.PID_TEACHING_BAD_NUMBER
    rows[TEACHING_ROW - 1]["phone_mentioned"] = CORRECTED
    return rows


@pytest.fixture(scope="module")
async def reports() -> Run:
    graph, store, _ = await loaded(*BEFORE)
    before_nodes = frozenset(n.id for n in graph.committed_nodes)
    before_edges = frozenset(e.id for e in graph.committed_edges)
    media = InMemoryMediaStore()
    report, events = await load(
        graph, FILE, Sink(store, CASE), "load-corrected", rows=corrected_rows(), media=media
    )
    assert report.rejections == [], report.rejections[:3]
    return Run(graph, store, report, events, media, before_nodes, before_edges)


def _ref_of(key: str) -> str:
    """The IR reference a plan report is written under: its text's first words, as the file has
    it."""
    found = IR.match(PLAN.report_texts[key])
    assert found is not None, key
    return found.group()


def _planned_links() -> list[Any]:
    _, link_keys = keys_in(FILE)
    wanted = set(link_keys)
    return [lk for lk in PLAN.links if lk.key in wanted]


def _planned_reports() -> list[Any]:
    keys, _ = keys_in(FILE)
    return [PLAN.entity(k) for k in keys if PLAN.entity(k).entity_type == "Document"]


def _documents(graph: MergingGraph) -> dict[str, Any]:
    return {
        str(n.properties["message_id"]): n for n in graph.committed_nodes if n.type == "Document"
    }


def _name_of(node: Any) -> str:
    """How the plan names a stored element: the property it is found by."""
    for name in ("message_id", "prison_number", "nino", "site_ref", "value_normalised"):
        if name in node.properties:
            return f"{name}={node.properties[name]}"
    raise AssertionError(f"{node.type} {node.id} has no identifying property")


def _plan_name(key: str) -> str:
    entity = PLAN.entity(key)
    if entity.entity_type == "Document":
        return f"message_id={_ref_of(key)}"
    for name in ("prison_number", "nino", "site_ref", "value_normalised"):
        if name in entity.properties:
            return f"{name}={entity.properties[name]}"
    raise AssertionError(key)


def _as_text(value: Any) -> str:
    return value.isoformat() if isinstance(value, datetime | date) else str(value)


def nino_made_a_prisoner(graph: MergingGraph) -> list[str]:
    """The `Person` nodes whose `prison_number` is not a prison number: one made from a National
    Insurance number by a prisoner slot. Taken by shape, not by the plan, so it holds for any
    file."""
    return sorted(
        str(n.properties["prison_number"])
        for n in graph.committed_nodes
        if n.type == "Person"
        and "prison_number" in n.properties
        and not PRISON_NUMBER.fullmatch(str(n.properties["prison_number"]))
    )


async def test_every_report_is_one_document_as_the_plan_holds_it_with_its_own_text(
    reports: Run,
) -> None:
    graph, report, media = reports.graph, reports.report, reports.media
    stored = _documents(graph)
    planned = _planned_reports()
    assert len(planned) == len(rows_of(FILE)) == len(stored) == 350
    assert report.nodes_created == 351, "350 reports and the one outside person, nothing else"
    assert set(stored) == {_ref_of(e.key) for e in planned}
    for entity in planned:
        node = stored[_ref_of(entity.key)]
        assert node.properties["title"] == entity.properties["title"], entity.key
        assert (
            datetime.fromisoformat(str(node.properties["sent_at"])) == entity.properties["sent_at"]
        ), entity.key
        assert node.properties["document_kind"] == entity.properties["document_kind"], entity.key
        assert node.properties["media_kind"] == entity.properties["media_kind"] == "text"
        assert set(node.properties) == {*entity.properties, "message_id", "object_ref"}, entity.key
        text = (await media.get(str(node.properties["object_ref"]))).decode()
        want = PLAN.report_texts[entity.key]
        if entity.key == pid_plan.PID_TEACHING_REPORT:
            assert text.startswith(want) and text != want  # the file's text names the bad number
        else:
            assert text == want, entity.key
    assert [e for e in graph.committed_edges if e.type == "HOLDS"] == [], "the text is its own"


async def test_every_report_is_mentioned_in_by_what_the_plan_names(reports: Run) -> None:
    graph = reports.graph
    planned = _planned_links()
    assert all(lk.link_type == "MENTIONED_IN" for lk in planned)
    nodes = {n.id: n for n in graph.committed_nodes}
    by_source: dict[str, int] = {}
    for lk in planned:
        kind = PLAN.entity(lk.source).entity_type
        by_source[kind] = by_source.get(kind, 0) + 1
    assert by_source == {"Location": 662, "Person": 89, "Endpoint": 1}
    stored_by_source: dict[str, int] = {}
    stored: set[tuple[str, str]] = set()
    for e in reports.new_edges:
        assert e.type == "MENTIONED_IN", e.type
        assert nodes[e.target].type == "Document", "a mention is of a report"
        stored.add((_name_of(nodes[e.source]), _name_of(nodes[e.target])))
        stored_by_source[nodes[e.source].type] = stored_by_source.get(nodes[e.source].type, 0) + 1
    assert stored_by_source == by_source
    assert reports.report.edges_created == len(reports.new_edges) == len(planned) == 752
    assert stored == {(_plan_name(lk.source), _plan_name(lk.target)) for lk in planned}
    for e in reports.new_edges:
        assert e.properties == {} and e.occurrences == 1, e.id


async def test_the_outside_person_is_made_with_their_names_date_of_birth_and_nino(
    reports: Run,
) -> None:
    graph = reports.graph
    keys, _ = keys_in(FILE)
    named = [PLAN.entity(k) for k in keys if PLAN.entity(k).entity_type == "Person"]
    assert len(named) == 1, "one report names a person outside by National Insurance number"
    entity = named[0]
    stored = [
        n
        for n in graph.committed_nodes
        if n.type == "Person" and n.properties.get("nino") == entity.properties["nino"]
    ]
    assert len(stored) == 1
    assert stored[0].id not in reports.before_nodes, "R9 made them: no earlier load names them"
    for name in ("family_name", "given_names", "date_of_birth", "nino"):
        assert _as_text(stored[0].properties[name]) == _as_text(entity.properties[name]), name
    assert "prison_number" not in stored[0].properties
    # Their slot is the second, after a prisoner in the first, so a row is read by column and not
    # by the position of its first subject.
    rows = [r for r in rows_of(FILE) if r["subject_2_nino"] == entity.properties["nino"]]
    assert len(rows) == 1 and rows[0]["subject_1"] and rows[0]["subject_2"] == ""


async def test_no_person_is_made_with_a_nino_as_a_prison_number(reports: Run) -> None:
    assert nino_made_a_prisoner(reports.graph) == []
    for row in rows_of(FILE):
        for i in (1, 2, 3):
            assert not NINO.fullmatch(row[f"subject_{i}"]), (row["report_ref"], i)
    # Shown able to fail, on the shape the check reads: a `Person` with a NINO as its prison number.
    bad = SimpleNamespace(type="Person", properties={"prison_number": "QQ240404C"})
    fine = SimpleNamespace(type="Person", properties={"prison_number": "Z2486ZZ"})
    assert nino_made_a_prisoner(SimpleNamespace(committed_nodes=[fine, bad])) == ["QQ240404C"]  # type: ignore[arg-type]
    # And the file as the older layout wrote it, the National Insurance number in `subject_2` and
    # nothing in `subject_2_nino`, does not load: the prisoner slot would make a `Person` that has
    # no family name, which the ontology refuses.
    fresh, store, _ = await loaded(*BEFORE)
    rows = []
    for row in corrected_rows():
        row = dict(row)
        if row["subject_2_nino"]:
            row["subject_2"], row["subject_2_nino"] = row["subject_2_nino"], ""
        rows.append(row)
    with pytest.raises(OntologyError, match="family_name"):
        await load(fresh, FILE, Sink(store, CASE), "load-old-layout", rows=rows)


async def test_every_element_carries_the_marking_its_first_row_gives(reports: Run) -> None:
    """ADR-127 Amendment 18: the plan's own rows are replayed in the seed's order (R11, R1, R3, R16,
    then this file), through the store's merge rule for a link, and every node and link stored is
    held to the result. The reports and what they name carry more than one marking (the regional
    unit's report, the covert-development code), so the replay is not one marking repeated."""
    expected = replay(*BEFORE, FILE)
    assert expected.rows_replayed > len(rows_of(FILE))
    assert_loaded_markings(reports.graph, expected)
    units = {n.handling.owning_unit for n in reports.graph.committed_nodes if n.type == "Document"}
    assert len(units) > 1, "more than one owning unit among the reports"


async def test_the_file_as_written_rejects_row_17_alone_naming_the_number_and_the_cause() -> None:
    graph, store, _ = await loaded(*BEFORE)
    edges_before = len(graph.committed_edges)
    written = list(rows_of(FILE))
    assert written[TEACHING_ROW - 1]["phone_mentioned"] == pid_plan.PID_TEACHING_BAD_NUMBER
    report, _events = await load(graph, FILE, Sink(store, CASE), "load-as-written")
    # A rejection's row index counts from 0, so the 17th data row is index 16.
    assert [r.row_index for r in report.rejections] == [TEACHING_ROW - 1], report.rejections[:3]
    reason = report.rejections[0].reason
    assert "phone_mentioned" in reason, reason
    assert "msisdn" in reason and "letter" in reason, reason
    stored = _documents(graph)
    assert len(stored) == 349 and written[TEACHING_ROW - 1]["report_ref"] not in stored
    assert report.rows_read == 350
    # Nothing of the bad row was written: not its report and not its four links; the other 349 rows
    # and the outside person loaded whole.
    (bad,) = [
        r for r in pid_plan.rows_for(PLAN, FILE) if r.entities[0] == pid_plan.PID_TEACHING_REPORT
    ]
    assert len(bad.links) == 4
    assert report.nodes_created == 349 + 1
    assert report.edges_created == len(graph.committed_edges) - edges_before == 752 - 4


async def test_a_second_run_creates_nothing(reports: Run) -> None:
    graph = reports.graph
    before = (len(graph.committed_nodes), len(graph.committed_edges))
    second, events = await load(
        graph, FILE, Sink(reports.store, CASE), "load-again", rows=corrected_rows(),
        media=reports.media,
    )  # fmt: skip
    assert second.rows_already_loaded == len(rows_of(FILE))
    assert (second.nodes_created, second.edges_created, events) == (0, 0, [])
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == before
