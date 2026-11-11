"""ADR-110 Amendment 19: a scheduled load's notice reaches its owner in *Needs you*, read and counted
by owner alone, in the query itself (rules 3 and 4; the orchestrator's ruling of 10 November 2026:
the owner, with no dataset reach). Against the throwaway Postgres, through the real `schedule_notice`
and `AlertStore.list_schedule_notices`, with each reader made as the route makes it
(`dataset_scope.outside_any_case`, so `datasets=[]`). Every notice this file writes is its own
owner's, under ids made here, and is removed in teardown even when a case fails (the database is
shared).

What a mistake would do, and the case that catches it (each shown red by a plant in the query,
under the rules lease: `process/lanes/rules/hyg/3-schedule-notices-red.txt`):

- another person's notice served, or counted, to someone else, an administrator, the owner's team
  lead or an unknown principal (the owner filter dropped from the list or the total):
  `test_only_the_owner_reads_or_counts_a_notice`;
- a notice hidden once `scripts.stamp_datasets` placed it in its case's dataset (a dataset reach
  applied to a reader outside any case): `test_a_stamped_notice_and_an_unstamped_one_are_both_served`;
- a notice written before the amendment left out, or a rule's alert served as a notice (the prefix
  or `typology IS NULL` dropped): `test_a_notice_is_any_schedule_alert_and_nothing_else`;
- a notice older than the window, or closed, served (either filter dropped):
  `test_the_window_and_the_status_bound_it`;
- more notices than the limit cut without saying so (the total taken after the limit):
  `test_more_than_the_limit_is_said_by_the_total`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from conduit_common.identity import new_id
from schemas.domain import Alert, AlertMode, Principal
from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus
from services.api.alerts import AlertStore
from services.api.config import PostgresConfig
from services.api.dataset_scope import outside_any_case
from services.api.needs_you import NOTICE_LIMIT
from services.api.scheduler import schedule_notice

pytestmark = pytest.mark.skipif(
    not os.environ.get("OSPREY_LANE")
    and not os.environ.get("OSPREY_TEST_ARCADEDB_CONTAINER"),
    reason="needs a leased lane stack (OSPREY_LANE and its pinned ports), or CI's live job",
)

NOW = datetime(2026, 11, 10, 21, 0, tzinfo=UTC)
SINCE = NOW - timedelta(days=7)


def _recipe(owner: str) -> StudioRecipeDraft:
    return StudioRecipeDraft(
        recipe_id=new_id(), version=1, status=StudioRecipeStatus.PUBLISHED, label="Daily export",
        handling={}, owning_unit="unit-1", created_by=owner, created_at=NOW, ready_for_profile=True,
        schedule_cron="0 6 * * *", schedule_owner=owner, schedule_case=new_id(),
    )  # fmt: skip


def _reader(pid: str, roles: list[str]) -> Principal:
    """A reader as `/v1/me/needs-you` makes one: outside any case, so `datasets=[]`."""
    return outside_any_case(
        Principal(id=pid, clearance="SECRET", org_unit="unit-1", roles=roles)
    )


@pytest.fixture
async def world() -> AsyncIterator[tuple[AlertStore, list[str]]]:
    store = await AlertStore.connect(PostgresConfig.from_env().dsn)
    written: list[str] = []
    try:
        yield store, written
    finally:
        if written:
            async with store._pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM alerts WHERE id = ANY($1::text[])", written
                )
        await store.close()


async def _notice(
    store: AlertStore,
    written: list[str],
    owner: str,
    at: datetime,
    *,
    dataset: str | None = None,
) -> Alert:
    notice = schedule_notice(
        owner, _recipe(owner), "The scheduled run of Daily export failed.", at
    )
    if (
        dataset is not None
    ):  # as `scripts.stamp_datasets` places an alert in its case's dataset
        notice = notice.model_copy(update={"dataset_id": dataset})
    await store.save(notice)
    written.append(notice.id)
    return notice


async def test_only_the_owner_reads_or_counts_a_notice(
    world: tuple[AlertStore, list[str]],
) -> None:
    store, written = world
    owner = f"owner-{new_id()}"
    mine = await _notice(store, written, owner, NOW - timedelta(hours=1))
    stamped = await _notice(
        store, written, owner, NOW - timedelta(hours=2), dataset=new_id()
    )
    listed, total = await store.list_schedule_notices(
        _reader(owner, ["data_engineer"]), since=SINCE, limit=NOTICE_LIMIT
    )
    assert [n.id for n in listed] == [mine.id, stamped.id] and total == 2
    # Someone else, an administrator, the owner's team lead and a principal the deployment has
    # never seen: each reads none of the owner's notices and counts none (rule 3: nothing of them
    # is known by its number either). Each is new here, so has none of its own.
    for other in (
        _reader(f"other-{new_id()}", ["data_engineer"]),
        _reader(f"admin-{new_id()}", ["osprey-admin", "analyst"]),
        _reader(f"lead-{new_id()}", ["analyst", "team_lead"]),
        _reader(f"unknown-{new_id()}", []),
    ):
        assert await store.list_schedule_notices(
            other, since=SINCE, limit=NOTICE_LIMIT
        ) == ([], 0), other.roles


async def test_a_stamped_notice_and_an_unstamped_one_are_both_served(
    world: tuple[AlertStore, list[str]],
) -> None:
    """The ruling: a notice is read by owner alone, never by dataset reach. A reader outside any
    case reaches no dataset (`datasets=[]`), so a reach would hide every notice once stamped."""
    store, written = world
    owner = f"owner-{new_id()}"
    unstamped = await _notice(store, written, owner, NOW - timedelta(hours=1))
    stamped = await _notice(
        store, written, owner, NOW - timedelta(hours=2), dataset=f"ds-{new_id()}"
    )
    listed, total = await store.list_schedule_notices(
        _reader(owner, ["analyst"]), since=SINCE, limit=NOTICE_LIMIT
    )
    assert {n.id for n in listed} == {unstamped.id, stamped.id} and total == 2


async def test_a_notice_is_any_schedule_alert_and_nothing_else(
    world: tuple[AlertStore, list[str]],
) -> None:
    store, written = world
    owner = f"owner-{new_id()}"
    # Written before this amendment, exactly as the scheduler wrote it then (`schedule:<id>`, no
    # typology, no referent): the same shape, so it is served.
    before = await _notice(store, written, owner, NOW - timedelta(days=2))
    rule_alert = Alert(id=new_id(), rule_id=f"rule-{new_id()}", owner_id=owner, mode=AlertMode.FULL,
                       referent_node_ids=["n-1"], investigation_id=new_id(), created_at=NOW,
                       typology="structuring", words="A rule's alert")  # fmt: skip
    typed = Alert(id=new_id(), rule_id=f"schedule:{new_id()}", owner_id=owner, mode=AlertMode.FULL,
                  referent_node_ids=[], investigation_id=new_id(), created_at=NOW,
                  typology="structuring", words="Not a notice: it has a typology")  # fmt: skip
    for alert in (rule_alert, typed):
        await store.save(alert)
        written.append(alert.id)
    listed, total = await store.list_schedule_notices(
        _reader(owner, ["analyst"]), since=SINCE, limit=NOTICE_LIMIT
    )
    assert [n.id for n in listed] == [before.id] and total == 1


async def test_the_window_and_the_status_bound_it(
    world: tuple[AlertStore, list[str]],
) -> None:
    store, written = world
    owner = f"owner-{new_id()}"
    await _notice(store, written, owner, NOW - timedelta(days=8))
    closed = await _notice(store, written, owner, NOW - timedelta(hours=3))
    async with store._pool.acquire() as conn:
        await conn.execute(
            "UPDATE alerts SET status = 'closed' WHERE id = $1", closed.id
        )
    fresh = await _notice(store, written, owner, NOW - timedelta(hours=2))
    listed, total = await store.list_schedule_notices(
        _reader(owner, ["analyst"]), since=SINCE, limit=NOTICE_LIMIT
    )
    assert [n.id for n in listed] == [fresh.id] and total == 1


async def test_more_than_the_limit_is_said_by_the_total(
    world: tuple[AlertStore, list[str]],
) -> None:
    store, written = world
    owner = f"owner-{new_id()}"
    made = [
        await _notice(store, written, owner, NOW - timedelta(minutes=m))
        for m in range(5)
    ]
    listed, total = await store.list_schedule_notices(
        _reader(owner, ["analyst"]), since=SINCE, limit=3
    )
    assert [n.id for n in listed] == [n.id for n in made[:3]]  # newest first
    assert total == 5
