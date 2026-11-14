"""ADR-148 Amendment 16 (the owner's ruling 1, option A): on Entra ID a run acts as its owner's
stored identity. Roles and the disabled flag are read live from Admin › People's store; clearance,
unit and codes are as at the owner's last sign-in, refused when older than 24 hours, and each
caller says so in those words, never "the identity provider could not be reached".

The store is a fake that refuses as `entra_people.EntraPeopleStore.owner` does (rule 15): keyed by
tenant and object id, `None` for a person not held, a failure raised, never answered as "nobody".
`test_entra_people_live.py` holds the real store's `owner` to the same.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from services.api.list_schedule import ListRefreshExecutor
from services.api.monitor_schedule import MonitorScheduleExecutor
from services.api.rule_schedule import RuleScheduleExecutor
from services.api.rule_schedule import _Refused as RuleRefused
from services.api.schedule_notices import notice_words, served_words
from services.api.scheduler import ScheduleExecutor
from services.api.scheduler import _Refused as ScheduleRefused

from principal_auth import (
    ACCESS_FRESH,
    ACCESS_OUT_OF_DATE_WORDS,
    NEXT_SLOT_WORDS,
    RUN_AGAIN_WORDS,
    OwnerNotHeld,
    OwnerRecordUnavailable,
    PrincipalAccessOutOfDate,
    PrincipalExchangeRefused,
    PrincipalExchangeUnavailable,
    PrincipalResolver,
    PrincipalRevoked,
    StoredOwner,
)
from schemas.monitoring import ListSchedule
from tests.services.api.test_auth_entra_claims import BY_EXTENSION, TENANT, _entra_config
from tests.services.api.test_rule_schedule import _Valkey

OWNER = "50000000-0000-4000-8000-000000000009"
#: The words a 24-hour refusal must never carry: it is not an outage (the orchestrator, 14 Nov).
UNREACHABLE = "could not be reached"


def _held(**overrides: Any) -> StoredOwner:
    fields: dict[str, Any] = {
        "roles": ("analyst", "source_author"),
        "disabled": False,
        "clearance": "OFFICIAL-SENSITIVE",
        "org_unit": "unit-2",
        "receivable_handling_codes": ("R",),
        "access_read_at": datetime.now(UTC) - timedelta(hours=2),
    }
    fields.update(overrides)
    return StoredOwner(**fields)


class FakeOwners:
    """`EntraPeopleStore.owner`'s refusals: another tenant's person is not held; a failure raises."""

    def __init__(self, rows: dict[str, StoredOwner] | None = None) -> None:
        self.rows = dict(rows or {})
        self.fail: Exception | None = None
        self.delay = 0.0
        self.calls: list[tuple[str, str]] = []

    async def person(self, *_: Any) -> Any:  # pragma: no cover - a session's read, not asked here
        raise AssertionError("a run as its owner records nobody")

    async def owner(self, tenant_id: str, oid: str) -> StoredOwner | None:
        self.calls.append((tenant_id, oid))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail is not None:
            raise self.fail
        return self.rows.get(oid) if tenant_id == TENANT else None


def _resolver(owners: FakeOwners) -> PrincipalResolver:
    return PrincipalResolver(
        _entra_config("http://127.0.0.1:9/keys"),
        claim_mapping=BY_EXTENSION,
        role_source=owners,
        role_lookup_timeout_seconds=0.2,
    )


# --- the resolver ---------------------------------------------------------------------------------


async def test_a_held_owner_signed_in_today_is_acted_as_with_their_stored_access() -> None:
    owners = FakeOwners({OWNER: _held()})
    principal = await _resolver(owners).resolve_for_owner_detailed(OWNER)
    assert (principal.id, principal.clearance, principal.org_unit) == (
        OWNER, "OFFICIAL-SENSITIVE", "unit-2"
    )  # fmt: skip
    assert principal.receivable_handling_codes == ["R"]
    assert principal.roles == ["analyst", "source_author"]
    assert owners.calls == [(TENANT, OWNER)]


async def test_roles_and_disabled_are_read_live_at_every_run() -> None:
    owners = FakeOwners({OWNER: _held()})
    resolver = _resolver(owners)
    assert (await resolver.resolve_for_owner_detailed(OWNER)).roles == ["analyst", "source_author"]
    owners.rows[OWNER] = _held(roles=("analyst",))
    assert (await resolver.resolve_for_owner_detailed(OWNER)).roles == ["analyst"]
    owners.rows[OWNER] = _held(disabled=True)
    with pytest.raises(PrincipalRevoked):
        await resolver.resolve_for_owner_detailed(OWNER)
    assert len(owners.calls) == 3  # never cached


async def test_access_older_than_24_hours_is_out_of_date_and_just_inside_is_not() -> None:
    now = datetime.now(UTC)
    inside = FakeOwners({OWNER: _held(access_read_at=now - ACCESS_FRESH + timedelta(minutes=1))})
    assert (await _resolver(inside).resolve_for_owner_detailed(OWNER)).id == OWNER
    stale = FakeOwners({OWNER: _held(access_read_at=now - ACCESS_FRESH - timedelta(minutes=1))})
    with pytest.raises(PrincipalAccessOutOfDate) as raised:
        await _resolver(stale).resolve_for_owner_detailed(OWNER)
    assert raised.value.owner_id == OWNER
    assert ACCESS_FRESH == timedelta(hours=24)


@pytest.mark.parametrize(
    "held",
    [
        _held(access_read_at=None, clearance=None, org_unit=None, receivable_handling_codes=()),
        _held(access_read_at=None),
        _held(clearance=None),
    ],
    ids=["added-by-object-id-never-signed-in", "no-time", "no-clearance"],
)
async def test_an_owner_whose_access_was_never_read_is_out_of_date(held: StoredOwner) -> None:
    with pytest.raises(PrincipalAccessOutOfDate):
        await _resolver(FakeOwners({OWNER: held})).resolve_for_owner_detailed(OWNER)


async def test_an_owner_not_held_is_refused_and_is_not_out_of_date() -> None:
    with pytest.raises(OwnerNotHeld) as raised:
        await _resolver(FakeOwners()).resolve_for_owner_detailed(OWNER)
    assert isinstance(raised.value, PrincipalExchangeRefused)
    assert not isinstance(raised.value, PrincipalRevoked)


async def test_a_store_of_another_tenant_is_the_store_unread_never_every_owner_not_held() -> None:
    """`EntraPeopleStore.owner` raises when asked for another tenant (as `person` does), so a store
    wired to the wrong tenant pauses nothing: the resolver says the store, never "not held"."""
    owners = FakeOwners({OWNER: _held()})
    owners.fail = RuntimeError("the people store is another tenant's")
    with pytest.raises(OwnerRecordUnavailable):
        await _resolver(owners).resolve_for_owner_detailed(OWNER)


async def test_a_disabled_owner_is_revoked_whatever_their_access() -> None:
    owners = FakeOwners({OWNER: _held(disabled=True, access_read_at=None)})
    with pytest.raises(PrincipalRevoked):
        await _resolver(owners).resolve_for_owner_detailed(OWNER)


@pytest.mark.parametrize("trouble", ["fails", "slow"])
async def test_the_store_unread_is_its_own_unavailable_never_out_of_date(trouble: str) -> None:
    owners = FakeOwners({OWNER: _held()})
    if trouble == "fails":
        owners.fail = ConnectionError("down")
    else:
        owners.delay = 1.0
    with pytest.raises(OwnerRecordUnavailable) as raised:
        await _resolver(owners).resolve_for_owner_detailed(OWNER)
    assert not isinstance(raised.value, PrincipalAccessOutOfDate)


async def test_the_collapsed_form_answers_none_for_an_out_of_date_owner() -> None:
    """At a load, hotlists, watches and anyone else's rules ask `resolve_for_owner`: `None`, not raised."""
    owners = FakeOwners({OWNER: _held(access_read_at=None)})
    assert await _resolver(owners).resolve_for_owner(OWNER) is None


# --- each caller's words --------------------------------------------------------------------------


def _schedules(resolve: Any) -> ScheduleExecutor:
    return ScheduleExecutor(recipes=None, runs=None, valkey=None, scheme=None,  # type: ignore[arg-type]
                            resolve_owner=resolve, check_case=None, run=None,  # type: ignore[arg-type]
                            notify=None)  # type: ignore[arg-type]  # fmt: skip


async def _raises(error: Exception) -> Any:
    raise error


async def test_a_schedule_s_owner_out_of_date_is_refused_in_the_24_hour_words_and_never_pauses() -> None:
    """A pipeline's schedule, its watched folder, *Run now* in Operations and `ospreyflow run` all
    judge their owner through `ScheduleExecutor._resolve`."""
    executor = _schedules(lambda _o: _raises(PrincipalAccessOutOfDate(OWNER, None)))
    with pytest.raises(ScheduleRefused) as refused:
        await executor._resolve(OWNER)
    words = str(refused.value)
    assert words == f"the schedule's owner, {OWNER}, {ACCESS_OUT_OF_DATE_WORDS}: {NEXT_SLOT_WORDS}"
    assert "24 hours" in words and "sign in" in words and UNREACHABLE not in words
    assert refused.value.about_the_owner is False
    assert refused.value.kind == "owner_out_of_date"


async def test_the_people_store_unread_is_said_as_the_store_never_as_the_identity_provider() -> None:
    executor = _schedules(lambda _o: _raises(OwnerRecordUnavailable("down")))
    with pytest.raises(ScheduleRefused) as refused:
        await executor._resolve(OWNER)
    assert "People" in str(refused.value) and UNREACHABLE not in str(refused.value)
    assert refused.value.about_the_owner is False


async def test_keycloak_s_unreachable_exchange_keeps_its_words() -> None:
    executor = _schedules(lambda _o: _raises(PrincipalExchangeUnavailable("timed out")))
    with pytest.raises(ScheduleRefused) as refused:
        await executor._resolve(OWNER)
    assert "the identity provider could not be reached" in str(refused.value)


async def test_an_owner_not_held_is_said_as_people_and_counted() -> None:
    executor = _schedules(lambda _o: _raises(OwnerNotHeld("gone")))
    with pytest.raises(ScheduleRefused) as refused:
        await executor._resolve(OWNER)
    assert str(refused.value) == f"the schedule's owner, {OWNER}, is not a person Admin › People holds"
    assert "identity provider" not in str(refused.value)
    assert refused.value.about_the_owner is True and refused.value.kind == "refused_rights"


@pytest.mark.parametrize("asked", ["run_now", "owner_for_external"])
async def test_run_now_and_ospreyflow_run_say_to_run_it_again_once_the_owner_signs_in(asked: str) -> None:
    """*Run now* (the 409's detail) and `ospreyflow run` (the trigger's refusal) are asked for now:
    nothing runs again by itself, so their words say what to do (the lane review's must 3)."""
    from services.api.scheduler import ScheduleRunRefused

    executor = _schedules(lambda _o: _raises(PrincipalAccessOutOfDate(OWNER, None)))
    recipe = SimpleNamespace(recipe_id="r-1", schedule_owner=OWNER, schedule_case="case-1",
                             datasets=["ds-1"], dataset_id="ds-1")  # fmt: skip
    with pytest.raises(ScheduleRunRefused) as refused:
        await getattr(executor, asked)(recipe)
    assert str(refused.value) == f"the schedule's owner, {OWNER}, {ACCESS_OUT_OF_DATE_WORDS}: {RUN_AGAIN_WORDS}"
    assert "runs at its next slot" not in str(refused.value)


@pytest.mark.parametrize(
    ("error", "words"),
    [
        (PrincipalAccessOutOfDate(OWNER, None), f"the schedule's owner, {OWNER}, {ACCESS_OUT_OF_DATE_WORDS}: {NEXT_SLOT_WORDS}"),
        (OwnerNotHeld("gone"), f"the schedule's owner, {OWNER}, is not a person Admin › People holds"),
        (OwnerRecordUnavailable("down"), "Admin › People's store could not be read to act as the schedule's owner"),
        (PrincipalRevoked("disabled"), f"the schedule's owner, {OWNER}, can no longer sign in"),
    ],
    ids=["out-of-date", "not-held", "store-unread", "revoked"],
)
async def test_a_deployment_wide_list_s_schedule_says_each_refusal_in_its_own_words(error: Exception, words: str) -> None:
    """`app._deployment_list_scheduler.may_run` (ADR-140 Amendment 13): the same words as a
    subscribed list's, from the one wording (the lane review's must 1)."""
    from services.api.app import _deployment_list_scheduler

    class _Resolver:
        async def resolve_for_owner_detailed(self, _o: str) -> Any:
            raise error

    application = SimpleNamespace(state=SimpleNamespace(principal_resolver=_Resolver(), valkey=None, list_store=None))
    assert await _deployment_list_scheduler(application).may_run(OWNER) == words  # type: ignore[arg-type]


def test_the_owner_s_notice_names_the_24_hours_and_is_served_as_written() -> None:
    words = notice_words("The scheduled run of Daily export due 06:00", "owner_out_of_date")
    assert "24 hours" in words and "sign in" in words and UNREACHABLE not in words
    assert served_words(words) == words


async def test_a_scheduled_rule_s_author_out_of_date_is_refused_in_the_24_hour_words() -> None:
    executor = RuleScheduleExecutor(rules=None, valkey=None,  # type: ignore[arg-type]
                                    resolve_owner=lambda _o: _raises(PrincipalAccessOutOfDate(OWNER, None)),
                                    check_case=None, judge=None)  # type: ignore[arg-type]  # fmt: skip
    rule = type("Rule", (), {"owner_id": OWNER})()
    with pytest.raises(RuleRefused) as refused:
        await executor._author(rule)  # type: ignore[arg-type]
    assert str(refused.value) == f"the rule's author, {OWNER}, {ACCESS_OUT_OF_DATE_WORDS}: {NEXT_SLOT_WORDS}"


class _Lists:
    """`ScheduledLists` as the scheduler asks it: one list due, its refusal recorded."""

    def __init__(self) -> None:
        self.updates: list[Any] = []

    async def mark_slot(self, _name: str, _slot: datetime) -> bool:
        return True

    async def record_update(self, update: Any) -> None:
        self.updates.append(update)


class _Claims(_Valkey):
    async def delete(self, key: str) -> int:
        return 1 if self.keys.pop(key, None) is not None else 0


async def test_a_list_refresh_s_owner_out_of_date_is_refused_in_the_24_hour_words() -> None:
    lists = _Lists()
    refreshed: list[str] = []

    async def refresh(name: str, *_: Any) -> Any:
        refreshed.append(name)

    executor = ListRefreshExecutor(lists=lists, valkey=_Claims(),  # type: ignore[arg-type]
                                   resolve_owner=lambda _o: _raises(PrincipalAccessOutOfDate(OWNER, None)),
                                   refresh=refresh, scheme=None)  # type: ignore[arg-type]  # fmt: skip
    now = datetime.now(UTC)
    scheduled = SimpleNamespace(list_name="synthetic-list", owner=OWNER, last_slot=None,
                                set_at=now - timedelta(days=2), schedule=ListSchedule(every="daily", hour=5))  # fmt: skip
    await executor._consider(scheduled, now)  # type: ignore[arg-type]
    assert refreshed == []
    (update,) = lists.updates
    assert update.words == (f"The scheduled refresh was refused: the schedule's owner, {OWNER}, "
                            f"{ACCESS_OUT_OF_DATE_WORDS}: {NEXT_SLOT_WORDS}. The list was left as it was.")  # fmt: skip


async def test_a_watch_s_owner_out_of_date_is_logged_in_the_24_hour_words_and_its_slot_kept(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _Monitors:
        recorded: list[Any] = []

        async def last_slot(self, _id: str) -> datetime | None:
            return None

        async def record_slot(self, *args: Any) -> None:
            self.recorded.append(args)

        async def set_status(self, *args: Any) -> None:
            raise AssertionError("an out-of-date owner never stops the watch")

    claims, monitors = _Claims(), _Monitors()
    executor = MonitorScheduleExecutor(monitors=monitors, valkey=claims,  # type: ignore[arg-type]
                                       resolve_owner=lambda _o: _raises(PrincipalAccessOutOfDate(OWNER, None)),
                                       match=None, reaches_dataset=None)  # type: ignore[arg-type]  # fmt: skip
    now = datetime.now(UTC)
    watch = SimpleNamespace(id="watch-1", owner_id=OWNER, every="daily", hour=5, weekday=None,
                            status="active", created_at=now - timedelta(days=2), dataset_id=None)  # fmt: skip
    with caplog.at_level(logging.WARNING):
        await executor._consider(watch, now)  # type: ignore[arg-type]
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert f"{ACCESS_OUT_OF_DATE_WORDS}: {NEXT_SLOT_WORDS}" in logged and UNREACHABLE not in logged
    assert monitors.recorded == [] and claims.keys == {}  # the slot is tried again, not spent


async def test_the_daily_kyc_check_s_deployer_out_of_date_is_said_in_the_24_hour_words() -> None:
    """The daily check for lapsing KYC documents runs each rule as its deployer: on Entra ID, a
    deployer not signed in within 24 hours is said so in the rule's audit, nothing judged."""
    from datetime import date

    from services.api.kyc_sweep import KYC_OUT_OF_DATE_NEXT, sweep

    from schemas.domain import Principal

    sweeper = Principal(id="kyc-sweeper", clearance="OFFICIAL", org_unit="unit-1")
    said: list[dict[str, Any]] = []

    class _Expiries:
        async def lapsed(self, **_: Any) -> list[Any]:
            return [SimpleNamespace(investigation_id="case-1", customer_id="c-1", document_id="d-1")]

    class _Rules:
        async def list_active_for_case(self, _case: str) -> list[Any]:
            return [SimpleNamespace(id="rule-1", owner_id=OWNER, dataset_id=None,
                                    params=SimpleNamespace(typology="document_verification"))]  # fmt: skip

    class _Audit:
        async def record(self, **fields: Any) -> None:
            said.append(fields)

    class _Unused:
        def __getattr__(self, name: str) -> Any:
            raise AssertionError(f"nothing is judged for a deployer out of date ({name})")

    async def never(_o: str) -> None:
        raise AssertionError("the detailed resolver is asked, not the collapsed one")

    report = await sweep(day=date(2026, 11, 16), expiries=_Expiries(), rules=_Rules(),  # type: ignore[arg-type]
                         graph=_Unused(), scheme=None, alert_store=_Unused(), audit=_Audit(),  # type: ignore[arg-type]
                         valkey=_Claims(), principal_for_owner=never, sweeper=sweeper,  # type: ignore[arg-type]
                         deployer_of=lambda _o: _raises(PrincipalAccessOutOfDate(OWNER, None)))  # fmt: skip
    (failure,) = report.failures
    assert failure.endswith(f"its deployer, {OWNER}, {ACCESS_OUT_OF_DATE_WORDS}: {KYC_OUT_OF_DATE_NEXT}")
    assert "runs again" not in failure  # the day is closed: nothing runs again (the lane review)
    (entry,) = said
    words = entry["resolved_query"]["words"]
    assert ACCESS_OUT_OF_DATE_WORDS in words and UNREACHABLE not in words


async def test_a_fault_resolving_the_kyc_deployer_is_logged_and_named_as_before(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """On Keycloak too, `deployer_of` changes only the refusals: a fault that is no refusal of the
    exchange still reaches the sweep's own handler, logged and named by type (the lane review, should 8)."""
    from datetime import date

    from services.api.kyc_sweep import sweep

    from schemas.domain import Principal

    class _Expiries:
        async def lapsed(self, **_: Any) -> list[Any]:
            return [SimpleNamespace(investigation_id="case-1", customer_id="c-1", document_id="d-1")]

    class _Rules:
        async def list_active_for_case(self, _case: str) -> list[Any]:
            return [SimpleNamespace(id="rule-1", owner_id=OWNER, dataset_id=None,
                                    params=SimpleNamespace(typology="document_verification"))]  # fmt: skip

    class _Audit:
        async def record(self, **_: Any) -> None:
            return None

    sweeper = Principal(id="kyc-sweeper", clearance="OFFICIAL", org_unit="unit-1")
    with caplog.at_level(logging.ERROR):
        report = await sweep(day=date(2026, 11, 16), expiries=_Expiries(), rules=_Rules(),  # type: ignore[arg-type]
                             graph=None, scheme=None, alert_store=None, audit=_Audit(),  # type: ignore[arg-type]
                             valkey=_Claims(), principal_for_owner=None, sweeper=sweeper,  # type: ignore[arg-type]
                             deployer_of=lambda _o: _raises(RuntimeError("a bug")))  # fmt: skip
    (failure,) = report.failures
    assert failure.endswith("it could not be run as its deployer (RuntimeError)")
    assert any("could not be scoped" in r.getMessage() for r in caplog.records)
