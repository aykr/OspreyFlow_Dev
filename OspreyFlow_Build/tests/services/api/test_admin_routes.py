"""The Admin area's routes (`06_DECISIONS.md` ADR-110 Amendment 1, ADR-112): people's roles and
dashboard identities, behind their rights, audited — and a dashboard can never read above the
clearance of the administrator who registers it (rule 3)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_graph,
    get_handling_scheme,
    get_identity_admin,
    get_investigations,
    get_principal,
    get_report_freshness,
    get_valkey,
)
from services.api.identity_admin import PersonExistsError, UnknownRoleError, allowed_role
from services.api.report_freshness import Freshness

from ontology.handling import load_uk_le_scheme
from schemas.admin import AccessInput, DashboardIdentity, InviteInput, PersonAccount, RegisteredDashboard, SignInDelivery
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

    # ADR-114 Amendment 5 (B4b)
    async def invite(self, invite: InviteInput) -> SignInDelivery:
        if invite.username == "taken":
            raise PersonExistsError("taken")
        if not all(allowed_role(r) for r in invite.roles):
            raise UnknownRoleError("not a role")
        self.made.append(("invite", invite.username))
        return SignInDelivery(person=PersonAccount(id="u-new", username=invite.username, name=invite.username,
                                                   enabled=True, roles=invite.roles, must_set_password=True),
                              delivery="one_time_code", one_time_code="ABCD-EFGH-JKLM-NPQR")  # fmt: skip

    async def set_access(self, user_id: str, access: AccessInput) -> PersonAccount:
        self.made.append(("access", user_id))
        return PersonAccount(id=user_id, username="x", name="x", enabled=True, roles=[], clearance=access.clearance)

    async def set_enabled(self, user_id: str, enabled: bool) -> PersonAccount:
        self.made.append(("enabled" if enabled else "disabled", user_id))
        return PersonAccount(id=user_id, username="x", name="x", enabled=enabled, roles=[])

    async def reset_sign_in(self, user_id: str) -> SignInDelivery:
        self.made.append(("reset", user_id))
        return SignInDelivery(person=PersonAccount(id=user_id, username="x", name="x", enabled=True, roles=[]),
                              delivery="one_time_code", one_time_code="WXYZ-WXYZ-WXYZ-WXYZ")  # fmt: skip

    async def list_dashboards(self) -> list[DashboardIdentity]:
        return [DashboardIdentity(client_id="osprey-dashboard-board", account_id="sa-1"),
                DashboardIdentity(client_id="osprey-dashboard-new", account_id="sa-2")]  # fmt: skip

    async def create_dashboard(self, name: str, *, clearance: str, org_unit: str) -> RegisteredDashboard:
        self.made.append((name, clearance))
        return RegisteredDashboard(dashboard=DashboardIdentity(client_id="osprey-dashboard-x", account_id="sa-1",
                                                               clearance=clearance, org_unit=org_unit), secret="s")  # fmt: skip


class _Freshness:
    async def by_dashboard(self) -> dict[str, Freshness]:
        from datetime import UTC, datetime

        return {"osprey-dashboard-board": Freshness(
            last_pulled=datetime(2026, 10, 11, 10, 24, tzinfo=UTC), last_failure="the feed was refused (403)",
            failed_at=datetime(2026, 10, 11, 10, 39, tzinfo=UTC), cases_pulled=2)}  # fmt: skip


@pytest.fixture
def client() -> Any:
    audit, identity = _Audit(), _Identity()
    app.dependency_overrides[get_report_freshness] = _Freshness
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


class _Broken:
    async def type_counts(self, principal: Principal) -> object:
        raise ConnectionError("graph store unreachable")


class _Fine:
    async def list_for(self, principal: Principal) -> list[object]:
        return []

    async def ping(self) -> bool:
        return True


def test_the_system_screen_says_which_component_failed_and_still_answers(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from services.api import readiness as readiness_module

    async def ready() -> object:
        return readiness_module.Readiness(ready=True, models=[])

    async def reachable() -> None:
        return None

    monkeypatch.setattr(readiness_module, "deployment_readiness", ready)
    client.identity.reachable = reachable
    app.dependency_overrides[get_graph] = _Broken
    app.dependency_overrides[get_investigations] = _Fine
    app.dependency_overrides[get_valkey] = _Fine
    _as(ADMIN)
    status = client.get("/v1/admin/system")
    assert status.status_code == 200, status.text
    by_name = {c["name"]: c for c in status.json()["components"]}
    assert by_name["Graph store"]["ok"] is False and "unreachable" in by_name["Graph store"]["detail"]
    assert all(c["ok"] for n, c in by_name.items() if n != "Graph store")
    _as(ANALYST)
    assert client.get("/v1/admin/system").status_code == 403


def test_the_dashboards_screen_says_how_fresh_each_feed_is_and_never_which_cases(client: Any) -> None:
    """ADR-111 Amendment 2: the Admin area sees a stale or failing feed; a dashboard never pulled
    says so by absence; no case identifier reaches the screen."""
    _as(ADMIN)
    response = client.get("/v1/admin/dashboards")
    assert response.status_code == 200, response.text
    board, new = response.json()
    assert board["last_pulled"].startswith("2026-10-11T10:24")
    assert (board["last_failure"], board["cases_pulled"]) == ("the feed was refused (403)", 2)
    assert (new["last_pulled"], new["last_failure"], new["cases_pulled"]) == (None, None, 0)
    assert "case_id" not in response.text



# --- ADR-114 Amendment 5 (B4b): invite, access, disable, enable, reset — behind manage_people ----

INVITE = {"username": "new.person", "first_name": "New", "last_name": "Person", "email": None,
          "clearance": "OFFICIAL", "org_unit": "verify", "receivable_handling_codes": [], "roles": ["analyst"]}  # fmt: skip
ACCESS = {"clearance": "OFFICIAL", "org_unit": "verify", "receivable_handling_codes": []}
ROUTES = [("post", "/v1/admin/people", INVITE), ("put", "/v1/admin/people/u1/access", ACCESS),
          ("post", "/v1/admin/people/u1/disable", None), ("post", "/v1/admin/people/u1/enable", None),
          ("post", "/v1/admin/people/u1/reset-sign-in", None)]  # fmt: skip


@pytest.mark.parametrize(("verb", "path", "body"), ROUTES)
def test_each_people_route_is_refused_without_manage_people(client: Any, verb: str, path: str, body: Any) -> None:
    _as(ANALYST)
    response = getattr(client, verb)(path, **({"json": body} if body is not None else {}))
    assert response.status_code == 403
    assert client.identity.made == [] and client.audit.records == []


def test_an_invitation_hands_the_code_over_once_and_never_into_the_audit(client: Any) -> None:
    _as(ADMIN)
    response = client.post("/v1/admin/people", json=INVITE)
    assert response.status_code == 201, response.text
    assert response.json()["one_time_code"] == "ABCD-EFGH-JKLM-NPQR"
    (record,) = client.audit.records
    assert record["action"] == "invite_person"
    assert "ABCD-EFGH-JKLM-NPQR" not in repr(record), "the code is the person's, never the log's"
    reset = client.post("/v1/admin/people/u1/reset-sign-in")
    assert reset.status_code == 200 and "WXYZ" not in repr(client.audit.records[-1])
    assert client.audit.records[-1]["action"] == "reset_person_sign_in"


def test_nobody_is_given_more_than_the_administrator_holds(client: Any) -> None:
    """The dashboard rule (rule 3) for people: inviting someone, or setting their access, above one's
    own clearance or with a handling code one cannot receive would be a way to read above it."""
    _as(ADMIN)
    above = client.post("/v1/admin/people", json={**INVITE, "clearance": "SECRET"})
    assert above.status_code == 403 and above.json()["detail"]["error"] == "above_your_clearance"
    codes = client.put("/v1/admin/people/u1/access", json={**ACCESS, "receivable_handling_codes": ["C"]})
    assert codes.status_code == 403 and codes.json()["detail"]["error"] == "handling_code_you_do_not_hold"
    unknown = client.put("/v1/admin/people/u1/access", json={**ACCESS, "clearance": "COSMIC"})
    assert unknown.status_code == 422
    assert client.identity.made == [], "refused before the identity provider was asked"
    fine = client.put("/v1/admin/people/u1/access", json=ACCESS)
    assert fine.status_code == 200 and client.audit.records[-1]["action"] == "set_person_access"


def test_an_administrator_cannot_disable_their_own_account(client: Any) -> None:
    _as(ADMIN)
    response = client.post(f"/v1/admin/people/{ADMIN.id}/disable")
    assert response.status_code == 409 and response.json()["detail"]["error"] == "cannot_disable_yourself"
    assert client.identity.made == []
    assert client.post("/v1/admin/people/u1/disable").json()["enabled"] is False
    assert client.post("/v1/admin/people/u1/enable").json()["enabled"] is True
    assert [r["action"] for r in client.audit.records] == ["disable_person", "enable_person"]


def test_a_name_already_held_is_a_conflict_said_in_words(client: Any) -> None:
    _as(ADMIN)
    response = client.post("/v1/admin/people", json={**INVITE, "username": "taken"})
    assert response.status_code == 409 and response.json()["error"] == "person_exists"
