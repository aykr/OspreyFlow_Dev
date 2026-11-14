"""A principal admitted to named routes alone (`06_DECISIONS.md` ADR-148 Amendment 10).

Some principals are admitted to a few routes and no others: a dashboard identity on Entra ID to the
case list and the report feed. The resolver names them on the principal (`Principal.routes`, each
`"<METHOD> <path template>"`), and `get_principal`, which every route asking who is calling goes
through, refuses any other route with 403 `route_not_admitted`, before anything else is read.

Rule 12: `test_a_principal_admitted_to_named_routes_is_refused_every_other` asks every route of the
app that takes a principal (read from the app itself, so a route another lane adds is asked too)
through the real `get_principal`, only the resolver stood in for; each kind of such principal is one
row of `KINDS`, so a new kind is a row, not a test.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from principal_auth import DASHBOARD_ROUTES, SUPERSET_ROUTES
from schemas.domain import Principal

#: (kind, the routes it is admitted to); Superset's delegated sign-in (ADR-148 Am 9) is a row.
KINDS: list[tuple[str, frozenset[str]]] = [
    ("dashboard identity", DASHBOARD_ROUTES),
    # ADR-148 Amendment 9: a person's token issued to Superset, reading who they are alone.
    ("superset sign-in", SUPERSET_ROUTES),
]


class _Resolver:
    def __init__(self, principal: Principal) -> None:
        self.principal = principal

    async def resolve_principal(self, _token: str) -> Principal:
        return self.principal


def _takes_principal(dependant: Any) -> bool:
    from services.api.app import get_principal

    return any(
        d.call is get_principal or _takes_principal(d) for d in dependant.dependencies
    )


def _asked() -> list[tuple[str, str, str]]:
    """Every (method, path template, a path) of the app whose route asks who is calling."""
    from services.api.app import app

    asked = []
    for route in app.routes:
        if isinstance(route, APIRoute) and _takes_principal(route.dependant):
            path = re.sub(r"\{[a-z_]+(:path)?\}", "x", route.path)
            asked += [(method, route.path, path) for method in sorted(route.methods or {"GET"})]
    return asked


@pytest.fixture
def as_principal() -> Iterator[Any]:
    from services.api.app import app

    before = getattr(app.state, "principal_resolver", None)

    def client_for(principal: Principal) -> TestClient:
        app.state.principal_resolver = _Resolver(principal)
        return TestClient(app, raise_server_exceptions=False)

    try:
        yield client_for
    finally:
        app.state.principal_resolver = before


def _gate_refused(client: TestClient, method: str, path: str) -> bool:
    response = client.request(method, path, json={}, headers={"Authorization": "Bearer x"})
    return response.status_code == 403 and "route_not_admitted" in response.text


@pytest.mark.parametrize(("kind", "routes"), KINDS, ids=[kind for kind, _ in KINDS])
def test_a_principal_admitted_to_named_routes_is_refused_every_other(
    kind: str, routes: frozenset[str], as_principal: Any
) -> None:
    asked = _asked()
    assert len(asked) > 200
    assert routes <= {f"{method} {template}" for method, template, _ in asked}, (
        f"{kind}: a route it is admitted to is not a route of the app"
    )
    principal = Principal(
        id="00000000-0000-4000-8000-000000000001", clearance="SECRET", org_unit="unit-1",
        roles=["reports_viewer"], routes=sorted(routes),
    )  # fmt: skip
    client = as_principal(principal)
    wrong = [
        f"{method} {template}"
        for method, template, path in asked
        if _gate_refused(client, method, path) == (f"{method} {template}" in routes)
    ]
    assert wrong == [], f"{kind}: the gate answered wrongly at {wrong}"


def test_a_principal_with_no_routes_named_is_never_refused_by_the_gate(as_principal: Any) -> None:
    person = Principal(
        id="00000000-0000-4000-8000-000000000002", clearance="SECRET", org_unit="unit-1",
        roles=["analyst"],
    )  # fmt: skip
    client = as_principal(person)
    refused = [f"{m} {t}" for m, t, path in _asked() if _gate_refused(client, m, path)]
    assert refused == []


@pytest.mark.parametrize(("kind", "routes"), KINDS, ids=[kind for kind, _ in KINDS])
def test_a_principal_admitted_to_named_routes_never_opens_a_case_stream(
    kind: str, routes: frozenset[str], as_principal: Any
) -> None:
    """The delta socket asks no `get_principal`, so the gate is its own: a principal admitted to
    named routes alone is closed 1008 before its case is read or the socket accepted (the lane
    review of 009a889). A person is still read as before."""
    from services.api.app import app
    from services.api.investigations import InsufficientAccessError
    from starlette.websockets import WebSocketDisconnect

    read: list[str] = []

    class _Cases:
        async def get_authorized(self, investigation_id: str, principal: Any, **_: Any) -> Any:
            read.append(principal.id)
            raise InsufficientAccessError(investigation_id)

    class _Audit:
        async def record(self, **_: Any) -> None:
            return None

    saved = {k: getattr(app.state, k, None) for k in ("investigations", "audit", "people_store")}
    app.state.investigations, app.state.audit, app.state.people_store = _Cases(), _Audit(), None
    try:
        for principal, admitted in (
            (Principal(id="dash", clearance="SECRET", org_unit="u", roles=["reports_viewer"],
                       routes=sorted(routes)), False),  # fmt: skip
            (Principal(id="person", clearance="SECRET", org_unit="u", roles=["analyst"]), True),
        ):
            client = as_principal(principal)
            with pytest.raises(WebSocketDisconnect) as closed:
                with client.websocket_connect(
                    "/v1/investigations/case-1/stream", headers={"Authorization": "Bearer x"}
                ) as socket:
                    socket.receive_json()
            assert closed.value.code == 1008
            assert (principal.id in read) is admitted, f"{kind}: {principal.id}'s case was read"
    finally:
        for key, value in saved.items():
            setattr(app.state, key, value)
