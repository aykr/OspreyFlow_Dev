"""`services/resolve/conflicts.py` — `spec/01_DOMAIN_MODEL.md` §4, `spec/03_CONDUIT_MIDDLEWARE.md`
§5.3: "a later run that would have merged the pair records the conflict for review rather than
acting on it." Pure function, same discipline as `tests/resolve/test_projection.py`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from services.resolve.conflicts import conflict_properties, detect_conflicts
from services.resolve.resolver import MODEL_VERSION, SameAsCandidate

from schemas.domain import (
    AuditStub,
    Edge,
    Handling,
    Provenance,
    ProvenanceState,
    SourceRef,
)


def _not_same_as(edge_id: str, node_a: str, node_b: str) -> Edge:
    return Edge(
        id=edge_id,
        type="NOT_SAME_AS",
        source=node_a,
        target=node_b,
        properties={},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="manual:n1:n2", locator="analyst-1", excerpt_hash="")],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u"
        ),
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="analyst-1"),
    )


def test_a_high_scoring_candidate_against_a_split_pair_is_a_conflict() -> None:
    split = _not_same_as("split-1", "n1", "n2")
    candidate = SameAsCandidate(
        node_a="n1", node_b="n2", score=0.97, comparison_vector={"match_weight": 5.1}
    )

    conflicts = detect_conflicts([candidate], [split])

    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict.not_same_as_edge_id == "split-1"
    assert conflict.would_be_score == 0.97
    assert conflict.would_be_model_version == MODEL_VERSION
    assert conflict.would_be_comparison_vector == {"match_weight": 5.1}


def test_a_low_scoring_candidate_against_a_split_pair_is_not_a_conflict() -> None:
    split = _not_same_as("split-1", "n1", "n2")
    candidate = SameAsCandidate(node_a="n1", node_b="n2", score=0.5, comparison_vector={})

    assert detect_conflicts([candidate], [split]) == []


def test_a_high_scoring_candidate_with_no_split_pair_is_not_a_conflict() -> None:
    candidate = SameAsCandidate(node_a="n1", node_b="n2", score=0.99, comparison_vector={})

    assert detect_conflicts([candidate], []) == []


def test_threshold_is_configurable() -> None:
    split = _not_same_as("split-1", "n1", "n2")
    candidate = SameAsCandidate(node_a="n1", node_b="n2", score=0.85, comparison_vector={})

    assert detect_conflicts([candidate], [split], threshold=0.95) == []
    assert len(detect_conflicts([candidate], [split], threshold=0.80)) == 1


def test_conflict_properties_carries_json_encoded_comparison_vector() -> None:
    split = _not_same_as("split-1", "n1", "n2")
    candidate = SameAsCandidate(
        node_a="n1", node_b="n2", score=0.97, comparison_vector={"match_weight": 5.1}
    )
    conflict = detect_conflicts([candidate], [split])[0]

    properties = conflict_properties(conflict)

    assert properties["conflict_pending"] is True
    assert properties["conflict_score"] == 0.97
    assert properties["conflict_model_version"] == MODEL_VERSION
    assert json.loads(properties["conflict_comparison_vector"]) == {"match_weight": 5.1}
