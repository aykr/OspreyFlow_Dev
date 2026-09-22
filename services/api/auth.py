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

**`resolve_for_owner` — OAuth2 Token Exchange (RFC 8693), `06_DECISIONS.md` ADR-043's own
accepted mechanism for a stored `owner_id` with no live bearer token.** Exchanges this Conduit's
own client credentials for a token minted *as* the target owner, then decodes that token through
`resolve()` below **unchanged** — ADR-043's own central argument is that there is exactly one
claims-construction path in this codebase, not two; a token obtained by exchange is, from
`resolve()`'s own perspective, indistinguishable from a live session's token. **Simplified
relative to a full Keycloak wire protocol, disclosed rather than silently assumed exact:** this
client authenticates with `client_id`/`client_secret` and requests a token for `requested_subject`
in one round trip; a real deployment's own two-step client-credentials-then-exchange flow (or
Keycloak's own "Direct Naked Impersonation" extension) is an operator-configured detail
`05_DEPLOYMENT.md`'s own operational material owns, not replicated wire-for-wire here. What this
client and its own test fixture prove is the shape that actually matters for ADR-043's own
argument: a real async network call, authenticated by client credentials, requesting a token for
an arbitrary subject id, refused when the IdP's own policy says no, and — the one property Stage
1's own containment test exists to pin — returning a token that, once decoded, carries exactly
that subject's own real claims, never a broader set.
"""

from __future__ import annotations

import httpx
import jwt
from fastapi.security import HTTPBearer
from jwt import PyJWKClient

from schemas.domain import Principal

from .config import ApiConfig

CLAIM_CLEARANCE = "clearance"
CLAIM_ORG_UNIT = "org_unit"
CLAIM_RECEIVABLE_HANDLING_CODES = "receivable_handling_codes"
CLAIM_ROLES = "roles"

#: RFC 8693 §2.1's own grant-type URI, unchanged by this simplified client.
TOKEN_EXCHANGE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"


class PrincipalResolutionError(Exception):
    """A token failed validation or is missing a required claim — a 401,
    never a 500: "no `Principal`" is a different failure from "the Vault
    is unreachable", and the API surface (`app.py`) maps this exception
    type to the former."""


class PrincipalExchangeError(Exception):
    """Base for a failed `resolve_for_owner_detailed` call — see the two subclasses below for
    which failure. `06_DECISIONS.md` ADR-044 decides nothing about whether a caller should treat
    the two differently (the "unreachable vs. revoked" question, Proposed, not built) — but the
    distinction is real at this layer regardless, and collapsing it before ADR-044 resolves would
    make it harder, not easier, for that future work to build on. `resolve_for_owner` (below)
    is the caller-facing collapse every producer uses today, until ADR-044 changes that."""


class PrincipalExchangeRefused(PrincipalExchangeError):
    """The identity provider was reached and refused the exchange — the target subject is
    disabled, unknown, or the realm's own policy does not permit exchanging for it. A real,
    current fact about that principal, distinct from `PrincipalExchangeUnavailable` below."""


class PrincipalExchangeUnavailable(PrincipalExchangeError):
    """The token-exchange endpoint could not be reached at all (network/timeout), or this
    deployment has not configured one — a fact about *reachability*, not a decision the IdP made
    about the target subject."""


class PrincipalResolver:
    """One `PyJWKClient` per configured JWKS URL, built once at process
    start and reused for the process lifetime — `resolve()` itself makes
    no state-carrying assumption between calls beyond that client's own
    internal TTL cache, so this class carries nothing that would break
    `services/api`'s statelessness if two instances of it exist behind a
    load balancer with different local caches: both ask the same JWKS URL
    and converge on the same keys. `resolve_for_owner`'s own `httpx.
    AsyncClient` is built the same way, for the same reason — one per
    process, `aclose()`d at lifespan shutdown alongside every other
    client this codebase already closes there."""

    def __init__(self, config: ApiConfig) -> None:
        self._config = config
        self._jwk_client = PyJWKClient(
            config.oidc_jwks_url, cache_keys=True, lifespan=config.oidc_jwks_ttl_seconds
        )
        self._exchange_http = httpx.AsyncClient(timeout=10.0)

    async def aclose(self) -> None:
        await self._exchange_http.aclose()

    async def resolve_for_owner(self, owner_id: str) -> Principal | None:
        """The caller-facing form every `principal_for_owner` producer uses — collapses both
        `PrincipalExchangeRefused` and `PrincipalExchangeUnavailable` to `None`, the single
        "skip this evaluation, mark stopped" signal every existing caller already handles
        (`06_DECISIONS.md` ADR-036's own disclosed stand-in). Call `resolve_for_owner_detailed`
        directly to observe which of the two actually happened."""
        try:
            return await self.resolve_for_owner_detailed(owner_id)
        except PrincipalExchangeError:
            return None

    async def resolve_for_owner_detailed(self, owner_id: str) -> Principal:
        """Raises rather than collapses — see the two exception classes above. Never caches
        anything between calls: `06_DECISIONS.md` ADR-036's own "resolved fresh, never cached"
        requirement, and ADR-043's own freshness argument, both mean every call is a real,
        independent exchange against the IdP's own current state, not a lookup against anything
        this process remembers from a previous call."""
        if not self._config.oidc_token_exchange_url:
            raise PrincipalExchangeUnavailable(
                "OIDC_TOKEN_EXCHANGE_URL is not set — this deployment has not configured "
                "token exchange (06_DECISIONS.md ADR-043)"
            )
        try:
            response = await self._exchange_http.post(
                self._config.oidc_token_exchange_url,
                data={
                    "grant_type": TOKEN_EXCHANGE_GRANT_TYPE,
                    "client_id": self._config.oidc_token_exchange_client_id,
                    "client_secret": self._config.oidc_token_exchange_client_secret,
                    "requested_subject": owner_id,
                    "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
                },
            )
        except httpx.HTTPError as exc:
            raise PrincipalExchangeUnavailable(
                f"token-exchange endpoint unreachable for owner {owner_id!r}: {exc}"
            ) from exc
        if response.status_code != 200:
            raise PrincipalExchangeRefused(
                f"token exchange refused for owner {owner_id!r}: "
                f"{response.status_code} {response.text}"
            )
        exchanged_token = response.json().get("access_token")
        if not exchanged_token:
            raise PrincipalExchangeRefused(
                f"token exchange for owner {owner_id!r} returned no access_token"
            )
        try:
            return self.resolve(exchanged_token)
        except PrincipalResolutionError as exc:
            raise PrincipalExchangeRefused(
                f"exchanged token for owner {owner_id!r} failed verification: {exc}"
            ) from exc

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
