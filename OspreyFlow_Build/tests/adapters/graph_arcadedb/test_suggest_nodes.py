"""Type-ahead suggestions for the Glass search box: `GraphPort.suggest_nodes` (spec 03 §3.3 note,
ADR-059).

Seen, 2 October 2026: the search box found nothing for `C` and nothing for a partial id, because
`search_nodes` is an exact match by contract. A search that starts on partial input is a separate
read, so the exact one keeps its contract (the same reasoning `suggest_locations` records).

The store here answers as the real one does where it matters: it refuses a query it does not
recognise (rule 15), and it computes `more` from what it is asked for, so a limit applied after
the access filter and not before is what the answer shows.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from adapters.graph_arcadedb import builders
from adapters.graph_arcadedb.naming import physical_type_name
from ports.graph import NodeSuggestions
from schemas.domain import (
    AuditStub,
    Handling,
    Principal,
    PropertyType,
    Provenance,
    ProvenanceState,
    SourceRef,
)

from tests.adapters.graph_arcadedb.edge_store import CountingStore, make_adapter

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


def _element_map(node_id: str) -> dict[str, Any]:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return {
        "id": node_id,
        "label": physical_type_name("Endpoint"),
        "properties": {"value_normalised": node_id, "endpoint_kind": "account"},
        "provenance": Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="d", locator="p.1", excerpt_hash="a" * 64)],
            first_seen=now,
        ).model_dump(mode="json"),
        "handling": Handling(
            classification="OFFICIAL",
            handling_code="P",
            originator="u",
            owning_unit="unit-1",
        ).model_dump(mode="json"),
        "audit": AuditStub(created_at=now, created_by="loader").model_dump(mode="json"),
    }


class _SuggestStore(CountingStore):
    """Holds accounts; answers only the suggestion query, by its prefix and its limit."""

    def __init__(self, ids: list[str]) -> None:
        super().__init__()
        self.ids = ids

    async def gremlin(self, query: str, **_: Any) -> list[Any]:  # type: ignore[override]
        self.queries.append(query)
        if "TextP.startingWith(" not in query or not query.startswith(
            "g.V().hasLabel("
        ):
            raise RuntimeError(f"unexpected query: {query}")
        prefix = query.split("TextP.startingWith(")[1].split(")")[0].strip("'\"")
        limit = int(query.split(".limit(")[1].split(")")[0])
        return [_element_map(i) for i in self.ids if i.startswith(prefix)][:limit]


def _suggest(store: _SuggestStore, prefix: str, limit: int = 10) -> NodeSuggestions:
    return asyncio.run(
        make_adapter(store).suggest_nodes(prefix, PRINCIPAL, limit=limit)
    )


def test_the_suggestions_scope_is_string_identifiers_on_the_types_that_carry_them() -> (
    None
):
    """Catches a prefix scan over every property of every type: it must be label-first (an
    unlabelled lookup scans the whole vertex set, ADR-058 Amendment 9) and over string fields
    only, since a prefix of a number or a flag means nothing."""
    from ontology.loader import load_default_ontology

    schema = load_default_ontology()
    labels, fields = builders.suggestion_scope(schema)
    assert physical_type_name("Endpoint") in labels
    assert "value_normalised" in fields
    declared = {p.name: p.type for e in schema.entity_types for p in e.properties}
    for field in fields:
        assert declared.get(field, PropertyType.STRING) is PropertyType.STRING, field
    for entity in schema.entity_types:
        assert (physical_type_name(entity.name) in labels) == any(
            f in fields
            for f in (
                *entity.identifiers,
                *(p.name for p in entity.properties if p.indexed),
            )
        )


def test_the_query_is_label_first_starts_with_the_prefix_and_keeps_the_access_step() -> (
    None
):
    store = _SuggestStore(["C1305486145"])
    graph = make_adapter(store)
    asyncio.run(graph.suggest_nodes("C13", PRINCIPAL, limit=10))
    query = store.queries[0]
    assert query.startswith("g.V().hasLabel(")
    assert "TextP.startingWith('C13')" in query
    assert graph._access.gremlin_has_step(PRINCIPAL) in query
    assert (
        query.index("hasLabel(") < query.index("startingWith(") < query.index(".limit(")
    )


def test_a_quote_in_the_prefix_cannot_break_out_of_the_query() -> None:
    store = _SuggestStore(["O'Brien"])
    _suggest(store, "O'B")
    assert "TextP.startingWith('O'B')" not in store.queries[0]
    assert "O\\'B" in store.queries[0]


def test_more_is_said_when_there_are_more_and_not_when_there_are_not() -> None:
    """Rule 2: a cut-off list says it was cut off. The adapter asks for one more than the limit,
    returns the limit, and reports the extra as `more`."""
    ids = [f"C1{n:04d}" for n in range(25)]
    store = _SuggestStore(ids)
    page = _suggest(store, "C1", limit=10)
    assert len(page.nodes) == 10 and page.more is True
    assert ".limit(11)" in store.queries[0]
    exact = _suggest(_SuggestStore(ids[:10]), "C1", limit=10)
    assert len(exact.nodes) == 10 and exact.more is False
    assert _suggest(store, "ZZZ").nodes == [] and _suggest(store, "ZZZ").more is False


def test_an_empty_prefix_is_refused_and_asks_the_store_nothing() -> None:
    """Catches a bare scan of every vertex dressed as a suggestion."""
    store = _SuggestStore(["a"])
    with pytest.raises(ValueError, match="prefix"):
        _suggest(store, "")
    assert store.queries == []


def test_an_indexed_property_that_is_not_a_string_is_never_scanned_for_a_prefix() -> (
    None
):
    """The shipped ontology happens to index only strings, so the string-only rule needs a type
    that breaks it: an indexed integer and an integer named as an identifier."""
    from ontology.loader import load_default_ontology
    from schemas.domain import PropertyDef

    schema = load_default_ontology()
    person = next(e for e in schema.entity_types if e.name == "Person")
    person.properties += [
        PropertyDef(name="shoe_size", type=PropertyType.INTEGER, indexed=True),
        PropertyDef(name="badge_no", type=PropertyType.INTEGER),
    ]
    person.identifiers.append("badge_no")
    _, fields = builders.suggestion_scope(schema)
    assert "shoe_size" not in fields and "badge_no" not in fields
