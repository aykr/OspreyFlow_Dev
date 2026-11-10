"""A load meeting a drawn item: the drawn watch's run (ADR-143 Amendment 2 decision 8; ADR-146
decision 4; L3.6).

Drawing an item sets a watch for it on the case's dataset (`board_store.new_watch`, L3.3). A watch
is run by every load into its dataset, whatever pipeline loads it (ADR-146 decision 4), as its
owner, resolved afresh (G16): each node the load wrote that *looks like* the drawn item, by the
board's own rule (`boards.resembles`: the same identifier, or a name alike, of the same type),
raises one `drawn_watch` alert in the watch's case, once per match per case
(`BoardItemStore.claim_match`), whose action is *Open the board*.

**Only while the owner may still open the case** (rule 3): each watch is run only for an owner
who holds a level on its case now (the case's own Viewer check, `holds_a_level`; none to ask, none
run), and reads only what that case reads, as a request under it would (`case_read_set`: a borrowed
read-only layer only for one holding a level on its own case, as `scope_to_case`). A watch on a
composite is run by a load into any of its members.

**Read as the owner, in the adapter**: the drawn item is read through the owner scoped to the
case's read set, the loaded nodes through the owner scoped to the load's dataset, each filtered by
the adapter. A node the owner may not see is never read, so never matched, claimed or counted; a
drawn item they may no longer see raises nothing. A pair already decided on the board (*Same* or
*Not the same*) raises nothing either. What a reader of the queue is shown is the queue's own read
(L2.10): the alert cites the drawn item, so it is withheld whole from a reader who may not see it.

A drawn link's watch never matches: only nodes are loaded as matches. The run is inside the
load's request, as the hotlists' and monitors' are, so its time grows with the live watches on the
dataset (one owner resolution each), whatever they match.

**The alert** (`drawn_watch_alert`): an ordinary watch alert, `rule_id` `drawn_watch:<watch id>`,
the watch owner's, in the watch's case, on the watched dataset (ADR-146 decision 1; the queue's
`queue_scope` reads it to its owner in that case alone). It cites the drawn item and the loaded
node, so the queue, reading both as each reader through the adapter, withholds it whole from one
who may not see either (rule 3, `test_drawn_watch_queue.py`). Its words name the two by id alone,
each named at every read as the reader reads it. *Open the board* opens the board the drawn item's
own provenance names, read as the reader with the rest of the evidence.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from conduit_common.identity import new_id
from schemas.boards import DrawnWatch
from schemas.domain import NOT_SAME_AS, SAME_AS, Alert, AlertMode, Handling, Node, Principal

from .alerts import AlertStore
from .board_store import BoardItemStore
from .boards import resembles
from .dataset_scope import readable_of_case
from .investigations import AccessLevel, InsufficientAccessError, InvestigationNotFoundError


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


_log = logging.getLogger(__name__)

#: ADR-146 decision 1: a watch set by drawing, told apart by its rule's prefix
#: (`alerts._KIND_SQL`).
DRAWN_WATCH_PREFIX = "drawn_watch:"


def drawn_watch_rule(watch_id: str) -> str:
    return f"{DRAWN_WATCH_PREFIX}{watch_id}"


def drawn_watch_alert(match: DrawnWatchMatch) -> tuple[Alert, list[Handling]]:
    """The alert one match raises, and the markings of what it cites (kept with it, as every
    alert's, for `alerts.raiser_read_admits`)."""
    drawn, loaded = match.drawn, match.loaded
    alert = Alert(
        id=new_id(),
        rule_id=drawn_watch_rule(match.watch.id),
        owner_id=match.watch.owner,
        mode=AlertMode.FULL,
        referent_node_ids=[drawn.id, loaded.id],
        investigation_id=match.watch.case_id,
        dataset_id=match.watch.dataset_id,
        created_at=match.matched_at,
        words=f"A load met a drawn item: {loaded.id} looks like {drawn.id} ({match.why}).",
    )
    return alert, [drawn.handling, loaded.handling]


def raise_into(store: AlertStore) -> Callable[[DrawnWatchMatch], Awaitable[None]]:
    """The one queue's raise for a drawn watch: the alert saved in the alert store."""

    async def raise_alert(match: DrawnWatchMatch) -> None:
        alert, handlings = drawn_watch_alert(match)
        await store.save(alert, handlings=handlings)

    return raise_alert


#: Whether a principal holds any level on a case now (its Viewer check), as `app.holds_a_level_in`.
HoldsALevel = Callable[[Principal, str], Awaitable[bool]]


def holds_a_level_in(investigations: Any) -> HoldsALevel:
    async def holds(principal: Principal, case_id: str) -> bool:
        try:
            await investigations.get_authorized(case_id, principal, need=AccessLevel.VIEWER)
        except (InvestigationNotFoundError, InsufficientAccessError):
            return False
        return True

    return holds


async def case_read_set(
    datasets: Any, case_id: str, owner: Principal, holds_a_level: HoldsALevel
) -> list[str]:
    """What a request under `case_id` reads for `owner`, as `dataset_scope.scope_to_case` decides
    it, without setting the request's scope (this runs inside the loader's request): a case's
    borrowed read-only layer only for one holding a level on its own case."""
    read = await datasets.ids_of_case(case_id)
    if read and not await datasets.layer_of_case(case_id):
        borrowed = await datasets.read_only_layer_of(case_id)
        if borrowed is not None and borrowed in read:
            original = await datasets.case_of_layer(borrowed)
            holds = original is not None and await holds_a_level(owner, original)
            return readable_of_case(read, borrowed, holds_the_original=holds)
    return list(read)


@dataclass
class DrawnWatchRun:
    items: BoardItemStore
    graph: Any
    ontology: Any
    #: The watch's owner, resolved afresh (G16); `None` for an account gone: its watches run no
    #: more.
    owner_of: Callable[[str], Awaitable[Principal | None]]
    #: The dataset store: each case's read set (`case_read_set`) and the composites of a dataset.
    datasets: Any
    #: Whether the owner holds a level on the watch's case now (`holds_a_level_in`).
    holds_a_level: HoldsALevel
    #: The one queue's raise, given each match (`raise_into`, the alert store's).
    raise_alert: Callable[[DrawnWatchMatch], Awaitable[None]]

    async def after_load(
        self,
        dataset_id: str,
        node_ids: Sequence[str],
        *,
        load_id: str | None = None,
        counted_for: str | None = None,
    ) -> int:
        """Every live drawn watch on `dataset_id`, run against the nodes a load wrote there. The
        number of alerts raised, never of what was read (rule 7); with `counted_for`, only those
        raised for that account (the run's report: a drawn watch's alert is its owner's alone, so
        another owner's is neither counted nor said to the loader)."""
        if not node_ids:
            return 0
        raised = 0
        failed: Exception | None = None
        # A watch on a composite is on each of its members (the case reads them all).
        watched = [dataset_id, *(c.id for c in await self.datasets.composites_of(dataset_id))]
        for on in watched:
            for watch in await self.items.active_watches_on(on):
                # One watch's failure (its owner's resolution, its save) never skips the rest; the
                # first is raised once every watch has run, for the caller to audit.
                try:
                    made = await self._run(watch, dataset_id, node_ids, load_id)
                    if counted_for is None or watch.owner == counted_for:
                        raised += made
                except Exception as error:  # noqa: BLE001 - raised again below
                    failed = failed or error
        if failed is not None:
            raise failed
        return raised

    async def _run(
        self, watch: DrawnWatch, dataset_id: str, node_ids: Sequence[str], load_id: str | None
    ) -> int:
        owner = await self.owner_of(watch.owner)
        if owner is None or not await self.holds_a_level(owner, watch.case_id):
            return 0  # an account gone, or one who may no longer open the case
        read_set = await case_read_set(self.datasets, watch.case_id, owner, self.holds_a_level)
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
            try:
                await self.raise_alert(
                    DrawnWatchMatch(watch=watch, drawn=drawn[0], loaded=node, score=score,
                                    why=why, load_id=load_id, matched_at=now)
                )  # fmt: skip
            except BaseException:
                # Not raised, so not claimed: the next load meeting it raises it. A failure to give
                # the claim back is logged, never put in place of the save's own failure.
                try:
                    await self.items.release_match(watch, node.id)
                except Exception:  # noqa: BLE001
                    _log.warning("a drawn watch's claim was not given back", exc_info=True)
                raise
            raised += 1
        return raised


__all__: Sequence[str] = (
    "DRAWN_WATCH_PREFIX",
    "DrawnWatchMatch",
    "DrawnWatchRun",
    "drawn_watch_alert",
    "case_read_set",
    "drawn_watch_rule",
    "holds_a_level_in",
    "raise_into",
)
