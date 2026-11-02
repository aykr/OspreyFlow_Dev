"""`InfluencerStore` — installation-wide link-strength influencers and each case's override
(`06_DECISIONS.md` ADR-139 decision 3). Postgres, small, bootstrapped with `CREATE TABLE IF NOT
EXISTS`, as every other control-plane store.

**Installation-wide: maker–checker** (ADR-133 stage (d)'s pattern). A holder of
`manage_strength_influencers` proposes a whole set as a new version; it is `pending`, and changes
nothing, until a second holder approves it (`approve`), never its proposer (`OwnChangeRefused`).
A second holder may send it back with words, and its proposer may withdraw it the same way. One
version waits at a time. **Every version is kept** in `strength_influencer_versions`, with who
proposed and who decided it, and each step is audited by the route. The set in force is the latest
approved version; before any, the weights file's defaults alone.

**A case override** is its Author's (decision 3): influencers added for the case and installation or
shipped influencers switched off in it. It needs no second person, because it changes only that
case; every version of it is kept in `case_strength_influencers`, and each change is audited.

**Resolution** (`active_for_case`): the case override, then the installation set, then the file
(`ontology/influencers.py`'s `resolve_influencers`).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg

from ontology.influencers import resolve_influencers
from schemas.domain import OntologySchema, Principal
from schemas.strength import (
    ActiveInfluencer,
    CaseInfluencersInput,
    InfluencerSetHistory,
    InfluencerSetVersion,
    StrengthInfluencer,
)

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS strength_influencer_versions (
    version INTEGER PRIMARY KEY,
    influencers JSONB NOT NULL,
    status TEXT NOT NULL,
    proposed_by TEXT NOT NULL,
    proposed_at TIMESTAMPTZ NOT NULL,
    words TEXT NOT NULL DEFAULT '',
    decided_by TEXT,
    decided_at TIMESTAMPTZ,
    decision_words TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS strength_influencer_versions_one_pending
    ON strength_influencer_versions ((status)) WHERE status = 'pending';
CREATE TABLE IF NOT EXISTS case_strength_influencers (
    investigation_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    added JSONB NOT NULL,
    switched_off JSONB NOT NULL,
    words TEXT NOT NULL DEFAULT '',
    set_by TEXT NOT NULL,
    set_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (investigation_id, version)
);
"""

_COLUMNS = (
    "version, influencers, status, proposed_by, proposed_at, words, decided_by, decided_at, "
    "decision_words"
)


class InfluencerRefused(Exception):
    """An influencer naming a type, property or link type the deployment's ontology does not
    declare (422, in words)."""

    def __init__(self, influencer: str, reason: str) -> None:
        super().__init__(reason)
        self.influencer = influencer
        self.reason = reason


def check_influencers(influencers: Sequence[StrengthInfluencer], ontology: OntologySchema) -> None:
    """Every name an influencer uses is one the ontology declares, as a sentence's blanks are
    (ADR-133 decision 1): the trigger's type and property, each value of an enumerated property,
    and each link type."""
    for influencer in influencers:
        for link_type in influencer.link_types:
            if ontology.edge_type(link_type) is None:
                raise InfluencerRefused(
                    influencer.id, f"“{link_type}” is not a link type this deployment declares"
                )
        trigger = influencer.trigger
        if trigger is None:
            continue
        entity = ontology.entity_type(trigger.entity_type)
        if entity is None:
            raise InfluencerRefused(
                influencer.id, f"“{trigger.entity_type}” is not a type this deployment declares"
            )
        declared = next((p for p in entity.properties if p.name == trigger.property), None)
        if declared is None:
            raise InfluencerRefused(
                influencer.id,
                f"a {entity.name} has no property “{trigger.property}” in this deployment",
            )
        if declared.values:
            unknown = [v for v in trigger.values if v not in declared.values]
            if unknown:
                raise InfluencerRefused(
                    influencer.id,
                    f"“{unknown[0]}” is not one of the values a {entity.name}'s "
                    f"{trigger.property} may take",
                )


class InfluencerChangeRefused(Exception):
    """A proposal, approval or sending back that cannot be made, in words (409)."""


class OwnInfluencerChangeRefused(Exception):
    """The proposer of a waiting version tried to approve it (403 `own_change`)."""


@dataclass(frozen=True)
class CaseOverride:
    version: int
    override: CaseInfluencersInput
    set_by: str
    set_at: datetime


def _influencers(raw: Any) -> list[StrengthInfluencer]:
    data: Any = json.loads(raw) if isinstance(raw, str) else raw
    return [StrengthInfluencer.model_validate(i) for i in data or []]


def _version(row: asyncpg.Record, in_force: int | None) -> InfluencerSetVersion:
    return InfluencerSetVersion(
        version=row["version"],
        influencers=_influencers(row["influencers"]),
        status=row["status"],
        proposed_by=row["proposed_by"],
        proposed_at=row["proposed_at"],
        words=row["words"] or "",
        decided_by=row["decided_by"],
        decided_at=row["decided_at"],
        decision_words=row["decision_words"],
        in_force=row["version"] == in_force,
    )


def _dumped(influencers: Sequence[StrengthInfluencer]) -> str:
    return json.dumps([i.model_dump(mode="json") for i in influencers])


class InfluencerStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> InfluencerStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    # --- installation-wide, maker–checker ------------------------------------------------------

    async def _in_force_version(self, conn: asyncpg.Connection) -> int | None:
        value = await conn.fetchval(
            "SELECT max(version) FROM strength_influencer_versions WHERE status = 'approved'"
        )
        return int(value) if value is not None else None

    async def history(self, defaults: Sequence[StrengthInfluencer]) -> InfluencerSetHistory:
        """Every version, newest first, the one in force marked."""
        async with self._pool.acquire() as conn:
            in_force = await self._in_force_version(conn)
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM strength_influencer_versions ORDER BY version DESC"
            )
        return InfluencerSetHistory(
            versions=[_version(r, in_force) for r in rows], defaults=list(defaults)
        )

    async def in_force(self) -> tuple[int, list[StrengthInfluencer]] | None:
        """The approved version in force and its influencers; None before any is approved."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT version, influencers FROM strength_influencer_versions "
                "WHERE status = 'approved' ORDER BY version DESC LIMIT 1"
            )
        if row is None:
            return None
        return int(row["version"]), _influencers(row["influencers"])

    async def propose(
        self, influencers: Sequence[StrengthInfluencer], words: str, principal: Principal
    ) -> InfluencerSetVersion:
        """A new version, waiting for a second person; it changes nothing until approved."""
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("LOCK TABLE strength_influencer_versions IN EXCLUSIVE MODE")
            waiting = await conn.fetchval(
                "SELECT version FROM strength_influencer_versions WHERE status = 'pending'"
            )
            if waiting is not None:
                raise InfluencerChangeRefused(
                    f"version {waiting} is already waiting for a second person's approval; "
                    "approve it or send it back first"
                )
            latest = await conn.fetchval("SELECT max(version) FROM strength_influencer_versions")
            version = int(latest or 0) + 1
            row = await conn.fetchrow(
                f"INSERT INTO strength_influencer_versions ({_COLUMNS}) "
                "VALUES ($1, $2::jsonb, 'pending', $3, $4, $5, NULL, NULL, NULL) "
                f"RETURNING {_COLUMNS}",
                version, _dumped(influencers), principal.id, now, words,
            )  # fmt: skip
            in_force = await self._in_force_version(conn)
        assert row is not None
        return _version(row, in_force)

    async def approve(self, version: int, principal: Principal) -> InfluencerSetVersion:
        """The waiting version takes effect, decided by `principal`, never its proposer."""
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM strength_influencer_versions WHERE version = $1 "
                "FOR UPDATE",
                version,
            )
            if row is None or row["status"] != "pending":
                raise InfluencerChangeRefused(f"version {version} is not waiting for approval")
            if row["proposed_by"] == principal.id:
                raise OwnInfluencerChangeRefused(
                    "you proposed this version; a second person with the right must approve it"
                )
            row = await conn.fetchrow(
                "UPDATE strength_influencer_versions SET status = 'approved', decided_by = $2, "
                f"decided_at = $3 WHERE version = $1 RETURNING {_COLUMNS}",
                version, principal.id, now,
            )  # fmt: skip
            in_force = await self._in_force_version(conn)
        assert row is not None
        return _version(row, in_force)

    async def send_back(
        self, version: int, words: str, principal: Principal
    ) -> InfluencerSetVersion:
        """The waiting version is turned down with words (or withdrawn by its proposer); the set in
        force stays as it was."""
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                "UPDATE strength_influencer_versions SET status = 'sent_back', decided_by = $2, "
                "decided_at = $3, decision_words = $4 WHERE version = $1 AND status = 'pending' "
                f"RETURNING {_COLUMNS}",
                version, principal.id, now, words,
            )  # fmt: skip
            if row is None:
                raise InfluencerChangeRefused(f"version {version} is not waiting for approval")
            in_force = await self._in_force_version(conn)
        return _version(row, in_force)

    # --- a case's override ---------------------------------------------------------------------

    async def case_override(self, investigation_id: str) -> CaseOverride | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT version, added, switched_off, words, set_by, set_at "
                "FROM case_strength_influencers WHERE investigation_id = $1 "
                "ORDER BY version DESC LIMIT 1",
                investigation_id,
            )
        if row is None:
            return None
        switched = row["switched_off"]
        return CaseOverride(
            version=int(row["version"]),
            override=CaseInfluencersInput(
                added=_influencers(row["added"]),
                switched_off=json.loads(switched) if isinstance(switched, str) else switched,
                words=row["words"] or "",
            ),
            set_by=row["set_by"],
            set_at=row["set_at"],
        )

    async def set_case(
        self, investigation_id: str, override: CaseInfluencersInput, principal: Principal
    ) -> CaseOverride:
        """A new version of the case's override, at once (no second person: it changes only this
        case). Clearing it is a version with nothing added and nothing switched off."""
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext('case_strength_influencers:' || $1))",
                investigation_id,
            )
            latest = await conn.fetchval(
                "SELECT max(version) FROM case_strength_influencers WHERE investigation_id = $1",
                investigation_id,
            )
            version = int(latest or 0) + 1
            await conn.execute(
                "INSERT INTO case_strength_influencers (investigation_id, version, added, "
                "switched_off, words, set_by, set_at) VALUES ($1, $2, $3::jsonb, $4::jsonb, $5, "
                "$6, $7)",
                investigation_id, version, _dumped(override.added),
                json.dumps(override.switched_off), override.words, principal.id, now,
            )  # fmt: skip
        return CaseOverride(version=version, override=override, set_by=principal.id, set_at=now)

    # --- resolution ----------------------------------------------------------------------------

    async def active_for_case(
        self, investigation_id: str | None, shipped: Sequence[StrengthInfluencer]
    ) -> tuple[list[ActiveInfluencer], list[str], CaseOverride | None]:
        """The influencers in force in a case (none named: the installation's), what the case
        switched off, and its override."""
        installation = await self.in_force()
        case = await self.case_override(investigation_id) if investigation_id else None
        active, switched_off = resolve_influencers(
            shipped,
            installation[1] if installation else None,
            case.override if case else None,
            installation_version=installation[0] if installation else None,
            case_version=case.version if case else None,
        )
        return active, switched_off, case


__all__ = [
    "CaseOverride",
    "InfluencerRefused",
    "check_influencers",
    "InfluencerChangeRefused",
    "InfluencerStore",
    "OwnInfluencerChangeRefused",
]
