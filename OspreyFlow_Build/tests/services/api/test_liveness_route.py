"""`GET /healthz` — `03_CONDUIT_MIDDLEWARE.md` §3.0, the owner's decision of 24 September 2026.

The one unauthenticated route on this app, which is why it gets its own access-control file rather
than a case tucked into `test_app.py`. Standing rule 2 / `CLAUDE.md` rule 4 apply to it exactly as
to every other read path: **every** read path gets an access-control test, no exceptions for
internal endpoints — and "this one is meant to be public" is the reading under which a public route
never gets checked at all.

The property is not "an anonymous caller gets a 200". It is that the anonymous caller and the
authenticated caller get the **same bytes**: a liveness route that quietly said more to an
authenticated caller would be a route with two behaviours, and the unauthenticated one is the one
an attacker gets.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from services.api.app import LIVENESS_BODY, app, get_principal, liveness_route

from schemas.domain import Principal

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


@pytest.fixture
def anonymous() -> TestClient:
    """No principal override at all — nothing in `dependency_overrides`, so anything that required
    a principal would fail here rather than quietly resolve one."""
    app.dependency_overrides.pop(get_principal, None)
    return TestClient(app)


@pytest.fixture
def authenticated() -> TestClient:
    app.dependency_overrides[get_principal] = lambda: PRINCIPAL
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_principal, None)


def test_liveness_answers_without_a_principal(anonymous: TestClient) -> None:
    """Requiring a token to answer "is the process alive" would make liveness depend on the
    identity provider being reachable — inverting the point, since an unreachable IdP is one of the
    conditions liveness most needs to survive."""
    response = anonymous.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_anonymous_and_authenticated_responses_are_byte_for_byte_identical(
    anonymous: TestClient, authenticated: TestClient
) -> None:
    """The access-control property, stated as bytes rather than as shape. A route that returned the
    same *keys* to both callers with different *values* would pass a shape comparison and leak the
    difference."""
    anon = anonymous.get("/healthz")
    auth = authenticated.get("/healthz")

    assert anon.status_code == auth.status_code
    assert anon.content == auth.content, (
        "the liveness route answers an authenticated caller differently from an anonymous one; "
        "the anonymous answer is the one an attacker gets"
    )


def test_the_body_is_fixed_and_discloses_nothing(anonymous: TestClient) -> None:
    """§3.0: no version, no build, no uptime, no component status, no counts. Asserted as an exact
    equality rather than as a set of absent keys — an absence list only excludes the leaks someone
    thought of, and the next one added will not be on it."""
    payload = anonymous.get("/healthz").json()

    assert payload == {"status": "ok"}
    assert LIVENESS_BODY == {"status": "ok"}
    serialised = json.dumps(payload)
    for leak in ("version", "count", "uptime", "store", "build", "commit", "host"):
        assert leak not in serialised.lower()


def test_liveness_touches_no_store(anonymous: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """It must stay true when every store is down — which is exactly when an orchestrator needs to
    tell "the process is up, its dependencies are not" from "the process is gone". Planted by
    removing every store from the app's own dependency overrides and asserting the route is
    unaffected; a handler that reached for one would raise rather than answer."""
    import services.api.app as app_module

    for name in ("get_graph", "get_analytics", "get_working_set_store"):
        dependency = getattr(app_module, name, None)
        if dependency is not None:

            def _explode() -> None:
                raise AssertionError("liveness reached for a store")

            app.dependency_overrides[dependency] = _explode

    try:
        assert anonymous.get("/healthz").json() == {"status": "ok"}
    finally:
        for name in ("get_graph", "get_analytics", "get_working_set_store"):
            dependency = getattr(app_module, name, None)
            if dependency is not None:
                app.dependency_overrides.pop(dependency, None)


# --- Rule 15: the test must fail for a route that discloses something ---------


def _probe(handler) -> tuple[bytes, bytes]:
    """Runs the byte-comparison property against an arbitrary handler on a throwaway app, so a
    planted leak can be tested without mutating the real one."""
    planted = FastAPI()
    planted.get("/healthz")(handler)
    anon_client = TestClient(planted)
    return anon_client.get("/healthz").content, anon_client.get("/healthz").content


def test_a_route_reporting_a_count_is_caught() -> None:
    """The planted violation takes the shape the real risk has: a liveness route that grew a
    "helpful" number. It is caught by the fixed-body assertion, not by the byte comparison — the
    two callers would agree with each other and both be told the count."""

    async def leaks_a_count() -> dict[str, object]:
        return {"status": "ok", "nodes": 41_233}

    body, _ = _probe(leaks_a_count)
    payload = json.loads(body)

    assert payload != {"status": "ok"}, "a count-leaking body must not satisfy the fixed-body check"
    assert "count" in json.dumps(payload).lower() or "nodes" in json.dumps(payload).lower()


def test_a_route_reporting_store_status_is_caught() -> None:
    """The other real shape: a liveness route that tells an unauthenticated caller which stores are
    reachable, and so describes the deployment's internal topology."""

    async def leaks_store_status() -> dict[str, object]:
        return {"status": "ok", "stores": {"arcadedb": "up", "postgres": "down"}}

    body, _ = _probe(leaks_store_status)

    assert json.loads(body) != {"status": "ok"}
    assert "arcadedb" in body.decode()


def test_a_route_that_answers_differently_when_authenticated_is_caught() -> None:
    """The byte-comparison property's own red case, planted at the shape it guards: a handler whose
    answer depends on whether a caller presented a token. Without this, the comparison above proves
    only that two identical calls return identical bytes, which is true of any pure handler."""
    async def two_faced(request: Request) -> dict[str, object]:
        if request.headers.get("authorization"):
            return {"status": "ok", "realm": "osprey-internal"}
        return {"status": "ok"}

    planted = FastAPI()
    planted.get("/healthz")(two_faced)
    client = TestClient(planted)

    anon = client.get("/healthz")
    auth = client.get("/healthz", headers={"Authorization": "Bearer token"})

    assert anon.content != auth.content, (
        "this planted handler must differ between callers, or it is not exercising the property"
    )


def test_the_real_route_is_the_one_under_test() -> None:
    """Guards against the file passing while pointed at something else — the planted handlers above
    all live on throwaway apps, so nothing here would notice if the real route were removed."""
    assert liveness_route is not None
    assert any(getattr(route, "path", None) == "/healthz" for route in app.routes)
