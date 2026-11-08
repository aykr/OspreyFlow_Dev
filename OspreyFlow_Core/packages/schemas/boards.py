"""Drawing boards (ADR-143 decisions 4 to 7; Amendments 2 and 3; `01_DOMAIN_MODEL.md` §2.2d; L3.3).

A **board** is a case view with drawing switched on (ADR-143 decision 5; ADR-144): it always belongs
to a case and keeps its own layout. What is drawn on it is data, written into the case's analyst
layer (or, for a case that began as a drawing, into its drawn dataset: Amendment 3 decision 1),
never into a source. Each drawn node and link carries a `DrawnAssertion` on its provenance: who
asserted it, on which board of which case, its grading and its source note (decision 4). That is
the provenance class `analyst_drawn`, drawn dashed in amber everywhere it appears.

- **`Grading`**: a grade in the deployment's scheme (decision 11; the scheme setting itself is
  L3.7's, and until it is built every board grades in `5x5x5`).
- **`DrawnItemInput`**, **`DrawnLinkInput`**, **`DrawnItemEdit`**: declaring, linking, editing.
- **`BoardInput`**, **`Board`**, **`BoardOpened`**: making, listing and opening a board.
- **`MatchSuggestion`**, **`MatchDecision`**: *Looks like a loaded item* (decision 6). A
  suggestion is `inferred` and never acts on its own (rule 5); a decision writes a link, never a
  merge (rule 6).
- **`DrawnWatch`**: the watch drawing an item sets (Amendment 2 decision 8).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.domain import (
    GRADING_PARTS,
    DocumentId,
    DrawnAssertion,
    Edge,
    EdgeId,
    Grading,
    GradingScheme,
    Node,
    NodeId,
    PrincipalId,
)

__all__ = ["GRADING_PARTS", "DrawnAssertion", "Grading", "GradingScheme"]


class _Asserted(BaseModel):
    """What every drawn node and link is given (decision 4)."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=200)
    marking: str = Field(min_length=1)
    grading: Grading
    source_note: str | None = Field(default=None, max_length=2000)
    source_document: DocumentId | None = None

    @model_validator(mode="after")
    def _has_a_source(self) -> _Asserted:
        if not (self.source_note and self.source_note.strip()) and not self.source_document:
            raise ValueError("give a source note, a document of the case, or both")
        return self


class DrawnItemInput(_Asserted):
    """*Add to board*: a node of a type of the case's model (C14), with its key properties if the
    analyst knows them (each checked against the type), placed where it was dropped."""

    type: str = Field(min_length=1)
    properties: dict[str, Any] = Field(default_factory=dict)
    icon: str | None = None
    x: float = 0.0
    y: float = 0.0


class DrawnLinkInput(_Asserted):
    """A link drawn by the handle, by Alt-drag, by *Draw a link from here* or by the link form:
    between two items on the board, drawn or loaded. The label is what the link says."""

    type: str = Field(min_length=1)
    source: NodeId
    target: NodeId


class DrawnItemEdit(BaseModel):
    """The author changes their own item: what is not given stays. A marking is never lowered."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=200)
    marking: str | None = None
    grading: Grading | None = None
    source_note: str | None = Field(default=None, max_length=2000)
    source_document: DocumentId | None = None
    properties: dict[str, Any] | None = None
    icon: str | None = None


BoardStart = Literal["blank", "view", "selection"]


class BoardInput(BaseModel):
    """*New drawing board* in a case: blank, from a view (its loaded items as live references),
    or from a selection (replacing *Branch selected*)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    start: BoardStart = "blank"
    view_id: str | None = None
    node_ids: list[NodeId] | None = Field(default=None, max_length=10_000)

    @model_validator(mode="after")
    def _start_is_whole(self) -> BoardInput:
        if self.start == "view" and not self.view_id:
            raise ValueError("a board from a view names the view")
        if self.start == "selection" and not self.node_ids:
            raise ValueError("a board from a selection names what is selected")
        if self.start == "blank" and (self.view_id or self.node_ids):
            raise ValueError("a blank board starts from nothing")
        return self


class DrawingInput(BaseModel):
    """*New drawing board* with no case (Amendment 2 decision 5): a drawn dataset named after the
    drawing, its home case and the board, in one step."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    pack: Literal["fibo", "niem", "stix"] | None = None
    highest_marking: str = Field(min_length=1)


class Board(BaseModel):
    """A board as listed: never naming its items."""

    id: str
    case_id: str
    name: str
    created_by: PrincipalId
    created_at: datetime
    shared: bool = False
    #: The drawn items on it the reader may see (withdrawn ones not counted).
    drawn: int = 0
    #: How it began.
    start: BoardStart = "blank"


class NewDrawing(BaseModel):
    """`POST /v1/drawings`'s answer: the case made for the drawing and its board."""

    dataset_id: str
    investigation_id: str
    board: Board


class BoardOpened(BaseModel):
    """A board opened now, as the reader may see it. `nodes` are its drawn items and its loaded
    references; `drawn` names which are drawn (the rest are live references, not editable here);
    `missing` counts what it could not show and names none (rule 3)."""

    board: Board
    nodes: list[Node]
    edges: list[Edge]
    drawn: list[str] = Field(default_factory=list)
    #: The item id of each drawn node and link the reader may see, by element id.
    items: dict[str, str] = Field(default_factory=dict)
    layout: dict[NodeId, Any] = Field(default_factory=dict)
    missing: int = 0
    #: What may be drawn here: the model's node and link types, the markings up to the ceiling,
    #: and the grading scheme.
    node_types: list[str] = Field(default_factory=list)
    link_types: list[str] = Field(default_factory=list)
    markings: list[str] = Field(default_factory=list)
    ceiling: str | None = None
    grading_scheme: GradingScheme = "5x5x5"
    #: Whether this reader may draw on it (its creator, holding `draw_on_boards`).
    may_draw: bool = False


class DrawnItemMade(BaseModel):
    """What declaring or linking wrote: the element's id, the board's item id, and the watch set."""

    element_id: str
    item_id: str
    watch_id: str | None = None


class BoardMove(BaseModel):
    """Items moved on the board (by drag or by arrow keys): the board's own layout, not data."""

    model_config = ConfigDict(extra="forbid")

    positions: dict[NodeId, dict[str, float]] = Field(max_length=10_000)


class Withdrawn(BaseModel):
    """What a withdrawal took back (never deleted: kept in the audit). Every drawn link touching a
    withdrawn node goes with it, and is named here, so nothing is dropped silently (rule 2)."""

    nodes: list[NodeId] = Field(default_factory=list)
    links: list[EdgeId] = Field(default_factory=list)
    watches_ended: int = 0


class MatchSuggestion(BaseModel):
    """*Looks like a loaded item*: a drawn node and a loaded one the reader may see, of the same
    type, with how alike they are. `inferred` until a person decides (rule 5)."""

    drawn: NodeId
    loaded: Node
    score: float = Field(ge=0.0, le=1.0)
    why: str
    state: Literal["inferred"] = "inferred"


class MatchSuggestions(BaseModel):
    suggestions: list[MatchSuggestion] = Field(default_factory=list)
    #: More matched than are shown (rule 2: said, never cut silently).
    more: bool = False


class MatchDecision(BaseModel):
    """*Same* writes a confirmed `SAME_AS` (score 1.0) in the layer; *Not the same* a `NOT_SAME_AS`.
    Neither changes the loaded item (decision 6; rule 6)."""

    model_config = ConfigDict(extra="forbid")

    drawn: NodeId
    loaded: NodeId
    same: bool


class MatchDecided(BaseModel):
    """The link a match decision wrote."""

    edge_id: str


class BoardPictures(BaseModel):
    """Each drawn node's picture on a board that the reader may see: node id to Document id."""

    pictures: dict[NodeId, str] = Field(default_factory=dict)


class PictureChoice(BaseModel):
    """C17 (b): a picture the case already holds, linked to the drawn node by a `DEPICTS` in the
    layer; the image stays in its dataset."""

    model_config = ConfigDict(extra="forbid")

    document_id: DocumentId
    marking: str = Field(min_length=1)


class DrawnWatch(BaseModel):
    """Amendment 2 decision 8: drawing an item sets a watch for it on the case's dataset, owned by
    the item's author; withdrawing the item ends it. Its alerts' queue is L3.6's, with L2.10."""

    id: str
    item_id: str
    element_id: str
    case_id: str
    dataset_id: str | None
    owner: PrincipalId
    created_at: datetime
    ended_at: datetime | None = None
    kind: Literal["drawn_watch"] = "drawn_watch"


ALL_MODELS: tuple[type[BaseModel], ...] = (
    DrawnItemInput,
    DrawnLinkInput,
    DrawnItemEdit,
    BoardInput,
    DrawingInput,
    Board,
    NewDrawing,
    BoardOpened,
    DrawnItemMade,
    BoardMove,
    Withdrawn,
    MatchSuggestion,
    MatchSuggestions,
    MatchDecision,
    MatchDecided,
    BoardPictures,
    PictureChoice,
    DrawnWatch,
)
