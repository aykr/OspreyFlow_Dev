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
from services.api.screening import (
    ListClearance,
    MarkingLowered,
    ScreeningEntry,
    ScreeningListStore,
    UnitCounts,
)
from services.api.typology_rules import TypologyRuleStore

from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from schemas.domain import KycScreeningParams, Principal, StructuringParams, TypologyRuleInput
from schemas.screening import ScreeningListUpdate, ScreeningSubscriptionInput
from tests.services.api.screening_cleanup import EVERYTHING, remove_screening_lists

SCHEME = load_uk_le_scheme()
ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="unit-a", datasets=["ds-1"])


@pytest.fixture
async def store() -> AsyncIterator[ScreeningListStore]:
    dsn = PostgresConfig.from_env().dsn
    made = await ScreeningListStore.connect(dsn)
    conn = await asyncpg.connect(dsn)
    await conn.execute("DELETE FROM screening_list_updates; DELETE FROM screening_lists; "
                       "DELETE FROM screening_entries WHERE list_name LIKE 'Store test%'")  # fmt: skip
    await conn.close()
    # Its own lists' kept markings too, so a run killed before its teardown leaves none.
    await remove_screening_lists(dsn, prefixes=["Store test"])
    try:
        yield made
    finally:
        # Its own list removed, on a failure too (CARRIES row 113, `screening_cleanup`), before the
        # store it was loaded through is closed (the orchestrator's review, a note).
        await remove_screening_lists(dsn, prefixes=["Store test"])
        await made.close()


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
    assert {e.id for e in await store.entries("Person", cleared=EVERYTHING)} >= {"Store test:1", "Store test:2", "Store test:4"}
    assert "Store test:3" not in {e.id for e in await store.entries("Person", cleared=EVERYTHING)}


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
    (latest, *_) = await store.updates(org_unit="unit-a", cleared=EVERYTHING)
    assert latest.outcome == "failed"


async def test_aliases_are_kept_and_read_back(store: ScreeningListStore) -> None:
    await _subscribe(store)
    await store.apply_update(
        "Store test", "v1", [_entry("1", "Ann Able", aliases=("Annie Able", "A. Able"))], synthetic=True
    )
    (read,) = [e for e in await store.entries("Person", cleared=EVERYTHING) if e.id == "Store test:1"]
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
    (a,) = [u for u in await store.updates(org_unit="unit-a", cleared=EVERYTHING) if u.id == update.id]
    assert (a.rescreened, a.alerts) == (4, 1)
    assert a.words == ("Version v2: 2 added, 1 changed, 0 removed. 4 customers re-screened against "
                       "3 changed entries; 1 alert raised.")  # fmt: skip
    b = await store.update_for(update.id, org_unit="unit-b", cleared=EVERYTHING)
    assert b is not None and (b.rescreened, b.alerts) == (5, 2)
    assert b.words.endswith("Rule “Unit B watch” could not re-screen: the graph failed.")
    c = await store.update_for(update.id, org_unit="unit-c", cleared=EVERYTHING)
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
    read = await store.update_for(older.id, org_unit="unit-a", cleared=EVERYTHING)
    assert read is not None and (read.rescreened, read.alerts) == (0, 0)
    assert read.words.startswith("Version v1: 3 added, 0 changed, 0 removed.")
    assert "12" not in read.words and "not counted by unit" in read.words


async def test_an_update_keeps_a_marked_lists_marking(store: ScreeningListStore) -> None:
    """ADR-146 Amendment 7 (the lane review's item 10): a refresh's file carries no marking, so an
    update of a list loaded marked keeps the list's marking, and the same entries are no change.
    Red with `apply_update` writing the file's entries as they come: every entry OFFICIAL again,
    each one "changed" and re-screened."""
    await _subscribe(store)
    marked = [ScreeningEntry(id="Store test:1", list_name="Store test", listing="sanction",
                             entity_type="Person", name="Ann Able", classification="SECRET",
                             handling_code="P")]  # fmt: skip
    await store.replace_list("Store test", marked, scheme=SCHEME)
    diff = await store.apply_update("Store test", "v2", [_entry("1", "Ann Able")], synthetic=True)
    assert (diff.added, diff.changed, diff.removed) == ((), (), ())
    (entry,) = [e for e in await store.entries("Person", cleared=EVERYTHING) if e.list_name == "Store test"]
    assert (entry.classification, entry.handling_code) == ("SECRET", "P")


# --- a list read only by whom its marking clears (ADR-146 Amendment 7; the review, items 3 and 8) ---

OFFICIAL_READER = ListClearance.of(ADMIN, SCHEME)
SECRET_READER = ListClearance.of(ADMIN.model_copy(update={"clearance": "SECRET"}), SCHEME)


def _marked(ref: str, name: str) -> ScreeningEntry:
    return ScreeningEntry(id=f"Store test marked:{ref}", list_name="Store test marked", listing="sanction",
                          entity_type="Person", name=name, classification="SECRET", handling_code="P")  # fmt: skip


async def _marked_list(store: ScreeningListStore) -> ScreeningListUpdate:
    """"Store test" unmarked and "Store test marked" SECRET, both subscribed and refreshed once."""
    await _subscribe(store)
    await store.apply_update("Store test", "v1", [_entry("1", "Ann Able")], synthetic=True)
    await store.replace_list("Store test marked", [_marked("1", "Ann Secret")], scheme=SCHEME)
    await store.subscribe(
        ScreeningSubscriptionInput(list_name="Store test marked", source="opensanctions", location="m.json"),
        ADMIN.id, synthetic=True,
    )  # fmt: skip
    await store.apply_update("Store test marked", "v2", [_marked("1", "Ann Secret")], synthetic=True)
    update = ScreeningListUpdate(id=new_id(), list_name="Store test marked", at=datetime.now(UTC),
                                 outcome="updated", version="v2", words="")  # fmt: skip
    await store.record_update(update, list_words="Version v2.", by_unit={"unit-a": UnitCounts(1, 0)})
    return update


async def test_a_lists_entries_are_read_only_for_a_clearance_admitting_its_marking(
    store: ScreeningListStore,
) -> None:
    """Item 1, in the query: red with `entries` reading every list (an OFFICIAL deployer's rule
    screened against the SECRET list)."""
    await _marked_list(store)
    low = {e.list_name for e in await store.entries("Person", cleared=OFFICIAL_READER)}
    high = {e.list_name for e in await store.entries("Person", cleared=SECRET_READER)}
    assert "Store test marked" not in low and "Store test" in low
    assert {"Store test marked", "Store test"} <= high


async def test_a_lists_subscription_and_refreshes_are_read_only_for_a_clearance_admitting_it(
    store: ScreeningListStore,
) -> None:
    """Item 3 (rule 4, each way): the Lists screen's subscriptions, its refreshes and one refresh,
    and whether a name is held hidden. Red with the reads unfiltered: the SECRET list's name,
    version, count and failure words shown to an OFFICIAL administrator."""
    update = await _marked_list(store)
    assert [s.list_name for s in await store.subscriptions(cleared=OFFICIAL_READER)] == ["Store test"]
    assert [s.list_name for s in await store.subscriptions(cleared=SECRET_READER)] == ["Store test", "Store test marked"]
    low = {u.list_name for u in await store.updates(org_unit="unit-a", cleared=OFFICIAL_READER)}
    assert "Store test marked" not in low
    assert await store.update_for(update.id, org_unit="unit-a", cleared=OFFICIAL_READER) is None
    assert await store.update_for(update.id, org_unit="unit-a", cleared=SECRET_READER) is not None
    assert await store.hidden("Store test marked", cleared=OFFICIAL_READER)
    assert not await store.hidden("Store test marked", cleared=SECRET_READER)
    assert not await store.hidden("Store test", cleared=OFFICIAL_READER)
    assert not await store.hidden("Store test never held", cleared=OFFICIAL_READER)


async def test_an_emptied_list_keeps_its_marking(store: ScreeningListStore) -> None:
    """The marking is kept apart from the entries: a refresh that empties the SECRET list, then one
    that fills it again from a file carrying no marking, leaves it SECRET (and hidden throughout).
    Red with the marking read from the entries alone: the second refresh made it OFFICIAL."""
    await _marked_list(store)
    await store.apply_update("Store test marked", "v3", [], synthetic=True)
    assert await store.hidden("Store test marked", cleared=OFFICIAL_READER)
    plain = ScreeningEntry(id="Store test marked:1", list_name="Store test marked", listing="sanction",
                           entity_type="Person", name="Ann Secret")  # fmt: skip
    await store.apply_update("Store test marked", "v4", [plain], synthetic=True)
    (entry,) = [e for e in await store.entries("Person", cleared=SECRET_READER) if e.list_name == "Store test marked"]
    assert (entry.classification, entry.handling_code) == ("SECRET", "P")
    assert "Store test marked" not in {e.list_name for e in await store.entries("Person", cleared=OFFICIAL_READER)}


async def test_a_reload_that_would_lower_a_lists_marking_is_refused_and_changes_nothing(
    store: ScreeningListStore,
) -> None:
    """Item 8: loading the SECRET list's file again with no marking (OFFICIAL) is refused in words,
    its entries and marking as they were. Red with `replace_list` taking the file's marking: the
    list read as OFFICIAL by every reader."""
    await store.replace_list("Store test marked", [_marked("1", "Ann Secret")], scheme=SCHEME)
    plain = ScreeningEntry(id="Store test marked:2", list_name="Store test marked", listing="sanction",
                           entity_type="Person", name="Bea Plain")  # fmt: skip
    with pytest.raises(MarkingLowered, match="would lower it"):
        await store.replace_list("Store test marked", [plain], scheme=SCHEME)
    held = [e for e in await store.entries("Person", cleared=SECRET_READER) if e.list_name == "Store test marked"]
    assert [(e.id, e.classification) for e in held] == [("Store test marked:1", "SECRET")]
    raised = [_marked("1", "Ann Secret")]
    assert await store.replace_list("Store test marked", raised, scheme=SCHEME) == 1
