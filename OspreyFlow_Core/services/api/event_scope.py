"""Which events a read in a case may count: the case's own, and nothing else (ADR-144 Amendment 1).

Before L3.2 a case made from another also counted, on the links it held, the events of the cases it
came from (ADR-084 Amendment 2). No case is made from another now, and the upgrade turns every such
case into a view of its original (ADR-144 decision 6), so a read counts its own case's events
alone.

`EventFilter.inherited` stays a field the analytics port understands, so this module still sets
it on every read, to nothing, and whatever a caller sent in it is discarded: a request body can
never name another case's events into a read.
"""

from __future__ import annotations

from schemas.analytics import EventFilter
from schemas.domain import Principal

from .investigations import InvestigationStore

#: The case store a reader of events is given. An alias rather than a `Protocol` restating
#: `get_authorized`: a body-less `*authorized*` method in `services/api` reads, to
#: `tools/authorized_query_check.py`, as a fetch-then-check, and the gate is right to ask.
CaseRecords = InvestigationStore


def own_events_only(event_filter: EventFilter) -> EventFilter:
    """`event_filter` for its case alone: anything a caller put in `inherited` is dropped."""
    return event_filter.model_copy(update={"inherited": None})


async def link_event_filter(
    investigations: CaseRecords | None,
    event_filter: EventFilter,
    edge_id: str,
    principal: Principal,
) -> EventFilter:
    """The events behind one link the caller can see in the case: the case's own."""
    return own_events_only(event_filter)
