"""A picture's removal, without a database (ADR-124 decision 4 and decision 11).

`EntityPictureService.remove` supersedes the picture's link with a successor. Its provenance used to
name the old link (`manual:remove-picture:{old.id}`), which row two of decision 4 would send, with
the old link's id, to a reader who may read the successor and not the old link. Since U10 the
successor records `manual:remove-picture` with no id and carries no id-bearing entry over from an
earlier revision. The service's own behaviour against a real graph is `test_entity_pictures.py`."""

from __future__ import annotations

from services.api.document_content import DOCUMENT_TYPE
from services.api.entity_pictures import DEPICTS, EntityPictureService
from services.api.working_set.models import DeltaReplaceEdge
from services.api.working_set.service import WorkingSetService

from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.loader import load_default_ontology
from schemas.domain import EdgeId, EdgeWrite, Principal, Subgraph, TxId

from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, edge, node

CASE = "inv-1"
EDITOR = Principal(id="editor-1", clearance="OFFICIAL", org_unit="unit-1")


class _SupersedingGraph(FakeGraphPort):
    """Holds one picture (a Document and the `DEPICTS` link to a car) and accepts a supersede."""

    def __init__(self) -> None:
        document = node("doc-1").model_copy(
            update={
                "type": DOCUMENT_TYPE,
                "properties": {"media_kind": "image", "object_ref": "media:abc.png"},
            }
        )
        link = edge("picture-1", "doc-1", "car-1").model_copy(
            update={"type": DEPICTS, "properties": {"shown": True}}
        )
        super().__init__(Subgraph(nodes=[document], edges=[link]))
        self.superseded: list[tuple[EdgeId, EdgeWrite]] = []

    async def supersede_edge(self, edge_id: EdgeId, replacement: EdgeWrite, tx: TxId) -> EdgeId:
        self.superseded.append((edge_id, replacement))
        return replacement.id


async def _removed() -> tuple[DeltaReplaceEdge, _SupersedingGraph]:
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("car-1"), node("doc-1")])
    graph = _SupersedingGraph()
    service = EntityPictureService(
        WorkingSetService(graph, store, SCHEME),
        graph,
        InMemoryMediaStore(),
        load_default_ontology(),
        scheme=SCHEME,
    )
    return await service.remove(CASE, "car-1", EDITOR), graph


async def test_removing_a_picture_supersedes_its_link_and_records_the_old_one() -> None:
    """The case the marker below stands on: the removal is a replacement whose record is the old
    link's, and whose successor is not shown."""
    delta, graph = await _removed()

    assert [old for old, _ in graph.superseded] == ["picture-1"]
    assert delta.old_edge_id == "picture-1"
    assert delta.edge.properties["shown"] is False
    assert delta.removed is not None and delta.removed.source == "doc-1"


async def test_a_removed_pictures_successor_names_nothing_of_the_old_link() -> None:
    """Violation caught (rule 3): the successor's provenance carries the old link's id, so the
    addition row two sends names a link this reader may not read."""
    delta, _ = await _removed()

    assert "picture-1" not in delta.edge.model_dump_json()
