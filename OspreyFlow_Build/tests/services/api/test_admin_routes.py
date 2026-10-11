"""The Admin area's routes (`06_DECISIONS.md` ADR-110 Amendment 1, ADR-112): people's roles and
dashboard identities, behind their rights, audited — and a dashboard can never read above the
clearance of the administrator who registers it (rule 3)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import app, get_audit, get_handling_scheme, get_identity_admin, get_principal
from services.api.identity_admin import UnknownRoleError, allowed_role

from ontology.handling import load_uk_le_scheme
from schemas.admin import DashboardIdentity, PersonAccount, RegisteredDashboard
from schemas.domain import Principal

ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="verify", roles=["osprey-admin"])
ANALYST = Principal(id="analyst-1", clearance="SECRET", org_unit="verify", roles=["analyst"])


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


class _Identity:
    def __init__(self) -> None:
        self.made: list[tuple[str, str]] = []

    async def list_people(self) -> list[PersonAccount]:
        return [PersonAccount(id="u1", username="osprey-demo-analyst", name="Demo Analyst", enabled=True, roles=["analyst"])]

    async def set_roles(self, user_id: str, roles: list[str]) -> PersonAccount:
        if not all(allowed_role(r) for r in roles):
            raise UnknownRoleError("not a role")
        return PersonAccount(id=user_id, username="x", name="x", enabled=True, roles=roles)

    async def create_dashboard(self, name: str, *, clearance: str, org_unit: str) -> RegisteredDashboard:
        self.made.append((name, clearance))
        return RegisteredDashboard(dashboard=DashboardIdentity(client_id="osprey-dashboard-x", account_id="sa-1",
                                                               clearance=clearance, org_unit=org_unit), secret="s")  # fmt: skip


@pytest.fixture
def client() -> Any:
    audit, identity = _Audit(), _Identity()
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_identity_admin] = lambda: identity
    app.dependency_overrides[get_handling_scheme] = load_uk_le_scheme
    test_client = TestClient(app)
    test_client.audit, test_client.identity = audit, identity  # type: ignore[attr-defined]
    yield test_client
    app.dependency_overrides.clear()


def _as(who: Principal) -> None:
    app.dependency_overrides[get_principal] = lambda: who


def test_an_administrator_sets_roles_and_the_change_is_audited(client: Any) -> None:
    _as(ADMIN)
    response = client.put("/v1/admin/people/u1/roles", json={"roles": ["analyst", "reports_viewer"]})
    assert response.status_code == 200, response.text
    assert response.json()["roles"] == ["analyst", "reports_viewer"]
    assert [r["action"] for r in client.audit.records] == ["set_person_roles"]


def test_realm_administration_is_not_a_role_that_can_be_handed_out(client: Any) -> None:
    _as(ADMIN)
    response = client.put("/v1/admin/people/u1/roles", json={"roles": ["realm-admin"]})
    assert response.status_code == 422 and response.json()["error"] == "not_allowed"


def test_an_analyst_is_refused_the_admin_area(client: Any) -> None:
    _as(ANALYST)
    assert client.get("/v1/admin/people").status_code == 403
    assert client.post("/v1/admin/dashboards", json={"name": "b", "clearance": "OFFICIAL", "org_unit": "verify"}).status_code == 403


def test_a_dashboard_cannot_read_above_its_registrars_clearance(client: Any) -> None:
    _as(ADMIN)
    above = client.post("/v1/admin/dashboards", json={"name": "b", "clearance": "SECRET", "org_unit": "verify"})
    assert above.status_code == 403 and above.json()["detail"]["error"] == "dashboard_above_your_clearance"
    assert client.identity.made == [], "refused before the identity provider was asked"
    made = client.post("/v1/admin/dashboards", json={"name": "Board", "clearance": "OFFICIAL", "org_unit": "verify"})
    assert made.status_code == 201 and made.json()["secret"] == "s"
    assert client.identity.made == [("Board", "OFFICIAL")]
