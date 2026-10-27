"""`GraphArcadeDBAdapter.use_schema`: the ontology in memory, for a read-only caller (the seed's
`--check`), with none of `apply_schema`'s DDL or backfill UPDATE.

What a mistake would do, and the case that catches it: `use_schema` sending a statement to the
store (`test_use_schema_sends_nothing_to_the_store`), or taking the schema without the link-type
aliases, so a link stored under an old name reads as a type the ontology no longer has
(`test_use_schema_sets_the_schema_and_the_aliases_apply_schema_sets`)."""

from __future__ import annotations

from typing import Any

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.naming import logical_type_name, physical_type_name
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import EdgeTypeDef


class RefusingClient:
    """Any call at all is a write or a read the caller did not ask for."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"use_schema must not touch the store: {name}")


def _adapter() -> GraphArcadeDBAdapter:
    return GraphArcadeDBAdapter(RefusingClient(), load_uk_le_scheme())  # type: ignore[arg-type]


def _ontology() -> Any:
    base = load_default_ontology()
    promoted = EdgeTypeDef.model_validate(
        {
            "name": "ACQUAINTED_WITH",
            "from": ["Person"],
            "to": ["Person"],
            "basis": "probabilistic",
            "aliases": ["KNOWN_TO"],
        }
    )
    return base.model_copy(update={"edge_types": [*base.edge_types, promoted]})


def test_use_schema_sends_nothing_to_the_store() -> None:
    adapter = _adapter()
    adapter.use_schema(_ontology())
    assert adapter._require_schema() is not None


def test_use_schema_sets_the_schema_and_the_aliases_apply_schema_sets() -> None:
    adapter = _adapter()
    schema = _ontology()
    adapter.use_schema(schema)
    assert adapter._require_schema() is schema
    assert logical_type_name(physical_type_name("KNOWN_TO")) == "ACQUAINTED_WITH"
