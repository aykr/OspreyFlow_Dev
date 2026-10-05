"""The full-screen reader's text — `06_DECISIONS.md` ADR-092 decision 5.

A Document opens to read with its title, its full text and the entities already accepted from it
marked in place. The text is the document's stored extraction text where there is one (the
Dossier's source, `dossier.get_document_view`, which also gives the marked spans); otherwise, for
an email, the event it was made from, read through the analytics port under the case's scope rules
(on a branch, the visible parents' events too, ADR-084 Amendment 2) and its handling filter.

**Who may read it: whoever can see the Document in the case.** A Document above the caller, one not
in the case, and a node that is not a Document all answer `DocumentNotFoundError`, one refusal for
all three (rules 3 and 4).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from schemas.analytics import EventFilter, EventListRequest, EventRecord
from schemas.domain import Principal

from .dossier import MessageSpan, get_document_view
from .event_scope import CaseRecords, visible_ancestors, with_inherited
from .review import DocumentNotFoundError, ExtractionCandidateStore
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


class DocumentReaderService:
    def __init__(
        self,
        working_set: WorkingSetService,
        analytics: AnalyticsPort,
        graph: GraphPort,
        candidates: ExtractionCandidateStore,
        investigations: CaseRecords | None = None,
    ) -> None:
        self._working_set = working_set
        self._analytics = analytics
        self._graph = graph
        self._candidates = candidates
        self._investigations = investigations

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
