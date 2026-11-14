"""A service identity's sign-in, for the run API (`06_DECISIONS.md` ADR-141 decision 10; R14).

An orchestrator's client signs in to the deployment's identity provider with the OAuth 2.0
client-credentials grant and sends that token. It is not a person's: it carries no clearance or
unit, so `PrincipalResolver.resolve` refuses it (401) on every other route, which is what keeps a
service identity from reading anything. This module verifies it the same way (the realm's JWKS,
audience and issuer) and answers only *which client* it is.

**What Keycloak puts in such a token, and what is required here.** A client-credentials token
names its client in `azp`, and its subject is the client's service-account user, whose username
Keycloak makes `service-account-<client id, lower case>` (`preferred_username`). Both are required
and must agree, so a person's token (whose `preferred_username` is the person's) is never taken
for a service identity's, whatever its `azp`. **Not yet measured against a real Keycloak**
(rule 15): the claims are Keycloak 26's documented ones, and the live run under the lease is where
they are checked; REPORT.md says so until it is.
"""

from __future__ import annotations

import jwt

from principal_auth import (
    DASHBOARD_APP_ROLE,
    DEFAULT_CLAIM_MAPPING,
    ENTRA_ALGORITHMS,
    LEEWAY_SECONDS,
    ClaimMapping,
    OidcSettings,
    PrincipalResolutionError,
    SigningKeys,
    SigningKeysUnavailable,
    is_object_id,
)

SERVICE_ACCOUNT_PREFIX = "service-account-"

#: The deployment's own clients are named `osprey-*` (the Conduit, the Glass, the Admin console, a
#: report dashboard `osprey-dashboard-*`, the verify probes: `harness/realm.py`, `identity.py`).
#: Several have service accounts; none is an orchestrator, so none may trigger a pipeline (rule 3,
#: the independent review of L1.7).
DEPLOYMENT_CLIENT_PREFIX = "osprey-"
DEPLOYMENT_CLIENT_WORDS = (
    "that client is one of the deployment's own (osprey-…): name the orchestrator's own client"
)


def is_deployment_client(client: str) -> bool:
    return client.lower().startswith(DEPLOYMENT_CLIENT_PREFIX)


class ServiceIdentityRefused(Exception):
    """A token that is not a service identity's, said in words that name no claim's value.
    `status`: 401 for a sign-in that could not be verified, 403 for a verified one that is not a
    service identity's (a person's)."""

    def __init__(self, words: str, *, status: int) -> None:
        super().__init__(words)
        self.status = status


NOT_A_SERVICE_IDENTITY = (
    "the sign-in is not a service identity's: sign in with the client-credentials "
    "grant of the client the pipeline is owned externally by"
)


#: ADR-148 Amendment 10: a dashboard identity reads the report feed and never submits runs.
DASHBOARD_IS_NO_SERVICE_IDENTITY = (
    "the sign-in is a dashboard identity's: a dashboard reads the report feed and never "
    "submits runs"
)


class ServiceIdentityVerifier:
    """**On Entra ID sign-in** (ADR-148 Amendment 8) a service identity's token is an app-only
    token of the pinned tenant: the configured issuer and audience, `tid` the tenant, no delegated
    `scp`, `idtyp` `app` where present, and its client (`azp`, or `appid` in v1.0; the same if both)
    an application id that is neither the Glass's nor this API's own. Entra issues no
    `preferred_username` for an application, so the Keycloak rule below cannot apply. **On
    Keycloak**, a token carrying `tid` (Entra's) is refused, as `principal_auth` refuses one."""

    def __init__(
        self,
        config: OidcSettings,
        *,
        claim_mapping: ClaimMapping = DEFAULT_CLAIM_MAPPING,
        signing_keys: SigningKeys | None = None,
    ) -> None:
        mapping = ClaimMapping.model_validate(claim_mapping.model_dump(mode="python"))
        if mapping.is_entra and not (config.oidc_issuer and config.oidc_audience):
            raise ValueError(
                "a service identity on Entra ID needs the token issuer and audience checked "
                "(OIDC_ISSUER, OIDC_AUDIENCE)"
            )
        self._mapping = mapping
        self._config = config
        # The keys as `principal_auth` reads them: kept, an unknown key id fetched again at most
        # once per five minutes, each fetch bounded (ADR-148 Amendment 8). The Conduit passes the
        # person path's own set (the same URL), so the two share one cache and one fetch limit.
        self._keys = signing_keys or SigningKeys(
            config.oidc_jwks_url, config.oidc_jwks_ttl_seconds
        )
        self._algorithms = (
            list(ENTRA_ALGORITHMS) if mapping.is_entra else list(config.oidc_algorithms)
        )

    def client_of(self, token: str) -> str:
        """The client a service identity's token names; `ServiceIdentityRefused` otherwise."""
        try:
            key = self._keys.key_for(token)
            claims = jwt.decode(
                token,
                key,
                algorithms=self._algorithms,
                leeway=LEEWAY_SECONDS,
                audience=self._config.oidc_audience,
                issuer=self._config.oidc_issuer,
                options={
                    # `azp` is judged below: a person's verified token without one is 403, not 401.
                    # `exp` too: a client-credentials token always carries one.
                    "require": ["sub", "exp"],
                    "verify_aud": self._config.oidc_audience is not None,
                    "verify_iss": self._config.oidc_issuer is not None,
                },
            )
        except SigningKeysUnavailable as error:
            raise ServiceIdentityRefused(
                "the sign-in could not be checked: the identity provider's signing keys could not "
                "be read",
                status=503,
            ) from error
        except PrincipalResolutionError as error:
            raise ServiceIdentityRefused("the sign-in could not be verified", status=401) from error
        except jwt.PyJWTError as error:
            raise ServiceIdentityRefused("the sign-in could not be verified", status=401) from error
        if self._mapping.is_entra:
            return self._entra_client(claims)
        if "tid" in claims:
            # Keycloak never emits `tid`: an Entra token is no service identity here.
            raise ServiceIdentityRefused(NOT_A_SERVICE_IDENTITY, status=403)
        client = claims.get("azp")
        username = claims.get("preferred_username")
        if (
            not isinstance(client, str)
            or not client
            or username != f"{SERVICE_ACCOUNT_PREFIX}{client.lower()}"
        ):
            raise ServiceIdentityRefused(NOT_A_SERVICE_IDENTITY, status=403)
        if is_deployment_client(client):
            raise ServiceIdentityRefused(DEPLOYMENT_CLIENT_WORDS, status=403)
        return client

    def _entra_client(self, claims: dict[str, object]) -> str:
        if claims.get("tid") != self._mapping.tenant_id:
            raise ServiceIdentityRefused(NOT_A_SERVICE_IDENTITY, status=403)
        if "scp" in claims or claims.get("idtyp", "app") != "app":
            # A delegated token is a person's, whichever application asked for it.
            raise ServiceIdentityRefused(NOT_A_SERVICE_IDENTITY, status=403)
        # A claim of any other shape than a string is no client: refused, never an error.
        named = [claims[c] for c in ("azp", "appid") if c in claims]
        if not named or not all(isinstance(c, str) for c in named) or len(set(named)) != 1:
            raise ServiceIdentityRefused(NOT_A_SERVICE_IDENTITY, status=403)
        client = named[0]
        if not isinstance(client, str) or not is_object_id(client):
            raise ServiceIdentityRefused(NOT_A_SERVICE_IDENTITY, status=403)
        if client in (
            self._mapping.client_id,
            self._mapping.api_client_id,
            self._config.oidc_audience,
        ):
            # The Glass's own registration, or this API's: the deployment's, never an orchestrator.
            raise ServiceIdentityRefused(DEPLOYMENT_CLIENT_WORDS, status=403)
        roles = claims.get("roles")
        if isinstance(roles, list) and DASHBOARD_APP_ROLE in roles:
            # Amendment 10: a client granted the dashboards' role is a dashboard's, registered or
            # not.
            raise ServiceIdentityRefused(DASHBOARD_IS_NO_SERVICE_IDENTITY, status=403)
        return client
