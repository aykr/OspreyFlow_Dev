"""The caps and the preview count the reader's own projected view (ADR-124 decision 2; rules 3, 7).

`CardinalityPreview.candidate_node_count` and `candidate_edge_count`, `LimitExceeded.would_be`,
`ensure_room`'s check and `expand`'s choice of asking for the links among its nodes were each
counted over the stored set, hidden items included. A radial menu previews each link type
separately, so subtracting the visible figure from the stored one located a hidden link by its type
and its two ends. Each is now counted over `_project` of the stored set for the reader asking, plus
what the request adds: a link counts only when it and both its ends are readable.

Each case builds the same case twice, once with nothing the reader may not read and once with a
stored item of each kind they may not, and asserts that every figure the reader is shown is equal.
The kinds are the three that tell a per-element count from the projection:

- a stored node above the reader's clearance;
- a stored link, readable on its own marking, to such a node (it is in no view of theirs);
- a stored link above the reader's clearance between two nodes they can read.

Plants, each shown red in the hand-back: counting the stored ids (the old behaviour), and counting
each readable element on its own marking (which counts the link to a hidden node).
"""

from __future__ import annotations

import pytest
from services.api.working_set import service as service_module
from services.api.working_set.models import LimitExceededError
from services.api.working_set.service import WorkingSetService

from schemas.domain import Edge, ExpandRequest, Node, Subgraph

from .fakes import FakeGraphPort, FakeWorkingSetStore
from .test_visible_link import OFFICIAL_READER, SCHEME, SECRET_READER, edge, node

CASE = "case-1"
REQ = ExpandRequest(node_ids=["a"], depth=1)

#: A stored item the reader may not read, of each kind, and the case with none of them.
HIDDEN_KINDS: dict[str, tuple[list[Node], list[Edge]]] = {
    "nothing hidden": ([], []),
    "a node above clearance": ([node("s", "SECRET")], []),
    "a readable link to a hidden node": (
        [node("s", "SECRET")],
        [edge("a-s", "a", "s", "OFFICIAL")],
    ),
    "a hidden link between readable nodes": ([], [edge("a-b-secret", "a", "b", "SECRET")]),
    "all three": (
        [node("s", "SECRET")],
        [edge("a-s", "a", "s", "OFFICIAL"), edge("a-b-secret", "a", "b", "SECRET")],
    ),
}


async def _case(
    kind: str, expansion: Subgraph, *, graph_edges: list[Edge] | None = None
) -> tuple[WorkingSetService, FakeGraphPort, FakeWorkingSetStore]:
    """The case with two readable nodes and one readable link, plus the stored items of `kind`."""
    hidden_nodes, hidden_edges = HIDDEN_KINDS[kind]
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("a"), node("b"), *hidden_nodes])
    await store.add_edges(CASE, [edge("a-b", "a", "b"), *hidden_edges])
    graph = FakeGraphPort(expansion, 0, graph_edges=graph_edges or [])
    return WorkingSetService(graph, store, SCHEME), graph, store


@pytest.mark.parametrize("kind", HIDDEN_KINDS)
async def test_the_previews_counts_are_equal_with_and_without_a_hidden_stored_item(
    kind: str,
) -> None:
    expansion = Subgraph(nodes=[node("a"), node("c")], edges=[edge("a-c", "a", "c")])
    service, _, _ = await _case(kind, expansion)
    plain, _, _ = await _case("nothing hidden", expansion)

    preview = await service.expand_preview(CASE, REQ, OFFICIAL_READER)
    expected = await plain.expand_preview(CASE, REQ, OFFICIAL_READER)

    assert preview == expected
    # Two readable stored nodes and the one new; one readable stored link and the one new.
    assert (preview.candidate_node_count, preview.candidate_edge_count) == (3, 2)
    assert preview.would_breach is None


@pytest.mark.parametrize("kind", HIDDEN_KINDS)
async def test_a_node_cap_breach_reports_the_same_would_be_with_and_without_a_hidden_item(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service_module, "MAX_NODES", 3)
    expansion = Subgraph(nodes=[node("a"), node("c"), node("d")], edges=[])
    service, _, store = await _case(kind, expansion)
    plain, _, _ = await _case("nothing hidden", expansion)

    figures = []
    for target in (service, plain):
        preview = await target.expand_preview(CASE, REQ, OFFICIAL_READER)
        assert preview.would_breach is not None
        with pytest.raises(LimitExceededError) as expanded:
            await target.expand(CASE, REQ, OFFICIAL_READER)
        with pytest.raises(LimitExceededError) as seeded:
            await target.seed(CASE, [node("c"), node("d"), node("e")], [], OFFICIAL_READER)
        with pytest.raises(LimitExceededError) as roomed:
            await target.ensure_room(CASE, ["c", "d", "e"], [], OFFICIAL_READER)
        figures.append(
            (
                preview.would_breach.would_be,
                expanded.value.detail.would_be,
                seeded.value.detail.would_be,
                roomed.value.detail.would_be,
            )
        )

    assert figures[0] == figures[1] == (4, 4, 5, 5)
    # Nothing was written by a refused request, and the hidden items are still stored.
    assert await store.node_count(CASE) == 2 + len(HIDDEN_KINDS[kind][0])


@pytest.mark.parametrize("kind", HIDDEN_KINDS)
async def test_a_link_cap_breach_reports_the_same_would_be_with_and_without_a_hidden_item(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service_module, "MAX_EDGES", 2)
    expansion = Subgraph(
        nodes=[node("a"), node("c")],
        edges=[edge("a-c", "a", "c"), edge("a-c2", "a", "c"), edge("a-c3", "a", "c")],
    )
    service, _, _ = await _case(kind, expansion)
    plain, _, _ = await _case("nothing hidden", expansion)

    seen = []
    for target in (service, plain):
        with pytest.raises(LimitExceededError) as expanded:
            await target.expand(CASE, REQ, OFFICIAL_READER)
        with pytest.raises(LimitExceededError) as roomed:
            await target.ensure_room(CASE, [], ["x", "y"], OFFICIAL_READER)
        seen.append((expanded.value.detail, roomed.value.detail.would_be))

    assert seen[0] == seen[1]
    assert seen[0][0].cap_kind == "edges" and seen[0][0].would_be == 4
    assert seen[0][1] == 3


@pytest.mark.parametrize("kind", HIDDEN_KINDS)
async def test_the_choice_to_ask_for_links_among_does_not_move_with_a_hidden_stored_node(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`expand` asks the graph for the links among its nodes and the view only while the view is at
    most `AUTO_LINKS_MAX_VIEW_NODES`. Counting the stored set, a hidden node pushes a reader over
    the line that another reader, with none stored, is under: the choice is a yes or no they can
    read off the response, and the ids asked for are what the adapter is given."""
    monkeypatch.setattr(service_module, "AUTO_LINKS_MAX_VIEW_NODES", 3)
    expansion = Subgraph(nodes=[node("a"), node("c")], edges=[])
    service, graph, _ = await _case(kind, expansion)

    outcome = await service.expand(CASE, REQ, OFFICIAL_READER)

    assert outcome.links_among == "added"
    ((asked, principal),) = graph.edges_among_requests
    assert asked == ["a", "b", "c"] and principal == OFFICIAL_READER


async def test_a_reader_who_can_read_the_item_is_counted_with_it() -> None:
    """The figures are the reader's own, not zero for everyone: a reader cleared for the SECRET
    node and the link to it has both in their view, so their figures are higher by exactly them.
    Without this, a count that ignored the store altogether would pass every case above."""
    expansion = Subgraph(nodes=[node("a"), node("c")], edges=[edge("a-c", "a", "c")])
    service, _, _ = await _case("all three", expansion)

    cleared = await service.expand_preview(CASE, REQ, SECRET_READER)
    official = await service.expand_preview(CASE, REQ, OFFICIAL_READER)

    assert (cleared.candidate_node_count, cleared.candidate_edge_count) == (4, 4)
    assert (official.candidate_node_count, official.candidate_edge_count) == (3, 2)
