"""Case report packs (`06_DECISIONS.md` ADR-113 decisions 3 to 5, Amendment 1): the analyst's
intelligence product — an ordered list of items, each a dated trend snapshot, an assessment as
written at the time, a chosen entity with a caption, a note, or an alert (ADR-134 decision 1).
Each item is marked at the highest classification it rests on; a reader who may not view
everything an item rests on does not get it, and is told only whether some were withheld, never how
many or which. Publishing freezes an immutable version.
Generated into TypeScript for the Glass's Packs and Published tabs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from schemas.domain import AlertDisposition, AlertKind, AlertSeverity, AlertStatus, Interval
from schemas.trends import TrendFigures

PackItemKind = Literal["trend", "assessment", "entity", "note", "alert"]


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


class AlertEntitySnapshot(BaseModel):
    """An entity an alert matched, named as its adder read it."""

    node_id: str
    entity_type: str
    name: str
    #: Step 9e: for a screening list's own entry for a listed party (`kyc_rules._listed_write`
    #: gives it `listing` and `list_name`), the list it is the entry on. A screening alert cites
    #: the customer and that entry, never merged (rule 6), and named alike they read as one person
    #: matched twice; the stored item says which is the list's, as the Glass does (`concernWords`).
    list_entry_on: str | None = None


class AlertLinkSnapshot(BaseModel):
    """A link an alert cites as evidence."""

    edge_id: str
    type: str
    source_name: str
    target_name: str


class AlertTransactionSnapshot(BaseModel):
    """A transaction an alert cites as evidence: when, how much, between whom."""

    occurred_at: datetime
    amount: float | None = None
    source_name: str
    target_name: str


class AlertSnapshot(BaseModel):
    """An alert as its adder read it (ADR-134 decision 1): its explanation, the entity it matched,
    its evidence, and its outcome and reason if it was closed. Frozen when added, like every item;
    `status` says what it was then, so an alert still open says so."""

    alert_id: str
    kind: AlertKind
    severity: AlertSeverity
    #: The alert in words: the rule's sentence or the typology's, each entity named.
    explanation: str
    typology: str | None = None
    #: The hotlisted identifier it matched, for a hotlist alert.
    hotlist_entry: str | None = None
    window: Interval | None = None
    raised_at: datetime
    entities: list[AlertEntitySnapshot] = Field(default_factory=list)
    links: list[AlertLinkSnapshot] = Field(default_factory=list)
    transactions: list[AlertTransactionSnapshot] = Field(default_factory=list)
    status: AlertStatus
    outcome: AlertDisposition | None = None
    reason: str | None = None
    #: Rule 5: a match no person has confirmed is `inferred`, and the pack says so.
    match: Literal["inferred", "confirmed"]
    #: Every node it cites, its own included: checked again as each reader, when read.
    node_ids: list[str] = Field(default_factory=list)


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
    alert: AlertSnapshot | None = None
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
    #: An alert of the adder's queue in this case (ADR-134 decision 1).
    alert_id: str | None = None
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
    #: ADR-106: the name, resolved when served and never stored; `None` shows the id.
    published_by_name: str | None = None
    withdrawn_at: datetime | None = None
    withdrawn_by: str | None = None
    withdrawn_by_name: str | None = None
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
    #: Whether some of the draft's items are ones this reader may not see — a yes or no, never how
    #: many or which (ADR-124 decision 9).
    withheld: bool
    #: The highest marking among the items shown.
    marking: str | None = None


class PackHistory(BaseModel):
    """The earlier snapshots a refresh replaced, as this reader may see them, and the versions."""

    earlier_snapshots: list[PackItem]
    #: Whether some earlier snapshots are withheld from this reader: a yes or no.
    withheld: bool
    versions: list[PackVersionSummary]


class PublishedPack(BaseModel):
    pack_id: str
    investigation_id: str
    title: str
    version: int
    published_at: datetime
    published_by: str
    #: ADR-106: the name, resolved when served and never stored; `None` shows the id.
    published_by_name: str | None = None
    items: list[PackItem]
    #: Whether some of the publication's items are withheld from this reader: a yes or no.
    withheld: bool
    marking: str | None = None


class PublishedPackSummary(BaseModel):
    pack_id: str
    title: str
    version: int
    published_at: datetime
    published_by: str
    #: ADR-106: the name, resolved when served and never stored; `None` shows the id.
    published_by_name: str | None = None


class PackWithheldBody(BaseModel):
    """Publishing refused: the draft holds items the publisher may not see (Amendment 1)."""

    error: Literal["pack_has_withheld_items"] = "pack_has_withheld_items"
    #: Always true: the draft holds an item the publisher may not see. Never how many.
    withheld: bool = True


class PackExportRequest(BaseModel):
    """An override, when an item needs its originator consulted: both, or the export is refused
    (ADR-045/047, as for every export)."""

    justification: str | None = Field(default=None, max_length=2000)
    originator_reference: str | None = Field(default=None, max_length=200)


class PackExportMark(BaseModel):
    """ADR-047's mark for a pack: what a recipient must act on, printed on every page. A pack is
    frozen snapshots, not a view of the graph, so it carries its version, not a resolution
    threshold."""

    osprey_mark: Literal["OspreyFlow"] = "OspreyFlow"
    investigation_id: str
    pack_id: str
    version: int
    exported_at: datetime
    exported_by: str
    #: ADR-106: the name, resolved when served and never stored; `None` shows the id.
    exported_by_name: str | None = None
    #: The highest marking among the items exported.
    handling_level: str
    #: An exported entity or assessment rests on a record since superseded (retracted or corrected).
    rests_on_retracted_evidence: bool = False


class PackExport(BaseModel):
    """The approved manifest (ADR-113 decision 6): only what the exporter may see, in order, each
    with its own marking for its page's banner. The Glass renders the PDF from this and nothing
    else."""

    mark: PackExportMark
    title: str
    version: int
    published_at: datetime
    published_by: str
    #: ADR-106: the name, resolved when served and never stored; `None` shows the id.
    published_by_name: str | None = None
    items: list[PackItem]
    policy: Literal["disclose", "omit"]
    #: Whether any of the pack's own items is withheld from the exporter (ADR-124 decision 9): a yes
    #: or no, never a count. `None` under `omit`, where the artefact carries no such field; never
    #: `None` under `disclose`.
    withheld: bool | None = None
    ledger_entry_id: str


ALL_MODELS: tuple[type[BaseModel], ...] = (
    AssessmentSnapshot,
    EntitySnapshot,
    AlertEntitySnapshot,
    AlertLinkSnapshot,
    AlertTransactionSnapshot,
    AlertSnapshot,
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
    PackExportRequest,
    PackExportMark,
    PackExport,
)
