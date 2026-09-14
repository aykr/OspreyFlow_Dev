"""Validate a write against the ontology's own declarations —
`01_DOMAIN_MODEL.md` §2: "properties: dict[str, Any]  # validated against
the ontology's property definitions." An adapter that accepts whatever a
caller sends leaves a graph an ingest bug can fill with garbage silently;
this is the check that makes that impossible regardless of which adapter
enforces it.

Two checks, both raising `OntologyError`:
- `validate_properties` — every `required` property present, every present
  property's value shaped like its declared `type`, and no property key
  that isn't either declared in `properties` or listed in `identifiers`
  (entity types only; edge types have no `identifiers`).
- `validate_edge_endpoints` — the source and target's actual entity types
  are each a member of the edge type's declared `from`/`to` list, or that
  list is the wildcard `["*"]`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from schemas.domain import EdgeTypeDef, EntityTypeDef, PropertyDef, PropertyType

from .errors import OntologyError


def validate_properties(
    type_def: EntityTypeDef | EdgeTypeDef, properties: dict[str, Any]
) -> None:
    declared = {p.name: p for p in type_def.properties}
    identifiers = set(type_def.identifiers) if isinstance(type_def, EntityTypeDef) else set()
    known_keys = set(declared) | identifiers

    unknown = sorted(set(properties) - known_keys)
    if unknown:
        raise OntologyError(
            f"{type_def.name!r} does not declare propert{'y' if len(unknown) == 1 else 'ies'} "
            f"{', '.join(unknown)!r} in its `properties` or `identifiers`"
        )

    missing_required = sorted(
        p.name for p in type_def.properties if p.required and p.name not in properties
    )
    if missing_required:
        raise OntologyError(
            f"{type_def.name!r} requires propert{'y' if len(missing_required) == 1 else 'ies'} "
            f"{', '.join(missing_required)!r}"
        )

    for name, value in properties.items():
        prop = declared.get(name)
        if prop is None:
            continue  # an identifier-only key: opaque, no declared type to check against
        if not _matches_type(prop, value):
            raise OntologyError(
                f"{type_def.name!r}.{name} = {value!r} does not match declared type "
                f"{prop.type.value!r}"
            )


def _matches_type(prop: PropertyDef, value: Any) -> bool:
    match prop.type:
        case PropertyType.STRING:
            return isinstance(value, str)
        case PropertyType.STRING_LIST:
            return isinstance(value, list) and all(isinstance(v, str) for v in value)
        case PropertyType.DATE:
            return isinstance(value, date) or _parses_as(date.fromisoformat, value)
        case PropertyType.DATETIME:
            return isinstance(value, datetime) or _parses_as(datetime.fromisoformat, value)
        case PropertyType.INTEGER:
            if isinstance(value, bool):
                return False
            return isinstance(value, int) or _parses_as(int, value)
        case PropertyType.FLOAT:
            if isinstance(value, bool):
                return False
            return isinstance(value, int | float) or _parses_as(float, value)
        case PropertyType.BOOLEAN:
            return isinstance(value, bool)
        case PropertyType.ENUM:
            return isinstance(value, str) and value in (prop.values or [])
    return False  # pragma: no cover — exhaustive over PropertyType


def _parses_as(parser: Any, value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parser(value)
    except ValueError:
        return False
    return True


def validate_edge_endpoints(
    edge_type: EdgeTypeDef, *, source_type: str, target_type: str
) -> None:
    for endpoint_type, declared, label in (
        (source_type, edge_type.from_types, "from"),
        (target_type, edge_type.to_types, "to"),
    ):
        if declared != ["*"] and endpoint_type not in declared:
            raise OntologyError(
                f"edge type {edge_type.name!r} does not permit {label}={endpoint_type!r} "
                f"— declared {label}: {declared}"
            )
