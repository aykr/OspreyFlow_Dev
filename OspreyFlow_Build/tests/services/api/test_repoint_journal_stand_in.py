"""The repoint journal's stand-in (`repoint_journal_fakes.Journal`) and `supersede_journalled`'s
record of the node a route corrects (ADR-109 Amendments 11 and 12), offline. The journal's own
behaviour against the real store is `tests/ingest/test_repoint_journal_callers_live.py`'s.

Rule 15: the stand-in refuses what the real journal refuses, and that refusal is exercised here (the
L2.8c review's item 11), not only stated in its docstring."""

from __future__ import annotations

from typing import Any

import pytest
from services.api.alerts import RepointRecordGone, supersede_journalled

from tests.services.api.repoint_journal_fakes import Journal


class _Graph:
    """Transactions only: what `supersede_journalled` asks of the graph around its write."""

    def __init__(self) -> None:
        self.committed: list[str] = []
        self.rolled_back: list[str] = []

    async def begin_transaction(self) -> str:
        return "tx-1"

    async def commit_transaction(self, tx: str) -> None:
        self.committed.append(tx)

    async def rollback_transaction(self, tx: str) -> None:
        self.rolled_back.append(tx)


async def test_a_pair_recorded_after_its_write_left_is_refused_by_the_stand_in() -> None:
    """The L2.8c review's item 11. The real store refuses a pair recorded in a record already applied
    (`AlertStore._add_to_record` raises `RepointRecordGone`: a pair recorded there would never be
    applied, so its writer must not commit; `test_alert_evidence_withheld_live.py`'s held-open case
    shows the real refusal). A writer that keeps its journal past leaving the repointing and
    records into it is refused the same way by the stand-in, for a link, a node and a corrected node
    alike, and nothing it tried is kept. Red with the stand-in's refusal removed: each pair was
    accepted into a record its settle had already passed."""
    journal = Journal()
    async with journal.repointing(_Graph()) as record:
        await record.cloned("edge-1", "edge-2", "ASSOCIATE_OF")
    with pytest.raises(RepointRecordGone):
        await record.cloned("edge-3", "edge-4", "ASSOCIATE_OF")
    with pytest.raises(RepointRecordGone):
        await record.record_node("alert-node-1", "alert-node-2")
    with pytest.raises(RepointRecordGone):
        await record.superseded("node-1", "node-2")
    assert journal.links == [("edge-1", "edge-2", "ASSOCIATE_OF")]
    assert journal.referents == []


async def test_a_routes_correction_records_the_corrected_node_and_its_revision() -> None:
    """ADR-109 Amendment 12. `supersede_journalled(..., superseding=)` (the confirm and retract
    routes) records the node it corrects and the revision its write returns, before the commit, so
    an alert naming the node among its referents follows it. Red with `superseding` not recorded:
    the journal held no referent and the alert would keep naming a node no read returns."""
    journal, graph = Journal(), _Graph()
    order: list[str] = []

    async def write(tx: str, recorder: Any) -> str:
        await recorder("edge-1", "edge-2", "ASSOCIATE_OF")
        order.append("written")
        return "node-2"

    new = await supersede_journalled(journal, graph, write, superseding="node-1")  # type: ignore[arg-type]
    assert new == "node-2"
    assert journal.referents == [("node-1", "node-2")]
    assert journal.links == [("edge-1", "edge-2", "ASSOCIATE_OF")]
    assert graph.committed == ["tx-1"]


async def test_a_correction_the_graph_refuses_before_its_commit_records_nothing() -> None:
    """The record's other side: a write refused before its commit says `never_committed`, so the
    corrected node it named is not kept (nothing it recorded can land), and the transaction is
    rolled back, never committed. Red with the write's refusal not said: the stand-in kept a
    referent for a correction that never happened."""
    journal, graph = Journal(), _Graph()

    async def write(tx: str, recorder: Any) -> str:
        await recorder.superseded("node-1", "node-2")
        raise RuntimeError("the graph refused the correction")

    with pytest.raises(RuntimeError, match="refused"):
        await supersede_journalled(journal, graph, write)  # type: ignore[arg-type]
    assert journal.referents == [] and graph.rolled_back == ["tx-1"] and graph.committed == []
