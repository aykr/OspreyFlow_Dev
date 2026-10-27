"""ADR-130 Amendment 2: a node's or link's sources reach a reader only when every dataset the
element belongs to is one the reader's case reads. The one predicate, and the one function that
applies it."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ontology.handling import sources_within_case, withhold_sources
from schemas.domain import (
    AuditStub,
    Edge,
    Handling,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)


def _provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="files/calls.csv", locator="row 4", excerpt_hash="b" * 64)],
        first_seen=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _handling() -> Handling:
    return Handling(
        classification="OFFICIAL", handling_code="P", originator="org-1", owning_unit="org-1"
    )


def _audit() -> AuditStub:
    return AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="analyst-1")


def _node(datasets: list[str]) -> Node:
    return Node(
        id="N1",
        type="Person",
        provenance=_provenance(),
        handling=_handling(),
        audit=_audit(),
        datasets=datasets,
    )


def _edge(datasets: list[str]) -> Edge:
    return Edge(
        id="E1",
        type="KNOWS",
        source="N1",
        target="N2",
        provenance=_provenance(),
        handling=_handling(),
        audit=_audit(),
        datasets=datasets,
    )


def _principal(datasets: list[str] | None) -> Principal:
    return Principal(id="p-1", clearance="OFFICIAL", org_unit="org-1", datasets=datasets)


def test_an_element_in_two_datasets_read_by_a_case_of_one_is_withheld() -> None:
    node = withhold_sources(_node(["Z1001ZZ", "Z1002ZZ"]), _principal(["Z1001ZZ"]))
    assert node.provenance.sources == []
    assert node.provenance.sources_withheld is True


def test_an_element_in_two_datasets_read_by_a_case_of_both_keeps_its_sources() -> None:
    node = withhold_sources(_node(["Z1001ZZ", "Z1002ZZ"]), _principal(["Z1001ZZ", "Z1002ZZ"]))
    assert len(node.provenance.sources) == 1
    assert node.provenance.sources_withheld is False


def test_an_element_in_two_datasets_read_by_a_case_of_none_is_withheld() -> None:
    node = withhold_sources(_node(["Z1001ZZ", "Z1002ZZ"]), _principal([]))
    assert node.provenance.sources_withheld is True


def test_an_element_naming_no_dataset_is_withheld_from_a_scoped_reader() -> None:
    assert sources_within_case([], _principal(["Z1001ZZ"])) is False
    assert withhold_sources(_node([]), _principal(["Z1001ZZ"])).provenance.sources_withheld


def test_the_unlimited_principal_reads_every_source() -> None:
    node = _node(["Z1001ZZ", "Z1002ZZ"])
    assert withhold_sources(node, _principal(None)) is node
    assert sources_within_case([], _principal(None)) is True


def test_a_link_is_withheld_the_same_way() -> None:
    edge = withhold_sources(_edge(["Z1001ZZ", "Z1002ZZ"]), _principal(["Z1002ZZ"]))
    assert edge.provenance.sources == []
    assert edge.provenance.sources_withheld is True


def test_the_original_is_not_changed() -> None:
    """The working set holds the full body and projects a copy for each reader."""
    node = _node(["Z1001ZZ", "Z1002ZZ"])
    withhold_sources(node, _principal(["Z1001ZZ"]))
    assert len(node.provenance.sources) == 1
    assert node.provenance.sources_withheld is False


@pytest.mark.parametrize("held", [["Z1001ZZ"], ["Z1001ZZ", "Z1002ZZ", "Z1003ZZ"]])
def test_a_case_reading_a_superset_names_the_sources_only_when_it_covers_every_dataset(
    held: list[str],
) -> None:
    node = withhold_sources(_node(["Z1001ZZ", "Z1002ZZ"]), _principal(held))
    assert node.provenance.sources_withheld is (held == ["Z1001ZZ"])
