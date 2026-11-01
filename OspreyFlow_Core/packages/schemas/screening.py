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

from schemas.monitoring import ListSchedule

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
    #: The owner's answer of 1 November 2026: false for a connector whose licence for a customer's
    #: screening is not confirmed (UN, OpenSanctions), which reads synthetic lists only; the
    #: reason in words beside it.
    licence_confirmed: bool = True
    licence_note: str | None = None
    version: str | None = None
    entries: int = 0
    updated_at: datetime | None = None
    attempted_at: datetime | None = None
    failure: str | None = None
    #: ADR-133 stage (d): the list's refresh schedule, in words and as set, who it runs as, and
    #: when it next runs; `None` when it is refreshed by hand only.
    schedule: ListSchedule | None = None
    schedule_words: str | None = None
    schedule_owner: str | None = None
    next_refresh: datetime | None = None


class ScreeningListUpdate(BaseModel):
    """One refresh of one list: what changed, and — counted in the reader's own organisational unit
    alone (the owner's answer of 1 November 2026; rule 7) — how many customers its re-screening read
    and how many alerts it raised."""

    id: str
    list_name: str
    at: datetime
    outcome: ScreeningUpdateOutcome
    version: str | None = None
    previous_version: str | None = None
    added: int = 0
    changed: int = 0
    #: Entries the publisher took off the list. Not `removed`: that name is the removal record's on
    #: the wire (ADR-124 decision 4), which no route may carry.
    delisted: int = 0
    #: The customers of the reader's own unit re-screened against the changed entries, and the
    #: alerts that raised there; never another unit's.
    rescreened: int = 0
    alerts: int = 0
    words: str
    #: ADR-133 stage (d): how the refresh was started — by a person, or by the list's schedule.
    trigger: Literal["manual", "schedule"] = "manual"


class ScreeningListsOverview(BaseModel):
    """The Lists screen for a reader of the alert queue: the lists alone. No refreshes — their
    counts of customers re-screened and alerts raised are for whoever may load lists, in their own
    unit (rule 7) — and no field that could hold them, so the route cannot send them, not merely
    does not."""

    lists: list[ScreeningListStatus]
    can_manage: Literal[False] = False


class ScreeningLists(BaseModel):
    """The Lists screen for whoever may load screening lists (`load_screening_lists`)."""

    lists: list[ScreeningListStatus]
    #: The latest refreshes, newest first, across every list; each counted in the reader's own unit.
    updates: list[ScreeningListUpdate]
    #: Whether the reader may subscribe and refresh (an administrator).
    can_manage: bool = False


ALL_MODELS = (
    ScreeningSubscriptionInput,
    ScreeningListStatus,
    ScreeningListUpdate,
    ScreeningListsOverview,
    ScreeningLists,
)
