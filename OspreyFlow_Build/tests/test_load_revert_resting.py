"""`links_resting_on` (ADR-127 Amendment 23, "The reset", "What it checks first"): before the Prison
Intelligence reset reverts anything it asks, once, of every load it is about to revert, which live
links outside those loads rest on the nodes they created (resolution `SAME_AS`, a link an analyst
made). It lives in `services/ingest/load_revert.py` because `live_edges_touching` answers whatever
the caller may read and is confined to that module (`test_unfiltered_node_lookup_confined.py`).

What a mistake would do, and the case that catches it:

- a link made by one of the loads themselves counted as resting on them, so every reset is refused
  (`test_a_link_one_of_the_loads_wrote_is_not_resting_on_them`);
- a link outside them that touches a node they made not listed, so the reset reverts half and then
  stops at the first refusal (`test_a_live_link_outside_the_loads_is_listed`);
- the check made one load at a time, so a link resting on the older load alone is missed until the
  newer is already reverted (`test_the_check_is_over_every_load_together`);
- nothing to revert asking the graph (`test_no_loads_ask_the_graph_nothing`).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from services.ingest.load_revert import links_resting_on

from schemas.ingest import LoadRecord

T0 = datetime(2026, 10, 26, 9, tzinfo=UTC)


class _Graph:
    def __init__(self, touching: dict[str, set[str]]) -> None:
        self.touching = touching  # node id -> live link ids at it
        self.asked: list[list[str]] = []

    async def live_edges_touching(self, node_ids: Sequence[str]) -> set[str]:
        self.asked.append(list(node_ids))
        return {e for n in node_ids for e in self.touching.get(n, set())}


def _record(load_id: str, nodes: list[str], links: list[str]) -> LoadRecord:
    return LoadRecord(
        load_id=load_id, recipe_id="r", recipe_version=1, source="x.csv", started_at=T0,
        created_by="w", created_node_ids=nodes, created_edge_ids=links,
    )  # fmt: skip


async def test_a_link_one_of_the_loads_wrote_is_not_resting_on_them() -> None:
    graph = _Graph({"n1": {"own-link"}})
    found = await links_resting_on([_record("a", ["n1"], ["own-link"])], graph)  # type: ignore[arg-type]
    assert found == frozenset()


async def test_a_live_link_outside_the_loads_is_listed() -> None:
    graph = _Graph({"n1": {"own-link", "same-as-1"}, "n2": {"analyst-link"}})
    found = await links_resting_on([_record("a", ["n1", "n2"], ["own-link"])], graph)  # type: ignore[arg-type]
    assert found == frozenset({"same-as-1", "analyst-link"})


async def test_the_check_is_over_every_load_together() -> None:
    """A link the newer load wrote that touches a node the older made is the loads' own, though it
    would be outside the older load alone; one that neither wrote is still outside."""
    graph = _Graph({"older-node": {"newer-link", "analyst-link"}})
    records = [_record("newer", [], ["newer-link"]), _record("older", ["older-node"], [])]
    found = await links_resting_on(records, graph)  # type: ignore[arg-type]
    assert found == frozenset({"analyst-link"})
    assert graph.asked == [["older-node"]]


async def test_no_loads_ask_the_graph_nothing() -> None:
    graph = _Graph({})
    assert await links_resting_on([], graph) == frozenset()  # type: ignore[arg-type]
    assert await links_resting_on([_record("a", [], ["l"])], graph) == frozenset()  # type: ignore[arg-type]
    assert graph.asked == []
