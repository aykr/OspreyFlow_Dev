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
import re
from datetime import UTC, datetime
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
from services.api.custom_roles import people_managers
from services.api.entra_people import (
    AccessBeyondTheSetter,
    EntraPeopleAdmin,
    NoSuchPerson,
    _held,
    _person,
    EntraPeopleStore,
    access_current,
    check_administrator_access,
    open_people_store,
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


def test_an_access_that_sets_nothing_is_refused_and_writes_nothing() -> None:
    """Round 2's could 10: no "set by", and no audit row whose before equals its after."""
    store = _Store()
    client = _client(store, _admin())
    before = dict(store.rows[(TENANT, PERSON)])
    response = client.put(f"/v1/admin/people/{PERSON}/access", json={})
    assert response.status_code == 422 and "at least one" in response.json()["detail"], response.text
    assert store.rows[(TENANT, PERSON)] == before and client.audit.records == []  # type: ignore[attr-defined]


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


@pytest.mark.parametrize(
    "set_here", [(None, None, None), ("OFFICIAL", None, ["P"]), ("OFFICIAL", "unit-1", None)],
    ids=["nothing-set", "the-unit-unset", "the-codes-unset"],
)  # fmt: skip
def test_a_person_with_a_value_unset_is_stale_and_counts_as_no_manager(set_here: tuple[Any, Any, Any]) -> None:
    """Refused at sign-in after being recorded, so never signed in: nothing is sent to them (stale),
    and no lock-out check counts them among those who manage people, every route's included, since
    every route's people come through `_person` (round 2's should-fix 3 and 8)."""
    row = _row(PERSON, set_here=set_here, roles=("osprey-admin",)) | {"first_seen": datetime.now(UTC)}
    person = _person(row, EVERY)
    assert person.signed_in is False and access_current(person) is False
    assert people_managers([person], {}) == []
    # Every value set: they sign in, are current, and do manage people.
    whole = _person(row | {"admin_clearance": "OFFICIAL", "admin_org_unit": "unit-1", "admin_codes": []}, EVERY)
    assert whole.signed_in and access_current(whole) and people_managers([whole], {}) == [PERSON]


# --- the first administrators' values at install ---


def test_the_first_administrators_values_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OSPREY_FIRST_ADMINISTRATOR_ACCESS",
                       '{"clearance": "SECRET", "org_unit": "unit-1", "handling_codes": ["P"]}')  # fmt: skip
    assert first_administrator_access_from_env({"clearance", "handling_codes"}) == {"clearance": "SECRET", "handling_codes": ["P"]}
    assert first_administrator_access_from_env(()) == {}


@pytest.mark.parametrize(
    ("raw", "says"),
    [
        ("", "gives the first administrators no clearance, handling_codes, org_unit"),
        ('{"clearance": "SECRET"}', "gives the first administrators no handling_codes, org_unit"),
        # The presence check's own case: every other check would pass a missing list's absence
        # only by refusing it as "not a list", in other words.
        ('{"clearance": "SECRET", "org_unit": "u"}', "gives the first administrators no handling_codes:"),
        ('{"clearance": "", "org_unit": "u", "handling_codes": []}', "clearance is not a value"),
        ("not json", "is not JSON"),
        ('{"clearance": "S", "org_unit": "u", "handling_codes": "P"}', "handling_codes is a list of codes"),
    ],
    ids=["none", "two-fields-missing", "the-codes-missing", "an-empty-clearance", "not-json", "codes-not-a-list"],
)  # fmt: skip
def test_a_start_with_the_fallback_and_no_first_administrators_values_is_refused(
    monkeypatch: pytest.MonkeyPatch, raw: str, says: str
) -> None:
    """Nobody could sign in to set anyone's values, the first administrators included. Each case
    matches its own refusal's words, so a case refused by another branch fails (rule 15)."""
    monkeypatch.setenv("OSPREY_FIRST_ADMINISTRATOR_ACCESS", raw)
    with pytest.raises(ValueError, match=re.escape(says)):
        first_administrator_access_from_env(EVERY)


@pytest.mark.parametrize(
    ("raw", "says"),
    [
        ('{"clearance": "SECERT", "org_unit": "u", "handling_codes": ["P"]}', "clearance 'SECERT' is not a classification"),
        ('{"clearance": "SECRET", "org_unit": "u", "handling_codes": ["P", "Q9"]}', "handling codes Q9 are not this deployment's"),
    ],
    ids=["a-clearance-the-scheme-does-not-know", "a-code-the-scheme-does-not-know"],
)  # fmt: skip
def test_a_first_administrators_value_the_scheme_does_not_know_is_refused_at_start(
    monkeypatch: pytest.MonkeyPatch, raw: str, says: str
) -> None:
    """Seeded only where nothing is set, a typo could never be put right from the config, and no
    Access would be within the first administrators' reach (round 2's should-fix 6)."""
    monkeypatch.setenv("OSPREY_FIRST_ADMINISTRATOR_ACCESS", raw)
    with pytest.raises(ValueError, match=re.escape(says)):
        first_administrator_access_from_env(EVERY, load_uk_le_scheme())
    # The same values with the deployment's own words pass.
    monkeypatch.setenv("OSPREY_FIRST_ADMINISTRATOR_ACCESS",
                       '{"clearance": "SECRET", "org_unit": "u", "handling_codes": ["P"]}')  # fmt: skip
    assert first_administrator_access_from_env(EVERY, load_uk_le_scheme())["clearance"] == "SECRET"


def test_the_start_seeds_the_first_administrators_values_it_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """`open_people_store` with the fallback hands the values it read, checked against the scheme, to
    the seed; dropping them there would leave the first administrators unable to sign in. The seed's
    own SQL is the live section's (`test_entra_people_live.py`, am15)."""
    from principal_auth import ClaimMapping, ValueSource

    seeded: list[tuple[list[str], Any]] = []

    class _Seeding:
        by_administrator = EVERY

        async def seed_first_administrators(self, oids: Any, audit: Any, access: Any = None) -> list[str]:
            seeded.append((list(oids), access))
            return []

        async def close(self) -> None:
            pass

    async def connect(dsn: str, tenant: str, by_administrator: Any) -> _Seeding:
        assert set(by_administrator) == EVERY
        return _Seeding()

    monkeypatch.setattr(EntraPeopleStore, "connect", staticmethod(connect))
    monkeypatch.setenv("OSPREY_FIRST_ADMINISTRATORS", SETTER)
    monkeypatch.setenv("OSPREY_FIRST_ADMINISTRATOR_ACCESS",
                       '{"clearance": "SECRET", "org_unit": "unit-1", "handling_codes": ["P"]}')  # fmt: skip
    mapping = ClaimMapping(tenant_id=TENANT, client_id="00000000-0000-4000-8000-0000000000c1",
                           clearance=ValueSource(administrator=True), org_unit=ValueSource(administrator=True),
                           handling_codes={"administrator": True})  # type: ignore[arg-type]  # fmt: skip
    asyncio.run(open_people_store("postgresql://unused", mapping, _Audit(), load_uk_le_scheme()))  # type: ignore[arg-type]
    assert seeded == [([SETTER], {"clearance": "SECRET", "org_unit": "unit-1", "handling_codes": ["P"]})]
    # A clearance the scheme does not know stops the start before anything is seeded.
    monkeypatch.setenv("OSPREY_FIRST_ADMINISTRATOR_ACCESS",
                       '{"clearance": "SECERT", "org_unit": "unit-1", "handling_codes": ["P"]}')  # fmt: skip
    with pytest.raises(ValueError, match="not a classification"):
        asyncio.run(open_people_store("postgresql://unused", mapping, _Audit(), load_uk_le_scheme()))  # type: ignore[arg-type]
    assert len(seeded) == 1


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


# --- a run acting as its owner, with values set here (Amendment 16 meets Amendment 15) ----------


def _owner_resolver(sets: frozenset[str], row: dict[str, Any]) -> Any:
    """The real resolver's `_stored_owner`, over a store whose `owner` is the real `_owner` on a row of
    `entra_people` as the table holds it (rule 15: the store's own decision, not a stand-in's)."""
    from principal_auth import ClaimMapping, PrincipalResolver, ValueSource
    from services.api.entra_people import _owner
    from tests.services.api.test_auth_entra_claims import TENANT as CLAIMS_TENANT
    from tests.services.api.test_auth_entra_claims import _entra_config

    source = lambda field: ValueSource(administrator=True) if field in sets else ValueSource(claim=f"ext_{field}")  # noqa: E731
    codes = {"administrator": True} if "handling_codes" in sets else {"claim": "ext_codes"}
    mapping = ClaimMapping(tenant_id=CLAIMS_TENANT, client_id="00000000-0000-4000-8000-0000000000c1",
                           clearance=source("clearance"), org_unit=source("org_unit"), handling_codes=codes)  # type: ignore[arg-type]  # fmt: skip

    class _Owners:
        async def owner(self, tenant_id: str, oid: str) -> Any:
            return _owner(row, sets)

    return PrincipalResolver(_entra_config("http://127.0.0.1:9/keys"), claim_mapping=mapping, role_source=_Owners(),
                             role_lookup_timeout_seconds=0.5)  # fmt: skip


def _owner_row(*, set_here: tuple[Any, Any, Any], seen: tuple[Any, Any, Any] = (None, None, []), read_hours_ago: float | None = None) -> dict[str, Any]:
    from datetime import timedelta

    read = None if read_hours_ago is None else datetime.now(UTC) - timedelta(hours=read_hours_ago)
    return {"roles": ["analyst"], "disabled": False, "clearance": seen[0], "org_unit": seen[1], "receivable_handling_codes": seen[2],
            "admin_clearance": set_here[0], "admin_org_unit": set_here[1], "admin_codes": set_here[2], "access_read_at": read}  # fmt: skip


def test_a_run_acts_with_every_value_set_here_and_they_never_age() -> None:
    """The token's columns stay empty under the fallback, and an owner who never signed in has no time:
    a run still acts with the values Access set, which do not age."""
    row = _owner_row(set_here=("SECRET", "unit-7", ["P", "R"]), read_hours_ago=None)
    owner = asyncio.run(_owner_resolver(EVERY, row).resolve_for_owner_detailed(SETTER))
    assert (owner.clearance, owner.org_unit, owner.receivable_handling_codes, owner.roles) == ("SECRET", "unit-7", ["P", "R"], ["analyst"])


def test_a_partial_fallback_takes_the_value_set_here_and_the_token_s_others_within_the_day() -> None:
    sets = frozenset({"clearance"})
    fresh = _owner_row(set_here=("SECRET", None, None), seen=("PUBLIC", "unit-1", ["R"]), read_hours_ago=2)
    owner = asyncio.run(_owner_resolver(sets, fresh).resolve_for_owner_detailed(SETTER))
    assert (owner.clearance, owner.org_unit, owner.receivable_handling_codes) == ("SECRET", "unit-1", ["R"])
    from principal_auth import PrincipalAccessOutOfDate

    stale = _owner_row(set_here=("SECRET", None, None), seen=("PUBLIC", "unit-1", ["R"]), read_hours_ago=25)
    with pytest.raises(PrincipalAccessOutOfDate):
        asyncio.run(_owner_resolver(sets, stale).resolve_for_owner_detailed(SETTER))


@pytest.mark.parametrize(
    ("sets", "set_here"),
    [(EVERY, ("SECRET", "unit-7", None)), (EVERY, ("SECRET", None, ["P"])), (frozenset({"clearance"}), (None, None, None))],
    ids=["every-set-here-codes-unset", "every-set-here-unit-unset", "partial-its-own-value-unset"],
)  # fmt: skip
def test_a_value_set_by_the_administrator_but_not_set_yet_refuses_the_run(sets: frozenset[str], set_here: tuple[Any, Any, Any]) -> None:
    """As the person's own sign-in is refused, never acting on a token's value or on none."""
    from principal_auth import PrincipalAccessOutOfDate

    row = _owner_row(set_here=set_here, seen=("OFFICIAL", "unit-1", ["R"]), read_hours_ago=1)
    with pytest.raises(PrincipalAccessOutOfDate):
        asyncio.run(_owner_resolver(sets, row).resolve_for_owner_detailed(SETTER))


def test_a_value_not_set_here_is_said_as_such_never_as_signing_in() -> None:
    """The run's refusal names what an administrator has not set, and what happens next, never "sign in",
    which cannot help (Amendment 15 point 8). Through the real resolver and a real caller's words."""
    from principal_auth import ACCESS_OUT_OF_DATE_WORDS, OwnerValueNotSet, PrincipalAccessOutOfDate, out_of_date_next, out_of_date_words
    from services.api.list_schedule import owner_refusal_words

    row = _owner_row(set_here=("SECRET", None, None), read_hours_ago=1)
    with pytest.raises(OwnerValueNotSet) as refused:
        asyncio.run(_owner_resolver(EVERY, row).resolve_for_owner_detailed(SETTER))
    assert refused.value.unset == ("unit", "handling codes")
    said = owner_refusal_words(refused.value, SETTER)
    assert said == (f"the schedule's owner, {SETTER}, an administrator has not set unit and handling codes for this person in "
                    "Admin › People: it runs at its next slot once an administrator has set it")  # fmt: skip
    assert "sign in" not in said and "signed in" not in said
    assert out_of_date_next(refused.value, by_hand=True) == "run it again once an administrator has set it"
    # A token's values out of date are still said as before.
    stale = PrincipalAccessOutOfDate(SETTER, None)
    assert out_of_date_words(stale) == ACCESS_OUT_OF_DATE_WORDS and "sign in" in out_of_date_next(stale)


def test_a_run_asked_for_by_hand_is_told_what_to_do_in_the_refusal_s_own_words() -> None:
    from services.api.scheduler import _asked_for, _Refused

    told = _Refused("slot words", kind="owner_out_of_date", about_the_owner=False,
                    asked_for="the schedule's owner, x, an administrator has not set unit for this person in Admin › People: "
                              "run it again once an administrator has set it")  # fmt: skip
    assert _asked_for(told, None) == told.asked_for  # type: ignore[arg-type]


def test_a_guest_refused_while_guests_are_not_admitted_sets_nothing() -> None:
    """Amendment 17 meets 15 in the store (rule 3): the setter is read as every read has them, and a guest
    refused while guests are not admitted is not enabled to set anyone's values, whatever their roles."""
    setter = _row(SETTER, set_here=("OFFICIAL", "unit-1", ["P"]), roles=("osprey-admin",)) | {"guest": True, "guest_refused": True}
    with pytest.raises(AccessBeyondTheSetter, match="setter_cannot_set"):
        check_administrator_access(EVERY, setter, PersonAccessInput(clearance="OFFICIAL"), CLASSES)
    admitted = setter | {"guest_refused": False}  # guests admitted: a guest sets as anyone does
    check_administrator_access(EVERY, admitted, PersonAccessInput(clearance="OFFICIAL"), CLASSES)
