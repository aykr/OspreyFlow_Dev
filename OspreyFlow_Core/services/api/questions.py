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
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

import asyncpg
from pydantic import BaseModel, Field
from services.extract.candidates import ExtractionCandidate
from services.extract.recognised import properties_for

from conduit_common.identity import new_edge_id, new_id
from ports.graph import GraphPort
from ports.model import ModelPort
from schemas.domain import (
    EdgeWrite,
    Handling,
    OntologySchema,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from schemas.model import ExtractionRequest

from .document_reader import DocumentReaderService
from .email_extraction import _edge_from_write
from .review import (
    DocumentNotFoundError,
    ExtractionCandidateNotFoundError,
    ExtractionCandidateRecord,
    ExtractionCandidateStore,
    accept_candidate,
    reject_candidate,
)
from .working_set.models import DeltaAdd
from .working_set.service import WorkingSetService

#: How much document text one question may send the model: the extraction model is served with a
#: 32,768-token context (ADR-095), which also holds the instructions, the question and the answer.
QUESTIONS_MAX_CHARS = 80_000
MAX_QUESTION_CHARS = 2_000
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


def _schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "cited": {"type": "array", "items": {"type": "integer"}},
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


class QuestionAnswer(BaseModel):
    """A question as the Glass shows it: the answer, what it cites (those the reader may see) and
    its proposals with their present state (those of the reader's unit)."""

    id: str
    author: str
    question: str
    answer: str
    citations: list[Citation]
    candidates: list[ExtractionCandidateRecord]
    unplaced: int
    created_at: datetime


class QuestionAccepted(BaseModel):
    node_id: str
    delta: DeltaAdd


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


class NoDocumentsError(Exception):
    """The case holds no Document the analyst can see, so there is nothing to ask about."""


class QuestionsTooLargeError(Exception):
    """The documents together are longer than the model can read at once (rule 2: never cut)."""

    def __init__(self, would_be: int, limit: int) -> None:
        super().__init__(f"{would_be} characters against a limit of {limit}")
        self.would_be = would_be
        self.limit = limit


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
"""


class PostgresQuestionStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PostgresQuestionStore:
        pool = await asyncpg.create_pool(dsn)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def add(self, entry: QuestionEntry) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO case_questions (id, investigation_id, author, question, answer, "
                "document_ids, read_ids, candidate_ids, unplaced, model, created_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)",
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
    ) -> None:
        self._working_set = working_set
        self._reader = reader
        self._graph = graph
        self._model = model
        self._ontology = ontology
        self._candidates = candidates
        self._store = store
        self._default_model = default_model

    async def _documents(
        self, investigation_id: str, principal: Principal
    ) -> list[tuple[str, str | None, str]]:
        """`(id, title, text)` of every Document in the case's view the analyst can see."""
        nodes, _ = await self._working_set.visible_membership(investigation_id, principal)
        found: list[tuple[str, str | None, str]] = []
        for node in sorted(
            (n for n in nodes if n.type == DOCUMENT_TYPE),
            key=lambda n: str(n.properties.get("title", n.id)),
        ):
            view = await self._reader.read(investigation_id, node.id, principal)
            if view.text.strip():
                found.append((node.id, view.title, view.text))
        return found

    async def ask(
        self, investigation_id: str, question: str, principal: Principal
    ) -> QuestionAnswer:
        documents = await self._documents(investigation_id, principal)
        if not documents:
            raise NoDocumentsError(investigation_id)
        total = sum(len(text) for _, _, text in documents)
        if total > QUESTIONS_MAX_CHARS:
            raise QuestionsTooLargeError(total, QUESTIONS_MAX_CHARS)
        numbered = "\n\n".join(
            f"Document {i}: {title or '(no title)'}\n{text}"
            for i, (_, title, text) in enumerate(documents, start=1)
        )
        result = await self._model.extract(
            ExtractionRequest(
                document_id=f"questions:{investigation_id}",
                text=f"{_INSTRUCTIONS}\n\n{numbered}\n\nQuestion: {question}",
                json_schema=_schema(),
                model=self._default_model,
            )
        )
        data = result.data
        answer = str(data.get("answer") or "").strip()
        cited_numbers = [n for n in data.get("cited") or [] if isinstance(n, int)]
        cited = [documents[n - 1][0] for n in cited_numbers if 1 <= n <= len(documents)]

        proposals: list[ExtractionCandidate] = []
        unplaced = 0
        for item in data.get("entities") or []:
            if not isinstance(item, dict) or item.get("type") not in PROPOSABLE_TYPES:
                unplaced += 1
                continue
            number = item.get("document")
            if not isinstance(number, int) or not 1 <= number <= len(documents):
                unplaced += 1
                continue
            document_id, _, text = documents[number - 1]
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
        for document_id, _, text in documents:
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
            read_ids=[d for d, _, _ in documents],
            candidate_ids=[r.id for r in records],
            unplaced=unplaced,
            model=result.model,
            created_at=datetime.now(UTC),
        )
        await self._store.add(entry)
        titles = {d: t for d, t, _ in documents}
        return QuestionAnswer(
            id=entry.id,
            author=entry.author,
            question=question,
            answer=answer,
            citations=[Citation(document_id=d, title=titles.get(d)) for d in entry.document_ids],
            candidates=records,
            unplaced=unplaced,
            created_at=entry.created_at,
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
        for entry in await self._store.list_for_case(investigation_id):
            if not await self._sees_all(investigation_id, entry.read_ids, principal):
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
            investigation_id, [f"accepting:{candidate_id}"], [f"accepting:{candidate_id}:mention"]
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
            await graph.upsert_edges([mention], tx)
        except Exception:
            await graph.rollback_transaction(tx)
            raise
        await graph.commit_transaction(tx)
        node = await graph.get_node(node_id, principal)
        if node is None:
            raise DocumentNotFoundError(record.document_id)
        delta = await self._working_set.add_written(
            investigation_id, [node], [_edge_from_write(mention)]
        )
        return QuestionAccepted(node_id=node_id, delta=delta)

    async def reject(self, investigation_id: str, candidate_id: str, principal: Principal) -> None:
        await self._proposal(investigation_id, candidate_id, principal)
        await reject_candidate(self._candidates, candidate_id, principal)


__all__: Sequence[str] = (
    "AskRequest",
    "Citation",
    "InMemoryQuestionStore",
    "NoDocumentsError",
    "PostgresQuestionStore",
    "QuestionAccepted",
    "QuestionAnswer",
    "QuestionsService",
    "QuestionsTooLargeError",
)
