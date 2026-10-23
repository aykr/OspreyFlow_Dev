"""ADR-120: a link stored before the weights file has components with no `parameter_set` key
(`01_DOMAIN_MODEL.md` §6.1: "a component with none was computed under the uncalibrated curve that
preceded ADR-120"). Weights stored then are not recomputed, so they must keep reading back.

Catches a `WeightComponents.parameter_set` that is required, or a reader that fails on an old
row; and a new row that loses its parameter set on the way through `serialization.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from adapters.graph_arcadedb.naming import physical_type_name
from adapters.graph_arcadedb.serialization import edge_from_element_map, edge_write_to_properties
from ontology.loader import load_default_ontology
from schemas.domain import (
    AuditStub,
    EdgeWrite,
    Handling,
    Provenance,
    ProvenanceState,
    SourceRef,
    WeightComponents,
)

NOW = datetime(2026, 10, 23, tzinfo=UTC)


def _write() -> EdgeWrite:
    return EdgeWrite(
        id="e1",
        type="ASSOCIATE_OF",
        source="a",
        target="b",
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
            first_seen=NOW,
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
        created_by="analyst-1",
        created_at=NOW,
    )


def _record(components: dict[str, Any] | WeightComponents) -> dict[str, Any]:
    """A stored edge record, built by the real serialiser, with its components as given."""
    edge_type = load_default_ontology().edge_type("ASSOCIATE_OF")
    assert edge_type is not None
    stored = (
        components
        if isinstance(components, WeightComponents)
        else WeightComponents(
            occurrences=1,
            corpus_pair_count=1,
            corpus_source_degree=1,
            corpus_target_degree=1,
            corpus_total_occurrences=1,
            computed_at=NOW,
        )
    )
    props = edge_write_to_properties(
        _write(),
        edge_id="e1",
        audit=AuditStub(created_at=NOW, created_by="analyst-1"),
        edge_type=edge_type,
        weight=0.5,
        weight_components=stored,
    )
    if isinstance(components, dict):
        props["weight_components"] = components
    return {**props, "label": physical_type_name("ASSOCIATE_OF")}


def test_a_row_stored_without_a_parameter_set_reads_back_with_none() -> None:
    old_row = {
        "occurrences": 4,
        "corpus_pair_count": 4,
        "corpus_source_degree": 9,
        "corpus_target_degree": 6,
        "corpus_total_occurrences": 40,
        "computed_at": "2026-01-02T03:04:05Z",
    }
    assert "parameter_set" not in old_row
    edge = edge_from_element_map(_record(old_row))
    assert edge.weight_components is not None
    assert edge.weight_components.parameter_set is None
    assert edge.weight_components.corpus_source_degree == 9
    assert edge.weight == 0.5


def test_a_parameter_set_survives_the_trip_through_the_store() -> None:
    components = WeightComponents(
        occurrences=1,
        corpus_pair_count=1,
        corpus_source_degree=1,
        corpus_target_degree=1,
        corpus_total_occurrences=1,
        computed_at=NOW,
        parameter_set="1/COMMUNICATED_WITH",
    )
    edge = edge_from_element_map(_record(components))
    assert edge.weight_components is not None
    assert edge.weight_components.parameter_set == "1/COMMUNICATED_WITH"
