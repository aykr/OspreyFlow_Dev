"""`GraphPort` conformance suite — `docs/07_BUILD_PLAN.md` Phase 1,
`docs/04_VAULT_BACKEND.md` §6, `docs/00_ARCHITECTURE.md` §2.1 and §5.

Parametrised over `GRAPH_PORT_ADAPTERS` in `tests/conformance/registry.py` —
each entry opens a fresh, uniquely-named ArcadeDB database per test. A
second dialect or a second adapter proves itself against these same cases
with no change to this file's shape, only the registry.

The existence-leak tests (`test_unauthorised_*`) are the hard part: it is
not enough that an unauthorised principal's query omits a hidden node's
properties. Each one builds a "hidden" fixture — a SECRET-classified
node/edge an OFFICIAL-cleared analyst cannot see — and asserts the
unauthorised principal's result carries no trace of it at all: not in a
degree count, not in a path length, not in a match result. A leak here
would mean the result differs only because the hidden record exists, which
is exactly what must never be observable.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ontology.errors import OntologyError
from ports.graph import GraphPort
from schemas.domain import (
    EdgeWrite,
    ExpandRequest,
    Interval,
    NodeWrite,
    PathRequest,
    PatternEdge,
    PatternNode,
    PatternQuery,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory

pytestmark = pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str)

OFFICIAL = Principal(id="analyst-official", clearance="OFFICIAL", org_unit="unit-1")
SENSITIVE = Principal(id="analyst-sensitive", clearance="OFFICIAL-SENSITIVE", org_unit="unit-1")
CLEARED = Principal(id="analyst-secret", clearance="SECRET", org_unit="unit-1")
UNKNOWN_CLEARANCE = Principal(id="analyst-unknown", clearance="NOT-A-SCHEME-LEVEL", org_unit="u")


def _provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
        first_seen=datetime.now(UTC),
    )


def _handling(
    classification: str,
    *,
    handling_code: str = "P",
    owning_unit: str = "unit-1",
    originator: str = "unit-1",
) -> dict[str, str]:
    return {
        "classification": classification,
        "handling_code": handling_code,
        "originator": originator,
        "owning_unit": owning_unit,
    }


#: Required properties per default-ontology entity type, so every test
#: fixture satisfies `validate_properties` without each call site having to
#: know the ontology's required fields.
_DEFAULT_PROPERTIES: dict[str, dict[str, object]] = {
    "Person": {"family_name": "Test"},
    "Endpoint": {"value_normalised": "+441234567890"},
}


def _node(
    node_type: str,
    *,
    classification: str,
    handling_code: str = "P",
    owning_unit: str = "unit-1",
    originator: str = "unit-1",
    **properties: object,
) -> NodeWrite:
    merged_properties = {**_DEFAULT_PROPERTIES.get(node_type, {}), **properties}
    return NodeWrite(
        type=node_type,
        properties=merged_properties,
        provenance=_provenance(),
        handling=_handling(  # type: ignore[arg-type]
            classification, handling_code=handling_code, owning_unit=owning_unit,
            originator=originator,
        ),
        created_by="loader-1",
    )


def _edge(
    edge_type: str,
    source: str,
    target: str,
    *,
    classification: str,
    handling_code: str = "P",
    owning_unit: str = "unit-1",
    originator: str = "unit-1",
    interval: Interval | None = None,
) -> EdgeWrite:
    return EdgeWrite(
        type=edge_type,
        source=source,
        target=target,
        provenance=_provenance(),
        handling=_handling(  # type: ignore[arg-type]
            classification, handling_code=handling_code, owning_unit=owning_unit,
            originator=originator,
        ),
        created_by="loader-1",
        interval=interval,
    )


async def _write(
    adapter: GraphPort, nodes: list[NodeWrite], edges: list[EdgeWrite]
) -> tuple[list[str], list[str]]:
    tx = await adapter.begin_transaction()
    node_ids = await adapter.upsert_nodes(nodes, tx)
    edge_ids = await adapter.upsert_edges(edges, tx) if edges else []
    await adapter.commit_transaction(tx)
    return node_ids, edge_ids


# --- basic round trips -------------------------------------------------------


async def test_write_and_read_back_every_default_ontology_entity_type(
    factory: GraphAdapterFactory,
) -> None:
    from ontology.loader import load_default_ontology

    ontology = load_default_ontology()
    async with factory.context() as adapter:
        for entity in ontology.entity_types:
            (node_id,), _ = await _write(
                adapter, [_node(entity.name, classification="OFFICIAL")], []
            )
            node = await adapter.get_node(node_id, CLEARED)
            assert node is not None
            assert node.type == entity.name


async def test_write_and_read_back_an_edge(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL"),
                _node("Person", classification="OFFICIAL"),
            ],
            [],
        )
        _, (edge_id,) = await _write(
            adapter, [], [_edge("ASSOCIATE_OF", a, b, classification="OFFICIAL")]
        )
        stats = await adapter.neighbourhood_stats(a, CLEARED)
        assert stats.degree == 1
        assert stats.degree_by_type == {"ASSOCIATE_OF": 1}
        assert edge_id


# --- expand at depth 1-4 -----------------------------------------------------


async def test_expand_reaches_further_nodes_as_depth_increases(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        node_ids, _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL") for _ in range(5)], []
        )
        edges = [
            _edge("ASSOCIATE_OF", node_ids[i], node_ids[i + 1], classification="OFFICIAL")
            for i in range(4)
        ]
        await _write(adapter, [], edges)

        for depth in (1, 2, 3, 4):
            subgraph = await adapter.expand(
                ExpandRequest(node_ids=[node_ids[0]], depth=depth), CLEARED
            )
            reached = {n.id for n in subgraph.nodes}
            assert reached == set(node_ids[: depth + 1])


# --- k-shortest paths --------------------------------------------------------


async def test_paths_finds_the_chain_and_respects_max_hops(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        node_ids, _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL") for _ in range(4)], []
        )
        edges = [
            _edge("ASSOCIATE_OF", node_ids[i], node_ids[i + 1], classification="OFFICIAL")
            for i in range(3)
        ]
        await _write(adapter, [], edges)

        found = await adapter.paths(
            PathRequest(source=node_ids[0], target=node_ids[3], max_hops=6, k=1), CLEARED
        )
        assert len(found) == 1
        assert found[0].length == 3

        too_short = await adapter.paths(
            PathRequest(source=node_ids[0], target=node_ids[3], max_hops=2, k=1), CLEARED
        )
        assert too_short == []


# --- pattern match ------------------------------------------------------------


async def test_match_finds_the_declared_pattern(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL"),
                _node("Endpoint", classification="OFFICIAL"),
            ],
            [],
        )
        await _write(adapter, [], [_edge("USES", a, b, classification="OFFICIAL")])

        pattern = PatternQuery(
            nodes=[
                PatternNode(var="p", entity_type="Person"),
                PatternNode(var="e", entity_type="Endpoint"),
            ],
            edges=[PatternEdge(edge_type="USES", from_var="p", to_var="e")],
        )
        subgraph = await adapter.match(pattern, CLEARED)
        found_ids = {n.id for n in subgraph.nodes}
        assert {a, b} <= found_ids


# --- temporal filtering on the vertex-centric index -------------------------


async def test_expand_temporal_window_filters_edges_by_valid_from(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (a, b, c), _ = await _write(
            adapter, [_node("Endpoint", classification="OFFICIAL") for _ in range(3)], []
        )
        now = datetime.now(UTC)
        await _write(
            adapter,
            [],
            [
                _edge(
                    "COMMUNICATED_WITH",
                    a,
                    b,
                    classification="OFFICIAL",
                    interval=Interval(valid_from=now - timedelta(days=30)),
                ),
                _edge(
                    "COMMUNICATED_WITH",
                    a,
                    c,
                    classification="OFFICIAL",
                    interval=Interval(valid_from=now),
                ),
            ],
        )

        window = Interval(valid_from=now - timedelta(hours=1), valid_to=now + timedelta(hours=1))
        subgraph = await adapter.expand(
            ExpandRequest(node_ids=[a], depth=1, temporal_window=window), CLEARED
        )
        reached = {n.id for n in subgraph.nodes}
        assert reached == {a, c}


# --- transactions -------------------------------------------------------------


async def test_rollback_discards_every_write_made_under_the_transaction(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        tx = await adapter.begin_transaction()
        (node_id,) = await adapter.upsert_nodes(
            [_node("Person", classification="OFFICIAL")], tx
        )
        await adapter.rollback_transaction(tx)

        assert await adapter.get_node(node_id, CLEARED) is None


# --- schema migration up and down --------------------------------------------


async def test_schema_migration_is_idempotent_and_reversible(
    factory: GraphAdapterFactory,
) -> None:
    """"Up" twice is a no-op; "down" — `revert_schema` — is provable through
    `GraphPort` itself, not by reaching into an adapter's private client
    (the conformance suite is the contract; a second adapter cannot satisfy
    a contract it must reach past the Protocol to prove)."""
    from ontology.loader import load_default_ontology
    from schemas.domain import EntityTypeDef, PoleClass

    ontology = load_default_ontology()
    async with factory.context() as adapter:
        # `factory.context()` already applied `ontology` once (version 3).
        up_again = await adapter.apply_schema(ontology)
        assert set(up_again.applied_entity_types) == {e.name for e in ontology.entity_types}

        extra_type = EntityTypeDef(
            name="Widget", pole_class=PoleClass.OBJECT, channel="rose", shape="star"
        )
        widened = ontology.model_copy(
            update={
                "version": ontology.version + 1,
                "entity_types": [*ontology.entity_types, extra_type],
            }
        )
        await adapter.apply_schema(widened)
        (widget_id,), _ = await _write(adapter, [_node("Widget", classification="OFFICIAL")], [])
        assert await adapter.get_node(widget_id, CLEARED) is not None

        reverted = await adapter.revert_schema(ontology.version)
        assert "Widget" not in set(reverted.applied_entity_types)

        # The dropped type is genuinely gone from both the adapter's
        # tracked schema and the live store, not just unlisted.
        with pytest.raises(OntologyError):
            await _write(adapter, [_node("Widget", classification="OFFICIAL")], [])

        (node_id,), _ = await _write(adapter, [_node("Person", classification="OFFICIAL")], [])
        assert await adapter.get_node(node_id, CLEARED) is not None


# --- existence-leak assertions ------------------------------------------------


async def test_unauthorised_get_node_matches_a_graph_where_the_node_never_existed(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (hidden,), _ = await _write(adapter, [_node("Person", classification="SECRET")], [])
        assert await adapter.get_node(hidden, OFFICIAL) is None
        assert await adapter.get_node("not-a-real-id-at-all", OFFICIAL) is None


async def test_unauthorised_degree_count_matches_a_graph_without_the_hidden_neighbour(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (hub,), _ = await _write(adapter, [_node("Person", classification="OFFICIAL")], [])
        (visible,), _ = await _write(adapter, [_node("Endpoint", classification="OFFICIAL")], [])
        await _write(adapter, [], [_edge("USES", hub, visible, classification="OFFICIAL")])
        before_hidden_edge = await adapter.neighbourhood_stats(hub, OFFICIAL)

        (secret_neighbour,), _ = await _write(
            adapter, [_node("Endpoint", classification="SECRET")], []
        )
        await _write(adapter, [], [_edge("USES", hub, secret_neighbour, classification="SECRET")])
        after_hidden_edge = await adapter.neighbourhood_stats(hub, OFFICIAL)

        # Adding a SECRET neighbour must not move the OFFICIAL-cleared
        # degree count by even one — the two observations are identical.
        assert before_hidden_edge == after_hidden_edge

        authorised_view = await adapter.neighbourhood_stats(hub, CLEARED)
        assert authorised_view.degree == 2  # proves the filter is real, not a no-op


async def test_unauthorised_path_length_matches_a_graph_without_the_hidden_hop(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (a, b, target), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL"),
                _node("Person", classification="OFFICIAL"),
                _node("Person", classification="OFFICIAL"),
            ],
            [],
        )
        await _write(
            adapter,
            [],
            [
                _edge("ASSOCIATE_OF", a, b, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", b, target, classification="OFFICIAL"),
            ],
        )
        # A shorter, hidden route a->target directly, at SECRET.
        await _write(adapter, [], [_edge("ASSOCIATE_OF", a, target, classification="SECRET")])

        unauthorised = await adapter.paths(
            PathRequest(source=a, target=target, max_hops=6, k=5), OFFICIAL
        )
        authorised = await adapter.paths(
            PathRequest(source=a, target=target, max_hops=6, k=5), CLEARED
        )

        # The unauthorised principal only ever sees the 2-hop route — the
        # 1-hop SECRET shortcut is invisible, not merely deprioritised.
        assert {p.length for p in unauthorised} == {2}
        assert {p.length for p in authorised} == {1, 2}


async def test_unauthorised_match_never_returns_the_hidden_node(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (person, secret_endpoint), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL"),
                _node("Endpoint", classification="SECRET"),
            ],
            [],
        )
        await _write(
            adapter, [], [_edge("USES", person, secret_endpoint, classification="SECRET")]
        )

        pattern = PatternQuery(
            nodes=[
                PatternNode(var="p", entity_type="Person"),
                PatternNode(var="e", entity_type="Endpoint"),
            ],
            edges=[PatternEdge(edge_type="USES", from_var="p", to_var="e")],
        )
        result = await adapter.match(pattern, OFFICIAL)
        assert secret_endpoint not in {n.id for n in result.nodes}


async def test_an_unrecognised_clearance_sees_nothing_rather_than_everything(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (node_id,), _ = await _write(adapter, [_node("Person", classification="OFFICIAL")], [])
        assert await adapter.get_node(node_id, UNKNOWN_CLEARANCE) is None


# --- the second access axis: handling_code, scoped by owning_unit ----------
#
# `01_DOMAIN_MODEL.md` §2.2's field-by-field table: `classification` alone
# is a partial implementation — it passes every existence-leak test above
# and still discloses a recipient-restricted (`handling_code: R`) record to
# a principal outside its owning unit. Same three assertions as the
# classification axis (get_node, degree, path length), against a record
# that is fully within the OFFICIAL-cleared unauthorised principal's
# classification but restricted to a unit it doesn't belong to.


async def test_restricted_record_visible_only_to_the_owning_unit_and_receivable_set(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (restricted,), _ = await _write(
            adapter,
            [
                _node(
                    "Person",
                    classification="OFFICIAL",
                    handling_code="R",
                    owning_unit="unit-restricted",
                )
            ],
            [],
        )

        in_unit_and_receives_r = Principal(
            id="a1",
            clearance="OFFICIAL",
            org_unit="unit-restricted",
            receivable_handling_codes=["R"],
        )
        wrong_unit_but_receives_r = Principal(
            id="a2",
            clearance="OFFICIAL",
            org_unit="unit-elsewhere",
            receivable_handling_codes=["R"],
        )
        right_unit_but_does_not_receive_r = Principal(
            id="a3", clearance="OFFICIAL", org_unit="unit-restricted"
        )

        assert (await adapter.get_node(restricted, in_unit_and_receives_r)) is not None
        assert (await adapter.get_node(restricted, wrong_unit_but_receives_r)) is None
        assert (await adapter.get_node(restricted, right_unit_but_does_not_receive_r)) is None
        # OFFICIAL's clearance dominates the record's classification, and it
        # is otherwise the same principal shape as every other test in this
        # suite — classification alone would have let it through.
        assert (await adapter.get_node(restricted, OFFICIAL)) is None


async def test_unauthorised_degree_count_matches_a_graph_without_the_wrong_unit_neighbour(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (hub,), _ = await _write(adapter, [_node("Person", classification="OFFICIAL")], [])
        (visible,), _ = await _write(adapter, [_node("Endpoint", classification="OFFICIAL")], [])
        await _write(adapter, [], [_edge("USES", hub, visible, classification="OFFICIAL")])
        before = await adapter.neighbourhood_stats(hub, OFFICIAL)

        (restricted_neighbour,), _ = await _write(
            adapter,
            [
                _node(
                    "Endpoint",
                    classification="OFFICIAL",
                    handling_code="R",
                    owning_unit="unit-restricted",
                )
            ],
            [],
        )
        await _write(
            adapter,
            [],
            [
                _edge(
                    "USES",
                    hub,
                    restricted_neighbour,
                    classification="OFFICIAL",
                    handling_code="R",
                    owning_unit="unit-restricted",
                )
            ],
        )
        after = await adapter.neighbourhood_stats(hub, OFFICIAL)

        # OFFICIAL's clearance covers this record's classification
        # entirely — only the unit scoping on the restricted `handling_code`
        # hides it. A classification-only filter would have let this count
        # move.
        assert before == after

        in_unit = Principal(
            id="a1",
            clearance="OFFICIAL",
            org_unit="unit-restricted",
            receivable_handling_codes=["R"],
        )
        assert (await adapter.neighbourhood_stats(hub, in_unit)).degree == 2
