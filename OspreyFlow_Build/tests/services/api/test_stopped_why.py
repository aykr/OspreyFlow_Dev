"""ADR-044 Amendment 1: a stopped hotlist or watch says why. The reason is kept beside the binary status
when it is stopped (ADR-044's decision: `status_detail`), cleared when it is active, and served with
its words for the owner, never an id (rule 7). Every stop says one: a load that cannot act as the
owner (each refusal `resolve_for_owner_detailed` raises, its reason), a watch's pattern no longer
theirs, a watch's schedule finding its owner revoked.

Offline: the stores are fakes recording what `set_status` is told; the real stores' column and words
are live cases in `test_hotlists.py` and `test_monitors.py`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from services.api.evaluation import evaluate_hotlists_for_entry, evaluate_monitors_for_entry, match_monitor
from services.api.monitor_schedule import MonitorScheduleExecutor
from services.api.pattern_store import PatternNotFoundError
from services.api.watch_status import STOPPED_WHY, reason_of, stopped_why

from ontology.handling import load_uk_le_scheme
from principal_auth import (
    ACCESS_OUT_OF_DATE_WORDS,
    OwnerNotHeld,
    OwnerRecordUnavailable,
    PrincipalAccessOutOfDate,
    PrincipalExchangeRefused,
    PrincipalExchangeUnavailable,
    PrincipalRevoked,
)
from schemas.domain import Hotlist, Monitor, Principal, StoppedReason
from tests.services.api.test_owner_on_entra import _Claims

OWNER = Principal(id="owner-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
NOW = datetime(2026, 11, 14, 9, tzinfo=UTC)

#: Each refusal the detailed resolver raises, and the reason a stop records for it.
REFUSALS: list[tuple[Exception | None, StoppedReason]] = [
    (PrincipalRevoked("disabled"), "revoked"),
    (PrincipalAccessOutOfDate("owner-1", None), "out_of_date"),
    (OwnerNotHeld("gone"), "refused"),
    (PrincipalExchangeRefused("refused"), "refused"),
    (PrincipalExchangeUnavailable("down"), "unreachable"),
    (OwnerRecordUnavailable("store down"), "unreachable"),
    (None, "unresolved"),
]
IDS = ["revoked", "out-of-date", "not-held", "refused", "unreachable", "store-unread", "none"]


def _hotlist() -> Hotlist:
    return Hotlist(id="h-1", identifier="07700900123", owner_id=OWNER.id, review_date=date(2027, 1, 1),
                   created_at=NOW)  # fmt: skip


def _monitor() -> Monitor:
    return Monitor(id="m-1", pattern_id="p-1", owner_id=OWNER.id, created_at=NOW - timedelta(days=2),
                   every="daily", hour=5)  # fmt: skip


class _Watches:
    """`HotlistStore`/`MonitorStore` as the evaluator calls them: what `set_status` was told."""

    def __init__(self, active: list[Any]) -> None:
        self.active = active
        self.told: list[tuple[str, str, str | None]] = []

    async def list_all_active(self) -> list[Any]:
        return self.active

    async def set_status(self, watch_id: str, status: str, detail: str | None = None) -> None:
        self.told.append((watch_id, status, detail))

    async def last_slot(self, _id: str) -> None:
        return None

    async def record_slot(self, *_: Any) -> None:
        return None


def _resolving(outcome: Exception | None):  # type: ignore[no-untyped-def]
    async def resolve(_owner: str) -> Principal | None:
        if outcome is None:
            return None
        raise outcome

    return resolve


class _Nothing:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"nothing is read for a watch whose owner cannot be acted as ({name})")


class _Entry(_Nothing):
    """A load's change-stream entry, which a hotlist's evaluation reads the touched ids of first."""

    node_ids: list[str] = ["n-1"]


# --- the words -------------------------------------------------------------------------------------


def test_every_reason_has_its_words_and_none_names_an_id() -> None:
    from typing import get_args

    assert set(STOPPED_WHY) == set(get_args(StoppedReason))
    for reason, words in STOPPED_WHY.items():
        served = stopped_why(reason)  # what a row is served with: the words, whole, and no id
        assert served == words and served.startswith("Stopped: ") and OWNER.id not in served, reason
    assert ACCESS_OUT_OF_DATE_WORDS in STOPPED_WHY["out_of_date"]
    assert "could not be reached" not in " ".join(STOPPED_WHY.values())
    assert stopped_why(None) is None and stopped_why("a-reason-a-later-release-wrote") is None


@pytest.mark.parametrize(("refusal", "reason"), [r for r in REFUSALS if r[0] is not None],
                         ids=[i for i, r in zip(IDS, REFUSALS) if r[0] is not None])  # fmt: skip
def test_each_refusal_is_its_reason(refusal: Exception, reason: str) -> None:
    assert reason_of(refusal) == reason  # type: ignore[arg-type]


# --- every stop records why ------------------------------------------------------------------------


@pytest.mark.parametrize(("refusal", "reason"), REFUSALS, ids=IDS)
async def test_a_load_that_cannot_act_as_a_hotlist_s_owner_stops_it_with_the_reason(
    refusal: Exception | None, reason: str
) -> None:
    store = _Watches([_hotlist()])
    await evaluate_hotlists_for_entry(_Entry(), graph=_Nothing(), scheme=load_uk_le_scheme(), hotlist_store=store,  # type: ignore[arg-type]
                                      alert_store=_Nothing(), audit=_Nothing(), valkey=_Nothing(),  # type: ignore[arg-type]
                                      principal_for_owner=_resolving(refusal), policy="strict")  # type: ignore[arg-type]  # fmt: skip
    assert store.told == [("h-1", "stopped", reason)]


@pytest.mark.parametrize(("refusal", "reason"), REFUSALS, ids=IDS)
async def test_a_load_that_cannot_act_as_a_watch_s_owner_stops_it_with_the_reason(
    refusal: Exception | None, reason: str
) -> None:
    store = _Watches([_monitor()])
    await evaluate_monitors_for_entry(_Nothing(), graph=_Nothing(), monitor_store=store, pattern_store=_Nothing(),  # type: ignore[arg-type]
                                      alert_store=_Nothing(), audit=_Nothing(), valkey=_Nothing(),  # type: ignore[arg-type]
                                      principal_for_owner=_resolving(refusal))  # fmt: skip
    assert store.told == [("m-1", "stopped", reason)]


async def test_a_watch_whose_pattern_is_no_longer_its_owner_s_stops_with_that_reason() -> None:
    class _Patterns:
        async def get_authorized(self, *_: Any) -> Any:
            raise PatternNotFoundError("p-1")

    store = _Watches([])
    await match_monitor(_monitor(), OWNER, graph=_Nothing(), monitor_store=store, pattern_store=_Patterns(),  # type: ignore[arg-type]
                        alert_store=_Nothing(), audit=_Nothing(), valkey=_Nothing(), investigation_id=None)  # type: ignore[arg-type]  # fmt: skip
    assert store.told == [("m-1", "stopped", "pattern_gone")]


async def test_a_watch_s_schedule_stops_it_as_revoked_when_its_owner_can_no_longer_sign_in() -> None:
    store = _Watches([])
    executor = MonitorScheduleExecutor(monitors=store, valkey=_Claims(),  # type: ignore[arg-type]
                                       resolve_owner=_resolving(PrincipalRevoked("disabled")),
                                       match=None, reaches_dataset=None)  # type: ignore[arg-type]  # fmt: skip
    watch = _monitor()
    await executor._consider(watch, NOW)
    assert store.told == [("m-1", "stopped", "revoked")]


async def test_a_load_s_watches_are_given_the_resolver_that_says_why() -> None:
    """`recipe_run` evaluates a load's hotlists and watches with `_watch_owner_resolver`: the loader
    at once, anyone else through `resolve_for_owner_detailed`, whose refusal reaches the evaluator."""
    from services.api.recipe_run import _watch_owner_resolver

    class _Resolver:
        async def resolve_for_owner_detailed(self, _o: str) -> Principal:
            raise PrincipalAccessOutOfDate("owner-2", None)

        async def resolve_for_owner(self, _o: str) -> None:
            raise AssertionError("the collapsed form tells the evaluator nothing")

    resolve = _watch_owner_resolver(OWNER, _Resolver())  # type: ignore[arg-type]
    assert await resolve(OWNER.id) is OWNER
    with pytest.raises(PrincipalAccessOutOfDate):
        await resolve("owner-2")


def test_the_user_guide_gives_each_reason_in_the_conduit_s_words() -> None:
    """User guide §7.5 quotes each reason as `STOPPED_WHY` words it (rule 12): a reason reworded in the
    code and not the guide, or added without its sentence, fails here."""
    import re
    from pathlib import Path

    guide = (Path(__file__).resolve().parents[4] / "OspreyFlow_Core/docs/user-guide.md").read_text(encoding="utf-8")
    start = guide.index("### 7.5")
    section = re.sub(r"\s+", " ", guide[start : guide.index("\n### ", start + 1)])
    quoted = {
        "revoked": "its owner can no longer sign in to OspreyFlow",
        "refused": "the identity provider refused to act as its owner",
        "unreachable": "its owner's sign-in could not be checked at the last load",
        "pattern_gone": "its saved pattern is no longer its owner's",
    }
    for reason, words in quoted.items():
        assert words in STOPPED_WHY[reason] and words in section, reason
    assert "has not signed in within the last 24 hours" in section
