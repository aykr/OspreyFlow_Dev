"""What a saved view reports of its deletions (SE9; ADR-144 Amendment 7; rules 3, 4, 7, 12).

`CaseViewOpened.missing` is how many of a view's chosen nodes have been **deleted since** (a load
reverted, a refresh's withdrawal, a removed case's layer) **and would pass this reader's own access
step if they were live**. The count is made in the graph port, `GraphPort.count_deleted_visible`,
with the reader's access step in the store's query. This module never reads a deletion's record, a
stored count of the view's ids or an existence lookup, and never sees what is hidden: the port
answers a number, and the number leaves out everything the reader could not see (a node above their
clearance, in a dataset the case does not read, under a handling code they may not receive; an id
nobody holds). A missing id and a hidden deleted one therefore answer alike.

A deletion's time and person (`reverted_at`, `reverted_by`) are for the audit and are read by
nothing here, so a deletion made before the store kept them counts as any other does.

Kept out of `app.py` and of `case_views.py`'s stores on purpose (the file is a collision point):
`case_views.missing_for` is the one hook, and it calls `deleted_and_visible`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from schemas.domain import NodeId, Principal


class _DeletionCounts(Protocol):
    async def count_deleted_visible(
        self, node_ids: Sequence[NodeId], principal: Principal
    ) -> int: ...


async def deleted_and_visible(
    graph: _DeletionCounts, chosen: Sequence[NodeId] | None, principal: Principal
) -> int:
    """How many of `chosen` are deleted and would pass `principal`'s access step if live, counted
    by the port for `principal` alone (a shared view counts each reader's own visibility). `chosen`
    is the creator's choice, never the stored selection a merged drawing added to; `None` is a
    filtered view, which has no chosen nodes and asks the store nothing."""
    if not chosen:
        return 0
    return await graph.count_deleted_visible(list(chosen), principal)
