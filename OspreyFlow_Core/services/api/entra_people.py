"""Admin › People on Entra ID sign-in: the deployment's own record of each person's roles
(`06_DECISIONS.md` ADR-148 Amendment 8; the orchestrator's ruling of 11 November 2026, on the admin
lane's recommendation, which the owner may overrule).

**Entra holds the accounts; this deployment holds the roles.** With no Keycloak there is no user
attribute to keep roles in, and decision 9 keeps roles assigned in Admin › People, never by an Entra
administrator. So each person is a row keyed by **tenant and object id** (`oid`, Amendment 6 point
6): the roles Admin › People gave them, whether an administrator disabled them here, and, for the
list, the names and access their last token carried.

**Read on every session** by `principal_auth`'s one construction path (`EntraPeopleStore.person`,
its `RoleSource`), never cached: a role taken away holds from the next request. A read that fails is
the resolver's 503, never a principal with no roles.

**Who appears.** A person is recorded, with no roles, at their first sign-in; an administrator may
also add one by object id ahead of it, which the Entra admin centre shows (`add_person`). The
first administrators are named by object id at install (`OSPREY_FIRST_ADMINISTRATORS`, rendered
from `cloud_platform.claims.first_administrators`) and given the Admin role when first recorded.
Taking it away later stands at every start, **unless nobody can manage people** (no enabled person
who has signed in holds `manage_people`): then each one named is given Admin again, audited, which
is the way back in (the orchestrator's ruling, amended 12 November 2026; the runbook's step 6).

**What Admin › People cannot do here, said in words** (`PersonActionRefused`): invite or reset a
sign-in (Entra holds the accounts), change a person's clearance, unit or handling codes (Entra's
claims carry them, through the deployment's claim mapping), remove a person (they would reappear,
with no roles, at their next sign-in: disable them here instead, or in Entra), or join an
organisation account.

**Dashboard identities** (ADR-148 Amendment 10) are registered here by their Entra app
registration's application id and a slug-shaped name, one a tenant, with what they read with; Entra
holds each one's secret. The deployment's own applications (the Glass's, the API's) are refused.

**Every query names the tenant.** A row of another tenant's same object id grants nothing
(`test_entra_people_live.py`, rule 3).
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

from principal_auth import (
    ACCESS_FRESH,
    ClaimMapping,
    SeenPerson,
    StoredDashboard,
    StoredOwner,
    StoredPerson,
    is_object_id,
)
from schemas.admin import (
    AccessInput,
    DashboardIdentity,
    InviteInput,
    OrganisationArrival,
    PersonAccount,
    RegisteredDashboard,
    SignInDelivery,
)
from schemas.domain import Principal
from schemas.rights import Right

from .audit import AuditWriter
from .custom_roles import PEOPLE_LOCK, people_managers, rights_on
from .identity_admin import (
    CredentialCheck,
    DashboardExistsError,
    IdentityAdminRefused,
    PersonActionRefused,
    PersonExistsError,
    UnknownRoleError,
    allowed_role,
    dashboard_slug,
)

#: The role the first administrators are given (`schemas.rights.ROLE_RIGHTS`).
ADMIN_ROLE = "osprey-admin"

#: `ACCESS_FRESH` (imported above, `principal_auth`'s): how long a clearance, unit and handling
#: codes read from a token are trusted for anything sent to the person (a transfer, a promotion's
#: alert) or done as them (a run as its owner, ADR-148 Amendment 16). Display is unchanged.
#: How often a session brings the stored access's time up to date when nothing in it changed.
ACCESS_REFRESH = timedelta(hours=1)
#: An Entra person whose access was never read (added by object id) or read before the column.
_NEVER = datetime(1970, 1, 1, tzinfo=UTC)
#: Two Conduits starting together create the table once (`pg_advisory_xact_lock`).
BOOTSTRAP_LOCK = 0x0E7A_9E09


def access_current(person: PersonAccount, now: datetime | None = None) -> bool:
    """Whether a person's stored clearance and unit may be trusted to receive: always on Keycloak
    (`access_read_at` None, the directory's own); on Entra ID, read from a token within a day."""
    if person.access_read_at is None:
        return True
    return (now or datetime.now(UTC)) - person.access_read_at <= ACCESS_FRESH


STALE_ACCESS_WORDS = (
    "their clearance and unit were last read from Entra ID over a day ago: they sign in again first"
)

#: The install's first administrators, by object id, comma-separated.
FIRST_ADMINISTRATORS_VARIABLE = "OSPREY_FIRST_ADMINISTRATORS"


BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS entra_people (
    tenant_id text NOT NULL,
    oid text NOT NULL,
    roles text[] NOT NULL DEFAULT '{}',
    disabled boolean NOT NULL DEFAULT false,
    name text,
    username text,
    email text,
    clearance text,
    org_unit text,
    receivable_handling_codes text[] NOT NULL DEFAULT '{}',
    first_seen timestamptz,
    access_read_at timestamptz,
    added_by text,
    PRIMARY KEY (tenant_id, oid)
);
CREATE TABLE IF NOT EXISTS entra_dashboards (
    tenant_id text NOT NULL,
    application_id text NOT NULL,
    name text NOT NULL,
    clearance text NOT NULL,
    org_unit text NOT NULL,
    receivable_handling_codes text[] NOT NULL DEFAULT '{}',
    registered_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, application_id),
    UNIQUE (tenant_id, name)
);
CREATE TABLE IF NOT EXISTS entra_sign_in (
    tenant_id text PRIMARY KEY,
    admit_guests boolean NOT NULL DEFAULT false,
    changed_by text,
    changed_at timestamptz
);
"""

#: A dashboard identity's handling codes, as Keycloak's registration gives them
#: (`identity_admin.IdentityAdmin.create_dashboard`).
DASHBOARD_CODES = ("P",)

#: Said for every Admin › People action Entra holds.
ENTRA_HOLDS_ACCOUNTS = (
    "On this deployment Entra ID holds people's accounts: they sign in with their organisation "
    "account, and their clearance, unit and handling codes come from Entra. Here you give them "
    "roles, add them by object id, and disable them."
)


def first_administrators_from_env() -> list[str]:
    """`OSPREY_FIRST_ADMINISTRATORS`, each an object id. Empty, or any entry not an object id, is
    refused at start: an Entra deployment with no administrator named could never be administered,
    and "none named" is never read as "everyone"."""
    raw = os.environ.get(FIRST_ADMINISTRATORS_VARIABLE, "")
    oids = [o.strip() for o in raw.split(",") if o.strip()]
    if not oids:
        raise ValueError(
            f"{FIRST_ADMINISTRATORS_VARIABLE} names no administrator: an Entra ID deployment "
            "needs at least one, by object id (cloud_platform.claims.first_administrators)"
        )
    if bad := [o for o in oids if not is_object_id(o)]:
        raise ValueError(f"{FIRST_ADMINISTRATORS_VARIABLE}: not an Entra object id: {bad[0]!r}")
    return list(dict.fromkeys(oids))


def _refused(what: str) -> PersonActionRefused:
    return PersonActionRefused("entra_holds_accounts", f"{what} {ENTRA_HOLDS_ACCOUNTS}")


def _person(row: Mapping[str, Any]) -> PersonAccount:
    oid = str(row["oid"])
    username = row["username"] or row["email"] or oid
    return PersonAccount(
        id=oid,
        username=username,
        name=row["name"] or username,
        enabled=not row["disabled"],
        roles=list(row["roles"]),
        clearance=row["clearance"],
        org_unit=row["org_unit"],
        email=row["email"],
        receivable_handling_codes=list(row["receivable_handling_codes"]),
        signed_in=row["first_seen"] is not None,
        access_read_at=row["access_read_at"] or _NEVER,
        guest=bool(row.get("guest")),
    )


def _dashboard(row: Mapping[str, Any]) -> StoredDashboard:
    return StoredDashboard(
        application_id=str(row["application_id"]),
        clearance=str(row["clearance"]),
        org_unit=str(row["org_unit"]),
        receivable_handling_codes=tuple(row["receivable_handling_codes"]),
        name=str(row["name"]),
    )


@dataclass
class EntraPeopleStore:
    """The `entra_people` table, every statement bound to one tenant."""

    pool: asyncpg.Pool
    tenant_id: str

    @classmethod
    async def connect(cls, dsn: str, tenant_id: str) -> EntraPeopleStore:
        if not is_object_id(tenant_id):
            raise ValueError("the people store's tenant must be an Entra tenant id")
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", BOOTSTRAP_LOCK)
            await conn.execute(BOOTSTRAP_SQL)
            await conn.execute(
                "ALTER TABLE entra_people ADD COLUMN IF NOT EXISTS access_read_at timestamptz"
            )
            await conn.execute(
                "ALTER TABLE entra_people ADD COLUMN IF NOT EXISTS guest boolean NOT NULL "
                "DEFAULT false"
            )
        return cls(pool, tenant_id)

    async def close(self) -> None:
        await self.pool.close()

    async def ping(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("SELECT 1")

    # --- dashboard identities (ADR-148 Amendment 10; `principal_auth.DashboardSource`) ---------

    async def dashboard(self, tenant_id: str, application_id: str) -> StoredDashboard | None:
        """A registered dashboard identity of this store's tenant; None for any other tenant."""
        if tenant_id != self.tenant_id:
            return None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT application_id, name, clearance, org_unit, receivable_handling_codes "
                "FROM entra_dashboards WHERE tenant_id = $1 AND application_id = $2",
                self.tenant_id, application_id,
            )  # fmt: skip
        return _dashboard(row) if row is not None else None

    async def dashboards(self) -> list[StoredDashboard]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT application_id, name, clearance, org_unit, receivable_handling_codes "
                "FROM entra_dashboards WHERE tenant_id = $1 ORDER BY registered_at, application_id",
                self.tenant_id,
            )
        return [_dashboard(row) for row in rows]

    async def register_dashboard(
        self, application_id: str, name: str, *, clearance: str, org_unit: str
    ) -> StoredDashboard:
        if not is_object_id(application_id):
            raise ValueError("a dashboard identity is named by its application id")
        if not name or dashboard_slug(name) != name:
            raise ValueError(f"a dashboard's name is a slug, as Keycloak's: {name!r} is not one")
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "INSERT INTO entra_dashboards (tenant_id, application_id, name, clearance, "
                    "org_unit, receivable_handling_codes) VALUES ($1, $2, $3, $4, $5, $6) "
                    "ON CONFLICT (tenant_id, application_id) DO NOTHING RETURNING "
                    "application_id, name, clearance, org_unit, receivable_handling_codes",
                    self.tenant_id, application_id, name, clearance, org_unit,
                    list(DASHBOARD_CODES),
                )  # fmt: skip
        except asyncpg.UniqueViolationError as clash:  # UNIQUE (tenant_id, name)
            raise DashboardExistsError(name) from clash
        if row is None:
            raise DashboardExistsError(application_id)
        return _dashboard(row)

    async def remove_dashboard(self, application_id: str) -> bool:
        async with self.pool.acquire() as conn:
            done = await conn.execute(
                "DELETE FROM entra_dashboards WHERE tenant_id = $1 AND application_id = $2",
                self.tenant_id, application_id,
            )  # fmt: skip
        return str(done).endswith(" 1")

    # --- the resolver's read (`principal_auth.RoleSource`) ------------------------------------

    async def person(self, tenant_id: str, oid: str, seen: SeenPerson) -> StoredPerson:
        """The stored person, recorded at their first sign-in, their names and access brought up to
        date when their token says otherwise. Asked for another tenant than the store's, it raises
        (the resolver's 503): the two are configured from one setting and must never differ."""
        if tenant_id != self.tenant_id:
            raise IdentityAdminRefused("the people store is another tenant's")
        values = (
            seen.name,
            seen.username,
            seen.email,
            seen.clearance,
            seen.org_unit,
            list(seen.receivable_handling_codes),
            bool(seen.guest),
        )
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT roles, disabled, name, username, email, clearance, org_unit, "
                "receivable_handling_codes, guest, access_read_at, now() AS at "
                "FROM entra_people WHERE tenant_id = $1 AND oid = $2",
                tenant_id,
                oid,
            )
            if row is None:
                row = await conn.fetchrow(
                    "INSERT INTO entra_people (tenant_id, oid, name, username, email, clearance, "
                    "org_unit, receivable_handling_codes, guest, first_seen, access_read_at) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now(), now()) "
                    "ON CONFLICT (tenant_id, oid) DO UPDATE SET first_seen = "
                    "COALESCE(entra_people.first_seen, now()), access_read_at = now(), "
                    "name = EXCLUDED.name, username = EXCLUDED.username, email = EXCLUDED.email, "
                    "clearance = EXCLUDED.clearance, org_unit = EXCLUDED.org_unit, "
                    "receivable_handling_codes = EXCLUDED.receivable_handling_codes, "
                    "guest = EXCLUDED.guest "
                    "RETURNING roles, disabled",
                    tenant_id,
                    oid,
                    *values,
                )
            elif (
                row["name"],
                row["username"],
                row["email"],
                row["clearance"],
                row["org_unit"],
                list(row["receivable_handling_codes"]),
                bool(row["guest"]),
            ) != values or (
                row["access_read_at"] is None or row["at"] - row["access_read_at"] > ACCESS_REFRESH
            ):
                await conn.execute(
                    "UPDATE entra_people SET name = $3, username = $4, email = $5, "
                    "clearance = $6, org_unit = $7, receivable_handling_codes = $8, guest = $9, "
                    "first_seen = COALESCE(first_seen, now()), access_read_at = now() "
                    "WHERE tenant_id = $1 AND oid = $2",
                    tenant_id,
                    oid,
                    *values,
                )
        assert row is not None
        return StoredPerson(roles=tuple(row["roles"]), disabled=bool(row["disabled"]))

    async def standing(self, oid: str) -> StoredPerson | None:
        """The stored person as they are now, read without recording anyone: an open delta socket
        asks it before each message (ADR-148 Amendment 8). None for a person not recorded."""
        async with self.pool.acquire() as conn:
            # A guest, once guests are no longer admitted, stands as disabled (ADR-148 Am 17).
            row = await conn.fetchrow(
                "SELECT p.roles, p.disabled OR (p.guest AND NOT COALESCE(s.admit_guests, false)) "
                "AS disabled FROM entra_people p LEFT JOIN entra_sign_in s "
                "ON s.tenant_id = p.tenant_id WHERE p.tenant_id = $1 AND p.oid = $2",
                self.tenant_id,
                oid,
            )
        if row is None:
            return None
        return StoredPerson(roles=tuple(row["roles"]), disabled=bool(row["disabled"]))

    # --- guests (ADR-148 Amendment 17; `principal_auth.RoleSource.guests_admitted`) --------------

    async def guests_admitted(self, tenant_id: str) -> bool:
        """Whether this deployment admits guest (B2B) accounts: off until an administrator turns it
        on. Asked for another tenant, it raises, as `person` does."""
        if tenant_id != self.tenant_id:
            raise IdentityAdminRefused("the people store is another tenant's")
        async with self.pool.acquire() as conn:
            admitted = await conn.fetchval(
                "SELECT admit_guests FROM entra_sign_in WHERE tenant_id = $1", self.tenant_id
            )
        return admitted is True

    async def guest_sign_in(self) -> tuple[bool, str | None, datetime | None]:
        """The setting, who last changed it and when (none, never)."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT admit_guests, changed_by, changed_at FROM entra_sign_in "
                "WHERE tenant_id = $1",
                self.tenant_id,
            )
        if row is None:
            return False, None, None
        return bool(row["admit_guests"]), row["changed_by"], row["changed_at"]

    async def set_guests_admitted(self, admitted: bool, by: str) -> bool:
        """Sets the setting and answers what it was before, in one statement."""
        async with self.pool.acquire() as conn, conn.transaction():
            before = await conn.fetchval(
                "SELECT admit_guests FROM entra_sign_in WHERE tenant_id = $1 FOR UPDATE",
                self.tenant_id,
            )
            await conn.execute(
                "INSERT INTO entra_sign_in (tenant_id, admit_guests, changed_by, changed_at) "
                "VALUES ($1, $2, $3, now()) ON CONFLICT (tenant_id) DO UPDATE SET "
                "admit_guests = EXCLUDED.admit_guests, changed_by = EXCLUDED.changed_by, "
                "changed_at = EXCLUDED.changed_at",
                self.tenant_id,
                admitted,
                by,
            )
        return before is True

    async def owner(self, tenant_id: str, oid: str) -> StoredOwner | None:
        """A person as held, for a run acting as them (ADR-148 Amendment 16): read without
        recording anyone, and only within this store's tenant. None for a person not held; asked for
        another tenant, it raises, as `person` does: a store wired to the wrong tenant is a fault,
        never every owner "not held"."""
        if tenant_id != self.tenant_id:
            raise IdentityAdminRefused("the people store is another tenant's")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT roles, disabled, clearance, org_unit, receivable_handling_codes, "
                "access_read_at, guest FROM entra_people WHERE tenant_id = $1 AND oid = $2",
                self.tenant_id,
                oid,
            )
        if row is None:
            return None
        return StoredOwner(
            roles=tuple(row["roles"]),
            disabled=bool(row["disabled"]),
            clearance=row["clearance"],
            org_unit=row["org_unit"],
            receivable_handling_codes=tuple(row["receivable_handling_codes"]),
            access_read_at=row["access_read_at"],
            guest=bool(row["guest"]),
        )

    # --- the install's first administrators ---------------------------------------------------

    async def seed_first_administrators(
        self, oids: Iterable[str], audit: AuditWriter | None = None
    ) -> list[str]:
        """The named object ids given the Admin role at this start, which the caller audits:

        - one **not yet recorded**, with Admin (the install);
        - one already recorded, **only when nobody can manage people** (`people_managers` empty:
          no enabled person who has signed in holds `manage_people`, by their roles and the custom
          roles' rights, both read inside the lock), Admin added to what they hold. Otherwise what
          an administrator set stands, a named person's roles cleared on purpose included.

        Under `PEOPLE_LOCK`, the lock every change that could leave nobody able to manage people
        takes, so a start and such a change are never interleaved (the orchestrator's ruling,
        amended 12 November 2026). Each grant's audit row (`grant_first_administrator`) is written
        on the same connection in the same transaction, so a grant is never kept without its row
        (`audit_log` is in this database; the third review's should-fix 3)."""
        oids = list(oids)
        for oid in oids:
            if not is_object_id(oid):
                raise ValueError(f"not an Entra object id: {oid!r}")
        given: list[str] = []
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", PEOPLE_LOCK)
            rows = await conn.fetch(
                "SELECT * FROM entra_people WHERE tenant_id = $1", self.tenant_id
            )
            custom = await rights_on(conn)
            nobody_administers = not people_managers([_person(r) for r in rows], custom)
            for oid in oids:
                added = await conn.fetchval(
                    "INSERT INTO entra_people (tenant_id, oid, roles, added_by) "
                    "VALUES ($1, $2, $3, 'install') ON CONFLICT (tenant_id, oid) DO NOTHING "
                    "RETURNING oid",
                    self.tenant_id,
                    oid,
                    [ADMIN_ROLE],
                )
                if added is None and nobody_administers:
                    added = await conn.fetchval(
                        "UPDATE entra_people SET roles = array_append(roles, $3) "
                        "WHERE tenant_id = $1 AND oid = $2 AND NOT ($3 = ANY(roles)) RETURNING oid",
                        self.tenant_id,
                        oid,
                        ADMIN_ROLE,
                    )
                if added is not None:
                    given.append(oid)
                    if audit is not None:
                        await audit.record(
                            principal=FIRST_ADMINISTRATORS_PRINCIPAL,
                            action=GRANT_ACTION,
                            resolved_query={"user_id": oid, "roles": [ADMIN_ROLE]},
                            result_cardinality=1,
                            conn=conn,
                        )
        return given

    # --- Admin › People -----------------------------------------------------------------------

    async def rows(self) -> list[PersonAccount]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM entra_people WHERE tenant_id = $1", self.tenant_id
            )
        return sorted((_person(r) for r in rows), key=lambda p: (p.username, p.id))

    async def one(self, oid: str) -> PersonAccount:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM entra_people WHERE tenant_id = $1 AND oid = $2", self.tenant_id, oid
            )
        if row is None:
            raise IdentityAdminRefused("no such person")
        return _person(row)

    async def update(self, oid: str, column: str, value: object) -> PersonAccount:
        assert column in ("roles", "disabled")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"UPDATE entra_people SET {column} = $3 WHERE tenant_id = $1 AND oid = $2 "
                "RETURNING *",
                self.tenant_id,
                oid,
                value,
            )
        if row is None:
            raise IdentityAdminRefused("no such person")
        return _person(row)

    async def add(self, oid: str, by: str) -> PersonAccount:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO entra_people (tenant_id, oid, added_by) VALUES ($1, $2, $3) "
                "ON CONFLICT (tenant_id, oid) DO NOTHING RETURNING *",
                self.tenant_id,
                oid,
                by,
            )
        if row is None:
            raise PersonExistsError(oid)
        return _person(row)


class EntraPeopleAdmin:
    """Admin › People's calls on Entra ID sign-in, answering what `IdentityAdmin` answers on
    Keycloak (the routes call either): roles and *Disable* written to the deployment's own store,
    everything Entra holds refused in words."""

    def __init__(self, store: EntraPeopleStore, *, own_clients: Iterable[str | None] = ()) -> None:
        self.store = store
        #: The Glass's and this API's own application ids, never a dashboard identity's: the
        #: resolver refuses a token of either as a dashboard's (ADR-148 Amendment 10).
        self.own_clients = frozenset(c.lower() for c in own_clients if c)

    async def aclose(self) -> None:
        """The store is the run resources' (`run_resources.py` closes it), not this admin's."""

    async def reachable(self) -> None:
        try:
            await self.store.ping()
        except (OSError, asyncpg.PostgresError) as error:
            raise IdentityAdminRefused(f"the people store did not answer: {error}") from None

    async def credential_check(self) -> CredentialCheck:
        """Can the Conduit act for people? On Entra it acts only on its own store."""
        try:
            await self.reachable()
        except IdentityAdminRefused:
            return CredentialCheck("unreachable", 0, "the people store did not answer")
        return CredentialCheck("accepted", 0, None)

    async def list_people(self) -> list[PersonAccount]:
        return await self.store.rows()

    async def guest_sign_in(self) -> tuple[bool, str | None, datetime | None]:
        """ADR-148 Amendment 17: whether guests are admitted, who last changed it and when."""
        return await self.store.guest_sign_in()

    async def set_guests_admitted(self, admitted: bool, by: str) -> bool:
        """Admit guest (B2B) accounts, or no longer; answers what it was before. A guest already
        recorded is refused at their next request once it is off (`standing`, the resolver)."""
        return await self.store.set_guests_admitted(admitted, by)

    async def set_roles(self, user_id: str, roles: list[str]) -> PersonAccount:
        if refused := [r for r in roles if not allowed_role(r)]:
            raise UnknownRoleError(
                f"not a role or right this deployment grants: {', '.join(refused)}"
            )
        return await self.store.update(user_id, "roles", list(dict.fromkeys(roles)))

    async def set_enabled(self, user_id: str, enabled: bool) -> PersonAccount:
        """Disabled here, refused at their next request (`principal_auth`): no session outlives
        it, since every request reads the store."""
        return await self.store.update(user_id, "disabled", not enabled)

    async def add_person(self, oid: str, by: str) -> PersonAccount:
        if not is_object_id(oid):
            raise UnknownRoleError(
                "not an Entra object id (like 1b2c3d4e-0000-4000-8000-00000000abcd, in lower case)"
            )
        try:
            return await self.store.add(oid, by)
        except PersonExistsError:
            raise PersonActionRefused(
                "person_exists", f"{oid} is already in People: give them roles there."
            ) from None

    async def invite(self, invite: InviteInput) -> SignInDelivery:
        raise _refused("People are not invited here.")

    async def set_access(self, user_id: str, access: AccessInput) -> PersonAccount:
        raise _refused("A person's clearance, unit and handling codes are changed in Entra ID.")

    async def reset_sign_in(self, user_id: str) -> SignInDelivery:
        raise _refused("A sign-in is reset in Entra ID.")

    async def remove_person(
        self, user_id: str, custom: Mapping[str, Iterable[Right]] | None = None
    ) -> PersonAccount:
        raise _refused(
            "A person is not removed here: they would return, with no roles, at their next "
            "sign-in. Disable them instead, or remove them in Entra ID."
        )

    async def list_arrivals(self) -> list[OrganisationArrival]:
        return []

    async def link_organisation(
        self, user_id: str, subject: str
    ) -> tuple[PersonAccount, OrganisationArrival]:
        raise _refused("There is no organisation account to join.")

    # ADR-148 Amendment 10: a dashboard identity is its own Entra app registration, which holds its
    # secret; Admin › Dashboards registers it by application id with what it reads with.
    async def list_dashboards(self) -> list[DashboardIdentity]:
        return [_identity(d) for d in await self.store.dashboards()]

    async def create_dashboard(
        self, name: str, *, clearance: str, org_unit: str, application_id: str | None = None
    ) -> RegisteredDashboard:
        if application_id is None:
            raise UnknownRoleError(
                "on Entra ID a dashboard identity is its own app registration: give its "
                "application id (the registration holds its secret)"
            )
        if application_id.lower() in self.own_clients:
            raise UnknownRoleError(
                f"{application_id} is this deployment's own application (the Glass's or the "
                "API's), never a dashboard identity: give the dashboard's own app registration"
            )
        stored = await self.store.register_dashboard(
            application_id, dashboard_slug(name), clearance=clearance, org_unit=org_unit
        )
        return RegisteredDashboard(dashboard=_identity(stored), secret=None)

    async def delete_dashboard(self, client_id: str) -> None:
        if not await self.store.remove_dashboard(client_id):
            raise PersonActionRefused(
                "no_such_dashboard", f"{client_id} is not a registered dashboard identity."
            )


def _identity(stored: StoredDashboard) -> DashboardIdentity:
    """Its account, which a case Author grants Viewer to, is its application id: what its token's
    principal is (`principal_auth.principal_from_claims`)."""
    return DashboardIdentity(
        client_id=stored.application_id,
        account_id=stored.application_id,
        name=stored.name or None,
        clearance=stored.clearance,
        org_unit=stored.org_unit,
        receivable_handling_codes=list(stored.receivable_handling_codes),
    )


#: Who an audit row of the start's own grant names: no person did it.
FIRST_ADMINISTRATORS_PRINCIPAL = Principal(
    id="first-administrators", clearance="", org_unit="system"
)
GRANT_ACTION = "grant_first_administrator"


async def open_people_store(
    dsn: str, mapping: ClaimMapping, audit: AuditWriter
) -> EntraPeopleStore | None:
    """The people store, its first administrators seeded, for an Entra mapping; None otherwise.
    Refuses to start an Entra deployment that names no first administrator. Each Admin role the
    start gives is audited (`grant_first_administrator`), the install's and a way back in alike."""
    if not mapping.is_entra:
        return None
    assert mapping.tenant_id is not None
    first = first_administrators_from_env()
    store = await EntraPeopleStore.connect(dsn, mapping.tenant_id)
    try:
        await store.seed_first_administrators(first, audit)
    except BaseException:
        await store.close()
        raise
    return store
