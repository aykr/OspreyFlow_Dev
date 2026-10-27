"""ADR-130 Amendment 2: `node_from_element_map` and `edge_from_element_map` are the one place every
read path turns a stored record into an element, so they are where a reader's scope is applied to
its sources. Hermetic: element maps are plain dicts. The adapter's own read paths are held by
`test_sources_withheld_live.py`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from adapters.graph_arcadedb.naming import physical_type_name
from adapters.graph_arcadedb.serialization import (
    edge_from_element_map,
    node_from_element_map,
    node_write_to_properties,
)
from ontology.loader import load_default_ontology
from schemas.domain import (
    AuditStub,
    Handling,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)

_PROVENANCE = {
    "state": "asserted",
    "sources": [{"document_id": "files/calls.csv", "locator": "row 2", "excerpt_hash": "c" * 64}],
    "first_seen": "2026-01-01T00:00:00Z",
}
_HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "unit-1",
    "owning_unit": "unit-1",
}
_AUDIT = {"created_at": "2026-01-01T00:00:00Z", "created_by": "analyst-1"}


def _node_record(datasets: list[str]) -> dict:  # type: ignore[type-arg]
    return {
        "id": "n1",
        "label": physical_type_name("Person"),
        "properties": {},
        "provenance": _PROVENANCE,
        "handling": _HANDLING,
        "audit": _AUDIT,
        "datasets": datasets,
    }


def _edge_record(datasets: list[str]) -> dict:  # type: ignore[type-arg]
    return {
        "id": "e1",
        "label": physical_type_name("ASSOCIATE_OF"),
        "source": "n1",
        "target": "n2",
        "provenance": _PROVENANCE,
        "handling": _HANDLING,
        "audit": _AUDIT,
        "datasets": datasets,
    }


def _reader(datasets: list[str] | None) -> Principal:
    return Principal(id="p-1", clearance="OFFICIAL", org_unit="unit-1", datasets=datasets)


def test_a_node_in_two_datasets_read_by_a_case_of_one_has_no_sources() -> None:
    node = node_from_element_map(_node_record(["Z1001ZZ", "Z1002ZZ"]), _reader(["Z1001ZZ"]))
    assert node.provenance.sources == []
    assert node.provenance.sources_withheld is True


def test_a_node_in_two_datasets_read_by_a_case_of_both_names_its_sources() -> None:
    node = node_from_element_map(
        _node_record(["Z1001ZZ", "Z1002ZZ"]), _reader(["Z1001ZZ", "Z1002ZZ"])
    )
    assert [s.document_id for s in node.provenance.sources] == ["files/calls.csv"]
    assert node.provenance.sources_withheld is False


def test_a_link_in_two_datasets_read_by_a_case_of_one_has_no_sources() -> None:
    edge = edge_from_element_map(_edge_record(["Z1001ZZ", "Z1002ZZ"]), _reader(["Z1002ZZ"]))
    assert edge.provenance.sources == []
    assert edge.provenance.sources_withheld is True


def test_a_read_with_no_principal_is_a_system_read_and_keeps_every_source() -> None:
    node = node_from_element_map(_node_record(["Z1001ZZ", "Z1002ZZ"]))
    edge = edge_from_element_map(_edge_record(["Z1001ZZ", "Z1002ZZ"]))
    assert len(node.provenance.sources) == 1
    assert len(edge.provenance.sources) == 1


def test_the_unlimited_principal_keeps_every_source() -> None:
    node = node_from_element_map(_node_record(["Z1001ZZ", "Z1002ZZ"]), _reader(None))
    assert len(node.provenance.sources) == 1


def test_a_write_carrying_withheld_provenance_is_refused_not_stored() -> None:
    """A service that read a node as a scoped reader and writes its provenance back would replace
    the stored sources with none. The store refuses it, loudly, rather than lose them."""
    entity_type = load_default_ontology().entity_type("Person")
    assert entity_type is not None
    write = NodeWrite(
        id="n1",
        type="Person",
        provenance=Provenance(
            state=ProvenanceState.ASSERTED, sources=[], sources_withheld=True, first_seen=_WHEN
        ),
        handling=Handling.model_validate(_HANDLING),
        created_by="analyst-1",
        created_at=_WHEN,
        datasets=["Z1001ZZ"],
    )
    with pytest.raises(ValueError, match="withheld"):
        node_write_to_properties(
            write,
            node_id="n1",
            audit=AuditStub(created_at=_WHEN, created_by="analyst-1"),
            entity_type=entity_type,
        )
