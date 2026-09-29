"""`services/extract/writer.py` — `spec/01_DOMAIN_MODEL.md` §2.1, `spec/09_INGEST_STUDIO.md` §7."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.extract.candidates import ExtractionCandidate
from services.extract.writer import (
    NodeNotFoundError,
    ProvenanceTransitionError,
    confirm_node,
    retract_node,
    write_candidate,
)

from schemas.domain import (
    AuditStub,
    EdgeWrite,
    Handling,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


def _handling() -> Handling:
    return Handling(classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u")


def _candidate() -> ExtractionCandidate:
    return ExtractionCandidate(
        id="cand-1",
        document_id="doc-1",
        entity_type="Person",
        properties={"family_name": "MERCER", "given_names": "Dana"},
        confidence=0.9,
        model="qwen2.5:0.5b-instruct",
        locator="char span 0-6",
        excerpt_hash="abc123",
        handling=_handling(),
    )


def _node(node_id: str, state: ProvenanceState) -> Node:
    return Node(
        id=node_id,
        type="Person",
        properties={"family_name": "MERCER"},
        provenance=Provenance(
            state=state,
            sources=[SourceRef(document_id="doc-1", locator="char span 0-6", excerpt_hash="h")],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
            extraction_confidence=0.9 if state is not ProvenanceState.ASSERTED else None,
        ),
        handling=_handling(),
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="model:m"),
    )


class _FakeGraphPort:
    def __init__(self, existing: Node | None = None) -> None:
        self.existing = existing
        self.upserted: list[NodeWrite] = []
        self.superseded: list[tuple[str, NodeWrite]] = []

    async def upsert_nodes(self, nodes: list[NodeWrite], tx: str) -> list[str]:
        self.upserted.extend(nodes)
        return [n.id for n in nodes]

    async def upsert_edges(self, edges: list[EdgeWrite], tx: str) -> list[str]:
        raise AssertionError("not exercised by these tests")

    async def get_node(
        self, node_id: str, principal: Principal, *, include_superseded: bool = False
    ) -> Node | None:
        if self.existing is not None and self.existing.id == node_id:
            return self.existing
        return None

    async def supersede_node(self, node_id: str, replacement: NodeWrite, tx: str) -> str:
        self.superseded.append((node_id, replacement))
        return replacement.id


async def test_write_candidate_writes_an_inferred_node_not_asserted() -> None:
    graph = _FakeGraphPort()

    node_id = await write_candidate(graph, _candidate(), created_by="analyst-1", tx="tx-1")

    assert node_id == graph.upserted[0].id
    written = graph.upserted[0]
    assert written.type == "Person"
    assert written.properties == {"family_name": "MERCER", "given_names": "Dana"}
    assert written.provenance.state == ProvenanceState.INFERRED
    assert written.provenance.extraction_confidence == 0.9
    assert written.provenance.extracted_by == "model:qwen2.5:0.5b-instruct"
    assert written.provenance.sources[0].document_id == "doc-1"
    assert written.provenance.sources[0].locator == "char span 0-6"
    assert written.handling == _handling()


async def test_confirm_node_flips_inferred_to_asserted_via_supersede() -> None:
    node = _node("n1", ProvenanceState.INFERRED)
    graph = _FakeGraphPort(existing=node)

    new_id = await confirm_node(graph, "n1", PRINCIPAL, tx="tx-1")

    assert new_id == graph.superseded[0][1].id
    superseded_id, replacement = graph.superseded[0]
    assert superseded_id == "n1"
    # A fresh id, not the original node's own — `GraphPort.supersede_node`'s own conformance suite
    # requires this, and reusing the original id collides with the still-present superseded
    # revision on a real adapter (found live against ArcadeDB, not merely asserted here).
    assert replacement.id != "n1"
    assert replacement.provenance.state == ProvenanceState.ASSERTED
    assert replacement.provenance.confirmed_by == "analyst-1"
    assert replacement.provenance.last_confirmed is not None
    # `extraction_confidence` must be null for asserted provenance (`Provenance`'s own validator).
    assert replacement.provenance.extraction_confidence is None


async def test_confirm_node_from_unresolved_also_succeeds() -> None:
    node = _node("n1", ProvenanceState.UNRESOLVED)
    graph = _FakeGraphPort(existing=node)

    await confirm_node(graph, "n1", PRINCIPAL, tx="tx-1")

    assert graph.superseded[0][1].provenance.state == ProvenanceState.ASSERTED


async def test_confirm_node_already_asserted_raises() -> None:
    node = _node("n1", ProvenanceState.ASSERTED)
    graph = _FakeGraphPort(existing=node)

    with pytest.raises(ProvenanceTransitionError):
        await confirm_node(graph, "n1", PRINCIPAL, tx="tx-1")
    assert graph.superseded == []


async def test_confirm_node_not_found_or_not_visible_raises() -> None:
    graph = _FakeGraphPort(existing=None)

    with pytest.raises(NodeNotFoundError):
        await confirm_node(graph, "no-such-node", PRINCIPAL, tx="tx-1")


async def test_retract_node_flips_asserted_back_to_inferred_and_clears_confirmation() -> None:
    node = _node("n1", ProvenanceState.ASSERTED)
    graph = _FakeGraphPort(existing=node)

    await retract_node(graph, "n1", PRINCIPAL, tx="tx-1")

    replacement = graph.superseded[0][1]
    assert replacement.id != "n1"
    assert replacement.provenance.state == ProvenanceState.INFERRED
    assert replacement.provenance.confirmed_by is None
    assert replacement.provenance.last_confirmed is None


async def test_retract_node_not_currently_asserted_raises() -> None:
    node = _node("n1", ProvenanceState.INFERRED)
    graph = _FakeGraphPort(existing=node)

    with pytest.raises(ProvenanceTransitionError):
        await retract_node(graph, "n1", PRINCIPAL, tx="tx-1")
    assert graph.superseded == []


async def test_retract_node_not_found_or_not_visible_raises() -> None:
    graph = _FakeGraphPort(existing=None)

    with pytest.raises(NodeNotFoundError):
        await retract_node(graph, "no-such-node", PRINCIPAL, tx="tx-1")
