"""Shared by the tests that hold ADR-122's rule (no response carries a link's corpus-wide counts)
and ADR-124's (no response carries a figure for what the reader may not read).

The five keys, an `Edge` that has components, a walk for keys at any depth, and a builder of an
instance of any response model holding that `Edge` wherever the model can hold one; and, for
ADR-124, the withheld-figure keys and a walk over every field name a model can put on the wire,
whether or not it holds an `Edge`. Not a test file: it holds no `test_` function.
"""

from __future__ import annotations

import dataclasses
import enum
import types
import typing
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from schemas.domain import (
    AuditStub,
    Edge,
    Handling,
    Interval,
    Provenance,
    ProvenanceState,
    SourceRef,
    WeightComponents,
)

FORBIDDEN_KEYS = {
    "weight_components",
    "corpus_source_degree",
    "corpus_target_degree",
    "corpus_pair_count",
    "corpus_total_occurrences",
}

#: ADR-124 decision 1: a figure for withheld material is removed, not held at 0. `withheld_count`
#: is in the set with no exemption: the export manifest and the export ledger carried it until
#: U9 replaced it with a yes or no.
WITHHELD_KEYS = {"filtered_count", "unreadable_count", "withheld_count"}

#: ADR-124 decision 8: a step of the case's history carries no size. The listing's own counts were
#: taken over the stored, unfiltered snapshot, so they were a figure for material the reader may
#: not read. No route's response, at any depth, can carry either name.
SIZE_KEYS = {"node_count", "edge_count"}

WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def edge_with_components() -> Edge:
    return Edge(
        id="e-1",
        type="COMMUNICATED_WITH",
        source="n-1",
        target="n-2",
        interval=Interval(valid_from=WHEN),
        occurrences=3,
        weight=0.4,
        weight_components=WeightComponents(
            occurrences=3,
            corpus_pair_count=3,
            corpus_source_degree=11,
            corpus_target_degree=12,
            corpus_total_occurrences=999,
            parameter_set="v1/default",
            computed_at=WHEN,
        ),
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
            first_seen=WHEN,
        ),
        handling=Handling(
            classification="SECRET", handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
        audit=AuditStub(created_at=WHEN, created_by="loader-1"),
    )


def contains_model(annotation: Any, target: type[BaseModel], seen: set[type]) -> bool:
    """Whether `target` is reachable from `annotation` through model fields and generics."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation is target:
            return True
        if annotation in seen:
            return False
        seen.add(annotation)
        return any(
            contains_model(f.annotation, target, seen) for f in annotation.model_fields.values()
        )
    return any(contains_model(a, target, seen) for a in typing.get_args(annotation))


def build(annotation: Any, edge: Edge, depth: int = 0) -> Any:
    """An instance of `annotation` with every collection holding one element, every optional
    filled, and every `Edge` the one given. Models are constructed, not validated, so a
    constraint on an unrelated field cannot stop the build."""
    if depth > 12:
        return None
    if annotation is Edge:
        return edge
    supertype = getattr(annotation, "__supertype__", None)
    if supertype is not None:
        return build(supertype, edge, depth + 1)
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is typing.Annotated:
        return build(args[0], edge, depth + 1)
    if origin is typing.Literal:
        return args[0]
    if origin in (typing.Union, types.UnionType):
        options = [a for a in args if a is not type(None)]
        return build(options[0], edge, depth + 1) if options else None
    if origin in (list, set, frozenset, tuple):
        inner = build(args[0], edge, depth + 1) if args else None
        return [inner] if origin is list else origin([inner]) if origin is not tuple else (inner,)
    if origin is dict:
        return {"k": build(args[1], edge, depth + 1)} if len(args) == 2 else {}
    if isinstance(annotation, type):
        if issubclass(annotation, BaseModel):
            values = {
                name: build(field.annotation, edge, depth + 1)
                for name, field in annotation.model_fields.items()
            }
            return annotation.model_construct(**values)
        if issubclass(annotation, enum.Enum):
            return next(iter(annotation))
        if annotation is bool:
            return False
        if annotation is int:
            return 1
        if annotation is float:
            return 1.0
        if annotation is str:
            return "x"
        if annotation is datetime:
            return WHEN
    return None


def keys_at_any_depth(value: Any) -> set[str]:
    if isinstance(value, dict):
        found = set(value)
        for inner in value.values():
            found |= keys_at_any_depth(inner)
        return found
    if isinstance(value, list):
        found = set()
        for inner in value:
            found |= keys_at_any_depth(inner)
        return found
    return set()


def field_names_reachable(annotation: Any, seen: set[type] | None = None) -> set[str]:
    """Every field name a value of `annotation` can carry on the wire: the fields of each model or
    dataclass reachable through fields and generics, their aliases and their computed fields. A
    walk over the declared shape, not over an instance, so it needs no value to be buildable and
    sees a field whatever its default; what it cannot see is a key put into a model typed
    `dict[str, Any]` at run time (the limit `test_no_corpus_counts_on_the_wire.py` states)."""
    seen = set() if seen is None else seen
    names: set[str] = set()
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in seen:
            return names
        seen.add(annotation)
        for name, field in annotation.model_fields.items():
            names |= {name, *(a for a in (field.alias, field.serialization_alias) if a)}
            names |= field_names_reachable(field.annotation, seen)
        for name, computed in annotation.model_computed_fields.items():
            names.add(name)
            names |= field_names_reachable(computed.return_type, seen)
        return names
    if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
        if annotation in seen:
            return names
        seen.add(annotation)
        hints = typing.get_type_hints(annotation)
        for field in dataclasses.fields(annotation):
            names.add(field.name)
            names |= field_names_reachable(hints.get(field.name), seen)
        return names
    for inner in typing.get_args(annotation):
        names |= field_names_reachable(inner, seen)
    return names


def models_with_field(annotation: Any, field: str, seen: set[type] | None = None) -> set[str]:
    """The names of the models and dataclasses reachable from `annotation` that declare `field`
    (or an alias of it): which of them carries it, where `field_names_reachable` says only that
    something does."""
    seen = set() if seen is None else seen
    found: set[str] = set()
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in seen:
            return found
        seen.add(annotation)
        for name, model_field in annotation.model_fields.items():
            if field in {name, model_field.alias, model_field.serialization_alias}:
                found.add(annotation.__name__)
            found |= models_with_field(model_field.annotation, field, seen)
        if field in annotation.model_computed_fields:
            found.add(annotation.__name__)
        return found
    if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
        if annotation in seen:
            return found
        seen.add(annotation)
        hints = typing.get_type_hints(annotation)
        for dc_field in dataclasses.fields(annotation):
            if dc_field.name == field:
                found.add(annotation.__name__)
            found |= models_with_field(hints.get(dc_field.name), field, seen)
        return found
    for inner in typing.get_args(annotation):
        found |= models_with_field(inner, field, seen)
    return found


def field_annotations(annotation: Any, field: str, seen: set[type] | None = None) -> list[Any]:
    """The declared type of `field` on every model reachable from `annotation` that declares it: what
    a gate needs to pin a name's type where the name itself is allowed."""
    seen = set() if seen is None else seen
    found: list[Any] = []
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in seen:
            return found
        seen.add(annotation)
        for name, model_field in annotation.model_fields.items():
            if name == field:
                found.append(model_field.annotation)
            found += field_annotations(model_field.annotation, field, seen)
        return found
    for inner in typing.get_args(annotation):
        found += field_annotations(inner, field, seen)
    return found
