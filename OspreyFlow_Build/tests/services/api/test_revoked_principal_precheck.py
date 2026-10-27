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

**Set-up, round 13cc: `make idp-test`.** Until then these five tests had **never run, in any
tier** — nothing in the repository set `OSPREY_TEST_KEYCLOAK_URL`, and the realm they needed lived
in a `/tmp/kcsetup.py` that was never in the tree. Owner ruling R8 ordered them made to run.

The realm is no longer a scratch script: it is **this repository's own deployment realm**,
rendered by `harness/realm.py` and configured by `harness/keycloak_admin.py` — the same two
modules a real `harness.apply` uses. That is deliberate and is the whole point of rule 15's second
worked example: a fixture IdP built to suit the test would once again be more permissive than the
real thing. Every name below is imported from that generator rather than restated here, so a realm
change cannot leave these tests asserting against a realm nobody deploys.

What the rendered realm provides: `osprey-conduit`, a confidential client whose service account
holds **both** the impersonation and view-users grants (applied after import, since a realm import
cannot express a `realm-management` role mapping); `osprey-unprivileged`, holding neither; an
enabled `osprey-verify-probe`; and a **disabled** `osprey-verify-revoked`.
"""

from __future__ import annotations

import os

import pytest
from harness.realm import (
    CONDUIT_CLIENT_ID,
    REVOKED_SUBJECT,
    UNPRIVILEGED_CLIENT_ID,
    VERIFY_SUBJECT,
)
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

#: **Imported, never restated.** The previous version hardcoded `preflight-probe`,
#: `revoked-subject` and `other-secret` — names from a scratch script that was never in the tree
#: and that no deployment has ever created. A test asserting against subjects the product does not
#: provision is the fixture-more-convenient-than-reality failure in `CLAUDE.md` rule 15.
#:
#: Both clients carry the *same* secret: `grant_service_account_roles` sets one apply-time value on
#: both, so the unprivileged client is unprivileged by its **grants**, not by its credentials —
#: which is the distinction assertion 2 exists to prove.
PROBE_SECRET = os.environ.get("OSPREY_TEST_KEYCLOAK_SECRET", "probe-secret")

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
        _config(client_id=CONDUIT_CLIENT_ID, secret=PROBE_SECRET, with_precheck=True)
    )
    try:
        principal = await resolver.resolve_for_owner_detailed(VERIFY_SUBJECT)
    finally:
        await resolver.aclose()

    assert principal is not None
    assert principal.id, "the exchanged principal must carry the target subject's own identity"


@requires_keycloak
async def test_an_unprivileged_client_is_refused_by_keycloak() -> None:
    """Verify assertion 2 — the one refusal the realm *does* enforce, measured. It refuses by
    requesting client, which is the containment that actually exists."""
    resolver = PrincipalResolver(
        _config(client_id=UNPRIVILEGED_CLIENT_ID, secret=PROBE_SECRET, with_precheck=False)
    )
    try:
        with pytest.raises(PrincipalExchangeRefused) as raised:
            await resolver.resolve_for_owner_detailed(VERIFY_SUBJECT)
    finally:
        await resolver.aclose()

    assert "refused" in str(raised.value).lower()


@requires_keycloak
async def test_a_disabled_subject_is_refused_by_the_conduits_own_precheck() -> None:
    """Verify assertion 3, and the reason this amendment exists. `PrincipalRevoked` rather than the
    generic refusal, so ADR-044's revoked-principal reason is available to whatever marks the
    watch stopped."""
    resolver = PrincipalResolver(
        _config(client_id=CONDUIT_CLIENT_ID, secret=PROBE_SECRET, with_precheck=True)
    )
    try:
        with pytest.raises(PrincipalRevoked) as raised:
            await resolver.resolve_for_owner_detailed(REVOKED_SUBJECT)
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
        _config(client_id=CONDUIT_CLIENT_ID, secret=PROBE_SECRET, with_precheck=False)
    )
    try:
        principal = await resolver.resolve_for_owner_detailed(REVOKED_SUBJECT)
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
    config = _config(client_id=CONDUIT_CLIENT_ID, secret=PROBE_SECRET, with_precheck=True)
    resolver = PrincipalResolver(
        __import__("dataclasses").replace(
            config, oidc_admin_users_url="http://127.0.0.1:9/admin/realms/osprey/users"
        )
    )
    try:
        with pytest.raises(PrincipalExchangeUnavailable):
            await resolver.resolve_for_owner_detailed(VERIFY_SUBJECT)
    finally:
        await resolver.aclose()


# --- the owner as the Conduit records it: Keycloak's subject id (ADR-043 Amendment, 27 Oct 2026) ---


async def _subject_id_of(username: str) -> str:
    """The user's Keycloak id, read with the Conduit client's own view-users grant. A principal's id
    is this subject id (the token's `sub`, ADR-127 Amendment 34), never the username."""
    resolver = PrincipalResolver(
        _config(client_id=CONDUIT_CLIENT_ID, secret=PROBE_SECRET, with_precheck=True)
    )
    try:
        token = await resolver._client_credentials_token()
        response = await resolver._exchange_http.get(
            f"{KC}/admin/realms/{REALM}/users",
            params={"username": username, "exact": "true"},
            headers={"Authorization": f"Bearer {token}"},
        )
        return str(response.json()[0]["id"])
    finally:
        await resolver.aclose()


@requires_keycloak
async def test_an_enabled_owner_recorded_by_subject_id_is_resolved() -> None:
    """Found on the owner's deployment: every hotlist owned by an analyst was marked stopped and no
    alert fired, because the pre-check looked the owner up as a *username* while the Conduit records
    owners by subject id. Measured on Keycloak 26.0: `users?username=<subject>&exact=true` answers
    200 with no users. The tests above passed throughout, because `VERIFY_SUBJECT` is a username."""
    subject = await _subject_id_of(VERIFY_SUBJECT)
    resolver = PrincipalResolver(
        _config(client_id=CONDUIT_CLIENT_ID, secret=PROBE_SECRET, with_precheck=True)
    )
    try:
        principal = await resolver.resolve_for_owner_detailed(subject)
    finally:
        await resolver.aclose()
    assert principal.id == subject


@requires_keycloak
async def test_a_disabled_owner_recorded_by_subject_id_is_still_revoked() -> None:
    subject = await _subject_id_of(REVOKED_SUBJECT)
    resolver = PrincipalResolver(
        _config(client_id=CONDUIT_CLIENT_ID, secret=PROBE_SECRET, with_precheck=True)
    )
    try:
        with pytest.raises(PrincipalRevoked):
            await resolver.resolve_for_owner_detailed(subject)
    finally:
        await resolver.aclose()


@requires_keycloak
async def test_an_owner_unknown_by_id_and_by_name_is_refused_as_not_known() -> None:
    resolver = PrincipalResolver(
        _config(client_id=CONDUIT_CLIENT_ID, secret=PROBE_SECRET, with_precheck=True)
    )
    try:
        with pytest.raises(PrincipalExchangeRefused) as raised:
            await resolver.resolve_for_owner_detailed("00000000-0000-4000-8000-000000000000")
    finally:
        await resolver.aclose()
    assert "not known" in str(raised.value)


# --- the exchange judges the subject the pre-check resolved; a misconfigured URL passes no one ---


@requires_keycloak
async def test_an_owner_recorded_by_username_is_exchanged_by_the_id_the_precheck_resolved() -> None:
    """The pre-check resolves a username to its user and judges that user; the exchange must ask
    for the same user's id, not the original string, so the two cannot judge different subjects.
    The exchanged principal's `sub` is the id the username resolved to."""
    subject = await _subject_id_of(VERIFY_SUBJECT)
    resolver = PrincipalResolver(
        _config(client_id=CONDUIT_CLIENT_ID, secret=PROBE_SECRET, with_precheck=True)
    )
    try:
        principal = await resolver.resolve_for_owner_detailed(VERIFY_SUBJECT)
    finally:
        await resolver.aclose()
    assert principal.id == subject


@requires_keycloak
async def test_a_users_url_left_at_the_realm_root_is_unavailable_and_passes_no_one() -> None:
    """A misconfigured `OIDC_ADMIN_USERS_URL` (the realm root, not `.../users`) answers 200 with an
    object that is not a user. It used to be read as a user and every owner passed, the disabled
    one included. Now: unavailable, for the enabled and the disabled alike."""
    config = _config(client_id=CONDUIT_CLIENT_ID, secret=PROBE_SECRET, with_precheck=True)
    resolver = PrincipalResolver(
        __import__("dataclasses").replace(config, oidc_admin_users_url=f"{KC}/admin/realms/{REALM}")
    )
    try:
        for owner in (VERIFY_SUBJECT, REVOKED_SUBJECT):
            with pytest.raises(PrincipalExchangeUnavailable):
                await resolver.resolve_for_owner_detailed(owner)
    finally:
        await resolver.aclose()
