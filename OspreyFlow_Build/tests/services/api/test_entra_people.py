"""Admin › People and the signed-in person's own principal on Entra ID sign-in (`06_DECISIONS.md`
ADR-148 Amendment 8; the orchestrator's ruling of 11 November 2026).

**The roles are the deployment's**, kept by tenant and object id and written only by Admin › People
(`services/api/entra_people.py`); the resolver reads them inside `principal_auth`'s one construction
path. These cases run the routes through FastAPI with Admin › People's Entra backend over a store
that refuses as the real one does (`_Store`: an unknown person, a person already added, another
tenant), and `GET /v1/me` through the real `get_principal` with an Entra resolver. The real store's
SQL, and another tenant's row granting nothing, are `test_entra_people_live.py`'s.

Every value is synthetic (rule 9).
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_handling_scheme,
    get_identity_admin,
    get_principal,
)
from services.api.auth import PrincipalResolver
from services.api.entra_people import (
    ENTRA_HOLDS_ACCOUNTS,
    EntraPeopleAdmin,
    first_administrators_from_env,
    open_people_store,
)
from services.api.identity_admin import IdentityAdminRefused, PersonExistsError

from ontology.handling import load_uk_le_scheme
from principal_auth import ClaimMapping, StoredPerson, ValueSource
from schemas.admin import PersonAccount
from schemas.domain import Principal
from tests.conftest import sign_token
from tests.services.api.test_auth import _config
from tests.services.api.test_auth_entra_claims import FakePeople

TENANT = "00000000-1111-4222-8333-444444444444"
OTHER_TENANT = "99999999-8888-4777-8666-555555555555"
API = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
GLASS = "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"
ISSUER = f"https://login.microsoftonline.com/{TENANT}/v2.0"
OID = "50000000-0000-4000-8000-000000000001"
NEW = "50000000-0000-4000-8000-000000000002"

ADMIN = Principal(id=OID, clearance="OFFICIAL", org_unit="unit-1", roles=["osprey-admin"])
ANALYST = Principal(id=NEW, clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])

MAPPING = ClaimMapping(
    tenant_id=TENANT,
    client_id=GLASS,
    clearance=ValueSource(claim="ext_clearance"),
    org_unit=ValueSource(claim="ext_unit"),
)


def _row(oid: str, roles: list[str], *, disabled: bool = False) -> PersonAccount:
    return PersonAccount(
        id=oid, username=oid, name=oid, enabled=not disabled, roles=roles, clearance="OFFICIAL"
    )


class _Store:
    """`EntraPeopleStore`'s Admin › People half, refusing as it refuses: an update of a person not
    recorded is `IdentityAdminRefused`, adding one already recorded `PersonExistsError`, and only
    this tenant's rows are seen."""

    def __init__(self) -> None:
        self.tenant_id = TENANT
        self.people: dict[tuple[str, str], PersonAccount] = {
            (TENANT, OID): _row(OID, ["osprey-admin"]),
            (OTHER_TENANT, NEW): _row(NEW, ["osprey-admin"]),
        }
        self.down = False

    async def ping(self) -> None:
        if self.down:
            raise OSError("down")

    async def rows(self) -> list[PersonAccount]:
        return [p for (t, _), p in self.people.items() if t == self.tenant_id]

    async def update(self, oid: str, column: str, value: object) -> PersonAccount:
        found = self.people.get((self.tenant_id, oid))
        if found is None:
            raise IdentityAdminRefused("no such person")
        if column == "roles":
            found = found.model_copy(update={"roles": value})
        else:
            found = found.model_copy(update={"enabled": not value})
        self.people[(self.tenant_id, oid)] = found
        return found

    async def add(self, oid: str, by: str) -> PersonAccount:
        if (self.tenant_id, oid) in self.people:
            raise PersonExistsError(oid)
        self.people[(self.tenant_id, oid)] = _row(oid, [])
        return self.people[(self.tenant_id, oid)]


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


class _NoCustomRoles:
    async def current_rights(self, ids: Any = None) -> dict[str, Any]:
        return {}

    async def teams(self, today: Any) -> list[Any]:
        return []

    def people_lock(self) -> Any:
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def held() -> Any:
            yield

        return held()


@pytest.fixture
def client() -> Any:
    from services.api.app import get_custom_roles

    store, audit = _Store(), _Audit()
    admin = EntraPeopleAdmin(store)  # type: ignore[arg-type]
    app.dependency_overrides[get_identity_admin] = lambda: admin
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_custom_roles] = _NoCustomRoles
    app.dependency_overrides[get_handling_scheme] = load_uk_le_scheme
    test_client = TestClient(app)
    test_client.store, test_client.audit = store, audit  # type: ignore[attr-defined]
    yield test_client
    app.dependency_overrides.clear()


def _as(who: Principal) -> None:
    app.dependency_overrides[get_principal] = lambda: who


# --- Admin › People on Entra (rule 4: the roles store's read behind manage_people) ---


def test_the_people_list_is_this_tenants_rows(client: Any) -> None:
    _as(ADMIN)
    response = client.get("/v1/admin/people")
    assert response.status_code == 200, response.text
    assert [p["id"] for p in response.json()] == [OID]


def test_the_people_list_is_refused_without_manage_people(client: Any) -> None:
    _as(ANALYST)
    assert client.get("/v1/admin/people").status_code == 403


def test_roles_are_written_to_the_store_and_audited(client: Any) -> None:
    _as(ADMIN)
    client.store.people[(TENANT, NEW)] = _row(NEW, [])
    response = client.put(f"/v1/admin/people/{NEW}/roles", json={"roles": ["analyst"]})
    assert response.status_code == 200, response.text
    assert client.store.people[(TENANT, NEW)].roles == ["analyst"]
    assert [r["action"] for r in client.audit.records] == ["set_person_roles"]


def test_an_unknown_role_is_refused_before_the_store(client: Any) -> None:
    _as(ADMIN)
    client.store.people[(TENANT, NEW)] = _row(NEW, [])
    response = client.put(f"/v1/admin/people/{NEW}/roles", json={"roles": ["realm-admin"]})
    assert response.status_code == 422
    assert client.store.people[(TENANT, NEW)].roles == []


def test_a_person_is_added_by_object_id_with_no_roles(client: Any) -> None:
    _as(ADMIN)
    response = client.post("/v1/admin/people/by-object-id", json={"object_id": NEW})
    assert response.status_code == 201, response.text
    assert response.json()["roles"] == []
    assert client.audit.records[-1]["action"] == "add_person_by_object_id"
    assert client.audit.records[-1]["resolved_query"] == {"user_id": NEW}


@pytest.mark.parametrize(
    "oid", ["not-an-oid", NEW.upper().replace("-", "_"), "", NEW + "0"], ids=str
)
def test_an_object_id_that_is_not_one_is_refused(client: Any, oid: str) -> None:
    _as(ADMIN)
    response = client.post("/v1/admin/people/by-object-id", json={"object_id": oid})
    assert response.status_code == 422
    assert (TENANT, oid) not in client.store.people


def test_adding_a_person_already_recorded_is_refused(client: Any) -> None:
    _as(ADMIN)
    response = client.post("/v1/admin/people/by-object-id", json={"object_id": OID})
    assert response.status_code == 409
    # The words name the object id, never a sign-in name or email address (finding 13).
    assert response.json() == {
        "error": "person_exists",
        "detail": f"{OID} is already in People: give them roles there.",
    }
    assert client.store.people[(TENANT, OID)].roles == ["osprey-admin"]


def test_adding_a_person_needs_manage_people(client: Any) -> None:
    _as(ANALYST)
    response = client.post("/v1/admin/people/by-object-id", json={"object_id": NEW})
    assert response.status_code == 403
    assert (TENANT, NEW) not in client.store.people


def test_adding_by_object_id_is_refused_on_keycloak(client: Any) -> None:
    """The control for the route: with Keycloak's backend people are invited."""

    class _Keycloak:
        pass

    app.dependency_overrides[get_identity_admin] = lambda: _Keycloak()
    _as(ADMIN)
    response = client.post("/v1/admin/people/by-object-id", json={"object_id": NEW})
    assert response.status_code == 409 and response.json()["error"] == "not_entra"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        (
            "post",
            "/v1/admin/people",
            {"username": "new.person", "first_name": "N", "last_name": "P",
             "email": "n@example.test", "clearance": "OFFICIAL", "org_unit": "unit-1",
             "receivable_handling_codes": [], "roles": []},
        ),
        ("put", f"/v1/admin/people/{OID}/access",
         {"clearance": "OFFICIAL", "org_unit": "unit-1", "receivable_handling_codes": []}),
        ("post", f"/v1/admin/people/{OID}/reset-sign-in", None),
    ],
    ids=["invite", "access", "reset"],
)  # fmt: skip
def test_what_entra_holds_is_refused_in_words(
    client: Any, method: str, path: str, body: Any
) -> None:
    _as(ADMIN)
    response = getattr(client, method)(path, json=body) if body else getattr(client, method)(path)
    assert response.status_code == 409, (path, response.status_code, response.text)
    assert response.json()["error"] == "entra_holds_accounts"
    assert ENTRA_HOLDS_ACCOUNTS in response.json()["detail"]


def test_people_is_told_the_deployment_signs_in_with_entra(client: Any) -> None:
    _as(ADMIN)
    assert client.get("/v1/admin/sign-in").json() == {"kind": "entra"}


def test_the_sign_in_kind_needs_manage_people(client: Any) -> None:
    _as(ANALYST)
    assert client.get("/v1/admin/sign-in").status_code == 403


# --- GET /v1/me through the real get_principal (rule 4; rule 7) ---


@pytest.fixture
def entra_app(jwks_url: str) -> Any:
    people = FakePeople()
    resolver = PrincipalResolver(
        _config(jwks_url, oidc_issuer=ISSUER, oidc_audience=API),
        claim_mapping=MAPPING,
        role_source=people,
        role_lookup_timeout_seconds=0.2,
    )
    before = getattr(app.state, "principal_resolver", None)
    app.state.principal_resolver = resolver
    yield TestClient(app), people
    app.state.principal_resolver = before
    app.dependency_overrides.clear()


def _entra_token(keypair: Any, **overrides: object) -> dict[str, str]:
    now = int(time.time())
    claims: dict[str, object] = {
        "aud": API, "iss": ISSUER, "iat": now, "nbf": now, "exp": now + 3600, "ver": "2.0",
        "tid": TENANT, "oid": OID, "azp": GLASS, "sub": "pairwise", "scp": "access_as_user",
        "ext_clearance": "OFFICIAL", "ext_unit": "unit-1", "roles": ["osprey-admin"],
    }  # fmt: skip
    claims.update(overrides)
    return {"Authorization": f"Bearer {sign_token(keypair[0], claims)}"}


def test_me_answers_the_resolved_principal_never_the_tokens_roles(entra_app, keypair) -> None:
    client, people = entra_app
    people.rows[(TENANT, OID)] = StoredPerson(roles=("analyst",), disabled=False)
    response = client.get("/v1/me", headers=_entra_token(keypair))
    assert response.status_code == 200, response.text
    assert response.json() == {
        "id": OID, "clearance": "OFFICIAL", "org_unit": "unit-1", "roles": ["analyst"],
        "receivable_handling_codes": [],
    }  # fmt: skip


def test_me_without_a_token_is_refused(entra_app) -> None:
    client, people = entra_app
    assert client.get("/v1/me").status_code in (401, 403)
    assert people.calls == []


def test_me_for_another_tenants_token_is_refused(entra_app, keypair) -> None:
    client, people = entra_app
    response = client.get("/v1/me", headers=_entra_token(keypair, tid=OTHER_TENANT))
    assert response.status_code == 401
    assert people.calls == []


def test_me_for_a_person_disabled_here_is_refused(entra_app, keypair) -> None:
    client, people = entra_app
    people.rows[(TENANT, OID)] = StoredPerson(roles=("osprey-admin",), disabled=True)
    assert client.get("/v1/me", headers=_entra_token(keypair)).status_code == 401


def test_a_session_whose_roles_cannot_be_read_is_a_503(entra_app, keypair) -> None:
    """Never a principal with no roles (the ruling): every route, `/v1/me` among them."""
    client, people = entra_app
    people.fail = ConnectionError("store down")
    response = client.get("/v1/me", headers=_entra_token(keypair))
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "people_store_unavailable"
    assert client.get("/v1/me/rights", headers=_entra_token(keypair)).status_code == 503


# --- the install's first administrators ---


@pytest.mark.parametrize("raw", ["", " , ", "not-an-oid", f"{OID},Bad"], ids=repr)
def test_first_administrators_none_or_malformed_stop_the_start(monkeypatch, raw: str) -> None:
    """Never "none named" read as everyone, and never a mistyped id that grants nobody."""
    monkeypatch.setenv("OSPREY_FIRST_ADMINISTRATORS", raw)
    with pytest.raises(ValueError):
        first_administrators_from_env()


def test_first_administrators_are_read_once_each(monkeypatch) -> None:
    monkeypatch.setenv("OSPREY_FIRST_ADMINISTRATORS", f"{OID}, {NEW},{OID}")
    assert first_administrators_from_env() == [OID, NEW]


async def test_a_keycloak_mapping_opens_no_people_store(monkeypatch) -> None:
    monkeypatch.delenv("OSPREY_FIRST_ADMINISTRATORS", raising=False)
    assert await open_people_store("postgresql://unused", ClaimMapping()) is None


async def test_an_entra_mapping_with_no_first_administrator_does_not_start(monkeypatch) -> None:
    """Refused before any connection is opened."""
    monkeypatch.delenv("OSPREY_FIRST_ADMINISTRATORS", raising=False)
    with pytest.raises(ValueError, match="OSPREY_FIRST_ADMINISTRATORS"):
        await open_people_store("postgresql://unused", MAPPING)


async def test_admin_system_says_unreachable_when_the_store_is_down() -> None:
    store = _Store()
    store.down = True
    check = await EntraPeopleAdmin(store).credential_check()  # type: ignore[arg-type]
    assert check.state == "unreachable"


# --- the delta socket (the lane-reviewer's finding 1: a socket outlives the request) ---


class _Standing:
    """`EntraPeopleStore.standing`, refusing as it does: a person not recorded is None, a failure
    raises (never "no roles")."""

    def __init__(self, stored: StoredPerson | None, fail: bool = False) -> None:
        self.stored, self.fail = stored, fail

    async def standing(self, oid: str) -> StoredPerson | None:
        if self.fail:
            raise ConnectionError("store down")
        return self.stored


class _AnyCase:
    async def get_authorized(self, *_: Any, **__: Any) -> None:
        return None


def _socket_app(people: _Standing | None) -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(
        state=SimpleNamespace(people_store=people, investigations=_AnyCase(), custom_roles=None)
    )


@pytest.mark.parametrize(
    ("people", "code"),
    [
        (_Standing(StoredPerson(roles=("osprey-admin",), disabled=False)), None),
        (_Standing(StoredPerson(roles=("osprey-admin",), disabled=True)), 1008),
        (_Standing(StoredPerson(roles=("analyst",), disabled=False)), 1008),
        (_Standing(None), 1008),
        (_Standing(None, fail=True), 1013),
        (None, None),
    ],
    ids=["stands", "disabled", "roles-changed", "not-recorded", "store-down", "keycloak"],
)
async def test_a_socket_stands_only_while_the_store_says_so(people, code) -> None:
    """At connect (a ticket minted before a disable) and before every message: a person disabled,
    gone or whose roles changed is closed (1008, to sign in afresh); a read that fails is 1013."""
    from services.api.app import _socket_standing

    assert await _socket_standing(_socket_app(people), ADMIN) == code


@pytest.mark.parametrize(
    ("people", "admitted"),
    [
        (_Standing(StoredPerson(roles=("osprey-admin",), disabled=False)), True),
        (_Standing(StoredPerson(roles=("osprey-admin",), disabled=True)), False),
        (_Standing(StoredPerson(roles=(), disabled=False)), False),
        (_Standing(None, fail=True), False),
    ],
    ids=["stands", "disabled-mid-socket", "roles-taken-away", "store-down"],
)
async def test_an_open_socket_is_closed_at_its_next_message_once_the_person_no_longer_stands(
    people, admitted
) -> None:
    from services.api.app import _admission

    principal = await _admission(_socket_app(people), ADMIN, "case-1")()
    assert (principal is not None) is admitted


def _stream_asks_before_its_first_send(source: str) -> bool:
    import ast

    tree = ast.parse(source)
    stream = next(
        n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "stream"
    )
    asked = sent = None
    for node in ast.walk(stream):
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name == "_socket_standing" and asked is None:
                asked = node.lineno
            if name.endswith("working_set.sync") and sent is None:
                sent = node.lineno
    return asked is not None and sent is not None and asked < sent


def test_the_stream_asks_the_store_before_its_first_send() -> None:
    """A ticket minted before a disable is refused at connect, before the snapshot is sent (the
    stream needs a live socket to run, so its order is read from the source; shown red below)."""
    from pathlib import Path

    import services.api.app as app_module

    assert _stream_asks_before_its_first_send(Path(app_module.__file__).read_text())
    planted = (
        "async def stream(w, i):\n    await working_set.sync(i)\n    await _socket_standing(w, r)\n"
    )
    assert not _stream_asks_before_its_first_send(planted)


@pytest.mark.parametrize(
    ("call", "words"),
    [
        (lambda a: a.remove_person(OID), "is not removed here"),
        (lambda a: a.link_organisation(OID, "subject"), "no organisation account"),
        (lambda a: a.create_dashboard("Reports", clearance="OFFICIAL", org_unit="u"), "Dashboard"),
        (lambda a: a.delete_dashboard("osprey-dashboard-reports"), "Dashboard"),
    ],
    ids=["remove", "organisation-link", "register-dashboard", "delete-dashboard"],
)
async def test_the_rest_of_what_entra_holds_is_refused_in_words(call, words) -> None:
    """Amendment 8 point 3's other refusals, each 409 `entra_holds_accounts` through the route's
    handler (finding 7); the store is never written."""
    from services.api.identity_admin import PersonActionRefused

    store = _Store()
    before = dict(store.people)
    with pytest.raises(PersonActionRefused) as refused:
        await call(EntraPeopleAdmin(store))  # type: ignore[arg-type]
    assert refused.value.error == "entra_holds_accounts" and words in refused.value.words
    assert store.people == before
