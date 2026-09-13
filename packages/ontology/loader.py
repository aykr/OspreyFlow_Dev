"""The ontology loader — `docs/01_DOMAIN_MODEL.md` §1.

Validates a deployment's ontology YAML against the JSON Schema in
`schema/ontology.schema.json`, then enforces the business rules a schema
alone cannot express: the nine-channel constraint, the closed `pole_class`
vocabulary, and that `SAME_AS`/`NOT_SAME_AS` are system edge types injected
by the loader, never authored or overridden by a deployment (ADR-006).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from schemas.domain import (
    DATA_CHANNELS,
    SYSTEM_EDGE_TYPES,
    EdgeTypeDef,
    EntityTypeDef,
    OntologySchema,
)

from .errors import OntologyError

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "ontology.schema.json"
_DEFAULT_PATH = Path(__file__).resolve().parent / "default.yaml"

_SYSTEM_EDGE_DEFS: dict[str, EdgeTypeDef] = {
    name: EdgeTypeDef.model_validate(
        {"name": name, "from": ["*"], "to": ["*"], "directed": False, "system": True}
    )
    for name in SYSTEM_EDGE_TYPES
}


def _json_schema() -> dict[str, Any]:
    schema: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text())
    return schema


def load_ontology(path: str | Path) -> OntologySchema:
    """Load, structurally validate and business-rule-check one ontology file."""
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise OntologyError(f"{path}: ontology must be a YAML mapping")

    try:
        jsonschema.validate(raw, _json_schema())
    except jsonschema.ValidationError as exc:
        raise OntologyError(f"{path}: {exc.message}") from exc

    entity_types = [EntityTypeDef.model_validate(e) for e in raw["entity_types"]]
    edge_types = [EdgeTypeDef.model_validate(e) for e in raw.get("edge_types", [])]

    _check_entity_types(entity_types)
    edge_types = _inject_system_edge_types(edge_types)
    _check_edge_endpoints(entity_types, edge_types)

    return OntologySchema(version=raw["version"], entity_types=entity_types, edge_types=edge_types)


def load_default_ontology() -> OntologySchema:
    return load_ontology(_DEFAULT_PATH)


def _check_entity_types(entity_types: list[EntityTypeDef]) -> None:
    """The loader enforces exactly two rules on channel allocation
    (`01_DOMAIN_MODEL.md` §1.1): an unknown channel name is rejected, and no
    two entity types may share a channel *and* a shape. Sharing a hue alone
    is permitted — shape is always carried alongside it precisely so that
    hue never carries a distinction on its own, which is what makes a tenth
    entity type sharing a channel safe."""
    names = [e.name for e in entity_types]
    dup_names = sorted({n for n, c in Counter(names).items() if c > 1})
    if dup_names:
        raise OntologyError(f"duplicate entity type name(s): {', '.join(dup_names)}")

    channels = [e.channel for e in entity_types]
    unknown = sorted(set(channels) - set(DATA_CHANNELS))
    if unknown:
        raise OntologyError(
            f"unknown data channel(s): {', '.join(unknown)} — must be one of {DATA_CHANNELS}"
        )

    pairs = [(e.channel, e.shape) for e in entity_types]
    dup_pairs = sorted({p for p, n in Counter(pairs).items() if n > 1})
    if dup_pairs:
        rendered = ", ".join(f"{channel}+{shape}" for channel, shape in dup_pairs)
        raise OntologyError(
            "channel and shape combination(s) assigned to more than one entity type "
            f"(sharing a channel is fine; sharing channel and shape is not): {rendered}"
        )


def _inject_system_edge_types(edge_types: list[EdgeTypeDef]) -> list[EdgeTypeDef]:
    by_name = {e.name: e for e in edge_types}
    for name in SYSTEM_EDGE_TYPES:
        existing = by_name.get(name)
        if existing is not None and existing != _SYSTEM_EDGE_DEFS[name]:
            raise OntologyError(f"{name} is a system edge type (ADR-006) and may not be redefined")

    user_edges = [e for e in edge_types if e.name not in SYSTEM_EDGE_TYPES]
    return [*user_edges, *(_SYSTEM_EDGE_DEFS[name] for name in SYSTEM_EDGE_TYPES)]


def _check_edge_endpoints(
    entity_types: list[EntityTypeDef], edge_types: list[EdgeTypeDef]
) -> None:
    known = {e.name for e in entity_types}
    for edge in edge_types:
        if edge.system:
            continue
        for endpoint_types, label in ((edge.from_types, "from"), (edge.to_types, "to")):
            unknown = [t for t in endpoint_types if t != "*" and t not in known]
            if unknown:
                raise OntologyError(
                    f"edge type {edge.name!r} references unknown entity type(s) in "
                    f"{label!r}: {', '.join(unknown)}"
                )
