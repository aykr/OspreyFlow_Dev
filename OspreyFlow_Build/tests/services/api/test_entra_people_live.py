"""The people store on real Postgres (`06_DECISIONS.md` ADR-148 Amendment 8): an Entra person's
roles, kept by tenant and object id, read by the resolver inside `principal_auth`'s one construction
path. A fresh schema per test, dropped after it, pass or fail.

Rule 3: every statement names the tenant, so **a row of another tenant's same object id grants
nothing** (`test_another_tenants_row_for_the_same_oid_grants_nothing`), whether it is read by the
resolver, listed in Admin › People or written by it. Rule 4: the store's read is the resolver's,
proved here end to end with a real token; the route's `manage_people` gate is
`test_entra_people.py`'s. Rule 15: the offline fake (`FakePeople`, `_Store`) is held to what this
store does: an unknown person recorded with no roles, a person already recorded not added twice, an
update of a person not recorded refused.

Synthetic values only (rule 9).
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace

import asyncpg
import pytest
from services.api.auth import PrincipalResolutionError, PrincipalResolver
from services.api.config import PostgresConfig
from services.api.entra_people import ADMIN_ROLE, EntraPeopleAdmin, EntraPeopleStore
from services.api.identity_admin import IdentityAdminRefused, PersonExistsError

from principal_auth import ClaimMapping, PrincipalLookupUnavailable, SeenPerson, ValueSource
from tests.conftest import sign_token
from tests.services.api.test_auth import _config

TENANT = "00000000-1111-4222-8333-444444444444"
OTHER_TENANT = "99999999-8888-4777-8666-555555555555"
API = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
GLASS = "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"
ISSUER = f"https://login.microsoftonline.com/{TENANT}/v2.0"
OID = "50000000-0000-4000-8000-000000000001"
NEW = "50000000-0000-4000-8000-000000000002"

MAPPING = ClaimMapping(
    tenant_id=TENANT,
    client_id=GLASS,
    clearance=ValueSource(claim="ext_clearance"),
    org_unit=ValueSource(claim="ext_unit"),
)
SEEN = SeenPerson(
    name="Synthetic Analyst",
    username="analyst@example.test",
    email=None,
    clearance="OFFICIAL",
    org_unit="unit-1",
    receivable_handling_codes=("R",),
)


@pytest.fixture
async def world() -> AsyncIterator[SimpleNamespace]:
    name = "entra_" + uuid.uuid4().hex[:10]
    base = PostgresConfig.from_env().dsn
    conn = await asyncpg.connect(dsn=base)
    await conn.execute(f'CREATE SCHEMA "{name}"')
    await conn.close()
    dsn = f"{base}?search_path={name}"
    store = await EntraPeopleStore.connect(dsn, TENANT)
    other = await EntraPeopleStore.connect(dsn, OTHER_TENANT)
    try:
        yield SimpleNamespace(store=store, other=other, dsn=dsn)
    finally:
        await store.close()
        await other.close()
        conn = await asyncpg.connect(dsn=base)
        await conn.execute(f'DROP SCHEMA "{name}" CASCADE')
        await conn.close()


def _token(keypair, **overrides: object) -> str:  # type: ignore[no-untyped-def]
    now = int(time.time())
    claims: dict[str, object] = {
        "aud": API, "iss": ISSUER, "iat": now, "nbf": now, "exp": now + 3600, "ver": "2.0",
        "tid": TENANT, "oid": OID, "azp": GLASS, "sub": "pairwise", "scp": "access_as_user",
        "ext_clearance": "OFFICIAL", "ext_unit": "unit-1", "roles": [ADMIN_ROLE],
        "name": "Synthetic Analyst", "preferred_username": "analyst@example.test",
    }  # fmt: skip
    claims.update(overrides)
    # A claim given as None is one the token does not carry (an app-only token has no `scp`).
    return sign_token(keypair[0], {k: v for k, v in claims.items() if v is not None})


def _resolver(jwks_url: str, store: EntraPeopleStore) -> PrincipalResolver:
    return PrincipalResolver(
        _config(jwks_url, oidc_issuer=ISSUER, oidc_audience=API),
        claim_mapping=MAPPING,
        role_source=store,
    )


async def test_a_first_sign_in_is_recorded_with_no_roles_and_listed(world) -> None:
    stored = await world.store.person(TENANT, OID, SEEN)
    assert (stored.roles, stored.disabled) == ((), False)
    [listed] = await world.store.rows()
    assert (listed.id, listed.username, listed.clearance, listed.roles) == (
        OID, "analyst@example.test", "OFFICIAL", []
    )  # fmt: skip
    assert listed.receivable_handling_codes == ["R"]


async def test_the_tokens_access_is_brought_up_to_date_but_never_its_roles(world) -> None:
    await world.store.person(TENANT, OID, SEEN)
    await world.store.update(OID, "roles", ["analyst"])
    changed = SeenPerson(**{**SEEN.__dict__, "clearance": "OFFICIAL-SENSITIVE"})
    stored = await world.store.person(TENANT, OID, changed)
    assert stored.roles == ("analyst",)
    assert (await world.store.one(OID)).clearance == "OFFICIAL-SENSITIVE"


async def test_another_tenants_row_for_the_same_oid_grants_nothing(
    world, keypair, jwks_url
) -> None:
    """Rule 3: the other tenant's administrator row for the very same object id is never read,
    listed or written for this tenant."""
    await world.other.seed_first_administrators([OID])
    resolver = _resolver(jwks_url, world.store)
    try:
        principal = await resolver.resolve_principal(_token(keypair))
    finally:
        await resolver.aclose()
    assert principal.roles == []
    assert [p.roles for p in await world.store.rows()] == [[]]
    await world.store.update(OID, "roles", ["analyst"])
    assert [p.roles for p in await world.other.rows()] == [[ADMIN_ROLE]]


async def test_the_resolver_reads_the_stored_roles_with_a_real_token(
    world, keypair, jwks_url
) -> None:
    await world.store.seed_first_administrators([OID])
    resolver = _resolver(jwks_url, world.store)
    try:
        assert (await resolver.resolve_principal(_token(keypair, roles=[]))).roles == [ADMIN_ROLE]
        await EntraPeopleAdmin(world.store).set_roles(OID, ["analyst"])
        # Taken away: the very next request, never a cached set.
        assert (await resolver.resolve_principal(_token(keypair))).roles == ["analyst"]
        await EntraPeopleAdmin(world.store).set_enabled(OID, False)
        with pytest.raises(PrincipalResolutionError, match="disabled"):
            await resolver.resolve_principal(_token(keypair))
    finally:
        await resolver.aclose()


async def test_a_store_that_cannot_answer_is_unavailable_never_no_roles(
    world, keypair, jwks_url
) -> None:
    await world.store.seed_first_administrators([OID])
    resolver = _resolver(jwks_url, world.store)
    await world.store.pool.close()
    try:
        with pytest.raises(PrincipalLookupUnavailable):
            await resolver.resolve_principal(_token(keypair))
    finally:
        await resolver.aclose()
        world.store.pool = await asyncpg.create_pool(dsn=world.dsn, min_size=1, max_size=1)


OTHER_ADMIN = "50000000-0000-4000-8000-000000000003"


async def _a_signed_in_administrator(world) -> None:  # type: ignore[no-untyped-def]
    """Someone else who can manage people: Admin, enabled, and signed in at least once."""
    await world.store.person(TENANT, OTHER_ADMIN, SEEN)
    await world.store.update(OTHER_ADMIN, "roles", [ADMIN_ROLE])


async def test_first_administrators_are_seeded_once_and_a_removal_stands(world) -> None:
    """While someone else can manage people, a named first administrator's Admin taken away stands
    at the next start, and the start gives nothing."""
    assert await world.store.seed_first_administrators([OID]) == [OID]
    await _a_signed_in_administrator(world)
    await world.store.update(OID, "roles", ["analyst"])
    assert await world.store.seed_first_administrators([OID]) == []
    assert (await world.store.one(OID)).roles == ["analyst"]


async def test_adding_by_object_id_once_and_the_refusals_the_fakes_model(world) -> None:
    added = await world.store.add(NEW, "adm-1")
    assert (added.id, added.roles, added.enabled) == (NEW, [], True)
    with pytest.raises(PersonExistsError):
        await world.store.add(NEW, "adm-1")
    with pytest.raises(IdentityAdminRefused):
        await world.store.update("50000000-0000-4000-8000-0000000000ff", "roles", ["analyst"])
    with pytest.raises(IdentityAdminRefused):
        await world.other.update(NEW, "roles", ["analyst"])


async def test_the_store_refuses_a_read_for_another_tenant(world) -> None:
    with pytest.raises(IdentityAdminRefused):
        await world.store.person(OTHER_TENANT, OID, SEEN)
    assert await world.store.rows() == []


async def test_the_sockets_read_is_this_tenants_and_records_nobody(world) -> None:
    """`standing`, which an open delta socket asks before each message: the stored roles and flag,
    another tenant's same object id never read (rule 3), and nobody recorded by asking."""
    await world.other.seed_first_administrators([OID])
    assert await world.store.standing(OID) is None
    assert await world.store.rows() == []
    await world.store.seed_first_administrators([OID])
    await EntraPeopleAdmin(world.store).set_enabled(OID, False)
    stored = await world.store.standing(OID)
    assert stored is not None and (stored.roles, stored.disabled) == ((ADMIN_ROLE,), True)


async def test_when_nobody_can_manage_people_the_named_first_administrators_get_admin_again(
    world,
) -> None:
    """The way back in (the orchestrator's ruling, amended 12 November 2026): only when nobody can
    manage people does a start give each named first administrator Admin again, added to what they
    hold. While someone else can, a named person's roles cleared on purpose stand."""
    await world.store.seed_first_administrators([OID])
    await _a_signed_in_administrator(world)
    await world.store.update(OID, "roles", [])
    assert await world.store.seed_first_administrators([OID]) == []
    assert (await world.store.one(OID)).roles == []
    await world.store.update(OTHER_ADMIN, "roles", ["analyst"])  # now nobody can
    await world.store.update(OID, "roles", ["analyst"])
    assert await world.store.seed_first_administrators([OID]) == [OID]
    assert (await world.store.one(OID)).roles == ["analyst", ADMIN_ROLE]
    assert await world.store.seed_first_administrators([OID]) == []


async def test_each_admin_role_a_start_gives_is_audited(world, monkeypatch) -> None:
    """`open_people_store` at start: the install's grant and a way back in each write an audit row
    (`grant_first_administrator`), naming the person; a start that gives nothing writes none."""
    from services.api.audit import AuditWriter
    from services.api.entra_people import open_people_store

    monkeypatch.setenv("OSPREY_FIRST_ADMINISTRATORS", OID)
    audit = await AuditWriter.connect(world.dsn)
    try:
        for _ in range(2):
            store = await open_people_store(world.dsn, MAPPING, audit)
            assert store is not None
            await store.close()
        await world.store.update(OID, "roles", [])
        store = await open_people_store(world.dsn, MAPPING, audit)
        assert store is not None
        await store.close()
        conn = await asyncpg.connect(dsn=world.dsn)
        try:
            rows = await conn.fetch(
                "SELECT principal_id, resolved_query FROM audit_log "
                "WHERE action = 'grant_first_administrator' ORDER BY id"
            )
        finally:
            await conn.close()
    finally:
        await audit.close()
    assert [(r["principal_id"], json.loads(r["resolved_query"])["user_id"]) for r in rows] == [
        ("first-administrators", OID),
        ("first-administrators", OID),
    ]


async def test_a_grant_is_never_kept_without_its_audit_row(world) -> None:
    """The third review's should-fix 3: the start's grant and its audit row are one transaction on
    one connection, so an audit write that fails takes the grant back with it."""
    from services.api.audit import AuditWriteError
    from services.api.identity_admin import IdentityAdminRefused

    class _Failing:
        async def record(self, **kwargs: object) -> None:
            raise AuditWriteError("audit write failed for action 'grant_first_administrator'")

    with pytest.raises(AuditWriteError):
        await world.store.seed_first_administrators([OID], _Failing())  # type: ignore[arg-type]
    with pytest.raises(IdentityAdminRefused):
        await world.store.one(OID)


async def test_a_start_waits_for_the_people_lock(world) -> None:
    """The seed runs under `PEOPLE_LOCK` (the lock every change that could leave nobody able to
    manage people takes): while another session holds it, the seed does not finish."""
    import asyncio

    from services.api.custom_roles import PEOPLE_LOCK

    holder = await asyncpg.connect(dsn=world.dsn)
    try:
        await holder.execute("SELECT pg_advisory_lock($1)", PEOPLE_LOCK)
        seeding = asyncio.create_task(world.store.seed_first_administrators([OID]))
        await asyncio.sleep(1.0)
        assert not seeding.done(), "the seed ran while another held PEOPLE_LOCK"
        await holder.execute("SELECT pg_advisory_unlock($1)", PEOPLE_LOCK)
        assert await asyncio.wait_for(seeding, timeout=10) == [OID]
    finally:
        await holder.close()


async def test_a_custom_role_that_manages_people_counts_at_the_start(world) -> None:
    """The custom roles' rights are read inside the lock: someone signed in who manages people by a
    custom role is someone who can administer, so a named first administrator's cleared roles
    stand."""
    from services.api.custom_roles import CustomRoleStore

    from schemas.rights import CUSTOM_ROLE_PREFIX, Right

    roles = await CustomRoleStore.connect(world.dsn)
    try:
        role = await roles.create("People leads", [Right.MANAGE_PEOPLE], by="adm-1")
    finally:
        await roles.close()
    await world.store.seed_first_administrators([OID])
    await world.store.person(TENANT, OTHER_ADMIN, SEEN)
    await world.store.update(OTHER_ADMIN, "roles", [f"{CUSTOM_ROLE_PREFIX}{role.id}"])
    await world.store.update(OID, "roles", [])
    assert await world.store.seed_first_administrators([OID]) == []
    assert (await world.store.one(OID)).roles == []


async def _read_back(world, hours: float) -> object:  # type: ignore[no-untyped-def]
    conn = await asyncpg.connect(dsn=world.dsn)
    try:
        await conn.execute(
            "UPDATE entra_people SET access_read_at = now() - make_interval(secs => $2) "
            "WHERE tenant_id = $1",
            TENANT,
            hours * 3600,
        )
        before = await conn.fetchval("SELECT access_read_at FROM entra_people WHERE oid = $1", OID)
        await world.store.person(TENANT, OID, SEEN)
        after = await conn.fetchval("SELECT access_read_at FROM entra_people WHERE oid = $1", OID)
    finally:
        await conn.close()
    return before, after


@pytest.mark.parametrize(("hours", "refreshed"), [(2.0, True), (0.5, False)], ids=["2h", "30min"])
async def test_access_read_at_is_refreshed_at_most_hourly(world, hours, refreshed) -> None:
    """The second review's must-fix 2: a sign-in with the same access records when it was read
    again once the last record is over an hour old, and writes nothing inside the hour."""
    await world.store.person(TENANT, OID, SEEN)
    before, after = await _read_back(world, hours)
    assert (after != before) is refreshed


async def test_one_person_is_read_by_this_tenant_alone(world) -> None:
    """Rule 3 for `one`: another tenant's row for the same object id is not this tenant's person."""
    await world.other.seed_first_administrators([OID])
    with pytest.raises(IdentityAdminRefused):
        await world.store.one(OID)


async def test_a_sign_in_records_when_access_was_read_and_an_added_person_has_not_signed_in(
    world,
) -> None:
    """What the lock-out and the stale-access rulings read: `signed_in` and `access_read_at`."""
    await world.store.add(NEW, "adm-1")
    added = await world.store.one(NEW)
    assert added.signed_in is False and added.access_read_at is not None
    await world.store.person(TENANT, OID, SEEN)
    seen = await world.store.one(OID)
    assert seen.signed_in is True and seen.access_read_at is not None
    assert seen.access_read_at > added.access_read_at


async def test_a_conduit_starting_waits_for_the_bootstrap_lock(world) -> None:
    """`BOOTSTRAP_SQL` runs under a transaction-scoped advisory lock, so two Conduits starting
    together make the table once. Shown deterministically (note 9 of the second review): while
    another session holds the lock, `connect` does not finish; once it is let go, it does. Two
    connects racing would show nothing reliably: the race the lock prevents may simply not happen."""
    import asyncio

    from services.api.entra_people import BOOTSTRAP_LOCK

    holder = await asyncpg.connect(dsn=world.dsn)
    try:
        await holder.execute("SELECT pg_advisory_lock($1)", BOOTSTRAP_LOCK)
        starting = asyncio.create_task(EntraPeopleStore.connect(world.dsn, TENANT))
        await asyncio.sleep(1.0)
        assert not starting.done(), "connect ran its bootstrap while another held the lock"
        await holder.execute("SELECT pg_advisory_unlock($1)", BOOTSTRAP_LOCK)
        store = await asyncio.wait_for(starting, timeout=10)
        await store.close()
    finally:
        await holder.close()


# --- ADR-148 Amendment 10: dashboard identities, in the same store ------------------------------

DASHBOARD = "dddddddd-eeee-4fff-8000-111111111111"


async def test_a_dashboard_identity_is_registered_read_listed_and_removed(world) -> None:
    from services.api.identity_admin import DashboardExistsError

    from principal_auth import StoredDashboard

    await world.store.register_dashboard(
        DASHBOARD, "compliance-board", clearance="OFFICIAL-SENSITIVE", org_unit="unit-2"
    )
    wanted = StoredDashboard(DASHBOARD, "OFFICIAL-SENSITIVE", "unit-2", ("P",), "compliance-board")
    assert await world.store.dashboard(TENANT, DASHBOARD) == wanted
    assert await world.store.dashboards() == [wanted]
    # Bound to its tenant: the other tenant's store sees none, and this one answers for no other.
    assert await world.other.dashboard(OTHER_TENANT, DASHBOARD) is None
    assert await world.store.dashboard(OTHER_TENANT, DASHBOARD) is None
    with pytest.raises(DashboardExistsError):
        await world.store.register_dashboard(DASHBOARD, "again", clearance="OFFICIAL", org_unit="u")
    # UNIQUE (tenant_id, name): another application id of the same name is refused, the same 409;
    # the other tenant may use the name.
    with pytest.raises(DashboardExistsError):
        await world.store.register_dashboard(
            "ffffffff-0000-4111-8222-333333333333", "compliance-board",
            clearance="OFFICIAL", org_unit="u",
        )  # fmt: skip
    await world.other.register_dashboard(
        "ffffffff-0000-4111-8222-333333333333", "compliance-board", clearance="OFFICIAL",
        org_unit="u",
    )  # fmt: skip
    assert [d.application_id for d in await world.store.dashboards()] == [DASHBOARD]
    # A name not slug-shaped never reaches the table (the admin slugs it first).
    with pytest.raises(ValueError, match="name"):
        await world.store.register_dashboard(
            "aaaaaaaa-0000-4111-8222-333333333333", "Compliance board", clearance="OFFICIAL",
            org_unit="u",
        )  # fmt: skip
    assert await world.store.remove_dashboard(DASHBOARD) is True
    assert await world.store.dashboard(TENANT, DASHBOARD) is None
    assert await world.store.remove_dashboard(DASHBOARD) is False


async def test_the_resolver_reads_a_registered_dashboard_with_a_real_token(
    world, keypair, jwks_url
) -> None:
    from principal_auth import DASHBOARD_APP_ROLE, DASHBOARD_ROUTES

    await world.store.register_dashboard(
        DASHBOARD, "compliance-board", clearance="OFFICIAL", org_unit="unit-2"
    )
    resolver = PrincipalResolver(
        _config(jwks_url, oidc_issuer=ISSUER, oidc_audience=API),
        claim_mapping=MAPPING, role_source=world.store, dashboard_source=world.store,
    )  # fmt: skip
    token = _token(keypair, azp=DASHBOARD, oid="60000000-0000-4000-8000-000000000001",
                   idtyp="app", scp=None, roles=[DASHBOARD_APP_ROLE])  # fmt: skip
    principal = await resolver.resolve_principal(token)
    assert (principal.id, principal.clearance) == (DASHBOARD, "OFFICIAL")
    assert principal.org_unit == "unit-2"
    assert principal.roles == ["reports_viewer"] and set(principal.routes or ()) == DASHBOARD_ROUTES


# --- ADR-148 Amendment 16: a run acting as its owner, against the real store --------------------


async def test_a_run_acts_as_its_owner_as_the_store_holds_them(world) -> None:  # type: ignore[no-untyped-def]
    """The real store's `owner` and the real resolver: the access the last sign-in recorded, the
    roles as Admin › People holds them now, read without recording anyone; the other tenant's row
    for the same object id is never this tenant's owner; an owner whose access is a day old, or who
    was added and never signed in, is out of date; one disabled here is revoked."""
    from principal_auth import PrincipalAccessOutOfDate, PrincipalExchangeRefused, PrincipalRevoked

    resolver = _resolver("http://127.0.0.1:9/keys", world.store)
    try:
        await world.other.person(OTHER_TENANT, OID, SEEN)  # another tenant's row, same oid
        with pytest.raises(PrincipalExchangeRefused):
            await resolver.resolve_for_owner_detailed(OID)
        await world.store.person(TENANT, OID, SEEN)
        await world.store.update(OID, "roles", ["analyst", "source_author"])
        owner = await resolver.resolve_for_owner_detailed(OID)
        assert (owner.id, owner.clearance, owner.org_unit, owner.receivable_handling_codes, owner.roles) == (
            OID, "OFFICIAL", "unit-1", ["R"], ["analyst", "source_author"]
        )  # fmt: skip
        assert len(await world.store.rows()) == 1  # nobody recorded by the read

        await world.store.add(NEW, "adm-1")  # added by object id, never signed in
        with pytest.raises(PrincipalAccessOutOfDate):
            await resolver.resolve_for_owner_detailed(NEW)

        conn = await asyncpg.connect(dsn=world.dsn)
        try:
            await conn.execute("UPDATE entra_people SET access_read_at = now() - interval '25 hours' "
                               "WHERE tenant_id = $1 AND oid = $2", TENANT, OID)  # fmt: skip
        finally:
            await conn.close()
        with pytest.raises(PrincipalAccessOutOfDate):
            await resolver.resolve_for_owner_detailed(OID)

        await EntraPeopleAdmin(world.store).set_enabled(OID, False)
        with pytest.raises(PrincipalRevoked):
            await resolver.resolve_for_owner_detailed(OID)
    finally:
        await resolver.aclose()


async def test_the_store_refuses_an_owner_read_for_another_tenant(world) -> None:  # type: ignore[no-untyped-def]
    """As `person` does: a store wired to the wrong tenant is a fault, never every owner "not held"."""
    await world.store.person(TENANT, OID, SEEN)
    with pytest.raises(IdentityAdminRefused):
        await world.store.owner(OTHER_TENANT, OID)
    held = await world.store.owner(TENANT, OID)
    assert held is not None and (held.clearance, held.org_unit) == ("OFFICIAL", "unit-1")


# --- ADR-148 Amendment 17: guests, against the real store -----------------------------------------


async def test_guests_are_off_until_set_and_each_change_answers_what_it_was(world) -> None:  # type: ignore[no-untyped-def]
    assert await world.store.guests_admitted(TENANT) is False
    assert await world.store.guest_sign_in() == (False, None, None)
    assert await world.store.set_guests_admitted(True, "adm-1") is False
    assert await world.store.guests_admitted(TENANT) is True
    admitted, by, at = await world.store.guest_sign_in()
    assert (admitted, by) == (True, "adm-1") and at is not None
    assert await world.store.set_guests_admitted(False, "adm-2") is True
    # Another tenant's store has its own setting, and this store refuses to be asked for another.
    assert await world.other.guests_admitted(OTHER_TENANT) is False
    with pytest.raises(IdentityAdminRefused):
        await world.store.guests_admitted(OTHER_TENANT)


async def test_a_guest_is_recorded_as_one_and_stands_disabled_once_guests_are_no_longer_admitted(
    world,
) -> None:  # type: ignore[no-untyped-def]
    from dataclasses import replace

    await world.store.set_guests_admitted(True, "adm-1")
    await world.store.person(TENANT, OID, replace(SEEN, guest=True))
    await world.store.person(TENANT, NEW, SEEN)
    assert (await world.store.one(OID)).guest is True and (await world.store.one(NEW)).guest is False
    assert (await world.store.standing(OID)).disabled is False  # type: ignore[union-attr]
    held = await world.store.owner(TENANT, OID)
    assert held is not None and held.guest is True
    await world.store.set_guests_admitted(False, "adm-1")
    assert (await world.store.standing(OID)).disabled is True  # type: ignore[union-attr]
    assert (await world.store.standing(NEW)).disabled is False  # type: ignore[union-attr]
    # A sign-in as a member (the same object id, a token without guest claims) records them as one.
    await world.store.person(TENANT, OID, SEEN)
    assert (await world.store.one(OID)).guest is False


async def test_the_resolver_refuses_a_guest_until_the_real_store_admits_guests(
    world, keypair, jwks_url
) -> None:  # type: ignore[no-untyped-def]
    resolver = _resolver(jwks_url, world.store)
    guest = _token(keypair, acct=1)
    with pytest.raises(PrincipalResolutionError, match="guest"):
        await resolver.resolve_principal(guest)
    assert await world.store.rows() == []  # nothing recorded of a refused guest
    await world.store.set_guests_admitted(True, "adm-1")
    principal = await resolver.resolve_principal(guest)
    assert (principal.id, principal.clearance, principal.org_unit) == (OID, "OFFICIAL", "unit-1")
    assert (await world.store.one(OID)).guest is True
    await resolver.aclose()
