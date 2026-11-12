"""A service identity's sign-in on Entra ID (`06_DECISIONS.md` ADR-141 decision 10; ADR-148
Amendment 8; CARRIES, P10 round 2).

On Keycloak the run API knows an orchestrator's client by `preferred_username`
`service-account-<azp>`; Entra issues no such claim, so on Entra no orchestrator could call the run
API, and nothing pinned the tenant. On an Entra mapping a service identity's token is **an app-only
token of the pinned tenant**: issued by the configured issuer for this API's audience, `tid` the
tenant, no delegated `scp` (a person's token is 403), `idtyp` `app` where present, and its client
(`azp` in v2.0, `appid` in v1.0; both, if both are present, the same) an Entra application id that
is **neither the Glass's nor this API's own**. A token carrying `tid` under Keycloak's handling is
refused (403), as `principal_auth` refuses one.

**Shaped from Microsoft's documentation, not measured** (rule 15): a client-credentials token's
claims as documented for v1.0 and v2.0. The test against the client's development tenant is
Amendment 6's list, carried. Synthetic values only (rule 9).
"""

from __future__ import annotations

import time

import pytest
from services.api.service_identity import ServiceIdentityRefused, ServiceIdentityVerifier

from principal_auth import ClaimMapping, OidcResolverSettings, ValueSource
from tests.conftest import default_claims, sign_token

TENANT = "00000000-1111-4222-8333-444444444444"
OTHER_TENANT = "99999999-8888-4777-8666-555555555555"
API = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
GLASS = "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"
AIRFLOW = "dddddddd-eeee-4fff-8000-111111111111"
SP_OID = "60000000-0000-4000-8000-000000000001"
ISSUER = f"https://login.microsoftonline.com/{TENANT}/v2.0"

MAPPING = ClaimMapping(
    tenant_id=TENANT, client_id=GLASS, api_client_id=API, clearance=ValueSource(claim="c")
)

_ABSENT = object()


def _settings(jwks_url: str, **overrides: object) -> OidcResolverSettings:
    fields: dict[str, object] = {
        "oidc_jwks_url": jwks_url,
        "oidc_issuer": ISSUER,
        "oidc_audience": API,
    }
    fields.update(overrides)
    return OidcResolverSettings(**fields)  # type: ignore[arg-type]


def _verifier(jwks_url: str) -> ServiceIdentityVerifier:
    return ServiceIdentityVerifier(_settings(jwks_url), claim_mapping=MAPPING)


def _app_token(keypair, **overrides: object) -> str:  # type: ignore[no-untyped-def]
    """A v2.0 client-credentials token for this API, as Entra documents one."""
    now = int(time.time())
    claims: dict[str, object] = {
        "aud": API, "iss": ISSUER, "iat": now, "nbf": now, "exp": now + 3600, "ver": "2.0",
        "tid": TENANT, "oid": SP_OID, "sub": SP_OID, "azp": AIRFLOW, "azpacr": "1",
        "idtyp": "app", "roles": ["Runs.Trigger"],
    }  # fmt: skip
    claims.update(overrides)
    return sign_token(keypair[0], {k: v for k, v in claims.items() if v is not _ABSENT})


def test_an_entra_app_only_token_names_its_client(jwks_url, keypair) -> None:
    assert _verifier(jwks_url).client_of(_app_token(keypair)) == AIRFLOW


def test_a_v1_app_only_token_names_its_client_by_appid(jwks_url, keypair) -> None:
    token = _app_token(
        keypair, azp=_ABSENT, azpacr=_ABSENT, appid=AIRFLOW, ver="1.0", idtyp=_ABSENT
    )
    assert _verifier(jwks_url).client_of(token) == AIRFLOW


@pytest.mark.parametrize(
    ("overrides", "status"),
    [
        ({"tid": OTHER_TENANT}, 403),
        ({"tid": _ABSENT}, 403),
        ({"scp": "access_as_user"}, 403),
        ({"idtyp": "user"}, 403),
        ({"azp": GLASS}, 403),
        ({"azp": API}, 403),
        ({"azp": _ABSENT}, 403),
        ({"azp": "airflow-prod"}, 403),
        ({"appid": GLASS}, 403),
        ({"iss": f"https://login.microsoftonline.com/{OTHER_TENANT}/v2.0"}, 401),
        ({"aud": GLASS}, 401),
    ],
    ids=[
        "other-tenant",
        "no-tid",
        "a-persons-delegated-token",
        "idtyp-user",
        "the-glass",
        "this-api-itself",
        "no-client",
        "client-not-an-app-id",
        "azp-and-appid-disagree",
        "other-issuer",
        "other-audience",
    ],
)
def test_what_is_no_service_identity_on_entra_is_refused(
    jwks_url, keypair, overrides, status
) -> None:
    with pytest.raises(ServiceIdentityRefused) as refused:
        _verifier(jwks_url).client_of(_app_token(keypair, **overrides))
    assert refused.value.status == status


def test_keycloaks_service_account_shape_is_not_a_service_identity_on_entra(
    jwks_url, keypair
) -> None:
    """The Keycloak shape, signed by a trusted key: no `tid`, so refused, never read by name."""
    claims = {
        "aud": API, "iss": ISSUER, "sub": "uuid-1", "azp": "airflow-prod",
        "preferred_username": "service-account-airflow-prod", "exp": default_claims()["exp"],
    }  # fmt: skip
    with pytest.raises(ServiceIdentityRefused):
        _verifier(jwks_url).client_of(sign_token(keypair[0], claims))


@pytest.mark.parametrize("tenant", [TENANT, OTHER_TENANT], ids=["our-tenant", "other-tenant"])
def test_an_entra_token_under_keycloaks_handling_is_refused(jwks_url, keypair, tenant) -> None:
    """Keycloak never emits `tid`: an Entra token here is no service identity, whatever its
    `preferred_username` says."""
    claims = {
        "sub": "uuid-1", "azp": "airflow-prod", "tid": tenant,
        "preferred_username": "service-account-airflow-prod", "exp": default_claims()["exp"],
    }  # fmt: skip
    verifier = ServiceIdentityVerifier(OidcResolverSettings(oidc_jwks_url=jwks_url))
    with pytest.raises(ServiceIdentityRefused) as refused:
        verifier.client_of(sign_token(keypair[0], claims))
    assert refused.value.status == 403


@pytest.mark.parametrize("missing", ["oidc_issuer", "oidc_audience"])
def test_an_entra_verifier_without_issuer_and_audience_is_refused_at_construction(
    jwks_url, missing
) -> None:
    with pytest.raises(ValueError, match="OIDC_"):
        ServiceIdentityVerifier(_settings(jwks_url, **{missing: None}), claim_mapping=MAPPING)


def test_on_v1_tokens_this_apis_own_registration_is_no_orchestrator(jwks_url, keypair) -> None:
    """v1.0 tokens name the API's `api://` URI as their audience, so the API's own application id
    is no longer the audience: it is refused by the mapping's `api_client_id` (the lane-reviewer's
    finding 3; red with only the audience compared)."""
    v1 = ServiceIdentityVerifier(
        _settings(
            jwks_url, oidc_issuer=f"https://sts.windows.net/{TENANT}/", oidc_audience=f"api://{API}"
        ),
        claim_mapping=MAPPING,
    )
    token = _app_token(
        keypair, aud=f"api://{API}", iss=f"https://sts.windows.net/{TENANT}/", ver="1.0",
        azp=_ABSENT, azpacr=_ABSENT, idtyp=_ABSENT, appid=API,
    )  # fmt: skip
    with pytest.raises(ServiceIdentityRefused) as refused:
        v1.client_of(token)
    assert refused.value.status == 403
    other = _app_token(
        keypair, aud=f"api://{API}", iss=f"https://sts.windows.net/{TENANT}/", ver="1.0",
        azp=_ABSENT, azpacr=_ABSENT, idtyp=_ABSENT, appid=AIRFLOW,
    )  # fmt: skip
    assert v1.client_of(other) == AIRFLOW


def test_a_service_identitys_token_without_an_expiry_is_refused(jwks_url, keypair) -> None:
    """The orchestrator's note: `exp` required on the service identity's path too."""
    with pytest.raises(ServiceIdentityRefused) as refused:
        _verifier(jwks_url).client_of(_app_token(keypair, exp=_ABSENT))
    assert refused.value.status == 401
