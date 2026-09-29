"""`harness/realm.py` — `06_DECISIONS.md` ADR-050's own additions to the rendered realm: the
Glass's public client and the optional demo-analyst subject.

`test_the_rendered_realm_carries_only_fields_keycloak_defines` (`tests/harness/test_render.py`)
already proves the realm document as a whole carries no field Keycloak would refuse; these tests
are about what ADR-050 specifically requires of the new client and the new subject.
"""

from __future__ import annotations

import yaml
from harness.realm import (
    ADMIN_ROLE,
    CONDUIT_CLIENT_ID,
    DEMO_ADMIN_SUBJECT,
    DEMO_ANALYST_SUBJECT,
    GLASS_CLIENT_ID,
    HARNESS_CLIENT_ID,
    HARNESS_PORT,
    HARNESS_REDIRECT_URI,
    LAUNCHER_CLIENT_ID,
    LAUNCHER_PORT,
    LAUNCHER_REDIRECT_URI,
    VERIFY_SUBJECT,
    render_realm,
)

from schemas.deployment import OspreyConfig

FIXTURE_CONFIG = """
network:
  public_origin: http://localhost:9999
"""


def _config() -> OspreyConfig:
    return OspreyConfig.model_validate(yaml.safe_load(FIXTURE_CONFIG))


def _glass_client(realm: dict) -> dict:
    (client,) = [c for c in realm["clients"] if c["clientId"] == GLASS_CLIENT_ID]
    return client


def test_the_glass_client_is_public_with_pkce_and_the_standard_flow() -> None:
    """`06_DECISIONS.md` ADR-050's Decision section: "the Glass registered as a public client — no
    secret in the browser", authorization code with PKCE (S256)."""
    client = _glass_client(render_realm(_config()))

    assert client["publicClient"] is True
    assert client["standardFlowEnabled"] is True
    assert client.get("serviceAccountsEnabled") is False, (
        "a public client has no service account to hold a grant with"
    )
    assert client["attributes"]["pkce.code.challenge.method"] == "S256"


def test_the_glass_clients_redirect_and_post_logout_uris_are_exact_not_wildcards() -> None:
    """Objection 2's resolution: "an exact redirect URI and post-logout URI, no wildcards" — a
    planted `*` here is exactly the looseness ADR-050 rejected, so this is the case that goes red
    if it recurs.

    `post.logout.redirect.uris` is a client **attribute**, not a top-level field — measured against
    a real Keycloak 26 import (`_glass_client`'s own docstring has the failure this test would
    otherwise have missed entirely, since a top-level `postLogoutRedirectUris` field round-trips
    through this function's own return value just as readably as the correct shape does)."""
    client = _glass_client(render_realm(_config()))

    assert client["redirectUris"] == ["http://localhost:9999/"]
    assert client["webOrigins"] == ["http://localhost:9999"]
    assert client["attributes"]["post.logout.redirect.uris"] == "http://localhost:9999"
    for uri in [*client["redirectUris"], client["attributes"]["post.logout.redirect.uris"]]:
        assert "*" not in uri, f"{uri} contains a wildcard — objection 2 rejected exactly this"


def test_the_glass_client_carries_the_four_principal_claim_mappers() -> None:
    """Without these, a token that verifies perfectly fails as a `Principal`
    (`05_DEPLOYMENT.md` §2.1.1) — the same requirement the Conduit's own client already meets,
    extended to the new client rather than assumed to be inherited."""
    client = _glass_client(render_realm(_config()))
    names = {m["name"] for m in client["protocolMappers"]}

    assert {"clearance", "org_unit", "receivable_handling_codes", "roles"} <= names


def test_the_glass_client_carries_an_audience_mapper_naming_the_conduit() -> None:
    """Objection 1's resolution. Removing this mapper (or pointing it at the wrong client) is
    exactly the regression `services/api/tests/test_auth.py`'s own audience test would need to
    catch on the Conduit side — this is the realm-side half of the same guarantee.

    A custom string audience, not `included.client.audience` — measured against a real Keycloak 26
    (`_audience_mapper`'s own docstring): `included.client.audience` on the Glass alone left every
    token the Conduit's *own* client mints (client-credentials, token exchange) without an `aud`
    claim, and the seed step failed with `token rejected: Token is missing the "aud" claim` the
    moment the Conduit started verifying it unconditionally."""
    client = _glass_client(render_realm(_config()))
    (audience_mapper,) = [
        m for m in client["protocolMappers"] if m["protocolMapper"] == "oidc-audience-mapper"
    ]

    assert audience_mapper["config"]["included.custom.audience"] == CONDUIT_CLIENT_ID


def test_the_conduits_own_client_also_carries_the_audience_mapper() -> None:
    """The regression this test exists to catch, named directly: the Conduit's own
    client-credentials and token-exchange grants (`harness/apply.py`'s `create_investigation`,
    `grant_service_account_roles`, and every ADR-043 token exchange) are presented to the Conduit
    exactly like the Glass's tokens, and are refused the same way if this mapper is only on the
    Glass — measured directly against a real Keycloak, not assumed."""
    realm = render_realm(_config())
    (conduit_client,) = [c for c in realm["clients"] if c["clientId"] == CONDUIT_CLIENT_ID]
    (audience_mapper,) = [
        m
        for m in conduit_client["protocolMappers"]
        if m["protocolMapper"] == "oidc-audience-mapper"
    ]

    assert audience_mapper["config"]["included.custom.audience"] == CONDUIT_CLIENT_ID


def test_demo_analyst_is_absent_by_default() -> None:
    """`06_DECISIONS.md` ADR-050's own resolution of objection 3: "Apply gains --demo-analyst…
    absent by default." A plain render must not grow a new sign-in-capable subject nobody asked
    for."""
    realm = render_realm(_config())

    usernames = {u["username"] for u in realm["users"]}
    assert DEMO_ANALYST_SUBJECT not in usernames


def test_demo_analyst_is_rendered_enabled_with_no_credentials_when_asked() -> None:
    """No `credentials` block — the module docstring's own reasoning: a plaintext password in the
    realm document would defeat the "safe to write into generated output and diff" property
    `render_realm` states of itself, the same reason the client secret is never in here either.
    `harness/keycloak_admin.py` sets the password after import."""
    realm = render_realm(_config(), demo_analyst=True)
    (demo_analyst,) = [u for u in realm["users"] if u["username"] == DEMO_ANALYST_SUBJECT]

    assert demo_analyst["enabled"] is True
    assert "credentials" not in demo_analyst
    assert demo_analyst["attributes"]["clearance"] == ["OFFICIAL"]


def test_demo_analyst_can_receive_the_handling_code_the_seed_fixtures_actually_write() -> None:
    """Measured directly, running the real exit test end to end: both `scripts/seed_hmp_fixture.py`
    and `scripts/seed_fixture_corp.py` write every node with `handling_code="P"`. Reusing
    `_SUBJECT_ATTRIBUTES`'s verify-scoped `receivable_handling_codes: ["R"]` for the demo analyst
    passed every realm-shape test above and still opened the seeded investigation to a working set
    of exactly zero nodes — `CLAUDE.md` rule 3's own access-control filter doing precisely what it
    is for, on a subject nobody had actually granted the seeded data's own handling code."""
    realm = render_realm(_config(), demo_analyst=True)
    (demo_analyst,) = [u for u in realm["users"] if u["username"] == DEMO_ANALYST_SUBJECT]

    assert "P" in demo_analyst["attributes"]["receivable_handling_codes"]


def test_demo_analyst_shares_the_verify_subjects_org_unit_so_the_seeded_investigation_is_visible() -> None:  # noqa: E501
    """Measured directly, running the real exit test end to end: `harness/apply.py`'s
    `create_investigation` creates the seeded investigation by exchanging for `VERIFY_SUBJECT`, so
    the investigation's own `owning_unit` is `VERIFY_SUBJECT`'s `org_unit` —
    `services/api/investigations.py`'s `principal.org_unit == investigation.owning_unit` boundary
    then hides that investigation from any principal whose `org_unit` differs, a 403 on the delta
    WebSocket and a 404 on every investigation-scoped route. Handling codes and `org_unit` gate
    different things (content within a visible investigation vs. the investigation's own
    existence) and this subject needs both, not just the one that happens to change per demo."""
    realm = render_realm(_config(), demo_analyst=True)
    (demo_analyst,) = [u for u in realm["users"] if u["username"] == DEMO_ANALYST_SUBJECT]
    (verify_probe,) = [u for u in realm["users"] if u["username"] == VERIFY_SUBJECT]

    assert demo_analyst["attributes"]["org_unit"] == verify_probe["attributes"]["org_unit"]


def test_demo_analyst_has_a_complete_profile_so_keycloak_does_not_demand_one_at_first_sign_in() -> (
    None
):
    """Measured directly against a real Keycloak 26, running the exit test end to end: a subject
    with no mapped email/first/last name hits Keycloak's own default `VERIFY_PROFILE` required
    action on its very first interactive login — an unexpected "Update Account Information" form
    in the middle of what ADR-050's own exit test describes as a plain sign-in."""
    realm = render_realm(_config(), demo_analyst=True)
    (demo_analyst,) = [u for u in realm["users"] if u["username"] == DEMO_ANALYST_SUBJECT]

    assert demo_analyst["email"]
    assert demo_analyst["emailVerified"] is True
    assert demo_analyst["firstName"]
    assert demo_analyst["lastName"]


def test_demo_analyst_is_a_separate_subject_from_the_verify_probe() -> None:
    """Objection 4: reusing `VERIFY_SUBJECT` for interactive sign-in would let a demonstration's own
    clearance/handling tweaks silently change what the three-sided verify asserts."""
    assert DEMO_ANALYST_SUBJECT != VERIFY_SUBJECT

    realm = render_realm(_config(), demo_analyst=True)
    usernames = [u["username"] for u in realm["users"]]
    assert usernames.count(VERIFY_SUBJECT) == 1
    assert usernames.count(DEMO_ANALYST_SUBJECT) == 1


def test_the_realm_still_carries_only_fields_keycloak_defines_with_demo_analyst_on() -> None:
    """The same guarantee `tests/harness/test_render.py`'s own realm test states, re-checked with
    the flag on — a realm import refuses any field it does not recognise outright."""
    realm = render_realm(_config(), demo_analyst=True)

    # `displayName` and `loginTheme` are `RealmRepresentation` fields: the sign-in page's
    # name and look.
    known_top_level = {"realm", "displayName", "loginTheme", "enabled", "clients", "users"}
    assert set(realm) <= known_top_level

    known_client_fields = {
        "clientId",
        "enabled",
        "publicClient",
        "serviceAccountsEnabled",
        "standardFlowEnabled",
        "directAccessGrantsEnabled",
        "attributes",
        "redirectUris",
        "webOrigins",
        "protocolMappers",
    }
    for client in realm["clients"]:
        assert set(client) <= known_client_fields, (
            f"{client['clientId']}: unexpected field(s) {sorted(set(client) - known_client_fields)}"
        )

    known_user_fields = {
        "username",
        "enabled",
        "attributes",
        "email",
        "emailVerified",
        "firstName",
        "lastName",
    }
    for user in realm["users"]:
        assert set(user) <= known_user_fields, (
            f"{user['username']}: unexpected field(s) {sorted(set(user) - known_user_fields)}"
        )


# --- The launcher's client and the demo admin (friction log, 29 September 2026, third item;
# 06_DECISIONS.md ADR-051, the owner's ruling of that date) ---
#
# The launcher (`scripts/launch.py`) signs a person in so it can show the interfaces their roles
# allow. It is a third public client beside the Glass, and it is *not* the Glass: its tokens must
# not be usable against the Conduit, its redirect is a fixed loopback address, and the account that
# unlocks the Admin console is a separate subject rather than a power added to the demo analyst.


def _launcher_client(realm: dict) -> dict:
    (client,) = [c for c in realm["clients"] if c["clientId"] == LAUNCHER_CLIENT_ID]
    return client


def test_the_launcher_client_is_public_with_pkce_and_the_standard_flow_only() -> None:
    client = _launcher_client(render_realm(_config()))

    assert client["publicClient"] is True
    assert client["standardFlowEnabled"] is True
    assert client.get("serviceAccountsEnabled") is False
    assert client.get("directAccessGrantsEnabled") is False, (
        "a password grant would let anything holding a password mint launcher tokens without the "
        "browser sign-in the client exists for"
    )
    assert client["attributes"]["pkce.code.challenge.method"] == "S256"


def test_the_launchers_redirect_and_post_logout_uris_are_exact_loopback_addresses() -> None:
    """The same rule ADR-050's objection 2 states for the Glass: exact, no wildcard. Loopback and
    not `network.public_origin`, because the launcher runs on the operator's own machine whatever
    the workspace's public origin is."""
    client = _launcher_client(render_realm(_config()))

    assert client["redirectUris"] == [LAUNCHER_REDIRECT_URI]
    assert LAUNCHER_REDIRECT_URI == f"http://localhost:{LAUNCHER_PORT}/callback"
    assert client["webOrigins"] == [f"http://localhost:{LAUNCHER_PORT}"]
    assert client["attributes"]["post.logout.redirect.uris"] == f"http://localhost:{LAUNCHER_PORT}/"
    for uri in [*client["redirectUris"], client["attributes"]["post.logout.redirect.uris"]]:
        assert "*" not in uri
        assert "9999" not in uri, "derived from the workspace origin, not the loopback address"


def test_a_launcher_token_carries_the_roles_claim_but_is_not_acceptable_to_the_conduit() -> None:
    """The launcher reads `roles` from its ID token. It must carry no audience mapper: the Conduit's
    `verify_aud` refuses any token whose audience is not `osprey-conduit`, so a launcher token that
    leaked could not be replayed against the Conduit — which the Glass's own client deliberately
    can be (`_audience_mapper`)."""
    client = _launcher_client(render_realm(_config()))

    mappers = {m["name"]: m for m in client["protocolMappers"]}
    assert mappers["roles"]["config"]["id.token.claim"] == "true"
    assert mappers["roles"]["config"]["multivalued"] == "true"
    kinds = [m["protocolMapper"] for m in client["protocolMappers"]]
    assert "oidc-audience-mapper" not in kinds


def test_the_demo_admin_is_absent_by_default() -> None:
    usernames = [u["username"] for u in render_realm(_config())["users"]]
    assert DEMO_ADMIN_SUBJECT not in usernames


def test_the_demo_admin_holds_only_the_admin_role_and_nothing_an_analyst_has() -> None:
    """The owner's ruling of 29 September 2026: a second demo account, so the analyst account stays
    unprivileged. If it also held the Studio roles the two accounts would differ only in name."""
    realm = render_realm(_config(), demo_analyst=True)
    (admin,) = [u for u in realm["users"] if u["username"] == DEMO_ADMIN_SUBJECT]
    (analyst,) = [u for u in realm["users"] if u["username"] == DEMO_ANALYST_SUBJECT]

    assert admin["attributes"]["roles"] == [ADMIN_ROLE]
    assert ADMIN_ROLE not in analyst["attributes"]["roles"]
    assert admin["enabled"] is True
    assert "credentials" not in admin, "the password travels beside the realm, never inside it"


def test_the_demo_admin_has_a_complete_profile_so_keycloak_does_not_demand_one() -> None:
    realm = render_realm(_config(), demo_analyst=True)
    (admin,) = [u for u in realm["users"] if u["username"] == DEMO_ADMIN_SUBJECT]
    assert admin["email"].endswith(".invalid")
    assert admin["emailVerified"] is True
    assert admin["firstName"] and admin["lastName"]


def test_the_admin_role_has_one_name_across_the_realm_the_harness_and_the_conduit() -> None:
    """Three modules each check the same role; a rename in one leaves an admin the harness admits
    and the Conduit refuses (or the reverse) with every test still green."""
    from harness.webapp_auth import ADMIN_ROLE as HARNESS_ADMIN_ROLE
    from services.api.app import ADMIN_ROLE as CONDUIT_ADMIN_ROLE

    assert ADMIN_ROLE == HARNESS_ADMIN_ROLE == CONDUIT_ADMIN_ROLE == "osprey-admin"


# --- The Admin console's own client (ADR-051 decision 4) ---


def _harness_client(realm: dict) -> dict:
    (client,) = [c for c in realm["clients"] if c["clientId"] == HARNESS_CLIENT_ID]
    return client


def test_the_harness_client_is_public_with_pkce_and_the_standard_flow_only() -> None:
    client = _harness_client(render_realm(_config()))

    assert client["publicClient"] is True
    assert client["standardFlowEnabled"] is True
    assert client.get("serviceAccountsEnabled") is False
    assert client.get("directAccessGrantsEnabled") is False
    assert client["attributes"]["pkce.code.challenge.method"] == "S256"


def test_the_harness_redirect_and_logout_addresses_are_exact_and_on_the_harness_port() -> None:
    """The harness serves on `HARNESS_PORT`; a redirect anywhere else would either be refused by
    Keycloak (sign-in fails with an error page) or, if loosened to make it work, be the loose
    redirect ADR-050's objection 2 forbids."""
    client = _harness_client(render_realm(_config()))

    assert HARNESS_PORT == 7000
    assert HARNESS_REDIRECT_URI == f"http://localhost:{HARNESS_PORT}/callback"
    assert client["redirectUris"] == [HARNESS_REDIRECT_URI]
    assert client["webOrigins"] == [f"http://localhost:{HARNESS_PORT}"]
    assert client["attributes"]["post.logout.redirect.uris"] == f"http://localhost:{HARNESS_PORT}/"
    for uri in [*client["redirectUris"], client["attributes"]["post.logout.redirect.uris"]]:
        assert "*" not in uri


def test_a_harness_token_carries_roles_and_no_conduit_audience() -> None:
    client = _harness_client(render_realm(_config()))
    kinds = [m["protocolMapper"] for m in client["protocolMappers"]]
    assert "oidc-audience-mapper" not in kinds
    (roles,) = [m for m in client["protocolMappers"] if m["name"] == "roles"]
    assert roles["config"]["id.token.claim"] == "true"


def test_the_harness_client_is_rendered_by_default_because_the_console_must_be_reachable() -> None:
    """Unlike the demo subjects, the client is not optional: the Admin console enforces sign-in
    against the realm whether or not `--demo-analyst` was passed."""
    assert HARNESS_CLIENT_ID in [c["clientId"] for c in render_realm(_config())["clients"]]
