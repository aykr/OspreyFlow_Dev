"""OIDC `Principal` resolution — `docs/03_CONDUIT_MIDDLEWARE.md` §6:
"OIDC via Keycloak (Apache-2.0). The session token resolves to a
`Principal` carrying identity, unit, roles, clearance, and the handling
codes the principal may receive."

**The JWKS source is a config point, not a hardcoded key.** `ApiConfig.
oidc_jwks_url` names the endpoint `PyJWKClient` fetches and caches keys
from — a Keycloak realm's `.../protocol/openid-connect/certs` in a real
deployment, a loopback HTTP fixture in tests
(`tests/services/api/test_auth.py`) — `PyJWKClient` deliberately rejects
any scheme but `http`/`https` (closing exactly the local-file-read risk a
`jku` header or a misconfigured URL could otherwise open), so the fixture
is a real, if ephemeral, HTTP server rather than a `file://` URL. Key
rotation is the thing that breaks first in a real deployment, and
`PyJWKClient` already does the two things that matter for it: a
TTL-bounded cache (`cache_keys=True, lifespan=...`) and one refresh-and-
retry when a token's `kid` isn't in the cached set (`PyJWKClient.
get_signing_key`) — nothing here reimplements either, and nothing here
special-cases the fixture path, so the exact same code runs against the
test fixture's URL as against a real IdP later; only the config value
changes.

**Claim names are this deployment's mapping, not a standard.** OIDC has no
standard claim for `clearance`, `org_unit` or `receivable_handling_codes`
— those come from `01_DOMAIN_MODEL.md` §2.2's handling model, which no IdP
knows about natively. A real deployment maps its IdP's actual claims (a
Keycloak protocol mapper, typically) onto the names below; this module
does not invent a mapping convention beyond naming what it expects.
"""

from __future__ import annotations

import jwt
from fastapi.security import HTTPBearer
from jwt import PyJWKClient

from schemas.domain import Principal

from .config import ApiConfig

CLAIM_CLEARANCE = "clearance"
CLAIM_ORG_UNIT = "org_unit"
CLAIM_RECEIVABLE_HANDLING_CODES = "receivable_handling_codes"
CLAIM_ROLES = "roles"


class PrincipalResolutionError(Exception):
    """A token failed validation or is missing a required claim — a 401,
    never a 500: "no `Principal`" is a different failure from "the Vault
    is unreachable", and the API surface (`app.py`) maps this exception
    type to the former."""


class PrincipalResolver:
    """One `PyJWKClient` per configured JWKS URL, built once at process
    start and reused for the process lifetime — `resolve()` itself makes
    no state-carrying assumption between calls beyond that client's own
    internal TTL cache, so this class carries nothing that would break
    `services/api`'s statelessness if two instances of it exist behind a
    load balancer with different local caches: both ask the same JWKS URL
    and converge on the same keys."""

    def __init__(self, config: ApiConfig) -> None:
        self._config = config
        self._jwk_client = PyJWKClient(
            config.oidc_jwks_url, cache_keys=True, lifespan=config.oidc_jwks_ttl_seconds
        )

    def resolve(self, token: str) -> Principal:
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(self._config.oidc_algorithms),
                audience=self._config.oidc_audience,
                issuer=self._config.oidc_issuer,
                options={
                    "require": ["sub"],
                    "verify_aud": self._config.oidc_audience is not None,
                    "verify_iss": self._config.oidc_issuer is not None,
                },
            )
        except jwt.PyJWTError as exc:
            raise PrincipalResolutionError(f"token rejected: {exc}") from exc

        try:
            clearance = str(claims[CLAIM_CLEARANCE])
            org_unit = str(claims[CLAIM_ORG_UNIT])
        except KeyError as exc:
            # Defaulting a missing claim to "" would still fail closed
            # (`01_DOMAIN_MODEL.md` §2.2: an unrecognised clearance sees
            # nothing) but silently, as a principal who can never see
            # anything rather than a rejected token — worse for whoever
            # has to debug an IdP misconfiguration than an explicit 401.
            raise PrincipalResolutionError(
                f"token is missing required claim: {exc}"
            ) from exc

        return Principal(
            id=str(claims["sub"]),
            clearance=clearance,
            org_unit=org_unit,
            receivable_handling_codes=list(claims.get(CLAIM_RECEIVABLE_HANDLING_CODES, [])),
            roles=list(claims.get(CLAIM_ROLES, [])),
        )


#: Shared by every route that needs a `Principal` — `app.py` wires the
#: actual resolution as a `Request`-aware dependency (`app.state.
#: principal_resolver` is built once in the lifespan), so this scheme
#: only extracts the bearer token; it does not itself validate one.
bearer_scheme = HTTPBearer(auto_error=True)
