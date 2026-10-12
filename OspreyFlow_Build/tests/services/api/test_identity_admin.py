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
    CODE_ALPHABET,
    DashboardExistsError,
    PersonExistsError,
    IdentityAdmin,
    IdentityAdminRefused,
    UnknownRoleError,
)

from principal_auth import OidcResolverSettings
from schemas.admin import AccessInput, InviteInput

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
        # ADR-114 Amendment 5, measured on Keycloak 26.0.8: with no mail server the realm refuses
        # an actions email (500, "No sender address configured"); with one it sends it.
        self.mail = False
        self.emails: list[tuple[str, list[str]]] = []
        self.passwords: dict[str, tuple[str, bool]] = {}
        self.logged_out: list[str] = []


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
            if url.path.endswith("/users"):
                user = self._body()
                assert isinstance(user, dict)
                name = str(user.get("username", ""))
                if not name or any(ch in name for ch in " !@#$%^&*()"):
                    return self._send(400, {"field": "username", "errorMessage": "error-username-invalid-character"})
                taken = {str(u["username"]) for u in realm.users.values()}
                emails = {str(u.get("email")) for u in realm.users.values() if u.get("email")}
                if name in taken or (user.get("email") and user["email"] in emails):
                    return self._send(409, {"errorMessage": "User exists with same email"})
                uid = f"u-{uuid.uuid4()}"
                for credential in user.pop("credentials", []) or []:
                    realm.passwords[uid] = (credential["value"], bool(credential.get("temporary")))
                realm.users[uid] = {**user, "id": uid}
                return self._send(201, None, {"Location": f"/users/{uid}"})
            if url.path.endswith("/logout"):
                parts = url.path.split("/")
                if parts[-2] not in realm.users:
                    return self._send(404, {"error": "User not found"})
                realm.logged_out.append(parts[-2])
                return self._send(204)
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
                wanted = parse_qs(url.query).get("username", [None])[0]
                users = list(realm.users.values())
                if wanted is not None:
                    users = [u for u in users if u["username"] == wanted]
                return self._send(200, users)
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
            if parts[-1] in ("reset-password", "execute-actions-email"):
                if parts[-2] not in realm.users:
                    return self._send(404, {"error": "User not found"})
                body = self._body()
                if parts[-1] == "reset-password":
                    assert isinstance(body, dict)
                    realm.passwords[parts[-2]] = (str(body["value"]), bool(body.get("temporary")))
                    return self._send(204)
                if not realm.mail:
                    return self._send(500, {"errorMessage": "Failed to send execute actions email: "
                                            "No sender address configured in the realm settings for emails"})  # fmt: skip
                assert isinstance(body, list)
                realm.emails.append((parts[-2], [str(a) for a in body]))
                return self._send(204)
            user = realm.users.get(parts[-1])
            if "users" not in parts or user is None:
                return self._send(404, {"error": "User not found"})
            body = self._body()
            assert isinstance(body, dict)
            # Measured: a PUT replaces each key it names — `attributes` whole, not merged.
            user.update(body)
            self._send(204)

        def do_DELETE(self) -> None:  # noqa: N802
            if not self._authorised():
                return
            parts = urlparse(self.path).path.split("/")
            realm.calls.append(f"DELETE {self.path}")
            if "users" in parts:
                return self._send(204) if realm.users.pop(parts[-1], None) else self._send(404, {})
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


@pytest.fixture
def idp_by_email(idp: tuple[IdentityAdmin, _Realm]) -> tuple[IdentityAdmin, _Realm]:
    admin, realm = idp
    return IdentityAdmin(admin._settings, by_email=True), realm


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



# --- ADR-114 Amendment 5 (stage B4b): invite, access, disable, enable, reset sign-in ---------------

INVITE = InviteInput(username="new.person", first_name="New", last_name="Person", email="new@example.org",
                     clearance="OFFICIAL", org_unit="verify", receivable_handling_codes=["P"],
                     roles=["analyst"])  # fmt: skip


async def test_an_invitation_without_email_hands_over_a_one_time_code_once(idp: tuple[IdentityAdmin, _Realm]) -> None:
    admin, realm = idp
    made = await admin.invite(INVITE)
    assert made.delivery == "one_time_code" and made.one_time_code
    code = made.one_time_code
    assert len(code.replace("-", "")) >= 16 and set(code.replace("-", "")) <= set(CODE_ALPHABET)
    stored = next(u for u in realm.users.values() if u["username"] == "new.person")
    assert realm.passwords[str(stored["id"])] == (code, True), "temporary: changed at first sign-in"
    assert stored["requiredActions"] == ["UPDATE_PASSWORD"] and stored["enabled"] is True
    assert stored["attributes"] == {"clearance": ["OFFICIAL"], "org_unit": ["verify"],
                                    "receivable_handling_codes": ["P"], "roles": ["analyst"]}  # fmt: skip
    assert (made.person.username, made.person.must_set_password) == ("new.person", True)
    assert (await admin.invite(INVITE.model_copy(update={"username": "second", "email": None}))).one_time_code != code
    await admin.aclose()


async def test_an_invitation_by_email_sends_the_identity_providers_own_link(idp_by_email: tuple[IdentityAdmin, _Realm]) -> None:
    admin, realm = idp_by_email
    realm.mail = True
    made = await admin.invite(INVITE)
    assert (made.delivery, made.one_time_code) == ("email", None)
    stored = next(u for u in realm.users.values() if u["username"] == "new.person")
    assert realm.emails == [(stored["id"], ["UPDATE_PASSWORD"])]
    assert str(stored["id"]) not in realm.passwords, "no password at all until the person sets one"
    await admin.aclose()


async def test_an_email_that_cannot_be_sent_leaves_no_half_made_account(idp_by_email: tuple[IdentityAdmin, _Realm]) -> None:
    admin, realm = idp_by_email
    with pytest.raises(IdentityAdminRefused, match="email"):
        await admin.invite(INVITE)
    assert not [u for u in realm.users.values() if u["username"] == "new.person"]
    await admin.aclose()


async def test_a_name_or_email_already_held_is_said_as_such(idp: tuple[IdentityAdmin, _Realm]) -> None:
    admin, _ = idp
    await admin.invite(INVITE)
    with pytest.raises(PersonExistsError):
        await admin.invite(INVITE)
    with pytest.raises(PersonExistsError):
        await admin.invite(INVITE.model_copy(update={"username": "someone.else"}))
    await admin.aclose()


async def test_a_role_outside_the_known_set_is_refused_before_any_account_is_made(idp: tuple[IdentityAdmin, _Realm]) -> None:
    admin, realm = idp
    with pytest.raises(UnknownRoleError):
        await admin.invite(INVITE.model_copy(update={"roles": ["realm-admin"]}))
    assert not [c for c in realm.calls if c.startswith("POST") and c.endswith("/users")]
    await admin.aclose()


async def test_setting_access_keeps_everything_else_the_person_holds(idp: tuple[IdentityAdmin, _Realm]) -> None:
    """Measured on Keycloak 26.0.8: a PUT naming `attributes` replaces them whole — setting
    clearance alone wiped the unit and the roles."""
    admin, realm = idp
    person = await admin.set_access("u-analyst", AccessInput(clearance="SECRET", org_unit="intel",
                                                             receivable_handling_codes=["P", "C"]))  # fmt: skip
    assert (person.clearance, person.org_unit, person.roles) == ("SECRET", "intel", ["analyst"])
    assert realm.users["u-analyst"]["attributes"] == {"roles": ["analyst"], "clearance": ["SECRET"],  # type: ignore[comparison-overlap]
                                                      "org_unit": ["intel"], "receivable_handling_codes": ["P", "C"]}  # fmt: skip
    assert realm.users["u-analyst"]["username"] == "osprey-demo-analyst"
    await admin.aclose()


async def test_disabling_ends_the_persons_sessions_and_enabling_brings_them_back(idp: tuple[IdentityAdmin, _Realm]) -> None:
    admin, realm = idp
    off = await admin.set_enabled("u-analyst", False)
    assert off.enabled is False and realm.users["u-analyst"]["enabled"] is False
    assert realm.logged_out == ["u-analyst"]
    assert realm.users["u-analyst"]["attributes"]["roles"] == ["analyst"]  # type: ignore[index]
    on = await admin.set_enabled("u-analyst", True)
    assert on.enabled is True and realm.users["u-analyst"]["enabled"] is True
    await admin.aclose()


async def test_resetting_sign_in_ends_sessions_and_hands_over_a_new_code(idp: tuple[IdentityAdmin, _Realm]) -> None:
    admin, realm = idp
    reset = await admin.reset_sign_in("u-analyst")
    assert reset.delivery == "one_time_code" and reset.one_time_code
    assert realm.passwords["u-analyst"] == (reset.one_time_code, True)
    assert realm.users["u-analyst"]["requiredActions"] == ["UPDATE_PASSWORD"]
    assert realm.logged_out == ["u-analyst"]
    await admin.aclose()


async def test_a_service_account_is_no_person_to_manage(idp: tuple[IdentityAdmin, _Realm]) -> None:
    admin, realm = idp
    for act in (admin.set_enabled("u-sa", False), admin.reset_sign_in("u-sa"),
                admin.set_access("u-sa", AccessInput(clearance="OFFICIAL", org_unit="x", receivable_handling_codes=[]))):  # fmt: skip
        with pytest.raises(IdentityAdminRefused, match="no such person"):
            await act
    assert realm.users["u-sa"]["enabled"] is True
    await admin.aclose()
