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

#: `manage-users` and `manage-clients` (ADR-112 Amendment 1): the Admin area's People and roles and
#: Dashboards, through the Conduit's own account so every change passes its right check and audit.
REQUIRED_ROLES = ("impersonation", "view-users", "manage-users", "manage-clients")


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
    a second run, not a failure. An existing client keeps everything it has except the addresses it
    redirects to, which are brought up to date: they are exact-match, so a client registered at an
    address that has since moved would fail at Keycloak's own error page."""
    status, found = _call(
        f"{issuer}/admin/realms/{realm}/clients?clientId={client['clientId']}", token=token
    )
    if status == 200 and found:
        existing = found[0]
        attributes = {**existing.get("attributes", {})}
        for key in ("post.logout.redirect.uris",):
            if key in client.get("attributes", {}):
                attributes[key] = client["attributes"][key]
        wanted = {
            "redirectUris": client["redirectUris"],
            "webOrigins": client["webOrigins"],
            "attributes": attributes,
        }
        if "secret" in client:
            # A confidential client's secret comes from the env file; keep Keycloak in step with it.
            wanted["secret"] = client["secret"]
        if all(existing.get(k) == v for k, v in wanted.items()):
            return "already registered"
        status, body = _call(
            f"{issuer}/admin/realms/{realm}/clients/{existing['id']}",
            token=token,
            data={**existing, **wanted},
            method="PUT",
        )
        if status not in (200, 204):
            raise RealmConfigurationFailed(
                f"could not update client {client['clientId']!r}: {status} {body}"
            )
        return "already registered; redirect address brought up to date"
    status, body = _call(f"{issuer}/admin/realms/{realm}/clients", token=token, data=client)
    if status == 409:
        return "already registered"
    if status not in (200, 201):
        raise RealmConfigurationFailed(
            f"could not register client {client['clientId']!r}: {status} {body}"
        )
    return "registered"


def remove_client(*, issuer: str, realm: str, token: str, client_id: str) -> str:
    """Remove a retired client; a client already gone is not a failure."""
    base = f"{issuer}/admin/realms/{realm}/clients"
    status, found = _call(f"{base}?clientId={urllib.parse.quote(client_id)}", token=token)
    if status != 200:
        raise RealmConfigurationFailed(f"listing clients was refused: {status}")
    if not found:
        return "not present"
    status, body = _call(f"{base}/{found[0]['id']}", token=token, method="DELETE")
    if status not in (204, 404):
        raise RealmConfigurationFailed(f"removing {client_id} was refused: {status} {body}")
    return "removed"


def ensure_realm_mail(
    *, issuer: str, realm: str, token: str, mail: Any, password: str | None
) -> str:
    """The realm's mail server (ADR-114 Amendment 5), so Keycloak sends invitations and resets.
    Measured on Keycloak 26.0.8: Keycloak never gives the password back when the realm is read, so
    it is written every time from the deployment's own secrets file. Says nothing of the
    password."""
    status, current = _call(f"{issuer}/admin/realms/{realm}", token=token)
    if status != 200:
        raise RealmConfigurationFailed(f"reading the realm was refused: {status}")
    server = {
        "host": mail.host, "port": str(mail.port), "from": mail.from_address,
        "fromDisplayName": "OspreyFlow", "starttls": "true" if mail.starttls else "false",
        "ssl": "false", "auth": "true" if mail.username else "false",
    }  # fmt: skip
    if mail.username:
        server |= {"user": mail.username, "password": password or ""}
    status, body = _call(
        f"{issuer}/admin/realms/{realm}", token=token, data={**current, "smtpServer": server},
        method="PUT",
    )  # fmt: skip
    if status not in (200, 204):
        raise RealmConfigurationFailed(f"setting the realm's mail server was refused: {status}")
    return f"mail server {mail.host}:{mail.port} from {mail.from_address}"


def ensure_realm_sign_in_rules(
    *, issuer: str, realm: str, token: str, rules: dict[str, Any]
) -> str:
    """The realm's sign-in rules (ADR-115 decisions 5 and 6: lock-out, reset-link lifetime, reset
    only with mail), written each registration: a realm imported before them keeps its old settings
    across restarts (ADR-114 Amendment 5), so the file alone would never reach it."""
    status, current = _call(f"{issuer}/admin/realms/{realm}", token=token)
    if status != 200:
        raise RealmConfigurationFailed(f"reading the realm was refused: {status}")
    if all(current.get(key) == value for key, value in rules.items()):
        return "sign-in rules: already set"
    status, _body = _call(
        f"{issuer}/admin/realms/{realm}", token=token, data={**current, **rules}, method="PUT"
    )
    if status not in (200, 204):
        raise RealmConfigurationFailed(f"setting the realm's sign-in rules was refused: {status}")
    return "sign-in rules: set (five failures lock for 15 minutes; reset by email " + (
        "on)" if rules.get("resetPasswordAllowed") else "off: no mail is configured)"
    )


def ensure_unmanaged_attributes(*, issuer: str, realm: str, token: str) -> None:
    """Switch on custom user attributes. The policy lives in the realm's user profile, which is not
    part of `RealmRepresentation` and so cannot travel in the realm import. Without it Keycloak
    silently discards every custom attribute written to a user: no error, and the account signs in
    with no `roles`, no clearance, nothing."""
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


def ensure_realm_look(*, issuer: str, realm: str, token: str, theme: str, display_name: str) -> str:
    """Give a running realm its sign-in page's name and, if Keycloak can see it, its theme.

    The theme is named only when Keycloak lists it: a theme is mounted by compose, so a Keycloak
    started before it was written cannot see it, and naming a theme that is not there risks a
    sign-in page that will not render. Returns one plain sentence for the operator."""
    status, info = _call(f"{issuer}/admin/serverinfo", token=token)
    available = (
        {t.get("name") for t in info.get("themes", {}).get("login", [])}
        if status == 200 and isinstance(info, dict)
        else set()
    )
    status, current = _call(f"{issuer}/admin/realms/{realm}", token=token)
    if status != 200 or not isinstance(current, dict):
        raise RealmConfigurationFailed(f"could not read realm {realm!r}: {status}")
    wanted = {**current, "displayName": display_name}
    if theme in available:
        wanted["loginTheme"] = theme
    status, body = _call(f"{issuer}/admin/realms/{realm}", token=token, data=wanted, method="PUT")
    if status not in (200, 204):
        raise RealmConfigurationFailed(f"could not update realm {realm!r}: {status} {body}")
    if theme in available:
        return f"sign-in page: {display_name} look applied"
    return (
        f"sign-in page: named {display_name}, but Keycloak cannot see the {display_name} look yet. "
        "Run `python -m harness.apply` again (it writes the look and recreates the stack), then "
        "`make register-sign-in` once more"
    )


def ensure_user(*, issuer: str, realm: str, token: str, user: dict[str, Any]) -> str:
    """As `ensure_client`, for a subject. The subject is created without a password."""
    username = user["username"]
    status, found = _call(
        f"{issuer}/admin/realms/{realm}/users?username={username}&exact=true", token=token
    )
    if status == 200 and found:
        wanted = user.get("attributes") or {}
        stored = found[0].get("attributes") or {}
        # Present but without what the realm renders for it (created while custom attributes were
        # still off, or before a ruling widened its roles): put back what is missing. **Only what
        # is missing** (ADR-112): an attribute absent is restored, and a rendered role the account
        # lacks is added — but nothing the account holds is removed or replaced, so a role an
        # administrator added in the Admin area's People and roles survives `make refresh`. The
        # cost, on the disposable demo accounts only: a rendered role taken away is put back.
        merged = {**stored}
        for key, value in wanted.items():
            if key not in stored:
                merged[key] = value
            elif key == "roles":
                merged[key] = [*stored[key], *(v for v in value if v not in stored[key])]
        if merged != stored:
            status, body = _call(
                f"{issuer}/admin/realms/{realm}/users/{found[0]['id']}",
                token=token,
                data={**found[0], "attributes": merged},
                method="PUT",
            )
            if status not in (200, 204):
                raise RealmConfigurationFailed(f"could not repair {username!r}: {status} {body}")
            return "already there; attributes restored"
        return "already there"
    status, body = _call(f"{issuer}/admin/realms/{realm}/users", token=token, data=user)
    if status == 409:
        return "already there"
    if status not in (200, 201):
        raise RealmConfigurationFailed(f"could not create {username!r}: {status} {body}")
    return "created"


def withdraw_roles(*, issuer: str, realm: str, token: str, username: str, roles: list[str]) -> str:
    """Removes the named roles from an account's `roles` attribute and nothing else — the one way a
    role leaves a demo account, each use backed by a ruling (`harness.realm.WITHDRAWN_DEMO_ROLES`).
    An absent account or role is not an error: there is nothing to withdraw."""
    status, found = _call(
        f"{issuer}/admin/realms/{realm}/users?username={username}&exact=true", token=token
    )
    if status != 200 or not found:
        return "not present"
    stored = found[0].get("attributes") or {}
    held = list(stored.get("roles") or [])
    kept = [r for r in held if r not in roles]
    if kept == held:
        return "nothing to withdraw"
    status, body = _call(
        f"{issuer}/admin/realms/{realm}/users/{found[0]['id']}",
        token=token,
        data={**found[0], "attributes": {**stored, "roles": kept}},
        method="PUT",
    )
    if status not in (200, 204):
        raise RealmConfigurationFailed(
            f"could not withdraw roles from {username!r}: {status} {body}"
        )
    return f"withdrew {', '.join(r for r in held if r in roles)}"


def user_id(*, issuer: str, realm: str, token: str, username: str) -> str:
    """The subject Keycloak gives an account: the Conduit's principal id for it, which is what a case
    grant is written to. Raises, naming the account, when the realm has no such account (a Keycloak
    restart drops accounts created after its first start: `make register-sign-in` restores them)."""
    status, found = _call(
        f"{issuer}/admin/realms/{realm}/users?username={username}&exact=true", token=token
    )
    if status != 200 or not found:
        raise RealmConfigurationFailed(
            f"{username!r} is not in the realm; run `make register-sign-in` and try again"
        )
    return str(found[0]["id"])


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

    ensure_unmanaged_attributes(issuer=issuer, realm=realm, token=token)
    ensure_service_account_roles(issuer=issuer, realm=realm, token=token)


def ensure_service_account_roles(*, issuer: str, realm: str, token: str) -> str:
    """The Conduit's service account holds every role in `REQUIRED_ROLES`: granted at apply, and
    again by every `make refresh` (ADR-112 Amendment 1) — so a deployment made before a role was
    added (`manage-users`, `manage-clients` for the Admin area) gains it without being re-applied.
    Touches nothing but the account's realm-management role mappings."""
    from harness.realm import CONDUIT_CLIENT_ID

    status, conduit = _call(
        f"{issuer}/admin/realms/{realm}/clients?clientId={CONDUIT_CLIENT_ID}", token=token
    )
    if status != 200 or not conduit:
        raise RealmConfigurationFailed(f"client {CONDUIT_CLIENT_ID!r} not found")
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

    mapped_url = (
        f"{issuer}/admin/realms/{realm}/users/{service_account['id']}"
        f"/role-mappings/clients/{management_uuid}"
    )
    status, held = _call(mapped_url, token=token)
    held_names = (
        {role["name"] for role in held} if status == 200 and isinstance(held, list) else set()
    )
    lacking = [role for role in wanted if role["name"] not in held_names]
    if not lacking:
        return "the Conduit's account already holds its roles"
    status, _ = _call(mapped_url, token=token, data=lacking)
    if status not in (204, 201, 200):
        raise RealmConfigurationFailed(f"could not grant {REQUIRED_ROLES}: {status}")
    return "the Conduit's account granted " + ", ".join(sorted(r["name"] for r in lacking))


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
