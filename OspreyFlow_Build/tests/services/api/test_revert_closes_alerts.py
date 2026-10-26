"""ADR-127 Amendment 6 and ADR-039: an alert that cites something a revert took back is gone from
the alert queue for every reader.

Three alerts, all in one case:

- **A**: raised by a rule over the reverted load. Its own `Alert` node is one the load's record
  lists, so the revert closes it by that node (`AlertStore.close_for_elements`).
- **B**: raised over live entities, by a rule of another load, and citing a *node* the revert took
  back. Its own node is in no record. The queue's all-or-nothing read already leaves it out, because
  the cited node is hidden from every reader (`alert_queue._visible_nodes`).
- **C**: also another load's, citing only a *link* the revert took back, with every entity live.
  The queue's read checks only an alert's nodes, so C stayed listed as open work (opening it found
  a link missing). The revert therefore closes an alert by the links it cites too; C is then in the
  queue only as a closed alert, never as open or claimed work.

The graph here hides a reverted element from every reader, as the adapter's access step does
(`test_a_revert_takes_the_nodes_and_links_out_of_every_read_for_every_reader`); the store holds to
`AlertStore`'s two methods, whose SQL `test_recipe_runs.py` proves live."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from services.api import alert_queue
from services.ingest.load_revert import RevertDeps, revert

from schemas.domain import Alert, AlertMode, Principal
from tests.ingest.test_revert_load import (
    Analytics,
    Audit,
    Held,
    Ledger,
    Steps,
    WorkingSets,
    _record,
    no_caches,
)

T0 = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)
CASE = "case-1"
OFFICIAL = Principal(id="reader-o", clearance="OFFICIAL", org_unit="unit-1")
CLEARED = Principal(id="reader-s", clearance="SECRET", org_unit="unit-1")


class Graph:
    """Nodes and links, each hidden from every reader once reverted."""

    def __init__(self, nodes: set[str], links: set[str]) -> None:
        self.nodes, self.links, self.reverted = nodes, links, set[str]()

    async def get_node(self, node_id: str, principal: Principal) -> Any:
        live = node_id in self.nodes and node_id not in self.reverted
        return SimpleNamespace(id=node_id, type="Person", properties={}) if live else None

    async def begin_transaction(self) -> str:
        return "tx"

    async def commit_transaction(self, tx: str) -> None:
        return None

    async def rollback_transaction(self, tx: str) -> None:
        return None

    async def revert_elements(self, node_ids: Any, edge_ids: Any, tx: str) -> None:
        self.reverted.update(node_ids)
        self.reverted.update(edge_ids)

    # The revert's three unfiltered lookups: nothing outside the load rests on it, names its points
    # or has rewritten its nodes, which is not what this case is about.
    async def live_edges_touching(self, node_ids: Any) -> set[str]:
        return set()

    async def live_nodes_naming_geometry(self, refs: Any) -> dict[str, set[str]]:
        return {}

    async def stored_writes(self, node_ids: Any) -> dict[str, Any]:
        return {}

    async def stored_link_states(self, edge_ids: Any) -> dict[str, Any]:
        return {}


class Store:
    """`AlertStore.list_case_queue` and `close_for_elements`, with the same matching: an alert not
    already closed is closed when its own node, a node it cites or a link it cites is named."""

    def __init__(self, *alerts: Alert) -> None:
        self.alerts = {a.id: a for a in alerts}

    async def list_case_queue(self, investigation_id: str, principal: Principal) -> list[Alert]:
        return [a for a in self.alerts.values() if a.investigation_id == investigation_id]

    async def alerts_citing_events(self) -> dict[str, list[str]]:
        return {}

    async def close_by_ids(
        self, alert_ids: Any, *, closed_by: str, at: datetime, reason: str
    ) -> int:
        return 0

    async def close_for_elements(
        self, node_ids: Any, edge_ids: Any, *, closed_by: str, at: datetime, reason: str
    ) -> int:
        nodes, links = set(node_ids), set(edge_ids)
        closed = 0
        for alert in list(self.alerts.values()):
            hit = (
                alert.alert_node_id in nodes
                or bool(nodes & set(alert.referent_node_ids))
                or bool(links & set(alert.edge_ids))
            )
            if hit and alert.status != "closed":
                self.alerts[alert.id] = alert.model_copy(update={"status": "closed"})
                closed += 1
        return closed


def _alert(alert_id: str, **fields: Any) -> Alert:
    base: dict[str, Any] = {
        "id": alert_id,
        "rule_id": "rule-1",
        "owner_id": "owner-1",
        "mode": AlertMode.FULL,
        "investigation_id": CASE,
        "created_at": T0,
        "typology": "structuring",
        "words": f"finding {alert_id}",
        "referent_node_ids": [],
        "edge_ids": [],
    }
    return Alert(**{**base, **fields})


async def _queue(store: Store, graph: Graph, reader: Principal, **kwargs: Any) -> list[str]:
    shown = await alert_queue.queue(store, graph, CASE, reader, **kwargs)  # type: ignore[arg-type]
    return sorted(q.alert.id for q in shown)


async def test_an_alert_citing_something_a_revert_took_back_is_gone_from_the_queue_for_every_reader() -> (
    None
):
    graph = Graph(
        nodes={"alert-node-a", "alert-node-b", "alert-node-c", "doc-gone", "p1", "p2"},
        links={"link-gone", "link-kept"},
    )
    store = Store(
        _alert("A", alert_node_id="alert-node-a", referent_node_ids=["p1"]),
        _alert("B", alert_node_id="alert-node-b", referent_node_ids=["doc-gone", "p2"]),
        _alert("C", alert_node_id="alert-node-c", referent_node_ids=["p1"], edge_ids=["link-gone"]),
        _alert("D", alert_node_id="alert-node-c", referent_node_ids=["p2"], edge_ids=["link-kept"]),
    )
    open_only = {"statuses": ["open", "claimed"]}
    for reader in (OFFICIAL, CLEARED):
        assert await _queue(store, graph, reader) == ["A", "B", "C", "D"]

    # The load wrote A's node and the link C cites and the node B cites.
    record = _record(
        "load-1",
        created_node_ids=["alert-node-a", "doc-gone"],
        created_edge_ids=["link-gone"],
    )
    steps = Steps()
    deps = RevertDeps(
        ledger=Ledger(record),
        graph=graph,  # type: ignore[arg-type]
        analytics=Analytics(steps),  # type: ignore[arg-type]
        held_rows=Held(steps),
        alerts=store,
        audit=Audit(steps),
        working_sets=WorkingSets(steps),
        invalidate_caches=no_caches,
    )
    await revert("load-1", reverted_by="operator-1", deps=deps, now=T0)

    for reader in (OFFICIAL, CLEARED):
        # Open work: only D. Listed with every status, A and B are hidden by the read (a node they
        # rest on is hidden), and C is there as a *closed* alert, because the read cannot tell that
        # a link it cites was taken back; it is not open work and opens as not found.
        assert await _queue(store, graph, reader, **open_only) == ["D"], reader.id
        assert await _queue(store, graph, reader) == ["C", "D"], reader.id
    # B is left out by the read itself, with no help from the store (a cited node is hidden);
    # C is left out because the revert closed it. Nothing else was touched.
    assert {a.id: a.status for a in store.alerts.values()} == {
        "A": "closed",
        "B": "closed",
        "C": "closed",
        "D": "open",
    }


async def test_without_the_close_an_alert_citing_only_a_reverted_link_stays_listed() -> None:
    """Why the revert closes by links (rule 15 for the test above): the queue's own read leaves C in,
    since every node it names is live. The test above fails if the close drops the links."""
    graph = Graph(nodes={"alert-node-c", "p1"}, links={"link-gone"})
    graph.reverted.add("link-gone")
    store = Store(_alert("C", alert_node_id="alert-node-c", referent_node_ids=["p1"],
                         edge_ids=["link-gone"]))  # fmt: skip
    for reader in (OFFICIAL, CLEARED):
        assert await _queue(store, graph, reader) == ["C"]
