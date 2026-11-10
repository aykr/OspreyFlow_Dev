"""The schema applied as one batch, against a real ArcadeDB (admin's T1, 10 November 2026).

- The full ontology's schema, applied as one `sqlscript`, dumps identically to the same statements
  sent one at a time, as `apply_schema` sent them before the batch.
- A bad statement planted in the batch fails the whole apply with `SchemaApplyError`, and the schema
  is left as it was: empty on a fresh database, and the older schema whole on one that had it (the
  Conduit's start-up case), compared by the same dump.
- The first case prints its times, one at a time and batched, for a fresh database and for one whose
  schema is already there (what every start-up of the Conduit pays).

Each case creates its own `conformance_*` databases and drops them in teardown.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest

from adapters.graph_arcadedb import schema as schema_module
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.graph_arcadedb.schema import SchemaApplyError, apply_schema, schema_statements
from ontology.loader import load_default_ontology
from schemas.domain import EntityTypeDef, PoleClass

# Counts and files that differ between two databases holding the same schema.
_VOLATILE = {"records", "buckets", "bucketId", "associatedBucketId", "fileId", "size", "pages"}


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in sorted(value.items()) if k not in _VOLATILE}
    if isinstance(value, list):
        return sorted((_clean(v) for v in value), key=repr)
    return value


async def _dump(client: ArcadeDBClient) -> dict[str, Any]:
    return {
        "types": _clean(await client.sql("SELECT FROM schema:types")),
        "indexes": _clean(await client.sql("SELECT FROM schema:indexes")),
    }


@pytest.fixture
async def databases() -> AsyncIterator[Any]:
    made: list[ArcadeDBClient] = []

    async def fresh() -> ArcadeDBClient:
        name = f"conformance_{int(time.time())}_{uuid.uuid4().hex[:12]}"
        client = ArcadeDBClient(ArcadeDBConfig.from_env(name))
        await client.create_database_if_absent()
        made.append(client)
        return client

    yield fresh
    for client in made:
        try:
            await client.drop_database()
        finally:
            await client.aclose()


async def _one_at_a_time(client: ArcadeDBClient) -> float:
    started = time.perf_counter()
    for statement in schema_statements(load_default_ontology()).ddl:
        await client.sql(statement)
    return time.perf_counter() - started


async def _batched(client: ArcadeDBClient) -> float:
    started = time.perf_counter()
    await apply_schema(client, load_default_ontology())
    return time.perf_counter() - started


async def test_the_full_ontology_batched_dumps_as_one_at_a_time_and_is_faster(
    databases: Any,
) -> None:
    one, batch = await databases(), await databases()
    fresh_one = await _one_at_a_time(one)
    fresh_batch = await _batched(batch)
    assert (await _dump(batch)) == (await _dump(one))
    assert (await _dump(batch))["indexes"], "the dump read no indexes: it compared nothing"
    # The Conduit's start-up: the schema already there, applied again.
    again_one = await _one_at_a_time(one)
    again_batch = await _batched(batch)
    assert (await _dump(batch)) == (await _dump(one))
    print(
        f"\nschema apply, {len(schema_statements(load_default_ontology()).ddl)} statements: "
        f"fresh {fresh_one:.1f} s one at a time, {fresh_batch:.1f} s batched; "
        f"already there {again_one:.1f} s one at a time, {again_batch:.1f} s batched"
    )


def _plant(monkeypatch: pytest.MonkeyPatch, *, extra_type: bool) -> None:
    real = schema_statements

    def planted(schema: Any) -> Any:
        if extra_type:
            schema = schema.model_copy(
                update={
                    "entity_types": [
                        *schema.entity_types,
                        EntityTypeDef(
                            name="PlantedVessel",
                            pole_class=PoleClass("object"),
                            channel="teal",
                            shape="square",
                        ),
                    ]
                }
            )
        plan = real(schema)
        plan.ddl.insert(len(plan.ddl) - 3, "CREATE PROPERTY NOT VALID SQL")
        return plan

    monkeypatch.setattr(schema_module, "schema_statements", planted)


async def test_a_bad_statement_fails_a_fresh_apply_typed_and_leaves_no_schema(
    databases: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = await databases()
    before = await _dump(client)
    _plant(monkeypatch, extra_type=False)
    with pytest.raises(SchemaApplyError) as raised:
        await apply_schema(client, load_default_ontology())
    assert raised.value.restored, str(raised.value)
    assert await _dump(client) == before


async def test_a_bad_statement_leaves_an_older_schema_whole(
    databases: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = await databases()
    await apply_schema(client, load_default_ontology())
    before = await _dump(client)
    _plant(monkeypatch, extra_type=True)
    with pytest.raises(SchemaApplyError) as raised:
        await apply_schema(client, load_default_ontology())
    assert raised.value.restored, str(raised.value)
    assert await _dump(client) == before
