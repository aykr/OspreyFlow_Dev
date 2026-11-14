"""Admin › People's Access on Entra ID for the values the claim mapping sources from the administrator
(`06_DECISIONS.md` ADR-148 Amendment 15; the audit's ruling 4c), through the real route.

The people store's limits are the store's own (rule 3): no clearance above, and no handling code beyond,
what the setter holds **as the store holds them**, whatever the setter's token or the route's own check
says; a setter disabled or with nothing set sets nothing. The store here keeps rows as the real table does
(by tenant and object id, the same columns), decides with the real `check_administrator_access` and shows
with the real `_person`; what only the real table can show (its transaction, its tenant clause, a sign-in
never overwriting what was set, the audit row in the same transaction) is `test_entra_people_live.py`'s
Amendment 15 section. Synthetic values only (rule 9).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    _socket_standing,
    app,
    get_audit,
    get_handling_scheme,
    get_identity_admin,
    get_principal,
)
from services.api.entra_people import (
    AccessBeyondTheSetter,
    EntraPeopleAdmin,
    NoSuchPerson,
    _held,
    _person,
    check_administrator_access,
    first_administrator_access_from_env,
)

from ontology.handling import load_uk_le_scheme
from principal_auth import StoredPerson
from schemas.admin import PersonAccessInput
from schemas.domain import Principal

TENANT = "00000000-1111-4222-8333-444444444444"
OTHER_TENANT = "99999999-8888-4777-8666-555555555555"
SETTER = "50000000-0000-4000-8000-000000000001"
PERSON = "50000000-0000-4000-8000-000000000002"
EVERY = frozenset({"clearance", "org_unit", "handling_codes"})
CLASSES = list(load_uk_le_scheme().classification)


def _row(oid: str, *, seen: tuple[Any, Any, Any] = (None, None, []), set_here: tuple[Any, Any, Any] = (None, None, None),
         disabled: bool = False, roles: tuple[str, ...] = ()) -> dict[str, Any]:  # fmt: skip
    """A row of `entra_people` as the real table holds it: what a token said, and what was set here."""
    return {"oid": oid, "username": oid, "email": None, "name": None, "disabled": disabled, "roles": list(roles),
            "clearance": seen[0], "org_unit": seen[1], "receivable_handling_codes": list(seen[2]),
            "admin_clearance": set_here[0], "admin_org_unit": set_here[1], "admin_codes": set_here[2],
            "first_seen": None, "access_read_at": None}  # fmt: skip


class _Store:
    """The people store as the Access route reaches it: rows by (tenant, object id), the real store's
    decision inside, another tenant's rows never read, the audit row written with the change."""

    def __init__(self, by_administrator: frozenset[str] = EVERY) -> None:
        self.tenant_id = TENANT
        self.by_administrator = by_administrator
        self.rows: dict[tuple[str, str], dict[str, Any]] = {
            (TENANT, SETTER): _row(SETTER, set_here=("OFFICIAL-SENSITIVE", "unit-1", ["P", "R"]), roles=("osprey-admin",)),
            (TENANT, PERSON): _row(PERSON, seen=("OFFICIAL", "unit-1", ["P"])),
        }

    async def set_administrator_access(self, oid: str, by: Principal, access: PersonAccessInput, classification: Any, audit: Any = None):  # type: ignore[no-untyped-def]
        target = self.rows.get((self.tenant_id, oid))
        if target is None:
            raise NoSuchPerson(f"{oid} is not in People here")
        check_administrator_access(self.by_administrator, self.rows.get((self.tenant_id, by.id)), access, classification)
        after = dict(target)
        for column, value in (("admin_clearance", access.clearance), ("admin_org_unit", access.org_unit),
                              ("admin_codes", access.receivable_handling_codes)):  # fmt: skip
            if value is not None:
                after[column] = value
        self.rows[(self.tenant_id, oid)] = after
        before_p, after_p = _person(target, self.by_administrator), _person(after, self.by_administrator)
        if audit is not None:
            await audit.record(principal=by, action="set_person_access",
                               resolved_query={"user_id": oid, "by_administrator": sorted(self.by_administrator),
                                               "before": _held(before_p), "after": _held(after_p)},
                               result_cardinality=1)  # fmt: skip
        return before_p, after_p


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


def _client(store: _Store, who: Principal) -> TestClient:
    audit = _Audit()
    admin = EntraPeopleAdmin(store)  # type: ignore[arg-type]
    app.dependency_overrides.update({
        get_identity_admin: lambda: admin, get_audit: lambda: audit, get_principal: lambda: who,
        get_handling_scheme: load_uk_le_scheme,
    })  # fmt: skip
    client = TestClient(app)
    client.audit = audit  # type: ignore[attr-defined]
    return client


@pytest.fixture(autouse=True)
def _clear():  # type: ignore[no-untyped-def]
    yield
    app.dependency_overrides.clear()


def _admin(clearance: str = "OFFICIAL-SENSITIVE", codes: tuple[str, ...] = ("P", "R")) -> Principal:
    return Principal(id=SETTER, clearance=clearance, org_unit="unit-1", roles=["osprey-admin"],
                     receivable_handling_codes=list(codes))  # fmt: skip


def _put(client: TestClient, **access: Any) -> Any:
    return client.put(f"/v1/admin/people/{PERSON}/access", json=access)


# --- through the route ---


def test_an_administrator_sets_the_values_within_their_own_and_it_is_audited() -> None:
    store = _Store()
    client = _client(store, _admin())
    response = _put(client, clearance="OFFICIAL-SENSITIVE", org_unit="unit-2", receivable_handling_codes=["R"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["clearance"], body["org_unit"], body["receivable_handling_codes"]) == ("OFFICIAL-SENSITIVE", "unit-2", ["R"])
    (record,) = client.audit.records  # type: ignore[attr-defined]
    assert record["action"] == "set_person_access" and record["principal"].id == SETTER
    query = record["resolved_query"]
    assert query["before"] == {"clearance": None, "org_unit": None, "receivable_handling_codes": []}
    assert query["after"] == {"clearance": "OFFICIAL-SENSITIVE", "org_unit": "unit-2", "receivable_handling_codes": ["R"]}
    assert query["by_administrator"] == ["clearance", "handling_codes", "org_unit"]


def test_the_store_refuses_a_clearance_above_the_setter_s_own_as_it_holds_them() -> None:
    """Rule 3: the setter's token says SECRET, so the route's own check passes; the store holds them
    at OFFICIAL-SENSITIVE, and refuses SECRET. A check in the route alone would have set it."""
    store = _Store()
    client = _client(store, _admin(clearance="SECRET"))
    response = _put(client, clearance="SECRET")
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["error"] == "above_your_clearance"
    assert store.rows[(TENANT, PERSON)]["admin_clearance"] is None
    assert client.audit.records == []  # type: ignore[attr-defined]


def test_the_store_refuses_a_code_beyond_the_setter_s_own_as_it_holds_them() -> None:
    client = _client(_Store(), _admin(codes=("P", "R", "C")))
    response = _put(client, receivable_handling_codes=["C"])
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == {"error": "handling_code_you_do_not_hold", "codes": ["C"]}


def test_a_partial_fallback_sets_its_value_whatever_entra_says_of_the_others() -> None:
    """Only the unit is the administrator's: an OFFICIAL setter sets the unit of a person whose Entra
    clearance is SECRET, since Entra's clearance is not given, so neither changed nor checked."""
    store = _Store(frozenset({"org_unit"}))
    store.rows[(TENANT, SETTER)] = _row(SETTER, seen=("OFFICIAL", "unit-1", ["P"]), set_here=(None, "unit-1", None))
    store.rows[(TENANT, PERSON)] = _row(PERSON, seen=("SECRET", None, ["R", "C"]))
    response = _put(_client(store, _admin(clearance="OFFICIAL", codes=("P",))), org_unit="unit-2")
    assert response.status_code == 200, response.text
    assert (response.json()["clearance"], response.json()["org_unit"]) == ("SECRET", "unit-2")


def test_a_person_never_signed_in_has_their_values_set() -> None:
    store = _Store()
    store.rows[(TENANT, PERSON)] = _row(PERSON)
    response = _put(_client(store, _admin()), clearance="OFFICIAL", org_unit="unit-3", receivable_handling_codes=[])
    assert response.status_code == 200, response.text
    assert response.json()["receivable_handling_codes"] == []


def test_a_value_entra_sends_is_never_given_here() -> None:
    response = _put(_client(_Store(frozenset({"clearance"})), _admin()), clearance="OFFICIAL", org_unit="unit-2")
    assert response.status_code == 409 and response.json()["error"] == "entra_holds_accounts", response.text
    assert "org_unit" in response.json()["detail"]


def test_without_the_fallback_access_is_entra_s_as_before() -> None:
    response = _put(_client(_Store(frozenset()), _admin()), clearance="OFFICIAL", org_unit="unit-2")
    assert response.status_code == 409 and response.json()["error"] == "entra_holds_accounts"


@pytest.mark.parametrize("setter", ["disabled", "nothing-set", "not-recorded"])
def test_a_setter_who_could_not_sign_in_sets_nothing(setter: str) -> None:
    store = _Store()
    if setter == "disabled":
        store.rows[(TENANT, SETTER)]["disabled"] = True
    elif setter == "nothing-set":
        store.rows[(TENANT, SETTER)] = _row(SETTER, roles=("osprey-admin",))
    else:
        store.rows[(OTHER_TENANT, SETTER)] = store.rows.pop((TENANT, SETTER))
    response = _put(_client(store, _admin()), clearance="OFFICIAL")
    assert response.status_code == 403 and response.json()["detail"]["error"] == "setter_cannot_set", response.text


def test_a_person_not_here_is_a_404() -> None:
    store = _Store()
    store.rows[(OTHER_TENANT, PERSON)] = store.rows.pop((TENANT, PERSON))
    response = _put(_client(store, _admin()), clearance="OFFICIAL")
    assert response.status_code == 404 and response.json()["error"] == "no_such_person", response.text


def test_it_is_refused_without_manage_people() -> None:
    analyst = Principal(id=SETTER, clearance="SECRET", org_unit="unit-1", roles=["analyst"])
    assert _put(_client(_Store(), analyst), clearance="OFFICIAL").status_code == 403


def test_keycloak_s_access_still_sets_clearance_and_unit_together() -> None:
    class _Keycloak:
        async def set_access(self, user_id: str, access: Any) -> Any:  # pragma: no cover - refused first
            raise AssertionError("not reached")

    app.dependency_overrides.update({get_identity_admin: _Keycloak, get_audit: _Audit, get_principal: lambda: _admin(),
                                     get_handling_scheme: load_uk_le_scheme})  # fmt: skip
    response = TestClient(app).put(f"/v1/admin/people/{PERSON}/access", json={"clearance": "OFFICIAL"})
    assert response.status_code == 422 and "clearance and a unit" in response.json()["detail"]


# --- the store's own decision, unit by unit ---


def test_the_decision_is_the_store_s_whatever_the_caller_checked() -> None:
    setter = _row(SETTER, set_here=("OFFICIAL", "unit-1", ["P"]))
    check_administrator_access(EVERY, setter, PersonAccessInput(clearance="OFFICIAL", org_unit="unit-3"), CLASSES)
    with pytest.raises(AccessBeyondTheSetter, match="above_your_clearance"):
        check_administrator_access(EVERY, setter, PersonAccessInput(clearance="SECRET"), CLASSES)
    with pytest.raises(AccessBeyondTheSetter, match="handling_code_you_do_not_hold"):
        check_administrator_access(EVERY, setter, PersonAccessInput(receivable_handling_codes=["R"]), CLASSES)
    with pytest.raises(AccessBeyondTheSetter, match="setter_cannot_set"):
        check_administrator_access(EVERY, None, PersonAccessInput(clearance="OFFICIAL"), CLASSES)


# --- the first administrators' values at install ---


def test_the_first_administrators_values_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OSPREY_FIRST_ADMINISTRATOR_ACCESS",
                       '{"clearance": "SECRET", "org_unit": "unit-1", "handling_codes": ["P"]}')  # fmt: skip
    assert first_administrator_access_from_env({"clearance", "handling_codes"}) == {"clearance": "SECRET", "handling_codes": ["P"]}
    assert first_administrator_access_from_env(()) == {}


@pytest.mark.parametrize(
    "raw", ["", '{"clearance": "SECRET"}', '{"clearance": "", "org_unit": "u", "handling_codes": []}', "not json",
            '{"clearance": "S", "org_unit": "u", "handling_codes": "P"}'],
    ids=["none", "a-field-missing", "an-empty-clearance", "not-json", "codes-not-a-list"],
)  # fmt: skip
def test_a_start_with_the_fallback_and_no_first_administrators_values_is_refused(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    """Nobody could sign in to set anyone's values, the first administrators included."""
    monkeypatch.setenv("OSPREY_FIRST_ADMINISTRATOR_ACCESS", raw)
    with pytest.raises(ValueError, match="OSPREY_FIRST_ADMINISTRATOR_ACCESS"):
        first_administrator_access_from_env(EVERY)


# --- an open socket ---


class _StandingStore:
    def __init__(self, stored: StoredPerson, by_administrator: frozenset[str] = EVERY) -> None:
        self.stored, self.by_administrator = stored, by_administrator

    async def standing(self, oid: str) -> StoredPerson:
        return self.stored


@pytest.mark.parametrize(
    ("stored", "closes"),
    [
        (StoredPerson(("analyst",), False, "OFFICIAL", "unit-1", ("P",)), False),
        (StoredPerson(("analyst",), False, "OFFICIAL-SENSITIVE", "unit-1", ("P",)), True),
        (StoredPerson(("analyst",), False, "OFFICIAL", "unit-2", ("P",)), True),
        (StoredPerson(("analyst",), False, "OFFICIAL", "unit-1", ("P", "R")), True),
    ],
    ids=["unchanged", "clearance-changed", "unit-changed", "codes-changed"],
)
def test_an_open_socket_closes_when_what_the_administrator_set_changes(stored: StoredPerson, closes: bool) -> None:
    """The socket's principal is the one resolved at connect, before custom roles and case scoping,
    which change roles and datasets alone (a ticket's too: it is `get_principal`'s, admin)."""
    raw = Principal(id=PERSON, clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"], receivable_handling_codes=["P"])
    state = type("S", (), {"people_store": _StandingStore(stored)})()
    answer = asyncio.run(_socket_standing(type("A", (), {"state": state})(), raw))
    assert (answer == 1008) is closes and (answer is None) is not closes


# --- what People is told ---


@pytest.mark.parametrize("sets", [frozenset({"clearance", "org_unit"}), frozenset()], ids=["fallback", "none"])
def test_people_is_told_which_values_are_set_here(sets: frozenset[str]) -> None:
    response = _client(_Store(sets), _admin()).get("/v1/admin/sign-in")
    assert response.status_code == 200, response.text
    assert response.json() == {"kind": "entra", "administrator_sets": sorted(sets)}
