"""The identity-provider realm, rendered from `osprey.yaml`'s governance section.

`05_DEPLOYMENT.md` §2.1.1 states what a rendered realm must carry and why each item is written down:
every one of them fails **silently** when missing. This module produces that realm as a Keycloak
realm-import document, plus the client secret that must never be in the repository.

## What is in here and what is deliberately not

**In:** the Conduit's confidential client; the impersonation grant it exchanges with; a **separate**
view-users grant for the pre-check; protocol mappers for the four custom claims a `Principal` is
built from; `unmanagedAttributePolicy: ENABLED`; a disposable verify-only subject; a deliberately
disabled subject; and an unprivileged client that holds neither grant.

**Not in:** the client secret. `05_DEPLOYMENT.md` §2.5 — "It never sees a secret. Credentials are
entered as references" — and §7, "Secrets from the environment or a secret manager, never in
`osprey.yaml`, never in an image". `generate_client_secret()` mints one at apply time and
`harness/apply.py` writes it into the deployment's own environment file, which is generated output
and gitignored. The realm document references the client by id; the secret travels beside it, never
inside it.

## Why the two test subjects are in a *dev* realm and what that means

`06_DECISIONS.md` ADR-043's amendment requires a three-sided verify, and two of its three sides need
subjects that exist: one enabled and disposable, one disabled. They are rendered for `local-lite`
and `small` — profiles whose whole purpose is a machine you own — and a `cluster` realm is not
rendered by this module at all. A production realm is the operator's, and these subjects have no
place in it.
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


def render_realm(config: OspreyConfig, *, realm_name: str = "osprey") -> dict[str, Any]:
    """The realm-import document. Pure — the secret is not in it, so this is safe to write into
    generated output and to diff."""
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
                "protocolMappers": _claim_mappers(),
            },
            {
                "clientId": UNPRIVILEGED_CLIENT_ID,
                "enabled": True,
                "publicClient": False,
                "serviceAccountsEnabled": True,
                "standardFlowEnabled": False,
            },
        ],
        "users": [
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
        ],
    }


def render_realm_json(config: OspreyConfig, *, realm_name: str = "osprey") -> str:
    import json

    return json.dumps(render_realm(config, realm_name=realm_name), indent=2, sort_keys=True) + "\n"
