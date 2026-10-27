"""`GraphArcadeDBAdapter.use_schema`: the ontology in memory, for a read-only caller (the seed's
`--check`), with none of `apply_schema`'s DDL or backfill UPDATE.

What a mistake would do, and the case that catches it: `use_schema` sending a statement to the
store (`test_use_schema_sends_nothing_to_the_store`), or taking the schema without the link-type
aliases, so a link stored under an old name reads as a type the ontology no longer has
(`test_use_schema_sets_the_schema_and_the_aliases_apply_schema_sets`)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from adapters.graph_arcadedb import naming
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.naming import logical_type_name, physical_type_name
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import EdgeTypeDef


class RefusingClient:
    """Any call at all is a write or a read the caller did not ask for."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"use_schema must not touch the store: {name}")


@pytest.fixture(autouse=True)
def _restore_the_alias_registry() -> Iterator[None]:
    """The registry is module-global (one ontology per process): put back what was there."""
    canonical, aliases_of = dict(naming._CANONICAL), dict(naming._ALIASES_OF)
    yield
    naming._CANONICAL.clear()
    naming._CANONICAL.update(canonical)
    naming._ALIASES_OF.clear()
    naming._ALIASES_OF.update(aliases_of)


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


def test_the_last_case_left_no_alias_in_the_process_wide_registry() -> None:
    """`use_schema` sets `naming`'s module-global alias registry, which every later test in the
    process reads. The fixture below puts it back; this, last in the file, fails if it does not."""
    assert "KNOWN_TO" not in naming._CANONICAL
    assert "ACQUAINTED_WITH" not in naming._ALIASES_OF
