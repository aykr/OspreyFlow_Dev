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

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import cast, get_args

import asyncpg
from pydantic import BaseModel, Field, field_validator

from conduit_common.identity import new_id
from schemas.domain import DomainPack, Interval, Principal

logger = logging.getLogger(__name__)

#: What a stored pack may be. `schemas.domain.DomainPack` is the one definition (ADR-126).
_KNOWN_PACKS: frozenset[str] = frozenset(get_args(DomainPack))

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
ALTER TABLE investigations ADD COLUMN IF NOT EXISTS removed_at TIMESTAMPTZ;
ALTER TABLE investigations ADD COLUMN IF NOT EXISTS removed_by TEXT;
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

#: ADR-084. Which case tabs an account has closed: a row means hidden, and no row means open. One
#: row per account and case, so closing a tab says nothing about anyone else's strip of tabs.
_TAB_SQL = """
CREATE TABLE IF NOT EXISTS investigation_tab_state (
    investigation_id TEXT NOT NULL REFERENCES investigations (id),
    account_id TEXT NOT NULL,
    hidden_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (investigation_id, account_id)
);
"""

#: ADR-126 decision 1. The case's domain packs: NULL until anyone chooses (read as the empty list,
#: the POLE core model), an array once someone has, `{}` included. Run on every start, so a database
#: from before the change gains the column. There is no CHECK constraint, so a new pack needs no
#: constraint change; an unknown value is refused on the way in and dropped on the way out.
_DOMAIN_SQL = "ALTER TABLE investigations ADD COLUMN IF NOT EXISTS domains TEXT[]"

#: ADR-128 decision 2 (B3). A branch made from what is lit records its window, and the events it
#: inherits from its parents are held to it. NULL for every case that has none, which is every
#: case from before the change. Run on every start, as the domains column is.
_BRANCH_WINDOW_SQL = """
ALTER TABLE investigations ADD COLUMN IF NOT EXISTS branch_valid_from TIMESTAMPTZ;
ALTER TABLE investigations ADD COLUMN IF NOT EXISTS branch_valid_to TIMESTAMPTZ;
"""

_MIGRATE_EXISTING_SQL = """
UPDATE investigations SET unit_level = 'viewer';
INSERT INTO investigation_grants (investigation_id, account_id, level)
    SELECT id, created_by, 'author' FROM investigations ON CONFLICT DO NOTHING;
"""

_LEVEL_SQL = (
    "SELECT i.id, i.name, i.created_at, i.created_by, i.owning_unit, "
    "i.branched_from, i.branch_valid_from, i.branch_valid_to, i.domains, "
    "g.level AS grant_level, i.unit_level "
    "FROM investigations i "
    "LEFT JOIN investigation_grants g "
    "ON g.investigation_id = i.id AND g.account_id = $3 "
    "WHERE i.id = $1 AND i.owning_unit = $2 AND i.removed_at IS NULL"
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
    #: ADR-126: the domain packs the case carries, sorted and without repeats. Empty means the POLE
    #: core model alone. An unknown value is refused here, so no write can take one; a stored one is
    #: dropped on the way out by `_known_domains`, before it reaches this model.
    domains: list[DomainPack] = Field(default_factory=list)
    #: ADR-126 decision 2: someone has chosen (the column is not NULL), `{}` included. Not on the
    #: wire (`exclude`): it is for a branch, which inherits the stored value exactly, so a branch of
    #: a never-chosen case is never chosen too. See `domains_to_inherit`.
    domains_chosen: bool = Field(default=False, exclude=True)
    #: ADR-128 decision 2: the window a branch made from what is lit was made with, both ends
    #: included; its inherited events are held to it. `None` for every other case. Not on the wire.
    branch_window: Interval | None = Field(default=None, exclude=True)

    def domains_to_inherit(self) -> list[DomainPack] | None:
        """What a branch of this case is created with: the stored value, NULL (None) included, not
        the read-side list, which cannot tell "never chosen" from "chosen POLE"."""
        return self.domains if self.domains_chosen else None

    @field_validator("domains")
    @classmethod
    def _sorted_without_repeats(cls, value: list[DomainPack]) -> list[DomainPack]:
        return sorted(set(value))


def _known_domains(stored: Sequence[str] | None, investigation_id: str) -> list[str]:
    """The stored column as the empty list when NULL, without any value the model does not know
    (written by hand, or left by a removed pack). Such a value is logged and dropped, never an
    error: every case-scoped route reads the case through `get_authorized`, so a strict read would
    make the whole case unreadable (ADR-126 decision 1)."""
    if stored is None:
        return []
    unknown = sorted({value for value in stored if value not in _KNOWN_PACKS})
    if unknown:
        logger.warning(
            "case %s holds domain packs this deployment does not know, ignored: %s",
            investigation_id,
            ", ".join(unknown),
        )
    return [value for value in stored if value in _KNOWN_PACKS]


def _domain_fields(row: asyncpg.Record) -> dict[str, object]:
    """The `domains`, `domains_chosen` and `branch_window` fields of a case row, as stored."""
    window = (
        Interval(valid_from=row["branch_valid_from"], valid_to=row["branch_valid_to"])
        if row["branch_valid_from"] is not None
        else None
    )
    return {
        "domains": _known_domains(row["domains"], row["id"]),
        "domains_chosen": row["domains"] is not None,
        "branch_window": window,
    }


def _checked_domains(domains: Sequence[str]) -> list[DomainPack]:
    """`domains` as the model holds it: sorted, without repeats, and a `ValueError` naming any pack
    this deployment does not know."""
    unknown = sorted({value for value in domains if value not in _KNOWN_PACKS})
    if unknown:
        raise ValueError(
            f"unknown domain packs {', '.join(unknown)}; domains are among "
            f"{', '.join(sorted(_KNOWN_PACKS))}"
        )
    return sorted({cast(DomainPack, value) for value in domains})


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
                await conn.execute(_TAB_SQL)
                await conn.execute(_DOMAIN_SQL)
                await conn.execute(_BRANCH_WINDOW_SQL)
                if first_time:
                    await conn.execute(_MIGRATE_EXISTING_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def create(
        self,
        principal: Principal,
        *,
        name: str,
        branched_from: str | None = None,
        domains: Sequence[str] | None = None,
        branch_window: Interval | None = None,
    ) -> Investigation:
        """`owning_unit` is always the *acting* principal's own `org_unit`
        — for a branch, that is the branching principal, never inherited
        from the source investigation (`app.py`'s `branch_investigation`
        already authorised the branching principal against the source
        before calling this). The creator is the case's first Author, and a new case is
        visible to nobody else until an Author shares it (ADR-052 §2, §4).

        `domains` (ADR-126): None leaves the column NULL, "never chosen"; a list, empty included,
        is a choice. An unknown pack is a `ValueError`, before any row is written."""
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("a case needs a name")
        chosen = None if domains is None else _checked_domains(domains)
        investigation = Investigation(
            id=new_id(),
            name=clean_name,
            created_at=datetime.now(UTC),
            created_by=principal.id,
            owning_unit=principal.org_unit,
            branched_from=branched_from,
            domains=chosen or [],
            domains_chosen=chosen is not None,
            branch_window=branch_window,
        )
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO investigations "
                "(id, name, created_at, created_by, owning_unit, branched_from, domains, "
                "branch_valid_from, branch_valid_to) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
                investigation.id,
                investigation.name,
                investigation.created_at,
                investigation.created_by,
                investigation.owning_unit,
                investigation.branched_from,
                chosen,
                branch_window.valid_from if branch_window else None,
                branch_window.valid_to if branch_window else None,
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
                "SELECT id, name, created_at, created_by, owning_unit, branched_from, "
                "branch_valid_from, branch_valid_to, domains "
                "FROM investigations WHERE id = $1 AND removed_at IS NULL",
                investigation_id,
            )
        if row is None:
            raise InvestigationNotFoundError(investigation_id)
        return Investigation(**{**dict(row), **_domain_fields(row)})

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
        fields.update(_domain_fields(row))
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
                "i.branched_from, i.branch_valid_from, i.branch_valid_to, i.domains, "
                "g.level AS grant_level, i.unit_level "
                "FROM investigations i "
                "LEFT JOIN investigation_grants g "
                "ON g.investigation_id = i.id AND g.account_id = $3 "
                "WHERE i.id = $1 AND i.owning_unit = $2 AND i.removed_at IS NULL",
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

    # --- stage 2: listing, naming, reading who holds what ---------------------------------

    async def list_for(self, principal: Principal) -> list[tuple[Investigation, AccessLevel]]:
        """The cases `principal` holds a level on, newest first, with that level. Another unit's
        cases never appear, whatever grants exist; a case nobody has shared with this account does
        not either (ADR-052 §7)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT i.id, i.name, i.created_at, i.created_by, i.owning_unit, "
                "i.branched_from, i.branch_valid_from, i.branch_valid_to, i.domains, "
                "g.level AS grant_level, i.unit_level "
                "FROM investigations i "
                "LEFT JOIN investigation_grants g "
                "ON g.investigation_id = i.id AND g.account_id = $2 "
                "WHERE i.owning_unit = $1 AND i.removed_at IS NULL "
                "AND (g.level IS NOT NULL OR i.unit_level IS NOT NULL) "
                "ORDER BY i.created_at DESC, i.id DESC",
                principal.org_unit,
                principal.id,
            )
        listed: list[tuple[Investigation, AccessLevel]] = []
        for row in rows:
            found = self._parse_level_row(row)
            if found is not None and found[1] is not None:
                listed.append((found[0], found[1]))
        return listed

    # --- ADR-084: which tabs an account has closed -------------------------------------------

    async def hidden_tab_ids(self, principal: Principal) -> set[str]:
        """The cases whose tab `principal` has closed. Only this account's own rows: the account
        is in the `WHERE`, not applied afterwards, so one account can never read another's."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT investigation_id FROM investigation_tab_state WHERE account_id = $1",
                principal.id,
            )
        return {row["investigation_id"] for row in rows}

    async def set_tab_hidden(
        self, principal: Principal, investigation_id: str, hidden: bool
    ) -> None:
        """Closes (`hidden`) or reopens `investigation_id`'s tab for `principal` alone. Whether the
        account may see the case at all is the caller's job (the route's level dependency, which
        answers 404 for a case it cannot see); this writes only the caller's own row."""
        async with self._pool.acquire() as conn:
            if hidden:
                await conn.execute(
                    "INSERT INTO investigation_tab_state "
                    "(investigation_id, account_id, hidden_at) VALUES ($1, $2, $3) "
                    "ON CONFLICT (investigation_id, account_id) DO UPDATE SET hidden_at = $3",
                    investigation_id,
                    principal.id,
                    datetime.now(UTC),
                )
            else:
                await conn.execute(
                    "DELETE FROM investigation_tab_state "
                    "WHERE investigation_id = $1 AND account_id = $2",
                    investigation_id,
                    principal.id,
                )

    async def rename(self, investigation_id: str, name: str, *, by: Principal) -> None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("a case needs a name")
        async with self._pool.acquire() as conn, conn.transaction():
            updated = await conn.fetchval(
                "UPDATE investigations SET name = $2 WHERE id = $1 RETURNING id",
                investigation_id,
                clean_name,
            )
            if updated is None:
                raise InvestigationNotFoundError(investigation_id)
            await self._record(conn, investigation_id, by.id, "rename", clean_name, None)

    async def change(
        self,
        investigation_id: str,
        *,
        name: str | None = None,
        domains: Sequence[str] | None = None,
        by: Principal,
    ) -> None:
        """An Author's change of the name, the packs or both, in one transaction: if the case is
        gone (removed by someone else a moment ago) nothing is written and nothing is recorded,
        so a request that changes both is never half applied. Each change is recorded in the
        access history as `rename` and `domains` do on their own. A blank name or an unknown pack
        is a `ValueError`, before anything is written. Authorisation is the caller's job."""
        clean_name = None if name is None else name.strip()
        if clean_name is not None and not clean_name:
            raise ValueError("a case needs a name")
        chosen = None if domains is None else _checked_domains(domains)
        async with self._pool.acquire() as conn, conn.transaction():
            exists = await conn.fetchval(
                "SELECT id FROM investigations WHERE id = $1 AND removed_at IS NULL FOR UPDATE",
                investigation_id,
            )
            if exists is None:
                raise InvestigationNotFoundError(investigation_id)
            if clean_name is not None:
                await conn.execute(
                    "UPDATE investigations SET name = $2 WHERE id = $1",
                    investigation_id,
                    clean_name,
                )
                await self._record(conn, investigation_id, by.id, "rename", clean_name, None)
            if chosen is not None:
                await conn.execute(
                    "UPDATE investigations SET domains = $2 WHERE id = $1", investigation_id, chosen
                )
                await self._record(
                    conn, investigation_id, by.id, "domains", ",".join(chosen) or "pole", None
                )

    async def set_domains(
        self, investigation_id: str, domains: Sequence[str], *, by: Principal
    ) -> None:
        """An Author's change of the case's packs (ADR-126 decision 1), kept in the access history
        as `domains`, the subject the packs in order or `pole` for none. Authorisation is the
        caller's job. An unknown pack is a `ValueError`, before anything is written."""
        chosen = _checked_domains(domains)
        async with self._pool.acquire() as conn, conn.transaction():
            updated = await conn.fetchval(
                "UPDATE investigations SET domains = $2 WHERE id = $1 AND removed_at IS NULL "
                "RETURNING id",
                investigation_id,
                chosen,
            )
            if updated is None:
                raise InvestigationNotFoundError(investigation_id)
            await self._record(
                conn, investigation_id, by.id, "domains", ",".join(chosen) or "pole", None
            )

    async def set_domains_if_unset(
        self, investigation_id: str, domains: Sequence[str], *, by: Principal
    ) -> bool:
        """The seeds' setting (ADR-126 decision 2): the packs, only while the column is NULL, in
        one atomic `UPDATE ... WHERE domains IS NULL`, so a choice anyone has made, POLE included,
        is never overwritten and two seeds racing set it once. True when this call set it, and only
        then is it recorded in the access history."""
        chosen = _checked_domains(domains)
        async with self._pool.acquire() as conn, conn.transaction():
            updated = await conn.fetchval(
                "UPDATE investigations SET domains = $2 "
                "WHERE id = $1 AND domains IS NULL AND removed_at IS NULL RETURNING id",
                investigation_id,
                chosen,
            )
            if updated is None:
                return False
            await self._record(
                conn, investigation_id, by.id, "domains", ",".join(chosen) or "pole", None
            )
            return True

    async def remove(self, investigation_id: str, *, by: Principal) -> None:
        """A soft remove (ADR-052 Amendment 7): the case, its grants and its history stay in the
        database and the graph and analytics stores are untouched; every read then treats the case
        as one that does not exist. Authorisation is the caller's job (an Author, or the
        administrator safety net); this records who and when."""
        async with self._pool.acquire() as conn, conn.transaction():
            removed = await conn.fetchval(
                "UPDATE investigations SET removed_at = $2, removed_by = $3 "
                "WHERE id = $1 AND removed_at IS NULL RETURNING id",
                investigation_id,
                datetime.now(UTC),
                by.id,
            )
            if removed is None:
                raise InvestigationNotFoundError(investigation_id)
            await self._record(conn, investigation_id, by.id, "remove", investigation_id, None)

    async def list_grants(self, investigation_id: str) -> dict[str, AccessLevel]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT account_id, level FROM investigation_grants WHERE investigation_id = $1 "
                "ORDER BY account_id",
                investigation_id,
            )
        return {r["account_id"]: AccessLevel(r["level"]) for r in rows}

    async def unit_level(self, investigation_id: str) -> AccessLevel | None:
        async with self._pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT unit_level FROM investigations WHERE id = $1", investigation_id
            )
        return None if value is None else AccessLevel(value)

    async def get_for_access_admin(
        self, investigation_id: str, principal: Principal
    ) -> Investigation:
        """The administrator's safety net (ADR-052 §4): the case's record, found by unit only, so
        a case whose Authors have left can be given a new one. It returns the record and nothing of
        the case's contents, and it confers no level: reading still needs one. Another unit's
        administrator finds nothing."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, name, created_at, created_by, owning_unit, branched_from, "
                "branch_valid_from, branch_valid_to, domains "
                "FROM investigations WHERE id = $1 AND owning_unit = $2 AND removed_at IS NULL",
                investigation_id,
                principal.org_unit,
            )
        if row is None:
            raise InvestigationNotFoundError(investigation_id)
        return Investigation(**{**dict(row), **_domain_fields(row)})
