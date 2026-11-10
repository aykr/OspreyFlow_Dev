"""The schema applied as one batch (admin's T1, 10 November 2026): the same statements in the same
order as one at a time, sent in one request; a refusal typed and never undone.

The stand-in below models what ArcadeDB does with a `sqlscript` and what it refuses (rule 15). It
parses the **whole** script before running any of it, so a parse error anywhere applies nothing.
It then runs the statements in order, refuses one that names a type or property it does not have,
and **keeps every schema change before it** (ArcadeDB's schema changes are not transactional). The
live proof, a schema dump compared on a real ArcadeDB, is
`tests/conformance/graph_port/test_schema_batch_live.py`.
"""

from __future__ import annotations

import re
from typing import Any

import httpx
import pytest

from adapters.graph_arcadedb import schema as schema_module
from adapters.graph_arcadedb.client import ArcadeDBError
from adapters.graph_arcadedb.schema import SchemaApplyError, apply_schema, schema_statements
from schemas.domain import (
    EdgeTypeDef,
    EntityTypeDef,
    OntologySchema,
    PoleClass,
    PropertyDef,
    PropertyType,
)

_PARSE = "com.arcadedb.query.sql.parser.ParseException"
_SCHEMA = "com.arcadedb.exception.SchemaException"

_FORMS = (
    re.compile(r"CREATE (VERTEX|EDGE) TYPE (\w+) IF NOT EXISTS"),
    re.compile(r"CREATE PROPERTY (\w+)\.(\w+) IF NOT EXISTS [A-Z ]+"),
    re.compile(r"CREATE INDEX IF NOT EXISTS ON (\w+) \((\w+)( BY ITEM)?\) (UNIQUE|NOTUNIQUE)"),
    re.compile(r"UPDATE .+"),
)

#: The statements, in order, that `apply_schema` sent one at a time on main 17c202d for the
#: ontology below (rule 12: a later change to what the schema says, or its order, is red here).
GOLDEN = [
    "CREATE VERTEX TYPE mx_Person IF NOT EXISTS",
    "CREATE PROPERTY mx_Person.id IF NOT EXISTS STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_Person (id) UNIQUE",
    "CREATE PROPERTY mx_Person.handling_classification IF NOT EXISTS STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_Person (handling_classification) NOTUNIQUE",
    "CREATE PROPERTY mx_Person.handling_code IF NOT EXISTS STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_Person (handling_code) NOTUNIQUE",
    "CREATE PROPERTY mx_Person.owning_unit IF NOT EXISTS STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_Person (owning_unit) NOTUNIQUE",
    "CREATE PROPERTY mx_Person.originator IF NOT EXISTS STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_Person (originator) NOTUNIQUE",
    "CREATE PROPERTY mx_Person.reverted IF NOT EXISTS BOOLEAN",
    "CREATE INDEX IF NOT EXISTS ON mx_Person (reverted) NOTUNIQUE",
    "CREATE PROPERTY mx_Person.superseded_by IF NOT EXISTS STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_Person (superseded_by) NOTUNIQUE",
    "CREATE PROPERTY mx_Person.withdrawn_by_load IF NOT EXISTS STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_Person (withdrawn_by_load) NOTUNIQUE",
    "CREATE PROPERTY mx_Person.promoted_by_load IF NOT EXISTS STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_Person (promoted_by_load) NOTUNIQUE",
    "CREATE PROPERTY mx_Person.datasets IF NOT EXISTS LIST OF STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_Person (datasets BY ITEM) NOTUNIQUE",
    "CREATE PROPERTY mx_Person.nino IF NOT EXISTS STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_Person (nino) NOTUNIQUE",
    "CREATE PROPERTY mx_Person.family_name IF NOT EXISTS STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_Person (family_name) NOTUNIQUE",
    "CREATE EDGE TYPE mx_KNOWS IF NOT EXISTS",
    "CREATE PROPERTY mx_KNOWS.id IF NOT EXISTS STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_KNOWS (id) UNIQUE",
    "CREATE PROPERTY mx_KNOWS.handling_classification IF NOT EXISTS STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_KNOWS (handling_classification) NOTUNIQUE",
    "CREATE PROPERTY mx_KNOWS.handling_code IF NOT EXISTS STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_KNOWS (handling_code) NOTUNIQUE",
    "CREATE PROPERTY mx_KNOWS.owning_unit IF NOT EXISTS STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_KNOWS (owning_unit) NOTUNIQUE",
    "CREATE PROPERTY mx_KNOWS.originator IF NOT EXISTS STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_KNOWS (originator) NOTUNIQUE",
    "CREATE PROPERTY mx_KNOWS.reverted IF NOT EXISTS BOOLEAN",
    "CREATE INDEX IF NOT EXISTS ON mx_KNOWS (reverted) NOTUNIQUE",
    "CREATE PROPERTY mx_KNOWS.superseded_by IF NOT EXISTS STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_KNOWS (superseded_by) NOTUNIQUE",
    "CREATE PROPERTY mx_KNOWS.withdrawn_by_load IF NOT EXISTS STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_KNOWS (withdrawn_by_load) NOTUNIQUE",
    "CREATE PROPERTY mx_KNOWS.promoted_by_load IF NOT EXISTS STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_KNOWS (promoted_by_load) NOTUNIQUE",
    "CREATE PROPERTY mx_KNOWS.datasets IF NOT EXISTS LIST OF STRING",
    "CREATE INDEX IF NOT EXISTS ON mx_KNOWS (datasets BY ITEM) NOTUNIQUE",
    "CREATE PROPERTY mx_KNOWS.valid_from IF NOT EXISTS DATETIME",
    "CREATE INDEX IF NOT EXISTS ON mx_KNOWS (valid_from) NOTUNIQUE",
]


class FakeArcade:
    """Types, properties and indexes; a script parsed whole, then run in order, never undone."""

    def __init__(self, *, failures: list[Exception] | None = None) -> None:
        self.types: dict[str, str] = {}
        self.properties: dict[str, set[str]] = {}
        self.indexes: set[tuple[str, str]] = set()
        self.requests: list[tuple[str, str, Any]] = []
        self._failures = list(failures or [])

    @staticmethod
    def _parse(statement: str) -> re.Match[str]:
        for form in _FORMS:
            if m := form.fullmatch(statement.strip()):
                return m
        raise ArcadeDBError(f"cannot parse {statement!r}", status_code=500, exception_class=_PARSE)

    def _run(self, m: re.Match[str]) -> None:
        if m.re is _FORMS[0]:
            self.types.setdefault(m[2], m[1])
            self.properties.setdefault(m[2], set())
        elif m.re is _FORMS[1]:
            self._has(m[1])
            self.properties[m[1]].add(m[2])
        elif m.re is _FORMS[2]:
            self._has(m[1])
            if m[2] not in self.properties[m[1]]:
                raise ArcadeDBError(
                    f"property {m[2]} not found", status_code=500, exception_class=_SCHEMA
                )
            self.indexes.add((m[1], m[2]))

    def _has(self, type_name: str) -> None:
        if type_name not in self.types:
            raise ArcadeDBError(
                f"type {type_name} was not found", status_code=500, exception_class=_SCHEMA
            )

    async def command(self, language: str, command: str, **kw: Any) -> list[dict[str, Any]]:
        self.requests.append((language, command, kw.get("timeout")))
        if self._failures:
            raise self._failures.pop(0)
        assert language == "sqlscript", language
        parsed = [self._parse(s) for s in command.split(";\n")]  # the whole script, first
        for m in parsed:
            self._run(m)  # stops at the first refusal; what ran before it stays
        return []

    async def sql(self, command: str, **_: Any) -> list[dict[str, Any]]:
        self.requests.append(("sql", command, None))
        self._run(self._parse(command))
        return []

    def shape(self) -> tuple[Any, ...]:
        return dict(self.types), {t: set(p) for t, p in self.properties.items()}, set(self.indexes)

    def scripts(self) -> int:
        return sum(1 for r in self.requests if r[0] == "sqlscript")


def _ontology() -> OntologySchema:
    return OntologySchema(
        version=1,
        entity_types=[
            EntityTypeDef(
                name="Person",
                pole_class=PoleClass("person"),
                channel="indigo",
                shape="circle",
                identifiers=["nino"],
                properties=[
                    PropertyDef(name="family_name", type=PropertyType.STRING, indexed=True)
                ],
            )
        ],
        edge_types=[
            EdgeTypeDef.model_validate(
                {"name": "KNOWS", "from": ["Person"], "to": ["Person"], "temporal": True,
                 "evidence": "direct"}
            )
        ],
    )  # fmt: skip


def _planted(monkeypatch: pytest.MonkeyPatch, statement: str, at: str) -> None:
    real = schema_statements

    def planted(schema: OntologySchema) -> Any:
        plan = real(schema)
        plan.ddl.insert(
            {"first": 0, "middle": len(plan.ddl) // 2, "last": len(plan.ddl)}[at], statement
        )
        return plan

    monkeypatch.setattr(schema_module, "schema_statements", planted)


async def test_the_statements_are_main_s_in_main_s_order_sent_as_one_script() -> None:
    fake = FakeArcade()
    report = await apply_schema(fake, _ontology())  # type: ignore[arg-type]
    assert schema_statements(_ontology()).ddl == GOLDEN
    scripts = [r for r in fake.requests if r[0] == "sqlscript"]
    assert len(scripts) == 1 and scripts[0][1].split(";\n") == GOLDEN
    assert scripts[0][2] == schema_module._SCRIPT_TIMEOUT_SECONDS  # its own timeout, not 30 s
    assert report.applied_entity_types == ["Person"] and report.applied_edge_types == ["KNOWS"]
    # the copy-up still runs after the script, one statement each, so a refused one never stops it
    assert [r[1] for r in fake.requests if r[0] == "sql"] == [
        "UPDATE mx_Person SET family_name = properties.family_name "
        "WHERE properties.family_name IS NOT NULL AND ifnull(family_name, '') = ''"
    ]


@pytest.mark.parametrize("at", ["first", "middle", "last"])
async def test_a_parse_error_anywhere_applies_nothing_and_is_typed_and_sent_once(
    monkeypatch: pytest.MonkeyPatch, at: str
) -> None:
    _planted(monkeypatch, "CREATE PROPERTY NOT VALID SQL", at)
    fake = FakeArcade()
    with pytest.raises(SchemaApplyError) as raised:
        await apply_schema(fake, _ontology())  # type: ignore[arg-type]
    assert raised.value.exception_class == _PARSE and fake.scripts() == 1
    assert fake.shape() == ({}, {}, set())


async def test_a_refusal_while_running_keeps_what_ran_is_never_retried_and_a_re_apply_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main's own semantics: the statements before the refused one stay; the next apply makes the
    schema whole. Nothing is dropped to undo it, since a drop could take another process's type."""
    _planted(monkeypatch, "CREATE INDEX IF NOT EXISTS ON NoSuchType (id) UNIQUE", "middle")
    fake = FakeArcade()
    with pytest.raises(SchemaApplyError) as raised:
        await apply_schema(fake, _ontology())  # type: ignore[arg-type]
    assert raised.value.exception_class == _SCHEMA and fake.scripts() == 1
    assert "mx_Person" in fake.types and "mx_KNOWS" not in fake.types  # half, as main left it
    monkeypatch.undo()
    await apply_schema(fake, _ontology())  # type: ignore[arg-type]
    whole = FakeArcade()
    await apply_schema(whole, _ontology())  # type: ignore[arg-type]
    assert fake.shape() == whole.shape()


async def test_a_failure_to_connect_re_sends_the_whole_script() -> None:
    fake = FakeArcade(failures=[httpx.ConnectError("refused"), httpx.ConnectError("refused")])
    await apply_schema(fake, _ontology())  # type: ignore[arg-type]
    assert fake.scripts() == 3 and "mx_KNOWS" in fake.types


async def test_a_script_that_timed_out_is_not_sent_again_beside_itself() -> None:
    """A read timeout means the script reached the server and may still be running there."""
    fake = FakeArcade(failures=[httpx.ReadTimeout("no answer")])
    with pytest.raises(SchemaApplyError) as raised:
        await apply_schema(fake, _ontology())  # type: ignore[arg-type]
    assert fake.scripts() == 1 and "outcome is unknown" in str(raised.value)
