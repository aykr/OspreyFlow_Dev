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
#: The routes about alerts the Reports Viewer is given (Home's list of the alerts on the cases they
#: can read; ADR-146 Amendment 2 point 3), and no other.
SHARED_WITH_THE_VIEWER = {"read_alert_queue", "read_alert_queue_counts"}


def _alert_routes() -> dict[str, tuple[str, str]]:
    """Every route of the app about an alert (its path names `alert`), but the shared ones: read
    from `app.routes`, so a route added beside this step (L2.10's) is held too."""
    import re

    from fastapi.routing import APIRoute
    from services.api.app import app

    found: dict[str, tuple[str, str]] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute) or "alert" not in route.path:
            continue
        if route.endpoint.__name__ in SHARED_WITH_THE_VIEWER:
            continue
        path = re.sub(r"\{[a-z_]+(:path)?\}", "x", route.path)
        found[route.endpoint.__name__] = (sorted(route.methods or {"GET"})[0], path)
    return found


#: The named ways into an alert the table must hold, so the derivation cannot quietly find none.
NAMED = {"open_alert_at_address", "explain_alert", "alert_canvas", "claim_alert", "release_alert",
         "dispose_alert", "assign_alert", "approve_alert_close", "send_back_alert_close",
         "get_alert_route", "list_alerts_route", "read_alert_assignees"}  # fmt: skip


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
    assert set(REACHED) <= names, set(REACHED) - names
    assert SHARED_WITH_THE_VIEWER <= names
    found = set(_alert_routes())
    assert len(found) >= len(NAMED) and not set(REACHED) & found
    assert NAMED <= found, NAMED - found


def test_a_reports_viewer_reaches_figures_and_the_boards(client: TestClient) -> None:
    stopped = {name: code for name, (method, path) in REACHED.items()
               if (code := _ask(client, method, path)[0]) == 403}  # fmt: skip
    assert stopped == {}, f"the journey's destinations refused the Reports Viewer: {stopped}"


def test_a_reports_viewer_is_refused_every_way_into_an_alert(client: TestClient) -> None:
    answered = {}
    for name, (method, path) in _alert_routes().items():
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
        opened = {name for name, (method, path) in _alert_routes().items()
                  if _ask(client, method, path)[0] != 403}  # fmt: skip
    finally:
        app.dependency_overrides.pop(require_rules_place, None)
    assert {"open_alert_at_address", "explain_alert"} <= opened


def test_the_reached_half_can_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """The red half of `test_a_reports_viewer_reaches_figures_and_the_boards`, planted where the
    rights are really given: the Reports Viewer's own role without `read_reports` is stopped at the
    Figures and the boards (and still reads Home's list, by `read_alert_queue`), so that case would
    report them."""
    from services.api.app import app, get_principal

    from schemas.rights import ROLE_RIGHTS, Right

    monkeypatch.setitem(
        ROLE_RIGHTS, "reports_viewer", ROLE_RIGHTS["reports_viewer"] - {Right.READ_REPORTS}
    )
    viewer = Principal(
        id="viewer-2", clearance="SECRET", org_unit="unit-1", roles=["reports_viewer"]
    )
    app.dependency_overrides[get_principal] = lambda: viewer
    try:
        client = TestClient(app, raise_server_exceptions=False)
        stopped = {
            name for name, (method, path) in REACHED.items() if _ask(client, method, path)[0] == 403
        }
    finally:
        app.dependency_overrides.pop(get_principal, None)
    assert stopped == set(REACHED) - {"read_alert_queue"}
