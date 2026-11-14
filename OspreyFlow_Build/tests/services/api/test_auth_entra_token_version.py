"""ADR-148 Amendment 18: an Entra access token of the other version than the deployment expects
(`cloud_platform.claims.token_version`) is refused in words naming the API registration's
`requestedAccessTokenVersion` and the setting, not as a bare issuer or audience mismatch.

The tokens are shaped as Entra issues each version, and as R1's Entra stand-in signs them in its v1.0
mode (`process/lanes/platform-b/v052-tokver/standin_v1.diff`, platform's file): a v1.0 token's issuer is
`https://sts.windows.net/<tenant>/`, its audience the API's application id URI, `ver` "1.0", and `appid` in
place of `azp`. Only a token the tenant signed reaches the version words: one signed by another key, or of
another tenant, or not Entra's at all, keeps the plain refusal, and the token is never admitted.
"""

from __future__ import annotations

import asyncio
import logging
import time

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from services.api.auth import PrincipalResolutionError, PrincipalResolver

from principal_auth import TokenVersionMismatch, entra_issuers
from tests.conftest import sign_token
from tests.services.api.test_auth import _config
from tests.services.api.test_auth_entra_claims import (
    _GOOD,
    BY_EXTENSION,
    CLIENT_ID,
    GLASS,
    OID,
    OTHER_TENANT,
    TENANT,
    FakePeople,
    entra_claims,
)

V1, V2 = entra_issuers(TENANT)["1.0"], entra_issuers(TENANT)["2.0"]
ID_URI = f"api://{CLIENT_ID}"


def _v1_claims(**overrides: object) -> dict[str, object]:
    """An Entra ID v1.0 access token's claims for a person, as Entra shapes them."""
    now = int(time.time())
    base: dict[str, object] = {
        "aud": ID_URI, "iss": V1, "iat": now, "nbf": now, "exp": now + 3600, "ver": "1.0",
        "tid": TENANT, "oid": OID, "appid": GLASS, "sub": "pairwise-subject-v1",
        "upn": "synthetic.analyst@example.test", "scp": "access_as_user", **_GOOD,
    }  # fmt: skip
    base.update(overrides)
    return base


def _resolve(jwks_url: str, token: str, *, expects: str = "2.0") -> object:
    issuer, audience = (V2, CLIENT_ID) if expects == "2.0" else (V1, ID_URI)
    resolver = PrincipalResolver(_config(jwks_url, oidc_issuer=issuer, oidc_audience=audience),
                                 claim_mapping=BY_EXTENSION, role_source=FakePeople(), role_lookup_timeout_seconds=0.2)  # fmt: skip
    return asyncio.run(resolver.resolve_principal(token))


def test_a_v1_token_where_v2_is_expected_is_refused_in_words(keypair, jwks_url) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(TokenVersionMismatch) as refused:
        _resolve(jwks_url, sign_token(keypair[0], _v1_claims()))
    said = str(refused.value)
    assert "issues v1.0 access tokens" in said and "expects v2.0" in said
    assert "requestedAccessTokenVersion to 2" in said and 'token_version: "2.0"' in said and 'token_version to "1.0"' in said


def test_a_v2_token_where_v1_is_expected_is_refused_in_words(keypair, jwks_url) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(TokenVersionMismatch, match=r"issues v2\.0 access tokens.*expects v1\.0.*requestedAccessTokenVersion to 1"):
        _resolve(jwks_url, sign_token(keypair[0], entra_claims(**_GOOD)), expects="1.0")


def test_each_version_s_own_token_still_resolves(keypair, jwks_url) -> None:  # type: ignore[no-untyped-def]
    assert _resolve(jwks_url, sign_token(keypair[0], entra_claims(**_GOOD))).id == OID  # type: ignore[attr-defined]
    assert _resolve(jwks_url, sign_token(keypair[0], _v1_claims()), expects="1.0").id == OID  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "token_of",
    ["another-key", "another-tenant", "not-entra", "ver-disagrees-with-issuer", "expired"],
)
def test_a_token_the_tenant_did_not_sign_as_that_version_never_reaches_the_words(keypair, jwks_url, token_of: str) -> None:  # type: ignore[no-untyped-def]
    """The plain refusal, never the version words, and never admitted."""
    if token_of == "another-key":
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = sign_token(other, _v1_claims())  # the tenant's key id, another key's signature
    else:
        claims = {
            "another-tenant": _v1_claims(iss=entra_issuers(OTHER_TENANT)["1.0"], tid=OTHER_TENANT),
            "not-entra": _v1_claims(iss="https://keycloak.example.test/realms/osprey"),
            "ver-disagrees-with-issuer": _v1_claims(ver="2.0"),
            "expired": _v1_claims(exp=int(time.time()) - 3600, iat=int(time.time()) - 7200, nbf=int(time.time()) - 7200),
        }[token_of]
        token = sign_token(keypair[0], claims)
    with pytest.raises(PrincipalResolutionError) as refused:
        _resolve(jwks_url, token)
    assert not isinstance(refused.value, TokenVersionMismatch), refused.value
    assert "requestedAccessTokenVersion" not in str(refused.value)


def test_the_mismatch_is_logged_once_for_install_step_6(keypair, jwks_url, caplog) -> None:  # type: ignore[no-untyped-def]
    resolver = PrincipalResolver(_config(jwks_url, oidc_issuer=V2, oidc_audience=CLIENT_ID),
                                 claim_mapping=BY_EXTENSION, role_source=FakePeople(), role_lookup_timeout_seconds=0.2)  # fmt: skip
    token = sign_token(keypair[0], _v1_claims())
    with caplog.at_level(logging.WARNING, logger="principal_auth"):
        for _ in range(3):
            with pytest.raises(TokenVersionMismatch):
                asyncio.run(resolver.resolve_principal(token))
    said = [r.getMessage() for r in caplog.records if r.getMessage().startswith("token version: ")]
    assert len(said) == 1 and "requestedAccessTokenVersion to 2" in said[0]
