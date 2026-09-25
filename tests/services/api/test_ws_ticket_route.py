"""`POST /v1/ws-ticket` route wiring — `06_DECISIONS.md` ADR-050 objection 8.

`services.api.ws_ticket.mint_ws_ticket`'s own real Valkey mechanics are
`tests/services/api/test_ws_ticket.py`'s own live-service tests; this file only proves the route
requires authentication (standing rule 2 / `CLAUDE.md` rule 4 — no exceptions for internal
endpoints) and mints a ticket bound to the calling principal, via a fake Valkey that records what
it was asked to store rather than a live one.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from services.api.app import app, get_principal, get_valkey

from schemas.domain import Principal

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


class _FakeValkey:
    """The only surface `mint_ws_ticket` touches."""

    def __init__(self) -> None:
        self.stored: dict[str, tuple[str, int]] = {}

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.stored[key] = (value, ex)


@pytest.fixture
def fake_valkey() -> _FakeValkey:
    return _FakeValkey()


@pytest.fixture
def client(fake_valkey: _FakeValkey) -> TestClient:
    app.dependency_overrides[get_principal] = lambda: PRINCIPAL
    app.dependency_overrides[get_valkey] = lambda: fake_valkey
    yield TestClient(app)
    app.dependency_overrides.pop(get_principal, None)
    app.dependency_overrides.pop(get_valkey, None)


@pytest.fixture
def anonymous_client() -> TestClient:
    """No principal override at all — standing rule 2 / `CLAUDE.md` rule 4: every route gets an
    access-control test, no exceptions for internal endpoints, and `/v1/ws-ticket` mints a real
    credential, so this is exactly the route that must not answer an anonymous caller."""
    app.dependency_overrides.pop(get_principal, None)
    return TestClient(app)


def test_an_unauthenticated_request_is_refused(anonymous_client: TestClient) -> None:
    response = anonymous_client.post("/v1/ws-ticket")

    assert response.status_code == 401


def test_an_authenticated_request_mints_a_ticket_bound_to_the_calling_principal(
    client: TestClient, fake_valkey: _FakeValkey
) -> None:
    response = client.post("/v1/ws-ticket")

    assert response.status_code == 200
    body = response.json()
    assert body["ticket"]
    assert body["expires_in"] == 30

    stored_key = f"ws-ticket:{body['ticket']}"
    assert stored_key in fake_valkey.stored
    stored_value, ttl = fake_valkey.stored[stored_key]
    assert PRINCIPAL.id in stored_value
    assert ttl == 30


def test_two_requests_from_the_same_principal_mint_two_different_tickets(
    client: TestClient,
) -> None:
    first = client.post("/v1/ws-ticket").json()["ticket"]
    second = client.post("/v1/ws-ticket").json()["ticket"]

    assert first != second
