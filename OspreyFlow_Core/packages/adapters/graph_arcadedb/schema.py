"""Schema and migration runner — `spec/04_VAULT_BACKEND.md` §1.4.

Every DDL statement is idempotent (`IF NOT EXISTS`), so applying the same
ontology twice is a no-op rather than an error — the shape a migration
runner needs for "up" to be safely re-run and to make "down" tractable.

Indexes created, matching §1.4 exactly:
- a unique index on `id` (every node/edge is looked up by its ULID);
- a composite index on `(type, handling.classification)`, plus
  `handling_code`, `owning_unit` and `originator` — the access filter's two
  axes (`access_filter.py`) both run on every read;
- one per ontology-declared `identifiers` field;
- **one per `properties` entry the ontology marks `indexed: true`** — "the
  flag is a schema instruction, not documentation" (§1.4);
- a vertex-centric index on `(edge_type, interval.from)` for every temporal
  edge type — realised as an indexed `valid_from` property on that edge
  type, so a timeline-filtered expansion does not scan the whole adjacency
  list.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import httpx

from schemas.domain import EdgeTypeDef, EntityTypeDef, OntologySchema, PropertyType, SchemaReport

from .client import ArcadeDBClient, ArcadeDBError
from .gremlin_literals import groovy_identifier
from .naming import physical_type_name

_log = logging.getLogger(__name__)

_DDL_MAX_ATTEMPTS = 6
_DDL_BACKOFF_BASE_SECONDS = 0.5
# Raised from 3/0.2s in Phase 5. Investigated a wave of `IndexException` on
# `CREATE INDEX` across the full suite; the actual root cause turned out to
# be the *host's* Docker Desktop VM disk filling up (unrelated stopped
# containers/volumes from other work on the machine, not this repo) —
# ArcadeDB was hitting `IOException: No space left on device` and every
# retry attempt failed identically because the condition wasn't transient.
# Freeing disk space (`docker image/builder prune`) resolved the vast
# majority of failures outright; no code change was actually the fix for
# that incident. This widened retry is kept anyway as a reasonable general
# hardening against genuine transient load (e.g. real heap pressure during
# concurrent schema DDL, per the class-level docstring above) — 6 attempts
# at 0.5s base (0.5+1+2+4+8=15.5s worst case, paid only when the server is
# first attempt still succeeds and costs nothing extra.

# ArcadeDB returns the same HTTP status (usually 500, occasionally 503) for
# both a permanent command error and a transient server-side failure, so
# status code alone cannot gate retry — confirmed empirically: "type not
# found" and a malformed command both come back 500, and a genuine unique-
# index conflict on duplicate data comes back 503. These are the server's
# own `exception` classes for the permanent cases actually reachable from
# this module's DDL (missing type/property, bad SQL, a real uniqueness
# conflict on `id`) — denylisted so they always fail immediately and
# loudly rather than being retried into a slower version of the same
# failure. Anything else (including `IndexException`, the class observed
# when the server was heap-starved under concurrent schema load) retries.
_NON_RETRYABLE_ARCADEDB_EXCEPTIONS = frozenset(
    {
        "com.arcadedb.exception.SchemaException",
        "com.arcadedb.query.sql.parser.ParseException",
        "com.arcadedb.exception.ConcurrentModificationException",
    }
)


async def _ddl(client: ArcadeDBClient, command: str) -> None:
    """Every DDL statement here is idempotent (`IF NOT EXISTS`/`UNSAFE`), so
    retrying one is safe: at worst it repeats a no-op. Retries only on
    genuinely transient failures — a connection-level error, or a server
    error whose `exception` class isn't a known-permanent one (see
    `_NON_RETRYABLE_ARCADEDB_EXCEPTIONS`) — never a real schema conflict,
    which fails immediately and loudly instead."""
    for attempt in range(1, _DDL_MAX_ATTEMPTS + 1):
        try:
            await client.sql(command)
            return
        except ArcadeDBError as exc:
            non_retryable = (
                exc.status_code is None
                or exc.status_code < 500
                or exc.exception_class in _NON_RETRYABLE_ARCADEDB_EXCEPTIONS
            )
            if non_retryable or attempt == _DDL_MAX_ATTEMPTS:
                raise
        except httpx.TransportError:
            if attempt == _DDL_MAX_ATTEMPTS:
                raise
        await asyncio.sleep(_DDL_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))


_SQL_TYPE: dict[PropertyType, str] = {
    PropertyType.STRING: "STRING",
    PropertyType.STRING_LIST: "LIST",
    PropertyType.DATE: "DATE",
    PropertyType.DATETIME: "DATETIME",
    PropertyType.INTEGER: "INTEGER",
    PropertyType.FLOAT: "FLOAT",
    PropertyType.BOOLEAN: "BOOLEAN",
    PropertyType.ENUM: "STRING",
}


async def apply_schema(client: ArcadeDBClient, schema: OntologySchema) -> SchemaReport:
    applied_entity_types: list[str] = []
    applied_edge_types: list[str] = []
    indexes_created: list[str] = []

    for entity in schema.entity_types:
        name = groovy_identifier(physical_type_name(entity.name))
        await _ddl(client, f"CREATE VERTEX TYPE {name} IF NOT EXISTS")
        indexes_created += await _apply_common_indexes(client, name)
        for identifier in entity.identifiers:
            indexes_created += await _apply_indexed_property(client, name, identifier, "STRING")
        indexes_created += await _apply_indexed_declared_properties(client, name, entity)
        applied_entity_types.append(entity.name)

    for edge in schema.edge_types:
        name = groovy_identifier(physical_type_name(edge.name))
        await _ddl(client, f"CREATE EDGE TYPE {name} IF NOT EXISTS")
        indexes_created += await _apply_common_indexes(client, name)
        indexes_created += await _apply_indexed_declared_properties(client, name, edge)
        if edge.temporal:
            await _create_property(client, name, "valid_from", "DATETIME")
            await _create_index(client, name, "valid_from", unique=False)
            indexes_created.append(f"{name}.valid_from")
        applied_edge_types.append(edge.name)

    return SchemaReport(
        migration_id=f"ontology-v{schema.version}-{datetime.now(UTC).isoformat()}",
        applied_entity_types=applied_entity_types,
        applied_edge_types=applied_edge_types,
        indexes_created=indexes_created,
        reversible=True,
    )


async def drop_schema(client: ArcadeDBClient, schema: OntologySchema) -> None:
    """The migration runner's "down": drops every vertex/edge type the given
    ontology declares. Called from `adapter.py`'s `revert_schema` — not part
    of `GraphPort` itself, since schema migration is ops tooling, not a
    per-analyst read."""
    for edge in schema.edge_types:
        await _drop_type_if_present(client, groovy_identifier(physical_type_name(edge.name)))
    for entity in schema.entity_types:
        await _drop_type_if_present(client, groovy_identifier(physical_type_name(entity.name)))


async def _drop_type_if_present(client: ArcadeDBClient, type_name: str) -> None:
    try:
        await _ddl(client, f"DROP TYPE {type_name} UNSAFE")
    except ArcadeDBError as exc:
        if "was not found" not in str(exc):
            raise


async def _apply_common_indexes(client: ArcadeDBClient, type_name: str) -> list[str]:
    names = ["id", "handling_classification", "handling_code", "owning_unit", "originator"]
    for name in names:
        await _create_property(client, type_name, name, "STRING")
        await _create_index(client, type_name, name, unique=(name == "id"))
    # `reverted` — checked on every read alongside the access filter
    # (`access_filter.py`), so it needs the same treatment, not just a
    # schemaless property. Not unique: every non-reverted element shares
    # the value `false`.
    await _create_property(client, type_name, "reverted", "BOOLEAN")
    await _create_index(client, type_name, "reverted", unique=False)
    # `superseded_by` — sparse (`01_DOMAIN_MODEL.md` §2.4): present only on
    # a node `supersede_node` has replaced. Declared here so `hasNot(...)`
    # and a direct lookup both have a real, indexed property to run
    # against rather than one that only ever appears schemaless.
    await _create_property(client, type_name, "superseded_by", "STRING")
    await _create_index(client, type_name, "superseded_by", unique=False)
    return [
        *(f"{type_name}.{name}" for name in names),
        f"{type_name}.reverted",
        f"{type_name}.superseded_by",
    ]


async def _apply_indexed_property(
    client: ArcadeDBClient, type_name: str, prop_name: str, sql_type: str
) -> list[str]:
    prop = groovy_identifier(prop_name)
    await _create_property(client, type_name, prop, sql_type)
    await _create_index(client, type_name, prop, unique=False)
    return [f"{type_name}.{prop}"]


async def _apply_indexed_declared_properties(
    client: ArcadeDBClient, type_name: str, type_def: EntityTypeDef | EdgeTypeDef
) -> list[str]:
    created: list[str] = []
    for prop in type_def.properties:
        if prop.indexed:
            created += await _apply_indexed_property(
                client, type_name, prop.name, _SQL_TYPE[prop.type]
            )
            if prop.type in _BACKFILLED_TYPES:
                await _backfill_flattened_field(client, type_name, prop.name)
    return created


#: The indexed types worth copying up. Text is what a suggestion or an exact search reads; a date or
#: a number would need its own conversion from the map's stored form, which nothing needs yet.
_BACKFILLED_TYPES = frozenset({PropertyType.STRING, PropertyType.ENUM})


async def _backfill_flattened_field(client: ArcadeDBClient, type_name: str, prop_name: str) -> None:
    """Fill an indexed field on nodes written before the property was indexed.

    The store keeps an indexed property twice, inside `properties` and as its own top-level field
    (`serialization.py`); only the field is indexed and searched, and it is copied at write time.
    A node written before the ontology marked the property `indexed` therefore has the map and not
    the field, and is invisible to the index, to `search_nodes` and to `suggest_nodes` for that
    property (seen 3 October 2026: `family_name` after ontology v11).

    It fills a missing (or empty) field and never replaces one that has a value. It runs on every
    schema apply, so it also repairs a field that went missing some other way; once nothing is
    missing it changes nothing. If ArcadeDB refuses it, the schema step carries on (every statement
    before and after still runs, so the API starts) and the refusal is logged by name: the property
    then stays unsearchable for old nodes until they are written again, which is what the log line
    says."""
    prop = groovy_identifier(prop_name)
    # Not `{prop} IS NULL`: the field is indexed, and on ArcadeDB 25.5.1 that form is answered from
    # the index, which holds no entry for a missing value, so it matched 0 rows while 463 nodes had
    # none (seen live 3 October 2026). `ifnull(...)` cannot use the index, so the type is scanned.
    statement = (
        f"UPDATE {type_name} SET {prop} = properties.{prop} "
        f"WHERE properties.{prop} IS NOT NULL AND ifnull({prop}, '') = ''"
    )
    try:
        await client.sql(statement)
    except ArcadeDBError as exc:
        _log.warning(
            "could not copy %s.%s up from the properties map for nodes written before it was "
            "indexed (%s); those nodes will not be found by that property until they are written "
            "again, for example by re-running the seed or load",
            type_name,
            prop,
            exc,
        )


async def _create_property(
    client: ArcadeDBClient, type_name: str, prop_name: str, sql_type: str
) -> None:
    await _ddl(client, f"CREATE PROPERTY {type_name}.{prop_name} IF NOT EXISTS {sql_type}")


async def _create_index(
    client: ArcadeDBClient, type_name: str, prop_name: str, *, unique: bool
) -> None:
    kind = "UNIQUE" if unique else "NOTUNIQUE"
    await _ddl(client, f"CREATE INDEX IF NOT EXISTS ON {type_name} ({prop_name}) {kind}")
