"""End-to-end proof of Phase 6's own exit criterion: "A manual split survives
a subsequent resolution run that would have merged the pair, and the conflict is recorded for
review." `tests/resolve/test_conflicts.py` and `test_same_as_writer.py` each prove one stage of
this pipeline against synthetic `SameAsCandidate`/`Edge` fixtures; this file wires
`resolve_entity_type` (real Splink, no live infra needed — see `test_resolver.py`'s own module
docstring) through `detect_conflicts` through `record_conflicts` in one pass, so the claim rests
on the resolver's own real output, not a hand-built stand-in for it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.resolve.conflicts import detect_conflicts
from services.resolve.resolver import resolve_entity_type
from services.resolve.same_as_writer import record_conflicts

from ontology.loader import load_default_ontology
from schemas.domain import (
    AuditStub,
    Edge,
    EdgeWrite,
    EntityTypeDef,
    Handling,
    Node,
    Provenance,
    ProvenanceState,
    SourceRef,
)

PERSON_TYPE: EntityTypeDef = next(
    e for e in load_default_ontology().entity_types if e.name == "Person"
)


def _person(node_id: str, family_name: str, given_names: str, date_of_birth: str) -> Node:
    return Node(
        id=node_id,
        type="Person",
        properties={
            "family_name": family_name,
            "given_names": given_names,
            "date_of_birth": date_of_birth,
        },
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="d1", locator="p1", excerpt_hash="h")],
            first_seen=datetime.now(UTC),
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
        audit=AuditStub(created_at=datetime.now(UTC), created_by="analyst-1"),
    )


class _FakeGraphPort:
    def __init__(self) -> None:
        self.superseded: list[tuple[str, EdgeWrite]] = []

    async def supersede_edge(self, edge_id: str, replacement: EdgeWrite, tx: str) -> str:
        self.superseded.append((edge_id, replacement))
        return replacement.id


async def test_a_near_certain_match_against_a_manual_split_is_recorded_as_a_conflict() -> None:
    """Two identical-rendering `Person` nodes score near-certain under the real, untrained
    Splink defaults (`tests/resolve/test_resolution_accuracy.py`'s own "identical rendering"
    case) — exactly the situation an analyst's earlier `NOT_SAME_AS` (`manual_split`) must
    survive."""
    nodes = [
        _person("n1", "Mercer", "Dana", "1980-01-01"),
        _person("n2", "Mercer", "Dana", "1980-01-01"),
    ]
    candidates = resolve_entity_type(nodes, PERSON_TYPE)
    assert len(candidates) == 1
    assert candidates[0].score > 0.9  # confirms this pair really would have merged

    split_edge = Edge(
        id="split-1",
        type="NOT_SAME_AS",
        source="n1",
        target="n2",
        properties={},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="manual:n1:n2", locator="analyst-1", excerpt_hash="")],
            first_seen=datetime.now(UTC),
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
        audit=AuditStub(created_at=datetime.now(UTC), created_by="analyst-1"),
    )

    conflicts = detect_conflicts(candidates, [split_edge])
    assert len(conflicts) == 1

    graph = _FakeGraphPort()
    new_ids = await record_conflicts(
        graph, conflicts, {split_edge.id: split_edge}, created_by="resolve-service", tx="tx-1"
    )

    assert len(new_ids) == 1
    superseded_id, replacement = graph.superseded[0]
    assert superseded_id == "split-1"
    assert replacement.type == "NOT_SAME_AS"  # the split itself is preserved, never overridden
    assert replacement.properties["conflict_pending"] is True
    assert replacement.properties["conflict_score"] == candidates[0].score


async def test_a_clear_non_match_against_a_manual_split_is_not_a_conflict() -> None:
    """The negative-control case: an unrelated pair that also happens to have a stale
    `NOT_SAME_AS` edge between them (e.g. from a since-corrected earlier split) should not be
    flagged — there is nothing to review if the fresh run agrees with the split. `n1`/`n2` share
    `date_of_birth`'s year (so they block together and are actually compared, not skipped) but are
    otherwise unrelated — `tests/resolve/test_resolution_accuracy.py`'s own "same year, different
    person" negative control, confirmed there to score near-zero, not merely never assessed."""
    nodes = [
        _person("n1", "Okafor", "Susan", "1980-01-01"),
        _person("n2", "Mercer", "Dana", "1980-01-01"),
    ]
    candidates = resolve_entity_type(nodes, PERSON_TYPE)
    assert len(candidates) == 1
    assert candidates[0].score < 0.5  # confirms this pair really was assessed and rejected

    split_edge = Edge(
        id="split-1",
        type="NOT_SAME_AS",
        source="n1",
        target="n2",
        properties={},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="manual:n1:n2", locator="analyst-1", excerpt_hash="")],
            first_seen=datetime.now(UTC),
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
        audit=AuditStub(created_at=datetime.now(UTC), created_by="analyst-1"),
    )

    assert detect_conflicts(candidates, [split_edge]) == []
