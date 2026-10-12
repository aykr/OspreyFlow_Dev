"""A realm's people and dashboard identities, carried from one deployment to another **with their
ids** (`06_DECISIONS.md` ADR-114 Amendment 3). Every case grant, every `created_by` and every audit
row names a person by the identity provider's subject id, so a restore that re-created people under
new ids would lock them out of their own cases and orphan a dashboard's grants.

What a real Keycloak 26.0 does, measured on 12 October 2026 before this was written:

- A user's or client's id is unique across the whole server. A partial import naming an id or a
  username that already exists is refused 409, "Duplicate resource error".
- An imported user keeps its given id, attributes and role mappings.
- An imported client keeps its secret but gets a new internal id — which nothing outside Keycloak
  names, so it does not matter.
- A client's service account keeps its id **only** when it is imported as a user naming its client
  (`serviceAccountClientId`). That id is the subject of the dashboard's token and of its case
  grants, so it travels that way.

So the export takes every person, each dashboard client (`osprey-dashboard-*`) with its secret, and
each dashboard's service account; the import first removes what a fresh install made under the same
names — the install's own demo accounts and any same-named dashboard, which hold nothing yet — and
then imports. Passwords never travel: Keycloak does not give them out, and the install's own
registration sets the demo accounts' again. The install's own clients (the Glass, the token
exchange) are never carried: the new deployment's are the ones its secrets match.

The export holds client secrets, so whoever writes it to disk writes it readable by its owner only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from harness.keycloak_admin import _call

#: The clients the Admin area registers for business dashboards (ADR-111 Amendment 3, ADR-112).
DASHBOARD_PREFIX = "osprey-dashboard-"
FORMAT = 1
#: Fields Keycloak reports but will not take back, or that describe the old server only.
_NOT_IMPORTED = ("access", "createdTimestamp", "notBefore", "disableableCredentialTypes", "totp")

Call = Callable[..., tuple[int, Any]]


class IdentityFailed(RuntimeError):
    """Keycloak refused or could not be read; the message says which call, never a secret."""


def _get(call: Call, url: str, token: str, what: str) -> Any:
    status, body = call(url, token=token)
    if status != 200:
        raise IdentityFailed(f"reading {what} was refused by Keycloak ({status})")
    return body


def _person(call: Call, admin: str, token: str, record: dict[str, Any]) -> dict[str, Any]:
    person = {k: v for k, v in record.items() if k not in _NOT_IMPORTED}
    mappings = _get(call, f"{admin}/users/{record['id']}/role-mappings", token, "role mappings")
    person["realmRoles"] = sorted(r["name"] for r in mappings.get("realmMappings") or [])
    client_roles = {
        client: sorted(r["name"] for r in mapped.get("mappings") or [])
        for client, mapped in (mappings.get("clientMappings") or {}).items()
    }
    if client_roles:
        person["clientRoles"] = client_roles
    groups = _get(call, f"{admin}/users/{record['id']}/groups", token, "groups")
    if groups:
        person["groups"] = [g["path"] for g in groups]
    return person


def export_identity(*, issuer: str, realm: str, token: str, call: Call = _call) -> dict[str, Any]:
    """Every person in `realm` and every dashboard identity, with ids, roles and client secrets."""
    admin = f"{issuer}/admin/realms/{realm}"
    users = _get(call, f"{admin}/users?briefRepresentation=false&max=100000", token, "the people")
    people = [_person(call, admin, token, u) for u in users if not u.get("serviceAccountClientId")]
    dashboards: list[dict[str, Any]] = []
    for client in _get(call, f"{admin}/clients?max=100000", token, "the clients"):
        if not str(client.get("clientId", "")).startswith(DASHBOARD_PREFIX):
            continue
        secret = _get(
            call, f"{admin}/clients/{client['id']}/client-secret", token, "a dashboard's secret"
        )
        exported = {k: v for k, v in client.items() if k != "id"}
        exported["secret"] = secret["value"]
        dashboards.append(exported)
        account = _get(
            call, f"{admin}/clients/{client['id']}/service-account-user", token, "a service account"
        )
        full = _get(call, f"{admin}/users/{account['id']}", token, "a service account")
        person = _person(call, admin, token, full)
        person["serviceAccountClientId"] = client["clientId"]
        people.append(person)
    return {"format": FORMAT, "realm": realm, "people": people, "dashboards": dashboards}


def import_identity(
    *, issuer: str, realm: str, token: str, identity: dict[str, Any], call: Call = _call
) -> dict[str, int]:
    """Bring `identity` into `realm`, replacing what a fresh install made under the same names."""
    if identity.get("format") != FORMAT:
        raise IdentityFailed(
            f"this identity file is format {identity.get('format')!r}, not {FORMAT}"
        )
    if identity.get("realm") != realm:
        raise IdentityFailed(
            f"this identity is the realm {identity.get('realm')!r}'s, not {realm!r}'s"
        )
    admin = f"{issuer}/admin/realms/{realm}"
    replaced = 0
    names = {d["clientId"] for d in identity["dashboards"]}
    for client in _get(call, f"{admin}/clients?max=100000", token, "the clients"):
        if client.get("clientId") in names:
            call(f"{admin}/clients/{client['id']}", token=token, method="DELETE")
            replaced += 1
    for person in identity["people"]:
        if person.get("serviceAccountClientId"):
            continue  # its client was removed above, and its account with it
        existing = _get(
            call, f"{admin}/users?username={person['username']}&exact=true", token, "a person"
        )
        for other in existing:
            if other["id"] != person["id"]:
                call(f"{admin}/users/{other['id']}", token=token, method="DELETE")
                replaced += 1
    status, body = call(
        f"{admin}/partialImport",
        token=token,
        data={
            "ifResourceExists": "FAIL",
            "users": identity["people"],
            "clients": identity["dashboards"],
        },
    )
    if status != 200:
        said = body.get("errorMessage") if isinstance(body, dict) else ""
        raise IdentityFailed(f"Keycloak refused the import ({status}): {said or 'no reason given'}")
    return {
        "people": len(identity["people"]),
        "dashboards": len(identity["dashboards"]),
        "replaced": replaced,
    }
