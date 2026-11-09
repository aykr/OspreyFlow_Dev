"""A drawn dataset merged into another (ADR-143 Amendment 2 decisions 6 and 7; Amendment 3 decision
2; spec 03 §3.1d; L3.9).

**Who** (Amendment 3, L6 answered (a)): an Author of the **target** dataset (its home case's,
ADR-145 Amendment 4) who holds `merge_datasets` (the routes' right), with a second person when the
target's promotion policy asks. An administrator does not merge one by being an administrator. The
merger reads the drawing as any reader does: through a case of theirs that reads it, its home case
(the drawing's Author shares it with them). Nothing here widens what anyone may read (rule 3): the
merger reads the drawn dataset and the target, each of which they could already read, and nothing
else.

**The four steps** (decision 6), from the Ingest Studio's *Merge into a dataset…*:

1. **Map the models.** Each drawn type goes in as the target's type of the same name; a type the
   target's model lacks is left out, saying so, and may be proposed on the target's Model tab. An
   element keeps its type for good (types are the store's classes, and the merge keeps the same
   element: rule 6), so a drawn type is never mapped onto another name here (the case lane's choice
   under Prompt L, `REPORT.md`, asked of the orchestrator).
2. **Match.** *Looks like a loaded item* (`Boards.alike`), with candidates read through the merger
   scoped to the **target alone**, so the adapter leaves out every node the merger may not see and
   every node of any other dataset: no match is offered, counted or ordered across what they may
   not read (rules 3 and 7). A chosen match is written with the load as a scored, `inferred`
   `SAME_AS` (rule 5), shaped as the resolver writes one; a person confirms it later, and nothing is
   collapsed in storage (rule 6).
3. **Dry run.** What would be added and matched, counting only what the merger may see; nothing
   written.
4. **Merge.** One promotion (L3.4's `Promotions`, trigger `drawn_merge`): the drawn elements gain
   the target, all or nothing, under its highest marking and policy, reviewed in its Runs, audited,
   and reverted as a promotion is (`scripts.revert_promotion`).

**After the merge** (decision 7): the drawing's home case reads the target, and its drawn dataset
read-only (`DatasetStore.merge_drawn`); each of its boards becomes a view (drawing off, layout and
sharing kept, `CaseViewStore.merge_boards`); what did not become data is shown on the view as
annotations, read through each reader's own handling (`view_annotations`), so an item they may not
see has none. Drawing again opens a new board, into the case's layer.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from conduit_common.identity import new_edge_id
from ontology.handling import merge_handling
from schemas.case_views import ViewAnnotation
from schemas.domain import (
    SAME_AS,
    EdgeWrite,
    Handling,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from schemas.promotions import (
    DrawnMergeDryRun,
    DrawnMergeInput,
    DrawnMergeSheet,
    LeftOut,
    MergeMatch,
    MergeTarget,
    MergeTargets,
    TypeMapping,
)

from .board_store import BoardItemStore
from .case_views import CaseViewStore, StoredCaseView
from .datasets import DRAWN, SOURCE, Dataset, DrawnAlreadyMerged, DrawnMerged
from .evidence_brief import display_name
from .promotion_store import MergeMatchRow, PromotionRecord
from .promotions import PromotionRefused, Promotions, _Read, is_gazetteer

logger = logging.getLogger(__name__)

#: What a merge's `SAME_AS` names as its maker, in the resolver's `model_version` place.
MATCH_MODEL_VERSION = "drawn_merge"
_NOT_A_TARGET = "No dataset of that id may take this drawing from you."


class _Cases(Protocol):
    async def list_for(self, principal: Principal) -> list[tuple[Any, Any]]: ...


@dataclass
class DrawnMerges:
    """The merge, built per request from the app's stores (`app.get_drawn_merges`)."""

    promotions: Promotions
    cases: _Cases

    @property
    def _datasets(self) -> Any:
        return self.promotions.boards.datasets

    # --- the drawing and where it may go -------------------------------------------------

    async def drawn(self, dataset_id: str) -> tuple[Dataset, str]:
        """The drawn dataset the route's gate admitted, and its home case."""
        held = (await self._datasets.egress_of([dataset_id])).get(dataset_id)
        home = await self._datasets.home_case_of(dataset_id) if held is not None else None
        if held is None or held.kind != DRAWN or home is None:
            raise PromotionRefused(
                "not_drawn", "Only a drawn dataset is merged into another from here.", status=409
            )
        return held, home.investigation_id

    async def targets(self, drawn: Dataset, reader: Principal) -> list[Dataset]:
        """The datasets `reader` may merge `drawn` into: a source dataset of the drawing's own unit
        (the case must be able to read it afterwards) that they are an Author of. Never a
        composite (it holds none of its members' data), a gazetteer (its build's places alone), a
        drawn dataset or a layer."""
        out: dict[str, Dataset] = {}
        for case, _ in await self.cases.list_for(reader):
            dataset_id = await self._datasets.dataset_of_home_case(case.id)
            if dataset_id is None or dataset_id == drawn.id or dataset_id in out:
                continue
            dataset = (await self._datasets.egress_of([dataset_id])).get(dataset_id)
            if (
                dataset is None
                or dataset.kind != SOURCE
                or is_gazetteer(dataset)
                or dataset.owning_unit != drawn.owning_unit
            ):
                continue
            # The Author level, asked as every promotion route asks it (teams included).
            if await self.promotions.is_author_of(dataset_id, reader):
                out[dataset_id] = dataset
        return sorted(out.values(), key=lambda d: (d.name, d.id))

    async def target_list(self, drawn: Dataset, reader: Principal) -> MergeTargets:
        return MergeTargets(
            drawn_dataset_id=drawn.id, drawn_name=drawn.name,
            targets=[
                MergeTarget(dataset_id=t.id, name=t.name,
                            highest_marking=self.promotions.highest(t),
                            policy=t.promotion_policy)
                for t in await self.targets(drawn, reader)
            ],
        )  # fmt: skip

    async def target(self, drawn: Dataset, target_id: str, reader: Principal) -> Dataset:
        """One answer for every dataset not offered (none of that id, another unit's, one the
        merger is no Author of, a composite): its existence and kind are not told (rule 3)."""
        for held in await self.targets(drawn, reader):
            if held.id == target_id:
                return held
        raise PromotionRefused("not_a_target", _NOT_A_TARGET, status=404)

    # --- reading the drawing ---------------------------------------------------------------

    @staticmethod
    def _read_as(reader: Principal, drawn: Dataset, target: Dataset) -> Principal:
        """The drawing and the target, each of which the merger already reads, and nothing else."""
        return reader.model_copy(update={"datasets": [drawn.id, target.id]})

    async def _reads(self, drawn: Dataset, case_id: str, read: Principal) -> list[_Read]:
        # The drawing's own items: those written into the drawn dataset (the home case's layer
        # holds only what was marked by hand, and is never merged from here).
        reads = await self.promotions._seen(case_id, None, read)
        return [r for r in reads if r.item.dataset_id == drawn.id]

    async def _matches(
        self, reads: Sequence[_Read], drawn: Dataset, target: Dataset, reader: Principal
    ) -> tuple[list[tuple[Node, Node, float, str]], bool]:
        nodes = [r.element for r in reads if r.item.kind == "node" and isinstance(r.element, Node)]
        if not nodes:
            return [], False
        # Rule 3 and 7: candidates through the target alone, so nothing of another dataset, and
        # nothing the merger may not see, is ever a candidate.
        found = await self.promotions.boards.alike(
            nodes,
            reader.model_copy(update={"datasets": [target.id]}),
            self._read_as(reader, drawn, target),
        )
        by_id = {n.id: n for n in nodes}
        return [
            (by_id[s.drawn], s.loaded, s.score, s.why)
            for s in found.suggestions
            if s.drawn in by_id
        ], found.more

    @staticmethod
    def _mapping(
        reads: Sequence[_Read], problems: dict[str, list[tuple[str, str]]], target: Dataset
    ) -> list[TypeMapping]:
        counts: dict[tuple[str, str], int] = {}
        refused: dict[tuple[str, str], str] = {}
        for read in reads:
            if read.item.kind not in ("node", "link") or read.element is None:
                continue
            key = (read.item.kind, read.element.type)
            counts[key] = counts.get(key, 0) + 1
            why = next((w for c, w in problems[read.item.item_id] if c == "types"), None)
            if why is not None:
                refused[key] = (
                    f"{why} Its items are left out and stay on the drawing; propose the type on "
                    f"{target.name}'s Model tab to merge them later."
                )
        return [
            TypeMapping(
                kind=kind,  # type: ignore[arg-type]
                drawn_type=name, target_type=None if (kind, name) in refused else name,
                items=n, why_not=refused.get((kind, name)),
            )
            for (kind, name), n in sorted(counts.items())
        ]  # fmt: skip

    async def sheet(
        self, drawn: Dataset, case_id: str, target: Dataset, reader: Principal
    ) -> DrawnMergeSheet:
        promotions = self.promotions
        read = self._read_as(reader, drawn, target)
        reads = await self._reads(drawn, case_id, read)
        problems = await promotions._problems(
            reads, target, case_id, read, into_its_own_dataset=False
        )
        matches, more = await self._matches(reads, drawn, target, reader)
        return DrawnMergeSheet(
            drawn_dataset_id=drawn.id, drawn_name=drawn.name, target_dataset_id=target.id,
            target_name=target.name, highest_marking=promotions.highest(target),
            policy=target.promotion_policy, mapping=self._mapping(reads, problems, target),
            matches=[
                MergeMatch(
                    drawn=d.id,
                    drawn_label=d.provenance.drawn.label if d.provenance.drawn else d.id,
                    loaded=n.id, loaded_label=display_name(n), loaded_type=n.type, score=score,
                    why=why,
                )
                for d, n, score, why in matches
            ],
            more_matches=more,
            items=[promotions._sheet_item(r, problems[r.item.item_id]) for r in reads],
            checks=promotions._checks(reads, problems, target),
            recorded_as=promotions._recorded_as(target, "drawn_merge"),
        )  # fmt: skip

    # --- what goes ------------------------------------------------------------------------

    async def _plan(
        self, drawn: Dataset, case_id: str, target: Dataset, body: DrawnMergeInput,
        reader: Principal,
    ) -> tuple[list[_Read], list[LeftOut], list[MergeMatchRow]]:  # fmt: skip
        """Every check again, here (the sheet may have been bypassed): the items as a promotion's
        are planned, and each chosen match must be one offered now, of a drawn node that goes."""
        promotions = self.promotions
        read = self._read_as(reader, drawn, target)
        reads = await self._reads(drawn, case_id, read)
        problems = await promotions._problems(
            reads, target, case_id, read, into_its_own_dataset=False
        )
        goes, left = await promotions._plan(
            reads, problems, list(dict.fromkeys(body.item_ids)), target, read
        )
        going = {r.item.element_id for r in goes if r.item.kind == "node"}
        offered = {
            (d.id, n.id): score
            for d, n, score, _ in (await self._matches(reads, drawn, target, reader))[0]
        }
        picks = list(dict.fromkeys((p.drawn, p.loaded) for p in body.matches))
        # Both ends as the merger reads them (the drawing and the target, nothing else).
        ends = {
            n.id: n
            for n in await promotions.boards.graph.get_nodes(
                sorted({x for pick in picks for x in pick}), read
            )
        } if picks else {}  # fmt: skip
        rows: list[MergeMatchRow] = []
        scheme, highest = promotions.boards.scheme, promotions.highest(target)
        for pick in picks:
            if (
                pick not in offered
                or pick[0] not in going
                or pick[0] not in ends
                or pick[1] not in ends
            ):
                # One answer whether the loaded node is hidden, another dataset's, or not alike.
                raise PromotionRefused(
                    "not_a_match",
                    "One of the chosen matches is not offered: choose from Match again.",
                    status=422,
                )
            d, n, score = ends[pick[0]], ends[pick[1]], offered.get(pick, 0.0)
            stricter = merge_handling(d.handling, n.handling, scheme)
            if not scheme.clears(highest, stricter.classification):
                raise PromotionRefused(
                    "check_failed",
                    f"A match would be marked {stricter.classification}, above {target.name}'s "
                    f"highest allowed marking, {highest}.",
                    status=422,
                )
            rows.append(
                MergeMatchRow(drawn=d.id, loaded=n.id, score=score,
                              handling=stricter.model_dump_json())
            )  # fmt: skip
        return goes, left, rows

    async def dry_run(
        self, drawn: Dataset, case_id: str, target: Dataset, body: DrawnMergeInput,
        reader: Principal,
    ) -> DrawnMergeDryRun:  # fmt: skip
        """Step 3: nothing written, and only what the merger may see counted (an item above them
        is not read, so not counted, and not named in what is left out)."""
        goes, left, rows = await self._plan(drawn, case_id, target, body, reader)
        return DrawnMergeDryRun(
            target_dataset_id=target.id,
            nodes=sum(1 for r in goes if r.item.kind == "node"),
            links=sum(1 for r in goes if r.item.kind != "node"),
            matches=len(rows), left_out=left,
            recorded_as=self.promotions._recorded_as(target, "drawn_merge"),
        )  # fmt: skip

    async def merge(
        self, drawn: Dataset, case_id: str, target: Dataset, body: DrawnMergeInput,
        reader: Principal,
    ) -> PromotionRecord:  # fmt: skip
        promotions = self.promotions
        if await promotions.store.waiting_from_layer(drawn.id):
            raise PromotionRefused(
                "merge_waiting",
                "A merge of this drawing is waiting for review: it is decided first.",
                status=409,
            )
        goes, left, rows = await self._plan(drawn, case_id, target, body, reader)
        markings = [Handling.model_validate_json(r.handling).classification for r in rows]
        record = await promotions._record(
            trigger="drawn_merge", case_id=case_id, board_id=None, dataset=target,
            layer_id=drawn.id, proposer=reader, goes=goes, left=left, extra_markings=markings,
        )  # fmt: skip
        await promotions.store.add_matches(record.id, rows)
        if promotions.commits_at_once(target):
            return await promotions._commit(record, by=None)
        return record


@dataclass
class MergeCommit:
    """What a `drawn_merge` promotion's commit does beside promoting its elements (`Promotions.
    merges`): its matches written in the same transaction, then decision 7."""

    promotions_store: Any
    graph: Any
    datasets: Any
    views: CaseViewStore
    items: BoardItemStore
    scheme: Any
    _written: dict[str, list[str]] = field(default_factory=dict)

    async def writes(self, record: PromotionRecord, tx: Any) -> None:
        rows = await self.promotions_store.matches_of(record.id)
        if not rows:
            return
        now = datetime.now(UTC)
        writes = [
            EdgeWrite(
                id=new_edge_id(),
                type=SAME_AS,
                source=r.drawn,
                target=r.loaded,
                properties={"score": r.score, "model_version": MATCH_MODEL_VERSION},
                # Rule 5: proposed, never confirmed by the merge; a person confirms it.
                provenance=Provenance(
                    state=ProvenanceState.INFERRED,
                    sources=[
                        SourceRef(
                            document_id=f"drawn-merge:{record.load_id}:{r.drawn}:{r.loaded}",
                            locator=record.proposed_by,
                            excerpt_hash="",
                        )
                    ],
                    first_seen=now,
                    extraction_confidence=r.score,
                ),
                handling=Handling.model_validate_json(r.handling),
                created_by=record.proposed_by,
                created_at=now,
                # Written with the load, so read as the load's (the lane review, item 12).
                load_id=record.load_id,
                # ADR-099: the datasets both ends are in once the load lands: the target.
                datasets=[record.dataset_id],
            )
            for r in rows
        ]
        self._written[record.id] = list(await self.graph.upsert_edges(writes, tx))

    async def recheck(self, record: PromotionRecord, reviewer: Principal) -> bool:
        """At an approval: whether any match has changed since it was chosen, as the reviewer reads
        it now: an end gone from their read (withdrawn, or raised above the promotion's marking,
        which they clear), its marking moved, its loaded end out of the target, or the target's
        highest lowered below it."""
        rows = await self.promotions_store.matches_of(record.id)
        if not rows:
            return False
        read = reviewer.model_copy(update={"datasets": [record.dataset_id, record.layer_id]})
        ids = sorted({x for r in rows for x in (r.drawn, r.loaded)})
        nodes = {n.id: n for n in await self.graph.get_nodes(ids, read)}
        if any(i not in nodes for i in ids):
            return True
        held = (await self.datasets.egress_of([record.dataset_id])).get(record.dataset_id)
        highest = (held.highest_marking if held else None) or self.scheme.classification[-1]
        for r in rows:
            ends = (nodes[r.drawn].handling, nodes[r.loaded].handling)
            stricter = merge_handling(*ends, self.scheme)
            if (
                stricter != Handling.model_validate_json(r.handling)
                or record.dataset_id not in nodes[r.loaded].datasets
                or not self.scheme.clears(highest, stricter.classification)
            ):
                return True
        return False

    async def before_commit(self, record: PromotionRecord) -> None:
        """Before the graph commits: the matches' link ids recorded (so the revert can always find
        them), then the drawing's one merge claimed and its case moved onto the target, in one
        Postgres transaction (`merge_drawn`, refused for a second: `DrawnAlreadyMerged`). A
        failure here rolls the graph back, so nothing is half merged."""
        written = self._written.pop(record.id, [])
        if written:
            await self.promotions_store.set_match_edges(record.id, written)
        await self.datasets.merge_drawn(
            DrawnMerged(
                dataset_id=record.layer_id, into=record.dataset_id, load_id=record.load_id,
                case_id=record.case_id, merged_at=datetime.now(UTC),
            )
        )  # fmt: skip

    @staticmethod
    def is_already_merged(error: Exception) -> bool:
        return isinstance(error, DrawnAlreadyMerged)

    async def undo_before_commit(self, record: PromotionRecord) -> None:
        """The graph commit failed after `before_commit`: the case back on its drawing."""
        held = await self.datasets.drawn_merged_of(record.layer_id)
        if held is not None and held.load_id == record.load_id:
            await self.datasets.unmerge_drawn(record.layer_id)

    async def after(self, record: PromotionRecord) -> None:
        """Decision 7, once the load is committed: the drawing's boards become views. A failure
        here is logged and leaves them boards, on which nothing is drawn any more (the drawing is
        read-only: `Boards._own_item`, `Boards.into`); the merge itself stands."""
        drawn: dict[str, list[str]] = {}
        for item in await self.items.in_case(record.case_id):
            if item.kind == "node" and item.dataset_id == record.layer_id and not item.withdrawn_at:
                drawn.setdefault(item.board_id, []).append(item.element_id)
        try:
            await self.views.merge_boards(record.case_id, record.load_id, drawn)
        except Exception:
            logger.exception(
                "drawn merge %s committed, but its boards were not made views", record.load_id
            )

    async def shown(
        self, record: PromotionRecord, reviewer: Principal
    ) -> tuple[list[MergeMatch], bool]:
        """What a reviewer reads of the merge's matches (the lane review, item 5): each whose two
        ends they may see, read through their own handling, and whether any was not shown."""
        rows = await self.promotions_store.matches_of(record.id)
        if not rows:
            return [], False
        read = reviewer.model_copy(update={"datasets": [record.dataset_id, record.layer_id]})
        ids = sorted({x for r in rows for x in (r.drawn, r.loaded)})
        nodes = {n.id: n for n in await self.graph.get_nodes(ids, read)}
        shown = [
            MergeMatch(
                drawn=r.drawn,
                drawn_label=(
                    d.provenance.drawn.label if (d := nodes[r.drawn]).provenance.drawn else r.drawn
                ),
                loaded=r.loaded, loaded_label=display_name(nodes[r.loaded]),
                loaded_type=nodes[r.loaded].type, score=r.score, why="chosen at the merge",
            )
            for r in rows
            if r.drawn in nodes and r.loaded in nodes
        ]  # fmt: skip
        return shown, len(shown) != len(rows)

    async def undo_writes(self, record: PromotionRecord, tx: Any) -> None:
        """The revert's: the merge's matches withdrawn with it (never deleted)."""
        edges = [r.edge_id for r in await self.promotions_store.matches_of(record.id) if r.edge_id]
        if edges:
            await self.graph.withdraw_elements([], edges, record.load_id, tx)

    async def undo(self, record: PromotionRecord) -> None:
        """The revert's, after its graph commit: the case back on its drawing, its views boards."""
        await self.datasets.unmerge_drawn(record.layer_id)
        await self.views.unmerge_boards(record.case_id, record.load_id)


# --- a merged drawing's view (decision 7) -----------------------------------------------------


def _grade(element: Any) -> str | None:
    g = element.provenance.drawn.grading if element.provenance.drawn else None
    return f"{g.source}{g.intelligence}{g.handling}" if g is not None else None


async def view_annotations(
    view: StoredCaseView,
    reader: Principal,
    *,
    graph: Any,
    items: BoardItemStore,
    names: Callable[[Sequence[str]], Awaitable[dict[str, str]]] | None = None,
) -> list[ViewAnnotation]:
    """What a merged drawing keeps of each drawn item on the view: read now, through `reader`'s
    own principal (the adapter filters each by marking and dataset), so an item they may not see
    has no annotation and is not counted (rule 3)."""
    if view.merged_load is None:
        return []
    held = [
        i for i in await items.on_board(view.case_id, view.id)
        if i.kind in ("node", "link") and i.withdrawn_at is None
    ]  # fmt: skip
    node_ids = [i.element_id for i in held if i.kind == "node"]
    edge_ids = [i.element_id for i in held if i.kind == "link"]
    elements: dict[str, Any] = {n.id: n for n in await graph.get_nodes(node_ids, reader)}
    if edge_ids:
        elements |= {e.id: e for e in await graph.get_edges(edge_ids, reader)}
    authors = sorted({i.author for i in held})
    named = await names(authors) if names is not None and authors else {}
    out = []
    for item in held:
        element = elements.get(item.element_id)
        if element is None or element.provenance.drawn is None:
            continue
        who = named.get(item.author, item.author)
        merged = item.promoted_at is not None
        words = (
            f"Drawn by {who}, merged as load {view.merged_load}"
            if merged
            else f"Drawn by {who}, not merged: it stays in the drawing, read-only"
        )
        out.append(
            ViewAnnotation(
                element_id=element.id, kind=item.kind,  # type: ignore[arg-type]
                label=element.provenance.drawn.label,
                marking=element.handling.classification, grading=_grade(element),
                source_note=element.provenance.drawn.source_note, words=words, merged=merged,
            )
        )  # fmt: skip
    return out


__all__: Sequence[str] = ("DrawnMerges", "MergeCommit", "view_annotations", "MATCH_MODEL_VERSION")
