"""Which cases' events a read in a case may count — `06_DECISIONS.md` ADR-084 Amendment 2.

A branch is a case of its own holding copies of some of its parent's links (ADR-084); the events
behind those links were loaded under the parent and stay there. Without this, a branch's timeline
and its *Show emails* read nothing. With it, a read in a branch also counts the events of each case
it came from, up the branch family, **on the links the branch holds only**, and only from a parent
the caller may see at Viewer level: a parent the caller cannot see contributes nothing, and nothing
about it is said. The adapter applies its own access filter to every inherited event as to the
case's own (`EventFilter.inherited`, the conformance suite's `test_*inherited*` cases).

`inherited` is always set here, from the case's own record and working set, and whatever a caller
sent in it is discarded, so a request body cannot name another case's events into a read.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from schemas.analytics import EventFilter, InheritedEvents
from schemas.domain import Principal

from .investigations import (
    AccessLevel,
    InsufficientAccessError,
    Investigation,
    InvestigationNotFoundError,
)

#: A branch family deeper than this is a loop in the data, not a real lineage.
MAX_LINEAGE = 64


class CaseRecords(Protocol):
    async def get(self, investigation_id: str) -> Investigation: ...

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation: ...


async def visible_ancestors(
    investigations: CaseRecords, case: Investigation, principal: Principal
) -> list[str]:
    """The cases `case` was branched from, nearest first, that `principal` may see at Viewer."""
    found: list[str] = []
    seen = {case.id}
    parent_id = case.branched_from
    while parent_id is not None and parent_id not in seen and len(seen) <= MAX_LINEAGE:
        seen.add(parent_id)
        try:
            await investigations.get_authorized(parent_id, principal, need=AccessLevel.VIEWER)
            found.append(parent_id)
        except (InvestigationNotFoundError, InsufficientAccessError):
            pass
        try:
            parent_id = (await investigations.get(parent_id)).branched_from
        except InvestigationNotFoundError:
            break
    return found


def with_inherited(
    event_filter: EventFilter, ancestors: Sequence[str], edge_ids: Sequence[str]
) -> EventFilter:
    """`event_filter` for the case alone, widened to `ancestors`' events on `edge_ids`."""
    inherited = (
        InheritedEvents(scopes=list(ancestors), edge_ids=list(edge_ids))
        if ancestors and edge_ids
        else None
    )
    return event_filter.model_copy(update={"inherited": inherited})


async def link_event_filter(
    investigations: CaseRecords | None,
    event_filter: EventFilter,
    edge_id: str,
    principal: Principal,
) -> EventFilter:
    """The events behind one link the caller can see in the case: the case's own and, on a
    branch, its visible parents' on that link."""
    if investigations is None:
        return with_inherited(event_filter, [], [])
    try:
        case = await investigations.get(event_filter.investigation_scope)
    except InvestigationNotFoundError:
        return with_inherited(event_filter, [], [])
    ancestors = await visible_ancestors(investigations, case, principal)
    return with_inherited(event_filter, ancestors, [edge_id])
