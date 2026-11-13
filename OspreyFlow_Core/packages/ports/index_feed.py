"""The search index feed's source (`spec/06_DECISIONS.md` ADR-150 decisions 1 and 2).

Every write of the graph adapter records the ids of the nodes it touched in an outbox, in the
same transaction as the write. The indexer drains that outbox through this port and nothing else:
it reads each node as stored, **unfiltered by design**, to build the node's one search document
with the node's own access fields (the query side enforces access, ADR-149). A separate `Protocol`
from `GraphPort`, so that no route, which is given a `GraphPort`, can reach the unfiltered read
(rule 4: `tests/services/search_index/test_index_feed_reach.py` holds that no route module names
it).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from schemas.domain import Node, NodeId


@dataclass(frozen=True)
class PendingIndex:
    """One outbox row: the store's own reference to it (to remove it once indexed) and the node."""

    ref: str
    node_id: NodeId


@runtime_checkable
class IndexFeedSource(Protocol):
    async def pending_index(self, limit: int) -> list[PendingIndex]:
        """The oldest outbox rows, at most `limit`. A node may appear more than once."""
        ...

    async def clear_pending_index(self, refs: Sequence[str]) -> None:
        """Removes these outbox rows, once their nodes are indexed (at least once delivery)."""
        ...

    async def nodes_for_index(self, node_ids: Sequence[NodeId]) -> dict[NodeId, Node | None]:
        """Each id's node as stored, unfiltered, with its sources whole; None for a node that is
        not live (absent, reverted, superseded or withdrawn), which the indexer deletes."""
        ...

    async def live_node_ids(self, *, after: NodeId | None, limit: int) -> list[NodeId]:
        """Every live node's id, in id order after `after`, for the rebuild and the drift check."""
        ...
