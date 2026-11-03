"""Questions to the model about a case's documents (`06_DECISIONS.md` ADR-098 decision 4).

The service's own rules, against the fakes the email and reader tests keep honest. What a mistake
here would do, and the case that catches it:

- a Document the analyst cannot see would be read to the model and quoted back
  (`test_a_hidden_document_is_never_sent_to_the_model_nor_cited`, rule 3);
- documents too long to read at once would be cut and answered from in part
  (`test_documents_past_what_the_model_can_read_are_refused_not_cut`, rule 2);
- a proposed entity would reach the graph without a person (`..._are_pending_until_accepted`,
  rule 5);
- a proposal would be placed in a document where its words are not (`..._not_in_the_text_...`).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
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

from schemas.domain import Principal, ProvenanceState

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
from .test_questions_graph_facts import TrendAnalytics
from .working_set.fakes import FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, edge, node

ANSWER = {
    "answer": "Dana MERCER wrote to Callum PRICE about the Dabhol plant [1].",
    "cited": [1],
    "entities": [
        {
            "type": "Person",
            "name": "Dana MERCER",
            "document": 1,
            "quote": "Dana MERCER",
            "confidence": 90,
        },
        {
            "type": "Location",
            "name": "Dabhol",
            "document": 1,
            "quote": "Dabhol plant",
            "confidence": 80,
        },
        {"type": "Person", "name": "Dan LEE", "document": 1, "quote": "Dan LEE", "confidence": 70},
    ],
}


async def _service(
    documents: list[object] | None = None, answer: dict[str, object] | None = None
) -> tuple[QuestionsService, FixedModel, InMemoryCandidates, WritingGraph, FakeWorkingSetStore]:
    docs = (
        documents
        if documents is not None
        else [_document(email_document_id("ev-1"), event_id="ev-1")]
    )
    working = FakeWorkingSetStore()
    await working.add_nodes("inv-1", [node("a"), node("b"), *docs])  # type: ignore[list-item]
    await working.add_edges("inv-1", [edge("e1", "a", "b")])
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
    service = QuestionsService(
        working_set,
        reader,
        graph,
        model,  # type: ignore[arg-type]
        ONTOLOGY,
        candidates,  # type: ignore[arg-type]
        InMemoryQuestionStore(),
        default_model="local-model",
        analytics=TrendAnalytics([]),  # type: ignore[arg-type]
        datasets=InMemoryDatasetStore(),
        investigations=None,
    )
    return service, model, candidates, graph, working


async def test_the_model_reads_the_cases_documents_and_answers_with_what_it_cites() -> None:
    service, model, _, _, _ = await _service()
    answered = await service.ask("inv-1", "Who wrote about Dabhol?", ANALYST)
    (request,) = model.requests
    assert TEXT in request.text and "Who wrote about Dabhol?" in request.text
    assert request.model == "local-model"
    assert answered.answer.startswith("Dana MERCER wrote")
    assert [c.document_id for c in answered.citations] == [email_document_id("ev-1")]
    assert answered.citations[0].title == "Dabhol"


async def test_proposed_entities_are_located_in_their_document_and_are_pending_until_accepted() -> (
    None
):
    service, _, _, graph, _ = await _service()
    answered = await service.ask("inv-1", "Who?", ANALYST)
    found = {(c.entity_type, c.locator) for c in answered.candidates}
    start = TEXT.index("Dana MERCER")
    assert ("Person", f"char span {start}-{start + 11}") in found
    assert all(c.status is CandidateStatus.PENDING for c in answered.candidates)  # rule 5
    assert all(w.type == "Document" for w in graph.nodes.values())  # nothing written


async def test_a_proposal_whose_words_are_not_in_the_text_is_left_out_and_counted() -> None:
    service, _, _, _, _ = await _service()
    answered = await service.ask("inv-1", "Who?", ANALYST)
    assert "LAY" not in str([c.properties for c in answered.candidates])
    assert answered.unplaced == 1


async def test_accepting_a_proposal_writes_an_inferred_node_linked_to_its_document() -> None:
    service, _, candidates, graph, _ = await _service()
    answered = await service.ask("inv-1", "Who?", ANALYST)
    person = next(c for c in answered.candidates if c.entity_type == "Person")
    accepted = await service.accept("inv-1", person.id, ANALYST)
    assert graph.nodes[accepted.node_id].provenance.state is ProvenanceState.INFERRED
    (mention,) = [e for e in graph.committed_edges if e.source == accepted.node_id]
    assert (mention.type, mention.target) == ("MENTIONED_IN", email_document_id("ev-1"))
    assert candidates.records[person.id].status is CandidateStatus.ACCEPTED
    await service.reject(
        "inv-1", next(c.id for c in answered.candidates if c.id != person.id), ANALYST
    )


async def test_a_hidden_document_is_never_sent_to_the_model_nor_cited() -> None:
    """Rule 3: a SECRET Document in the case is not read to the model for an OFFICIAL analyst, and
    a citation of its number is not an answer about it."""
    secret = _document("secret-doc", "SECRET", event_id="ev-1")
    secret.properties["title"] = "Hidden"
    visible = _document(email_document_id("ev-1"), event_id="ev-1")
    service, model, _, _, _ = await _service(
        [visible, secret], {"answer": "See [2].", "cited": [1, 2], "entities": []}
    )
    answered = await service.ask("inv-1", "What?", ANALYST)
    (request,) = model.requests
    assert "Hidden" not in request.text
    assert [c.document_id for c in answered.citations] == [email_document_id("ev-1")]


async def test_a_case_with_no_document_the_analyst_can_see_is_refused_before_the_model() -> None:
    from services.api.questions import NoDocumentsError

    service, model, _, _, _ = await _service([_document("secret-doc", "SECRET", event_id="ev-1")])
    with pytest.raises(NoDocumentsError):
        await service.ask("inv-1", "What?", ANALYST)
    assert model.requests == []


async def test_documents_past_what_the_model_can_read_are_refused_not_cut() -> None:
    from services.api import questions

    service, model, _, _, _ = await _service()
    limit = questions.QUESTIONS_MAX_CHARS
    questions.QUESTIONS_MAX_CHARS = 10
    try:
        with pytest.raises(QuestionsTooLargeError) as refused:
            await service.ask("inv-1", "What?", ANALYST)
    finally:
        questions.QUESTIONS_MAX_CHARS = limit
    assert refused.value.limit == 10 and refused.value.would_be > 10
    assert model.requests == []


async def test_the_conversation_is_kept_and_read_back_with_each_proposals_state() -> None:
    service, _, _, _, _ = await _service()
    answered = await service.ask("inv-1", "Who?", ANALYST)
    await service.accept("inv-1", answered.candidates[0].id, ANALYST)
    (entry,) = await service.history("inv-1", ANALYST)
    assert entry.question == "Who?" and entry.answer == answered.answer
    assert entry.candidates[0].status is CandidateStatus.ACCEPTED


async def test_another_analyst_of_the_unit_reads_the_conversation_and_another_unit_does_not() -> (
    None
):
    """The conversation belongs to the case: whoever can open the case reads it (the route checks
    the case level); a proposal answers only to its owning unit, as every finding does."""
    service, _, _, _, _ = await _service()
    await service.ask("inv-1", "Who?", ANALYST)
    colleague = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-1")
    (entry,) = await service.history("inv-1", colleague)
    assert entry.candidates
    stranger = Principal(id="analyst-9", clearance="OFFICIAL", org_unit="unit-9")
    (other,) = await service.history("inv-1", stranger)
    assert other.candidates == []


async def test_an_answer_asked_over_a_document_the_reader_cannot_see_is_not_shown_to_them() -> None:
    """Rule 3: an answer's words are drawn from every Document the model read. A reader who cannot
    see one of them is not shown the answer at all, and not told one was left out, which would say
    that a Document above them is in the case."""
    secret = _document("secret-doc", "SECRET", event_id="ev-1")
    visible = _document(email_document_id("ev-1"), event_id="ev-1")
    service, model, _, _, _ = await _service(
        [visible, secret], {"answer": "Drawn from both.", "cited": [1], "entities": []}
    )
    cleared = Principal(id="analyst-3", clearance="SECRET", org_unit="unit-1")
    await service.ask("inv-1", "What?", cleared)
    (request,) = model.requests
    assert request.text.count("Document ") >= 2  # the cleared asker's question read both
    assert [e.answer for e in await service.history("inv-1", cleared)] == ["Drawn from both."]
    assert await service.history("inv-1", ANALYST) == []


async def test_an_answer_says_the_engine_and_model_that_produced_it_and_keeps_saying_it() -> None:
    """ADR-135 decision 4: the engine the analyst named reaches the routing, and the answer — and
    the conversation read back later — names the engine and model that produced it."""
    from services.api.model_routing import Engine, ModelRoutes, RoutedModel

    service, model, _, _, _ = await _service()
    gemini = Engine(name="gemini", label="Gemini", key_present=True,
                    models={"extraction": "gemini/gemini-2.5-flash"})  # fmt: skip
    codes = {_document("d").handling.handling_code, node("a").handling.handling_code}
    # ADR-136: the case reads a dataset an administrator set to `any`.
    datasets = service._datasets
    opened = Dataset(id="open", name="Open", owning_unit="unit-1", egress="any",
                     created_at=datetime.now(UTC), created_by="seed")  # fmt: skip
    datasets.add(opened)  # type: ignore[attr-defined]
    datasets.cases["inv-1"] = ["open"]  # type: ignore[attr-defined]
    service._model = RoutedModel(  # type: ignore[assignment]
        model,  # type: ignore[arg-type]
        routes=ModelRoutes(
            locals={"extraction": "local-model"},
            engines={"gemini": gemini},
            sendable=frozenset(codes),
        ),
        egress=datasets,
    )
    answered = await service.ask("inv-1", "Who?", ANALYST, engine="gemini")
    (request,) = model.requests
    assert request.model == "gemini/gemini-2.5-flash"
    assert (answered.engine, answered.model) == ("gemini", "gemini/gemini-2.5-flash")
    (kept,) = await service.history("inv-1", ANALYST)
    assert (kept.engine, kept.model) == ("gemini", "gemini/gemini-2.5-flash")
    local = await service.ask("inv-1", "Who?", ANALYST, engine="local")
    assert (local.engine, local.model) == ("local", "local-model")


async def test_ask_the_case_names_its_datasets_and_one_set_to_none_stays_local() -> None:
    """ADR-136 decision 3, at the caller: Ask the case names the case's datasets on its request, so
    a case reading a dataset left at `none` is answered locally even when Gemini is named and the
    handling code is sendable — and the answer says so."""
    from services.api.model_routing import Engine, ModelRoutes, RoutedModel

    service, model, _, _, _ = await _service()
    gemini = Engine(name="gemini", label="Gemini", key_present=True,
                    models={"extraction": "gemini/gemini-2.5-flash"})  # fmt: skip
    codes = {_document("d").handling.handling_code, node("a").handling.handling_code}
    datasets = service._datasets
    for id_, egress in (("open", "any"), ("kept-in", "none")):
        made = Dataset(id=id_, name=id_, owning_unit="unit-1", egress=egress,  # type: ignore[arg-type]
                       created_at=datetime.now(UTC), created_by="seed")  # fmt: skip
        datasets.add(made)  # type: ignore[attr-defined]
    datasets.cases["inv-1"] = ["open", "kept-in"]  # type: ignore[attr-defined]
    service._model = RoutedModel(  # type: ignore[assignment]
        model,  # type: ignore[arg-type]
        routes=ModelRoutes(locals={"extraction": "local-model"}, engines={"gemini": gemini},
                           sendable=frozenset(codes)),  # fmt: skip
        egress=datasets,
    )
    answered = await service.ask("inv-1", "Who?", ANALYST, engine="gemini")
    (request,) = model.requests
    assert request.datasets == ["open", "kept-in"]
    assert request.model == "local-model"
    assert (answered.engine, answered.model) == ("local", "local-model")


async def test_the_answer_just_asked_names_its_author_as_the_conversation_does() -> None:
    """Build order step 18c: chapter 8's answer, asked on GOV.UK, read "e369dd84-… · 3 Nov" (the
    identity provider's subject) until the panel was reopened, when the list named "Demo Analyst":
    the ask route returned the answer with no name, and the Glass showed the stored id (rule 7). The
    ask names its author as the list does (ADR-106)."""
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from services.api import app as app_module
    from services.api.questions import AskRequest, QuestionAnswer

    answer = QuestionAnswer(
        id="q1", author="e369dd84-subject", question="q", answer="a", citations=[], candidates=[],
        unplaced=0, created_at=datetime(2026, 11, 3, tzinfo=UTC),
    )  # fmt: skip

    class _Questions:
        async def ask(self, *_: object, **__: object) -> QuestionAnswer:
            return answer

    class _Audit:
        async def record(self, **_: object) -> None:
            return None

    class _Names:
        async def display_names(self, ids: object) -> dict[str, str]:
            return {i: "Demo Analyst" for i in ids if i == "e369dd84-subject"}  # type: ignore[attr-defined]

    got = await app_module.ask_question_route(
        investigation=SimpleNamespace(id="c1"),  # type: ignore[arg-type]
        body=AskRequest(question="What connects them?"),
        principal=SimpleNamespace(id="e369dd84-subject"),  # type: ignore[arg-type]
        questions=_Questions(),  # type: ignore[arg-type]
        audit=_Audit(),  # type: ignore[arg-type]
        principal_names=_Names(),  # type: ignore[arg-type]
    )
    assert got.author_name == "Demo Analyst"
