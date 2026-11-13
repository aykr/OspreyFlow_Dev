"""The nodes the index may hold at older facts (ADR-150 decision 2; the orchestrator's ruling of 13
November for ADR-149's query side): every node in the graph's outbox, and every Document whose
text is in the text outbox. The query side excludes them in its own filter (`must_not` on
`node_id`) and says its counts are not exact while any are pending, so a node reverted, withdrawn,
superseded or re-marked to a tighter marking is never counted or grouped at its older marking
while the indexer lags.

Ids alone, read with no principal: they are only ever excluded, never shown. When either outbox
holds more rows than `limit`, the set is not known to be whole (`complete` false) and the caller
must not rely on it (it falls back to the graph); a node may appear in an outbox more than once,
so `limit` bounds the rows read, not the ids returned.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ports.index_feed import IndexFeedSource


class _TextOutbox(Protocol):
    async def pending_text_index(self, limit: int) -> list[tuple[int, str]]: ...


@dataclass(frozen=True)
class PendingIds:
    ids: frozenset[str]
    #: Both outboxes read whole. False: more rows than `limit` in one of them, so some pending
    #: node may be missing from `ids`.
    complete: bool


async def pending_node_ids(
    source: IndexFeedSource, texts: _TextOutbox, *, limit: int
) -> PendingIds:
    rows = await source.pending_index(limit + 1)
    text_rows = await texts.pending_text_index(limit + 1)
    complete = len(rows) <= limit and len(text_rows) <= limit
    ids = {str(r.node_id) for r in rows[:limit]} | {d for _, d in text_rows[:limit]}
    return PendingIds(ids=frozenset(ids), complete=complete)
