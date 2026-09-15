"""Schema and migration runner — `docs/04_VAULT_BACKEND.md` §1.4.

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
from datetime import UTC, datetime

import httpx

from schemas.domain import EdgeTypeDef, EntityTypeDef, OntologySchema, PropertyType, SchemaReport

from .client import ArcadeDBClient, ArcadeDBError
from .gremlin_literals import groovy_identifier
from .naming import physical_type_name

_DDL_MAX_ATTEMPTS = 3
_DDL_BACKOFF_BASE_SECONDS = 0.2

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
    return created


async def _create_property(
    client: ArcadeDBClient, type_name: str, prop_name: str, sql_type: str
) -> None:
    await _ddl(client, f"CREATE PROPERTY {type_name}.{prop_name} IF NOT EXISTS {sql_type}")


async def _create_index(
    client: ArcadeDBClient, type_name: str, prop_name: str, *, unique: bool
) -> None:
    kind = "UNIQUE" if unique else "NOTUNIQUE"
    await _ddl(client, f"CREATE INDEX IF NOT EXISTS ON {type_name} ({prop_name}) {kind}")
