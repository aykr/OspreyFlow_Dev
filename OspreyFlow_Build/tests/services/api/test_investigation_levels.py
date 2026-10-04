"""ADR-052 §8: the level each case route needs, as a table, and the check that no route is left
without one. The table is the specification; the app is compared against it in both directions,
so a new route with no declared level, or a declared level that drifts, fails here."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.routing import APIRoute
from services.api.app import (
    app,
    get_audit,
    get_investigations,
    get_principal,
)
from services.api.investigations import (
    AccessLevel,
    InsufficientAccessError,
    Investigation,
    InvestigationNotFoundError,
)

from schemas.domain import Principal

V, E, A = AccessLevel.VIEWER, AccessLevel.EDITOR, AccessLevel.AUTHOR
P = "/v1/investigations/{investigation_id}"

#: (method, path) -> the level the route needs. Reads, queries and previews need Viewer; anything
#: that changes the case needs Editor; branching and export need Editor (owner's rulings P1, P2).
NEEDS: dict[tuple[str, str], AccessLevel] = {
    ("GET", P): V,
    ("POST", P + "/branch"): E,
    # Closing or reopening a tab (ADR-084) changes only the caller's own strip, so Viewer suffices.
    ("PUT", P + "/tab"): V,
    ("POST", P + "/seed"): E,
    ("POST", P + "/expand"): E,
    ("POST", P + "/expand/preview"): V,
    ("DELETE", P + "/nodes"): E,
    ("GET", P + "/resolution/threshold"): V,
    ("PUT", P + "/resolution/threshold"): E,
    ("POST", P + "/resolution/link"): E,
    ("POST", P + "/resolution/split"): E,
    ("GET", P + "/resolution/explain/{cluster_id}"): V,
    ("POST", P + "/compute/{metric}"): V,
    ("POST", P + "/ingest/extract"): E,
    ("GET", P + "/ingest/candidates"): V,
    ("POST", P + "/ingest/candidates/{candidate_id}/accept"): E,
    ("POST", P + "/ingest/candidates/{candidate_id}/reject"): E,
    ("GET", P + "/dossier/documents/{document_id}"): V,
    ("GET", P + "/history"): V,
    ("POST", P + "/history/{step_id}"): E,
    ("POST", P + "/judgements"): E,
    ("GET", P + "/judgements"): V,
    ("POST", P + "/gaps"): E,
    ("GET", P + "/gaps"): V,
    ("POST", P + "/assumptions"): E,
    ("GET", P + "/assumptions"): V,
    # Link notes (ADR-075): reading is Viewer; adding, changing and removing a note changes the case.
    ("GET", P + "/links/{edge_id}/notes"): V,
    ("POST", P + "/links/{edge_id}/notes"): E,
    ("PUT", P + "/links/{edge_id}/notes/{note_id}"): E,
    ("DELETE", P + "/links/{edge_id}/notes/{note_id}"): E,
    # Changing a link (ADR-080) changes the case; reading a link's history is a read of it.
    ("POST", P + "/links/{edge_id}/change"): E,
    ("GET", P + "/links/{edge_id}/history"): V,
    ("GET", P + "/links/{edge_id}/events"): V,
    ("POST", P + "/links/{edge_id}/events/{event_id}/extract"): E,
    ("POST", P + "/links/{edge_id}/events/documents"): E,
    ("GET", P + "/documents/{document_id}/reader"): V,
    ("POST", P + "/links/{edge_id}/events/{event_id}/candidates/{candidate_id}/accept"): E,
    ("POST", P + "/export"): E,
    ("POST", P + "/sites"): E,
    ("GET", P + "/sites/{site_id}"): V,
    ("GET", P + "/sites/{site_id}/image"): V,
    ("PATCH", P + "/sites/{site_id}/control-points"): E,
    ("POST", P + "/sites/{site_id}/grid"): E,
    ("POST", P + "/ingest/recipes/{recipe_id}/run"): E,
    # Stage 2: naming, and reading and changing who holds what. Reading needs only Viewer because
    # everyone may see their own level; the handler shows the full list to an Author only.
    ("PATCH", P): A,
    ("DELETE", P): A,
    ("GET", P + "/access"): V,
    ("PUT", P + "/access"): A,
    ("PUT", P + "/access/grants/{account_id}"): A,
    ("DELETE", P + "/access/grants/{account_id}"): A,
    ("GET", P + "/access/history"): A,
}


def _declared_levels(route: APIRoute) -> set[AccessLevel]:
    found: set[AccessLevel] = set()

    def walk(dependant: object) -> None:
        for sub in dependant.dependencies:  # type: ignore[attr-defined]
            level = getattr(sub.call, "required_level", None)
            if level is not None:
                found.add(level)
            walk(sub)

    walk(route.dependant)
    return found


def _case_routes() -> dict[tuple[str, str], APIRoute]:
    routes: dict[tuple[str, str], APIRoute] = {}
    for route in app.routes:
        if isinstance(route, APIRoute) and "{investigation_id}" in route.path:
            for method in route.methods:
                routes[(method, route.path)] = route
    return routes


def test_every_case_route_is_in_the_table_and_every_table_row_is_a_route() -> None:
    assert set(_case_routes()) == set(NEEDS)


@pytest.mark.parametrize(("key", "need"), sorted(NEEDS.items(), key=lambda kv: kv[0]))
def test_each_route_declares_exactly_the_level_the_table_gives_it(
    key: tuple[str, str], need: AccessLevel
) -> None:
    assert _declared_levels(_case_routes()[key]) == {need}


def test_the_stream_route_is_not_an_http_route_and_is_covered_by_its_own_test() -> None:
    """The delta WebSocket is checked by `test_the_stream_needs_a_viewer_grant` below; it is not
    in `app.routes` as an `APIRoute`, which is why this table cannot see it."""
    assert all(path != P + "/stream" for _method, path in NEEDS)


# --- behaviour through the real dependency ---------------------------------------------------

_PRINCIPAL = Principal(id="bob", clearance="OFFICIAL", org_unit="unit-1")
_CASE = Investigation(
    id="inv-1",
    name="A case",
    created_at=datetime(2026, 1, 1, tzinfo=UTC),
    created_by="alice",
    owning_unit="unit-1",
)


class _LevelAwareInvestigations:
    """Holds one level for `bob` on `inv-1`, and applies it the way the real store does."""

    def __init__(self, held: AccessLevel | None) -> None:
        self.held = held
        self.asked: list[AccessLevel] = []

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        self.asked.append(need)
        if investigation_id != "inv-1" or self.held is None:
            raise InvestigationNotFoundError(investigation_id)
        if self.held.rank < need.rank:
            raise InsufficientAccessError(f"{need.value} needed")
        return _CASE


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


@pytest.fixture
def audit() -> _Audit:
    return _Audit()


def _client(held: AccessLevel | None, audit: _Audit):  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    store = _LevelAwareInvestigations(held)
    app.dependency_overrides[get_investigations] = lambda: store
    app.dependency_overrides[get_principal] = lambda: _PRINCIPAL
    app.dependency_overrides[get_audit] = lambda: audit
    return TestClient(app, raise_server_exceptions=False), store


@pytest.fixture(autouse=True)
def _clear_overrides():  # type: ignore[no-untyped-def]
    yield
    app.dependency_overrides.clear()


def test_a_viewer_can_read_a_case(audit: _Audit) -> None:
    client, _store = _client(AccessLevel.VIEWER, audit)

    response = client.get("/v1/investigations/inv-1")

    assert response.status_code == 200
    assert response.json()["name"] == "A case"


def test_a_viewer_is_refused_a_route_that_changes_the_case_with_a_403_and_an_audit_record(
    audit: _Audit,
) -> None:
    client, store = _client(AccessLevel.VIEWER, audit)

    response = client.post("/v1/investigations/inv-1/branch")

    assert response.status_code == 403
    assert store.asked == [AccessLevel.EDITOR]
    assert [r["action"] for r in audit.records] == ["access_denied"]


def test_an_account_with_no_level_gets_the_same_404_as_a_case_that_does_not_exist(
    audit: _Audit,
) -> None:
    no_grant, _ = _client(None, audit)
    unshared = no_grant.get("/v1/investigations/inv-1")
    missing, _ = _client(AccessLevel.AUTHOR, audit)  # replaces the shared app's overrides
    absent = missing.get("/v1/investigations/no-such-case")

    assert unshared.status_code == absent.status_code == 404
    assert unshared.json() == absent.json()


# --- the delta stream ----------------------------------------------------------------------


class _FakeSocket:
    def __init__(self, store: object, audit: _Audit) -> None:
        class _State:
            pass

        self.app = type("A", (), {"state": _State()})()
        self.app.state.investigations = store
        self.app.state.audit = audit
        self.closed_with: int | None = None
        self.accepted = False

    async def close(self, code: int) -> None:
        self.closed_with = code

    async def accept(self) -> None:
        self.accepted = True
        raise _Stop  # everything after the access check is out of scope here


class _Stop(Exception):
    pass


async def test_the_stream_needs_a_viewer_grant_and_closes_without_one(audit: _Audit) -> None:
    from unittest.mock import patch

    from services.api.app import stream

    no_grant = _LevelAwareInvestigations(None)
    socket = _FakeSocket(no_grant, audit)
    with patch("services.api.app._authenticate_websocket", return_value=_PRINCIPAL):
        await stream(socket, "inv-1")  # type: ignore[arg-type]
    assert no_grant.asked == [AccessLevel.VIEWER]
    assert socket.closed_with == 1008 and not socket.accepted

    viewer = _LevelAwareInvestigations(AccessLevel.VIEWER)
    socket = _FakeSocket(viewer, audit)
    with (
        patch("services.api.app._authenticate_websocket", return_value=_PRINCIPAL),
        pytest.raises(_Stop),
    ):
        await stream(socket, "inv-1")  # type: ignore[arg-type]
    assert viewer.asked == [AccessLevel.VIEWER] and socket.accepted
