"""Monitoring, stage (d) (`06_DECISIONS.md` ADR-133 decisions 1, 6 and 7): the scheduled trigger,
the Ingest Studio's "Checks on load" step, and maker–checker.

**Maker–checker (decision 7).** Deploying, changing or retiring a whole-deployment rule, and closing
a high-severity alert, waits for a second person with the right; the person who proposed it cannot
approve it. Every change to a rule is kept as a `RuleVersion`: what it did, who proposed it and
when, and who decided it.

**The scheduled trigger (decision 1).** A rule written as a sentence may run every day or every
week, at an hour; each run is recorded as a `RuleRun`, in words, and run as the rule's own author.
A screening list may be refreshed on a schedule too (Amendment 3, item 4).

**Checks on load (decision 6).** A data engineer attaches existing case and deployment rules to a
pipeline and chooses what a hit does there; they never write a rule here. Verify then shows the
alerts the sample would raise, writing nothing.

TypeScript is generated from these models (`generate_ts.py`); drift fails the build.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from schemas.domain import RuleChangeAction, RuleTrigger, TypologyParams
from schemas.sentences import RuleCadence

#: What became of a proposed change: waiting for a second person, approved by one, rejected (or
#: withdrawn by the person who proposed it), or applied at once (a change that needs no approval).
#: ADR-146 decision 3 (L2.11): `draft`, saved and not yet asked to go live; at most one per rule.
RuleChangeStatus = Literal["draft", "pending", "approved", "rejected", "applied"]


class RuleVersion(BaseModel):
    """One change to one rule, kept whole (decision 7: "rules keep their versions, and each change
    records who made it"). `name`, `params`, `trigger` and `budget_ms` are the rule as this version
    has it; for a retirement they are the rule as it stood."""

    rule_id: str
    version: int = Field(ge=1)
    action: RuleChangeAction
    name: str
    params: TypologyParams
    trigger: RuleTrigger
    budget_ms: int
    proposed_by: str
    proposed_at: datetime
    status: RuleChangeStatus
    decided_by: str | None = None
    decided_at: datetime | None = None
    #: Why, in words: the reason given for a rejection, or what the change awaited.
    words: str | None = None
    #: ADR-146 decision 3: *Test* of this version over the dataset's last `tested_days` days, by
    #: whom, and how many alerts it would have raised. A version goes live only once tested.
    tested_at: datetime | None = None
    tested_by: str | None = None
    tested_days: int | None = None
    would_raise: int | None = Field(default=None, ge=0)
    #: Resolved when the read is served, never stored (ADR-106).
    proposed_by_name: str | None = None
    decided_by_name: str | None = None


class RuleChangeRejection(BaseModel):
    """Rejecting (or, by its own proposer, withdrawing) a change waiting for approval."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)


# --- the scheduled trigger ------------------------------------------------------------------------

#: What became of one scheduled slot: run; refused (in words, the rule's author could not act);
#: missed (the deployment was not running then); failed (it ran and could not finish).
RuleRunOutcome = Literal["ran", "refused", "missed", "failed"]
#: ADR-146 decision 3 (L2.11): `draft`, a rule not yet made live, which has not run.
RuleScheduleState = Literal["draft", "scheduled", "stopped", "waiting_for_approval"]


class RuleRun(BaseModel):
    """One scheduled slot of one rule, as recorded."""

    id: str
    rule_id: str
    rule_version: int
    slot: datetime
    ran_at: datetime
    #: Whom it ran as: the rule's author, resolved afresh (ADR-036, ADR-043).
    run_as: str
    outcome: RuleRunOutcome
    alerts: int = 0
    words: str


class RuleScheduleView(BaseModel):
    """A scheduled rule's schedule, in words, with its next run and its latest runs. A schedule
    that will not run says why (`state` and `words`), never only a missing next run."""

    rule_id: str
    #: "Every day at 06:00 (Europe/London)".
    schedule: str
    state: RuleScheduleState
    #: Why it is stopped or waiting, in words; `None` when scheduled.
    words: str | None = None
    next_run: datetime | None = None
    runs: list[RuleRun] = Field(default_factory=list)


class ListSchedule(BaseModel):
    """A screening list's refresh schedule (ADR-133 Amendment 3, item 4): every day, or every week
    on one day, at a whole hour, read in Europe/London. That a weekly one names its day, and a daily
    one none, is checked by `services/api/list_schedule.check_list_schedule`, so the route says it
    in words."""

    model_config = ConfigDict(extra="forbid")

    every: RuleCadence = "daily"
    hour: int = Field(default=5, ge=0, le=23)
    #: 1 (Monday) to 7 (Sunday): a weekly schedule names one, a daily schedule none.
    weekday: int | None = Field(default=None, ge=1, le=7)


class ListScheduleInput(BaseModel):
    """Setting (or, with `schedule` left out, stopping) a list's refresh schedule."""

    model_config = ConfigDict(extra="forbid")

    schedule: ListSchedule | None = None


# --- checks on load ------------------------------------------------------------------------------

#: At this pipeline, what a hit of an attached rule does: loads with its alert, or holds its rows
#: for a reviewer (before commit only; ADR-109 ruling 1).
LoadCheckOnHit = Literal["alert", "hold"]


class LoadCheck(BaseModel):
    """One rule attached to a pipeline, by its id, and what a hit does there. It names a rule; it
    cannot carry one (`extra="forbid"`): engineers attach rules, they do not write them."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(min_length=1)
    on_hit: LoadCheckOnHit = "alert"


class LoadChecksInput(BaseModel):
    """The pipeline's checks on load, replaced whole."""

    model_config = ConfigDict(extra="forbid")

    checks: list[LoadCheck] = Field(default_factory=list, max_length=100)


class LoadCheckRule(BaseModel):
    """A load-time rule the engineer may attach, as the rules list shows it: its name, its sentence
    or typology in words, its scope, when it runs and how urgent its alerts are."""

    rule_id: str
    name: str
    words: str
    scope: Literal["this_case", "deployment"]
    trigger: RuleTrigger
    severity: Literal["low", "medium", "high"]
    status: Literal["pending", "active"]
    #: Before commit only: a rule that runs after commit cannot hold rows.
    can_hold: bool
    #: A whole-deployment rule applies to every pipeline; it cannot be left off one.
    always_applies: bool
    #: Its author's own choice for a hit, before this pipeline's: "hold" only for a sentence that
    #: holds its rows.
    authors_on_hit: LoadCheckOnHit


class LoadChecksView(BaseModel):
    """The pipeline's "Checks on load" step. `chosen` is false until an engineer has chosen: then
    every case rule judges the pipeline's loads, as before the step existed."""

    recipe_id: str
    chosen: bool
    checks: list[LoadCheck] = Field(default_factory=list)
    available: list[LoadCheckRule] = Field(default_factory=list)
    set_by: str | None = None
    set_at: datetime | None = None


class WouldRaise(BaseModel):
    """One alert Verify's sample would raise (decision 6): the rule, what a hit does at this
    pipeline, and the entity matched, as the person verifying reads it in the sample."""

    rule_id: str
    rule_name: str
    severity: Literal["low", "medium", "high"]
    on_hit: LoadCheckOnHit
    entity_id: str
    entity_type: str
    entity_name: str


class CheckNotJudged(BaseModel):
    """A rule that applies at load but that a dry run cannot judge, and why, in words."""

    rule_id: str
    rule_name: str
    why: str


ALL_MODELS = (
    RuleVersion,
    RuleChangeRejection,
    RuleRun,
    RuleScheduleView,
    ListSchedule,
    ListScheduleInput,
    LoadCheck,
    LoadChecksInput,
    LoadCheckRule,
    LoadChecksView,
    WouldRaise,
    CheckNotJudged,
)
