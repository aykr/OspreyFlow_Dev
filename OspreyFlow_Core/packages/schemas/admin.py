"""The Admin area's shapes (`06_DECISIONS.md` ADR-110 Amendment 1, ADR-112): people and their roles,
and dashboard identities. Generated into TypeScript for the Glass's Admin area."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PersonAccount(BaseModel):
    id: str
    username: str
    name: str
    enabled: bool
    roles: list[str]
    clearance: str | None = None
    org_unit: str | None = None


class DashboardIdentity(BaseModel):
    client_id: str
    #: The identity's account id — what a case Author grants Viewer to.
    account_id: str
    clearance: str | None = None
    org_unit: str | None = None


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


ALL_MODELS = [PersonAccount, DashboardIdentity, RegisteredDashboard, RolesInput, DashboardInput]
