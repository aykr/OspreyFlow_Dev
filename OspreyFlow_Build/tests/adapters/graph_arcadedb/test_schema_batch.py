"""The schema applied as one batch (admin's T1, 10 November 2026): the same statements in the same
order as one at a time, sent in one request, and a refusal leaving the schema as it was.

The stand-in below models what ArcadeDB does with a `sqlscript` and what it refuses (rule 15): it
runs a script's statements in order, stops at the first it cannot parse or that names a type it
does not have, and **keeps every schema change before it** (ArcadeDB's schema changes are not
transactional). A fake that rolled the script back itself would hide the very fault the restore
exists for. The live proof, a schema dump compared against the one-at-a-time schema on a real
ArcadeDB, is
`tests/conformance/graph_port/test_schema_batch_live.py`.
"""

from __future__ import annotations

import re
from typing import Any

import httpx
import pytest

from adapters.graph_arcadedb import schema as schema_module
from adapters.graph_arcadedb.client import ArcadeDBError
from adapters.graph_arcadedb.naming import physical_type_name
from adapters.graph_arcadedb.schema import SchemaApplyError, apply_schema, schema_statements
from schemas.domain import EdgeTypeDef, EntityTypeDef, OntologySchema, PropertyDef, PropertyType

_PARSE = "com.arcadedb.query.sql.parser.ParseException"
_SCHEMA = "com.arcadedb.exception.SchemaException"


class FakeArcade:
    """Types, properties and indexes, changed statement by statement; scripts not transactional."""

    def __init__(self, *, transient_failures: int = 0) -> None:
        self.types: dict[str, str] = {}
        self.properties: dict[str, set[str]] = {}
        self.indexes: dict[str, str] = {}  # index name -> its type
        self.requests: list[tuple[str, str]] = []
        self._transient = transient_failures

    def _run(self, statement: str) -> None:
        s = statement.strip()
        if m := re.fullmatch(r"CREATE (VERTEX|EDGE) TYPE (\w+) IF NOT EXISTS", s):
            self.types.setdefault(m[2], m[1])
            self.properties.setdefault(m[2], set())
        elif m := re.fullmatch(r"CREATE PROPERTY (\w+)\.(\w+) IF NOT EXISTS [A-Z ]+", s):
            self._has(m[1])
            self.properties[m[1]].add(m[2])
        elif m := re.fullmatch(
            r"CREATE INDEX IF NOT EXISTS ON (\w+) \((\w+)( BY ITEM)?\) (UNIQUE|NOTUNIQUE)", s
        ):
            self._has(m[1])
            if m[2] not in self.properties[m[1]]:
                raise ArcadeDBError(
                    f"property {m[2]} not found", status_code=500, exception_class=_SCHEMA
                )
            self.indexes.setdefault(f"{m[1]}[{m[2]}]", m[1])
        elif m := re.fullmatch(r"DROP INDEX `(.+)`", s):
            self.indexes.pop(m[1], None)
        elif m := re.fullmatch(r"DROP PROPERTY (\w+)\.(\w+) FORCE", s):
            self.properties.get(m[1], set()).discard(m[2])
        elif m := re.fullmatch(r"DROP TYPE (\w+) UNSAFE", s):
            self.types.pop(m[1], None)
            self.properties.pop(m[1], None)
            self.indexes = {k: t for k, t in self.indexes.items() if t != m[1]}
        elif s.startswith("UPDATE "):
            return
        else:
            raise ArcadeDBError(f"cannot parse {s!r}", status_code=500, exception_class=_PARSE)

    def _has(self, type_name: str) -> None:
        if type_name not in self.types:
            raise ArcadeDBError(
                f"type {type_name} was not found", status_code=500, exception_class=_SCHEMA
            )

    async def command(self, language: str, command: str, **_: Any) -> list[dict[str, Any]]:
        self.requests.append((language, command))
        if self._transient:
            self._transient -= 1
            raise httpx.ConnectError("connection reset")
        if language == "sqlscript":
            for statement in command.split(";\n"):
                self._run(statement)  # stops at the first refusal; what ran before it stays
            return []
        return await self.sql(command)

    async def sql(self, command: str, **_: Any) -> list[dict[str, Any]]:
        if command == "SELECT name, properties FROM schema:types":
            return [
                {"name": t, "properties": [{"name": p} for p in sorted(self.properties[t])]}
                for t in self.types
            ]
        if command == "SELECT name, typeName FROM schema:indexes":
            return [{"name": n, "typeName": t} for n, t in self.indexes.items()]
        self.requests.append(("sql", command))
        self._run(command)
        return []

    def shape(self) -> tuple[Any, ...]:
        return (
            dict(self.types),
            {t: set(p) for t, p in self.properties.items()},
            dict(self.indexes),
        )


def _ontology(*, extra_entity: bool = False) -> OntologySchema:
    entities = [
        EntityTypeDef(
            name="Person",
            pole_class="person",
            channel="indigo",
            shape="circle",
            identifiers=["nino"],
            properties=[PropertyDef(name="family_name", type=PropertyType.STRING, indexed=True)],
        )
    ]
    if extra_entity:
        entities.append(
            EntityTypeDef(name="Vessel", pole_class="object", channel="teal", shape="square")
        )
    return OntologySchema(
        version=1,
        entity_types=entities,
        edge_types=[
            EdgeTypeDef.model_validate(
                {
                    "name": "KNOWS",
                    "from": ["Person"],
                    "to": ["Person"],
                    "temporal": True,
                    "evidence": "direct",
                }
            )
        ],
    )


async def test_the_batch_runs_the_same_statements_in_the_same_order_in_one_request() -> None:
    fake = FakeArcade()
    report = await apply_schema(fake, _ontology())  # type: ignore[arg-type]
    scripts = [c for lang, c in fake.requests if lang == "sqlscript"]
    assert len(scripts) == 1
    assert scripts[0].split(";\n") == schema_statements(_ontology()).ddl
    person = physical_type_name("Person")
    assert f"{person}[family_name]" in fake.indexes and f"{person}[nino]" in fake.indexes
    assert report.applied_entity_types == ["Person"] and report.applied_edge_types == ["KNOWS"]
    # the copy-up still runs after the script, one statement each, so a refused one never stops it
    assert [c for lang, c in fake.requests if lang == "sql" and c.startswith("UPDATE")]


@pytest.mark.parametrize("where", ["first", "middle", "last"])
async def test_a_refused_statement_fails_the_apply_typed_and_leaves_a_fresh_schema_empty(
    monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    real = schema_statements

    def planted(schema: OntologySchema) -> Any:
        plan = real(schema)
        at = {"first": 0, "middle": len(plan.ddl) // 2, "last": len(plan.ddl)}[where]
        plan.ddl.insert(at, "CREATE PROPERTY NOT VALID SQL")
        return plan

    monkeypatch.setattr(schema_module, "schema_statements", planted)
    fake = FakeArcade()
    with pytest.raises(SchemaApplyError) as raised:
        await apply_schema(fake, _ontology())  # type: ignore[arg-type]
    assert raised.value.restored and raised.value.exception_class == _PARSE
    assert fake.shape() == ({}, {}, {})


async def test_a_refused_statement_leaves_an_older_schema_as_it_was(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Conduit's start-up case: a schema already there, a newer ontology adding a type and its
    indexes, refused part-way: the older schema stays whole and nothing of the new one is left."""
    fake = FakeArcade()
    await apply_schema(fake, _ontology())  # type: ignore[arg-type]
    before = fake.shape()
    real = schema_statements

    def planted(schema: OntologySchema) -> Any:
        plan = real(schema)
        plan.ddl.append("CREATE INDEX IF NOT EXISTS ON NoSuchType (id) UNIQUE")
        return plan

    monkeypatch.setattr(schema_module, "schema_statements", planted)
    with pytest.raises(SchemaApplyError) as raised:
        await apply_schema(fake, _ontology(extra_entity=True))  # type: ignore[arg-type]
    assert raised.value.restored and raised.value.exception_class == _SCHEMA
    assert fake.shape() == before
    assert physical_type_name("Vessel") not in fake.types


async def test_a_transient_failure_re_sends_the_whole_script() -> None:
    fake = FakeArcade(transient_failures=2)
    await apply_schema(fake, _ontology())  # type: ignore[arg-type]
    assert [lang for lang, _ in fake.requests].count("sqlscript") == 3
    assert physical_type_name("Person") in fake.types


async def test_a_restore_that_cannot_put_the_schema_back_says_what_is_left() -> None:
    class StubbornArcade(FakeArcade):
        def _run(self, statement: str) -> None:
            if statement.startswith("DROP TYPE"):
                raise ArcadeDBError("cannot drop", status_code=500, exception_class=_SCHEMA)
            if statement.startswith("CREATE EDGE TYPE"):
                raise ArcadeDBError("refused", status_code=500, exception_class=_SCHEMA)
            super()._run(statement)

    fake = StubbornArcade()
    with pytest.raises(SchemaApplyError) as raised:
        await apply_schema(fake, _ontology())  # type: ignore[arg-type]
    assert not raised.value.restored
    assert "left over" in str(raised.value) and physical_type_name("Person") in str(raised.value)
