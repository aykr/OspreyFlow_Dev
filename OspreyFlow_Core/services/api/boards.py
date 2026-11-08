"""Drawing boards (ADR-143 decisions 4 to 7; Amendments 2 and 3; spec 03 §3.1c; L3.3).

A board is a case view with drawing switched on (`case_views.py`). What is drawn on it is data: a
node or link written into the graph with an `analyst_drawn` provenance (`Provenance.drawn`), into
the case's **analyst layer** (`dataset_scope.analyst_writes_into`), or, for a case that began as a
drawing, into its **drawn dataset** (Amendment 3 decision 1), and never into a source. The board's
item registry (`board_store.py`) holds ids alone.

**Rule 3.** Every read goes through the reader's own principal, already scoped by `get_principal`
to the case's read set, so the adapter filters each element by marking and dataset: another case's
layer is never in that set, and an element the reader may not see is absent exactly as one that
does not exist. The registry is read by case, so another case's board or item is not found. The
routes stand behind the case's own level check first.

**What each refusal says.** A refusal names the rule it keeps, in words: the case's marking
ceiling (Amendment 2 decision 3), the reader's own clearance, a type not in the case's model (C14),
a link's ends not on the board, an item that is not the reader's own (decision 5).

**Matching never merges** (decision 6; rule 6): *Same* writes one `SAME_AS` (score 1.0) into the
layer and *Not the same* one `NOT_SAME_AS`; neither node is changed. A suggestion is `inferred` and
does nothing by itself (rule 5).

**Withdrawing never deletes** (decision 5): the element is taken out of every read as a reverted
element is (`withdraw_elements`, under the board's own id for the withdrawal) and stays in the store
and the audit. A drawn link touching a withdrawn node goes with it; the watch ends.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Protocol

from adapters.media_objectstore import content_type_of, reference_for
from conduit_common.identity import new_edge_id, new_id
from ontology.handling import HandlingScheme, merge_handling
from ontology.validation import validate_properties
from ports.graph import GraphPort, SuggestOptions
from ports.media import MediaStore
from schemas.boards import (
    Board,
    BoardInput,
    BoardOpened,
    DrawnItemEdit,
    DrawnItemInput,
    DrawnItemMade,
    DrawnLinkInput,
    MatchDecision,
    MatchSuggestion,
    MatchSuggestions,
    PictureChoice,
    Withdrawn,
)
from schemas.case_views import NodePosition
from schemas.domain import (
    NOT_SAME_AS,
    SAME_AS,
    DrawnAssertion,
    Edge,
    EdgeWrite,
    Grading,
    Handling,
    Node,
    NodeId,
    NodeWrite,
    OntologySchema,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

from .board_store import BoardItem, BoardItemStore, new_item, new_watch
from .case_views import CaseViewStore, StoredCaseView, ViewNotFound
from .dataset_scope import analyst_writes_into
from .datasets import DRAWN, DatasetStore
from .document_content import DOCUMENT_TYPE
from .entity_pictures import DEPICTS, PICTURE_TYPES  # ADR-105's own names and formats
from .evidence_brief import display_name
from .working_set.models import LimitExceededError

#: Never drawn on a board: what the platform itself raises or holds as evidence.
_NOT_DRAWN_NODE_TYPES = frozenset({"Alert", DOCUMENT_TYPE})
_NOT_DRAWN_LINK_TYPES = frozenset({SAME_AS, NOT_SAME_AS, DEPICTS, "ALERTED_ON", "MENTIONED_IN"})
#: How alike a drawn name and a loaded one must be to be offered (decision 6).
MATCH_AT = 0.75
#: The most suggestions answered at once; past it `more` is set (rule 2).
MATCH_LIMIT = 20
#: The withdrawal's own id on a withdrawn element (`withdraw_elements`'s `load_id`).
WITHDRAWAL_PREFIX = "board-withdrawal:"


class BoardNotFound(Exception):
    """No board by that id in the case that the reader may see (absent, another's private board,
    another case's, or a view that is not a board), alike."""


class DrawingRefused(Exception):
    """A drawing refused in words, before anything is written."""

    def __init__(self, code: str, message: str, *, status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class NotTheBoardsCreator(Exception):
    """A shared board the reader can see but did not make: only its creator draws on it."""


class ItemNotFound(Exception):
    """No drawn item by that id in the case that the reader may see."""


@dataclass(frozen=True)
class Into:
    """Where a case's drawing is written, and the ceiling on it."""

    dataset_id: str
    ceiling: str
    #: The case's dataset a drawn item's watch is set on (Amendment 2 decision 8).
    watched: str | None
    drawn_dataset: bool


class _Models(Protocol):
    async def live(self, dataset_id: str) -> Any: ...


class _Projection(Protocol):
    async def filtered_view(self, case_id: str, principal: Principal, keeps: Any) -> Any: ...


@dataclass
class Boards:
    """The board service, built per request from the app's stores."""

    graph: GraphPort
    views: CaseViewStore
    items: BoardItemStore
    datasets: DatasetStore
    ontology: OntologySchema
    scheme: HandlingScheme
    models: _Models | None = None
    media: MediaStore | None = None
    cap_breach: Callable[[int, int], Any] | None = None

    # --- where drawing goes ---------------------------------------------------------------

    def _top(self) -> str:
        return self.scheme.classification[-1]

    def _strictest(self, markings: Sequence[str]) -> str:
        ranked = [m for m in markings if m in self.scheme.classification]
        if not ranked:
            return self._top()
        return min(ranked, key=self.scheme.classification.index)

    async def ceiling(self, case_id: str) -> str:
        """Amendment 2 decision 3: nothing in a case's layer above its dataset's highest allowed
        marking (the strictest of those it reads; the deployment's highest where none is set)."""
        chosen = await self.datasets.chosen_of_case(case_id)
        return self._strictest([d.highest_marking for d in chosen if d.highest_marking])

    async def into(self, case_id: str) -> Into:
        """The case's drawn dataset when it began as a drawing (Amendment 3 decision 1); otherwise
        its analyst layer, made by the writer if the case has none yet (ADR-143 Amendment 1). Only
        ever called inside a route, after its level check."""
        chosen = await self.datasets.chosen_of_case(case_id)
        ceiling = self._strictest([d.highest_marking for d in chosen if d.highest_marking])
        if chosen and chosen[0].kind == DRAWN:
            return Into(chosen[0].id, ceiling, chosen[0].id, drawn_dataset=True)
        layer = (await analyst_writes_into())[0]
        return Into(layer, ceiling, chosen[0].id if chosen else None, drawn_dataset=False)

    def check_marking(self, marking: str, ceiling: str, principal: Principal) -> None:
        if marking not in self.scheme.classification:
            raise DrawingRefused(
                "not_a_marking", f"{marking} is not a marking of this deployment", status=422
            )
        if not self.scheme.clears(ceiling, marking):
            raise DrawingRefused(
                "above_the_ceiling",
                f"{marking} is above this case's ceiling, {ceiling}: nothing drawn in this case "
                f"may be marked above {ceiling}",
            )
        if not self.scheme.clears(principal.clearance, marking):
            raise DrawingRefused(
                "above_your_clearance",
                f"{marking} is above your own clearance, {principal.clearance}",
            )

    def _handling(self, marking: str, principal: Principal) -> Handling:
        code = next(
            (c for c, h in self.scheme.handling_codes.items() if h.dissemination == "permitted"),
            next(iter(self.scheme.handling_codes)),
        )
        return Handling(
            classification=marking,
            handling_code=code,
            originator=principal.org_unit,
            owning_unit=principal.org_unit,
        )

    # --- what may be drawn ----------------------------------------------------------------

    async def node_types(self, case_id: str) -> list[str]:
        """C14: a board's node types come only from the case's model: the core and the live
        model's packs; the deployment's whole ontology while the case's dataset has no model yet."""
        packs: set[str] | None = None
        if self.models is not None:
            chosen = await self.datasets.chosen_of_case(case_id)
            if chosen:
                live = await self.models.live(chosen[0].id)
                if live is not None:
                    packs = set(live.packs)
        names = []
        for t in self.ontology.entity_types:
            if t.name in _NOT_DRAWN_NODE_TYPES:
                continue
            pack = self.ontology.type_packs.get(t.name)
            if packs is not None and pack is not None and pack not in packs:
                continue
            names.append(t.name)
        return sorted(names)

    def link_types(self) -> list[str]:
        return sorted(
            e.name
            for e in self.ontology.edge_types
            if not e.system and e.name not in _NOT_DRAWN_LINK_TYPES
        )

    def markings_up_to(self, ceiling: str, principal: Principal) -> list[str]:
        return [
            m
            for m in self.scheme.classification
            if self.scheme.clears(ceiling, m) and self.scheme.clears(principal.clearance, m)
        ]

    # --- boards ---------------------------------------------------------------------------

    async def board(self, case_id: str, board_id: str, reader: str) -> StoredCaseView:
        try:
            held = await self.views.get(case_id, board_id, reader)
        except ViewNotFound as missing:
            raise BoardNotFound(board_id) from missing
        if not held.drawing:
            raise BoardNotFound(board_id)
        return held

    async def own_board(self, case_id: str, board_id: str, reader: str) -> StoredCaseView:
        """A board the reader made: only its creator draws on it, moves its items or adds to it
        (ADR-143 decision 5; the lane's decision, logged)."""
        held = await self.board(case_id, board_id, reader)
        if held.created_by != reader:
            raise NotTheBoardsCreator(board_id)
        return held

    async def wire(self, board: StoredCaseView, principal: Principal) -> Board:
        live = [
            i for i in await self.items.on_board(board.case_id, board.id) if i.withdrawn_at is None
        ]
        drawn_nodes = [i.element_id for i in live if i.kind == "node"]
        seen = await self.graph.get_nodes(drawn_nodes, principal) if drawn_nodes else []
        return Board(
            id=board.id,
            case_id=board.case_id,
            name=board.name,
            created_by=board.created_by,
            created_at=board.created_at,
            shared=board.shared,
            drawn=len(seen),
            start="blank" if not board.node_ids else "selection",
        )

    async def make(
        self,
        case_id: str,
        given: BoardInput,
        principal: Principal,
        *,
        projection: _Projection | None = None,
    ) -> StoredCaseView:
        """*New drawing board*: blank, from a view the reader may see (its loaded items now, as
        live references), or from a selection (only the nodes the reader may see are kept)."""
        wanted: list[NodeId] = []
        if given.start == "view":
            assert given.view_id is not None
            view = await self.views.get(case_id, given.view_id, principal.id)
            if view.node_ids is not None:
                wanted = list(view.node_ids)
            elif view.filter is not None and projection is not None:
                nodes, _ = await projection.filtered_view(case_id, principal, view.filter)
                wanted = [n.id for n in nodes]
        elif given.start == "selection":
            wanted = list(given.node_ids or [])
        seen = await self.graph.get_nodes(wanted, principal) if wanted else []
        # Drawn items selected come too, as references: a deleted board's items stay reachable.
        kept = [n.id for n in seen]
        return await self.views.save_board(case_id, given.name, principal.id, node_ids=kept)

    async def open(self, board: StoredCaseView, principal: Principal) -> BoardOpened:
        """The board now, as `principal` may see it: its live drawn items and its references."""
        live = [
            i for i in await self.items.on_board(board.case_id, board.id) if i.withdrawn_at is None
        ]
        drawn_nodes = [i.element_id for i in live if i.kind == "node"]
        drawn_links = {i.element_id for i in live if i.kind == "link"}
        wanted = list(dict.fromkeys([*(board.node_ids or []), *drawn_nodes]))
        nodes = await self.graph.get_nodes(wanted, principal) if wanted else []
        shown = [n.id for n in nodes]
        edges = await self.graph.edges_among(shown, principal) if len(shown) > 1 else []
        edges = [e for e in edges if e.type not in (DEPICTS,)]
        missing = len(wanted) - len(nodes) + len(drawn_links - {e.id for e in edges})
        if self.cap_breach is not None:
            breach = self.cap_breach(len(nodes), len(edges))
            if breach is not None:
                raise LimitExceededError(breach)
        drawn = [n.id for n in nodes if n.provenance.drawn is not None] + [
            e.id for e in edges if e.provenance.drawn is not None
        ]
        by_element = {i.element_id: i.item_id for i in live}
        items = {element: by_element[element] for element in drawn if element in by_element}
        # A drawn element made on another board of the case keeps its own item id.
        elements: list[Node | Edge] = [*nodes, *edges]
        for held in elements:
            if held.id not in items and held.provenance.drawn is not None:
                items[held.id] = held.provenance.drawn.item_id
        ceiling = await self.ceiling(board.case_id)
        return BoardOpened(
            board=await self.wire(board, principal),
            nodes=nodes,
            edges=edges,
            drawn=drawn,
            items=items,
            layout={k: v.model_dump() for k, v in board.layout.items() if k in set(shown)},
            missing=max(missing, 0),
            node_types=await self.node_types(board.case_id),
            link_types=self.link_types(),
            markings=self.markings_up_to(ceiling, principal),
            ceiling=ceiling,
            may_draw=board.created_by == principal.id,
        )

    # --- drawing --------------------------------------------------------------------------

    def _provenance(
        self, item_id: str, board: StoredCaseView, principal: Principal, given: Any, **extra: Any
    ) -> Provenance:
        drawn = DrawnAssertion(
            item_id=item_id,
            asserted_by=principal.id,
            board_id=board.id,
            case_id=board.case_id,
            label=given.label,
            grading=given.grading,
            source_note=given.source_note,
            source_document=given.source_document,
            **extra,
        )
        return Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[
                SourceRef(
                    document_id=given.source_document or f"drawn:{item_id}",
                    locator=f"board {board.id}",
                    excerpt_hash="",
                )
            ],
            first_seen=datetime.now(UTC),
            drawn=drawn,
        )

    async def _write(
        self, nodes: Sequence[NodeWrite], edges: Sequence[EdgeWrite]
    ) -> tuple[list[str], list[str]]:
        tx = await self.graph.begin_transaction()
        try:
            node_ids = list(await self.graph.upsert_nodes(nodes, tx)) if nodes else []
            edge_ids = list(await self.graph.upsert_edges(edges, tx)) if edges else []
        except Exception:
            await self.graph.rollback_transaction(tx)
            raise
        await self.graph.commit_transaction(tx)
        return node_ids, edge_ids

    async def _source_document_check(self, document_id: str | None, principal: Principal) -> None:
        """A source document must be one the reader may see in the case (decision 4)."""
        if document_id is None:
            return
        found = await self.graph.get_nodes([document_id], principal)
        if not found or found[0].type != DOCUMENT_TYPE:
            raise DrawingRefused(
                "no_such_document", "that document is not one this case holds", status=422
            )

    async def declare(
        self, board: StoredCaseView, given: DrawnItemInput, principal: Principal
    ) -> DrawnItemMade:
        """*Add to board*: a node, marked, graded and sourced, into the case's layer (or drawn
        dataset), with its watch set (Amendment 2 decision 8)."""
        if given.type not in await self.node_types(board.case_id):
            raise DrawingRefused(
                "not_in_the_model",
                f"{given.type} is not a type of this case's model: ask a data engineer to add it",
                status=422,
            )
        entity = self.ontology.entity_type(given.type)
        assert entity is not None
        try:
            validate_properties(entity, given.properties)
        except Exception as invalid:
            raise DrawingRefused("not_a_property", str(invalid), status=422) from invalid
        # The ceiling first: a refused drawing makes nothing, not even the case's layer.
        self.check_marking(given.marking, await self.ceiling(board.case_id), principal)
        await self._source_document_check(given.source_document, principal)
        into = await self.into(board.case_id)
        item_id = new_id()
        now = datetime.now(UTC)
        write = NodeWrite(
            id=new_id(),
            type=given.type,
            properties=dict(given.properties),
            provenance=self._provenance(item_id, board, principal, given, icon=given.icon),
            handling=self._handling(given.marking, principal),
            created_by=principal.id,
            created_at=now,
            datasets=[into.dataset_id],
        )
        (node_id,), _ = await self._write([write], [])
        item = new_item(
            board_id=board.id, case_id=board.case_id, kind="node", element_id=node_id,
            author=principal.id, dataset_id=into.dataset_id, item_id=item_id,
        )  # fmt: skip
        watch = new_watch(item, dataset_id=into.watched)
        await self.items.add(item, watch)
        await self.views.update_board(
            board.case_id, board.id, principal.id,
            layout={node_id: NodePosition(x=given.x, y=given.y)},
        )  # fmt: skip
        return DrawnItemMade(element_id=node_id, item_id=item_id, watch_id=watch.id)

    async def link(
        self, board: StoredCaseView, given: DrawnLinkInput, principal: Principal
    ) -> DrawnItemMade:
        """A drawn link between two items on the board the reader may see, drawn or loaded. The
        link lives in the layer; a loaded end stays in its dataset untouched (decision 2)."""
        if given.type not in self.link_types():
            raise DrawingRefused(
                "not_in_the_model", f"{given.type} is not a link type of this case's model",
                status=422,
            )  # fmt: skip
        if given.source == given.target:
            raise DrawingRefused("same_item", "a link joins two different items", status=422)
        on_board = set(board.node_ids or []) | {
            i.element_id
            for i in await self.items.on_board(board.case_id, board.id)
            if i.kind == "node" and i.withdrawn_at is None
        }
        ends = await self.graph.get_nodes([given.source, given.target], principal)
        if len(ends) != 2 or given.source not in on_board or given.target not in on_board:
            raise DrawingRefused(
                "ends_not_on_the_board", "both ends of a link must be items on this board",
                status=422,
            )  # fmt: skip
        by_id = {n.id: n for n in ends}
        edge_type = self.ontology.edge_type(given.type)
        assert edge_type is not None
        source_type, target_type = by_id[given.source].type, by_id[given.target].type
        if not _accepts(edge_type.from_types, source_type) or not _accepts(
            edge_type.to_types, target_type
        ):
            raise DrawingRefused(
                "wrong_ends",
                f"a {given.type} link runs from {', '.join(edge_type.from_types)} to "
                f"{', '.join(edge_type.to_types)}, not from {source_type} to {target_type}",
                status=422,
            )
        self.check_marking(given.marking, await self.ceiling(board.case_id), principal)
        await self._source_document_check(given.source_document, principal)
        already = await self.graph.edges_among(
            [given.source, given.target], principal, edge_types=[given.type]
        )
        if any(
            e.provenance.drawn is not None and {e.source, e.target} == {given.source, given.target}
            for e in already
        ):
            raise DrawingRefused(
                "already_drawn", f"a {given.type} link is already drawn between these two items"
            )
        into = await self.into(board.case_id)
        item_id = new_id()
        write = EdgeWrite(
            id=new_edge_id(),
            type=given.type,
            source=given.source,
            target=given.target,
            provenance=self._provenance(item_id, board, principal, given),
            handling=self._handling(given.marking, principal),
            created_by=principal.id,
            created_at=datetime.now(UTC),
            datasets=[into.dataset_id],
        )
        _, (edge_id,) = await self._write([], [write])
        item = new_item(
            board_id=board.id, case_id=board.case_id, kind="link", element_id=edge_id,
            author=principal.id, dataset_id=into.dataset_id, item_id=item_id,
            source=given.source, target=given.target,
        )  # fmt: skip
        watch = new_watch(item, dataset_id=into.watched)
        await self.items.add(item, watch)
        return DrawnItemMade(element_id=edge_id, item_id=item_id, watch_id=watch.id)

    async def move(
        self, board: StoredCaseView, positions: dict[NodeId, dict[str, float]], principal: Principal
    ) -> None:
        """The board's own layout, for items on it the reader may see."""
        held = set(board.node_ids or []) | {
            i.element_id for i in await self.items.on_board(board.case_id, board.id)
        }
        wanted = [k for k in positions if k in held]
        seen = {n.id for n in await self.graph.get_nodes(wanted, principal)} if wanted else set()
        layout = {
            k: NodePosition(x=float(v.get("x", 0.0)), y=float(v.get("y", 0.0)))
            for k, v in positions.items()
            if k in seen
        }
        await self.views.update_board(board.case_id, board.id, principal.id, layout=layout)

    async def _own_item(
        self, case_id: str, item_id: str, principal: Principal
    ) -> tuple[BoardItem, Node | Edge]:
        item = await self.items.get(case_id, item_id)
        if item is None or item.withdrawn_at is not None:
            raise ItemNotFound(item_id)
        found: Sequence[Node | Edge]
        if item.kind == "node":
            found = await self.graph.get_nodes([item.element_id], principal)
        else:
            found = await self.graph.get_edges([item.element_id], principal)
        element = found[0] if found else None
        if element is None:
            raise ItemNotFound(item_id)
        if item.author != principal.id:
            raise DrawingRefused(
                "not_your_item", "only the person who drew an item edits or withdraws it",
                status=403,
            )  # fmt: skip
        if set(element.datasets) != {item.dataset_id}:
            raise DrawingRefused(
                "promoted",
                "this item has been promoted into a dataset: it is changed only by reverting "
                "its promotion",
            )
        return item, element

    async def edit(
        self, case_id: str, item_id: str, given: DrawnItemEdit, principal: Principal
    ) -> DrawnItemMade:
        """The author changes their own item, in place (same id; the revision rises and the audit
        holds the change). A marking is never lowered: the store would keep the higher one, so
        the request is refused rather than half done."""
        item, element = await self._own_item(case_id, item_id, principal)
        drawn = element.provenance.drawn
        assert drawn is not None
        marking = given.marking or element.handling.classification
        order = self.scheme.classification
        if marking not in order:
            raise DrawingRefused(
                "not_a_marking", f"{marking} is not a marking of this deployment", status=422
            )
        if not isinstance(element, Node) and marking != element.handling.classification:
            # A link's marking is part of who may see it (ADR-102): written again at another
            # marking it would be a second link, the first left live. Refused, not half done.
            raise DrawingRefused(
                "link_marking_kept",
                "a drawn link's marking is not changed: withdraw it and draw it again at the "
                "marking it needs",
            )
        if order.index(marking) < order.index(element.handling.classification):
            raise DrawingRefused(
                "marking_never_lowered",
                f"a drawn item's marking is never lowered, from {element.handling.classification}: "
                "withdraw it and draw it again",
            )
        self.check_marking(marking, await self.ceiling(case_id), principal)
        await self._source_document_check(given.source_document, principal)
        new_drawn = drawn.model_copy(
            update={
                k: v
                for k, v in {
                    "label": given.label,
                    "grading": given.grading,
                    "source_note": given.source_note,
                    "source_document": given.source_document,
                    "icon": given.icon,
                }.items()
                if v is not None
            }
        )
        try:
            DrawnAssertion.model_validate(new_drawn.model_dump())  # a source is still given
        except ValueError as invalid:
            raise DrawingRefused(
                "no_source",
                "a drawn item needs a source note, a document of the case, or both",
                status=422,
            ) from invalid
        provenance = element.provenance.model_copy(update={"drawn": new_drawn})
        handling = element.handling.model_copy(update={"classification": marking})
        now = datetime.now(UTC)
        if isinstance(element, Node):
            properties = given.properties if given.properties is not None else element.properties
            entity = self.ontology.entity_type(element.type)
            assert entity is not None
            try:
                validate_properties(entity, properties)
            except Exception as invalid:
                raise DrawingRefused("not_a_property", str(invalid), status=422) from invalid
            await self._write(
                [NodeWrite(
                    id=element.id, type=element.type, properties=properties,
                    provenance=provenance, handling=handling, created_by=principal.id,
                    created_at=now, datasets=[item.dataset_id],
                )],
                [],
            )  # fmt: skip
        else:
            # A link's second write of the same pair and audience merges into it (ADR-102), so
            # its body is the latest write's: the edit lands on the same link.
            await self._write(
                [],
                [EdgeWrite(
                    id=element.id, type=element.type, source=element.source,
                    target=element.target, properties=element.properties,
                    provenance=provenance, handling=handling, created_by=principal.id,
                    created_at=now, datasets=[item.dataset_id],
                )],
            )  # fmt: skip
        return DrawnItemMade(element_id=element.id, item_id=item.item_id)

    async def withdraw(
        self,
        case_id: str,
        item_id: str,
        principal: Principal,
        *,
        before_write: Callable[[list[str], list[str]], Awaitable[None]] | None = None,
    ) -> Withdrawn:
        """Decision 5: the author's own item taken out of every read, never deleted. A drawn link
        touching a withdrawn node goes with it, as does a picture of it; its watch ends.

        Rule 3: what the reader may not see goes too, but is told to them in nothing: not named,
        not counted among the links, the pictures or the watches ended. `before_write` is given
        every node and link withdrawn, seen or not, and is called after every refusal and before
        anything is written, so the audit names all of it (ADR-127 Amendment 23's order)."""
        item, element = await self._own_item(case_id, item_id, principal)
        case_items = [i for i in await self.items.in_case(case_id) if i.withdrawn_at is None]
        nodes: list[str] = []
        links: list[str] = []
        withdrawn_items = [item.item_id]
        if item.kind == "node":
            nodes.append(item.element_id)
            for other in case_items:
                if other.kind in ("link", "picture") and item.element_id in (
                    other.source,
                    other.target,
                ):
                    links.append(other.element_id)
                    withdrawn_items.append(other.item_id)
        else:
            links.append(item.element_id)
        # Rule 3 over rule 2: a link the reader may not see is withdrawn with its node, but is not
        # named to them. Read before the withdrawal, which takes every one out of every read.
        seen_links = await self.graph.get_edges(links, principal) if links else []
        seen = {e.id for e in seen_links}
        pictures = {i.element_id for i in case_items if i.kind == "picture"}
        # Each link going with the node is wholly drawn data still: one promoted into a dataset
        # (L3.4) is changed only by reverting its promotion, so the withdrawal is refused.
        held_in = {i.element_id: i.dataset_id for i in case_items}
        # One the reader may not see is not read here (an unfiltered read is confined away from
        # routes): L3.4 records a promotion in the board's registry, so that its check reads the
        # registry, never the element, and refuses in the same words for both.
        if any(set(e.datasets) != {held_in.get(e.id, item.dataset_id)} for e in seen_links):
            raise DrawingRefused(
                "promoted",
                "a link drawn to this item has been promoted into a dataset: revert that "
                "promotion before withdrawing the item",
            )
        told = {item.item_id} | {
            i.item_id for i in case_items if i.element_id in seen and i.item_id in withdrawn_items
        }
        watched = {
            w.item_id for w in await self.items.active_watches(case_id) if w.item_id in told
        }
        if before_write is not None:
            await before_write(nodes, links)
        # Through the graph's own path for a drawn element (`withdraw_drawn`, on the dataset
        # stamping graph every route's service holds): it refuses in a case not yet converted, and
        # clears what was kept from reads after it, as every write does. No other path is taken.
        tx = await self.graph.begin_transaction()
        try:
            await self.graph.withdraw_drawn(  # type: ignore[attr-defined]
                nodes, links, f"{WITHDRAWAL_PREFIX}{item.item_id}", tx
            )
        except Exception:
            await self.graph.rollback_transaction(tx)
            raise
        await self.graph.commit_transaction(tx)
        await self.items.withdraw(case_id, withdrawn_items, principal.id, datetime.now(UTC))
        named = [link for link in links if link == item.element_id or link in seen]
        return Withdrawn(
            nodes=nodes,
            links=[link for link in named if link not in pictures],
            pictures=[link for link in named if link in pictures],
            watches_ended=len(watched),
        )

    # --- matching -------------------------------------------------------------------------

    async def suggestions(self, board: StoredCaseView, principal: Principal) -> MatchSuggestions:
        """*Looks like a loaded item* (decision 6): for each drawn node on the board, loaded nodes
        of its type the reader may see, by an identifier equal or a name alike. `inferred`."""
        live = [
            i for i in await self.items.on_board(board.case_id, board.id)
            if i.kind == "node" and i.withdrawn_at is None
        ]  # fmt: skip
        drawn_nodes = await self.graph.get_nodes([i.element_id for i in live], principal)
        found: list[MatchSuggestion] = []
        more = False
        for drawn in drawn_nodes:
            assert drawn.provenance.drawn is not None
            candidates: dict[str, tuple[Node, float, str]] = {}
            entity = self.ontology.entity_type(drawn.type)
            for key in entity.identifiers if entity is not None else []:
                value = drawn.properties.get(key)
                if isinstance(value, str) and value.strip():
                    hits_by_key = await self.graph.search_nodes(value, principal, limit=MATCH_LIMIT)
                    more = more or len(hits_by_key) >= MATCH_LIMIT
                    for hit in hits_by_key:
                        # Search also matches other indexed properties: the same key, or no hit.
                        if hit.type == drawn.type and hit.properties.get(key) == value:
                            candidates[hit.id] = (hit, 1.0, f"the same {key}")
            label = drawn.provenance.drawn.label
            word = _longest_word(label)
            if word is not None:
                # `word` is never empty, the one thing `suggest_nodes` refuses: nothing is caught.
                hits = await self.graph.suggest_nodes(
                    word, principal, limit=MATCH_LIMIT,
                    options=SuggestOptions(mode="contains", ignore_case=True,
                                           types=(drawn.type,)),
                )  # fmt: skip
                more = more or hits.more
                for hit in hits.nodes:
                    score = _alike(label, display_name(hit))
                    if score >= MATCH_AT and hit.id not in candidates:
                        candidates[hit.id] = (hit, round(score, 2), "a name alike")
            loaded = [
                c for c in candidates.values()
                if c[0].provenance.drawn is None and c[0].id != drawn.id
            ]  # fmt: skip
            if not loaded:
                continue
            decided = await self.graph.edges_among(
                [drawn.id, *[c[0].id for c in loaded]], principal, edge_types=[SAME_AS, NOT_SAME_AS]
            )
            settled = {
                e.target if e.source == drawn.id else e.source
                for e in decided
                if drawn.id in (e.source, e.target)
            }
            for node, score, why in sorted(loaded, key=lambda c: (-c[1], c[0].id)):
                if node.id in settled:
                    continue
                found.append(MatchSuggestion(drawn=drawn.id, loaded=node, score=score, why=why))
        if len(found) > MATCH_LIMIT:
            found, more = found[:MATCH_LIMIT], True
        return MatchSuggestions(suggestions=found, more=more)

    async def decide(
        self, board: StoredCaseView, given: MatchDecision, principal: Principal
    ) -> str:
        """*Same* or *Not the same*: one link into the layer, neither node changed (rule 6)."""
        item = await self.items.by_element(board.case_id, given.drawn)
        # A drawn item of this board only: another member's private board is not reached from here.
        if (
            item is None
            or item.withdrawn_at is not None
            or item.kind != "node"
            or item.board_id != board.id
        ):
            raise ItemNotFound(given.drawn)
        found = {
            n.id: n for n in await self.graph.get_nodes([given.drawn, given.loaded], principal)
        }
        drawn, loaded = found.get(given.drawn), found.get(given.loaded)
        if drawn is None or loaded is None or loaded.provenance.drawn is not None:
            raise ItemNotFound(given.loaded)
        # Marked as both ends together (`merge_handling`: the higher marking, the stricter code),
        # and within the case's ceiling, like any drawing (Amendment 2 decision 3).
        stricter = merge_handling(drawn.handling, loaded.handling, self.scheme)
        self.check_marking(stricter.classification, await self.ceiling(board.case_id), principal)
        into = await self.into(board.case_id)
        nodes, edges = match_writes(
            drawn, loaded, same=given.same, into=into.dataset_id, principal=principal,
            stricter=stricter,
        )  # fmt: skip
        _, ids = await self._write(nodes, edges)
        return ids[0]

    # --- pictures (C17; ADR-105 Amendment 3) ----------------------------------------------

    async def _picture_subject(
        self, board: StoredCaseView, node_id: str, principal: Principal
    ) -> BoardItem:
        item = await self.items.by_element(board.case_id, node_id)
        if item is None or item.withdrawn_at is not None or item.kind != "node":
            raise ItemNotFound(node_id)
        # A node on this board only, drawn here or placed here as a reference, as `decide` asks.
        if item.board_id != board.id and node_id not in (board.node_ids or []):
            raise ItemNotFound(node_id)
        if not await self.graph.get_nodes([node_id], principal):
            raise ItemNotFound(node_id)
        if item.author != principal.id:
            raise DrawingRefused(
                "not_your_item", "only the person who drew an item gives it a picture",
                status=403,
            )  # fmt: skip
        # As ADR-105 refuses it, and as the store would after the file was kept: a picture only of
        # a type that may have one.
        (node,) = await self.graph.get_nodes([node_id], principal)
        depicts = self.ontology.edge_type(DEPICTS)
        if depicts is None or node.type not in depicts.to_types:
            raise DrawingRefused(
                "no_picture_for_this_type", f"a {node.type} cannot have a picture of its own",
                status=422,
            )  # fmt: skip
        return item

    async def _depict(
        self,
        board: StoredCaseView,
        subject: BoardItem,
        document_id: str,
        marking: str,
        principal: Principal,
        into: Into,
        document: NodeWrite | None = None,
    ) -> DrawnItemMade:
        now = datetime.now(UTC)
        provenance = Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id=document_id, locator="whole file", excerpt_hash="")],
            first_seen=now,
        )
        link = EdgeWrite(
            id=new_edge_id(),
            type=DEPICTS,
            source=document_id,
            target=subject.element_id,
            properties={"shown": True},
            provenance=provenance,
            handling=self._handling(marking, principal),
            created_by=principal.id,
            created_at=now,
            datasets=[into.dataset_id],
        )
        current = await self._current_picture(board.case_id, subject.element_id, principal)
        if current is None:
            _, (edge_id,) = await self._write([document] if document is not None else [], [link])
        else:
            # ADR-105: a new picture supersedes the one before, which is kept, no longer shown.
            tx = await self.graph.begin_transaction()
            try:
                if document is not None:
                    await self.graph.upsert_nodes([document], tx)
                edge_id = await self.graph.supersede_edge(current, link, tx, old_type=DEPICTS)
            except Exception:
                await self.graph.rollback_transaction(tx)
                raise
            await self.graph.commit_transaction(tx)
        item = new_item(
            board_id=board.id, case_id=board.case_id, kind="picture", element_id=edge_id,
            author=principal.id, dataset_id=into.dataset_id, source=document_id,
            target=subject.element_id,
        )  # fmt: skip
        await self.items.add(item, None)
        return DrawnItemMade(element_id=edge_id, item_id=item.item_id)

    async def _current_picture(
        self, case_id: str, subject: str, principal: Principal
    ) -> str | None:
        """The drawn node's picture link as `principal` may see it, the newest; `None` for none."""
        held = [
            i.element_id
            for i in await self.items.in_case(case_id)
            if i.kind == "picture" and i.target == subject and i.withdrawn_at is None
        ]
        links = await self.graph.get_edges(held, principal) if held else []
        if not links:
            return None
        return max(links, key=lambda e: e.audit.created_at).id

    async def upload_picture(
        self,
        board: StoredCaseView,
        node_id: str,
        principal: Principal,
        *,
        name: str,
        data: bytes,
        marking: str,
        source_note: str,
        before_write: Callable[[], Awaitable[None]] | None = None,
    ) -> DrawnItemMade:
        """C17 (a): an uploaded image becomes an image `Document` in the layer, with a `DEPICTS`
        link to the drawn node, both carrying the picture's own marking: a reader not cleared for
        the picture sees no picture. Its source note is the Document's own source (decision 7).
        Every refusal comes before the file is kept."""
        if not source_note.strip():
            raise DrawingRefused(
                "no_source", "say where the picture comes from: a source note", status=422
            )
        if self.media is None:
            raise DrawingRefused("no_media_store", "pictures cannot be stored here", status=503)
        extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        content_type = PICTURE_TYPES.get(extension)
        if content_type is None:
            raise DrawingRefused(
                "not_a_picture", f"{name!r} is not a picture (a png, jpeg, webp or gif)",
                status=422,
            )  # fmt: skip
        subject = await self._picture_subject(board, node_id, principal)
        self.check_marking(marking, await self.ceiling(board.case_id), principal)
        into = await self.into(board.case_id)
        ref = reference_for(data, content_type)
        # The Document's id is the layer's own, so it is never the same element as a copy of
        # the same file uploaded into a source or another case's layer (rule 3).
        document_id = "content:" + sha256(f"{into.dataset_id}:{ref}".encode()).hexdigest()[:32]
        # The audit entry is written after every refusal and before anything is kept (ADR-127
        # Amendment 23): a row without a picture records an attempt; never the reverse.
        if before_write is not None:
            await before_write()
        await self.media.put(data, content_type)
        now = datetime.now(UTC)
        document = NodeWrite(
            id=document_id,
            type=DOCUMENT_TYPE,
            properties={
                "title": name,
                "media_kind": "image",
                "object_ref": ref,
                "size_bytes": len(data),
            },  # fmt: skip
            provenance=Provenance(
                state=ProvenanceState.ASSERTED,
                sources=[
                    SourceRef(
                        document_id=f"upload:{name}", locator=source_note.strip(), excerpt_hash=""
                    )
                ],
                first_seen=now,
            ),  # fmt: skip
            handling=self._handling(marking, principal),
            created_by=principal.id,
            created_at=now,
            datasets=[into.dataset_id],
        )
        return await self._depict(
            board, subject, document_id, marking, principal, into, document=document
        )

    async def choose_picture(
        self,
        board: StoredCaseView,
        node_id: str,
        given: PictureChoice,
        principal: Principal,
        *,
        before_write: Callable[[str], Awaitable[None]] | None = None,
    ) -> DrawnItemMade:
        """C17 (b): an image the case already holds, linked by a `DEPICTS` written into the layer;
        the image stays in its dataset. The link is marked at least as the image is.
        `before_write` is given that marking, after every refusal and before the link is written
        (ADR-127 Amendment 27: a picture is never left unaudited)."""
        subject = await self._picture_subject(board, node_id, principal)
        found = await self.graph.get_nodes([given.document_id], principal)
        if (
            not found
            or found[0].type != DOCUMENT_TYPE
            or found[0].properties.get("media_kind") != "image"
        ):
            raise DrawingRefused(
                "not_a_picture", "that is not a picture this case holds", status=422
            )
        if given.marking not in self.scheme.classification:
            raise DrawingRefused(
                "not_a_marking", f"{given.marking} is not a marking of this deployment", status=422
            )
        marking = merge_handling(
            self._handling(given.marking, principal), found[0].handling, self.scheme
        ).classification
        self.check_marking(marking, await self.ceiling(board.case_id), principal)
        into = await self.into(board.case_id)
        if before_write is not None:
            await before_write(marking)
        return await self._depict(board, subject, given.document_id, marking, principal, into)

    async def pictures(self, board: StoredCaseView, principal: Principal) -> dict[str, str]:
        """Each drawn node's picture on the board the reader may see: the newest shown `DEPICTS`
        from an image Document, read through the reader's principal."""
        live = [
            i for i in await self.items.on_board(board.case_id, board.id)
            if i.kind == "picture" and i.withdrawn_at is None
        ]  # fmt: skip
        if not live:
            return {}
        links = await self.graph.get_edges([i.element_id for i in live], principal)
        documents = {
            n.id: n
            for n in await self.graph.get_nodes(list({e.source for e in links}), principal)
            if n.type == DOCUMENT_TYPE and n.properties.get("media_kind") == "image"
        }
        newest: dict[str, Edge] = {}
        for edge in links:
            if edge.source not in documents or edge.properties.get("shown") is False:
                continue
            held = newest.get(edge.target)
            if held is None or edge.audit.created_at > held.audit.created_at:
                newest[edge.target] = edge
        return {target: edge.source for target, edge in newest.items()}

    async def picture_file(
        self, board: StoredCaseView, node_id: str, principal: Principal
    ) -> tuple[bytes, str]:
        if self.media is None:
            raise ItemNotFound(node_id)
        document_id = (await self.pictures(board, principal)).get(node_id)
        if document_id is None:
            raise ItemNotFound(node_id)
        (document,) = await self.graph.get_nodes([document_id], principal)
        ref = str(document.properties["object_ref"])
        return await self.media.get(ref), content_type_of(ref)

    # --- watches --------------------------------------------------------------------------

    async def watches(self, case_id: str, principal: Principal) -> list[Any]:
        """The case's drawn-item watches the reader may see: a watch on an item they may not see
        is withheld whole (Amendment 2 decision 8; rule 3)."""
        held = await self.items.active_watches(case_id)
        if not held:
            return []
        nodes = {i.element_id for i in await self.items.in_case(case_id) if i.kind == "node"}
        node_ids = [w.element_id for w in held if w.element_id in nodes]
        edge_ids = [w.element_id for w in held if w.element_id not in nodes]
        seen = (
            {n.id for n in await self.graph.get_nodes(node_ids, principal)} if node_ids else set()
        )
        if edge_ids:
            seen |= {e.id for e in await self.graph.get_edges(edge_ids, principal)}
        return [w for w in held if w.element_id in seen]


def match_writes(
    drawn: Node,
    loaded: Node,
    *,
    same: bool,
    into: str,
    principal: Principal,
    stricter: Handling,
) -> tuple[list[NodeWrite], list[EdgeWrite]]:
    """What a match decision writes: one link, `SAME_AS` (score 1.0, asserted: a manual link,
    `01_DOMAIN_MODEL.md` §4) or `NOT_SAME_AS`, into the layer, marked as the stricter of the two
    ends. No node is written: the two stay two (rule 6)."""
    now = datetime.now(UTC)
    edge_type = SAME_AS if same else NOT_SAME_AS
    return [], [
        EdgeWrite(
            id=new_edge_id(),
            type=edge_type,
            source=drawn.id,
            target=loaded.id,
            properties={"score": 1.0} if same else {},
            provenance=Provenance(
                state=ProvenanceState.ASSERTED,
                sources=[
                    SourceRef(
                        document_id=f"manual:{drawn.id}:{loaded.id}",
                        locator=principal.id,
                        excerpt_hash="",
                    )
                ],
                first_seen=now,
            ),  # fmt: skip
            handling=stricter,
            created_by=principal.id,
            created_at=now,
            datasets=[into],
        )
    ]


def _accepts(types: Sequence[str], node_type: str) -> bool:
    return "*" in types or node_type in types


def _normal(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.casefold()).split())


def _alike(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _normal(a), _normal(b)).ratio()


def _longest_word(label: str) -> str | None:
    words = sorted((w for w in _normal(label).split() if len(w) >= 3), key=len, reverse=True)
    return words[0] if words else None


__all__: Sequence[str] = (
    "Boards",
    "BoardNotFound",
    "DrawingRefused",
    "ItemNotFound",
    "Grading",
    "match_writes",
)
