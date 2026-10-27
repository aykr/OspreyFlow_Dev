"""Conversions between the domain model and ArcadeDB's JSON records.

Every node/edge is written with `properties`, `provenance`, `handling`,
`resolution`/`interval` and `audit` stored verbatim as schemaless nested
maps (ArcadeDB types are not strict, so this needs no per-field DDL), plus a
handful of flattened, indexed top-level fields:

- `id`, `handling_classification`, `handling_code`, `owning_unit`,
  `originator` on everything — the access filter's two axes
  (`access_filter.py`, `01_DOMAIN_MODEL.md` §2.2) run on every read, and an
  unindexed filter there costs more than the query.
- `source`/`target` on edges, and `valid_from`/`valid_to` on temporal edges.
- every ontology `identifiers` entry, and every `properties` entry the
  ontology marks `indexed: true` — mirrored out of the `properties` map
  into its own top-level field, because an index on a key *inside* a
  schemaless map indexes the map, not the key (`schema.py`,
  `04_VAULT_BACKEND.md` §1.4).

Indexing a field that is never populated is worse than not indexing it —
`schema.py` and this module's flattening must stay in lockstep.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ontology.handling import withhold_sources
from schemas.domain import (
    AuditStub,
    Edge,
    EdgeTypeDef,
    EdgeWrite,
    EntityTypeDef,
    Handling,
    Interval,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ResolutionState,
    WeightComponents,
)

from .naming import logical_type_name


def _indexed_property_names(type_def: EntityTypeDef | EdgeTypeDef) -> set[str]:
    identifiers = set(type_def.identifiers) if isinstance(type_def, EntityTypeDef) else set()
    indexed_properties = {p.name for p in type_def.properties if p.indexed}
    return identifiers | indexed_properties


def _refuse_withheld(provenance: Provenance) -> None:
    """ADR-130 Amendment 2: provenance with its sources withheld is what a scoped reader is sent,
    never what is stored. Writing it back would replace the stored sources with none."""
    if provenance.sources_withheld:
        raise ValueError(
            "provenance with its sources withheld cannot be written: it was read for a reader "
            "whose case does not read all of the element's datasets"
        )


def node_write_to_properties(
    write: NodeWrite, *, node_id: str, audit: AuditStub, entity_type: EntityTypeDef
) -> dict[str, Any]:
    _refuse_withheld(write.provenance)
    flattened: dict[str, Any] = {
        name: write.properties[name]
        for name in _indexed_property_names(entity_type)
        if name in write.properties
    }
    props: dict[str, Any] = {
        "id": node_id,
        "handling_classification": write.handling.classification,
        "handling_code": write.handling.handling_code,
        "owning_unit": write.handling.owning_unit,
        "originator": write.handling.originator,
        "reverted": audit.reverted,
        # ADR-099: top-level, beside the handling fields, for the access step to read.
        "datasets": sorted(set(write.datasets)),
        **flattened,
        "properties": write.properties,
        "provenance": write.provenance.model_dump(mode="json"),
        "handling": write.handling.model_dump(mode="json"),
        "resolution": write.resolution.model_dump(mode="json"),
        "audit": audit.model_dump(mode="json"),
    }
    # Sparse, unlike `reverted`: most nodes are never superseded, so the
    # property is only present at all once `supersede_node` sets it on an
    # outgoing revision — `hasNot("superseded_by")` is what the access
    # filter checks for "this is the current revision" (`access_filter.py`).
    if audit.superseded_by is not None:
        props["superseded_by"] = audit.superseded_by
    return props


def edge_write_to_properties(
    write: EdgeWrite,
    *,
    edge_id: str,
    audit: AuditStub,
    edge_type: EdgeTypeDef,
    weight: float,
    weight_components: WeightComponents,
) -> dict[str, Any]:
    _refuse_withheld(write.provenance)
    flattened: dict[str, Any] = {
        name: write.properties[name]
        for name in _indexed_property_names(edge_type)
        if name in write.properties
    }
    props: dict[str, Any] = {
        "id": edge_id,
        "source": write.source,
        "target": write.target,
        "handling_classification": write.handling.classification,
        "handling_code": write.handling.handling_code,
        "owning_unit": write.handling.owning_unit,
        "originator": write.handling.originator,
        "reverted": audit.reverted,
        "datasets": sorted(set(write.datasets)),
        **flattened,
        "properties": write.properties,
        "occurrences": write.occurrences,
        "weight": weight,
        "weight_components": weight_components.model_dump(mode="json"),
        "provenance": write.provenance.model_dump(mode="json"),
        "handling": write.handling.model_dump(mode="json"),
        "audit": audit.model_dump(mode="json"),
    }
    # ADR-081 step B: a link's own basis is stored only where one was written, so a link that
    # takes its type's basis (every loader's and the resolution engine's) carries no property.
    if write.basis is not None:
        props["basis"] = write.basis
    if write.interval is not None:
        props["interval"] = write.interval.model_dump(mode="json")
        # Flattened as epoch milliseconds, not an ISO string: ArcadeDB's
        # DATETIME parser expects its own `yyyy-MM-dd HH:mm:ss` format, and
        # a `gte`/`lte` predicate against a DATETIME property needs an
        # actual `Date`, not a String, to compare correctly — see
        # `builders.py`'s `_temporal_filter` and `adapter.py`'s
        # `upsert_edges`, which both wrap this value in `new Date(millis)`.
        props["valid_from"] = int(write.interval.valid_from.timestamp() * 1000)
        if write.interval.valid_to is not None:
            props["valid_to"] = int(write.interval.valid_to.timestamp() * 1000)
    return props


def node_from_element_map(record: Mapping[str, Any], principal: Principal | None = None) -> Node:
    """The stored record as a `Node`. Given the reading `principal`, a node whose datasets the
    principal's case does not wholly read comes back with its sources withheld (ADR-130
    Amendment 2). No principal is a system read of the whole record: the Conduit's own scripts."""
    # `supersede_node` updates the top-level flattened `superseded_by`
    # directly, on the *old* revision, without rewriting its nested
    # `audit` blob — so the flattened field, when present, is the
    # authoritative value, not whatever the nested blob still says.
    audit_data: dict[str, Any] = dict(record["audit"])
    if "superseded_by" in record:
        audit_data["superseded_by"] = record["superseded_by"]
    node = Node(
        id=record["id"],
        type=logical_type_name(record["label"]),
        properties=record.get("properties") or {},
        provenance=Provenance.model_validate(record["provenance"]),
        handling=Handling.model_validate(record["handling"]),
        resolution=ResolutionState.model_validate(record.get("resolution") or {}),
        audit=AuditStub.model_validate(audit_data),
        datasets=list(record.get("datasets") or []),
    )
    return node if principal is None else withhold_sources(node, principal)


def edge_from_element_map(record: Mapping[str, Any], principal: Principal | None = None) -> Edge:
    """As `node_from_element_map`, for a link."""
    interval = None
    if record.get("interval"):
        interval = Interval.model_validate(record["interval"])
    weight_components = None
    if record.get("weight_components"):
        weight_components = WeightComponents.model_validate(record["weight_components"])
    edge = Edge(
        id=record["id"],
        type=logical_type_name(record["label"]),
        source=record["source"],
        target=record["target"],
        properties=record.get("properties") or {},
        interval=interval,
        occurrences=record.get("occurrences", 1),
        weight=record.get("weight", 0.0),
        weight_components=weight_components,
        basis=record.get("basis"),
        provenance=Provenance.model_validate(record["provenance"]),
        handling=Handling.model_validate(record["handling"]),
        audit=AuditStub.model_validate(record["audit"]),
        datasets=list(record.get("datasets") or []),
    )
    return edge if principal is None else withhold_sources(edge, principal)
