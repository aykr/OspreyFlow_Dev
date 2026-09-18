"""`services/resolve/same_as_writer.py` — `docs/01_DOMAIN_MODEL.md` §4."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from services.resolve.conflicts import ResolutionConflict
from services.resolve.resolver import MODEL_VERSION, SameAsCandidate
from services.resolve.same_as_writer import record_conflicts, write_same_as_edges

from schemas.domain import (
    AuditStub,
    Edge,
    EdgeWrite,
    Handling,
    Node,
    Provenance,
    ProvenanceState,
    SourceRef,
)


class _FakeGraphPort:
    def __init__(self) -> None:
        self.writes: list[EdgeWrite] = []
        self.superseded: list[tuple[str, EdgeWrite]] = []

    async def upsert_edges(self, edges: list[EdgeWrite], tx: str) -> list[str]:
        self.writes.extend(edges)
        return [e.id for e in edges]

    async def supersede_edge(self, edge_id: str, replacement: EdgeWrite, tx: str) -> str:
        self.superseded.append((edge_id, replacement))
        return replacement.id


def _person(node_id: str, classification: str = "OFFICIAL") -> Node:
    return Node(
        id=node_id,
        type="Person",
        properties={},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="d", locator="l", excerpt_hash="")],
            first_seen=datetime.now(UTC),
        ),
        handling=Handling(
            classification=classification,
            handling_code="P",
            originator="unit-1",
            owning_unit="unit-1",
        ),
        audit=AuditStub(created_at=datetime.now(UTC), created_by="analyst-1"),
    )


async def test_writes_one_edge_per_candidate_with_score_and_model_version() -> None:
    graph = _FakeGraphPort()
    nodes_by_id = {"n1": _person("n1"), "n2": _person("n2")}
    candidate = SameAsCandidate(
        node_a="n1", node_b="n2", score=0.93, comparison_vector={"match_weight": 4.2}
    )

    edge_ids = await write_same_as_edges(
        graph, [candidate], nodes_by_id, created_by="resolve-service", tx="tx-1"
    )

    assert len(edge_ids) == 1
    written = graph.writes[0]
    assert written.type == "SAME_AS"
    assert written.source == "n1"
    assert written.target == "n2"
    assert written.properties["score"] == 0.93
    assert written.properties["model_version"] == MODEL_VERSION
    assert json.loads(written.properties["comparison_vector"]) == {"match_weight": 4.2}
    assert written.provenance.state.value == "inferred"
    assert written.provenance.extraction_confidence == 0.93


async def test_edge_inherits_node_as_own_handling() -> None:
    graph = _FakeGraphPort()
    nodes_by_id = {
        "n1": _person("n1", classification="SECRET"),
        "n2": _person("n2", classification="OFFICIAL"),
    }
    candidate = SameAsCandidate(node_a="n1", node_b="n2", score=0.9, comparison_vector={})

    await write_same_as_edges(
        graph, [candidate], nodes_by_id, created_by="resolve-service", tx="tx-1"
    )

    assert graph.writes[0].handling.classification == "SECRET"


async def test_no_candidates_writes_nothing() -> None:
    graph = _FakeGraphPort()
    edge_ids = await write_same_as_edges(graph, [], {}, created_by="resolve-service", tx="tx-1")
    assert edge_ids == []
    assert graph.writes == []


def _split_edge() -> Edge:
    return Edge(
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


async def test_record_conflicts_supersedes_the_split_edge_with_conflict_properties() -> None:
    graph = _FakeGraphPort()
    split = _split_edge()
    conflict = ResolutionConflict(
        node_a="n1",
        node_b="n2",
        not_same_as_edge_id=split.id,
        would_be_score=0.97,
        would_be_model_version=MODEL_VERSION,
        would_be_comparison_vector={"match_weight": 5.1},
    )

    new_ids = await record_conflicts(
        graph, [conflict], {split.id: split}, created_by="resolve-service", tx="tx-1"
    )

    assert len(new_ids) == 1
    superseded_id, replacement = graph.superseded[0]
    assert superseded_id == "split-1"
    assert replacement.type == "NOT_SAME_AS"
    assert replacement.source == "n1"
    assert replacement.target == "n2"
    assert replacement.properties["conflict_pending"] is True
    assert replacement.properties["conflict_score"] == 0.97
    assert replacement.properties["conflict_model_version"] == MODEL_VERSION
    assert json.loads(replacement.properties["conflict_comparison_vector"]) == {"match_weight": 5.1}
    # The original split edge's own fields (handling, provenance) are preserved, not replaced —
    # a conflict recording is an annotation on the analyst's decision, not a new decision.
    assert replacement.handling == split.handling
    assert replacement.provenance == split.provenance


async def test_record_conflicts_with_no_conflicts_writes_nothing() -> None:
    graph = _FakeGraphPort()
    ids = await record_conflicts(graph, [], {}, created_by="resolve-service", tx="tx-1")
    assert ids == []
    assert graph.superseded == []
