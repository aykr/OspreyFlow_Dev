"""A node that comes back to the view brings the links stored at it (build order step 18c, D5).

"Clear view" and "Remove from view" remove nodes and leave their links stored, with that end
absent (`WorkingSetStore.remove_edges`'s docstring). When the node is added again, those links join
the view: `would_add` counts them against the cap, and a snapshot draws them. But the change the add
returned
carried the requested elements alone, so the Glass never drew them, and `links_among`, finding them
already stored, added nothing: at the 3 November rehearsal's J5 the selection bar said there were no
routes between two nodes Find connections joins at two degrees.

What a mistake would do, and the case that catches it:
- the returning node's links left out of the change, so the canvas and the working set disagree:
  `test_a_returning_node_brings_its_stored_links_into_the_change`;
- a returning link the reader may not read put in their change (rule 3): the same request with that
  link hidden and with no such link at all gives the same change:
  `test_a_returning_link_the_reader_may_not_read_is_not_in_the_change`."""

from __future__ import annotations

from services.api.working_set.service import WorkingSetService

from schemas.domain import Subgraph

from .fakes import FakeGraphPort, FakeWorkingSetStore
from .test_visible_link import OFFICIAL_READER, SCHEME, edge, node


async def _returned(hidden: bool | None) -> list[str]:
    """`a`, `b` and `c` in view with links a-b and b-c (b-c SECRET when `hidden`, absent when
    None); `c` is removed, as Clear view does, then seeded back. Answers the change's link ids."""
    store = FakeWorkingSetStore()
    a, b = node("a"), node("b")
    c = node("c")
    links = [edge("ab", "a", "b")]
    if hidden is not None:
        links.append(edge("bc", "b", "c", "SECRET" if hidden else "OFFICIAL"))
    await store.add_nodes("inv-1", [a, b, c])
    await store.add_edges("inv-1", links)
    await store.remove_nodes("inv-1", ["c"])
    graph = FakeGraphPort(Subgraph(nodes=[], edges=[]), graph_nodes=[a, b, c], graph_edges=links)
    outcome = await WorkingSetService(graph, store, SCHEME).seed("inv-1", [c], [], OFFICIAL_READER)
    return sorted(e.id for e in outcome.delta.edges)


async def test_a_returning_node_brings_its_stored_links_into_the_change() -> None:
    assert await _returned(hidden=False) == ["bc"]


async def test_a_returning_link_the_reader_may_not_read_is_not_in_the_change() -> None:
    assert await _returned(hidden=True) == await _returned(hidden=None) == []
