"""ADR-121: a condition on a pattern node's property. What may be asked, and what is refused by
name (equality only, at most three entries, indexed text properties only, nothing the ontology marks
`sensitivity: high`), checked against the ontology both the route and the graph adapter hold.

Rule 12: each refusal the decision states has a case that fails if the refusal is dropped. The
refusals are checked on a small ontology of our own in which one property is indexed *and* high, so
the sensitivity refusal is proven for its own sake and not because the property also happens to be
unindexed (rule 15: a planted violation that any other branch would have caught proves nothing).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ontology.loader import load_default_ontology
from ontology.pattern_where import PatternConditionRefused, check_pattern_conditions
from schemas.domain import (
    EntityTypeDef,
    OntologySchema,
    PatternEdge,
    PatternNode,
    PatternQuery,
    PropertyDef,
    PropertyType,
    SavedPattern,
)


def _ontology() -> OntologySchema:
    base = load_default_ontology()
    person = base.entity_type("Person")
    assert person is not None
    extra = [
        PropertyDef(name="niu_area", type=PropertyType.STRING, indexed=True),
        PropertyDef(name="soct_region", type=PropertyType.STRING, indexed=True),
        PropertyDef(name="wing", type=PropertyType.STRING, indexed=True),
        PropertyDef(name="block", type=PropertyType.STRING, indexed=True),
        PropertyDef(name="secret_code", type=PropertyType.STRING, indexed=True, sensitivity="high"),
        PropertyDef(name="note", type=PropertyType.STRING),
        PropertyDef(name="capacity", type=PropertyType.INTEGER, indexed=True),
        PropertyDef(name="regime", type=PropertyType.ENUM, indexed=True, values=["open", "closed"]),
    ]
    site = EntityTypeDef(
        name="Establishment", pole_class=person.pole_class, channel=person.channel,
        shape=person.shape, properties=extra,
    )  # fmt: skip
    return base.model_copy(update={"entity_types": [*base.entity_types, site]})


def _pattern(where: dict[str, str], *, entity_type: str | None = "Establishment") -> PatternQuery:
    return PatternQuery(
        nodes=[
            PatternNode(var="p", entity_type="Person"),
            PatternNode(var="e", entity_type=entity_type, where=where),
        ],
        edges=[PatternEdge(edge_type="HELD_AT", from_var="p", to_var="e")],
    )


def _refusal(where: dict[str, str], *, entity_type: str | None = "Establishment") -> (
    PatternConditionRefused
):
    with pytest.raises(PatternConditionRefused) as raised:
        check_pattern_conditions(_pattern(where, entity_type=entity_type), _ontology())
    return raised.value


def test_a_pattern_with_no_condition_is_never_refused() -> None:
    check_pattern_conditions(_pattern({}), _ontology())


def test_an_equality_on_an_indexed_text_property_is_allowed() -> None:
    check_pattern_conditions(_pattern({"niu_area": "North"}), _ontology())
    check_pattern_conditions(_pattern({"regime": "open"}), _ontology())


def test_three_conditions_are_allowed_and_a_fourth_is_refused() -> None:
    three = {"niu_area": "a", "soct_region": "b", "wing": "c"}
    check_pattern_conditions(_pattern(three), _ontology())
    with pytest.raises(ValidationError, match="at most 3"):
        PatternNode(var="e", entity_type="Establishment", where={**three, "block": "d"})


@pytest.mark.parametrize(
    "value", [{"$gt": "a"}, ["a", "b"], 3, None, {"not": "a"}], ids=lambda v: repr(v)
)
def test_only_one_text_value_per_property_is_accepted(value: object) -> None:
    """Equality only (ADR-121): no range, no list of values, no negation shape."""
    with pytest.raises(ValidationError):
        PatternNode.model_validate({"var": "e", "where": {"niu_area": value}})


def test_a_sensitive_property_is_refused_by_name_though_it_is_indexed() -> None:
    refused = _refusal({"secret_code": "x"})
    assert refused.reason == "sensitive"
    assert refused.property_name == "secret_code" and refused.var == "e"
    assert "secret_code" in str(refused) and "sensitivity" in str(refused)


def test_the_default_ontologys_own_high_property_is_refused() -> None:
    pattern = PatternQuery(
        nodes=[PatternNode(var="p", entity_type="Person", where={"date_of_birth": "1990-01-01"})],
        edges=[],
    )
    with pytest.raises(PatternConditionRefused) as raised:
        check_pattern_conditions(pattern, load_default_ontology())
    assert raised.value.reason == "sensitive" and raised.value.property_name == "date_of_birth"


def test_a_property_that_is_not_indexed_is_refused_by_name() -> None:
    refused = _refusal({"note": "x"})
    assert refused.reason == "not_indexed" and refused.property_name == "note"
    assert "note" in str(refused)


def test_a_property_the_type_does_not_declare_is_refused_by_name() -> None:
    refused = _refusal({"nonsense": "x"})
    assert refused.reason == "unknown_property" and refused.property_name == "nonsense"


def test_an_identifier_that_is_not_an_indexed_property_is_refused() -> None:
    """`prison_number` is an identifier of Person, not an indexed property: ADR-121 says indexed."""
    pattern = PatternQuery(
        nodes=[PatternNode(var="p", entity_type="Person", where={"prison_number": "A1234BC"})],
        edges=[],
    )
    with pytest.raises(PatternConditionRefused) as raised:
        check_pattern_conditions(pattern, _ontology())
    assert raised.value.reason == "unknown_property"


def test_a_property_that_is_not_text_is_refused_because_the_value_is_one_string() -> None:
    refused = _refusal({"capacity": "40"})
    assert refused.reason == "unsupported_type" and refused.property_name == "capacity"


def test_a_condition_on_a_node_with_no_type_is_refused() -> None:
    refused = _refusal({"niu_area": "x"}, entity_type=None)
    assert refused.reason == "no_type"


def test_a_condition_on_a_type_the_ontology_does_not_hold_is_refused() -> None:
    refused = _refusal({"niu_area": "x"}, entity_type="Nowhere")
    assert refused.reason == "unknown_type"


def test_the_first_refusal_is_the_node_in_drawing_order_and_names_its_variable() -> None:
    pattern = PatternQuery(
        nodes=[
            PatternNode(var="p", entity_type="Person", where={"family_name": "Smith"}),
            PatternNode(var="e", entity_type="Establishment", where={"note": "x"}),
        ],
        edges=[PatternEdge(edge_type="HELD_AT", from_var="p", to_var="e")],
    )
    with pytest.raises(PatternConditionRefused) as raised:
        check_pattern_conditions(pattern, _ontology())
    assert raised.value.var == "e"


def test_a_saved_pattern_carries_its_conditions_through_the_store_serialisation() -> None:
    """`PatternStore.save` writes `json.dumps(definition.model_dump(mode="json"))` and `get` reads
    it back through `PatternQuery.model_validate`; a field dropped there would drop the condition
    silently, and a rule that replays the saved pattern (ADR-109) would run unfiltered."""
    definition = _pattern({"niu_area": "North", "soct_region": "East"})
    stored = json.dumps(definition.model_dump(mode="json"))
    saved = SavedPattern(
        id="s1", pattern_id="p1", version=1, name="Held at North", owner_id="analyst-1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        definition=PatternQuery.model_validate(json.loads(stored)),
    )  # fmt: skip
    assert saved.definition == definition
    assert saved.definition.nodes[1].where == {"niu_area": "North", "soct_region": "East"}
    assert SavedPattern.model_validate_json(saved.model_dump_json()) == saved


def test_a_pattern_saved_before_conditions_existed_reads_with_none() -> None:
    old = {
        "nodes": [{"var": "p", "entity_type": "Person", "node_id": None}],
        "edges": [],
        "limit": 5,
    }
    assert PatternQuery.model_validate(old).nodes[0].where == {}
