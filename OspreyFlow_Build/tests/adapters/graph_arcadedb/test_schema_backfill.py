"""Applying a schema fills an indexed field on nodes written before it was indexed (ADR-074, found
the day it shipped).

Seen, 3 October 2026: after ontology v11 marked `family_name` and the other name fields `indexed`,
a search for `Petrenko` found nothing although both Petrenko nodes were on screen. The store keeps
an indexed property twice, once inside the `properties` map and once as its own top-level field,
and the top-level copy is what an index and a suggestion read (`serialization.py`). The copy is made
when a node is *written*, so every node written before the property became indexed has the map and
not the field. Marking a property `indexed` is therefore a promise `apply_schema` must keep for
nodes that already exist, not only for the ones written afterwards.

These tests run the schema step against a recording stand-in for the client, so they prove which
statements are issued and in what order. They cannot prove ArcadeDB accepts the `UPDATE`; the live
case in `tests/conformance/graph_port/test_suite.py` does, and a stand-in that records every
statement as accepted proves nothing about that (rule 15), so the stand-in here can be told to
refuse one and the schema step is shown to carry on and say so.
"""

from __future__ import annotations

import logging

import pytest

from adapters.graph_arcadedb.client import ArcadeDBError
from adapters.graph_arcadedb.naming import physical_type_name
from adapters.graph_arcadedb.schema import apply_schema
from schemas.domain import (
    EntityTypeDef,
    OntologySchema,
    PropertyDef,
    PropertyType,
)


class RecordingClient:
    def __init__(self, refuse_updates: bool = False) -> None:
        self.statements: list[str] = []
        self._refuse_updates = refuse_updates

    async def sql(self, command: str, **_: object) -> list[dict[str, object]]:
        self.statements.append(command)
        if self._refuse_updates and command.startswith("UPDATE"):
            raise ArcadeDBError(
                "refused", status_code=500, exception_class="com.arcadedb.exception.SchemaException"
            )
        return []

    def updates(self) -> list[str]:
        return [s for s in self.statements if s.startswith("UPDATE")]


def _schema() -> OntologySchema:
    return OntologySchema(
        version=1,
        entity_types=[
            EntityTypeDef(
                name="Person",
                pole_class="person",
                channel="indigo",
                shape="circle",
                identifiers=["nino"],
                properties=[
                    PropertyDef(name="family_name", type=PropertyType.STRING, indexed=True),
                    PropertyDef(name="given_names", type=PropertyType.STRING, indexed=True),
                    PropertyDef(name="shoe_size", type=PropertyType.INTEGER, indexed=True),
                    PropertyDef(name="nickname", type=PropertyType.STRING),
                ],
            )
        ],
        edge_types=[],
    )


def _type() -> str:
    return physical_type_name("Person")


async def test_each_indexed_text_property_is_copied_up_from_the_map() -> None:
    client = RecordingClient()
    await apply_schema(client, _schema())  # type: ignore[arg-type]
    t = _type()
    assert client.updates() == [
        f"UPDATE {t} SET family_name = properties.family_name "
        "WHERE properties.family_name IS NOT NULL AND ifnull(family_name, '') = ''",
        f"UPDATE {t} SET given_names = properties.given_names "
        "WHERE properties.given_names IS NOT NULL AND ifnull(given_names, '') = ''",
    ]


async def test_the_copy_only_fills_a_missing_field_and_never_overwrites_one() -> None:
    client = RecordingClient()
    await apply_schema(client, _schema())  # type: ignore[arg-type]
    for statement in client.updates():
        assert "ifnull(" in statement and ", '') = ''" in statement


async def test_a_missing_field_is_not_asked_for_with_is_null() -> None:
    """Seen live on ArcadeDB 25.5.1 (3 October 2026): the field is indexed, and
    `WHERE field IS NULL` on it matched 0 rows while 463 nodes had no value, so the first form of
    this copy changed nothing and logged nothing. The `ifnull(...)` form updated all 463."""
    client = RecordingClient()
    await apply_schema(client, _schema())  # type: ignore[arg-type]
    for statement in client.updates():
        assert " IS NULL" not in statement


async def test_a_property_that_is_not_indexed_or_not_text_is_left_alone() -> None:
    client = RecordingClient()
    await apply_schema(client, _schema())  # type: ignore[arg-type]
    joined = "\n".join(client.updates())
    assert "nickname" not in joined
    assert "shoe_size" not in joined
    assert "nino" not in joined  # identifiers have always been written as their own field


async def test_the_copy_runs_after_the_property_and_its_index_exist() -> None:
    client = RecordingClient()
    await apply_schema(client, _schema())  # type: ignore[arg-type]
    t = _type()
    index = client.statements.index(f"CREATE INDEX IF NOT EXISTS ON {t} (family_name) NOTUNIQUE")
    update = next(
        i for i, s in enumerate(client.statements) if s.startswith("UPDATE") and "family_name" in s
    )
    assert index < update


async def test_a_refused_copy_does_not_stop_the_schema_and_is_named_in_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If ArcadeDB declines the `UPDATE`, the API must still start (every other statement still
    ran) and the failure must be loud, naming the type and property, not swallowed."""
    client = RecordingClient(refuse_updates=True)
    with caplog.at_level(logging.WARNING):
        report = await apply_schema(client, _schema())  # type: ignore[arg-type]
    assert report.applied_entity_types == ["Person"]
    assert len(client.updates()) == 2  # it tried both, and carried on after the first refusal
    text = "\n".join(r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING)
    assert _type() in text and "family_name" in text and "given_names" in text
