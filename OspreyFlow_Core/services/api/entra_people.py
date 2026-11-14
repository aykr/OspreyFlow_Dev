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

import json
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

from ontology.handling import HandlingScheme
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
    PersonAccessInput,
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


#: ADR-148 Amendment 15: what the first administrators hold, at install, of each value the claim
#: mapping sources from the administrator (`cloud_platform.claims.first_administrator_access`).
FIRST_ADMINISTRATOR_ACCESS_VARIABLE = "OSPREY_FIRST_ADMINISTRATOR_ACCESS"
ACCESS_GRANT_ACTION = "grant_first_administrator_access"


def first_administrator_access_from_env(
    by_administrator: Iterable[str], scheme: HandlingScheme | None = None
) -> dict[str, Any]:
    """The first administrators' values for each field the administrator sets, refused at start when
    one is missing: they could not sign in, and so nobody could set anyone's (Amendment 15). With
    the deployment's handling scheme, a clearance or code it does not know is refused too: seeded
    only where nothing is set, such a value could never be put right by the config, and no Access
    would be within the first administrators' reach."""
    sets = set(by_administrator)
    if not sets:
        return {}
    raw = os.environ.get(FIRST_ADMINISTRATOR_ACCESS_VARIABLE, "")
    try:
        held = json.loads(raw) if raw else {}
    except ValueError:
        raise ValueError(f"{FIRST_ADMINISTRATOR_ACCESS_VARIABLE} is not JSON") from None
    if not isinstance(held, dict) or (missing := sorted(sets - held.keys())):
        raise ValueError(
            f"{FIRST_ADMINISTRATOR_ACCESS_VARIABLE} gives the first administrators no "
            f"{', '.join(missing) if isinstance(held, dict) else 'values'}: with those set by the "
            "administrator, nobody could sign in (cloud_platform.claims.first_administrator_access)"
        )
    codes = held.get("handling_codes")
    listed = isinstance(codes, list) and all(isinstance(c, str) for c in codes)
    if "handling_codes" in sets and not listed:
        raise ValueError(
            f"{FIRST_ADMINISTRATOR_ACCESS_VARIABLE}: handling_codes is a list of codes"
        )
    for field in sets & {"clearance", "org_unit"}:
        if not isinstance(held[field], str) or not held[field]:
            raise ValueError(f"{FIRST_ADMINISTRATOR_ACCESS_VARIABLE}: {field} is not a value")
    if scheme is not None:
        if "clearance" in sets and held["clearance"] not in scheme.classification:
            raise ValueError(
                f"{FIRST_ADMINISTRATOR_ACCESS_VARIABLE}: clearance {held['clearance']!r} is not a "
                f"classification of this deployment ({', '.join(scheme.classification)})"
            )
        unknown = sorted(set(held.get("handling_codes") or []) - scheme.handling_codes.keys())
        if "handling_codes" in sets and unknown:
            raise ValueError(
                f"{FIRST_ADMINISTRATOR_ACCESS_VARIABLE}: handling codes {', '.join(unknown)} are "
                "not this deployment's"
            )
    return {f: held[f] for f in sets}


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


#: ADR-148 Amendment 15: the values a claim mapping may source from the administrator, by the name
#: `ClaimMapping` gives each, and the store's column holding what the administrator set.
ADMINISTRATOR_FIELDS = {"clearance": "admin_clearance", "org_unit": "admin_org_unit",
                        "handling_codes": "admin_codes"}  # fmt: skip


class NoSuchPerson(IdentityAdminRefused):
    """ADR-148 Amendment 15: no such person in this tenant's people store (404, never the identity
    provider's own refusal)."""


class AccessBeyondTheSetter(Exception):
    """ADR-148 Amendment 15, rule 3 in the store: a clearance above, or a handling code beyond, what
    the person setting it holds as this store has them. `error` and `detail` as the route's own
    check answers (403)."""

    def __init__(self, error: str, detail: dict[str, Any]) -> None:
        super().__init__(error)
        self.error, self.detail = error, detail


def _person(
    row: Mapping[str, Any], by_administrator: frozenset[str] = frozenset()
) -> PersonAccount:
    """A person as People shows them: each value the mapping sources from the administrator is the
    one set here (Amendment 15), the others the token's last. Values set here do not age, so a
    person whose every value is set here is never stale (`access_current`)."""
    oid = str(row["oid"])
    username = row["username"] or row["email"] or oid

    def held(field: str, seen: str) -> Any:
        return row.get(ADMINISTRATOR_FIELDS[field]) if field in by_administrator else row[seen]

    codes = held("handling_codes", "receivable_handling_codes")
    # Never stale when nothing of theirs is read from a token; stale (never read) when a value set
    # here is missing, so nothing is sent to them on a clearance that is not there.
    every_value_set_here = by_administrator >= ADMINISTRATOR_FIELDS.keys() and _all_set(
        row, by_administrator
    )
    return PersonAccount(
        id=oid,
        username=username,
        name=row["name"] or username,
        enabled=not row["disabled"],
        roles=list(row["roles"]),
        clearance=held("clearance", "clearance"),
        org_unit=held("org_unit", "org_unit"),
        email=row["email"],
        receivable_handling_codes=list(codes or []),
        # A person whose values set here are not all set is refused at sign-in after being
        # recorded (`first_seen`), so has never signed in: counted by no lock-out check
        # (`people_managers`, every route's as well as the seed's).
        signed_in=row["first_seen"] is not None and _all_set(row, by_administrator),
        access_read_at=(
        None if every_value_set_here
        else _NEVER if not _all_set(row, by_administrator)
        else (row["access_read_at"] or _NEVER)
    ),
    )


def _all_set(row: Mapping[str, Any], by_administrator: frozenset[str]) -> bool:
    """Whether every value the administrator sets is set for this person's row (Amendment 15): a
    clearance or unit not empty, the codes a list (none is a value); otherwise they cannot sign
    in."""
    for field in by_administrator:
        held = row.get(ADMINISTRATOR_FIELDS[field])
        if held is None or (field != "handling_codes" and not held):
            return False
    return True


def _held(person: PersonAccount) -> dict[str, Any]:
    return {"clearance": person.clearance, "org_unit": person.org_unit,
            "receivable_handling_codes": person.receivable_handling_codes}  # fmt: skip


def _owner(
    row: Mapping[str, Any], by_administrator: frozenset[str], now: datetime | None = None
) -> StoredOwner:
    """A run's owner as held (ADR-148 Amendments 15 and 16): each value the mapping sources from
    the administrator is the one set here, the others the token's last. A value set here never
    ages, so an owner whose every value is set here is current at this read; with only some set
    here, the token's still need a sign-in within the day (`access_read_at`, judged by the
    resolver). One set by the administrator but not set yet refuses the run, as the person's own
    sign-in is refused (no clearance and no time are given)."""
    sets = by_administrator

    def held(field: str, seen: str) -> Any:
        return row.get(ADMINISTRATOR_FIELDS[field]) if field in sets else row[seen]

    read_at = row["access_read_at"]
    clearance, org_unit = held("clearance", "clearance"), held("org_unit", "org_unit")
    codes = held("handling_codes", "receivable_handling_codes")
    named = (("clearance", "clearance"), ("org_unit", "unit"), ("handling_codes", "handling codes"))
    unset = tuple(
        words for field, words in named if field in sets and not _all_set(row, frozenset({field}))
    )
    if unset:
        clearance, read_at = None, None
    elif sets >= ADMINISTRATOR_FIELDS.keys():
        read_at = now or datetime.now(UTC)
    return StoredOwner(
        roles=tuple(row["roles"]),
        disabled=bool(row["disabled"]),
        clearance=clearance,
        org_unit=org_unit,
        receivable_handling_codes=tuple(codes or ()),
        access_read_at=read_at,
        unset=unset,
    )


def _stored(row: Mapping[str, Any]) -> StoredPerson:
    """The resolver's and the socket's read: roles, disabled, and what the administrator set (None
    where nothing was), whatever the mapping sources; the resolver takes only what it sources so."""
    codes = row.get("admin_codes")
    return StoredPerson(
        roles=tuple(row["roles"]), disabled=bool(row["disabled"]),
        clearance=row.get("admin_clearance"), org_unit=row.get("admin_org_unit"),
        receivable_handling_codes=None if codes is None else tuple(codes),
    )  # fmt: skip


def _dashboard(row: Mapping[str, Any]) -> StoredDashboard:
    return StoredDashboard(
        application_id=str(row["application_id"]),
        clearance=str(row["clearance"]),
        org_unit=str(row["org_unit"]),
        receivable_handling_codes=tuple(row["receivable_handling_codes"]),
        name=str(row["name"]),
    )


def check_administrator_access(
    by_administrator: frozenset[str],
    setter: Mapping[str, Any] | None,
    access: PersonAccessInput,
    classification: Sequence[str],
) -> None:
    """ADR-148 Amendment 15: whether the person `setter` (their row as the people store holds it)
    may give `access`, the store's own limits (rule 3), run inside its transaction:

    - nothing is set where the mapping sources no value from the administrator, and a value Entra
      sends is never given here (409 `entra_holds_accounts`);
    - the setter is recorded here and enabled, with every value of theirs set (403
      `setter_cannot_set`);
    - no clearance above the setter's own, nor one the deployment does not know (403
      `above_your_clearance`);
    - no handling code beyond the setter's own (403 `handling_code_you_do_not_hold`)."""
    if not by_administrator:
        raise _refused("A person's clearance, unit and handling codes are changed in Entra ID.")
    given = {"clearance": access.clearance, "org_unit": access.org_unit,
             "handling_codes": access.receivable_handling_codes}  # fmt: skip
    if entra_s := [f for f, v in given.items() if v is not None and f not in by_administrator]:
        raise _refused(f"Here {' and '.join(entra_s)} come from Entra ID, and are changed there.")
    if setter is None or setter["disabled"] or not _all_set(setter, by_administrator):
        raise AccessBeyondTheSetter("setter_cannot_set", {})
    mine = _person(setter, by_administrator)
    order = list(classification)
    if access.clearance is not None and (
        mine.clearance not in order
        or access.clearance not in order
        or order.index(access.clearance) > order.index(mine.clearance)
    ):
        raise AccessBeyondTheSetter("above_your_clearance", {"clearance": access.clearance})
    asked = set(access.receivable_handling_codes or [])
    beyond = sorted(asked - set(mine.receivable_handling_codes))
    if beyond:
        raise AccessBeyondTheSetter("handling_code_you_do_not_hold", {"codes": beyond})


@dataclass
class EntraPeopleStore:
    """The `entra_people` table, every statement bound to one tenant."""

    pool: asyncpg.Pool
    tenant_id: str
    #: ADR-148 Amendment 15: which of ADMINISTRATOR_FIELDS the claim mapping sources from the
    #: administrator; the others are never written by Admin › People.
    by_administrator: frozenset[str] = frozenset()

    @classmethod
    async def connect(
        cls, dsn: str, tenant_id: str, by_administrator: Iterable[str] = ()
    ) -> EntraPeopleStore:
        if not is_object_id(tenant_id):
            raise ValueError("the people store's tenant must be an Entra tenant id")
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", BOOTSTRAP_LOCK)
            await conn.execute(BOOTSTRAP_SQL)
            await conn.execute(
                "ALTER TABLE entra_people ADD COLUMN IF NOT EXISTS access_read_at timestamptz"
            )
            # ADR-148 Amendment 15: what an administrator set, apart from what a token said (the
            # columns above), so a sign-in never overwrites it; null where nothing was set.
            await conn.execute(
                "ALTER TABLE entra_people ADD COLUMN IF NOT EXISTS admin_clearance text, "
                "ADD COLUMN IF NOT EXISTS admin_org_unit text, "
                "ADD COLUMN IF NOT EXISTS admin_codes text[], "
                "ADD COLUMN IF NOT EXISTS access_set_by text, "
                "ADD COLUMN IF NOT EXISTS access_set_at timestamptz"
            )
        unknown = set(by_administrator) - ADMINISTRATOR_FIELDS.keys()
        if unknown:
            raise ValueError(f"not a value the administrator may set: {sorted(unknown)}")
        return cls(pool, tenant_id, frozenset(by_administrator))

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
            # None where the administrator sets the value (Amendment 15): the token was not read.
            list(seen.receivable_handling_codes or ()),
        )
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT roles, disabled, name, username, email, clearance, org_unit, "
                "receivable_handling_codes, access_read_at, admin_clearance, admin_org_unit, "
                "admin_codes, now() AS at "
                "FROM entra_people WHERE tenant_id = $1 AND oid = $2",
                tenant_id,
                oid,
            )
            if row is None:
                row = await conn.fetchrow(
                    "INSERT INTO entra_people (tenant_id, oid, name, username, email, clearance, "
                    "org_unit, receivable_handling_codes, first_seen, access_read_at) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now(), now()) "
                    "ON CONFLICT (tenant_id, oid) DO UPDATE SET first_seen = "
                    "COALESCE(entra_people.first_seen, now()), access_read_at = now(), "
                    "name = EXCLUDED.name, username = EXCLUDED.username, email = EXCLUDED.email, "
                    "clearance = EXCLUDED.clearance, org_unit = EXCLUDED.org_unit, "
                    "receivable_handling_codes = EXCLUDED.receivable_handling_codes "
                    "RETURNING roles, disabled, admin_clearance, admin_org_unit, admin_codes",
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
            ) != values or (
                row["access_read_at"] is None or row["at"] - row["access_read_at"] > ACCESS_REFRESH
            ):
                await conn.execute(
                    "UPDATE entra_people SET name = $3, username = $4, email = $5, "
                    "clearance = $6, org_unit = $7, receivable_handling_codes = $8, "
                    "first_seen = COALESCE(first_seen, now()), access_read_at = now() "
                    "WHERE tenant_id = $1 AND oid = $2",
                    tenant_id,
                    oid,
                    *values,
                )
        assert row is not None
        return _stored(row)

    async def standing(self, oid: str) -> StoredPerson | None:
        """The stored person as they are now, read without recording anyone: an open delta socket
        asks it before each message (ADR-148 Amendment 8). None for a person not recorded."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT roles, disabled, admin_clearance, admin_org_unit, admin_codes "
                "FROM entra_people WHERE tenant_id = $1 AND oid = $2",
                self.tenant_id,
                oid,
            )
        if row is None:
            return None
        return _stored(row)

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
                "access_read_at, admin_clearance, admin_org_unit, admin_codes "
                "FROM entra_people WHERE tenant_id = $1 AND oid = $2",
                self.tenant_id,
                oid,
            )
        if row is None:
            return None
        # Amendment 15: the values the administrator sets are this deployment's, never a token's.
        return _owner(row, self.by_administrator)

    # --- the install's first administrators ---------------------------------------------------

    async def seed_first_administrators(
        self,
        oids: Iterable[str],
        audit: AuditWriter | None = None,
        access: Mapping[str, Any] | None = None,
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
            # Amendment 15: a person whose values the administrator sets, not all set yet, cannot
            # sign in, so cannot manage anyone (`_person`'s `signed_in`).
            people = [_person(r, self.by_administrator) for r in rows]
            nobody_administers = not people_managers(people, custom)
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
                # Only where the role gate above admits them: a person already recorded while
                # someone can manage people keeps what an administrator set, values unset included.
                if access and (added is not None or nobody_administers):
                    await self._seed_access(conn, oid, access, audit)
        return given

    async def _seed_access(
        self, conn: Any, oid: str, access: Mapping[str, Any], audit: AuditWriter | None
    ) -> None:
        """ADR-148 Amendment 15: a first administrator's values, each only where none is set, so an
        administrator's later change stands and a restart never undoes it; audited when given."""
        sets = self.by_administrator
        set_now = await conn.fetchrow(
            "UPDATE entra_people SET "
            "admin_clearance = CASE WHEN $3 AND admin_clearance IS NULL THEN $4 "
            "ELSE admin_clearance END, "
            "admin_org_unit = CASE WHEN $5 AND admin_org_unit IS NULL THEN $6 "
            "ELSE admin_org_unit END, "
            "admin_codes = CASE WHEN $7 AND admin_codes IS NULL THEN $8::text[] "
            "ELSE admin_codes END, "
            "access_set_by = COALESCE(access_set_by, 'install'), "
            "access_set_at = COALESCE(access_set_at, now()) "
            "WHERE tenant_id = $1 AND oid = $2 AND ("
            "($3 AND admin_clearance IS NULL) OR ($5 AND admin_org_unit IS NULL) "
            "OR ($7 AND admin_codes IS NULL)) RETURNING oid",
            self.tenant_id, oid,
            "clearance" in sets, access.get("clearance"),
            "org_unit" in sets, access.get("org_unit"),
            "handling_codes" in sets, list(access.get("handling_codes") or []),
        )  # fmt: skip
        if set_now is not None and audit is not None:
            await audit.record(
                principal=FIRST_ADMINISTRATORS_PRINCIPAL,
                action=ACCESS_GRANT_ACTION,
                resolved_query={"user_id": oid, **{f: access[f] for f in sorted(sets)}},
                result_cardinality=1,
                conn=conn,
            )

    # --- Admin › People -----------------------------------------------------------------------

    async def rows(self) -> list[PersonAccount]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM entra_people WHERE tenant_id = $1", self.tenant_id
            )
        people = (_person(r, self.by_administrator) for r in rows)
        return sorted(people, key=lambda p: (p.username, p.id))

    async def one(self, oid: str) -> PersonAccount:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM entra_people WHERE tenant_id = $1 AND oid = $2", self.tenant_id, oid
            )
        if row is None:
            raise IdentityAdminRefused("no such person")
        return _person(row, self.by_administrator)

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
        return _person(row, self.by_administrator)

    async def set_administrator_access(
        self,
        oid: str,
        by: Principal,
        access: PersonAccessInput,
        classification: Sequence[str],
        audit: AuditWriter | None = None,
    ) -> tuple[PersonAccount, PersonAccount]:
        """ADR-148 Amendment 15: what the administrator `by` gives `oid`, each value the mapping
        sources from the administrator and given, in one transaction with its audit row. The
        limits are this store's, read here from `by`'s own row (rule 3, not only the route's).
        Another tenant's row is never read. Answers (before, after)."""
        sets = self.by_administrator
        async with self.pool.acquire() as conn, conn.transaction():
            setter = await conn.fetchrow(
                "SELECT * FROM entra_people WHERE tenant_id = $1 AND oid = $2 FOR SHARE",
                self.tenant_id, by.id,
            )  # fmt: skip
            target = await conn.fetchrow(
                "SELECT * FROM entra_people WHERE tenant_id = $1 AND oid = $2 FOR UPDATE",
                self.tenant_id, oid,
            )  # fmt: skip
            if target is None:
                raise NoSuchPerson(f"{oid} is not in People here")
            check_administrator_access(sets, setter, access, classification)
            row = await conn.fetchrow(
                "UPDATE entra_people SET "
                "admin_clearance = COALESCE($3, admin_clearance), "
                "admin_org_unit = COALESCE($4, admin_org_unit), "
                "admin_codes = COALESCE($5::text[], admin_codes), "
                "access_set_by = $6, access_set_at = now() "
                "WHERE tenant_id = $1 AND oid = $2 RETURNING *",
                self.tenant_id, oid, access.clearance, access.org_unit,
                access.receivable_handling_codes, by.id,
            )  # fmt: skip
            assert row is not None
            before, after = _person(target, sets), _person(row, sets)
            if audit is not None:
                await audit.record(
                    principal=by,
                    action="set_person_access",
                    resolved_query={"user_id": oid, "by_administrator": sorted(sets),
                                    "before": _held(before), "after": _held(after)},  # fmt: skip
                    result_cardinality=1,
                    conn=conn,
                )
        return before, after

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
        return _person(row, self.by_administrator)


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

    @property
    def by_administrator(self) -> frozenset[str]:
        """ADR-148 Amendment 15: the values this deployment's administrators set (none by
        default)."""
        return frozenset(getattr(self.store, "by_administrator", frozenset()))

    async def set_administrator_access(
        self,
        user_id: str,
        by: Principal,
        access: PersonAccessInput,
        classification: Sequence[str],
        audit: AuditWriter | None = None,
    ) -> PersonAccount:
        """ADR-148 Amendment 15: the values the mapping sources from the administrator, set by `by`
        within what the store holds for them (the store's own limits, rule 3), audited in the
        store's transaction. Without the fallback, refused in Entra's words before the store is
        asked, as before."""
        if not self.by_administrator:
            raise _refused("A person's clearance, unit and handling codes are changed in Entra ID.")
        _before, after = await self.store.set_administrator_access(
            user_id, by, access, classification, audit
        )
        return after

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
    dsn: str, mapping: ClaimMapping, audit: AuditWriter, scheme: HandlingScheme | None = None
) -> EntraPeopleStore | None:
    """The people store, its first administrators seeded, for an Entra mapping; None otherwise.
    Refuses to start an Entra deployment that names no first administrator. Each Admin role the
    start gives is audited (`grant_first_administrator`), the install's and a way back in alike."""
    if not mapping.is_entra:
        return None
    assert mapping.tenant_id is not None
    first = first_administrators_from_env()
    # ADR-148 Amendment 15: the values the mapping sources from the administrator.
    by_administrator = [
        field
        for field, source in (
            ("clearance", mapping.clearance),
            ("org_unit", mapping.org_unit),
            ("handling_codes", mapping.handling_codes),
        )
        if source.administrator
    ]  # fmt: skip
    store = await EntraPeopleStore.connect(dsn, mapping.tenant_id, by_administrator)
    try:
        access = first_administrator_access_from_env(store.by_administrator, scheme)
        await store.seed_first_administrators(first, audit, access)
    except BaseException:
        await store.close()
        raise
    return store
