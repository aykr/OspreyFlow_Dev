"""ADR-090 Amendment 1, by alias (owner, 5 October 2026): a proposal renamed at promotion keeps its
links under its old name, and the graph store treats that name as an alias of the promoted type.
What a mistake would do: links of the renamed proposal would read under a name the ontology no
longer has, drop out of every expansion by the new type, and a rewrite would have missed those under
restricted handling. Run against the real store (a link is planted under the old name first)."""

from __future__ import annotations

import pytest

from ontology.errors import OntologyError
from ontology.loader import load_default_ontology
from schemas.domain import EdgeTypeDef, ExpandRequest
from tests.conformance.graph_port.test_suite import CLEARED, _edge, _node, _write
from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory

pytestmark = [
    pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str),
    pytest.mark.usefixtures("_sweep_stale_conformance_databases"),
]

BASE = load_default_ontology()
PROPOSED = EdgeTypeDef.model_validate(
    {
        "name": "KNOWN_TO",
        "from": ["Person"],
        "to": ["Person"],
        "basis": "probabilistic",
        "analyst_defined": True,
    }
)
PROMOTED = EdgeTypeDef.model_validate(
    {
        "name": "ACQUAINTED_WITH",
        "from": ["Person"],
        "to": ["Person"],
        "basis": "probabilistic",
        "aliases": ["KNOWN_TO"],
    }
)


def _with(*types: EdgeTypeDef):  # type: ignore[no-untyped-def]
    return BASE.model_copy(update={"edge_types": [*BASE.edge_types, *types]})


async def test_a_link_under_an_alias_reads_and_is_found_as_its_type(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        await adapter.apply_schema(_with(PROPOSED))
        (a, b), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL", family_name="A"),
                _node("Person", classification="OFFICIAL", family_name="B"),
            ],
            [],
        )
        await _write(adapter, [], [_edge("KNOWN_TO", a, b, classification="OFFICIAL")])

        await adapter.apply_schema(_with(PROMOTED))

        filtered = await adapter.expand(
            ExpandRequest(node_ids=[a], edge_types=["ACQUAINTED_WITH"]), CLEARED
        )
        assert [e.type for e in filtered.edges] == ["ACQUAINTED_WITH"]
        everything = await adapter.expand(ExpandRequest(node_ids=[a]), CLEARED)
        assert {e.type for e in everything.edges} == {"ACQUAINTED_WITH"}


async def test_no_new_link_is_written_under_the_old_name(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        await adapter.apply_schema(_with(PROPOSED))
        (a, b), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL", family_name="A"),
                _node("Person", classification="OFFICIAL", family_name="B"),
            ],
            [],
        )
        await adapter.apply_schema(_with(PROMOTED))
        with pytest.raises(OntologyError):
            await _write(adapter, [], [_edge("KNOWN_TO", a, b, classification="OFFICIAL")])


def _proposal(status: str = "pending", promoted_name: str | None = None):  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime

    from services.api.link_types import LinkTypeProposal

    return LinkTypeProposal(
        id="01JPROPOSAL",
        name="KNOWN_TO",
        from_types=["Person"],
        to_types=["Person"],
        directed=False,
        investigation_id="inv-1",
        owning_unit="unit-1",
        proposed_by="analyst-1",
        proposed_at=datetime(2026, 10, 5, tzinfo=UTC),
        reason="By sight",
        status=status,
        promoted_name=promoted_name,
        basis="probabilistic" if status == "promoted" else None,
    )


async def test_a_pending_proposals_links_are_stored_under_its_label_and_read_as_its_name(
    factory: GraphAdapterFactory,
) -> None:
    """The composed ontology end to end (`compose_ontology`): written under the proposal's own
    label, read and filtered as its name; renamed at promotion, read and filtered as the new one."""
    from services.api.link_types import compose_ontology

    from adapters.graph_arcadedb.naming import set_edge_aliases

    pending = _proposal()
    async with factory.context() as adapter:
        await adapter.apply_schema(compose_ontology(BASE, [pending], revision=0))
        (a, b), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL", family_name="A"),
                _node("Person", classification="OFFICIAL", family_name="B"),
            ],
            [],
        )
        await _write(adapter, [], [_edge(pending.storage_name, a, b, classification="OFFICIAL")])

        found = await adapter.expand(ExpandRequest(node_ids=[a], edge_types=["KNOWN_TO"]), CLEARED)
        assert [e.type for e in found.edges] == ["KNOWN_TO"]

        # A process that composed before the proposal was made still reads it under its name.
        set_edge_aliases({})
        everything = await adapter.expand(ExpandRequest(node_ids=[a]), CLEARED)
        assert {e.type for e in everything.edges} == {"KNOWN_TO"}

        renamed = _proposal("promoted", "ACQUAINTED_WITH")
        await adapter.apply_schema(compose_ontology(BASE, [renamed], revision=1))
        found = await adapter.expand(
            ExpandRequest(node_ids=[a], edge_types=["ACQUAINTED_WITH"]), CLEARED
        )
        assert [e.type for e in found.edges] == ["ACQUAINTED_WITH"]


async def test_get_edges_reads_an_aliased_link_as_its_type_among_other_types(
    factory: GraphAdapterFactory,
) -> None:
    """`get_edges` asks every stored link type for the ids, so a link stored under an alias is
    found and read back as the type it now answers to, beside links of other types, in one call
    (ADR-124 U1)."""
    from schemas.domain import Principal

    reader = Principal(id="reader", clearance="OFFICIAL", org_unit="unit-1", datasets=["enron"])
    async with factory.context() as adapter:
        await adapter.apply_schema(_with(PROPOSED))
        (a, b, c), _ = await _write(
            adapter,
            [_node("Person", classification="OFFICIAL", datasets=["enron"]) for _ in "abc"],
            [],
        )
        _, (aliased, assoc, family) = await _write(
            adapter,
            [],
            [
                _edge("KNOWN_TO", a, b, classification="OFFICIAL", datasets=["enron"]),
                _edge("ASSOCIATE_OF", b, c, classification="OFFICIAL", datasets=["enron"]),
                _edge("FAMILY_OF", a, c, classification="OFFICIAL", datasets=["enron"]),
            ],
        )

        await adapter.apply_schema(_with(PROMOTED))

        edges = await adapter.get_edges([family, aliased, assoc], reader)
        assert [e.id for e in edges] == sorted([aliased, assoc, family])
        assert {e.id: e.type for e in edges} == {
            aliased: "ACQUAINTED_WITH",
            assoc: "ASSOCIATE_OF",
            family: "FAMILY_OF",
        }


async def test_reads_by_id_find_a_type_another_process_created_after_this_one_applied_its_ontology(
    factory: GraphAdapterFactory,
) -> None:
    """ADR-124 Amendment 2: the types a lookup asks come from the store, not from the ontology the
    reading process applied. A link stored under a pending proposal's own storage type, and a node
    of an entity type, both created by another process, are found by one that knows neither."""
    from typing import Any

    from services.api.link_types import compose_ontology

    from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
    from schemas.domain import Principal

    pending = _proposal()
    boat = next(e for e in BASE.entity_types if e.name == "Person").model_copy(
        update={"name": "Boat"}
    )
    composed = compose_ontology(BASE, [pending], revision=0)
    composed = composed.model_copy(update={"entity_types": [*composed.entity_types, boat]})
    reader = Principal(id="reader", clearance="OFFICIAL", org_unit="unit-1", datasets=["enron"])
    async with factory.context() as writer:
        await writer.apply_schema(composed)
        (a, b, boat_id), _ = await _write(
            writer,
            [
                _node("Person", classification="OFFICIAL", datasets=["enron"]),
                _node("Person", classification="OFFICIAL", datasets=["enron"]),
                _node("Boat", classification="OFFICIAL", datasets=["enron"], family_name="Hull"),
            ],
            [],
        )
        _, (link,) = await _write(
            writer,
            [],
            [_edge(pending.storage_name, a, b, classification="OFFICIAL", datasets=["enron"])],
        )

        # Another process on the same database, whose ontology lacks the proposal and the type.
        shared: Any = writer
        other = GraphArcadeDBAdapter(shared._client, shared._scheme)
        await other.apply_schema(BASE)

        (edge,) = await other.get_edges([link], reader)
        assert (edge.id, edge.type) == (link, "KNOWN_TO")
        nodes = await other.get_nodes([boat_id, a], reader)
        assert {n.id: n.type for n in nodes} == {boat_id: "Boat", a: "Person"}
        # The access step still applies to what it found.
        assert await other.get_edges([link], reader.model_copy(update={"datasets": []})) == []
