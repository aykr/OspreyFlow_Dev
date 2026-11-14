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
from typing import Any, cast

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
        self.dashboard_rows: dict[tuple[str, str], Any] = {}

    async def ping(self) -> None:
        if self.down:
            raise OSError("down")

    async def rows(self) -> list[PersonAccount]:
        # As the real store reads them (`PEOPLE_SQL`): a guest is not enabled while guests are not
        # admitted (ADR-148 Amendment 17).
        refused = not self.guests[0]
        return [p.model_copy(update={"enabled": False}) if p.guest and refused else p
                for (t, _), p in self.people.items() if t == self.tenant_id]  # fmt: skip

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

    # ADR-148 Amendment 10: dashboard identities, refused as the real store refuses
    # (`test_entra_people_live.py`): a second registration of one id, and only this tenant's rows.
    async def register_dashboard(
        self, application_id: str, name: str, *, clearance: str, org_unit: str
    ) -> Any:
        from services.api.identity_admin import DashboardExistsError

        from principal_auth import StoredDashboard

        rows = self.dashboard_rows
        if (self.tenant_id, application_id) in rows:
            raise DashboardExistsError(application_id)
        # UNIQUE (tenant_id, name), as the real table refuses a second board of one name.
        if any(t == self.tenant_id and d.name == name for (t, _), d in rows.items()):
            raise DashboardExistsError(name)
        rows[(self.tenant_id, application_id)] = StoredDashboard(
            application_id, clearance, org_unit, ("P",), name
        )
        return rows[(self.tenant_id, application_id)]

    async def dashboards(self) -> list[Any]:
        rows = self.dashboard_rows
        return [d for (t, _), d in rows.items() if t == self.tenant_id]

    async def remove_dashboard(self, application_id: str) -> bool:
        rows = self.dashboard_rows
        return rows.pop((self.tenant_id, application_id), None) is not None

    # ADR-148 Amendment 17: whether guests are admitted, off when never set, as the real table is.
    guests: tuple[bool, str | None, Any] = (False, None, None)

    async def guest_sign_in(self) -> tuple[bool, str | None, Any]:
        return self.guests

    async def set_guests_admitted(self, admitted: bool, by: str) -> bool:
        from datetime import UTC, datetime

        before = self.guests[0]
        self.guests = (admitted, by, datetime.now(UTC))
        return before


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
        "detail": f"{OID} is already in People and roles: give them roles there.",
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
    # ADR-148 Amendment 15: and the values set here, none without the fallback.
    assert client.get("/v1/admin/sign-in").json() == {"kind": "entra", "administrator_sets": []}


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
    unused: Any = None  # never opened: a Keycloak mapping has no people store
    assert await open_people_store("postgresql://unused", ClaimMapping(), unused) is None


async def test_an_entra_mapping_with_no_first_administrator_does_not_start(monkeypatch) -> None:
    """Refused before any connection is opened."""
    monkeypatch.delenv("OSPREY_FIRST_ADMINISTRATORS", raising=False)
    with pytest.raises(ValueError, match="OSPREY_FIRST_ADMINISTRATORS"):
        await open_people_store("postgresql://unused", MAPPING, cast(Any, None))


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
    ("people", "closed"),
    [
        (_Standing(StoredPerson(roles=("osprey-admin",), disabled=False)), None),
        (_Standing(StoredPerson(roles=("osprey-admin",), disabled=True)), 1008),
        (_Standing(StoredPerson(roles=(), disabled=False)), 1008),
        (_Standing(None, fail=True), 1013),
    ],
    ids=["stands", "disabled-mid-socket", "roles-taken-away", "store-down"],
)
async def test_an_open_socket_is_closed_at_its_next_message_once_the_person_no_longer_stands(
    people, closed
) -> None:
    """Before each message: 1008 for a person disabled or whose roles changed, 1013 when the store
    cannot answer (Amendment 8 point 1; the second review's note 12), and both loops close with
    the code the admission gives."""
    from types import SimpleNamespace

    from services.api.app import _admission, _handle_resync_requests, _SocketState

    admitted = _admission(_socket_app(people), ADMIN, "case-1")
    answer = await admitted()
    assert (answer if isinstance(answer, int) else None) == closed
    if closed is None:
        return

    class _Socket:
        def __init__(self) -> None:
            self.closed: list[int] = []

        async def receive_json(self) -> dict[str, object]:
            return {"last_acknowledged_seq": 0}

        async def close(self, code: int = 1000) -> None:
            self.closed.append(code)

    socket = _Socket()
    await _handle_resync_requests(
        socket,  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        "case-1",
        ADMIN,
        _SocketState(admitted=admitted),
    )
    assert socket.closed == [closed]


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
    ],
    ids=["remove", "organisation-link"],
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


# --- the orchestrator's review of P10 part 2: lock-out and stale access (rulings, 12 November) ---


def test_a_manager_who_never_signed_in_is_no_proof_anyone_can_administer(client: Any) -> None:
    """Item 4 (b): a phantom object id added by hand, holding the Admin role but never signed in,
    does not count: taking the role from the one administrator who has signed in is refused."""
    _as(ADMIN)
    phantom = _row(NEW, ["osprey-admin"]).model_copy(update={"signed_in": False})
    client.store.people[(TENANT, NEW)] = phantom
    response = client.put(f"/v1/admin/people/{OID}/roles", json={"roles": ["analyst"]})
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["error"] == "locks_out_administrators"
    assert client.store.people[(TENANT, OID)].roles == ["osprey-admin"]


def test_the_lock_out_counts_a_manager_who_has_signed_in(client: Any) -> None:
    """The control: the second administrator has signed in, so the change is allowed."""
    _as(ADMIN)
    client.store.people[(TENANT, NEW)] = _row(NEW, ["osprey-admin"])
    response = client.put(f"/v1/admin/people/{OID}/roles", json={"roles": ["analyst"]})
    assert response.status_code == 200, response.text


def _read(hours_ago: float) -> PersonAccount:
    from datetime import UTC, datetime, timedelta

    return _row(NEW, ["osprey-admin", "analyst"]).model_copy(
        update={
            "org_unit": "unit-1",
            "access_read_at": datetime.now(UTC) - timedelta(hours=hours_ago),
        }
    )


@pytest.mark.parametrize(("hours_ago", "stale"), [(25, True), (23, False)], ids=["stale", "fresh"])
def test_a_transfer_to_someone_whose_access_is_a_day_old_is_refused_in_words(
    hours_ago: float, stale: bool
) -> None:
    """Item 5: a clearance or unit read from Entra ID over a day ago is not trusted to receive."""
    from services.api.admin_people import DisableRefused, check_transfers, recipients

    from schemas.admin import OwnedItem, OwnedTransfer

    who = recipients([_read(hours_ago)], {}, {})
    item = OwnedItem(kind="hotlist", id="h1", label="The hotlist Watch")
    transfer = OwnedTransfer(kind="hotlist", id="h1", to=NEW)
    if stale:
        with pytest.raises(DisableRefused) as refused:
            check_transfers(OID, [item], [transfer], who)
        assert "over a day ago" in refused.value.words and NEW in refused.value.words
    else:
        assert check_transfers(OID, [item], [transfer], who) == {("hotlist", "h1"): NEW}


@pytest.mark.parametrize(("hours_ago", "sent"), [(25, False), (23, True)], ids=["stale", "fresh"])
def test_a_promotions_alert_skips_someone_whose_access_is_a_day_old(
    hours_ago: float, sent: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """Item 5 for promotions: `recipients_of` leaves out a unit administrator whose clearance and
    unit were read from Entra ID over a day ago, and the log says why, in the transfer's words."""
    import logging
    from datetime import UTC, datetime

    from services.api.entra_people import STALE_ACCESS_WORDS
    from services.api.promotion_ageing import PendingPromotion, recipients_of

    promotion = PendingPromotion(
        items_marking=None, promotion_id="p1", load_id="l1", dataset_id="ds-a",
        dataset_name="Records", dataset_unit="unit-1", proposed_by="someone-else",
        proposed_at=datetime(2026, 11, 1, tzinfo=UTC),
    )  # fmt: skip
    with caplog.at_level(logging.INFO, logger="services.api.promotion_ageing"):
        assert (recipients_of(promotion, [], [_read(hours_ago)]) == [NEW]) is sent
    assert (STALE_ACCESS_WORDS in caplog.text) is not sent


def test_keycloaks_people_are_always_current() -> None:
    """The control: no `access_read_at` (Keycloak's directory attributes) is never stale."""
    from services.api.entra_people import access_current

    assert access_current(_row(OID, ["osprey-admin"]))


class _Socket:
    """Just enough of a `WebSocket` for `stream`'s authentication: a bearer header, the app's
    resolver, and a record of how it was closed."""

    def __init__(self, resolver: Any) -> None:
        from types import SimpleNamespace

        self.headers = {"authorization": "Bearer a-token"}
        self.query_params: dict[str, str] = {}
        self.app = SimpleNamespace(state=SimpleNamespace(principal_resolver=resolver))
        self.closed: list[int] = []

    async def close(self, code: int = 1000) -> None:
        self.closed.append(code)


@pytest.mark.parametrize(
    ("raised", "code"),
    [("lookup", 1013), ("refused", 1008)],
    ids=["roles-unreadable", "token-refused"],
)
async def test_a_bearer_whose_roles_cannot_be_read_is_closed_try_again_later(raised, code) -> None:
    """Item 7 (Amendment 8 point 1): at connect, a bearer header whose stored roles cannot be read
    closes the socket with 1013, never 1008 and never a socket left open; a refused token 1008."""
    from services.api.app import stream

    from principal_auth import PrincipalLookupUnavailable, PrincipalResolutionError

    class _Resolver:
        async def resolve_principal(self, token: str) -> Principal:
            if raised == "lookup":
                raise PrincipalLookupUnavailable("store down")
            raise PrincipalResolutionError("token rejected")

    socket = _Socket(_Resolver())
    await stream(socket, "case-1")  # type: ignore[arg-type]
    assert socket.closed == [code]


# --- ADR-148 Amendment 10: dashboard identities on Entra ID, registered by application id ------

DASHBOARD = "dddddddd-eeee-4fff-8000-111111111111"


async def test_a_dashboard_identity_is_registered_listed_and_removed_by_application_id() -> None:
    """Entra holds the registration and its secret; Admin › Dashboards holds what it reads with. The
    identity's account (what a case Author grants Viewer to) is its application id."""
    store = _Store()
    admin = EntraPeopleAdmin(store)  # type: ignore[arg-type]
    made = await admin.create_dashboard(
        "Compliance board", clearance="OFFICIAL", org_unit="unit-2", application_id=DASHBOARD
    )
    assert made.secret is None  # Entra keeps it; nothing to show once
    assert (made.dashboard.client_id, made.dashboard.account_id) == (DASHBOARD, DASHBOARD)
    assert (made.dashboard.clearance, made.dashboard.org_unit) == ("OFFICIAL", "unit-2")
    assert made.dashboard.receivable_handling_codes == ["P"]
    assert [d.client_id for d in await admin.list_dashboards()] == [DASHBOARD]
    await admin.delete_dashboard(DASHBOARD)
    assert await admin.list_dashboards() == []


async def test_on_entra_a_dashboard_is_named_as_keycloak_names_one_and_once_a_tenant() -> None:
    """The name Superset's embedding matches a board on (platform-b's agreement): required, the
    slug Keycloak's `osprey-dashboard-<slug>` carries, one dashboard of a name in a tenant."""
    from services.api.identity_admin import DashboardExistsError, UnknownRoleError

    store = _Store()
    admin = EntraPeopleAdmin(store)  # type: ignore[arg-type]
    made = await admin.create_dashboard(
        "Compliance board", clearance="OFFICIAL", org_unit="u", application_id=DASHBOARD
    )
    assert made.dashboard.name == "compliance-board"
    assert [d.name for d in await admin.list_dashboards()] == ["compliance-board"]
    with pytest.raises(DashboardExistsError):
        await admin.create_dashboard("COMPLIANCE  Board!", clearance="OFFICIAL", org_unit="u",
                                     application_id="ffffffff-0000-4111-8222-333333333333")  # fmt: skip
    with pytest.raises(UnknownRoleError, match="name"):
        await admin.create_dashboard("!!!", clearance="OFFICIAL", org_unit="u",
                                     application_id="ffffffff-0000-4111-8222-333333333333")  # fmt: skip
    assert len(await admin.list_dashboards()) == 1


async def test_on_entra_a_dashboard_is_refused_in_words_without_its_application_id() -> None:
    from services.api.identity_admin import (
        DashboardExistsError,
        PersonActionRefused,
        UnknownRoleError,
    )

    store = _Store()
    admin = EntraPeopleAdmin(store)  # type: ignore[arg-type]
    with pytest.raises(UnknownRoleError, match="application id"):
        await admin.create_dashboard("Board", clearance="OFFICIAL", org_unit="u")
    assert await store.dashboards() == []
    await admin.create_dashboard("Board", clearance="OFFICIAL", org_unit="u",
                                 application_id=DASHBOARD)  # fmt: skip
    with pytest.raises(DashboardExistsError):
        await admin.create_dashboard("Again", clearance="OFFICIAL", org_unit="u",
                                     application_id=DASHBOARD)  # fmt: skip
    with pytest.raises(PersonActionRefused) as refused:
        await admin.delete_dashboard("ffffffff-0000-4111-8222-333333333333")
    assert refused.value.error == "no_such_dashboard"


GLASS_APP = "aaaaaaaa-1111-4222-8333-444444444444"
API_APP = "bbbbbbbb-1111-4222-8333-444444444444"


@pytest.mark.parametrize("own", [GLASS_APP, API_APP, API_APP.upper()], ids=["glass", "api", "api-upper"])
async def test_the_deployment_s_own_applications_are_never_registered_as_dashboards(own: str) -> None:
    """The resolver would refuse their tokens as a dashboard's, so a registration of either is a
    mistake, refused in words before anything is written (the lane review of 009a889)."""
    from services.api.identity_admin import UnknownRoleError

    store = _Store()
    admin = EntraPeopleAdmin(store, own_clients=[GLASS_APP, API_APP, None])  # type: ignore[arg-type]
    with pytest.raises(UnknownRoleError, match="own"):
        await admin.create_dashboard("Board", clearance="OFFICIAL", org_unit="u", application_id=own)
    assert await store.dashboards() == []


async def test_on_keycloak_an_application_id_is_refused_in_words() -> None:
    """Keycloak registers its own client for a dashboard; an application id is Entra's."""
    from services.api.identity_admin import IdentityAdmin, UnknownRoleError

    admin = IdentityAdmin.__new__(IdentityAdmin)
    with pytest.raises(UnknownRoleError, match="Entra"):
        await admin.create_dashboard(
            "Board", clearance="OFFICIAL", org_unit="u", application_id=DASHBOARD
        )


def test_the_app_tells_the_entra_admin_its_own_applications() -> None:
    """The call site the app starts with (`people_directory`): on Entra ID the admin is given the
    claim mapping's Glass and API ids, so the refusal above holds in the running app (the lane
    review of 2b42dea)."""
    from types import SimpleNamespace

    from services.api.app import people_directory

    mapping = SimpleNamespace(client_id=GLASS_APP, api_client_id=API_APP)
    resources = SimpleNamespace(
        people_store=_Store(), principal_resolver=SimpleNamespace(claim_mapping=mapping)
    )
    admin = people_directory(resources, config=None)  # type: ignore[arg-type]
    assert isinstance(admin, EntraPeopleAdmin)
    assert admin.own_clients == {GLASS_APP, API_APP}


# --- ADR-148 Amendment 17: admitting guests, switched by an administrator of people alone ----------


def test_guests_are_not_admitted_until_an_administrator_admits_them(client: Any) -> None:
    _as(ADMIN)
    assert client.get("/v1/admin/sign-in/guests").json() == {
        "admitted": False, "changed_by": None, "changed_at": None}  # fmt: skip


@pytest.mark.parametrize("method", ["get", "put"])
def test_the_guest_setting_is_refused_without_manage_people_and_left_as_it_was(
    client: Any, method: str
) -> None:
    _as(ANALYST)
    kwargs = {"json": {"admitted": True}} if method == "put" else {}
    assert getattr(client, method)("/v1/admin/sign-in/guests", **kwargs).status_code == 403
    assert client.store.guests[0] is False and client.audit.records == []


def test_admitting_guests_is_set_by_who_and_audited_with_before_and_after(client: Any) -> None:
    _as(ADMIN)
    on = client.put("/v1/admin/sign-in/guests", json={"admitted": True})
    assert on.status_code == 200, on.text
    assert on.json()["admitted"] is True and on.json()["changed_by"] == ADMIN.id
    off = client.put("/v1/admin/sign-in/guests", json={"admitted": False})
    assert off.json()["admitted"] is False
    assert [(r["action"], r["resolved_query"]) for r in client.audit.records] == [
        ("set_guest_sign_in", {"before": False, "after": True}),
        ("set_guest_sign_in", {"before": True, "after": False}),
    ]


def test_turning_guests_off_is_refused_when_every_people_manager_is_a_guest(client: Any) -> None:
    _as(ADMIN)
    client.store.guests = (True, ADMIN.id, None)
    member = client.store.people[(TENANT, OID)]
    client.store.people[(TENANT, OID)] = member.model_copy(update={"guest": True})
    refused = client.put("/v1/admin/sign-in/guests", json={"admitted": False})
    assert refused.status_code == 409 and refused.json()["detail"]["error"] == "locks_out_administrators"
    assert client.store.guests[0] is True and client.audit.records == []
    client.store.people[(TENANT, OID)] = member  # a member who can manage people: allowed
    assert client.put("/v1/admin/sign-in/guests", json={"admitted": False}).status_code == 200


def test_an_unknown_field_is_refused(client: Any) -> None:
    _as(ADMIN)
    assert client.put("/v1/admin/sign-in/guests", json={"admitted": True, "x": 1}).status_code == 422


def test_on_keycloak_there_are_no_guests_to_admit() -> None:
    from services.api.app import get_custom_roles

    class _Keycloak:
        async def list_people(self) -> list[Any]:
            return []

    app.dependency_overrides[get_identity_admin] = lambda: _Keycloak()
    app.dependency_overrides[get_audit] = lambda: _Audit()
    app.dependency_overrides[get_custom_roles] = _NoCustomRoles
    _as(ADMIN)
    try:
        refused = TestClient(app).put("/v1/admin/sign-in/guests", json={"admitted": True})
        assert refused.status_code == 409 and refused.json()["detail"]["error"] == "not_entra"
    finally:
        app.dependency_overrides.clear()


def test_a_guest_manager_counts_for_nothing_once_guests_are_off_so_the_last_member_cannot_leave(
    client: Any,
) -> None:
    """The lane review's must 1: guests on, a member and a guest both manage people. Turning guests
    off is allowed (the member still can); the member then giving up manage_people is refused,
    since the guest can no longer sign in."""
    _as(ADMIN)
    client.store.guests = (True, ADMIN.id, None)
    client.store.people[(TENANT, NEW)] = _row(NEW, ["osprey-admin"]).model_copy(update={"guest": True})
    assert client.put("/v1/admin/sign-in/guests", json={"admitted": False}).status_code == 200
    listed = {p["id"]: p for p in client.get("/v1/admin/people").json()}
    assert listed[NEW]["enabled"] is False and listed[NEW]["guest"] is True
    refused = client.put(f"/v1/admin/people/{OID}/roles", json={"roles": ["analyst"]})
    assert refused.status_code == 409 and refused.json()["detail"]["error"] == "locks_out_administrators"
    client.store.guests = (True, ADMIN.id, None)  # admitted again: the guest counts
    assert client.put(f"/v1/admin/people/{OID}/roles", json={"roles": ["analyst"]}).status_code == 200


def test_on_keycloak_the_guest_setting_cannot_be_read_either() -> None:
    from services.api.app import get_custom_roles

    class _Keycloak:
        pass

    app.dependency_overrides[get_identity_admin] = lambda: _Keycloak()
    app.dependency_overrides[get_custom_roles] = _NoCustomRoles
    _as(ADMIN)
    try:
        assert TestClient(app).get("/v1/admin/sign-in/guests").status_code == 409
    finally:
        app.dependency_overrides.clear()
