"""Promotion into a dataset, and a removed case's layer merged or deleted (ADR-143 decisions 8 and
10; Amendment 2 decision 1; ADR-145 decision 8 and Amendment 4 decisions 3 and 11; spec 03 §3.1d;
L3.4).

**Promotion is a load** (decision 8). The board's drawn items the analyst ticks gain the case's
source dataset, as the same elements (`GraphPort.promote_elements`, ADR-099 decision 2's union;
rule 6: never a copy, never a merge), in one graph transaction under one `load_id` (trigger
`analyst_promotion`), all or nothing. A drawn link goes only when both its ends will be in the
dataset (loaded already, going now, or promoted before); a picture and a match decision follow
their drawn node. Everything that does not go is listed with its reason (rule 2).

**The checks** run on the sheet and again at the route, so a sheet bypassed refuses the same
(rule 15): each marking within the dataset's highest allowed marking (ADR-145 decision 8); each type
in the dataset's model (C14; a link of an analyst-defined type through case-b's
`promotion_refusals`, ADR-143 Amendment 4 decision 3); each item graded with a source (decision 4);
no link without both ends.

**The policy** (ADR-145 decision 8): under *Author promotes* the promotion is committed at once;
under *Second person reviews* it waits, and nothing of it is readable outside its case until a
second person approves it (the graph is not written before). The approvers are the dataset's
Authors (its home case's, ADR-145 Amendment 4 decision 3) holding `review_promotions` (the route's
right), never the proposer (ADR-133 Amendment 8). A reviewer reads exactly the promotion's own
elements, from the case's layer, through their own clearance in the adapter; one who may not see
every item may not approve (rule 3: approving would commit what they have not read).

**A removed case's layer** (Amendment 2 decision 1): merged by one of the dataset's Authors as a
promotion (trigger `layer_merge`), under the dataset's policy, through a read grant for that one
layer opened by the merge sheet and closed with the merge; never a composite case's layer (the
orchestrator's settlement of admin's Q5), which is only deleted. Deleting withdraws every element
wholly the layer's (`withdraw_layer`); promoted items are never touched.

**Revert.** A promotion is reverted like any load: with the Conduit stopped, by the operator command
`python -m scripts.revert_promotion` (ADR-127 Amendment 9), whose core is `revert`. There is no
online revert: the owner settled ADR-143 open question 2 as (a), the operator command alone
(Amendment 5 decision 8).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from conduit_common.identity import new_id
from ports.graph import NotPromotable
from schemas.domain import NOT_SAME_AS, SAME_AS, Edge, Node, Principal
from schemas.mapconfig import GAZETTEER_DATASET_PREFIX
from schemas.promotions import (
    DetailItem,
    LayerDeleted,
    LayerMergeSheet,
    LeftOut,
    Promotion,
    PromotionCheck,
    PromotionDetails,
    PromotionSheet,
    SheetItem,
)

from .board_store import BoardItem
from .boards import Boards, ItemNotFound
from .case_views import StoredCaseView
from .datasets import COMPOSITE, DRAWN, Dataset
from .document_content import DOCUMENT_TYPE
from .evidence_brief import display_name
from .promotion_store import LayerGrant, PromotionRecord, PromotionStore

#: The revert command shown to a reader holding `revert_loads` (ADR-127 Amendment 9).
REVERT_COMMAND = "python -m scripts.revert_promotion {load_id} --reverted-by <your username>"
LAYER_DELETE_PREFIX = "layer-delete:"
#: Who the registry says withdrew a deleted layer's items.
LAYER_DELETER = "layer-delete"
#: A merge's read grant lasts a working day at most (Amendment 5 decision 7, as reviewed): an
#: Author who walks away from the sheet does not keep the layer open.
GRANT_HOURS = 8
#: Each check's code, in the order the sheet shows them.
CHECKS = ("marking", "types", "graded", "ends")


class PromotionRefused(Exception):
    """A promotion, a review or a layer action refused in words, before anything is written."""

    def __init__(self, code: str, message: str, *, status: int = 409) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class PromotionNotFound(Exception):
    """No promotion by that id for this reader: another dataset's, or none, alike (rule 3)."""


class _LinkTypes(Protocol):
    async def promotion_refusals(
        self, investigation_id: str, principal: Principal, names: Sequence[str]
    ) -> dict[str, str | None]: ...


class _Investigations(Protocol):
    async def get_authorized(self, case_id: str, principal: Principal, *, need: Any) -> Any: ...
    async def admin_states(
        self, investigation_ids: Sequence[str]
    ) -> dict[str, tuple[str, bool]]: ...


@dataclass(frozen=True)
class _Read:
    """A board item as the sheet reads it: its registry row and its element (`None` when the
    reader may not see it now)."""

    item: BoardItem
    element: Node | Edge | None


GAZETTEER_TAKES_NOTHING_DRAWN = (
    "A gazetteer dataset holds only the places its build loads: nothing drawn in a case is "
    "promoted or merged into it."
)


def is_gazetteer(dataset: Dataset) -> bool:
    """A `gazetteer-*` dataset (ADR-147 Amendment 1 decision 2): the build's places alone."""
    return dataset.id.startswith(GAZETTEER_DATASET_PREFIX)


@dataclass
class Promotions:
    boards: Boards
    store: PromotionStore
    investigations: _Investigations
    author_level: Any
    link_types: _LinkTypes | None = None
    #: Names for display, by account id (the people directory); ids where absent.
    names: Callable[[Sequence[str]], Awaitable[dict[str, str]]] | None = None
    case_names: Callable[[str], Awaitable[str | None]] | None = None
    #: The audit entry for a promotion ended rejected by anything but a reviewer's own *Reject*
    #: (the approval's re-check, a refused or failed load, a restored case, a deleted layer),
    #: which the route audits itself: no state change without its entry.
    on_rejected: Callable[[PromotionRecord, str], Awaitable[None]] | None = None
    #: A picture's Document as the last `_read` found it.
    _docs: dict[str, Node] = field(default_factory=dict)

    # --- where a case's promotion goes ------------------------------------------------------

    def _top(self) -> str:
        return self.boards.scheme.classification[-1]

    def highest(self, dataset: Dataset) -> str:
        return dataset.highest_marking or self._top()

    async def _target(self, case_id: str) -> tuple[Dataset | None, str | None]:
        """The dataset a case promotes into, or why it promotes into none."""
        chosen = await self.boards.datasets.chosen_of_case(case_id)
        if not chosen:
            return None, "This case reads no dataset, so there is nothing to promote into."
        if chosen[0].kind == DRAWN:
            return None, (
                "This drawing is its own dataset: what is drawn here is already its data. Merge "
                "the drawing into another dataset from the Ingest Studio instead."
            )
        if chosen[0].kind == COMPOSITE:
            return None, (
                "A case reading a composite promotes nothing: a composite holds none of its "
                "members' data. Promote from a case reading the member dataset."
            )
        if is_gazetteer(chosen[0]):
            return None, GAZETTEER_TAKES_NOTHING_DRAWN
        return chosen[0], None

    # --- reading the items ----------------------------------------------------------------

    async def _read(self, items: Sequence[BoardItem], reader: Principal) -> list[_Read]:
        node_ids = [i.element_id for i in items if i.kind == "node"]
        edge_ids = [i.element_id for i in items if i.kind != "node"]
        nodes = {n.id: n for n in await self.boards.graph.get_nodes(node_ids, reader)}
        edges = {e.id: e for e in await self.boards.graph.get_edges(edge_ids, reader)}
        # A picture's Document is a node of the layer, read with its link.
        docs = [i.source for i in items if i.kind == "picture" and i.source]
        nodes |= {n.id: n for n in await self.boards.graph.get_nodes(docs, reader)} if docs else {}
        self._docs = nodes
        return [_Read(i, nodes.get(i.element_id) or edges.get(i.element_id)) for i in items]

    def _label(self, read: _Read) -> str:
        element = read.element
        if element is None:
            return "An item"
        drawn = element.provenance.drawn
        if drawn is not None:
            return drawn.label
        if read.item.kind == "picture":
            return "A picture"
        if read.item.kind == "match":
            return "Same" if element.type == SAME_AS else "Not the same"
        return display_name(element) if isinstance(element, Node) else element.type

    async def _problems(
        self, reads: Sequence[_Read], dataset: Dataset, case_id: str, reader: Principal
    ) -> dict[str, list[tuple[str, str]]]:
        """Every check each item fails, as (check, words) (decision 8's checks; `CHECKS`)."""
        highest = self.highest(dataset)
        node_types = set(await self.boards.node_types(case_id))
        link_names = sorted(
            {r.element.type for r in reads if r.item.kind == "link" and r.element is not None}
        )
        refusals: dict[str, str | None] = {}
        if link_names and self.link_types is not None:
            refusals = await self.link_types.promotion_refusals(case_id, reader, link_names)
        # C14 for links as for nodes: the dataset's model, its live packs (not the deployment's).
        model_links = set(await self.boards.model_link_types(case_id))
        out: dict[str, list[tuple[str, str]]] = {}
        for read in reads:
            problems: list[tuple[str, str]] = []
            element = read.element
            if element is None:
                out[read.item.item_id] = [("unseen", "You may not see this item now.")]
                continue
            marking = element.handling.classification
            if not self.boards.scheme.clears(highest, marking):
                problems.append((
                    "marking",
                    f"Marked {marking}, above {dataset.name}'s highest allowed marking, {highest}.",
                ))  # fmt: skip
            if read.item.kind == "picture" and read.item.source in self._docs:
                doc_marking = self._docs[read.item.source].handling.classification
                if not self.boards.scheme.clears(highest, doc_marking):
                    problems.append((
                        "marking",
                        f"The picture is marked {doc_marking}, above {dataset.name}'s highest "
                        f"allowed marking, {highest}.",
                    ))  # fmt: skip
            if read.item.kind == "node" and element.type not in node_types:
                problems.append(
                    ("types", f"{element.type} is not a type of {dataset.name}'s model.")
                )
            if read.item.kind == "link":
                why = refusals.get(element.type)
                if why is not None:
                    problems.append(("types", why))
                elif element.type not in model_links and element.type not in refusals:
                    problems.append(
                        ("types", f"{element.type} is not a link type of {dataset.name}'s model.")
                    )
            drawn = element.provenance.drawn
            if read.item.kind in ("node", "link"):
                if drawn is None or drawn.grading is None:
                    problems.append(("graded", "It has no grading."))
                elif not ((drawn.source_note or "").strip() or drawn.source_document):
                    problems.append(("graded", "It has no source note or source document."))
            out[read.item.item_id] = problems
        return out

    def _sheet_item(self, read: _Read, problems: list[tuple[str, str]]) -> SheetItem:
        element = read.element
        return SheetItem(
            item_id=read.item.item_id,
            element_id=read.item.element_id,
            kind=read.item.kind,
            type=element.type if element is not None else "",
            label=self._label(read),
            marking=element.handling.classification if element is not None else "",
            follows=read.item.kind != "node",
            source=read.item.source,
            target=read.item.target,
            problems=[words for _, words in problems],
        )

    async def _pending_items(self, case_id: str, board_id: str | None) -> list[BoardItem]:
        held = (
            await self.boards.items.on_board(case_id, board_id)
            if board_id is not None
            else await self.boards.items.in_case(case_id)
        )
        # An item an open promotion already carries is not offered again: one item, one open
        # promotion, so no two loads stamp one element.
        open_ = await self.store.pending_item_ids(case_id)
        return [
            i for i in held
            if i.withdrawn_at is None and i.promoted_at is None and i.item_id not in open_
        ]  # fmt: skip

    def _checks(
        self, reads: Sequence[_Read], problems: dict[str, list[tuple[str, str]]], dataset: Dataset
    ) -> list[PromotionCheck]:
        """Each check counted by its code, never by its words. `ends` counts the links one of whose
        drawn ends cannot go (a check that can fail, not a sentence)."""
        highest = self.highest(dataset)

        def failing(code: str) -> int:
            return sum(1 for r in reads if any(c == code for c, _ in problems[r.item.item_id]))

        blocked = {
            r.item.element_id for r in reads if r.item.kind == "node" and problems[r.item.item_id]
        }
        ends = sum(
            1 for r in reads
            if r.item.kind == "link" and ({r.item.source, r.item.target} & blocked)
        )  # fmt: skip
        counts = {"marking": failing("marking"), "types": failing("types"),
                  "graded": failing("graded"), "ends": ends}  # fmt: skip
        words = {
            "marking": f"Every marking within {dataset.name}'s highest allowed, {highest}",
            "types": f"Every type in {dataset.name}'s model",
            "graded": "Every item graded, with a source",
            "ends": "Every link with both its ends able to go",
        }
        return [
            PromotionCheck(
                name=code, passed=counts[code] == 0,
                words=words[code] + ("" if counts[code] == 0 else f": {counts[code]} not"),
            )
            for code in CHECKS
        ]  # fmt: skip

    def _recorded_as(self, dataset: Dataset, trigger: str) -> str:
        how = (
            "committed at once (the Author promotes)"
            if dataset.promotion_policy == "author_promotes"
            else "sent for review by a second person: one of the dataset's Authors who may "
            "review promotions"
        )
        return (
            f"One load into {dataset.name} (trigger {trigger}), {how}. Each item stays drawn "
            "and keeps its marking and grading; it is listed in the Ingest Studio's Analyst "
            "promotions and reverted like any load."
        )

    async def _warnings(self, board: StoredCaseView, reader: Principal) -> list[str]:
        found = await self.boards.suggestions(board, reader)
        drawn = sorted({s.drawn for s in found.suggestions})
        if not drawn:
            return []
        labels = {
            n.id: (n.provenance.drawn.label if n.provenance.drawn else n.id)
            for n in await self.boards.graph.get_nodes(drawn, reader)
        }
        return [
            f"{labels.get(d, 'An item')} looks like a loaded item and has no decision yet: decide "
            "Same or Not the same on the board first, or promote it as a separate item."
            for d in drawn
        ]

    # --- the sheet ------------------------------------------------------------------------

    async def _seen(self, case_id: str, board_id: str | None, reader: Principal) -> list[_Read]:
        reads = await self._read(await self._pending_items(case_id, board_id), reader)
        return [r for r in reads if r.element is not None]

    async def sheet(self, board: StoredCaseView, reader: Principal) -> PromotionSheet:
        dataset, refused = await self._target(board.case_id)
        top = self._top()
        if dataset is None:
            return PromotionSheet(
                board_id=board.id, dataset_id=None, dataset_name=None, highest_marking=top,
                policy="author_promotes", items=[], checks=[], recorded_as="", refused=refused,
            )  # fmt: skip
        # Rule 3: an item the reader may not see now is not on their sheet, as from every read.
        reads = await self._seen(board.case_id, board.id, reader)
        problems = await self._problems(reads, dataset, board.case_id, reader)
        items = [self._sheet_item(r, problems[r.item.item_id]) for r in reads]
        return PromotionSheet(
            board_id=board.id,
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            highest_marking=self.highest(dataset),
            policy=dataset.promotion_policy,
            items=items,
            checks=self._checks(reads, problems, dataset),
            warnings=await self._warnings(board, reader),
            recorded_as=self._recorded_as(dataset, "analyst_promotion"),
        )

    # --- what goes ------------------------------------------------------------------------

    async def _plan(
        self,
        reads: Sequence[_Read],
        problems: dict[str, list[tuple[str, str]]],
        ticked: Sequence[str],
        dataset: Dataset,
        reader: Principal,
    ) -> tuple[list[_Read], list[LeftOut]]:
        """What goes, and what is left out with its reason. A ticked item with a problem refuses
        the whole promotion (the route's own check, whatever the sheet said); an unticked item is
        left out; a link goes only when both its ends will be in the dataset."""
        by_id = {r.item.item_id: r for r in reads}
        unknown = [i for i in ticked if i not in by_id]
        if unknown:
            raise ItemNotFound
        failing = [by_id[i] for i in ticked if problems[i]]
        if failing:
            first = failing[0]
            raise PromotionRefused(
                "check_failed",
                f"{self._label(first)} cannot be promoted: {problems[first.item.item_id][0][1]}",
                status=422,
            )
        going_nodes = {by_id[i].item.element_id for i in ticked if by_id[i].item.kind == "node"}
        # An end already in the dataset: loaded there, or promoted before; read through the
        # reader's own handling in the dataset alone, so an end they may not see does not count.
        ends = {
            e for r in reads if r.item.kind != "node" for e in (r.item.source, r.item.target) if e
        }
        in_it = reader.model_copy(update={"datasets": [dataset.id]})
        held = await self.boards.graph.get_nodes(sorted(ends - going_nodes), in_it)
        in_dataset = {n.id for n in held if dataset.id in n.datasets}
        lands = going_nodes | in_dataset
        goes: list[_Read] = [by_id[i] for i in ticked if by_id[i].item.kind == "node"]
        left: list[LeftOut] = []
        for read in reads:
            label = self._label(read)
            if read.item.kind == "node":
                if read.item.item_id not in ticked:
                    left.append(LeftOut(item_id=read.item.item_id, label=label, why="Not ticked."))
                continue
            follows = read.item.kind in ("picture", "match")
            wanted = follows or read.item.item_id in ticked
            both = self.ends_land(read.item, lands, going_nodes)
            if not wanted:
                left.append(LeftOut(item_id=read.item.item_id, label=label, why="Not ticked."))
            elif not both:
                left.append(
                    LeftOut(
                        item_id=read.item.item_id, label=label,
                        why=(
                            "Its drawn item does not go."
                            if follows
                            else "One of its ends will not be in the dataset: it stays behind."
                        ),
                    )
                )  # fmt: skip
            elif problems[read.item.item_id]:
                left.append(
                    LeftOut(item_id=read.item.item_id, label=label,
                            why=problems[read.item.item_id][0][1])
                )  # fmt: skip
            else:
                goes.append(read)
        return goes, left

    async def _record(
        self,
        *,
        trigger: str,
        case_id: str,
        board_id: str | None,
        dataset: Dataset,
        layer_id: str,
        proposer: Principal,
        goes: Sequence[_Read],
        left: Sequence[LeftOut],
        grant_id: str | None = None,
    ) -> PromotionRecord:
        if not goes:
            raise PromotionRefused(
                "nothing_goes", "Nothing ticked can be promoted: see what was left out and why.",
                status=422,
            )  # fmt: skip
        node_ids = [r.item.element_id for r in goes if r.item.kind == "node"]
        edge_ids = [r.item.element_id for r in goes if r.item.kind != "node"]
        # A picture's Document goes with its DEPICTS link.
        node_ids += [r.item.source for r in goes if r.item.kind == "picture" and r.item.source]
        markings = [r.element.handling.classification for r in goes if r.element is not None]
        markings += [
            self._docs[r.item.source].handling.classification
            for r in goes
            if r.item.kind == "picture" and r.item.source in self._docs
        ]
        ranked = self.boards.scheme.classification
        marking = max(markings, key=ranked.index) if markings else ranked[0]
        record = PromotionRecord(
            id=new_id(), load_id=f"promotion-{new_id()}", trigger=trigger,  # type: ignore[arg-type]
            case_id=case_id, board_id=board_id, dataset_id=dataset.id, layer_id=layer_id,
            proposed_by=proposer.id, proposed_at=datetime.now(UTC), status="awaiting_review",
            marking=marking, unit=dataset.owning_unit, node_ids=tuple(dict.fromkeys(node_ids)),
            edge_ids=tuple(edge_ids), item_ids=tuple(r.item.item_id for r in goes),
            left_out=tuple((x.item_id, x.label, x.why) for x in left), grant_id=grant_id,
        )  # fmt: skip
        await self.store.add(record)
        return record

    async def promote(
        self, board: StoredCaseView, ticked: Sequence[str], proposer: Principal
    ) -> PromotionRecord:
        """*Promote*: every check again, here (the sheet may have been bypassed); then one load,
        committed at once or sent for review under the dataset's policy."""
        dataset, refused = await self._target(board.case_id)
        if dataset is None:
            raise PromotionRefused("nothing_to_promote_into", refused or "", status=409)
        reads = await self._seen(board.case_id, board.id, proposer)
        problems = await self._problems(reads, dataset, board.case_id, proposer)
        goes, left = await self._plan(
            reads, problems, list(dict.fromkeys(ticked)), dataset, proposer
        )
        layer = goes[0].item.dataset_id if goes else ""
        record = await self._record(
            trigger="analyst_promotion", case_id=board.case_id, board_id=board.id,
            dataset=dataset, layer_id=layer, proposer=proposer, goes=goes, left=left,
        )  # fmt: skip
        if self.commits_at_once(dataset):
            return await self._commit(record, by=None)
        return record

    # --- the checks, each its own call site (rule 15: each plant replaces exactly one) ------

    @staticmethod
    def ends_land(item: BoardItem, lands: set[str], going: set[str]) -> bool:
        """A link goes only when both its ends will be in the dataset. A picture or a match
        decision goes only with its own drawn node in this promotion, never with a later,
        unrelated one (a *Same* changes resolution for every case reading the dataset)."""
        if item.kind == "picture":
            return item.target in going
        if item.kind == "match":
            return bool({item.source, item.target} & going) and (
                item.source in lands and item.target in lands
            )
        return item.source in lands and item.target in lands

    @staticmethod
    def commits_at_once(dataset: Dataset) -> bool:
        """ADR-145 decision 8: *Author promotes* commits at once; otherwise a second person."""
        return dataset.promotion_policy == "author_promotes"

    @staticmethod
    def refuse_own_promotion(record: PromotionRecord, reviewer: Principal) -> None:
        """Never the second person on one's own work (ADR-133 Amendment 8)."""
        if reviewer.id == record.proposed_by:
            raise PromotionRefused(
                "own_promotion",
                "You sent this promotion: a second person must review it.",
                status=403,
            )

    @staticmethod
    def reviewer_sees_all(reads: Sequence[_Read]) -> bool:
        """Rule 3: a reviewer approves only what they have read; one item they may not see and
        they may not approve (another of the dataset's Authors may)."""
        return all(r.element is not None for r in reads)

    async def reject(
        self,
        record: PromotionRecord,
        *,
        was: str,
        by: str | None,
        reason: str,
        audited_by_route: bool = False,
    ) -> bool:
        """Every way a promotion ends rejected (a reviewer's, the approval's re-check, a refused or
        failed load, its layer deleted): recorded once, and a layer merge's read grant closed with
        it (Amendment 2 decision 1: the grant ends with the merge, whatever ends it)."""
        now = datetime.now(UTC)
        done = await self.store.decide(
            record.id,
            was=was,
            now="rejected",
            by=by,
            at=now,
            reason=reason,  # type: ignore[arg-type]
        )
        if record.grant_id is not None:
            await self.store.close_grant(record.grant_id, now)
        if done and not audited_by_route and self.on_rejected is not None:
            await self.on_rejected(record, reason)
        return done

    async def item_marked(self, case_id: str, item_id: str, marking: str) -> None:
        """An item edited to `marking`: an open promotion carrying it is marked as it is now."""
        await self.store.raise_marking(
            case_id, item_id, marking, list(self.boards.scheme.classification)
        )

    async def case_still_removed(self, case_id: str) -> bool:
        """A removed case's layer is merged only while the case is still removed (Amendment 5
        decision 7): one restored since is a live case again, read by its members alone."""
        states = await self.investigations.admin_states([case_id])
        return case_id in states and states[case_id][1]

    async def _commit(self, record: PromotionRecord, *, by: str | None) -> PromotionRecord:
        """The load itself: one graph transaction, all or nothing; then the registry's
        `promoted_at` (the withdrawal reads it, never the element). A load that fails leaves the
        promotion rejected, saying so, with nothing written."""
        graph = self.boards.graph
        tx = await graph.begin_transaction()
        try:
            await graph.promote_elements(
                list(record.node_ids), list(record.edge_ids), record.dataset_id, record.load_id, tx
            )
        except NotPromotable as gone:
            await graph.rollback_transaction(tx)
            await self.reject(
                record, was="awaiting_review", by=by,
                reason=f"Nothing was written: {gone.count} of its items changed since it was sent.",
            )  # fmt: skip
            raise PromotionRefused(
                "items_changed",
                "Nothing was promoted: some of its items were withdrawn or changed since it was "
                "sent. Promote again from the board.",
            ) from gone
        except Exception:
            # Whatever refused the load (an ambiguous id, a composite, an unconverted case), the
            # promotion is not left waiting as if it could still be approved.
            await graph.rollback_transaction(tx)
            await self.reject(
                record, was="awaiting_review", by=by,
                reason="The load was refused, and nothing was written.",
            )  # fmt: skip
            raise
        now = datetime.now(UTC)
        if not await self.store.decide(
            record.id, was="awaiting_review", now="committed", by=by, at=now
        ):
            await graph.rollback_transaction(tx)
            raise PromotionRefused("already_decided", "This promotion has already been decided.")
        try:
            await graph.commit_transaction(tx)
        except Exception:
            await self.reject(
                record, was="committed", by=by, reason="The load failed, and nothing was written."
            )
            raise
        await self.boards.items.mark_promoted(record.case_id, list(record.item_ids), now)
        if record.grant_id is not None:
            await self.store.close_grant(record.grant_id, now)
        held = await self.store.get(record.id)
        assert held is not None
        return held

    # --- review ---------------------------------------------------------------------------

    async def is_author_of(self, dataset_id: str, reader: Principal) -> bool:
        home = await self.boards.datasets.home_case_of(dataset_id)
        if home is None:
            return False
        try:
            await self.investigations.get_authorized(
                home.investigation_id, reader, need=self.author_level
            )
        except Exception:
            return False
        return True

    async def of_dataset(self, dataset_id: str, promotion_id: str) -> PromotionRecord:
        held = await self.store.get(promotion_id)
        if held is None or held.dataset_id != dataset_id:
            raise PromotionNotFound
        return held

    def _reviewer_read(self, record: PromotionRecord, reviewer: Principal) -> Principal | None:
        """What the reviewer reads the promotion's own elements through, by id, with their own
        handling (Amendment 2 decision 1: "as a promotion reviewer reads what they review"):
        while it waits, its layer and the dataset it goes into (a drawn link's loaded end is
        there); once committed, the dataset alone, where its elements now are. A rejected or
        reverted promotion's elements are the case's layer's alone, read by its members and no
        one else: nothing of them is read for it (rule 3; `None`)."""
        if record.status == "awaiting_review":
            return reviewer.model_copy(update={"datasets": [record.dataset_id, record.layer_id]})
        if record.status == "committed":
            return reviewer.model_copy(update={"datasets": [record.dataset_id]})
        return None

    async def _elements(
        self, record: PromotionRecord, reviewer: Principal
    ) -> tuple[list[Node], list[Edge]]:
        reader = self._reviewer_read(record, reviewer)
        if reader is None:
            return [], []
        nodes = await self.boards.graph.get_nodes(list(record.node_ids), reader)
        edges = await self.boards.graph.get_edges(list(record.edge_ids), reader)
        return nodes, edges

    async def shown_counts(
        self, records: Sequence[PromotionRecord], reader: Principal
    ) -> dict[str, tuple[int, int]]:
        """Each promotion's counts as `reader` would be shown its items in *Details*, never as
        recorded (Amendment 5 decision 6a: the counts of what is shown, never the difference).
        One read per layer, not per promotion. A promotion whose elements are read for no one
        (rejected, reverted) keeps its recorded counts: none of its items is shown to anyone."""
        out: dict[str, tuple[int, int]] = {}
        groups: dict[tuple[str, ...], list[PromotionRecord]] = {}
        for record in records:
            read = self._reviewer_read(record, reader)
            if read is None:
                out[record.id] = (len(record.node_ids), len(record.edge_ids))
                continue
            groups.setdefault(tuple(read.datasets), []).append(record)
        for datasets, held in groups.items():
            read = reader.model_copy(update={"datasets": list(datasets)})
            node_ids = sorted({n for r in held for n in r.node_ids})
            edge_ids = sorted({e for r in held for e in r.edge_ids})
            nodes = {n.id for n in await self.boards.graph.get_nodes(node_ids, read)}
            edges = {e.id for e in await self.boards.graph.get_edges(edge_ids, read)}
            for r in held:
                out[r.id] = (
                    sum(1 for n in set(r.node_ids) if n in nodes),
                    sum(1 for e in r.edge_ids if e in edges),
                )
        return out

    async def details(self, record: PromotionRecord, reviewer: Principal) -> PromotionDetails:
        nodes, edges = await self._elements(record, reviewer)
        items = [_detail(n, "node") for n in nodes] + [_detail(e, _kind(e)) for e in edges]
        read = self._reviewer_read(record, reviewer) is not None
        withheld = read and (
            len(nodes) != len(set(record.node_ids)) or len(edges) != len(record.edge_ids)
        )
        promotion = await self.view(record, reviewer, show_case=True)
        if read:
            # Rule 7: the counts of what is shown, never beside a difference; the same counts
            # the list gives this reader (`shown_counts`).
            promotion = promotion.model_copy(update={"nodes": len(nodes), "links": len(edges)})
        return PromotionDetails(promotion=promotion, items=items, withheld=withheld)

    async def decide(
        self, record: PromotionRecord, reviewer: Principal, *, approve: bool, reason: str | None
    ) -> PromotionRecord:
        """*Approve and commit* or *Reject with a reason*, by one of the policy's approvers, never
        the proposer. The route has checked `review_promotions`; this checks the rest."""
        if record.status != "awaiting_review":
            raise PromotionRefused("already_decided", "This promotion has already been decided.")
        self.refuse_own_promotion(record, reviewer)
        if not await self.is_author_of(record.dataset_id, reviewer):
            raise PromotionRefused(
                "not_an_author",
                "Only one of the dataset's Authors who may review promotions can decide this.",
                status=403,
            )
        if approve:
            if record.trigger == "layer_merge" and not await self.case_still_removed(
                record.case_id
            ):
                await self.reject(
                    record, was="awaiting_review", by=reviewer.id,
                    reason="Nothing was written: the case was restored since the merge was sent.",
                )  # fmt: skip
                raise PromotionRefused(
                    "case_open",
                    "Nothing was merged: the case has been restored, so its layer is its own "
                    "again.",
                )
            await self.recheck(record, reviewer)
            return await self._commit(record, by=reviewer.id)
        if not await self.reject(
            record, was="awaiting_review", by=reviewer.id, reason=(reason or "").strip(),
            audited_by_route=True,
        ):  # fmt: skip
            raise PromotionRefused("already_decided", "This promotion has already been decided.")
        held = await self.store.get(record.id)
        assert held is not None
        return held

    async def recheck(self, record: PromotionRecord, reviewer: Principal) -> None:
        """At the approval, on the items as they are now. First, the reviewer must see every one
        (403, and the promotion waits for another reviewer). Then every check runs again: an item
        withdrawn or edited since it was sent (a marking raised, the dataset's highest lowered)
        refuses the load, and the promotion is recorded rejected, saying why. Nothing is written."""
        held = (await self.boards.datasets.egress_of([record.dataset_id])).get(record.dataset_id)
        if held is None:
            raise PromotionNotFound
        reader = self._reviewer_read(record, reviewer)
        assert reader is not None  # `decide` reads only a promotion still waiting
        items = [await self.boards.items.get(record.case_id, i) for i in record.item_ids]
        live = [i for i in items if i is not None and i.withdrawn_at is None]
        reads = await self._read(live, reader)
        if not self.reviewer_sees_all(reads):
            raise PromotionRefused(
                "not_all_seen",
                "You may not see every item in this promotion, so you may not approve it: ask "
                "another of the dataset's Authors who may review promotions.",
                status=403,
            )
        reads = [r for r in reads if r.element is not None]
        problems = await self._problems(reads, held, record.case_id, reader)
        failing = [(r, problems[r.item.item_id][0][1]) for r in reads if problems[r.item.item_id]]
        if len(live) != len(record.item_ids) or failing:
            why = (
                f"{self._label(failing[0][0])} has changed since it was sent: {failing[0][1]}"
                if failing
                else "One of its items was withdrawn since it was sent."
            )
            await self.reject(
                record, was="awaiting_review", by=reviewer.id, reason=f"Nothing was written. {why}"
            )
            raise PromotionRefused("items_changed", f"Nothing was promoted. {why}")

    # --- views ----------------------------------------------------------------------------

    async def view(
        self,
        record: PromotionRecord,
        reader: Principal,
        *,
        may_review: bool = False,
        why_not: str | None = None,
        reverts: bool = False,
        with_board: bool = False,
        show_case: bool = True,
        counts: tuple[int, int] | None = None,
    ) -> Promotion:
        """One promotion for `reader`. What it left out, with its labels as the sheet showed them,
        goes to its proposer alone (rule 3: an unticked item may be one no one else may see). The
        case is named only where `show_case` says the reader may know it (its own board, one of
        the dataset's Authors)."""
        held = await self.boards.datasets.egress_of([record.dataset_id])
        dataset = held.get(record.dataset_id)
        people = [p for p in (record.proposed_by, record.reviewed_by) if p]
        names = await self.names(people) if self.names is not None else {}
        case_name = (
            await self._case_name(record.case_id) if show_case else "a case reading this dataset"
        )
        return Promotion(
            id=record.id, load_id=record.load_id, trigger=record.trigger,
            dataset_id=record.dataset_id,
            dataset_name=dataset.name if dataset is not None else record.dataset_id,
            case_id=record.case_id if show_case else "", case_name=case_name,
            board_id=record.board_id if with_board else None,
            proposed_by=record.proposed_by,
            proposed_by_name=names.get(record.proposed_by, record.proposed_by),
            proposed_at=record.proposed_at, status=record.status,
            reviewed_by=record.reviewed_by,
            reviewed_by_name=names.get(record.reviewed_by, record.reviewed_by)
            if record.reviewed_by else None,
            reviewed_at=record.reviewed_at, reason=record.reason,
            nodes=counts[0] if counts else len(record.node_ids),
            links=counts[1] if counts else len(record.edge_ids),
            left_out=[LeftOut(item_id=i, label=lab, why=why) for i, lab, why in record.left_out]
            if reader.id == record.proposed_by else [],
            revert_command=REVERT_COMMAND.format(load_id=record.load_id)
            if reverts and record.status == "committed" else None,
            may_review=may_review and record.status == "awaiting_review",
            why_not=why_not if record.status == "awaiting_review" else None,
        )  # fmt: skip

    async def _case_name(self, case_id: str) -> str:
        if self.case_names is None:
            return case_id
        return await self.case_names(case_id) or case_id

    # --- a removed case's layer (Amendment 2 decision 1) ------------------------------------

    async def open_merge(
        self, dataset: Dataset, case_id: str, case_name: str, layer_id: str, author: Principal
    ) -> LayerMergeSheet:
        """The merge sheet: a grant to this Author for this layer, for this merge alone; then the
        layer's unpromoted drawn items, read through the grant and the Author's own handling."""
        grant = LayerGrant(
            id=new_id(), layer_id=layer_id, case_id=case_id, dataset_id=dataset.id,
            holder=author.id, opened_at=datetime.now(UTC),
        )  # fmt: skip
        await self.store.open_grant(grant)
        return await self.merge_sheet(grant, dataset, case_name, author)

    async def _granted(
        self, grant_id: str, dataset: Dataset, author: Principal, *, case_checked: bool = True
    ) -> LayerGrant:
        grant = await self.store.grant(grant_id)
        if (
            grant is None
            or grant.holder != author.id
            or grant.dataset_id != dataset.id
            or grant.closed_at is not None
            or datetime.now(UTC) - grant.opened_at > timedelta(hours=GRANT_HOURS)
        ):
            raise PromotionRefused(
                "no_open_grant",
                "This merge is closed: open Merge into the dataset again to read the layer.",
                status=403,
            )
        if case_checked and not await self.case_still_removed(grant.case_id):
            # Restored since the sheet was opened: its layer is a live case's again, and the
            # grant ends now, whether it is read, merged or cancelled next.
            await self.store.close_grant(grant.id, datetime.now(UTC))
            raise PromotionRefused(
                "case_open",
                "Only a removed case's layer can be merged: this case has been restored.",
            )
        return grant

    def _granted_read(self, grant: LayerGrant, author: Principal) -> Principal:
        """The grant's read: that one layer, with the dataset its loaded ends are in."""
        return author.model_copy(update={"datasets": [grant.dataset_id, grant.layer_id]})

    async def merge_sheet(
        self, grant: LayerGrant, dataset: Dataset, case_name: str, author: Principal
    ) -> LayerMergeSheet:
        grant = await self._granted(grant.id, dataset, author)
        reader = self._granted_read(grant, author)
        # Rule 3: an item above the Author's clearance is absent from the sheet, as from every
        # read, and is not counted; it stays in the layer.
        reads = await self._seen(grant.case_id, None, reader)
        problems = await self._problems(reads, dataset, grant.case_id, reader)
        items = [self._sheet_item(r, problems[r.item.item_id]) for r in reads]
        return LayerMergeSheet(
            grant_id=grant.id, investigation_id=grant.case_id, case_name=case_name,
            dataset_id=dataset.id, dataset_name=dataset.name,
            highest_marking=self.highest(dataset), policy=dataset.promotion_policy, items=items,
            checks=self._checks(reads, problems, dataset),
            recorded_as=self._recorded_as(dataset, "layer_merge"),
        )  # fmt: skip

    async def merge(
        self, grant_id: str, dataset: Dataset, ticked: Sequence[str], author: Principal
    ) -> PromotionRecord:
        grant = await self._granted(grant_id, dataset, author)
        reader = self._granted_read(grant, author)
        reads = await self._seen(grant.case_id, None, reader)
        problems = await self._problems(reads, dataset, grant.case_id, reader)
        goes, left = await self._plan(reads, problems, list(dict.fromkeys(ticked)), dataset, reader)
        record = await self._record(
            trigger="layer_merge", case_id=grant.case_id, board_id=None, dataset=dataset,
            layer_id=grant.layer_id, proposer=author, goes=goes, left=left, grant_id=grant.id,
        )  # fmt: skip
        if self.commits_at_once(dataset):
            return await self._commit(record, by=None)
        return record

    async def cancel_merge(self, grant_id: str, dataset: Dataset, author: Principal) -> None:
        # Cancelling always closes the holder's grant, the case restored or not.
        grant = await self._granted(grant_id, dataset, author, case_checked=False)
        await self.store.close_grant(grant.id, datetime.now(UTC))

    async def delete_layer(self, case_id: str, layer_id: str) -> LayerDeleted:
        """Every element wholly the layer's withdrawn, never deleted; the registry's items too.
        Promoted items hold the dataset as well and are never touched."""
        graph = self.boards.graph
        tx = await graph.begin_transaction()
        try:
            gone = await graph.withdraw_layer(layer_id, f"{LAYER_DELETE_PREFIX}{case_id}", tx)
        except Exception:
            await graph.rollback_transaction(tx)
            raise
        await graph.commit_transaction(tx)
        now = datetime.now(UTC)
        await self.store.close_grants_for_layer(layer_id, now)
        await self.store.mark_layer_deleted(layer_id, now)
        # What still waits from the layer is rejected now, not left waiting (and ageing in
        # *Promotions overdue*) until someone tries to approve it.
        for waiting in await self.store.waiting_from_layer(layer_id):
            await self.reject(
                waiting, was="awaiting_review", by=None,
                reason="Nothing was written: its case's layer was deleted.",
            )  # fmt: skip
        held = await self.boards.items.in_case(case_id)
        unpromoted = [i.item_id for i in held if i.withdrawn_at is None and i.promoted_at is None]
        if unpromoted:
            await self.boards.items.withdraw(case_id, unpromoted, LAYER_DELETER, now)
        # Rule 7: no count of what was withdrawn, which would include what the deleter may not see.
        del gone
        return LayerDeleted(
            investigation_id=case_id,
            words="The layer was deleted: its items are withdrawn and kept in the audit. Promoted "
            "items were not touched.",
        )

    # --- revert (the operator command's core) ----------------------------------------------

    async def revert(self, record: PromotionRecord) -> PromotionRecord:
        return await revert_promotion(record, self.boards.graph, self.store, self.boards.items)


async def revert_promotion(
    record: PromotionRecord, graph: Any, store: PromotionStore, items: Any
) -> PromotionRecord:
    """The revert of a committed promotion: the dataset taken back from exactly its elements in
    one transaction, the promotion recorded `reverted`, its items' `promoted_at` cleared. The
    operator command's core (`scripts.revert_promotion`), run with the Conduit stopped (ADR-127
    Amendment 9); never a route (ADR-143 open question 2, settled (a): Amendment 5 decision 8).

    Refused, as a load's revert is (ADR-127 Amendment 6, `live_edges_touching`), while a live link
    other than the promotion's own and the case's own unpromoted drawing rests on one of its
    nodes: another case's link or a later load's would be left resting on a node gone from the
    dataset. A promotion from a layer since deleted takes its elements out with the layer."""
    if record.status != "committed":
        raise PromotionRefused(
            "not_committed",
            f"Promotion {record.load_id} is {record.status}: nothing to revert.",
        )
    held = await items.in_case(record.case_id)
    own_drawing = {
        i.element_id for i in held
        if i.kind != "node" and i.withdrawn_at is None and i.promoted_at is None
    }  # fmt: skip
    resting = await graph.live_edges_touching(list(record.node_ids))
    others = set(resting) - set(record.edge_ids) - own_drawing
    if others:
        raise PromotionRefused(
            "links_rest_on_it",
            f"{len(others)} link(s) written since rest on its items: revert those first.",
        )
    layer_deleted = await store.layer_deleted(record.layer_id)
    tx = await graph.begin_transaction()
    try:
        await graph.revert_promotion(record.load_id, record.dataset_id, tx)
        if layer_deleted:
            await graph.withdraw_layer(
                record.layer_id, f"{LAYER_DELETE_PREFIX}{record.case_id}", tx
            )
    except Exception:
        await graph.rollback_transaction(tx)
        raise
    if not await store.decide(
        record.id, was="committed", now="reverted", by=None, at=datetime.now(UTC)
    ):
        await graph.rollback_transaction(tx)
        raise PromotionRefused("already_decided", "This promotion has changed since it was read.")
    await graph.commit_transaction(tx)
    await items.mark_promoted(record.case_id, list(record.item_ids), None)
    if layer_deleted:
        await items.withdraw(
            record.case_id, list(record.item_ids), LAYER_DELETER, datetime.now(UTC)
        )
    return replace(record, status="reverted")


def _kind(edge: Edge) -> Any:
    if edge.type in (SAME_AS, NOT_SAME_AS):
        return "match"
    if edge.provenance.drawn is None:
        return "picture"
    return "link"


def _detail(element: Node | Edge, kind: Any) -> DetailItem:
    drawn = element.provenance.drawn
    if drawn is not None:
        label = drawn.label
    elif isinstance(element, Node):
        label = (
            str(element.properties.get("title") or "A picture")
            if element.type == DOCUMENT_TYPE
            else display_name(element)
        )
        kind = "picture" if element.type == DOCUMENT_TYPE else kind
    else:
        label = element.type
    grade = drawn.grading if drawn is not None else None
    return DetailItem(
        element_id=element.id, kind=kind, type=element.type, label=label,
        marking=element.handling.classification,
        source_note=drawn.source_note if drawn is not None else None,
        grading=f"{grade.source}{grade.intelligence}{grade.handling}" if grade else None,
    )  # fmt: skip
