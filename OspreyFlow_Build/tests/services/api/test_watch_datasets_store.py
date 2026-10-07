"""Watches belong to their dataset (`06_DECISIONS.md` ADR-099 Amendment 3, part c), in the
database itself: a hotlist, a monitor and an alert made in a case of one dataset are listed and
found only in a case reading it, by their owner, with one answer for another dataset's and a
missing one. One made before the amendment names no dataset and stays its owner's everywhere until
`stamp_datasets` places it. Real Postgres (`make dev-up`, or a throwaway one)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from services.api.alerts import AlertNotFoundError, AlertStore
from services.api.config import PostgresConfig
from services.api.hotlists import HotlistNotFoundError, HotlistStore
from services.api.monitors import MonitorNotFoundError, MonitorStore

from conduit_common.identity import new_id
from schemas.domain import Alert, AlertMode, Principal


def _owner() -> Principal:
    return Principal(id=f"analyst-{new_id()}", clearance="OFFICIAL", org_unit="unit-1")


def _in(principal: Principal, *datasets: str) -> Principal:
    return principal.model_copy(update={"datasets": list(datasets)})


@pytest.fixture
async def stores():
    dsn = PostgresConfig.from_env().dsn
    hotlists, monitors, alerts = (
        await HotlistStore.connect(dsn),
        await MonitorStore.connect(dsn),
        await AlertStore.connect(dsn),
    )
    yield hotlists, monitors, alerts
    for store in (hotlists, monitors, alerts):
        await store.close()


async def test_a_hotlist_is_its_datasets(stores) -> None:  # type: ignore[no-untyped-def]
    hotlists, _, _ = stores
    owner = _owner()
    made = await hotlists.create(
        _in(owner, "fixture-corp"), identifier="+441", review_date=date(2027, 1, 1)
    )
    assert made.dataset_id == "fixture-corp"
    assert [h.id for h in await hotlists.list_authorized(_in(owner, "fixture-corp"))] == [made.id]
    assert await hotlists.list_authorized(_in(owner, "enron")) == []
    with pytest.raises(HotlistNotFoundError):
        await hotlists.get_authorized(made.id, _in(owner, "enron"))
    assert (await hotlists.list_all_active())  # the evaluator still sees every one


async def test_a_monitor_is_its_datasets(stores) -> None:  # type: ignore[no-untyped-def]
    _, monitors, _ = stores
    owner = _owner()
    made = await monitors.create(_in(owner, "fixture-corp"), pattern_id=new_id())
    assert made.dataset_id == "fixture-corp"
    assert [m.id for m in await monitors.list_authorized(_in(owner, "fixture-corp"))] == [made.id]
    assert await monitors.list_authorized(_in(owner, "enron")) == []
    with pytest.raises(MonitorNotFoundError):
        await monitors.get_authorized(made.id, _in(owner, "enron"))


async def test_an_alert_is_its_rules_datasets(stores) -> None:  # type: ignore[no-untyped-def]
    _, _, alerts = stores
    owner = _owner()
    alert = Alert(
        id=new_id(),
        rule_id="hotlist:h1",
        owner_id=owner.id,
        mode=AlertMode.FULL,
        referent_node_ids=["n1"],
        investigation_id="case-f",
        created_at=datetime.now(UTC),
        dataset_id="fixture-corp",
    )
    await alerts.save(alert)
    assert [a.id for a in await alerts.list_authorized(_in(owner, "fixture-corp"))] == [alert.id]
    assert await alerts.list_authorized(_in(owner, "enron")) == []
    with pytest.raises(AlertNotFoundError):
        await alerts.get_authorized(alert.id, _in(owner, "enron"))


async def test_a_watch_made_before_the_amendment_stays_its_owners(stores) -> None:  # type: ignore[no-untyped-def]
    hotlists, _, _ = stores
    owner = _owner()
    older = await hotlists.create(owner, identifier="+442", review_date=date(2027, 1, 1))
    assert older.dataset_id is None
    assert [h.id for h in await hotlists.list_authorized(_in(owner, "enron"))] == [older.id]
