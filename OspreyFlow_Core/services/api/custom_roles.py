"""Custom roles and teams (`06_DECISIONS.md` ADR-112 Amendments 4 and 5, ADR-145 decision 7 and
Amendment 5; ADR-146 Amendment 1).

**A custom role** is a name and a set of existing rights, versioned (v1, v2 …) and audited. A person
holds it as `role:<id>` in their identity-provider `roles` attribute; its rights are its current
version's, read from this store on every request that carries one (`expand`), never cached, so an
edit takes effect at once (the owner's L2.5 Q1 (a)). The built-in roles and the *Super user* preset
are listed and copied, never edited (`schemas.rights`).

**Refused at the route** (`role_refusal`, `leaves_no_people_manager`): a name already used, no
rights, a right that is not one, a forbidden pair (no role both proposes and approves the same kind
of decision), a right the giver may not give (`giver_may_give`, the owner's Q3b (a)), and a
change that leaves no enabled person holding `manage_people` (ADR-145 Amendment 5).

**A team** is a custom role with a display name and a contact mailbox. Its members are the role's
holders (the owner's L2.5 Q4 (a)): a person's level in a case through the team is read from the
`role:<id>` in the token on each request (`investigations.grant_subjects`), and ends when the role
is taken away. One member is its **lead**; an administrator names the lead, hands the role over to
another member, or names a **cover until a date** (inclusive), after which the lead acts again with
no action (`acting_lead`). The lead's own hand-over and cover are rules' L2.10, in the queue.
A service account is never a member, a lead or a cover. **What rules' L2.10
reads:** `CustomRoleStore.team(role_id)` and `acting_lead(team, today)`: who may use ADR-146
Amendment 1's lead tools today.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any

import asyncpg

from schemas.admin import CustomRole, CustomRoleVersion, PersonAccount, Team, TeamInput, TeamMember
from schemas.domain import Principal
from schemas.rights import (
    ADMINISTRATION_RIGHTS,
    CUSTOM_ROLE_PREFIX,
    SINGLE_RIGHT_PREFIX,
    Right,
    forbidden_pairs_in,
    right_name,
    rights_for,
    rights_listed,
)

BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS custom_roles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version INTEGER NOT NULL,
    rights TEXT[] NOT NULL,
    changed_by TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS custom_roles_name_key
    ON custom_roles (lower(regexp_replace(btrim(name), '\\s+', ' ', 'g')));
CREATE TABLE IF NOT EXISTS custom_role_versions (
    role_id TEXT NOT NULL REFERENCES custom_roles (id),
    version INTEGER NOT NULL,
    name TEXT NOT NULL,
    rights TEXT[] NOT NULL,
    changed_by TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (role_id, version)
);
CREATE TABLE IF NOT EXISTS teams (
    role_id TEXT PRIMARY KEY REFERENCES custom_roles (id),
    display_name TEXT NOT NULL,
    mailbox TEXT NOT NULL,
    lead TEXT,
    cover TEXT,
    cover_until DATE
);
-- A team is named by its display name in *Make live* and *Change owner…* (`_owners_allowed`), so
-- two teams never share one, case and spacing aside.
CREATE UNIQUE INDEX IF NOT EXISTS teams_display_name_key
    ON teams (lower(regexp_replace(btrim(display_name), '\\s+', ' ', 'g')));
"""

#: The advisory lock every lock-out check holds with its write (`people_lock`); any fixed key.
PEOPLE_LOCK = 0x05EF_A001

#: The built-in role names a custom role's name may not take, case aside.
_BUILT_IN_NAMES = frozenset(
    {
        "analyst",
        "data engineer",
        "admin",
        "administrator",
        "reports viewer",
        "rule author",
        "super user",
    }
)
_RIGHT_VALUES = {r.value: r for r in Right}


def name_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).lower()


class RoleRefused(Exception):
    """A custom role, or a change to who holds one, refused in words: `error` is the answer's
    code."""

    def __init__(self, error: str, words: str, **detail: object) -> None:
        super().__init__(words)
        self.error = error
        self.words = words
        self.detail = detail


def giver_may_give(right: Right, giver_rights: Iterable[Right]) -> bool:
    """Whether someone holding `giver_rights` may put `right` in a role, or give it: the owner's
    ruling on L2.5 Q3b (a), 8 November 2026. An administration right only by a holder of it, every
    other right freely; the clearance and handling ceiling (ADR-114 Amendment 5) stands apart."""
    return right not in ADMINISTRATION_RIGHTS or right in set(giver_rights)


def parse_rights(names: Sequence[str]) -> list[Right]:
    unknown = sorted({n for n in names if n not in _RIGHT_VALUES})
    if unknown:
        raise RoleRefused(
            "unknown_right", f"not a right of this deployment: {', '.join(unknown)}", rights=unknown
        )
    # Only the known names are read: the refusal above is what stops an unknown one, never a
    # lookup failing after it (rule 15).
    return sorted({_RIGHT_VALUES[n] for n in names if n in _RIGHT_VALUES}, key=lambda r: r.value)


def role_refusal(
    name: str,
    rights: Sequence[str],
    *,
    giver_rights: Iterable[Right],
    names_taken: Iterable[str],
) -> list[Right]:
    """ADR-145 decision 7's refusals, before anything is written; the role's rights if none."""
    if name_key(name) in _BUILT_IN_NAMES or name_key(name) in {name_key(n) for n in names_taken}:
        raise RoleRefused("name_taken", f"a role called {name.strip()} already exists")
    if not rights:
        raise RoleRefused("no_rights", "a role needs at least one right")
    parsed = parse_rights(rights)
    pairs = forbidden_pairs_in(parsed)
    if pairs:
        a, b = pairs[0]
        raise RoleRefused(
            "forbidden_pair",
            f"a role cannot hold both {right_name(a)} and {right_name(b)}: no role both proposes "
            "and approves the same kind of decision",
            pair=[a.value, b.value],
        )
    held = set(giver_rights)
    beyond = [r.value for r in parsed if not giver_may_give(r, held)]
    if beyond:
        raise RoleRefused(
            "beyond_your_rights",
            f"you cannot give a right you do not hold: {rights_listed(beyond)}",
            rights=beyond,
        )
    return parsed


def people_managers(
    people: Iterable[PersonAccount], custom: Mapping[str, Iterable[Right]]
) -> list[str]:
    """The enabled people (never a system account) who hold `manage_people`, by their roles and
    the custom roles' rights as given, and who have signed in at least once: on Entra ID a person
    added by object id who never has is no proof anyone can still administer (ADR-148 Amendment 8;
    the orchestrator's ruling, 12 November 2026)."""
    return [
        p.id
        for p in people
        if p.enabled
        and p.signed_in
        and not p.system_account
        and Right.MANAGE_PEOPLE in rights_for(p.roles, custom)
    ]


def leaves_no_people_manager(
    people: Iterable[PersonAccount], custom_after: Mapping[str, Iterable[Right]]
) -> None:
    """ADR-145 Amendment 5's lock-out: refused when, after the change, no enabled person holds
    `manage_people`."""
    if not people_managers(people, custom_after):
        raise RoleRefused(
            "locks_out_administrators",
            "this would leave nobody able to manage people: keep manage_people with at least one "
            "enabled person who has signed in",
        )


def custom_role_ids(roles: Iterable[str]) -> list[str]:
    return [r[len(CUSTOM_ROLE_PREFIX) :] for r in roles if r.startswith(CUSTOM_ROLE_PREFIX)]


def expand(principal: Principal, current: Mapping[str, Iterable[Right]]) -> Principal:
    """The principal with each custom role's current rights added as single grants, so every
    `rights_for(principal.roles)` reads them; `role:<id>` is kept, which is what a team's level
    reads.
    A custom role that is not in `current` (none such, or removed) adds nothing."""
    ids = custom_role_ids(principal.roles)
    if not ids:
        return principal
    added = sorted(
        f"{SINGLE_RIGHT_PREFIX}{r.value}"
        for r in rights_for([f"{CUSTOM_ROLE_PREFIX}{i}" for i in ids], current)
    )
    return principal.model_copy(update={"roles": [*principal.roles, *added]})


def acting_lead(team: Team, today: date) -> str | None:
    """Who acts as the team's lead today (ADR-112 Amendment 5 decision 4, ADR-146 Amendment 1): the
    cover through their last day, else the lead. What rules' L2.10 holds the lead tools to."""
    if team.cover is not None and team.cover_until is not None and today <= team.cover_until:
        return team.cover
    return team.lead


def _role(row: asyncpg.Record, team: Team | None = None, holders: int = 0) -> CustomRole:
    return CustomRole(
        id=row["id"],
        name=row["name"],
        version=row["version"],
        rights=[_RIGHT_VALUES[r] for r in row["rights"] if r in _RIGHT_VALUES],
        changed_by=row["changed_by"],
        changed_at=row["changed_at"],
        holders=holders,
        team=team,
    )


def _team(row: asyncpg.Record, today: date, members: Sequence[TeamMember] = ()) -> Team:
    team = Team(
        role_id=row["role_id"],
        display_name=row["display_name"],
        mailbox=row["mailbox"],
        lead=row["lead"],
        cover=row["cover"],
        cover_until=row["cover_until"],
        members=list(members),
    )
    return team.model_copy(update={"acting_lead": acting_lead(team, today)})


async def rights_on(conn: asyncpg.Connection) -> dict[str, frozenset[Right]]:
    """Each custom role's current rights, read on a connection the caller holds (its lock and
    transaction: the Entra people store's start, ADR-148 Amendment 8). None yet made, none."""
    if await conn.fetchval("SELECT to_regclass('custom_roles')") is None:
        return {}
    rows = await conn.fetch("SELECT id, rights FROM custom_roles")
    return {
        r["id"]: frozenset(_RIGHT_VALUES[x] for x in r["rights"] if x in _RIGHT_VALUES)
        for r in rows
    }


class CustomRoleStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> CustomRoleStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    @asynccontextmanager
    async def people_lock(self) -> AsyncIterator[None]:
        """ADR-145 Amendment 5's lock-out, serialised: every change that could leave nobody holding
        `manage_people` (a role's rights, a person's roles, a removal, a disable) reads the people
        and writes its change under this one session-level advisory lock, across Conduit replicas,
        so two changes each fine alone cannot together leave no administrator."""
        async with self._pool.acquire() as conn:
            await conn.execute("SELECT pg_advisory_lock($1)", PEOPLE_LOCK)
            try:
                yield
            finally:
                await conn.execute("SELECT pg_advisory_unlock($1)", PEOPLE_LOCK)

    async def current_rights(self, ids: Sequence[str] | None = None) -> dict[str, frozenset[Right]]:
        """Each custom role's current rights (only `ids`, when given): read at every request that
        carries a custom role, never kept between them."""
        async with self._pool.acquire() as conn:
            if ids is None:
                rows = await conn.fetch("SELECT id, rights FROM custom_roles")
            else:
                rows = await conn.fetch(
                    "SELECT id, rights FROM custom_roles WHERE id = ANY($1::text[])", list(ids)
                )
        return {
            r["id"]: frozenset(_RIGHT_VALUES[x] for x in r["rights"] if x in _RIGHT_VALUES)
            for r in rows
        }

    async def expand(self, principal: Principal) -> Principal:
        ids = custom_role_ids(principal.roles)
        if not ids:
            return principal
        return expand(principal, await self.current_rights(ids))

    async def names(self, *, except_id: str | None = None) -> list[str]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, name FROM custom_roles")
        return [r["name"] for r in rows if r["id"] != except_id]

    async def all(self, today: date) -> list[CustomRole]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM custom_roles ORDER BY lower(name), id")
            teams = {t["role_id"]: t for t in await conn.fetch("SELECT * FROM teams")}
        return [_role(r, _team(teams[r["id"]], today) if r["id"] in teams else None) for r in rows]

    async def get(self, role_id: str, today: date) -> CustomRole | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM custom_roles WHERE id = $1", role_id)
            team = await conn.fetchrow("SELECT * FROM teams WHERE role_id = $1", role_id)
        if row is None:
            return None
        return _role(row, None if team is None else _team(team, today))

    async def create(self, name: str, rights: Sequence[Right], *, by: str) -> CustomRole:
        role_id = secrets.token_hex(6)
        now = datetime.now(UTC)
        values = [r.value for r in rights]
        async with self._pool.acquire() as conn, conn.transaction():
            try:
                row = await conn.fetchrow(
                    "INSERT INTO custom_roles (id, name, version, rights, changed_by, changed_at) "
                    "VALUES ($1, $2, 1, $3, $4, $5) RETURNING *",
                    role_id,
                    name.strip(),
                    values,
                    by,
                    now,
                )
            except asyncpg.UniqueViolationError as error:
                raise RoleRefused(
                    "name_taken", f"a role called {name.strip()} already exists"
                ) from error
            await conn.execute(
                "INSERT INTO custom_role_versions VALUES ($1, 1, $2, $3, $4, $5)",
                role_id,
                name.strip(),
                values,
                by,
                now,
            )
        assert row is not None
        return _role(row)

    async def update(
        self, role_id: str, name: str, rights: Sequence[Right], *, by: str
    ) -> tuple[CustomRole, CustomRole]:
        """A new version; the one before it and the one after, for the audit."""
        now = datetime.now(UTC)
        values = [r.value for r in rights]
        async with self._pool.acquire() as conn, conn.transaction():
            before = await conn.fetchrow(
                "SELECT * FROM custom_roles WHERE id = $1 FOR UPDATE", role_id
            )
            if before is None:
                raise KeyError(role_id)
            try:
                after = await conn.fetchrow(
                    "UPDATE custom_roles SET name = $2, rights = $3, version = version + 1, "
                    "changed_by = $4, changed_at = $5 WHERE id = $1 RETURNING *",
                    role_id,
                    name.strip(),
                    values,
                    by,
                    now,
                )
            except asyncpg.UniqueViolationError as error:
                raise RoleRefused(
                    "name_taken", f"a role called {name.strip()} already exists"
                ) from error
            assert after is not None
            await conn.execute(
                "INSERT INTO custom_role_versions VALUES ($1, $2, $3, $4, $5, $6)",
                role_id,
                after["version"],
                name.strip(),
                values,
                by,
                now,
            )
        return _role(before), _role(after)

    async def versions(self, role_id: str) -> list[CustomRoleVersion]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM custom_role_versions WHERE role_id = $1 ORDER BY version", role_id
            )
        return [
            CustomRoleVersion(
                version=r["version"],
                name=r["name"],
                rights=[_RIGHT_VALUES[x] for x in r["rights"] if x in _RIGHT_VALUES],
                changed_by=r["changed_by"],
                changed_at=r["changed_at"],
            )
            for r in rows
        ]

    # --- teams -------------------------------------------------------------------------------
    async def make_team(self, role_id: str, team: TeamInput, today: date) -> Team:
        async with self._pool.acquire() as conn:
            try:
                row = await self._upsert_team(conn, role_id, team)
            except asyncpg.UniqueViolationError as error:
                raise RoleRefused(
                    "team_name_taken", f"a team called {team.display_name.strip()} already exists"
                ) from error
        assert row is not None
        return _team(row, today)

    @staticmethod
    async def _upsert_team(conn: asyncpg.Connection, role_id: str, team: TeamInput) -> Any:
        return await conn.fetchrow(
            "INSERT INTO teams (role_id, display_name, mailbox) VALUES ($1, $2, $3) "
            "ON CONFLICT (role_id) DO UPDATE SET display_name = EXCLUDED.display_name, "
            "mailbox = EXCLUDED.mailbox RETURNING *",
            role_id,
            team.display_name.strip(),
            team.mailbox.strip(),
        )

    async def team(self, role_id: str, today: date) -> Team | None:
        """A team, as rules' L2.10 reads it: its lead, its cover and who acts today."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM teams WHERE role_id = $1", role_id)
        return None if row is None else _team(row, today)

    async def teams(self, today: date) -> list[Team]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM teams ORDER BY lower(display_name)")
        return [_team(r, today) for r in rows]

    async def set_lead(self, role_id: str, lead: str, today: date) -> tuple[Team, Team]:
        """The lead named or handed over; a cover who becomes lead stops covering."""
        async with self._pool.acquire() as conn, conn.transaction():
            before = await conn.fetchrow(
                "SELECT * FROM teams WHERE role_id = $1 FOR UPDATE", role_id
            )
            if before is None:
                raise KeyError(role_id)
            after = await conn.fetchrow(
                "UPDATE teams SET lead = $2, "
                "cover = CASE WHEN cover = $2 THEN NULL ELSE cover END, "
                "cover_until = CASE WHEN cover = $2 THEN NULL ELSE cover_until END "
                "WHERE role_id = $1 RETURNING *",
                role_id,
                lead,
            )
        assert after is not None
        return _team(before, today), _team(after, today)

    async def set_cover(
        self, role_id: str, cover: str | None, until: date | None, today: date
    ) -> tuple[Team, Team]:
        async with self._pool.acquire() as conn, conn.transaction():
            before = await conn.fetchrow(
                "SELECT * FROM teams WHERE role_id = $1 FOR UPDATE", role_id
            )
            if before is None:
                raise KeyError(role_id)
            after = await conn.fetchrow(
                "UPDATE teams SET cover = $2, cover_until = $3 WHERE role_id = $1 RETURNING *",
                role_id,
                cover,
                until if cover is not None else None,
            )
        assert after is not None
        return _team(before, today), _team(after, today)


__all__ = [
    "BOOTSTRAP_SQL",
    "CustomRoleStore",
    "RoleRefused",
    "acting_lead",
    "custom_role_ids",
    "expand",
    "giver_may_give",
    "leaves_no_people_manager",
    "name_key",
    "parse_rights",
    "people_managers",
    "role_refusal",
]
