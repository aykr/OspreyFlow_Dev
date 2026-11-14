"""What a question reads (`06_DECISIONS.md` ADR-098 Amendment 7, ADR-129 Amendment 4): *Selected items*,
*Everything on the graph* or *Whole case*; no refusal for want of documents; the `read` summary on the
answer and from the dry-run *will read*; and the engine that will answer, with the engines that cannot.

What a mistake here would do, and the case that catches it (rule 12):

- a selection would still send every document in the view
  (`test_selected_items_reads_the_selection_its_links_and_their_documents`);
- a case with no document would be refused, or answered as if documents had been read
  (`test_with_no_document_the_model_answers_from_the_links_and_events_and_the_answer_says_so`);
- *Whole case* would quietly fall back to the graph with no case search to call
  (`test_whole_case_is_refused_in_words_without_a_case_search`);
- an image Document would vanish from the count (`test_a_document_with_no_text_is_counted_apart`);
- a Document or item the reader may not see would be counted, quoted or cited, in *will read* or in
  the answer (`test_a_hidden_document_and_item_are_not_counted_quoted_or_cited`, rule 3 and 4), and a
  reader cleared for them is counted differently, so the comparison is able to fail
  (`test_the_cleared_reader_is_counted_the_hidden_document_and_item`);
- *will read* would count differently from the question it describes
  (`test_will_read_counts_what_the_question_then_reads_and_sends_nothing`);
- the engine named would be the one chosen, not the one the routing will use
  (`test_will_read_names_the_engine_that_will_answer_not_the_one_chosen`).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from services.api.datasets import Dataset
from services.api.email_extraction import email_document_id
from services.api.model_routing import Engine, ModelRoutes, RoutedModel
from services.api.questions import (
    WHOLE_CASE_LINE,
    NothingToReadError,
    QuestionsService,
    QuestionsTooLargeError,
    ReadFromUnavailableError,
)

from schemas.domain import Node

from .test_document_reader import _document
from .test_questions_graph_facts import (
    ANALYST,
    CALLED,
    CALLUM,
    CLEARED,
    DANA,
    ELI,
    _base_links,
    _base_nodes,
    _case,
    _link,
    _occurred,
    _person,
)
from .working_set.test_visible_link import edge, node

ABOUT_DANA = email_document_id("ev-1")  # the fixture's email, its text from event ev-1
FAR_DOC = "doc-far-31c9"
IMAGE = "doc-image-7b20"
HIDDEN_DOC = "doc-hidden-90af"
HIDDEN_PERSON = "node-hidden-person-4c1e"

PLAIN: dict[str, Any] = {"answer": "Dana MERCER called Callum PRICE [G-1].", "cited": [],
                         "graph_cited": [1], "entities": []}  # fmt: skip


def _docs() -> list[Node]:
    far = _document(FAR_DOC, event_id="ev-1")
    far.properties["title"] = "Far away"
    return [_document(ABOUT_DANA, event_id="ev-1"), far]


def _links_with_mentions() -> list[Any]:
    return [
        *_base_links(),
        _link("link-mention-1", DANA, ABOUT_DANA, "MENTIONED_IN"),
        _link("link-mention-2", ELI, FAR_DOC, "MENTIONED_IN"),
    ]


def _text(service: QuestionsService) -> str:
    (request,) = service._model.requests  # type: ignore[attr-defined]
    return str(request.text)


# --- Selected items and Everything on the graph -----------------------------------------------


async def test_selected_items_reads_the_selection_its_links_and_their_documents() -> None:
    service, model, _, _, _ = await _case(links=_links_with_mentions(), documents=_docs())
    answered = await service.ask("inv-1", "Who?", ANALYST, selected_node_ids=[DANA])
    (request,) = model.requests
    assert "Document 1: Dabhol" in request.text
    assert "Far away" not in request.text  # a document two links away is not read
    assert answered.read is not None
    assert answered.read.read_from == "selection"
    assert answered.read.documents == 1


async def test_everything_on_the_graph_reads_every_document_whatever_is_selected() -> None:
    service, model, _, _, _ = await _case(links=_links_with_mentions(), documents=_docs())
    answered = await service.ask(
        "inv-1", "Who?", ANALYST, selected_node_ids=[DANA], read_from="graph"
    )
    (request,) = model.requests
    assert "Dabhol" in request.text and "Far away" in request.text
    assert "- Person: Eli WARD" in request.text  # the brief is the whole graph too
    assert answered.read is not None
    assert (answered.read.read_from, answered.read.documents) == ("graph", 2)
    assert (answered.read.selected, answered.read.first_selected) == (0, None)


async def test_with_nothing_selected_the_default_is_everything_on_the_graph() -> None:
    service, _, _, _, _ = await _case(links=_links_with_mentions(), documents=_docs())
    answered = await service.ask("inv-1", "Who?", ANALYST)
    assert answered.read is not None and answered.read.read_from == "graph"


async def test_selected_items_with_nothing_selected_is_nothing_to_read() -> None:
    service, model, _, _, _ = await _case()
    with pytest.raises(NothingToReadError) as refused:
        await service.ask("inv-1", "Who?", ANALYST, read_from="selection")
    assert "Nothing is selected" in refused.value.words
    assert model.requests == []


async def test_an_empty_graph_is_nothing_to_read() -> None:
    service, model, _, _, _ = await _case(nodes=[], links=[], documents=[])
    with pytest.raises(NothingToReadError):
        await service.ask("inv-1", "Who?", ANALYST)
    assert model.requests == []


async def test_whole_case_is_refused_in_words_without_a_case_search() -> None:
    """A service with no case search refuses *Whole case*: it never falls back to the graph."""
    service, model, _, _, _ = await _case()
    with pytest.raises(ReadFromUnavailableError) as refused:
        await service.ask("inv-1", "Who?", ANALYST, read_from="case")
    assert "Whole case" in refused.value.words
    with pytest.raises(ReadFromUnavailableError):
        await service.will_read("inv-1", ANALYST, read_from="case")
    assert model.requests == []


# --- no refusal for want of documents ---------------------------------------------------------


async def test_with_no_document_the_model_answers_from_the_links_and_events_and_the_answer_says_so(
) -> None:  # fmt: skip
    service, model, _, _, _ = await _case(
        documents=[], events=[_occurred("2026-03")], answer=PLAIN
    )
    answered = await service.ask("inv-1", "Who did Dana call?", ANALYST, selected_node_ids=[DANA])
    (request,) = model.requests
    assert "There are no documents to read" in request.text
    assert "Document 1" not in request.text
    assert "Entities in scope:" in request.text
    assert answered.answer == "Dana MERCER called Callum PRICE [G-1]."
    assert answered.read is not None
    assert (answered.read.documents, answered.read.links, answered.read.events) == (0, 2, 1)


async def test_a_document_with_no_text_is_counted_apart() -> None:
    """ADR-098 Amendment 7: a Document with no text to read (an image) is counted, not dropped."""
    image = _document(IMAGE)  # no event and nothing stored: no text
    service, model, _, _, _ = await _case(documents=[image], answer=PLAIN)
    answered = await service.ask("inv-1", "Who?", ANALYST)
    assert answered.read is not None
    assert (answered.read.documents, answered.read.documents_without_text) == (0, 1)
    assert "There are no documents to read" in model.requests[0].text


# --- the read summary -------------------------------------------------------------------------


async def test_the_read_summary_counts_the_items_links_events_and_names_the_first_selected(
) -> None:  # fmt: skip
    service, _, _, _, _ = await _case(
        links=_links_with_mentions(),
        documents=_docs(),
        events=[_occurred("2026-03"), _occurred("2026-04")],
    )
    answered = await service.ask(
        "inv-1", "Who?", ANALYST, selected_node_ids=[DANA, CALLUM], selected_link_ids=[CALLED]
    )
    read = answered.read
    assert read is not None
    # Dana, Callum, and Rohan one link from Dana; the document is counted as a document.
    assert (read.items, read.documents, read.links, read.events) == (3, 1, 3, 2)
    assert (read.selected, read.first_selected) == (3, "MERCER, Dana")


def test_about_names_the_first_selected_as_the_canvas_does_never_by_its_id() -> None:
    """"About: Tarbuck, Kyle and 1 other": a person as the canvas labels them by default
    (`labelChoices.ts`'s `defaultLabel`, "FAMILY, Given"), not as the brief does ("Given FAMILY");
    a thing by its name or identifier; one with neither by its type, never a piece of its id."""
    from services.api.questions import canvas_label

    from .working_set.test_visible_link import node as bare

    kyle = _person("node-kyle-1", "Kyle TARBUCK")
    assert canvas_label(kyle) == "TARBUCK, Kyle"
    phone = bare("node-phone-9f2").model_copy(update={"properties": {"e164": "+447700900123"}})
    assert canvas_label(phone) == "+447700900123"
    nameless = bare("node-x-7c3a91")
    assert "7c3a91" not in canvas_label(nameless) and canvas_label(nameless).startswith("unnamed")


async def test_a_selected_link_outside_the_window_is_not_counted() -> None:
    """Every link `selected` counts must be one the kept entry names in `graph_link_ids`, which a
    later reader must see to be shown the answer (rule 3): a selected link the timeline window
    leaves out of the scope is not counted, though its ends still bring their neighbours."""
    from schemas.domain import Interval

    service, _, _, _, _ = await _case(links=_links_with_mentions(), documents=_docs())
    window = Interval(
        valid_from=datetime(2027, 1, 1, tzinfo=UTC), valid_to=datetime(2027, 12, 31, tzinfo=UTC)
    )
    answered = await service.ask(
        "inv-1", "Who?", ANALYST, selected_node_ids=[DANA], selected_link_ids=[CALLED],
        window=window,
    )  # fmt: skip
    assert answered.read is not None and answered.read.selected == 1  # Dana alone
    (kept,) = await service.history("inv-1", ANALYST)
    assert CALLED not in kept.graph_citations and answered.read == kept.read


async def test_the_read_summary_is_kept_with_the_answer_and_read_back() -> None:
    service, _, _, _, _ = await _case(links=_links_with_mentions(), documents=_docs())
    answered = await service.ask("inv-1", "Who?", ANALYST, selected_node_ids=[DANA])
    (kept,) = await service.history("inv-1", ANALYST)
    assert kept.read is not None and kept.read == answered.read


# --- rule 3 and 4: what the reader may not see ------------------------------------------------


def _with_hidden() -> tuple[list[Node], list[Any], list[Node]]:
    secret_doc = _document(HIDDEN_DOC, "SECRET", event_id="ev-1")
    secret_doc.properties["title"] = "Hidden memo"
    nodes = [*_base_nodes(), _person(HIDDEN_PERSON, "Hidden PERSON", "SECRET")]
    links = [
        *_links_with_mentions(),
        _link("link-hidden-mention", DANA, HIDDEN_DOC, "MENTIONED_IN", classification="SECRET"),
        _link("link-hidden-assoc", DANA, HIDDEN_PERSON, "ASSOCIATED_WITH", classification="SECRET"),
    ]
    return nodes, links, [*_docs(), secret_doc]


async def _read_as(principal: Any, held: tuple[list[Node], list[Any], list[Node]]) -> Any:
    nodes, links, docs = held
    service, model, _, _, _ = await _case(
        nodes, links, answer={"answer": "See [1] [2].", "cited": [1, 2], "entities": []},
        documents=docs,
    )  # fmt: skip
    will = await service.will_read(
        "inv-1", principal, selected_node_ids=[DANA, HIDDEN_PERSON, HIDDEN_DOC]
    )
    answered = await service.ask(
        "inv-1", "Who?", principal, selected_node_ids=[DANA, HIDDEN_PERSON, HIDDEN_DOC]
    )
    return will, answered, model.requests[0].text


async def test_a_hidden_document_and_item_are_not_counted_quoted_or_cited() -> None:
    will, answered, text = await _read_as(ANALYST, _with_hidden())
    bare = (_base_nodes(), _links_with_mentions(), _docs())
    will_bare, answered_bare, text_bare = await _read_as(ANALYST, bare)
    assert will.read == will_bare.read  # the same summary as a case without them
    assert answered.read == answered_bare.read
    assert text == text_bare  # not quoted: the same bytes to the model
    assert "Hidden" not in text
    assert [c.document_id for c in answered.citations] == [ABOUT_DANA]  # [2] cites nothing
    assert will.read.first_selected == "MERCER, Dana" and will.read.selected == 1


async def test_the_cleared_reader_is_counted_the_hidden_document_and_item() -> None:
    will, answered, text = await _read_as(CLEARED, _with_hidden())
    assert (will.read.documents, will.read.items, will.read.selected) == (2, 4, 3)
    assert answered.read == will.read
    assert "Hidden memo" in text


async def test_an_answer_whose_summary_counts_a_hidden_document_is_not_shown_to_a_lower_reader(
) -> None:  # fmt: skip
    """The summary's counts are the asker's: a reader who may not see one of the things it counted
    (here a Document with no text, which the model never read) is not shown the answer at all."""
    image = _document(IMAGE, "SECRET")
    service, _, _, _, _ = await _case(documents=[_document(ABOUT_DANA, event_id="ev-1"), image])
    await service.ask("inv-1", "Who?", CLEARED)
    (kept,) = await service.history("inv-1", CLEARED)
    assert kept.read is not None and kept.read.documents_without_text == 1
    assert await service.history("inv-1", ANALYST) == []


# --- will read --------------------------------------------------------------------------------


async def test_will_read_counts_what_the_question_then_reads_and_sends_nothing() -> None:
    service, model, _, _, _ = await _case(
        links=_links_with_mentions(), documents=_docs(), events=[_occurred("2026-03")]
    )
    will = await service.will_read("inv-1", ANALYST, selected_node_ids=[DANA])
    assert model.requests == []
    answered = await service.ask("inv-1", "Who?", ANALYST, selected_node_ids=[DANA])
    assert will.read == answered.read
    assert (will.engine, will.model) == ("local", "local-model")
    assert will.refused is None


async def test_will_read_past_the_budget_is_the_same_typed_limit() -> None:
    from services.api import questions

    service, _, _, _, _ = await _case()
    original = questions.QUESTIONS_MAX_CHARS
    questions.QUESTIONS_MAX_CHARS = 10
    try:
        with pytest.raises(QuestionsTooLargeError):
            await service.will_read("inv-1", ANALYST)
    finally:
        questions.QUESTIONS_MAX_CHARS = original


def _routed(
    service: QuestionsService,
    *,
    egress: str = "any",
    sendable: bool = True,
    sendable_codes: set[str] | None = None,
    local: bool = True,
    extra: dict[str, Engine] | None = None,
) -> None:
    gemini = Engine(name="gemini", label="Gemini", key_present=True,
                    models={"extraction": "gemini/gemini-2.5-flash"})  # fmt: skip
    datasets = service._datasets
    datasets.add(Dataset(id="open", name="Open", owning_unit="unit-1", egress=egress,  # type: ignore[attr-defined,arg-type]
                         created_at=datetime.now(UTC), created_by="seed"))  # fmt: skip
    datasets.cases["inv-1"] = ["open"]  # type: ignore[attr-defined]
    codes = (
        {_document("d").handling.handling_code, node("a").handling.handling_code,
         edge("e", "a", "b").handling.handling_code}
        if sendable else set()
    )  # fmt: skip
    if sendable_codes is not None:
        codes = sendable_codes
    service._model = RoutedModel(
        service._model,
        routes=ModelRoutes(
            locals={"extraction": "local-model" if local else None},
            engines={"gemini": gemini, **(extra or {})},
            sendable=frozenset(codes),
        ),
        egress=datasets,
    )


async def test_will_read_names_the_engine_that_will_answer_not_the_one_chosen() -> None:
    """ADR-136: Gemini named, but the case reads a dataset set to `none`, so the routing answers
    locally. *Will read* says so, and lists Gemini with its reason."""
    service, _, _, _, _ = await _case()
    _routed(service, egress="none")
    will = await service.will_read("inv-1", ANALYST, engine="gemini")
    assert (will.engine, will.engine_label) == ("local", "This deployment's own model")
    (gemini,) = will.unusable
    assert gemini.name == "gemini" and "egress none" in gemini.reason


async def test_will_read_names_a_hosted_engine_the_material_may_reach() -> None:
    service, _, _, _, _ = await _case()
    _routed(service)
    will = await service.will_read("inv-1", ANALYST, engine="gemini")
    assert (will.engine, will.engine_label, will.model) == (
        "gemini", "Gemini", "gemini/gemini-2.5-flash"
    )
    assert will.unusable == []


async def test_will_read_lists_an_engine_the_materials_handling_may_not_reach() -> None:
    service, _, _, _, _ = await _case()
    _routed(service, sendable=False, extra={"other": Engine(
        name="other", label="Other", key_present=True, models={"extraction": "o/x"})})  # fmt: skip
    will = await service.will_read("inv-1", ANALYST)
    assert will.engine == "local"
    assert {u.name for u in will.unusable} == {"gemini", "other"}


async def test_will_read_lists_an_engine_the_materials_own_handling_code_may_not_reach() -> None:
    """Another code may leave this deployment, but not the one this question's material carries:
    the case's data may reach Gemini, this question's may not."""
    service, _, _, _, _ = await _case()
    _routed(service, sendable_codes={"SOME-OTHER-CODE"})
    will = await service.will_read("inv-1", ANALYST, engine="gemini")
    assert will.engine == "local"
    (gemini,) = will.unusable
    assert "handling code" in gemini.reason and "this question" in gemini.reason


async def test_will_read_lists_an_engine_with_no_model_for_questions() -> None:
    service, _, _, _, _ = await _case()
    vision_only = Engine(name="eyes", label="Eyes", key_present=True, models={"vision": "e/v"})
    _routed(service, extra={"eyes": vision_only})
    will = await service.will_read("inv-1", ANALYST)
    (eyes,) = [u for u in will.unusable if u.name == "eyes"]
    assert "no model for questions" in eyes.reason


async def test_will_read_says_in_words_when_no_engine_may_answer() -> None:
    service, _, _, _, _ = await _case()
    _routed(service, egress="none", local=False)
    will = await service.will_read("inv-1", ANALYST, engine="gemini")
    assert will.engine is None
    assert will.refused is not None and "no local extraction model" in will.refused


async def test_will_reads_refusal_names_no_dataset_to_a_caller_the_store_names_none_to() -> None:
    """ADR-099 Amendment 11: the routing's refusal names the case's datasets; a caller with no role
    is told no dataset's name, here as in `GET …/models/engines`. The analyst is told it, so the
    comparison can fail."""
    from .test_email_extraction import ANALYST as NO_ROLE

    service, _, _, _, _ = await _case()
    _routed(service, egress="none", local=False)
    named = await service.will_read("inv-1", ANALYST, engine="gemini")
    unnamed = await service.will_read("inv-1", NO_ROLE, engine="gemini")
    assert named.refused is not None and "“Open”" in named.refused
    assert unnamed.engine is None and unnamed.refused is not None
    assert "Open" not in unnamed.refused and "no local extraction model" in unnamed.refused
    assert all("Open" not in u.reason for u in unnamed.unusable)


async def test_asks_refusal_names_no_dataset_to_a_caller_the_store_names_none_to() -> None:
    """The same leak on the question's own 409 (`model_egress_refused`): the words are the same as
    *will read* gives that caller."""
    from services.api.model_routing import ModelEgressRefused

    from .test_email_extraction import ANALYST as NO_ROLE

    service, _, _, _, _ = await _case()
    _routed(service, egress="none", local=False)
    with pytest.raises(ModelEgressRefused) as named:
        await service.ask("inv-1", "Who?", ANALYST, engine="gemini")
    with pytest.raises(ModelEgressRefused) as unnamed:
        await service.ask("inv-1", "Who?", NO_ROLE, engine="gemini")
    assert "“Open”" in str(named.value)
    assert "Open" not in str(unnamed.value) and "no local extraction model" in str(unnamed.value)


def test_the_panel_says_whole_cases_line_in_the_servers_own_words() -> None:
    """One wording for what *Whole case* does (ADR-098 Amendment 9): the panel's line, shown before
    anything is asked, is the server's."""
    from pathlib import Path

    panel = (
        Path(__file__).resolve().parents[4]
        / "OspreyFlow_Core/apps/workspace/src/questions/QuestionsPanel.tsx"
    ).read_text(encoding="utf-8")
    assert f'"{WHOLE_CASE_LINE}"' in " ".join(panel.split())


# --- the routes -------------------------------------------------------------------------------


async def test_the_route_refuses_nothing_to_read_and_whole_case_in_words() -> None:
    from services.api.app import _nothing_to_read_handler, _read_from_unavailable_handler

    nothing = await _nothing_to_read_handler(None, NothingToReadError("Nothing is selected."))  # type: ignore[arg-type]
    assert nothing.status_code == 422
    assert json.loads(bytes(nothing.body)) == {
        "error": "nothing_to_read", "detail": "Nothing is selected."
    }
    later = await _read_from_unavailable_handler(None, ReadFromUnavailableError())  # type: ignore[arg-type]
    body = json.loads(bytes(later.body))
    assert later.status_code == 422 and body["error"] == "read_from_unavailable"
    assert "Whole case" in body["detail"]


def test_no_documents_is_no_longer_a_refusal() -> None:
    from services.api import app as app_module
    from services.api import questions

    assert not hasattr(questions, "NoDocumentsError")
    assert not hasattr(app_module, "_no_documents_handler")


async def test_a_selected_hidden_id_is_the_same_as_one_that_is_not_there_in_will_read() -> None:
    nodes, links, docs = _with_hidden()
    service, _, _, _, _ = await _case(nodes, links, documents=docs)
    # A selection of nothing the reader can see is nothing to read, the same as one not there.
    with pytest.raises(NothingToReadError) as w:
        await service.will_read("inv-1", ANALYST, selected_node_ids=[HIDDEN_PERSON])
    with pytest.raises(NothingToReadError) as a:
        await service.ask("inv-1", "Who?", ANALYST, selected_node_ids=[HIDDEN_PERSON])
    with pytest.raises(NothingToReadError) as b:
        await service.ask("inv-1", "Who?", ANALYST, selected_node_ids=["no-such-node"])
    assert a.value.words == b.value.words == w.value.words

