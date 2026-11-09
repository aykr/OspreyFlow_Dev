"""Promotion into a dataset, and a removed case's layer merged or deleted (ADR-143 decisions 8 and
10; Amendment 2 decision 1; ADR-145 decision 8; `01_DOMAIN_MODEL.md` §2.2e; L3.4).

A **promotion** is a load: the board's drawn items the analyst ticks, and the links, pictures and
match decisions resting only on them, each *gain* the case's source dataset (ADR-099 decision 2's
union: the same element, never a copy, never a merge, rule 6). It is one load (`load_id`, trigger
`analyst_promotion`), all or nothing, revertible. Under the dataset's policy it is committed at once
(*Author promotes*) or waits for a second person (*Second person reviews*): one of the dataset's
Authors holding `review_promotions`, never its proposer.

- **`PromotionSheet`**: the *Promote…* sheet: every item, whether it may go and why not, the checks,
  the warnings (undecided matches) and how it will be recorded. Nothing is dropped silently
  (rule 2).
- **`PromotionInput`**: what the analyst ticked; every check is run again at the route.
- **`Promotion`**: one promotion as the board and the Studio's *Analyst promotions* list show it.
- **`PromotionDecision`**: *Approve and commit* or *Reject with a reason*.
- **`PromotionDetails`**: what a reviewer reads of what they review: the promotion's own items, each
  filtered by the reviewer's own clearance in the adapter (rule 3).
- **`RemovedCaseLayer`**, **`LayerMergeSheet`**, **`LayerMergeInput`**, **`LayerDeleted`**: a
  removed case's layer, merged by the dataset's Authors as a promotion (trigger `layer_merge`)
  under a read grant for that merge alone, or deleted (promoted items never touched).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PromotionStatus = Literal["awaiting_review", "committed", "rejected", "reverted"]
PromotionTrigger = Literal["analyst_promotion", "layer_merge"]
SheetItemKind = Literal["node", "link", "picture", "match"]


class SheetItem(BaseModel):
    """One drawn item on the sheet. `problems` says, in words, every check it fails; an item with
    a problem cannot be ticked. A link, picture or match decision `follows` its items: it goes when
    both its ends will be in the dataset, and is listed with the reason when it will not."""

    model_config = ConfigDict(extra="forbid")

    item_id: str
    element_id: str
    kind: SheetItemKind
    type: str
    label: str
    marking: str
    follows: bool = False
    #: Its ends, for a link, a picture and a match decision.
    source: str | None = None
    target: str | None = None
    problems: list[str] = Field(default_factory=list)


class PromotionCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    passed: bool
    words: str


class PromotionSheet(BaseModel):
    """The *Promote…* sheet for a board (decision 8)."""

    model_config = ConfigDict(extra="forbid")

    board_id: str
    dataset_id: str | None
    dataset_name: str | None
    highest_marking: str
    policy: Literal["author_promotes", "second_person_reviews"]
    items: list[SheetItem]
    checks: list[PromotionCheck]
    #: Undecided matches and anything else worth saying, which does not stop the promotion.
    warnings: list[str] = Field(default_factory=list)
    #: How it will be recorded, in words.
    recorded_as: str
    #: Why nothing on this board can be promoted at all, when that is so (a drawing that is its
    #: own dataset, a case reading a composite, a case reading no dataset).
    refused: str | None = None


class PromotionInput(BaseModel):
    """The items ticked. Links, pictures and match decisions follow their items, and are listed
    here only to say which of them go; each is checked again."""

    model_config = ConfigDict(extra="forbid")

    item_ids: list[str] = Field(min_length=1, max_length=500)


class LeftOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    label: str
    why: str


class Promotion(BaseModel):
    """One promotion (decision 10): the load, what it adds as counts, who, the case, its status.
    Never the items themselves: those are read through `PromotionDetails`, by the reader's own
    principal."""

    model_config = ConfigDict(extra="forbid")

    id: str
    load_id: str
    trigger: PromotionTrigger
    dataset_id: str
    dataset_name: str
    case_id: str
    case_name: str
    #: The board it came from, for the board's own list; `None` for a layer merge, and in the
    #: Studio's list (a board's id is its author's and its case's: the board-id rule). The case is
    #: named only to a reader who may know it (its own board's readers, the dataset's Authors);
    #: anyone else is told "a case reading this dataset" and an empty `case_id`.
    board_id: str | None = None
    proposed_by: str
    proposed_by_name: str
    proposed_at: datetime
    status: PromotionStatus
    reviewed_by: str | None = None
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    reason: str | None = None
    nodes: int = Field(ge=0)
    links: int = Field(ge=0)
    #: Given to its proposer alone: an unticked item may be one no one else may see (rule 3).
    left_out: list[LeftOut] = Field(default_factory=list)
    #: The operator command that reverts it, for a reader holding `revert_loads` (ADR-127
    #: Amendment 9: with the Conduit stopped). An online revert waits for the owner's ruling on
    #: ADR-143 open question 2.
    revert_command: str | None = None
    #: Whether this reader may approve or reject it, and, when not, why and who can.
    may_review: bool = False
    why_not: str | None = None


class Promotions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    promotions: list[Promotion]


class PromotionDecision(BaseModel):
    """*Approve and commit*, or *Reject with a reason* (a reason is required to reject)."""

    model_config = ConfigDict(extra="forbid")

    approve: bool
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _a_rejection_says_why(self) -> PromotionDecision:
        if not self.approve and not (self.reason or "").strip():
            raise ValueError("a rejection needs a reason")
        return self


class DetailItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    element_id: str
    kind: SheetItemKind
    type: str
    label: str
    marking: str
    source_note: str | None = None
    grading: str | None = None


class PromotionDetails(BaseModel):
    """What a reviewer reads of the promotion they review: its own items, nothing else of the
    case. `withheld` counts nothing and names nothing: it says only that some item is not shown to
    this reader, who therefore may not approve (rule 3: approving what one cannot read would
    commit it unseen)."""

    model_config = ConfigDict(extra="forbid")

    promotion: Promotion
    items: list[DetailItem]
    withheld: bool = False


class RemovedCaseLayer(BaseModel):
    """A removed case reading the dataset, as its Authors see it in the Studio: counts only."""

    model_config = ConfigDict(extra="forbid")

    investigation_id: str
    name: str
    items: int = Field(ge=0)
    #: A composite case's layer is never merged, only deleted (the orchestrator's settlement).
    mergeable: bool
    why_not: str | None = None


class RemovedCaseLayers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    cases: list[RemovedCaseLayer]


class LayerMergeSheet(BaseModel):
    """*Merge into the dataset*: opening it grants the Author read access to this one layer, for
    this merge alone (Amendment 2 decision 1), recorded in the audit; the grant ends when the merge
    closes (committed, rejected or cancelled)."""

    model_config = ConfigDict(extra="forbid")

    grant_id: str
    investigation_id: str
    case_name: str
    dataset_id: str
    dataset_name: str
    highest_marking: str
    policy: Literal["author_promotes", "second_person_reviews"]
    items: list[SheetItem]
    checks: list[PromotionCheck]
    warnings: list[str] = Field(default_factory=list)
    recorded_as: str


class LayerMergeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_ids: list[str] = Field(min_length=1, max_length=5000)


class LayerDeleted(BaseModel):
    """A removed case's layer deleted, in words. No count of what was withdrawn: it would include
    what the deleter may not see (rule 7). Promoted items are untouched."""

    model_config = ConfigDict(extra="forbid")

    investigation_id: str
    words: str


ALL_MODELS: tuple[type[BaseModel], ...] = (
    SheetItem,
    PromotionCheck,
    PromotionSheet,
    PromotionInput,
    LeftOut,
    Promotion,
    Promotions,
    PromotionDecision,
    DetailItem,
    PromotionDetails,
    RemovedCaseLayer,
    RemovedCaseLayers,
    LayerMergeSheet,
    LayerMergeInput,
    LayerDeleted,
)
