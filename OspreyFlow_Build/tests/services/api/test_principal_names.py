"""`PrincipalNameDirectory` — ADR-106: a principal shown to a person is named, resolved at read
time from the identity provider, never stored.

The fixture models the identity provider's **refusals**, not only its grants (`process/CLAUDE.md`
rule 15's third worked example): a read without the bearer this fixture itself issued is 401, an
unknown id is 404 — so a directory that forgot the token, or trusted a locator-shaped id blindly,
goes red here rather than green against a fixture more permissive than the real Keycloak.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from services.api.principal_names import PrincipalNameDirectory

from principal_auth import OidcResolverSettings

CLIENT_ID = "osprey-conduit"
CLIENT_SECRET = "conduit-secret"
ISSUED_BEARER = "fixture-issued-token"

ACCOUNTS: dict[str, dict[str, str]] = {
    "uuid-ayan": {"firstName": "Ayan", "lastName": "Kar", "username": "osprey-demo-analyst"},
    "uuid-bare": {"username": "osprey-admin"},
}


class _IdpState:
    def __init__(self) -> None:
        self.users_asked: list[str] = []
        self.token_grants = 0


def _make_handler(state: _IdpState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib signature
            pass

        def _json(self, status: int, payload: object) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler method name
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode()
            if f"client_id={CLIENT_ID}" in body and f"client_secret={CLIENT_SECRET}" in body:
                state.token_grants += 1
                self._json(200, {"access_token": ISSUED_BEARER})
            else:
                self._json(401, {"error": "invalid_client"})

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler method name
            # The refusal a real Keycloak makes first: no (or a wrong) bearer is 401,
            # whatever the id.
            if self.headers.get("Authorization") != f"Bearer {ISSUED_BEARER}":
                self._json(401, {"error": "HTTP 401 Unauthorized"})
                return
            principal_id = self.path.rsplit("/", 1)[-1]
            state.users_asked.append(principal_id)
            account = ACCOUNTS.get(principal_id)
            if account is None:
                self._json(404, {"error": "User not found"})
            else:
                self._json(200, account)

    return Handler


@pytest.fixture
def idp() -> Iterator[tuple[str, _IdpState]]:
    state = _IdpState()
    server = HTTPServer(("127.0.0.1", 0), _make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield base, state
    finally:
        server.shutdown()
        thread.join()


def _settings(base: str, *, secret: str = CLIENT_SECRET) -> OidcResolverSettings:
    return OidcResolverSettings(
        oidc_jwks_url=f"{base}/jwks",
        oidc_token_exchange_url=f"{base}/token",
        oidc_token_exchange_client_id=CLIENT_ID,
        oidc_token_exchange_client_secret=secret,
        oidc_admin_users_url=f"{base}/admin/realms/osprey/users",
    )


async def test_names_resolve_first_and_last_or_the_username(idp: tuple[str, _IdpState]) -> None:
    base, _ = idp
    directory = PrincipalNameDirectory(_settings(base))
    try:
        names = await directory.display_names(["uuid-ayan", "uuid-bare", "uuid-unknown"])
    finally:
        await directory.aclose()
    assert names == {"uuid-ayan": "Ayan Kar", "uuid-bare": "osprey-admin"}


async def test_a_refused_client_yields_no_names_and_no_error(idp: tuple[str, _IdpState]) -> None:
    base, state = idp
    directory = PrincipalNameDirectory(_settings(base, secret="wrong"))
    try:
        assert await directory.display_names(["uuid-ayan"]) == {}
    finally:
        await directory.aclose()
    # Refused before any user read: the directory never got a bearer the users endpoint takes.
    assert state.users_asked == []


async def test_an_unreachable_idp_yields_no_names_and_no_error() -> None:
    directory = PrincipalNameDirectory(_settings("http://127.0.0.1:9"))
    try:
        assert await directory.display_names(["uuid-ayan"]) == {}
    finally:
        await directory.aclose()


async def test_an_unconfigured_deployment_asks_nothing(idp: tuple[str, _IdpState]) -> None:
    base, state = idp
    directory = PrincipalNameDirectory(
        OidcResolverSettings(oidc_jwks_url=f"{base}/jwks", oidc_admin_users_url=None)
    )
    try:
        assert await directory.display_names(["uuid-ayan"]) == {}
    finally:
        await directory.aclose()
    assert state.users_asked == [] and state.token_grants == 0


async def test_a_name_and_a_404_are_cached_within_the_ttl(idp: tuple[str, _IdpState]) -> None:
    base, state = idp
    directory = PrincipalNameDirectory(_settings(base))
    try:
        await directory.display_names(["uuid-ayan", "uuid-unknown"])
        again = await directory.display_names(["uuid-ayan", "uuid-unknown"])
    finally:
        await directory.aclose()
    assert again == {"uuid-ayan": "Ayan Kar"}
    assert state.users_asked == ["uuid-ayan", "uuid-unknown"]


async def test_nothing_to_resolve_fetches_no_token(idp: tuple[str, _IdpState]) -> None:
    base, state = idp
    directory = PrincipalNameDirectory(_settings(base))
    try:
        assert await directory.display_names([]) == {}
    finally:
        await directory.aclose()
    assert state.token_grants == 0
