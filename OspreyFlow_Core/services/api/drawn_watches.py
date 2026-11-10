"""A load meeting a drawn item: the drawn watch's run (ADR-143 Amendment 2 decision 8; ADR-146
decision 4; L3.6).

Drawing an item sets a watch for it on the case's dataset (`board_store.new_watch`, L3.3). A watch
is run by every load into its dataset, whatever pipeline loads it (ADR-146 decision 4), as its
owner, resolved afresh (G16): each node the load wrote that *looks like* the drawn item, by the
board's own rule (`boards.resembles`: the same identifier, or a name alike, of the same type),
raises one `drawn_watch` alert in the watch's case, once per match per case
(`BoardItemStore.claim_match`), whose action is *Open the board*.

**Read as the owner, in the adapter** (rule 3): the drawn item is read through the owner scoped to
the case's read set, the loaded nodes through the owner scoped to the load's dataset, each filtered
by the adapter. A node the owner may not see is never read, so never matched, claimed or counted; a
drawn item they may no longer see raises nothing. A pair already decided on the board (*Same* or
*Not the same*) raises nothing either. What a reader of the queue is shown is the queue's own read
(L2.10): the alert cites the drawn item, so it is withheld whole from a reader who may not see it.

The raise itself is the one queue's (`raise_alert`), given each match: wired to L2.10's alert store
once it lands, so this module decides what matched and nothing about routing.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from schemas.boards import DrawnWatch
from schemas.domain import NOT_SAME_AS, SAME_AS, Node, Principal

from .board_store import BoardItemStore
from .boards import resembles


@dataclass(frozen=True)
class DrawnWatchMatch:
    """One match: the watch, its drawn item and the loaded node, each as the owner read them."""

    watch: DrawnWatch
    drawn: Node
    loaded: Node
    score: float
    why: str
    load_id: str | None
    matched_at: datetime


@dataclass
class DrawnWatchRun:
    items: BoardItemStore
    graph: Any
    ontology: Any
    #: The watch's owner, resolved afresh (G16); `None` for an account gone: its watches run no
    #: more.
    owner_of: Callable[[str], Awaitable[Principal | None]]
    #: A case's read set (its datasets, its layer, a merged drawing), as the app scopes its readers.
    case_datasets: Callable[[str], Awaitable[list[str]]]
    #: The one queue's raise, given each match (L2.10's alert store).
    raise_alert: Callable[[DrawnWatchMatch], Awaitable[None]]

    async def after_load(
        self, dataset_id: str, node_ids: Sequence[str], *, load_id: str | None = None
    ) -> int:
        """Every live drawn watch on `dataset_id`, run against the nodes a load wrote there. The
        number of alerts raised (for the run's report): never of what was read (rule 7)."""
        if not node_ids:
            return 0
        raised = 0
        for watch in await self.items.active_watches_on(dataset_id):
            raised += await self._run(watch, dataset_id, node_ids, load_id)
        return raised

    async def _run(
        self, watch: DrawnWatch, dataset_id: str, node_ids: Sequence[str], load_id: str | None
    ) -> int:
        owner = await self.owner_of(watch.owner)
        if owner is None:
            return 0
        read_set = await self.case_datasets(watch.case_id)
        if dataset_id not in read_set:
            return 0  # the case reads that dataset no more
        in_case = owner.model_copy(update={"datasets": read_set})
        drawn = await self.graph.get_nodes([watch.element_id], in_case)
        if not drawn:
            return 0  # withdrawn, or no longer the owner's to see
        loaded = await self.graph.get_nodes(
            sorted(set(node_ids)), owner.model_copy(update={"datasets": [dataset_id]})
        )
        found = [
            (node, alike)
            for node in loaded
            if node.id != drawn[0].id
            and node.provenance.drawn is None
            and (alike := resembles(drawn[0], node, self.ontology)) is not None
        ]
        if not found:
            return 0
        decided = {
            e.target if e.source == drawn[0].id else e.source
            for e in await self.graph.edges_among(
                [drawn[0].id, *(n.id for n, _ in found)], in_case,
                edge_types=[SAME_AS, NOT_SAME_AS],
            )
            if drawn[0].id in (e.source, e.target)
        }  # fmt: skip
        raised = 0
        for node, (score, why) in found:
            if node.id in decided:
                continue
            now = datetime.now(UTC)
            if not await self.items.claim_match(watch, node.id, now):
                continue  # one alert per match per case
            await self.raise_alert(
                DrawnWatchMatch(watch=watch, drawn=drawn[0], loaded=node, score=score, why=why,
                                load_id=load_id, matched_at=now)
            )  # fmt: skip
            raised += 1
        return raised


__all__: Sequence[str] = ("DrawnWatchMatch", "DrawnWatchRun")
