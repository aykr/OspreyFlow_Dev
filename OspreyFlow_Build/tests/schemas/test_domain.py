"""The real domain model — `spec/01_DOMAIN_MODEL.md` §2-4."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from schemas.domain import (
    AuditStub,
    Edge,
    Handling,
    Node,
    Provenance,
    ProvenanceState,
    ResolutionState,
    SourceRef,
)


def _source() -> SourceRef:
    return SourceRef(document_id="doc-1", locator="p.7", excerpt_hash="a" * 64)


def _handling(**overrides: object) -> Handling:
    base: dict[str, object] = {
        "classification": "OFFICIAL",
        "handling_code": "P",
        "originator": "org-1",
        "owning_unit": "org-1",
    }
    base.update(overrides)
    return Handling.model_validate(base)


def _audit() -> AuditStub:
    return AuditStub(created_at=datetime.now(UTC), created_by="analyst-1")


def test_provenance_sources_must_not_be_empty() -> None:
    with pytest.raises(ValidationError):
        Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[],
            first_seen=datetime.now(UTC),
        )


def test_asserted_provenance_rejects_a_confidence_score() -> None:
    """`extraction_confidence` is 'null for asserted' — `01_DOMAIN_MODEL.md` §2.1."""
    with pytest.raises(ValidationError):
        Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[_source()],
            extraction_confidence=0.9,
            first_seen=datetime.now(UTC),
        )


def test_inferred_provenance_may_carry_a_confidence_score() -> None:
    prov = Provenance(
        state=ProvenanceState.INFERRED,
        sources=[_source()],
        extracted_by="model:qwen2-vl:7b@2026-05-02",
        extraction_confidence=0.82,
        first_seen=datetime.now(UTC),
    )
    assert prov.state is ProvenanceState.INFERRED
    assert prov.confirmed_by is None


def test_confirming_an_inferred_node_flips_state_and_records_who() -> None:
    """No automatic promotion, no confidence threshold — an explicit analyst
    action is the only thing that flips `inferred` to `asserted`
    (`01_DOMAIN_MODEL.md` §2.1)."""
    prov = Provenance(
        state=ProvenanceState.INFERRED,
        sources=[_source()],
        extracted_by="model:qwen2-vl:7b@2026-05-02",
        extraction_confidence=0.97,
        first_seen=datetime.now(UTC),
    )
    confirmed = prov.model_copy(
        update={
            "state": ProvenanceState.ASSERTED,
            "extraction_confidence": None,
            "confirmed_by": "analyst-1",
            "last_confirmed": datetime.now(UTC),
        }
    )
    assert confirmed.state is ProvenanceState.ASSERTED
    assert confirmed.confirmed_by == "analyst-1"


def test_resolution_state_has_no_merge_concept() -> None:
    """ADR-006: resolution is a query-time projection, never a merge. There
    is no field on `ResolutionState` or `Node` that combines two records —
    only scored links and analyst-asserted splits."""
    fields = set(ResolutionState.model_fields)
    assert fields == {
        "cluster_id",
        "cluster_score",
        "resolution_run",
        "manually_linked",
        "manually_split",
    }
    assert not hasattr(ResolutionState, "merge")
    assert not hasattr(Node, "merge")


def test_manual_split_and_manual_link_are_independent_lists() -> None:
    state = ResolutionState(manually_linked=["n1"], manually_split=["n2"])
    assert state.manually_linked == ["n1"]
    assert state.manually_split == ["n2"]


def test_node_round_trips_every_block() -> None:
    node = Node(
        id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        type="Person",
        properties={"family_name": "Doe"},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED, sources=[_source()], first_seen=datetime.now(UTC)
        ),
        handling=_handling(),
        audit=_audit(),
    )
    dumped = node.model_dump()
    assert Node.model_validate(dumped) == node


def test_edge_carries_its_own_handling_and_provenance() -> None:
    edge = Edge(
        id="01ARZ3NDEKTSV4RRFFQ69G5FAX",
        type="ASSOCIATE_OF",
        source="n1",
        target="n2",
        provenance=Provenance(
            state=ProvenanceState.UNRESOLVED, sources=[_source()], first_seen=datetime.now(UTC)
        ),
        handling=_handling(handling_code="C"),
        audit=_audit(),
    )
    assert edge.handling.handling_code == "C"
    assert edge.provenance.state is ProvenanceState.UNRESOLVED
