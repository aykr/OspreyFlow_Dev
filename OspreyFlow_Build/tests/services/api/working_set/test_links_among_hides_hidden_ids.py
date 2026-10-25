"""Links-among as a membership test (ADR-124 decision 3). The ids a request names are intersected
with the stored ids the reader may read before anything else, so a stored hidden id behaves exactly
as an absent one: the same graph requests (so the same work and timing), the same counts, the same
delta. Before this the intersection was with the stored set, and a hidden id raised
`unconnected_pairs` at degree above one and made the one-id early return at degree one differ."""

from __future__ import annotations

import pytest
from services.api.working_set.models import LinksAmongOutcome
from services.api.working_set.service import WorkingSetService

from schemas.domain import Subgraph

from .fakes import FakeGraphPort, FakeWorkingSetStore
from .test_visible_link import OFFICIAL_READER, SCHEME, edge, node


async def _outcome(
    *, hidden_id_is_stored: bool, degree: int, ids: list[str] | None
) -> tuple[LinksAmongOutcome, FakeGraphPort]:
    """A case holding `a`, `b` and a link between them, and (or not) a stored SECRET `x`; an
    OFFICIAL reader asks for links among `ids`."""
    store = FakeWorkingSetStore()
    held = [node("a"), node("b")]
    if hidden_id_is_stored:
        held.append(node("x", "SECRET"))
    await store.add_nodes("inv-1", held)
    graph = FakeGraphPort(
        Subgraph(nodes=[], edges=[]),
        graph_nodes=[*held, node("c")],
        graph_edges=[edge("ab", "a", "b"), edge("ax", "a", "x", "SECRET")],
    )
    service = WorkingSetService(graph, store, SCHEME)
    outcome = await service.links_among("inv-1", OFFICIAL_READER, ids, degree)
    return outcome, graph


@pytest.mark.parametrize("degree", [1, 2, 3])
async def test_a_stored_hidden_id_and_an_absent_id_give_the_same_links_among(degree: int) -> None:
    """Violation caught (rule 3): `ids = stored & requested`, which kept the hidden id, so its pairs
    were searched and counted unconnected, and the graph was asked about it."""
    ids = ["a", "b", "x"]
    hidden, hidden_graph = await _outcome(hidden_id_is_stored=True, degree=degree, ids=ids)
    absent, absent_graph = await _outcome(hidden_id_is_stored=False, degree=degree, ids=ids)

    assert hidden.model_dump() == absent.model_dump()
    assert hidden_graph.edges_among_requests == absent_graph.edges_among_requests
    assert hidden_graph.paths_at_length_requests == absent_graph.paths_at_length_requests


async def test_one_visible_id_and_a_stored_hidden_one_ask_the_graph_as_one_id_alone_does() -> None:
    """At degree one the adapter returns early for fewer than two ids, which is observable as time.
    A stored hidden id must not turn one id into two."""
    hidden, hidden_graph = await _outcome(hidden_id_is_stored=True, degree=1, ids=["a", "x"])
    absent, absent_graph = await _outcome(hidden_id_is_stored=False, degree=1, ids=["a", "x"])

    assert [ids for ids, _ in hidden_graph.edges_among_requests] == [["a"]]
    assert hidden_graph.edges_among_requests == absent_graph.edges_among_requests
    assert hidden.model_dump() == absent.model_dump()


async def test_unconnected_pairs_at_degree_two_count_only_what_the_reader_may_read() -> None:
    """`a` and `b` are joined; `c` is readable and joined to neither. So two pairs are unconnected,
    (a, c) and (b, c), whether or not a hidden `x` is stored: its pairs are not searched."""
    for stored in (True, False):
        store = FakeWorkingSetStore()
        held = [node("a"), node("b"), node("c")]
        if stored:
            held.append(node("x", "SECRET"))
        await store.add_nodes("inv-1", held)
        graph = FakeGraphPort(
            Subgraph(nodes=[], edges=[]),
            graph_nodes=held,
            graph_edges=[edge("ab", "a", "b")],
        )
        service = WorkingSetService(graph, store, SCHEME)
        outcome = await service.links_among("inv-1", OFFICIAL_READER, ["a", "b", "c", "x"], 2)
        assert outcome.unconnected_pairs == 2, stored  # (a, c) and (b, c)
        assert outcome.added == 1


async def test_the_whole_view_is_the_readers_not_the_stored_set() -> None:
    """With no ids named, the ids asked about are the reader's visible nodes."""
    with_hidden, graph_with = await _outcome(hidden_id_is_stored=True, degree=1, ids=None)
    without, graph_without = await _outcome(hidden_id_is_stored=False, degree=1, ids=None)
    assert graph_with.edges_among_requests == graph_without.edges_among_requests
    assert with_hidden.model_dump() == without.model_dump()


@pytest.mark.parametrize("degree", [1, 2, 3])
async def test_a_stored_id_in_another_dataset_behaves_as_an_absent_one_for_a_reader_of_the_case(
    degree: int,
) -> None:
    """Violation caught (rule 3): the membership read judged on handling alone, so a node stored
    in another dataset (OFFICIAL, hidden only by the case's datasets) counted as the reader's and
    raised `unconnected_pairs` and the graph's requests as a hidden id did."""
    reader = OFFICIAL_READER.model_copy(update={"datasets": ["fixture"]})
    results = []
    for stored in (True, False):
        store = FakeWorkingSetStore()
        held = [
            node("a").model_copy(update={"datasets": ["fixture"]}),
            node("b").model_copy(update={"datasets": ["fixture"]}),
        ]
        if stored:
            held.append(node("x").model_copy(update={"datasets": ["enron"]}))
        await store.add_nodes("inv-1", held)
        graph = FakeGraphPort(
            Subgraph(nodes=[], edges=[]),
            graph_nodes=held,
            graph_edges=[edge("ab", "a", "b")],
        )
        outcome = await WorkingSetService(graph, store, SCHEME).links_among(
            "inv-1", reader, ["a", "b", "x"], degree
        )
        results.append((outcome.model_dump(), graph.edges_among_requests))

    assert results[0] == results[1]
