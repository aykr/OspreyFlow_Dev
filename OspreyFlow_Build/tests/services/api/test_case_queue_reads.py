"""Rule 3 review of the case queue (`spec/06_DECISIONS.md` ADR-134 decision 4): `alert_queue.queue`,
the typology alerts the Reports figures and neighbourhood risk count, must say nothing of an alert
the reader may not see — not by its count, not by the order of the rest, and not by the work done.

Found in the review (1 November 2026): `queue` read each alert's nodes one at a time and stopped at
the first hidden one, so the number of graph reads — the time the Reports view took — grew with
every alert in the case the reader could not see. The one queue (`monitoring_queue`) already read
them in one batch (`test_monitoring_queue.py::test_a_hidden_alert_reveals_nothing_through_count_
order_or_reads`); `queue` now goes through it. Real Postgres; the graph is `test_monitoring_queue`'s
fake, which leaves a hidden id out of its answer, as the adapter does, and counts its reads.
"""

from __future__ import annotations

from typing import Any

from services.api import alert_queue

from conduit_common.identity import new_id
from tests.services.api.test_monitoring_queue import (  # noqa: F401 — `stores`, `_fresh_units` are fixtures
    NOW,
    _alert,
    _fresh_units,
    _Graph,
    _person,
    stores,
)


async def test_the_case_queue_reveals_no_hidden_alert_through_count_order_or_reads(stores: Any) -> None:
    _, alerts = stores
    deployer, member = _person(), _person()
    case_with, case_without = new_id(), new_id()
    names = {"n-a": "Alpha Ltd", "n-b": "Bravo Ltd", "n-secret": "Hidden person"}
    for case in (case_with, case_without):
        for minutes, node in ((3, "n-a"), (2, "n-b")):
            await alerts.save(_alert("typology:r1", deployer, investigation_id=case, typology="structuring",
                                     referent_node_ids=[node], words=f"Seen {node}",
                                     created_at=NOW.replace(minute=minutes)))  # fmt: skip
    for _ in range(3):
        await alerts.save(_alert("typology:r2", deployer, investigation_id=case_with, typology="structuring",
                                 referent_node_ids=["n-a", "n-secret"], words="Hidden",
                                 created_at=NOW.replace(minute=1)))  # fmt: skip
    with_graph, without_graph = _Graph(names, hidden={"n-secret"}), _Graph(names)
    shown_with = await alert_queue.queue(alerts, with_graph, case_with, member)
    shown_without = await alert_queue.queue(alerts, without_graph, case_without, member)
    assert [q.summary for q in shown_with] == [q.summary for q in shown_without] == ["Seen Alpha Ltd", "Seen Bravo Ltd"]
    assert with_graph.reads == without_graph.reads, (
        "the work done must not grow with the alerts the reader may not see")


async def test_the_case_queue_holds_typology_alerts_only_and_filters_by_status(stores: Any) -> None:
    hotlists, alerts = stores
    deployer = _person()
    case = new_id()
    names = {"n-a": "Alpha Ltd"}
    opened = _alert("typology:r1", deployer, investigation_id=case, typology="structuring", referent_node_ids=["n-a"])
    closed = _alert("typology:r1", deployer, investigation_id=case, typology="structuring", referent_node_ids=["n-a"],
                    status="closed", disposition="false_positive")  # fmt: skip
    mine = _alert("monitor:m1", deployer, referent_node_ids=["n-a"])
    for alert in (opened, closed, mine):
        await alerts.save(alert)
    everything = await alert_queue.queue(alerts, _Graph(names), case, deployer)
    assert {q.alert.id for q in everything} == {opened.id, closed.id}, "the Reports figures count typology alerts"
    only_open = await alert_queue.queue(alerts, _Graph(names), case, deployer, statuses=["open"])
    assert [q.alert.id for q in only_open] == [opened.id]
