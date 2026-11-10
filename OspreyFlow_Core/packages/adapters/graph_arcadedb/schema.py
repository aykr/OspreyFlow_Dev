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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
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
    await _with_ddl_retry(lambda: client.sql(command), transport=httpx.TransportError)


async def _with_ddl_retry(
    send: Callable[[], Awaitable[object]],
    *,
    transport: type[Exception] | tuple[type[Exception], ...],
) -> None:
    """`_ddl`'s retry policy, shared by one statement and the whole script: a permanent refusal
    raises at once; a transient one (a 5xx not denylisted, or one of `transport`) is re-sent."""
    for attempt in range(1, _DDL_MAX_ATTEMPTS + 1):
        try:
            await send()
            return
        except ArcadeDBError as exc:
            non_retryable = (
                exc.status_code is None
                or exc.status_code < 500
                or exc.exception_class in _NON_RETRYABLE_ARCADEDB_EXCEPTIONS
            )
            if non_retryable or attempt == _DDL_MAX_ATTEMPTS:
                raise
        except transport:
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


class SchemaApplyError(ArcadeDBError):
    """The schema's script was refused, or its outcome is unknown. A refusal that the script's
    parse found applied nothing; one found while it ran left the statements before it applied, as
    the statement-by-statement apply did; either way the next apply, each statement being
    `IF NOT EXISTS`, completes the schema. Nothing is dropped to undo it (admin's T1 review: a drop
    could take a type another process had just created and written to)."""

    def __init__(self, message: str, *, cause: ArcadeDBError | httpx.TransportError) -> None:
        super().__init__(
            message,
            status_code=getattr(cause, "status_code", None),
            exception_class=getattr(cause, "exception_class", None),
        )


@dataclass(frozen=True)
class _Plan:
    """Every DDL statement an ontology needs, in the order they run, and what the report names."""

    ddl: list[str] = field(default_factory=list)
    backfills: list[tuple[str, str]] = field(default_factory=list)
    entity_types: list[str] = field(default_factory=list)
    edge_types: list[str] = field(default_factory=list)
    indexes: list[str] = field(default_factory=list)


def schema_statements(schema: OntologySchema) -> _Plan:
    """The statements `apply_schema` sends, built once: the Conduit's start-up and the test
    fixture's fresh database run the same list (admin's T1, 10 November 2026)."""
    plan = _Plan()
    for entity in schema.entity_types:
        name = groovy_identifier(physical_type_name(entity.name))
        plan.ddl.append(f"CREATE VERTEX TYPE {name} IF NOT EXISTS")
        _common_indexes(plan, name)
        for identifier in entity.identifiers:
            _indexed_property(plan, name, identifier, "STRING")
        _indexed_declared_properties(plan, name, entity)
        plan.entity_types.append(entity.name)
    for edge in schema.edge_types:
        name = groovy_identifier(physical_type_name(edge.name))
        plan.ddl.append(f"CREATE EDGE TYPE {name} IF NOT EXISTS")
        _common_indexes(plan, name)
        _indexed_declared_properties(plan, name, edge)
        if edge.temporal:
            plan.ddl.append(_property(name, "valid_from", "DATETIME"))
            plan.ddl.append(_index(name, "valid_from", unique=False))
            plan.indexes.append(f"{name}.valid_from")
        plan.edge_types.append(edge.name)
    return plan


async def apply_schema(client: ArcadeDBClient, schema: OntologySchema) -> SchemaReport:
    """Apply an ontology's schema as one `sqlscript` request, not one request per statement.

    A fresh database's schema took about 30 s one statement at a time on the owner's test server
    (T1's measured run, stack b, 10 November 2026), paid by every live test that opens one. The
    statements and their order are unchanged (`test_schema_batch.py`'s golden list).

    A refusal raises `SchemaApplyError` and is never undone: ArcadeDB parses the whole script
    first, so a parse error applies nothing; one found while the script runs leaves the
    statements before it applied, as the statement-by-statement apply did, and the next apply
    completes the schema. Re-sent only when the request never reached the server (a failure to
    connect) or the server called it transient; a timed-out script may still be running there, so
    it is not sent again beside itself: its outcome is unknown and the error says so. The copy-up
    of indexed text fields runs after the script, statement by statement: a refusal there is
    logged and never stops the schema (`_backfill_flattened_field`)."""
    plan = schema_statements(schema)
    try:
        await _ddl_script(client, plan.ddl)
    except (ArcadeDBError, httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise SchemaApplyError(
            "the schema's script was refused, or the server could not be reached; any statement "
            "before a refused one stays applied, and applying the schema again completes it: "
            f"{exc!r}",
            cause=exc,
        ) from exc
    except httpx.TransportError as exc:
        # Sent, and then no whole answer (a read timed out, the connection dropped): the script may
        # still be running on the server, so it is not sent again beside itself.
        raise SchemaApplyError(
            "the schema's script was sent and no answer came back; it may still be running on the "
            f"server, so its outcome is unknown: apply the schema again once it is idle ({exc!r})",
            cause=exc,
        ) from exc
    for type_name, prop in plan.backfills:
        await _backfill_flattened_field(client, type_name, prop)
    return SchemaReport(
        migration_id=f"ontology-v{schema.version}-{datetime.now(UTC).isoformat()}",
        applied_entity_types=plan.entity_types,
        applied_edge_types=plan.edge_types,
        indexes_created=plan.indexes,
        reversible=True,
    )


#: The whole script's own timeout: 585 statements, and an index built over a populated type, take
#: longer than one statement's 30 s.
_SCRIPT_TIMEOUT_SECONDS = 600.0


async def _ddl_script(client: ArcadeDBClient, statements: list[str]) -> None:
    """The statements as one script. Only a failure to connect is re-sent: a read that timed out
    may still be running there (`apply_schema`)."""
    if not statements:
        return
    script = ";\n".join(statements)
    await _with_ddl_retry(
        lambda: client.command("sqlscript", script, timeout=_SCRIPT_TIMEOUT_SECONDS),
        transport=(httpx.ConnectError, httpx.ConnectTimeout),
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


def _common_indexes(plan: _Plan, type_name: str) -> None:
    names = ["id", "handling_classification", "handling_code", "owning_unit", "originator"]
    for name in names:
        plan.ddl.append(_property(type_name, name, "STRING"))
        plan.ddl.append(_index(type_name, name, unique=(name == "id")))
    # `reverted` — checked on every read alongside the access filter
    # (`access_filter.py`), so it needs the same treatment, not just a
    # schemaless property. Not unique: every non-reverted element shares
    # the value `false`.
    plan.ddl.append(_property(type_name, "reverted", "BOOLEAN"))
    plan.ddl.append(_index(type_name, "reverted", unique=False))
    # `superseded_by` — sparse (`01_DOMAIN_MODEL.md` §2.4): present only on
    # a node `supersede_node` has replaced. Declared here so `hasNot(...)`
    # and a direct lookup both have a real, indexed property to run
    # against rather than one that only ever appears schemaless.
    plan.ddl.append(_property(type_name, "superseded_by", "STRING"))
    plan.ddl.append(_index(type_name, "superseded_by", unique=False))
    # `withdrawn_by_load` — sparse, as `superseded_by` (ADR-110 Amendment 6 point 3): present only
    # on an element a full-snapshot refresh withdrew, and looked up by that refresh's load id when
    # its revert restores them.
    plan.ddl.append(_property(type_name, "withdrawn_by_load", "STRING"))
    plan.ddl.append(_index(type_name, "withdrawn_by_load", unique=False))
    # `promoted_by_load` — sparse (ADR-143 decision 8): present only on an element a promotion
    # added a dataset to, looked up by that promotion's load id when it is reverted.
    plan.ddl.append(_property(type_name, "promoted_by_load", "STRING"))
    plan.ddl.append(_index(type_name, "promoted_by_load", unique=False))
    # `datasets` (ADR-099 decision 2, Amendment 6): a list, indexed by each of its items, so a read
    # by dataset (`WHERE datasets CONTAINS ...`) is answered from the index. The access step's
    # Gremlin filter tests the list itself (`AccessFilter.gremlin_dataset_step`).
    plan.ddl.append(_property(type_name, "datasets", "LIST OF STRING"))
    plan.ddl.append(_index(type_name, "datasets BY ITEM", unique=False))
    plan.indexes.extend(
        [
            *(f"{type_name}.{name}" for name in names),
            f"{type_name}.reverted",
            f"{type_name}.superseded_by",
            f"{type_name}.withdrawn_by_load",
            f"{type_name}.promoted_by_load",
            f"{type_name}.datasets",
        ]
    )


def _indexed_property(plan: _Plan, type_name: str, prop_name: str, sql_type: str) -> None:
    prop = groovy_identifier(prop_name)
    plan.ddl.append(_property(type_name, prop, sql_type))
    plan.ddl.append(_index(type_name, prop, unique=False))
    plan.indexes.append(f"{type_name}.{prop}")


def _indexed_declared_properties(
    plan: _Plan, type_name: str, type_def: EntityTypeDef | EdgeTypeDef
) -> None:
    for prop in type_def.properties:
        if prop.indexed:
            _indexed_property(plan, type_name, prop.name, _SQL_TYPE[prop.type])
            if prop.type in _BACKFILLED_TYPES:
                plan.backfills.append((type_name, prop.name))


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
    missing it changes nothing. It runs after the schema's whole script, one statement per
    copy-up. If ArcadeDB refuses it, the schema step carries on (every other copy-up still runs,
    so the API starts) and the refusal is logged by name: the property
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


def _property(type_name: str, prop_name: str, sql_type: str) -> str:
    return f"CREATE PROPERTY {type_name}.{prop_name} IF NOT EXISTS {sql_type}"


def _index(type_name: str, prop_name: str, *, unique: bool) -> str:
    kind = "UNIQUE" if unique else "NOTUNIQUE"
    return f"CREATE INDEX IF NOT EXISTS ON {type_name} ({prop_name}) {kind}"
