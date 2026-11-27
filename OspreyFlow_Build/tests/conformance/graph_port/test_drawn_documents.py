"""`GraphPort` conformance: a drawn node's and a drawn link's source document is sent only to a
reader who may read it (ADR-143 Amendment 8 items 1 to 6; slice GG4b, a security part; rules 3
and 4).

**A** drew an item citing document **D**, marked above **B**'s clearance. **B** reads the case but
may not read D; **C** reads the case and may read D. Rows 1 and 7 of the slice's table, through
every adapter read that returns a node or a link: `get_node`, `get_nodes`, `get_edges`, `find_node`,
`search_nodes`, `suggest_nodes`, `suggest_locations`, `list_nodes`, `expand`, `edges_among`,
`paths`, `paths_at_length`, `match`, `most_connected`, `busiest_links`, `recently_confirmed` and
`shared_contacts`. B is sent each drawn element with D in neither place; C is sent D in both. A
re-marking by a later write is caught by the next read, and a read written back
(`sources_in_full`) keeps D. B's answers have the same shape whether D is hidden from them or does
not exist (rule 3).

Written before the adapter was changed (rule 1), and red against it: every read sent B the id.
Needs a live ArcadeDB (`make conformance` runs the directory).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from services.api.boards import Boards

from conduit_common.identity import new_edge_id, new_node_id, now_utc
from ontology.handling import sources_in_full
from ports.graph import GraphPort
from schemas.domain import (
    Edge,
    EdgeWrite,
    ExpandRequest,
    Grading,
    Handling,
    Node,
    NodeWrite,
    PathRequest,
    PatternNode,
    PatternQuery,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory

pytestmark = [
    pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str),
    pytest.mark.usefixtures("_sweep_stale_conformance_databases"),
]

SOURCE_DATASET = "source-dataset"
LAYER = "analyst-layer-case-a"
BOARD_LOCATOR = "a drawing board of the case"
WHEN = datetime(2026, 11, 1, tzinfo=UTC)
NINO = "QQ123456C"
FAMILY = "Quillfeather"
PLACE = "Quillfeather Wharf"


def _reader(who: str, clearance: str) -> Principal:
    return Principal(
        id=who, clearance=clearance, org_unit="unit-1", datasets=[SOURCE_DATASET, LAYER]
    )


A = _reader("analyst-a", "SECRET")
B = _reader("analyst-b", "OFFICIAL")
C = _reader("analyst-c", "SECRET")


def _handling(classification: str, code: str = "P") -> Handling:
    return Handling(
        classification=classification, handling_code=code, originator="unit-1", owning_unit="unit-1"
    )


def _loaded_provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="files/register.csv", locator="row 1", excerpt_hash="")],
        first_seen=WHEN,
    )


def _drawn_provenance(item_id: str, document: str, *, confirmed: bool = False) -> Provenance:
    """As the board service writes a drawn item's (`Boards._provenance`): the document in the
    assertion and as the board's own source."""
    given = SimpleNamespace(
        label="Unknown male",
        grading=Grading(source="B", intelligence="2", handling="1"),
        source_note="Seen from the quay",
        source_document=document,
    )
    board: Any = SimpleNamespace(id="board-a", case_id="case-a")
    written = Boards._provenance(None, item_id, board, A, given)  # type: ignore[arg-type]
    if confirmed:
        return written.model_copy(update={"last_confirmed": WHEN, "confirmed_by": A.id})
    return written


def _node(
    node_type: str,
    provenance: Provenance,
    *,
    classification: str = "OFFICIAL",
    datasets: tuple[str, ...] = (LAYER,),
    **properties: Any,
) -> NodeWrite:
    return NodeWrite(
        id=new_node_id(),
        type=node_type,
        properties=properties,
        provenance=provenance,
        handling=_handling(classification),
        created_by=A.id,
        created_at=now_utc(),
        datasets=list(datasets),
    )


def _link(source: str, target: str, provenance: Provenance, datasets: tuple[str, ...]) -> EdgeWrite:
    return EdgeWrite(
        id=new_edge_id(),
        type="ASSOCIATE_OF",
        source=source,
        target=target,
        provenance=provenance,
        handling=_handling("OFFICIAL"),
        created_by=A.id,
        created_at=now_utc(),
        datasets=list(datasets),
    )


async def _write(graph: GraphPort, nodes: list[NodeWrite], edges: list[EdgeWrite]) -> None:
    tx = await graph.begin_transaction()
    await graph.upsert_nodes(nodes, tx)
    if edges:
        await graph.upsert_edges(edges, tx)
    await graph.commit_transaction(tx)


async def _world(graph: GraphPort, document_id: str | None = None) -> SimpleNamespace:
    """Two loaded people, `a` and `b`; the document D (SECRET, in the source); a drawn person `c`
    and a drawn place, each citing D; a loaded link a to b and a drawn link c to b citing D. With
    `document_id`, the items cite that id instead, and no D is written."""
    document = _node(
        "Document",
        _loaded_provenance(),
        classification="SECRET",
        datasets=(SOURCE_DATASET,),
        title="Sealed statement",
    )
    cited = document_id or document.id
    a = _node("Person", _loaded_provenance(), datasets=(SOURCE_DATASET,), family_name="Mercer")
    b = _node("Person", _loaded_provenance(), datasets=(SOURCE_DATASET,), family_name="Ward")
    c = _node(
        "Person", _drawn_provenance("item-c", cited, confirmed=True), family_name=FAMILY, nino=NINO
    )
    place = _node("Location", _drawn_provenance("item-p", cited), name=PLACE)
    ab = _link(a.id, b.id, _loaded_provenance(), (SOURCE_DATASET,))
    cb = _link(c.id, b.id, _drawn_provenance("item-cb", cited), (LAYER,))
    documents = [] if document_id else [document]
    await _write(graph, [*documents, a, b, c, place], [ab, cb])
    return SimpleNamespace(
        d=cited, a=a.id, b=b.id, c=c.id, place=place.id, cb=cb.id, document=document
    )


async def _every_read(
    graph: GraphPort, held: SimpleNamespace, reader: Principal
) -> dict[str, list[Node | Edge]]:
    """Each adapter read that returns an element, and what it returned, by the read's name."""
    got = await graph.get_node(held.c, reader)
    found = await graph.find_node("Person", "nino", NINO, reader)
    paths = await graph.paths(PathRequest(source=held.a, target=held.c), reader)
    routes = await graph.paths_at_length(held.a, held.c, 2, 5, reader)
    expanded = await graph.expand(ExpandRequest(node_ids=[held.c]), reader)
    ranked = await graph.most_connected(reader, limit=50)
    busy = await graph.busiest_links(reader, limit=50)
    confirmed = await graph.recently_confirmed(reader, limit=50)
    shared = await graph.shared_contacts(held.a, reader, edge_type="ASSOCIATE_OF", min_shared=1)
    matched = await graph.match(
        PatternQuery(nodes=[PatternNode(var="p", entity_type="Person")], edges=[]), reader
    )
    return {
        "get_node": [got] if got is not None else [],
        "get_nodes": list(await graph.get_nodes([held.c, held.place, held.a], reader)),
        "get_edges": list(await graph.get_edges([held.cb], reader)),
        "find_node": [found] if found is not None else [],
        "search_nodes": list(await graph.search_nodes(NINO, reader)),
        "suggest_nodes": list((await graph.suggest_nodes(FAMILY[:5], reader)).nodes),
        "suggest_locations": list(await graph.suggest_locations(PLACE[:5], reader)),
        "list_nodes": list((await graph.list_nodes("Person", reader)).nodes),
        "expand": [*expanded.nodes, *expanded.edges],
        "edges_among": list(await graph.edges_among([held.c, held.b], reader)),
        "paths": [x for p in paths for x in (*p.nodes, *p.edges)],
        "paths_at_length": [x for p in routes.paths for x in (*p.nodes, *p.edges)],
        "match": list(matched.nodes),
        "most_connected": [r.node for r in ranked.nodes],
        "busiest_links": [x for r in busy.links for x in (r.edge, r.source, r.target)],
        "recently_confirmed": [n.node for n in confirmed.nodes],
        "shared_contacts": [s.node for s in shared.contacts],
    }


def _drawn(elements: Iterable[Node | Edge]) -> list[Node | Edge]:
    return [e for e in elements if e.provenance.drawn is not None]


def _without_the_document(element: Node | Edge, document: str) -> bool:
    drawn = element.provenance.drawn
    assert drawn is not None
    return (
        document not in element.model_dump_json()
        and drawn.source_document is None
        and element.provenance.sources
        == [SourceRef(document_id=f"drawn:{drawn.item_id}", locator=BOARD_LOCATOR, excerpt_hash="")]
    )


def _with_the_document(element: Node | Edge, document: str) -> bool:
    drawn = element.provenance.drawn
    assert drawn is not None
    return drawn.source_document == document and [
        s.document_id for s in element.provenance.sources
    ] == [document]


async def test_every_read_sends_a_drawn_items_document_only_to_a_reader_who_may_read_it(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as graph:
        held = await _world(graph)
        for reader, check in ((B, _without_the_document), (C, _with_the_document)):
            for read, elements in (await _every_read(graph, held, reader)).items():
                drawn = _drawn(elements)
                assert drawn, f"{read} returned no drawn element to {reader.id}"
                wrong = [e.id for e in drawn if not check(e, held.d)]
                assert wrong == [], f"{read}, as {reader.id}"


async def test_a_document_re_marked_after_drawing_is_caught_by_the_next_read(
    factory: GraphAdapterFactory,
) -> None:
    """Ruling 4 (b): no sweep; the read itself catches it, whatever re-marked the document, for
    the author as for anyone."""
    async with factory.context() as graph:
        held = await _world(graph)
        (before,) = await graph.get_nodes([held.c], A)
        assert _with_the_document(before, held.d)
        # Restricted to named recipients, which neither A nor C is: SECRET is the scheme's top.
        raised = held.document.model_copy(update={"handling": _handling("SECRET", "R")})
        await _write(graph, [raised], [])

        for reader in (A, C):
            (node,) = await graph.get_nodes([held.c], reader)
            (link,) = await graph.get_edges([held.cb], reader)
            assert _without_the_document(node, held.d), reader.id
            assert _without_the_document(link, held.d), reader.id


async def test_a_read_written_back_keeps_the_document_for_any_reader(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as graph:
        held = await _world(graph)
        with sources_in_full():
            (node,) = await graph.get_nodes([held.c], B)
            (link,) = await graph.get_edges([held.cb], B)
        assert _with_the_document(node, held.d) and _with_the_document(link, held.d)
        # Nothing was changed in the store by a read sent without it.
        await graph.get_nodes([held.c], B)
        (again,) = await graph.get_nodes([held.c], C)
        assert _with_the_document(again, held.d)


async def test_an_id_that_is_not_a_document_is_sent_to_no_one(
    factory: GraphAdapterFactory,
) -> None:
    """The question drawing asks: an element the reader reads that is a Document."""
    async with factory.context() as graph:
        other = _node("Person", _loaded_provenance(), datasets=(SOURCE_DATASET,), family_name="X")
        await _write(graph, [other], [])
        held = await _world(graph, document_id=other.id)
        (node,) = await graph.get_nodes([held.c], C)
        assert _without_the_document(node, other.id)


async def test_b_s_answers_have_the_same_shape_whether_the_document_exists_or_not(
    factory: GraphAdapterFactory,
) -> None:
    """Rule 3: two worlds alike but for whether D exists. To B, every read's elements are the same
    in all but their ids, so nothing tells B that a hidden document is there."""

    def shape(elements: list[Node | Edge]) -> list[tuple[Any, ...]]:
        return sorted(
            (
                (
                    e.type,
                    e.provenance.drawn.source_document if e.provenance.drawn else "loaded",
                    e.provenance.drawn.source_note if e.provenance.drawn else "loaded",
                    tuple(s.document_id for s in e.provenance.sources),
                    e.provenance.sources_withheld,
                )
                for e in elements
            ),
            key=repr,
        )

    seen: list[dict[str, list[tuple[Any, ...]]]] = []
    for cited in (None, new_node_id()):
        async with factory.context() as graph:
            held = await _world(graph, document_id=cited)
            answers = await _every_read(graph, held, B)
            seen.append({read: shape(elements) for read, elements in answers.items()})
    assert seen[0] == seen[1]
