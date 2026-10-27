"""ADR-130 Amendment 2, "a read that is written back", for a link change.

A reader whose case reads one of a link's two datasets changes it. What is stored is the link's
whole record with the change added (the writer reads it in full), and what is sent back to that
reader carries no sources, with `sources_withheld` set. Hermetic: `SupersedingGraph` is the
adapter's stand-in, and `FakeGraphPort` withholds sources as the adapter does, so a read that was
not made in full would fail the first case. The same against the real adapter is
`test_link_changes_withheld_live.py`."""

from __future__ import annotations

from services.api.link_changes import LinkChangeRequest, LinkChangeService
from services.api.working_set.service import WorkingSetService

from schemas.domain import Edge, Node, Principal

from .test_link_changes import (
    ONTOLOGY,
    InMemoryChanges,
    MovedNotes,
    SupersedingGraph,
    _edge,
    _node,
)
from .working_set.fakes import FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME

TWO = ["Z1001ZZ", "Z1002ZZ"]
SCOPED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", datasets=[TWO[0]])
BOTH = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-1", datasets=TWO)


def _in(datasets: list[str], element: Node | Edge) -> Node | Edge:
    return element.model_copy(update={"datasets": datasets})


async def _build(
    *, stored_withheld: bool = False
) -> tuple[LinkChangeService, SupersedingGraph, FakeWorkingSetStore]:
    store = FakeWorkingSetStore()
    a, b = _in(TWO, _node("a")), _in(TWO, _node("b"))
    link = _in(TWO, _edge("e1", "a", "b", occurrences=3))
    assert isinstance(link, Edge)
    held = link
    if stored_withheld:
        held = link.model_copy(
            update={
                "provenance": link.provenance.model_copy(
                    update={"sources": [], "sources_withheld": True}
                )
            }
        )
    await store.add_nodes("inv-1", [a, b])  # type: ignore[list-item]
    await store.add_edges("inv-1", [held])
    graph = SupersedingGraph({"e1"})
    # The Vault holds the whole record, as the real store does.
    graph._graph_nodes = {"a": a, "b": b}  # type: ignore[assignment]  # noqa: SLF001
    graph._graph_edges = [link]  # noqa: SLF001
    service = LinkChangeService(
        InMemoryChanges(), WorkingSetService(graph, store, SCHEME), graph, ONTOLOGY, MovedNotes()
    )
    return service, graph, store


async def test_a_scoped_reader_changing_a_two_dataset_link_keeps_every_stored_source() -> None:
    """Violation caught: the change is built from a withheld list, so the stored link loses its
    document sources and keeps only the marker of this change."""
    service, graph, _ = await _build()
    await service.change(
        "inv-1", "e1", SCOPED, LinkChangeRequest(occurrences=7, reason="Seen four more times")
    )
    written = graph.superseded[0][1]
    assert [s.document_id for s in written.provenance.sources] == ["doc-1", "manual:change"]
    assert written.provenance.sources_withheld is False


async def test_what_is_sent_back_to_the_scoped_reader_carries_no_sources() -> None:
    service, _, _ = await _build()
    result = await service.change(
        "inv-1", "e1", SCOPED, LinkChangeRequest(occurrences=7, reason="Seen four more times")
    )
    response = result.to_response(SCOPED)
    assert response.edge.provenance.sources == []
    assert response.edge.provenance.sources_withheld is True
    assert response.delta.edge.provenance.sources == []
    assert response.delta.edge.provenance.sources_withheld is True
    assert "doc-1" not in response.model_dump_json()


async def test_a_reader_of_both_datasets_is_sent_the_sources() -> None:
    service, _, _ = await _build()
    result = await service.change(
        "inv-1", "e1", BOTH, LinkChangeRequest(occurrences=7, reason="Seen four more times")
    )
    response = result.to_response(BOTH)
    assert [s.document_id for s in response.edge.provenance.sources] == ["doc-1", "manual:change"]
    assert [s.document_id for s in response.delta.edge.provenance.sources] == [
        "doc-1",
        "manual:change",
    ]


async def test_a_body_the_working_set_stored_withheld_is_changed_from_the_vaults_record() -> None:
    """The working set reads the Vault with the case's principal, so a body it stored may already be
    withheld. The change is still built from the record in full."""
    service, graph, _ = await _build(stored_withheld=True)
    await service.change(
        "inv-1", "e1", SCOPED, LinkChangeRequest(occurrences=7, reason="Seen four more times")
    )
    written = graph.superseded[0][1]
    assert [s.document_id for s in written.provenance.sources] == ["doc-1", "manual:change"]
