"""ADR-081 step B: a link's own basis travels to ArcadeDB and back exactly, and a link written
without one carries none (it takes its type's basis when drawn). `serialization.py` is the one
place an `EdgeWrite` becomes stored properties and a stored record becomes an `Edge`, so a field
dropped there is dropped for every write path (`upsert_edges`, the bulk loader, `supersede_edge`,
and the clone `supersede_node` makes)."""

from __future__ import annotations

from datetime import UTC, datetime

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

NOW = datetime(2026, 10, 4, tzinfo=UTC)


def _write(basis: str | None) -> EdgeWrite:
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
        basis=basis,  # type: ignore[arg-type]
    )


def _properties(write: EdgeWrite) -> dict:  # type: ignore[type-arg]
    edge_type = load_default_ontology().edge_type("ASSOCIATE_OF")
    assert edge_type is not None
    return edge_write_to_properties(
        write,
        edge_id=write.id,
        audit=AuditStub(created_at=NOW, created_by="analyst-1"),
        edge_type=edge_type,
        weight=0.5,
        weight_components=WeightComponents(
            occurrences=1,
            corpus_pair_count=1,
            corpus_source_degree=1,
            corpus_target_degree=1,
            corpus_total_occurrences=1,
            computed_at=NOW,
        ),
    )


def _record(props: dict) -> dict:  # type: ignore[type-arg]
    return {**props, "label": physical_type_name("ASSOCIATE_OF")}


def test_a_probabilistic_mark_is_stored_and_read_back() -> None:
    props = _properties(_write("probabilistic"))
    assert props["basis"] == "probabilistic"
    assert edge_from_element_map(_record(props)).basis == "probabilistic"


def test_a_link_written_without_a_basis_stores_none_and_reads_none() -> None:
    props = _properties(_write(None))
    assert "basis" not in props
    assert edge_from_element_map(_record(props)).basis is None


def test_a_record_from_before_step_b_reads_as_no_basis() -> None:
    # Links written before this field existed have no `basis` property at all.
    props = _properties(_write(None))
    props.pop("basis", None)
    assert edge_from_element_map(_record(props)).basis is None
