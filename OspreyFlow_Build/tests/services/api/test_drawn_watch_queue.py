"""A drawn watch's alert in the one queue, withheld whole (ADR-143 Amendment 2 decision 8; ADR-146
decisions 1 and 10; rule 3; L3.6).

A load meeting a drawn item raises one `drawn_watch` alert (`drawn_watches.drawn_watch_alert`),
citing the drawn item and the loaded node. The queue reads every alert's evidence as the reader,
through the adapter's access step, and leaves out whole an alert any of whose evidence is missing
from that answer (`alert_queue.monitoring_queue`, ADR-039's all-or-nothing). These cases run the
real alert, built by the real function from a real match, through the real queue, against a graph
that answers as the adapter does (a hidden id is absent from `get_nodes`'s answer, never an error;
rule 15):

- a reader who may not see the drawn item is shown nothing of the alert: no row, no count, no
  change of order, and the same reads as when it is readable (rule 7) —
  `test_an_alert_over_a_drawn_item_the_reader_may_not_see_is_withheld_whole`;
- the same for the loaded node —
  `test_an_alert_over_a_loaded_node_the_reader_may_not_see_is_withheld`;
- the alert names who it is for and where —
  `test_the_alert_is_the_watch_owners_in_the_watchs_case`.

Shown red with the drawn item left out of the alert's evidence (`gates/L3.6-plants.py`). Which rows
the query returns for whom is the live counterpart, `test_drawn_watch_queue_live.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from services.api import alert_queue
from services.api.alerts import QueueRow
from services.api.drawn_watches import DrawnWatchMatch, drawn_watch_alert, drawn_watch_rule

from schemas.boards import DrawnWatch
from schemas.domain import (
    Alert,
    AlertMode,
    AuditStub,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from tests.services.api.no_transactions import NO_TRANSACTIONS
from tests.services.api.repoint_journal_fakes import RaiserReads

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
CASE = "case-1"
READER = Principal(id="alice", clearance="OFFICIAL", org_unit="unit-1", datasets=["src", "layer"])
_HANDLING = {"classification": "OFFICIAL", "handling_code": "P", "originator": "unit-1",
             "owning_unit": "unit-1"}  # fmt: skip


def _node(node_id: str, *, drawn: bool = False) -> Node:
    return Node(
        id=node_id, type="Person", properties={"family_name": f"Name of {node_id}"},
        datasets=["layer"] if drawn else ["src"],
        provenance=Provenance(
            state=ProvenanceState.ASSERTED, first_seen=NOW,
            sources=[SourceRef(document_id="doc-1", locator="row 1", excerpt_hash="a" * 64)],
        ),
        handling=_HANDLING,  # type: ignore[arg-type]
        audit=AuditStub(created_at=NOW, created_by="loader-1"),
    )  # fmt: skip


def _match(drawn: str, loaded: str, *, minute: int = 0) -> DrawnWatchMatch:
    watch = DrawnWatch(id=f"w-{drawn}", item_id=f"i-{drawn}", element_id=drawn, case_id=CASE,
                       dataset_id="src", owner="alice", created_at=NOW)  # fmt: skip
    return DrawnWatchMatch(watch=watch, drawn=_node(drawn, drawn=True), loaded=_node(loaded),
                           score=1.0, why="the same pnc_id", load_id="load-1",
                           matched_at=NOW.replace(minute=minute))  # fmt: skip


class Graph:
    """`get_nodes` and `get_edges` as the adapter answers them: an id the reader may not read is
    absent. Every read recorded, so the reads with and without a hidden alert can be compared."""

    def __init__(self, hidden: set[str]) -> None:
        self.hidden = hidden
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    async def get_nodes(self, node_ids: Any, principal: Principal) -> list[Node]:
        ids = tuple(sorted(set(node_ids)))
        self.calls.append(("get_nodes", ids))
        return [_node(i, drawn=i.startswith("d-")) for i in ids if i not in self.hidden]

    async def get_edges(self, edge_ids: Any, principal: Principal) -> list[Any]:
        self.calls.append(("get_edges", tuple(sorted(set(edge_ids)))))
        return []


class Store(RaiserReads):
    """The rows the query returned for the reader (which rows is the live file's), as
    `AlertStore.list_queue` returns them; the journal holds nothing to settle."""

    def __init__(self, alerts: list[Alert]) -> None:
        self.alerts = alerts

    async def settle_pending(self, graph: Any, *, now: Any = None) -> None:
        return None

    def held_alert_ids(self) -> set[str]:
        return {a.id for a in self.alerts}

    async def list_queue(
        self, investigation_id: str, reader: Principal, **_: object
    ) -> list[QueueRow]:
        return [QueueRow(a, "drawn_watch", "medium", "owner") for a in self.alerts]


async def _shown(alerts: list[Alert], hidden: set[str]) -> tuple[list[str], Graph]:
    graph = Graph(hidden)
    store: Any = Store(alerts)
    queued = await alert_queue.monitoring_queue(store, graph, NO_TRANSACTIONS, CASE, READER)  # type: ignore[arg-type]
    return [q.alert.id for q in queued], graph


FIRST, _ = drawn_watch_alert(_match("d-1", "p-1", minute=3))
OVER_SECRET_DRAWN, _ = drawn_watch_alert(_match("d-secret", "p-2", minute=2))
OVER_SECRET_LOADED, _ = drawn_watch_alert(_match("d-2", "p-secret", minute=2))
LAST, _ = drawn_watch_alert(_match("d-3", "p-3", minute=1))


async def test_an_alert_over_a_drawn_item_the_reader_may_not_see_is_withheld_whole() -> None:
    """No row, the rest in the same order, and the same reads as when the drawn item is readable:
    nothing says by count, order or the work done that the alert is there (rules 3 and 7)."""
    shown, hidden_reads = await _shown([FIRST, OVER_SECRET_DRAWN, LAST], {"d-secret"})
    assert shown == [FIRST.id, LAST.id]
    without, _ = await _shown([FIRST, LAST], {"d-secret"})
    assert shown == without
    readable, open_reads = await _shown([FIRST, OVER_SECRET_DRAWN, LAST], set())
    assert readable == [FIRST.id, OVER_SECRET_DRAWN.id, LAST.id]
    assert hidden_reads.calls == open_reads.calls


async def test_an_alert_over_a_loaded_node_the_reader_may_not_see_is_withheld() -> None:
    shown, _ = await _shown([FIRST, OVER_SECRET_LOADED, LAST], {"p-secret"})
    assert shown == [FIRST.id, LAST.id]


async def test_the_alert_is_the_watch_owners_in_the_watchs_case() -> None:
    """Its kind is read from its rule (`drawn_watch:<watch>`); it is its owner's, in the watch's
    case, on the watched dataset (the queue's reach), citing the two nodes; its words name them
    by id only, each named at every read as the reader reads it (`alert_queue.summary_of`)."""
    match = _match("d-1", "p-1")
    alert, handlings = drawn_watch_alert(match)
    assert alert.rule_id == drawn_watch_rule("w-d-1") == "drawn_watch:w-d-1"
    assert (alert.owner_id, alert.investigation_id, alert.dataset_id) == ("alice", CASE, "src")
    assert alert.referent_node_ids == ["d-1", "p-1"]
    assert alert.mode is AlertMode.FULL and alert.team is None and alert.routed_team is None
    assert alert.created_at == match.matched_at
    assert len(handlings) == 2
    named = alert_queue.summary_of(alert, {"d-1": _node("d-1", drawn=True), "p-1": _node("p-1")})
    assert (
        "Name of p-1" in named
        and "Name of d-1" in named
        and "p-1" not in named.replace("Name of p-1", "")
    )
