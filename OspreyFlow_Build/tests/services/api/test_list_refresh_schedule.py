"""A screening list's refresh schedule (`spec/06_DECISIONS.md` ADR-133 Amendment 3 item 4, built
with stage (d)'s scheduled trigger): set by whoever may load lists, run as that person resolved
afresh — never as the system — once per slot, and recorded with the list's refreshes in words.

The list store is the real one on Postgres (a throwaway one); the claim is `test_rule_schedule.
_Valkey`, which refuses a second `SET NX` as Valkey does. The refresh itself is a recorder here:
`test_screening_refresh.py` proves what a refresh does; this file proves who it runs as and when.
The routes run on `test_screening_list_routes.py`'s app (lifespan replaced, the real store).

What a mistake would do, and the case that catches it:
- a scheduled refresh run as the system, or twice for one slot —
  `test_a_scheduled_refresh_runs_once_as_the_person_who_set_it`;
- an owner who lost the right, refreshing anyway or silently —
  `test_an_owner_without_the_right_is_refused_in_words_and_nothing_is_read`;
- the schedule set by someone without the right — `test_setting_a_schedule_needs_the_right_to_load_lists`;
- a schedule shown with no words — `test_the_lists_screen_says_the_schedule_in_words`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from fastapi.testclient import TestClient
from services.api.config import PostgresConfig
from services.api.list_schedule import ListRefreshExecutor
from services.api.scheduler import next_slot
from services.api.screening import ListClearance, ScreeningListStore

from ontology.handling import load_uk_le_scheme

from conduit_common.identity import new_id
from schemas.domain import Principal
from schemas.monitoring import ListSchedule
from schemas.screening import ScreeningListUpdate, ScreeningSubscriptionInput
from tests.services.api.screening_cleanup import EVERYTHING, remove_screening_lists
from tests.services.api.test_rule_schedule import _Valkey
from tests.services.api.test_screening_list_routes import (  # noqa: F401 - `world` is a fixture
    ANALYST,
    ENGINEER,
    LIST,
    _World,
    world,
)

#: This file's lists' names begin so (`lists` removes them by it).
SCHEDULED = "Scheduled test "
SCHEME = load_uk_le_scheme()
OWNER = Principal(id="list-owner", clearance="OFFICIAL", org_unit="unit-a", roles=["osprey-admin"])


@pytest.fixture
async def lists() -> AsyncIterator[ScreeningListStore]:
    dsn = PostgresConfig.from_env().dsn
    store = await ScreeningListStore.connect(dsn)
    try:
        yield store
    finally:
        # Its own lists, and the refusals recorded for them, removed on a failure too (CARRIES row
        # 113, `screening_cleanup`); the `world` fixture removes the routes' own. First, so a store
        # that fails to close cannot leave them (the orchestrator's review, a note).
        try:
            await remove_screening_lists(dsn, prefixes=[SCHEDULED])
        finally:
            await store.close()


class _Refreshes:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def __call__(self, list_name: str, runner: Principal, slot: datetime) -> ScreeningListUpdate:
        self.calls.append((list_name, runner.id))
        return ScreeningListUpdate(id=new_id(), list_name=list_name, at=slot, outcome="unchanged",
                                   words="Version v1: no entry changed.", trigger="schedule")  # fmt: skip


async def _subscribed(lists: ScreeningListStore, schedule: ListSchedule) -> tuple[str, datetime]:
    name = f"{SCHEDULED}{new_id()}"
    await lists.subscribe(ScreeningSubscriptionInput(list_name=name, source="opensanctions",
                                                     location="lists/x.json"), OWNER.id, synthetic=False)  # fmt: skip
    status = await lists.set_schedule(name, schedule, OWNER.id)
    assert status.schedule == schedule and status.schedule_owner == OWNER.id
    return name, next_slot("0 5 * * *", "Europe/London", after=datetime.now(UTC)) + timedelta(minutes=1)


def _executor(lists: ScreeningListStore, refresh: _Refreshes, owner: Principal | None, names: set[str]) -> ListRefreshExecutor:
    async def resolve(owner_id: str) -> Principal:
        assert owner is not None and owner_id == owner.id
        return owner

    class _Only:  # the database is shared by the run: this test's lists alone
        async def scheduled_lists(self) -> list[object]:
            return [s for s in await lists.scheduled_lists() if s.list_name in names]

        def __getattr__(self, name: str) -> object:
            return getattr(lists, name)

    return ListRefreshExecutor(lists=_Only(), valkey=_Valkey(), resolve_owner=resolve, refresh=refresh,  # type: ignore[arg-type]
                               scheme=SCHEME)  # fmt: skip


async def test_a_scheduled_refresh_runs_once_as_the_person_who_set_it(lists: ScreeningListStore) -> None:
    name, at = await _subscribed(lists, ListSchedule(every="daily", hour=5))
    refresh = _Refreshes()
    executor = _executor(lists, refresh, OWNER, {name})
    await executor.tick(at)
    await executor.tick(at + timedelta(minutes=1))
    assert refresh.calls == [(name, OWNER.id)]
    await _executor(lists, refresh, OWNER, {name}).tick(at + timedelta(minutes=2))  # a second replica
    assert refresh.calls == [(name, OWNER.id)]


async def test_an_owner_without_the_right_is_refused_in_words_and_nothing_is_read(lists: ScreeningListStore) -> None:
    name, at = await _subscribed(lists, ListSchedule(every="daily", hour=5))
    refresh = _Refreshes()
    await _executor(lists, refresh, OWNER.model_copy(update={"roles": ["analyst"]}), {name}).tick(at)
    assert refresh.calls == []
    (update,) = [u for u in await lists.updates(org_unit=OWNER.org_unit, cleared=EVERYTHING, limit=50) if u.list_name == name]
    assert (update.outcome, update.trigger) == ("refused", "schedule")
    assert update.words == (f"The scheduled refresh was refused: the schedule's owner, {OWNER.id}, no "
                            "longer holds load_screening_lists. The list was left as it was.")  # fmt: skip


async def _marked(name: str, classification: str) -> None:
    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        await conn.execute(
            "INSERT INTO screening_list_markings (list_name, classification, handling_code) "
            "VALUES ($1, $2, 'P') ON CONFLICT (list_name) DO UPDATE SET classification = $2",
            name, classification,
        )  # fmt: skip
    finally:
        await conn.close()


async def test_an_owner_not_cleared_for_the_list_is_refused_in_words_and_nothing_is_read(
    lists: ScreeningListStore,
) -> None:
    """The orchestrator's verification of e911b90, item 2: the list is SECRET now (raised since the
    schedule was set, or the schedule given to someone), and its OFFICIAL owner's slot is refused,
    recorded in words with the list's refreshes, which only a reader cleared for it is shown. Red
    with the owner's clearance unread: the refresh ran as them."""
    name, at = await _subscribed(lists, ListSchedule(every="daily", hour=5))
    await _marked(name, "SECRET")
    refresh = _Refreshes()
    await _executor(lists, refresh, OWNER, {name}).tick(at)
    assert refresh.calls == []
    (update,) = [u for u in await lists.updates(org_unit=OWNER.org_unit, cleared=EVERYTHING, limit=50) if u.list_name == name]
    assert (update.outcome, update.words) == ("refused", (
        f"The scheduled refresh was refused: the schedule's owner, {OWNER.id}, is not cleared for "
        "the list. The list was left as it was."))  # fmt: skip
    official = ListClearance.of(OWNER, SCHEME)
    assert name not in {u.list_name for u in await lists.updates(org_unit=OWNER.org_unit, cleared=official, limit=50)}


async def test_an_owner_cleared_for_a_marked_list_refreshes_it(lists: ScreeningListStore) -> None:
    """The other way: the same SECRET list, its owner SECRET, refreshed as them."""
    name, at = await _subscribed(lists, ListSchedule(every="daily", hour=5))
    await _marked(name, "SECRET")
    refresh = _Refreshes()
    cleared = OWNER.model_copy(update={"clearance": "SECRET"})
    await _executor(lists, refresh, cleared, {name}).tick(at)
    assert refresh.calls == [(name, OWNER.id)]


async def test_a_stopped_schedule_runs_no_more(lists: ScreeningListStore) -> None:
    name, at = await _subscribed(lists, ListSchedule(every="daily", hour=5))
    status = await lists.set_schedule(name, None, OWNER.id)
    assert status.schedule is None and status.schedule_words is None
    refresh = _Refreshes()
    await _executor(lists, refresh, OWNER, {name}).tick(at)
    assert refresh.calls == []


def test_setting_a_schedule_needs_the_right_to_load_lists(world: tuple[_World, TestClient]) -> None:
    w, client = world
    client.post("/v1/admin/screening-lists", json=LIST)
    path = "/v1/admin/screening-lists/Synthetic list/schedule"
    for who in (ANALYST,):
        w.as_ = who
        refused = client.put(path, json={"schedule": {"every": "daily", "hour": 5}})
        assert refused.status_code == 403 and refused.json()["detail"]["right"] == "load_screening_lists"
    w.as_ = ENGINEER
    made = client.put(path, json={"schedule": {"every": "weekly", "hour": 5, "weekday": 1}})
    assert made.status_code == 200, made.text
    assert (made.json()["schedule_owner"], made.json()["schedule_words"]) == (
        ENGINEER.id, "every Monday at 05:00 (Europe/London)")  # fmt: skip
    assert w.audit.records[-1]["action"] == "screening_list_schedule_set"
    missing = client.put("/v1/admin/screening-lists/No such list/schedule", json={"schedule": None})
    assert missing.status_code == 404


def test_an_invalid_list_schedule_is_refused_in_words(world: tuple[_World, TestClient]) -> None:
    w, client = world
    client.post("/v1/admin/screening-lists", json=LIST)
    refused = client.put("/v1/admin/screening-lists/Synthetic list/schedule",
                         json={"schedule": {"every": "weekly", "hour": 5}})  # fmt: skip
    assert refused.status_code == 422
    assert refused.json()["detail"]["message"] == "a weekly schedule names the day of the week it runs on"


def test_the_lists_screen_says_the_schedule_in_words(world: tuple[_World, TestClient]) -> None:
    w, client = world
    client.post("/v1/admin/screening-lists", json=LIST)
    client.put("/v1/admin/screening-lists/Synthetic list/schedule", json={"schedule": {"every": "daily", "hour": 5}})
    (one,) = client.get("/v1/admin/screening-lists").json()["lists"]
    assert one["schedule_words"] == "every day at 05:00 (Europe/London)" and one["next_refresh"]
    w.as_ = ANALYST
    (seen,) = client.get("/v1/screening-lists").json()["lists"]
    assert seen["schedule_words"] == "every day at 05:00 (Europe/London)"
    assert seen["schedule_owner"] is None  # who runs it is the managers' to know


async def test_the_list_store_keeps_the_schedule_columns() -> None:
    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        columns = {r["column_name"] for r in await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'screening_lists'")}  # fmt: skip
    finally:
        await conn.close()
    assert {"schedule_every", "schedule_hour", "schedule_weekday", "schedule_owner"} <= columns

