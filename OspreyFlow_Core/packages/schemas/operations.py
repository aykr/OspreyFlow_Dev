"""Operations and external orchestration (`06_DECISIONS.md` ADR-141; the redesign's phase 10).

The deployment's view of the run ledger (decisions 1–7), the run quotas (decision 6), and the
versioned run API an orchestrator drives through a thin client (decisions 9–14). Every count a run
read, staged or wrote is `None` with `withheld` set where the reader may not view one of the run's
markings (decision 7, ADR-110 decision 8): never a number the reader could not have counted.
**No account id is in any of these** (rule 7, ADR-106): a person is named by `*_name`, a service
identity by the client name the deployment's identity provider gives it.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

QuotaScope = Literal["dataset", "unit"]
#: The external run id an orchestrator sends (an Airflow `dag_id`/`run_id`): printable, bounded.
_EXTERNAL_RUN_ID = r"^[A-Za-z0-9][A-Za-z0-9._:+@/-]{0,254}$"
#: An OIDC client's name (Keycloak's `clientId`).
_CLIENT_ID = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"


class RunQuota(BaseModel):
    """A dataset's or a unit's quota (decision 6). `None` is no limit. A run past a quota is refused
    in words at the run path, whatever triggered it; `alert_at_share` of a quota raises the budget
    alert to the administrators first."""

    model_config = ConfigDict(extra="forbid")

    scope: QuotaScope
    key: str = Field(min_length=1, max_length=200)
    runs_per_day: int | None = Field(default=None, ge=1, le=100_000)
    alert_at_share: float = Field(default=0.8, gt=0, lt=1)


class RunQuotaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs_per_day: int | None = Field(default=None, ge=1, le=100_000)
    alert_at_share: float = Field(default=0.8, gt=0, lt=1)


class RunQuotaUse(BaseModel):
    """The quota as the Runs tab's bar shows it: today's runs against the limit."""

    model_config = ConfigDict(extra="forbid")

    quota: RunQuota | None = None
    runs_today: int = Field(ge=0)


class ExternallyOwnedInput(BaseModel):
    """*Owned externally* (decision 11): the one service identity that may trigger the pipeline
    (ADR-141 open question 1, taken per pipeline: the strict option), and the version it runs."""

    model_config = ConfigDict(extra="forbid")

    client_id: str = Field(pattern=_CLIENT_ID)


class ExternalRunInput(BaseModel):
    """`POST /v1/runs` (decision 9): start a run of one pipeline at a deployed version, or the
    latest deployed, keyed by the orchestrator's own run id (decision 12)."""

    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1, max_length=200)
    pipeline_id: str = Field(min_length=1, max_length=200)
    version: int | Literal["latest"] = "latest"
    external_run_id: str = Field(pattern=_EXTERNAL_RUN_ID)


ExternalRunOutcome = Literal["running", "succeeded", "failed", "refused"]


class ExternalRunStatus(BaseModel):
    """`GET /v1/runs/{run_id}`: a run's status, its report's counts and its held rows."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    pipeline_id: str
    version: int
    external_run_id: str
    outcome: ExternalRunOutcome
    started_at: datetime
    finished_at: datetime | None = None
    #: The refusal or failure in words; never a stack or an id.
    words: str | None = None
    #: True when this was the same external run id again: nothing more was loaded.
    already_recorded: bool = False
    rows_read: int | None = None
    rows_rejected: int | None = None
    rows_held: int | None = None
    graph_writes: int | None = None
    withheld: bool = False


TriggerName = Literal["manual", "schedule", "watch", "release", "source_refresh", "external"]


class RollupRow(BaseModel):
    """One day of one pipeline's runs by one trigger (decision 3)."""

    model_config = ConfigDict(extra="forbid")

    day: date
    pipeline_id: str
    pipeline_label: str
    dataset_id: str | None = None
    unit: str
    trigger: TriggerName
    runs: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    refused: int = Field(ge=0)
    failed: int = Field(ge=0)
    wall_ms: int = Field(ge=0)
    rows_read: int | None = None
    rows_staged: int | None = None
    graph_writes: int | None = None
    #: A count above is withheld: one of the day's runs wrote a marking the reader may not view.
    withheld: bool = False


class RefusalCount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    count: int = Field(ge=0)


class PausedPipeline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pipeline_id: str
    pipeline_label: str
    reason: str | None = None


class SchedulerHealth(BaseModel):
    """Decision 4: what the executor already records, counted over the window."""

    model_config = ConfigDict(extra="forbid")

    skipped: int = Field(ge=0)
    missed: int = Field(ge=0)
    refused: list[RefusalCount] = Field(default_factory=list)
    paused: list[PausedPipeline] = Field(default_factory=list)
    running_now: int = Field(ge=0)


class ExternalTrigger(BaseModel):
    """Decision 14: an external trigger, with its service identity, who it ran as, and its cost."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    pipeline_label: str
    service_identity: str
    ran_as_name: str
    started_at: datetime
    outcome: str
    wall_ms: int | None = None
    withheld: bool = False


class QuotaAlertView(BaseModel):
    """A budget alert (decision 6): a quota's day reached its alert share."""

    model_config = ConfigDict(extra="forbid")

    scope: QuotaScope
    key: str
    day: date
    words: str


class OperationsRollup(BaseModel):
    """`GET /v1/admin/operations/runs`: the window's days, newest first, the reader's unit's alone
    unless the reader administers the system (the redesign's phase 10 step 7)."""

    model_config = ConfigDict(extra="forbid")

    days: int = Field(ge=1, le=90)
    rows: list[RollupRow] = Field(default_factory=list)
    scheduler: SchedulerHealth
    external: list[ExternalTrigger] = Field(default_factory=list)
    quotas: list[RunQuota] = Field(default_factory=list)
    #: The budget alerts of those quotas in the window, newest first.
    alerts: list[QuotaAlertView] = Field(default_factory=list)
    #: The units read; one unless the reader administers the system.
    units: list[str] = Field(default_factory=list)


ALL_MODELS: list[type[BaseModel]] = [
    RunQuota,
    RunQuotaInput,
    RunQuotaUse,
    ExternallyOwnedInput,
    ExternalRunInput,
    ExternalRunStatus,
    RollupRow,
    RefusalCount,
    PausedPipeline,
    SchedulerHealth,
    ExternalTrigger,
    QuotaAlertView,
    OperationsRollup,
]
