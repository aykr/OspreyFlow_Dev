"""Superset dashboards inside the Glass (`06_DECISIONS.md` ADR-111 Amendment 3).

An embedded board shows figures counted for its dashboard identity, not for the viewer, so the
Conduit opens it only to someone who could count every one of them (rule 3). The routes run the real
`SupersetEmbedder` over a fake Superset that models Superset's refusals, not only its grants (rule 15):
a wrong service password is refused, an unknown dashboard is refused, and a guest token asked for
without a row-level rule is refused here so a missing restriction cannot pass unnoticed.

What a mistake would do, and the case that catches it:
- a viewer below the identity's clearance shown its figures — `test_a_lower_clearance_cannot_open_it`;
- a viewer lacking one of the identity's cases shown its figures — `test_missing_one_case_is_not_found`;
- a guest token without the identity's row restriction — `test_the_guest_token_is_limited_to_the_identitys_rows`;
- a refused service user swallowed — `test_a_refused_service_user_is_said`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_handling_scheme,
    get_identity_admin,
    get_investigations,
    get_principal,
    get_principal_names,
    get_superset_embedder,
)
from services.api.investigations import AccessLevel, Investigation
from services.api.superset_embed import SupersetEmbedder, SupersetSettings, may_open

from ontology.handling import load_uk_le_scheme
from schemas.admin import DashboardIdentity
from schemas.domain import Principal

CLASSES = list(load_uk_le_scheme().classification)
BOARD = DashboardIdentity(client_id="osprey-dashboard-compliance-board", account_id="sa-board",
                          clearance="OFFICIAL", org_unit="verify")  # fmt: skip
VIEWER = Principal(id="u-viewer", clearance="OFFICIAL", org_unit="verify", roles=["reports_viewer"])
LOW = Principal(id="u-low", clearance="PUBLIC", org_unit="verify", roles=["reports_viewer"])
NO_ROLE = Principal(id="u-none", clearance="SECRET", org_unit="verify", roles=[])


def _case(cid: str) -> Investigation:
    return Investigation(id=cid, name=cid, created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="x",
                         owning_unit="verify")  # fmt: skip


class _Cases:
    def __init__(self, by_principal: dict[str, list[str]]) -> None:
        self.by_principal = by_principal

    async def list_for(self, principal: Principal) -> list[tuple[Investigation, AccessLevel]]:
        return [(_case(c), AccessLevel.VIEWER) for c in self.by_principal.get(principal.id, [])]


#: What Admin › Dashboards lists: Keycloak's identity, unless a test registers Entra ID's.
LISTED: list[DashboardIdentity] = [BOARD]


class _Identities:
    async def list_dashboards(self) -> list[DashboardIdentity]:
        return list(LISTED)


class _Names:
    async def display_names(self, ids):  # type: ignore[no-untyped-def]
        return {}


class _Audit:
    async def record(self, **kwargs: Any) -> None:
        return None


class _Superset:
    """Superset's API as the embedder uses it, with its refusals."""

    def __init__(self) -> None:
        self.embedded: dict[int, dict[str, Any]] = {}
        self.guest_bodies: list[dict[str, Any]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/security/login":
            body = json.loads(request.content)
            if body.get("username") != "osprey-embedder" or body.get("password") != "right":
                return httpx.Response(401, json={"message": "Not authorized"})
            return httpx.Response(200, json={"access_token": "jwt"})
        if request.headers.get("Authorization") != "Bearer jwt":
            return httpx.Response(401, json={"msg": "Missing Authorization Header"})
        if path == "/api/v1/security/csrf_token/":
            return httpx.Response(200, json={"result": "csrf"})
        if request.method != "GET" and request.headers.get("X-CSRFToken") != "csrf":
            return httpx.Response(400, json={"message": "The CSRF token is missing."})
        if path == "/api/v1/dashboard/":
            return httpx.Response(200, json={"result": [
                {"id": 1, "slug": "compliance-board", "dashboard_title": "Compliance board"},
                {"id": 2, "slug": "unregistered", "dashboard_title": "Someone's scratch board"},
                {"id": 3, "slug": None, "dashboard_title": "No slug"}]})  # fmt: skip
        if path.startswith("/api/v1/dashboard/") and path.endswith("/embedded"):
            did = int(path.split("/")[4])
            if did not in (1, 2):
                return httpx.Response(404, json={"message": "Not found"})
            if request.method == "GET":
                found = self.embedded.get(did)
                return httpx.Response(200, json={"result": found}) if found else httpx.Response(404, json={"message": "Not found"})
            self.embedded[did] = {"uuid": f"uuid-{did}", **json.loads(request.content)}
            return httpx.Response(200, json={"result": self.embedded[did]})
        if path == "/api/v1/security/guest_token/":
            body = json.loads(request.content)
            if not body.get("rls"):
                return httpx.Response(400, json={"message": "this fake refuses an unrestricted token"})
            if body["resources"][0]["id"] not in {e["uuid"] for e in self.embedded.values()}:
                return httpx.Response(404, json={"message": "dashboard not embedded"})
            self.guest_bodies.append(body)
            return httpx.Response(200, json={"token": "guest-token"})
        return httpx.Response(404, json={"message": "Not found"})


@pytest.fixture
def superset() -> _Superset:
    return _Superset()


def _client(who: Principal, superset: _Superset, *, cases: dict[str, list[str]], password: str = "right") -> TestClient:
    settings = SupersetSettings("http://superset:8088", "http://localhost:8088", "http://localhost:8080", password)
    embedder = SupersetEmbedder(settings, transport=httpx.MockTransport(superset.handle))
    app.dependency_overrides.update({
        get_principal: lambda: who, get_superset_embedder: lambda: embedder,
        get_identity_admin: _Identities, get_investigations: lambda: _Cases(cases),
        get_handling_scheme: load_uk_le_scheme, get_principal_names: _Names, get_audit: _Audit,
    })  # fmt: skip
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear():  # type: ignore[no-untyped-def]
    yield
    app.dependency_overrides.clear()
    LISTED[:] = [BOARD]


def test_may_open_needs_everything_the_identity_counts() -> None:
    both = {"case-a", "case-b"}
    assert may_open(VIEWER, BOARD, classification=CLASSES, viewer_cases=both, identity_cases={"case-a"})
    assert not may_open(LOW, BOARD, classification=CLASSES, viewer_cases=both, identity_cases={"case-a"})
    other_unit = VIEWER.model_copy(update={"org_unit": "elsewhere"})
    assert not may_open(other_unit, BOARD, classification=CLASSES, viewer_cases=both, identity_cases={"case-a"})
    coded = BOARD.model_copy(update={"receivable_handling_codes": ["H2"]})
    assert not may_open(VIEWER, coded, classification=CLASSES, viewer_cases=both, identity_cases=set())
    assert not may_open(VIEWER, BOARD.model_copy(update={"clearance": None}), classification=CLASSES,
                        viewer_cases=both, identity_cases=set()), "an identity of unknown clearance is never opened"  # fmt: skip


def test_a_viewer_who_covers_the_identity_sees_and_opens_it(superset: _Superset) -> None:
    client = _client(VIEWER, superset, cases={"sa-board": ["aml"], "u-viewer": ["aml", "other"]})
    listed = client.get("/v1/reports/dashboards")
    assert listed.status_code == 200, listed.text
    assert listed.json() == [{"slug": "compliance-board", "title": "Compliance board"}], "unregistered boards are not offered"
    token = client.post("/v1/reports/dashboards/compliance-board/guest-token")
    assert token.status_code == 200, token.text
    assert token.json() == {"token": "guest-token", "uuid": "uuid-1", "superset_origin": "http://localhost:8088"}
    assert superset.embedded[1]["allowed_domains"] == ["http://localhost:8080"], "framed only by the Glass"


def test_the_guest_token_is_limited_to_the_identitys_rows(superset: _Superset) -> None:
    client = _client(VIEWER, superset, cases={"sa-board": ["aml"], "u-viewer": ["aml"]})
    client.post("/v1/reports/dashboards/compliance-board/guest-token")
    (body,) = superset.guest_bodies
    assert body["rls"] == [{"clause": "dashboard = 'osprey-dashboard-compliance-board'"}]
    assert body["user"]["username"] == "u-viewer"


def test_a_lower_clearance_cannot_open_it(superset: _Superset) -> None:
    client = _client(LOW, superset, cases={"sa-board": ["aml"], "u-low": ["aml"]})
    assert client.get("/v1/reports/dashboards").json() == []
    assert client.post("/v1/reports/dashboards/compliance-board/guest-token").status_code == 404
    assert superset.guest_bodies == []


def test_missing_one_case_is_not_found(superset: _Superset) -> None:
    client = _client(VIEWER, superset, cases={"sa-board": ["aml", "second"], "u-viewer": ["aml"]})
    assert client.get("/v1/reports/dashboards").json() == []
    assert client.post("/v1/reports/dashboards/compliance-board/guest-token").status_code == 404


def test_without_the_reports_right_it_is_refused(superset: _Superset) -> None:
    client = _client(NO_ROLE, superset, cases={"sa-board": [], "u-none": []})
    assert client.get("/v1/reports/dashboards").status_code == 403
    assert client.post("/v1/reports/dashboards/compliance-board/guest-token").status_code == 403


def test_a_refused_service_user_is_said(superset: _Superset) -> None:
    client = _client(VIEWER, superset, cases={"sa-board": ["aml"], "u-viewer": ["aml"]}, password="wrong")
    response = client.get("/v1/reports/dashboards")
    assert response.status_code == 502
    assert response.json()["error"] == "superset_refused" and "service user" in response.json()["detail"]


def test_not_configured_offers_nothing(superset: _Superset) -> None:
    _client(VIEWER, superset, cases={})
    app.dependency_overrides[get_superset_embedder] = lambda: None
    client = TestClient(app)
    assert client.get("/v1/reports/dashboards").json() == []
    assert client.post("/v1/reports/dashboards/compliance-board/guest-token").status_code == 404



# --- On Entra ID (ADR-148 Amendments 10 and 11, v0.5.2's step 5) ---------------------------------
#
# A dashboard identity is an Entra app registration: its client id and account id are its application
# id (a GUID), and its name, registered in Admin › Dashboards, is the board's slug. The report sync
# writes the mart under its client id, so the guest token's rows are that application id's.

APP_ID = "dddddddd-eeee-4fff-8000-111111111111"
ENTRA_BOARD = DashboardIdentity(client_id=APP_ID, account_id=APP_ID, name="compliance-board",
                                clearance="OFFICIAL", org_unit="verify")  # fmt: skip


def test_on_entra_a_board_is_its_identity_s_by_name_and_its_rows_the_application_s(superset: _Superset) -> None:
    LISTED[:] = [ENTRA_BOARD]
    client = _client(VIEWER, superset, cases={APP_ID: ["aml"], "u-viewer": ["aml", "other"]})
    assert client.get("/v1/reports/dashboards").json() == [{"slug": "compliance-board", "title": "Compliance board"}]
    token = client.post("/v1/reports/dashboards/compliance-board/guest-token")
    assert token.status_code == 200, token.text
    (body,) = superset.guest_bodies
    assert body["rls"] == [{"clause": f"dashboard = '{APP_ID}'"}]


def test_on_entra_an_identity_of_another_name_opens_no_board(superset: _Superset) -> None:
    LISTED[:] = [ENTRA_BOARD.model_copy(update={"name": "another-board"})]
    client = _client(VIEWER, superset, cases={APP_ID: ["aml"], "u-viewer": ["aml"]})
    assert client.get("/v1/reports/dashboards").json() == []
    assert client.post("/v1/reports/dashboards/compliance-board/guest-token").status_code == 404
    assert superset.guest_bodies == []


@pytest.mark.parametrize(
    ("who", "cases"),
    [(LOW, {APP_ID: ["aml"], "u-low": ["aml"]}), (VIEWER, {APP_ID: ["aml", "second"], "u-viewer": ["aml"]})],
    ids=["a-lower-clearance", "missing-one-of-its-cases"],
)
def test_on_entra_who_cannot_see_all_it_counts_is_not_shown_it(superset: _Superset, who: Principal, cases: dict[str, list[str]]) -> None:
    """Rule 4 on Entra ID: the identity's cases are read by its application id, as its token reads."""
    LISTED[:] = [ENTRA_BOARD]
    client = _client(who, superset, cases=cases)
    assert client.get("/v1/reports/dashboards").json() == []
    assert client.post("/v1/reports/dashboards/compliance-board/guest-token").status_code == 404
    assert superset.guest_bodies == []


def test_a_name_is_never_matched_through_another_identity_s_client_id(superset: _Superset) -> None:
    """An identity named on Entra ID is matched by its name alone: one whose name is another board's is
    not opened as the board its client id would name on Keycloak."""
    from services.api.superset_embed import identity_for

    keycloak_shaped = DashboardIdentity(client_id="osprey-dashboard-compliance-board", account_id="x",
                                        name="something-else")  # fmt: skip
    assert identity_for("compliance-board", [keycloak_shaped]) is None
    assert identity_for("compliance-board", [BOARD]) == BOARD  # Keycloak, no name stored
    assert identity_for("compliance-board", [ENTRA_BOARD]) == ENTRA_BOARD
