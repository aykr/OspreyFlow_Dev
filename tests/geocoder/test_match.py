"""`services/geocoder/match.py` — `docs/01_DOMAIN_MODEL.md` §4's
entity-resolution design mirrored for gazetteer matching,
`docs/07_BUILD_PLAN.md` Phase 5 Checkpoint 3c. `GraphPort` is faked (only
`upsert_edges` is ever called) — the same "prove only the wiring, fake the
port" discipline `test_sites_routes.py` already established; nothing here
needs a live ArcadeDB.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.geocoder.match import match_place_mention

from ontology.handling import load_uk_le_scheme
from schemas.domain import (
    AuditStub,
    Handling,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    ResolutionState,
    SourceRef,
)

CLEARED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
SCHEME = load_uk_le_scheme()


class _FakeGraph:
    def __init__(self) -> None:
        self.upserted_edges: list[object] = []

    async def upsert_edges(self, edges: list[object], tx: str) -> list[str]:
        self.upserted_edges.extend(edges)
        return [f"edge-{i}" for i in range(len(edges))]


def _location(node_id: str, name: str, *, classification: str = "OFFICIAL") -> Node:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return Node(
        id=node_id,
        type="Location",
        properties={"name": name},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="gazetteer-fixture", locator=node_id, excerpt_hash="")],
            first_seen=now,
        ),
        handling=Handling(
            classification=classification, handling_code="P", originator="unit-1",
            owning_unit="unit-1",
        ),
        resolution=ResolutionState(),
        audit=AuditStub(created_at=now, created_by="tester"),
    )


async def test_matches_the_best_scoring_candidate_above_threshold() -> None:
    graph = _FakeGraph()
    mention = _location("mention-1", "Cranford")
    candidates = [_location("loc-1", "Cranford"), _location("loc-2", "Oxford")]

    edge = await match_place_mention(graph, mention, candidates, CLEARED, SCHEME, "tx-1")  # type: ignore[arg-type]

    assert edge is not None
    assert edge.type == "SAME_AS"
    assert edge.source == "mention-1"
    assert edge.target == "loc-1"
    assert edge.properties["score"] == pytest.approx(1.0)
    assert edge.provenance.state == "inferred"
    assert len(graph.upserted_edges) == 1


async def test_returns_none_when_nothing_scores_above_the_threshold() -> None:
    graph = _FakeGraph()
    mention = _location("mention-1", "Cranford")
    candidates = [_location("loc-1", "Zzyzx")]

    edge = await match_place_mention(graph, mention, candidates, CLEARED, SCHEME, "tx-1")  # type: ignore[arg-type]

    assert edge is None
    assert graph.upserted_edges == []


async def test_never_matches_against_a_candidate_the_principal_cannot_view() -> None:
    graph = _FakeGraph()
    mention = _location("mention-1", "Cranford")
    # The perfect-scoring candidate is above the principal's clearance —
    # the imperfect one is visible and should be matched instead.
    candidates = [
        _location("loc-secret", "Cranford", classification="SECRET"),
        _location("loc-visible", "Cranfor"),
    ]

    edge = await match_place_mention(graph, mention, candidates, CLEARED, SCHEME, "tx-1")  # type: ignore[arg-type]

    assert edge is not None
    assert edge.target == "loc-visible"
