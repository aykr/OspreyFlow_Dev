"""The realm configuration a realm-import document cannot express.

Two service-account role grants — `impersonation` and `view-users` — must land on the Conduit's own
client after import, because expressing them in the import would need client and role ids that do
not exist until the import has run.

**They are two grants, not one, and that is the point.** `06_DECISIONS.md` ADR-043's amendment
(Accepted, 24 September 2026) places the revoked-principal containment in a pre-check that reads a
principal's enabled status *before* exchanging for them — and it must read with an authority other
than the one that mints the token. A single combined grant would leave the pre-check asking the
component that has already said yes.

`set_demo_analyst_password` (ADR-050 objection 3's resolution) is the same shape for a different
secret: the demo-analyst subject's own apply-time password, set here rather than carried in the
realm document for the same reason the client secret is — a realm import cannot carry a password
that never touches the repository.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

REQUIRED_ROLES = ("impersonation", "view-users")


class RealmConfigurationFailed(RuntimeError):
    """Names what could not be configured. A deployment whose grants are missing resolves no watch
    owner at all, and the symptom an operator meets is watches marked stopped — so this fails
    loudly here rather than silently later."""


class AdminLoginRefused(RealmConfigurationFailed):
    """Keycloak was reached and refused the admin login (as opposed to not being reachable)."""


def _call(
    url: str,
    *,
    token: str | None = None,
    data: dict[str, Any] | list[Any] | None = None,
    form: bool = False,
    method: str | None = None,
) -> Any:
    """`method` is explicit because `urllib` infers POST whenever a body is present, and Keycloak's
    admin API uses PUT for updates — a PUT sent as POST comes back 405, which reads like a wrong
    URL rather than a wrong verb. Found configuring the realm's user profile."""
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
    request = urllib.request.Request(
        url, data=body, headers=headers, method=method or ("POST" if body is not None else "GET")
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode()
            return response.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else raw)
    except urllib.error.HTTPError as error:
        raw = error.read().decode()
        return error.code, (json.loads(raw) if raw.strip().startswith(("{", "[")) else raw)
    except OSError as error:
        raise RealmConfigurationFailed(f"{url} unreachable: {error}") from error


def admin_token(*, issuer: str, admin_user: str, admin_password: str) -> str:
    """A master-realm admin token. A refusal and an unreachable Keycloak are different failures:
    `_call` raises for the second, this raises for the first (ADR-044's distinction)."""
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
        raise (AdminLoginRefused if status in (400, 401) else RealmConfigurationFailed)(
            f"could not authenticate to Keycloak: {status} {token_response}"
        )
    return str(token_response["access_token"])


def ensure_client(*, issuer: str, realm: str, token: str, client: dict[str, Any]) -> str:
    """Create a client unless it exists. Keycloak's 409 for a duplicate is the expected answer on
    a second run, not a failure. An existing client is left as it is."""
    status, found = _call(
        f"{issuer}/admin/realms/{realm}/clients?clientId={client['clientId']}", token=token
    )
    if status == 200 and found:
        return "already registered"
    status, body = _call(f"{issuer}/admin/realms/{realm}/clients", token=token, data=client)
    if status == 409:
        return "already registered"
    if status not in (200, 201):
        raise RealmConfigurationFailed(
            f"could not register client {client['clientId']!r}: {status} {body}"
        )
    return "registered"


def ensure_user(*, issuer: str, realm: str, token: str, user: dict[str, Any]) -> str:
    """As `ensure_client`, for a subject. The subject is created without a password."""
    username = user["username"]
    status, found = _call(
        f"{issuer}/admin/realms/{realm}/users?username={username}&exact=true", token=token
    )
    if status == 200 and found:
        return "already there"
    status, body = _call(f"{issuer}/admin/realms/{realm}/users", token=token, data=user)
    if status == 409:
        return "already there"
    if status not in (200, 201):
        raise RealmConfigurationFailed(f"could not create {username!r}: {status} {body}")
    return "created"


def set_user_password(*, issuer: str, realm: str, token: str, username: str, password: str) -> None:
    """Sets a non-temporary password on a subject that must already exist."""
    status, found = _call(
        f"{issuer}/admin/realms/{realm}/users?username={username}&exact=true", token=token
    )
    if status != 200 or not found:
        raise RealmConfigurationFailed(
            f"{username!r} not found in the realm — was it rendered with demo_analyst=True, or "
            "has Keycloak restarted since?"
        )
    status, _ = _call(
        f"{issuer}/admin/realms/{realm}/users/{found[0]['id']}/reset-password",
        token=token,
        data={"type": "password", "value": password, "temporary": False},
        method="PUT",
    )
    if status not in (204, 200):
        raise RealmConfigurationFailed(
            f"could not set {username}'s password: {status} — the credentials written to the "
            "environment file will not work"
        )


def grant_service_account_roles(
    *, issuer: str, realm: str, admin_user: str, admin_password: str, client_secret: str
) -> None:
    token = admin_token(issuer=issuer, admin_user=admin_user, admin_password=admin_password)

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
            method="PUT",
        )

    # The user-profile policy, which is not part of `RealmRepresentation` and so cannot travel in
    # the realm import. Without it every custom attribute written below is silently discarded.
    from harness.realm import UNMANAGED_ATTRIBUTE_POLICY

    status, profile = _call(f"{issuer}/admin/realms/{realm}/users/profile", token=token)
    if status == 200 and isinstance(profile, dict):
        profile["unmanagedAttributePolicy"] = UNMANAGED_ATTRIBUTE_POLICY
        status, _ = _call(
            f"{issuer}/admin/realms/{realm}/users/profile",
            token=token,
            data=profile,
            method="PUT",
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


def set_demo_analyst_password(
    *, issuer: str, realm: str, admin_user: str, admin_password: str, password: str
) -> None:
    """`06_DECISIONS.md` ADR-050 objection 3's resolution — `harness/apply.py`'s `--demo-analyst`
    flag calls this after the realm import, the same shape `grant_service_account_roles` above
    already uses for the client secret: the realm document names the subject with no `credentials`
    block (`harness/realm.py`'s own docstring has the reasoning), and the apply-time value travels
    beside it, never inside it.

    Only called when `--demo-analyst` renders the subject at all; a `RealmConfigurationFailed` here
    means the demo/exit-test subject cannot sign in, which is exactly the failure ADR-050's own exit
    test would otherwise discover the hard way — as a login that refuses the printed credentials.
    """
    from harness.realm import DEMO_ANALYST_SUBJECT

    token = admin_token(issuer=issuer, admin_user=admin_user, admin_password=admin_password)
    set_user_password(
        issuer=issuer, realm=realm, token=token, username=DEMO_ANALYST_SUBJECT, password=password
    )


def set_demo_admin_password(
    *, issuer: str, realm: str, admin_user: str, admin_password: str, password: str
) -> None:
    """`06_DECISIONS.md` ADR-051: the second demo subject's password, set the same way and for the
    same reason as the analyst's. Only its own subject is touched."""
    from harness.realm import DEMO_ADMIN_SUBJECT

    token = admin_token(issuer=issuer, admin_user=admin_user, admin_password=admin_password)
    set_user_password(
        issuer=issuer, realm=realm, token=token, username=DEMO_ADMIN_SUBJECT, password=password
    )
