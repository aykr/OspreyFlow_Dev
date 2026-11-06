"""Connections and registered sources (`06_DECISIONS.md` ADR-140 decision 7, Amendment 4).

**Connections** are the deployment's, kept by its administrators: one kind today, `files`, the
ingest root. The built-in one (`FILES_CONNECTION_ID`) is written at start-up so every deployment has
it; an administrator may name others, for the folders an operator keeps apart.

**Sources** belong to a dataset. Every read takes the dataset in its `WHERE` (rule 3): a source of
another dataset is not found, and the answer says nothing of whether it exists. A source is
registered once per (dataset, location); editing its governance is a new version, audited by the
route. Its profile is never stored (`schemas.sources`: computed for each reader).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Protocol

import asyncpg

from conduit_common.identity import new_id
from schemas.domain import Principal
from schemas.sources import (
    Connection,
    ConnectionInput,
    RegisterSourceInput,
    SourceGovernanceInput,
    SourceRefresh,
    SourceTable,
)

#: The deployment's own Files connection: the ingest root (`OSPREY_INGEST_ROOT`).
FILES_CONNECTION_ID = "files"
FILES_CONNECTION_NAME = "Files: the ingest root"


class SourceAlreadyRegisteredError(Exception):
    """The dataset already holds a source reading that location."""


class UnknownConnectionError(Exception):
    """No connection has that id."""


class SourceNotFoundError(Exception):
    """No source of that id in the dataset (another dataset's included: rule 3)."""


class SourceStore(Protocol):
    async def connections(self) -> list[Connection]: ...
    async def add_connection(self, body: ConnectionInput, principal: Principal) -> Connection: ...
    async def list_for(self, dataset_id: str) -> list[SourceTable]: ...
    async def get(self, dataset_id: str, source_id: str) -> SourceTable: ...
    async def register(
        self, dataset_id: str, body: RegisterSourceInput, principal: Principal
    ) -> SourceTable: ...
    async def edit_governance(
        self, dataset_id: str, source_id: str, body: SourceGovernanceInput, principal: Principal
    ) -> SourceTable: ...
    async def adopt_refresh(self, source_id: str, refresh: SourceRefresh) -> None: ...


def _now() -> datetime:
    return datetime.now(UTC)


def _built_in(now: datetime) -> Connection:
    return Connection(
        id=FILES_CONNECTION_ID,
        kind="files",
        name=FILES_CONNECTION_NAME,
        created_by="system",
        created_at=now,
    )


def _registered(dataset_id: str, body: RegisterSourceInput, principal: Principal) -> SourceTable:
    return SourceTable(
        id=new_id(),
        dataset_id=dataset_id,
        connection_id=body.connection_id,
        name=body.name.strip(),
        location=body.location,
        connector_profile=body.connector_profile,
        handling=body.handling,
        legal_basis=body.legal_basis,
        # Amendment 6 point 6: the owner is whoever set it, and nothing starts paused.
        refresh=body.refresh.model_copy(
            update={
                "owner": principal.id,
                "set_at": _now(),
                "paused": False,
                "paused_reason": None,
            }
        ),
        created_by=principal.id,
        created_at=_now(),
    )


def _governed(
    source: SourceTable, body: SourceGovernanceInput, principal: Principal
) -> SourceTable:
    return source.model_copy(
        update={
            "handling": body.handling,
            "legal_basis": body.legal_basis,
            "refresh": _refresh_after(source.refresh, body.refresh, principal),
            "version": source.version + 1,
            "updated_by": principal.id,
            "updated_at": _now(),
        }
    )


def _refresh_after(
    stored: SourceRefresh, given: SourceRefresh | None, principal: Principal
) -> SourceRefresh:
    """An edit's refresh: the stored policy when none is given or it is unchanged (its owner kept);
    otherwise the new one, owned by the editor. Either way the pause is the stored one: only pause
    and resume change it (ADR-110 Amendment 6 point 6)."""
    if given is None or given.policy() == stored.policy():
        return stored
    return given.model_copy(
        update={
            "owner": principal.id,
            "set_at": _now(),
            "paused": stored.paused,
            "paused_reason": stored.paused_reason,
        }
    )


class InMemorySourceStore:
    """The Postgres store's behaviour, refusals included (rule 15), for tests and a test app."""

    def __init__(self) -> None:
        self._connections: dict[str, Connection] = {FILES_CONNECTION_ID: _built_in(_now())}
        self._sources: dict[str, SourceTable] = {}

    async def connections(self) -> list[Connection]:
        return sorted(
            self._connections.values(), key=lambda c: (c.id != FILES_CONNECTION_ID, c.name)
        )

    async def add_connection(self, body: ConnectionInput, principal: Principal) -> Connection:
        made = Connection(
            id=new_id(),
            kind=body.kind,
            name=body.name.strip(),
            created_by=principal.id,
            created_at=_now(),
        )
        self._connections[made.id] = made
        return made

    async def list_for(self, dataset_id: str) -> list[SourceTable]:
        return sorted(
            (s for s in self._sources.values() if s.dataset_id == dataset_id), key=lambda s: s.name
        )

    async def get(self, dataset_id: str, source_id: str) -> SourceTable:
        found = self._sources.get(source_id)
        if found is None or found.dataset_id != dataset_id:
            raise SourceNotFoundError(source_id)
        return found

    async def register(
        self, dataset_id: str, body: RegisterSourceInput, principal: Principal
    ) -> SourceTable:
        if body.connection_id not in self._connections:
            raise UnknownConnectionError(body.connection_id)
        if any(
            s.dataset_id == dataset_id and s.location == body.location
            for s in self._sources.values()
        ):
            raise SourceAlreadyRegisteredError(body.location)
        made = _registered(dataset_id, body, principal)
        self._sources[made.id] = made
        return made

    async def edit_governance(
        self, dataset_id: str, source_id: str, body: SourceGovernanceInput, principal: Principal
    ) -> SourceTable:
        edited = _governed(await self.get(dataset_id, source_id), body, principal)
        self._sources[source_id] = edited
        return edited

    async def watched(self) -> list[SourceTable]:
        """Every source, of any dataset, whose refresh is a folder watch (the executor's alone)."""
        return sorted(
            (s for s in self._sources.values() if s.refresh.trigger == "watch"), key=lambda s: s.id
        )

    async def set_refresh_paused(self, source_id: str, *, paused: bool, reason: str | None) -> None:
        """Pausing is not an edit: no new version, the owner kept (Amendment 6 point 6)."""
        found = self._sources.get(source_id)
        if found is None:
            raise SourceNotFoundError(source_id)
        refresh = found.refresh.model_copy(
            update={"paused": paused, "paused_reason": reason if paused else None}
        )
        self._sources[source_id] = found.model_copy(update={"refresh": refresh})

    async def adopt_refresh(self, source_id: str, refresh: SourceRefresh) -> None:
        """`scripts.migrate_sources` alone (ADR-110 Amendment 6 point 7): a pipeline's watch moved
        onto its source, with its owner, time and pause. Not a governance edit: the pipelines ran by
        that watch before, so none needs attention, and the version stays."""
        found = self._sources.get(source_id)
        if found is None:
            raise SourceNotFoundError(source_id)
        self._sources[source_id] = found.model_copy(update={"refresh": refresh})


_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS ingest_connections (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS ingest_sources (
    id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    connection_id TEXT NOT NULL REFERENCES ingest_connections (id),
    name TEXT NOT NULL,
    location TEXT NOT NULL,
    connector_profile TEXT NOT NULL,
    handling JSONB NOT NULL,
    legal_basis TEXT,
    refresh JSONB NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_by TEXT,
    updated_at TIMESTAMPTZ,
    UNIQUE (dataset_id, location)
);
CREATE INDEX IF NOT EXISTS ingest_sources_dataset ON ingest_sources (dataset_id);
"""

_SOURCE_COLUMNS = (
    "id, dataset_id, connection_id, name, location, connector_profile, handling, legal_basis, "
    "refresh, version, created_by, created_at, updated_by, updated_at"
)


def _source(row: asyncpg.Record) -> SourceTable:
    data: dict[str, Any] = dict(row)
    for key in ("handling", "refresh"):
        if isinstance(data[key], str):
            data[key] = json.loads(data[key])
    data["refresh"] = SourceRefresh(**data["refresh"])
    return SourceTable(**data)


class PostgresSourceStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PostgresSourceStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
            built_in = _built_in(_now())
            await conn.execute(
                "INSERT INTO ingest_connections (id, kind, name, created_by, created_at) "
                "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING",
                built_in.id, built_in.kind, built_in.name, built_in.created_by, built_in.created_at,
            )  # fmt: skip
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def connections(self) -> list[Connection]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, kind, name, created_by, created_at FROM ingest_connections "
                "ORDER BY id <> $1, name",
                FILES_CONNECTION_ID,
            )
        return [Connection(**dict(r)) for r in rows]

    async def add_connection(self, body: ConnectionInput, principal: Principal) -> Connection:
        made = Connection(
            id=new_id(),
            kind=body.kind,
            name=body.name.strip(),
            created_by=principal.id,
            created_at=_now(),
        )
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO ingest_connections (id, kind, name, created_by, created_at) "
                "VALUES ($1, $2, $3, $4, $5)",
                made.id, made.kind, made.name, made.created_by, made.created_at,
            )  # fmt: skip
        return made

    async def list_for(self, dataset_id: str) -> list[SourceTable]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_SOURCE_COLUMNS} FROM ingest_sources WHERE dataset_id = $1 ORDER BY name",
                dataset_id,
            )
        return [_source(r) for r in rows]

    async def get(self, dataset_id: str, source_id: str) -> SourceTable:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_SOURCE_COLUMNS} FROM ingest_sources WHERE dataset_id = $1 AND id = $2",
                dataset_id,
                source_id,
            )
        if row is None:
            raise SourceNotFoundError(source_id)
        return _source(row)

    async def register(
        self, dataset_id: str, body: RegisterSourceInput, principal: Principal
    ) -> SourceTable:
        made = _registered(dataset_id, body, principal)
        async with self._pool.acquire() as conn:
            known = await conn.fetchval(
                "SELECT 1 FROM ingest_connections WHERE id = $1", body.connection_id
            )
            if known is None:
                raise UnknownConnectionError(body.connection_id)
            try:
                await conn.execute(
                    f"INSERT INTO ingest_sources ({_SOURCE_COLUMNS}) VALUES "
                    "($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9::jsonb, $10, $11, $12, $13, $14)",
                    made.id, made.dataset_id, made.connection_id, made.name, made.location,
                    made.connector_profile, json.dumps(made.handling), made.legal_basis,
                    made.refresh.model_dump_json(), made.version, made.created_by, made.created_at,
                    None, None,
                )  # fmt: skip
            except asyncpg.UniqueViolationError as exc:
                raise SourceAlreadyRegisteredError(body.location) from exc
        return made

    async def edit_governance(
        self, dataset_id: str, source_id: str, body: SourceGovernanceInput, principal: Principal
    ) -> SourceTable:
        edited = _governed(await self.get(dataset_id, source_id), body, principal)
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE ingest_sources SET handling = $3::jsonb, legal_basis = $4, "
                "refresh = $5::jsonb, version = $6, updated_by = $7, updated_at = $8 "
                "WHERE dataset_id = $1 AND id = $2",
                dataset_id, source_id, json.dumps(edited.handling), edited.legal_basis,
                edited.refresh.model_dump_json(), edited.version, edited.updated_by,
                edited.updated_at,
            )  # fmt: skip
        return edited

    async def watched(self) -> list[SourceTable]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_SOURCE_COLUMNS} FROM ingest_sources "
                "WHERE refresh ->> 'trigger' = 'watch' ORDER BY id"
            )
        return [_source(r) for r in rows]

    async def set_refresh_paused(self, source_id: str, *, paused: bool, reason: str | None) -> None:
        async with self._pool.acquire() as conn:
            done = await conn.execute(
                "UPDATE ingest_sources SET refresh = refresh "
                "|| jsonb_build_object('paused', $2::boolean, 'paused_reason', $3::text) "
                "WHERE id = $1",
                source_id, paused, reason if paused else None,
            )  # fmt: skip
        if done.endswith(" 0"):
            raise SourceNotFoundError(source_id)

    async def adopt_refresh(self, source_id: str, refresh: SourceRefresh) -> None:
        """As `InMemorySourceStore.adopt_refresh`: `scripts.migrate_sources` alone."""
        async with self._pool.acquire() as conn:
            done = await conn.execute(
                "UPDATE ingest_sources SET refresh = $2::jsonb WHERE id = $1",
                source_id, refresh.model_dump_json(),
            )  # fmt: skip
        if done.endswith(" 0"):
            raise SourceNotFoundError(source_id)
