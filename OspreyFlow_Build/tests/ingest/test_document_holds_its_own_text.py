"""ADR-127 decisions 1 and 2: a report `Document` holds its own text, and an edge that names a ref
the row template does not declare is refused. What a mistake would do, and the case that catches it:

- the Document written through a separate content node and a `HOLDS` link, which the ontology
  refuses from a Document, so the run fails
  (`test_a_document_holds_its_own_text_and_writes_no_holds`);
- the text not readable by the reader, or by what Extract reads, because `object_ref` or
  `media_kind` is missing from the Document itself (`test_the_reader_and_extract_read_the_text`);
- a `MENTIONED_IN` that cannot reach the Document, so a report names nobody
  (`test_each_named_person_and_the_area_are_linked_to_their_reports_document`);
- the holder shape changed for a Device, Endpoint, Person or Organisation
  (`test_a_person_holding_text_still_gets_a_content_document_held_by_holds`);
- an undeclared ref written as nothing, silently, for every row
  (`test_an_edge_naming_an_undeclared_ref_is_refused_at_save` and `..._at_run`);
- a declared ref skipped by its `when` on one row treated as an error, which would reject R9's rows
  that name fewer than three people (`test_a_ref_skipped_by_when_writes_no_link_for_that_row`).

The rows are the first rows of Brief 1's real `pid_intel_reports.csv`, written by
`demo_fixtures.pid_files.write_files` into a temporary folder. The run is the engine's real run path
(`studio_publish.load_with_rules`) against a graph stand-in that refuses what the ArcadeDB adapter
refuses (rule 15): a type the ontology lacks, an undeclared property, a link whose ends its type
does not allow. The live counterpart, against the real adapter, is
`test_document_holds_its_own_text_live.py`."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path
from typing import Any

import pytest
from services.api.document_content import DocumentContentService
from services.api.document_reader import DocumentReaderService
from services.api.studio_publish import load_with_rules
from services.api.working_set.service import WorkingSetService
from services.ingest.recipe_rules import RecipeRuleError, recipe_rule_violations

from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.loader import load_default_ontology
from schemas.domain import AuditStub, Node, NodeWrite, Principal
from schemas.ingest import Recipe
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    ValidatingGraph,
    local_staging,
)
from tests.services.api.test_email_extraction import (
    ANALYST,
    FixedModel,
    InMemoryCandidates,
    RecordingAnalytics,
    WritingGraph,
)
from tests.services.api.test_questions_graph_facts import TrendAnalytics
from tests.services.api.working_set.fakes import FakeWorkingSetStore
from tests.services.api.working_set.test_visible_link import SCHEME

ONTOLOGY = load_default_ontology()
LOADER = Principal(id="loader-1", clearance="OFFICIAL", org_unit="unit-1")
FILE = "pid_intel_reports.csv"
ROWS = 3


def real_report_rows() -> list[dict[str, str]]:
    """The first rows of the real `pid_intel_reports.csv`, as the connector hands them over."""
    from demo_fixtures import pid_files, pid_plan

    with tempfile.TemporaryDirectory(prefix="own-text-files-") as folder:
        pid_files.write_files(pid_plan.build_plan("demo"), Path(folder))
        with (Path(folder) / FILE).open(newline="", encoding="utf-8") as handle:
            return [row for _, row in zip(range(ROWS), csv.DictReader(handle), strict=False)]


@pytest.fixture(scope="module")
def reports() -> list[dict[str, str]]:
    return real_report_rows()


def _recipe(entities: list[dict[str, Any]], edges: list[dict[str, Any]]) -> Recipe:
    return Recipe.model_validate(
        {
            "id": "pid-intel-reports",
            "version": 1,
            "label": "Intelligence reports",
            "connector": {"profile": "csv"},
            "ontology_version": ONTOLOGY.version,
            "pack_versions": {},
            "defaults": {
                "provenance": {"state": "asserted"},
                "handling": {
                    "classification": "OFFICIAL",
                    "handling_code": "P",
                    "originator": "unit-1",
                    "owning_unit": "unit-1",
                },
            },
            "row_template": {"entities": entities, "edges": edges},
        }
    )


def _document(*, title_bound: bool = True) -> dict[str, Any]:
    return {
        "ref": "doc",
        "pole_class": "object",
        "type": "Document",
        "properties": {"title": {"field": "title"}} if title_bound else {},
        "content": {"kind": "document_text", "field": "report_text"},
    }


def _person(ref: str, column: str, *, content: bool = False) -> dict[str, Any]:
    entity: dict[str, Any] = {
        "ref": ref,
        "pole_class": "person",
        "type": "Person",
        "match_on": "prison_number",
        "on_match": "reference",
        "when": {"field": column, "is": "not_null"},
        "properties": {"prison_number": {"field": column}},
    }
    if content:
        entity["content"] = {"kind": "document_text", "field": "report_text"}
    return entity


def _area() -> dict[str, Any]:
    return {
        "ref": "area",
        "pole_class": "location",
        "type": "Location",
        "match_on": "site_ref",
        "on_match": "reference",
        "properties": {"site_ref": {"field": "area_ref"}},
    }


def _report_entities() -> list[dict[str, Any]]:
    return [
        _document(),
        _person("p1", "subject_1"),
        _person("p2", "subject_2"),
        _person("p3", "subject_3"),
        _area(),
    ]


def _mentions() -> list[dict[str, Any]]:
    refs = ("p1", "p2", "p3", "area")
    return [{"type": "MENTIONED_IN", "from": ref, "to": "doc"} for ref in refs]


async def _seeded(rows: list[dict[str, str]], graph: Any = None) -> Any:
    """What R1 and R11 would have loaded: the people and the areas the reports name. Into `graph`
    when given (the live test's real adapter), else a new stand-in."""
    graph = graph if graph is not None else ValidatingGraph(ONTOLOGY)
    people = sorted({r[c] for r in rows for c in ("subject_1", "subject_2", "subject_3") if r[c]})
    areas = sorted({r["area_ref"] for r in rows})
    for entity_type, key, values, extra in (
        ("Person", "prison_number", people, {"family_name": {"literal": "Seeded"}}),
        ("Location", "site_ref", areas, {}),
    ):
        recipe = _recipe(
            [
                {
                    "ref": "e",
                    "pole_class": "person" if entity_type == "Person" else "location",
                    "type": entity_type,
                    "properties": {key: {"field": "v"}, **extra},
                }
            ],
            [],
        )
        await _run(graph, recipe, [{"v": v} for v in values], load_id=f"seed-{entity_type}")
    return graph


async def _run(
    graph: Any,
    recipe: Recipe,
    rows: list[dict[str, str]],
    *,
    media: InMemoryMediaStore | None = None,
    load_id: str = "load-1",
) -> Any:
    report, _events, _held = await load_with_rules(
        recipe,
        rows,
        LOADER,
        graph=graph,
        ontology=ONTOLOGY,
        load_id=load_id,
        investigation_scope="case-1",
        source=FILE,
        media=media,
        rules=None,
    )
    return report


async def _load_reports(rows: list[dict[str, str]]) -> tuple[ValidatingGraph, InMemoryMediaStore]:
    graph, media = await _seeded(rows), InMemoryMediaStore()
    recipe = _recipe(_report_entities(), _mentions())
    report = await _run(graph, recipe, rows, media=media)
    assert report.rejections == [], report.rejections
    return graph, media


def _documents(graph: ValidatingGraph) -> list[NodeWrite]:
    return sorted(
        (n for n in graph.nodes.values() if n.type == "Document"),
        key=lambda n: str(n.properties["title"]),
    )


def _pairs(
    graph: ValidatingGraph, rows: list[dict[str, str]]
) -> list[tuple[NodeWrite, dict[str, str]]]:
    """Each Document with the row it was written from, matched by its bound title."""
    by_title = {row["title"]: row for row in rows}
    documents = _documents(graph)
    assert sorted(str(d.properties["title"]) for d in documents) == sorted(by_title)
    return [(d, by_title[str(d.properties["title"])]) for d in documents]


def _named(row: dict[str, str]) -> list[str]:
    return [row[c] for c in ("subject_1", "subject_2", "subject_3") if row[c]]


def _node(write: NodeWrite) -> Node:
    return Node(
        id=write.id,
        type=write.type,
        properties=write.properties,
        provenance=write.provenance,
        handling=write.handling,
        audit=AuditStub(created_at=write.created_at, created_by=write.created_by),
    )


async def _working_set(graph: ValidatingGraph) -> FakeWorkingSetStore:
    working = FakeWorkingSetStore()
    await working.add_nodes("case-1", [_node(n) for n in graph.nodes.values()])
    return working


# --- decision 1: the Document holds its own text ----------------------------------------------


async def test_a_document_holds_its_own_text_and_writes_no_holds(
    reports: list[dict[str, str]],
) -> None:
    graph, media = await _load_reports(reports)
    documents = _documents(graph)
    assert len(documents) == len(reports)  # one per row, and no separate content node
    for document, row in _pairs(graph, reports):
        assert document.properties["media_kind"] == "text"
        assert (await media.get(str(document.properties["object_ref"]))).decode() == row[
            "report_text"
        ]
    assert [e for e in graph.edges if e.type == "HOLDS"] == []
    assert graph.rolled_back == 0


async def test_a_title_that_is_bound_wins_and_an_unbound_one_is_the_texts_first_words(
    reports: list[dict[str, str]],
) -> None:
    graph = await _seeded(reports)
    entities = [_document(title_bound=False), _area()]
    edges = [{"type": "MENTIONED_IN", "from": "area", "to": "doc"}]
    await _run(graph, _recipe(entities, edges), reports, media=InMemoryMediaStore())
    titles = sorted(str(d.properties["title"]) for d in _documents(graph))
    assert titles == sorted(
        " ".join(r["report_text"].split())[:57] + "…"
        if len(r["report_text"]) > 60
        else r["report_text"]
        for r in reports
    )


async def test_the_reader_and_extract_read_the_text(reports: list[dict[str, str]]) -> None:
    graph, media = await _load_reports(reports)
    working = await _working_set(graph)
    write_graph = WritingGraph()
    reader = DocumentReaderService(
        WorkingSetService(write_graph, working, SCHEME),  # type: ignore[arg-type]
        RecordingAnalytics([]),  # type: ignore[arg-type]
        write_graph,  # type: ignore[arg-type]
        InMemoryCandidates(),  # type: ignore[arg-type]
        media=media,
    )
    model = FixedModel({})
    content = DocumentContentService(
        WorkingSetService(write_graph, working, SCHEME),  # type: ignore[arg-type]
        write_graph,  # type: ignore[arg-type]
        media,
        model,  # type: ignore[arg-type]
        ONTOLOGY,
        InMemoryCandidates(),  # type: ignore[arg-type]
        text_model="text-model",
        vision_model="vision-model",
        transcribe_model="speech-model",
        scheme=SCHEME,
    )
    for document, row in _pairs(graph, reports):
        view = await reader.read("case-1", document.id, ANALYST)
        assert (view.text, view.media_kind, view.has_file) == (row["report_text"], "text", True)
        data, _content_type = await content.file("case-1", document.id, ANALYST)
        assert data.decode() == row["report_text"]
        await content.extract("case-1", document.id, ANALYST)
        assert model.requests[-1].text == row["report_text"]


async def test_each_named_person_and_the_area_are_linked_to_their_reports_document(
    reports: list[dict[str, str]],
) -> None:
    graph, _media = await _load_reports(reports)
    by_id = {n.id: n for n in graph.nodes.values()}
    for document, row in _pairs(graph, reports):
        into = [e for e in graph.edges if e.type == "MENTIONED_IN" and e.target == document.id]
        people = sorted(
            str(by_id[e.source].properties["prison_number"])
            for e in into
            if by_id[e.source].type == "Person"
        )
        areas = [
            str(by_id[e.source].properties["site_ref"])
            for e in into
            if by_id[e.source].type == "Location"
        ]
        assert people == sorted(_named(row))
        assert areas == [row["area_ref"]]


# --- the holder shape is unchanged ------------------------------------------------------------


async def test_a_person_holding_text_still_gets_a_content_document_held_by_holds(
    reports: list[dict[str, str]],
) -> None:
    graph, media = await _seeded(reports), InMemoryMediaStore()
    entities = [_person("p1", "subject_1", content=True)]
    report = await _run(graph, _recipe(entities, []), reports, media=media)
    assert report.rejections == []
    documents = _documents(graph)
    assert len(documents) == len(reports)
    assert all(d.id.startswith("content:") for d in documents)  # a content node of its own
    holds = [e for e in graph.edges if e.type == "HOLDS"]
    assert len(holds) == len(reports)
    people = {n.id for n in graph.nodes.values() if n.type == "Person"}
    assert all(e.source in people and e.target.startswith("content:") for e in holds)


# --- decision 2: an undeclared ref is refused -------------------------------------------------


def _undeclared() -> Recipe:
    edges = [*_mentions(), {"type": "MENTIONED_IN", "from": "p9", "to": "doc"}]
    return _recipe(_report_entities(), edges)


def test_an_edge_naming_an_undeclared_ref_is_refused_at_save() -> None:
    problems = recipe_rule_violations(_undeclared().row_template, ONTOLOGY)
    assert len(problems) == 1 and "'p9'" in problems[0] and "MENTIONED_IN" in problems[0]
    to_side = _recipe(_report_entities(), [{"type": "MENTIONED_IN", "from": "p1", "to": "content"}])
    (problem,) = recipe_rule_violations(to_side.row_template, ONTOLOGY)
    assert "'content'" in problem


async def test_an_edge_naming_an_undeclared_ref_is_refused_at_run(
    reports: list[dict[str, str]],
) -> None:
    graph = await _seeded(reports)
    commits = graph.commits
    with pytest.raises(RecipeRuleError, match="p9"):
        await _run(graph, _undeclared(), reports, media=InMemoryMediaStore())
    assert graph.commits == commits  # nothing was written


async def test_an_edge_naming_an_undeclared_ref_is_refused_at_run_and_save_alike(
    reports: list[dict[str, str]],
) -> None:
    """The one rule serves both: what save reports is what run raises."""
    graph = await _seeded(reports)
    with pytest.raises(RecipeRuleError) as refused:
        await _run(graph, _undeclared(), reports, media=InMemoryMediaStore())
    assert refused.value.problems == recipe_rule_violations(_undeclared().row_template, ONTOLOGY)


# --- a declared ref skipped by `when` is normal -----------------------------------------------


async def test_a_ref_skipped_by_when_writes_no_link_for_that_row(
    reports: list[dict[str, str]],
) -> None:
    from demo_fixtures import pid_files, pid_plan

    with tempfile.TemporaryDirectory(prefix="own-text-files-") as folder:
        pid_files.write_files(pid_plan.build_plan("demo"), Path(folder))
        with (Path(folder) / FILE).open(newline="", encoding="utf-8") as handle:
            all_rows = list(csv.DictReader(handle))
    # The first rows of the file naming none, one, two and three people: the gate matters on each.
    by_count: dict[int, dict[str, str]] = {}
    for row in all_rows:
        by_count.setdefault(len(_named(row)), row)
    assert sorted(by_count) == [0, 1, 2, 3]
    rows = [by_count[n] for n in (0, 1, 2, 3)]
    graph, _media = await _load_reports(rows)
    for document, row in _pairs(graph, rows):
        into = [e for e in graph.edges if e.type == "MENTIONED_IN" and e.target == document.id]
        assert len(into) == len(_named(row)) + 1  # the named people and the area, no more


# --- ADR-127 amendment: an empty text fails closed; a Document holds only its own text ---


async def test_a_row_with_an_empty_report_text_is_rejected_and_its_neighbours_load(
    reports: list[dict[str, str]],
) -> None:
    rows = [dict(r) for r in reports]
    rows[1]["report_text"] = "   "
    graph, media = await _seeded(rows), InMemoryMediaStore()
    report = await _run(graph, _recipe(_report_entities(), _mentions()), rows, media=media)
    (rejection,) = report.rejections
    assert "report_text" in rejection.reason and "empty" in rejection.reason
    titles = sorted(str(d.properties["title"]) for d in _documents(graph))
    assert titles == sorted([rows[0]["title"], rows[2]["title"]])  # no text-less Document
    assert rows[1]["title"] not in titles


@pytest.mark.parametrize("kind", ["image_file", "video_file"])
def test_file_content_on_a_document_is_refused_at_save(kind: str) -> None:
    entities = [_document(), _area()]
    entities[0]["content"] = {"kind": kind, "field": "report_text"}
    recipe = _recipe(entities, [{"type": "MENTIONED_IN", "from": "area", "to": "doc"}])
    (problem,) = recipe_rule_violations(recipe.row_template, ONTOLOGY)
    assert "Document" in problem and "document_text" in problem and "own text" in problem


@pytest.mark.parametrize("kind", ["image_file", "video_file"])
async def test_file_content_on_a_document_is_refused_at_run(
    kind: str, reports: list[dict[str, str]]
) -> None:
    entities = [_document(), _area()]
    entities[0]["content"] = {"kind": kind, "field": "report_text"}
    recipe = _recipe(entities, [{"type": "MENTIONED_IN", "from": "area", "to": "doc"}])
    graph = await _seeded(reports)
    commits = graph.commits
    with pytest.raises(RecipeRuleError, match="document_text"):
        await _run(graph, recipe, reports, media=InMemoryMediaStore())
    assert graph.commits == commits


# --- review fixes: the `when` gate, bound content fields, a referenced Document, Questions --


async def test_a_when_gated_own_text_document_with_no_text_is_skipped_not_rejected(
    reports: list[dict[str, str]],
) -> None:
    """The gate is judged before the empty-text rule: a row whose gate says the Document is not
    there is not rejected for having no text, and its other entities load."""
    rows = [dict(r) for r in reports]
    rows[1]["report_text"] = ""
    gated = _document()
    gated["when"] = {"field": "report_text", "is": "not_null"}
    graph, media = await _seeded(rows), InMemoryMediaStore()
    recipe = _recipe([gated, _area()], [{"type": "MENTIONED_IN", "from": "area", "to": "doc"}])
    report = await _run(graph, recipe, rows, media=media)
    assert report.rejections == []
    titles = sorted(str(d.properties["title"]) for d in _documents(graph))
    assert titles == sorted([rows[0]["title"], rows[2]["title"]])
    mentions = [e for e in graph.edges if e.type == "MENTIONED_IN"]
    assert len(mentions) == 2  # no link for the row with no Document
    assert report.nodes_referenced + report.nodes_created > 0  # the row's area was still read


@pytest.mark.parametrize("name", ["object_ref", "media_kind"])
def test_binding_object_ref_or_media_kind_on_an_own_text_document_is_refused_at_save(
    name: str,
) -> None:
    document = _document()
    document["properties"] = {**document["properties"], name: {"field": "title"}}
    recipe = _recipe([document, _area()], [{"type": "MENTIONED_IN", "from": "area", "to": "doc"}])
    (problem,) = recipe_rule_violations(recipe.row_template, ONTOLOGY)
    assert name in problem and "own text" in problem


@pytest.mark.parametrize("name", ["object_ref", "media_kind"])
async def test_binding_object_ref_or_media_kind_on_an_own_text_document_is_refused_at_run(
    name: str, reports: list[dict[str, str]]
) -> None:
    document = _document()
    document["properties"] = {**document["properties"], name: {"field": "title"}}
    recipe = _recipe([document, _area()], [{"type": "MENTIONED_IN", "from": "area", "to": "doc"}])
    graph = await _seeded(reports)
    commits = graph.commits
    with pytest.raises(RecipeRuleError, match=name):
        await _run(graph, recipe, reports, media=InMemoryMediaStore())
    assert graph.commits == commits


async def test_a_referenced_document_keeps_its_object_ref_and_the_media_store_gains_nothing(
    reports: list[dict[str, str]],
) -> None:
    referenced = _document()
    referenced |= {"match_on": "title", "on_match": "reference"}
    recipe = _recipe([referenced, _area()], [{"type": "MENTIONED_IN", "from": "area", "to": "doc"}])
    graph, media = await _seeded(reports), InMemoryMediaStore()
    first = await _run(graph, recipe, reports, media=media, load_id="first")
    assert first.rejections == []
    refs = {d.properties["title"]: d.properties["object_ref"] for d in _documents(graph)}
    kept = dict(media.files)
    changed = [{**r, "report_text": r["report_text"] + " Amended."} for r in reports]
    second = await _run(graph, recipe, changed, media=media, load_id="second")
    assert second.rejections == [] and second.nodes_referenced >= len(reports)
    assert {d.properties["title"]: d.properties["object_ref"] for d in _documents(graph)} == refs
    assert media.files == kept  # nothing orphaned: no object written for a Document not rewritten


async def test_questions_reads_an_own_text_documents_text(reports: list[dict[str, str]]) -> None:
    from services.api.datasets import InMemoryDatasetStore
    from services.api.questions import InMemoryQuestionStore, QuestionsService

    graph, media = await _load_reports(reports)
    working = await _working_set(graph)
    write_graph = WritingGraph()
    working_set = WorkingSetService(write_graph, working, SCHEME)  # type: ignore[arg-type]
    candidates = InMemoryCandidates()
    reader = DocumentReaderService(
        working_set,
        RecordingAnalytics([]),  # type: ignore[arg-type]
        write_graph,  # type: ignore[arg-type]
        candidates,  # type: ignore[arg-type]
        media=media,
    )
    model = FixedModel({"answer": "Nothing to add.", "cited": [], "entities": []})
    service = QuestionsService(
        working_set,
        reader,
        write_graph,  # type: ignore[arg-type]
        model,  # type: ignore[arg-type]
        ONTOLOGY,
        candidates,  # type: ignore[arg-type]
        InMemoryQuestionStore(),
        default_model="local-model",
        analytics=TrendAnalytics([]),  # type: ignore[arg-type]
        datasets=InMemoryDatasetStore(),
        investigations=None,
    )
    await service.ask("case-1", "Who is named?", ANALYST)
    (request,) = model.requests
    for row in reports:
        assert row["report_text"] in request.text
