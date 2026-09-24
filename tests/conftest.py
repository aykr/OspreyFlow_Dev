"""Repo-wide pytest fixtures.

The OIDC fixtures below back every test that needs a real, signed bearer
token against `services/api/auth.py`'s `PrincipalResolver` — an RSA
keypair plus a loopback HTTP server serving the resulting JWKS document.
`PyJWKClient` (the underlying OIDC client) rejects any URI scheme but
`http`/`https`, so this is a real ephemeral HTTP server, not a `file://`
URL — see `services/api/auth.py`'s module docstring for why.

`token_exchange_url` (`06_DECISIONS.md` ADR-043, Phase 8 Stage 1) is the same class of fixture
for `PrincipalResolver.resolve_for_owner` — a real, loopback, ephemeral HTTP server implementing
enough of RFC 8693's token endpoint to exercise the real request/refusal/response shapes, not a
mock of the Python method. See `services/api/auth.py`'s own module docstring for exactly what is
and isn't replicated relative to a full Keycloak deployment.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from functools import partial
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

DEFAULT_KID = "test-signing-key-1"
TOKEN_EXCHANGE_CLIENT_ID = "conduit-service-account"
TOKEN_EXCHANGE_CLIENT_SECRET = "test-client-secret"  # noqa: S105 - test fixture only


@pytest.fixture
def keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


@pytest.fixture
def jwks_dir(tmp_path: Path) -> Iterator[tuple[Path, str]]:
    """A loopback HTTP server rooted at `tmp_path`, serving whatever
    `jwks.json` it finds there fresh on every request — a test can
    overwrite the file mid-test (a key-rotation scenario) and the next
    fetch sees the new content, the same as a real JWKS endpoint's
    content changing without the server restarting."""
    handler = partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[0], server.server_address[1]
        yield tmp_path, f"http://{host}:{port}/jwks.json"
    finally:
        server.shutdown()
        thread.join()


@pytest.fixture
def jwks_url(
    jwks_dir: tuple[Path, str], keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> str:
    directory, url = jwks_dir
    _, public_key = keypair
    jwk = RSAAlgorithm.to_jwk(public_key, as_dict=True)
    jwk["kid"] = DEFAULT_KID
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    (directory / "jwks.json").write_text(json.dumps({"keys": [jwk]}))
    return url


def sign_token(
    private_key: rsa.RSAPrivateKey, claims: dict[str, object], *, kid: str = DEFAULT_KID
) -> str:
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


class TokenExchangeRegistry:
    """The mutable per-test state a `token_exchange_url` handler reads on every request —
    `subject -> claims` for a subject the exchange should succeed for, absent or explicitly
    `None` for one it should refuse (`06_DECISIONS.md` ADR-044's own "refused" case: a disabled
    or unknown account, distinct from the server being unreachable at all, which a test gets by
    pointing `oidc_token_exchange_url` at a closed port instead of using this fixture)."""

    def __init__(self) -> None:
        self.subjects: dict[str, dict[str, object]] = {}
        #: Claims for this client's *own* token, returned by the `client_credentials` grant. The
        #: resolver needs one as the exchange's `subject_token`; it is never resolved into a
        #: `Principal`, so the claim set only has to be signable.
        self.client_claims: dict[str, object] = {
            "sub": "osprey-conduit",
            "clearance": "OFFICIAL",
            "org_unit": "conduit",
            "receivable_handling_codes": [],
            "roles": ["service-account"],
        }

    def register(self, principal_id: str, claims: dict[str, object]) -> None:
        self.subjects[principal_id] = claims

    def disable(self, principal_id: str) -> None:
        self.subjects.pop(principal_id, None)


def _make_token_exchange_handler(
    registry: TokenExchangeRegistry, private_key: rsa.RSAPrivateKey
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib signature
            pass  # quiet by default, matching SimpleHTTPRequestHandler's own test usage elsewhere

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler method name
            length = int(self.headers.get("Content-Length", "0"))
            body = parse_qs(self.rfile.read(length).decode())
            grant_type = body.get("grant_type", [None])[0]
            client_id = body.get("client_id", [None])[0]
            client_secret = body.get("client_secret", [None])[0]
            requested_subject = body.get("requested_subject", [None])[0]

            def _error(status: int, error: str) -> None:
                payload = json.dumps({"error": error}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            valid_client = (
                client_id == TOKEN_EXCHANGE_CLIENT_ID
                and client_secret == TOKEN_EXCHANGE_CLIENT_SECRET
            )

            # `client_credentials` is served because a real token endpoint serves it and the
            # resolver needs its own token as the exchange's `subject_token` — RFC 8693 §2.1 makes
            # that field REQUIRED, and this fixture previously accepted an exchange without it,
            # which is exactly why the omission survived until it was run against a real Keycloak
            # (06_DECISIONS.md ADR-043's amendment, 24 September 2026). A fixture that accepts a
            # request the real server rejects is worse than no fixture: it makes the wrong thing
            # look tested.
            if grant_type == "client_credentials":
                if not valid_client:
                    _error(401, "invalid_client")
                    return
                token = sign_token(private_key, dict(registry.client_claims))
                payload = json.dumps({"access_token": token, "token_type": "Bearer"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            if grant_type != "urn:ietf:params:oauth:grant-type:token-exchange":
                _error(400, "unsupported_grant_type")
                return
            if not valid_client:
                _error(401, "invalid_client")
                return
            if not body.get("subject_token", [None])[0]:
                # A real Keycloak refuses this outright. The fixture now does too.
                _error(400, "invalid_request")
                return
            claims = registry.subjects.get(requested_subject or "")
            if claims is None:
                # Same OAuth2-shaped refusal for "never registered" and "explicitly disabled" —
                # `TokenExchangeRegistry.disable` removes the entry rather than flagging it, since
                # the IdP's own real refusal looks identical either way from the caller's side.
                _error(400, "invalid_grant")
                return
            token = sign_token(private_key, dict(claims))
            payload = json.dumps({"access_token": token, "token_type": "Bearer"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


@pytest.fixture
def token_exchange_registry() -> TokenExchangeRegistry:
    return TokenExchangeRegistry()


@pytest.fixture
def token_exchange_url(
    token_exchange_registry: TokenExchangeRegistry,
    keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> Iterator[str]:
    """A real, loopback, ephemeral RFC-8693-shaped token endpoint — `06_DECISIONS.md` ADR-043.
    Signs with the same keypair `jwks_url` publishes, so a token this endpoint issues verifies
    against that same fixture's own JWKS document without a second keypair to keep in sync."""
    private_key, _ = keypair
    handler = _make_token_exchange_handler(token_exchange_registry, private_key)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[0], server.server_address[1]
        yield f"http://{host}:{port}/token-exchange"
    finally:
        server.shutdown()
        thread.join()


def default_claims(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "sub": "analyst-1",
        "clearance": "OFFICIAL",
        "org_unit": "unit-1",
        "receivable_handling_codes": [],
        "roles": ["analyst"],
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    base.update(overrides)
    return base
