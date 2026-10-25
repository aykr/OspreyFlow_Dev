"""ADR-102 Amendment 3: a picture set twice on one entity, in one audience, leaves one live link,
and what the canvas is told names the link the store holds.

The store hands back its own id for a link it writes (`upsert_edges`, `supersede_edge`), and the
service builds the delta from that id, never from the one it sent. `test_entity_pictures.py` proves
the replacement against a real ArcadeDB; this one needs no store, so the id handling is exercised on
every run. The graph fake gives every link it holds an id of its own (`stored-n`), as the adapter
does whenever another audience's link holds the id sent."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from services.api.entity_pictures import DEPICTS, EntityPictureService
from services.api.working_set.service import WorkingSetService

from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    AuditStub,
    Edge,
    EdgeWrite,
    Handling,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
    TxId,
)

from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore

ONTOLOGY = load_default_ontology()
SCHEME = load_uk_le_scheme()
NOW = datetime(2026, 10, 9, tzinfo=UTC)
READER = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
HANDLING = Handling(
    classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
)
PROVENANCE = Provenance(
    state=ProvenanceState.ASSERTED,
    sources=[SourceRef(document_id="fixture", locator="row 1", excerpt_hash="")],
    first_seen=NOW,
)
CAR = Node(
    id="car-1",
    type="Vehicle",
    properties={},
    provenance=PROVENANCE,
    handling=HANDLING,
    audit=AuditStub(created_at=NOW, created_by="loader"),
)


class PictureGraph:
    """Holds nodes and links; a link written or superseded is held under `stored-n`, and its
    predecessor is no longer live. Only what `EntityPictureService.set` calls."""

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.links: list[tuple[Edge, bool]] = []
        self.counter = 0

    def _store(self, write: EdgeWrite, revision: int = 1) -> str:
        self.counter += 1
        edge = Edge(
            id=f"stored-{self.counter}",
            type=write.type,
            source=write.source,
            target=write.target,
            properties=dict(write.properties),
            provenance=write.provenance,
            handling=write.handling,
            audit=AuditStub(
                created_at=write.created_at, created_by=write.created_by, revision=revision
            ),
        )
        self.links.append((edge, True))
        return edge.id

    @property
    def live(self) -> list[Edge]:
        return [e for e, live in self.links if live]

    async def begin_transaction(self) -> TxId:
        return "tx-1"

    async def commit_transaction(self, tx: TxId) -> None:
        return None

    async def rollback_transaction(self, tx: TxId) -> None:
        return None

    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: TxId) -> list[str]:
        for w in nodes:
            self.nodes[w.id] = Node(
                id=w.id,
                type=w.type,
                properties=dict(w.properties),
                provenance=w.provenance,
                handling=w.handling,
                audit=AuditStub(created_at=w.created_at, created_by=w.created_by),
            )
        return [w.id for w in nodes]

    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: TxId) -> list[str]:
        return [self._store(w) for w in edges]

    async def supersede_edge(self, edge_id: str, replacement: EdgeWrite, tx: TxId) -> str:
        self.links = [(e, live and e.id != edge_id) for e, live in self.links]
        return self._store(replacement)

    async def expand(self, req: Any, principal: Principal) -> Subgraph:
        edges = [e for e in self.live if e.type in req.edge_types and e.target in req.node_ids]
        ends = {e.source for e in edges}
        return Subgraph(nodes=[n for i, n in self.nodes.items() if i in ends], edges=edges)


async def _service() -> tuple[EntityPictureService, PictureGraph, FakeWorkingSetStore]:
    graph = PictureGraph()
    graph.nodes["car-1"] = CAR
    store = FakeWorkingSetStore()
    await store.add_nodes("inv-1", [CAR])
    working_set = WorkingSetService(
        FakeGraphPort(Subgraph(nodes=[], edges=[])), store, SCHEME  # type: ignore[arg-type]
    )
    service = EntityPictureService(
        working_set, graph, InMemoryMediaStore(), ONTOLOGY, scheme=SCHEME  # type: ignore[arg-type]
    )
    return service, graph, store


async def test_a_picture_set_twice_in_one_audience_is_one_link_named_by_its_stored_id() -> None:
    service, graph, store = await _service()
    first = await service.set(
        "inv-1", "car-1", READER, name="car.png", data=b"\x89PNG\r\n\x1a\nfirst", handling=HANDLING
    )
    (added,) = first.deltas
    assert [e.id for e in added.edges] == ["stored-1"]  # type: ignore[union-attr]

    second = await service.set(
        "inv-1", "car-1", READER, name="car.png", data=b"\x89PNG\r\n\x1a\nsecond", handling=HANDLING
    )

    (live,) = graph.live
    assert live.id == "stored-2" and live.type == DEPICTS
    (_, replaced) = second.deltas
    assert (replaced.old_edge_id, replaced.edge.id) == ("stored-1", "stored-2")  # type: ignore[union-attr]
    assert await store.edge_ids("inv-1") == {"stored-2"}, "the case holds the store's one link"
