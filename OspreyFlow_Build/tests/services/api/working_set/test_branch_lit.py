"""Branching what is lit: the slice a window leaves, derived on the server (ADR-128 decision 2, B3;
rules 2, 3 and 4).

A link is lit when at least one of its events falls inside the brushed window, ends included; an
undated link is never lit; a node is lit when a lit link touches it. The analytics read says which
links are lit (`first_seen`, access-filtered in its own query). `branch_lit_contents` turns that
into what a branch carries: the lit links and their nodes, kept only where the request names a
node, read from the source case's access-filtered view.

What a mistake here would do, and the case that catches it:

- a branch that carried every link among the named nodes, as "Branch selected" does, would put
  links whose events lie outside the window into the new case
  (`test_a_link_among_lit_nodes_that_is_not_itself_lit_is_not_carried`);
- an undated link treated as lit would carry the people it joins
  (`test_an_undated_link_is_never_lit_so_a_node_only_it_touches_is_left_out`);
- a hidden node id that was refused differently from a made-up one would tell the asker the node
  exists (`test_naming_a_hidden_node_reads_as_naming_a_made_up_one`);
- a node the request did not name but a lit link touches would arrive anyway
  (`test_only_the_nodes_the_request_names_are_kept`);
- a slice past the cap that was cut to fit would be a silent truncation
  (`test_a_slice_past_the_cap_is_refused_with_its_figures_and_nothing_is_cut`).

The edge-of-window rule (an event exactly at either end of the window lights its link) is the
analytics port's, in the query, and its conformance case is
`test_first_seen_gives_each_node_and_link_its_earliest_event_in_the_window`.
"""

from __future__ import annotations

import pytest
from services.api.working_set import service as service_module
from services.api.working_set.models import LimitExceededError, NothingToBranchError
from services.api.working_set.service import WorkingSetService

from schemas.domain import Principal, Subgraph

from .fakes import FakeGraphPort, FakeWorkingSetStore
from .test_visible_link import OFFICIAL_READER, SCHEME, edge, node

CASE = "inv-1"


def _service(store: FakeWorkingSetStore) -> WorkingSetService:
    return WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), store, SCHEME)


async def _held() -> FakeWorkingSetStore:
    """Five people and a SECRET one. `ab` and `cd` are lit; `bc` joins two lit people and is not;
    `ex` is undated and joins `e` and `x`; `ah` is lit but its far end is above the reader."""
    store = FakeWorkingSetStore()
    await store.add_nodes(
        CASE,
        [
            node("a"),
            node("b"),
            node("c"),
            node("d"),
            node("e"),
            node("x"),
            node("h", "SECRET"),
        ],
    )
    await store.add_edges(
        CASE,
        [
            edge("ab", "a", "b"),
            edge("bc", "b", "c"),
            edge("cd", "c", "d"),
            edge("ex", "e", "x"),
            edge("ah", "a", "h"),
        ],
    )
    return store


LIT = {"ab", "cd", "ah"}
EVERYONE = ["a", "b", "c", "d", "e", "x", "h"]


async def _carried(
    named: list[str],
    lit: set[str] | None = None,
    reader: Principal = OFFICIAL_READER,
    store: FakeWorkingSetStore | None = None,
) -> tuple[set[str], set[str]]:
    held = store if store is not None else await _held()
    nodes, edges = await _service(held).branch_lit_contents(
        CASE, reader, named, LIT if lit is None else lit
    )
    return {n.id for n in nodes}, {e.id for e in edges}


async def test_the_slice_is_the_lit_links_and_the_nodes_they_touch() -> None:
    nodes, edges = await _carried(EVERYONE)

    assert nodes == {"a", "b", "c", "d"}
    assert edges == {"ab", "cd"}


async def test_a_link_among_lit_nodes_that_is_not_itself_lit_is_not_carried() -> None:
    """`bc` joins two lit people and is the link "Branch selected" would carry; here its events lie
    outside the window, so the branch's own timeline would be wider than the story."""
    _, edges = await _carried(["a", "b", "c", "d"])

    assert "bc" not in edges


async def test_an_undated_link_is_never_lit_so_a_node_only_it_touches_is_left_out() -> None:
    nodes, edges = await _carried(EVERYONE)

    assert "ex" not in edges
    assert not {"e", "x"} & nodes


async def test_only_the_nodes_the_request_names_are_kept() -> None:
    nodes, edges = await _carried(["a", "b"])

    assert nodes == {"a", "b"}
    assert edges == {"ab"}


async def test_a_named_node_no_lit_link_touches_is_ignored() -> None:
    nodes, _ = await _carried(["a", "b", "e"])

    assert nodes == {"a", "b"}


async def test_a_link_is_carried_only_when_both_its_ends_are_named() -> None:
    nodes, edges = await _carried(["a", "c", "d"])

    assert nodes == {"a", "c", "d"}
    assert edges == {"cd"}


async def test_naming_a_hidden_node_reads_as_naming_a_made_up_one() -> None:
    """Violation caught (rule 3): `h` is above the reader and joined to `a` by a lit link. Naming
    it must give what naming `ghost` gives, with the same nodes and links, and when it is the only
    name, the same refusal. A branch that carried it, or refused one and not the other, would tell
    the asker it exists."""
    with_hidden = await _carried(["a", "b", "h"])
    with_made_up = await _carried(["a", "b", "ghost"])
    assert with_hidden == with_made_up == ({"a", "b"}, {"ab"})

    for only in ("h", "ghost"):
        with pytest.raises(NothingToBranchError):
            await _carried([only])


async def test_a_lit_link_to_a_node_above_the_reader_is_not_carried() -> None:
    _, edges = await _carried(EVERYONE)

    assert "ah" not in edges


async def test_a_cleared_reader_does_carry_what_the_first_could_not_see() -> None:
    """The red half of the access case: the filter is real, because a reader cleared for `h` gets
    it, and its link."""
    nodes, edges = await _carried(
        EVERYONE, reader=Principal(id="analyst-2", clearance="SECRET", org_unit="unit-1")
    )

    assert "h" in nodes
    assert "ah" in edges


async def test_a_lit_id_that_is_not_a_link_in_the_case_carries_nothing() -> None:
    """The analytics answer is by link id; one this case's view does not hold lights nothing."""
    with pytest.raises(NothingToBranchError):
        await _carried(EVERYONE, lit={"no-such-link"})


async def test_nothing_lit_is_refused_as_branch_refuses_nothing() -> None:
    with pytest.raises(NothingToBranchError):
        await _carried(EVERYONE, lit=set())


async def test_an_empty_choice_is_refused() -> None:
    with pytest.raises(NothingToBranchError):
        await _carried([])


@pytest.fixture
def small_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "MAX_NODES", 3)


async def test_a_slice_past_the_cap_is_refused_with_its_figures_and_nothing_is_cut(
    small_cap: None,
) -> None:
    with pytest.raises(LimitExceededError) as refused:
        await _carried(["a", "b", "c", "d"])

    detail = refused.value.detail
    assert (detail.cap_kind, detail.cap, detail.would_be) == ("nodes", 3, 4)
    assert detail.options == ("branch", "filter", "promote_to_batch")


async def test_a_hidden_node_does_not_move_the_figure_of_a_refusal(small_cap: None) -> None:
    """The figure is the reader's own slice: naming the hidden node, or a made-up one, gives the
    same refusal."""
    figures = []
    for extra in ("h", "ghost"):
        with pytest.raises(LimitExceededError) as refused:
            await _carried(["a", "b", "c", "d", extra])
        figures.append(refused.value.detail.model_dump())

    assert figures[0] == figures[1] and figures[0]["would_be"] == 4
