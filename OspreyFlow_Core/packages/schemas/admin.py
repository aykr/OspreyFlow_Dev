"""The Admin area's shapes (`06_DECISIONS.md` ADR-110 Amendment 1, ADR-112): people and their roles,
and dashboard identities. Generated into TypeScript for the Glass's Admin area."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
    receivable_handling_codes: list[str] = Field(default_factory=list, max_length=16)


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


ALL_MODELS = [
    PersonAccount, DashboardIdentity, RegisteredDashboard, RolesInput, DashboardInput,
    ComponentHealth, SystemStatus, EmbeddedDashboard, DashboardGuestToken,
    AccessInput, InviteInput, SignInDelivery,
]  # fmt: skip
