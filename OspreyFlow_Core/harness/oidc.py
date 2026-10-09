"""Browser sign-in against the deployment's own realm, shared by the launcher and the Admin console.

`06_DECISIONS.md` ADR-051. Authorization code with PKCE (S256) for a **public** client: nothing
secret is held, and the code is exchanged by this process (the person's machine), never by page
script. The identity used is the **ID token** the realm signs for the client — its audience is the
client's own id, so a token minted for the Glass or the Conduit is not accepted here, and one minted
here is refused by the Conduit (the launcher and harness clients carry no Conduit audience).

**Two outcomes, never merged (ADR-044).** `IdentityProviderUnreachable` — nothing answered, or it
answered with a server error — and `SignInRefused` — the provider was reached and said no, or handed
back something that does not verify. The operator's next step differs (start the stack, versus try a
different account), so callers report them differently.

Standard library and PyJWT only, so it works inside the harness image, which does not carry
`services/` (see `harness/webapp_auth.py`).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import jwt
from jwt import PyJWKClient

#: How long the provider gets to answer before it counts as unreachable.
HTTP_TIMEOUT_SECONDS = 5.0
#: A started sign-in that is not finished within this long is forgotten.
ATTEMPT_TTL_SECONDS = 600.0
#: Bounds on in-memory state, so a loop of started sign-ins cannot grow the process without limit.
MAX_ATTEMPTS = 256
MAX_SESSIONS = 256


class IdentityProviderUnreachable(RuntimeError):
    """Nothing answered, or it answered with a server error."""


class SignInRefused(RuntimeError):
    """The provider was reached and refused, or returned something that does not verify.
    `reason` is a short stable code for tests and logs; it is never shown as advice to an
    attacker, only as a plain sentence by the caller."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class SignInConfig:
    """Where the provider is, and which registered client this process signs in as."""

    issuer: str  # e.g. http://localhost:8081/realms/osprey — as the person's browser reaches it
    client_id: str
    redirect_uri: str
    post_logout_uri: str
    #: ADR-107: where THIS PROCESS reaches the provider, when that differs from `issuer` — a
    #: containerised launcher's `localhost` is itself, so its token and certs fetches go to the
    #: compose network's own address (e.g. http://keycloak:8080/realms/osprey) while the browser's
    #: redirects, and the `iss` claim every token is verified against, stay `issuer`. Unset, the
    #: issuer is used for both, exactly as before.
    backchannel: str | None = None

    @property
    def auth_url(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/auth"

    @property
    def token_url(self) -> str:
        return f"{self.backchannel or self.issuer}/protocol/openid-connect/token"

    @property
    def certs_url(self) -> str:
        return f"{self.backchannel or self.issuer}/protocol/openid-connect/certs"

    @property
    def logout_url(self) -> str:
        query = urllib.parse.urlencode(
            {"client_id": self.client_id, "post_logout_redirect_uri": self.post_logout_uri}
        )
        return f"{self.issuer}/protocol/openid-connect/logout?{query}"


@dataclass(frozen=True)
class Identity:
    subject: str
    username: str
    roles: tuple[str, ...]

    def has_role(self, role: str) -> bool:
        return role in self.roles


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def pkce_challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


@dataclass
class Attempt:
    verifier: str
    nonce: str
    expires: float


@dataclass
class LoginAttempts:
    """Sign-ins that have been started and not yet finished. Each state is single-use."""

    clock: Callable[[], float] = time.monotonic
    _attempts: dict[str, Attempt] = field(default_factory=dict)

    def start(self, config: SignInConfig) -> str:
        """The address to send the browser to."""
        return self.begin(config)[0]

    def begin(self, config: SignInConfig) -> tuple[str, str]:
        """The address to send the browser to, and the `state` it will carry back — for a caller
        that also binds the sign-in to the browser that started it (a cookie holding the state)."""
        self._evict()
        if len(self._attempts) >= MAX_ATTEMPTS:
            oldest = min(self._attempts, key=lambda s: self._attempts[s].expires)
            del self._attempts[oldest]
        state = secrets.token_urlsafe(24)
        attempt = Attempt(
            verifier=secrets.token_urlsafe(48),
            nonce=secrets.token_urlsafe(24),
            expires=self.clock() + ATTEMPT_TTL_SECONDS,
        )
        self._attempts[state] = attempt
        query = urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": config.client_id,
                "redirect_uri": config.redirect_uri,
                "scope": "openid",
                "state": state,
                "nonce": attempt.nonce,
                "code_challenge": pkce_challenge(attempt.verifier),
                "code_challenge_method": "S256",
            }
        )
        return f"{config.auth_url}?{query}", state

    def finish(self, state: str | None) -> Attempt:
        """Consumes the attempt. An unknown, reused or expired state is refused."""
        self._evict()
        attempt = self._attempts.pop(state or "", None)
        if attempt is None:
            raise SignInRefused("unknown_or_expired_state")
        return attempt

    def _evict(self) -> None:
        now = self.clock()
        for state in [s for s, a in self._attempts.items() if a.expires <= now]:
            del self._attempts[state]


def _read_json(response_body: bytes) -> dict[str, object]:
    try:
        value = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise SignInRefused("unreadable_token_response") from error
    if not isinstance(value, dict):
        raise SignInRefused("unreadable_token_response")
    return value


def probe(config: SignInConfig) -> None:
    """Raises `IdentityProviderUnreachable` unless the provider answers with its signing keys."""
    try:
        with urllib.request.urlopen(config.certs_url, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310 - the configured provider
            if response.status != 200:
                raise IdentityProviderUnreachable(f"the provider answered {response.status}")
    except urllib.error.HTTPError as error:
        raise IdentityProviderUnreachable(f"the provider answered {error.code}") from error
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        raise IdentityProviderUnreachable(f"nothing answered at {config.issuer}") from error


def complete(config: SignInConfig, *, code: str, attempt: Attempt) -> Identity:
    """Exchange the code for tokens and verify the ID token. Raises one of the two errors above."""
    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.redirect_uri,
            "client_id": config.client_id,
            "code_verifier": attempt.verifier,
        }
    ).encode("ascii")
    request = urllib.request.Request(
        config.token_url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310 - the configured provider
            payload = _read_json(response.read())
    except urllib.error.HTTPError as error:
        if error.code >= 500:
            raise IdentityProviderUnreachable(f"the provider answered {error.code}") from error
        raise SignInRefused("code_rejected") from error
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        raise IdentityProviderUnreachable(f"nothing answered at {config.issuer}") from error

    id_token = payload.get("id_token")
    if not isinstance(id_token, str) or not id_token:
        raise SignInRefused("no_id_token")
    return verify_id_token(config, id_token, nonce=attempt.nonce)


def verify_id_token(config: SignInConfig, id_token: str, *, nonce: str) -> Identity:
    try:
        key = PyJWKClient(config.certs_url, timeout=HTTP_TIMEOUT_SECONDS).get_signing_key_from_jwt(
            id_token
        )
        claims = jwt.decode(
            id_token,
            key.key,
            algorithms=["RS256"],
            audience=config.client_id,
            # ADR-107: a split-horizon dev IdP mints `iss` from the request's host — measured
            # against the deployed Keycloak, 9 October 2026: the same realm answered
            # `http://keycloak:8080/realms/osprey` through the compose network and the
            # `localhost` form from the host. A config with a back channel accepts exactly those
            # two forms and nothing else; without one, behaviour is unchanged. A deployment that
            # pins its hostname collapses the two into one.
            issuer=[config.issuer, config.backchannel] if config.backchannel else config.issuer,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.PyJWKClientConnectionError as error:
        raise IdentityProviderUnreachable(f"nothing answered at {config.issuer}") from error
    except jwt.PyJWTError as error:
        raise SignInRefused("token_invalid") from error

    if claims.get("nonce") != nonce:
        raise SignInRefused("nonce_mismatch")
    roles = claims.get("roles", [])
    if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
        raise SignInRefused("roles_claim_malformed")
    subject = str(claims["sub"])
    return Identity(
        subject=subject,
        username=str(claims.get("preferred_username") or subject),
        roles=tuple(roles),
    )


@dataclass
class SessionStore:
    """Signed-in people, held in this process's memory only. A restart signs everyone out, which is
    the safe direction. The expiry is absolute, not sliding."""

    ttl_seconds: float = 8 * 3600.0
    clock: Callable[[], float] = time.monotonic
    _sessions: dict[str, tuple[Identity, float]] = field(default_factory=dict)

    def create(self, identity: Identity) -> str:
        self._evict()
        if len(self._sessions) >= MAX_SESSIONS:
            oldest = min(self._sessions, key=lambda t: self._sessions[t][1])
            del self._sessions[oldest]
        token = secrets.token_urlsafe(32)
        self._sessions[token] = (identity, self.clock() + self.ttl_seconds)
        return token

    def get(self, token: str | None) -> Identity | None:
        if not token:
            return None
        entry = self._sessions.get(token)
        if entry is None:
            return None
        identity, expires = entry
        if expires <= self.clock():
            del self._sessions[token]
            return None
        return identity

    def destroy(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)

    def _evict(self) -> None:
        now = self.clock()
        for token in [t for t, (_, exp) in self._sessions.items() if exp <= now]:
            del self._sessions[token]


# --- Where the realm is, from the rendered deployment ---------------------------------------

DEFAULT_KEYCLOAK_PORT = 8081
REALM_NAME = "osprey"
#: Read only from an operator's own environment, for a Keycloak published on another address.
ISSUER_ENV = "OSPREY_HARNESS_OIDC_ISSUER"


def rendered_realm_exists(out_root: Path) -> bool:
    """Has a deployment been rendered (is there a realm to sign in to)? When it cannot be told, the
    answer is yes: a failed listing must never open a console."""
    try:
        return any(out_root.glob("*/realm.json"))
    except OSError:
        return True


def default_issuer(out_root: Path) -> str:
    """Where the person's browser reaches the realm. The port comes from the rendered deployment's
    own environment file when it names one."""
    override = os.environ.get(ISSUER_ENV)
    if override:
        return override.rstrip("/")
    port = DEFAULT_KEYCLOAK_PORT
    for env_file in sorted(out_root.glob("*/deployment.env")):
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                key, _, value = line.partition("=")
                if key.strip() == "OSPREY_KEYCLOAK_PORT":
                    port = int(value.strip())
        except (OSError, ValueError):
            continue
    return f"http://localhost:{port}/realms/{REALM_NAME}"


# --- The callback, once, for every tool that signs in ---------------------------------------


@dataclass(frozen=True)
class CallbackOutcome:
    kind: Literal["signed_in", "invalid_link", "not_completed", "unreachable", "refused"]
    identity: Identity | None = None


def handle_callback(
    config: SignInConfig,
    attempts: LoginAttempts,
    *,
    code: str | None,
    state: str | None,
    error: str | None,
    login_cookie: str | None,
) -> CallbackOutcome:
    """Everything between 'the browser came back' and 'here is who signed in'. The state must equal
    the cookie set by the browser that started the sign-in (so someone else's code cannot sign this
    browser in as them), and is single-use. Callers turn the outcome into a page; what they do with
    a signed-in identity (which roles matter) is theirs."""
    if not state or not login_cookie or not secrets.compare_digest(login_cookie, state):
        return CallbackOutcome("invalid_link")
    try:
        attempt = attempts.finish(state)
    except SignInRefused:
        return CallbackOutcome("invalid_link")
    if error or not code:
        return CallbackOutcome("not_completed")
    try:
        identity = complete(config, code=code, attempt=attempt)
    except IdentityProviderUnreachable:
        return CallbackOutcome("unreachable")
    except SignInRefused:
        return CallbackOutcome("refused")
    return CallbackOutcome("signed_in", identity)
