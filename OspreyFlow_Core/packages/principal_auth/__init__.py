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

import asyncio
import json
import logging
import os
import re
import threading
import time
import urllib.request
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from typing import Any, Protocol, runtime_checkable
from urllib.parse import quote

import httpx
import jwt
from jwt import PyJWKSet
from pydantic import BaseModel, ConfigDict, model_validator

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
# oidc_jwks_url` names the endpoint `SigningKeys` fetches and keeps keys
# from — a Keycloak realm's `.../protocol/openid-connect/certs` or Entra ID's
# `.../discovery/v2.0/keys` in a real deployment, a loopback HTTP fixture in
# tests (`tests/services/api/test_auth.py`). `SigningKeys` refuses any scheme
# but `http`/`https` (closing the local-file-read risk a misconfigured URL
# could otherwise open), so the fixture is a real, if ephemeral, HTTP server
# rather than a `file://` URL. Key rotation is the thing that breaks first in
# a real deployment: `SigningKeys` keeps the set for its configured time,
# fetches again for a key id it does not hold (at most once per five
# minutes), and keeps the last good set through a short outage (ADR-148
# Amendment 8; it replaced `PyJWKClient`, whose cache could not be told to
# fetch in one thread while others go on, nor to tell an unreachable
# identity provider from a body that is not JSON). Nothing here special-cases
# the fixture path, so the same code runs against the fixture's URL as
# against a real IdP; only the config value changes.
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


# --- where the principal's claims come from: settings, not fixed names (ADR-148 decision 9) ---
#
# Entra ID issues no `clearance`, `org_unit` or `receivable_handling_codes` claim. The deployment
# says, for each, which token claim carries it (a directory extension attribute,
# `extension_<app id>_<name>`) or a table from Entra group id to value. The default is the three
# fixed names this module always read, so every deployment that names nothing behaves exactly as
# before. Only the *source names* are settings: what a principal is, and the one function that
# builds it (`principal_from_claims`), stay here.
#
# **Refused, never guessed** (CLAUDE.md rules 3 and 5's spirit): a clearance or unit with no source
# in the token, groups granting more than one clearance or unit, a group overage, or a value of the
# wrong type is a `PrincipalResolutionError` (a 401), never a default. `principal_auth` holds no
# marking scheme, so "the lowest of two clearances" is not something it could compute honestly;
# and a person in two clearance groups is a directory error the operator should see. An unmapped
# group grants nothing.


#: The delegated scope the Glass asks this API for, unless the mapping names another.
DEFAULT_SCOPE = "access_as_user"

#: The claim mapping's environment variable: the profile renders `cloud_platform.claims` into it as
#: JSON (ADR-148 Amendment 8); unset, the fixed names (Keycloak).
CLAIM_MAPPING_VARIABLE = "OSPREY_CLAIM_MAPPING"

#: An Entra object id (a tenant, a group, a person, an application): lower-case, as Entra writes it
#: in a token. The one pattern: `entra_people` and `service_identity` use `is_object_id`.
_GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def is_object_id(value: object) -> bool:
    return isinstance(value, str) and bool(_GUID.match(value))


class _Source(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim: str | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> _Source:
        groups = getattr(self, "groups", None)
        if (self.claim is None) == (groups is None):
            raise ValueError("name exactly one of `claim` or `groups`")
        if self.claim is not None and not self.claim:
            raise ValueError("`claim` must name a claim")
        if groups is not None:
            if not groups:
                raise ValueError("`groups` must map at least one group")
            for group, value in groups.items():
                values = value if isinstance(value, list) else [value]
                if not values or not all(values):
                    raise ValueError(f"group {group!r} must grant a non-empty value")
                if not _GUID.match(group):
                    # A mistyped id would match no token's group and silently grant nothing.
                    raise ValueError(f"group {group!r} is not an Entra group id (a GUID)")
        return self


class ValueSource(_Source):
    """Where a single-valued claim (clearance, organisational unit) comes from: a token claim, or a
    table from group id to value."""

    groups: dict[str, str] | None = None


class CodesSource(_Source):
    """Where the receivable handling codes come from: a token claim (a list, or one code as a
    string), or a table from group id to the codes that group grants."""

    groups: dict[str, list[str]] | None = None


class ClaimMapping(BaseModel):
    """The deployment's claim settings.

    **A mapping other than the fixed names is an Entra ID mapping, and needs `tenant_id`** (ADR-148
    decision 9 is the only reason the names are settings; a Keycloak deployment maps onto the fixed
    names with protocol mappers). With `tenant_id` set the token must carry `oid` and `exp` and a
    `tid` equal to it, the resolver must check issuer and audience, and **roles are not read from
    the token**: an Entra token's `roles` are app roles an Entra administrator assigns, and roles
    stay assigned in Admin › People (decision 9). An app-only token (a daemon's, with no `scp`) is
    no person and is refused; so is a token without this API's `scope`, one issued to a client
    other than `client_id` (the Glass), and a guest's. The principal is keyed by `oid`, not by
    Entra's pairwise `sub`. A token carrying `tid` under the fixed names (Keycloak) is refused.

    **The validators are the safety, so the resolver validates again** what it is given:
    `model_copy` and `model_construct` skip them, and a copy of the default mapping with a changed
    source would otherwise be Keycloak-handled (no tenant check, the token's roles read)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    clearance: ValueSource = ValueSource(claim=CLAIM_CLEARANCE)
    org_unit: ValueSource = ValueSource(claim=CLAIM_ORG_UNIT)
    handling_codes: CodesSource = CodesSource(claim=CLAIM_RECEIVABLE_HANDLING_CODES)
    groups_claim: str = "groups"
    tenant_id: str | None = None
    #: The Glass's own app registration: an Entra token's `azp` (v2.0) or `appid` (v1.0) must name
    #: it, so a token another application obtained for this API is no session of ours.
    client_id: str | None = None
    #: This API's own app registration (application id): never an orchestrator's service
    #: identity, whichever form the audience takes (v1.0 tokens name the `api://` URI there).
    api_client_id: str | None = None
    #: The delegated scope the Glass asks for; an Entra token's `scp` must include it.
    scope: str = DEFAULT_SCOPE

    @model_validator(mode="after")
    def _entra_needs_its_tenant(self) -> ClaimMapping:
        if not self.groups_claim:
            raise ValueError("`groups_claim` must name a claim")
        if self.tenant_id is not None and not _GUID.match(self.tenant_id):
            raise ValueError("`tenant_id` must be the Entra tenant's id (a GUID)")
        if self.tenant_id is not None and (
            self.client_id is None or not _GUID.match(self.client_id)
        ):
            raise ValueError("an Entra ID mapping needs `client_id`, the Glass's application id")
        if not self.scope or " " in self.scope:
            raise ValueError("`scope` must name one delegated scope")
        if self.api_client_id is not None and not _GUID.match(self.api_client_id):
            raise ValueError("`api_client_id` must be the API's application id (a GUID)")
        if self.tenant_id is None and (
            self.client_id is not None
            or self.api_client_id is not None
            or self.scope != DEFAULT_SCOPE
        ):
            # Only an Entra mapping checks the client and the scope; accepted here they would be
            # ignored, and a deployment that set them would believe they were checked.
            raise ValueError(
                "`client_id` and `scope` are checked only for an Entra ID mapping: set `tenant_id`"
            )
        fixed = (
            self.clearance == ValueSource(claim=CLAIM_CLEARANCE)
            and self.org_unit == ValueSource(claim=CLAIM_ORG_UNIT)
            and self.handling_codes == CodesSource(claim=CLAIM_RECEIVABLE_HANDLING_CODES)
            and self.groups_claim == "groups"
        )
        if not fixed and self.tenant_id is None:
            raise ValueError(
                "a claim mapping other than the fixed names is an Entra ID mapping: "
                "set `tenant_id`, so the tenant, issuer and audience are checked"
            )
        return self

    @property
    def is_entra(self) -> bool:
        return self.tenant_id is not None

    @classmethod
    def from_env(cls) -> ClaimMapping:
        """The deployment's mapping from `OSPREY_CLAIM_MAPPING` (JSON), or the fixed names when it
        is unset. A value that is not JSON or not a valid mapping stops the Conduit at start, in
        words: a sign-in mapping that silently fell back to the fixed names would be Keycloak-
        handled, with no tenant check."""
        raw = os.environ.get(CLAIM_MAPPING_VARIABLE, "").strip()
        if not raw:
            return DEFAULT_CLAIM_MAPPING
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise ValueError(f"{CLAIM_MAPPING_VARIABLE} is not JSON: {exc}") from None
        return cls.model_validate(data)

    def required_claims(self) -> list[str]:
        """The claims PyJWT must find before anything is mapped. `tid` and `oid` are checked once
        each, in `principal_from_claims` (an absent one fails there), and `sub`'s type is PyJWT's
        own check."""
        return ["sub", "exp"] if self.is_entra else ["sub"]


DEFAULT_CLAIM_MAPPING = ClaimMapping()

#: How long a session waits for its stored roles before the request is a 503.
ROLE_LOOKUP_TIMEOUT_SECONDS = 2.0

#: Entra's own cap on the groups a JWT carries; past it the claim is replaced by an overage.
MAX_TOKEN_GROUPS = 200


def _token_groups(claims: Mapping[str, Any], mapping: ClaimMapping) -> list[str]:
    """The token's group ids. A group overage (Entra leaves `groups` out of a JWT past 200 groups
    and names a Graph source in `_claim_names`, or, in the implicit flow, sends `hasgroups: true`)
    is refused, never read as "no groups"."""
    names = claims.get("_claim_names")
    if mapping.groups_claim not in claims and (
        (isinstance(names, dict) and mapping.groups_claim in names)
        or claims.get("hasgroups") is True
    ):
        raise PrincipalResolutionError(
            f"token has a group overage: its `{mapping.groups_claim}` claim was left out for "
            "Graph; limit the groups the app's token carries (groups assigned to the application)"
        )
    groups = claims.get(mapping.groups_claim, [])
    if not isinstance(groups, list) or not all(isinstance(g, str) for g in groups):
        raise PrincipalResolutionError(
            f"token's `{mapping.groups_claim}` claim is not a list of group ids"
        )
    if len(groups) > MAX_TOKEN_GROUPS:
        # Entra never sends more; a longer list is not a token Entra issued.
        raise PrincipalResolutionError(
            f"token's `{mapping.groups_claim}` claim lists more than {MAX_TOKEN_GROUPS} groups"
        )
    return groups


def _single_value(
    claims: Mapping[str, Any], source: ValueSource, what: str, groups: list[str]
) -> str:
    if source.claim is not None:
        value = claims.get(source.claim)
        if value is None:
            raise PrincipalResolutionError(
                f"token is missing required claim: {what} ({source.claim!r})"
            )
        if not isinstance(value, str) or not value:
            raise PrincipalResolutionError(
                f"token's {what} claim ({source.claim!r}) is not a non-empty string"
            )
        return value
    assert source.groups is not None
    found = {source.groups[g] for g in groups if g in source.groups}
    if not found:
        raise PrincipalResolutionError(
            f"token is missing required claim: no group grants the {what}"
        )
    if len(found) > 1:
        raise PrincipalResolutionError(f"token's groups grant more than one {what}; refused")
    return found.pop()


def _string_list(claims: Mapping[str, Any], claim: str, what: str) -> list[str]:
    """A claim holding names: a list of strings, or one string as **one** name (never its
    letters, as `list("RS")` would make it); absent is none. An empty name is refused, and a name
    given twice is kept once, as the group path keeps a code two groups grant."""
    value = claims.get(claim, [])
    names = [value] if isinstance(value, str) else value
    if not isinstance(names, list) or not all(isinstance(v, str) for v in names):
        raise PrincipalResolutionError(f"token's {what} claim ({claim!r}) is not a list of names")
    if not all(names):
        raise PrincipalResolutionError(f"token's {what} claim ({claim!r}) holds an empty name")
    return list(dict.fromkeys(names))


def _handling_codes(claims: Mapping[str, Any], source: CodesSource, groups: list[str]) -> list[str]:
    if source.claim is not None:
        return _string_list(claims, source.claim, "handling codes")
    assert source.groups is not None
    codes: list[str] = []
    for g in groups:
        for code in source.groups.get(g, []):
            if code not in codes:
                codes.append(code)
    return codes


#: Entra's two issuer forms, v1.0 and v2.0, each naming the tenant (Amendment 6's assumptions).
_ENTRA_ISSUER = re.compile(
    r"^https://(?:sts\.windows\.net/(?P<v1>[0-9a-f-]{36})/"
    r"|login\.microsoftonline\.com/(?P<v2>[0-9a-f-]{36})/v2\.0)$"
)


def _tenant_of_entra_issuer(value: object) -> str | None:
    """The tenant an Entra issuer URL names, in either form, or None for anything else (another
    provider, a federation's own issuer, a malformed URL). Entra sends `idp` only for an account
    homed elsewhere, and in either form whatever the token's own version, so a member's `idp` is
    compared by its tenant, never as a string against `iss` (CARRIES, P10 round 2)."""
    if not isinstance(value, str):
        return None
    found = _ENTRA_ISSUER.match(value)
    if found is None:
        return None
    tenant = found.group("v1") or found.group("v2")
    return tenant if _GUID.match(tenant) else None


@dataclass(frozen=True)
class StoredPerson:
    """What the deployment keeps of an Entra person (ADR-148 Amendment 8): the roles Admin › People
    gave them and whether an administrator disabled them here. Entra holds the account; these are
    ours."""

    roles: tuple[str, ...]
    disabled: bool


@dataclass(frozen=True)
class SeenPerson:
    """What a verified token says of the person, for Admin › People's list: their names as Entra
    gives them (`name`, `preferred_username`, `email`, each text or none) and the clearance, unit
    and codes the mapping resolved. Never their roles: those are only ever the store's."""

    name: str | None
    username: str | None
    email: str | None
    clearance: str
    org_unit: str
    receivable_handling_codes: tuple[str, ...]


def _text_claim(claims: Mapping[str, Any], name: str) -> str | None:
    value = claims.get(name)
    return value[:200] if isinstance(value, str) and value else None


@dataclass(frozen=True)
class StoredDashboard:
    """A dashboard identity as the deployment registered it (ADR-148 Amendment 10): Admin ›
    Dashboards' clearance, unit and handling codes for one Entra app registration."""

    application_id: str
    clearance: str
    org_unit: str
    receivable_handling_codes: tuple[str, ...]
    #: Its name, the slug Keycloak's `osprey-dashboard-<slug>` carries; Superset's embedding
    #: matches a board on it. The resolver never reads it.
    name: str = ""


class DashboardSource(Protocol):
    """Where a dashboard identity is read (ADR-148 Amendment 10): the deployment's own store, keyed
    by tenant and the registration's application id; `None` when it is not registered. It raises on
    any failure, which the resolver turns into `PrincipalLookupUnavailable`, never a principal."""

    async def dashboard(self, tenant_id: str, application_id: str) -> StoredDashboard | None: ...


class RoleSource(Protocol):
    """Where an Entra principal's roles are read (ADR-148 Amendment 8, the orchestrator's ruling of
    11 November 2026): the deployment's own store, keyed by tenant and object id. `person` records
    a person on their first sign-in (with no roles) and answers what is stored; it raises on any
    failure, which the resolver turns into `PrincipalLookupUnavailable`, never a principal."""

    async def person(self, tenant_id: str, oid: str, seen: SeenPerson) -> StoredPerson: ...


class PrincipalLookupUnavailable(Exception):
    """The stored person could not be read in time (the store down, slow or answering something
    malformed): a 503, never a principal with no roles and never one from an earlier read."""


class SigningKeysUnavailable(PrincipalLookupUnavailable):
    """The identity provider's signing keys could not be read (unreachable, or no answer in time):
    a 503 in its own words, never "token rejected", since nothing about the token is known."""


#: How long a session waits for the identity provider's keys before it is a 503.
KEYS_TIMEOUT_SECONDS = 5.0
#: At most one fetch of the keys for a key id not held, per this long (ADR-148 Amendment 8): a
#: token naming an unknown key cannot make every request fetch them again. A key published within
#: this long after such a fetch is refused until the next one (or the keys' own time is up).
UNKNOWN_KID_REFETCH_SECONDS = 300.0
#: Past the keys' own time, a fetch that fails leaves the last good set in use for this long
#: (logged), so a short outage at the identity provider signs nobody out; after it, a 503.
KEYS_GRACE_SECONDS = 3600.0
#: Leeway on a token's times, for clocks a little apart.
LEEWAY_SECONDS = 60
#: The one algorithm an Entra ID token is signed with, whatever `OIDC_ALGORITHMS` says.
ENTRA_ALGORITHMS = ("RS256",)
#: The keys' own threads: a slow identity provider holds these, never `asyncio.to_thread`'s pool
#: that the rest of the Conduit shares.
KEYS_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="signing-keys")

_log = logging.getLogger(__name__)


async def in_keys_thread[T](call: Callable[..., T], *args: Any) -> T:
    """`call(*args)` in the keys' own threads, bounded **in total** by `KEYS_TIMEOUT_SECONDS`: a
    slow identity provider never holds the event loop, and however its answer is slow (a name that
    does not resolve, a connection, a body that trickles in under each read's own timeout) the
    caller has `SigningKeysUnavailable` by then. A fetch still running past it is abandoned
    (`SigningKeys._take_fetch`), so the next caller may try again."""
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(KEYS_EXECUTOR, partial(call, *args)),
            timeout=KEYS_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise SigningKeysUnavailable(
            "sign-in is unavailable: the identity provider's signing keys did not answer"
        ) from exc


_UNREADABLE = "sign-in is unavailable: the identity provider's signing keys could not be read"


class SigningKeys:
    """The identity provider's signing keys, as the resolver and the service identity's verifier
    read them (ADR-148 Amendment 8; the orchestrator's second review of P10 part 2):

    - **kept** for the configured time, and fetched by **one thread at a time**: while one fetches,
      the others go on with the last good set rather than wait; concurrent sign-ins that find the
      keys out of date fetch once (each reads the set's age once, before anything else);
    - past their time, a fetch that fails leaves the last good set in use for
      `KEYS_GRACE_SECONDS` (logged), then `SigningKeysUnavailable`. A key the identity provider has
      rotated out therefore stays valid for up to the keys' time plus that hour while it cannot be
      reached;
    - for a key id not held, fetched again at most once per `UNKNOWN_KID_REFETCH_SECONDS`, counted
      from the last fetch that succeeded (an unreachable identity provider is a 503 each time,
      never a 401); a key not published is `PrincipalResolutionError` (401);
    - each fetch bounded in total by `in_keys_thread`'s wait; a fetch held past
      `KEYS_TIMEOUT_SECONDS` is abandoned, its answer dropped, and the next caller fetches. Every
      way the identity provider can fail to give keys (unreachable, a refusal, a body that is not
      JSON, a set with no usable key, a set whose keys are all for encryption or have no key id)
      is `SigningKeysUnavailable`, a 503 in words, never "token rejected", which signs people out.

    Synchronous: callers on the event loop use `in_keys_thread`."""

    def __init__(
        self, url: str, ttl_seconds: float, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError("the signing keys' URL (OIDC_JWKS_URL) must be http or https")
        self._url = url
        self._ttl = ttl_seconds
        self._clock = clock
        self._held: dict[str, Any] | None = None
        self._fetched_at = float("-inf")
        self._last_unknown_fetch = float("-inf")
        # Who is fetching now, and until when (real time, whatever `clock` is): one at a time, a
        # fetch past its deadline abandoned. Guarded by `_state`, which nothing holds across I/O.
        self._state = threading.Condition()
        self._fetch_owner: object | None = None
        self._fetch_deadline = 0.0
        self._stamp_lock = threading.Lock()
        #: Fetches made (each a request to the identity provider), for the record.
        self.fetches = 0

    def _fetch(self) -> dict[str, Any]:
        self.fetches += 1
        try:
            request = urllib.request.Request(self._url, headers={"User-Agent": "ospreyflow"})
            with urllib.request.urlopen(request, timeout=KEYS_TIMEOUT_SECONDS) as response:  # noqa: S310 - the configured JWKS URL
                data = json.load(response)
            jwk_set = PyJWKSet.from_dict(data)
        except (OSError, ValueError, TypeError, AttributeError, jwt.PyJWTError) as exc:
            # OSError: unreachable, refused or timed out (URLError, HTTPError, TimeoutError);
            # ValueError: not JSON; the rest: not a key set, or none of its keys usable.
            raise SigningKeysUnavailable(_UNREADABLE) from exc
        keys = {k.key_id: k for k in jwk_set.keys if k.key_id and k.public_key_use in ("sig", None)}
        if not keys:
            # Keys only for encryption, or none naming a key id: nothing a token can be checked by.
            raise SigningKeysUnavailable(_UNREADABLE)
        return keys

    def _take_fetch(self, *, wait: bool) -> object | None:
        """The right to fetch, one thread at a time. A fetch held past `KEYS_TIMEOUT_SECONDS` is
        abandoned (its thread stuck on a slow identity provider, its caller already answered by
        `in_keys_thread`), so it is taken from it. None when another thread fetches and `wait` is
        false; with `wait`, None when none finished within `KEYS_TIMEOUT_SECONDS`."""
        token = object()
        until = time.monotonic() + KEYS_TIMEOUT_SECONDS
        with self._state:
            while True:
                now = time.monotonic()
                if self._fetch_owner is None or now >= self._fetch_deadline:
                    self._fetch_owner = token
                    self._fetch_deadline = now + KEYS_TIMEOUT_SECONDS
                    return token
                if not wait or now >= until:
                    return None
                self._state.wait(timeout=min(until, self._fetch_deadline) - now)

    def _give_back(self, token: object, keys: dict[str, Any] | None) -> None:
        """The fetch done: its keys kept, unless it was abandoned meanwhile (then dropped)."""
        with self._state:
            if self._fetch_owner is token:
                if keys is not None:
                    self._held, self._fetched_at = keys, self._clock()
                self._fetch_owner = None
                self._state.notify_all()

    def _refresh(self, *, wait: bool, seen: float) -> None:
        """Fetch, one thread at a time, unless another has fetched since `seen`. With `wait`, wait
        for a fetch under way (bounded) and use what it got; without, go on with the last good set
        while another thread fetches."""
        token = self._take_fetch(wait=wait)
        if token is None:
            if wait:
                raise SigningKeysUnavailable(_UNREADABLE)
            return
        keys: dict[str, Any] | None = None
        try:
            if self._fetched_at != seen and self._held is not None:
                return  # another thread fetched while this one waited
            keys = self._fetch()
        finally:
            self._give_back(token, keys)

    def _current(self, seen: float) -> dict[str, Any]:
        age = self._clock() - seen
        if age >= self._ttl:
            past_grace = self._held is None or age >= self._ttl + KEYS_GRACE_SECONDS
            try:
                self._refresh(wait=past_grace, seen=seen)
            except SigningKeysUnavailable:
                if past_grace:
                    raise
                _log.warning(
                    "the identity provider's signing keys could not be read; the last good set, "
                    "%.0f s old, is used for at most %.0f s more",
                    age, self._ttl + KEYS_GRACE_SECONDS - age,
                )  # fmt: skip
        if self._held is None:
            raise SigningKeysUnavailable(_UNREADABLE)
        return self._held

    def key_for(self, token: str) -> Any:
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except jwt.PyJWTError as exc:
            raise PrincipalResolutionError(f"token rejected: {exc}") from exc
        seen = self._fetched_at
        keys = self._current(seen)
        if kid not in keys:
            with self._stamp_lock:
                now = self._clock()
                fresh = self._fetched_at != seen  # fetched in this very call: it opens the window
                due = not fresh and now - self._last_unknown_fetch >= UNKNOWN_KID_REFETCH_SECONDS
                if fresh:
                    self._last_unknown_fetch = now
            if due:
                self._refresh(wait=True, seen=self._fetched_at)
                # Only once a fetch has succeeded: an unreachable identity provider stays a 503.
                with self._stamp_lock:
                    self._last_unknown_fetch = self._clock()
                keys = self._held or {}
        if kid not in keys:
            raise PrincipalResolutionError(
                "token rejected: it names a signing key the identity provider does not publish"
            )
        return keys[kid].key


@dataclass(frozen=True)
class _Verified:
    """A verified token's principal parts, before roles: built only by `_verified_parts`."""

    id: str
    clearance: str
    org_unit: str
    codes: list[str]
    token_roles: list[str]


def _stored_roles(stored: StoredPerson) -> list[str]:
    roles = stored.roles
    if not isinstance(roles, tuple) or not all(isinstance(r, str) and r for r in roles):
        raise PrincipalLookupUnavailable("the stored person's roles are not a list of role names")
    return list(dict.fromkeys(roles))


def principal_from_claims(
    claims: Mapping[str, Any],
    mapping: ClaimMapping,
    stored: StoredPerson | StoredDashboard | None = None,
) -> Principal:
    """The one claims-construction path (ADR-043; ADR-148 decision 9): every `Principal` this
    package builds, from a session's token or an exchanged one, is built here from verified
    claims. An Entra principal's roles are the stored person's (`stored`, read by the resolver
    from its `RoleSource`), never the token's; one disabled here is refused (401). A dashboard
    identity's (ADR-148 Amendment 10, `stored` its registration) is its registration's clearance,
    unit and codes, the role `reports_viewer` alone, admitted to `DASHBOARD_ROUTES` alone."""
    routes: list[str] | None = None
    if isinstance(stored, StoredDashboard):
        principal_id = _verified_dashboard(claims, mapping)
        if principal_id != stored.application_id:
            raise PrincipalLookupUnavailable("the store answered another dashboard identity")
        clearance, org_unit = stored.clearance, stored.org_unit
        codes, roles = list(stored.receivable_handling_codes), ["reports_viewer"]
        routes = sorted(DASHBOARD_ROUTES)
    else:
        verified = _verified_parts(claims, mapping)
        if mapping.is_entra:
            if stored is None:
                raise PrincipalLookupUnavailable(
                    "an Entra principal's roles are read from the deployment's store, and none "
                    "was read"
                )
            if stored.disabled:
                raise PrincipalResolutionError(
                    "this account is disabled in this deployment: ask an administrator"
                )
            roles = _stored_roles(stored)
        else:
            if stored is not None:
                raise PrincipalLookupUnavailable(
                    "a stored person is read only for an Entra mapping"
                )
            roles = verified.token_roles
        principal_id, clearance, org_unit = verified.id, verified.clearance, verified.org_unit
        codes = verified.codes
    return Principal(
        # Entra: the object id, one per person in the (pinned) tenant, which Graph also gives, so
        # Admin › People can assign roles before a first sign-in; Entra's `sub` is pairwise per
        # application. Keycloak: `sub`, required and refused unless a string by PyJWT's decode.
        # A dashboard identity: its registration's application id.
        id=principal_id,
        clearance=clearance,
        org_unit=org_unit,
        receivable_handling_codes=codes,
        roles=roles,
        routes=routes,
    )


#: ADR-148 Amendment 10: the app role a dashboard identity's registration holds on the API's own
#: (an application permission the client's Entra administrator grants), without which its app-only
#: token is no dashboard; and the routes alone such a principal is admitted to.
DASHBOARD_APP_ROLE = "Dashboard.Read"
DASHBOARD_ROUTES = frozenset(
    {"GET /v1/investigations", "GET /v1/investigations/{investigation_id}/reports/feed"}
)


def _verified_dashboard(claims: Mapping[str, Any], mapping: ClaimMapping) -> str:
    """A dashboard identity's app-only token (ADR-148 Amendment 10), checked before its
    registration is read: the pinned tenant, one client that is an application id and neither the
    Glass's nor this API's, and the app role. Answers that client's application id."""
    if not mapping.is_entra or mapping.tenant_id is None:
        raise PrincipalResolutionError("a dashboard identity is read only for an Entra mapping")
    if claims.get("tid") != mapping.tenant_id:
        raise PrincipalResolutionError("token's tid is missing or names another tenant")
    # v2.0 names the client in `azp`, v1.0 in `appid`: one client, whichever are present.
    # A claim of any other shape than a string is no client: refused, never an error.
    named = [claims[c] for c in ("azp", "appid") if c in claims]
    texts = all(isinstance(c, str) for c in named)
    client = named[0] if named and texts and len(set(named)) == 1 else None
    # The audience a verified token names (one, or a list holding the configured one) is the API's.
    aud = claims.get("aud")
    audiences = [aud] if isinstance(aud, str) else aud if isinstance(aud, list) else []
    own = {mapping.client_id, mapping.api_client_id, *(a for a in audiences if isinstance(a, str))}
    if not isinstance(client, str) or not _GUID.match(client) or client in own:
        raise PrincipalResolutionError(
            "token is app-only and its client is no dashboard identity's application"
        )
    roles = claims.get("roles")
    if not isinstance(roles, list) or DASHBOARD_APP_ROLE not in roles:
        raise PrincipalResolutionError(
            f"token is app-only without the app role {DASHBOARD_APP_ROLE}: no dashboard identity"
        )
    return client


def _is_app_only(claims: Mapping[str, Any]) -> bool:
    """An Entra token with no person behind it: `idtyp: app`, or no delegated `scp`."""
    scope = claims.get("scp")
    return claims.get("idtyp") == "app" or not isinstance(scope, str) or not scope


def _verified_parts(claims: Mapping[str, Any], mapping: ClaimMapping) -> _Verified:
    """Every refusal a token's claims can earn, before anything is read about the person: a
    refused token never records a person in the store."""
    if mapping.is_entra:
        if claims.get("tid") != mapping.tenant_id:
            raise PrincipalResolutionError("token's tid is missing or names another tenant")
        if not isinstance(claims.get("oid"), str) or not _GUID.match(claims["oid"]):
            raise PrincipalResolutionError("token's oid is not an Entra object id")
        scope = claims.get("scp")
        if claims.get("idtyp") == "app" or not isinstance(scope, str) or not scope:
            raise PrincipalResolutionError(
                "token is app-only (no delegated scp): a service principal is no person"
            )
        if not isinstance(scope, str) or mapping.scope not in scope.split(" "):
            raise PrincipalResolutionError(
                f"token's scp does not grant this API's scope ({mapping.scope!r})"
            )
        # v2.0 names the client in `azp`, v1.0 in `appid`: whichever is present must be the Glass.
        clients = [claims[c] for c in ("azp", "appid") if c in claims]
        if not clients or any(c != mapping.client_id for c in clients):
            raise PrincipalResolutionError("token was not issued to the Glass's client")
        # A guest (B2B) account is homed in another tenant: `acct` 1, or an `idp` other than the
        # issuer. Refused until the deployment decides to admit guests (ADR-148 Amendment 6).
        guest_idp = "idp" in claims and _tenant_of_entra_issuer(claims["idp"]) != mapping.tenant_id
        if claims.get("acct") in (1, "1") or guest_idp:
            raise PrincipalResolutionError("token is a guest account's: guests are not admitted")
    elif "tid" in claims:
        # Keycloak never emits `tid`; an Entra token here would skip every check above and have its
        # app roles read as OspreyFlow roles.
        raise PrincipalResolutionError(
            "token carries tid: an Entra ID token is refused without an Entra claim mapping"
        )
    uses_groups = any(
        s.groups is not None for s in (mapping.clearance, mapping.org_unit, mapping.handling_codes)
    )
    groups = _token_groups(claims, mapping) if uses_groups else []
    clearance = _single_value(claims, mapping.clearance, "clearance", groups)
    org_unit = _single_value(claims, mapping.org_unit, "organisational unit", groups)
    return _Verified(
        id=str(claims["oid"]) if mapping.is_entra else str(claims["sub"]),
        clearance=clearance,
        org_unit=org_unit,
        codes=_handling_codes(claims, mapping.handling_codes, groups),
        # Keycloak's `roles` come from Admin › People through its attribute; an Entra token's are
        # app roles an Entra administrator assigns, never read (Amendment 6 point 4).
        token_roles=[] if mapping.is_entra else _string_list(claims, CLAIM_ROLES, "roles"),
    )


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


def _access_token_of(response: httpx.Response, what: str) -> str:
    """The `access_token` of a token endpoint's 200, or `PrincipalExchangeUnavailable`. A body that
    is not JSON, is not an object, or carries no non-empty string token is a malformed answer, not
    a refusal and not an exception of its own: left alone they escaped `resolve_for_owner` as
    `JSONDecodeError`, `AttributeError` and `KeyError`, none a `PrincipalExchangeError`."""
    try:
        body = response.json()
    except ValueError as exc:
        raise PrincipalExchangeUnavailable(
            f"{what} answered 200 with a body that is not JSON"
        ) from exc
    token = body.get("access_token") if isinstance(body, dict) else None
    if not isinstance(token, str) or not token:
        raise PrincipalExchangeUnavailable(f"{what} answered 200 with no access_token")
    return token


class PrincipalResolver:
    """One `SigningKeys` per configured JWKS URL, built once at process
    start and reused for the process lifetime — `resolve()` itself makes
    no state-carrying assumption between calls beyond that set's own
    TTL cache, so this class carries nothing that would break
    `services/api`'s statelessness if two instances of it exist behind a
    load balancer with different local caches: both ask the same JWKS URL
    and converge on the same keys. `resolve_for_owner`'s own `httpx.
    AsyncClient` is built the same way, for the same reason — one per
    process, `aclose()`d at lifespan shutdown alongside every other
    client this codebase already closes there."""

    def __init__(
        self,
        config: OidcSettings,
        *,
        claim_mapping: ClaimMapping | None = None,
        role_source: RoleSource | None = None,
        dashboard_source: DashboardSource | None = None,
        role_lookup_timeout_seconds: float = ROLE_LOOKUP_TIMEOUT_SECONDS,
    ) -> None:
        # Validated again from plain data: a copy or a `model_construct` skips the validators,
        # and they are what make an Entra mapping checked as one.
        mapping = ClaimMapping.model_validate(
            (claim_mapping or DEFAULT_CLAIM_MAPPING).model_dump(mode="python")
        )
        if mapping.is_entra:
            # A tenant-bound mapping that did not check `iss` and `aud` would take another tenant's
            # (or another app's) token signed by a key it trusts: refused before any token is read.
            if not config.oidc_issuer:
                raise ValueError(
                    "an Entra ID claim mapping needs the token issuer checked (OIDC_ISSUER)"
                )
            if not config.oidc_audience:
                raise ValueError(
                    "an Entra ID claim mapping needs the token audience checked (OIDC_AUDIENCE)"
                )
            if role_source is None:
                # Its roles live in the deployment's store (Amendment 8); a resolver that could not
                # read them would build principals with none, or with the token's app roles.
                raise ValueError("an Entra ID claim mapping needs the deployment's people store")
        elif role_source is not None:
            raise ValueError("a people store is read only for an Entra ID claim mapping")
        elif dashboard_source is not None:
            raise ValueError("a dashboard store is read only for an Entra ID claim mapping")
        if role_lookup_timeout_seconds <= 0:
            raise ValueError("the role lookup's timeout must be positive")
        self._role_source = role_source
        self._dashboard_source = dashboard_source
        self._role_lookup_timeout = role_lookup_timeout_seconds
        self._config = config
        self._claim_mapping = mapping
        self._keys = SigningKeys(config.oidc_jwks_url, config.oidc_jwks_ttl_seconds)
        # An Entra mapping's tokens are RS256 alone, whatever OIDC_ALGORITHMS says.
        self._algorithms = (
            list(ENTRA_ALGORITHMS) if mapping.is_entra else list(config.oidc_algorithms)
        )
        self._exchange_http = httpx.AsyncClient(timeout=10.0)

    @property
    def signing_keys(self) -> SigningKeys:
        """The keys this resolver reads, which the run API's service identity verifier shares
        (one cache, one fetch limit; the orchestrator's second review, item 8)."""
        return self._keys

    @property
    def claim_mapping(self) -> ClaimMapping:
        """The mapping this resolver was built with, validated: what the run API's service
        identities are judged by too, so the two never disagree."""
        return self._claim_mapping

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

    async def _refuse_if_revoked(self, owner_id: str) -> str | None:
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
        behaviour exactly, which is what keeps existing deployments working; it answers `None`.

        **Returns the subject id the pre-check judged**, which the exchange then asks for, so the
        two never judge different subjects (an owner recorded by username is exchanged by the id
        that username resolved to). **A 200 is accepted only in the shape the read promises**: the
        by-id read answers the one user, whose `id` is the id asked for, and the username read
        answers a list. Anything else (a URL left at the realm root answers 200 with an object
        whose `enabled` is true) is `PrincipalExchangeUnavailable`, never a pass.
        """
        if not self._config.oidc_admin_users_url:
            return None
        # An owner is recorded by Keycloak's subject id (the token's `sub`, ADR-127 Amendment 34),
        # so it is read as `users/{id}`; a name is read as `users?username=` only when no user has
        # that id, which keeps an owner recorded by username (before that amendment) working.
        # Measured on Keycloak 26.0: the username query for a subject id answers 200 with no users.
        base = self._config.oidc_admin_users_url.rstrip("/")
        try:
            headers = {"Authorization": f"Bearer {await self._client_credentials_token()}"}
            by_id = await self._exchange_http.get(
                f"{base}/{quote(owner_id, safe='')}", headers=headers
            )
            response = by_id
            by_username = by_id.status_code == 404
            if by_username:
                response = await self._exchange_http.get(
                    base, params={"username": owner_id, "exact": "true"}, headers=headers
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
        try:
            found = response.json()
        except ValueError as exc:
            raise PrincipalExchangeUnavailable(
                f"the read of owner {owner_id!r} answered 200 with a body that is not JSON: "
                "OIDC_ADMIN_USERS_URL may not be the realm's users endpoint"
            ) from exc
        if by_username:
            if not isinstance(found, list):
                raise PrincipalExchangeUnavailable(
                    f"the username read for owner {owner_id!r} did not answer a list of users: "
                    "OIDC_ADMIN_USERS_URL may not be the realm's users endpoint"
                )
            users = found
        else:
            if not isinstance(found, dict) or found.get("id") != owner_id:
                raise PrincipalExchangeUnavailable(
                    f"the read of owner {owner_id!r} by id did not answer that user: "
                    "OIDC_ADMIN_USERS_URL may not be the realm's users endpoint"
                )
            users = [found]
        if not users:
            raise PrincipalExchangeRefused(
                f"owner {owner_id!r} is not known to the identity provider"
            )
        if by_username:
            # `exact=true` asks for the whole username; a realm, proxy or version that drops it
            # answers every name that starts with the text. Exactly one user, and the one asked
            # for, or nothing is exchanged: the first of several is a coin toss and a prefix match
            # is somebody else. Keycloak stores usernames in lower case, so the comparison is
            # case-folded.
            if len(users) != 1:
                raise PrincipalExchangeUnavailable(
                    f"the username read for owner {owner_id!r} answered {len(users)} users, "
                    "where exactly one was asked for"
                )
            named = users[0].get("username") if isinstance(users[0], dict) else None
            if not isinstance(named, str) or named.casefold() != owner_id.casefold():
                raise PrincipalExchangeUnavailable(
                    f"the username read for owner {owner_id!r} answered a different user"
                )
        resolved = users[0].get("id") if isinstance(users[0], dict) else None
        if not isinstance(resolved, str) or not resolved:
            raise PrincipalExchangeUnavailable(
                f"the identity provider's answer for owner {owner_id!r} carried no user id"
            )
        if not users[0].get("enabled", False):
            raise PrincipalRevoked(
                f"owner {owner_id!r} is disabled at the identity provider — refused by the "
                "Conduit's own pre-check, because the realm will issue a token for a disabled "
                "subject (06_DECISIONS.md ADR-043's amendment)"
            )
        return resolved

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
        return _access_token_of(response, "this client's own token")

    async def resolve_for_owner_detailed(self, owner_id: str) -> Principal:
        """Raises rather than collapses — see the two exception classes above. Never caches
        anything between calls: `06_DECISIONS.md` ADR-036's own "resolved fresh, never cached"
        requirement, and ADR-043's own freshness argument, both mean every call is a real,
        independent exchange against the IdP's own current state, not a lookup against anything
        this process remembers from a previous call."""
        if self._claim_mapping.is_entra:
            # Entra has no impersonation exchange: a person cannot be signed in as without them
            # (the orchestrator's ruling, 11 November 2026). ADR-044's unreachable path marks the
            # run stopped; a later step gives owners a way to resolve (CARRIES).
            raise PrincipalExchangeUnavailable(
                "owner resolution is unavailable with Entra ID sign-in: a scheduled run cannot act "
                "as its owner on this deployment"
            )
        if not self._config.oidc_token_exchange_url:
            raise PrincipalExchangeUnavailable(
                "OIDC_TOKEN_EXCHANGE_URL is not set — this deployment has not configured "
                "token exchange (06_DECISIONS.md ADR-043)"
            )
        resolved = await self._refuse_if_revoked(owner_id)
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
                    "requested_subject": resolved or owner_id,
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
        exchanged_token = _access_token_of(response, f"the exchange for owner {owner_id!r}")
        try:
            # In the keys' own threads: a fetch of the keys never holds the event loop, and the
            # keys unreadable is the exchange unavailable (ADR-044's path: the run marked stopped),
            # never an exception the scheduler, a monitor or a screening run does not expect.
            return await in_keys_thread(self.resolve, exchanged_token)
        except SigningKeysUnavailable as exc:
            raise PrincipalExchangeUnavailable(
                f"the exchanged token for owner {owner_id!r} could not be checked: {exc}"
            ) from exc
        except PrincipalResolutionError as exc:
            raise PrincipalExchangeRefused(
                f"exchanged token for owner {owner_id!r} failed verification: {exc}"
            ) from exc

    def resolve(self, token: str) -> Principal:
        """A Keycloak session's principal, from its token alone. An Entra principal's roles are
        read from the store, which this synchronous path cannot do: `resolve_principal`."""
        if self._claim_mapping.is_entra:
            raise PrincipalLookupUnavailable(
                "an Entra principal is resolved with its stored roles (resolve_principal)"
            )
        return principal_from_claims(self._verified_claims(token), self._claim_mapping)

    async def resolve_principal(self, token: str) -> Principal:
        """Every session's principal, as the Conduit asks for it. For an Entra mapping the token is
        checked in full first (a refused token records nobody), then the person is read from the
        store, within the timeout: a failure or a slow answer is `PrincipalLookupUnavailable` (a
        503), never a principal with no roles. Nothing is kept between calls."""
        # In a thread, bounded: a slow or unreachable identity provider never holds the event loop,
        # and is a 503 in words, never "token rejected" (ADR-148 Amendment 8).
        claims = await in_keys_thread(self._verified_claims, token)
        if not self._claim_mapping.is_entra:
            return principal_from_claims(claims, self._claim_mapping)
        if self._dashboard_source is not None and _is_app_only(claims):
            return await self._dashboard_principal(claims)
        verified = _verified_parts(claims, self._claim_mapping)
        assert self._role_source is not None and self._claim_mapping.tenant_id is not None
        seen = SeenPerson(
            name=_text_claim(claims, "name"),
            username=_text_claim(claims, "preferred_username"),
            email=_text_claim(claims, "email"),
            clearance=verified.clearance,
            org_unit=verified.org_unit,
            receivable_handling_codes=tuple(verified.codes),
        )
        try:
            stored = await asyncio.wait_for(
                self._role_source.person(self._claim_mapping.tenant_id, verified.id, seen),
                timeout=self._role_lookup_timeout,
            )
        except Exception as exc:  # noqa: BLE001 - every failure of the read is the one 503
            raise PrincipalLookupUnavailable(
                f"the person's stored roles could not be read: {type(exc).__name__}"
            ) from exc
        if not isinstance(stored, StoredPerson):
            raise PrincipalLookupUnavailable("the people store answered something not a person")
        return principal_from_claims(claims, self._claim_mapping, stored)

    async def _dashboard_principal(self, claims: Mapping[str, Any]) -> Principal:
        """ADR-148 Amendment 10: a dashboard identity's app-only token, checked in full before the
        store is read (`_verified_dashboard`); its principal built as every other is."""
        mapping = self._claim_mapping
        assert mapping.tenant_id is not None and self._dashboard_source is not None
        # The API's own audience is refused there: a verified token's `aud` is, or holds, the
        # configured one.
        application_id = _verified_dashboard(claims, mapping)
        try:
            stored = await asyncio.wait_for(
                self._dashboard_source.dashboard(mapping.tenant_id, application_id),
                timeout=self._role_lookup_timeout,
            )
        except Exception as exc:  # noqa: BLE001 - every failure of the read is the one 503
            raise PrincipalLookupUnavailable(
                f"the dashboard identity could not be read: {type(exc).__name__}"
            ) from exc
        if stored is None:
            raise PrincipalResolutionError(
                "token is app-only and its client is not a registered dashboard identity"
            )
        if not isinstance(stored, StoredDashboard):
            raise PrincipalLookupUnavailable("the store answered something not a dashboard")
        return principal_from_claims(claims, mapping, stored)

    def _verified_claims(self, token: str) -> dict[str, Any]:
        try:
            signing_key = self._keys.key_for(token)
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=self._algorithms,
                leeway=LEEWAY_SECONDS,
                audience=self._config.oidc_audience,
                issuer=self._config.oidc_issuer,
                options={
                    "require": self._claim_mapping.required_claims(),
                    "verify_aud": self._config.oidc_audience is not None,
                    "verify_iss": self._config.oidc_issuer is not None,
                },
            )
        except jwt.PyJWTError as exc:
            raise PrincipalResolutionError(f"token rejected: {exc}") from exc

        # A missing clearance or unit is refused, not defaulted to "": defaulting would still fail
        # closed (`01_DOMAIN_MODEL.md` §2.2: an unrecognised clearance sees nothing) but silently,
        # as a principal who can never see anything rather than a rejected token — worse for
        # whoever has to debug an IdP misconfiguration than an explicit 401.
        return dict(claims)
