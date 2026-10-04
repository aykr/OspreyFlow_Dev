"""Entities from an email behind a link — `06_DECISIONS.md` ADR-089 step 3, `02_GLASS_FRONTEND.md`
§3.1f.

An Enron email is an analytics event on a summarised link, with up to 4,000 characters of its body
as `excerpt`. An analyst who has opened one may ask for the entities in it. That is the existing
extraction (`review.run_extraction`: the model, a profile, candidates stored `pending`), applied to
the email's text under a document id derived from the event, so the Dossier's document view can
mark what was found in place. Nothing a model finds reaches the graph until a person accepts it
(`CLAUDE.md` rule 5): accepting a candidate writes it as an `inferred` node, exactly as the review
queue does, and here also links it to the email.

**The email becomes a `Document` node at the first extraction** (the owner's choice), linked to its
sender and recipient by `MENTIONED_IN` (both addresses appear in the message), and each accepted
entity gets a `MENTIONED_IN` link to that Document, the shape the ontology already has, so the
evidence trail from entity to email to addresses is on the canvas. Both are put into the case's
working set at once, so the canvas shows them without a reload.

**Who may: whoever can see the link** (`WorkingSetService.visible_edge`, the same gate as the
events listing, one refusal for hidden and missing alike), and the route needs Editor since it
writes. An event that is not on that link, or a candidate that is not from that email, is refused
as not found. The model is the caller's choice (ADR-005); left out, the deployment's local model.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from services.extract.profile import ExtractionProfile

from conduit_common.identity import new_edge_id
from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from ports.model import ModelPort
from schemas.analytics import EventFilter, EventListRequest, EventRecord
from schemas.domain import (
    AuditStub,
    Edge,
    EdgeWrite,
    Node,
    NodeWrite,
    OntologySchema,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

from .link_notes import LinkNotFoundError
from .review import (
    ExtractionCandidateRecord,
    ExtractionCandidateStore,
    accept_candidate,
    run_extraction,
)
from .working_set.models import DeltaAdd
from .working_set.service import WorkingSetService

MENTIONED_IN = "MENTIONED_IN"
DOCUMENT_TYPE = "Document"


class EmailNotFoundError(Exception):
    """The event is not on this link, or the candidate is not from this email."""

    def __init__(self, what: str) -> None:
        super().__init__(f"{what} not found")
        self.what = what


def email_document_id(event_id: str) -> str:
    """The document id an email's text and candidates are kept under."""
    return f"email:{event_id}"


class ExtractEmailRequest(BaseModel):
    """`model` is the caller's choice (ADR-005); left out, the deployment's local model is used."""

    model: str | None = None


class EmailExtractionResult(BaseModel):
    document_id: str
    candidates: list[ExtractionCandidateRecord]
    delta: DeltaAdd


class EmailAcceptResult(BaseModel):
    node_id: str
    delta: DeltaAdd


def _node_from_write(write: NodeWrite) -> Node:
    return Node(
        id=write.id,
        type=write.type,
        properties=write.properties,
        provenance=write.provenance,
        handling=write.handling,
        audit=AuditStub(created_at=write.created_at, created_by=write.created_by),
    )


def _edge_from_write(write: EdgeWrite) -> Edge:
    return Edge(
        id=write.id,
        type=write.type,
        source=write.source,
        target=write.target,
        properties=write.properties,
        occurrences=write.occurrences,
        provenance=write.provenance,
        handling=write.handling,
        audit=AuditStub(created_at=write.created_at, created_by=write.created_by),
    )


class EmailExtractionService:
    def __init__(
        self,
        working_set: WorkingSetService,
        analytics: AnalyticsPort,
        graph: GraphPort,
        ontology: OntologySchema,
        candidates: ExtractionCandidateStore,
        model: ModelPort,
        default_model: str,
    ) -> None:
        self._working_set = working_set
        self._analytics = analytics
        self._graph = graph
        self._ontology = ontology
        self._candidates = candidates
        self._model = model
        self._default_model = default_model

    async def _event_on_link(
        self, investigation_id: str, edge_id: str, event_id: str, principal: Principal
    ) -> EventRecord:
        edge = await self._working_set.visible_edge(investigation_id, edge_id, principal)
        if edge is None:
            raise LinkNotFoundError(edge_id)
        page = await self._analytics.list_events(
            EventListRequest(
                filter=EventFilter(
                    investigation_scope=investigation_id,
                    edge_ids=[edge.id],
                    value_filters={"event_id": [event_id]},
                ),
                offset=0,
                limit=1,
            ),
            principal,
        )
        for event in page.events:
            if event.event_id == event_id:
                return event
        raise EmailNotFoundError("email")

    def _document_writes(
        self, event: EventRecord, principal: Principal, now: datetime
    ) -> tuple[NodeWrite, list[EdgeWrite]]:
        document_id = email_document_id(event.event_id)
        props: dict[str, Any] = dict(event.properties)
        title = props.get("subject")
        provenance = Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[
                SourceRef(
                    document_id=str(props.get("message_id") or event.event_id),
                    locator=f"event:{event.event_id}",
                    excerpt_hash="",
                )
            ],
            first_seen=event.occurred_at,
        )
        node = NodeWrite(
            id=document_id,
            type=DOCUMENT_TYPE,
            properties={
                "title": title if isinstance(title, str) and title else "(no subject)",
                "sent_at": event.occurred_at.isoformat(),
                "message_id": props.get("message_id"),
                "event_id": event.event_id,
            },
            provenance=provenance,
            handling=event.handling,
            created_by=principal.id,
            created_at=now,
        )
        # Ids are derived, so a second extraction of the same email writes the same links again
        # rather than a second pair; `upsert_edges` merges a same-pair write in any case.
        edges = [
            EdgeWrite(
                id=f"{document_id}:mentions:{end}",
                type=MENTIONED_IN,
                source=end,
                target=document_id,
                provenance=provenance,
                handling=event.handling,
                created_by=principal.id,
                created_at=now,
            )
            for end in (event.source_id, event.target_id)
        ]
        return node, edges

    async def extract(
        self,
        investigation_id: str,
        edge_id: str,
        event_id: str,
        principal: Principal,
        *,
        model: str | None = None,
    ) -> EmailExtractionResult:
        event = await self._event_on_link(investigation_id, edge_id, event_id, principal)
        now = datetime.now(UTC)
        node, edges = self._document_writes(event, principal, now)

        tx = await self._graph.begin_transaction()
        try:
            await self._graph.upsert_nodes([node], tx)
            await self._graph.upsert_edges(edges, tx)
        except Exception:
            await self._graph.rollback_transaction(tx)
            raise
        await self._graph.commit_transaction(tx)
        delta = await self._working_set.add_written(
            investigation_id, [_node_from_write(node)], [_edge_from_write(e) for e in edges]
        )

        text = event.properties.get("excerpt")
        profile = ExtractionProfile(
            [t.name for t in self._ontology.entity_types if t.name != DOCUMENT_TYPE]
        )
        candidates = await run_extraction(
            self._model,
            self._ontology,
            self._candidates,
            document_id=node.id,
            text=text if isinstance(text, str) else "",
            profile=profile,
            handling=event.handling,
            principal=principal,
            extraction_model=model or self._default_model,
        )
        return EmailExtractionResult(document_id=node.id, candidates=candidates, delta=delta)

    async def accept(
        self,
        investigation_id: str,
        edge_id: str,
        event_id: str,
        candidate_id: str,
        principal: Principal,
    ) -> EmailAcceptResult:
        await self._event_on_link(investigation_id, edge_id, event_id, principal)
        document_id = email_document_id(event_id)
        record = await self._candidates.get_authorized(candidate_id, principal)
        if record.document_id != document_id:
            raise EmailNotFoundError("candidate")

        node_id = await accept_candidate(self._candidates, self._graph, candidate_id, principal)
        now = datetime.now(UTC)
        mention = EdgeWrite(
            id=new_edge_id(),
            type=MENTIONED_IN,
            source=node_id,
            target=document_id,
            provenance=Provenance(
                state=ProvenanceState.INFERRED,
                sources=[
                    SourceRef(
                        document_id=document_id,
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
        tx = await self._graph.begin_transaction()
        try:
            await self._graph.upsert_edges([mention], tx)
        except Exception:
            await self._graph.rollback_transaction(tx)
            raise
        await self._graph.commit_transaction(tx)

        node = await self._graph.get_node(node_id, principal)
        if node is None:
            raise EmailNotFoundError("candidate")
        delta = await self._working_set.add_written(
            investigation_id, [node], [_edge_from_write(mention)]
        )
        return EmailAcceptResult(node_id=node_id, delta=delta)
