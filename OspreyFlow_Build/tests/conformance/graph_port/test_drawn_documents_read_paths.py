"""A drawn item's source document on the working set's and search's read paths, over a real
ArcadeDB and a real Valkey (ADR-143 Amendment 8; slice GG4b, a security part; rules 3 and 4).
Rows 4 to 7, 12 and 15 of the slice's table, live: the pure cases are
`tests/services/api/working_set/test_drawn_source_document_read_paths.py`, and the adapter's own
are `test_drawn_documents.py`, whose world and readers these use.

**B** reads the case but may not read **D**; **C** reads the case and may read D. B is sent no D on
the working set's snapshot (row 4), a delta, replayed and pushed (row 5), a search hit (row 6) or
a drawn link to a loaded node (row 7); C is sent it; the working set keeps it whoever added the
items; B's answers are the same shape whether or not D exists (row 12). Row 15, the budget: an
expansion of 499 drawn people and their 499 drawn links, citing 50 documents, finishes within
`spec/02_GLASS_FRONTEND.md` §5's "Expansion of ≤ 500 nodes: < 800 ms end to end", with a number
of document reads that does not grow with the number of items.

Needs a live ArcadeDB and a live Valkey (`make conformance` runs the directory).
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import pytest
from services.api import search_service
from services.api.config import ValkeyConfig
from services.api.working_set.models import DeltaAdd, DeltaSnapshot
from services.api.working_set.service import WorkingSetService
from services.api.working_set.store import ValkeyWorkingSetStore
from valkey.asyncio import Valkey

from conduit_common.identity import new_node_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ports.graph import GraphPort
from schemas.domain import ExpandRequest, Node, NodeWrite, Principal
from schemas.search import SearchPageRequest
from tests.conformance.graph_port.test_drawn_documents import (
    DOCUMENT_DATASET,
    LAYER,
    NINO,
    SOURCE_DATASET,
    B,
    C,
    _drawn_provenance,
    _link,
    _loaded_provenance,
    _node,
    _while_the_case_reads_it,
    _world,
    _write,
)
from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory

pytestmark = [
    pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str),
    pytest.mark.usefixtures("_sweep_stale_conformance_databases"),
]

SCHEME = load_uk_le_scheme()
#: `spec/02_GLASS_FRONTEND.md` §5: "Expansion of ≤ 500 nodes: < 800 ms end to end".
EXPANSION_BUDGET_SECONDS = 0.8


@asynccontextmanager
async def _working_set(graph: GraphPort) -> AsyncIterator[tuple[WorkingSetService, str, Any]]:
    """The Conduit's working set over the real graph and a real Valkey, for a case of its own,
    cleared on the way out."""
    config = ValkeyConfig.from_env()
    client = Valkey(host=config.host, port=config.port, db=config.db, password=config.password)
    store = ValkeyWorkingSetStore(client)
    case = f"gg4b-{uuid4().hex}"
    try:
        yield WorkingSetService(graph, store, SCHEME), case, store
    finally:
        await store.clear(case)
        await client.aclose()


async def _held_nodes(graph: GraphPort, ids: Sequence[str]) -> list[Node]:
    # What a seed is given is used for its ids alone: the service reads each again.
    return await graph.get_nodes(list(ids), C)


def _drawn(delta: Any) -> list[Any]:
    return [e for e in [*delta.nodes, *delta.edges] if e.provenance.drawn is not None]


def _assert_without(delta: Any, document: str) -> None:
    assert document not in delta.model_dump_json()
    drawn = _drawn(delta)
    assert drawn, "no drawn element was sent"
    for element in drawn:
        assert element.provenance.drawn.source_document is None
        assert [s.document_id for s in element.provenance.sources] == [
            f"drawn:{element.provenance.drawn.item_id}"
        ]


def _assert_with(delta: Any, document: str) -> None:
    drawn = _drawn(delta)
    assert drawn
    for element in drawn:
        assert element.provenance.drawn.source_document == document
        assert [s.document_id for s in element.provenance.sources] == [document]


async def test_the_working_set_never_sends_a_drawn_items_source_document_its_reader_may_not_read(
    factory: GraphAdapterFactory,
) -> None:
    """Rows 4, 5 and 7, with the items added by B, so the stored copy is shown to keep D."""
    async with factory.context() as graph:
        held = await _world(graph)
        async with _working_set(graph) as (service, case, store):
            nodes = await _held_nodes(graph, [held.b, held.c])
            links = await graph.get_edges([held.cb], C)

            added = await service.seed(case, nodes, links, B)

            _assert_without(added.delta, held.d)
            _assert_with(added.to_publish(), held.d)
            (snapshot,) = await service.sync(case, B, last_acknowledged_seq=None)
            assert isinstance(snapshot, DeltaSnapshot)
            assert [e.id for e in snapshot.edges] == [held.cb]
            _assert_without(snapshot, held.d)
            (replayed,) = await service.sync(case, B, last_acknowledged_seq=0)
            assert isinstance(replayed, DeltaAdd)
            _assert_without(replayed, held.d)
            (stored,) = await store.deltas_after(case, 0) or []
            _assert_without(await service.project_live(case, stored, B), held.d)
            _assert_with(await service.project_live(case, stored, C), held.d)
            (for_c,) = await service.sync(case, C, last_acknowledged_seq=None)
            _assert_with(for_c, held.d)
            visible, visible_links = await service.visible_membership(case, B)
            assert held.d not in "".join(e.model_dump_json() for e in [*visible, *visible_links])


async def test_the_working_sets_snapshot_follows_the_datasets_the_readers_case_reads(
    factory: GraphAdapterFactory,
) -> None:
    """Item 2's other half: C is cleared for D throughout. The items are added while the case
    reads D's own dataset; once it no longer does, C's snapshot, replayed delta and pushed delta
    hold D nowhere, and the elements are still sent."""
    async with factory.context() as graph:
        held = await _world(graph, document_dataset=DOCUMENT_DATASET)
        reading = _while_the_case_reads_it(C)
        async with _working_set(graph) as (service, case, store):
            nodes = await graph.get_nodes([held.b, held.c], reading)
            links = await graph.get_edges([held.cb], reading)
            await service.seed(case, nodes, links, reading)
            (stored,) = await store.deltas_after(case, 0) or []

            for principal, check in ((reading, _assert_with), (C, _assert_without)):
                (snapshot,) = await service.sync(case, principal, last_acknowledged_seq=None)
                (replayed,) = await service.sync(case, principal, last_acknowledged_seq=0)
                pushed = await service.project_live(case, stored, principal)
                for delta in (snapshot, replayed, pushed):
                    assert [e.id for e in delta.edges] == [held.cb]  # type: ignore[union-attr]
                    check(delta, held.d)


async def _searched(graph: GraphPort, reader: Principal) -> Any:
    return await search_service.search_page(
        SearchPageRequest(query=NINO),
        reader,
        graph,
        searcher=None,
        access_filter=None,
        phonetic_codes=lambda word: [],
        types=[t.name for t in load_default_ontology().entity_types],
        case_datasets={SOURCE_DATASET: "Source", LAYER: "Layer"},
        schema=load_default_ontology(),
    )


async def test_search_never_returns_a_drawn_items_source_document_its_reader_may_not_read(
    factory: GraphAdapterFactory,
) -> None:
    """Row 6: the hit, with no D."""
    async with factory.context() as graph:
        held = await _world(graph)

        for_b = await _searched(graph, B)
        for_c = await _searched(graph, C)

        assert [n.id for n in for_b.nodes] == [held.c] == [n.id for n in for_c.nodes]
        assert held.d not in for_b.model_dump_json()
        assert held.d in for_c.model_dump_json()


async def test_the_working_sets_and_searchs_answers_to_b_do_not_say_whether_the_document_exists(
    factory: GraphAdapterFactory,
) -> None:
    """Row 12 (rule 3): two worlds alike but for whether D exists."""

    def shape(elements: Sequence[Any]) -> list[tuple[Any, ...]]:
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

    seen: list[list[list[tuple[Any, ...]]]] = []
    for cited in (None, new_node_id()):
        async with factory.context() as graph:
            held = await _world(graph, document_id=cited)
            async with _working_set(graph) as (service, case, _):
                nodes = await _held_nodes(graph, [held.b, held.c])
                added = await service.seed(case, nodes, await graph.get_edges([held.cb], C), B)
                (snapshot,) = await service.sync(case, B, last_acknowledged_seq=None)
                (replayed,) = await service.sync(case, B, last_acknowledged_seq=0)
                found = await _searched(graph, B)
                seen.append(
                    [
                        shape([*d.nodes, *d.edges])
                        for d in (added.delta, snapshot, replayed)  # type: ignore[union-attr]
                    ]
                    + [shape(found.nodes)]
                )
    assert seen[0] == seen[1]


async def _hub_world(graph: GraphPort, items: int, documents: int) -> tuple[str, list[str]]:
    """A loaded hub, `documents` Documents C may read, and `items` drawn people each linked to the
    hub by a drawn link, the people and links citing the documents in turn."""
    cited = [
        _node(
            "Document",
            _loaded_provenance(),
            classification="SECRET",
            datasets=(SOURCE_DATASET,),
            title=f"Statement {n}",
        )
        for n in range(documents)
    ]
    hub = _node("Person", _loaded_provenance(), datasets=(SOURCE_DATASET,), family_name="Hub")
    people: list[NodeWrite] = [
        _node(
            "Person",
            _drawn_provenance(f"item-n{n}", cited[n % documents].id),
            family_name="Quillfeather",
        )
        for n in range(items)
    ]
    links = [
        _link(p.id, hub.id, _drawn_provenance(f"item-e{n}", cited[n % documents].id), (LAYER,))
        for n, p in enumerate(people)
    ]
    await _write(graph, [*cited, hub, *people], links)
    return hub.id, [d.id for d in cited]


async def test_an_expansion_of_drawn_items_citing_documents_is_within_budget(
    factory: GraphAdapterFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Row 15, live (question 5 (a)): `spec/02` §5's expansion budget, and a number of document
    reads that is the same for 20 drawn items as for 499. A first, unmeasured preview of the same
    expansion warms the store, as a canvas's own preview does before an expansion."""
    reads: dict[int, int] = {}
    for items in (20, 499):
        async with factory.context() as graph:
            hub, documents = await _hub_world(graph, items, min(items, 50))
            async with _working_set(graph) as (service, case, _):
                await service.seed(case, await _held_nodes(graph, [hub]), [], C)
                request = ExpandRequest(node_ids=[hub], depth=1)
                await service.expand_preview(case, request, C)
                asked: list[int] = []
                real = graph._documents  # type: ignore[attr-defined]

                async def counted(ids: list[str], principal: Principal, real: Any = real) -> Any:
                    asked.append(len(ids))
                    return await real(ids, principal)

                monkeypatch.setattr(graph, "_documents", counted)
                real_get_nodes = graph.get_nodes

                async def counted_get_nodes(
                    ids: Sequence[str], principal: Principal, real: Any = real_get_nodes
                ) -> Any:
                    if ids and set(ids) <= set(documents):
                        asked.append(len(ids))
                    return await real(ids, principal)

                monkeypatch.setattr(graph, "get_nodes", counted_get_nodes)

                started = time.perf_counter()
                outcome = await service.expand(case, request, C)
                elapsed = time.perf_counter() - started

                assert len(outcome.delta.nodes) == items + 1
                assert len(_drawn(outcome.delta)) == 2 * items
                reads[items] = len(asked)
                if items == 499:
                    assert elapsed < EXPANSION_BUDGET_SECONDS, f"{elapsed:.3f} s"
                for element in _drawn(outcome.delta):
                    assert element.provenance.drawn.source_document in documents
    assert reads[499] == reads[20], reads
    assert reads[499] <= 3, reads
