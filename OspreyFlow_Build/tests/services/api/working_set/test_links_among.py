"""Links among what is on screen (ADR-098 decision 1): an expansion returns only the links it walked
along, so the links between the nodes it brought, and between them and the rest of the view, are
asked for separately, automatically after a small expansion and on demand otherwise. Never a
silent slice (rule 2)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from services.api.working_set.models import (
    LINKS_AMONG_MAX_DEGREE,
    LINKS_AMONG_ROUTE_NODES,
    MAX_EDGES,
    LimitExceededError,
    LinksAmongRequest,
)
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
    graph = FakeGraphPort(expand_result=star, graph_edges=[*star.edges, *between])
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
    graph = FakeGraphPort(expand_result=star, graph_edges=star.edges)
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
    graph = FakeGraphPort(expand_result=star, graph_edges=[*star.edges, *extra])
    service = WorkingSetService(graph, store, SCHEME)

    outcome = await service.expand("inv-1", ExpandRequest(node_ids=["hub"]), PRINCIPAL)

    assert {e.id for e in outcome.delta.edges} == {"h0", "h1"}
    assert outcome.links_among == "view_full"


async def test_on_demand_the_links_among_the_whole_view_are_added() -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes("inv-1", [_node("a"), _node("b"), _node("c")])
    graph = FakeGraphPort(
        expand_result=Subgraph(nodes=[], edges=[]),
        graph_edges=[_edge("ab", "a", "b"), _edge("bc", "b", "c"), _edge("cz", "c", "z")],
    )
    service = WorkingSetService(graph, store, SCHEME)

    outcome = await service.links_among("inv-1", PRINCIPAL)

    assert {e.id for e in outcome.delta.edges} == {"ab", "bc"}
    assert outcome.added == 2


async def test_on_demand_only_named_nodes_that_are_in_the_view_are_asked_about() -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes("inv-1", [_node("a"), _node("b")])
    graph = FakeGraphPort(expand_result=Subgraph(nodes=[], edges=[]))
    service = WorkingSetService(graph, store, SCHEME)

    await service.links_among("inv-1", PRINCIPAL, node_ids=["a", "b", "not-on-screen"])

    asked, _ = graph.edges_among_requests[0]
    assert set(asked) == {"a", "b"}


async def test_on_demand_past_the_cap_adds_nothing_and_raises_limit_exceeded() -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes("inv-1", [_node("a"), _node("b")])
    graph = FakeGraphPort(
        expand_result=Subgraph(nodes=[], edges=[]),
        graph_edges=[_edge(f"e{i}", "a", "b") for i in range(MAX_EDGES + 1)],
    )
    service = WorkingSetService(graph, store, SCHEME)

    with pytest.raises(LimitExceededError) as refused:
        await service.links_among("inv-1", PRINCIPAL)
    assert refused.value.detail.cap_kind == "edges"
    assert await store.edge_count("inv-1") == 0


# --- ADR-098 Amendment 4: links among these within a chosen number of degrees -------------------


def _view_graph(edges: list) -> tuple[FakeWorkingSetStore, FakeGraphPort, WorkingSetService]:
    store = FakeWorkingSetStore()
    graph = FakeGraphPort(expand_result=Subgraph(nodes=[], edges=[]),
                          graph_edges=edges)  # fmt: skip
    return store, graph, WorkingSetService(graph, store, SCHEME)


CHAIN = [_edge("ab", "a", "b"), _edge("bc", "b", "c"), _edge("cd", "c", "d")]


async def test_at_a_degree_the_routes_between_the_selected_nodes_are_drawn() -> None:
    """The owner's case: two nodes joined only through others; at three degrees the route is drawn,
    its nodes and links with it."""
    store, graph, service = _view_graph(CHAIN)
    await store.add_nodes("inv-1", [_node("a"), _node("d")])

    outcome = await service.links_among("inv-1", PRINCIPAL, node_ids=["a", "d"], degree=3)

    assert {e.id for e in outcome.delta.edges} == {"ab", "bc", "cd"}
    assert {n.id for n in outcome.delta.nodes} == {"b", "c"}
    assert (outcome.added, outcome.added_nodes, outcome.unconnected_pairs) == (3, 2, 0)


async def test_no_route_is_looked_for_beyond_the_degree_asked() -> None:
    store, graph, service = _view_graph(CHAIN)
    await store.add_nodes("inv-1", [_node("a"), _node("d")])

    outcome = await service.links_among("inv-1", PRINCIPAL, node_ids=["a", "d"], degree=2)

    assert outcome.delta.edges == [] and outcome.unconnected_pairs == 1
    assert max(length for *_, length, _ in graph.paths_at_length_requests) == 2


async def test_the_fewest_degrees_that_join_a_pair_are_the_routes_drawn() -> None:
    store, graph, service = _view_graph([*CHAIN, _edge("ax", "a", "x"), _edge("xd", "x", "d")])
    await store.add_nodes("inv-1", [_node("a"), _node("d")])

    outcome = await service.links_among("inv-1", PRINCIPAL, node_ids=["a", "d"], degree=6)

    assert {e.id for e in outcome.delta.edges} == {"ax", "xd"}


async def test_a_pair_joined_only_through_a_hidden_node_stays_unjoined() -> None:
    """Rule 3: the search is the reader's, in the adapter — a route through what they cannot see is
    not found, and nothing says it exists."""
    store = FakeWorkingSetStore()
    graph = FakeGraphPort(expand_result=Subgraph(nodes=[], edges=[]),
                          graph_edges=[_edge("ah", "a", "h"), _edge("hd", "h", "d")],
                          hidden_node_ids=frozenset({"h"}))  # fmt: skip
    service = WorkingSetService(graph, store, SCHEME)
    await store.add_nodes("inv-1", [_node("a"), _node("d")])

    outcome = await service.links_among("inv-1", PRINCIPAL, node_ids=["a", "d"], degree=4)

    assert outcome.delta.nodes == [] and outcome.delta.edges == []
    assert outcome.unconnected_pairs == 1
    assert graph.paths_at_length_requests
    assert all(principal == PRINCIPAL for *_, principal in graph.paths_at_length_requests)


async def test_more_routes_than_are_drawn_are_said_not_hidden() -> None:
    """Rule 2: a pair with more routes at its degree than are drawn is counted in the answer."""
    middles = [f"m{i}" for i in range(11)]
    edges = [e for m in middles for e in (_edge(f"a{m}", "a", m), _edge(f"{m}d", m, "d"))]
    store, graph, service = _view_graph(edges)
    await store.add_nodes("inv-1", [_node("a"), _node("d")])

    outcome = await service.links_among("inv-1", PRINCIPAL, node_ids=["a", "d"], degree=2)

    assert outcome.added_nodes == 10 and outcome.more_routes_pairs == 1


async def test_routes_past_the_cap_add_nothing_and_raise_limit_exceeded() -> None:
    store, graph, service = _view_graph(CHAIN)
    await store.add_nodes("inv-1", [_node("a"), _node("d")])
    await store.add_edges("inv-1", [_edge(f"held{i}", "a", "a") for i in range(MAX_EDGES - 1)])

    with pytest.raises(LimitExceededError):
        await service.links_among("inv-1", PRINCIPAL, node_ids=["a", "d"], degree=3)
    assert await store.node_count("inv-1") == 2


def test_a_degree_is_one_to_six_and_above_one_needs_two_to_eight_selected_nodes() -> None:
    assert LINKS_AMONG_MAX_DEGREE == 6 and LINKS_AMONG_ROUTE_NODES == 8
    LinksAmongRequest(node_ids=["a", "b"], degree=6)
    LinksAmongRequest(node_ids=None)  # the whole view, at one degree, as before
    for wrong in (
        {"node_ids": ["a", "b"], "degree": 7},
        {"node_ids": ["a", "b"], "degree": 0},
        {"node_ids": None, "degree": 2},
        {"node_ids": ["a"], "degree": 2},
        {"node_ids": [f"n{i}" for i in range(9)], "degree": 2},
    ):
        with pytest.raises(ValidationError):
            LinksAmongRequest(**wrong)
