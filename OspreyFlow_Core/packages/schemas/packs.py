"""Case report packs (`06_DECISIONS.md` ADR-113 decisions 3 to 5, Amendment 1): the analyst's
intelligence product — an ordered list of items, each a dated trend snapshot, an assessment as
written at the time, a chosen entity with a caption, or a note. Each item is marked at the highest
classification it rests on; a reader who may not view everything an item rests on does not get it,
and is told how many items were withheld, never which. Publishing freezes an immutable version.
Generated into TypeScript for the Glass's Packs and Published tabs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from schemas.trends import TrendFigures

PackItemKind = Literal["trend", "assessment", "entity", "note"]


class AssessmentSnapshot(BaseModel):
    """A judgement as it was written when it was added — later edits to the judgement do not reach
    the pack."""

    judgement_id: str
    statement: str
    probability_band: str
    supporting: list[str] = Field(default_factory=list)
    contradicting: list[str] = Field(default_factory=list)
    author: str
    created_at: datetime


class EntitySnapshot(BaseModel):
    node_id: str
    entity_type: str
    #: The entity's name as its adder saw it.
    name: str
    caption: str


class PackItem(BaseModel):
    """One item as a reader gets it. It carries no position: the order of the list is the order, so
    a withheld item leaves no gap that says where it was."""

    id: str
    kind: PackItemKind
    #: The highest classification the item rests on — each page's banner.
    marking: str
    added_by: str
    added_at: datetime
    #: For a trend: the saved definition it was taken from, and its frozen figures.
    trend_id: str | None = None
    trend: TrendFigures | None = None
    assessment: AssessmentSnapshot | None = None
    entity: EntitySnapshot | None = None
    note: str | None = None
    #: Set only on an earlier snapshot in the pack's history: when it was refreshed, and by what.
    replaced_at: datetime | None = None
    replaced_by: str | None = None


class AddPackItem(BaseModel):
    """What to add. The server reads and freezes the content itself, as the adder; nothing here is
    trusted as content except a caption and a note's own words."""

    kind: PackItemKind
    trend_id: str | None = None
    judgement_id: str | None = None
    node_id: str | None = None
    caption: str | None = Field(default=None, max_length=500)
    text: str | None = Field(default=None, max_length=4000)
    #: A note's marking, stated by its author (Amendment 1): never above their own clearance.
    classification: str | None = None
    #: A note's handling code; the scheme's least restrictive code when left empty.
    handling_code: str | None = None


class PackInput(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class PackOrder(BaseModel):
    """The reader's own visible items in their new order: the items withheld from them keep their
    places."""

    item_ids: list[str] = Field(max_length=200)


class PackWithdrawal(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class PackVersionSummary(BaseModel):
    version: int
    published_at: datetime
    published_by: str
    withdrawn_at: datetime | None = None
    withdrawn_by: str | None = None
    withdrawal_reason: str | None = None


class ReportPack(BaseModel):
    id: str
    investigation_id: str
    title: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    versions: list[PackVersionSummary] = Field(default_factory=list)


class PackDraft(BaseModel):
    """The draft as an Editor assembling it sees it."""

    pack: ReportPack
    items: list[PackItem]
    #: Items in the draft this reader may not see — how many, never which.
    withheld: int = Field(ge=0)
    #: The highest marking among the items shown.
    marking: str | None = None


class PackHistory(BaseModel):
    """The earlier snapshots a refresh replaced, as this reader may see them, and the versions."""

    earlier_snapshots: list[PackItem]
    withheld: int = Field(ge=0)
    versions: list[PackVersionSummary]


class PublishedPack(BaseModel):
    pack_id: str
    investigation_id: str
    title: str
    version: int
    published_at: datetime
    published_by: str
    items: list[PackItem]
    withheld: int = Field(ge=0)
    marking: str | None = None


class PublishedPackSummary(BaseModel):
    pack_id: str
    title: str
    version: int
    published_at: datetime
    published_by: str


class PackWithheldBody(BaseModel):
    """Publishing refused: the draft holds items the publisher may not see (Amendment 1)."""

    error: Literal["pack_has_withheld_items"] = "pack_has_withheld_items"
    withheld: int


ALL_MODELS: tuple[type[BaseModel], ...] = (
    AssessmentSnapshot,
    EntitySnapshot,
    PackItem,
    AddPackItem,
    PackInput,
    PackOrder,
    PackWithdrawal,
    PackVersionSummary,
    ReportPack,
    PackDraft,
    PackHistory,
    PublishedPack,
    PublishedPackSummary,
    PackWithheldBody,
)
