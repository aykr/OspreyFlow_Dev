"""The events behind one link — `06_DECISIONS.md` ADR-089, `02_GLASS_FRONTEND.md` §3.1f.

A summarised link (an Enron `COMMUNICATED_WITH` between two addresses, ADR-053) stands for many
events, each one email. This reads them back a page at a time, newest first, with the total said,
so the Glass can show "Show emails (n)" and page through them; each event carries its subject and
excerpt in its properties, so no second read is needed to open one.

**Who may read them: whoever can see the link** — the same `WorkingSetService.visible_edge`
question link notes and link changes ask, with one refusal for "not there" and "not yours to see"
(`LinkNotFoundError`), so a hidden link cannot be told from a missing one (rules 3 and 4). The
events themselves are then read through `AnalyticsPort.list_events`, whose access control is in
the adapter's own query: an event the principal may not see is neither listed nor counted. The
case-level Viewer level is checked by the route before this runs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ports.analytics import AnalyticsPort
from schemas.analytics import EventFilter, EventListRequest, EventRecord
from schemas.domain import Principal

from .link_notes import LinkNotFoundError
from .working_set.service import WorkingSetService

PAGE_SIZE = 50


class LinkEventListResponse(BaseModel):
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    events: list[EventRecord] = Field(default_factory=list)


class LinkEventsService:
    def __init__(self, working_set: WorkingSetService, analytics: AnalyticsPort) -> None:
        self._working_set = working_set
        self._analytics = analytics

    async def list(
        self,
        investigation_id: str,
        edge_id: str,
        principal: Principal,
        *,
        offset: int = 0,
        limit: int = PAGE_SIZE,
    ) -> LinkEventListResponse:
        edge = await self._working_set.visible_edge(investigation_id, edge_id, principal)
        if edge is None:
            raise LinkNotFoundError(edge_id)
        result = await self._analytics.list_events(
            EventListRequest(
                filter=EventFilter(investigation_scope=investigation_id, edge_ids=[edge.id]),
                offset=offset,
                limit=limit,
            ),
            principal,
        )
        return LinkEventListResponse(
            total=result.total, offset=offset, limit=limit, events=result.events
        )
