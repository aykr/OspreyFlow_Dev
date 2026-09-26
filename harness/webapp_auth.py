"""`06_DECISIONS.md` ADR-049 Stage 2 §6 amendment 22, and `DECISIONS.md` ruling R2 — the two access
controls the setup harness itself needs, built now even though the surfaces they protect (the
post-launch admin console) arrive in `Stage 2 §6` part B.

**Not a reuse of `services/api/auth.py`, and that is a packaging constraint, not a preference.**
`harness/Dockerfile`'s own comment traces every module its entrypoint imports and copies in exactly
three project-tree roots: `harness`, `packages/schemas`, `scripts` — `services/` is not one of them.
Importing `services.api.auth.PrincipalResolver` here would work on this checkout and break inside
the actual harness image, the same class of "works everywhere except the one place it has to" gap
`CLAUDE.md` rule 15 exists to catch. This module re-implements the same audience-checked JWT
verification shape independently, using the same libraries (`PyJWT`, `PyJWKClient`) and reading the
same `OIDC_JWKS_URL`/`OIDC_AUDIENCE` environment variables the Conduit reads — "the same audience
check the Conduit uses" (ruling R2) means the same parameters and the same failure shape, not a
shared function across a dependency boundary this image cannot cross.
"""

from __future__ import annotations

import os
from ipaddress import ip_address

import jwt
from fastapi import HTTPException, Request
from jwt import PyJWKClient

#: R2's own named role.
ADMIN_ROLE = "osprey-admin"


def _not_found() -> HTTPException:
    """R2: "any request without one receives 404, never 401, so the endpoint's existence cannot
    be inferred." Every failure below — missing header, unreachable JWKS, expired token, wrong
    audience, missing role — raises the identical status and the identical (empty) body, on
    purpose: distinguishing them from outside would itself be the leak this status code exists to
    prevent. A fresh instance per call, not a shared module-level one — `HTTPException` carries its
    own traceback once raised, and reusing one object across concurrent requests would let one
    request's traceback attach to another's exception."""
    return HTTPException(status_code=404)

_LOOPBACK_ADDRESSES = {"127.0.0.1", "::1"}


def is_loopback(client_host: str | None) -> bool:
    """`ip_address()`-checked, not a string-equality list — `127.0.0.1` is the only literal
    IPv4 loopback address that ever appears as a socket peer, but this also correctly refuses
    `None` (no client info at all, the ASGI shape a raw TCP proxy or a misconfigured server can
    produce) rather than treating an absent value as trusted by default."""
    if client_host is None:
        return False
    if client_host in _LOOPBACK_ADDRESSES:
        return True
    try:
        return ip_address(client_host).is_loopback
    except ValueError:
        return False


async def loopback_only_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    """R2: "in setup mode the harness binds to loopback only... and refuses any non-loopback
    source." The bootstrap command's own `-p 127.0.0.1:7000:7000` is the first, docker-level layer
    of this; this middleware is the second, application-level one — belt and braces, not a
    substitute for the port binding, since a operator who runs the container with a wider publish
    by mistake should still get a refusal rather than a silently-reachable setup harness.

    **Setup mode only.** Once `Stage 2 §6` part B builds Launch, the running deployment's own
    workspace nginx is what the analyst reaches from off-host — this harness container's own admin
    console is reached the same, deliberately-narrow way, and this check does not relax for it: an
    operator opening the post-launch console does so from the same host, or through an operator's
    own secured tunnel, never a bare published port.

    **A real limit, found running the built image, not a hypothetical.** Docker's own bridge-mode
    port publishing (`-p 127.0.0.1:7000:7000`, the exact shape 05 §2's own bootstrap command uses)
    NATs every forwarded connection through the bridge gateway — `request.client.host` sees the
    same address for a genuine host-loopback caller and, were the operator to publish more widely
    by mistake, for a genuine LAN caller too. **The two are indistinguishable at this layer**, so
    this middleware's own refusal, correct as a mechanism (proven directly by `tests/harness/
    test_webapp_loopback.py`, which drives it via the real ASGI request path rather than a mock),
    provides no defence *in addition to* the port-binding when reached through bridge networking —
    the port-binding is what actually does the work in that deployment shape. It remains real,
    working defence for every path that is not NATed this way: `python -m harness` run directly on
    a host with no Docker at all, or a future `--network host` deployment, where the visible
    client address is the true one. **Which mechanism should carry R2's guarantee for the
    published-container case — adopting `--network host`, or accepting that the port-binding alone
    is the enforcement and this middleware is redundant-but-harmless there — is a real,
    undecided question, not resolved by this round** (`07_BUILD_PLAN.md` Stage 2 §6 part A's own
    entry has it as Proposed).
    """
    if not is_loopback(request.client.host if request.client else None):
        from starlette.responses import PlainTextResponse

        return PlainTextResponse(
            "refused: this harness only accepts loopback connections", status_code=403
        )
    return await call_next(request)


def _jwks_url() -> str | None:
    return os.environ.get("OIDC_JWKS_URL") or None


def _audience() -> str | None:
    return os.environ.get("OIDC_AUDIENCE") or None


def require_admin_role(request: Request) -> None:
    """`/admin`'s own access-control dependency (amendment 22: "every read path gets an
    access-control test, and `/admin` is a read path"). Raises the identical 404 for every
    failure — see `_not_found`'s own docstring."""
    header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not header or not header.lower().startswith("bearer "):
        raise _not_found()
    token = header.split(" ", 1)[1].strip()

    jwks_url = _jwks_url()
    if jwks_url is None:
        # No identity provider configured — setup mode, before Launch. There is no principal to
        # check a role against, so there is nothing to admit; refuse the same way an invalid token
        # would be refused, not a different status that would disclose the endpoint exists.
        raise _not_found()

    try:
        signing_key = PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=_audience(),
            options={"require": ["sub"], "verify_aud": _audience() is not None},
        )
    except jwt.PyJWTError as exc:
        raise _not_found() from exc

    roles = claims.get("roles")
    if not isinstance(roles, list) or ADMIN_ROLE not in roles:
        raise _not_found()
