"""The Reports Viewer's journey (`spec/06_DECISIONS.md` ADR-145 Amendment 4 decision 10; ADR-146
Amendment 2 point 3): from an alert on Home, a Reports Viewer reaches the case's *Figures* and the
boards behind it, **and nothing else** — never the alert's address, its detail, its evidence, or any
way to work it (rule 4: every read path gets an access-control test).

Over HTTP through the real app, as the real `get_principal` would give a Reports Viewer (the
override hands the routes the principal the token decodes to), with no stores: a route the role is
refused answers 403 from a check before anything is read; a route it may reach gets past its checks
and then meets a missing store (500) or a missing case (404), never a 403.

What a mistake would do, and the case that catches it:
- an alert's address, detail or evidence opened to the Reports Viewer —
  `test_a_reports_viewer_is_refused_every_way_into_an_alert`, red with the place's gate opened to
  all at its real call site (`test_the_refusals_are_the_gate_s_own`);
- the journey's two destinations refused, so the journey dead-ends —
  `test_a_reports_viewer_reaches_figures_and_the_boards`.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from schemas.domain import Principal

#: Where an alert row on the Reports Viewer's Home leads (*Open in its case*, *Open the dashboard*),
#: and Home's own list of the alerts.
REACHED = {
    "read_case_report": ("GET", "/v1/investigations/case-1/reports"),
    "list_embedded_dashboards": ("GET", "/v1/reports/dashboards"),
    "embedded_dashboard_guest_token": ("POST", "/v1/reports/dashboards/alert-board/guest-token"),
    "read_alert_queue": ("GET", "/v1/investigations/case-1/alert-queue"),
}
#: Every way into an alert itself: its address, its detail, its canvas, and working it.
REFUSED = {
    "open_alert_at_address": ("GET", "/v1/alerts/alert-1"),
    "explain_alert": ("GET", "/v1/investigations/case-1/alert-queue/alert-1"),
    "alert_canvas": ("POST", "/v1/investigations/case-1/alert-queue/alert-1/canvas"),
    "claim_alert": ("POST", "/v1/investigations/case-1/alert-queue/alert-1/claim"),
    "release_alert": ("POST", "/v1/investigations/case-1/alert-queue/alert-1/release"),
    "dispose_alert": ("POST", "/v1/investigations/case-1/alert-queue/alert-1/disposition"),
    "assign_alert": ("POST", "/v1/investigations/case-1/alert-queue/alert-1/assign"),
}


@pytest.fixture
def client() -> Iterator[TestClient]:
    from services.api.app import app, get_principal

    who = Principal(id="viewer-1", clearance="SECRET", org_unit="unit-1", roles=["reports_viewer"])
    app.dependency_overrides[get_principal] = lambda: who
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_principal, None)


def _ask(client: TestClient, method: str, path: str) -> tuple[int, str]:
    response = client.request(method, path, json={}, headers={"Authorization": "Bearer x"})
    return response.status_code, response.text


def test_the_paths_are_the_routes_named() -> None:
    """The table above names real routes at the paths it calls, so a renamed route cannot leave a
    row asking nothing."""
    from services.api.app import app

    names = {getattr(r, "endpoint", None).__name__ for r in app.routes if hasattr(r, "endpoint")}  # type: ignore[union-attr]
    assert set(REACHED) | set(REFUSED) <= names, (set(REACHED) | set(REFUSED)) - names


def test_a_reports_viewer_reaches_figures_and_the_boards(client: TestClient) -> None:
    stopped = {name: code for name, (method, path) in REACHED.items()
               if (code := _ask(client, method, path)[0]) == 403}  # fmt: skip
    assert stopped == {}, f"the journey's destinations refused the Reports Viewer: {stopped}"


def test_a_reports_viewer_is_refused_every_way_into_an_alert(client: TestClient) -> None:
    answered = {}
    for name, (method, path) in REFUSED.items():
        code, text = _ask(client, method, path)
        if code != 403 or not any(why in text for why in ("place_required", "right_required")):
            answered[name] = code
    assert answered == {}, f"a way into an alert answered the Reports Viewer: {answered}"


def test_the_refusals_are_the_gate_s_own(client: TestClient) -> None:
    """The red half: with the place's gate opened at its real call site (the dependency every
    route of Rules and Monitoring declares), the address and the detail are no longer refused by a
    check, so the case above would fail. Shown here so the case cannot pass for a reason it does
    not claim (rule 15)."""
    from services.api.app import app, require_rules_place

    app.dependency_overrides[require_rules_place] = lambda: None
    try:
        opened = {name for name, (method, path) in REFUSED.items()
                  if _ask(client, method, path)[0] != 403}  # fmt: skip
    finally:
        app.dependency_overrides.pop(require_rules_place, None)
    assert {"open_alert_at_address", "explain_alert"} <= opened
