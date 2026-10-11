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
from typing import Any

import httpx

from principal_auth import OidcSettings
from schemas.admin import DashboardIdentity, PersonAccount, RegisteredDashboard
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
    )


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise UnknownRoleError("a dashboard needs a name of letters or digits")
    return slug[:48]


class IdentityAdmin:
    """One per process, beside the `PrincipalResolver`; closed with it."""

    def __init__(self, settings: OidcSettings) -> None:
        self._settings = settings
        self._http = httpx.AsyncClient(timeout=10.0)

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
