"""`WorkingSetService.add_by_identifiers` (ADR-128 decision 1, B2): the nodes found from a list go
in through the working set's own seed, so the cap check, the Vault re-read and the delta are the
ones every other add gets.

What a mistake would do, and the case that catches it:

- the default adding links nobody asked for (`test_by_default_no_links_are_added`);
- "Add with all links" asking the graph for the links among the added nodes alone, leaving out
  those to nodes already on the canvas
  (`test_with_links_asks_for_the_links_among_the_new_and_the_view`);
- an add that went round `seed` and so round its cap and its re-read
  (`test_both_paths_go_through_seed`);
- a large view named in full to the graph (`test_a_large_view_is_not_named_to_the_graph`).

The cap itself is `seed`'s, proved in the working-set suite; a cap breach here is that same
`LimitExceededError`, which the route renders as the typed `limit_exceeded` with its three options
(`test_add_by_identifiers_route.py`).
"""

from __future__ import annotations

from typing import Any

from services.api.working_set.models import DeltaAdd, ExpansionOutcome
from services.api.working_set.service import AUTO_LINKS_MAX_VIEW_NODES, WorkingSetService

from schemas.domain import Edge, Node, Principal
from tests.services.api.test_add_by_identifiers import ANALYST, _person


class _View:
    def __init__(self, visible: set[str], nodes: int) -> None:
        self.visible = visible
        self.nodes = nodes
        self.named = False

    async def would_add(
        self, node_ids: Any, edge_ids: Any, nodes: Any = None
    ) -> tuple[int, int, Any]:
        return len({i for i in node_ids if i not in self.visible}), 0, None

    async def visible_node_ids(self) -> set[str]:
        self.named = True
        return set(self.visible)


class _Graph:
    def __init__(self) -> None:
        self.among: list[list[str]] = []

    async def edges_among(self, ids: list[str], principal: Principal) -> list[Edge]:
        self.among.append(ids)
        return []


class _Service:
    """Stands for the service: `seed` and the reader's counts are its own, proved elsewhere."""

    def __init__(self, view: _View) -> None:
        self._view = view
        self._graph = _Graph()
        self.seeded: list[tuple[str, list[str], list[Edge]]] = []

    async def _reader_counts(self, investigation_id: str, principal: Principal) -> _View:
        return self._view

    async def seed(
        self, investigation_id: str, nodes: list[Node], edges: list[Edge], principal: Principal
    ) -> ExpansionOutcome:
        self.seeded.append((investigation_id, [n.id for n in nodes], list(edges)))
        return ExpansionOutcome(delta=DeltaAdd(seq=7, nodes=nodes, edges=list(edges)))


NODES = [_person("p1"), _person("p2")]


async def test_by_default_no_links_are_added() -> None:
    service = _Service(_View({"x"}, 1))
    outcome = await WorkingSetService.add_by_identifiers(  # type: ignore[arg-type]
        service, "inv-1", NODES, ANALYST
    )
    assert service.seeded == [("inv-1", ["p1", "p2"], [])]
    assert service._graph.among == []
    assert outcome.delta.seq == 7


async def test_with_links_asks_for_the_links_among_the_new_and_the_view() -> None:
    service = _Service(_View({"x", "y"}, 2))
    outcome = await WorkingSetService.add_by_identifiers(  # type: ignore[arg-type]
        service, "inv-1", NODES, ANALYST, with_links=True
    )
    assert service._graph.among == [["p1", "p2", "x", "y"]]
    assert outcome.links_among == "added"


async def test_both_paths_go_through_seed() -> None:
    for with_links in (False, True):
        service = _Service(_View(set(), 0))
        await WorkingSetService.add_by_identifiers(  # type: ignore[arg-type]
            service, "inv-1", NODES, ANALYST, with_links=with_links
        )
        assert [s[1] for s in service.seeded] == [["p1", "p2"]]


async def test_a_large_view_is_not_named_to_the_graph_and_the_outcome_says_not_asked() -> None:
    """Rule 2: nothing was asked for the links to the canvas, so the outcome must not say `added`
    (which means every link among what was named): it says `not_asked`, as `expand` does."""
    view = _View({"x"}, AUTO_LINKS_MAX_VIEW_NODES)
    service = _Service(view)
    outcome = await WorkingSetService.add_by_identifiers(  # type: ignore[arg-type]
        service, "inv-1", NODES, ANALYST, with_links=True
    )
    assert view.named is False
    assert service._graph.among == []
    assert [s[1] for s in service.seeded] == [["p1", "p2"]]
    assert outcome.links_among == "not_asked"


async def test_no_ask_for_links_names_more_ids_than_the_one_ask_limit() -> None:
    """Thousands of identifiers found on an empty canvas: the ids named to the graph in one ask
    never pass `AUTO_LINKS_MAX_VIEW_NODES`, whatever the view's size."""
    many = [_person(f"p{n}") for n in range(AUTO_LINKS_MAX_VIEW_NODES + 5)]
    service = _Service(_View(set(), 0))
    outcome = await WorkingSetService.add_by_identifiers(  # type: ignore[arg-type]
        service, "inv-1", many, ANALYST, with_links=True
    )
    assert all(len(ids) <= AUTO_LINKS_MAX_VIEW_NODES for ids in service._graph.among)
    assert outcome.links_among == "not_asked"
