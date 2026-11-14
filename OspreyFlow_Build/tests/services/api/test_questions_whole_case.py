"""*Whole case* (`06_DECISIONS.md` ADR-098 Amendment 9, ADR-129 Amendment 5): Ask reads the case
through the case's search service, as the asker, with the question's own words.

The search here is a fake that answers as `search_service.search_page` does for the parts Ask
relies on, and refuses what it refuses (rule 15): its request is the real `SearchPageRequest`, so a
query past 200 characters or a page past 50 is refused as the route refuses it, and it finds only
what the graph's own access step lets the asker read (`FakeGraphPort._node_readable`, the step
`get_nodes` uses), so a record they may not see is never found. The live leak test
(`tests/services/search_index/test_ask_whole_case_leak_live.py`) holds the real search to the
same.

Each invariant names its test (rule 12):
- the question is the query, whole, one page of 50 (`test_the_questions_own_words_are_the_query`);
- a question past the search's limit is refused in words that say what to do, never cut
  (`test_a_question_longer_than_the_search_takes_is_refused_never_cut`);
- what the asker may not see is not found, counted, read or cited
  (`test_a_record_the_asker_may_not_see_is_not_found_counted_read_or_cited`);
- a Document the reader opens is read whole, one it does not is its passage only
  (`test_a_document_on_the_canvas_is_read_whole`,
  `test_a_document_off_the_canvas_is_read_as_its_passage_never_whole`);
- `[S-n]` stand for their records, an invented one is dropped and counted
  (`test_a_cited_source_stands_for_its_records_and_an_invented_one_is_dropped`);
- the fallback's words and the counts' limits reach the summary
  (`test_the_searchs_fallback_and_limits_reach_the_read_summary`);
- *will read* counts what asking reads
  (`test_will_read_counts_what_asking_reads_and_sends_nothing`);
- a later reader who may not see a source is not shown the answer, wherever the source is
  (`test_an_answer_is_shown_only_to_a_reader_who_may_see_every_source`).
"""

from __future__ import annotations

from typing import Any

import pytest
from services.api.questions import (
    WHOLE_CASE_PAGE,
    NothingToReadError,
    QuestionsService,
    QuestionTooLongToSearchError,
    canvas_label,
)

from schemas.domain import Node, Principal
from schemas.search import (
    OfferedFilters,
    PassagePart,
    SearchMatch,
    SearchPageRequest,
    SearchPageResponse,
    SearchResult,
)

from .test_document_reader import _document
from .test_email_extraction import WritingGraph
from .test_questions_graph_facts import ANALYST, CLEARED, DANA, _case, _person

KESTREL, KESTREL_TWIN = "node-kestrel-1a2b", "node-kestrel-3c4d"
HIDDEN_KESTREL = "node-kestrel-5e6f"
OFF_DOC, ON_DOC = "doc-off-canvas-7a81", "doc-on-canvas-9b02"
QUESTION = "Who paid Kestrel?"
PASSAGE = [
    PassagePart(text="the plant ", match=False),
    PassagePart(text="paid Kestrel", match=True),
    PassagePart(text=" for the invoice", match=False),
]
CITING: dict[str, Any] = {
    "answer": "Ann KESTREL was paid [S-1]; see also [S-9].",
    "cited": [],
    "search_cited": [1, 9],
    "entities": [],
}


class FakeCaseSearch:
    """Answers as `search_page` does for the parts Ask relies on, as the asker: a record is found
    when a word of the query is in its name or title, and only when the graph's access step lets
    the asker read it. The two Kestrels are one merged entity (its visible members only)."""

    def __init__(
        self,
        graph: WritingGraph,
        *,
        source: str = "index",
        limited_reason: str | None = None,
        counts_exact: bool = True,
        more: bool = False,
    ) -> None:
        self.graph = graph
        self.requests: list[tuple[str, Principal, SearchPageRequest]] = []
        self.source = source
        self.limited_reason = limited_reason
        self.counts_exact = counts_exact
        self.more = more

    async def __call__(
        self, investigation_id: str, principal: Principal, body: SearchPageRequest
    ) -> SearchPageResponse:
        # The real request is re-validated: what the route would refuse with a 422 is refused.
        body = SearchPageRequest.model_validate(body.model_dump())
        self.requests.append((investigation_id, principal, body))
        words = {w.strip("?.,").lower() for w in body.query.split()}
        held = self.graph._world_nodes()
        readable = [n for n in held.values() if self.graph._node_readable(principal, n)]

        def matches(n: Node) -> bool:
            said = f"{canvas_label(n)} {n.properties.get('title', '')}".lower()
            return any(w and w in said for w in words)

        found = sorted((n for n in readable if matches(n)), key=lambda n: n.id)
        results: list[SearchResult] = []
        people = [n for n in found if n.type != "Document"]
        if people:
            results.append(
                SearchResult(
                    node_ids=[n.id for n in people],
                    type="Person",
                    match=SearchMatch(band="name_exact", why="Name is 'Kestrel'", field="Name"),
                    is_document=False,
                )
            )
        for doc in (n for n in found if n.type == "Document"):
            results.append(
                SearchResult(
                    node_ids=[doc.id],
                    type="Document",
                    match=SearchMatch(band="mention_words", why="Mentions 'Kestrel'"),
                    passage=PASSAGE,
                    is_document=True,
                )
            )
        return SearchPageResponse(
            nodes=found,
            query=body.query,
            source=self.source,  # type: ignore[arg-type]
            limited=self.source == "fallback",
            limited_reason=self.limited_reason,
            total=len(results),
            counts_exact=self.counts_exact,
            groups=[],
            filters=OfferedFilters(datasets=[], dates=None),
            page=body.page,
            page_size=body.page_size or body.limit,
            more=self.more,
            results=results,
        )


def _kestrel(node_id: str, classification: str = "OFFICIAL") -> Node:
    return _person(node_id, "Ann KESTREL", classification)


def _off_canvas_doc() -> Node:
    doc = _document(OFF_DOC)
    doc.properties["title"] = "Kestrel invoice"
    return doc


async def _whole_case(
    *,
    answer: dict[str, Any] | None = None,
    on_canvas_doc: bool = False,
    **search: Any,
) -> tuple[QuestionsService, Any, FakeCaseSearch, WritingGraph]:
    """The fixture case, its canvas as `_case` holds it, and in the graph beyond the canvas: a
    merged Kestrel (two members), a SECRET Kestrel, and a Document about Kestrel."""
    documents = None
    if on_canvas_doc:
        on = _document(ON_DOC, event_id="ev-1")
        on.properties["title"] = "Kestrel letter"
        documents = [on]
    service, model, _, _, graph = await _case(
        answer=answer if answer is not None else CITING, documents=documents
    )
    beyond = [
        _kestrel(KESTREL),
        _kestrel(KESTREL_TWIN),
        _kestrel(HIDDEN_KESTREL, "SECRET"),
        _off_canvas_doc(),
    ]
    # The canvas's own Document is in the graph too: the search finds it, the reader opens it.
    graph._graph_nodes.update({n.id: n for n in [*beyond, *(documents or [])]})
    return service, model, FakeCaseSearch(graph, **search), graph


# --- what is searched --------------------------------------------------------------------------


async def test_the_questions_own_words_are_the_query() -> None:
    service, _, search, _ = await _whole_case()
    await service.ask("inv-1", QUESTION, ANALYST, read_from="case", case_search=search)
    ((case, principal, body),) = search.requests
    assert (case, principal.id) == ("inv-1", ANALYST.id)  # as the asker, never a service account
    assert body.query == QUESTION
    assert (body.page, body.page_size, body.group) == (1, WHOLE_CASE_PAGE, None)
    assert body.filters.datasets is None and body.filters.date_from is None


async def test_a_question_longer_than_the_search_takes_is_refused_never_cut() -> None:
    service, model, search, _ = await _whole_case()
    longest = "Kestrel " + "k" * 192  # 200 characters: the search's own limit, accepted
    await service.ask("inv-1", longest, ANALYST, read_from="case", case_search=search)
    assert search.requests[-1][2].query == longest
    asked = len(model.requests)

    with pytest.raises(QuestionTooLongToSearchError) as refused:
        await service.ask("inv-1", longest + "?", ANALYST, read_from="case", case_search=search)
    words = refused.value.words
    assert "at most 200 characters; yours has 201" in words
    assert "Shorten the question" in words
    assert "Selected items or Everything on the graph" in words
    assert len(search.requests) == 1  # never searched with part of it
    assert len(model.requests) == asked
    with pytest.raises(QuestionTooLongToSearchError):
        await service.will_read(
            "inv-1", ANALYST, read_from="case", question="k" * 201, case_search=search
        )


async def test_will_read_with_no_question_yet_says_to_type_it() -> None:
    service, _, search, _ = await _whole_case()
    with pytest.raises(NothingToReadError) as refused:
        await service.will_read(
            "inv-1", ANALYST, read_from="case", question="  ", case_search=search
        )
    assert "type the question first" in refused.value.words
    assert search.requests == []


async def test_nothing_found_is_refused_in_words() -> None:
    service, model, search, _ = await _whole_case()
    with pytest.raises(NothingToReadError) as refused:
        await service.ask("inv-1", "Who is Zebedee?", ANALYST, read_from="case", case_search=search)
    assert "Nothing in the case matches your question's words" in refused.value.words
    assert model.requests == []


# --- what is read, counted and cited ------------------------------------------------------------


async def test_a_record_the_asker_may_not_see_is_not_found_counted_read_or_cited() -> None:
    """Rule 4: the SECRET Kestrel is above the analyst. It is not a member of the merged result,
    not counted, not in the text the model reads and not cited; a cleared reader's question does
    read it, so the fixture is not vacuous."""
    service, model, search, _ = await _whole_case()
    answered = await service.ask("inv-1", QUESTION, ANALYST, read_from="case", case_search=search)
    assert HIDDEN_KESTREL not in model.requests[-1].text
    (cited,) = answered.search_citations
    assert cited.node_ids == [KESTREL, KESTREL_TWIN]
    assert answered.read is not None and answered.read.found == 2  # the merged Kestrel, the doc

    cleared = await service.ask("inv-1", QUESTION, CLEARED, read_from="case", case_search=search)
    assert cleared.search_citations[0].node_ids == [KESTREL, KESTREL_TWIN, HIDDEN_KESTREL]


async def test_a_document_on_the_canvas_is_read_whole() -> None:
    service, model, search, _ = await _whole_case(on_canvas_doc=True)
    answered = await service.ask("inv-1", QUESTION, ANALYST, read_from="case", case_search=search)
    text = model.requests[-1].text
    assert "Document 1: Kestrel letter" in text
    assert answered.read is not None
    assert (answered.read.documents, answered.read.read_from) == (1, "case")


async def test_a_document_off_the_canvas_is_read_as_its_passage_never_whole() -> None:
    """The reader opens only a Document in the working set, and checks access again. One the
    search found beyond the canvas is a source read as the passage the search matched."""
    service, model, search, _ = await _whole_case()
    answered = await service.ask("inv-1", QUESTION, ANALYST, read_from="case", case_search=search)
    text = model.requests[-1].text
    assert "Document 1:" not in text
    assert '[S-2] Document: Kestrel invoice. Found because: Mentions \'Kestrel\'.' in text
    assert 'Passage: "the plant paid Kestrel for the invoice"' in text
    assert answered.read is not None
    assert (answered.read.documents, answered.read.passages, answered.read.items) == (0, 1, 1)
    assert OFF_DOC not in text  # the model never sees an id (rule 7)


async def test_a_cited_source_stands_for_its_records_and_an_invented_one_is_dropped() -> None:
    service, _, search, _ = await _whole_case()
    answered = await service.ask("inv-1", QUESTION, ANALYST, read_from="case", case_search=search)
    (cited,) = answered.search_citations
    assert (cited.number, cited.label, cited.type) == (1, "[S-1]", "Person")
    assert cited.name == "KESTREL, Ann" and cited.why == "Name is 'Kestrel'"
    assert "[S-9]" not in answered.answer and "[S-1]" in answered.answer
    assert answered.unplaced == 1


async def test_the_searchs_fallback_and_limits_reach_the_read_summary() -> None:
    reason = "Results are limited: this deployment has no search index."
    service, _, search, _ = await _whole_case(
        source="fallback", limited_reason=reason, counts_exact=False, more=True
    )
    answered = await service.ask("inv-1", QUESTION, ANALYST, read_from="case", case_search=search)
    assert answered.read is not None
    assert answered.read.limited_reason == reason
    assert (answered.read.counts_exact, answered.read.more) == (False, True)


async def test_will_read_counts_what_asking_reads_and_sends_nothing() -> None:
    service, model, search, _ = await _whole_case()
    will = await service.will_read(
        "inv-1", ANALYST, read_from="case", question=QUESTION, case_search=search
    )
    assert model.requests == []
    answered = await service.ask("inv-1", QUESTION, ANALYST, read_from="case", case_search=search)
    assert will.read == answered.read


async def test_in_a_view_only_what_the_view_holds_is_read() -> None:
    service, model, search, _ = await _whole_case()
    answered = await service.ask(
        "inv-1", QUESTION, ANALYST, read_from="case", case_search=search,
        view_id="v-1", view_node_ids=[DANA, OFF_DOC],
    )  # fmt: skip
    assert answered.read is not None and answered.read.found == 1
    assert "Ann" not in model.requests[-1].text


async def test_the_other_choices_never_search() -> None:
    service, _, search, _ = await _whole_case()
    answered = await service.ask("inv-1", QUESTION, ANALYST, read_from="graph", case_search=search)
    assert search.requests == []
    assert answered.read is not None and answered.read.found == 0


# --- a later reader (rule 3) -------------------------------------------------------------------


async def test_an_answer_is_shown_only_to_a_reader_who_may_see_every_source() -> None:
    """The asker sees their answer though its sources are not on the canvas: a source is checked by
    the graph's own access step, as the search found it. A reader the graph hides one source from
    (here, the cleared asker's SECRET Kestrel) is not shown the answer at all."""
    service, _, search, _ = await _whole_case()
    await service.ask("inv-1", QUESTION, ANALYST, read_from="case", case_search=search)
    assert [a.question for a in await service.history("inv-1", ANALYST)] == [QUESTION]

    service, _, search, _ = await _whole_case()
    await service.ask("inv-1", QUESTION, CLEARED, read_from="case", case_search=search)
    assert [a.question for a in await service.history("inv-1", CLEARED)] == [QUESTION]
    assert await service.history("inv-1", ANALYST) == []


# --- the route's refusal ------------------------------------------------------------------------


async def test_the_route_refuses_a_question_too_long_to_search_in_words() -> None:
    import json

    from services.api.app import _question_too_long_to_search_handler

    response = await _question_too_long_to_search_handler(None, QuestionTooLongToSearchError(240))  # type: ignore[arg-type]
    body = json.loads(bytes(response.body))
    assert response.status_code == 422
    assert body["error"] == "question_too_long_to_search"
    assert "yours has 240" in body["detail"]
