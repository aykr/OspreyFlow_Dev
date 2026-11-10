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

import json
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from conduit_common.identity import new_edge_id, new_id
from ontology.handling import merge_handling
from ontology.validation import validate_properties
from schemas.case_views import ViewAnnotation
from schemas.domain import (
    SAME_AS,
    Edge,
    EdgeTypeDef,
    EdgeWrite,
    Handling,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from schemas.promotions import (
    DetailItem,
    DrawnMergeDryRun,
    DrawnMergeInput,
    DrawnMergeSheet,
    LeftOut,
    MergeMatch,
    MergeTarget,
    MergeTargets,
    TargetType,
    TypeChoice,
    TypeMapping,
)

from .board_store import BoardItemStore
from .boards import _accepts
from .case_views import CaseViewStore, StoredCaseView
from .datasets import DRAWN, SOURCE, Dataset, DrawnAlreadyMerged, DrawnMerged
from .evidence_brief import display_name
from .promotion_store import CopyRow, MergeMatchRow, PromotionRecord
from .promotions import PromotionRefused, Promotions, _detail, _kind, _Read, is_gazetteer
from .rule_evaluation import handling_readable

logger = logging.getLogger(__name__)

#: What a merge's `SAME_AS` names as its maker, in the resolver's `model_version` place.
MATCH_MODEL_VERSION = "drawn_merge"
#: What a retyped copy's `SAME_AS` back to its drawn original names as its maker (Amendment 7).
RETYPE_MODEL_VERSION = "drawn_merge_retype"
#: Each drawn (kind, type): the target's type it goes in as (`None`: left out) and, retyped,
#: each drawn property's place in it (`None`: not carried).
_Chosen = dict[tuple[str, str], tuple[str | None, dict[str, str | None]]]
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

    async def _names(self, case_id: str, read: Principal) -> dict[str, str]:
        """Each link storage label the drawing may use, and the name it reads as (a case's own
        proposal is stored as `NAME__<proposal>`, never shown: rule 7)."""
        return await self.promotions._link_names(case_id, read)

    @staticmethod
    def _drawn_type(read: _Read, names: Mapping[str, str]) -> str:
        assert read.element is not None
        name = read.element.type
        return names.get(name, name) if read.item.kind == "link" else name

    async def _target_types(self, target: Dataset) -> list[TargetType]:
        """The target's live model: every type a drawn type may be mapped onto, as a Studio load's
        Map step maps onto the domain model (the owner's ruling; Amendment 7)."""
        boards = self.promotions.boards
        out: list[TargetType] = []
        for name in await boards.dataset_node_types(target.id):
            entity = boards.ontology.entity_type(name)
            if entity is not None:
                out.append(TargetType(
                    kind="node", name=name,
                    properties=list(dict.fromkeys(
                        [*entity.identifiers, *(p.name for p in entity.properties)])),
                    required=[p.name for p in entity.properties if p.required],
                ))  # fmt: skip
        for name in await boards.dataset_link_types(target.id):
            edge = boards.ontology.edge_type(name)
            if edge is not None:
                out.append(TargetType(
                    kind="link", name=name, properties=[p.name for p in edge.properties],
                    required=[p.name for p in edge.properties if p.required],
                ))  # fmt: skip
        return out

    def _chosen(
        self,
        reads: Sequence[_Read],
        names: Mapping[str, str],
        target: Dataset,
        target_types: Sequence[TargetType],
        choices: Sequence[TypeChoice],
    ) -> _Chosen:
        """Each drawn type the merger reads, and the type it goes in as with its properties'
        places: as chosen, else the same name when the target's model holds it, else none. A
        choice for a drawn type the merger does not read changes nothing (it tells nothing either).
        Refused whole (422) for a type outside the target's model or a property outside the
        chosen type: nothing is guessed."""
        offered: dict[tuple[str, str], TargetType] = {(t.kind, t.name): t for t in target_types}
        given: dict[tuple[str, str], TypeChoice] = {(c.kind, c.drawn_type): c for c in choices}
        drawn_props: dict[tuple[str, str], set[str]] = {}
        for read in reads:
            if read.item.kind in ("node", "link") and read.element is not None:
                key = (read.item.kind, self._drawn_type(read, names))
                drawn_props.setdefault(key, set()).update(read.element.properties)
        out: _Chosen = {}
        for pair in sorted(drawn_props):
            kind, drawn_type = pair
            choice = given.get(pair)
            to = choice.target_type if choice is not None else (
                drawn_type if pair in offered else None
            )  # fmt: skip
            if to is not None and (kind, to) not in offered:
                raise PromotionRefused(
                    "not_a_type",
                    f"{to} is not a {'link ' if kind == 'link' else ''}type of {target.name}'s "
                    "model: choose from Map again.",
                    status=422,
                )
            places: dict[str, str | None] = {}
            if to is not None and to != drawn_type:
                allowed = offered[(kind, to)].properties
                asked = {p.drawn_property: p.target_property for p in choice.properties} if (
                    choice is not None
                ) else {}  # fmt: skip
                for prop in sorted(drawn_props[pair]):
                    place = asked.get(prop, prop if prop in allowed else None)
                    if place is not None and place not in allowed:
                        raise PromotionRefused(
                            "not_a_property",
                            f"{to} has no property {place}: choose from Map again.",
                            status=422,
                        )
                    places[prop] = place
                taken = [v for v in places.values() if v is not None]
                if len(taken) != len(set(taken)):
                    raise PromotionRefused(
                        "not_a_property",
                        f"Two drawn properties go into one property of {to}: choose one.",
                        status=422,
                    )
            out[pair] = (to, places)
        return out

    def _as_types(
        self, reads: Sequence[_Read], names: Mapping[str, str], chosen: _Chosen
    ) -> dict[str, str | None]:
        """Each element mapped elsewhere than its own type: the type it goes in as, or `None`,
        left out at Map. One mapped to its own type is not listed (it goes as L3.4's promotion)."""
        out: dict[str, str | None] = {}
        for read in reads:
            if read.item.kind not in ("node", "link") or read.element is None:
                continue
            drawn_type = self._drawn_type(read, names)
            to, _ = chosen[(read.item.kind, drawn_type)]
            if to is None or to != drawn_type:
                out[read.element.id] = to
        return out

    @staticmethod
    def _carried(element: Node | Edge, places: Mapping[str, str | None]) -> dict[str, Any]:
        return {
            place: value
            for prop, value in element.properties.items()
            if (place := places.get(prop)) is not None
        }

    async def _retyped_problems(
        self,
        reads: Sequence[_Read],
        names: Mapping[str, str],
        chosen: _Chosen,
        as_types: Mapping[str, str | None],
        read: Principal,
    ) -> dict[str, list[tuple[str, str]]]:
        """What a copy would break (Amendment 7): its properties as mapped checked against its new
        type, as a load's are, and a link's ends against what its type joins."""
        ontology = self.promotions.boards.ontology
        out: dict[str, list[tuple[str, str]]] = {}
        node_type = {
            r.element.id: as_types.get(r.element.id) or r.element.type
            for r in reads if r.item.kind == "node" and r.element is not None
        }  # fmt: skip
        loaded = sorted({
            end for r in reads if r.item.kind == "link"
            for end in (r.item.source, r.item.target) if end and end not in node_type
        })  # fmt: skip
        if loaded:
            node_type |= {
                n.id: n.type for n in await self.promotions.boards.graph.get_nodes(loaded, read)
            }
        copied = {i for i, t in as_types.items() if t is not None}
        for r in reads:
            element = r.element
            if element is None or r.item.kind not in ("node", "link"):
                continue
            retyped = element.id in copied
            if (
                r.item.kind == "link"
                and not retyped
                and not ({r.item.source, r.item.target} & copied)
            ):
                continue
            if r.item.kind == "node" and not retyped:
                continue
            to = as_types.get(element.id) or self._drawn_type(r, names)
            _, places = chosen[(r.item.kind, self._drawn_type(r, names))]
            props = self._carried(element, places) if retyped else dict(element.properties)
            problems: list[tuple[str, str]] = []
            held = ontology.entity_type(to) if r.item.kind == "node" else ontology.edge_type(to)
            # Its properties checked when it is retyped (as a load's are): one kept as its own type
            # is the drawn item as it was drawn, and checked as drawing checked it.
            if held is not None and retyped:
                try:
                    validate_properties(held, props)
                except Exception as invalid:
                    problems.append(("types", f"Mapped onto {to}: {invalid}."))
            if isinstance(held, EdgeTypeDef):
                ends = (node_type.get(r.item.source or ""), node_type.get(r.item.target or ""))
                if not (
                    ends[0] and ends[1] and _accepts(held.from_types, ends[0])
                    and _accepts(held.to_types, ends[1])
                ):  # fmt: skip
                    problems.append((
                        "types",
                        f"A {to} link runs from {', '.join(held.from_types)} to "
                        f"{', '.join(held.to_types)}, not from {ends[0]} to {ends[1]}: map it "
                        "onto a link type that joins them.",
                    ))  # fmt: skip
            if problems:
                out[r.item.item_id] = problems
        return out

    async def _matches(
        self,
        reads: Sequence[_Read],
        drawn: Dataset,
        target: Dataset,
        reader: Principal,
        chosen: _Chosen,
        as_types: Mapping[str, str | None],
    ) -> tuple[list[tuple[Node, Node, float, str]], bool]:
        nodes: list[Node] = []
        for r in reads:
            if r.item.kind != "node" or not isinstance(r.element, Node):
                continue
            if r.element.id not in as_types:
                nodes.append(r.element)
            elif (to := as_types[r.element.id]) is not None:
                # A retyped node is looked for as what it goes in as (Amendment 7).
                _, places = chosen[("node", r.element.type)]
                nodes.append(r.element.model_copy(
                    update={"type": to, "properties": self._carried(r.element, places)}
                ))  # fmt: skip
        if not nodes:
            return [], False
        # Rule 3 and 7: candidates through the target alone, so nothing of another dataset, and
        # nothing the merger may not see, is ever a candidate.
        found = await self.promotions.boards.alike(
            nodes,
            reader.model_copy(update={"datasets": [target.id]}),
            self._read_as(reader, drawn, target),
        )
        by_id = {r.element.id: r.element for r in reads if isinstance(r.element, Node)}
        return [
            (by_id[s.drawn], s.loaded, s.score, s.why)
            for s in found.suggestions
            if s.drawn in by_id
        ], found.more

    @staticmethod
    def _mapping(
        reads: Sequence[_Read],
        names: Mapping[str, str],
        chosen: _Chosen,
        target: Dataset,
        target_types: Sequence[TargetType],
    ) -> list[TypeMapping]:
        counts: dict[tuple[str, str], int] = {}
        props: dict[tuple[str, str], set[str]] = {}
        for read in reads:
            if read.item.kind not in ("node", "link") or read.element is None:
                continue
            key = (read.item.kind, DrawnMerges._drawn_type(read, names))
            counts[key] = counts.get(key, 0) + 1
            props.setdefault(key, set()).update(read.element.properties)
        rows = []
        for (kind, name), n in sorted(counts.items()):
            to, _ = chosen[(kind, name)]
            rows.append(TypeMapping(
                kind=kind,  # type: ignore[arg-type]
                drawn_type=name, target_type=to, items=n,
                why_not=None if to is not None else (
                    f"{name} is not a {'link ' if kind == 'link' else ''}type of {target.name}'s "
                    f"model. Map it onto one of its types, or its items are left out and stay on "
                    f"the drawing; propose the type on {target.name}'s Model tab to merge them "
                    "later."
                ),
                choices=[t.name for t in target_types if t.kind == kind],
                drawn_properties=sorted(props[(kind, name)]),
            ))  # fmt: skip
        return rows

    async def sheet(
        self, drawn: Dataset, case_id: str, target: Dataset, reader: Principal
    ) -> DrawnMergeSheet:
        promotions = self.promotions
        read = self._read_as(reader, drawn, target)
        reads = await self._reads(drawn, case_id, read)
        names = await self._names(case_id, read)
        target_types = await self._target_types(target)
        chosen = self._chosen(reads, names, target, target_types, ())
        as_types = self._as_types(reads, names, chosen)
        problems = await promotions._problems(
            reads, target, case_id, read, into_its_own_dataset=False, as_types=as_types
        )
        matches, more = await self._matches(reads, drawn, target, reader, chosen, as_types)
        return DrawnMergeSheet(
            drawn_dataset_id=drawn.id, drawn_name=drawn.name, target_dataset_id=target.id,
            target_name=target.name, highest_marking=promotions.highest(target),
            policy=target.promotion_policy,
            mapping=self._mapping(reads, names, chosen, target, target_types),
            target_types=target_types,
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
    ) -> tuple[list[_Read], list[LeftOut], list[MergeMatchRow], list[CopyRow]]:  # fmt: skip
        """Every check again, here (the sheet may have been bypassed): the mapping, the items as a
        promotion's are planned, the copies of what is retyped, and each chosen match must be one
        offered now, of a drawn node that goes. Only what the merger reads is ever copied: every
        copy is built from an element read through them (the orchestrator's condition)."""
        promotions = self.promotions
        read = self._read_as(reader, drawn, target)
        reads = await self._reads(drawn, case_id, read)
        names = await self._names(case_id, read)
        chosen = self._chosen(reads, names, target, await self._target_types(target), body.mapping)
        as_types = self._as_types(reads, names, chosen)
        # Left out at Map, with its reason (the owner's ruling): never refused for it.
        unmapped = [
            r for r in reads if r.element is not None and r.element.id in as_types
            and as_types[r.element.id] is None
        ]  # fmt: skip
        gone = {r.item.item_id for r in unmapped}
        mapped = [r for r in reads if r.item.item_id not in gone]
        problems = await promotions._problems(
            mapped, target, case_id, read, into_its_own_dataset=False, as_types=as_types
        )
        for item_id, more in (
            await self._retyped_problems(mapped, names, chosen, as_types, read)
        ).items():
            problems[item_id] = [*problems[item_id], *more]
        ticked = [i for i in dict.fromkeys(body.item_ids) if i not in gone]
        goes, left = await promotions._plan(mapped, problems, ticked, target, read)
        left = [
            *(LeftOut(item_id=r.item.item_id, label=promotions._label(r),
                      why=f"Its type, {self._drawn_type(r, names)}, goes into no type of "
                          f"{target.name} (Map): it stays on the drawing, read-only.")
              for r in unmapped),
            *left,
        ]  # fmt: skip
        copied = {
            r.item.element_id for r in goes
            if r.item.kind == "node" and as_types.get(r.item.element_id) is not None
        }  # fmt: skip
        # A picture or a board's Same or Not the same on a retyped node is not carried: the
        # copy is another element, and its decision is made again there.
        kept: list[_Read] = []
        for r in goes:
            if r.item.kind in ("picture", "match") and ({r.item.source, r.item.target} & copied):
                left.append(LeftOut(
                    item_id=r.item.item_id, label=promotions._label(r),
                    why="Its drawn item goes in as another type, as a new item: "
                        + ("the picture stays on the drawing." if r.item.kind == "picture"
                           else "decide Same or Not the same again on the new item."),
                ))  # fmt: skip
            else:
                kept.append(r)
        goes = kept
        copies = [
            self._copy(r, names, chosen, as_types)
            for r in goes
            if r.item.element_id in copied
            or (r.item.kind == "link" and (
                as_types.get(r.item.element_id) is not None
                or {r.item.source, r.item.target} & copied
            ))
        ]  # fmt: skip
        going = {r.item.element_id for r in goes if r.item.kind == "node"}
        offered = {
            (d.id, n.id): score
            for d, n, score, _ in (
                await self._matches(mapped, drawn, target, reader, chosen, as_types)
            )[0]
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
        return goes, left, rows, copies

    def _copy(
        self,
        read: _Read,
        names: Mapping[str, str],
        chosen: _Chosen,
        as_types: Mapping[str, str | None],
    ) -> CopyRow:
        """A retyped item's copy, from its element as the merger read it: its handling its
        original's (never lower: the orchestrator's condition), its provenance its original's (it
        stays drawn, with its grading and source)."""
        element = read.element
        assert element is not None
        retyped = as_types.get(element.id)
        _, places = chosen[(read.item.kind, self._drawn_type(read, names))]
        return CopyRow(
            kind="node" if read.item.kind == "node" else "link",
            original=element.id,
            type=retyped or element.type,
            properties=json.dumps(
                self._carried(element, places) if retyped else element.properties,
                sort_keys=True,
                default=str,
            ),
            handling=element.handling.model_dump_json(),
            provenance=element.provenance.model_dump_json(),
            original_properties=json.dumps(element.properties, sort_keys=True, default=str),
            source=read.item.source if read.item.kind == "link" else None,
            target=read.item.target if read.item.kind == "link" else None,
        )

    async def dry_run(
        self, drawn: Dataset, case_id: str, target: Dataset, body: DrawnMergeInput,
        reader: Principal,
    ) -> DrawnMergeDryRun:  # fmt: skip
        """Step 3: nothing written, and only what the merger may see counted (an item above them
        is not read, so not counted, and not named in what is left out)."""
        goes, left, rows, copies = await self._plan(drawn, case_id, target, body, reader)
        return DrawnMergeDryRun(
            target_dataset_id=target.id,
            nodes=sum(1 for r in goes if r.item.kind == "node"),
            links=sum(1 for r in goes if r.item.kind != "node"),
            matches=len(rows), retyped=len(copies), left_out=left,
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
        goes, left, rows, copies = await self._plan(drawn, case_id, target, body, reader)
        markings = [Handling.model_validate_json(r.handling).classification for r in rows]
        # The record, its matches and its copies in one store write (the second review, item 13).
        record = await promotions._record(
            trigger="drawn_merge", case_id=case_id, board_id=None, dataset=target,
            layer_id=drawn.id, proposer=reader, goes=goes, left=left, extra_markings=markings,
            matches=rows, copies=copies,
        )  # fmt: skip
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
    _copies: dict[str, list[tuple[str, str | None]]] = field(default_factory=dict)

    @staticmethod
    def _inferred(record: PromotionRecord, about: str, score: float, now: datetime) -> Provenance:
        # Rule 5: proposed, never confirmed by the merge; a person confirms it.
        return Provenance(
            state=ProvenanceState.INFERRED,
            sources=[SourceRef(document_id=f"drawn-merge:{record.load_id}:{about}",
                               locator=record.proposed_by, excerpt_hash="")],
            first_seen=now,
            extraction_confidence=score,
        )  # fmt: skip

    async def writes(self, record: PromotionRecord, tx: Any) -> None:
        """In the load's own transaction: each retyped item written as a new element of its mapped
        type in the target (Amendment 7), each node's with an inferred `SAME_AS` back to its drawn
        original, in the drawn dataset, where both are read (rules 5 and 6); then the chosen
        matches, from a retyped node's copy."""
        copies = await self.promotions_store.copies_of(record.id)
        rows = await self.promotions_store.matches_of(record.id)
        if not copies and not rows:
            return
        now = datetime.now(UTC)
        nodes = [c for c in copies if c.kind == "node"]
        written_nodes = list(await self.graph.upsert_nodes(
            [
                NodeWrite(
                    id=new_id(), type=c.type, properties=json.loads(c.properties),
                    provenance=Provenance.model_validate_json(c.provenance),
                    handling=Handling.model_validate_json(c.handling),
                    created_by=record.proposed_by, created_at=now, load_id=record.load_id,
                    datasets=[record.dataset_id],
                )
                for c in nodes
            ],
            tx,
        )) if nodes else []  # fmt: skip
        copy_of = {c.original: w for c, w in zip(nodes, written_nodes)}
        links = [c for c in copies if c.kind == "link"]
        edges = (
            [
                EdgeWrite(
                    id=new_edge_id(),
                    type=c.type,
                    source=copy_of.get(c.source or "", c.source or ""),
                    target=copy_of.get(c.target or "", c.target or ""),
                    properties=json.loads(c.properties),
                    provenance=Provenance.model_validate_json(c.provenance),
                    handling=Handling.model_validate_json(c.handling),
                    created_by=record.proposed_by,
                    created_at=now,
                    load_id=record.load_id,
                    datasets=[record.dataset_id],
                )
                for c in links
            ]
            + [
                EdgeWrite(
                    id=new_edge_id(),
                    type=SAME_AS,
                    source=copy_of[c.original],
                    target=c.original,
                    properties={"score": 1.0, "model_version": RETYPE_MODEL_VERSION},
                    provenance=self._inferred(record, f"{c.original}:retyped", 1.0, now),
                    handling=Handling.model_validate_json(c.handling),
                    created_by=record.proposed_by,
                    created_at=now,
                    load_id=record.load_id,
                    # Where both its ends are: the copy is in the target, its original in the drawing.
                    datasets=[record.layer_id],
                )
                for c in nodes
            ]
            + [
                EdgeWrite(
                    id=new_edge_id(),
                    type=SAME_AS,
                    source=copy_of.get(r.drawn, r.drawn),
                    target=r.loaded,
                    properties={"score": r.score, "model_version": MATCH_MODEL_VERSION},
                    provenance=self._inferred(record, f"{r.drawn}:{r.loaded}", r.score, now),
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
        )
        written_edges = list(await self.graph.upsert_edges(edges, tx)) if edges else []
        link_ids = written_edges[: len(links)]
        same_as = written_edges[len(links) : len(links) + len(nodes)]
        by_copy = dict(zip([c.original for c in links], link_ids)) | {
            c.original: w for c, w in zip(nodes, written_nodes)
        }
        back = dict(zip([c.original for c in nodes], same_as))
        self._written[record.id] = written_edges[len(links) + len(nodes) :]
        self._copies[record.id] = [(by_copy[c.original], back.get(c.original)) for c in copies]

    async def recheck(self, record: PromotionRecord, reviewer: Principal) -> str | None:
        """At an approval, each match as the reviewer reads it now (the second review, item 1):
        `unseen` when they may not receive a match as it was chosen (its stored handling: its
        classification, a restricted code, the unit), so they may not approve and another reviewer
        may (403, it waits); `changed` when they may and it has moved since: an end gone from their
        read (withdrawn, raised, or out of the target), its marking moved, or the target's highest
        lowered below it (rejected, never left waiting); `None` otherwise."""
        rows = await self.promotions_store.matches_of(record.id)
        read = reviewer.model_copy(update={"datasets": [record.dataset_id, record.layer_id]})
        # Each retyped item's original as it was chosen (Amendment 7): one edited since (its
        # properties, its marking) would be copied as it no longer is.
        copies = await self.promotions_store.copies_of(record.id)
        if copies:
            node_ids = [c.original for c in copies if c.kind == "node"]
            edge_ids = [c.original for c in copies if c.kind == "link"]
            now: dict[str, Node | Edge] = {
                n.id: n for n in await self.graph.get_nodes(node_ids, read)
            }
            if edge_ids:
                now |= {e.id: e for e in await self.graph.get_edges(edge_ids, read)}
            for c in copies:
                held = now.get(c.original)
                if held is None:  # withdrawn or raised since (an unseen item is 403 before this)
                    return "changed"
                if held.handling != Handling.model_validate_json(c.handling) or json.loads(
                    json.dumps(held.properties, sort_keys=True, default=str)
                ) != json.loads(c.original_properties):
                    return "changed"
        if not rows:
            return None
        if not all(
            handling_readable(self.scheme, reviewer, Handling.model_validate_json(r.handling))
            for r in rows
        ):
            return "unseen"
        ids = sorted({x for r in rows for x in (r.drawn, r.loaded)})
        nodes = {n.id: n for n in await self.graph.get_nodes(ids, read)}
        if any(i not in nodes for i in ids):
            return "changed"
        held = (await self.datasets.egress_of([record.dataset_id])).get(record.dataset_id)
        highest = (held.highest_marking if held else None) or self.scheme.classification[-1]
        for r in rows:
            ends = (nodes[r.drawn].handling, nodes[r.loaded].handling)
            stricter = merge_handling(*ends, self.scheme)
            if stricter != Handling.model_validate_json(r.handling):
                return "changed"
            # (A loaded end read here is in the target: the read is the target and the drawing,
            # and a loaded node is in no drawing.)
            if not self.scheme.clears(highest, stricter.classification):
                return "changed"
        return None

    async def before_commit(self, record: PromotionRecord) -> None:
        """Before the graph commits: the matches' link ids recorded (so the revert can always find
        them), then the drawing's one merge claimed and its case moved onto the target, in one
        Postgres transaction (`merge_drawn`, refused for a second: `DrawnAlreadyMerged`). A
        failure here rolls the graph back, so nothing is half merged."""
        written = self._written.pop(record.id, [])
        if written:
            await self.promotions_store.set_match_edges(record.id, written)
        copies = self._copies.pop(record.id, [])
        if copies:
            await self.promotions_store.set_copy_ids(record.id, copies)
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
        here is logged, never raised past the committed load (its route still audits it), and
        leaves them boards: drawing on one goes into the case's layer (`Boards.into`), the
        drawing's own items are changed by no one (`Boards._own_item`) and promoted by no one
        (`Promotions._pending_items`)."""
        try:
            drawn: dict[str, list[str]] = {}
            for item in await self.items.in_case(record.case_id):
                if (
                    item.kind == "node"
                    and item.dataset_id == record.layer_id
                    and not item.withdrawn_at
                ):
                    drawn.setdefault(item.board_id, []).append(item.element_id)
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

    async def as_types(self, record: PromotionRecord) -> dict[str, str | None]:
        """Each retyped item's original and the type it goes in as, for the approval's checks."""
        return {c.original: c.type for c in await self.promotions_store.copies_of(record.id)}

    async def copies_shown(
        self, record: PromotionRecord, reviewer: Principal
    ) -> tuple[list[DetailItem], bool]:
        """A reviewer's *Details* of the retyped items, each read through their own handling:
        while it waits, the original ("goes in as"), in the drawing and the target; once committed,
        the copy, in the target alone; afterwards nothing (rule 3)."""
        copies = await self.promotions_store.copies_of(record.id)
        if not copies or record.status not in ("awaiting_review", "committed"):
            return [], False
        waiting = record.status == "awaiting_review"
        read = reviewer.model_copy(update={
            "datasets": [record.dataset_id, record.layer_id] if waiting else [record.dataset_id]
        })  # fmt: skip
        ids = [(c, c.original if waiting else c.written_id) for c in copies]
        node_ids = [i for c, i in ids if c.kind == "node" and i]
        edge_ids = [i for c, i in ids if c.kind == "link" and i]
        nodes = await self.graph.get_nodes(node_ids, read) if node_ids else []
        edges = await self.graph.get_edges(edge_ids, read) if edge_ids else []
        as_type = {i: c.type for c, i in ids if i}
        shown = [
            _detail(n, "node").model_copy(update={"goes_in_as": as_type[n.id] if waiting else None})
            for n in nodes
        ] + [
            _detail(e, _kind(e)).model_copy(
                update={"goes_in_as": as_type[e.id] if waiting else None}
            )
            for e in edges
        ]
        return shown, len(shown) != len(copies)

    async def undo_writes(self, record: PromotionRecord, tx: Any) -> None:
        """The revert's: the merge's matches, its copies and their `SAME_AS` withdrawn with it
        (never deleted), as a load's are."""
        edges = [r.edge_id for r in await self.promotions_store.matches_of(record.id) if r.edge_id]
        copies = await self.promotions_store.copies_of(record.id)
        nodes = [c.written_id for c in copies if c.kind == "node" and c.written_id]
        edges += [c.written_id for c in copies if c.kind == "link" and c.written_id]
        edges += [c.same_as_id for c in copies if c.same_as_id]
        if nodes or edges:
            await self.graph.withdraw_elements(nodes, edges, record.load_id, tx)

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


__all__: Sequence[str] = (
    "DrawnMerges",
    "MergeCommit",
    "view_annotations",
    "MATCH_MODEL_VERSION",
    "RETYPE_MODEL_VERSION",
)
