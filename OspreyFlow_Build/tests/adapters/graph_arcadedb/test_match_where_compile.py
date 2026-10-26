"""ADR-121: `MatchBuilder` compiles a node's `where` into the traversal as a `has(property, value)`
step beside the access steps (rule 3), in `match` and in `match_count`, on every path the compiler
has (the single chain, a walk backwards, and the pinned-root diamond).

The compiled string is the thing under test, since the access filtering is the adapter's and is only
proven against the store by the conformance suite (`test_match_where_*`, live). Each case names the
step it expects by value and position, so a compiler that drops the condition, applies it to the
wrong variable, or puts it after the label fails (rule 15: the planted wrong compile is in the
hand-back; the compiled shape asserted here is the one the adapter really sends).
"""

from __future__ import annotations

import pytest

from adapters.graph_arcadedb.access_filter import AccessFilter
from adapters.graph_arcadedb.builders import MatchBuilder
from ontology.handling import load_uk_le_scheme
from schemas.domain import PatternEdge, PatternNode, PatternQuery, Principal

READER = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
ACCESS = AccessFilter(load_uk_le_scheme())
HAS_ACCESS = ACCESS.gremlin_has_step(READER)


def _held_at(where: dict[str, str]) -> PatternQuery:
    return PatternQuery(
        nodes=[
            PatternNode(var="p", entity_type="Person"),
            PatternNode(var="e", entity_type="Establishment", where=where),
        ],
        edges=[PatternEdge(edge_type="HELD_AT", from_var="p", to_var="e")],
    )


def _both_renderings(pattern: PatternQuery) -> list[str]:
    builder = MatchBuilder(pattern)
    return [
        builder.render_gremlin(ACCESS, READER),
        builder.render_count_gremlin(ACCESS, READER, ceiling=50),
    ]


@pytest.mark.parametrize("rendered", range(2), ids=["match", "match_count"])
def test_a_condition_on_a_reached_node_sits_beside_its_access_step(rendered: int) -> None:
    text = _both_renderings(_held_at({"niu_area": "North"}))[rendered]
    assert (
        f".{HAS_ACCESS}.hasLabel('mx_Establishment').has('niu_area','North').as('e')"
    ) in text


def test_a_condition_on_the_first_node_is_in_front_of_its_label() -> None:
    pattern = PatternQuery(
        nodes=[PatternNode(var="p", entity_type="Person", where={"family_name": "Smith"})],
        edges=[],
    )
    for text in _both_renderings(pattern):
        assert text.startswith(
            f"g.V().hasLabel('mx_Person').has('family_name','Smith').{HAS_ACCESS}.as('p')"
        )


def test_conditions_are_emitted_in_property_order_so_a_pattern_compiles_the_same_way() -> None:
    where_a = {"soct_region": "East", "niu_area": "North", "wing": "A"}
    where_b = {"wing": "A", "niu_area": "North", "soct_region": "East"}
    assert _both_renderings(_held_at(where_a)) == _both_renderings(_held_at(where_b))
    assert ".has('niu_area','North').has('soct_region','East').has('wing','A')" in (
        _both_renderings(_held_at(where_a))[0]
    )


def test_a_value_is_a_quoted_literal_never_pasted_into_the_query() -> None:
    nasty = "x').drop().has('y"
    text = _both_renderings(_held_at({"niu_area": nasty}))[0]
    assert ".has('niu_area','x\\').drop().has(\\'y')" in text


def test_a_pattern_with_no_condition_compiles_exactly_as_before() -> None:
    """No step is added for an empty `where`: the existing golden compile
    (`test_match_single_chain_pattern_compiles_to_the_same_gremlin_as_before`) is untouched."""
    plain = PatternQuery(
        nodes=[PatternNode(var="p", entity_type="Person"), PatternNode(var="e")],
        edges=[PatternEdge(edge_type="USES", from_var="p", to_var="e")],
    )
    with_empty = PatternQuery(
        nodes=[
            PatternNode(var="p", entity_type="Person", where={}),
            PatternNode(var="e", where={}),
        ],
        edges=plain.edges,
    )
    assert _both_renderings(plain) == _both_renderings(with_empty)
    assert all(".has('" not in text for text in _both_renderings(plain))


def test_a_condition_on_a_node_walked_to_backwards_is_applied_to_it() -> None:
    """The pattern is drawn with the conditioned node at the end of an edge, and walked from the
    other end: `e` is bound first (`nodes[0]`), `p` is reached through `inE`."""
    pattern = PatternQuery(
        nodes=[
            PatternNode(var="e", entity_type="Establishment", where={"niu_area": "North"}),
            PatternNode(var="p", entity_type="Person", where={"family_name": "Smith"}),
        ],
        edges=[PatternEdge(edge_type="HELD_AT", from_var="p", to_var="e")],
    )
    for text in _both_renderings(pattern):
        assert text.startswith("g.V().hasLabel('mx_Establishment').has('niu_area','North')")
        assert (
            f".outV().{HAS_ACCESS}.hasLabel('mx_Person').has('family_name','Smith').as('p')"
        ) in text


def test_a_condition_survives_the_diamond_path_on_the_open_root_and_the_convergence_node() -> None:
    pattern = PatternQuery(
        nodes=[
            PatternNode(var="a", entity_type="Person", node_id="n1"),
            PatternNode(var="b", entity_type="Person", node_id="n2"),
            PatternNode(var="x", entity_type="Establishment", where={"niu_area": "North"}),
        ],
        edges=[
            PatternEdge(edge_type="HELD_AT", from_var="a", to_var="x"),
            PatternEdge(edge_type="HELD_AT", from_var="b", to_var="x"),
        ],
    )
    for text in _both_renderings(pattern):
        assert (
            f".{HAS_ACCESS}.hasLabel('mx_Establishment').has('niu_area','North').as('x')"
        ) in text


def test_a_condition_on_a_pinned_secondary_root_is_checked_beside_its_id() -> None:
    pattern = PatternQuery(
        nodes=[
            PatternNode(var="a", entity_type="Person", node_id="n1"),
            PatternNode(
                var="b", entity_type="Person", node_id="n2", where={"family_name": "Jones"}
            ),
            PatternNode(var="x", entity_type="Establishment"),
        ],
        edges=[
            PatternEdge(edge_type="HELD_AT", from_var="a", to_var="x"),
            PatternEdge(edge_type="HELD_AT", from_var="b", to_var="x"),
        ],
    )
    for text in _both_renderings(pattern):
        assert ".has(\"id\",'n2').has('family_name','Jones')" in text


def test_the_condition_is_compiled_for_every_variable_that_carries_one() -> None:
    pattern = PatternQuery(
        nodes=[
            PatternNode(var="p", entity_type="Person", where={"family_name": "Smith"}),
            PatternNode(var="e", entity_type="Establishment", where={"niu_area": "North"}),
        ],
        edges=[PatternEdge(edge_type="HELD_AT", from_var="p", to_var="e")],
    )
    for text in _both_renderings(pattern):
        assert text.count(".has('family_name','Smith')") == 1
        assert text.count(".has('niu_area','North')") == 1


def test_a_condition_on_the_open_root_of_a_pinned_diamond_is_applied_to_it() -> None:
    """The open root is the primary of `_render_matched`: the walk starts there, so its condition
    narrows the whole walk, in front of its access step."""
    pattern = PatternQuery(
        nodes=[
            PatternNode(var="a", entity_type="Person", where={"family_name": "Smith"}),
            PatternNode(var="b", entity_type="Person", node_id="n2"),
            PatternNode(var="x", entity_type="Establishment"),
        ],
        edges=[
            PatternEdge(edge_type="HELD_AT", from_var="a", to_var="x"),
            PatternEdge(edge_type="HELD_AT", from_var="b", to_var="x"),
        ],
    )
    for text in _both_renderings(pattern):
        assert text.startswith(
            f"g.V().hasLabel('mx_Person').has('family_name','Smith').{HAS_ACCESS}.as('a')"
        )
