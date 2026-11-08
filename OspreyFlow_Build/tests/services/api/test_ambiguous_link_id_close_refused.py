"""ADR-110 Amendment 18 at the true-positive close (`alert_queue.dispose`, its `_close`): a close
confirms each cited `SAME_AS` link in one transaction, for the person closing. A link whose id two
edge types hold cannot be confirmed with certainty, so the close is refused whole. The
transaction is rolled back, nothing is confirmed, and the queue row is not closed. The person is
answered `409 link_id_ambiguous` by the app's handler (`test_ambiguous_link_id_refused.py`). A
close half confirmed would be worse than none (the orchestrator's ruling, QF a). Red with the
close's rollback or its refusal removed (`process/lanes/studio/L1.2a_RED_RECORD.md`). Glass's L2.8b
journal, reworking `_close`, keeps no record of a refused close: its own test covers that."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from ports.graph import AmbiguousLinkId
from schemas.domain import Alert, AlertMode, EdgeWrite, ProvenanceState
from services.api.alert_queue import dispose
from services.api.alerts import QueueRow

from tests.services.api.no_transactions import NO_TRANSACTIONS
from tests.services.api.test_written_back_reads_in_full_stages import (
    SCOPED,
    TWO,
    _Graph,
)
from tests.services.api.working_set.test_visible_link import edge, node


class _Ambiguous(_Graph):
    """The cited link's id is held by two edge types: `supersede_edge` refuses it, as the adapter
    does, and the close's transaction is watched."""

    def __init__(self, *a: Any, **k: Any) -> None:
        super().__init__(*a, **k)
        self.begun = self.rolled_back = self.committed = 0

    async def begin_transaction(self) -> str:
        self.begun += 1
        return "tx"

    async def commit_transaction(self, tx: Any) -> None:
        self.committed += 1

    async def rollback_transaction(self, tx: Any) -> None:
        self.rolled_back += 1

    async def supersede_edge(self, edge_id: str, replacement: EdgeWrite, tx: Any) -> str:
        raise AmbiguousLinkId(edge_id, ["SAME_AS", "OTHER"])


async def test_a_true_positive_citing_an_ambiguous_link_is_refused_whole() -> None:
    person = node("p1").model_copy(update={"datasets": list(TWO)})
    other = node("p2").model_copy(update={"datasets": list(TWO)})
    link = edge("sa1", "p1", "p2").model_copy(
        update={
            "type": "SAME_AS",
            "datasets": list(TWO),
            "provenance": edge("x", "p1", "p2").provenance.model_copy(
                update={"state": ProvenanceState.INFERRED}
            ),
        }
    )
    graph = _Ambiguous([person, other], [link])
    alert = Alert(
        id="al-1", rule_id="r", owner_id="analyst-1", mode=AlertMode.FULL,
        referent_node_ids=["p2"], created_at=datetime(2026, 1, 1, tzinfo=UTC),
        typology="kyc_screening", alert_node_id="p1", edge_ids=["sa1"],
    )  # fmt: skip
    closed: list[str] = []

    class _Store:
        async def get_queue_alert(self, alert_id: str, *_a: Any, **_k: Any) -> QueueRow:
            return QueueRow(alert, "typology", "medium", "case")

        async def set_queue_triage(self, alert_id: str, *_a: Any, **_k: Any) -> Alert:
            closed.append(alert_id)
            return alert

    with pytest.raises(AmbiguousLinkId):
        await dispose(
            _Store(),  # type: ignore[arg-type]
            graph,
            NO_TRANSACTIONS,
            "inv-1",
            "al-1",
            SCOPED,
            disposition="true_positive",
            reason="confirmed",
        )

    assert (graph.begun, graph.rolled_back, graph.committed) == (1, 1, 0), "rolled back whole"
    assert closed == [], "the queue row is not closed"
    assert graph.edge_writes == []
