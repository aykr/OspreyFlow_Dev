"""A real loopback identity provider that can say no, for the sign-in tests.

`CLAUDE.md` rule 15: a fixture that only ever answers yes proves nothing about the refusal paths,
and a planted violation must take the real call-site shape. So this is an actual HTTP server
(the code under test uses `urllib` and `PyJWKClient` against it exactly as it does against
Keycloak) that

- serves signing keys at Keycloak's `certs` path, and its discovery document;
- refuses an unregistered client, an inexact redirect URI, a plain (non-S256) challenge;
- issues single-use codes bound to their PKCE challenge, and refuses a wrong verifier, a reused
  code, a code redeemed for another client or redirect;
- **PL9a (the page service's confidential client), all off unless asked for, so the existing users
  are unchanged:** authenticates the client at the token endpoint when `client_secret` is set (a wrong
  or missing secret: `401 invalid_client`, before the code is looked at, as Keycloak does and
  `tests/conftest.py` records), lets a code expire (`code_ttl_seconds`, moved by `advance`), and
  hands out a real signed JWT access token for `access_token_audience` instead of an opaque string;
- signs ID tokens whose claims a test can bend one at a time (audience, issuer, nonce, expiry,
  roles, another signing key, no ID token at all);
- can answer 500 on the token endpoint, and can be stopped so nothing answers.

The test plays the browser through `authorise(url, ...)`: it parses the address the code under test
built, applies the provider's own checks, and returns the callback address the provider would send
the browser back to.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

REALM = "osprey"
KID = "fake-idp-key-1"


_KEYS: list[rsa.RSAPrivateKey] = []


def _keys() -> tuple[rsa.RSAPrivateKey, rsa.RSAPrivateKey]:
    """Two keys, made once per test session; 2048-bit generation dominates the run time."""
    if not _KEYS:
        _KEYS.extend(
            rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2)
        )
    return _KEYS[0], _KEYS[1]


def _s256(verifier: str) -> str:
    """Written out here rather than imported from the code under test, so a wrong challenge
    function there cannot be masked by the same wrong function here."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class AuthorisationRefused(Exception):
    """The provider would show an error page instead of sending the browser back."""


@dataclass
class _Code:
    client_id: str
    redirect_uri: str
    challenge: str
    nonce: str
    username: str
    roles: list[str]
    used: bool = False
    issued_at: float = 0.0


@dataclass
class FakeIdentityProvider:
    client_id: str
    redirect_uri: str
    users: dict[str, list[str]] = field(default_factory=dict)  # username -> roles

    #: Bend one thing at a time. Keys: aud, iss, nonce, exp, iat, roles, sub.
    claim_overrides: dict[str, Any] = field(default_factory=dict)
    sign_with_other_key: bool = False
    omit_id_token: bool = False
    token_status: int | None = None  # force this status from the token endpoint
    token_calls: int = 0
    #: A confidential client: the secret the provider holds. `None` is a public client (no
    #: authentication at the token endpoint), which is what the existing tests use.
    client_secret: str | None = None
    #: Whole seconds a code lives by the provider's own clock; `None` is for ever.
    code_ttl_seconds: float | None = None
    #: When set, the access token is a real signed JWT naming this audience (the Conduit's).
    access_token_audience: str | None = None

    def __post_init__(self) -> None:
        self._key, self._other_key = _keys()
        self._codes: dict[str, _Code] = {}
        self._offset = 0.0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:  # silence
                pass

            def do_GET(self) -> None:  # noqa: N802
                if self.path.endswith("/protocol/openid-connect/certs"):
                    jwk = json.loads(RSAAlgorithm.to_jwk(outer._key.public_key()))
                    jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
                    self._send(200, {"keys": [jwk]})
                elif self.path.endswith("/.well-known/openid-configuration"):
                    oidc = f"{outer.issuer}/protocol/openid-connect"
                    self._send(200, {
                        "issuer": outer.issuer,
                        "authorization_endpoint": f"{oidc}/auth",
                        "token_endpoint": f"{oidc}/token",
                        "jwks_uri": f"{oidc}/certs",
                        "response_types_supported": ["code"],
                        "subject_types_supported": ["public"],
                        "id_token_signing_alg_values_supported": ["RS256"],
                        "code_challenge_methods_supported": ["S256"],
                        "token_endpoint_auth_methods_supported": [
                            "client_secret_basic", "client_secret_post"],
                    })  # fmt: skip
                else:
                    self._send(404, {"error": "not_found"})

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                form = urllib.parse.parse_qs(self.rfile.read(length).decode())
                if self.path.endswith("/protocol/openid-connect/token"):
                    status, body = outer._token(
                        {k: v[0] for k, v in form.items()}, self.headers.get("Authorization")
                    )
                    self._send(status, body)
                else:
                    self._send(404, {"error": "not_found"})

            def _send(self, status: int, body: dict[str, Any]) -> None:
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = Thread(
            target=lambda: self._server.serve_forever(poll_interval=0.01), daemon=True
        )
        self._thread.start()
        self.port = self._server.server_address[1]
        self.issuer = f"http://127.0.0.1:{self.port}/realms/{REALM}"

    # --- the browser's side ---

    def authorise(self, auth_url: str, *, username: str) -> str:
        """What the browser does after the person signs in: returns the callback address."""
        parsed = urllib.parse.urlparse(auth_url)
        assert parsed.path.endswith("/protocol/openid-connect/auth"), parsed.path
        query = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        if query.get("client_id") != self.client_id:
            raise AuthorisationRefused("unknown client")
        if query.get("redirect_uri") != self.redirect_uri:
            raise AuthorisationRefused("invalid redirect_uri")
        if query.get("code_challenge_method") != "S256" or not query.get("code_challenge"):
            raise AuthorisationRefused("PKCE S256 required")
        if query.get("response_type") != "code":
            raise AuthorisationRefused("response_type")
        if username not in self.users:
            raise AuthorisationRefused("invalid credentials")
        code = secrets.token_urlsafe(16)
        self._codes[code] = _Code(
            client_id=query["client_id"],
            redirect_uri=query["redirect_uri"],
            challenge=query["code_challenge"],
            nonce=query.get("nonce", ""),
            username=username,
            roles=list(self.users[username]),
            issued_at=self._now(),
        )
        return f"{self.redirect_uri}?" + urllib.parse.urlencode(
            {"code": code, "state": query["state"]}
        )

    # --- the token endpoint ---

    def _now(self) -> float:
        return time.time() + self._offset

    def advance(self, seconds: float) -> None:
        """Moves the provider's own clock, which decides when a code expires."""
        self._offset += seconds

    def _authenticated(self, form: dict[str, str], authorization: str | None) -> bool:
        """A confidential client's secret, by a Basic header or by the form's own fields."""
        assert self.client_secret is not None
        client_id: str | None = form.get("client_id")
        secret: str | None = form.get("client_secret")
        if authorization and authorization.lower().startswith("basic "):
            decoded = base64.b64decode(authorization[6:]).decode()
            name, _, password = decoded.partition(":")
            client_id, secret = urllib.parse.unquote_plus(name), urllib.parse.unquote_plus(password)
        return client_id == self.client_id and bool(secret) and secret == self.client_secret

    def _token(
        self, form: dict[str, str], authorization: str | None = None
    ) -> tuple[int, dict[str, Any]]:
        self.token_calls += 1
        if self.token_status is not None:
            return self.token_status, {"error": "forced"}
        # The client is authenticated before the code is looked at, as Keycloak does: a wrong
        # secret does not spend the code (Keycloak's own refusal, recorded in tests/conftest.py).
        if self.client_secret is not None and not self._authenticated(form, authorization):
            return 401, {
                "error": "invalid_client",
                "error_description": "Invalid client or Invalid client credentials",
            }
        if form.get("grant_type") != "authorization_code":
            return 400, {"error": "unsupported_grant_type"}
        stored = self._codes.get(form.get("code", ""))
        if stored is None or stored.used:
            return 400, {"error": "invalid_grant"}
        stored.used = True  # single use, even when the rest is wrong or the code has expired
        if (
            self.code_ttl_seconds is not None
            and self._now() - stored.issued_at > self.code_ttl_seconds
        ):
            return 400, {"error": "invalid_grant", "error_description": "Code not valid"}
        if form.get("client_id") != stored.client_id:
            return 400, {"error": "invalid_grant"}
        if form.get("redirect_uri") != stored.redirect_uri:
            return 400, {"error": "invalid_grant"}
        if _s256(form.get("code_verifier", "")) != stored.challenge:
            return 400, {"error": "invalid_grant", "error_description": "PKCE verification failed"}
        if self.omit_id_token:
            return 200, {"access_token": "opaque", "token_type": "Bearer"}
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": self.issuer,
            "aud": stored.client_id,
            "sub": f"sub-{stored.username}",
            "preferred_username": stored.username,
            "roles": stored.roles,
            "nonce": stored.nonce,
            "iat": now,
            "exp": now + 300,
        }
        claims.update(self.claim_overrides)
        key = self._other_key if self.sign_with_other_key else self._key
        token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": KID})
        access: str = "opaque"
        if self.access_token_audience is not None:
            access = jwt.encode(
                {
                    "iss": self.issuer,
                    "aud": self.access_token_audience,
                    "azp": stored.client_id,
                    "sub": f"sub-{stored.username}",
                    "typ": "Bearer",
                    "roles": stored.roles,
                    "iat": now,
                    "exp": now + 300,
                },
                self._key,
                algorithm="RS256",
                headers={"kid": KID},
            )
        return 200, {"id_token": token, "access_token": access, "token_type": "Bearer"}

    def stop(self) -> None:
        """After this nothing answers: the connection is refused."""
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()
