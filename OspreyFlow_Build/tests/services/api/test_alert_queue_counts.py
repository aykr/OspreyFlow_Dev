"""The queue's shared read, as counts to whom Rules and Monitoring is not offered (`06_DECISIONS.md`
ADR-146 Amendment 2 point 3, the orchestrator's ruling (a) on its independent review's item 4).

`GET …/alert-queue` is read outside the place (Home, the switcher's count), so it carries no place
gate. Its rows, each alert's title, words and id, go only to a reader the place is offered to and to
the Reports Viewer, whose Home lists the alerts on the cases they can read (ADR-145 Amendment 4
decision 10). Anyone else holding the queue's read, the Data Engineer, is refused the rows and reads
`GET …/alert-queue/counts`: how many are open, claimed and closing, counted as the queue counts them,
so an alert with hidden evidence is not counted (rule 3). The Reports Viewer still has no way into an
alert's detail: the detail and the address are the place's, and refuse them at its gate.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from schemas.domain import Alert, Principal
from services.api.investigations import AccessLevel
from tests.services.api.test_alert_address import (
    CASE,
    READER,
    AddressStore,
    Audit,
    Cases,
    Datasets,
    Names,
    ScopedAnalytics,
    ScopedGraph,
    _in,
)
from tests.services.api.test_alert_evidence_withheld import OVER_LINK, V1, Recorder
from tests.services.api.test_monitoring_routes import _no_lifespan


class CaseDatasets(Datasets):
    """`Datasets`, and no chosen dataset (so a case route's packs stand as stored)."""

    async def chosen_of_case(self, investigation_id: str) -> list[Any]:
        return []


def _get(who: Principal, paths: list[str], alerts: list[Alert], hidden: set[str] = frozenset()) -> list[tuple[int, Any]]:  # type: ignore[assignment]  # noqa: E501
    from services.api.app import (
        app,
        get_alerts_store,
        get_analytics,
        get_audit,
        get_datasets,
        get_graph,
        get_investigations,
        get_principal,
        get_principal_names,
    )

    recorder = Recorder()
    graph, analytics = ScopedGraph(recorder, set(hidden)), ScopedAnalytics(recorder, set(hidden))
    cases = Cases(CASE, {who.id: AccessLevel.VIEWER})
    previous = app.router.lifespan_context
    app.router.lifespan_context = _no_lifespan
    app.dependency_overrides.update({
        get_principal: lambda: who, get_investigations: lambda: cases, get_graph: lambda: graph,
        get_analytics: lambda: analytics, get_alerts_store: lambda: AddressStore(alerts),
        get_audit: Audit, get_principal_names: Names, get_datasets: CaseDatasets,
    })  # fmt: skip
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            out = []
            for path in paths:
                r = client.get(path)
                out.append((r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text))
            return out
    finally:
        app.dependency_overrides.clear()
        app.router.lifespan_context = previous


def _as(role: str) -> Principal:
    # In the case's dataset already, as `get_principal` gives a route naming the case.
    return READER.model_copy(update={"id": f"reader-{role}", "roles": [role], "datasets": ["ds-1"]})


ROWS = f"/v1/investigations/{CASE}/alert-queue"
COUNTS = f"/v1/investigations/{CASE}/alert-queue/counts"
SHOWN = [_in(V1), _in(OVER_LINK)]  # the second cites a link hidden from every reader below


def test_the_data_engineer_gets_counts_and_no_rows() -> None:
    """Red with the rows' check removed: the Data Engineer is answered every row, its title and
    words with it."""
    (rows, counts) = _get(_as("data_engineer"), [ROWS, COUNTS], SHOWN, {"e-secret"})
    assert rows[0] == 403 and rows[1]["detail"]["error"] == "queue_rows_not_offered", rows
    assert V1.id not in str(rows[1]) and "Finding" not in str(rows[1])
    # Counted as the queue counts: the alert over the hidden link is not counted (rule 3).
    assert counts == (200, {"open": 1, "claimed": 0, "closing": 0}), counts


def test_the_reports_viewer_keeps_their_list_and_has_no_detail() -> None:
    """ADR-145 Amendment 4 decision 10: the Reports Viewer's Home lists the alerts on their cases.
    The alert's detail and its address are the place's, and refuse them at its gate."""
    viewer = _as("reports_viewer")
    rows, detail, address = _get(
        viewer, [ROWS, f"/v1/investigations/{CASE}/alert-queue/{V1.id}", f"/v1/alerts/{V1.id}"], SHOWN,
        {"e-secret"},
    )
    assert rows[0] == 200 and [r["alert"]["id"] for r in rows[1]] == [V1.id], rows
    # The detail (since L2.10 the queue's alone: the inbox is gone) and the address are the place's.
    assert detail[0] == 403 and "place_required" in str(detail[1]), detail
    assert address[0] == 403 and "place_required" in str(address[1]), address


@pytest.mark.parametrize("role", ["analyst", "rule_author"])
def test_a_reader_offered_the_place_gets_the_rows(role: str) -> None:
    (rows,) = _get(_as(role), [ROWS], SHOWN, {"e-secret"})
    assert rows[0] == 200 and [r["alert"]["id"] for r in rows[1]] == [V1.id], rows


def test_counts_need_the_queue_s_read() -> None:
    (counts,) = _get(_as("osprey-admin"), [COUNTS], SHOWN)
    assert counts[0] == 403 and "read_alert_queue" in str(counts[1]), counts
