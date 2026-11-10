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
    """Volatile keys dropped; every list kept in its own order (a composite index's key order and
    its key types are part of the schema, so sorting them would hide a real difference)."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in sorted(value.items()) if k not in _VOLATILE}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


async def _dump(client: ArcadeDBClient) -> dict[str, dict[str, Any]]:
    """Each type by its name and each index by what it indexes, so a difference names what
    differs."""
    return {
        "types": {str(r["name"]): _clean(r) for r in await client.sql("SELECT FROM schema:types")},
        "indexes": _by_what_they_index(await client.sql("SELECT FROM schema:indexes")),
    }


def _by_what_they_index(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Each index keyed by its type and key properties (with a count for a type's several bucket
    indexes over the same keys), not by its name, so a name that carries an allocation (a bucket
    or a file) shows as a differing `name` rather than as every index missing."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        what = f"{r.get('typeName')}{list(r.get('properties') or [])}"
        groups.setdefault(what, []).append(_clean(r))
    return {
        f"{what}#{i}": row
        for what, group in groups.items()
        for i, row in enumerate(sorted(group, key=lambda g: str(g.get("name"))))
    }


def _differences(a: dict[str, dict[str, Any]], b: dict[str, dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for part in ("types", "indexes"):
        for name in sorted(set(a[part]) | set(b[part])):
            if name not in a[part] or name not in b[part]:
                out.append(
                    f"{part} {name!r} only in the {'second' if name in b[part] else 'first'}"
                )
                continue
            x, y = a[part][name], b[part][name]
            for key in sorted(set(x) | set(y)):
                if x.get(key) != y.get(key):
                    out.append(f"{part} {name!r} {key}: {x.get(key)!r} != {y.get(key)!r}")
    return out


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
    diff = _differences(await _dump(batch), await _dump(one))
    assert not diff, "\n".join(diff[:40])
    assert (await _dump(batch))["indexes"], "the dump read no indexes: it compared nothing"
    # The Conduit's start-up: the schema already there, applied again.
    again_one = await _one_at_a_time(one)
    again_batch = await _batched(batch)
    diff = _differences(await _dump(batch), await _dump(one))
    assert not diff, "\n".join(diff[:40])
    print(
        f"\nschema apply, {len(schema_statements(load_default_ontology()).ddl)} statements: "
        f"fresh {fresh_one:.1f} s one at a time, {fresh_batch:.1f} s batched; "
        f"already there {again_one:.1f} s one at a time, {again_batch:.1f} s batched"
    )


async def test_the_dump_comparison_names_a_missing_index(
    databases: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The comparison's own red (rule 15): one CREATE INDEX left out of the batch is named."""
    one, batch = await databases(), await databases()
    await _one_at_a_time(one)
    real = schema_statements
    dropped: list[str] = []

    def without_one_index(schema: Any) -> Any:
        plan = real(schema)
        at = next(
            i for i, s in enumerate(plan.ddl) if s.startswith("CREATE INDEX") and "BY ITEM" in s
        )
        dropped.append(plan.ddl.pop(at))
        return plan

    monkeypatch.setattr(schema_module, "schema_statements", without_one_index)
    await apply_schema(batch, load_default_ontology())
    diff = _differences(await _dump(batch), await _dump(one))
    assert any("only in the second" in d and d.startswith("indexes") for d in diff), (dropped, diff)


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
    assert not _differences(await _dump(client), before)


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
    diff = _differences(await _dump(client), before)
    assert not diff, "\n".join(diff[:40])
