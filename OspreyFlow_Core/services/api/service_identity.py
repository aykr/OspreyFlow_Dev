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

from principal_auth import OidcSettings

SERVICE_ACCOUNT_PREFIX = "service-account-"


class ServiceIdentityRefused(Exception):
    """A token that is not a service identity's, said in words that name no claim's value.
    `status`: 401 for a sign-in that could not be verified, 403 for a verified one that is not a
    service identity's (a person's)."""

    def __init__(self, words: str, *, status: int) -> None:
        super().__init__(words)
        self.status = status


class ServiceIdentityVerifier:
    def __init__(self, config: OidcSettings) -> None:
        self._config = config
        self._jwk_client = jwt.PyJWKClient(
            config.oidc_jwks_url, cache_keys=True, lifespan=int(config.oidc_jwks_ttl_seconds)
        )

    def client_of(self, token: str) -> str:
        """The client a service identity's token names; `ServiceIdentityRefused` otherwise."""
        try:
            key = self._jwk_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=list(self._config.oidc_algorithms),
                audience=self._config.oidc_audience,
                issuer=self._config.oidc_issuer,
                options={
                    # `azp` is judged below: a person's verified token without one is 403, not 401.
                    "require": ["sub"],
                    "verify_aud": self._config.oidc_audience is not None,
                    "verify_iss": self._config.oidc_issuer is not None,
                },
            )
        except jwt.PyJWTError as error:
            raise ServiceIdentityRefused("the sign-in could not be verified", status=401) from error
        client = claims.get("azp")
        username = claims.get("preferred_username")
        if (
            not isinstance(client, str)
            or not client
            or username != f"{SERVICE_ACCOUNT_PREFIX}{client.lower()}"
        ):
            raise ServiceIdentityRefused(
                "the sign-in is not a service identity's: sign in with the client-credentials "
                "grant of the client the pipeline is owned externally by",
                status=403,
            )
        return client
