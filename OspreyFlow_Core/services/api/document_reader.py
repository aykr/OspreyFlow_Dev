"""The full-screen reader's text — `06_DECISIONS.md` ADR-092 decision 5.

A Document opens to read with its title, its full text and the entities already accepted from it
marked in place. The text is the document's stored extraction text where there is one (the
Dossier's source, `dossier.get_document_view`, which also gives the marked spans); otherwise, for
an email, the event it was made from, read through the analytics port under the case's scope rules
(on a branch, the visible parents' events too, ADR-084 Amendment 2) and its handling filter.

**Who may read it: whoever can see the Document in the case.** A Document above the caller, one not
in the case, and a node that is not a Document all answer `DocumentNotFoundError`, one refusal for
all three (rules 3 and 4).

**Marking an entity by hand (ADR-098 decision 5).** Words selected in the text the reader shows can
be marked as a Person, an Organisation, a Location or an Endpoint: written as a node of that type,
asserted (a person made it) and attributed to them, its source the Document with the selection's
character locator and the words' hash, and linked to the Document by `MENTIONED_IN`. The words are
checked against the text at that place, so a locator never points at something else.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from conduit_common.identity import new_id, new_node_id
from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from ports.media import MediaNotFoundError, MediaStore
from schemas.analytics import EventFilter, EventListRequest, EventRecord
from schemas.domain import (
    EdgeWrite,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

from .dossier import MessageSpan, get_document_view
from .email_extraction import _edge_from_write, _node_from_write
from .event_scope import CaseRecords, visible_ancestors, with_inherited
from services.extract.candidates import ExtractionCandidate

from .review import CandidateStatus, DocumentNotFoundError, ExtractionCandidateStore
from .working_set.models import DeltaAdd
from .working_set.service import WorkingSetService

DOCUMENT_TYPE = "Document"


class DocumentReaderView(BaseModel):
    document_id: str
    title: str | None = None
    text: str
    #: The email's excerpt was cut at the loader's limit (ADR-089 decision 1).
    truncated: bool = False
    spans: list[MessageSpan] = Field(default_factory=list)
    sent_at: datetime | None = None
    sender_id: str | None = None
    recipient_id: str | None = None
    #: For an email: what *Extract entities* names (`POST .../links/{edge}/events/{event}/extract`).
    edge_id: str | None = None
    event_id: str | None = None
    #: ADR-094: `text`, `image` or `video` for a Document written from held content; the reader
    #: shows an image or a video from `GET .../documents/{id}/file` when `has_file`.
    media_kind: str | None = None
    has_file: bool = False


MENTIONED_IN = "MENTIONED_IN"

#: The types an analyst can mark words as, and which property the words become (ADR-098).
DESIGNATABLE_TYPES = ("Person", "Organisation", "Location", "Endpoint")


class Designation(BaseModel):
    """Words selected in a Document's text and the type they are marked as."""

    entity_type: str
    text: str = Field(min_length=1, max_length=500)
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class DesignationResult(BaseModel):
    node_id: str
    delta: DeltaAdd


class DesignationRefusedError(Exception):
    """The words are not at that place in the text, or the type cannot be marked by hand."""


def designation_properties(entity_type: str, words: str) -> dict[str, str]:
    """The node's properties from the marked words: a person's last word is the family name and the
    rest the given names; anything else is named by the words, an endpoint by its value."""
    words = " ".join(words.split())
    if entity_type == "Person":
        *given, family = words.split(" ")
        return {"family_name": family, **({"given_names": " ".join(given)} if given else {})}
    if entity_type == "Endpoint":
        return {"value_raw": words, "value_normalised": words.lower()}
    return {"name": words}


class DocumentReaderService:
    def __init__(
        self,
        working_set: WorkingSetService,
        analytics: AnalyticsPort,
        graph: GraphPort,
        candidates: ExtractionCandidateStore,
        investigations: CaseRecords | None = None,
        media: MediaStore | None = None,
    ) -> None:
        self._working_set = working_set
        self._analytics = analytics
        self._graph = graph
        self._candidates = candidates
        self._investigations = investigations
        self._media = media

    async def read(
        self, investigation_id: str, document_id: str, principal: Principal
    ) -> DocumentReaderView:
        node = await self._working_set.visible_node(investigation_id, document_id, principal)
        if node is None or node.type != DOCUMENT_TYPE:
            raise DocumentNotFoundError(document_id)
        title = node.properties.get("title")
        view = DocumentReaderView(
            document_id=node.id, title=title if isinstance(title, str) else None, text=""
        )

        kind = node.properties.get("media_kind")
        ref = node.properties.get("object_ref")
        view.media_kind = kind if isinstance(kind, str) else None
        view.has_file = isinstance(ref, str)
        if view.has_file and kind == "text" and self._media is not None:
            # A held text Document keeps its text in the media store (ADR-094).
            try:
                view.text = (await self._media.get(str(ref))).decode("utf-8", errors="replace")
            except MediaNotFoundError:
                view.text = ""

        event_id = node.properties.get("event_id")
        if isinstance(event_id, str):
            event = await self._event(investigation_id, event_id, principal)
            if event is not None:
                excerpt = event.properties.get("excerpt")
                view.text = excerpt if isinstance(excerpt, str) else ""
                view.truncated = event.properties.get("truncated") is True
                view.sent_at = event.occurred_at
                # By the email's direction, as the Inspector's From and To read it: an inbound
                # email on an a→b link was sent by b.
                ends = (event.source_id, event.target_id)
                view.sender_id, view.recipient_id = (
                    ends[::-1] if event.direction == "inbound" else ends
                )
                view.edge_id, view.event_id = event.edge_id, event.event_id

        try:
            stored = await get_document_view(self._candidates, self._graph, node.id, principal)
        except DocumentNotFoundError:
            return view
        view.text, view.spans = stored.text, stored.spans
        return view

    async def designate(
        self,
        investigation_id: str,
        document_id: str,
        designation: Designation,
        principal: Principal,
    ) -> DesignationResult:
        """Writes the marked words as an asserted node linked to the Document (ADR-098 decision 5).
        Only on a Document the analyst can read here (rule 4: one they cannot see refuses as one
        that does not exist), and only for words that are at that place in the text it shows."""
        if designation.entity_type not in DESIGNATABLE_TYPES:
            raise DesignationRefusedError(f"{designation.entity_type} cannot be marked by hand")
        view = await self.read(investigation_id, document_id, principal)
        if view.text[designation.start : designation.end] != designation.text:
            raise DesignationRefusedError("the words are not at that place in the text")
        document = await self._working_set.visible_node(investigation_id, document_id, principal)
        if document is None:
            raise DocumentNotFoundError(document_id)
        now = datetime.now(UTC)
        source = SourceRef(
            document_id=document_id,
            # The Dossier's locator form (`dossier._CHAR_SPAN`), so the reader marks the words.
            locator=f"char span {designation.start}-{designation.end}",
            excerpt_hash=hashlib.sha256(designation.text.encode("utf-8")).hexdigest(),
        )
        provenance = Provenance(state=ProvenanceState.ASSERTED, sources=[source], first_seen=now)
        node = NodeWrite(
            id=new_node_id(),
            type=designation.entity_type,
            properties=designation_properties(designation.entity_type, designation.text),
            provenance=provenance,
            handling=document.handling,
            created_by=principal.id,
            created_at=now,
        )
        mention = EdgeWrite(
            id=f"{node.id}:mentioned-in:{document_id}",
            type=MENTIONED_IN,
            source=node.id,
            target=document_id,
            provenance=provenance,
            handling=document.handling,
            created_by=principal.id,
            created_at=now,
        )
        # Asked before the graph is written, so a full working set leaves nothing behind (rule 2).
        await self._working_set.ensure_room(investigation_id, [node.id], [mention.id])
        tx = await self._graph.begin_transaction()
        try:
            await self._graph.upsert_nodes([node], tx)
            await self._graph.upsert_edges([mention], tx)
        except Exception:
            await self._graph.rollback_transaction(tx)
            raise
        await self._graph.commit_transaction(tx)
        # The reader's marks come from accepted findings, so the marking is kept as one, the
        # analyst's, with the text it points into (an email never extracted has none stored yet).
        try:
            await self._candidates.get_document_text(document_id, principal)
        except DocumentNotFoundError:
            await self._candidates.store_document_text(document_id, view.text, principal)
        (record,) = await self._candidates.store(
            [
                ExtractionCandidate(
                    id=new_id(),
                    document_id=document_id,
                    entity_type=designation.entity_type,
                    properties=node.properties,
                    confidence=1.0,
                    model=f"analyst:{principal.id}",
                    locator=source.locator,
                    excerpt_hash=source.excerpt_hash,
                    handling=document.handling,
                )
            ],
            principal,
        )
        await self._candidates.mark_reviewed(
            record.id, principal, status=CandidateStatus.ACCEPTED, node_id=node.id
        )
        delta = await self._working_set.add_written(
            investigation_id, [_node_from_write(node)], [_edge_from_write(mention)]
        )
        return DesignationResult(node_id=node.id, delta=delta)

    async def _event(
        self, investigation_id: str, event_id: str, principal: Principal
    ) -> EventRecord | None:
        own = EventFilter(investigation_scope=investigation_id, event_ids=[event_id])
        event_filter = own
        if self._investigations is not None:
            case = await self._investigations.get(investigation_id)
            ancestors = await visible_ancestors(self._investigations, case, principal)
            if ancestors:
                _, edges = await self._working_set.current_membership(investigation_id)
                event_filter = with_inherited(own, ancestors, [e.id for e in edges])
        page = await self._analytics.list_events(
            EventListRequest(filter=event_filter, offset=0, limit=1), principal
        )
        return page.events[0] if page.events else None
