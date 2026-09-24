"""The realm configuration a realm-import document cannot express.

Two service-account role grants — `impersonation` and `view-users` — must land on the Conduit's own
client after import, because expressing them in the import would need client and role ids that do
not exist until the import has run.

**They are two grants, not one, and that is the point.** `06_DECISIONS.md` ADR-043's amendment
(Accepted, 24 September 2026) places the revoked-principal containment in a pre-check that reads a
principal's enabled status *before* exchanging for them — and it must read with an authority other
than the one that mints the token. A single combined grant would leave the pre-check asking the
component that has already said yes.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

REQUIRED_ROLES = ("impersonation", "view-users")


class RealmConfigurationFailed(RuntimeError):
    """Names what could not be configured. A deployment whose grants are missing resolves no watch
    owner at all, and the symptom an operator meets is watches marked stopped — so this fails
    loudly here rather than silently later."""


def _call(url: str, *, token: str | None = None, data: dict | None = None, form: bool = False):
    body = None
    headers: dict[str, str] = {}
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode()
            return response.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else raw)
    except urllib.error.HTTPError as error:
        raw = error.read().decode()
        return error.code, (json.loads(raw) if raw.strip().startswith(("{", "[")) else raw)
    except OSError as error:
        raise RealmConfigurationFailed(f"{url} unreachable: {error}") from error


def grant_service_account_roles(
    *, issuer: str, realm: str, admin_user: str, admin_password: str, client_secret: str
) -> None:
    status, token_response = _call(
        f"{issuer}/realms/master/protocol/openid-connect/token",
        data={
            "client_id": "admin-cli",
            "username": admin_user,
            "password": admin_password,
            "grant_type": "password",
        },
        form=True,
    )
    if status != 200:
        raise RealmConfigurationFailed(
            f"could not authenticate to Keycloak: {status} {token_response}"
        )
    token = token_response["access_token"]

    from harness.realm import CONDUIT_CLIENT_ID, UNPRIVILEGED_CLIENT_ID

    # The rendered realm declares both clients but a realm import cannot carry their secrets, so
    # they are set here from the same apply-time value the env file records.
    for client_id in (CONDUIT_CLIENT_ID, UNPRIVILEGED_CLIENT_ID):
        status, found = _call(
            f"{issuer}/admin/realms/{realm}/clients?clientId={client_id}", token=token
        )
        if status != 200 or not found:
            raise RealmConfigurationFailed(f"client {client_id!r} not found after realm import")
        uuid = found[0]["id"]
        _call(
            f"{issuer}/admin/realms/{realm}/clients/{uuid}",
            token=token,
            data={**found[0], "secret": client_secret},
        )

    # The user-profile policy, which is not part of `RealmRepresentation` and so cannot travel in
    # the realm import. Without it every custom attribute written below is silently discarded.
    from harness.realm import UNMANAGED_ATTRIBUTE_POLICY

    status, profile = _call(f"{issuer}/admin/realms/{realm}/users/profile", token=token)
    if status == 200 and isinstance(profile, dict):
        profile["unmanagedAttributePolicy"] = UNMANAGED_ATTRIBUTE_POLICY
        status, _ = _call(
            f"{issuer}/admin/realms/{realm}/users/profile", token=token, data=profile
        )
        if status not in (200, 204):
            raise RealmConfigurationFailed(
                f"could not enable unmanaged user attributes: {status} — every custom claim would "
                "be silently discarded and principals would arrive with no clearance"
            )

    status, conduit = _call(
        f"{issuer}/admin/realms/{realm}/clients?clientId={CONDUIT_CLIENT_ID}", token=token
    )
    uuid = conduit[0]["id"]
    status, service_account = _call(
        f"{issuer}/admin/realms/{realm}/clients/{uuid}/service-account-user", token=token
    )
    if status != 200:
        raise RealmConfigurationFailed(
            f"no service account on {CONDUIT_CLIENT_ID}: {service_account}"
        )

    status, management = _call(
        f"{issuer}/admin/realms/{realm}/clients?clientId=realm-management", token=token
    )
    management_uuid = management[0]["id"]
    status, roles = _call(
        f"{issuer}/admin/realms/{realm}/clients/{management_uuid}/roles", token=token
    )
    wanted = [role for role in roles if role["name"] in REQUIRED_ROLES]
    missing = set(REQUIRED_ROLES) - {role["name"] for role in wanted}
    if missing:
        raise RealmConfigurationFailed(f"realm-management has no role(s): {sorted(missing)}")

    status, _ = _call(
        f"{issuer}/admin/realms/{realm}/users/{service_account['id']}"
        f"/role-mappings/clients/{management_uuid}",
        token=token,
        data=wanted,
    )
    if status not in (204, 201, 200):
        raise RealmConfigurationFailed(f"could not grant {REQUIRED_ROLES}: {status}")
