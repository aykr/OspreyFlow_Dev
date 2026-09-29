"""The Conduit's own view of OIDC `Principal` resolution.

**The machinery itself moved to `packages/principal_auth` in round 13b, 27 September 2026, and
this module is now the Conduit's thin edge on it.** The reason is a dependency direction, not
tidiness: `harness/verify.py` needs a `PrincipalResolver` to run the deployment's three-sided
verify, and `harness/Dockerfile` deliberately carries no `services/` (its own header cites
ADR-049 — the traced set is "`harness`, `packages/schemas`, `scripts` — and nothing under
`services/`"). So the harness image shipped a verify stage that would raise `ModuleNotFoundError`
the moment it ran. `tests/test_image_imports_are_carried.py` found it in round 13.

Vendoring `services/` into the harness image would have reversed ADR-049's boundary. Moving the
shared contract into `packages/` instead lets the Conduit and the harness both import it without
either importing the other, which is what the dependency should have been all along —
principal resolution is not a `services/api` implementation detail, it is the thing both speak.

Everything below is re-exported unchanged, so every existing `from services.api.auth import ...`
keeps working: `app.py` and the four test modules that import from here needed no edit, which is
also what keeps this refactor honest — nothing about the Conduit's behaviour moved with it.
"""

from __future__ import annotations

from fastapi.security import HTTPBearer

from principal_auth import (
    OidcResolverSettings,
    OidcSettings,
    PrincipalExchangeError,
    PrincipalExchangeRefused,
    PrincipalExchangeUnavailable,
    PrincipalResolutionError,
    PrincipalResolver,
    PrincipalRevoked,
)

__all__ = [
    "OidcResolverSettings",
    "OidcSettings",
    "PrincipalExchangeError",
    "PrincipalExchangeRefused",
    "PrincipalExchangeUnavailable",
    "PrincipalResolutionError",
    "PrincipalResolver",
    "PrincipalRevoked",
    "bearer_scheme",
]

#: Shared by every route that needs a `Principal` — `app.py` wires the
#: actual resolution as a `Request`-aware dependency (`app.state.
#: principal_resolver` is built once in the lifespan), so this scheme
#: only extracts the bearer token; it does not itself validate one.
#:
#: Stays here rather than moving with the resolver: it is a FastAPI construct, and
#: `packages/principal_auth` is deliberately free of the web framework so the harness image can
#: import it without one.
bearer_scheme = HTTPBearer(auto_error=True)
