"""The Reports Viewer's journey (`spec/06_DECISIONS.md` ADR-145 Amendment 4 decision 10; ADR-146
Amendment 2 point 3): from an alert on Home, a Reports Viewer reaches the case's *Figures* and the
boards behind it, **and nothing else** — never the alert's address, its detail, its evidence, or any
way to work it (rule 4: every read path gets an access-control test).

Over HTTP through the real app, as the real `get_principal` would give a Reports Viewer (the
override hands the routes the principal the token decodes to). A route the role is refused answers
403 from a check before anything is read, so the refusals need no stores. The journey's destinations
are asked with stores enough to run the case's own level check (`_authorized_at`, through a case
store that gives the viewer a Viewer's level on `case-1` and nothing on any other case) and the
report and the queue behind it, so each must answer the 200 it really gives.

What a mistake would do, and the case that catches it:
- an alert's address, detail or evidence opened to the Reports Viewer —
  `test_a_reports_viewer_is_refused_every_way_into_an_alert`, red with the place's gate opened to
  all at its real call site (`test_the_refusals_are_the_gate_s_own`);
- anything beyond decision 10's list reachable, on any route of the app, not only an alert's —
  `test_a_reports_viewer_is_refused_every_route_beyond_its_rights`, red with one right more given
  where roles get their rights (`test_the_sweep_finds_a_right_given_beyond_the_list`);
- the journey's destinations refused or failing, so the journey dead-ends —
  `test_a_reports_viewer_reaches_figures_and_the_boards`, each a 200; red with the role short of
  `read_reports` (`test_the_reached_half_can_fail`) and with the case store refusing the viewer
  (`test_the_reached_half_sees_the_case_s_refusal`).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from schemas.domain import Principal

#: Where an alert row on the Reports Viewer's Home leads (*Open in its case* reads the case's
#: Figures; *Open the dashboard* lists the boards and draws the Alert monitoring board from the same
#: Figures, asking Superset for nothing), and Home's own list of the alerts and its counts.
REACHED = {
    "read_case_report": ("GET", "/v1/investigations/case-1/reports"),
    "list_embedded_dashboards": ("GET", "/v1/reports/dashboards"),
    "read_alert_queue": ("GET", "/v1/investigations/case-1/alert-queue"),
    "read_alert_queue_counts": ("GET", "/v1/investigations/case-1/alert-queue/counts"),
}
#: Decision 10's list, as rights: the Reports Viewer's own, written here and not read from
#: `rights.py`, so a right added to the role there is caught by the sweep below.
VIEWER_RIGHTS = {"read_alert_queue", "read_reports", "read_report_feed", "read_data_feeds"}
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


class _Cases:
    """The case store as the real one answers a level check: a Viewer's level on `case-1` for the
    viewer, and for anyone else or any other case the same `InvestigationNotFoundError`."""

    def __init__(self, viewer: str, *, refuse: bool = False) -> None:
        self.viewer, self.refuse = viewer, refuse

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: Any
    ) -> Any:
        from services.api.investigations import (
            AccessLevel,
            Investigation,
            InvestigationNotFoundError,
        )

        if self.refuse or investigation_id != "case-1" or principal.id != self.viewer:
            raise InvestigationNotFoundError(investigation_id)
        if need.rank > AccessLevel.VIEWER.rank:
            from services.api.investigations import InsufficientAccessError

            raise InsufficientAccessError(investigation_id)
        return Investigation(id="case-1", name="Case", created_at=datetime(2026, 1, 1, tzinfo=UTC),
                             created_by="alice", owning_unit="unit-1", domains=[])  # fmt: skip

    async def effective_level(self, investigation_id: str, principal: Principal) -> Any:
        """As the real store: a level only where `get_authorized` gives one, else none."""
        from services.api.investigations import AccessLevel

        given = not self.refuse and investigation_id == "case-1" and principal.id == self.viewer
        return AccessLevel.VIEWER if given else None

    async def list_for(self, principal: Principal) -> list[Any]:
        return []


class _Nothing:
    """Every store the report and the queue read past the case's check, answering empty."""

    async def record(self, *args: object, **kwargs: object) -> None:
        return None

    async def chosen_of_case(self, investigation_id: str) -> list[Any]:
        return []

    async def list_dashboards(self) -> list[Any]:
        return []

    async def display_names(self, ids: list[str]) -> dict[str, str]:
        return {}

    async def type_counts(self, principal: Principal) -> Any:
        from schemas.explore import TypeCounts

        return TypeCounts(nodes={}, edges={}, computed_at=datetime(2026, 11, 9, tzinfo=UTC))


def _journey_client(
    monkeypatch: pytest.MonkeyPatch,
    viewer: Principal,
    *,
    refuse: bool = False,
    rows: Sequence[Any] = (),
) -> TestClient:
    from types import SimpleNamespace

    from services.api import alert_queue, reports
    from services.api.app import (
        app,
        get_alerts_store,
        get_analytics,
        get_audit,
        get_compute,
        get_datasets,
        get_explore,
        get_export_ledger,
        get_graph,
        get_handling_scheme,
        get_held_rows,
        get_identity_admin,
        get_investigations,
        get_ontology,
        get_principal,
        get_principal_names,
        get_superset_embedder,
        get_target_models,
    )  # fmt: skip
    from services.api.explore import ExploreService

    from ontology.packs import load_deployment_ontology

    async def _queue(*args: object, **kwargs: object) -> list[Any]:
        return list(rows)

    monkeypatch.setattr(alert_queue, "monitoring_queue", _queue)
    monkeypatch.setattr(reports, "monitoring_queue", _queue)
    nothing = _Nothing()
    for dep in (get_alerts_store, get_analytics, get_audit, get_compute, get_datasets, get_export_ledger, get_graph,
                get_held_rows, get_identity_admin, get_principal_names, get_target_models):  # fmt: skip
        app.dependency_overrides[dep] = lambda: nothing
    explore = ExploreService(nothing, None)  # type: ignore[arg-type]
    ontology = load_deployment_ontology()
    app.dependency_overrides[get_explore] = lambda: explore
    app.dependency_overrides[get_ontology] = lambda: ontology
    app.dependency_overrides[get_handling_scheme] = lambda: SimpleNamespace(classification=[])
    app.dependency_overrides[get_superset_embedder] = lambda: None
    app.dependency_overrides[get_investigations] = lambda: _Cases(viewer.id, refuse=refuse)
    app.dependency_overrides[get_principal] = lambda: viewer
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def journey(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    from services.api.app import app

    yield lambda viewer, refuse=False: _journey_client(monkeypatch, viewer, refuse=refuse)
    app.dependency_overrides.clear()


VIEWER = Principal(id="viewer-1", clearance="SECRET", org_unit="unit-1", roles=["reports_viewer"])


def _reached(client: TestClient) -> dict[str, tuple[int, str]]:
    return {name: (r.status_code, r.text[:200]) for name, (method, path) in REACHED.items()
            if (r := client.request(method, path, headers={"Authorization": "Bearer x"})).status_code != 200}  # fmt: skip


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


def test_a_reports_viewer_reaches_figures_and_the_boards(journey: Any) -> None:
    """Each destination answers its 200, past the right, the case's own level check and the read."""
    client = journey(VIEWER)
    assert _reached(client) == {}, "the journey's destinations did not answer the Reports Viewer"
    # The level check is the real one at work, not waved through: another case is the same 404.
    assert client.get("/v1/investigations/case-2/reports").status_code == 404


def test_the_reached_half_sees_the_case_s_refusal(journey: Any) -> None:
    """The red half for the case's level check: the case store refusing the viewer, as the real one
    does for a case they hold no level on, is a 404 the case above reports (it counted any non-403
    as reached before)."""
    failed = _reached(journey(VIEWER, refuse=True))
    assert {n for n, (code, _) in failed.items() if code == 404} == set(REACHED) - {
        "list_embedded_dashboards"
    }


#: The routes that name no right, each open to any signed-in person (the case's level still asked
#: where the path names a case): reads of reference data, the reader's own case list and views, and
#: two that are the reader's own (`set_tab_state`, a tab's state; `issue_ws_ticket`, a connection
#: ticket). `get_grading_scheme_route` (L3.7, ADR-143 decision 11) weighed at L2.12's rebase on
#: 9 November: the deployment's grading scheme, reference settings as the yardstick is, no record's
#: content, so the Reports Viewer reading it is within decision 10. Pinned, so a route added with no
#: right, or a right taken off one, fails here until it is weighed against decision 10 (rule 12: the
#: sweep below cannot see a route that names nothing).
OPEN_TO_ANY_SIGNED_IN = {
    "list_datasets_route", "case_datasets_route", "list_investigations", "set_tab_state",
    "get_investigation", "list_case_views", "open_case_view", "readiness_route", "liveness_route",
    "openapi_document_route", "get_ontology_route", "get_map_providers_route", "get_map_tile_route",
    "get_map_local_source_route", "list_connectors", "list_domain_packs", "get_handling_scheme_route",
    "get_yardstick_route", "get_grading_scheme_route", "list_transforms", "my_rights_route",
    "model_engines_route", "case_model_engines_route", "issue_ws_ticket",
} | {
    # L3.4 (ADR-143 Amendment 2 decision 1), weighed at its independent review on 9 November: a
    # removed case's layers listed, and a merge sheet read again through its own grant. Reads by
    # one of the dataset's Authors alone: owning a dataset needs no right (ADR-145 Amendment 4
    # decision 3), and the dataset's own gate (404 to a person none of whose cases loads into it)
    # and Author level on its home case ask instead. Their writes (opening a merge, merging,
    # cancelling, deleting and its dry run) name `investigate`, which a Reports Viewer does not hold
    # (ADR-112: refused every write); `test_promotions.py`'s
    # `test_a_reports_viewer_who_is_an_author_writes_nothing_to_a_removed_cases_layer`.
    "removed_case_layers", "read_layer_merge",
}  # fmt: skip


def _routes_by_right() -> dict[str, tuple[str, str, str | None]]:
    """Every route of the app with the right it declares, read from the app itself (the same
    reading `test_route_rights.py`'s `_declared` makes), not from a table."""
    import re

    from fastapi.routing import APIRoute
    from services.api.app import app

    from tests.services.api.test_route_rights import _declared

    found: dict[str, tuple[str, str, str | None]] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = re.sub(r"\{[a-z_]+(:path)?\}", "x", route.path)
        found[route.endpoint.__name__] = (
            sorted(route.methods or {"GET"})[0],
            path,
            _declared(route),
        )
    return found


def _guarded_routes() -> dict[str, tuple[str, str, str]]:
    """Every route of the app that names a right, with that right."""
    return {name: (m, p, r) for name, (m, p, r) in _routes_by_right().items() if r is not None}


def test_every_route_naming_no_right_is_one_weighed_for_the_viewer() -> None:
    """The other half of "and nothing else": the routes the sweep cannot ask by a right. Each route
    that names none is one of the list above, and all of them read or are the reader's own."""
    rightless = {name for name, (_, _, right) in _routes_by_right().items() if right is None}
    assert rightless == OPEN_TO_ANY_SIGNED_IN, (
        f"named no right, not weighed: {sorted(rightless - OPEN_TO_ANY_SIGNED_IN)}; "
        f"weighed, now naming one or gone: {sorted(OPEN_TO_ANY_SIGNED_IN - rightless)}"
    )
    writes = {
        name
        for name, (method, _, right) in _routes_by_right().items()
        if right is None and method != "GET"
    }
    assert writes == {"set_tab_state", "issue_ws_ticket"}


def _answered_beyond(client: TestClient) -> dict[str, int]:
    answered = {}
    for name, (method, path, right) in _guarded_routes().items():
        if right in VIEWER_RIGHTS:
            continue
        code, text = _ask(client, method, path)
        if code != 403 or not any(why in text for why in ("place_required", "right_required")):
            answered[name] = code
    return answered


def test_a_reports_viewer_is_refused_every_route_beyond_its_rights(client: TestClient) -> None:
    """Decision 10's "and nothing else", over every route of the app that names a right (read from
    the app's own declarations, so a route another lane adds is asked too): each whose right is not
    on the Reports Viewer's list answers 403 with `right_required` or `place_required`, the right's
    own refusal, not some other 403. The routes naming no right are the pin above
    (`test_every_route_naming_no_right_is_one_weighed_for_the_viewer`); those whose path names a
    case still ask its level, which `test_route_rights.py` and `test_investigation_levels.py` hold."""
    routes = _guarded_routes()
    assert len(routes) > 200 and {"deploy_typology_rule", "claim_alert"} <= set(routes)
    from schemas.rights import ROLE_RIGHTS

    assert {r.value for r in ROLE_RIGHTS["reports_viewer"]} == VIEWER_RIGHTS
    assert _answered_beyond(client) == {}


def test_the_sweep_finds_a_right_given_beyond_the_list(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The red half, planted where roles get their rights: the Reports Viewer given `triage_alerts`
    is let through at the triage routes, which the sweep above reports."""
    from schemas.rights import ROLE_RIGHTS, Right

    monkeypatch.setitem(
        ROLE_RIGHTS, "reports_viewer", ROLE_RIGHTS["reports_viewer"] | {Right.TRIAGE_ALERTS}
    )
    assert {"claim_alert", "dispose_alert"} <= set(_answered_beyond(client))


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
    assert stopped == set(REACHED) - {"read_alert_queue", "read_alert_queue_counts"}


def test_neither_feed_format_carries_the_reader_s_own_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The orchestrator's review, item 8: a board pulls the feed as its dashboard identity, so the
    team view's *mine* stays in the Glass, in the JSON feed (the default) as in the CSV. The reader's
    own Figures still carry it. Red: the JSON feed answered the figures whole."""
    from schemas.domain import Alert, AlertMode, QueuedAlert

    from services.api.app import app

    claimed = Alert(id="a-1", rule_id="typology:r", owner_id="raiser", mode=AlertMode.FULL,
                    created_at=datetime.now(UTC), typology="structuring", status="claimed",
                    assignee=VIEWER.id)  # fmt: skip
    rows = [QueuedAlert(alert=claimed, summary="", kind="typology")]
    try:
        client = _journey_client(monkeypatch, VIEWER, rows=rows)
        view = client.get("/v1/investigations/case-1/reports")
        assert view.status_code == 200, view.text
        assert [t["mine"] for t in view.json()["monitoring"]["team"]] == [1]
        as_json = client.get("/v1/investigations/case-1/reports/feed")
        assert as_json.status_code == 200, as_json.text
        team = as_json.json()["monitoring"]["team"]
        assert team and all("mine" not in t for t in team), team
        as_csv = client.get("/v1/investigations/case-1/reports/feed?format=csv")
        assert as_csv.status_code == 200 and "team_unassigned" in as_csv.text
        assert "team_mine" not in as_csv.text
    finally:
        app.dependency_overrides.clear()
