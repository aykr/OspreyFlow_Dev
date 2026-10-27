"""ADR-130 Amendment 2, "a read that is written back": the writers that read an element and write
its provenance back (an extraction's confirm and retract, a resolution's conflict annotation) read
it in full, so a scoped reader's write succeeds and keeps every stored source. Hermetic, over a
graph that withholds sources as the adapter does and refuses what the adapter's write guard refuses
(a `Provenance` with its sources withheld is never written)."""

from __future__ import annotations

from services.extract.writer import confirm_node, retract_node
from services.resolve.conflicts import ResolutionConflict
from services.resolve.same_as_writer import record_conflicts
from services.resolve.trigger import _fetch_not_same_as_edges, service_principal

from ontology.handling import withhold_sources
from schemas.domain import (
    Edge,
    EdgeId,
    EdgeWrite,
    Node,
    NodeId,
    NodeWrite,
    Principal,
    ProvenanceState,
    Subgraph,
    TxId,
)

from .working_set.fakes import FakeGraphPort
from .working_set.test_visible_link import SCHEME, edge, node

TWO = ["Z1001ZZ", "Z1002ZZ"]
SCOPED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", datasets=[TWO[0]])


class _Graph(FakeGraphPort):
    def __init__(self, held_node: Node, held_edge: Edge) -> None:
        super().__init__(Subgraph(nodes=[held_node], edges=[held_edge]))
        self._held = held_node
        self.node_writes: list[NodeWrite] = []
        self.edge_writes: list[EdgeWrite] = []

    async def get_node(
        self, node_id: NodeId, principal: Principal, *, include_superseded: bool = False
    ) -> Node | None:
        return withhold_sources(self._held, principal) if node_id == self._held.id else None

    async def supersede_node(self, node_id: NodeId, replacement: NodeWrite, tx: TxId) -> NodeId:
        assert not replacement.provenance.sources_withheld, "the write guard refuses this"
        self.node_writes.append(replacement)
        return replacement.id

    async def supersede_edge(self, edge_id: EdgeId, replacement: EdgeWrite, tx: TxId) -> EdgeId:
        assert not replacement.provenance.sources_withheld, "the write guard refuses this"
        self.edge_writes.append(replacement)
        return replacement.id


def _inferred(item: Node) -> Node:
    return item.model_copy(
        update={
            "datasets": list(TWO),
            "provenance": item.provenance.model_copy(update={"state": ProvenanceState.INFERRED}),
        }
    )


async def test_a_scoped_reader_confirming_a_two_dataset_node_keeps_its_sources() -> None:
    graph = _Graph(_inferred(node("n1")), edge("e1", "n1", "n2"))
    await confirm_node(graph, "n1", SCOPED, tx="tx")
    written = graph.node_writes[0].provenance
    assert [s.document_id for s in written.sources] == ["doc-1"]
    assert written.state is ProvenanceState.ASSERTED


async def test_a_scoped_reader_retracting_a_two_dataset_node_keeps_its_sources() -> None:
    asserted = _inferred(node("n1")).model_copy(update={"provenance": node("n1").provenance})
    graph = _Graph(asserted.model_copy(update={"datasets": list(TWO)}), edge("e1", "n1", "n2"))
    await retract_node(graph, "n1", SCOPED, tx="tx")
    assert [s.document_id for s in graph.node_writes[0].provenance.sources] == ["doc-1"]


async def test_a_conflict_annotation_keeps_the_sources_of_the_link_it_supersedes() -> None:
    """Guards a future scoped caller. Production runs resolution as `service_principal`, whose
    `datasets` is `None` (unlimited), so it is never withheld today; the next test is that case."""
    link = edge("ns1", "n1", "n2").model_copy(update={"type": "NOT_SAME_AS", "datasets": list(TWO)})
    graph = _Graph(node("n1"), link)
    fetched = await _fetch_not_same_as_edges(graph, ["n1", "n2"], SCOPED)
    conflict = ResolutionConflict(
        node_a="n1",
        node_b="n2",
        not_same_as_edge_id="ns1",
        would_be_score=0.9,
        would_be_model_version="m1",
        would_be_comparison_vector={},
    )
    await record_conflicts(
        graph, [conflict], {e.id: e for e in fetched}, created_by="service", tx="tx"
    )
    assert [s.document_id for s in graph.edge_writes[0].provenance.sources] == ["doc-1"]


async def test_the_production_resolution_principal_keeps_the_sources_too() -> None:
    link = edge("ns1", "n1", "n2").model_copy(update={"type": "NOT_SAME_AS", "datasets": list(TWO)})
    graph = _Graph(node("n1"), link)
    service = service_principal(SCHEME)
    fetched = await _fetch_not_same_as_edges(graph, ["n1", "n2"], service)
    conflict = ResolutionConflict(
        node_a="n1",
        node_b="n2",
        not_same_as_edge_id="ns1",
        would_be_score=0.9,
        would_be_model_version="m1",
        would_be_comparison_vector={},
    )
    await record_conflicts(
        graph, [conflict], {e.id: e for e in fetched}, created_by="service", tx="tx"
    )
    assert [s.document_id for s in graph.edge_writes[0].provenance.sources] == ["doc-1"]
