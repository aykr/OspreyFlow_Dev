"""The identity item of a backup (`06_DECISIONS.md` ADR-114 Amendment 3, B2e): a realm's people and
dashboard identities carried to a new deployment **with their ids**, because every case grant, every
`created_by` and every audit row names a person by that id — a restore that gave people new ids
would lock them out of their own cases.

The fake below models what a real Keycloak 26.0 did when this was measured on 12 October 2026
(`CLAUDE.md` rule 15: a fake models the refusals, not only the grants): a user or client id is unique
across the whole server, and a partial import naming one that exists is refused 409 "Duplicate
resource error"; an imported client gets a new internal id; a dashboard's service account keeps its
id only when it is imported as a user naming its client. `test_a_real_keycloak_round_trip` runs the
same against a real Keycloak when `OSPREY_TEST_KEYCLOAK_URL` names one.

What a mistake would do, and the case that catches it:
- people re-created with new ids — `test_people_keep_their_ids_attributes_and_roles`;
- a dashboard's grants orphaned — `test_a_dashboards_service_account_keeps_its_id_and_its_secret`;
- the install's own same-name accounts blocking the import, or the import refused silently —
  `test_what_a_fresh_install_made_under_the_same_names_is_replaced`,
  `test_a_refused_import_is_said_in_words`;
- the install's own clients or their service accounts carried across —
  `test_only_dashboard_identities_travel`.
"""

from __future__ import annotations

import base64
import copy
import json
import os
import uuid
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from harness import identity

ISSUER, REALM = "http://kc.test", "osprey"


class FakeKeycloak:
    """One Keycloak server: realms of users and clients; ids unique across the server."""

    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {}  # id -> user (with "_realm")
        self.clients: dict[str, dict[str, Any]] = {}  # id -> client (with "_realm", "_secret")
        self.roles: dict[str, dict[str, list[str]]] = {}  # user id -> {"realm": [...], client: [...]}

    def add_user(self, username: str, realm: str = REALM, **extra: Any) -> str:
        uid = str(uuid.uuid4())
        self.users[uid] = {"id": uid, "username": username, "enabled": True, "_realm": realm, **extra}
        self.roles[uid] = {"realm": [f"default-roles-{realm}"]}
        return uid

    def add_client(self, client_id: str, secret: str, realm: str = REALM, service_account: bool = True) -> str:
        cid = str(uuid.uuid4())
        self.clients[cid] = {"id": cid, "clientId": client_id, "_realm": realm, "_secret": secret,
                             "serviceAccountsEnabled": service_account}  # fmt: skip
        if service_account:
            sa = self.add_user(f"service-account-{client_id}", realm, serviceAccountClientId=client_id)
            self.clients[cid]["_sa"] = sa
        return cid

    def _public(self, record: dict[str, Any]) -> dict[str, Any]:
        return {k: copy.deepcopy(v) for k, v in record.items() if not k.startswith("_")}

    def __call__(self, url: str, *, token: str | None = None, data: Any = None, form: bool = False,
                 method: str | None = None) -> tuple[int, Any]:  # fmt: skip
        parsed = urlparse(url)
        path = parsed.path.split(f"/admin/realms/{REALM}", 1)[-1]
        query = parse_qs(parsed.query)
        verb = method or ("POST" if data is not None else "GET")
        in_realm = {u: r for u, r in self.users.items() if r["_realm"] == REALM}
        if verb == "GET" and path == "/users":
            found = [r for r in in_realm.values() if "serviceAccountClientId" not in r]
            if "username" in query:
                found = [r for r in found if r["username"] == query["username"][0]]
            return 200, [self._public(r) for r in found]
        if verb == "GET" and path.startswith("/users/") and path.endswith("/role-mappings"):
            uid = path.split("/")[2]
            mapped = self.roles.get(uid, {})
            return 200, {"realmMappings": [{"name": n} for n in mapped.get("realm", [])],
                         "clientMappings": {c: {"client": c, "mappings": [{"name": n} for n in names]}
                                            for c, names in mapped.items() if c != "realm"}}  # fmt: skip
        if verb == "GET" and path.startswith("/users/") and path.endswith("/groups"):
            return 200, []
        if verb == "GET" and path.startswith("/users/"):
            uid = path.split("/")[2]
            return (200, self._public(self.users[uid])) if uid in in_realm else (404, {})
        if verb == "DELETE" and path.startswith("/users/"):
            self.users.pop(path.split("/")[2], None)
            return 204, None
        realm_clients = {c: r for c, r in self.clients.items() if r["_realm"] == REALM}
        if verb == "GET" and path == "/clients":
            return 200, [self._public(r) for r in realm_clients.values()]
        if verb == "GET" and path.endswith("/client-secret"):
            return 200, {"type": "secret", "value": realm_clients[path.split("/")[2]]["_secret"]}
        if verb == "GET" and path.endswith("/service-account-user"):
            return 200, self._public(self.users[realm_clients[path.split("/")[2]]["_sa"]])
        if verb == "DELETE" and path.startswith("/clients/"):
            gone = self.clients.pop(path.split("/")[2])
            self.users.pop(gone.get("_sa", ""), None)
            return 204, None
        if verb == "POST" and path == "/partialImport":
            return self._partial_import(data)
        raise AssertionError(f"the fake was asked for {verb} {path}")

    def _partial_import(self, body: dict[str, Any]) -> tuple[int, Any]:
        names = {r["username"] for r in self.users.values() if r["_realm"] == REALM}
        for person in body.get("users", []):
            if person["id"] in self.users or person["username"] in names:
                return 409, {"errorMessage": "Duplicate resource error"}
        for client in body.get("clients", []):
            if any(c["clientId"] == client["clientId"] and c["_realm"] == REALM for c in self.clients.values()):
                return 409, {"errorMessage": "Duplicate resource error"}
        sa_ids = {p["serviceAccountClientId"]: p for p in body.get("users", []) if p.get("serviceAccountClientId")}
        for client in body.get("clients", []):
            cid = str(uuid.uuid4())  # measured: an imported client gets a new internal id
            record = {"id": cid, "clientId": client["clientId"], "_realm": REALM, "_secret": client["secret"],
                      "serviceAccountsEnabled": True}  # fmt: skip
            self.clients[cid] = record
            if client["clientId"] in sa_ids:  # measured: kept only when imported with its client named
                person = sa_ids[client["clientId"]]
                record["_sa"] = person["id"]
            else:
                record["_sa"] = self.add_user(f"service-account-{client['clientId']}",
                                              serviceAccountClientId=client["clientId"])  # fmt: skip
        for person in body.get("users", []):
            stored = {k: v for k, v in person.items() if k not in ("realmRoles", "clientRoles", "groups")}
            self.users[person["id"]] = {**stored, "_realm": REALM}
            self.roles[person["id"]] = {"realm": list(person.get("realmRoles", [])),
                                        **{c: list(n) for c, n in (person.get("clientRoles") or {}).items()}}  # fmt: skip
        return 200, {"added": len(body.get("users", [])) + len(body.get("clients", []))}


def _old_deployment() -> tuple[FakeKeycloak, dict[str, str]]:
    old = FakeKeycloak()
    ana = old.add_user("osprey-demo-analyst", attributes={"clearance": ["OFFICIAL"], "org_unit": ["verify"]})
    old.roles[ana]["realm"].append("analyst")
    admin = old.add_user("osprey-demo-admin")
    old.roles[admin]["realm-management"] = ["manage-users", "view-users"]
    dash = old.add_client("osprey-dashboard-compliance", "board-secret")
    old.add_client("osprey-glass", "glass-secret")  # the install's own client
    return old, {"ana": ana, "admin": admin, "dash_sa": old.clients[dash]["_sa"]}


def _new_deployment_like(old: FakeKeycloak) -> FakeKeycloak:
    """A different server: what a fresh install made, under the same names but with new ids."""
    new = FakeKeycloak()
    new.add_user("osprey-demo-analyst")
    new.add_user("osprey-demo-admin")
    new.add_client("osprey-glass", "new-glass-secret")
    return new


def test_people_keep_their_ids_attributes_and_roles() -> None:
    old, ids = _old_deployment()
    exported = identity.export_identity(issuer=ISSUER, realm=REALM, token="t", call=old)
    new = _new_deployment_like(old)
    identity.import_identity(issuer=ISSUER, realm=REALM, token="t", identity=exported, call=new)
    by_name = {u["username"]: (uid, u) for uid, u in new.users.items()}
    uid, ana = by_name["osprey-demo-analyst"]
    assert uid == ids["ana"] and ana["attributes"] == {"clearance": ["OFFICIAL"], "org_unit": ["verify"]}
    assert "analyst" in new.roles[uid]["realm"]
    assert new.roles[ids["admin"]]["realm-management"] == ["manage-users", "view-users"]


def test_a_dashboards_service_account_keeps_its_id_and_its_secret() -> None:
    old, ids = _old_deployment()
    exported = identity.export_identity(issuer=ISSUER, realm=REALM, token="t", call=old)
    new = _new_deployment_like(old)
    identity.import_identity(issuer=ISSUER, realm=REALM, token="t", identity=exported, call=new)
    (board,) = [c for c in new.clients.values() if c["clientId"] == "osprey-dashboard-compliance"]
    assert board["_secret"] == "board-secret"
    assert board["_sa"] == ids["dash_sa"], "the id its case grants name"


def test_only_dashboard_identities_travel() -> None:
    old, _ids = _old_deployment()
    exported = identity.export_identity(issuer=ISSUER, realm=REALM, token="t", call=old)
    assert [d["clientId"] for d in exported["dashboards"]] == ["osprey-dashboard-compliance"]
    accounts = [p["username"] for p in exported["people"] if p.get("serviceAccountClientId")]
    assert accounts == ["service-account-osprey-dashboard-compliance"]
    assert "glass-secret" not in json.dumps(exported)


def test_what_a_fresh_install_made_under_the_same_names_is_replaced() -> None:
    old, _ids = _old_deployment()
    exported = identity.export_identity(issuer=ISSUER, realm=REALM, token="t", call=old)
    new = _new_deployment_like(old)
    new.add_client("osprey-dashboard-compliance", "a-newer-secret")
    summary = identity.import_identity(issuer=ISSUER, realm=REALM, token="t", identity=exported, call=new)
    assert summary == {"people": 3, "dashboards": 1, "replaced": 3}
    names = [u["username"] for u in new.users.values() if u["_realm"] == REALM]
    assert sorted(names) == sorted(set(names)), "no name twice"
    glass = [c for c in new.clients.values() if c["clientId"] == "osprey-glass"]
    assert glass and glass[0]["_secret"] == "new-glass-secret", "the install's own client is left alone"


def test_a_refused_import_is_said_in_words() -> None:
    old, _ids = _old_deployment()
    exported = identity.export_identity(issuer=ISSUER, realm=REALM, token="t", call=old)
    with pytest.raises(identity.IdentityFailed, match="refused") as refusal:
        identity.import_identity(issuer=ISSUER, realm=REALM, token="t", identity=exported, call=old)
    assert "board-secret" not in str(refusal.value)


def test_an_identity_from_another_realm_is_refused() -> None:
    old, _ids = _old_deployment()
    exported = identity.export_identity(issuer=ISSUER, realm=REALM, token="t", call=old)
    with pytest.raises(identity.IdentityFailed, match="realm"):
        identity.import_identity(issuer=ISSUER, realm="elsewhere", token="t", identity=exported, call=old)


@pytest.mark.skipif(not os.environ.get("OSPREY_TEST_KEYCLOAK_URL"), reason="needs a throwaway Keycloak")
def test_a_real_keycloak_round_trip() -> None:
    """Against a real, throwaway Keycloak 26 (admin `admin`, password in OSPREY_TEST_KEYCLOAK_ADMIN):
    two realms on one server stand in for two servers by deleting the first after its export."""
    from harness import keycloak_admin as kc

    url = os.environ["OSPREY_TEST_KEYCLOAK_URL"]
    token = kc.admin_token(issuer=url, admin_user="admin", admin_password=os.environ["OSPREY_TEST_KEYCLOAK_ADMIN"])
    call = kc._call
    realm = f"rt-{uuid.uuid4().hex[:6]}"
    base = f"{url}/admin/realms"
    call(base, token=token, data={"realm": realm, "enabled": True})
    kc.ensure_unmanaged_attributes(issuer=url, realm=realm, token=token)
    call(f"{base}/{realm}/users", token=token, data={"username": "ana", "enabled": True,
                                                       "attributes": {"clearance": ["OFFICIAL"]}})  # fmt: skip
    call(f"{base}/{realm}/clients", token=token, data={"clientId": "osprey-dashboard-rt", "secret": "rt-secret",
                                                          "serviceAccountsEnabled": True, "publicClient": False})  # fmt: skip
    exported = identity.export_identity(issuer=url, realm=realm, token=token, call=call)
    ana_id = next(p["id"] for p in exported["people"] if p["username"] == "ana")
    sa_id = next(p["id"] for p in exported["people"] if p.get("serviceAccountClientId"))
    call(f"{base}/{realm}", token=token, method="DELETE")
    call(base, token=token, data={"realm": realm, "enabled": True})
    kc.ensure_unmanaged_attributes(issuer=url, realm=realm, token=token)
    call(f"{base}/{realm}/users", token=token, data={"username": "ana", "enabled": True})
    try:
        identity.import_identity(issuer=url, realm=realm, token=token, identity=exported, call=call)
        _, people = call(f"{base}/{realm}/users?username=ana&exact=true", token=token)
        assert people[0]["id"] == ana_id and people[0]["attributes"]["clearance"] == ["OFFICIAL"]
        status, granted = call(f"{url}/realms/{realm}/protocol/openid-connect/token", form=True, data={
            "client_id": "osprey-dashboard-rt", "client_secret": "rt-secret", "grant_type": "client_credentials"})  # fmt: skip
        assert status == 200
        claims = json.loads(base64.urlsafe_b64decode(granted["access_token"].split(".")[1] + "=="))
        assert claims["sub"] == sa_id, "the dashboard is the same principal its grants name"
    finally:
        call(f"{base}/{realm}", token=token, method="DELETE")
