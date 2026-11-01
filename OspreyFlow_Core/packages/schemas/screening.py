"""Screening lists as managed sources (`06_DECISIONS.md` ADR-133 decision 4, stage (c)): a list
subscribed through a connector, its versions, and what each update changed.

A subscription names a connector (one of the Knowledge Adapters in
`knowledge_adapters/screening_lists.py`), the file it reads inside the deployment's ingest folder,
and, for a list that is not one of the repository's own synthetic files, the real dataset it is —
which the device's `real_data_exceptions.yaml` must name before anything loads (rule 9).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

#: The connectors a list may be subscribed through — `LIST_ADAPTERS`'s keys.
ScreeningListSource = Literal[
    "ofac_sdn", "ofsi_consolidated", "un_consolidated", "eu_consolidated", "opensanctions"
]
#: `scripts/real_data_exceptions.py`'s `APPROVED_USES`: what a real list is admitted for.
RealDataUse = Literal["local_development", "scale_testing", "owner_run_demonstration"]
#: What one refresh did: a new version applied, the same version found again, the list refused
#: before anything loaded (rule 9, or a file outside the ingest folder), or the file unreadable.
ScreeningUpdateOutcome = Literal["updated", "unchanged", "refused", "failed"]

_LIST_NAME = r"^[A-Za-z0-9][A-Za-z0-9 ()_.,'-]{0,119}$"


class ScreeningSubscriptionInput(BaseModel):
    """An administrator's subscription. `location` is a file inside the ingest folder; an OFAC
    subscription also reads `ALT.CSV` and `ADD.CSV` beside it when they are there."""

    list_name: str = Field(pattern=_LIST_NAME)
    source: ScreeningListSource
    location: str = Field(min_length=1, max_length=400)
    #: The real dataset this list is (for example `ofac_sdn`); `None` only for a synthetic file.
    dataset: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,64}$")
    use: RealDataUse = "local_development"


class ScreeningListStatus(BaseModel):
    """One list as the Lists screen shows it: its version, entries, last update and the failure of
    its last attempt, in words."""

    list_name: str
    source: ScreeningListSource
    location: str
    dataset: str | None = None
    synthetic: bool
    licence: str
    version: str | None = None
    entries: int = 0
    updated_at: datetime | None = None
    attempted_at: datetime | None = None
    failure: str | None = None


class ScreeningListUpdate(BaseModel):
    """One refresh of one list: what changed, and how many alerts its re-screening raised."""

    id: str
    list_name: str
    at: datetime
    outcome: ScreeningUpdateOutcome
    version: str | None = None
    previous_version: str | None = None
    added: int = 0
    changed: int = 0
    removed: int = 0
    #: The customers re-screened against the changed entries, and the alerts that raised.
    rescreened: int = 0
    alerts: int = 0
    words: str


class ScreeningLists(BaseModel):
    lists: list[ScreeningListStatus]
    #: The latest refreshes, newest first, across every list.
    updates: list[ScreeningListUpdate]
    #: Whether the reader may subscribe and refresh (an administrator).
    can_manage: bool = False


ALL_MODELS = (
    ScreeningSubscriptionInput,
    ScreeningListStatus,
    ScreeningListUpdate,
    ScreeningLists,
)
