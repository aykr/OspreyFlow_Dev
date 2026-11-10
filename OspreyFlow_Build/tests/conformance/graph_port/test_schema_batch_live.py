"""The schema applied as one batch, against a real ArcadeDB (admin's T1, 10 November 2026).

- The full ontology's schema, applied as one `sqlscript`, dumps identically to the same statements
  sent one at a time, on a fresh database and when applied again over itself (the Conduit's
  start-up). Only an index's `name` is relaxed, and only its allocation number (below).
- A parse error planted anywhere applies nothing: ArcadeDB parses the whole script first.
- A refusal while the script runs (an index on a type that does not exist) is typed, sent once and
  never retried, leaves what the statement-by-statement apply left, and the next apply completes the
  schema to the same dump. Nothing is dropped to undo it (a drop could take another replica's type).
- The first case prints the times: one at a time and batched, fresh and applied again, and the test
  fixture's own open (`testing.arcadedb_adapter`).

Each case's `conformance_*` databases are registered with the fixture's leak check and dropped in
teardown, each one even if another's drop fails.
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest

from adapters.graph_arcadedb import schema as schema_module
from adapters.graph_arcadedb import testing
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.graph_arcadedb.schema import SchemaApplyError, apply_schema, schema_statements
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology

# Counts and files that differ between two databases holding the same schema.
_VOLATILE = {"records", "buckets", "bucketId", "associatedBucketId", "fileId", "size", "pages"}

# A bucket index's name ends in its allocation number, e.g. `mx_ALERTED_ON_0_1280514856246682`
# against `mx_ALERTED_ON_0_1280508458223250` for the same index in a second database (the
# orchestrator's live run at ebc74d8, stack c: all 39 differences were this, none in any other
# field). The type and bucket part is kept, so an index on another bucket still differs.
_ALLOCATION = re.compile(r"_\d{10,}$")


def _clean(value: Any) -> Any:
    """Volatile keys dropped; every list kept in its own order (a composite index's key order and
    its key types are part of the schema, so sorting them would hide a real difference)."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in sorted(value.items()) if k not in _VOLATILE}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def _index_row(row: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = _clean(row)
    if isinstance(clean.get("name"), str):
        clean["name"] = _ALLOCATION.sub("", clean["name"])
    return clean


async def _dump(client: ArcadeDBClient) -> dict[str, dict[str, Any]]:
    """Each type by its name and each index by what it indexes, so a difference names what
    differs."""
    return {
        "types": {str(r["name"]): _clean(r) for r in await client.sql("SELECT FROM schema:types")},
        "indexes": _by_what_they_index(await client.sql("SELECT FROM schema:indexes")),
    }


def _by_what_they_index(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Each index keyed by its type and key properties (with a count for a type's several bucket
    indexes over the same keys), not by its name."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        what = f"{r.get('typeName')}{list(r.get('properties') or [])}"
        groups.setdefault(what, []).append(_index_row(r))
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


def _same(a: dict[str, dict[str, Any]], b: dict[str, dict[str, Any]]) -> None:
    diff = _differences(a, b)
    # Every difference, never a truncated diff: pytest prints this message whole.
    assert not diff, f"{len(diff)} difference(s):\n" + "\n".join(diff)


class _Counting(ArcadeDBClient):
    """The real client, counting the scripts it sends (a refusal must be sent once)."""

    scripts = 0

    async def command(self, language: str, command: str, **kw: Any) -> list[dict[str, Any]]:
        if language == "sqlscript":
            self.scripts += 1
        return await super().command(language, command, **kw)


@pytest.fixture
async def databases() -> AsyncIterator[Any]:
    made: list[tuple[str, ArcadeDBClient]] = []

    async def fresh() -> _Counting:
        name = f"conformance_{int(time.time())}_{uuid.uuid4().hex[:12]}"
        client = _Counting(ArcadeDBConfig.from_env(name))
        made.append((name, client))
        testing._LIVE_CONFORMANCE_DATABASES.add(name)
        await client.create_database_if_absent()
        return client

    yield fresh
    errors: list[BaseException] = []
    for name, client in made:
        try:
            await client.drop_database()
            testing._LIVE_CONFORMANCE_DATABASES.discard(name)
        except Exception as exc:  # every database is dropped, whatever one drop raised
            errors.append(exc)
        finally:
            await client.aclose()
    if errors:
        raise errors[0]


async def _one_at_a_time(client: ArcadeDBClient) -> float:
    started = time.perf_counter()
    for statement in schema_statements(load_default_ontology()).ddl:
        await client.sql(statement)
    return time.perf_counter() - started


async def _batched(client: ArcadeDBClient) -> float:
    started = time.perf_counter()
    await apply_schema(client, load_default_ontology())
    return time.perf_counter() - started


async def test_the_full_ontology_batched_dumps_as_one_at_a_time(databases: Any) -> None:
    one, batch = await databases(), await databases()
    fresh_one = await _one_at_a_time(one)
    fresh_batch = await _batched(batch)
    _same(await _dump(batch), await _dump(one))
    assert (await _dump(batch))["indexes"], "the dump read no indexes: it compared nothing"
    # The Conduit's start-up: the schema already there, applied again.
    again_one = await _one_at_a_time(one)
    again_batch = await _batched(batch)
    _same(await _dump(batch), await _dump(one))
    started = time.perf_counter()
    async with testing.arcadedb_adapter(load_default_ontology(), load_uk_le_scheme()):
        fixture_open = time.perf_counter() - started
    print(
        f"\nschema apply, {len(schema_statements(load_default_ontology()).ddl)} statements: "
        f"fresh {fresh_one:.1f} s one at a time, {fresh_batch:.1f} s batched; "
        f"applied again {again_one:.1f} s one at a time, {again_batch:.1f} s batched; "
        f"arcadedb_adapter's open (create, apply) {fixture_open:.1f} s"
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


def _plant(monkeypatch: pytest.MonkeyPatch, statement: str) -> None:
    real = schema_statements

    def planted(schema: Any) -> Any:
        plan = real(schema)
        plan.ddl.insert(len(plan.ddl) // 2, statement)
        return plan

    monkeypatch.setattr(schema_module, "schema_statements", planted)


async def test_a_parse_error_applies_nothing_and_is_sent_once(
    databases: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = await databases()
    before = await _dump(client)
    _plant(monkeypatch, "CREATE PROPERTY NOT VALID SQL")
    with pytest.raises(SchemaApplyError) as raised:
        await apply_schema(client, load_default_ontology())
    print(f"\na parse error is refused as {raised.value.exception_class}")
    assert client.scripts == 1, "a permanent refusal was re-sent"
    _same(await _dump(client), before)


async def test_a_refusal_while_running_is_sent_once_and_a_re_apply_completes(
    databases: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, whole = await databases(), await databases()
    _plant(monkeypatch, "CREATE INDEX IF NOT EXISTS ON NoSuchType (id) UNIQUE")
    with pytest.raises(SchemaApplyError) as raised:
        await apply_schema(client, load_default_ontology())
    print(f"\na refusal while running is refused as {raised.value.exception_class}")
    assert client.scripts == 1, "a permanent refusal was re-sent"
    half = await _dump(client)
    assert half["types"], "nothing ran before the refusal: this did not test a run-time refusal"
    monkeypatch.undo()
    await apply_schema(client, load_default_ontology())
    await apply_schema(whole, load_default_ontology())
    _same(await _dump(client), await _dump(whole))
