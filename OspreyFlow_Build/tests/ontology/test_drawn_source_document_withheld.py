"""ADR-143 Amendment 8 (slice GG4b, a security part): a drawn item's source document is told only to
a reader who may read it when it is sent (rules 3 and 4).

The readers: **A** drew an item citing document **D**; **B** reads the case but may not read D;
**C** reads the case and may read D. "May read" is decided when the item is sent: the batched read's
result, the cited documents this reader may read, is passed to
`ontology.handling.withhold_sources`, which stays a pure function and, given no result, withholds
every cited document.

Over `withhold_sources` (rows 1 to 3, 7, 8, 10 and 13 of the slice's table), and rows 1 to 3 again
through the boards service, over `tests/services/api/board_fakes.py`, whose fake document store
answers the reader's read as the adapter does. Every drawn provenance here is built by the board
service's own writer (`Boards._provenance`), so it has the shape the code writes (rule 15).

What fails if the rule is wrong, and the planted fault that showed each row red
(`process/lanes/v062/GG4b_RED_RECORD.md`):

- B sent D in either place: row 1 and row 7, red on the code as it stood;
- C not sent D: row 2, red with C's read skipped and the id kept from the author's check alone;
- A not sent D while A may read it, or sent it once A may not: row 3, red with the author's case
  inverted, and on the code as it stood;
- a note-only item changed: row 8, red with the note blanked too;
- an older item with a document and no note telling B more than an empty note: row 10;
- an item edited from one document to another sending B either: red with only the current one
  blanked;
- a read written back losing D: row 13, red with `sources_in_full()` ignored by the new rule.
"""

from __future__ import annotations

import inspect
from collections.abc import Container, Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from services.api.boards import Boards

from ontology import handling
from ontology.handling import sources_in_full, withhold_sources
from schemas.domain import (
    AuditStub,
    DrawnAssertion,
    Edge,
    Grading,
    Handling,
    Node,
    Principal,
    Provenance,
    SourceRef,
)
from tests.services.api.test_boards import (  # noqa: F401 (`world` is a fixture)
    PEOPLE,
    K,
    _as,
    _board,
    _item,
    _link,
    world,
)

LAYER, SOURCE_DATASET = "layer-k", "src"
D, D2 = "doc-sealed-statement", "doc-second-statement"
BOARD_LOCATOR = "a drawing board of the case"
NOTE = "Seen from the harbour wall"


def _reader(who: str, clearance: str) -> Principal:
    return Principal(
        id=who, clearance=clearance, org_unit="unit-1", datasets=[SOURCE_DATASET, LAYER]
    )


A = _reader("acct-a", "SECRET")
B = _reader("acct-b", "OFFICIAL")
C = _reader("acct-c", "SECRET")

#: Whether `withhold_sources` takes the batch's result. On the code as it stood it does not, and
#: is called as it was, so that each row is red there for what it claims, not a missing argument.
_TAKES_THE_READ = "readable_documents" in inspect.signature(withhold_sources).parameters


def _sent(element: Any, reader: Principal, readable: Container[str] | None = None) -> Any:
    """`element` as a read path sends it to `reader`, `readable` being the batched read's result."""
    if _TAKES_THE_READ:
        return withhold_sources(element, reader, readable)
    return withhold_sources(element, reader)


def _written(item_id: str, note: str | None, document: str | None) -> Provenance:
    """A drawn item's provenance exactly as the board service writes it. An item drawn before the
    amendment may have a document and no note, which the same writer wrote."""
    given = SimpleNamespace(
        label="Unknown male",
        grading=Grading(source="B", intelligence="2", handling="1"),
        source_note=note,
        source_document=document,
    )
    board: Any = SimpleNamespace(id="board-a", case_id="case-k")
    return Boards._provenance(None, item_id, board, A, given)  # type: ignore[arg-type]


def _common(provenance: Provenance, datasets: Sequence[str]) -> dict[str, Any]:
    return {
        "provenance": provenance,
        "handling": Handling(
            classification="OFFICIAL",
            handling_code="P",
            originator="unit-1",
            owning_unit="unit-1",
        ),
        "audit": AuditStub(created_at=datetime(2026, 11, 1, tzinfo=UTC), created_by=A.id),
        "datasets": list(datasets),
    }


def _node(provenance: Provenance, datasets: Sequence[str] = (LAYER,)) -> Node:
    return Node(id="n-drawn", type="Person", **_common(provenance, datasets))


def _edge(provenance: Provenance, datasets: Sequence[str] = (LAYER,)) -> Edge:
    return Edge(
        id="e-drawn",
        type="ASSOCIATE_OF",
        source="n-drawn",
        target="n-loaded",
        **_common(provenance, datasets),
    )


KINDS = pytest.mark.parametrize("make", [_node, _edge], ids=["node", "link"])


def _drawn(element: Any) -> DrawnAssertion:
    assert element.provenance.drawn is not None
    return element.provenance.drawn


def _placeholder(item_id: str) -> SourceRef:
    """The source of an item drawn from a note alone."""
    return SourceRef(document_id=f"drawn:{item_id}", locator=BOARD_LOCATOR, excerpt_hash="")


def _names(element: Any, document: str) -> bool:
    return document in element.model_dump_json()


# --- rows 1 and 7 -----------------------------------------------------------------------------


@KINDS
def test_a_drawn_items_source_document_is_not_sent_to_a_reader_who_may_not_read_it(
    make: Any,
) -> None:
    """Rows 1 and 7: B is sent the drawn node, and the drawn link, with D in neither place."""
    stored = make(_written("i-1", NOTE, D))

    sent = _sent(stored, B, readable=frozenset())

    assert not _names(sent, D)
    assert _drawn(sent).source_document is None
    assert sent.provenance.sources == [_placeholder("i-1")]
    assert _drawn(sent).source_note == NOTE
    # Nothing stored is changed: the next reader's own read decides again.
    assert _drawn(stored).source_document == D
    assert [s.document_id for s in stored.provenance.sources] == [D]


@KINDS
def test_given_no_read_every_cited_document_is_withheld(make: Any) -> None:
    """A caller that made no read fails closed, whoever the reader is: C and A too."""
    stored = make(_written("i-1", NOTE, D))

    for reader in (A, B, C):
        assert not _names(withhold_sources(stored, reader), D), reader.id


@KINDS
def test_where_the_sources_are_withheld_the_assertion_names_no_document_either(make: Any) -> None:
    """A reader whose case reads only one of the element's datasets is sent no source; before, the
    assertion's `source_document` still named D to them."""
    stored = make(_written("i-1", NOTE, D), datasets=(LAYER, "another-dataset"))

    sent = _sent(stored, B, readable=frozenset())

    assert sent.provenance.sources_withheld is True and sent.provenance.sources == []
    assert not _names(sent, D)


# --- rows 2 and 3 -----------------------------------------------------------------------------


@KINDS
def test_a_reader_who_may_read_the_document_is_sent_it(make: Any) -> None:
    """Row 2: C is sent D in both places, as before."""
    stored = make(_written("i-1", NOTE, D))

    sent = _sent(stored, C, readable=frozenset({D}))

    assert _drawn(sent).source_document == D
    assert [s.document_id for s in sent.provenance.sources] == [D]
    assert _drawn(sent).source_note == NOTE


@KINDS
def test_the_author_keeps_the_document_only_while_the_author_may_read_it(make: Any) -> None:
    """Row 3: A is sent D while A may read it, and is not sent it once A may not: the author's own
    check at drawing is never relied on."""
    stored = make(_written("i-1", NOTE, D))

    kept = _sent(stored, A, readable=frozenset({D}))
    assert _drawn(kept).source_document == D
    assert [s.document_id for s in kept.provenance.sources] == [D]
    assert _drawn(kept).board_id == "board-a"

    gone = _sent(stored, A, readable=frozenset())
    assert not _names(gone, D)
    assert _drawn(gone).board_id == "board-a"


# --- every document the board cited -----------------------------------------------------------


def _edited(item_id: str, first: str, then: str) -> Provenance:
    """An item drawn citing `first`, then edited to cite `then`: an edit changes the assertion and
    leaves the stored sources as they were."""
    before = _written(item_id, NOTE, first)
    assert before.drawn is not None
    return before.model_copy(
        update={"drawn": before.drawn.model_copy(update={"source_document": then})}
    )


@KINDS
def test_an_item_edited_from_one_document_to_another_sends_neither_to_who_may_read_neither(
    make: Any,
) -> None:
    sent = _sent(make(_edited("i-1", D, D2)), B, readable=frozenset())

    assert not _names(sent, D) and not _names(sent, D2)
    assert _drawn(sent).source_document is None
    assert sent.provenance.sources == [_placeholder("i-1")]


@KINDS
def test_each_cited_document_is_judged_by_itself(make: Any) -> None:
    stored = make(_edited("i-1", D, D2))

    only_the_new = _sent(stored, C, readable=frozenset({D2}))
    assert not _names(only_the_new, D)
    assert _drawn(only_the_new).source_document == D2
    assert only_the_new.provenance.sources == [_placeholder("i-1")]

    only_the_old = _sent(stored, C, readable=frozenset({D}))
    assert not _names(only_the_old, D2)
    assert _drawn(only_the_old).source_document is None
    assert [s.document_id for s in only_the_old.provenance.sources] == [D]


@KINDS
def test_the_sources_sent_do_not_say_how_many_documents_were_withheld(make: Any) -> None:
    """Two withheld documents, or one beside the note's own source, are one `drawn:<item_id>`."""
    two = _written("i-1", NOTE, D)
    two = two.model_copy(
        update={
            "sources": [
                *two.sources,
                SourceRef(document_id=D2, locator=BOARD_LOCATOR, excerpt_hash=""),
            ]
        }
    )
    beside = two.model_copy(update={"sources": [_placeholder("i-1"), two.sources[0]]})

    for stored in (make(two), make(beside)):
        assert _sent(stored, B, readable=frozenset()).provenance.sources == [_placeholder("i-1")]


@KINDS
def test_a_source_the_board_did_not_write_is_left_as_it_was(make: Any) -> None:
    """A loaded row's source merged onto a promoted drawn element names no board and is not judged:
    the source references of what was not drawn are not this rule's."""
    row = SourceRef(document_id="files/register.csv", locator="row 4", excerpt_hash="a" * 64)
    provenance = _written("i-1", NOTE, D)
    provenance = provenance.model_copy(update={"sources": [*provenance.sources, row]})

    sent = _sent(make(provenance), B, readable=frozenset())

    assert sent.provenance.sources == [_placeholder("i-1"), row]


# --- row 8 ------------------------------------------------------------------------------------


@KINDS
def test_an_item_drawn_from_a_note_alone_is_the_same_for_every_reader(make: Any) -> None:
    stored = make(_written("i-1", NOTE, None))

    for reader in (A, B, C):
        sent = _sent(stored, reader, readable=frozenset())
        assert _drawn(sent).source_note == NOTE, reader.id
        assert _drawn(sent).source_document is None
        assert sent.provenance.sources == [_placeholder("i-1")]
        assert sent.provenance.sources_withheld is False


# --- row 10 -----------------------------------------------------------------------------------


@KINDS
@pytest.mark.parametrize("note", [None, "", "  "], ids=["no-note", "empty", "blank"])
def test_an_older_item_with_a_document_and_no_note_is_sent_with_neither(
    make: Any, note: str | None
) -> None:
    """Row 10: B is sent no note and no document, the same on the wire whatever empty note was
    stored, so the screens say the one sentence they say for any empty note. The wire shape is a
    `DrawnAssertion` as it is read (Amendment 8 item 8)."""
    stored = make(_written("i-1", note, D))

    sent = _sent(stored, B, readable=frozenset())

    assert not _names(sent, D)
    assert _drawn(sent).source_note is None
    assert _drawn(sent).source_document is None
    empty = _written("i-1", "x", None)
    assert empty.drawn is not None
    expected = empty.model_copy(
        update={
            "drawn": empty.drawn.model_copy(update={"source_note": None, "board_id": ""}),
            "first_seen": stored.provenance.first_seen,
        }
    )
    assert sent.provenance.model_dump_json() == expected.model_dump_json()
    # What is sent is read back as it is: no rule of the read model asks for a source.
    Provenance.model_validate_json(sent.provenance.model_dump_json())


# --- row 13 -----------------------------------------------------------------------------------


@KINDS
def test_a_read_written_back_keeps_the_document(make: Any) -> None:
    stored = make(_written("i-1", NOTE, D))

    with sources_in_full():
        assert _sent(stored, B, readable=frozenset()) is stored


# --- the one batched read ---------------------------------------------------------------------


class _Documents:
    """A document store answering a reader's read as the adapter does: of the ids asked, the
    elements this reader may read, whatever their type."""

    def __init__(self, held: dict[str, tuple[str, str]]) -> None:
        #: id to (type, marking).
        self.held = held
        self.asked: list[tuple[list[str], str]] = []
        self.fails = False

    async def read(self, ids: Sequence[str], principal: Principal) -> list[Node]:
        self.asked.append((list(ids), principal.id))
        if self.fails:
            raise ConnectionError("the store is unreachable")
        scheme = handling.load_uk_le_scheme()
        return [
            Node(
                id=i,
                type=self.held[i][0],
                **{
                    **_common(_written("i-doc", NOTE, None), (SOURCE_DATASET,)),
                    "handling": Handling(
                        classification=self.held[i][1],
                        handling_code="P",
                        originator="unit-1",
                        owning_unit="unit-1",
                    ),
                },
            )
            for i in ids
            if i in self.held and scheme.clears(principal.clearance, self.held[i][1])
        ]


def _batched_read() -> Any:
    read = getattr(handling, "readable_cited_documents", None)
    assert read is not None, "there is no batched read of the documents an answer's items cite"
    return read


async def test_one_read_asks_for_every_document_an_answer_cites_with_the_reader() -> None:
    store = _Documents({D: ("Document", "SECRET"), D2: ("Document", "OFFICIAL")})
    answer = [_node(_written("i-1", NOTE, D)), _edge(_written("i-2", NOTE, D2))]
    answer += [_node(_written(f"i-{n}", NOTE, D)) for n in range(3, 40)]

    assert await _batched_read()(answer, C, store.read) == {D, D2}
    assert await _batched_read()(answer, B, store.read) == {D2}
    assert store.asked == [(sorted([D, D2]), C.id), (sorted([D, D2]), B.id)]


async def test_an_answer_that_cites_nothing_makes_no_read() -> None:
    store = _Documents({})

    assert await _batched_read()([_node(_written("i-1", NOTE, None))], C, store.read) == set()
    assert store.asked == []


async def test_a_read_that_fails_keeps_nothing() -> None:
    store = _Documents({D: ("Document", "OFFICIAL")})
    store.fails = True

    assert await _batched_read()([_node(_written("i-1", NOTE, D))], C, store.read) == set()


async def test_only_a_document_is_kept() -> None:
    """The question drawing asks: an element the reader reads **and** that is a Document."""
    store = _Documents({D: ("Person", "OFFICIAL")})

    assert await _batched_read()([_node(_written("i-1", NOTE, D))], C, store.read) == set()


# --- rows 1 to 3 through the boards service ---------------------------------------------------

THROUGH = "doc-through-the-boards"


def _document_node(marking: str, code: str = "P") -> Node:
    return Node(
        id=THROUGH,
        type="Document",
        properties={"title": "statement.txt"},
        **{
            **_common(_written("i-doc", NOTE, None), (SOURCE_DATASET,)),
            "handling": Handling(
                classification=marking,
                handling_code=code,
                originator="unit-1",
                owning_unit="unit-1",
            ),
            "provenance": Provenance(
                state="asserted",  # type: ignore[arg-type]
                sources=[SourceRef(document_id="files/s.txt", locator="whole", excerpt_hash="")],
                first_seen=datetime(2026, 11, 1, tzinfo=UTC),
            ),
        },
    )


def _cited(opened: dict[str, Any], element_id: str) -> tuple[str | None, list[str]]:
    """The two places an opened board names a drawn element's document."""
    (element,) = [e for e in [*opened["nodes"], *opened["edges"]] if e["id"] == element_id]
    return (
        element["provenance"]["drawn"].get("source_document"),
        [s["document_id"] for s in element["provenance"]["sources"]],
    )


def test_through_the_boards_service_the_document_reaches_only_a_reader_who_may_read_it(
    world: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rows 1 to 3 on the board route. A is Alice (SECRET), B is Bob (OFFICIAL), C is Cleo
    (SECRET), a Viewer of the case who did not draw."""
    monkeypatch.setitem(
        PEOPLE,
        "cleo",
        Principal(id="cleo", clearance="SECRET", org_unit="unit-1", roles=["analyst"]),
    )
    world.cases.grants[K]["cleo"] = world.cases.grants[K]["rita"]
    world.graph._graph_nodes[THROUGH] = _document_node("OFFICIAL-SENSITIVE")
    board = _board(start="selection", node_ids=["p-loaded"])
    node_id = _item(board, source_document=THROUGH)["element_id"]
    linked = _link(board, node_id, "p-loaded", source_document=THROUGH)
    assert linked.status_code == 201, linked.text
    link_id = linked.json()["element_id"]
    shared = _as("alice").post(f"/v1/investigations/{K}/boards/{board}/share")
    assert shared.status_code == 200, shared.text

    def opened(who: str) -> Any:
        answer = _as(who).get(f"/v1/investigations/{K}/boards/{board}")
        assert answer.status_code == 200, answer.text
        return answer

    # Row 1: B is sent both items, with the document in neither place.
    bob = opened("bob")
    assert {node_id, link_id} <= set(bob.json()["drawn"])
    assert THROUGH not in bob.text
    for element_id in (node_id, link_id):
        item_id = bob.json()["items"][element_id]
        assert _cited(bob.json(), element_id) == (None, [f"drawn:{item_id}"])
    # Rows 2 and 3: C and A are sent it.
    for who in ("cleo", "alice"):
        body = opened(who).json()
        for element_id in (node_id, link_id):
            assert _cited(body, element_id) == (THROUGH, [THROUGH]), who
    # Re-marked after drawing, by any path: the next send catches it, for the author too.
    # Restricted to named recipients, which neither of them is: SECRET is the scheme's top.
    world.graph._graph_nodes[THROUGH] = _document_node("SECRET", "R")
    for who in ("cleo", "alice"):
        assert THROUGH not in opened(who).text, who
