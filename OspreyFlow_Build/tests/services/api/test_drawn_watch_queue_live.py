"""Who the one queue gives a drawn watch's alert to, in the query (ADR-143 Amendment 2 decision 8;
ADR-146 decision 1; rules 3 and 4; L3.6). Real Postgres (a leased stack); the graph answers as the
adapter does (`test_monitoring_queue._Graph`).

A drawn watch's alert is an ordinary watch alert, its owner's — and, since the drawn item it cites
lives in its case's layer, its owner's **in the watch's case alone** (`alerts.queue_scope`):

- the owner reads it in the watch's case, with its kind, severity and audience read in the query —
  `test_a_drawn_watch_alert_reaches_its_owner_in_its_case`;
- another member of the case, of the owner's unit or not, and anyone outside it, read nothing —
  `test_no_one_but_its_owner_reads_a_drawn_watch_alert`;
- the owner, opening another case reading the same dataset, reads nothing (red without the
  watch clause's exclusion: a hotlist's or monitor's alert reaches its owner in every case) —
  `test_its_owner_does_not_read_it_through_another_case`;
- the owner who may not see the drawn item reads nothing either (the queue's read of the evidence,
  after the query) — `test_its_owner_reads_nothing_once_the_drawn_item_is_hidden_from_them`.

The plants at `queue_scope` are `gates/L3.6-live-plants.py`.
"""

from __future__ import annotations

from typing import Any

import pytest
from services.api import alert_queue
from services.api.alerts import AlertStore, default_severity
from services.api.drawn_watches import drawn_watch_rule

from conduit_common.identity import new_id
from schemas.domain import Alert, Principal
from tests.services.api.no_transactions import NO_TRANSACTIONS
from tests.services.api.test_monitoring_queue import _alert, _fresh_units, _Graph, _person, stores  # noqa: F401

NAMES = {"d-1": "Tall (drawn)", "p-1": "TALL, Jordan", "n-3": "OKAFOR, Callum"}


@pytest.fixture
def alerts(stores: Any) -> AlertStore:  # noqa: F811 - the live stores of the queue's own tests
    return stores[1]  # type: ignore[no-any-return]


def _graph(hidden: set[str] | None = None) -> Any:
    return _Graph(NAMES, hidden)


def _drawn_watch_alert(owner: Principal, case: str) -> Alert:
    return _alert(
        drawn_watch_rule(new_id()), owner, investigation_id=case, referent_node_ids=["d-1", "p-1"],
        words="A load met a drawn item: p-1 looks like d-1 (the same pnc_id).",
    )  # fmt: skip


async def _ids(
    alerts: AlertStore, case: str, reader: Principal, hidden: set[str] | None = None
) -> list[str]:
    rows = await alert_queue.monitoring_queue(
        alerts,
        _graph(hidden),
        NO_TRANSACTIONS,
        case,
        reader,
    )
    return [row.alert.id for row in rows]


async def test_a_drawn_watch_alert_reaches_its_owner_in_its_case(alerts: AlertStore) -> None:
    owner, case = _person(), f"case-{new_id()}"
    alert = _drawn_watch_alert(owner, case)
    await alerts.save(alert)
    rows = await alert_queue.monitoring_queue(
        alerts,
        _graph(),
        NO_TRANSACTIONS,
        case,
        owner,
    )
    assert [r.alert.id for r in rows] == [alert.id], "its owner is not given it in its case"
    row = rows[0]
    assert row.alert.id == alert.id
    assert (row.kind, row.severity, row.audience) == ("drawn_watch", "medium", "owner")
    assert default_severity("drawn_watch", None) == "medium"
    assert "TALL, Jordan" in row.summary and "p-1" not in row.summary
    # The kind filter is the query's.
    assert await _ids_of_kind(alerts, case, owner, ["drawn_watch"]) == [alert.id]
    assert await _ids_of_kind(alerts, case, owner, ["monitor"]) == []


async def _ids_of_kind(
    alerts: AlertStore, case: str, reader: Principal, kinds: list[str]
) -> list[str]:
    rows = await alert_queue.monitoring_queue(
        alerts,
        _graph(),
        NO_TRANSACTIONS,
        case,
        reader,
        kinds=kinds,
    )
    return [row.alert.id for row in rows]


async def test_no_one_but_its_owner_reads_a_drawn_watch_alert(alerts: AlertStore) -> None:
    """A member of the case of the owner's own unit (a monitor's alert would reach them, shared
    with the unit), one of another unit, and one outside the case: none reads it, in the case or
    out of it (rule 4)."""
    owner, case = _person(), f"case-{new_id()}"
    alert = _drawn_watch_alert(owner, case)
    await alerts.save(alert.model_copy(update={"team": owner.org_unit}))
    same_unit, other_unit = _person(), _person("unit-b")
    for reader in (same_unit, other_unit):
        assert alert.id not in await _ids(alerts, case, reader)
        assert alert.id not in await _ids(alerts, f"case-{new_id()}", reader)
    assert await _ids(alerts, case, owner) == [alert.id]


async def test_its_owner_does_not_read_it_through_another_case(alerts: AlertStore) -> None:
    """Another case of the owner's, reading the same dataset (`ds-1`): a monitor's alert reaches
    its owner there; a drawn watch's does not."""
    owner, case, other = _person(), f"case-{new_id()}", f"case-{new_id()}"
    drawn = _drawn_watch_alert(owner, case)
    monitor = _alert(f"monitor:{new_id()}", owner, investigation_id=case, referent_node_ids=["n-3"])
    await alerts.save(drawn)
    await alerts.save(monitor)
    assert await _ids(alerts, other, owner) == [monitor.id]
    assert sorted(await _ids(alerts, case, owner)) == sorted([drawn.id, monitor.id])


async def test_its_owner_reads_nothing_once_the_drawn_item_is_hidden_from_them(
    alerts: AlertStore,
) -> None:
    """The query admits the row; the queue's read of its evidence as the owner leaves it out whole
    once the drawn item is no longer theirs to see (re-marked above them, say)."""
    owner, case = _person(), f"case-{new_id()}"
    alert = _drawn_watch_alert(owner, case)
    await alerts.save(alert)
    assert await _ids(alerts, case, owner, {"d-1"}) == []
    assert await _ids(alerts, case, owner, {"p-1"}) == []
