"""A screening list as a managed source in Postgres (`spec/06_DECISIONS.md` ADR-133 decision 4, stage
(c)): versions, the diff each update makes, its record, and the failure the Lists screen shows.

What a mistake would do, and the case that catches it:
- a re-screening that reads the whole list, because the diff calls an unchanged entry changed —
  `test_an_update_says_which_entries_it_added_changed_and_removed`;
- a refresh that finds the same version again moving "last update" —
  `test_the_same_version_again_changes_nothing_and_keeps_the_last_update`;
- a failure that stays on the Lists screen after the list is read again, or none shown —
  `test_a_failure_is_shown_until_the_next_good_refresh`;
- aliases lost between the file and the screening — `test_aliases_are_kept_and_read_back`;
- a re-screening that misses a case's screening rule, or runs a retired one —
  `test_every_active_screening_rule_in_every_case_is_found`;
- another unit's counts, or its rule's failure, read by an administrator (the owner's answer of 1
  November 2026; rules 3 and 7) — `test_a_refresh_is_read_with_the_readers_own_units_counts_alone`;
- a refresh recorded before counts were kept per unit read with the deployment's totals —
  `test_an_older_refresh_shows_what_the_list_did_and_no_count`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import asyncpg
import pytest
from services.api.config import PostgresConfig
from services.api.screening import ScreeningEntry, ScreeningListStore, UnitCounts
from services.api.typology_rules import TypologyRuleStore

from conduit_common.identity import new_id
from schemas.domain import KycScreeningParams, Principal, StructuringParams, TypologyRuleInput
from schemas.screening import ScreeningListUpdate, ScreeningSubscriptionInput
from tests.services.api.screening_cleanup import remove_screening_lists

ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="unit-a", datasets=["ds-1"])


@pytest.fixture
async def store() -> AsyncIterator[ScreeningListStore]:
    dsn = PostgresConfig.from_env().dsn
    made = await ScreeningListStore.connect(dsn)
    conn = await asyncpg.connect(dsn)
    await conn.execute("DELETE FROM screening_list_updates; DELETE FROM screening_lists; "
                       "DELETE FROM screening_entries WHERE list_name LIKE 'Store test%'")  # fmt: skip
    await conn.close()
    try:
        yield made
    finally:
        await made.close()
        # Its own list removed, on a failure too (CARRIES row 113, `screening_cleanup`).
        await remove_screening_lists(dsn, prefixes=["Store test"])


def _entry(ref: str, name: str, **more: object) -> ScreeningEntry:
    return ScreeningEntry(id=f"Store test:{ref}", list_name="Store test", listing="sanction",
                          entity_type="Person", name=name, **more)  # type: ignore[arg-type]  # fmt: skip


async def _subscribe(store: ScreeningListStore) -> None:
    await store.subscribe(
        ScreeningSubscriptionInput(list_name="Store test", source="opensanctions", location="x.json"),
        ADMIN.id,
        synthetic=True,
    )


async def test_an_update_says_which_entries_it_added_changed_and_removed(
    store: ScreeningListStore,
) -> None:
    await _subscribe(store)
    first = await store.apply_update(
        "Store test", "v1", [_entry("1", "Ann Able"), _entry("2", "Ben Bold"), _entry("3", "Cy Cole")],
        synthetic=True,
    )  # fmt: skip
    assert (len(first.added), first.changed, first.removed, first.previous_version) == (3, (), (), None)
    second = await store.apply_update(
        "Store test", "v2",
        [_entry("1", "Ann Able"), _entry("2", "Ben Bold", date_of_birth=date(1970, 1, 1)),
         _entry("4", "Di Dorn")],
        synthetic=True,
    )  # fmt: skip
    assert [e.id for e in second.added] == ["Store test:4"]
    assert [e.id for e in second.changed] == ["Store test:2"]
    assert second.removed == ("Store test:3",)
    assert (second.unchanged, second.previous_version, second.version) == (1, "v1", "v2")
    assert [e.id for e in second.to_screen] == ["Store test:4", "Store test:2"]
    status = await store.subscription("Store test")
    assert status is not None and (status.version, status.entries) == ("v2", 3)
    assert {e.id for e in await store.entries("Person")} >= {"Store test:1", "Store test:2", "Store test:4"}
    assert "Store test:3" not in {e.id for e in await store.entries("Person")}


async def test_the_same_version_again_changes_nothing_and_keeps_the_last_update(
    store: ScreeningListStore,
) -> None:
    await _subscribe(store)
    await store.apply_update("Store test", "v1", [_entry("1", "Ann Able")], synthetic=True)
    before = await store.subscription("Store test")
    again = await store.apply_update("Store test", "v1", [_entry("1", "Ann Able")], synthetic=True)
    after = await store.subscription("Store test")
    assert (again.added, again.changed, again.removed, again.unchanged) == ((), (), (), 1)
    assert before is not None and after is not None
    assert after.updated_at == before.updated_at
    assert after.attempted_at is not None and before.attempted_at is not None
    assert after.attempted_at >= before.attempted_at


async def test_a_failure_is_shown_until_the_next_good_refresh(store: ScreeningListStore) -> None:
    await _subscribe(store)
    await store.record_update(ScreeningListUpdate(
        id=new_id(), list_name="Store test", at=datetime.now(UTC), outcome="failed",
        words="The file could not be read as opensanctions: line 1 is not a JSON object.",
    ))  # fmt: skip
    status = await store.subscription("Store test")
    assert status is not None and status.failure is not None and "not a JSON object" in status.failure
    await store.apply_update("Store test", "v1", [_entry("1", "Ann Able")], synthetic=True)
    status = await store.subscription("Store test")
    assert status is not None and status.failure is None
    (latest, *_) = await store.updates(org_unit="unit-a")
    assert latest.outcome == "failed"


async def test_aliases_are_kept_and_read_back(store: ScreeningListStore) -> None:
    await _subscribe(store)
    await store.apply_update(
        "Store test", "v1", [_entry("1", "Ann Able", aliases=("Annie Able", "A. Able"))], synthetic=True
    )
    (read,) = [e for e in await store.entries("Person") if e.id == "Store test:1"]
    assert read.aliases == ("Annie Able", "A. Able")


async def test_every_active_screening_rule_in_every_case_is_found() -> None:
    rules = await TypologyRuleStore.connect(PostgresConfig.from_env().dsn)
    try:
        cases = [f"case-{new_id()}", f"case-{new_id()}"]
        one = await rules.create(ADMIN, cases[0], TypologyRuleInput(name="screen", params=KycScreeningParams()))
        two = await rules.create(ADMIN, cases[1], TypologyRuleInput(name="screen", params=KycScreeningParams()))
        retired = await rules.create(ADMIN, cases[1], TypologyRuleInput(name="old", params=KycScreeningParams()))
        await rules.retire(retired.id, cases[1], ADMIN)
        await rules.create(ADMIN, cases[0], TypologyRuleInput(
            name="structuring", params=StructuringParams(threshold=10000, window_days=7, minimum_count=3)))  # fmt: skip
        found = {r.id for r in await rules.list_active_of_typology("kyc_screening")}
        assert {one.id, two.id} <= found
        assert retired.id not in found
        assert all(r.params.typology == "kyc_screening" for r in await rules.list_active_of_typology("kyc_screening"))
    finally:
        await rules.close()


async def test_a_refresh_is_read_with_the_readers_own_units_counts_alone(
    store: ScreeningListStore,
) -> None:
    await _subscribe(store)
    update = ScreeningListUpdate(
        id=new_id(), list_name="Store test", at=datetime.now(UTC), outcome="updated", added=2,
        changed=1, rescreened=9, alerts=3,
        words="Version v2: 2 added, 1 changed, 0 removed. 9 customers re-screened against 3 changed "
              "entries; 3 alerts raised. Rule “Unit B watch” could not re-screen: the graph failed.",
    )  # fmt: skip
    await store.record_update(
        update,
        list_words="Version v2: 2 added, 1 changed, 0 removed.",
        by_unit={
            "unit-a": UnitCounts(rescreened=4, alerts=1),
            "unit-b": UnitCounts(rescreened=5, alerts=2,
                                 failures=["rule “Unit B watch” could not re-screen: the graph failed"]),
        },
    )  # fmt: skip
    (a,) = [u for u in await store.updates(org_unit="unit-a") if u.id == update.id]
    assert (a.rescreened, a.alerts) == (4, 1)
    assert a.words == ("Version v2: 2 added, 1 changed, 0 removed. 4 customers re-screened against "
                       "3 changed entries; 1 alert raised.")  # fmt: skip
    b = await store.update_for(update.id, org_unit="unit-b")
    assert b is not None and (b.rescreened, b.alerts) == (5, 2)
    assert b.words.endswith("Rule “Unit B watch” could not re-screen: the graph failed.")
    c = await store.update_for(update.id, org_unit="unit-c")
    assert c is not None and (c.rescreened, c.alerts) == (0, 0)
    assert "Unit B" not in c.words and "9 customers" not in c.words


async def test_an_older_refresh_shows_what_the_list_did_and_no_count(
    store: ScreeningListStore,
) -> None:
    await _subscribe(store)
    older = ScreeningListUpdate(
        id=new_id(), list_name="Store test", at=datetime.now(UTC), outcome="updated", version="v1",
        added=3, rescreened=12, alerts=4,
        words="Version v1: 3 added, 0 changed, 0 removed. 12 customers re-screened against 3 changed "
              "entries; 4 alerts raised.",
    )  # fmt: skip
    await store.record_update(older)  # as stage (c) recorded it: no unit rows, no list words
    read = await store.update_for(older.id, org_unit="unit-a")
    assert read is not None and (read.rescreened, read.alerts) == (0, 0)
    assert read.words.startswith("Version v1: 3 added, 0 changed, 0 removed.")
    assert "12" not in read.words and "not counted by unit" in read.words
