"""Shared by the tests that hold ADR-122's rule: no response carries a link's corpus-wide counts.

The five keys, an `Edge` that has components, a walk for keys at any depth, and a builder of an
instance of any response model holding that `Edge` wherever the model can hold one. Not a test
file: it holds no `test_` function.
"""

from __future__ import annotations

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
