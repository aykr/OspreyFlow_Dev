"""OIDC `Principal` resolution, owned by `packages/` rather than by `services/api`.

**Why this lives here and not in `services/api/auth.py`** (round 13b, 27 September 2026). It used
to live there, and `harness/verify.py` imported it — a dependency pointing the wrong way, because
`harness/Dockerfile` deliberately does not carry `services/` (its own header cites ADR-049: the
traced set is "`harness`, `packages/schemas`, `scripts` — and nothing under `services/`"). The
harness image therefore shipped a `verify` stage that would raise `ModuleNotFoundError` the
moment it ran, which `tests/test_image_imports_are_carried.py` found in round 13.

The fix is the direction, not a vendored copy: the principal-resolution machinery is not a
`services/api` implementation detail — it is the contract both the Conduit and the harness's own
verify stage speak. Moving it here lets both import it without either importing the other, and
ADR-049's boundary stands untouched.

**`OidcSettings` is a Protocol, and that is the point.** The resolver reads exactly nine fields,
all OIDC. `services/api`'s own `ApiConfig` satisfies it structurally, so no call site there
changed. `harness/verify.py` previously had to fabricate a whole `ApiConfig` — inventing Postgres
credentials and a Valkey host it never used — purely to satisfy the type; it now builds the nine
real fields and nothing else.

The original module's own notes on JWKS handling, key rotation and the fixture path are kept
verbatim below, because they document decisions rather than location.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import httpx
import jwt
from jwt import PyJWKClient

from schemas.domain import Principal


@runtime_checkable
class OidcSettings(Protocol):
    """The nine fields `PrincipalResolver` actually reads.

    Structural, not nominal: `services/api/config.py`'s `ApiConfig` satisfies it without
    declaring so, and `OidcResolverSettings` below is for callers that have no `ApiConfig` and
    should not have to invent one."""

    # Read-only members (properties, not bare annotations): a bare `x: str` in a Protocol
    # declares a *settable* attribute, which `OidcResolverSettings` — frozen, as settings should
    # be — cannot satisfy. mypy says so precisely: "expected settable variable, got read-only
    # attribute".
    @property
    def oidc_jwks_url(self) -> str: ...
    @property
    def oidc_jwks_ttl_seconds(self) -> float: ...
    @property
    def oidc_audience(self) -> str | None: ...
    @property
    def oidc_issuer(self) -> str | None: ...
    @property
    def oidc_algorithms(self) -> tuple[str, ...]: ...
    @property
    def oidc_token_exchange_url(self) -> str | None: ...
    @property
    def oidc_token_exchange_client_id(self) -> str | None: ...
    @property
    def oidc_token_exchange_client_secret(self) -> str | None: ...
    @property
    def oidc_admin_users_url(self) -> str | None: ...


@dataclass(frozen=True)
class OidcResolverSettings:
    """A concrete `OidcSettings` for callers outside `services/api` — the harness's verify stage,
    and anything else that needs a resolver without a Conduit configuration behind it."""

    oidc_jwks_url: str
    oidc_token_exchange_url: str | None = None
    oidc_token_exchange_client_id: str | None = None
    oidc_token_exchange_client_secret: str | None = None
    oidc_admin_users_url: str | None = None
    oidc_audience: str | None = None
    oidc_issuer: str | None = None
    oidc_algorithms: tuple[str, ...] = ("RS256",)
    oidc_jwks_ttl_seconds: float = 300.0


# --- preserved from services/api/auth.py ---
#
# """OIDC `Principal` resolution — `spec/03_CONDUIT_MIDDLEWARE.md` §6:
# "OIDC via Keycloak (Apache-2.0). The session token resolves to a
# `Principal` carrying identity, unit, roles, clearance, and the handling
# codes the principal may receive."
# 
# **The JWKS source is a config point, not a hardcoded key.** `ApiConfig.
# oidc_jwks_url` names the endpoint `PyJWKClient` fetches and caches keys
# from — a Keycloak realm's `.../protocol/openid-connect/certs` in a real
# deployment, a loopback HTTP fixture in tests
# (`tests/services/api/test_auth.py`) — `PyJWKClient` deliberately rejects
# any scheme but `http`/`https` (closing exactly the local-file-read risk a
# `jku` header or a misconfigured URL could otherwise open), so the fixture
# is a real, if ephemeral, HTTP server rather than a `file://` URL. Key
# rotation is the thing that breaks first in a real deployment, and
# `PyJWKClient` already does the two things that matter for it: a
# TTL-bounded cache (`cache_keys=True, lifespan=...`) and one refresh-and-
# retry when a token's `kid` isn't in the cached set (`PyJWKClient.
# get_signing_key`) — nothing here reimplements either, and nothing here
# special-cases the fixture path, so the exact same code runs against the
# test fixture's URL as against a real IdP later; only the config value
# changes.
# 
# **Claim names are this deployment's mapping, not a standard.** OIDC has no
# standard claim for `clearance`, `org_unit` or `receivable_handling_codes`
# — those come from `01_DOMAIN_MODEL.md` §2.2's handling model, which no IdP
# knows about natively. A real deployment maps its IdP's actual claims (a
# Keycloak protocol mapper, typically) onto the names below; this module
# does not invent a mapping convention beyond naming what it expects.
# 
# **`resolve_for_owner` — OAuth2 Token Exchange (RFC 8693), `06_DECISIONS.md` ADR-043's own
# accepted mechanism for a stored `owner_id` with no live bearer token.** Exchanges this Conduit's
# own client credentials for a token minted *as* the target owner, then decodes that token through
# `resolve()` below **unchanged** — ADR-043's own central argument is that there is exactly one
# claims-construction path in this codebase, not two; a token obtained by exchange is, from
# `resolve()`'s own perspective, indistinguishable from a live session's token. **Simplified
# relative to a full Keycloak wire protocol, disclosed rather than silently assumed exact:** this
# client authenticates with `client_id`/`client_secret` and requests a token for `requested_subject`
# in one round trip; a real deployment's own two-step client-credentials-then-exchange flow (or
# Keycloak's own "Direct Naked Impersonation" extension) is an operator-configured detail
# `05_DEPLOYMENT.md`'s own operational material owns, not replicated wire-for-wire here. What this
# client and its own test fixture prove is the shape that actually matters for ADR-043's own
# argument: a real async network call, authenticated by client credentials, requesting a token for
# an arbitrary subject id, refused when the IdP's own policy says no, and — the one property Stage
# 1's own containment test exists to pin — returning a token that, once decoded, carries exactly
# that subject's own real claims, never a broader set.
# """


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
    """The identity provider was reached and the exchange was refused — by the realm, or by this
    Conduit's own pre-check below. A real, current fact about that principal, distinct from
    `PrincipalExchangeUnavailable` below."""


class PrincipalRevoked(PrincipalExchangeRefused):
    """The target principal exists at the IdP and is **disabled**.

    A subclass rather than a flag because ADR-044 needs the two apart: a revoked principal is a
    decision the organisation made, and a watch owned by one is marked stopped with the
    revoked-principal reason rather than the generic one. A caller that does not care still
    catches `PrincipalExchangeRefused` and behaves exactly as before.

    **This exists because the realm will not raise it.** Measured against a real Keycloak 26.0 on
    24 September 2026: a client holding the impersonation grant is issued a token for a *disabled*
    user. The refusal has to happen here, in the Conduit, before the exchange is attempted —
    ADR-043's amendment of the same date."""


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

    def __init__(self, config: OidcSettings) -> None:
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

    async def _refuse_if_revoked(self, owner_id: str) -> None:
        """Refuses, before any exchange, if the target principal is disabled at the IdP.

        **The finding this closes, measured rather than assumed** (ADR-043's amendment, 24
        September 2026). Against a real Keycloak 26.0 with token exchange enabled, a client holding
        the impersonation grant was issued a valid access token for a **disabled** user. Keycloak
        scopes impersonation by *requesting client*, not by target subject, and has no per-target
        policy — a bounded attempt to configure one through fine-grained admin permissions failed on
        26.0 (`PUT /users/{id}/management/permissions` → 404; the realm-level
        `adminPermissionsEnabled` toggle → 400). So the realm cannot refuse this, the Conduit must.

        **Read through a separate grant on purpose.** The pre-check uses `oidc_admin_users_url` and
        a view-users capability, not the impersonation client's own authority. Checking with the
        same authority that fails open would be asking the component that already said yes.

        **Unreachable is not revoked.** A network failure here raises
        `PrincipalExchangeUnavailable`, so ADR-044's unreachable path is unchanged and a transient
        IdP outage never marks a live analyst's watches as revoked.

        **Off when unconfigured.** No `oidc_admin_users_url` means no pre-check and the previous
        behaviour exactly, which is what keeps existing deployments working.
        """
        if not self._config.oidc_admin_users_url:
            return
        try:
            response = await self._exchange_http.get(
                self._config.oidc_admin_users_url,
                params={"username": owner_id, "exact": "true"},
                headers={"Authorization": f"Bearer {await self._client_credentials_token()}"},
            )
        except httpx.HTTPError as exc:
            raise PrincipalExchangeUnavailable(
                f"could not read enabled status for owner {owner_id!r}: {exc}"
            ) from exc
        if response.status_code != 200:
            raise PrincipalExchangeUnavailable(
                f"enabled-status read for owner {owner_id!r} returned "
                f"{response.status_code} {response.text}"
            )
        users = response.json()
        if not users:
            raise PrincipalExchangeRefused(
                f"owner {owner_id!r} is not known to the identity provider"
            )
        if not users[0].get("enabled", False):
            raise PrincipalRevoked(
                f"owner {owner_id!r} is disabled at the identity provider — refused by the "
                "Conduit's own pre-check, because the realm will issue a token for a disabled "
                "subject (06_DECISIONS.md ADR-043's amendment)"
            )

    async def _client_credentials_token(self) -> str:
        """This client's own token — used both as the `subject_token` of an exchange and as the
        bearer for the view-users pre-check read. Fetched per call rather than cached:
        ADR-036's own "resolved fresh, never cached" requirement applies to anything that decides
        whether a principal is still live, and a cached admin token would outlive a revoked grant
        exactly the way a cached principal would."""
        response = await self._exchange_http.post(
            self._config.oidc_token_exchange_url or "",
            data={
                "grant_type": "client_credentials",
                "client_id": self._config.oidc_token_exchange_client_id,
                "client_secret": self._config.oidc_token_exchange_client_secret,
            },
        )
        response.raise_for_status()
        token: str = response.json()["access_token"]
        return token

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
        await self._refuse_if_revoked(owner_id)
        try:
            subject_token = await self._client_credentials_token()
        except httpx.HTTPError as exc:
            raise PrincipalExchangeUnavailable(
                f"could not obtain this client's own token before exchanging for {owner_id!r}: "
                f"{exc}"
            ) from exc
        try:
            response = await self._exchange_http.post(
                self._config.oidc_token_exchange_url,
                data={
                    "grant_type": TOKEN_EXCHANGE_GRANT_TYPE,
                    "client_id": self._config.oidc_token_exchange_client_id,
                    "client_secret": self._config.oidc_token_exchange_client_secret,
                    # RFC 8693 §2.1 makes `subject_token` REQUIRED, and this request omitted it
                    # until 24 September 2026. Nothing noticed, because the only thing this code
                    # had ever been run against was the ephemeral fixture ADR-043's own cost note
                    # describes — which accepted a request a real Keycloak refuses outright with
                    # `access_denied` / "Client not allowed to exchange". Measured against
                    # Keycloak 26.0: identical request, with and without this field, refused and
                    # granted respectively. The token exchanged is this client's own
                    # client-credentials token, which is what identifies the *acting* party; the
                    # `requested_subject` below identifies the party acted for.
                    "subject_token": subject_token,
                    "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
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
            raise PrincipalResolutionError(f"token is missing required claim: {exc}") from exc

        return Principal(
            id=str(claims["sub"]),
            clearance=clearance,
            org_unit=org_unit,
            receivable_handling_codes=list(claims.get(CLAIM_RECEIVABLE_HANDLING_CODES, [])),
            roles=list(claims.get(CLAIM_ROLES, [])),
        )
