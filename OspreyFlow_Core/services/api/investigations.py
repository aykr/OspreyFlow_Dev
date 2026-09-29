"""Investigation metadata — `spec/03_CONDUIT_MIDDLEWARE.md` §3.1.

Neither the graph itself (the Vault's job) nor ephemeral working-set state
(Valkey's job, `working_set/store.py`) — an investigation record is small,
relational, control-plane metadata: who created it, when, and (for a
branch) what it was forked from. Postgres already exists in this phase for
the audit stream, so investigation metadata lives in the same database
rather than inventing a fourth store for a handful of columns.

**`owning_unit` is the investigation-level authorization boundary** —
the divergence-review fix: every investigation-scoped route in `app.py`
now checks `principal.org_unit == investigation.owning_unit` before doing
anything else. Deliberately shaped like `Handling.owning_unit`
(`01_DOMAIN_MODEL.md` §2.2) rather than a new concept, and deliberately
*not* `clearance`-gated — a shared investigation is exactly the case this
column exists to allow, with node/edge-level visibility still governed
separately by the handling filter on every read
(`working_set/service.py`'s `_project`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

import asyncpg
from pydantic import BaseModel

from conduit_common.identity import new_id
from schemas.domain import Principal

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS investigations (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    created_by TEXT NOT NULL,
    owning_unit TEXT NOT NULL,
    branched_from TEXT REFERENCES investigations (id)
);
"""

#: ADR-052. Applied once: `investigation_grants` not existing yet is what marks a database from
#: before the change, so the migration below runs exactly then and never again (an Author who
#: removes the creator's own grant must not have it put back by a restart).
_ACCESS_SQL = """
ALTER TABLE investigations ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT '';
ALTER TABLE investigations ADD COLUMN IF NOT EXISTS unit_level TEXT;
CREATE TABLE IF NOT EXISTS investigation_grants (
    investigation_id TEXT NOT NULL REFERENCES investigations (id),
    account_id TEXT NOT NULL,
    level TEXT NOT NULL,
    PRIMARY KEY (investigation_id, account_id)
);
CREATE TABLE IF NOT EXISTS investigation_access_history (
    id BIGSERIAL PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations (id),
    changed_at TIMESTAMPTZ NOT NULL,
    changed_by TEXT NOT NULL,
    action TEXT NOT NULL,
    subject TEXT NOT NULL,
    level TEXT
);
"""

_MIGRATE_EXISTING_SQL = """
UPDATE investigations SET unit_level = 'viewer';
INSERT INTO investigation_grants (investigation_id, account_id, level)
    SELECT id, created_by, 'author' FROM investigations ON CONFLICT DO NOTHING;
"""

_LEVEL_SQL = (
    "SELECT i.id, i.name, i.created_at, i.created_by, i.owning_unit, "
    "i.branched_from, g.level AS grant_level, i.unit_level "
    "FROM investigations i "
    "LEFT JOIN investigation_grants g "
    "ON g.investigation_id = i.id AND g.account_id = $3 "
    "WHERE i.id = $1 AND i.owning_unit = $2"
)

_RANK = {"viewer": 1, "editor": 2, "author": 3}


class AccessLevel(StrEnum):
    """What an account may do on a case; each level includes the one below (ADR-052 §1)."""

    VIEWER = "viewer"
    EDITOR = "editor"
    AUTHOR = "author"

    @property
    def rank(self) -> int:
        return _RANK[self.value]


class InsufficientAccessError(Exception):
    """The account holds a level on the case, but not the one this action needs. A 403: unlike
    "no level at all" (a 404, so the case's existence does not leak), the account can already see
    that the case exists."""


class AccessHistoryEntry(BaseModel):
    changed_at: datetime
    changed_by: str
    action: str
    subject: str
    level: str | None = None


class Investigation(BaseModel):
    id: str
    name: str = ""
    created_at: datetime
    created_by: str
    owning_unit: str
    branched_from: str | None = None


class InvestigationNotFoundError(Exception):
    """Also raised — deliberately, not a 403 — when the investigation
    exists but `principal.org_unit` does not match `owning_unit`: the
    existence-leak discipline `00_ARCHITECTURE.md` §5 already applies at
    node/edge level extends to the investigation id itself. An
    unauthorised principal must not be able to tell "wrong unit" apart
    from "no such investigation" from outside."""


class InvestigationStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> InvestigationStore:
        # `min_size`/`max_size` — `hotlists.py::HotlistStore.connect`'s own comment has the full
        # Stage 6c connection-ceiling reasoning. Sized larger than the control-plane stores: every
        # investigation-scoped route depends on this one via the level dependencies.
        pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=8)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
            # One Conduit instance migrates; another starting at the same moment waits and then
            # finds the tables already there.
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(52052)")
                first_time = (
                    await conn.fetchval("SELECT to_regclass('investigation_grants')") is None
                )
                await conn.execute(_ACCESS_SQL)
                if first_time:
                    await conn.execute(_MIGRATE_EXISTING_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def create(
        self, principal: Principal, *, name: str, branched_from: str | None = None
    ) -> Investigation:
        """`owning_unit` is always the *acting* principal's own `org_unit`
        — for a branch, that is the branching principal, never inherited
        from the source investigation (`app.py`'s `branch_investigation`
        already authorised the branching principal against the source
        before calling this). The creator is the case's first Author, and a new case is
        visible to nobody else until an Author shares it (ADR-052 §2, §4)."""
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("a case needs a name")
        investigation = Investigation(
            id=new_id(),
            name=clean_name,
            created_at=datetime.now(UTC),
            created_by=principal.id,
            owning_unit=principal.org_unit,
            branched_from=branched_from,
        )
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO investigations "
                "(id, name, created_at, created_by, owning_unit, branched_from) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                investigation.id,
                investigation.name,
                investigation.created_at,
                investigation.created_by,
                investigation.owning_unit,
                investigation.branched_from,
            )
            await conn.execute(
                "INSERT INTO investigation_grants (investigation_id, account_id, level) "
                "VALUES ($1, $2, 'author')",
                investigation.id,
                principal.id,
            )
            await self._record(
                conn, investigation.id, principal.id, "create", principal.id, AccessLevel.AUTHOR
            )
        return investigation

    async def get(self, investigation_id: str) -> Investigation:
        """No authorization check here — this is the raw record lookup.
        `get_authorized` is what every route actually uses."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, name, created_at, created_by, owning_unit, branched_from "
                "FROM investigations WHERE id = $1",
                investigation_id,
            )
        if row is None:
            raise InvestigationNotFoundError(investigation_id)
        return Investigation(**dict(row))

    @staticmethod
    def _parse_level_row(
        row: asyncpg.Record | None,
    ) -> tuple[Investigation, AccessLevel | None] | None:
        """The case and the level held on it, from the row both queries below return. The level is
        the higher of the account's own grant and the unit-wide level."""
        if row is None:
            return None
        held = [AccessLevel(v) for v in (row["grant_level"], row["unit_level"]) if v is not None]
        level = max(held, key=lambda held_level: held_level.rank) if held else None
        fields = {
            k: row[k]
            for k in ("id", "name", "created_at", "created_by", "owning_unit", "branched_from")
        }
        return Investigation(**fields), level

    async def effective_level(
        self, investigation_id: str, principal: Principal
    ) -> AccessLevel | None:
        found = await self._fetch_level(investigation_id, principal)
        return None if found is None else found[1]

    async def _fetch_level(
        self, investigation_id: str, principal: Principal
    ) -> tuple[Investigation, AccessLevel | None] | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                _LEVEL_SQL, investigation_id, principal.org_unit, principal.id
            )
        return self._parse_level_row(row)

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        """The one method every route calls, with the level the route needs (ADR-052 §2).

        No level at all — no such case, another unit's case, or a case nobody has shared with
        this account — is `InvestigationNotFoundError`, one and the same, so the case's existence
        does not leak (ADR-041). A level too low for `need` is `InsufficientAccessError`. A grant
        never widens what the unit, clearance and handling rules already allow: the unit check is
        in the query and the others are applied by every read the route goes on to make."""
        # The query is written out here, not delegated, so that the principal predicate is
        # visibly in this method's own body (ADR-041's `authorized-query-check`).
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT i.id, i.name, i.created_at, i.created_by, i.owning_unit, "
                "i.branched_from, g.level AS grant_level, i.unit_level "
                "FROM investigations i "
                "LEFT JOIN investigation_grants g "
                "ON g.investigation_id = i.id AND g.account_id = $3 "
                "WHERE i.id = $1 AND i.owning_unit = $2",
                investigation_id,
                principal.org_unit,
                principal.id,
            )
        found = self._parse_level_row(row)
        if found is None:
            raise InvestigationNotFoundError(investigation_id)
        investigation, level = found
        if level is None:
            raise InvestigationNotFoundError(investigation_id)
        if level.rank < need.rank:
            raise InsufficientAccessError(
                f"{need.value} access is needed on this case; this account has {level.value}"
            )
        return investigation

    # --- managing access (ADR-052 §4, §5) ------------------------------------------------

    @staticmethod
    async def _record(
        conn: asyncpg.Connection,
        investigation_id: str,
        by: str,
        action: str,
        subject: str,
        level: AccessLevel | None,
    ) -> None:
        await conn.execute(
            "INSERT INTO investigation_access_history "
            "(investigation_id, changed_at, changed_by, action, subject, level) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            investigation_id,
            datetime.now(UTC),
            by,
            action,
            subject,
            None if level is None else level.value,
        )

    async def set_grant(
        self, investigation_id: str, account_id: str, level: AccessLevel, *, by: Principal
    ) -> None:
        """Authorisation is the caller's job (an Author, or `osprey-admin`); this records it."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO investigation_grants (investigation_id, account_id, level) "
                "VALUES ($1, $2, $3) "
                "ON CONFLICT (investigation_id, account_id) DO UPDATE SET level = EXCLUDED.level",
                investigation_id,
                account_id,
                level.value,
            )
            await self._record(conn, investigation_id, by.id, "grant", account_id, level)

    async def remove_grant(self, investigation_id: str, account_id: str, *, by: Principal) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "DELETE FROM investigation_grants WHERE investigation_id = $1 AND account_id = $2",
                investigation_id,
                account_id,
            )
            await self._record(conn, investigation_id, by.id, "revoke", account_id, None)

    async def set_unit_level(
        self, investigation_id: str, level: AccessLevel | None, *, by: Principal
    ) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            unit = await conn.fetchval(
                "UPDATE investigations SET unit_level = $2 WHERE id = $1 RETURNING owning_unit",
                investigation_id,
                None if level is None else level.value,
            )
            if unit is None:
                raise InvestigationNotFoundError(investigation_id)
            await self._record(conn, investigation_id, by.id, "unit_level", unit, level)

    async def access_history(self, investigation_id: str) -> list[AccessHistoryEntry]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT changed_at, changed_by, action, subject, level "
                "FROM investigation_access_history WHERE investigation_id = $1 ORDER BY id",
                investigation_id,
            )
        return [AccessHistoryEntry(**dict(r)) for r in rows]
