"""The domain model mapped to Laurium's schema, and Laurium's output back to the request's shape
(`06_DECISIONS.md` ADR-135 Amendment 6 decision 6).

The schemas planted here are the ones the service really receives: `ExtractionRequest.json_schema`
as `services/extract/profile.build_schema` makes it from the default ontology, and the conformance
suite's own one-field schema. Laurium's schema is `{field: type}` (its `make_dynamic_example_model` and
`create_prompt` take it as is), so the check is that a Pydantic model built from the mapping accepts
exactly what the JSON Schema accepts on those shapes, and refuses what it refuses.
"""

from __future__ import annotations

import typing
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError, create_model

from ontology.loader import load_default_ontology
from services.extract.profile import ExtractionProfile, build_schema
from services.laurium.schema_map import (
    UnsupportedSchema,
    descriptions_for,
    laurium_schema,
    output_for,
)

CONFORMANCE_SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
    "additionalProperties": False,
}


def _profile_schema() -> dict[str, Any]:
    ontology = load_default_ontology()
    names = [t.name for t in ontology.entity_types]
    return build_schema(ExtractionProfile(names), ontology)


def _model(schema: dict[str, Any]) -> type:
    fields = laurium_schema(schema)
    return create_model(  # type: ignore[call-overload,no-any-return]
        "Planted", **{name: (kind, ...) for name, kind in fields.items()}
    )


def test_the_conformance_schema_maps_to_one_string_field() -> None:
    assert laurium_schema(CONFORMANCE_SCHEMA) == {"name": str}


def test_every_profile_schema_maps_and_round_trips() -> None:
    schema = _profile_schema()
    fields = laurium_schema(schema)
    assert set(fields) == set(schema["properties"])
    for kind in fields.values():
        assert typing.get_origin(kind) is list
    model = _model(schema)
    # An instance the JSON Schema accepts: one finding of each type, every property filled.
    instance: dict[str, Any] = {}
    for name, prop in schema["properties"].items():
        item: dict[str, Any] = {}
        for key, sub in prop["items"]["properties"].items():
            item[key] = _sample(sub)
        instance[name] = [item]
    Draft202012Validator(schema).validate(instance)
    parsed = model.model_validate(instance)  # type: ignore[attr-defined]
    back = output_for(parsed, schema)
    Draft202012Validator(schema).validate(back)
    assert back == instance


def _sample(prop: dict[str, Any]) -> Any:
    if "enum" in prop:
        return prop["enum"][0]
    return {"string": "Ada", "integer": 3, "number": 0.9, "boolean": True}.get(
        prop["type"], ["Ada"]
    )


def test_an_enum_becomes_a_literal_that_refuses_another_value() -> None:
    schema = {
        "type": "object",
        "properties": {"colour": {"type": "string", "enum": ["red", "blue"]}},
        "required": ["colour"],
        "additionalProperties": False,
    }
    model = _model(schema)
    assert model.model_validate({"colour": "red"})  # type: ignore[attr-defined]
    with pytest.raises(ValidationError):
        model.model_validate({"colour": "green"})  # type: ignore[attr-defined]


def test_an_item_refuses_a_property_its_schema_does_not_declare() -> None:
    """The item is complete, every property filled, so the one fault is the invented one (rule 15:
    an item missing a required property would be refused for that instead)."""
    schema = _profile_schema()
    model = _model(schema)
    name, prop = next(iter(schema["properties"].items()))
    item = {key: _sample(sub) for key, sub in prop["items"]["properties"].items()}
    assert model.model_validate({**_empty(), name: [item]})  # type: ignore[attr-defined]
    with pytest.raises(ValidationError):
        model.model_validate({**_empty(), name: [{**item, "invented": "x"}]})  # type: ignore[attr-defined]


def _empty() -> dict[str, list[Any]]:
    return {name: [] for name in _profile_schema()["properties"]}


def test_an_optional_property_left_out_or_null_is_left_out_of_the_output() -> None:
    schema = {
        "type": "object",
        "properties": {
            "people": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "alias": {"type": "string"}},
                    "required": ["name"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["people"],
        "additionalProperties": False,
    }
    model = _model(schema)
    parsed = model.model_validate(  # type: ignore[attr-defined]
        {"people": [{"name": "Ada", "alias": None}, {"name": "Bea"}]}
    )
    back = output_for(parsed, schema)
    assert back == {"people": [{"name": "Ada"}, {"name": "Bea"}]}
    Draft202012Validator(schema).validate(back)


def test_a_required_property_left_out_is_refused() -> None:
    with pytest.raises(ValidationError):
        _model(CONFORMANCE_SCHEMA).model_validate({})  # type: ignore[attr-defined]


def _one(prop: dict[str, Any]) -> dict[str, Any]:
    """A schema whose one top-level property `a` is `prop`, required, so the top level is well
    formed and `prop` reaches its own refusal (rule 15's second clause: without `required` each was
    refused at the top level before its own check ran)."""
    return {
        "type": "object",
        "properties": {"a": prop},
        "required": ["a"],
        "additionalProperties": False,
    }


@pytest.mark.parametrize(
    ("schema", "words"),
    [
        ({"type": "array", "items": {"type": "string"}}, "top level must be an object"),
        (_one({"oneOf": [{"type": "string"}]}), "'a' uses oneOf"),
        (_one({"$ref": "#/$defs/x"}), r"'a' uses \$ref"),
        # A combinator beside a type: Laurium would be given the type alone.
        (_one({"type": "string", "oneOf": [{"maxLength": 3}]}), "'a' uses oneOf"),
        (_one({"type": ["string", "null"]}), "'a' has no single type"),
        (_one({"type": "object"}), "'a' is an object with no declared properties"),
        (_one({"type": "array"}), "'a' is an array with no declared items"),
        (_one({"type": "string", "enum": [1, 2]}), "'a': only an enum of strings"),
        (_one({"type": "integer", "enum": [1, 2]}), "'a': only an enum of strings"),
        (_one({"type": "string", "enum": []}), "'a': only an enum of strings"),
        ({"type": "object", "properties": {}}, "the schema is an object with no declared"),
        # Undeclared properties allowed in so many words; otherwise well formed. (Left unsaid, they
        # are not refused: Laurium's model forbids them in the answer, stricter than the schema.)
        (
            {**_one({"type": "string"}), "additionalProperties": True},
            "allows properties it does not declare",
        ),
        # A top-level property not required: Laurium makes every field required.
        (
            {"type": "object", "properties": {"a": {"type": "string"}}, "required": []},
            "every top-level property must be required",
        ),
    ],
)
def test_a_schema_outside_the_subset_is_refused_for_its_own_reason(
    schema: dict[str, Any], words: str
) -> None:
    """Each refusal is matched by its own words, so a case refused by another rule fails here."""
    Draft202012Validator.check_schema(schema)  # a valid JSON Schema: only the subset refuses it
    with pytest.raises(UnsupportedSchema, match=words):
        laurium_schema(schema)


# --- every entity type of the default ontology and of the fibo and niem packs ---------------------


def _ontologies() -> list[tuple[str, Any]]:
    from ontology.packs import compose_with_packs

    base = load_default_ontology()
    return [
        ("default", base),
        ("fibo", compose_with_packs(base, ["fibo"])),
        ("niem", compose_with_packs(base, ["niem"])),
    ]


def _every_type() -> list[tuple[str, str]]:
    return [(label, t.name) for label, onto in _ontologies() for t in onto.entity_types]


@pytest.mark.parametrize(("label", "name"), _every_type(), ids=lambda v: str(v))
def test_every_entity_type_maps_and_round_trips(label: str, name: str) -> None:
    """Not a sample: each entity type of the default ontology and of each pack, alone, as the
    extraction profile builds its schema, maps to Laurium's and a filled finding round-trips."""
    onto = dict(_ontologies())[label]
    schema = build_schema(ExtractionProfile([name]), onto)
    _round_trip(schema)


@pytest.mark.parametrize("label", ["default", "fibo", "niem"])
def test_every_entity_type_together_maps(label: str) -> None:
    onto = dict(_ontologies())[label]
    schema = build_schema(ExtractionProfile([t.name for t in onto.entity_types]), onto)
    assert set(laurium_schema(schema)) == {t.name for t in onto.entity_types}


def _round_trip(schema: dict[str, Any]) -> None:
    model = _model(schema)
    instance = {
        name: [{key: _sample(sub) for key, sub in prop["items"]["properties"].items()}]
        for name, prop in schema["properties"].items()
    }
    Draft202012Validator(schema).validate(instance)
    back = output_for(model.model_validate(instance), schema)  # type: ignore[attr-defined]
    Draft202012Validator(schema).validate(back)
    assert back == instance


def test_each_field_is_described_with_its_own_schema() -> None:
    """Laurium's prompt shows a nested type as `<list>`; the description carries the item's own
    JSON Schema, so the model is told the shape it must write."""
    schema = _profile_schema()
    descriptions = descriptions_for(schema)
    name = next(iter(schema["properties"]))
    assert '"confidence"' in descriptions[name]


def test_a_description_names_no_template_variable() -> None:
    """Laurium's prompt is a LangChain f-string template: a JSON Schema's braces left single would
    be read as variables, and every call would fail. Read as that template reads it."""
    import string

    for text in descriptions_for(_profile_schema()).values():
        assert [field for _, field, _, _ in string.Formatter().parse(text) if field] == []
