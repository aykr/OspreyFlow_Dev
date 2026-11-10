"""ADR-110 Amendment 19: a scheduled load's notice reaches its owner in *Needs you*, read by owner in
the query itself (rule 3), against the throwaway Postgres, through the real `schedule_notice` and
`AlertStore.list_schedule_notices`. Every notice this file writes is its own owner's, under ids made
here, and is removed in teardown even when a case fails (the database is shared).

What a mistake would do, and the case that catches it (each shown red at its call site,
`process/lanes/rules/hyg/3-schedule-notices-red.txt`):

- another person's notice served, or counted, to someone else, an administrator or a team lead
  among them (the owner filter dropped from the query, or applied after it, or the total counted
  over every owner): `test_only_the_owner_reads_or_counts_a_notice`;
- a notice written before the fix (`schedule:<recipe>`, no typology) left out, or an alert of
  another kind served as a notice: `test_a_notice_is_any_schedule_alert_and_nothing_else`;
- a notice older than the window, or closed, served: `test_the_window_and_the_status_bound_it`;
- more notices than the limit cut without saying so: `test_more_than_the_limit_is_said_by_the_total`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from services.api.alerts import AlertStore
from services.api.config import PostgresConfig
from services.api.scheduler import schedule_notice

from conduit_common.identity import new_id
from schemas.domain import Alert, AlertMode, Principal
from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus

NOW = datetime(2026, 11, 10, 21, 0, tzinfo=UTC)
SINCE = NOW - timedelta(days=7)


def _recipe(owner: str) -> StudioRecipeDraft:
    return StudioRecipeDraft(  # type: ignore[call-arg]
        recipe_id=new_id(), version=1, status=StudioRecipeStatus.PUBLISHED, label="Daily export",
        handling={}, owning_unit="unit-1", created_by=owner, created_at=NOW, ready_for_profile=True,
        schedule_cron="0 6 * * *", schedule_owner=owner, schedule_case=new_id(),
    )  # fmt: skip


def _person(pid: str, roles: list[str]) -> Principal:
    return Principal(id=pid, clearance="SECRET", org_unit="unit-1", roles=roles)


@pytest.fixture
async def world() -> AsyncIterator[tuple[AlertStore, list[str]]]:
    store = await AlertStore.connect(PostgresConfig.from_env().dsn)
    written: list[str] = []
    try:
        yield store, written
    finally:
        if written:
            async with store._pool.acquire() as conn:
                await conn.execute("DELETE FROM alerts WHERE id = ANY($1::text[])", written)
        await store.close()


async def _notice(store: AlertStore, written: list[str], owner: str, at: datetime) -> Alert:
    notice = schedule_notice(owner, _recipe(owner), f"The scheduled run of Daily export failed {at}", at)
    await store.save(notice)
    written.append(notice.id)
    return notice


async def test_only_the_owner_reads_or_counts_a_notice(world: tuple[AlertStore, list[str]]) -> None:
    store, written = world
    owner = f"owner-{new_id()}"
    mine = await _notice(store, written, owner, NOW - timedelta(hours=1))
    listed, total = await store.list_schedule_notices(_person(owner, ["data_engineer"]), since=SINCE)
    assert [n.id for n in listed] == [mine.id] and total == 1
    # Someone else, an administrator and a team lead, each a real principal's shape: no notice of
    # the owner's, and none counted, so nothing of it is known by its number either (rule 3).
    for other in (
        _person(f"other-{new_id()}", ["data_engineer"]),
        _person(f"admin-{new_id()}", ["osprey-admin", "analyst"]),
        _person(f"lead-{new_id()}", ["analyst", "team_lead"]),
    ):
        theirs, counted = await store.list_schedule_notices(other, since=SINCE)
        assert all(n.owner_id == other.id for n in theirs), (other.roles, theirs)
        assert mine.id not in {n.id for n in theirs} and counted == len(theirs), other.roles


async def test_a_notice_is_any_schedule_alert_and_nothing_else(world: tuple[AlertStore, list[str]]) -> None:
    store, written = world
    owner = f"owner-{new_id()}"
    # One written before this amendment, exactly as the scheduler wrote it then (`schedule:<id>`,
    # no typology, no referent): the same shape, so it is served.
    before = await _notice(store, written, owner, NOW - timedelta(days=2))
    # An alert of the owner's that is no notice: a rule's, with a typology.
    rule_alert = Alert(id=new_id(), rule_id=f"rule-{new_id()}", owner_id=owner, mode=AlertMode.FULL,
                       referent_node_ids=["n-1"], investigation_id=new_id(), created_at=NOW,
                       typology="structuring", words="A rule's alert")  # fmt: skip
    await store.save(rule_alert)
    written.append(rule_alert.id)
    listed, total = await store.list_schedule_notices(_person(owner, ["analyst"]), since=SINCE)
    assert [n.id for n in listed] == [before.id] and total == 1


async def test_the_window_and_the_status_bound_it(world: tuple[AlertStore, list[str]]) -> None:
    store, written = world
    owner = f"owner-{new_id()}"
    await _notice(store, written, owner, NOW - timedelta(days=8))
    closed = await _notice(store, written, owner, NOW - timedelta(hours=3))
    async with store._pool.acquire() as conn:
        await conn.execute("UPDATE alerts SET status = 'closed' WHERE id = $1", closed.id)
    fresh = await _notice(store, written, owner, NOW - timedelta(hours=2))
    listed, total = await store.list_schedule_notices(_person(owner, ["analyst"]), since=SINCE)
    assert [n.id for n in listed] == [fresh.id] and total == 1


async def test_more_than_the_limit_is_said_by_the_total(world: tuple[AlertStore, list[str]]) -> None:
    store, written = world
    owner = f"owner-{new_id()}"
    made = [await _notice(store, written, owner, NOW - timedelta(minutes=m)) for m in range(5)]
    listed, total = await store.list_schedule_notices(_person(owner, ["analyst"]), since=SINCE, limit=3)
    assert [n.id for n in listed] == [n.id for n in made[:3]]  # newest first
    assert total == 5
