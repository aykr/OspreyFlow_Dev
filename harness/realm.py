"""The identity-provider realm, rendered from `osprey.yaml`'s governance section.

`05_DEPLOYMENT.md` §2.1.1 states what a rendered realm must carry and why each item is written down:
every one of them fails **silently** when missing. This module produces that realm as a Keycloak
realm-import document, plus the client secret that must never be in the repository.

## What is in here and what is deliberately not

**In:** the Conduit's confidential client; the impersonation grant it exchanges with; a **separate**
view-users grant for the pre-check; protocol mappers for the four custom claims a `Principal` is
built from; `unmanagedAttributePolicy: ENABLED`; a disposable verify-only subject; a deliberately
disabled subject; an unprivileged client that holds neither grant; and, since `06_DECISIONS.md`
ADR-050, the Glass's own **public** client (authorization code with PKCE, no secret) carrying an
audience mapper that names the Conduit as its token's audience, plus an optional disposable
demo-analyst subject rendered only when `apply --demo-analyst` asks for one.

**Not in:** the client secret, and — the same reasoning, ADR-050's objection 3's resolution — the
demo-analyst's password. `05_DEPLOYMENT.md` §2.5 — "It never sees a secret. Credentials are
entered as references" — and §7, "Secrets from the environment or a secret manager, never in
`osprey.yaml`, never in an image". `generate_client_secret()` mints one at apply time and
`harness/apply.py` writes it into the deployment's own environment file, which is generated output
and gitignored. The realm document references the client and the demo-analyst subject by id; the
secret and the password travel beside the document, never inside it — the demo-analyst is rendered
with no `credentials` block, exactly like `VERIFY_SUBJECT`/`REVOKED_SUBJECT` below, and
`harness/keycloak_admin.py` sets its password after import the same way it sets the client secret.

## Why the two verify subjects are in a *dev* realm and what that means

`06_DECISIONS.md` ADR-043's amendment requires a three-sided verify, and two of its three sides need
subjects that exist: one enabled and disposable, one disabled. They are rendered for `local-lite`
and `small` — profiles whose whole purpose is a machine you own — and a `cluster` realm is not
rendered by this module at all. A production realm is the operator's, and these subjects have no
place in it. The optional demo-analyst subject (below) is rendered for the same two profiles and for
the same reason, and is a **separate** subject from `VERIFY_SUBJECT` — ADR-050's objection 4: reusing
the verify subject for interactive sign-in would mean any change to its clearance or handling codes
for a demonstration silently changes what the three-sided verify itself asserts.
"""

from __future__ import annotations

import secrets
from typing import Any

from schemas.deployment import OspreyConfig

#: The Conduit's own confidential client.
CONDUIT_CLIENT_ID = "osprey-conduit"
#: Holds neither grant. Verify assertion 2 is that Keycloak refuses it — the one refusal the realm
#: actually enforces (ADR-043's amendment; measured, not assumed).
UNPRIVILEGED_CLIENT_ID = "osprey-unprivileged"
#: Enabled. Verify assertion 1 exchanges for this one.
VERIFY_SUBJECT = "osprey-verify-probe"
#: Disabled. Verify assertion 3 is that the Conduit's own pre-check refuses it — the realm will not.
REVOKED_SUBJECT = "osprey-verify-revoked"

#: `06_DECISIONS.md` ADR-050 — the Glass, registered as a **public** client (no secret in the
#: browser): authorization code with PKCE, `standardFlowEnabled`, an exact redirect URI and
#: post-logout URI derived from `osprey.yaml`'s `network.public_origin`, no wildcards (objection 2's
#: resolution), and an audience mapper naming `CONDUIT_CLIENT_ID` so the Conduit's own unconditional-
#: when-configured `verify_aud` refuses a token minted for anything else (objection 1's resolution).
GLASS_CLIENT_ID = "osprey-glass"

#: `06_DECISIONS.md` ADR-050 objection 3/4's resolution — a disposable analyst subject that can
#: actually sign in interactively, rendered only when `apply --demo-analyst` asks for one. Distinct
#: from `VERIFY_SUBJECT`: reusing that subject would let a demonstration's own clearance/handling
#: tweaks silently change what the three-sided verify asserts.
DEMO_ANALYST_SUBJECT = "osprey-demo-analyst"

#: Granted to the Conduit's service account *after* import, by `harness/keycloak_admin.py`: a realm
#: import cannot express a service-account role mapping onto `realm-management` without ids that do
#: not exist until the import has run.
#:
#: **Kept out of the rendered document.** It was briefly written into the realm JSON as a note, and
#: Keycloak's import refuses any field it does not recognise — `Unrecognized field
#: "ospreyRequiredServiceAccountRoles"` — so the whole realm failed to import and Keycloak never
#: became healthy. A realm document carries only what Keycloak defines; anything this harness needs
#: to remember lives here.
REQUIRED_SERVICE_ACCOUNT_ROLES = ("impersonation", "view-users")

#: Keycloak 26 discards unrecognised user attributes by default and reports nothing — the write
#: succeeds, the attribute is stored nowhere, and the token arrives without it, so a realm that
#: looks correct produces principals with no clearance (`05_DEPLOYMENT.md` §2.1.1).
#:
#: **Set after import, not in the realm document.** It belongs to the *user profile* configuration
#: (`/admin/realms/{realm}/users/profile`), not to `RealmRepresentation`; putting it in the realm
#: JSON makes the whole import fail with `Unrecognized field "unmanagedAttributePolicy"` and
#: Keycloak never becomes healthy. Found running the golden path — twice, once for this field and
#: once for a note-to-self left in the same document.
UNMANAGED_ATTRIBUTE_POLICY = "ENABLED"

#: The claims `services/api/auth.py` builds a `Principal` from. A mapper is rendered for each:
#: without one, an exchanged token verifies as a token and then fails as a principal, and the error
#: names a missing claim rather than a missing mapper.
PRINCIPAL_CLAIMS: tuple[tuple[str, bool], ...] = (
    ("clearance", False),
    ("org_unit", False),
    ("receivable_handling_codes", True),
    ("roles", True),
)

_SUBJECT_ATTRIBUTES = {
    "clearance": ["OFFICIAL"],
    "org_unit": ["verify"],
    "receivable_handling_codes": ["R"],
    "roles": ["analyst"],
}

#: `06_DECISIONS.md` ADR-050 objection 4's own reasoning, applied literally: the demo analyst is a
#: separate subject *because* its clearance/handling codes must be free to differ from
#: `_SUBJECT_ATTRIBUTES`'s verify-scoped values without touching what the three-sided verify
#: asserts. `receivable_handling_codes: ["R"]` above cannot see anything in either seed fixture —
#: measured directly, running the real exit test end to end: `scripts/seed_hmp_fixture.py` and
#: `scripts/seed_fixture_corp.py` both write `handling_code="P"`, so a subject that can only receive
#: `"R"` opens the seeded investigation to an empty working set, indistinguishable from a broken
#: sign-in unless someone reads the access-control filter's own reasoning for why it is doing
#: exactly what rule 3 asks of it. `clearance: OFFICIAL` is deliberately kept (not raised to
#: `SECRET`): `fixture_corp.py`'s own single `SECRET` shortcut node stays correctly invisible to
#: this subject, which is the access-control floor demonstrating itself rather than a gap.
#:
#: **`org_unit` stays `"verify"`, and this is not a copy-paste leftover.** Also measured directly:
#: changing it to anything else made the seeded investigation itself invisible — a 403 on the
#: delta WebSocket handshake and a 404 on every investigation-scoped route, both from
#: `services/api/investigations.py`'s own `principal.org_unit == investigation.owning_unit`
#: boundary. `harness/apply.py`'s `create_investigation` creates the seeded investigation by
#: exchanging for `VERIFY_SUBJECT` — `owning_unit` becomes `VERIFY_SUBJECT`'s own `org_unit`, so any
#: principal that is to see that investigation must share it. Handling codes gate *content* within
#: an investigation the principal can already open; `org_unit` gates whether the investigation
#: exists for them at all, and the two are not interchangeable.
_DEMO_ANALYST_ATTRIBUTES = {
    "clearance": ["OFFICIAL"],
    "org_unit": ["verify"],
    "receivable_handling_codes": ["P"],
    "roles": ["analyst"],
}


def generate_client_secret() -> str:
    """A fresh secret per apply. Never derived from anything in the repository, never written into
    the realm document, never logged."""
    return secrets.token_urlsafe(32)


def _claim_mappers() -> list[dict[str, Any]]:
    return [
        {
            "name": claim,
            "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-attribute-mapper",
            "config": {
                "user.attribute": claim,
                "claim.name": claim,
                "jsonType.label": "String",
                "multivalued": "true" if multivalued else "false",
                "access.token.claim": "true",
                "id.token.claim": "true",
            },
        }
        for claim, multivalued in PRINCIPAL_CLAIMS
    ]


def _audience_mapper() -> dict[str, Any]:
    """`06_DECISIONS.md` ADR-050 objection 1's resolution: without this, a token this mapper is
    attached to carries no `aud` claim naming the Conduit at all, and the Conduit's own
    `verify_aud` — unconditional whenever `OIDC_AUDIENCE` is configured, which every rendered
    deployment now does (`harness/render.py`'s `_render_env`) — refuses it, real sign-in or not.

    **A custom string audience, not `included.client.audience`.** The first version of this mapper
    used `included.client.audience` (naming the Conduit *as another client*) and attached it only to
    the Glass — measured directly against a real Keycloak: `harness/apply.py`'s own seed step then
    failed with `token rejected: Token is missing the "aud" claim`, because the Conduit's **own**
    client-credentials and token-exchange grants (used by the seed, and by
    `create_investigation`/`grant_service_account_roles`) carry no such mapper on the Conduit's own
    client, and every one of those tokens is presented to the Conduit exactly like the Glass's. This
    mapper is attached to *every* client whose tokens the Conduit must accept — the Conduit's own and
    the Glass's — with a plain literal audience string, not a client-to-client reference, which needs
    no self-reference special case for the Conduit's own client to name itself.
    """
    return {
        "name": "audience-conduit",
        "protocol": "openid-connect",
        "protocolMapper": "oidc-audience-mapper",
        "config": {
            "included.custom.audience": CONDUIT_CLIENT_ID,
            "access.token.claim": "true",
            "id.token.claim": "false",
        },
    }


def _glass_client(config: OspreyConfig) -> dict[str, Any]:
    """The Glass's public client — `06_DECISIONS.md` ADR-050's Decision section: "OIDC authorization
    code with PKCE… the Glass registered as a public client — no secret in the browser." Redirect
    and post-logout URIs are **exact**, derived from `network.public_origin`, never a wildcard
    (objection 2's resolution): a loose redirect URI is how authorization codes get stolen, and
    `05_DEPLOYMENT.md` §2.1.1's own client-secret note applies here too — this client has none to
    leak, being public, but the redirect URI is the equivalent surface for a public client.

    **`post.logout.redirect.uris` is a client *attribute*, not the top-level `postLogoutRedirectUris`
    field a hand-written realm document reaches for by analogy with `redirectUris`.** Measured
    directly, not assumed: a real Keycloak 26 realm import of the first version of this function
    refused the whole import — `Unrecognized field "postLogoutRedirectUris" (class
    org.keycloak.representations.idm.ClientRepresentation)` — and the Conduit's own confidential
    client never became healthy, the same class of silent-until-run failure `05_DEPLOYMENT.md`
    §2.1.1 already names for `unmanagedAttributePolicy`. `ClientRepresentation` has no post-logout
    field at all; Keycloak stores it as `attributes["post.logout.redirect.uris"]`, alongside the
    PKCE attribute already here.
    """
    origin = config.network.public_origin
    redirect_uri = f"{origin}/"
    return {
        "clientId": GLASS_CLIENT_ID,
        "enabled": True,
        "publicClient": True,
        "serviceAccountsEnabled": False,
        "standardFlowEnabled": True,
        "directAccessGrantsEnabled": False,
        "attributes": {
            "pkce.code.challenge.method": "S256",
            "post.logout.redirect.uris": origin,
        },
        "redirectUris": [redirect_uri],
        "webOrigins": [origin],
        "protocolMappers": [*_claim_mappers(), _audience_mapper()],
    }


def render_realm(
    config: OspreyConfig, *, realm_name: str = "osprey", demo_analyst: bool = False
) -> dict[str, Any]:
    """The realm-import document. Pure — no secret and no password is in it, so this is safe to
    write into generated output and to diff.

    `demo_analyst`: `06_DECISIONS.md` ADR-050 objection 3/4's resolution — `harness/apply.py`'s
    `--demo-analyst` flag. Off by default, so a plain `apply` renders exactly the realm it did
    before this subject existed.
    """
    users = [
        {
            "username": VERIFY_SUBJECT,
            "enabled": True,
            "attributes": dict(_SUBJECT_ATTRIBUTES),
        },
        {
            # Disabled on purpose. The realm will still mint a token for this subject on
            # request — that is the finding ADR-043's amendment records — so the Conduit's own
            # pre-check is what must refuse it, and this subject is how the deploy proves it.
            "username": REVOKED_SUBJECT,
            "enabled": False,
            "attributes": dict(_SUBJECT_ATTRIBUTES),
        },
    ]
    if demo_analyst:
        users.append(
            {
                # No `credentials` block — see the module docstring's "Not in" paragraph.
                # `harness/keycloak_admin.py` sets the password after import, the same way it sets
                # the client secret.
                "username": DEMO_ANALYST_SUBJECT,
                "enabled": True,
                "attributes": dict(_DEMO_ANALYST_ATTRIBUTES),
                # Without these, Keycloak's own default `VERIFY_PROFILE` required action stops the
                # exit test's first interactive sign-in with an "Update Account Information" form —
                # measured directly, not assumed, running the real exit test end to end: a subject
                # created without a mapped email/name is exactly what a fresh admin-API user looks
                # like, and Keycloak's own new-user default demands them before issuing a token.
                # `.invalid` is the RFC 2606-reserved TLD for exactly this — guaranteed never a real,
                # deliverable domain.
                "email": "osprey-demo-analyst@ospreyflow.invalid",
                "emailVerified": True,
                "firstName": "Demo",
                "lastName": "Analyst",
            }
        )
    return {
        "realm": realm_name,
        "enabled": True,
        "clients": [
            {
                "clientId": CONDUIT_CLIENT_ID,
                "enabled": True,
                "publicClient": False,
                "serviceAccountsEnabled": True,
                "standardFlowEnabled": False,
                # The audience mapper here (not only on the Glass client) is what
                # `_audience_mapper`'s own docstring explains: the Conduit's own client-credentials
                # and token-exchange grants are checked by exactly the same `verify_aud`, and a
                # token missing it is refused regardless of which client minted it.
                "protocolMappers": [*_claim_mappers(), _audience_mapper()],
            },
            {
                "clientId": UNPRIVILEGED_CLIENT_ID,
                "enabled": True,
                "publicClient": False,
                "serviceAccountsEnabled": True,
                "standardFlowEnabled": False,
            },
            _glass_client(config),
        ],
        "users": users,
    }


def render_realm_json(
    config: OspreyConfig, *, realm_name: str = "osprey", demo_analyst: bool = False
) -> str:
    import json

    return (
        json.dumps(
            render_realm(config, realm_name=realm_name, demo_analyst=demo_analyst),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
