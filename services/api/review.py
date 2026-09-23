"""The review queue — `docs/09_INGEST_STUDIO.md` §7: "Extraction produces candidates, not graph.
The review queue is where a human turns one into the other." `extraction_candidates` is a
Postgres-backed registry, the same instance and bootstrap-on-connect pattern
`services/api/studio_recipes.py`'s `studio_recipes` table already establishes — a candidate spans
sessions and people exactly the way a recipe draft does, so it is a row from the moment extraction
runs, not Glass-side state.

**Run extraction, then persist candidates — never write to `GraphPort` here.** `run_extraction`
calls `ModelPort.extract()`, `services/extract/candidates.extract_candidates` turns the result into
`ExtractionCandidate`s, and this module stores them `pending`. Nothing in this path touches the
graph; `accept_candidate` is the one function here that does, via `services/extract/writer.
write_candidate`.

**Accept, reject and confirm/retract are four different actions, not two.** `accept`/`reject`
operate on a *candidate row* that has never touched the graph (`reject` simply marks the row and
is retained — `09_INGEST_STUDIO.md` §7 — never deleted); `confirm`/`retract`
(`services/extract/writer.py`) operate on a *graph node* `accept` already created, promoting it
from `inferred` to `asserted` or reversing that. Conflating "accept" with "confirm" would make
every accepted candidate silently asserted the moment a human first saw it, which is exactly the
automatic promotion `CLAUDE.md` rule 5 forbids.

**No bulk accept, by construction, not by a checked rule.** `09_INGEST_STUDIO.md` §7: "No bulk
accept above a confidence threshold. Not as a default, not as a setting." `accept_candidate`/
`reject_candidate` both take exactly one `candidate_id` — there is no code path here that accepts
a list of ids, a filter, or a threshold, so this is structurally true rather than a rule a caller
could accidentally satisfy by passing a filter that happens to match one row.

**A document's own raw text, since Phase 6a Stage 4.** `run_extraction`'s `text` argument used to
be discarded once candidates were built — nothing anywhere served a document's text back by id.
`document_texts` (a sibling table to `extraction_candidates`, same pool, same `owning_unit`-scoped
shape) exists for exactly one consumer: `services/api/dossier.py`'s own assembly of "message
content renders with the entity spans... highlighted in place" (`08_ACCEPTANCE_SCENARIOS.md` B6).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast

import asyncpg
from pydantic import BaseModel, Field
from services.extract.candidates import ExtractionCandidate, extract_candidates
from services.extract.profile import DEFAULT_CONFIDENCE_FLOOR, ExtractionProfile, build_schema
from services.extract.writer import write_candidate

from ports.graph import GraphPort
from ports.model import ModelPort
from schemas.domain import Handling, NodeId, OntologySchema, Principal
from schemas.model import ExtractionRequest

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS extraction_candidates (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    properties TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    model TEXT NOT NULL,
    locator TEXT NOT NULL,
    excerpt_hash TEXT NOT NULL,
    handling TEXT NOT NULL,
    status TEXT NOT NULL,
    owning_unit TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    node_id TEXT
);
"""

# Phase 6a Stage 4 (B6, the Dossier): `run_extraction`'s own `text` argument was discarded once
# candidates were built, and nothing anywhere served a document's raw text back by id — the
# Dossier's own "message content renders... in place" (`08_ACCEPTANCE_SCENARIOS.md` B6) needs
# exactly that. A sibling table, not a new store/dependency: same pool, same
# `owning_unit`-scoped shape `extraction_candidates` already establishes.
_DOCUMENT_TEXT_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS document_texts (
    document_id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    owning_unit TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
"""


class CandidateStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ExtractionCandidateNotFoundError(Exception):
    """Also raised — deliberately, not a 403 — when the candidate exists but
    `principal.org_unit` does not match `owning_unit`: the same existence-leak discipline
    `StudioRecipeNotFoundError`/`SiteNotFoundError` already apply."""


class CandidateNotPendingError(Exception):
    """Raised by `accept_candidate`/`reject_candidate` against a candidate whose `status` has
    already moved past `pending` — a candidate is reviewed exactly once."""


class DocumentNotFoundError(Exception):
    """Also raised — deliberately, not a 403 — when the document's text exists but
    `principal.org_unit` does not match its own `owning_unit`: the same existence-leak discipline
    `ExtractionCandidateNotFoundError` already applies."""


class ExtractionProfileInput(BaseModel):
    """The wire shape of `services/extract/profile.ExtractionProfile` — a `BaseModel` so FastAPI
    can validate a request body with it; `ExtractionProfile` itself stays a plain class since
    nothing about it needs (de)serialisation outside this one request boundary."""

    entity_types: list[str]
    default_confidence_floor: float = Field(default=DEFAULT_CONFIDENCE_FLOOR, ge=0.0, le=1.0)
    confidence_floors: dict[str, float] = Field(default_factory=dict)
    adapters: dict[str, dict[str, str]] = Field(default_factory=dict)

    def to_profile(self) -> ExtractionProfile:
        return ExtractionProfile(
            self.entity_types,
            default_confidence_floor=self.default_confidence_floor,
            confidence_floors=self.confidence_floors,
            adapters=self.adapters,
        )


class RunExtractionRequest(BaseModel):
    """`model` is required, not defaulted to any particular pin — `ADR-005`: extraction model
    choice is always the caller's, never this module's own opinion (`packages/schemas/model.py`'s
    own docstring makes the same point about `ExtractionRequest.model`)."""

    document_id: str
    text: str
    profile: ExtractionProfileInput
    handling: Handling
    model: str


class AcceptCandidateRequest(BaseModel):
    properties_override: dict[str, Any] | None = None


class NodeIdResponse(BaseModel):
    node_id: NodeId


class RejectedResponse(BaseModel):
    status: str = "rejected"


class ExtractionCandidateRecord(ExtractionCandidate):
    """`ExtractionCandidate` (`services/extract/candidates.py`) plus the review-queue's own
    lifecycle fields — a candidate before it has been accepted or rejected is still just an
    `ExtractionCandidate` with `status=pending`, so this extends rather than wraps it."""

    status: CandidateStatus
    owning_unit: str
    created_by: str
    created_at: datetime
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    node_id: NodeId | None = None


def _row_to_record(row: asyncpg.Record) -> ExtractionCandidateRecord:
    data = dict(row)
    return ExtractionCandidateRecord(
        id=data["id"],
        document_id=data["document_id"],
        entity_type=data["entity_type"],
        properties=json.loads(data["properties"]),
        confidence=data["confidence"],
        model=data["model"],
        locator=data["locator"],
        excerpt_hash=data["excerpt_hash"],
        handling=Handling.model_validate(json.loads(data["handling"])),
        status=CandidateStatus(data["status"]),
        owning_unit=data["owning_unit"],
        created_by=data["created_by"],
        created_at=data["created_at"],
        reviewed_by=data["reviewed_by"],
        reviewed_at=data["reviewed_at"],
        node_id=data["node_id"],
    )


class ExtractionCandidateStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> ExtractionCandidateStore:
        # `min_size`/`max_size` — `hotlists.py::HotlistStore.connect`'s own comment has the full
        # Stage 6c connection-ceiling reasoning.
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
            await conn.execute(_DOCUMENT_TEXT_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def store(
        self, candidates: list[ExtractionCandidate], principal: Principal
    ) -> list[ExtractionCandidateRecord]:
        now = datetime.now(UTC)
        records = [
            ExtractionCandidateRecord(
                **candidate.model_dump(),
                status=CandidateStatus.PENDING,
                owning_unit=principal.org_unit,
                created_by=principal.id,
                created_at=now,
            )
            for candidate in candidates
        ]
        if not records:
            return records
        async with self._pool.acquire() as conn:
            await conn.executemany(
                "INSERT INTO extraction_candidates (id, document_id, entity_type, properties, "
                "confidence, model, locator, excerpt_hash, handling, status, owning_unit, "
                "created_by, created_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, "
                "$12, $13)",
                [
                    (
                        r.id,
                        r.document_id,
                        r.entity_type,
                        json.dumps(r.properties),
                        r.confidence,
                        r.model,
                        r.locator,
                        r.excerpt_hash,
                        r.handling.model_dump_json(),
                        r.status.value,
                        r.owning_unit,
                        r.created_by,
                        r.created_at,
                    )
                    for r in records
                ],
            )
        return records

    async def list_for_document(
        self, document_id: str, principal: Principal
    ) -> list[ExtractionCandidateRecord]:
        """Scoped to `principal.org_unit` — a candidate row is Postgres state with no `Handling`
        of its own to filter by (it has never touched `GraphPort`), so `owning_unit` is this
        store's own access boundary, the same as `StudioRecipeStore.list_drafts`."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM extraction_candidates WHERE document_id = $1 AND owning_unit = $2 "
                "ORDER BY created_at",
                document_id,
                principal.org_unit,
            )
        return [_row_to_record(row) for row in rows]

    async def get_authorized(
        self, candidate_id: str, principal: Principal
    ) -> ExtractionCandidateRecord:
        """`owning_unit` is filtered in the query itself, not after fetch — the same
        `list_for_document`'s own shape, and `CLAUDE.md` rule 3's reasoning even though this store
        is Conduit-internal Postgres, not one of the four ports: a bare `SELECT *` pulls every
        column of a candidate derived from an intelligence document into process memory for a
        principal who is not cleared for it, before anything checks, from where it can reach a log
        line, an exception trace or a debugger. `WHERE owning_unit = $2` means that row is never
        fetched at all for a principal outside it — existence and content are refused by the same
        query, not a query followed by a Python-side check that already holds what it's about to
        reject."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM extraction_candidates WHERE id = $1 AND owning_unit = $2",
                candidate_id,
                principal.org_unit,
            )
        if row is None:
            raise ExtractionCandidateNotFoundError(candidate_id)
        return _row_to_record(row)

    async def mark_reviewed(
        self,
        candidate_id: str,
        principal: Principal,
        *,
        status: CandidateStatus,
        node_id: NodeId | None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE extraction_candidates SET status = $1, reviewed_by = $2, "
                "reviewed_at = $3, node_id = $4 WHERE id = $5",
                status.value,
                principal.id,
                datetime.now(UTC),
                node_id,
                candidate_id,
            )

    async def store_document_text(
        self, document_id: str, text: str, principal: Principal
    ) -> None:
        """Upsert, not insert-only — `run_extraction` re-run against the same `document_id` (a
        different profile, a second model) re-stores the same text rather than failing on a
        primary-key conflict a caller has no reason to expect from an idempotent-looking action."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO document_texts (document_id, text, owning_unit, created_at) "
                "VALUES ($1, $2, $3, $4) ON CONFLICT (document_id) DO UPDATE SET "
                "text = EXCLUDED.text, owning_unit = EXCLUDED.owning_unit, "
                "created_at = EXCLUDED.created_at",
                document_id,
                text,
                principal.org_unit,
                datetime.now(UTC),
            )

    async def get_document_text(self, document_id: str, principal: Principal) -> str:
        """`WHERE owning_unit = $2` in the query itself, the same `get_authorized` shape —
        existence and content refused by the same query, not a fetch followed by a check."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT text FROM document_texts WHERE document_id = $1 AND owning_unit = $2",
                document_id,
                principal.org_unit,
            )
        if row is None:
            raise DocumentNotFoundError(document_id)
        return cast(str, row["text"])


async def run_extraction(
    model: ModelPort,
    ontology: OntologySchema,
    store: ExtractionCandidateStore,
    *,
    document_id: str,
    text: str,
    profile: ExtractionProfile,
    handling: Handling,
    principal: Principal,
    extraction_model: str,
) -> list[ExtractionCandidateRecord]:
    """`09_INGEST_STUDIO.md` §4 end to end: builds the schema from the profile, calls
    `ModelPort.extract()`, turns the result into candidates, and persists them `pending` — no
    graph write anywhere in this function (`module docstring`).

    Also persists `text` itself (`store_document_text`, Phase 6a Stage 4) — previously discarded
    the moment candidates were built, leaving nothing for the Dossier's own "message content
    renders... in place" to render against."""
    schema = build_schema(profile, ontology)
    result = await model.extract(
        ExtractionRequest(
            document_id=document_id, text=text, json_schema=schema, model=extraction_model
        )
    )
    candidates = extract_candidates(result, profile, ontology, text, handling)
    await store.store_document_text(document_id, text, principal)
    return await store.store(candidates, principal)


async def accept_candidate(
    store: ExtractionCandidateStore,
    graph: GraphPort,
    candidate_id: str,
    principal: Principal,
    *,
    properties_override: dict[str, Any] | None = None,
) -> NodeId:
    """`09_INGEST_STUDIO.md` §7's "Edit" is folded into "Accept" here, as an optional property
    override applied on top of the candidate's own extracted+adapter-normalised properties — a
    deliberately minimal shape rather than a second, stateful draft-edit round trip (a
    disclosed gap). Writes through a fresh transaction, following the
    same begin/commit-or-rollback shape `services/api/working_set/service.py`'s manual
    link/split already established."""
    record = await store.get_authorized(candidate_id, principal)
    if record.status is not CandidateStatus.PENDING:
        raise CandidateNotPendingError(candidate_id)

    candidate = ExtractionCandidate(
        id=record.id,
        document_id=record.document_id,
        entity_type=record.entity_type,
        properties={**record.properties, **(properties_override or {})},
        confidence=record.confidence,
        model=record.model,
        locator=record.locator,
        excerpt_hash=record.excerpt_hash,
        handling=record.handling,
    )

    tx = await graph.begin_transaction()
    try:
        node_id = await write_candidate(graph, candidate, created_by=principal.id, tx=tx)
    except Exception:
        await graph.rollback_transaction(tx)
        raise
    await graph.commit_transaction(tx)

    await store.mark_reviewed(
        candidate_id, principal, status=CandidateStatus.ACCEPTED, node_id=node_id
    )
    return node_id


async def reject_candidate(
    store: ExtractionCandidateStore, candidate_id: str, principal: Principal
) -> None:
    record = await store.get_authorized(candidate_id, principal)
    if record.status is not CandidateStatus.PENDING:
        raise CandidateNotPendingError(candidate_id)
    await store.mark_reviewed(
        candidate_id, principal, status=CandidateStatus.REJECTED, node_id=None
    )


__all__ = [
    "AcceptCandidateRequest",
    "CandidateNotPendingError",
    "CandidateStatus",
    "DocumentNotFoundError",
    "ExtractionCandidateNotFoundError",
    "ExtractionCandidateRecord",
    "ExtractionCandidateStore",
    "ExtractionProfileInput",
    "NodeIdResponse",
    "RejectedResponse",
    "RunExtractionRequest",
    "accept_candidate",
    "reject_candidate",
    "run_extraction",
]
