"""ADR-044 Amendment 2 (the owner's ruling, 14 November 2026): a load whose owner's sign-in cannot be checked
(`unreachable`) no longer stops a hotlist or a watch at once. It stays active, matching nothing, until the third
such load in a row, which stops it; a load that can act as the owner between them puts the count back to 0. The
count is the watch's own, kept by its store (the live restart case is `test_hotlists.py`'s and
`test_monitors.py`'s). Any other reason still stops it at once. A watch's schedule that gives its slot back for
an unreachable owner (`monitor_schedule.py`) is not an evaluation: it neither counts nor resets (the
orchestrator's ruling, 14 November 2026).

Offline, in the evaluator's own shape: the stores are doubles keeping the count as the real ones do
(`watch_status_fake.UnreachableCount`), and nothing is read or matched for a watch its owner cannot be acted as
(`_Nothing` raises if it is).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from services.api.evaluation import evaluate_hotlists_for_entry, evaluate_monitors_for_entry
from services.api.monitor_schedule import MonitorScheduleExecutor
from services.api.watch_status import STOPPED_WHY, UNREACHABLE_STOPS_AT, active_note

from ontology.handling import load_uk_le_scheme
from principal_auth import OwnerRecordUnavailable, PrincipalExchangeUnavailable, PrincipalRevoked
from schemas.domain import Hotlist, Monitor, Principal
from tests.services.api.test_owner_on_entra import _Claims
from tests.services.api.watch_status_fake import UnreachableCount, kept

OWNER = Principal(id="owner-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
NOW = datetime(2026, 11, 14, 9, tzinfo=UTC)
DOWN = PrincipalExchangeUnavailable("the identity provider could not be reached")


class _Store:
    """`HotlistStore`/`MonitorStore` as the evaluator calls them, with the count kept as the real one keeps it."""

    def __init__(self, watch: Any) -> None:
        self.watch = watch
        self.told: list[tuple[str, str | None]] = []
        self.count = UnreachableCount()

    async def list_all_active(self) -> list[Any]:
        return [self.watch]

    async def set_status(self, watch_id: str, status: str, detail: str | None = None) -> None:
        self.told.append(kept(status, detail))
        self.count.reset(watch_id)

    async def count_unreachable(self, watch_id: str) -> int:
        return self.count.count(watch_id)

    async def last_slot(self, _id: str) -> None:
        return None

    async def record_slot(self, *_: Any) -> None:
        return None

    @property
    def in_a_row(self) -> int:
        return self.count.in_a_row.get(self.watch.id, 0)


class _Nothing:
    node_ids: list[str] = ["n-1"]

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"nothing is read or matched for a watch its owner cannot be acted as ({name})")


def _owner_answers(*outcomes: Exception | None):  # type: ignore[no-untyped-def]
    """Each load's answer for the owner in turn: a refusal raised, or the owner (None: the owner resolves)."""
    answers = list(outcomes)

    async def resolve(_owner: str) -> Principal:
        outcome = answers.pop(0)
        if outcome is not None:
            raise outcome
        return OWNER

    return resolve


async def _no_reach(_owner: Principal, _dataset: str) -> bool:
    return False  # reachable, then not matched: the owner no longer reaches the dataset, so nothing is read


def _hotlist() -> Hotlist:
    return Hotlist(id="h-1", identifier="07700900123", owner_id=OWNER.id, review_date=date(2027, 1, 1),
                   created_at=NOW, dataset_id="ds-1")  # fmt: skip


def _monitor() -> Monitor:
    return Monitor(id="m-1", pattern_id="p-1", owner_id=OWNER.id, created_at=NOW - timedelta(days=2),
                   every="daily", hour=5, dataset_id="ds-1")  # fmt: skip


async def _hotlist_loads(store: _Store, *outcomes: Exception | None) -> None:
    resolve = _owner_answers(*outcomes)
    for _ in outcomes:
        await evaluate_hotlists_for_entry(_Nothing(), graph=_Nothing(), scheme=load_uk_le_scheme(), hotlist_store=store,  # type: ignore[arg-type]
                                          alert_store=_Nothing(), audit=_Nothing(), valkey=_Nothing(),  # type: ignore[arg-type]
                                          principal_for_owner=resolve, policy="strict", reaches_dataset=_no_reach)  # fmt: skip


async def _monitor_loads(store: _Store, *outcomes: Exception | None) -> None:
    resolve = _owner_answers(*outcomes)
    for _ in outcomes:
        await evaluate_monitors_for_entry(_Nothing(), graph=_Nothing(), monitor_store=store, pattern_store=_Nothing(),  # type: ignore[arg-type]
                                          alert_store=_Nothing(), audit=_Nothing(), valkey=_Nothing(),  # type: ignore[arg-type]
                                          principal_for_owner=resolve, reaches_dataset=_no_reach)  # fmt: skip


LOADS = [("hotlist", _hotlist, _hotlist_loads), ("watch", _monitor, _monitor_loads)]
KINDS = [k for k, _, _ in LOADS]


@pytest.mark.parametrize(("kind", "watch", "loads"), LOADS, ids=KINDS)
async def test_one_unreachable_load_leaves_it_active_counted_once_and_matches_nothing(kind, watch, loads) -> None:  # type: ignore[no-untyped-def]
    store = _Store(watch())
    await loads(store, DOWN)
    assert store.told == [] and store.in_a_row == 1


@pytest.mark.parametrize(("kind", "watch", "loads"), LOADS, ids=KINDS)
async def test_two_in_a_row_leave_it_active_counted_twice(kind, watch, loads) -> None:  # type: ignore[no-untyped-def]
    store = _Store(watch())
    await loads(store, DOWN, OwnerRecordUnavailable("Admin › People's store could not be read"))
    assert store.told == [] and store.in_a_row == 2


@pytest.mark.parametrize(("kind", "watch", "loads"), LOADS, ids=KINDS)
async def test_the_third_in_a_row_stops_it_unreachable(kind, watch, loads) -> None:  # type: ignore[no-untyped-def]
    store = _Store(watch())
    await loads(store, DOWN, DOWN, DOWN)
    assert store.told == [("stopped", "unreachable")] and store.in_a_row == 0
    assert "three loads in a row" in STOPPED_WHY["unreachable"]


@pytest.mark.parametrize(("kind", "watch", "loads"), LOADS, ids=KINDS)
async def test_a_reachable_load_between_puts_the_count_back(kind, watch, loads) -> None:  # type: ignore[no-untyped-def]
    store = _Store(watch())
    await loads(store, DOWN, None, DOWN)
    assert store.told == [("active", None)] and store.in_a_row == 1


@pytest.mark.parametrize(("kind", "watch", "loads"), LOADS, ids=KINDS)
async def test_any_other_reason_still_stops_it_at_once_and_puts_the_count_back(kind, watch, loads) -> None:  # type: ignore[no-untyped-def]
    store = _Store(watch())
    await loads(store, DOWN, DOWN, PrincipalRevoked("disabled"))
    assert store.told == [("stopped", "revoked")] and store.in_a_row == 0


@pytest.mark.parametrize(("kind", "watch", "loads"), LOADS, ids=KINDS)
async def test_another_reason_at_the_first_load_stops_it_at_once_uncounted(kind, watch, loads) -> None:  # type: ignore[no-untyped-def]
    store = _Store(watch())
    await loads(store, PrincipalRevoked("disabled"))
    assert store.told == [("stopped", "revoked")] and store.in_a_row == 0


async def test_a_schedule_giving_its_slot_back_neither_counts_nor_resets() -> None:
    store = _Store(_monitor())
    await _monitor_loads(store, DOWN, DOWN)
    executor = MonitorScheduleExecutor(monitors=store, valkey=_Claims(), resolve_owner=_owner_answers(DOWN),  # type: ignore[arg-type]
                                       match=None, reaches_dataset=None)  # type: ignore[arg-type]  # fmt: skip
    await executor._consider(store.watch, NOW)
    assert store.told == [] and store.in_a_row == 2


@pytest.mark.parametrize("dataset", [None, "ds-1"], ids=["no-dataset", "dataset-not-reached"])
async def test_a_schedule_that_acts_as_the_owner_puts_the_count_back_even_matching_nothing(dataset) -> None:  # type: ignore[no-untyped-def]
    """A scheduled run that resolves its owner reached them, as a load that can act as its owner does: the count
    goes back to 0 whether or not the run then matches (a watch with no dataset, or one its owner no longer
    reaches, matches nothing), so "in a row" stays true of the loads the owner sees counted."""
    store = _Store(_monitor().model_copy(update={"dataset_id": dataset}))
    await _monitor_loads(store, DOWN, DOWN)
    executor = MonitorScheduleExecutor(monitors=store, valkey=_Claims(), resolve_owner=_owner_answers(None),  # type: ignore[arg-type]
                                       match=_Nothing(), reaches_dataset=_no_reach)  # type: ignore[arg-type]  # fmt: skip
    await executor._consider(store.watch, NOW)
    assert store.told == [("active", None)] and store.in_a_row == 0


def test_the_words_for_an_active_watch_with_misses_and_none_without() -> None:
    assert UNREACHABLE_STOPS_AT == 3
    assert active_note(0) is None
    assert active_note(1) == (
        "Its owner's sign-in could not be checked at the last load. It stops if that happens at three loads in a row."
    )
    assert active_note(2) == (
        "Its owner's sign-in could not be checked at the last two loads. It stops if the next is the third in a row."
    )
    for n in (1, 2):
        assert OWNER.id not in active_note(n)  # type: ignore[operator]
    assert STOPPED_WHY["unreachable"] == (
        "Its owner's sign-in could not be checked at three loads in a row. It is tried again at the next."
    )


# --- ADR-044's own named tests (its decision, 2026), as Amendment 2 builds them -----------------------------------


@pytest.mark.parametrize(("kind", "watch", "loads"), LOADS, ids=KINDS)
async def test_three_consecutive_unreachable_evaluations_escalate_status_to_stopped_while_status_detail_stays_unreachable(  # noqa: E501
    kind, watch, loads  # type: ignore[no-untyped-def]
) -> None:
    """ADR-044's first named test. Its "status_detail stays unreachable throughout" is Amendment 2's: the first two
    leave the status active with no reason (Amendment 1 keeps a reason only with stopped) and the count and its
    note say it; the third stops it, its reason `unreachable`."""
    store = _Store(watch())
    await loads(store, DOWN, DOWN)
    assert store.told == [] and store.in_a_row == 2
    await loads(store, DOWN)
    assert store.told == [("stopped", "unreachable")]


@pytest.mark.parametrize(("kind", "watch", "loads"), LOADS, ids=KINDS)
async def test_a_successful_evaluation_resets_the_consecutive_unreachable_count(kind, watch, loads) -> None:  # type: ignore[no-untyped-def]
    """ADR-044's second named test: two unreachable, one that acts as the owner, then two more unreachable leave it
    active (the count started again), where without the reset the fourth unreachable in all would stop it."""
    store = _Store(watch())
    await loads(store, DOWN, DOWN, None, DOWN, DOWN)
    assert store.told == [("active", None)] and store.in_a_row == 2
