"""A drawn item needs a source note, a document only added to it (ADR-143 Amendment 8 items 5, 7
and 10; slice GG4b, rows 9 and 13 of its table, and the owner's rulings on its questions 2 and 3),
through the real app over `board_fakes.BoardGraph`.

**A** is Alice (SECRET), who draws; **B** is Bob (OFFICIAL). An item "drawn before" has a
document and no note, in the shape the board service wrote it then.

What fails if the rule is wrong (each shown red with its fault planted,
`process/lanes/v062/GG4b_RED_RECORD.md`):

- a new item or link with a document and no note made (row 9): red with the old body rule kept;
- an edit leaving an item with no note, or an older item edited without gaining one: red with the
  edit's old rule;
- an author who may no longer read a document erasing it by changing a label: red with the edit's
  read not keeping cited documents;
- the check at promotion passing an item with no note, or answering by who asks: red with the old
  check.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from schemas.domain import AuditStub, Handling, Node, Provenance, ProvenanceState, SourceRef

from .test_boards import K, _as, _board, _item, _link, world  # noqa: F401 (a fixture)
from .test_promotions import _sheet, pw  # noqa: F401 (a fixture)

BOARD_LOCATOR = "a drawing board of the case"
D, D2 = "doc-sealed-statement", "doc-second-statement"
NO_NOTE = "It has no source note."


def _document(graph: Any, document_id: str, marking: str, code: str = "P") -> None:
    when = datetime(2026, 11, 1, tzinfo=UTC)
    graph._graph_nodes[document_id] = Node(
        id=document_id,
        type="Document",
        properties={"title": "statement.txt"},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="files/s.txt", locator="whole", excerpt_hash="")],
            first_seen=when,
        ),
        handling=Handling(
            classification=marking, handling_code=code, originator="unit-1", owning_unit="unit-1"
        ),
        audit=AuditStub(created_at=when, created_by="eng"),
        datasets=["src"],
    )


def _drawn_before(graph: Any, element_id: str, document: str) -> None:
    """The stored item as an item drawn before the amendment is stored: a document, no note."""
    held = graph.node(element_id)
    assert held.provenance.drawn is not None
    graph._graph_nodes[element_id] = held.model_copy(
        update={
            "provenance": held.provenance.model_copy(
                update={
                    "sources": [
                        SourceRef(document_id=document, locator=BOARD_LOCATOR, excerpt_hash="")
                    ],
                    "drawn": held.provenance.drawn.model_copy(
                        update={"source_note": None, "source_document": document}
                    ),
                }
            )
        }
    )


def _stored(graph: Any, element_id: str) -> tuple[str | None, str | None, list[str]]:
    held = graph.node(element_id)
    drawn = held.provenance.drawn
    return (
        drawn.source_note,
        drawn.source_document,
        [s.document_id for s in held.provenance.sources],
    )


def _edit(item_id: str, **body: Any) -> Any:
    return _as("alice").patch(f"/v1/investigations/{K}/board-items/{item_id}", json=body)


# --- row 9: a new item or link --------------------------------------------------------------


@pytest.mark.parametrize("note", [None, "  "], ids=["no-note", "blank"])
def test_a_new_item_or_link_with_a_document_and_no_note_is_refused_by_the_bodys_validation(
    world: SimpleNamespace,  # noqa: F811
    note: str | None,
) -> None:
    _document(world.graph, D, "OFFICIAL")
    board = _board(start="selection", node_ids=["p-loaded"])
    drawn = _item(board, source_document=D)["element_id"]
    written = (len(world.graph.node_writes), len(world.graph.edge_writes))
    body = {
        "type": "Person",
        "label": "Tall",
        "marking": "OFFICIAL",
        "grading": {"source": "B", "intelligence": "2", "handling": "1"},
        "properties": {"family_name": "Tall"},
        "source_note": note,
        "source_document": D,
    }

    item = _as("alice").post(f"/v1/investigations/{K}/boards/{board}/items", json=body)
    link = _link(board, drawn, "p-loaded", source_note=note, source_document=D)

    for refused in (item, link):
        assert refused.status_code == 422, refused.text
        # FastAPI's own answer to a body its model refuses: a list, with no error code.
        assert list(refused.json()) == ["detail"]
        assert "give a source note" in refused.json()["detail"][0]["msg"]
    assert (len(world.graph.node_writes), len(world.graph.edge_writes)) == written


# --- question 2: an edit ---------------------------------------------------------------------


def test_an_item_drawn_before_gains_its_note_at_its_next_edit(
    world: SimpleNamespace,  # noqa: F811
) -> None:
    _document(world.graph, D, "OFFICIAL")
    made = _item(_board(), source_document=D)
    _drawn_before(world.graph, made["element_id"], D)

    refused = _edit(made["item_id"], label="Tall man")

    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == "no_source"
    assert "needs a source note" in refused.json()["detail"]
    assert _stored(world.graph, made["element_id"]) == (None, D, [D])

    noted = _edit(made["item_id"], label="Tall man", source_note="Wing officer, 4 Nov")

    assert noted.status_code == 200, noted.text
    assert _stored(world.graph, made["element_id"]) == ("Wing officer, 4 Nov", D, [D])


def test_an_edit_that_would_blank_the_note_is_refused(world: SimpleNamespace) -> None:  # noqa: F811
    _document(world.graph, D, "OFFICIAL")
    made = _item(_board(), source_document=D)

    refused = _edit(made["item_id"], source_note="  ")

    assert refused.status_code == 422 and refused.json()["error"] == "no_source", refused.text


# --- item 5: what is stored is kept whole ----------------------------------------------------


def test_an_author_who_may_no_longer_read_the_document_does_not_erase_it_by_editing(
    world: SimpleNamespace,  # noqa: F811
) -> None:
    """The edit keeps the stored ids: it reads the item with its cited documents left in."""
    _document(world.graph, D, "OFFICIAL")
    board = _board()
    made = _item(board, source_document=D)
    # Re-marked above her: restricted to named recipients (SECRET is the scheme's top).
    _document(world.graph, D, "SECRET", "R")
    assert D not in _as("alice").get(f"/v1/investigations/{K}/boards/{board}").text

    edited = _edit(made["item_id"], label="Tall man")

    assert edited.status_code == 200, edited.text
    assert _stored(world.graph, made["element_id"]) == ("Wing officer report, 4 Nov", D, [D])
    assert D not in edited.text


def test_changing_an_items_document_leaves_the_old_id_stored_and_each_is_judged_by_itself(
    world: SimpleNamespace,  # noqa: F811
) -> None:
    """The finding round 1 read from the code: an edit changes the assertion and leaves the
    stored sources naming the old document. The stored ids are kept; a reader is sent neither
    they may not read."""
    _document(world.graph, D, "OFFICIAL-SENSITIVE")
    _document(world.graph, D2, "OFFICIAL")
    board = _board()
    made = _item(board, source_document=D)

    edited = _edit(made["item_id"], source_document=D2)

    assert edited.status_code == 200, edited.text
    assert _stored(world.graph, made["element_id"]) == ("Wing officer report, 4 Nov", D2, [D])
    assert _as("alice").post(f"/v1/investigations/{K}/boards/{board}/share").status_code == 200
    bob = _as("bob").get(f"/v1/investigations/{K}/boards/{board}")
    assert D not in bob.text
    (node,) = bob.json()["nodes"]
    assert node["provenance"]["drawn"]["source_document"] == D2
    assert [s["document_id"] for s in node["provenance"]["sources"]] == [f"drawn:{made['item_id']}"]


# --- question 3: promotion --------------------------------------------------------------------


def test_promotion_asks_for_a_note_whoever_asks(pw: SimpleNamespace) -> None:  # noqa: F811
    """Item 10: an item sourced by a document alone fails the check, whether the reader asking
    may read the document or not; with a note it passes either way."""
    _document(pw.graph, D, "OFFICIAL")
    board = _board()
    made = _item(board, source_document=D)

    def problems() -> list[str]:
        (item,) = _sheet(board)["items"]
        return list(item["problems"])

    assert problems() == []
    _document(pw.graph, D, "SECRET", "R")  # now above the one asking
    assert problems() == []

    _drawn_before(pw.graph, made["element_id"], D)
    assert problems() == [NO_NOTE]
    _document(pw.graph, D, "OFFICIAL")  # and readable again: the same answer
    assert problems() == [NO_NOTE]
