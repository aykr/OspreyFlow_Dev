"""Links among what is on screen (ADR-098 decision 1): an expansion returns only the links it walked
along, so the links between the nodes it brought, and between them and the rest of the view, are
asked for separately, automatically after a small expansion and on demand otherwise. Never a
silent slice (rule 2)."""

from __future__ import annotations

import pytest
from services.api.working_set.models import MAX_EDGES, LimitExceededError
from services.api.working_set.service import AUTO_LINKS_MAX_NEW_NODES, WorkingSetService

from schemas.domain import ExpandRequest, Subgraph

from .fakes import FakeGraphPort, FakeWorkingSetStore
from .test_service import PRINCIPAL, SCHEME, _edge, _node


def _star(leaves: int) -> Subgraph:
    nodes = [_node("hub"), *(_node(f"l{i}") for i in range(leaves))]
    return Subgraph(nodes=nodes, edges=[_edge(f"h{i}", "hub", f"l{i}") for i in range(leaves)])


async def test_a_small_expansion_brings_the_links_among_its_nodes_and_the_view() -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes("inv-1", [_node("already")])
    star = _star(2)
    between = [
        _edge("l0-l1", "l0", "l1"),
        _edge("l1-already", "l1", "already"),
        _edge("out", "l0", "elsewhere"),
    ]
    graph = FakeGraphPort(
        expand_result=star, candidate_count=3, graph_edges=[*star.edges, *between]
    )
    service = WorkingSetService(graph, store, SCHEME)

    outcome = await service.expand("inv-1", ExpandRequest(node_ids=["hub"]), PRINCIPAL)

    ids = {e.id for e in outcome.delta.edges}
    assert {"h0", "h1", "l0-l1", "l1-already"} <= ids
    assert "out" not in ids  # one end is not on screen
    assert outcome.links_among == "added"
    asked, principal = graph.edges_among_requests[0]
    assert set(asked) == {"hub", "l0", "l1", "already"}
    assert principal == PRINCIPAL  # access is the adapter's, for this analyst (rule 3)


async def test_a_large_expansion_does_not_ask_and_says_so() -> None:
    store = FakeWorkingSetStore()
    star = _star(AUTO_LINKS_MAX_NEW_NODES + 1)
    graph = FakeGraphPort(
        expand_result=star, candidate_count=len(star.nodes), graph_edges=star.edges
    )
    service = WorkingSetService(graph, store, SCHEME)

    outcome = await service.expand("inv-1", ExpandRequest(node_ids=["hub"]), PRINCIPAL)

    assert graph.edges_among_requests == []
    assert outcome.links_among == "not_asked"


async def test_links_that_would_pass_the_cap_are_left_out_of_an_expansion_and_it_says_so() -> None:
    """The expansion still lands whole; the extra links are not a silent slice: none of them is
    added, and the outcome says the view was too full for them."""
    store = FakeWorkingSetStore()
    star = _star(2)
    extra = [_edge(f"x{i}", "l0", "l1") for i in range(MAX_EDGES)]
    graph = FakeGraphPort(expand_result=star, candidate_count=3, graph_edges=[*star.edges, *extra])
    service = WorkingSetService(graph, store, SCHEME)

    outcome = await service.expand("inv-1", ExpandRequest(node_ids=["hub"]), PRINCIPAL)

    assert {e.id for e in outcome.delta.edges} == {"h0", "h1"}
    assert outcome.links_among == "view_full"


async def test_on_demand_the_links_among_the_whole_view_are_added() -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes("inv-1", [_node("a"), _node("b"), _node("c")])
    graph = FakeGraphPort(
        expand_result=Subgraph(nodes=[], edges=[]),
        candidate_count=0,
        graph_edges=[_edge("ab", "a", "b"), _edge("bc", "b", "c"), _edge("cz", "c", "z")],
    )
    service = WorkingSetService(graph, store, SCHEME)

    outcome = await service.links_among("inv-1", PRINCIPAL)

    assert {e.id for e in outcome.delta.edges} == {"ab", "bc"}
    assert outcome.added == 2


async def test_on_demand_only_named_nodes_that_are_in_the_view_are_asked_about() -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes("inv-1", [_node("a"), _node("b")])
    graph = FakeGraphPort(expand_result=Subgraph(nodes=[], edges=[]), candidate_count=0)
    service = WorkingSetService(graph, store, SCHEME)

    await service.links_among("inv-1", PRINCIPAL, node_ids=["a", "b", "not-on-screen"])

    asked, _ = graph.edges_among_requests[0]
    assert set(asked) == {"a", "b"}


async def test_on_demand_past_the_cap_adds_nothing_and_raises_limit_exceeded() -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes("inv-1", [_node("a"), _node("b")])
    graph = FakeGraphPort(
        expand_result=Subgraph(nodes=[], edges=[]),
        candidate_count=0,
        graph_edges=[_edge(f"e{i}", "a", "b") for i in range(MAX_EDGES + 1)],
    )
    service = WorkingSetService(graph, store, SCHEME)

    with pytest.raises(LimitExceededError) as refused:
        await service.links_among("inv-1", PRINCIPAL)
    assert refused.value.detail.cap_kind == "edges"
    assert await store.edge_count("inv-1") == 0
