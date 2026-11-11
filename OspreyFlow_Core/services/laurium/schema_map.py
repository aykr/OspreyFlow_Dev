"""The domain model mapped to Laurium's schema, and Laurium's output back to the request's shape
(`06_DECISIONS.md` ADR-135 Amendment 6 decision 6).

`ExtractionRequest.json_schema` is a JSON Schema: the extraction profile's (one array of findings
per entity type, `services/extract/profile.build_schema`) or any caller's. Laurium takes a schema as
`{field: type}` (its `make_dynamic_example_model` and `create_prompt`), so this maps the JSON Schema
to Pydantic types: an object's declared properties (a nested model that forbids any other), arrays,
string enums as `Literal`, strings, integers, numbers and booleans. A shape outside that subset
(`oneOf`, `anyOf`, `allOf`, `not` or `$ref`, alone or beside a type; a list of types; an object or
array with no declared shape) is `UnsupportedSchema`, refused before any model call. A constraint
on a value within a type (`minLength`, `pattern`, `format`, bounds, `minItems`) is not given to
Laurium's model: Laurium's types cannot carry it. Nothing is trusted on that account, since the
adapter checks every answer against the request's whole schema before anything reads it
(`adapters/extract_laurium`).

**Every top-level property must be required**, as Laurium's own model makes every field required;
within an item, a property the schema does not require may be left out, and is left out of the
output too, never written as `null` where the schema says a string.

Pydantic and the standard library only, so the Conduit's test run reads this module as the image
does (`tests/services/laurium/test_schema_map.py`).
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, create_model

_SCALARS: dict[str, type] = {"string": str, "integer": int, "number": float, "boolean": bool}


class UnsupportedSchema(Exception):
    """The request's schema is a valid JSON Schema, but not one Laurium can be given."""


def laurium_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """`{field: type}` for Laurium, from the request's JSON Schema."""
    if schema.get("type") != "object":
        raise UnsupportedSchema("the schema's top level must be an object")
    properties = _properties(schema, "the schema")
    required = set(schema.get("required") or [])
    missing = [name for name in properties if name not in required]
    if missing:
        raise UnsupportedSchema(
            "every top-level property must be required, as Laurium makes every field required: "
            + ", ".join(sorted(missing))
        )
    return {name: _type(prop, name) for name, prop in properties.items()}


def descriptions_for(schema: dict[str, Any]) -> dict[str, str]:
    """Each top-level field's description for Laurium's prompt: its own `description`, if any, and
    its JSON Schema, since Laurium shows a nested type only as `<list>`. Braces are doubled, as
    Laurium's own schema text doubles them, because the prompt is a LangChain template."""
    out: dict[str, str] = {}
    for name, prop in (schema.get("properties") or {}).items():
        text = str(prop.get("description") or "").strip()
        shape = json.dumps(prop, sort_keys=True)
        words = f"{text} Each value must match this JSON Schema: {shape}".strip()
        out[name] = words.replace("{", "{{").replace("}", "}}")
    return out


def output_for(parsed: BaseModel, schema: dict[str, Any]) -> dict[str, Any]:
    """Laurium's parsed answer as the request's shape: a property the schema does not require and
    the model left out, or wrote as null, is left out."""
    data: dict[str, Any] = parsed.model_dump(mode="json")
    cleaned = _clean(data, schema)
    assert isinstance(cleaned, dict)
    return cleaned


def _properties(schema: dict[str, Any], where: str) -> dict[str, Any]:
    properties = schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        raise UnsupportedSchema(f"{where} is an object with no declared properties")
    if schema.get("additionalProperties", False) is not False:
        raise UnsupportedSchema(f"{where} allows properties it does not declare")
    return properties


def _type(prop: Any, name: str) -> Any:
    if not isinstance(prop, dict):
        raise UnsupportedSchema(f"{name!r} is not a schema")
    combined = sorted({"oneOf", "anyOf", "allOf", "not", "$ref"} & set(prop))
    if combined:
        raise UnsupportedSchema(f"{name!r} uses {', '.join(combined)}, which Laurium is not given")
    kind = prop.get("type")
    if not isinstance(kind, str):
        raise UnsupportedSchema(
            f"{name!r} has no single type (oneOf, anyOf, $ref and type lists are not supported)"
        )
    if "enum" in prop:
        values = prop["enum"]
        if kind != "string" or not values or not all(isinstance(v, str) for v in values):
            raise UnsupportedSchema(f"{name!r}: only an enum of strings is supported")
        return Literal[tuple(values)]
    if kind in _SCALARS:
        return _SCALARS[kind]
    if kind == "array":
        items = prop.get("items")
        if items is None:
            raise UnsupportedSchema(f"{name!r} is an array with no declared items")
        return list[_type(items, f"{name}[]")]  # type: ignore[misc]
    if kind == "object":
        properties = _properties(prop, repr(name))
        required = set(prop.get("required") or [])
        fields: dict[str, Any] = {}
        for key, sub in properties.items():
            inner = _type(sub, f"{name}.{key}")
            fields[key] = (inner, ...) if key in required else (inner | None, None)
        return create_model(
            _model_name(name), __config__=ConfigDict(extra="forbid"), **fields
        )
    raise UnsupportedSchema(f"{name!r} has a type Laurium is not given: {kind!r}")


def _model_name(name: str) -> str:
    cleaned = "".join(c if c.isalnum() else "_" for c in name)
    return f"Item_{cleaned}"


def _clean(value: Any, schema: dict[str, Any]) -> Any:
    kind = schema.get("type")
    if kind == "object" and isinstance(value, dict):
        required = set(schema.get("required") or [])
        properties = schema.get("properties") or {}
        return {
            key: _clean(item, properties.get(key, {}))
            for key, item in value.items()
            if not (item is None and key not in required)
        }
    if kind == "array" and isinstance(value, list):
        return [_clean(item, schema.get("items") or {}) for item in value]
    return value
