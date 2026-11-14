"""What a person owns that the case lane keeps, as Admin's *Disable…* reads it (`06_DECISIONS.md`
ADR-145 decision 6 and A4; L3.8, the case-b lane's ownership route).

Words and counts only (rule 7): each item is its kind, the Conduit's own id for it (what a
transfer names) and a label that places it by its case's name, which Admin › People and roles already shows
the administrator. Never a view's, a board's or a proposed type's analyst-written name, an
identity-provider id, or a source-system identifier. An item the administrator may not see
(another unit's, or on a dataset marked above their clearance) is never read: `withheld` says that
some exist, never how many or where, as ADR-145 Amendment 5 decision 8 says another unit's items,
so *Transfer and disable* is refused until someone who can see them transfers them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

OwnershipKind = Literal["view", "board", "link_type_proposal", "drawn_watch"]


class OwnershipItem(BaseModel):
    """One thing the person answers for, needing a *Transfer to…* before they are disabled."""

    kind: OwnershipKind
    id: str
    #: Its case, by the id and the name People shows ("Kestrel"), so the Glass can group by case.
    investigation_id: str
    #: What it is, in words ("A private view of the case Kestrel").
    label: str


class PersonOwnership(BaseModel):
    """`GET /v1/admin/people/{user_id}/ownership`: what the person owns in the administrator's own
    unit, within their clearance; `counts` by kind, of these items only; `not_yet_listed` names the
    kinds whose store is not built yet, so the list is never taken for whole."""

    person: str
    items: list[OwnershipItem] = Field(default_factory=list)
    counts: dict[OwnershipKind, int] = Field(default_factory=dict)
    #: They own items of these kinds the administrator may not see: said, never counted or named.
    withheld: bool = False
    not_yet_listed: list[str] = Field(default_factory=list)


ALL_MODELS: list[type[BaseModel]] = [OwnershipItem, PersonOwnership]
