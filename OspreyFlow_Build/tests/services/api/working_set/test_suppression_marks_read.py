"""The canvas reads its suppression marks back (v0.5.2 route row S7; owner ruling R7's step one,
`02_GLASS_FRONTEND.md` §9.5): `suppression.marks_on_the_canvas`, over the real `WorkingSetService`.

Before it, a mark lived only in the store: the canvas began with none, so after a reload the menu
offered the mark again, and choosing it overwrote the analyst's reason. What these prove, and the
mistake each catches:

- a mark on a node of the canvas comes back with its reason
  (`test_a_mark_on_the_canvas_comes_back_with_its_reason`);
- a mark on a node the reader may not see is never asked about, so neither its reason nor its
  existence reaches them (rules 3 and 4;
  `test_a_mark_on_a_node_the_reader_may_not_see_is_never_asked_about`);
- a mark on a node off this canvas is not this canvas's
  (`test_a_mark_on_a_node_off_the_canvas_is_not_named`).

The marks store stands in, and like the real `marked_among` it refuses nothing: it answers for any
id it is given, which is exactly why the ids it is given must already be the reader's own.
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.api.suppression import SuppressionMark, marks_on_the_canvas
from services.api.working_set.service import WorkingSetService

from ontology.handling import load_uk_le_scheme
from schemas.domain import (
    AuditStub,
    Handling,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
)

from .fakes import FakeGraphPort, FakeWorkingSetStore

SCHEME = load_uk_le_scheme()
INVESTIGATION = "inv-1"
CLEARED = Principal(id="analyst-1", clearance="SECRET", org_unit="u")
NOT_CLEARED = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="u")


def _person(node_id: str, classification: str = "OFFICIAL") -> Node:
    return Node(
        id=node_id,
        type="Person",
        properties={},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="d", locator="l", excerpt_hash="")],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        handling=Handling(
            classification=classification, handling_code="P", originator="u", owning_unit="u"
        ),
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="analyst-1"),
    )


class _Marks:
    """Every mark in the store, answered for any id asked, as the real `marked_among` does."""

    def __init__(self, *node_ids: str) -> None:
        self.held = {
            n: SuppressionMark(
                node_id=n,
                investigation_id=INVESTIGATION,
                marked_by="analyst-1",
                marked_at=datetime(2026, 11, 14, tzinfo=UTC),
                reason=f"why {n}",
            )
            for n in node_ids
        }
        self.asked: list[list[str]] = []

    async def marked_among(self, node_ids: list[str]) -> dict[str, SuppressionMark]:
        self.asked.append(list(node_ids))
        return {n: self.held[n] for n in node_ids if n in self.held}


async def _canvas(*nodes: Node) -> WorkingSetService:
    graph = FakeGraphPort(Subgraph(nodes=[], edges=[]), graph_nodes=list(nodes), graph_edges=[])
    service = WorkingSetService(graph, FakeWorkingSetStore(), SCHEME)
    await service.seed(INVESTIGATION, list(nodes), [], CLEARED)
    return service


async def test_a_mark_on_the_canvas_comes_back_with_its_reason() -> None:
    service = await _canvas(_person("p-a"), _person("p-b"))
    found = await marks_on_the_canvas(service, _Marks("p-b"), INVESTIGATION, NOT_CLEARED)
    assert [(m.node_id, m.reason) for m in found] == [("p-b", "why p-b")]


async def test_a_mark_on_a_node_the_reader_may_not_see_is_never_asked_about() -> None:
    service = await _canvas(_person("p-a"), _person("p-z", classification="SECRET"))
    marks = _Marks("p-a", "p-z")
    found = await marks_on_the_canvas(service, marks, INVESTIGATION, NOT_CLEARED)
    assert [m.node_id for m in found] == ["p-a"]
    assert marks.asked == [["p-a"]]
    # The cleared reader, on the same canvas, is given both.
    cleared = await marks_on_the_canvas(service, marks, INVESTIGATION, CLEARED)
    assert [m.node_id for m in cleared] == ["p-a", "p-z"]


async def test_a_mark_on_a_node_off_the_canvas_is_not_named() -> None:
    service = await _canvas(_person("p-a"))
    marks = _Marks("p-a", "p-elsewhere")
    found = await marks_on_the_canvas(service, marks, INVESTIGATION, CLEARED)
    assert [m.node_id for m in found] == ["p-a"]
    assert marks.asked == [["p-a"]]
