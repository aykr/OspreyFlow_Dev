"""The Conduit refuses to exchange for a disabled principal, because the realm will not.

`06_DECISIONS.md` ADR-043's amendment of 24 September 2026, and the owner's decision of the same
date. **Measured, not assumed:** against a real Keycloak 26.0 with token exchange enabled, a client
holding the impersonation grant is issued a valid access token for a *disabled* user. Keycloak
scopes impersonation by requesting client, not by target subject, and a bounded attempt to
configure per-target refusal through fine-grained admin permissions failed on 26.0. So the refusal
has to happen in the Conduit, before the exchange.

**This is a live-service test against a real IdP on purpose.** The whole finding is about what
Keycloak actually does rather than what it is documented to do — the first version of this check was
specified as "the realm refuses an out-of-scope subject", which measurement showed the realm never
does. A mocked IdP would have let that specification survive.

Set-up (`OSPREY_TEST_KEYCLOAK_URL` must point at a realm built like `/tmp/kcsetup.py` does): a
confidential client holding **both** the impersonation and view-users grants, an enabled
`preflight-probe` subject, a disabled `revoked-subject`, and an unprivileged client holding
neither.
"""

from __future__ import annotations

import os

import pytest
from services.api.auth import (
    PrincipalExchangeRefused,
    PrincipalExchangeUnavailable,
    PrincipalResolver,
    PrincipalRevoked,
)
from services.api.config import ApiConfig, PostgresConfig, ValkeyConfig

pytestmark = pytest.mark.asyncio

KC = os.environ.get("OSPREY_TEST_KEYCLOAK_URL")
REALM = "osprey"

requires_keycloak = pytest.mark.skipif(
    not KC, reason="OSPREY_TEST_KEYCLOAK_URL is not set — this test needs a real IdP by design"
)


def _config(*, client_id: str, secret: str, with_precheck: bool) -> ApiConfig:
    """Only what the resolver reads. `with_precheck=False` is the rule-15 lever, and it is the real
    shape of the thing rather than a patched-out method: it is exactly a deployment that has not
    set `OIDC_ADMIN_USERS_URL`."""
    return ApiConfig(
        valkey=ValkeyConfig(host="localhost", port=6379, db=0),
        postgres=PostgresConfig(host="localhost", port=5432, user="x", password="x", database="x"),
        oidc_jwks_url=f"{KC}/realms/{REALM}/protocol/openid-connect/certs",
        oidc_audience=None,
        oidc_issuer=None,
        oidc_algorithms=("RS256",),
        oidc_jwks_ttl_seconds=300.0,
        oidc_token_exchange_url=f"{KC}/realms/{REALM}/protocol/openid-connect/token",
        oidc_token_exchange_client_id=client_id,
        oidc_token_exchange_client_secret=secret,
        oidc_admin_users_url=f"{KC}/admin/realms/{REALM}/users" if with_precheck else None,
        supersede_job_degree_threshold=500,
        osprey_config_path="osprey.yaml",
        analytics_db_path=":memory:",
        hotlist_alert_policy="strict",
        export_manifest_policy="disclose",
    )


@requires_keycloak
async def test_an_enabled_subject_is_exchanged_and_carries_that_subjects_own_claims() -> None:
    """Verify assertion 1. The success side has to work, or the other two prove nothing: a
    resolver that refused everything would satisfy both refusal assertions."""
    resolver = PrincipalResolver(
        _config(client_id="osprey-conduit", secret="probe-secret", with_precheck=True)
    )
    try:
        principal = await resolver.resolve_for_owner_detailed("preflight-probe")
    finally:
        await resolver.aclose()

    assert principal is not None
    assert principal.id, "the exchanged principal must carry the target subject's own identity"


@requires_keycloak
async def test_an_unprivileged_client_is_refused_by_keycloak() -> None:
    """Verify assertion 2 — the one refusal the realm *does* enforce, measured. It refuses by
    requesting client, which is the containment that actually exists."""
    resolver = PrincipalResolver(
        _config(client_id="osprey-unprivileged", secret="other-secret", with_precheck=False)
    )
    try:
        with pytest.raises(PrincipalExchangeRefused) as raised:
            await resolver.resolve_for_owner_detailed("preflight-probe")
    finally:
        await resolver.aclose()

    assert "refused" in str(raised.value).lower()


@requires_keycloak
async def test_a_disabled_subject_is_refused_by_the_conduits_own_precheck() -> None:
    """Verify assertion 3, and the reason this amendment exists. `PrincipalRevoked` rather than the
    generic refusal, so ADR-044's revoked-principal reason is available to whatever marks the
    watch stopped."""
    resolver = PrincipalResolver(
        _config(client_id="osprey-conduit", secret="probe-secret", with_precheck=True)
    )
    try:
        with pytest.raises(PrincipalRevoked) as raised:
            await resolver.resolve_for_owner_detailed("revoked-subject")
    finally:
        await resolver.aclose()

    assert "disabled at the identity provider" in str(raised.value)


@requires_keycloak
async def test_without_the_precheck_the_realm_issues_a_token_for_the_disabled_subject() -> None:
    """**The rule-15 demonstration, and the finding itself.** Remove the pre-check — by leaving
    `OIDC_ADMIN_USERS_URL` unset, which is the real shape of a deployment that has not configured
    it — and the same disabled subject is exchanged successfully against the same real Keycloak.

    This is what makes the case above non-vacuous: without it, a `PrincipalRevoked` could be coming
    from anywhere, and the claim that "the realm will not refuse this" would be an assertion in a
    docstring rather than a measurement.
    """
    resolver = PrincipalResolver(
        _config(client_id="osprey-conduit", secret="probe-secret", with_precheck=False)
    )
    try:
        principal = await resolver.resolve_for_owner_detailed("revoked-subject")
    finally:
        await resolver.aclose()

    assert principal is not None, (
        "Keycloak was expected to issue a token for a disabled subject — if this now fails, the "
        "realm has gained per-target refusal and ADR-043's amendment should be revisited"
    )


@requires_keycloak
async def test_an_unreachable_idp_is_unavailable_not_revoked() -> None:
    """ADR-044's unreachable path, unchanged. A transient outage must never mark a live analyst's
    watches as revoked — the two are different facts and the pre-check must not collapse them."""
    config = _config(client_id="osprey-conduit", secret="probe-secret", with_precheck=True)
    resolver = PrincipalResolver(
        __import__("dataclasses").replace(
            config, oidc_admin_users_url="http://127.0.0.1:9/admin/realms/osprey/users"
        )
    )
    try:
        with pytest.raises(PrincipalExchangeUnavailable):
            await resolver.resolve_for_owner_detailed("preflight-probe")
    finally:
        await resolver.aclose()
