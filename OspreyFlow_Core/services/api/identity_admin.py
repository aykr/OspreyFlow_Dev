"""The Admin area's calls to the identity provider (`06_DECISIONS.md` ADR-112 Amendment 1): people's
roles, and dashboard identities (ADR-111 decision 7).

**Through the Conduit's own service account,** bearing the ADR-043 client-credentials token, so
every change passes the Conduit's right check and audit; the account needs `manage-users` and
`manage-clients`. **Narrowed here, before any call:** a person's `roles` attribute may hold only the
four roles of ADR-112, single `right:<name>` grants and the old role names — nothing else, so this
can never hand out realm administration — and only a client named `osprey-dashboard-*` is ever
created or removed.

**A dashboard identity** is a confidential client with a service account and no browser flow: its
token carries the principal claims (clearance, unit, roles — `reports_viewer` — handling codes) from
the service account's attributes, and the Conduit's audience. Its secret is handed over once, at
registration, and never stored by OspreyFlow. Case access is ADR-052's: a case Author grants the
identity's account Viewer, as for a person.
"""

from __future__ import annotations

import re
import secrets
from typing import Any

import httpx

from principal_auth import OidcSettings
from schemas.admin import (
    AccessInput,
    DashboardIdentity,
    InviteInput,
    PersonAccount,
    RegisteredDashboard,
    SignInDelivery,
)
from schemas.rights import LEGACY_ROLE_RIGHTS, ROLE_RIGHTS, SINGLE_RIGHT_PREFIX, Right

DASHBOARD_PREFIX = "osprey-dashboard-"
_RIGHT_VALUES = {r.value for r in Right}
#: The claims a principal is built from (`harness/realm.py::PRINCIPAL_CLAIMS`), mapped from user
#: attributes; kept in step with it by `test_identity_admin.py`'s mapper case.
_PRINCIPAL_CLAIMS = (("clearance", False), ("org_unit", False),
                     ("receivable_handling_codes", True), ("roles", True))  # fmt: skip


class IdentityAdminRefused(Exception):
    """The identity provider refused or could not be reached; said in words, never swallowed."""


class UnknownRoleError(ValueError):
    """A role outside the known set, or a client that is not a dashboard's — refused before any
    call to the identity provider."""


class DashboardExistsError(Exception):
    pass


class PersonExistsError(Exception):
    """The sign-in name or the email address is already held (the identity provider's 409)."""


#: The one-time code's letters: no 0/O or 1/I, so it can be read out and typed without a slip.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def one_time_code() -> str:
    """Sixteen letters in four groups — 80 bits. Keycloak applies no password policy of its own
    (measured: a one-letter password was accepted), so the strength is this code's."""
    letters = "".join(secrets.choice(CODE_ALPHABET) for _ in range(16))
    return "-".join(letters[i : i + 4] for i in range(0, 16, 4))


def allowed_role(role: str) -> bool:
    if role in ROLE_RIGHTS or role in LEGACY_ROLE_RIGHTS:
        return True
    return (
        role.startswith(SINGLE_RIGHT_PREFIX) and role[len(SINGLE_RIGHT_PREFIX) :] in _RIGHT_VALUES
    )


def _first(attributes: dict[str, Any], key: str) -> str | None:
    values = attributes.get(key) or []
    return str(values[0]) if values else None


def _person(user: dict[str, Any]) -> PersonAccount:
    attributes = user.get("attributes") or {}
    name = " ".join(str(user.get(k) or "").strip() for k in ("firstName", "lastName")).strip()
    return PersonAccount(
        id=str(user["id"]),
        username=str(user.get("username", "")),
        name=name or str(user.get("username", "")),
        enabled=bool(user.get("enabled", True)),
        roles=[str(r) for r in attributes.get("roles") or []],
        clearance=_first(attributes, "clearance"),
        org_unit=_first(attributes, "org_unit"),
        email=user.get("email") or None,
        receivable_handling_codes=[
            str(c) for c in attributes.get("receivable_handling_codes") or []
        ],
        must_set_password="UPDATE_PASSWORD" in (user.get("requiredActions") or []),
    )


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise UnknownRoleError("a dashboard needs a name of letters or digits")
    return slug[:48]


class IdentityAdmin:
    """One per process, beside the `PrincipalResolver`; closed with it."""

    def __init__(self, settings: OidcSettings, *, by_email: bool = False) -> None:
        self._settings = settings
        self._http = httpx.AsyncClient(timeout=10.0)
        #: ADR-114 Amendment 5: the deployment has a mail server, so a person with an address is
        #: signed in by the identity provider's own emailed link; anyone else by a one-time code.
        self._by_email = by_email

    async def aclose(self) -> None:
        await self._http.aclose()

    @property
    def _realm(self) -> str:
        users = self._settings.oidc_admin_users_url or ""
        if not users.endswith("/users"):
            raise IdentityAdminRefused("this deployment has no identity-provider admin address")
        return users[: -len("/users")]

    async def _token(self) -> str:
        try:
            response = await self._http.post(
                self._settings.oidc_token_exchange_url or "",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._settings.oidc_token_exchange_client_id,
                    "client_secret": self._settings.oidc_token_exchange_client_secret,
                },
            )
        except httpx.HTTPError as e:
            raise IdentityAdminRefused(f"the identity provider could not be reached: {e}") from e
        if response.status_code != 200:
            raise IdentityAdminRefused("the identity provider refused the Conduit's credentials")
        return str(response.json()["access_token"])

    async def _call(
        self, method: str, path: str, *, json: Any = None, params: Any = None
    ) -> httpx.Response:
        token = await self._token()
        try:
            response = await self._http.request(
                method, f"{self._realm}{path}", json=json, params=params,
                headers={"Authorization": f"Bearer {token}"},
            )  # fmt: skip
        except httpx.HTTPError as e:
            raise IdentityAdminRefused(f"the identity provider could not be reached: {e}") from e
        if response.status_code in (401, 403):
            raise IdentityAdminRefused(
                "the identity provider refused the Conduit — its account needs manage-users and "
                "manage-clients"
            )
        return response

    async def reachable(self) -> None:
        """Raises `IdentityAdminRefused` unless the identity provider grants the Conduit a token."""
        await self._token()

    # --- people -------------------------------------------------------------------------------

    async def list_people(self) -> list[PersonAccount]:
        response = await self._call(
            "GET", "/users", params={"max": 500, "briefRepresentation": "false"}
        )
        users = response.json()
        people = [
            _person(u)
            for u in users
            if not str(u.get("username", "")).startswith("service-account-")
        ]
        return sorted(people, key=lambda p: p.username)

    async def set_roles(self, user_id: str, roles: list[str]) -> PersonAccount:
        refused = [r for r in roles if not allowed_role(r)]
        if refused:
            raise UnknownRoleError(
                f"not a role or right this deployment grants: {', '.join(refused)}"
            )
        found = await self._call("GET", f"/users/{user_id}")
        if found.status_code == 404:
            raise IdentityAdminRefused("no such person")
        user = found.json()
        attributes = {**(user.get("attributes") or {}), "roles": list(dict.fromkeys(roles))}
        written = await self._call(
            "PUT", f"/users/{user_id}", json={**user, "attributes": attributes}
        )
        if written.status_code not in (200, 204):
            raise IdentityAdminRefused(
                f"the identity provider did not save the roles ({written.status_code})"
            )
        return _person({**user, "attributes": attributes})

    # --- invite, access, disable, enable, reset sign-in (ADR-114 Amendment 5) ------------------

    async def _user(self, user_id: str) -> dict[str, Any]:
        found = await self._call("GET", f"/users/{user_id}")
        user = found.json() if found.status_code == 200 else None
        if not user or str(user.get("username", "")).startswith("service-account-"):
            raise IdentityAdminRefused("no such person")
        return dict(user)

    def _emailed(self, email: str | None) -> bool:
        return self._by_email and bool(email)

    async def _put_user(self, user: dict[str, Any], what: str) -> None:
        # Measured: a PUT replaces each key it names — `attributes` whole — so the person is always
        # written back entire, read first.
        written = await self._call("PUT", f"/users/{user['id']}", json=user)
        if written.status_code not in (200, 204):
            raise IdentityAdminRefused(
                f"the identity provider did not save the {what} ({written.status_code})"
            )

    async def _send_set_password_email(self, user_id: str) -> None:
        sent = await self._call(
            "PUT", f"/users/{user_id}/execute-actions-email", json=["UPDATE_PASSWORD"]
        )
        if sent.status_code not in (200, 204):
            detail = sent.json().get("errorMessage", "") if sent.content else ""
            said = f"the sign-in email could not be sent: {detail}"
            raise IdentityAdminRefused(said.rstrip(": "))

    async def invite(self, invite: InviteInput) -> SignInDelivery:
        refused = [r for r in invite.roles if not allowed_role(r)]
        if refused:
            raise UnknownRoleError(
                f"not a role or right this deployment grants: {', '.join(refused)}"
            )
        attributes = {
            "clearance": [invite.clearance],
            "org_unit": [invite.org_unit],
            "receivable_handling_codes": list(dict.fromkeys(invite.receivable_handling_codes)),
            "roles": list(dict.fromkeys(invite.roles)),
        }
        user: dict[str, Any] = {
            "username": invite.username,
            "firstName": invite.first_name,
            "lastName": invite.last_name,
            "enabled": True,
            "emailVerified": False,
            "attributes": attributes,
            "requiredActions": ["UPDATE_PASSWORD"],
        }
        if invite.email:
            user["email"] = invite.email
        emailed = self._emailed(invite.email)
        code = None if emailed else one_time_code()
        if code is not None:
            user["credentials"] = [{"type": "password", "value": code, "temporary": True}]
        created = await self._call("POST", "/users", json=user)
        if created.status_code == 409:
            raise PersonExistsError(invite.username)
        if created.status_code == 400:
            raise UnknownRoleError(f"the identity provider refused the person: {created.text}")
        if created.status_code != 201:
            raise IdentityAdminRefused(
                f"the identity provider did not create the person ({created.status_code})"
            )
        user_id = created.headers.get("Location", "").rstrip("/").rsplit("/", 1)[-1]
        if emailed:
            try:
                await self._send_set_password_email(user_id)
            except IdentityAdminRefused:
                # No half-made account: the administrator can invite again once mail works.
                await self._call("DELETE", f"/users/{user_id}")
                raise
        user.pop("credentials", None)
        person = _person({**user, "id": user_id})
        return SignInDelivery(
            person=person, delivery="email" if emailed else "one_time_code", one_time_code=code
        )

    async def set_access(self, user_id: str, access: AccessInput) -> PersonAccount:
        user = await self._user(user_id)
        attributes = {
            **(user.get("attributes") or {}),
            "clearance": [access.clearance],
            "org_unit": [access.org_unit],
            "receivable_handling_codes": list(dict.fromkeys(access.receivable_handling_codes)),
        }
        user = {**user, "attributes": attributes}
        await self._put_user(user, "access")
        return _person(user)

    async def set_enabled(self, user_id: str, enabled: bool) -> PersonAccount:
        user = {**await self._user(user_id), "enabled": enabled}
        await self._put_user(user, "account")
        if not enabled:
            # Sessions already open end now, not when their tokens lapse.
            await self._call("POST", f"/users/{user_id}/logout")
        return _person(user)

    async def reset_sign_in(self, user_id: str) -> SignInDelivery:
        user = await self._user(user_id)
        actions = list(dict.fromkeys([*(user.get("requiredActions") or []), "UPDATE_PASSWORD"]))
        user = {**user, "requiredActions": actions}
        emailed = self._emailed(user.get("email"))
        code = None if emailed else one_time_code()
        if code is not None:
            reset = await self._call(
                "PUT", f"/users/{user_id}/reset-password",
                json={"type": "password", "value": code, "temporary": True},
            )  # fmt: skip
            if reset.status_code not in (200, 204):
                raise IdentityAdminRefused(
                    f"the identity provider did not reset the sign-in ({reset.status_code})"
                )
        await self._put_user(user, "sign-in")
        if emailed:
            await self._send_set_password_email(user_id)
        await self._call("POST", f"/users/{user_id}/logout")
        return SignInDelivery(
            person=_person(user), delivery="email" if emailed else "one_time_code",
            one_time_code=code,
        )  # fmt: skip

    # --- dashboards ---------------------------------------------------------------------------

    def _client(self, client_id: str, audience: str) -> dict[str, Any]:
        mappers = [
            {
                "name": claim, "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-attribute-mapper",
                "config": {"user.attribute": claim, "claim.name": claim, "jsonType.label": "String",
                           "multivalued": "true" if many else "false",
                           "access.token.claim": "true", "id.token.claim": "false"},
            }
            for claim, many in _PRINCIPAL_CLAIMS
        ] + [{
            "name": "audience-conduit", "protocol": "openid-connect",
            "protocolMapper": "oidc-audience-mapper",
            "config": {"included.custom.audience": audience, "access.token.claim": "true",
                       "id.token.claim": "false"},
        }]  # fmt: skip
        return {
            "clientId": client_id, "protocol": "openid-connect", "publicClient": False,
            "serviceAccountsEnabled": True, "standardFlowEnabled": False,
            "directAccessGrantsEnabled": False, "implicitFlowEnabled": False,
            "protocolMappers": mappers,
        }  # fmt: skip

    async def _uuid(self, client_id: str) -> str | None:
        found = (await self._call("GET", "/clients", params={"clientId": client_id})).json()
        exact = [c for c in found if c.get("clientId") == client_id]
        return str(exact[0]["id"]) if exact else None

    async def _identity(self, client: dict[str, Any]) -> DashboardIdentity:
        account = (await self._call("GET", f"/clients/{client['id']}/service-account-user")).json()
        attributes = account.get("attributes") or {}
        return DashboardIdentity(
            client_id=str(client["clientId"]), account_id=str(account["id"]),
            clearance=_first(attributes, "clearance"), org_unit=_first(attributes, "org_unit"),
            receivable_handling_codes=[
                str(c) for c in attributes.get("receivable_handling_codes") or []
            ],
        )  # fmt: skip

    async def list_dashboards(self) -> list[DashboardIdentity]:
        found = (
            await self._call(
                "GET", "/clients", params={"clientId": DASHBOARD_PREFIX, "search": "true"}
            )
        ).json()
        return [
            await self._identity(c)
            for c in found
            if str(c.get("clientId", "")).startswith(DASHBOARD_PREFIX)
        ]

    async def create_dashboard(
        self, name: str, *, clearance: str, org_unit: str
    ) -> RegisteredDashboard:
        client_id = f"{DASHBOARD_PREFIX}{_slug(name)}"
        made = await self._call(
            "POST",
            "/clients",
            json=self._client(client_id, self._settings.oidc_audience or "osprey-conduit"),
        )
        if made.status_code == 409:
            raise DashboardExistsError(client_id)
        if made.status_code != 201:
            raise IdentityAdminRefused(
                f"the identity provider did not register the dashboard ({made.status_code})"
            )
        uuid = await self._uuid(client_id)
        if uuid is None:
            raise IdentityAdminRefused("the dashboard was registered but cannot be found")
        secret = str((await self._call("GET", f"/clients/{uuid}/client-secret")).json()["value"])
        account = (await self._call("GET", f"/clients/{uuid}/service-account-user")).json()
        attributes = {**(account.get("attributes") or {}), "clearance": [clearance],
                      "org_unit": [org_unit], "roles": ["reports_viewer"],
                      "receivable_handling_codes": ["P"]}  # fmt: skip
        await self._call(
            "PUT", f"/users/{account['id']}", json={**account, "attributes": attributes}
        )
        return RegisteredDashboard(
            dashboard=DashboardIdentity(client_id=client_id, account_id=str(account["id"]),
                                        clearance=clearance, org_unit=org_unit),
            secret=secret,
        )  # fmt: skip

    async def delete_dashboard(self, client_id: str) -> None:
        if not client_id.startswith(DASHBOARD_PREFIX):
            raise UnknownRoleError(f"{client_id} is not a dashboard identity")
        uuid = await self._uuid(client_id)
        if uuid is None:
            raise IdentityAdminRefused("no such dashboard")
        await self._call("DELETE", f"/clients/{uuid}")


__all__ = [
    "DashboardExistsError", "DashboardIdentity", "IdentityAdmin", "IdentityAdminRefused",
    "PersonAccount", "RegisteredDashboard", "UnknownRoleError", "allowed_role",
]  # fmt: skip
