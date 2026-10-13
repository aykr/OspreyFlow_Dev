"""The Admin area's shapes (`06_DECISIONS.md` ADR-110 Amendment 1, ADR-112): people and their roles,
and dashboard identities. Generated into TypeScript for the Glass's Admin area."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class PersonAccount(BaseModel):
    id: str
    username: str
    name: str
    enabled: bool
    roles: list[str]
    clearance: str | None = None
    org_unit: str | None = None
    email: str | None = None
    receivable_handling_codes: list[str] = Field(default_factory=list)
    #: Invited or reset, and not yet signed in to choose their own password.
    must_set_password: bool = False


#: A sign-in name the identity provider takes (measured: spaces and most punctuation are refused).
USERNAME_PATTERN = r"^[a-z0-9][a-z0-9._-]{1,62}$"
#: Enough to catch a slip; whether the address works is the mail server's to say.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class AccessInput(BaseModel):
    """What a person may see (ADR-114 Amendment 5): clearance, unit and the handling codes they may
    receive — none above the administrator's own."""

    clearance: str = Field(min_length=1, max_length=40)
    org_unit: str = Field(min_length=1, max_length=60)
    receivable_handling_codes: list[str] = Field(default_factory=list)

    @field_validator("receivable_handling_codes")
    @classmethod
    def _few_codes(cls, codes: list[str]) -> list[str]:
        # A bound, kept out of the field so the generated type stays a plain array.
        if len(codes) > 16:
            raise ValueError("at most 16 handling codes")
        return codes


class InviteInput(AccessInput):
    """A new person (ADR-114 Amendment 5): signed in by an emailed link when the deployment has a
    mail server, else by a one-time code shown once to the administrator."""

    username: str = Field(pattern=USERNAME_PATTERN)
    first_name: str = Field(default="", max_length=60)
    last_name: str = Field(default="", max_length=60)
    email: str | None = Field(default=None, pattern=EMAIL_PATTERN, max_length=254)
    roles: list[str] = Field(default_factory=list, max_length=64)


class SignInDelivery(BaseModel):
    """How the person signs in next: by the identity provider's own emailed link, or by the one-time
    code in this answer — shown once, never stored by OspreyFlow, changed at first sign-in."""

    person: PersonAccount
    delivery: Literal["email", "one_time_code"]
    one_time_code: str | None = None


class DashboardIdentity(BaseModel):
    client_id: str
    #: The identity's account id — what a case Author grants Viewer to.
    account_id: str
    clearance: str | None = None
    org_unit: str | None = None
    #: The handling codes the identity may receive — a viewer of its embedded board must hold
    #: every one (ADR-111 Amendment 3).
    receivable_handling_codes: list[str] = Field(default_factory=list)
    #: From the reporting mart (ADR-111 Amendment 2): when `report-sync` last truly pulled for this
    #: dashboard, its standing failure in words and when, and how many cases it pulls. Absent —
    #: never pulled — when reporting is off or the dashboard has no case yet.
    last_pulled: datetime | None = None
    last_failure: str | None = None
    failed_at: datetime | None = None
    cases_pulled: int = 0


class RegisteredDashboard(BaseModel):
    dashboard: DashboardIdentity
    #: Shown once, at registration; OspreyFlow keeps no copy.
    secret: str


class RolesInput(BaseModel):
    """A person's roles, set whole: the four roles, `right:<name>` grants, the old role names."""

    roles: list[str] = Field(max_length=64)


class DashboardInput(BaseModel):
    """A dashboard identity to register: a name, and the clearance and unit it reads with — no
    higher than the registering administrator's own clearance."""

    name: str = Field(min_length=1, max_length=60)
    clearance: str = Field(min_length=1)
    org_unit: str = Field(min_length=1)


class ComponentHealth(BaseModel):
    """One part of the running deployment, asked just now: whether it answered, and how fast."""

    name: str
    ok: bool
    millis: int = Field(ge=0)
    detail: str | None = None


class SystemStatus(BaseModel):
    """The Admin area's *System* screen (ADR-110 Amendment 1): each component, asked as the screen
    opens — what the harness's preflight showed before launch, for a running deployment."""

    version: str | None = None
    components: list[ComponentHealth]


class EmbeddedDashboard(BaseModel):
    """A Superset dashboard this person may open inside the Glass (ADR-111 Amendment 3)."""

    slug: str
    title: str


class DashboardGuestToken(BaseModel):
    """A short-lived, read-only Superset guest token for one embedded dashboard."""

    token: str
    #: The dashboard's embedded id, which the Glass's SDK mounts.
    uuid: str
    #: Where the browser reaches Superset.
    superset_origin: str


class DemoPackStatus(BaseModel):
    """A demo pack as the Admin area shows it (ADR-114 Amendment 5, "Show and explain"): what it
    shows, its licence and credit, whether it is loaded — only in a case the administrator can open
    — and the command that adds it on the host. The Conduit never runs it."""

    id: str
    title: str
    shows: str
    delivery: Literal["seed", "download"]
    licence: str
    attribution: str | None = None
    case_name: str
    loaded_case_id: str | None = None
    command: str
    source_page: str | None = None
    size_bytes: int | None = None


class ScheduleRunView(BaseModel):
    """One row of the run ledger as the Admin area shows it (ADR-110 decisions 6 and 8). Where the
    reader may not view the source, `withheld` is set and the counts and the failure's words are
    left out: a count of what a load wrote is a read (rule 3)."""

    run_id: str
    trigger: Literal["manual", "schedule", "watch", "release"]
    slot: datetime | None = None
    started_at: datetime
    finished_at: datetime | None = None
    outcome: Literal["running", "succeeded", "failed", "refused", "blocked", "skipped", "missed"]
    run_as: str
    withheld: bool = False
    rows_read: int | None = None
    nodes_created: int | None = None
    nodes_referenced: int | None = None
    edges_created: int | None = None
    rows_rejected: int | None = None
    rows_held: int | None = None
    load_id: str | None = None
    failure: str | None = None


class AdminSchedule(BaseModel):
    """A scheduled recipe in the Admin area's *Schedules and runs* (ADR-110 decision 8)."""

    recipe_id: str
    label: str
    case_id: str | None = None
    cron: str
    timezone: str
    #: The schedule in words: "every weekday at 06:00 (Europe/London)".
    schedule: str
    owner: str | None = None
    next_run: datetime | None = None
    paused: bool = False
    paused_reason: str | None = None
    #: The ontology changed since it was published: due slots are blocked until it is again.
    flagged: bool = False
    last_run: ScheduleRunView | None = None


class DataFeed(BaseModel):
    """A pipeline feeding a case's datasets, as the Glass's *Data feeds* shows it (ADR-110
    decision 9): how fresh the case's data is. `schedule` is `None` for a recipe run only by hand."""

    recipe_id: str
    label: str
    schedule: str | None = None
    next_run: datetime | None = None
    paused: bool = False
    flagged: bool = False
    last_run: ScheduleRunView | None = None


class ChangeScheduleInput(BaseModel):
    """The Admin area's *Change schedule* (ADR-110 Amendment 3): a new time, the owner kept."""

    cron: str
    timezone: str | None = None


class PauseScheduleInput(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


ALL_MODELS = [
    PersonAccount, DashboardIdentity, RegisteredDashboard, RolesInput, DashboardInput,
    ComponentHealth, SystemStatus, EmbeddedDashboard, DashboardGuestToken,
    AccessInput, InviteInput, SignInDelivery, DemoPackStatus,
    ScheduleRunView, AdminSchedule, PauseScheduleInput, DataFeed, ChangeScheduleInput,
]  # fmt: skip
