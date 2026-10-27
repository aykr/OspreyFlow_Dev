"""Graph facts in a question's answer (`06_DECISIONS.md` ADR-129 decision 1, Brief 3 item E1).

The model is given, with the case's documents, an evidence brief: the entities in the analyst's
selection and one link around it (or the whole view with no selection), the links among them as
numbered facts `[G-n]`, and the events per month. These tests run the real `WorkingSetService`
projection over a fake store and a model that records exactly what it was sent, so the access cases
compare the bytes of two prompts.

What a mistake here would do, and the case that catches it (rule 12):

- a node, link or event count the analyst may not see would reach the model: the request for the
  analyst is the request for a copy of the case without the item, byte for byte
  (`test_a_hidden_*`), and a reader who may see the item is sent something different, so those
  comparisons are able to fail (`test_the_cleared_reader_is_sent_the_hidden_*`);
- an invented `[G-99]` would be shown as a fact
  (`test_an_invented_citation_is_dropped_and_counted_unplaced`);
- a brief too long to read would be cut or sent whole
  (`test_a_brief_past_the_budget_is_refused_with_the_typed_limit_and_never_cut`);
- an entity proposed from a graph-fact answer would be promoted without a person
  (`test_a_proposal_from_a_graph_fact_answer_is_pending_and_accepted_inferred`);
- an id, which the model must never see, would be written into the brief
  (`test_no_id_reaches_the_model`).

Where this file cannot prove it: the analytics store's own refusal of an event the analyst may not
see (the fake here refuses by classification, as the real one does, but only the conformance suite
proves the real one does), and the Postgres columns (`test_questions_store.py`, live).
"""

from __future__ import annotations

import itertools
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import pytest
from services.api import questions
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.document_reader import DocumentReaderService
from services.api.email_extraction import email_document_id
from services.api.questions import (
    InMemoryQuestionStore,
    QuestionsService,
    QuestionsTooLargeError,
)
from services.api.review import CandidateStatus
from services.api.working_set.service import WorkingSetService

from ports.analytics import TrendLimitExceeded
from schemas.analytics import (
    CountedHandling,
    EventRecord,
    TrendInterval,
    TrendPoint,
    TrendRequest,
    TrendResult,
)
from schemas.domain import Edge, Handling, Interval, Node, Principal, ProvenanceState

from .test_document_reader import _document
from .test_email_extraction import (
    ANALYST,
    ONTOLOGY,
    TEXT,
    FixedModel,
    InMemoryCandidates,
    RecordingAnalytics,
    WritingGraph,
    _event,
)
from .working_set.fakes import FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, edge, node

CLEARED = Principal(id="analyst-3", clearance="SECRET", org_unit="unit-1")

DANA, CALLUM, ROHAN, ELI = "node-dana-7f3a", "node-callum-9c1b", "node-rohan-2e8d", "node-eli-5a40"
HIDDEN = "node-hidden-b7c2"
CALLED, ASSOCIATED = "link-called-4d2e", "link-assoc-1a9f"
FAR, SECRET_LINK = "link-far-8c35", "link-secret-6e07"
CALLS = "dataset-calls-0001"

#: What the model answers: it cites fact 1 and an invented fact 99, names a document, and proposes
#: one entity whose words are in the document.
ANSWER: dict[str, Any] = {
    "answer": "Rohan SHAH is tied to Dana MERCER [G-1] [G-99]; she wrote to him [1].",
    "cited": [1],
    "graph_cited": [1, 99],
    "entities": [
        {
            "type": "Person",
            "name": "Dana MERCER",
            "document": 1,
            "quote": "Dana MERCER",
            "confidence": 90,
        }
    ],
}


def _person(node_id: str, name: str, classification: str = "OFFICIAL") -> Node:
    given, family = name.split(" ", 1)
    return node(node_id, classification).model_copy(
        update={"properties": {"given_names": given, "family_name": family}}
    )


def _link(
    link_id: str,
    source: str,
    target: str,
    link_type: str,
    *,
    classification: str = "OFFICIAL",
    occurrences: int = 1,
    first: str | None = None,
    last: str | None = None,
    inferred: bool = False,
    datasets: tuple[str, ...] = (),
) -> Edge:
    held = edge(link_id, source, target, classification)
    interval = (
        Interval(
            valid_from=datetime.fromisoformat(first).replace(tzinfo=UTC),
            valid_to=datetime.fromisoformat(last).replace(tzinfo=UTC) if last else None,
        )
        if first
        else None
    )
    provenance = held.provenance.model_copy(
        update={"state": ProvenanceState.INFERRED if inferred else ProvenanceState.ASSERTED}
    )
    return held.model_copy(
        update={
            "type": link_type,
            "occurrences": occurrences,
            "interval": interval,
            "provenance": provenance,
            "datasets": list(datasets),
        }
    )


def _calls(classification: str = "OFFICIAL") -> Edge:
    return _link(
        CALLED,
        DANA,
        CALLUM,
        "CALLED",
        classification=classification,
        occurrences=14,
        first="2026-01-04",
        last="2026-09-30",
        datasets=(CALLS,),
    )


def _base_nodes() -> list[Node]:
    return [
        _person(DANA, "Dana MERCER"),
        _person(CALLUM, "Callum PRICE"),
        _person(ROHAN, "Rohan SHAH"),
        _person(ELI, "Eli WARD"),
    ]


def _base_links() -> list[Edge]:
    return [
        _calls(),
        _link(ASSOCIATED, ROHAN, DANA, "ASSOCIATED_WITH", inferred=True),
        _link(FAR, ROHAN, ELI, "ASSOCIATED_WITH"),
    ]


_EVENT_NUMBERS = itertools.count(1)


def _occurred(
    month: str, handling_classification: str = "OFFICIAL", edge_id: str = CALLED
) -> EventRecord:
    return EventRecord(
        event_id=f"ev-{next(_EVENT_NUMBERS)}",
        edge_id=edge_id,
        edge_type="CALLED",
        source_id=DANA,
        target_id=CALLUM,
        occurred_at=datetime.fromisoformat(f"{month}-10T10:00:00").replace(tzinfo=UTC),
        investigation_scope="inv-1",
        handling=Handling(
            classification=handling_classification,
            handling_code="P",
            originator="unit-1",
            owning_unit="unit-1",
        ),
    )


class TrendAnalytics:
    """`AnalyticsPort.trend` as the real stores answer it, as far as this file needs: events per
    month on the links the filter names (an empty list of links does not restrict, as the real one
    does not), inside the window, of the case's own scope or the scopes it inherits, and only those
    the reader's clearance clears. Past `max_periods` it refuses (rule 15: it refuses what the real
    one refuses). Keeps every request."""

    def __init__(self, events: list[EventRecord]) -> None:
        self.events = events
        self.requests: list[tuple[TrendRequest, Principal]] = []

    async def trend(self, req: TrendRequest, principal: Principal) -> TrendResult:
        self.requests.append((req, principal))
        f = req.filter
        counted = [
            e
            for e in self.events
            if SCHEME.clears(principal.clearance, e.handling.classification)
            and e.investigation_scope == f.investigation_scope
            and (not f.edge_ids or e.edge_id in f.edge_ids)
            and (f.window is None or e.occurred_at >= f.window.valid_from)
            and (
                f.window is None or f.window.valid_to is None or e.occurred_at <= f.window.valid_to
            )
        ]
        months = Counter((e.occurred_at.year, e.occurred_at.month) for e in counted)
        if len(months) > req.max_periods:
            raise TrendLimitExceeded("periods", req.max_periods, len(months))
        handlings = {
            (h.classification, h.handling_code, h.owning_unit, h.originator): h
            for h in (e.handling for e in counted)
        }
        return TrendResult(
            interval=TrendInterval.MONTH,
            measure=req.measure,
            points=[
                TrendPoint(period_start=datetime(y, m, 1, tzinfo=UTC), value=float(n))
                for (y, m), n in sorted(months.items())
            ],
            total=float(len(counted)),
            events=len(counted),
            handlings=[
                CountedHandling(classification=c, handling_code=code, owning_unit=u, originator=o)
                for (c, code, u, o) in sorted(handlings)
            ],
        )


async def _case(
    nodes: list[Node] | None = None,
    links: list[Edge] | None = None,
    events: list[EventRecord] | None = None,
    *,
    answer: dict[str, Any] | None = None,
    documents: list[Node] | None = None,
    reverse: bool = False,
) -> tuple[QuestionsService, FixedModel, TrendAnalytics, InMemoryCandidates, WritingGraph]:
    docs = (
        documents
        if documents is not None
        else [_document(email_document_id("ev-1"), event_id="ev-1")]
    )
    held_nodes = [*(nodes if nodes is not None else _base_nodes()), *docs]
    held_links = links if links is not None else _base_links()
    if reverse:
        held_nodes, held_links = held_nodes[::-1], held_links[::-1]
    working = FakeWorkingSetStore()
    await working.add_nodes("inv-1", held_nodes)
    await working.add_edges("inv-1", held_links)
    graph = WritingGraph()
    candidates = InMemoryCandidates()
    model = FixedModel(answer if answer is not None else ANSWER)
    working_set = WorkingSetService(graph, working, SCHEME)
    reader = DocumentReaderService(
        working_set,
        RecordingAnalytics([_event("ev-1")]),  # type: ignore[arg-type]
        graph,
        candidates,  # type: ignore[arg-type]
    )
    analytics = TrendAnalytics(events if events is not None else [])
    datasets = InMemoryDatasetStore()
    datasets.add(
        Dataset(
            id=CALLS,
            name="Prison calls",
            owning_unit="unit-1",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by="loader-1",
        )
    )
    datasets.cases["inv-1"] = [CALLS]
    service = QuestionsService(
        working_set,
        reader,
        graph,
        model,  # type: ignore[arg-type]
        ONTOLOGY,
        candidates,  # type: ignore[arg-type]
        InMemoryQuestionStore(),
        default_model="local-model",
        analytics=analytics,  # type: ignore[arg-type]
        datasets=datasets,
        investigations=None,
    )
    return service, model, analytics, candidates, graph


def _brief_of(model: FixedModel) -> str:
    (request,) = model.requests
    text = request.text
    start = text.index("Entities in scope:")
    return text[start : text.index("\n\nQuestion:", start)]


async def _asked(
    service: QuestionsService,
    model: FixedModel,
    principal: Principal = ANALYST,
    *,
    nodes: list[str] | None = None,
    links: list[str] | None = None,
) -> None:
    await service.ask(
        "inv-1",
        "Who is connected to Dana?",
        principal,
        selected_node_ids=nodes or [],
        selected_link_ids=links or [],
    )


# --- the brief's content ----------------------------------------------------------------------


async def test_the_brief_holds_the_selection_and_one_link_around_it_as_numbered_facts() -> None:
    service, model, _, _, _ = await _case(
        events=[_occurred("2026-03"), _occurred("2026-03"), _occurred("2026-05")]
    )
    await _asked(service, model, nodes=[DANA])
    assert _brief_of(model) == (
        "Entities in scope:\n"
        "- Person: Callum PRICE\n"
        "- Person: Dana MERCER\n"
        "- Person: Rohan SHAH\n"
        "\n"
        "Links among them (cite a fact by its number, as [G-n]):\n"
        "[G-1] Person Rohan SHAH -ASSOCIATED_WITH-> Person Dana MERCER; inferred; "
        "1 occurrence; first not recorded, last not recorded; dataset: not recorded\n"
        "[G-2] Person Dana MERCER -CALLED-> Person Callum PRICE; direct; 14 occurrences; "
        "first 2026-01-04, last 2026-09-30; dataset: Prison calls\n"
        "\n"
        "Events per month on those links:\n"
        "2026-03: 2; 2026-05: 1"
    )  # Eli WARD, two links from Dana, is not in it, nor is the far link, nor the document


async def test_with_no_selection_the_brief_is_the_whole_view() -> None:
    service, model, _, _, _ = await _case()
    await _asked(service, model)
    brief = _brief_of(model)
    assert "- Person: Eli WARD" in brief and "- Document: Dabhol" in brief
    assert brief.count("\n[G-") == 3


async def test_a_selected_link_brings_its_two_ends() -> None:
    service, model, _, _, _ = await _case()
    await _asked(service, model, links=[FAR])
    brief = _brief_of(model)
    assert "Rohan SHAH" in brief and "Eli WARD" in brief and "Callum PRICE" not in brief


async def test_the_timeline_window_keeps_only_the_links_and_events_in_it() -> None:
    service, model, analytics, _, _ = await _case(
        events=[_occurred("2026-03"), _occurred("2026-08")]
    )
    window = Interval(
        valid_from=datetime(2026, 7, 1, tzinfo=UTC), valid_to=datetime(2026, 12, 31, tzinfo=UTC)
    )
    await service.ask("inv-1", "What?", ANALYST, selected_node_ids=[DANA], window=window)
    brief = _brief_of(model)
    assert "-CALLED->" in brief  # its interval overlaps the window
    assert "2026-08: 1" in brief and "2026-03" not in brief
    ((request, _),) = analytics.requests
    assert request.filter.window == window


async def test_events_are_read_only_on_the_links_in_scope_and_never_with_no_link() -> None:
    """An empty `edge_ids` does not restrict the real store, so no link must mean no question."""
    service, model, analytics, _, _ = await _case(
        nodes=[_person(DANA, "Dana MERCER")], links=[], events=[_occurred("2026-03")]
    )
    await _asked(service, model)
    assert analytics.requests == []
    assert "Events per month" not in _brief_of(model)


async def test_the_prompt_does_not_depend_on_the_order_the_store_holds_things_in() -> None:
    first = await _case(events=[_occurred("2026-03")])
    second = await _case(events=[_occurred("2026-03")], reverse=True)
    await _asked(first[0], first[1])
    await _asked(second[0], second[1])
    assert first[1].requests == second[1].requests


async def test_no_id_reaches_the_model() -> None:
    """Rule 7: not a node id, a link id, a dataset id, nor a fragment of one; and no Gremlin."""
    service, model, _, _, _ = await _case(events=[_occurred("2026-03")])
    await _asked(service, model)
    (request,) = model.requests
    sent = request.text + str(request.json_schema)
    for ident in (DANA, CALLUM, ROHAN, ELI, CALLED, ASSOCIATED, FAR, CALLS):
        assert ident not in sent
        assert ident[-6:] not in sent
    assert "g.V" not in sent and "gremlin" not in sent.lower()


async def test_a_node_with_no_name_is_called_by_its_type_never_by_a_piece_of_its_id() -> None:
    nameless = node(HIDDEN)  # a Person with no properties
    service, model, _, _, _ = await _case(nodes=[*_base_nodes(), nameless])
    await _asked(service, model)
    assert "- Person: unnamed Person" in _brief_of(model)
    assert HIDDEN[-6:] not in model.requests[0].text


# --- rule 3 and 12: a hidden item leaves no trace ----------------------------------------------


async def _prompts(
    with_hidden: tuple[list[Node], list[Edge], list[EventRecord]],
    without: tuple[list[Node], list[Edge], list[EventRecord]],
    principal: Principal,
    *,
    nodes: list[str] | None = None,
) -> tuple[Any, Any]:
    """The request sent for `principal` over the case that holds the hidden item, and over its
    copy without it."""
    sent = []
    for held_nodes, held_links, held_events in (with_hidden, without):
        service, model, _, _, _ = await _case(held_nodes, held_links, held_events)
        await _asked(service, model, principal, nodes=nodes)
        (request,) = model.requests
        sent.append(request)
    return sent[0], sent[1]


def _with_a_hidden_node() -> tuple[list[Node], list[Edge], list[EventRecord]]:
    return (
        [*_base_nodes(), _person(HIDDEN, "Sam SECRETIVE", "SECRET")],
        [*_base_links(), _link(SECRET_LINK, DANA, HIDDEN, "ASSOCIATED_WITH")],
        [_occurred("2026-03")],
    )


def _without_it() -> tuple[list[Node], list[Edge], list[EventRecord]]:
    return _base_nodes(), _base_links(), [_occurred("2026-03")]


async def test_a_hidden_node_leaves_no_trace_in_the_prompt() -> None:
    """The hidden node is one link from Dana, so it would be in the brief of anyone who could see
    it, with or without a selection. The whole request is compared, not the answer."""
    for selection in ([DANA], None):
        seen, copy = await _prompts(_with_a_hidden_node(), _without_it(), ANALYST, nodes=selection)
        assert seen.model_dump_json() == copy.model_dump_json()
        assert "Sam SECRETIVE" not in seen.text


async def test_the_cleared_reader_is_sent_the_hidden_node() -> None:
    """The comparison above can fail: someone who may see the node is sent a different prompt."""
    seen, copy = await _prompts(_with_a_hidden_node(), _without_it(), CLEARED, nodes=[DANA])
    assert "Sam SECRETIVE" in seen.text
    assert seen.text != copy.text


def _with_a_hidden_link() -> tuple[list[Node], list[Edge], list[EventRecord]]:
    return (
        _base_nodes(),
        [*_base_links(), _link(SECRET_LINK, CALLUM, ROHAN, "VISITED", classification="SECRET")],
        [_occurred("2026-03")],
    )


async def test_a_hidden_link_between_two_visible_nodes_leaves_no_trace() -> None:
    for selection in ([DANA], None):
        seen, copy = await _prompts(_with_a_hidden_link(), _without_it(), ANALYST, nodes=selection)
        assert seen.model_dump_json() == copy.model_dump_json()
        assert "VISITED" not in seen.text


async def test_the_cleared_reader_is_sent_the_hidden_link() -> None:
    seen, copy = await _prompts(_with_a_hidden_link(), _without_it(), CLEARED, nodes=[DANA])
    assert "VISITED" in seen.text and seen.text != copy.text


def _with_hidden_counts() -> tuple[list[Node], list[Edge], list[EventRecord]]:
    """Events the analyst may not see on a link they may, and events they may see on a link they
    may not (an event's own marking is its own: a link above the reader does not hide it from a
    count that names the node)."""
    return (
        _base_nodes(),
        [*_base_links(), _link(SECRET_LINK, DANA, CALLUM, "VISITED", classification="SECRET")],
        [
            _occurred("2026-03"),
            _occurred("2026-03", "SECRET"),
            _occurred("2026-04", "SECRET"),
            _occurred("2026-04", "OFFICIAL", edge_id=SECRET_LINK),
            _occurred("2026-06", "OFFICIAL", edge_id=SECRET_LINK),
        ],
    )


async def test_a_hidden_event_count_leaves_no_trace_in_the_prompt() -> None:
    seen, copy = await _prompts(_with_hidden_counts(), _without_it(), ANALYST, nodes=[DANA])
    assert seen.model_dump_json() == copy.model_dump_json()
    assert "2026-03: 1" in seen.text
    assert "2026-04" not in seen.text and "2026-06" not in seen.text


async def test_the_cleared_reader_is_sent_the_hidden_counts() -> None:
    seen, _ = await _prompts(_with_hidden_counts(), _without_it(), CLEARED, nodes=[DANA])
    assert "2026-03: 2; 2026-04: 2; 2026-06: 1" in seen.text


async def test_selecting_a_hidden_id_is_the_same_as_selecting_one_that_is_not_there() -> None:
    """A selection must not tell the analyst whether an id they name exists above them."""
    sent = []
    for held, ids in (
        (_with_a_hidden_node(), [HIDDEN, DANA]),
        (_without_it(), ["no-such-node", DANA]),
        (_with_a_hidden_node(), [HIDDEN]),
        (_without_it(), ["no-such-node"]),
    ):
        service, model, _, _, _ = await _case(*held)
        await _asked(service, model, nodes=ids)
        sent.append(model.requests[0].model_dump_json())
    assert sent[0] == sent[1]
    assert sent[2] == sent[3]


# --- handling ---------------------------------------------------------------------------------


async def test_the_question_goes_under_a_handling_only_when_documents_and_brief_share_one() -> None:
    same, model, _, _, _ = await _case(events=[_occurred("2026-03")])
    await _asked(same, model)
    assert model.requests[0].handling is not None
    assert model.requests[0].handling.handling_code == "P"

    other_code = _person(ROHAN, "Rohan SHAH").model_copy(
        update={
            "handling": _person(ROHAN, "Rohan SHAH").handling.model_copy(
                update={"handling_code": "C"}
            )
        }
    )
    mixed, model2, _, _, _ = await _case(
        nodes=[
            _person(DANA, "Dana MERCER"),
            _person(CALLUM, "Callum PRICE"),
            other_code,
            _person(ELI, "Eli WARD"),
        ]
    )
    await _asked(mixed, model2)
    assert model2.requests[0].handling is None  # the brief's element differs from the documents'


async def test_an_event_of_another_handling_code_also_takes_the_handling_away() -> None:
    odd = _occurred("2026-03").model_copy(
        update={
            "handling": Handling(
                classification="OFFICIAL",
                handling_code="C",
                originator="unit-1",
                owning_unit="unit-1",
            )
        }
    )
    service, model, _, _, _ = await _case(events=[odd])
    await _asked(service, model)
    assert model.requests[0].handling is None


# --- the answer's citations -------------------------------------------------------------------


async def test_the_answer_maps_each_cited_fact_to_the_ids_it_stands_for() -> None:
    service, model, _, _, _ = await _case()
    answered = await service.ask(
        "inv-1", "Who?", ANALYST, selected_node_ids=[DANA], selected_link_ids=[]
    )
    (cited,) = answered.graph_citations
    assert (cited.number, cited.label) == (1, "[G-1]")
    assert (cited.node_ids, cited.link_ids) == ([ROHAN, DANA], [ASSOCIATED])


async def test_an_invented_citation_is_dropped_and_counted_unplaced() -> None:
    service, _, _, _, _ = await _case()
    answered = await service.ask("inv-1", "Who?", ANALYST, selected_node_ids=[DANA])
    assert [c.number for c in answered.graph_citations] == [1]
    assert answered.answer == "Rohan SHAH is tied to Dana MERCER [G-1]; she wrote to him [1]."
    assert answered.unplaced == 1  # the entity is placed; the citation is the one left out


async def test_a_citation_listed_but_not_marked_in_the_words_is_still_a_citation() -> None:
    service, _, _, _, _ = await _case(
        answer={"answer": "They are linked.", "cited": [], "graph_cited": [2], "entities": []}
    )
    answered = await service.ask("inv-1", "Who?", ANALYST, selected_node_ids=[DANA])
    assert [(c.number, c.link_ids) for c in answered.graph_citations] == [(2, [CALLED])]
    assert answered.unplaced == 0


# --- the budget (rule 2) ----------------------------------------------------------------------


async def test_a_brief_past_the_budget_is_refused_with_the_typed_limit_and_never_cut() -> None:
    probe, probe_model, _, _, _ = await _case()
    await _asked(probe, probe_model)
    brief_alone = len(_brief_of(probe_model))
    service, model, _, _, _ = await _case()
    cap = len(TEXT) + 40  # room for the documents and a part of the brief: the brief tips it over
    original = questions.QUESTIONS_MAX_CHARS
    questions.QUESTIONS_MAX_CHARS = cap
    try:
        with pytest.raises(QuestionsTooLargeError) as refused:
            await _asked(service, model)
    finally:
        questions.QUESTIONS_MAX_CHARS = original
    error = refused.value
    assert model.requests == []  # nothing was sent, whole or in part
    assert error.documents_chars == len(TEXT)
    assert error.brief_chars == brief_alone > 40
    assert error.would_be == len(TEXT) + brief_alone
    body = error.body().model_dump()
    assert body["error"] == "limit_exceeded"
    assert body["cap"] == cap and body["would_be"] == error.would_be
    assert body["options"] == ["narrow_selection", "narrow_timeline_window", "branch"]
    assert body["documents_chars"] == len(TEXT)
    assert body["evidence_brief_chars"] == brief_alone


async def test_narrowing_the_selection_brings_the_same_case_under_the_budget() -> None:
    service, model, _, _, _ = await _case()
    await _asked(service, model, nodes=[ELI])
    narrow = len(_brief_of(model))
    service2, model2, _, _, _ = await _case()
    await _asked(service2, model2)
    whole = len(_brief_of(model2))
    assert narrow < whole
    service3, model3, _, _, _ = await _case()
    original = questions.QUESTIONS_MAX_CHARS
    questions.QUESTIONS_MAX_CHARS = len(TEXT) + (narrow + whole) // 2
    try:
        with pytest.raises(QuestionsTooLargeError):
            await _asked(service3, model3)
        await _asked(service3, model3, nodes=[ELI])
    finally:
        questions.QUESTIONS_MAX_CHARS = original
    assert len(model3.requests) == 1


async def test_the_documents_only_refusal_is_the_same_typed_limit() -> None:
    service, model, _, _, _ = await _case(nodes=[], links=[])
    original = questions.QUESTIONS_MAX_CHARS
    questions.QUESTIONS_MAX_CHARS = 10
    try:
        with pytest.raises(QuestionsTooLargeError) as refused:
            await _asked(service, model)
    finally:
        questions.QUESTIONS_MAX_CHARS = original
    assert refused.value.limit == 10 and refused.value.would_be > 10
    assert refused.value.body().error == "limit_exceeded"


async def test_the_route_answers_the_typed_limit_with_its_three_options() -> None:
    import json

    from services.api.app import _questions_too_large_handler

    response = await _questions_too_large_handler(
        None,  # type: ignore[arg-type]
        QuestionsTooLargeError(120_000, 80_000, documents_chars=70_000, brief_chars=50_000),
    )
    assert response.status_code == 409
    body = json.loads(bytes(response.body))
    assert body["error"] == "limit_exceeded"
    assert body["options"] == ["narrow_selection", "narrow_timeline_window", "branch"]
    assert (body["cap"], body["would_be"]) == (80_000, 120_000)


# --- proposals (rule 5) -----------------------------------------------------------------------


async def test_a_proposal_from_a_graph_fact_answer_is_pending_and_accepted_inferred() -> None:
    service, _, _, candidates, graph = await _case()
    answered = await service.ask("inv-1", "Who?", ANALYST, selected_node_ids=[DANA])
    assert answered.graph_citations  # it is a graph-fact answer
    assert answered.candidates
    assert all(c.status is CandidateStatus.PENDING for c in answered.candidates)
    assert graph.nodes == {}  # nothing written until a person accepts
    person = answered.candidates[0]
    accepted = await service.accept("inv-1", person.id, ANALYST)
    assert graph.nodes[accepted.node_id].provenance.state is ProvenanceState.INFERRED
    assert candidates.records[person.id].status is CandidateStatus.ACCEPTED


# --- the conversation as a later reader sees it -----------------------------------------------


async def test_an_answer_read_from_a_link_the_reader_cannot_see_is_not_shown_to_them() -> None:
    """Rule 3: an answer's words may draw on any element of its brief, so a reader who may not see
    one of them is not shown the answer, and is not told it exists."""
    nodes, links = (
        _base_nodes(),
        [*_base_links(), _link(SECRET_LINK, DANA, ROHAN, "VISITED", classification="SECRET")],
    )
    service, _, _, _, _ = await _case(nodes, links)
    await service.ask("inv-1", "Who?", CLEARED, selected_node_ids=[DANA])
    seen = await service.history("inv-1", CLEARED)
    assert [e.graph_citations[0].number for e in seen] == [1]
    assert await service.history("inv-1", ANALYST) == []


async def test_an_answer_counting_an_event_the_reader_cannot_see_is_not_shown_to_them() -> None:
    """Rule 3: the per-month counts were made as the asker. A reader cleared lower, who can see the
    link and every document but not one of the events counted on it, must not be shown the answer
    (and is not told it exists); a reader who can see every event is."""
    events = [_occurred("2026-03"), _occurred("2026-03", "SECRET")]
    service, _, _, _, _ = await _case(events=events)
    await service.ask("inv-1", "Who?", CLEARED, selected_node_ids=[DANA])
    assert await service.history("inv-1", ANALYST) == []
    assert len(await service.history("inv-1", CLEARED)) == 1


async def test_an_answer_counting_only_events_the_reader_can_see_is_shown_to_them() -> None:
    """The plant above is able to fail the other way: a lower reader is not hidden an answer whose
    counted events are all within their clearance."""
    service, _, _, _, _ = await _case(events=[_occurred("2026-03"), _occurred("2026-04")])
    await service.ask("inv-1", "Who?", ANALYST, selected_node_ids=[DANA])
    assert len(await service.history("inv-1", ANALYST)) == 1


async def test_an_answer_over_visible_elements_is_shown_with_its_citations() -> None:
    service, _, _, _, _ = await _case()
    await service.ask("inv-1", "Who?", ANALYST, selected_node_ids=[DANA])
    (entry,) = await service.history("inv-1", ANALYST)
    assert [(c.number, c.link_ids) for c in entry.graph_citations] == [(1, [ASSOCIATED])]
