"""A case view: a saved lens on a case (ADR-144; `01_DOMAIN_MODEL.md` §2.2c).

A case is the only container. A **view** is saved under one case and holds **no data**: a name, its
creator, whether it is shared with the case, what it shows (a chosen set of nodes or a filter), a
layout, a timeline range and a resolution threshold (*Match strictness*), and, for a drawing board
(ADR-143 decision 5, L3.3), `drawing`. It re-reads the case each time it opens (decision 2), through
the reader's own principal, so it never widens what its reader may see (ADR-099).

- **`CaseView`**: the view as listed, never naming its chosen nodes.
- **`CaseViewInput`**: what *Save what I see as a view* sends.
- **`CaseViewOpened`**: the view opened now: the items the reader may see, and how many of its
  chosen items it could not show, **never which** (decision 2; rule 3).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.domain import Edge, Interval, Node, NodeId, PrincipalId


class ViewFilter(BaseModel):
    """What a filtered view keeps (ADR-124 decision 2's filter, ADR-144 decision 1): entity types,
    a date window, or both. Applied to the reader's own projection of the case and nothing else."""

    model_config = ConfigDict(extra="forbid")

    entity_types: list[str] | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    @model_validator(mode="after")
    def _a_choice_is_made(self) -> ViewFilter:
        if self.entity_types is None and self.valid_from is None and self.valid_to is None:
            raise ValueError("choose entity types, a date window, or both")
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("the window ends before it starts")
        return self


class NodePosition(BaseModel):
    """Where a node sits on the view's canvas."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


class CaseViewInput(BaseModel):
    """*Save what I see as a view* (ADR-144 decision 4): a name and exactly one of a node selection
    or a filter, with the layout, timeline range and threshold the reader had."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    node_ids: list[NodeId] | None = Field(default=None, max_length=10_000)
    filter: ViewFilter | None = None
    layout: dict[NodeId, NodePosition] = Field(default_factory=dict)
    window: Interval | None = None
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _one_lens(self) -> CaseViewInput:
        if (self.node_ids is None) == (self.filter is None):
            raise ValueError("a view shows a chosen set of nodes or a filter, exactly one")
        return self


class CaseView(BaseModel):
    """A view as listed and answered (ADR-144 decisions 1 and 3). Private to `created_by` until
    shared; deleted only by its creator; deleting it deletes nothing else.

    **What it never carries:** the chosen nodes' ids or their positions. Those are kept by the
    Conduit alone (`services/api/case_views.py`'s stored view), because a shared view's selection is
    its creator's, and naming an id the reader may not see would tell them it exists (rules 3
    and 7). `chosen` counts the selection; opening the view (`CaseViewOpened`) gives the items and
    positions the reader may see now."""

    model_config = ConfigDict(extra="forbid")

    id: str
    case_id: str
    name: str
    created_by: PrincipalId
    created_at: datetime
    shared: bool = False
    #: How many nodes were chosen, for a view of chosen nodes; `None` for a filtered view.
    chosen: int | None = Field(default=None, ge=0)
    filter: ViewFilter | None = None
    window: Interval | None = None
    threshold: float | None = None
    #: A drawing board (ADR-143 decision 5); boards are built in L3.3.
    drawing: bool = False
    #: The retired case this view was converted from by the upgrade (ADR-144 decision 6), whose
    #: audit stays readable from the view; `None` for a view a person saved.
    converted_from_case: str | None = None
    #: A drawing merged into a dataset (ADR-143 Amendment 2 decision 7; L3.9): the load that merged
    #: it. The view keeps its sharing and layout; what did not become data is on it as annotations.
    merged_load: str | None = None


class ViewAnnotation(BaseModel):
    """What a merged drawing keeps of a drawn item on its view (Amendment 2 decision 7): what did
    not become data, read through the reader's own handling, so an item they may not see has none
    (rule 3)."""

    model_config = ConfigDict(extra="forbid")

    element_id: str
    kind: Literal["node", "link"]
    label: str
    marking: str
    grading: str | None = None
    source_note: str | None = None
    #: "Drawn by A. Field, merged as load 8812", or "… not merged: why".
    words: str
    merged: bool


class CaseViewOpened(BaseModel):
    """A view opened now (decision 2): what the reader may see of it, live, and the saved positions
    of those items alone. `missing` counts the chosen nodes it could not show, for whatever reason,
    and names none of them."""

    model_config = ConfigDict(extra="forbid")

    view: CaseView
    nodes: list[Node]
    edges: list[Edge]
    layout: dict[NodeId, NodePosition] = Field(default_factory=dict)
    missing: int = Field(ge=0)
    annotations: list[ViewAnnotation] = Field(default_factory=list)


ALL_MODELS: tuple[type[BaseModel], ...] = (
    ViewFilter,
    NodePosition,
    CaseViewInput,
    CaseView,
    ViewAnnotation,
    CaseViewOpened,
)
