"""`IdentityAdmin` — the Admin area's calls to the identity provider (`06_DECISIONS.md` ADR-112
Amendment 1): people's roles, and dashboard identities.

The fixture is a small stateful Keycloak admin API that models the provider's **refusals**, not only
its grants (`process/CLAUDE.md` rule 15): no bearer, or another bearer, is 401; an unknown user or
client is 404; a second client of one `clientId` is 409. Two narrowings are the Conduit's own and are
proved to refuse before any call: a role outside the known set, and a client not named
`osprey-dashboard-*`.
"""

from __future__ import annotations

import dataclasses
import json
import threading
import uuid
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from services.api.identity_admin import (
    DashboardExistsError,
    IdentityAdmin,
    IdentityAdminRefused,
    UnknownRoleError,
)

from principal_auth import OidcResolverSettings

CLIENT_ID, CLIENT_SECRET, BEARER = "osprey-conduit", "conduit-secret", "fixture-issued-token"


class _Realm:
    def __init__(self) -> None:
        self.users: dict[str, dict[str, object]] = {
            "u-analyst": {"id": "u-analyst", "username": "osprey-demo-analyst", "firstName": "Demo",
                          "lastName": "Analyst", "enabled": True,
                          "attributes": {"roles": ["analyst"], "clearance": ["OFFICIAL"], "org_unit": ["verify"]}},
            "u-sa": {"id": "u-sa", "username": "service-account-osprey-conduit", "enabled": True, "attributes": {}},
        }  # fmt: skip
        self.clients: dict[str, dict[str, object]] = {}
        self.calls: list[str] = []


def _handler(realm: _Realm) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

        def _send(self, status: int, payload: object = None, headers: dict[str, str] | None = None) -> None:
            body = b"" if payload is None else json.dumps(payload).encode()
            self.send_response(status)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> object:
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode()
            return json.loads(raw) if raw.startswith(("{", "[")) else raw

        def _authorised(self) -> bool:
            if self.headers.get("Authorization") != f"Bearer {BEARER}":
                self._send(401, {"error": "HTTP 401 Unauthorized"})
                return False
            return True

        def do_POST(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            if url.path.endswith("/token"):
                body = str(self._body())
                if f"client_id={CLIENT_ID}" in body and f"client_secret={CLIENT_SECRET}" in body:
                    return self._send(200, {"access_token": BEARER})
                return self._send(401, {"error": "invalid_client"})
            if not self._authorised():
                return
            realm.calls.append(f"POST {url.path}")
            if url.path.endswith("/clients"):
                client = self._body()
                assert isinstance(client, dict)
                if any(c["clientId"] == client["clientId"] for c in realm.clients.values()):
                    return self._send(409, {"errorMessage": "Client already exists"})
                cid = str(uuid.uuid4())
                sa = f"sa-{cid}"
                realm.users[sa] = {"id": sa, "username": f"service-account-{client['clientId']}",
                                   "enabled": True, "attributes": {}}  # fmt: skip
                realm.clients[cid] = {**client, "id": cid, "secret": f"secret-{cid}", "_sa": sa}
                return self._send(201, None, {"Location": f"/clients/{cid}"})
            self._send(404, {"error": "not found"})

        def do_GET(self) -> None:  # noqa: N802
            if not self._authorised():
                return
            url = urlparse(self.path)
            parts = url.path.split("/")
            realm.calls.append(f"GET {url.path}")
            if url.path.endswith("/users"):
                return self._send(200, list(realm.users.values()))
            if "users" in parts:
                user = realm.users.get(parts[-1])
                return self._send(200, user) if user else self._send(404, {"error": "User not found"})
            if url.path.endswith("/clients"):
                wanted = parse_qs(url.query).get("clientId", [""])[0]
                found = [c for c in realm.clients.values() if wanted in str(c["clientId"])]
                return self._send(200, [{k: v for k, v in c.items() if k not in ("secret", "_sa")} for c in found])
            if parts[-1] == "client-secret":
                client = realm.clients.get(parts[-2])
                return self._send(200, {"value": client["secret"]}) if client else self._send(404, {})
            if parts[-1] == "service-account-user":
                client = realm.clients.get(parts[-2])
                return self._send(200, realm.users[str(client["_sa"])]) if client else self._send(404, {})
            self._send(404, {"error": "not found"})

        def do_PUT(self) -> None:  # noqa: N802
            if not self._authorised():
                return
            parts = urlparse(self.path).path.split("/")
            realm.calls.append(f"PUT {self.path}")
            user = realm.users.get(parts[-1])
            if "users" not in parts or user is None:
                return self._send(404, {"error": "User not found"})
            body = self._body()
            assert isinstance(body, dict)
            user.update(body)
            self._send(204)

        def do_DELETE(self) -> None:  # noqa: N802
            if not self._authorised():
                return
            parts = urlparse(self.path).path.split("/")
            realm.calls.append(f"DELETE {self.path}")
            client = realm.clients.pop(parts[-1], None)
            if client is None:
                return self._send(404, {"error": "Could not find client"})
            realm.users.pop(str(client["_sa"]), None)
            self._send(204)

    return Handler


@pytest.fixture
def idp() -> Iterator[tuple[IdentityAdmin, _Realm]]:
    realm = _Realm()
    server = HTTPServer(("127.0.0.1", 0), _handler(realm))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    settings = OidcResolverSettings(
        oidc_jwks_url=f"{base}/certs", oidc_issuer=base, oidc_audience="osprey-conduit",
        oidc_token_exchange_url=f"{base}/token", oidc_token_exchange_client_id=CLIENT_ID,
        oidc_token_exchange_client_secret=CLIENT_SECRET,
        oidc_admin_users_url=f"{base}/admin/realms/osprey/users",
    )  # fmt: skip
    yield IdentityAdmin(settings), realm
    server.shutdown()


async def test_people_are_listed_without_service_accounts(idp: tuple[IdentityAdmin, _Realm]) -> None:
    admin, _ = idp
    (person,) = await admin.list_people()
    assert (person.username, person.name, person.roles, person.clearance, person.org_unit) == (
        "osprey-demo-analyst", "Demo Analyst", ["analyst"], "OFFICIAL", "verify")  # fmt: skip
    await admin.aclose()


async def test_setting_roles_writes_only_the_roles_attribute(idp: tuple[IdentityAdmin, _Realm]) -> None:
    admin, realm = idp
    person = await admin.set_roles("u-analyst", ["analyst", "data_engineer", "right:read_export_ledger"])
    assert person.roles == ["analyst", "data_engineer", "right:read_export_ledger"]
    attributes = realm.users["u-analyst"]["attributes"]
    assert attributes == {"roles": ["analyst", "data_engineer", "right:read_export_ledger"],  # type: ignore[comparison-overlap]
                          "clearance": ["OFFICIAL"], "org_unit": ["verify"]}  # fmt: skip
    await admin.aclose()


async def test_an_unknown_role_is_refused_before_any_call(idp: tuple[IdentityAdmin, _Realm]) -> None:
    admin, realm = idp
    with pytest.raises(UnknownRoleError):
        await admin.set_roles("u-analyst", ["analyst", "realm-admin"])
    assert not [c for c in realm.calls if c.startswith("PUT")]
    await admin.aclose()


async def test_a_dashboard_identity_is_registered_listed_and_removed(idp: tuple[IdentityAdmin, _Realm]) -> None:
    admin, realm = idp
    made = await admin.create_dashboard("Compliance board", clearance="OFFICIAL", org_unit="verify")
    assert made.dashboard.client_id == "osprey-dashboard-compliance-board"
    assert made.secret.startswith("secret-"), "the secret is handed over once, at registration"
    client = next(iter(realm.clients.values()))
    mappers = {m["name"] for m in client["protocolMappers"]}  # type: ignore[union-attr, index]
    assert {"clearance", "org_unit", "roles", "receivable_handling_codes", "audience-conduit"} <= mappers
    assert client["serviceAccountsEnabled"] is True and client["publicClient"] is False
    sa = realm.users[str(client["_sa"])]
    assert sa["attributes"]["roles"] == ["reports_viewer"]  # type: ignore[index]
    (listed,) = await admin.list_dashboards()
    assert (listed.client_id, listed.account_id, listed.clearance) == (made.dashboard.client_id, client["_sa"], "OFFICIAL")
    with pytest.raises(DashboardExistsError):
        await admin.create_dashboard("Compliance board", clearance="OFFICIAL", org_unit="verify")
    await admin.delete_dashboard("osprey-dashboard-compliance-board")
    assert realm.clients == {} and await admin.list_dashboards() == []
    await admin.aclose()


async def test_only_a_dashboard_client_can_be_removed(idp: tuple[IdentityAdmin, _Realm]) -> None:
    admin, realm = idp
    with pytest.raises(UnknownRoleError):
        await admin.delete_dashboard("osprey-conduit")
    assert not [c for c in realm.calls if c.startswith("DELETE")]
    await admin.aclose()


async def test_a_refused_token_is_said_not_swallowed(idp: tuple[IdentityAdmin, _Realm]) -> None:
    admin, _ = idp
    admin._settings = dataclasses.replace(admin._settings, oidc_token_exchange_client_secret="wrong")  # type: ignore[type-var]  # noqa: SLF001
    with pytest.raises(IdentityAdminRefused):
        await admin.list_people()
    await admin.aclose()
