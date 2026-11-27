"""A drawn item's source document on the working set's and search's read paths (ADR-143 Amendment
8; slice GG4b, a security part; rules 3 and 4). Rows 4 to 7, 12 and 15 of the slice's table, pure,
over `BoardGraph`, whose reads answer the reader's batched document read as the adapter does. The
same rows against ArcadeDB are `tests/conformance/graph_port/test_drawn_documents_read_paths.py`.

**A** drew an item citing document **D**; **B** reads the case but may not read D; **C** reads the
case and may read D.

What fails if the rule is wrong (each shown red with its fault planted,
`process/lanes/v062/GG4b_RED_RECORD.md`):

- B sent D on a snapshot (row 4), a delta, replayed or pushed (row 5), a search hit (row 6) or a
  link to a loaded node (row 7): red with the rule put in `open_board` alone, not in
  `withhold_sources`;
- the working set storing one reader's view as everyone's: a writer who may not read D would take
  it from everyone, and the delta it publishes would too;
- B's answers differing by whether D exists (row 12);
- the number of document reads growing with the number of drawn items (row 15): red with one read
  for each element in place of the batch.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from services.api import search_service
from services.api.boards import Boards
from services.api.working_set.models import DeltaAdd, DeltaSnapshot
from services.api.working_set.service import WorkingSetService

from ontology.packs import load_deployment_ontology
from schemas.case_views import ViewFilter
from schemas.domain import (
    AuditStub,
    Edge,
    ExpandRequest,
    Grading,
    Handling,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
)
from schemas.search import SearchPageRequest, SearchPageResponse

from ..board_fakes import SCHEME, BoardGraph
from ..test_search_service import _hit, _Index, _reply
from .fakes import FakeWorkingSetStore

ONTOLOGY = load_deployment_ontology()
SOURCE_DATASET, LAYER = "src", "layer-k"
CASE = "case-k"
D = "doc-sealed-statement"
NINO = "QQ123456C"
WHEN = datetime(2026, 11, 1, tzinfo=UTC)


def _reader(who: str, clearance: str) -> Principal:
    return Principal(
        id=who, clearance=clearance, org_unit="unit-1", datasets=[SOURCE_DATASET, LAYER]
    )


A = _reader("acct-a", "SECRET")
B = _reader("acct-b", "OFFICIAL")
C = _reader("acct-c", "SECRET")


def _common(provenance: Provenance, marking: str, datasets: Sequence[str]) -> dict[str, Any]:
    return {
        "provenance": provenance,
        "handling": Handling(
            classification=marking, handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
        "audit": AuditStub(created_at=WHEN, created_by=A.id),
        "datasets": list(datasets),
    }


def _loaded_provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="files/register.csv", locator="row 1", excerpt_hash="")],
        first_seen=WHEN,
    )


def _drawn_provenance(item_id: str, document: str | None) -> Provenance:
    """As the board service writes it (`Boards._provenance`)."""
    given = SimpleNamespace(
        label="Unknown male",
        grading=Grading(source="B", intelligence="2", handling="1"),
        source_note="Seen from the quay",
        source_document=document,
    )
    board: Any = SimpleNamespace(id="board-a", case_id=CASE)
    written = Boards._provenance(None, item_id, board, A, given)  # type: ignore[arg-type]
    return written.model_copy(update={"first_seen": WHEN})


def _person(node_id: str, provenance: Provenance, datasets: Sequence[str], **props: Any) -> Node:
    return Node(
        id=node_id, type="Person", properties=props, **_common(provenance, "OFFICIAL", datasets)
    )


def _document(document_id: str, marking: str) -> Node:
    return Node(
        id=document_id,
        type="Document",
        properties={"title": "Sealed statement"},
        **_common(_loaded_provenance(), marking, [SOURCE_DATASET]),
    )


def _link(edge_id: str, source: str, target: str, provenance: Provenance) -> Edge:
    return Edge(
        id=edge_id,
        type="ASSOCIATE_OF",
        source=source,
        target=target,
        **_common(provenance, "OFFICIAL", [LAYER]),
    )


class _World:
    """A loaded hub, and `items` drawn people each linked to it by a drawn link; each drawn item
    and link cites `documents[n % len(documents)]`. Each document is held, marked SECRET, unless
    `held` is false."""

    def __init__(self, items: int = 1, documents: int = 1, *, held: bool = True) -> None:
        self.cited = [D, *[f"{D}-{n}" for n in range(1, documents)]]
        self.hub = _person("p-hub", _loaded_provenance(), [SOURCE_DATASET], family_name="Ward")
        self.drawn = [
            _person(
                f"n-{n:04}",
                _drawn_provenance(f"item-n{n}", self.cited[n % documents]),
                [LAYER],
                family_name="Quillfeather",
                **({"nino": NINO} if n == 0 else {}),
            )
            for n in range(items)
        ]
        self.links = [
            _link(
                f"e-{n:04}",
                node.id,
                "p-hub",
                _drawn_provenance(f"item-e{n}", self.cited[n % documents]),
            )
            for n, node in enumerate(self.drawn)
        ]
        marked = [_document(i, "SECRET") for i in self.cited] if held else []
        self.graph = BoardGraph(
            ONTOLOGY, nodes=[self.hub, *self.drawn, *marked], edges=self.links
        )
        self.graph.expand_result = Subgraph(nodes=[self.hub, *self.drawn], edges=self.links)
        self.store = FakeWorkingSetStore()
        self.service = WorkingSetService(self.graph, self.store, SCHEME)

    def nodes(self) -> list[Node]:
        return [self.hub, *self.drawn]

    async def seed(self, who: Principal) -> Any:
        return await self.service.seed(CASE, self.nodes(), self.links, who)

    def reads_of_documents(self) -> int:
        """Every read of a cited document: the adapter's own batched reads, and the working
        set's, which it makes through `get_nodes`."""
        by_the_working_set = [
            ids for ids, _ in self.graph.get_nodes_requests if set(ids) & set(self.cited)
        ]
        return len(self.graph.document_reads) + len(by_the_working_set)


def _text(delta: Any) -> str:
    return str(delta.model_dump_json())


def _drawn_elements(delta: Any) -> list[Node | Edge]:
    return [e for e in [*delta.nodes, *delta.edges] if e.provenance.drawn is not None]


def _assert_without(delta: Any, items: int = 1) -> None:
    assert D not in _text(delta)
    drawn = _drawn_elements(delta)
    assert len(drawn) == 2 * items, "the drawn node and the drawn link are both sent"
    for element in drawn:
        assert element.provenance.drawn is not None
        assert element.provenance.drawn.source_document is None
        assert [s.document_id for s in element.provenance.sources] == [
            f"drawn:{element.provenance.drawn.item_id}"
        ]


def _assert_with(delta: Any) -> None:
    drawn = _drawn_elements(delta)
    assert len(drawn) == 2
    for element in drawn:
        assert element.provenance.drawn is not None
        assert element.provenance.drawn.source_document == D
        assert [s.document_id for s in element.provenance.sources] == [D]


# --- rows 4, 5 and 7 --------------------------------------------------------------------------


async def test_the_working_set_never_sends_a_drawn_items_source_document_its_reader_may_not_read(
) -> None:
    world = _World()
    await world.seed(C)

    # Row 4: the snapshot on connect. The link from the item to a loaded node is row 7.
    (snapshot,) = await world.service.sync(CASE, B, last_acknowledged_seq=None)
    assert isinstance(snapshot, DeltaSnapshot)
    _assert_without(snapshot)
    (for_c,) = await world.service.sync(CASE, C, last_acknowledged_seq=None)
    _assert_with(for_c)

    # Row 5: a delta, replayed on a reconnect and pushed live.
    (replayed,) = await world.service.sync(CASE, B, last_acknowledged_seq=0)
    assert isinstance(replayed, DeltaAdd)
    _assert_without(replayed)
    (stored,) = await world.store.deltas_after(CASE, 0)
    _assert_without(await world.service.project_live(CASE, stored, B))
    _assert_with(await world.service.project_live(CASE, stored, C))
    # A caller that projects with no read withholds it from everyone.
    assert D not in _text(world.service.project_delta(stored, C))

    # A view of the case, and a filtered one.
    nodes, edges = await world.service.visible_membership(CASE, B)
    _assert_without(DeltaSnapshot(seq=0, nodes=nodes, edges=edges))
    kept = ViewFilter(entity_types=["Person"])
    for reader, expected in ((B, False), (C, True)):
        shown_nodes, shown_edges = await world.service.filtered_view(CASE, reader, kept)
        said = "".join(e.model_dump_json() for e in [*shown_nodes, *shown_edges])
        assert (D in said) is expected, reader.id

    # A single stored element, read for a check, never carries it.
    node = await world.service.visible_node(CASE, "n-0000", C)
    link = await world.service.visible_edge(CASE, "e-0000", C)
    assert node is not None and link is not None
    assert D not in node.model_dump_json() + link.model_dump_json()


async def test_what_the_working_set_holds_and_publishes_keeps_the_document_whoever_added_it() -> (
    None
):
    """Item 5, and the test that shows the working set keeps stored ids: B, who may not read D,
    adds the items. B's own answer has no D; what is stored and published keeps it, so C is sent
    it on a snapshot and on the live push, and B still is not."""
    world = _World()

    outcome = await world.seed(B)

    _assert_without(outcome.delta)
    published = outcome.to_publish()
    _assert_with(published)
    stored_nodes = await world.store.source_fidelity_nodes(CASE)
    held = stored_nodes["n-0000"].provenance
    assert held.drawn is not None and held.drawn.source_document == D
    assert [s.document_id for s in held.sources] == [D]
    _assert_with(await world.service.project_live(CASE, published, C))
    _assert_without(await world.service.project_live(CASE, published, B))
    (for_c,) = await world.service.sync(CASE, C, last_acknowledged_seq=None)
    _assert_with(for_c)
    # The writer's answer, as a route sends it, never carries the stored form.
    assert D not in outcome.model_dump_json()


async def test_an_add_by_a_reader_who_may_read_the_document_answers_with_it() -> None:
    world = _World()

    outcome = await world.seed(C)

    _assert_with(outcome.delta)


async def test_an_expansion_and_the_links_among_it_keep_and_withhold_alike() -> None:
    world = _World()
    await world.service.seed(CASE, [world.hub], [], B)

    outcome = await world.service.expand(CASE, ExpandRequest(node_ids=["p-hub"]), B)

    assert D not in outcome.model_dump_json()
    _assert_with(outcome.to_publish())

    among = await world.service.links_among(CASE, B)
    assert D not in among.model_dump_json()


async def test_a_restore_stores_the_document_and_answers_its_restorer_without_it() -> None:
    world = _World()
    await world.seed(C)

    restored = await world.service.restore(CASE, world.nodes(), world.links, B)

    _assert_without(restored.response)
    _assert_with(restored.published)
    (for_c,) = await world.service.sync(CASE, C, last_acknowledged_seq=None)
    _assert_with(for_c)


async def test_a_link_that_comes_back_with_its_node_is_stored_with_the_document() -> None:
    """A removed drawn node leaves its link stored; B adding the node back brings the link into
    the change, stored whole and answered to B without D."""
    world = _World()
    await world.seed(C)
    await world.service.remove(CASE, ["n-0000"], C)

    outcome = await world.service.seed(CASE, [world.drawn[0]], [], B)

    assert [e.id for e in outcome.delta.edges] == ["e-0000"]
    _assert_without(outcome.delta)
    _assert_with(outcome.to_publish())


# --- row 6 ------------------------------------------------------------------------------------


async def _searched(world: _World, reader: Principal, index: _Index | None) -> SearchPageResponse:
    return await search_service.search_page(
        SearchPageRequest(query=NINO),
        reader,
        world.graph,
        searcher=index,
        access_filter={"match_all": {}} if index is not None else None,
        phonetic_codes=lambda word: [],
        types=[t.name for t in ONTOLOGY.entity_types],
        case_datasets={SOURCE_DATASET: "Harbour register"},
        schema=ONTOLOGY,
    )


@pytest.mark.parametrize("path", ["index", "fallback"])
async def test_search_never_returns_a_drawn_items_source_document_its_reader_may_not_read(
    path: str,
) -> None:
    """Row 6: the hit, with no D, by the index (its hits are read from the graph) and by the
    graph's own search."""
    world = _World()
    for reader, expected in ((B, False), (C, True)):
        index = _Index(_reply([_hit("n-0000", 100.0)])) if path == "index" else None

        found = await _searched(world, reader, index)

        assert found.source == path
        assert [n.id for n in found.nodes] == ["n-0000"], reader.id
        assert (D in found.model_dump_json()) is expected, reader.id


# --- row 12: the leak test --------------------------------------------------------------------


async def _every_answer_to_b(world: _World) -> list[str]:
    await world.seed(A)
    snapshot = (await world.service.sync(CASE, B, last_acknowledged_seq=None))[0]
    replayed = await world.service.sync(CASE, B, last_acknowledged_seq=0)
    expanded = await world.service.expand(CASE, ExpandRequest(node_ids=["p-hub"]), B)
    read = await world.graph.get_nodes(["n-0000"], B)
    links = await world.graph.edges_among(["n-0000", "p-hub"], B)
    searched = await _searched(world, B, _Index(_reply([_hit("n-0000", 100.0)])))
    return [
        snapshot.model_dump_json(),
        *[d.model_dump_json() for d in replayed],
        expanded.model_dump_json(),
        *[n.model_dump_json() for n in read],
        *[e.model_dump_json() for e in links],
        searched.model_dump_json(),
    ]


async def test_every_answer_to_b_is_the_same_whether_or_not_the_document_exists() -> None:
    """Row 12 (rule 3): two worlds alike but for whether D is there. B's answers are the same,
    byte for byte, and made with the same number of document reads."""
    hidden, absent = _World(held=True), _World(held=False)

    assert await _every_answer_to_b(hidden) == await _every_answer_to_b(absent)
    assert hidden.reads_of_documents() == absent.reads_of_documents()


async def test_b_is_sent_the_same_counts_with_or_without_the_rule_having_anything_to_withhold() -> (
    None
):
    """Rule 3: the rule withholds fields of elements B already sees. Which elements B is sent,
    and how many, are those C is sent."""
    world = _World(items=3)
    await world.seed(C)

    (for_b,) = await world.service.sync(CASE, B, last_acknowledged_seq=None)
    (for_c,) = await world.service.sync(CASE, C, last_acknowledged_seq=None)

    assert isinstance(for_b, DeltaSnapshot) and isinstance(for_c, DeltaSnapshot)
    assert [n.id for n in for_b.nodes] == [n.id for n in for_c.nodes]
    assert [(e.id, e.source, e.target) for e in for_b.edges] == [
        (e.id, e.source, e.target) for e in for_c.edges
    ]
    assert for_b.withheld == for_c.withheld is False


# --- row 15: the budget -----------------------------------------------------------------------


async def _reads_by_answer(items: int, who: Principal) -> dict[str, int]:
    """How many reads of cited documents each answer makes, in a working set holding `items`
    drawn people and `items` drawn links, each citing a document of its own."""
    world = _World(items=items, documents=items)
    await world.seed(C)
    stored = (await world.store.deltas_after(CASE, 0)) or []
    made: dict[str, int] = {}

    async def count(name: str, answer: Any) -> None:
        before = world.reads_of_documents()
        await answer
        made[name] = world.reads_of_documents() - before

    await count("open", world.service.sync(CASE, who, last_acknowledged_seq=None))
    await count("catch-up", world.service.sync(CASE, who, last_acknowledged_seq=0))
    await count("live delta", world.service.project_live(CASE, stored[0], who))
    await count("view", world.service.visible_membership(CASE, who))
    await count("seed", world.seed(who))
    await count("expand", world.service.expand(CASE, ExpandRequest(node_ids=["p-hub"]), who))
    await count("restore", world.service.restore(CASE, world.nodes(), world.links, who))
    return made


@pytest.mark.parametrize("who", [B, C], ids=["b", "c"])
async def test_document_reads_do_not_grow_with_the_number_of_drawn_items(who: Principal) -> None:
    """Row 15 (the owner, 26 November; question 5 (a)): opening a working set that holds drawn
    items citing documents, and taking its deltas, reads those documents in a number of reads that
    is the same for 2 items as for 80. The time budget (`spec/02` §5, an expansion of up to 500
    nodes under 800 ms) is the live case's."""
    few = await _reads_by_answer(2, who)
    many = await _reads_by_answer(80, who)

    assert many == few
    # One batched read for each answer. Opening makes two: the snapshot's own, and the one in the
    # graph read that finds the reader's clusters (Amendment 8 item 3: each graph read at most one).
    assert few == {
        "open": 2,
        "catch-up": 1,
        "live delta": 1,
        "view": 1,
        "seed": 1,
        "expand": 1,
        "restore": 1,
    }


async def test_an_answer_with_nothing_drawn_reads_no_document() -> None:
    world = _World(items=0, documents=1)
    await world.seed(C)

    await world.service.sync(CASE, B, last_acknowledged_seq=None)
    await world.service.sync(CASE, B, last_acknowledged_seq=0)

    assert world.reads_of_documents() == 0


async def test_a_document_only_a_hidden_drawn_item_cites_is_not_asked_about() -> None:
    world = _World()
    secret = world.drawn[0].model_copy(
        update={
            "handling": world.drawn[0].handling.model_copy(update={"classification": "SECRET"})
        }
    )
    await world.store.add_nodes(CASE, [world.hub, secret])
    await world.store.add_edges(CASE, world.links)

    (snapshot,) = await world.service.sync(CASE, B, last_acknowledged_seq=None)

    assert isinstance(snapshot, DeltaSnapshot)
    assert [n.id for n in snapshot.nodes] == ["p-hub"] and snapshot.edges == []
    assert world.reads_of_documents() == 0


async def test_a_failed_document_read_sends_no_document() -> None:
    world = _World()
    await world.seed(C)

    async def unreachable(ids: Sequence[str], principal: Principal) -> list[Node]:
        raise ConnectionError("the store is unreachable")

    world.graph.get_nodes = unreachable  # type: ignore[method-assign]
    (snapshot,) = await world.service.sync(CASE, C, last_acknowledged_seq=None)

    _assert_without(snapshot)
