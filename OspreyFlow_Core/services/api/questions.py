"""Questions to the model about a case's documents (`06_DECISIONS.md` ADR-098 decision 4).

An analyst branches the Documents they chose into a case of their own and asks the model about
them there. The model reads every Document in the case's view that the analyst can see, whole, and
answers from them only, saying which it draws on; anything it proposes (an entity, with the words
that name it) is a pending finding in the same review queue as an extraction's, inferred until a
person accepts it (rule 5), and placed in the Document where its words are, or left out and
counted when they are not there. The conversation is kept with the case.

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
from collections.abc import Sequence
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
    Edge,
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

from .datasets import DatasetStore
from .document_reader import DocumentReaderService
from .email_extraction import _edge_from_write
from .event_scope import CaseRecords, visible_ancestors, with_inherited
from .evidence_brief import (
    EvidenceBrief,
    cited_numbers,
    scope_of,
    strip_unheld,
    write_brief,
)
from .investigations import InvestigationNotFoundError
from .link_ids import as_stored
from .review import (
    DocumentNotFoundError,
    ExtractionCandidateNotFoundError,
    ExtractionCandidateRecord,
    ExtractionCandidateStore,
    accept_candidate,
    reject_candidate,
)
from .working_set.models import BranchFilter, DeltaAdd
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
    #: Every node and link the evidence brief was drawn from, held like `read_ids`: a reader who
    #: may not see one of them is not shown the entry (rule 3).
    graph_node_ids: list[str] = Field(default_factory=list)
    graph_link_ids: list[str] = Field(default_factory=list)
    graph_citations: list[GraphCitation] = Field(default_factory=list)


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


class QuestionAccepted(BaseModel):
    node_id: str
    delta: DeltaAdd


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    #: What the analyst has selected on the canvas: the evidence brief is these and one link around
    #: them. Nothing selected is the whole view. An id the analyst may not see selects nothing, as
    #: one that does not exist does.
    selected_node_ids: list[str] = Field(default_factory=list, max_length=MAX_SELECTION)
    selected_link_ids: list[str] = Field(default_factory=list, max_length=MAX_SELECTION)
    #: The timeline window, when one is set: only links whose interval overlaps it, and only events
    #: inside it, are in the brief ("narrow the timeline window" is one of the limit's options).
    window: Interval | None = None

    @model_validator(mode="after")
    def _window_runs_forward(self) -> AskRequest:
        if (
            self.window is not None
            and self.window.valid_to is not None
            and self.window.valid_from > self.window.valid_to
        ):
            raise ValueError("the window ends before it starts")
        return self


def shared_handling(handlings: Sequence[Handling]) -> Handling | None:
    """The handling a question about several Documents is sent under (ADR-114 Amendment 6): theirs
    when every one carries the same handling code, otherwise none — and material whose handling is
    not given is never sent to a client's provider (`model_routing.py`)."""
    codes = {h.handling_code for h in handlings}
    return handlings[0] if len(codes) == 1 else None


class NoDocumentsError(Exception):
    """The case holds no Document the analyst can see, so there is nothing to ask about."""


QuestionsOption = Literal["narrow_selection", "narrow_timeline_window", "branch"]
_QUESTIONS_OPTIONS: tuple[QuestionsOption, ...] = (
    "narrow_selection",
    "narrow_timeline_window",
    "branch",
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
    async def list_for_case(self, investigation_id: str) -> list[QuestionEntry]: ...


class InMemoryQuestionStore:
    """The store for tests and a process with no Postgres: the same two calls."""

    def __init__(self) -> None:
        self.entries: list[QuestionEntry] = []

    async def add(self, entry: QuestionEntry) -> None:
        self.entries.append(entry)

    async def list_for_case(self, investigation_id: str) -> list[QuestionEntry]:
        return sorted(
            (e for e in self.entries if e.investigation_id == investigation_id),
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
"""


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
                "graph_node_ids, graph_link_ids, graph_citations) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)",
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
            )

    async def list_for_case(self, investigation_id: str) -> list[QuestionEntry]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM case_questions WHERE investigation_id = $1 ORDER BY created_at",
                investigation_id,
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
    ) -> None:
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
    ) -> list[tuple[str, str | None, str, Handling]]:
        """`(id, title, text, handling)` of every Document among `nodes`, the case's view as the
        analyst may see it."""
        found: list[tuple[str, str | None, str, Handling]] = []
        for node in sorted(
            (n for n in nodes if n.type == DOCUMENT_TYPE),
            key=lambda n: str(n.properties.get("title", n.id)),
        ):
            view = await self._reader.read(investigation_id, node.id, principal)
            if view.text.strip():
                found.append((node.id, view.title, view.text, node.handling))
        return found

    async def _events_per_month(
        self,
        investigation_id: str,
        principal: Principal,
        link_ids: Sequence[str],
        window: Interval | None,
    ) -> tuple[list[tuple[str, int]], list[Handling]]:
        """The events on the links in scope, counted per month as the analyst: an event they may
        not see moves no figure (the store applies the access filter in its own query). Asked only
        by link, never by node: an event on a link the analyst may not see is not theirs to count,
        and an empty list of links would not restrict the store at all, so no link, no question."""
        if not link_ids:
            return [], []
        base = EventFilter(
            investigation_scope=investigation_id, edge_ids=list(link_ids), window=window
        )
        ancestors: list[str] = []
        branch_window: Interval | None = None
        if self._investigations is not None:
            try:
                case = await self._investigations.get(investigation_id)
            except InvestigationNotFoundError:
                case = None
            if case is not None:
                ancestors = await visible_ancestors(self._investigations, case, principal)
                branch_window = case.branch_window
        trend = await self._analytics.trend(
            TrendRequest(
                filter=with_inherited(base, ancestors, link_ids, window=branch_window),
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
        return months, handlings

    async def _evidence_brief(
        self,
        investigation_id: str,
        principal: Principal,
        nodes: Sequence[Node],
        edges: Sequence[Edge],
        selected_node_ids: Sequence[str],
        selected_link_ids: Sequence[str],
        window: Interval | None,
        documents_chars: int,
    ) -> EvidenceBrief:
        """The brief for what `principal` selected, from their own view, refused whole when it and
        the documents do not fit together (rule 2). The cap is checked before the events are read,
        so the links the events are asked over are only ever as many as the budget allows."""
        scope = scope_of(
            nodes,
            edges,
            selected_node_ids=selected_node_ids,
            selected_link_ids=selected_link_ids,
            window=(
                BranchFilter(valid_from=window.valid_from, valid_to=window.valid_to)
                if window is not None
                else None
            ),
        )
        labels = {d.id: d.name for d in await self._datasets.of_case(investigation_id)}
        brief = write_brief(scope, labels)
        _fits(documents_chars, len(brief.text))
        months, event_handlings = await self._events_per_month(
            investigation_id, principal, brief.link_ids, window
        )
        if months:
            brief = write_brief(scope, labels, months, event_handlings)
            _fits(documents_chars, len(brief.text))
        return brief

    async def ask(
        self,
        investigation_id: str,
        question: str,
        principal: Principal,
        *,
        selected_node_ids: Sequence[str] = (),
        selected_link_ids: Sequence[str] = (),
        window: Interval | None = None,
    ) -> QuestionAnswer:
        nodes, edges = await self._working_set.visible_membership(investigation_id, principal)
        documents = await self._documents(investigation_id, principal, nodes)
        if not documents:
            raise NoDocumentsError(investigation_id)
        documents_chars = sum(len(text) for _, _, text, _ in documents)
        brief = await self._evidence_brief(
            investigation_id,
            principal,
            nodes,
            edges,
            selected_node_ids,
            selected_link_ids,
            window,
            documents_chars,
        )
        numbered = "\n\n".join(
            f"Document {i}: {title or '(no title)'}\n{text}"
            for i, (_, title, text, _) in enumerate(documents, start=1)
        )
        graph_section = f"{_GRAPH_INSTRUCTIONS}\n\n{brief.text}\n\n" if brief.text else ""
        result = await self._model.extract(
            ExtractionRequest(
                document_id=f"questions:{investigation_id}",
                text=f"{_INSTRUCTIONS}\n\n{numbered}\n\n{graph_section}Question: {question}",
                json_schema=_schema(),
                model=self._default_model,
                handling=shared_handling([h for _, _, _, h in documents] + list(brief.handlings)),
            )
        )
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

        proposals: list[ExtractionCandidate] = []
        unplaced = len(asked_for) - len(graph_citations)
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
        records = await self._candidates.store(proposals, principal) if proposals else []
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
            created_at=datetime.now(UTC),
            graph_node_ids=list(brief.node_ids),
            graph_link_ids=list(brief.link_ids),
            graph_citations=graph_citations,
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
        )

    async def _handling_of(
        self, investigation_id: str, document_id: str, principal: Principal
    ) -> Handling:
        node = await self._working_set.visible_node(investigation_id, document_id, principal)
        if node is None:
            raise DocumentNotFoundError(document_id)
        return node.handling

    async def history(self, investigation_id: str, principal: Principal) -> list[QuestionAnswer]:
        """The case's conversation for `principal`: the answers asked over Documents they can all
        see, with the proposals their unit owns, each in its present state. An answer read from a
        Document above them is left out, without a word to say so (rule 3)."""
        out: list[QuestionAnswer] = []
        entries = await self._store.list_for_case(investigation_id)
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
            if not (
                seen_nodes.issuperset(entry.graph_node_ids)
                and seen_links.issuperset(entry.graph_link_ids)
            ):
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
    "NoDocumentsError",
    "PostgresQuestionStore",
    "QuestionAccepted",
    "QuestionAnswer",
    "QuestionsLimitExceeded",
    "QuestionsService",
    "QuestionsTooLargeError",
)
