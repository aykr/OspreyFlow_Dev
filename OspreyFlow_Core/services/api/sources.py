"""Connections and registered sources (`06_DECISIONS.md` ADR-140 decision 7, Amendment 4).

**Connections** are the deployment's, kept by its administrators: `files`, the ingest root, and
phase 9's `sql`, `api` and `json` (Amendment 13), each holding its settings and a secret's name
only. The built-in one (`FILES_CONNECTION_ID`) is written at start-up so every deployment has it;
an administrator may name others, for the folders an operator keeps apart.

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
from services.ingest.ceiling import DeploymentCeiling

from conduit_common.identity import new_id
from ontology.handling import HandlingScheme
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


class SecretInUseError(Exception):
    """Another connection already names that secret: a secret belongs to one connection, so its
    value never goes to another host or database (the orchestrator's review of L1.6)."""


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
    async def set_default_marking(
        self, dataset_id: str, source_id: str, marking: str | None, principal: Principal
    ) -> SourceTable: ...
    async def connection(self, connection_id: str) -> Connection: ...
    async def cursor(self, source_id: str) -> str | None: ...
    async def set_cursor(self, source_id: str, cursor: str | None) -> None: ...
    async def set_refresh_paused(
        self, source_id: str, *, paused: bool, reason: str | None
    ) -> None: ...


def _now() -> datetime:
    return datetime.now(UTC)


def _with_default_marking(
    source: SourceTable, marking: str | None, principal: Principal
) -> SourceTable:
    """ADR-140 Amendment 19: the source with its default marking declared, changed or cleared, by
    whom and when; a new version, as any change to how its rows are marked is."""
    return source.model_copy(
        update={
            "default_marking": marking,
            "default_marking_set_by": principal.id,
            "default_marking_set_at": _now(),
            "version": source.version + 1,
        }
    )


def default_marking_problems(
    source: SourceTable,
    marking: str | None,
    principal: Principal,
    scheme: HandlingScheme,
    ceiling: DeploymentCeiling,
) -> list[str]:
    """Why `marking` may not be `source`'s declared default (ADR-140 Amendment 19), in words; none
    when it may. Clearing it (`None`) always may: the table is then unmarked, which the Join
    refuses to join to a marked one (fail closed). A default is one of the scheme's
    classifications; never above the declarer's own clearance (they would mark rows they could
    not read) or the deployment's highest marking (ADR-148 decision 10); never below the source's
    own marking, since a default never lowers a marking."""
    if marking is None:
        return []
    levels = list(scheme.classification)
    if marking not in levels:
        return [
            f"{marking!r} is not a classification of the {scheme.name} handling scheme: use one "
            f"of {', '.join(levels)}"
        ]
    problems: list[str] = []
    if principal.clearance not in levels or levels.index(marking) > levels.index(
        principal.clearance
    ):
        problems.append(
            "the default marking is above your clearance: a source's rows are never marked "
            "higher than the person declaring it may read"
        )
    if ceiling.above(marking):
        problems.append(
            f"the default marking is above this deployment's highest marking, {ceiling.marking}"
        )
    own = source.handling.get("classification")
    if isinstance(own, str) and own in levels and levels.index(marking) < levels.index(own):
        problems.append(
            f"the default marking is below the source's own marking, {own}: a default never "
            "lowers a marking"
        )
    return problems


def _secret_of(settings: object) -> str | None:
    return getattr(settings, "secret", None)


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
        read=body.read,
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
        self._cursors: dict[str, str | None] = {}

    async def connections(self) -> list[Connection]:
        return sorted(
            self._connections.values(), key=lambda c: (c.id != FILES_CONNECTION_ID, c.name)
        )

    async def add_connection(self, body: ConnectionInput, principal: Principal) -> Connection:
        secret = _secret_of(body.settings)
        if secret and any(_secret_of(c.settings) == secret for c in self._connections.values()):
            raise SecretInUseError(secret)
        made = Connection(
            id=new_id(),
            kind=body.kind,
            name=body.name.strip(),
            created_by=principal.id,
            created_at=_now(),
            settings=body.settings,
            datasets=list(body.datasets),
        )
        self._connections[made.id] = made
        return made

    async def connection(self, connection_id: str) -> Connection:
        if connection_id not in self._connections:
            raise UnknownConnectionError(connection_id)
        return self._connections[connection_id]

    async def cursor(self, source_id: str) -> str | None:
        if source_id not in self._sources:
            raise SourceNotFoundError(source_id)
        return self._cursors.get(source_id)

    async def set_cursor(self, source_id: str, cursor: str | None) -> None:
        if source_id not in self._sources:
            raise SourceNotFoundError(source_id)
        self._cursors[source_id] = cursor

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

    async def set_default_marking(
        self, dataset_id: str, source_id: str, marking: str | None, principal: Principal
    ) -> SourceTable:
        edited = _with_default_marking(await self.get(dataset_id, source_id), marking, principal)
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
-- ADR-140 Amendment 13: a connection's settings (a secret's name, never its value), a source's
-- read, and how far an incremental connector source has read.
ALTER TABLE ingest_connections ADD COLUMN IF NOT EXISTS settings JSONB;
ALTER TABLE ingest_connections ADD COLUMN IF NOT EXISTS datasets JSONB NOT NULL DEFAULT '[]';
-- A secret belongs to one connection (the orchestrator's review of L1.6).
CREATE UNIQUE INDEX IF NOT EXISTS ingest_connections_secret
    ON ingest_connections ((settings ->> 'secret')) WHERE settings ->> 'secret' IS NOT NULL;
ALTER TABLE ingest_sources ADD COLUMN IF NOT EXISTS read JSONB;
-- ADR-140 Amendment 19: a source's declared default marking, and who set it when (audited too).
ALTER TABLE ingest_sources ADD COLUMN IF NOT EXISTS default_marking TEXT;
ALTER TABLE ingest_sources ADD COLUMN IF NOT EXISTS default_marking_set_by TEXT;
ALTER TABLE ingest_sources ADD COLUMN IF NOT EXISTS default_marking_set_at TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS connector_cursors (
    source_id TEXT PRIMARY KEY REFERENCES ingest_sources (id) ON DELETE CASCADE,
    cursor TEXT
);
"""

_SOURCE_COLUMNS = (
    "id, dataset_id, connection_id, name, location, connector_profile, handling, legal_basis, "
    "refresh, version, created_by, created_at, updated_by, updated_at, read, default_marking, "
    "default_marking_set_by, default_marking_set_at"
)


def _source(row: asyncpg.Record) -> SourceTable:
    data: dict[str, Any] = dict(row)
    for key in ("handling", "refresh", "read"):
        if isinstance(data[key], str):
            data[key] = json.loads(data[key])
    data["refresh"] = SourceRefresh(**data["refresh"])
    return SourceTable(**data)


def _connection(row: asyncpg.Record) -> Connection:
    data: dict[str, Any] = dict(row)
    for key in ("settings", "datasets"):
        if isinstance(data.get(key), str):
            data[key] = json.loads(data[key])
    return Connection(**data)


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
                "SELECT id, kind, name, created_by, created_at, settings, datasets "
                "FROM ingest_connections "
                "ORDER BY id <> $1, name",
                FILES_CONNECTION_ID,
            )
        return [_connection(r) for r in rows]

    async def connection(self, connection_id: str) -> Connection:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, kind, name, created_by, created_at, settings, datasets "
                "FROM ingest_connections "
                "WHERE id = $1",
                connection_id,
            )
        if row is None:
            raise UnknownConnectionError(connection_id)
        return _connection(row)

    async def cursor(self, source_id: str) -> str | None:
        async with self._pool.acquire() as conn:
            known = await conn.fetchval("SELECT 1 FROM ingest_sources WHERE id = $1", source_id)
            if known is None:
                raise SourceNotFoundError(source_id)
            value = await conn.fetchval(
                "SELECT cursor FROM connector_cursors WHERE source_id = $1", source_id
            )
        return value if value is None else str(value)

    async def set_cursor(self, source_id: str, cursor: str | None) -> None:
        async with self._pool.acquire() as conn:
            try:
                await conn.execute(
                    "INSERT INTO connector_cursors (source_id, cursor) VALUES ($1, $2) "
                    "ON CONFLICT (source_id) DO UPDATE SET cursor = EXCLUDED.cursor",
                    source_id, cursor,
                )  # fmt: skip
            except asyncpg.ForeignKeyViolationError as exc:
                raise SourceNotFoundError(source_id) from exc

    async def add_connection(self, body: ConnectionInput, principal: Principal) -> Connection:
        made = Connection(
            id=new_id(),
            kind=body.kind,
            name=body.name.strip(),
            created_by=principal.id,
            created_at=_now(),
            settings=body.settings,
            datasets=list(body.datasets),
        )
        async with self._pool.acquire() as conn:
            try:
                await conn.execute(
                    "INSERT INTO ingest_connections (id, kind, name, created_by, created_at, "
                    "settings, datasets) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb)",
                    made.id, made.kind, made.name, made.created_by, made.created_at,
                    made.settings.model_dump_json() if made.settings else None,
                    json.dumps(made.datasets),
                )  # fmt: skip
            except asyncpg.UniqueViolationError as exc:
                raise SecretInUseError(_secret_of(made.settings) or "") from exc
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
                    "($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9::jsonb, $10, $11, $12, $13, $14, "
                    "$15::jsonb, $16, $17, $18)",
                    made.id, made.dataset_id, made.connection_id, made.name, made.location,
                    made.connector_profile, json.dumps(made.handling), made.legal_basis,
                    made.refresh.model_dump_json(), made.version, made.created_by, made.created_at,
                    None, None, made.read.model_dump_json() if made.read else None,
                    made.default_marking, made.default_marking_set_by, made.default_marking_set_at,
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

    async def set_default_marking(
        self, dataset_id: str, source_id: str, marking: str | None, principal: Principal
    ) -> SourceTable:
        stamp = _with_default_marking(await self.get(dataset_id, source_id), marking, principal)
        # The version is taken in the update itself, so two edits at once never both write one
        # version (the lane review, item 6); the row is read back as written.
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE ingest_sources SET default_marking = $3, default_marking_set_by = $4, "
                f"default_marking_set_at = $5, version = version + 1 WHERE dataset_id = $1 "
                f"AND id = $2 RETURNING {_SOURCE_COLUMNS}",
                dataset_id, source_id, stamp.default_marking, stamp.default_marking_set_by,
                stamp.default_marking_set_at,
            )  # fmt: skip
        if row is None:
            raise SourceNotFoundError(source_id)
        return _source(row)

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
