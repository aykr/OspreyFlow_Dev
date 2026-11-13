"""Closing an alert that cites two screening lists (`06_DECISIONS.md` ADR-146 Amendment 7, the owner's
ruling of 12 November 2026, about 15:30; rules 3 and 5).

A close decides only the citations its closer may read. The alert stays open on a citation hidden
from them, shown only to a reader cleared for it, so list B's team still decides B's match; to the
closer cleared for A alone it reads as closed, so nothing tells them B was matched. This holds for
every disposition, a true match or not, and for a proposed close and its approval (ADR-133
decision 7): an approver decides only the proposals they may read, whatever the proposer could.

Three readers of one case: `A_ONLY` (list B's party and match hidden, as the adapters answer them),
`B_ONLY` (list A's hidden) and `BOTH`. The store is one fake for the queue and the triage
(`Desk`): its `list_queue` lets an alert with citations through the status and assignee filters,
as the real query does (`AlertStore.list_queue`), and its writes are the real store's own decision
(`decide_citations`, `TriageStore.triage_citations`). Each read path a reader reaches is asked here
by name: the queue and its filters, Home's counts, the Reports figures, the alert's address and its
explanation, and the trends' rows (`_row_to_facts`, through the DuckDB adapter). Each was shown red
by a plant at its real call site (`process/lanes/rules/lists/AM7_RED_RECORD.txt`).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import duckdb
import pytest
from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table
from services.api import alert_queue
from services.api.alerts import AlertTriageConflict, QueueRow, _row_to_facts

from ontology.handling import load_uk_le_scheme
from schemas.analytics import AlertTrendRequest, TrendInterval
from schemas.domain import Alert, Handling, Interval, Principal
from tests.services.api.test_alert_citations_per_list import A_WORDS, B_WORDS, BOTH
from tests.services.api.test_alert_evidence_withheld import (
    CASE,
    NOW,
    Analytics,
    Graph,
    Recorder,
    TriageStore,
)

SCHEME = load_uk_le_scheme()
A_ONLY = Principal(id="a-reader", clearance="OFFICIAL", org_unit="unit-1")
B_ONLY = Principal(id="b-reader", clearance="OFFICIAL", org_unit="unit-1")
BOTH_READER = Principal(id="both-reader", clearance="OFFICIAL", org_unit="unit-1")
SECOND = Principal(id="second-person", clearance="OFFICIAL", org_unit="unit-1")
HIDDEN = {A_ONLY.id: {"l-b", "s-b"}, B_ONLY.id: {"l-a", "s-a"}, BOTH_READER.id: set(),
          SECOND.id: {"l-b", "s-b"}}  # fmt: skip


class Readers(Graph):
    """The adapters' answer, per reader: what each may not read is left out (`get_nodes`,
    `get_edges`), as `Graph` answers one reader."""

    def __init__(self, hidden: dict[str, set[str]]) -> None:
        super().__init__(Recorder())
        self.by_reader = hidden

    async def get_nodes(self, node_ids: Any, principal: Principal) -> Any:
        self.hidden = self.by_reader.get(principal.id, set())
        return await super().get_nodes(node_ids, principal)

    async def get_edges(self, edge_ids: Any, principal: Principal) -> Any:
        self.hidden = self.by_reader.get(principal.id, set())
        return await super().get_edges(edge_ids, principal)


class Desk(TriageStore):
    """The queue and its triage over one set of alerts. `list_queue` applies the status and
    *Mine*/*Unassigned* filters to an alert without citations and lets one with citations through,
    as the real query does; `get_queue_alert` answers each alert at `severity` (a high one's close
    needs a second person, ADR-133 decision 7)."""

    def __init__(self, alerts: list[Alert], *, severity: str = "medium") -> None:
        super().__init__(alerts)
        self.severity = severity

    def _row(self, a: Alert) -> QueueRow:
        return QueueRow(a, "typology", self.severity, "case")

    async def list_queue(self, investigation_id: str, reader: Principal, *,
                         statuses: Any = None, show: Any = None, **_: Any) -> list[QueueRow]:  # fmt: skip
        rows = []
        for a in self.alerts:
            if not a.citations:
                if statuses is not None and a.status not in statuses:
                    continue
                if show == "mine" and a.assignee != reader.id:
                    continue
                if show == "unassigned" and a.assignee is not None:
                    continue
            rows.append(self._row(a))
        return rows

    async def get_queue_alert(self, alert_id: str, investigation_id: str, reader: Principal) -> QueueRow:
        row = await super().get_queue_alert(alert_id, investigation_id, reader)
        return self._row(row.alert)


def _world(severity: str = "medium") -> tuple[Desk, Readers, Analytics]:
    return Desk([BOTH], severity=severity), Readers(HIDDEN), Analytics(Recorder())


async def _seen(desk: Desk, graph: Readers, analytics: Analytics, reader: Principal, **filters: Any) -> list[Alert]:
    queued = await alert_queue.monitoring_queue(desk, graph, analytics, CASE, reader, **filters)  # type: ignore[arg-type]
    return [q.alert for q in queued]


async def _one(desk: Desk, graph: Readers, analytics: Analytics, reader: Principal) -> Alert:
    (alert,) = await _seen(desk, graph, analytics, reader)
    return alert


async def _close(desk: Desk, graph: Readers, analytics: Analytics, reader: Principal, disposition: str,
                 reason: str) -> Alert:  # fmt: skip
    return await alert_queue.dispose(desk, graph, analytics, CASE, BOTH.id, reader,  # type: ignore[arg-type]
                                     disposition=disposition, reason=reason)  # fmt: skip


def _nothing_of(served: Alert, *, words: str, person: str, reason: str | None = None) -> None:
    text = served.model_dump_json()
    assert words not in text and person not in text, text
    if reason is not None:
        assert reason not in text, text


# --- the ruling ---------------------------------------------------------------------------------


async def test_an_a_only_false_positive_leaves_b_open_to_a_b_reader_and_closed_to_the_a_reader() -> None:
    """Red before the ruling: the close decided the whole alert, B's match with it, unseen."""
    desk, graph, analytics = _world()
    returned = await _close(desk, graph, analytics, A_ONLY, "false_positive", "Not the listed Petrova")
    assert (returned.status, returned.disposition) == ("closed", "false_positive")
    _nothing_of(returned, words=B_WORDS, person=B_ONLY.id)

    a_view = await _one(desk, graph, analytics, A_ONLY)
    assert (a_view.status, a_view.disposition, a_view.decided_by) == ("closed", "false_positive", A_ONLY.id)

    b_view = await _one(desk, graph, analytics, B_ONLY)
    assert (b_view.status, b_view.assignee, b_view.disposition, b_view.decided_by) == ("open", None, None, None)
    assert [(c.words, c.status) for c in b_view.citations] == [(B_WORDS, "open")]
    _nothing_of(b_view, words=A_WORDS, person=A_ONLY.id, reason="Not the listed Petrova")

    both = await _one(desk, graph, analytics, BOTH_READER)
    assert both.status == "open" and [c.status for c in both.citations] == ["closed", "open"]


async def test_a_b_cleared_close_then_finishes_it() -> None:
    """B's reader then decides B: the alert is closed, each reader shown their own decision."""
    desk, graph, analytics = _world()
    await _close(desk, graph, analytics, A_ONLY, "false_positive", "Not the listed Petrova")
    await _close(desk, graph, analytics, B_ONLY, "referred", "Sent to the sanctions team")
    (stored,) = desk.alerts
    assert stored.status == "closed" and [c.status for c in stored.citations] == ["closed", "closed"]
    a_view = await _one(desk, graph, analytics, A_ONLY)
    assert (a_view.status, a_view.disposition, a_view.decided_by) == ("closed", "false_positive", A_ONLY.id)
    _nothing_of(a_view, words=B_WORDS, person=B_ONLY.id, reason="Sent to the sanctions team")
    b_view = await _one(desk, graph, analytics, B_ONLY)
    assert (b_view.status, b_view.disposition, b_view.decided_by) == ("closed", "referred", B_ONLY.id)
    _nothing_of(b_view, words=A_WORDS, person=A_ONLY.id, reason="Not the listed Petrova")


async def test_a_reader_shown_the_alert_closed_takes_no_further_triage_on_it() -> None:
    """Claim, assign and close again, by the reader for whom it is closed: refused, nothing written,
    as for any closed alert, so none of them says B is still open."""
    desk, graph, analytics = _world()
    await _close(desk, graph, analytics, A_ONLY, "false_positive", "Not her")
    writes = list(desk.writes)
    for act in (
        alert_queue.claim(desk, graph, analytics, CASE, BOTH.id, A_ONLY),  # type: ignore[arg-type]
        alert_queue.assign(desk, graph, analytics, CASE, BOTH.id, A_ONLY, assignee=A_ONLY.id,  # type: ignore[arg-type]
                           allowed={A_ONLY.id}),  # fmt: skip
        _close(desk, graph, analytics, A_ONLY, "duplicate", "Again"),
    ):
        with pytest.raises(AlertTriageConflict):
            await act
    assert desk.writes == writes
    await alert_queue.claim(desk, graph, analytics, CASE, BOTH.id, B_ONLY)  # type: ignore[arg-type]
    assert desk.writes == [*writes, f"triage {BOTH.id}"], "B's reader, shown it open, claims it"


# --- a proposed close and its approval (ADR-133 decision 7, the review's item 10) ---------------


async def test_an_approver_cleared_for_one_list_approves_only_that_lists_proposal() -> None:
    """Point 6 with an approver whose clearance differs from the proposer's: the proposer, cleared
    for both, proposes closing both; a second person cleared for A alone approves, and decides A
    alone. B's proposal waits for a second person cleared for B. Red with the approval deciding the
    alert: B was closed by a person who never saw it."""
    desk, graph, analytics = _world("high")
    proposed = await _close(desk, graph, analytics, BOTH_READER, "false_positive", "Both checked")
    assert proposed.status == "closing" and [c.status for c in proposed.citations] == ["closing", "closing"]
    approved = await alert_queue.approve_close(desk, graph, analytics, CASE, BOTH.id, SECOND)  # type: ignore[arg-type]
    assert approved.status == "closed"
    _nothing_of(approved, words=B_WORDS, person=B_ONLY.id)
    (stored,) = desk.alerts
    assert [c.status for c in stored.citations] == ["closed", "closing"]
    assert (await _one(desk, graph, analytics, B_ONLY)).status == "closing"
    finisher = B_ONLY.model_copy(update={"id": "b-second"})
    graph.by_reader[finisher.id] = HIDDEN[B_ONLY.id]
    await alert_queue.approve_close(desk, graph, analytics, CASE, BOTH.id, finisher)  # type: ignore[arg-type]
    assert desk.alerts[0].status == "closed"


async def test_a_proposer_cleared_for_one_list_proposes_only_that_one() -> None:
    """The proposer reads A alone and proposes; a second person cleared for both approves what was
    proposed, A, and B stays open for B's team. Red with the approval deciding every citation the
    approver could read: B closed on a proposal that never named it."""
    desk, graph, analytics = _world("high")
    await _close(desk, graph, analytics, A_ONLY, "false_positive", "Not her")
    second = BOTH_READER.model_copy(update={"id": "both-second"})
    graph.by_reader[second.id] = set()
    await alert_queue.approve_close(desk, graph, analytics, CASE, BOTH.id, second)  # type: ignore[arg-type]
    (stored,) = desk.alerts
    assert [c.status for c in stored.citations] == ["closed", "open"] and stored.status == "open"
    assert (await _one(desk, graph, analytics, B_ONLY)).status == "open"
    assert (await _one(desk, graph, analytics, A_ONLY)).status == "closed"


async def test_a_proposal_is_sent_back_on_the_citations_its_member_was_shown() -> None:
    desk, graph, analytics = _world("high")
    await _close(desk, graph, analytics, BOTH_READER, "false_positive", "Both checked")
    back = await alert_queue.send_back(desk, graph, analytics, CASE, BOTH.id, SECOND)  # type: ignore[arg-type]
    assert back.status == "claimed"
    (stored,) = desk.alerts
    assert [c.status for c in stored.citations] == ["open", "closing"]


async def test_no_one_approves_a_proposal_of_their_own_beside_anothers() -> None:
    """ADR-133 decision 7 (the lane review of the second pass, defect 3): B is proposed by the
    reader cleared for both, then A by the reader cleared for A alone. The first approves: A is
    closed, B, their own, still waits; asked again, with only their own proposal left, they are
    refused. Red with the approval taking every proposal the approver was shown: B approved by
    its own proposer."""
    proposed_b = BOTH.model_copy(update={"status": "claimed", "assignee": BOTH_READER.id, "citations": [
        BOTH.citations[0],
        BOTH.citations[1].model_copy(update={"status": "closing", "disposition": "false_positive",
                                             "close_proposed_by": BOTH_READER.id}),
    ]})  # fmt: skip
    desk, graph, analytics = Desk([proposed_b], severity="high"), Readers(HIDDEN), Analytics(Recorder())
    await _close(desk, graph, analytics, A_ONLY, "false_positive", "Not her")
    await alert_queue.approve_close(desk, graph, analytics, CASE, BOTH.id, BOTH_READER)  # type: ignore[arg-type]
    (stored,) = desk.alerts
    assert [(c.status, c.decided_by) for c in stored.citations] == [("closed", BOTH_READER.id), ("closing", None)]
    with pytest.raises(alert_queue.CloseRefused):
        await alert_queue.approve_close(desk, graph, analytics, CASE, BOTH.id, BOTH_READER)  # type: ignore[arg-type]


async def test_a_proposal_on_one_list_leaves_the_other_list_to_its_team() -> None:
    """The ruling: A's reader proposes closing A; the reader cleared for both, shown the alert
    `closing`, still proposes B, which is open. Red with the close refused for an alert shown
    `closing`: B could not be decided until A's proposal was."""
    desk, graph, analytics = _world("high")
    await _close(desk, graph, analytics, A_ONLY, "false_positive", "Not her")
    assert (await _one(desk, graph, analytics, BOTH_READER)).status == "closing"
    await _close(desk, graph, analytics, BOTH_READER, "true_positive", "The listed Petrova")
    (stored,) = desk.alerts
    assert [(c.status, c.close_proposed_by) for c in stored.citations] == [
        ("closing", A_ONLY.id), ("closing", BOTH_READER.id)]  # fmt: skip


async def test_a_close_on_one_list_leaves_a_claim_on_the_other_as_it_was() -> None:
    """The lane review of the second pass, defect 5: B's reader has claimed the alert; A's reader
    closes A. B's reader's claim stands, so nothing they are shown changes. Red with a partial
    close handing the alert back unassigned: their claim vanished, the trace of a decision on a
    list they may not read."""
    desk, graph, analytics = _world()
    claimed = BOTH.model_copy(update={"status": "claimed", "assignee": B_ONLY.id})
    desk.alerts[0] = claimed
    before = await _one(desk, graph, analytics, B_ONLY)
    await _close(desk, graph, analytics, A_ONLY, "false_positive", "Not her")
    after = await _one(desk, graph, analytics, B_ONLY)
    assert (after.status, after.assignee) == (before.status, before.assignee) == ("claimed", B_ONLY.id)
    assert (await _one(desk, graph, analytics, A_ONLY)).status == "closed"


# --- each read path, as each reader is shown the alert (the review's item 10) --------------------


async def test_the_queues_filters_follow_what_each_reader_is_shown() -> None:
    """Red with the store's status and assignee filters over the stored row: the alert, open as
    stored, was listed under *Open* to the reader shown it closed (and its count with it)."""
    desk, graph, analytics = _world()
    await _close(desk, graph, analytics, A_ONLY, "false_positive", "Not her")
    working = {"statuses": ["open", "claimed", "closing"]}
    assert await _seen(desk, graph, analytics, A_ONLY, **working) == []
    assert [a.status for a in await _seen(desk, graph, analytics, A_ONLY, statuses=["closed"])] == ["closed"]
    assert await _seen(desk, graph, analytics, A_ONLY, show="unassigned") == []
    assert [a.status for a in await _seen(desk, graph, analytics, B_ONLY, **working)] == ["open"]
    assert [a.status for a in await _seen(desk, graph, analytics, B_ONLY, show="unassigned")] == ["open"]


class _Audit:
    async def record(self, **_: Any) -> None:
        return None


async def test_homes_counts_follow_what_each_reader_is_shown() -> None:
    """ADR-146 Amendment 2 point 3's counts, by the route's own function."""
    from services.api.app import read_alert_queue_counts

    desk, graph, analytics = _world()
    await _close(desk, graph, analytics, A_ONLY, "false_positive", "Not her")
    counts = {}
    for reader in (A_ONLY, B_ONLY):
        counts[reader.id] = await read_alert_queue_counts(
            investigation=SimpleNamespace(id=CASE), principal=reader, graph=graph,  # type: ignore[arg-type]
            alerts_store=desk, audit=_Audit(), analytics=analytics,  # type: ignore[arg-type]
        )  # fmt: skip
    assert (counts[A_ONLY.id].open, counts[A_ONLY.id].claimed, counts[A_ONLY.id].closing) == (0, 0, 0)
    assert (counts[B_ONLY.id].open, counts[B_ONLY.id].claimed, counts[B_ONLY.id].closing) == (1, 0, 0)


async def test_the_reports_figures_follow_what_each_reader_is_shown() -> None:
    """The Reports page's alert figures (`reports.alert_report`): closed false positive for the
    reader cleared for A, open for the one cleared for B, and never a figure for B's decision to A."""
    from services.api.reports import alert_report

    desk, graph, analytics = _world()
    await _close(desk, graph, analytics, A_ONLY, "false_positive", "Not her")
    seen = {}
    for reader in (A_ONLY, B_ONLY):
        figures = await alert_report(desk, graph, analytics, CASE, reader, today=NOW.date())  # type: ignore[arg-type]
        (row,) = figures.outcomes
        seen[reader.id] = (row.open, row.false_positive)
    assert seen == {A_ONLY.id: (0, 1), B_ONLY.id: (1, 0)}


async def test_the_alerts_address_follows_what_each_reader_is_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    """`/alerts/<id>` (ADR-146 decision 6), by the route's own read (`_alert_at_address`)."""
    from services.api import app as app_module

    async def as_is(principal: Principal, *_: Any, **__: Any) -> Principal:
        return principal

    monkeypatch.setattr(app_module, "scope_to_case", as_is)
    desk, graph, analytics = _world()
    await _close(desk, graph, analytics, A_ONLY, "false_positive", "Not her")

    class Cases:
        async def get_authorized(self, *_: Any, **__: Any) -> None:
            return None

    class Names:
        async def display_names(self, ids: Any) -> dict[str, str]:
            return {}

    async def case_of(alert_id: str) -> str:
        return CASE

    desk.case_of = case_of  # type: ignore[method-assign]
    shown = {}
    for reader in (A_ONLY, B_ONLY):
        at = await app_module._alert_at_address(BOTH.id, reader, Cases(), graph, analytics, desk,  # type: ignore[arg-type]
                                                Names(), _Audit(), None)  # type: ignore[arg-type]  # fmt: skip
        shown[reader.id] = at.explanation.alert
    assert shown[A_ONLY.id].status == "closed" and shown[B_ONLY.id].status == "open"
    _nothing_of(shown[B_ONLY.id], words=A_WORDS, person=A_ONLY.id, reason="Not her")


# --- the trends (the review's item 6) ----------------------------------------------------------


def _h(classification: str) -> dict[str, str]:
    return Handling(classification=classification, handling_code="P", owning_unit="unit-1",
                    originator="unit-1").model_dump()  # fmt: skip


def _stored_row(alert: Alert) -> dict[str, Any]:
    """The alert as `publish_facts` selects it (`_FACT_COLUMNS`): list A's match OFFICIAL, list
    B's SECRET, the rest OFFICIAL."""
    return {
        "id": alert.id, "rule_id": alert.rule_id, "owner_id": alert.owner_id,
        "investigation_id": alert.investigation_id, "created_at": alert.created_at,
        "dataset_id": None, "typology": alert.typology, "status": alert.status,
        "disposition": alert.disposition, "team": None, "routed_team": None,
        "handlings": json.dumps([_h("OFFICIAL"), _h("SECRET")]),
        "citations": json.dumps([c.model_dump(mode="json") for c in alert.citations]),
        "cited_handlings": json.dumps({"core": [_h("OFFICIAL")],
                                       "citations": [[_h("OFFICIAL")], [_h("SECRET")]]}),
        "assignee": alert.assignee, "kind": "typology", "severity_read": "medium", "audience": "case",
    }  # fmt: skip


async def _trend(facts: list[Any], reader: Principal) -> tuple[float, list[str | None], list[str]]:
    con = duckdb.connect(":memory:")
    create_events_table(con)
    adapter = AnalyticsDuckDBAdapter(con, SCHEME)
    await adapter.load_alert_facts(facts)
    result = await adapter.alert_trend(
        AlertTrendRequest(investigation_scope=CASE, interval=TrendInterval.MONTH, group_by="outcome",
                          window=Interval(valid_from=datetime(2026, 1, 1, tzinfo=UTC))),
        reader,
    )  # fmt: skip
    return result.total, result.series, result.classifications


async def test_the_trends_count_a_cited_alert_once_for_each_reader_as_the_queue_shows_it() -> None:
    """Item 6: the OFFICIAL reader (cleared for list A) counts it once, closed as a false positive,
    and is given no SECRET marking; the SECRET reader (cleared for both) counts it once, open. Red
    with one row of every handling: the OFFICIAL reader, shown the alert in the queue, counted none
    (the queue less the trend said a hidden list matched)."""
    desk, graph, analytics = _world()
    await _close(desk, graph, analytics, A_ONLY, "false_positive", "Not her")
    facts = _row_to_facts(_stored_row(desk.alerts[0]))  # type: ignore[arg-type]
    official = Principal(id="o", clearance="OFFICIAL", org_unit="unit-1")
    secret = Principal(id="s", clearance="SECRET", org_unit="unit-1")
    assert await _trend(facts, official) == (1.0, ["false_positive"], ["OFFICIAL"])
    total, series, classifications = await _trend(facts, secret)
    assert (total, series) == (1.0, ["open"]) and "SECRET" in classifications
