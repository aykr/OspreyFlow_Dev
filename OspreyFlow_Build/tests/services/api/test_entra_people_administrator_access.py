"""Admin › People's Access on Entra ID for the values the claim mapping sources from the administrator
(`06_DECISIONS.md` ADR-148 Amendment 15; the audit's ruling 4c), through the real route.

The people store's limits are the store's own (rule 3): no clearance above, and no handling code beyond,
what the setter holds **as the store holds them**, whatever the setter's token or the route's own check
says. The store here keeps rows as the real one does (by tenant and object id) and decides with the real
store's `check_administrator_access`; `test_entra_people_live.py` holds the real table to the same, its
transaction, its columns and a sign-in that never overwrites what was set. Synthetic values only (rule 9).
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
from services.api.entra_people import AccessBeyondTheSetter, EntraPeopleAdmin, check_administrator_access
from services.api.identity_admin import IdentityAdminRefused

from ontology.handling import load_uk_le_scheme
from principal_auth import StoredPerson
from schemas.admin import AccessInput, PersonAccount
from schemas.domain import Principal

TENANT = "00000000-1111-4222-8333-444444444444"
OTHER_TENANT = "99999999-8888-4777-8666-555555555555"
SETTER = "50000000-0000-4000-8000-000000000001"
PERSON = "50000000-0000-4000-8000-000000000002"
EVERY = frozenset({"clearance", "org_unit", "handling_codes"})
CLASSES = list(load_uk_le_scheme().classification)


def _row(oid: str, clearance: str | None, unit: str | None, codes: list[str] | None, roles: list[str] = ()) -> PersonAccount:  # type: ignore[assignment]
    return PersonAccount(id=oid, username=oid, name=oid, enabled=True, roles=list(roles), clearance=clearance,
                         org_unit=unit, receivable_handling_codes=list(codes or []), signed_in=True)  # fmt: skip


class _Store:
    """The people store as the Access route reaches it: rows by (tenant, object id), the real store's
    decision (`check_administrator_access`) inside, another tenant's rows never read."""

    def __init__(self, by_administrator: frozenset[str] = EVERY) -> None:
        self.tenant_id = TENANT
        self.by_administrator = by_administrator
        self.people: dict[tuple[str, str], PersonAccount] = {
            (TENANT, SETTER): _row(SETTER, "OFFICIAL-SENSITIVE", "unit-1", ["P", "R"], ["osprey-admin"]),
            (TENANT, PERSON): _row(PERSON, "OFFICIAL", "unit-1", ["P"]),
        }

    async def set_administrator_access(self, oid: str, by: str, access: AccessInput, classification: Any):  # type: ignore[no-untyped-def]
        target = self.people.get((self.tenant_id, oid))
        setter = self.people.get((self.tenant_id, by))
        if target is None:
            raise IdentityAdminRefused("no such person")
        if setter is None:
            raise AccessBeyondTheSetter("above_your_clearance", {"clearance": access.clearance})
        check_administrator_access(self.by_administrator, setter, target, access, classification)
        update: dict[str, Any] = {}
        if "clearance" in self.by_administrator:
            update["clearance"] = access.clearance
        if "org_unit" in self.by_administrator:
            update["org_unit"] = access.org_unit
        if "handling_codes" in self.by_administrator:
            update["receivable_handling_codes"] = list(access.receivable_handling_codes)
        after = target.model_copy(update=update)
        self.people[(self.tenant_id, oid)] = after
        return target, after


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


def _access(clearance: str = "OFFICIAL-SENSITIVE", unit: str = "unit-2", codes: tuple[str, ...] = ("R",)) -> dict[str, Any]:
    return {"clearance": clearance, "org_unit": unit, "receivable_handling_codes": list(codes)}


# --- through the route ---


def test_an_administrator_sets_the_values_within_their_own_and_it_is_audited() -> None:
    store = _Store()
    client = _client(store, _admin())
    response = client.put(f"/v1/admin/people/{PERSON}/access", json=_access())
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["clearance"], body["org_unit"], body["receivable_handling_codes"]) == ("OFFICIAL-SENSITIVE", "unit-2", ["R"])
    (record,) = client.audit.records  # type: ignore[attr-defined]
    assert record["action"] == "set_person_access" and record["principal"].id == SETTER
    query = record["resolved_query"]
    assert query["before"] == {"clearance": "OFFICIAL", "org_unit": "unit-1", "receivable_handling_codes": ["P"]}
    assert query["after"] == {"clearance": "OFFICIAL-SENSITIVE", "org_unit": "unit-2", "receivable_handling_codes": ["R"]}
    assert query["by_administrator"] == ["clearance", "handling_codes", "org_unit"]


def test_the_store_refuses_a_clearance_above_the_setter_s_own_as_it_holds_them() -> None:
    """Rule 3: the setter's token says SECRET, so the route's own check passes; the store holds them
    at OFFICIAL-SENSITIVE, and refuses SECRET. A check in the route alone would have set it."""
    store = _Store()
    client = _client(store, _admin(clearance="SECRET"))
    response = client.put(f"/v1/admin/people/{PERSON}/access", json=_access(clearance="SECRET"))
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["error"] == "above_your_clearance"
    assert store.people[(TENANT, PERSON)].clearance == "OFFICIAL"
    assert client.audit.records == []  # type: ignore[attr-defined]


def test_the_store_refuses_a_code_beyond_the_setter_s_own_as_it_holds_them() -> None:
    store = _Store()
    client = _client(store, _admin(codes=("P", "R", "C")))
    response = client.put(f"/v1/admin/people/{PERSON}/access", json=_access(codes=("C",)))
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == {"error": "handling_code_you_do_not_hold", "codes": ["C"]}


def test_a_value_entra_sends_is_not_changed_here() -> None:
    """Only the clearance is the administrator's: a changed unit is Entra's and refused, the same
    unit as now is accepted with the clearance."""
    store = _Store(frozenset({"clearance"}))
    client = _client(store, _admin())
    refused = client.put(f"/v1/admin/people/{PERSON}/access", json=_access(unit="unit-2", codes=("P",)))
    assert refused.status_code == 409 and refused.json()["error"] == "entra_holds_accounts", refused.text
    accepted = client.put(f"/v1/admin/people/{PERSON}/access", json=_access(unit="unit-1", codes=("P",)))
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["clearance"] == "OFFICIAL-SENSITIVE"


def test_without_the_fallback_access_is_entra_s_as_before() -> None:
    client = _client(_Store(frozenset()), _admin())
    response = client.put(f"/v1/admin/people/{PERSON}/access", json=_access())
    assert response.status_code == 409 and response.json()["error"] == "entra_holds_accounts"


def test_another_tenant_s_rows_grant_nothing() -> None:
    """The setter recorded only in another tenant holds nothing here; a person only there is no one."""
    store = _Store()
    store.people[(OTHER_TENANT, SETTER)] = store.people.pop((TENANT, SETTER))
    client = _client(store, _admin())
    assert client.put(f"/v1/admin/people/{PERSON}/access", json=_access()).status_code == 403
    store = _Store()
    store.people[(OTHER_TENANT, PERSON)] = store.people.pop((TENANT, PERSON))
    response = _client(store, _admin()).put(f"/v1/admin/people/{PERSON}/access", json=_access())
    assert response.status_code in (404, 409, 502), response.text
    assert (TENANT, PERSON) not in store.people


def test_it_is_refused_without_manage_people() -> None:
    analyst = Principal(id=SETTER, clearance="SECRET", org_unit="unit-1", roles=["analyst"])
    assert _client(_Store(), analyst).put(f"/v1/admin/people/{PERSON}/access", json=_access()).status_code == 403


# --- the store's own decision, unit by unit ---


def test_the_decision_is_the_store_s_whatever_the_caller_checked() -> None:
    setter = _row(SETTER, "OFFICIAL", "unit-1", ["P"])
    before = _row(PERSON, "OFFICIAL", "unit-1", ["P"])
    check_administrator_access(EVERY, setter, before, AccessInput(**_access("OFFICIAL", "unit-3", ("P",))), CLASSES)
    with pytest.raises(AccessBeyondTheSetter, match="above_your_clearance"):
        check_administrator_access(EVERY, setter, before, AccessInput(**_access("SECRET", "unit-3", ())), CLASSES)
    with pytest.raises(AccessBeyondTheSetter, match="above_your_clearance"):
        check_administrator_access(EVERY, _row(SETTER, None, None, None), before, AccessInput(**_access("OFFICIAL")), CLASSES)
    with pytest.raises(AccessBeyondTheSetter, match="handling_code_you_do_not_hold"):
        check_administrator_access(EVERY, setter, before, AccessInput(**_access("OFFICIAL", codes=("R",))), CLASSES)


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
    raw = Principal(id=PERSON, clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"], receivable_handling_codes=["P"])
    state = type("S", (), {"people_store": _StandingStore(stored)})()
    answer = asyncio.run(_socket_standing(type("A", (), {"state": state})(), raw))
    assert (answer == 1008) is closes and (answer is None) is not closes
