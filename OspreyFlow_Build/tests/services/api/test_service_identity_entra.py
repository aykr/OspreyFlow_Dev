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


# --- the orchestrator's second review of P10 part 2, item 8: the run API's keys ---


def test_the_identity_provider_unreachable_is_a_503_on_the_run_api(keypair) -> None:
    """Its keys unreadable is said so (503), never "could not be verified" (401)."""
    with pytest.raises(ServiceIdentityRefused) as refused:
        _verifier("http://127.0.0.1:9/jwks.json").client_of(_app_token(keypair))
    assert refused.value.status == 503
    assert "signing keys could not be read" in str(refused.value)


def test_an_entra_service_identity_takes_rs256_alone_whatever_oidc_algorithms_says(
    jwks_dir,
) -> None:
    """With ES256 allowed by OIDC_ALGORITHMS and an EC key published, an ES256 app-only token is
    refused on the run API too."""
    import json

    import jwt as pyjwt
    from cryptography.hazmat.primitives.asymmetric import ec
    from jwt.algorithms import ECAlgorithm

    directory, url = jwks_dir
    ec_key = ec.generate_private_key(ec.SECP256R1())
    jwk = ECAlgorithm.to_jwk(ec_key.public_key(), as_dict=True)
    jwk.update(kid="ec", use="sig")
    (directory / "jwks.json").write_text(json.dumps({"keys": [jwk]}))
    now = int(time.time())
    claims = {
        "aud": API, "iss": ISSUER, "iat": now, "nbf": now, "exp": now + 3600, "ver": "2.0",
        "tid": TENANT, "oid": SP_OID, "sub": SP_OID, "azp": AIRFLOW, "idtyp": "app",
    }  # fmt: skip
    token = pyjwt.encode(claims, ec_key, algorithm="ES256", headers={"kid": "ec"})
    verifier = ServiceIdentityVerifier(
        _settings(url, oidc_algorithms=("RS256", "ES256")), claim_mapping=MAPPING
    )
    with pytest.raises(ServiceIdentityRefused) as refused:
        verifier.client_of(token)
    assert refused.value.status == 401


@pytest.mark.parametrize(("ago", "admitted"), [(30, True), (120, False)], ids=["30s", "120s"])
def test_a_service_identitys_token_a_little_past_its_expiry_is_given_sixty_seconds(
    jwks_url, keypair, ago, admitted
) -> None:
    now = int(time.time())
    token = _app_token(keypair, iat=now - 3600, nbf=now - 3600, exp=now - ago)
    if admitted:
        assert _verifier(jwks_url).client_of(token) == AIRFLOW
    else:
        with pytest.raises(ServiceIdentityRefused) as refused:
            _verifier(jwks_url).client_of(token)
        assert refused.value.status == 401


def test_the_run_api_shares_the_person_paths_keys(jwks_url, keypair) -> None:
    """One set of keys for both paths when the Conduit passes it: what one fetched, the other uses
    (one cache and one fetch limit for one OIDC_JWKS_URL)."""
    from principal_auth import SigningKeys

    keys = SigningKeys(jwks_url, 3600.0)
    verifier = ServiceIdentityVerifier(
        _settings(jwks_url), claim_mapping=MAPPING, signing_keys=keys
    )
    assert verifier.client_of(_app_token(keypair)) == AIRFLOW
    assert verifier.client_of(_app_token(keypair)) == AIRFLOW
    assert keys.fetches == 1


async def test_the_run_apis_sign_in_reads_its_keys_in_their_own_threads_never_the_loop() -> None:
    """The third review's should-fix 2: `get_service_identity` is async and asks the verifier in the
    keys' own threads, bounded in total, never on the event loop nor in anyio's shared pool: the
    call is seen in a `signing-keys` thread, and the loop's largest gap between ticks stays under
    0.2 s while it takes a second."""
    import asyncio
    import threading
    from types import SimpleNamespace

    from fastapi.security import HTTPAuthorizationCredentials
    from services.api.app import get_service_identity

    seen: list[str] = []

    class _Slow:
        def client_of(self, token: str) -> str:
            seen.append(threading.current_thread().name)
            time.sleep(1.0)
            return AIRFLOW

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(service_identities=_Slow())))
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="a-token")
    gaps: list[float] = []

    async def ticks() -> None:
        last = time.monotonic()
        for _ in range(12):
            await asyncio.sleep(0.05)
            now = time.monotonic()
            gaps.append(now - last)
            last = now

    client, _ = await asyncio.gather(get_service_identity(request, credentials), ticks())  # type: ignore[arg-type]
    assert client == AIRFLOW
    assert seen and seen[0].startswith("signing-keys"), seen
    assert max(gaps) < 0.2, max(gaps)


# --- ADR-148 Amendment 10: a dashboard identity never submits runs -----------------------------------


def test_a_token_carrying_the_dashboard_role_is_no_service_identity(jwks_url, keypair) -> None:
    """Its client holds this API's `Dashboard.Read`: a dashboard's, registered here or not."""
    from principal_auth import DASHBOARD_APP_ROLE

    token = _app_token(keypair, roles=["Runs.Trigger", DASHBOARD_APP_ROLE])
    with pytest.raises(ServiceIdentityRefused, match="dashboard") as refused:
        _verifier(jwks_url).client_of(token)
    assert refused.value.status == 403


class _Dashboards:
    """The deployment's store as the run API asks it: keyed by tenant and application id."""

    tenant_id = TENANT

    async def dashboard(self, tenant_id: str, application_id: str):  # type: ignore[no-untyped-def]
        from principal_auth import StoredDashboard

        if (tenant_id, application_id) == (TENANT, AIRFLOW):
            return StoredDashboard(AIRFLOW, "OFFICIAL", "unit-1", ("P",))
        return None


@pytest.mark.parametrize("registered", [True, False], ids=["registered-dashboard", "not-a-dashboard"])
def test_the_run_api_refuses_a_client_registered_as_a_dashboard_identity(
    jwks_url, keypair, registered
) -> None:
    """Through the real `get_service_identity`: a client Admin › Dashboards registered is refused
    before anything is read, though its token holds no dashboard role; any other gets past this
    door (to whatever the route's own dependencies then answer, here without the app's start)."""
    from fastapi.testclient import TestClient
    from services.api.app import app

    before = {k: getattr(app.state, k, None) for k in ("service_identities", "people_store")}
    app.state.service_identities = _verifier(jwks_url)
    app.state.people_store = _Dashboards() if registered else None
    try:
        answered = TestClient(app, raise_server_exceptions=False).post(
            "/v1/runs", json={}, headers={"Authorization": f"Bearer {_app_token(keypair)}"}
        )
    finally:
        for key, value in before.items():
            setattr(app.state, key, value)
    refused = answered.status_code == 403 and "dashboard identity" in answered.text
    assert refused is registered, (answered.status_code, answered.text)


class _AnswersNone(_Dashboards):
    async def dashboard(self, tenant_id: str, application_id: str):  # type: ignore[no-untyped-def]
        return None


class _Slow(_Dashboards):
    async def dashboard(self, tenant_id: str, application_id: str):  # type: ignore[no-untyped-def]
        import asyncio

        await asyncio.sleep(30)
        return None


@pytest.mark.parametrize(
    ("store", "answer"),
    [(_AnswersNone, "past"), (_Slow, 503)],
    ids=["store-answers-none", "store-too-slow"],
)
def test_the_run_api_door_with_a_store_answering_none_or_too_slowly(
    jwks_url, keypair, store, answer, monkeypatch
) -> None:
    """A store that holds no such registration lets the client past this door; one that does not
    answer within the role lookup's bound is a 503 in words, never a wait as long as the store's
    (ADR-148 Amendment 10, the lane review of 009a889)."""
    import time

    from fastapi.testclient import TestClient
    from services.api import app as app_module

    monkeypatch.setattr(app_module, "ROLE_LOOKUP_TIMEOUT_SECONDS", 0.2)
    app = app_module.app
    before = {k: getattr(app.state, k, None) for k in ("service_identities", "people_store")}
    app.state.service_identities = _verifier(jwks_url)
    app.state.people_store = store()
    started = time.monotonic()
    try:
        answered = TestClient(app, raise_server_exceptions=False).post(
            "/v1/runs", json={}, headers={"Authorization": f"Bearer {_app_token(keypair)}"}
        )
    finally:
        for key, value in before.items():
            setattr(app.state, key, value)
    assert time.monotonic() - started < 10
    if answer == 503:
        assert answered.status_code == 503 and "could not be read" in answered.text
    else:
        assert answered.status_code not in (403, 503), (answered.status_code, answered.text)


@pytest.mark.parametrize("claim", ["azp", "appid"])
def test_a_client_claim_that_is_a_list_is_refused_on_the_run_api_not_an_error(
    claim, jwks_url, keypair
) -> None:
    """A token is the caller's: a client claim of the wrong shape is refused, never a 500 (the lane
    review of 2b42dea; the resolver's own case is test_auth_entra_dashboards.py's)."""
    token = _app_token(keypair, **{claim: [AIRFLOW]})
    with pytest.raises(ServiceIdentityRefused):
        _verifier(jwks_url).client_of(token)
