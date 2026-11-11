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
    return sign_token(keypair[0], claims)


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


async def test_first_administrators_are_seeded_once_and_a_removal_stands(world) -> None:
    await world.store.seed_first_administrators([OID])
    await world.store.update(OID, "roles", ["analyst"])
    await world.store.seed_first_administrators([OID])
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
