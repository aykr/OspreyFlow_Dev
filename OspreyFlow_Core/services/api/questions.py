"""Questions to the model about a case's documents (`06_DECISIONS.md` ADR-098 decision 4).

An analyst asks the model about what they choose to read from (ADR-098 Amendment 7): *Selected
items* (the selection, its links and their Documents), *Everything on the graph* (every item, link
and Document they can see), or *Whole case* (ADR-098 Amendment 9: the case's search service, called
as the analyst with the question's own words; what it finds are numbered sources `[S-n]`, and a
Document the reader opens is read whole). A selection is the default when there is one. The model
reads every Document in that scope that the analyst can see, whole, and answers from them and the
graph facts, saying which it draws on. With no Document to read it answers from the links and
events, and the answer's `read` summary says so; there is no refusal for want of documents. The same
summary, counted as the analyst, is given before asking by *will read*
(`QuestionsService.will_read`), with the engine the routing will use and the engines it cannot, each
with its reason. Anything it proposes (an entity, with the words that name it) is a pending finding
in the same review queue as an extraction's, inferred until a person accepts it (rule 5), and placed
in the Document where its words are, or left out and counted when they are not there. The
conversation is kept with the case, or with the view it was asked in, read then only by those who
may see the view (the owner's ruling of 8 November 2026).

**Who may ask, and what the model is shown.** The case level is the route's (Editor to ask, since a
question writes findings; Viewer to read the conversation). What the model reads is
`WorkingSetService.visible_membership`, the same handling filter every read applies, so a Document
above the analyst is never sent to the model and a citation of its number is not an answer about it
(rule 3). Documents that together are longer than the model can read at once are refused by name
and size, never cut and answered from in part (rule 2).

**Graph facts (`06_DECISIONS.md` ADR-129 decision 1).** With the documents the model is given an
evidence brief (`evidence_brief.py`): the analyst's selection and one link around it, or the whole
view with no selection, from the same projection, as the analyst. It cites a fact as `[G-n]`; the
answer carries the node and link ids each stands for, for the Glass, and the model never sees an id.
The brief and the documents share one budget, and past it the question is refused with the typed
`limit_exceeded` and its three options, never trimmed. A `[G-n]` the brief does not hold is dropped
from the answer and counted unplaced.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import asyncpg
from pydantic import BaseModel, Field, model_validator
from services.extract.candidates import ExtractionCandidate
from services.extract.recognised import properties_for

from conduit_common.identity import new_edge_id, new_id
from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from ports.model import ModelPort
from schemas.analytics import EventFilter, TrendInterval, TrendRequest
from schemas.domain import (
    EdgeWrite,
    Handling,
    Interval,
    Node,
    OntologySchema,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from schemas.model import ExtractionRequest
from schemas.questions import ReadSummary, UnusableEngine, WillRead
from schemas.search import MAX_QUERY_CHARS, SearchPageRequest, SearchPageResponse

from .dataset_scope import refuse_writing_in_an_unconverted_case
from .datasets import DatasetStore
from .document_reader import DocumentReaderService
from .email_extraction import _edge_from_write
from .event_scope import CaseRecords, own_events_only
from .evidence_brief import (
    EvidenceBrief,
    EvidenceScope,
    cited_numbers,
    display_name,
    scope_of,
    strip_unheld,
    write_brief,
)
from .link_ids import as_stored
from .model_routing import (
    LOCAL,
    LOCAL_LABEL,
    EngineRefused,
    ModelEgressRefused,
    ModelRoutes,
    RoutedModel,
)
from .review import (
    DocumentNotFoundError,
    ExtractionCandidateNotFoundError,
    ExtractionCandidateRecord,
    ExtractionCandidateStore,
    accept_candidate,
    reject_candidate,
)
from .working_set.models import DeltaAdd, NarrowingFilter
from .working_set.service import WorkingSetService

#: How much document text one question may send the model: the extraction model is served with a
#: 32,768-token context (ADR-095), which also holds the instructions, the question and the answer.
QUESTIONS_MAX_CHARS = 80_000
MAX_QUESTION_CHARS = 2_000
#: The furthest back the brief's events per month reach: a hundred years, so the trend's own
#: default bound (104 periods) never refuses a question that is otherwise within the budget.
MAX_BRIEF_MONTHS = 1200
#: How many ids a selection may name: the Glass sends the nodes selected on the canvas.
MAX_SELECTION = 2_000
MENTIONED_IN = "MENTIONED_IN"
DOCUMENT_TYPE = "Document"
PROPOSABLE_TYPES = ("Person", "Organisation", "Location", "Endpoint")

_INSTRUCTIONS = (
    "You answer an analyst's question using only the numbered documents below. Say which "
    "documents your answer draws on by their numbers, in the answer as [n] and in `cited`. If "
    "the documents do not answer it, say so. In `entities`, list the people, organisations, "
    "places and identifiers (email addresses, phone numbers) your answer rests on, each with "
    "the number of the document it is in and `quote`, the exact words in that document that "
    "name it. Describe patterns (who wrote to whom, when, about what) in the answer."
)

#: In place of `_INSTRUCTIONS` when the scope holds no Document with text to read (ADR-098
#: Amendment 7): the question is answered from the graph facts alone, never refused.
_NO_DOCUMENTS_INSTRUCTIONS = (
    "You answer an analyst's question. There are no documents to read: answer using only the "
    "graph facts below, and say so if they do not answer it. Leave `cited` and `entities` empty. "
    "Describe patterns (who is linked to whom, when, how often) in the answer."
)

#: *Whole case* (ADR-098 Amendment 9): one page of the case's search, at the most it gives Ask
#: (`SEARCH_RESPONSE_SHAPE.md` note 5). A second page is never read; `more` says there was one.
WHOLE_CASE_PAGE = 50
#: The one line the panel and the answer's read line show under *Whole case*.
WHOLE_CASE_LINE = "Whole case finds things by their names and words, not by what they mean."

#: In place of `_NO_DOCUMENTS_INSTRUCTIONS` under *Whole case* when no Document is read whole.
_NO_DOCUMENTS_CASE_INSTRUCTIONS = (
    "You answer an analyst's question. There are no documents to read whole: answer using only "
    "the sources below, and say so if they do not answer it. Leave `cited` and `entities` empty."
)

#: Added to the instructions under *Whole case*, when the search found something.
_SEARCH_INSTRUCTIONS = (
    "Below are sources found in the case by searching for the words of the question, numbered "
    "[S-n], each with why it was found and, for a document found by its words, the passage that "
    "matched. Use them as well. Say which sources your answer draws on by their numbers, in the "
    "answer as [S-n] and in `search_cited`. Cite only numbers that are listed; do not invent one. "
    "They were found by names and words, not by meaning, so a source may not be about the "
    "question."
)
_SEARCH_CITATION = re.compile(r"\[S-(\d+)\]")
_SEARCH_MARKER = re.compile(r"( ?)\[S-(\d+)\]")

#: Added to the instructions only when there are graph facts to read.
_GRAPH_INSTRUCTIONS = (
    "Below the documents are graph facts about the case: the entities in scope, the links among "
    "them as numbered facts [G-n], and the events per month. Use them as well as the documents. "
    "Say which facts your answer draws on by their numbers, in the answer as [G-n] and in "
    "`graph_cited`. Cite only numbers that are listed; do not invent one. A fact is not a "
    "document: do not give a document number for it."
)


def _schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "cited": {"type": "array", "items": {"type": "integer"}},
            "graph_cited": {"type": "array", "items": {"type": "integer"}},
            "search_cited": {"type": "array", "items": {"type": "integer"}},
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": list(PROPOSABLE_TYPES)},
                        "name": {"type": "string"},
                        "document": {"type": "integer"},
                        "quote": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["type", "name", "document", "quote"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["answer", "cited", "entities"],
        "additionalProperties": False,
    }


class Citation(BaseModel):
    document_id: str
    title: str | None = None


class GraphCitation(BaseModel):
    """A `[G-n]` the answer cites and the ids it stands for, so the Glass can select them and bring
    them into view. The model is never given these ids (rule 7)."""

    number: int
    label: str
    node_ids: list[str]
    link_ids: list[str]


class SearchCitation(BaseModel):
    """An `[S-n]` the answer cites (ADR-129 Amendment 5): a record the case's search found for the
    question's words, and the ids it stands for (a merged entity's visible members), so the Glass
    can select them or bring them onto the canvas. The model is never given these ids (rule 7)."""

    number: int
    label: str
    #: The record's name as the canvas writes it (`canvas_label`), and its type.
    name: str
    type: str
    #: The search's own words for why it was found ("Sounds like 'Kestrel'").
    why: str
    node_ids: list[str]


#: What a question reads from (ADR-098 Amendments 7 and 9). `case` is *Whole case*, through the
#: case's search service.
ReadFrom = Literal["selection", "graph", "case"]


class QuestionEntry(BaseModel):
    """One question and its answer, as kept with the case."""

    id: str
    investigation_id: str
    author: str
    question: str
    answer: str
    document_ids: list[str] = Field(default_factory=list)
    #: Every Document the model read for this answer: a reader who cannot see one of them is not
    #: shown the entry (rule 3), since its words may come from any.
    read_ids: list[str] = Field(default_factory=list)
    candidate_ids: list[str] = Field(default_factory=list)
    unplaced: int = 0
    model: str
    created_at: datetime
    #: ADR-135: the engine that answered (`local` or a provider's name); `None` for an answer kept
    #: before engines were recorded.
    engine: str | None = None
    #: Every node and link the evidence brief was drawn from, held like `read_ids`: a reader who
    #: may not see one of them is not shown the entry (rule 3).
    graph_node_ids: list[str] = Field(default_factory=list)
    graph_link_ids: list[str] = Field(default_factory=list)
    graph_citations: list[GraphCitation] = Field(default_factory=list)
    #: The distinct handlings of the events the brief's per-month counts were made from, counted as
    #: the asker. A reader who may not view one of them is not shown the entry (rule 3): the figures
    #: in its words would count an event they cannot see. Empty for an entry with no counted event.
    event_handlings: list[Handling] = Field(default_factory=list)
    #: The cases whose events the counts were read from besides the case itself: the ancestors the
    #: asker could see at Viewer (`visible_ancestors`). A reader whose own visible ancestors do not
    #: include every one is not shown the entry (rule 3): they could not have counted those events
    #: by asking. `None` is "not recorded" (a row from before this was kept), which is not "none":
    #: `[]` is recorded, and no ancestor was read. It also marks `event_handlings` as recorded,
    #: since the column's earlier default of '[]' cannot be told from a real empty list.
    event_scopes: list[str] | None = None
    #: The case view the question was asked in (ADR-144 decision 4; the owner's ruling of 8
    #: November 2026 on L3.2's Q2): its conversation is kept with the view, read only by those who
    #: may see the view. `None` for the case's own conversation.
    view_id: str | None = None
    #: What the question read (ADR-098 Amendment 7); `None` for an entry kept before it was.
    read: ReadSummary | None = None
    #: *Whole case*: every record its sources stand for, held like `read_ids` (rule 3), and checked
    #: by the graph's own access step, since a record found by search need not be on the canvas.
    search_node_ids: list[str] = Field(default_factory=list)
    search_citations: list[SearchCitation] = Field(default_factory=list)


class QuestionAnswer(BaseModel):
    """A question as the Glass shows it: the answer, what it cites (those the reader may see) and
    its proposals with their present state (those of the reader's unit)."""

    id: str
    author: str
    #: Resolved at read time, never stored (`06_DECISIONS.md` ADR-106).
    author_name: str | None = None
    question: str
    answer: str
    citations: list[Citation]
    candidates: list[ExtractionCandidateRecord]
    #: Proposals and graph citations left out: the words are not in the document named, or the
    #: fact is not in the brief.
    unplaced: int
    created_at: datetime
    graph_citations: list[GraphCitation] = Field(default_factory=list)
    #: ADR-135 decision 4: which engine (`local` or a provider's name) and which model produced the
    #: answer. `engine` is `None` for an answer kept before engines were recorded.
    engine: str | None = None
    model: str | None = None
    #: ADR-098 Amendment 7: what was read; `None` for an answer kept before it was recorded.
    read: ReadSummary | None = None
    #: ADR-129 Amendment 5: the `[S-n]` it cites, under *Whole case*.
    search_citations: list[SearchCitation] = Field(default_factory=list)


class QuestionAccepted(BaseModel):
    node_id: str
    delta: DeltaAdd


class ScopeRequest(BaseModel):
    """What a question is asked over: the body of *will read*, and of a question with its words."""

    #: ADR-098 Amendment 7: *Selected items*, *Everything on the graph* or *Whole case*; none is the
    #: selection when there is one, else the graph.
    read_from: ReadFrom | None = None
    #: What the analyst has selected on the canvas: the evidence brief is these and one link around
    #: them. Nothing selected is the whole view. An id the analyst may not see selects nothing, as
    #: one that does not exist does.
    selected_node_ids: list[str] = Field(default_factory=list, max_length=MAX_SELECTION)
    selected_link_ids: list[str] = Field(default_factory=list, max_length=MAX_SELECTION)
    #: The timeline window, when one is set: only links whose interval overlaps it, and only events
    #: inside it, are in the brief ("narrow the timeline window" is one of the limit's options).
    window: Interval | None = None
    #: ADR-135 decision 4: the engine the analyst chose (`local` or an enabled provider's name,
    #: from `GET /v1/models/engines`); none is the role's default. The route still decides.
    engine: str | None = Field(default=None, min_length=1, max_length=64)
    #: The case view asked in (*Ask the model about these*, ADR-144 decision 4): the model reads its
    #: Documents alone, and the conversation is kept with it.
    view_id: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _window_runs_forward(self) -> ScopeRequest:
        if (
            self.window is not None
            and self.window.valid_to is not None
            and self.window.valid_from > self.window.valid_to
        ):
            raise ValueError("the window ends before it starts")
        return self


class WillReadRequest(ScopeRequest):
    """*Will read*'s body: the scope, and under *Whole case* the question as typed so far, since its
    words are what the search is asked (ADR-098 Amendment 9)."""

    question: str | None = Field(default=None, max_length=MAX_QUESTION_CHARS)


class AskRequest(ScopeRequest):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


#: The identifiers a thing with no name is known by, in the canvas's order
#: (`apps/workspace/src/canvas/labelChoices.ts`, `IDENTIFYING`).
_CANVAS_IDENTIFYING = (
    "account_number", "imei", "imsi", "e164", "email", "handle", "org_ref", "registration",
)  # fmt: skip


def canvas_label(node: Node) -> str:
    """A node as the canvas names it by default (`labelChoices.ts`'s `defaultLabel`): a person as
    "FAMILY, Given", a thing by its name, title, normalised value or identifier. Failing all of
    those it is called as the brief calls it (`display_name`), never by its id (rule 7). Used for
    "About: …", which the person reads beside the canvas."""
    props = node.properties

    def text(key: str) -> str | None:
        value = props.get(key)
        return " ".join(value.split()) or None if isinstance(value, str) else None

    family = text("family_name")
    if family is not None:
        given = text("given_names")
        return f"{family}, {given}" if given is not None else family
    for key in ("name", "title", "value_normalised", *_CANVAS_IDENTIFYING):
        found = text(key)
        if found is not None:
            return found
    return display_name(node)


def shared_handling(handlings: Sequence[Handling]) -> Handling | None:
    """The handling a question about several Documents is sent under (ADR-114 Amendment 6): theirs
    when every one carries the same handling code, otherwise none — and material whose handling is
    not given is never sent to a client's provider (`model_routing.py`)."""
    codes = {h.handling_code for h in handlings}
    return handlings[0] if len(codes) == 1 else None


class NothingToReadError(Exception):
    """The scope holds nothing the analyst can see: nothing selected that their view holds, or an
    empty graph. A selected id they may not see is answered as one that does not exist."""

    def __init__(self, words: str) -> None:
        super().__init__(words)
        self.words = words


class ReadFromUnavailableError(Exception):
    """*Whole case* asked of a service built with no case search (a test's, or a deployment wired
    without one): refused in words, never answered from something else."""

    words = (
        "Whole case is not available on this deployment. Choose Selected items or Everything on "
        "the graph."
    )

    def __init__(self) -> None:
        super().__init__(self.words)


class QuestionTooLongToSearchError(Exception):
    """*Whole case* with a question longer than the search takes (ADR-098 Amendment 9): refused in
    words that say what to do, never cut to fit and never reduced to keywords (rule 2)."""

    def __init__(self, length: int) -> None:
        self.length = length
        self.words = (
            f"Whole case searches the case with your question's own words, which can be at most "
            f"{MAX_QUERY_CHARS} characters; yours has {length}. Shorten the question, or choose "
            "Selected items or Everything on the graph to ask it as it is."
        )
        super().__init__(self.words)


_NOTHING_SELECTED = (
    "Nothing is selected. Select items on the canvas, or choose Everything on the graph."
)
_SELECTION_NOT_HELD = (
    "Nothing you selected is on the graph. Select items on the canvas, or choose Everything on the "
    "graph."
)
_EMPTY_GRAPH = "The graph holds nothing to read. Add items to the canvas first."
_NO_QUESTION_YET = "Whole case searches with your question's words: type the question first."
_NO_MATCHES = (
    "Nothing in the case matches your question's words. Try the names or words the records hold, "
    "or choose Everything on the graph."
)

#: The search, as the asker, for *Whole case*: `(investigation_id, principal, request)`. Built in
#: `app.py` from `search_service.search_page` with the dependencies `POST …/search` uses, so the
#: asker's own access filter goes into the index's query (rule 3).
CaseSearch = Callable[[str, Principal, SearchPageRequest], Awaitable[SearchPageResponse]]


@dataclass(frozen=True)
class _Source:
    """One `[S-n]`: a record the case's search found, as the model reads it and the Glass cites
    it."""

    number: int
    name: str
    type: str
    why: str
    node_ids: tuple[str, ...]
    #: A Document's matched passage, when the reader does not open it; "" otherwise.
    passage: str
    handlings: tuple[Handling, ...]

    def line(self) -> str:
        said = f"[S-{self.number}] {self.type}: {self.name}. Found because: {self.why}."
        return f'{said}\n  Passage: "{self.passage}"' if self.passage else said


def _empty_case_fields() -> dict[str, Any]:
    """The *Whole case* fields of a summary read from another choice."""
    return {"found": 0, "passages": 0, "limited_reason": None, "counts_exact": True, "more": False}


@dataclass(frozen=True)
class _Material:
    """What one question reads, gathered as the asker, for the question and *will read* alike."""

    documents: list[tuple[str, str | None, str, Handling]]
    brief: EvidenceBrief
    event_handlings: list[Handling]
    event_scopes: list[str]
    read: ReadSummary
    #: *Whole case*'s sources, in their numbered order; empty otherwise.
    sources: tuple[_Source, ...] = ()

    @property
    def handling(self) -> Handling | None:
        return shared_handling(
            [h for _, _, _, h in self.documents]
            + list(self.brief.handlings)
            + [h for s in self.sources for h in s.handlings]
        )

    @property
    def sources_text(self) -> str:
        return "\n".join(s.line() for s in self.sources)


#: The third option: ask in a case view of fewer Documents (ADR-144 decision 4).
QuestionsOption = Literal["narrow_selection", "narrow_timeline_window", "ask_in_a_view"]
_QUESTIONS_OPTIONS: tuple[QuestionsOption, ...] = (
    "narrow_selection",
    "narrow_timeline_window",
    "ask_in_a_view",
)


class QuestionsLimitExceeded(BaseModel):
    """What a question past the budget is answered with (`06_DECISIONS.md` ADR-129 decision 1): the
    typed `limit_exceeded` and its three options, never a trimmed brief or a cut document (rule 2).
    The two figures name what is large; both are of what the reader may see, so the refusal says
    nothing about what they may not."""

    error: Literal["limit_exceeded"] = "limit_exceeded"
    cap_kind: Literal["characters"] = "characters"
    cap: int
    would_be: int
    documents_chars: int
    evidence_brief_chars: int
    options: list[QuestionsOption] = Field(default_factory=lambda: list(_QUESTIONS_OPTIONS))


class QuestionsTooLargeError(Exception):
    """The documents and the evidence brief together are longer than the model can read at once
    (rule 2: never cut)."""

    def __init__(
        self, would_be: int, limit: int, *, documents_chars: int = 0, brief_chars: int = 0
    ) -> None:
        super().__init__(f"{would_be} characters against a limit of {limit}")
        self.would_be = would_be
        self.limit = limit
        self.documents_chars = documents_chars
        self.brief_chars = brief_chars

    def body(self) -> QuestionsLimitExceeded:
        return QuestionsLimitExceeded(
            cap=self.limit,
            would_be=self.would_be,
            documents_chars=self.documents_chars,
            evidence_brief_chars=self.brief_chars,
        )


def _fits(documents_chars: int, brief_chars: int) -> None:
    """One budget for the documents and the evidence brief together (rule 2). Read at the call, so
    a test can lower it."""
    if documents_chars + brief_chars > QUESTIONS_MAX_CHARS:
        raise QuestionsTooLargeError(
            documents_chars + brief_chars,
            QUESTIONS_MAX_CHARS,
            documents_chars=documents_chars,
            brief_chars=brief_chars,
        )


class QuestionStore(Protocol):
    async def add(self, entry: QuestionEntry) -> None: ...
    async def list_for_case(
        self, investigation_id: str, view_id: str | None = None
    ) -> list[QuestionEntry]: ...


class InMemoryQuestionStore:
    """The store for tests and a process with no Postgres: the same two calls."""

    def __init__(self) -> None:
        self.entries: list[QuestionEntry] = []

    async def add(self, entry: QuestionEntry) -> None:
        self.entries.append(entry)

    async def list_for_case(
        self, investigation_id: str, view_id: str | None = None
    ) -> list[QuestionEntry]:
        """The case's own conversation, or one view's (`view_id`): never the two mixed."""
        return sorted(
            (
                e
                for e in self.entries
                if e.investigation_id == investigation_id and e.view_id == view_id
            ),
            key=lambda e: e.created_at,
        )


_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS case_questions (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    author TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    document_ids JSONB NOT NULL,
    read_ids JSONB NOT NULL,
    candidate_ids JSONB NOT NULL,
    unplaced INTEGER NOT NULL,
    model TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS case_questions_case_idx ON case_questions (investigation_id, created_at);
ALTER TABLE case_questions ADD COLUMN IF NOT EXISTS graph_node_ids JSONB NOT NULL DEFAULT '[]';
ALTER TABLE case_questions ADD COLUMN IF NOT EXISTS graph_link_ids JSONB NOT NULL DEFAULT '[]';
ALTER TABLE case_questions ADD COLUMN IF NOT EXISTS graph_citations JSONB NOT NULL DEFAULT '[]';
ALTER TABLE case_questions ADD COLUMN IF NOT EXISTS event_handlings JSONB NOT NULL DEFAULT '[]';
-- NULL is "not recorded": every row written before this column existed, including those whose
-- event_handlings holds the earlier default '[]' (which a real "no events" cannot be told from).
ALTER TABLE case_questions ADD COLUMN IF NOT EXISTS event_scopes JSONB;
-- ADR-135: the engine that answered; NULL for an answer kept before engines were recorded.
ALTER TABLE case_questions ADD COLUMN IF NOT EXISTS engine TEXT;
-- ADR-144 decision 4: the view a question was asked in; NULL for the case's own conversation.
ALTER TABLE case_questions ADD COLUMN IF NOT EXISTS view_id TEXT;
-- ADR-098 Amendment 7: what the question read; NULL for an answer kept before it was recorded.
ALTER TABLE case_questions ADD COLUMN IF NOT EXISTS read JSONB;
-- ADR-098 Amendment 9 and ADR-129 Amendment 5: Whole case's sources.
ALTER TABLE case_questions ADD COLUMN IF NOT EXISTS search_node_ids JSONB NOT NULL DEFAULT '[]';
ALTER TABLE case_questions ADD COLUMN IF NOT EXISTS search_citations JSONB NOT NULL DEFAULT '[]';
"""


def _read_of(raw: str | None) -> ReadSummary | None:
    """A kept summary; one kept before *Whole case* existed has none of its fields, and read none
    of what they count."""
    if raw is None:
        return None
    return ReadSummary.model_validate({**_empty_case_fields(), **json.loads(raw)})


class PostgresQuestionStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PostgresQuestionStore:
        # Bounded, as every store here is: the default ten-connection floor per store pushed the
        # lifespan past its ceiling
        # (`test_app_lifespan_does_not_reopen_the_unbounded_pool_ceiling`).
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def add(self, entry: QuestionEntry) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO case_questions (id, investigation_id, author, question, answer, "
                "document_ids, read_ids, candidate_ids, unplaced, model, created_at, "
                "graph_node_ids, graph_link_ids, graph_citations, event_handlings, event_scopes, "
                "engine, view_id, read, search_node_ids, search_citations) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, "
                "$17, $18, $19, $20, $21)",
                entry.id,
                entry.investigation_id,
                entry.author,
                entry.question,
                entry.answer,
                json.dumps(entry.document_ids),
                json.dumps(entry.read_ids),
                json.dumps(entry.candidate_ids),
                entry.unplaced,
                entry.model,
                entry.created_at,
                json.dumps(entry.graph_node_ids),
                json.dumps(entry.graph_link_ids),
                json.dumps([c.model_dump() for c in entry.graph_citations]),
                json.dumps([h.model_dump(mode="json") for h in entry.event_handlings]),
                None if entry.event_scopes is None else json.dumps(entry.event_scopes),
                entry.engine,
                entry.view_id,
                None if entry.read is None else entry.read.model_dump_json(),
                json.dumps(entry.search_node_ids),
                json.dumps([c.model_dump() for c in entry.search_citations]),
            )

    async def list_for_case(
        self, investigation_id: str, view_id: str | None = None
    ) -> list[QuestionEntry]:
        """The case's own conversation, or one view's (`view_id`): never the two mixed."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM case_questions WHERE investigation_id = $1 "
                "AND view_id IS NOT DISTINCT FROM $2 ORDER BY created_at",
                investigation_id,
                view_id,
            )
        return [
            QuestionEntry(
                **{
                    **dict(row),
                    "document_ids": json.loads(row["document_ids"]),
                    "read_ids": json.loads(row["read_ids"]),
                    "candidate_ids": json.loads(row["candidate_ids"]),
                    "graph_node_ids": json.loads(row["graph_node_ids"]),
                    "graph_link_ids": json.loads(row["graph_link_ids"]),
                    "graph_citations": json.loads(row["graph_citations"]),
                    "event_handlings": json.loads(row["event_handlings"]),
                    "event_scopes": (
                        None if row["event_scopes"] is None else json.loads(row["event_scopes"])
                    ),
                    "read": _read_of(row["read"]),
                    "search_node_ids": json.loads(row["search_node_ids"]),
                    "search_citations": json.loads(row["search_citations"]),
                }
            )
            for row in rows
        ]


def _locate(text: str, words: str) -> tuple[int, int] | None:
    wanted = " ".join(words.split())
    if not wanted:
        return None
    start = text.lower().find(wanted.lower())
    return None if start < 0 else (start, start + len(wanted))


class QuestionsService:
    def __init__(
        self,
        working_set: WorkingSetService,
        reader: DocumentReaderService,
        graph: GraphPort,
        model: ModelPort,
        ontology: OntologySchema,
        candidates: ExtractionCandidateStore,
        store: QuestionStore,
        *,
        default_model: str,
        analytics: AnalyticsPort,
        datasets: DatasetStore,
        investigations: CaseRecords | None,
        case_search: CaseSearch | None = None,
    ) -> None:
        self._case_search = case_search
        self._working_set = working_set
        self._reader = reader
        self._graph = graph
        self._model = model
        self._ontology = ontology
        self._candidates = candidates
        self._store = store
        self._default_model = default_model
        self._analytics = analytics
        self._datasets = datasets
        self._investigations = investigations

    async def _documents(
        self, investigation_id: str, principal: Principal, nodes: Sequence[Node]
    ) -> tuple[list[tuple[str, str | None, str, Handling]], int]:
        """`(id, title, text, handling)` of every Document among `nodes` (the scope, as the analyst
        may see it) that has text, and how many have none (an image, say): counted, never read."""
        found: list[tuple[str, str | None, str, Handling]] = []
        without_text = 0
        for node in sorted(
            (n for n in nodes if n.type == DOCUMENT_TYPE),
            key=lambda n: str(n.properties.get("title", n.id)),
        ):
            view = await self._reader.read(investigation_id, node.id, principal)
            if view.text.strip():
                found.append((node.id, view.title, view.text, node.handling))
            else:
                without_text += 1
        return found, without_text

    async def _events_per_month(
        self,
        investigation_id: str,
        principal: Principal,
        link_ids: Sequence[str],
        window: Interval | None,
    ) -> tuple[list[tuple[str, int]], list[Handling], list[str]]:
        """The events on the links in scope, counted per month as the analyst: an event they may
        not see moves no figure (the store applies the access filter in its own query). Asked only
        by link, never by node: an event on a link the analyst may not see is not theirs to count,
        and an empty list of links would not restrict the store at all, so no link, no question.
        Returns, with the counts and the handlings counted, the other cases whose events were read:
        none, since a case counts its own events alone (`event_scope.py`)."""
        if not link_ids:
            return [], [], []
        base = EventFilter(
            investigation_scope=investigation_id, edge_ids=list(link_ids), window=window
        )
        trend = await self._analytics.trend(
            TrendRequest(
                filter=own_events_only(base),
                interval=TrendInterval.MONTH,
                max_periods=MAX_BRIEF_MONTHS,
            ),
            principal,
        )
        months = [
            (point.period_start.strftime("%Y-%m"), int(point.value))
            for point in sorted(trend.points, key=lambda p: p.period_start)
            if point.value
        ]
        handlings = [
            Handling(
                classification=h.classification,
                handling_code=h.handling_code,
                originator=h.originator,
                owning_unit=h.owning_unit,
            )
            for h in trend.handlings
        ]
        return months, handlings, []

    async def _evidence_brief(
        self,
        investigation_id: str,
        principal: Principal,
        scope: EvidenceScope,
        window: Interval | None,
        documents_chars: int,
    ) -> tuple[EvidenceBrief, list[Handling], list[str], int]:
        """The brief for what `principal` selected, from their own view, refused whole when it and
        the documents do not fit together (rule 2). The cap is checked before the events are read,
        so the links the events are asked over are only ever as many as the budget allows. Returns,
        with the brief, the distinct handlings of the events it counted and the ancestor cases they
        were read from: kept with the answer, so a later reader is shown it only if they could have
        seen every one, and could have read those cases themselves (rule 3), and the number of
        events counted."""
        named = await self._datasets.of_case(investigation_id, principal)
        labels = {d.id: d.name for d in named}
        # ADR-099 Amendment 12: a composite's links carry its members' ids, so its members are
        # labelled too; only for a caller the store names datasets to (Amendment 11).
        members = [m for d in named for m in d.members]
        if members:
            labels |= {i: d.name for i, d in (await self._datasets.egress_of(members)).items()}
        brief = write_brief(scope, labels)
        _fits(documents_chars, len(brief.text))
        months, event_handlings, event_scopes = await self._events_per_month(
            investigation_id, principal, brief.link_ids, window
        )
        if months:
            brief = write_brief(scope, labels, months, event_handlings)
            _fits(documents_chars, len(brief.text))
        return brief, event_handlings, event_scopes, sum(count for _, count in months)

    async def _gather(
        self,
        investigation_id: str,
        principal: Principal,
        *,
        selected_node_ids: Sequence[str],
        selected_link_ids: Sequence[str],
        window: Interval | None,
        view_node_ids: Sequence[str] | None,
        read_from: ReadFrom | None,
        question: str | None = None,
        case_search: CaseSearch | None = None,
    ) -> _Material:
        """What a question reads (ADR-098 Amendment 7), from the asker's own view (or the part of
        it a case view holds): the scope, its Documents, the brief within the budget (rule 2), and
        the summary of it all. Refused before anything is read when there is nothing to read.
        *Whole case* is `_gather_case`'s."""
        if read_from == "case":
            return await self._gather_case(
                investigation_id,
                principal,
                question,
                view_node_ids,
                case_search if case_search is not None else self._case_search,
            )
        asked = bool(selected_node_ids) or bool(selected_link_ids)
        chosen = read_from or ("selection" if asked else "graph")
        if chosen == "selection" and not asked:
            raise NothingToReadError(_NOTHING_SELECTED)
        nodes, edges = await self._working_set.visible_membership(investigation_id, principal)
        if view_node_ids is not None:
            in_view = set(view_node_ids)
            nodes = [n for n in nodes if n.id in in_view]
            edges = [e for e in edges if e.source in in_view and e.target in in_view]
        picked_nodes = selected_node_ids if chosen == "selection" else ()
        picked_links = selected_link_ids if chosen == "selection" else ()
        scope = scope_of(
            nodes,
            edges,
            selected_node_ids=picked_nodes,
            selected_link_ids=picked_links,
            window=(
                NarrowingFilter(valid_from=window.valid_from, valid_to=window.valid_to)
                if window is not None
                else None
            ),
        )
        if not scope.nodes:
            raise NothingToReadError(_SELECTION_NOT_HELD if chosen == "selection" else _EMPTY_GRAPH)
        documents, without_text = await self._documents(investigation_id, principal, scope.nodes)
        documents_chars = sum(len(text) for _, _, text, _ in documents)
        brief, event_handlings, event_scopes, events = await self._evidence_brief(
            investigation_id, principal, scope, window, documents_chars
        )
        # Counted from the asker's view alone: a selected id it does not hold is not counted, as
        # one that does not exist is not (rule 3). A selected link is counted only when it is in
        # the scope's links (inside the window, too), so every link counted is one the kept entry
        # names in `graph_link_ids`, which a later reader must see to be shown it.
        held = {n.id: n for n in nodes}
        held_nodes = [held[i] for i in dict.fromkeys(picked_nodes) if i in held]
        wanted_links = set(picked_links)
        held_links = {e.id for e in scope.edges if e.id in wanted_links}
        read = ReadSummary(
            read_from=chosen,
            documents=len(documents),
            documents_without_text=without_text,
            items=sum(1 for n in scope.nodes if n.type != DOCUMENT_TYPE),
            links=len(scope.edges),
            events=events,
            selected=len(held_nodes) + len(held_links),
            first_selected=canvas_label(held_nodes[0]) if held_nodes else None,
            **_empty_case_fields(),
        )
        return _Material(documents, brief, event_handlings, event_scopes, read)

    async def _gather_case(
        self,
        investigation_id: str,
        principal: Principal,
        question: str | None,
        view_node_ids: Sequence[str] | None,
        case_search: CaseSearch | None,
    ) -> _Material:
        """*Whole case* (ADR-098 Amendment 9): one page of the case's search for the question's own
        words, as the asker, so a record they may not see is never found, counted, read or cited
        (rule 3). A Document the reader opens is read whole, through the reader, which checks
        access again; one it does not open (not on the canvas) is a source read as the passage the
        search matched, never whole. Every other record is a source by its name and why it was
        found. In a case view, only what the view holds is read."""
        if case_search is None:
            raise ReadFromUnavailableError()
        words = (question or "").strip()
        if not words:
            raise NothingToReadError(_NO_QUESTION_YET)
        if len(words) > MAX_QUERY_CHARS:
            raise QuestionTooLongToSearchError(len(words))
        found = await case_search(
            investigation_id,
            principal,
            SearchPageRequest(query=words, page=1, page_size=WHOLE_CASE_PAGE),
        )
        results = list(found.results)
        if view_node_ids is not None:
            in_view = set(view_node_ids)
            results = [r for r in results if r.node_ids and set(r.node_ids) <= in_view]
        nodes = {n.id: n for n in found.nodes}
        documents: list[tuple[str, str | None, str, Handling]] = []
        without_text = 0
        passages = 0
        sources: list[_Source] = []
        read = 0
        for result in results:
            members = [nodes[i] for i in result.node_ids if i in nodes]
            if not members:
                continue
            first = members[0]
            passage = ""
            if result.is_document:
                try:
                    view = await self._reader.read(investigation_id, first.id, principal)
                except DocumentNotFoundError:
                    view = None
                if view is not None:
                    read += 1
                    if view.text.strip():
                        documents.append((first.id, view.title, view.text, first.handling))
                    else:
                        without_text += 1
                    continue
                passages += 1
                passage = "".join(part.text for part in result.passage).strip()
            read += 1
            sources.append(
                _Source(
                    number=len(sources) + 1,
                    name=canvas_label(first),
                    type=result.type,
                    why=result.match.why,
                    node_ids=tuple(n.id for n in members),
                    passage=passage,
                    handlings=tuple(n.handling for n in members),
                )
            )
        if not read:
            raise NothingToReadError(_NO_MATCHES)
        material = _Material(
            documents,
            EvidenceBrief(text=""),
            [],
            [],
            ReadSummary(
                read_from="case",
                documents=len(documents),
                documents_without_text=without_text,
                items=len(sources) - passages,
                links=0,
                events=0,
                selected=0,
                first_selected=None,
                found=read,
                passages=passages,
                limited_reason=found.limited_reason,
                counts_exact=found.counts_exact,
                more=found.more,
            ),
            tuple(sources),
        )
        _fits(sum(len(t) for _, _, t, _ in documents), len(material.sources_text))
        return material

    async def will_read(
        self,
        investigation_id: str,
        principal: Principal,
        *,
        selected_node_ids: Sequence[str] = (),
        selected_link_ids: Sequence[str] = (),
        window: Interval | None = None,
        engine: str | None = None,
        view_node_ids: Sequence[str] | None = None,
        read_from: ReadFrom | None = None,
        question: str | None = None,
        case_search: CaseSearch | None = None,
    ) -> WillRead:
        """What `ask` would read with the same scope, and the engine that would answer, decided as
        the routing will decide it on the same material (ADR-135 Amendment 12). Nothing is sent.
        The rules on what may leave for a hosted engine are the routing's own and are not changed:
        this only says what it would do."""
        material = await self._gather(
            investigation_id,
            principal,
            selected_node_ids=selected_node_ids,
            selected_link_ids=selected_link_ids,
            window=window,
            view_node_ids=view_node_ids,
            read_from=read_from,
            question=question,
            case_search=case_search,
        )
        routed = self._model if isinstance(self._model, RoutedModel) else None
        if routed is None:
            return WillRead(
                read=material.read, engine=LOCAL, engine_label=LOCAL_LABEL,
                model=self._default_model, unusable=[], refused=None,
            )  # fmt: skip
        datasets = await self._datasets.ids_of_case(investigation_id)
        routes = routed.routes
        unusable = await self._unusable(investigation_id, principal, routes, material.handling)
        try:
            choice = routed.choose(
                "extraction", self._default_model, material.handling, engine, datasets,
                await routed.held(datasets),
            )  # fmt: skip
        except EngineRefused as refused:
            return WillRead(
                read=material.read, engine=None, engine_label=None, model=None,
                unusable=unusable, refused=str(refused),
            )  # fmt: skip
        except ModelEgressRefused as refused:
            said = await self._egress_words(investigation_id, principal, refused)
            return WillRead(
                read=material.read, engine=None, engine_label=None, model=None,
                unusable=unusable, refused=str(said),
            )  # fmt: skip
        label = LOCAL_LABEL if choice.engine == LOCAL else routes.engines[choice.engine].label
        return WillRead(
            read=material.read,
            engine=choice.engine,
            engine_label=label,
            model=choice.model,
            unusable=[u for u in unusable if u.name != choice.engine],
            refused=None,
        )

    async def _egress_words(
        self, investigation_id: str, principal: Principal, refused: ModelEgressRefused
    ) -> ModelEgressRefused:
        """The routing's refusal names the case's datasets. A caller the store names none to
        (ADR-099 Amendment 11) is told the same thing without them (rule 3), as `_unusable` and
        `GET …/models/engines` tell them; the decision itself is the routing's, unchanged."""
        if await self._datasets.of_case(investigation_id, principal):
            return refused
        return ModelEgressRefused(
            "No engine may answer this question: what it reads may not be sent to the hosted "
            "engine, and this deployment has no local extraction model to use instead."
        )

    async def _unusable(
        self,
        investigation_id: str,
        principal: Principal,
        routes: ModelRoutes,
        handling: Handling | None,
    ) -> list[UnusableEngine]:
        """The hosted engines the deployment has that cannot answer this question, each with its
        reason: no model for questions, the case's data may not reach it (judged as
        `GET …/models/engines` judges it, so the datasets are named only to a caller the store
        names them to), or the material's handling may not leave."""
        named = await self._datasets.of_case(investigation_id, principal)
        case_datasets = await self._datasets.ids_of_case(investigation_id) if named else []
        held = await self._datasets.egress_of(case_datasets)
        out: list[UnusableEngine] = []
        for offered in routes.offered(case_datasets, held):
            if offered.name == LOCAL:
                continue
            reason: str | None = None
            if "extraction" not in offered.roles:
                reason = f"{offered.label} has no model for questions on this deployment."
            elif not offered.available:
                reason = offered.reason or "Not available for this case."
            elif handling is None:
                reason = (
                    "Not available for this question: what it reads carries more than one "
                    "handling code, and material whose handling is not one code is never sent to "
                    "a hosted engine."
                )
            elif handling.handling_code not in routes.sendable:
                reason = (
                    f"Not available for this question: material with handling code "
                    f"{handling.handling_code} may not be sent to a hosted engine on this "
                    "deployment."
                )
            if reason is not None:
                out.append(UnusableEngine(name=offered.name, label=offered.label, reason=reason))
        return out

    async def ask(
        self,
        investigation_id: str,
        question: str,
        principal: Principal,
        *,
        selected_node_ids: Sequence[str] = (),
        selected_link_ids: Sequence[str] = (),
        window: Interval | None = None,
        engine: str | None = None,
        view_id: str | None = None,
        view_node_ids: Sequence[str] | None = None,
        read_from: ReadFrom | None = None,
        case_search: CaseSearch | None = None,
    ) -> QuestionAnswer:
        """`view_id` and `view_node_ids`: asked in a case view the route has let the asker see
        (ADR-144 decision 4). The model reads only what the view holds of the case as the asker
        sees it, and the entry is kept with the view. `read_from`: ADR-098 Amendment 7."""
        material = await self._gather(
            investigation_id,
            principal,
            selected_node_ids=selected_node_ids,
            selected_link_ids=selected_link_ids,
            window=window,
            view_node_ids=view_node_ids,
            read_from=read_from,
            question=question,
            case_search=case_search,
        )
        documents, brief = material.documents, material.brief
        event_handlings, event_scopes = material.event_handlings, material.event_scopes
        if documents:
            numbered = "\n\n".join(
                f"Document {i}: {title or '(no title)'}\n{text}"
                for i, (_, title, text, _) in enumerate(documents, start=1)
            )
            reading = f"{_INSTRUCTIONS}\n\n{numbered}\n\n"
        elif material.sources:
            reading = f"{_NO_DOCUMENTS_CASE_INSTRUCTIONS}\n\n"
        else:
            reading = f"{_NO_DOCUMENTS_INSTRUCTIONS}\n\n"
        graph_section = f"{_GRAPH_INSTRUCTIONS}\n\n{brief.text}\n\n" if brief.text else ""
        if material.sources:
            graph_section += f"{_SEARCH_INSTRUCTIONS}\n\n{material.sources_text}\n\n"
        try:
            result = await self._model.extract(
                ExtractionRequest(
                    document_id=f"questions:{investigation_id}",
                    text=f"{reading}{graph_section}Question: {question}",
                    json_schema=_schema(),
                    model=self._default_model,
                    handling=material.handling,
                    engine=engine,
                    # ADR-136: what is sent is read from the case, so it comes from the case's
                    # datasets; a hosted engine sees it only when every one of them allows it.
                    datasets=await self._datasets.ids_of_case(investigation_id),
                )
            )
        except ModelEgressRefused as refused:
            # The same words as *will read* gives this caller (rule 3).
            raise await self._egress_words(investigation_id, principal, refused) from None
        data = result.data
        answer = str(data.get("answer") or "").strip()
        document_numbers = [n for n in data.get("cited") or [] if isinstance(n, int)]
        cited = [documents[n - 1][0] for n in document_numbers if 1 <= n <= len(documents)]

        # A fact the brief does not hold is one the model invented: dropped, in the words and in
        # the list, and counted with the proposals left out.
        listed = data.get("graph_cited")
        asked_for = cited_numbers(answer, listed if isinstance(listed, list) else [])
        held = {f.number: f for f in brief.facts}
        graph_citations = [
            GraphCitation(
                number=n,
                label=held[n].label,
                node_ids=list(held[n].node_ids),
                link_ids=list(held[n].link_ids),
            )
            for n in sorted(asked_for)
            if n in held
        ]
        answer = strip_unheld(answer, set(held))

        # The same for an `[S-n]` the sources do not hold (ADR-129 Amendment 5).
        listed_s = data.get("search_cited")
        asked_s = list(
            dict.fromkeys(
                [int(m.group(1)) for m in _SEARCH_CITATION.finditer(answer)]
                + [
                    n
                    for n in (listed_s if isinstance(listed_s, list) else [])
                    if isinstance(n, int) and not isinstance(n, bool)
                ]
            )
        )
        sources = {s.number: s for s in material.sources}
        search_citations = [
            SearchCitation(
                number=n,
                label=f"[S-{n}]",
                name=sources[n].name,
                type=sources[n].type,
                why=sources[n].why,
                node_ids=list(sources[n].node_ids),
            )
            for n in sorted(asked_s)
            if n in sources
        ]
        answer = _SEARCH_MARKER.sub(
            lambda m: m.group(0) if int(m.group(2)) in sources else "", answer
        )

        proposals: list[ExtractionCandidate] = []
        unplaced = len(asked_for) - len(graph_citations) + len(asked_s) - len(search_citations)
        for item in data.get("entities") or []:
            if not isinstance(item, dict) or item.get("type") not in PROPOSABLE_TYPES:
                unplaced += 1
                continue
            number = item.get("document")
            if not isinstance(number, int) or not 1 <= number <= len(documents):
                unplaced += 1
                continue
            document_id, _, text, _ = documents[number - 1]
            place = _locate(text, str(item.get("quote") or "")) or _locate(
                text, str(item.get("name") or "")
            )
            if place is None:
                unplaced += 1
                continue
            start, end = place
            raw = item.get("confidence")
            confidence = float(raw) if isinstance(raw, int | float) else 50.0
            proposals.append(
                ExtractionCandidate(
                    id=new_id(),
                    document_id=document_id,
                    entity_type=str(item["type"]),
                    properties=properties_for(str(item["type"]), text[start:end]),
                    confidence=max(
                        0.0, min(1.0, confidence / 100 if confidence > 1 else confidence)
                    ),
                    model=result.model,
                    locator=f"char span {start}-{end}",
                    excerpt_hash=hashlib.sha256(text[start:end].encode("utf-8")).hexdigest(),
                    handling=(await self._handling_of(investigation_id, document_id, principal)),
                )
            )
        # The reader's marks point into each document's kept text; one never extracted has none.
        for document_id, _, text, _ in documents:
            if any(p.document_id == document_id for p in proposals):
                try:
                    await self._candidates.get_document_text(document_id, principal)
                except DocumentNotFoundError:
                    await self._candidates.store_document_text(document_id, text, principal)
        records = (
            await self._candidates.store(
                proposals, principal, **({"view_id": view_id} if view_id is not None else {})
            )
            if proposals
            else []
        )
        entry = QuestionEntry(
            id=new_id(),
            investigation_id=investigation_id,
            author=principal.id,
            question=question,
            answer=answer,
            document_ids=list(dict.fromkeys(cited)),
            read_ids=[d for d, _, _, _ in documents],
            candidate_ids=[r.id for r in records],
            unplaced=unplaced,
            model=result.model,
            engine=result.engine,
            created_at=datetime.now(UTC),
            graph_node_ids=list(brief.node_ids),
            graph_link_ids=list(brief.link_ids),
            graph_citations=graph_citations,
            event_handlings=event_handlings,
            event_scopes=event_scopes,
            view_id=view_id,
            read=material.read,
            search_node_ids=list(dict.fromkeys(i for s in material.sources for i in s.node_ids)),
            search_citations=search_citations,
        )
        await self._store.add(entry)
        titles = {d: t for d, t, _, _ in documents}
        return QuestionAnswer(
            id=entry.id,
            author=entry.author,
            question=question,
            answer=answer,
            citations=[Citation(document_id=d, title=titles.get(d)) for d in entry.document_ids],
            candidates=records,
            unplaced=unplaced,
            created_at=entry.created_at,
            graph_citations=graph_citations,
            engine=entry.engine,
            model=entry.model,
            read=entry.read,
            search_citations=search_citations,
        )

    async def _handling_of(
        self, investigation_id: str, document_id: str, principal: Principal
    ) -> Handling:
        node = await self._working_set.visible_node(investigation_id, document_id, principal)
        if node is None:
            raise DocumentNotFoundError(document_id)
        return node.handling

    async def history(
        self, investigation_id: str, principal: Principal, *, view_id: str | None = None
    ) -> list[QuestionAnswer]:
        """The case's conversation for `principal`: the answers asked over Documents they can all
        see, with the proposals their unit owns, each in its present state. An answer read from a
        Document above them is left out, without a word to say so (rule 3)."""
        out: list[QuestionAnswer] = []
        entries = await self._store.list_for_case(investigation_id, view_id)
        seen_nodes: set[str] = set()
        seen_links: set[str] = set()
        if any(e.graph_node_ids or e.graph_link_ids for e in entries):
            # One read of the reader's own view, not one per element a brief was drawn from.
            visible_nodes, visible_links = await self._working_set.visible_membership(
                investigation_id, principal
            )
            seen_nodes = {n.id for n in visible_nodes}
            seen_links = {e.id for e in visible_links}
        for entry in entries:
            if not await self._sees_all(investigation_id, entry.read_ids, principal):
                continue
            # A *Whole case* source need not be on the canvas: checked by the graph's own access
            # step, as the search found it (rule 3).
            if entry.search_node_ids and len(
                await self._graph.get_nodes(entry.search_node_ids, principal)
            ) < len(set(entry.search_node_ids)):
                continue
            if not (
                seen_nodes.issuperset(entry.graph_node_ids)
                and seen_links.issuperset(entry.graph_link_ids)
            ):
                continue
            # The per-month counts in the words were made as the asker: a reader who may not view
            # an event they counted is not shown the answer (rule 3).
            if entry.event_scopes is None:
                # Not recorded: the counts may have been made from events whose handling or case
                # nobody kept. With graph facts that is unknown, so only the author is shown it.
                if (entry.graph_link_ids or entry.graph_citations) and entry.author != principal.id:
                    continue
            else:
                if not self._working_set.may_view_all(entry.event_handlings, principal):
                    continue
                # Counted from other cases' events as well as this one's, before a case counted its
                # own alone (ADR-144 Amendment 1): no reader now reads those cases' events here, so
                # none is shown it (rule 3).
                if entry.event_scopes:
                    continue
            citations = []
            for document_id in entry.document_ids:
                node = await self._working_set.visible_node(
                    investigation_id, document_id, principal
                )
                if node is not None:
                    title = node.properties.get("title")
                    citations.append(
                        Citation(
                            document_id=document_id, title=title if isinstance(title, str) else None
                        )
                    )
            records: list[ExtractionCandidateRecord] = []
            for candidate_id in entry.candidate_ids:
                try:
                    records.append(await self._candidates.get_authorized(candidate_id, principal))
                except ExtractionCandidateNotFoundError:
                    continue
            out.append(
                QuestionAnswer(
                    id=entry.id,
                    author=entry.author,
                    question=entry.question,
                    answer=entry.answer,
                    citations=citations,
                    candidates=records,
                    unplaced=entry.unplaced,
                    created_at=entry.created_at,
                    graph_citations=entry.graph_citations,
                    engine=entry.engine,
                    model=entry.model,
                    read=entry.read,
                    search_citations=entry.search_citations,
                )
            )
        return out

    async def _sees_all(
        self, investigation_id: str, document_ids: list[str], principal: Principal
    ) -> bool:
        for document_id in document_ids:
            node = await self._working_set.visible_node(investigation_id, document_id, principal)
            if node is None:
                return False
        return True

    async def _proposal(
        self, investigation_id: str, candidate_id: str, principal: Principal
    ) -> ExtractionCandidateRecord:
        record = await self._candidates.get_authorized(candidate_id, principal)
        if (
            await self._working_set.visible_node(investigation_id, record.document_id, principal)
            is None
        ):
            raise DocumentNotFoundError(record.document_id)
        return record

    async def accept(
        self, investigation_id: str, candidate_id: str, principal: Principal
    ) -> QuestionAccepted:
        """A proposal accepted: an inferred node and its `MENTIONED_IN` link to its Document, onto
        the canvas. Only for a Document the analyst can see in this case."""
        record = await self._proposal(investigation_id, candidate_id, principal)
        await self._working_set.ensure_room(
            investigation_id,
            [f"accepting:{candidate_id}"],
            [f"accepting:{candidate_id}:mention"],
            principal,
        )
        # L3.2 item 3: a case not yet converted writes nothing; refused before the node.
        await refuse_writing_in_an_unconverted_case()
        node_id = await accept_candidate(self._candidates, self._graph, candidate_id, principal)
        now = datetime.now(UTC)
        mention = EdgeWrite(
            id=new_edge_id(),
            type=MENTIONED_IN,
            source=node_id,
            target=record.document_id,
            provenance=Provenance(
                state=ProvenanceState.INFERRED,
                sources=[
                    SourceRef(
                        document_id=record.document_id,
                        locator=record.locator,
                        excerpt_hash=record.excerpt_hash,
                    )
                ],
                extracted_by=f"model:{record.model}",
                extraction_confidence=record.confidence,
                first_seen=now,
            ),
            handling=record.handling,
            created_by=principal.id,
            created_at=now,
        )
        graph = self._graph
        tx = await graph.begin_transaction()
        try:
            (mention,) = as_stored([mention], await graph.upsert_edges([mention], tx))
        except Exception:
            await graph.rollback_transaction(tx)
            raise
        await graph.commit_transaction(tx)
        node = await graph.get_node(node_id, principal)
        if node is None:
            raise DocumentNotFoundError(record.document_id)
        delta = await self._working_set.add_written(
            investigation_id, [node], [_edge_from_write(mention)], principal
        )
        return QuestionAccepted(node_id=node_id, delta=delta)

    async def reject(self, investigation_id: str, candidate_id: str, principal: Principal) -> None:
        await self._proposal(investigation_id, candidate_id, principal)
        await reject_candidate(self._candidates, candidate_id, principal)


__all__: Sequence[str] = (
    "AskRequest",
    "Citation",
    "GraphCitation",
    "InMemoryQuestionStore",
    "NothingToReadError",
    "PostgresQuestionStore",
    "QuestionAccepted",
    "QuestionAnswer",
    "QuestionsLimitExceeded",
    "QuestionsService",
    "QuestionsTooLargeError",
    "QuestionTooLongToSearchError",
    "ReadFromUnavailableError",
    "ReadSummary",
    "ScopeRequest",
    "SearchCitation",
    "UnusableEngine",
    "WHOLE_CASE_LINE",
    "WHOLE_CASE_PAGE",
    "WillRead",
    "WillReadRequest",
    "CaseSearch",
)
