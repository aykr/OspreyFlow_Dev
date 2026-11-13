"""A dashboard identity on Entra ID (`06_DECISIONS.md` ADR-148 Amendment 10).

One Entra app registration per dashboard identity, registered in Admin › Dashboards by its
application id with a clearance, a unit and handling codes. Its client-credentials (app-only)
token resolves to a narrow principal: the registration's id, its stored clearance, unit and codes,
the role `reports_viewer` and nothing else, admitted to the case list and the report feed alone
(`DASHBOARD_ROUTES`, `test_route_gate.py`). Every other app-only token is refused as before
(`test_auth_entra_claims.py::test_an_app_only_token_is_no_person`).

Rule 15: the tokens are shaped as Entra issues a client-credentials token for this API (v2.0:
`azp` the client, `idtyp: app`, `roles` the application permissions granted, no `scp`, no person's
claims), and the store stand-in refuses as the real one does (keyed by tenant **and** application
id).
"""

from __future__ import annotations

import asyncio
import time

import pytest
from services.api.auth import PrincipalResolutionError, PrincipalResolver

from principal_auth import (
    DASHBOARD_APP_ROLE,
    DASHBOARD_ROUTES,
    PrincipalLookupUnavailable,
    StoredDashboard,
)
from tests.conftest import sign_token
from tests.services.api.test_auth_entra_claims import (
    BY_EXTENSION,
    CLIENT_ID,
    GLASS,
    ISSUER,
    OTHER_TENANT,
    TENANT,
    FakePeople,
    _config,
    _entra_config,
    _key,
)

DASHBOARD = "dddddddd-eeee-4fff-8000-111111111111"  # a dashboard identity's app registration
UNREGISTERED = "eeeeeeee-ffff-4000-8111-222222222222"


def app_only_claims(client: str = DASHBOARD, **overrides: object) -> dict[str, object]:
    """An Entra ID v2.0 client-credentials token's claims for this API, as Entra shapes them."""
    now = int(time.time())
    claims: dict[str, object] = {
        "aud": CLIENT_ID, "iss": ISSUER, "iat": now, "nbf": now, "exp": now + 3600,
        "ver": "2.0", "tid": TENANT, "oid": "60000000-0000-4000-8000-000000000001",
        "sub": "60000000-0000-4000-8000-000000000001", "azp": client, "azpacr": "1",
        "idtyp": "app", "roles": [DASHBOARD_APP_ROLE],
    }  # fmt: skip
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


class FakeDashboards:
    """Stands in for the dashboard identities' store: keyed by tenant and application id, a failure
    raised, never answered as "not registered"."""

    def __init__(self) -> None:
        self.rows = {
            (TENANT, DASHBOARD): StoredDashboard(
                application_id=DASHBOARD, clearance="OFFICIAL-SENSITIVE", org_unit="unit-2",
                receivable_handling_codes=("R",),
            )  # fmt: skip
        }
        self.fail: Exception | None = None

    async def dashboard(self, tenant_id: str, application_id: str) -> StoredDashboard | None:
        if self.fail is not None:
            raise self.fail
        return self.rows.get((tenant_id, application_id))


def _resolver(jwks_url: str, dashboards: FakeDashboards | None) -> PrincipalResolver:
    return PrincipalResolver(
        _entra_config(jwks_url), claim_mapping=BY_EXTENSION, role_source=FakePeople(),
        dashboard_source=dashboards, role_lookup_timeout_seconds=0.2,
    )  # fmt: skip


def _resolve(resolver: PrincipalResolver, claims: dict[str, object], keypair):  # type: ignore[no-untyped-def]
    return asyncio.run(resolver.resolve_principal(sign_token(_key(keypair), claims)))


def test_a_registered_dashboard_s_token_is_its_narrow_principal(keypair, jwks_url) -> None:
    principal = _resolve(_resolver(jwks_url, FakeDashboards()), app_only_claims(), keypair)
    assert principal.id == DASHBOARD
    assert (principal.clearance, principal.org_unit) == ("OFFICIAL-SENSITIVE", "unit-2")
    assert principal.receivable_handling_codes == ["R"]
    assert principal.roles == ["reports_viewer"]
    assert set(principal.routes or ()) == DASHBOARD_ROUTES


@pytest.mark.parametrize(
    ("claims", "why"),
    [
        (app_only_claims(roles=None), "Dashboard.Read"),
        (app_only_claims(roles=["Something.Else"]), "Dashboard.Read"),
        (app_only_claims(UNREGISTERED), "registered"),
        (app_only_claims(tid=OTHER_TENANT), "tenant"),
        (app_only_claims(GLASS), "client"),
        (app_only_claims(CLIENT_ID), "client"),
        (app_only_claims("not-a-guid"), "client"),
        (app_only_claims(appid=UNREGISTERED), "client"),
    ],
    ids=["no-role", "another-role", "unregistered", "another-tenant", "the-glass",
         "this-api-itself", "not-an-application-id", "two-clients"],
)  # fmt: skip
def test_an_app_only_token_that_is_no_registered_dashboard_is_refused(
    claims: dict[str, object], why: str, keypair, jwks_url
) -> None:
    dashboards = FakeDashboards()
    for own in (GLASS, CLIENT_ID):  # even if registered
        dashboards.rows[(TENANT, own)] = StoredDashboard(own, "OFFICIAL", "unit-1", ())
    with pytest.raises(PrincipalResolutionError, match=why):
        _resolve(_resolver(jwks_url, dashboards), claims, keypair)


def test_the_api_s_own_application_is_refused_where_the_audience_is_its_uri(
    keypair, jwks_url
) -> None:
    """The audience may be the API's application id URI (`api://…`), not its id: then the only
    defence naming the API's own application is the mapping's `api_client_id`, held here alone
    (the lane review of 009a889: each own-client defence planted on its own)."""
    audience = "api://osprey-api"
    dashboards = FakeDashboards()
    dashboards.rows[(TENANT, CLIENT_ID)] = StoredDashboard(CLIENT_ID, "OFFICIAL", "unit-1", ())
    resolver = PrincipalResolver(
        _config(jwks_url, oidc_issuer=ISSUER, oidc_audience=audience),
        claim_mapping=BY_EXTENSION.model_copy(update={"api_client_id": CLIENT_ID}),
        role_source=FakePeople(), dashboard_source=dashboards, role_lookup_timeout_seconds=0.2,
    )  # fmt: skip
    with pytest.raises(PrincipalResolutionError, match="client"):
        _resolve(resolver, app_only_claims(CLIENT_ID, aud=audience), keypair)
    # The same token shape from a registered dashboard is its principal: the case asks the client.
    assert _resolve(resolver, app_only_claims(aud=audience), keypair).id == DASHBOARD


def test_without_the_dashboard_store_every_app_only_token_is_refused_as_before(
    keypair, jwks_url
) -> None:
    with pytest.raises(PrincipalResolutionError, match="app-only"):
        _resolve(_resolver(jwks_url, None), app_only_claims(), keypair)


def test_a_store_that_cannot_answer_is_a_503_never_a_refusal_or_a_principal(
    keypair, jwks_url
) -> None:
    dashboards = FakeDashboards()
    dashboards.fail = OSError("the store is down")
    with pytest.raises(PrincipalLookupUnavailable):
        _resolve(_resolver(jwks_url, dashboards), app_only_claims(), keypair)


def test_a_person_s_delegated_token_is_never_read_as_a_dashboard(keypair, jwks_url) -> None:
    """A person signed in through the Glass whose oid happened to equal a dashboard's application
    id is still a person: only an app-only token is looked up as a dashboard."""
    from tests.services.api.test_auth_entra_claims import _GOOD, entra_claims

    principal = _resolve(
        _resolver(jwks_url, FakeDashboards()), entra_claims(**_GOOD, oid=DASHBOARD), keypair
    )
    assert principal.routes is None and principal.roles != ["reports_viewer"]


def test_a_dashboard_store_is_refused_beside_a_keycloak_mapping(jwks_url) -> None:
    """Read only for an Entra mapping, so given beside Keycloak's it would be ignored in silence:
    refused at the start instead, as the people store is (the lane review of 009a889)."""
    from principal_auth import ClaimMapping

    with pytest.raises(ValueError, match="dashboard"):
        PrincipalResolver(_entra_config(jwks_url), claim_mapping=ClaimMapping(),
                          dashboard_source=FakeDashboards())  # fmt: skip


def test_a_v1_token_naming_its_client_in_appid_alone_is_the_dashboard(keypair, jwks_url) -> None:
    """Entra's v1.0 tokens name the client in `appid`, with no `azp`."""
    claims = app_only_claims(azp=None, azpacr=None, appid=DASHBOARD, ver="1.0")
    assert _resolve(_resolver(jwks_url, FakeDashboards()), claims, keypair).id == DASHBOARD


@pytest.mark.parametrize("claim", ["azp", "appid"])
def test_a_client_claim_that_is_a_list_is_refused_not_an_error(claim, keypair, jwks_url) -> None:
    """A token is the caller's: a claim of the wrong shape is a refusal (401), never a 500."""
    claims = app_only_claims(**{claim: [DASHBOARD]})
    with pytest.raises(PrincipalResolutionError, match="client"):
        _resolve(_resolver(jwks_url, FakeDashboards()), claims, keypair)


def test_a_store_too_slow_to_answer_is_a_503_within_the_bound(keypair, jwks_url) -> None:
    """The registration's read is bounded (0.2 s here): past it, a 503, never a wait as long as
    the store's (the lane review of 009a889)."""

    class _Slow(FakeDashboards):
        async def dashboard(self, tenant_id: str, application_id: str) -> StoredDashboard | None:
            await asyncio.sleep(30)
            return None

    started = time.monotonic()
    with pytest.raises(PrincipalLookupUnavailable):
        _resolve(_resolver(jwks_url, _Slow()), app_only_claims(), keypair)
    assert time.monotonic() - started < 10


def test_an_audience_that_is_a_list_is_read_as_its_members(keypair, jwks_url) -> None:
    """PyJWT admits an `aud` list holding the configured audience: its members are the API's own, so
    a token whose client is one of them is refused, never a 500 (the lane review of 2b42dea)."""
    dashboards = FakeDashboards()
    dashboards.rows[(TENANT, CLIENT_ID)] = StoredDashboard(CLIENT_ID, "OFFICIAL", "unit-1", ())
    with pytest.raises(PrincipalResolutionError, match="client"):
        _resolve(_resolver(jwks_url, dashboards), app_only_claims(CLIENT_ID, aud=[CLIENT_ID]), keypair)
    assert _resolve(_resolver(jwks_url, dashboards), app_only_claims(aud=[CLIENT_ID]), keypair).id == DASHBOARD
