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
    names = [t.name for t in ontology.entity_types][:4]
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


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "array", "items": {"type": "string"}},
        {"type": "object", "properties": {"a": {"oneOf": [{"type": "string"}]}}},
        {"type": "object", "properties": {"a": {"$ref": "#/$defs/x"}}},
        {"type": "object", "properties": {"a": {"type": ["string", "null"]}}},
        {"type": "object", "properties": {"a": {"type": "object"}}},
        {"type": "object", "properties": {"a": {"type": "array"}}},
        {"type": "object", "properties": {"a": {"type": "string", "enum": [1, 2]}}},
        {"type": "object", "properties": {}},
        # Undeclared properties allowed in so many words; otherwise well formed. (Left unsaid, they
        # are not refused: Laurium's model forbids them in the answer, stricter than the schema.)
        {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "required": ["a"],
            "additionalProperties": True,
        },
        # A top-level property not required: Laurium makes every field required.
        {"type": "object", "properties": {"a": {"type": "string"}}, "required": []},
    ],
)
def test_a_schema_outside_the_subset_is_refused(schema: dict[str, Any]) -> None:
    with pytest.raises(UnsupportedSchema):
        laurium_schema(schema)


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
