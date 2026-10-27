"""ADR-130 Amendment 2, "a read that is written back", for removing a picture.

A reader whose case reads one of a picture link's two datasets removes it. The successor is built
from the link as the graph holds it (the writer reads it in full), so it keeps every stored source
with this removal added; what the reader is sent back carries none. Hermetic, over `FakeGraphPort`,
which withholds sources as the adapter does."""

from __future__ import annotations

import pytest
from services.api.document_content import DOCUMENT_TYPE
from services.api.entity_pictures import DEPICTS, EntityPictureService, PictureNotFoundError
from services.api.working_set.service import WorkingSetService

from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.loader import load_default_ontology
from schemas.domain import EdgeId, EdgeWrite, Principal, Subgraph, TxId

from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, edge, node

CASE = "inv-1"
TWO = ["Z1001ZZ", "Z1002ZZ"]
SCOPED = Principal(id="editor-1", clearance="OFFICIAL", org_unit="unit-1", datasets=[TWO[0]])
BOTH = Principal(id="editor-2", clearance="OFFICIAL", org_unit="unit-1", datasets=TWO)


class _SupersedingGraph(FakeGraphPort):
    def __init__(self) -> None:
        document = node("doc-1").model_copy(
            update={
                "type": DOCUMENT_TYPE,
                "datasets": list(TWO),
                "properties": {"media_kind": "image", "object_ref": "media:abc.png"},
            }
        )
        link = edge("picture-1", "doc-1", "car-1").model_copy(
            update={"type": DEPICTS, "properties": {"shown": True}, "datasets": list(TWO)}
        )
        super().__init__(Subgraph(nodes=[document], edges=[link]))
        self.superseded: list[tuple[EdgeId, EdgeWrite]] = []

    async def supersede_edge(self, edge_id: EdgeId, replacement: EdgeWrite, tx: TxId) -> EdgeId:
        self.superseded.append((edge_id, replacement))
        return replacement.id


async def _service() -> tuple[EntityPictureService, _SupersedingGraph]:
    store = FakeWorkingSetStore()
    car = node("car-1").model_copy(update={"datasets": list(TWO)})
    doc = node("doc-1").model_copy(update={"datasets": list(TWO)})
    await store.add_nodes(CASE, [car, doc])
    graph = _SupersedingGraph()
    service = EntityPictureService(
        WorkingSetService(graph, store, SCHEME),
        graph,
        InMemoryMediaStore(),
        load_default_ontology(),
        scheme=SCHEME,
    )
    return service, graph


async def test_a_scoped_reader_removing_a_two_dataset_picture_keeps_every_stored_source() -> None:
    """Violation caught: the successor is built from a withheld list and the write guard refuses
    it, or (without the guard) the stored sources are replaced by the removal's own marker."""
    service, graph = await _service()
    await service.remove(CASE, "car-1", SCOPED)
    written = graph.superseded[0][1]
    assert [s.document_id for s in written.provenance.sources] == [
        "doc-1",
        "manual:remove-picture",
    ]
    assert written.provenance.sources_withheld is False


async def test_what_the_scoped_reader_is_sent_back_carries_no_sources() -> None:
    service, _ = await _service()
    delta = await service.remove(CASE, "car-1", SCOPED)
    sent = delta.to_sent(SCOPED)
    assert sent.edge.provenance.sources == []
    assert sent.edge.provenance.sources_withheld is True
    assert "manual:remove-picture" not in sent.model_dump_json()
    whole = delta.to_sent(BOTH)
    assert [s.document_id for s in whole.edge.provenance.sources] == [
        "doc-1",
        "manual:remove-picture",
    ]


class _StillWithheldGraph(_SupersedingGraph):
    """A graph whose full-scope read still returns the link withheld (stored so)."""

    async def expand(self, req, principal):  # type: ignore[no-untyped-def]
        found = await super().expand(req, principal)
        return found.model_copy(
            update={
                "edges": [
                    e.model_copy(
                        update={
                            "provenance": e.provenance.model_copy(
                                update={"sources": [], "sources_withheld": True}
                            )
                        }
                    )
                    for e in found.edges
                ]
            }
        )


async def test_a_link_still_withheld_after_the_full_read_is_not_found_and_nothing_is_written() -> (
    None
):
    """Violation caught: the marker-only rebuild, a successor whose sources are the removal's own
    marker alone, replacing every stored source."""
    store = FakeWorkingSetStore()
    await store.add_nodes(
        CASE,
        [
            node("car-1").model_copy(update={"datasets": list(TWO)}),
            node("doc-1").model_copy(update={"datasets": list(TWO)}),
        ],
    )
    graph = _StillWithheldGraph()
    service = EntityPictureService(
        WorkingSetService(graph, store, SCHEME),
        graph,
        InMemoryMediaStore(),
        load_default_ontology(),
        scheme=SCHEME,
    )
    with pytest.raises(PictureNotFoundError):
        await service.remove(CASE, "car-1", SCOPED)
    assert graph.superseded == []
