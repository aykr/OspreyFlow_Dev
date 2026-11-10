"""*Promotions overdue* and Operations' ageing (`06_DECISIONS.md` ADR-145 decision 9, Amendment 4
decision 11, R7; L2.6), against the seam case's L3.4 fills (`promotion_ageing.WaitingPromotions`).

What a mistake would do, and the case that catches it (each shown red at its call site,
`process/lanes/admin/L2.6_RED_RECORD.md`):

- the alert a day late (`>` for `>=`) or a day early: `test_the_alert_fires_at_n_days_and_not_before`;
- raised again on every sweep: `test_the_alert_fires_once`;
- the alert telling what the promotion adds: `test_the_alert_names_the_load_not_its_contents`;
- an administrator not cleared to the dataset's marking alerted (its name above them):
  `test_no_recipient_below_the_datasets_marking`;
- a recipient who may not review it (the proposer, a disabled account, another unit's administrator,
  an Author without `review_promotions`): `test_the_alert_goes_to_reviewers_and_the_units_administrators`.

"Once" is the database's (`PromotionAgeingStore.raise_once`, `test_audit_section_store.py`); the
in-memory store here holds the same key, the promotion's id.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.api.promotion_ageing import (
    InMemoryAgeingStore,
    NoPromotionsYet,
    PendingPromotion,
    age_days,
    ageing_rules,
    recipients_of,
    sweep,
    waiting_row,
)

from schemas.admin import PersonAccount
from schemas.domain import Principal

SENT = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
P = PendingPromotion(items_marking=None, promotion_id="p1", load_id="load-7", dataset_id="ds-a",
                     dataset_name="Prison records", dataset_unit="unit-1", proposed_by="ana-1",
                     proposed_at=SENT)  # fmt: skip


class _Source:
    """The seam as L3.4 will fill it: the promotions waiting."""

    recorded = True

    def __init__(self, waiting: list[PendingPromotion]) -> None:
        self.waiting = waiting

    async def waiting_for_review(self, reader: Principal) -> list[PendingPromotion]:
        return list(self.waiting)

    async def all_waiting(self) -> list[PendingPromotion]:
        return list(self.waiting)


async def _to(p: PendingPromotion) -> list[str]:
    return ["eng-1"]


async def test_the_alert_fires_at_n_days_and_not_before() -> None:
    store = InMemoryAgeingStore()
    source = _Source([P])
    almost = SENT + timedelta(days=3) - timedelta(minutes=1)
    assert await sweep(source, store, _to, now=almost, after_days=3) == []
    fired = await sweep(source, store, _to, now=SENT + timedelta(days=3), after_days=3)
    assert [a.promotion_id for a in fired] == ["p1"]
    assert fired[0].recipients == ["eng-1"]


async def test_the_alert_fires_once() -> None:
    store = InMemoryAgeingStore()
    source = _Source([P])
    first = await sweep(source, store, _to, now=SENT + timedelta(days=3), after_days=3)
    again = await sweep(source, store, _to, now=SENT + timedelta(days=3, hours=1), after_days=3)
    later = await sweep(source, store, _to, now=SENT + timedelta(days=9), after_days=3)
    assert len(first) == 1 and again == [] and later == []
    assert len(store.raised) == 1


async def test_the_alert_names_the_load_not_its_contents() -> None:
    store = InMemoryAgeingStore()
    [alert] = await sweep(_Source([P]), store, _to, now=SENT + timedelta(days=4), after_days=3)
    assert alert.words == "Promotion load-7 into Prison records has waited 4 days for review."
    assert set(type(alert).model_fields) == {
        "promotion_id", "load_id", "dataset_id", "raised_at", "recipients", "words",
    }  # fmt: skip


async def test_no_promotion_waits_until_l3_4_records_them() -> None:
    none = NoPromotionsYet()
    assert none.recorded is False
    assert await sweep(none, InMemoryAgeingStore(), _to, now=SENT, after_days=0) == []


def _person(pid: str, roles: list[str], unit: str = "unit-1", *, enabled: bool = True,
            system: bool = False) -> PersonAccount:  # fmt: skip
    return PersonAccount(id=pid, username=pid, name=pid, enabled=enabled, roles=roles,
                         org_unit=unit, system_account=system)  # fmt: skip


def test_the_alert_goes_to_reviewers_and_the_units_administrators() -> None:
    people = [
        _person("ana-1", ["data_engineer"]),  # the proposer, though an Author who could review
        _person("eng-1", ["data_engineer"]),  # an Author holding review_promotions
        _person("eng-2", ["data_engineer"], enabled=False),  # disabled
        _person("ana-2", ["analyst"]),  # an Author without review_promotions
        _person("cus-1", ["role:rv"]),  # an Author whose custom role holds it
        _person("adm-1", ["osprey-admin"]),  # the unit's administrator
        _person("adm-9", ["osprey-admin"], unit="unit-9"),  # another unit's
        _person("eng-9", ["data_engineer"]),  # holds it but is no Author
        _person("svc", ["osprey-admin"], system=True),
    ]
    from schemas.rights import Right

    authors = ["ana-1", "eng-1", "eng-2", "ana-2", "cus-1"]
    got = recipients_of(P, authors, people, {"rv": [Right.REVIEW_PROMOTIONS]})
    assert got == ["adm-1", "cus-1", "eng-1"]


def test_no_recipient_below_the_items_marking_on_an_unmarked_dataset() -> None:
    """CARRIES row 46, at the raise: an item marked SECRET in a promotion into an unmarked dataset
    is alerted to no one below SECRET, Author or administrator. Red with the items' marking left
    out of `may_review`."""
    from dataclasses import replace

    from ontology.handling import HandlingScheme

    scheme = HandlingScheme(name="t", classification=["OFFICIAL", "SECRET"], handling_codes={},
                            action_codes={}, sanitisation_codes={})  # fmt: skip
    item = replace(P, items_marking="SECRET")
    people = [_account("rev-1", ["data_engineer"]), _account("adm-1", ["osprey-admin"]),
              _account("rev-low", ["data_engineer"], clearance="OFFICIAL"),
              _account("adm-low", ["osprey-admin"], clearance="OFFICIAL")]  # fmt: skip
    assert recipients_of(item, ["rev-1", "rev-low"], people, scheme=scheme) == ["adm-1", "rev-1"]


def test_age_and_overdue_as_operations_lists_them() -> None:
    assert age_days(SENT, SENT + timedelta(days=2, hours=23)) == 2
    row = waiting_row(P, SENT + timedelta(days=3), 3, {})
    assert (row.age_days, row.overdue) == (3, True)
    assert waiting_row(P, SENT + timedelta(days=2), 3, {}).overdue is False
    [rule] = ageing_rules(1)
    assert rule.after_days == 1 and rule.then.startswith("After 1 day it is flagged overdue")


def test_no_recipient_below_the_datasets_marking() -> None:
    from dataclasses import replace

    from ontology.handling import HandlingScheme

    marked = replace(P, dataset_marking="SECRET")
    scheme = HandlingScheme(name="test", classification=["OFFICIAL", "SECRET", "TOP SECRET"],
                            handling_codes={}, action_codes={}, sanitisation_codes={})  # fmt: skip
    people = [
        PersonAccount(id="adm-1", username="a", name="a", enabled=True, roles=["osprey-admin"],
                      org_unit="unit-1", clearance="OFFICIAL"),
        PersonAccount(id="adm-2", username="b", name="b", enabled=True, roles=["osprey-admin"],
                      org_unit="unit-1", clearance="TOP SECRET"),
        PersonAccount(id="adm-3", username="c", name="c", enabled=True, roles=["osprey-admin"],
                      org_unit="unit-1", clearance=None),
        PersonAccount(id="eng-1", username="d", name="d", enabled=True, roles=["data_engineer"],
                      org_unit="unit-1", clearance="SECRET"),
    ]  # fmt: skip
    assert recipients_of(marked, ["eng-1"], people, scheme=scheme) == ["adm-2", "eng-1"]
    # No marking: no clearance asked.
    assert recipients_of(P, ["eng-1"], people, scheme=scheme) == [
        "adm-1", "adm-2", "adm-3", "eng-1"]  # fmt: skip


async def test_a_tick_sweeps_the_source_it_is_handed_at_that_tick() -> None:
    """The source L3.4 sets on `app.state` after start-up is the one swept: `PromotionSweep` asks
    for it at every tick, and a source that records no promotions is not read at all."""
    import asyncio  # noqa: F401 - the module runs under pytest-asyncio's auto mode

    from services.api.promotion_ageing import InMemoryAgeingStore, NoPromotionsYet, PromotionSweep

    store = InMemoryAgeingStore()
    holder: dict[str, object] = {"source": NoPromotionsYet()}
    asked: list[str] = []

    async def recipients(p: PendingPromotion) -> list[str]:
        asked.append(p.promotion_id)
        return ["rev-1"]

    job = PromotionSweep(store, store, lambda: holder["source"], recipients)  # type: ignore[arg-type,return-value]
    now = SENT + timedelta(days=3)
    assert await job.tick(now) == []
    holder["source"] = _Source([P])
    [alert] = await job.tick(now)
    assert alert.recipients == ["rev-1"] and asked == ["p1"]
    # Item 12: an alert already raised is not raised again, and its recipients are not read again.
    assert await job.tick(now) == []
    assert asked == ["p1"]


async def test_a_failed_tick_raises_nothing_and_the_next_tries_again() -> None:
    """The identity provider down at one tick (its people unreadable): nothing is raised, nothing
    is raised to fewer people, and the next tick raises it."""
    import asyncio

    from services.api.promotion_ageing import InMemoryAgeingStore, PromotionSweep, run_every

    store = InMemoryAgeingStore()
    tries: list[int] = []

    async def recipients(p: PendingPromotion) -> list[str]:
        tries.append(1)
        if len(tries) == 1:
            raise OSError("the identity provider is unreachable")
        return ["rev-1", "adm-1"]

    job = PromotionSweep(store, store, lambda: _Source([P]), recipients)  # type: ignore[arg-type,return-value]
    task = asyncio.create_task(run_every(job, 0.05))
    try:
        for _ in range(100):
            if store.raised:
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
    assert len(tries) >= 2
    assert [a.recipients for a in store.raised.values()] == [["rev-1", "adm-1"]]


async def test_an_overdue_promotion_with_no_recipient_is_not_spent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Rule 2: an alert raised to nobody would be spent on no one and never raised again. It is
    left unraised, counted in `unreached` and logged once, and raised at the first tick that finds
    someone who may review it. Red with the sweep raising an alert with no recipients."""
    from services.api.promotion_ageing import PromotionSweep

    store = InMemoryAgeingStore()
    store.days = 3
    who: list[str] = []

    async def recipients(p: PendingPromotion) -> list[str]:
        return list(who)

    job = PromotionSweep(store, store, lambda: _Source([P]), recipients)
    with caplog.at_level("WARNING"):
        assert await job.tick(SENT + timedelta(days=3)) == []
        assert await job.tick(SENT + timedelta(days=3, minutes=1)) == []
    assert store.raised == {} and job.unreached == {"p1"}
    assert sum("p1" in r.getMessage() for r in caplog.records) == 1  # logged once, not each tick
    who.append("adm-1")
    [alert] = await job.tick(SENT + timedelta(days=4))
    assert alert.recipients == ["adm-1"] and job.unreached == set()


def _account(pid: str, roles: list[str], *, unit: str = "unit-1", clearance: str = "SECRET",
             enabled: bool = True) -> PersonAccount:  # fmt: skip
    return PersonAccount(id=pid, username=pid, name=pid, enabled=enabled, roles=roles,
                         org_unit=unit, clearance=clearance)  # fmt: skip


SCHEME_ORDER = ["OFFICIAL", "SECRET", "TOP SECRET"]


@pytest.mark.parametrize(
    ("change", "now"),
    [
        ("still a reviewer", _account("rev-1", ["data_engineer"])),
        ("disabled since", _account("rev-1", ["data_engineer"], enabled=False)),
        ("review_promotions lost", _account("rev-1", ["analyst"])),
        ("cleared below the marking since", _account("rev-1", ["data_engineer"],
                                                      clearance="OFFICIAL")),
        ("an administrator moved to another unit", _account("adm-1", ["osprey-admin"],
                                                            unit="unit-9")),
        ("an Author moved to another unit", _account("rev-1", ["data_engineer"], unit="unit-9")),
    ],
)  # fmt: skip
async def test_an_alert_is_read_only_while_its_reader_is_still_a_recipient(
    change: str, now: PersonAccount
) -> None:
    """`alerts_for` asks again who the alert is for, with the sweep's own predicate over the
    person as they stand now (`recipients_of`): still enabled, still an Author holding
    `review_promotions` or the dataset's unit's administrator, still cleared to its marking. Red
    with `alerts_for` matching on the stored recipient alone."""
    from dataclasses import replace

    from ontology.handling import HandlingScheme

    scheme = HandlingScheme(name="t", classification=SCHEME_ORDER, handling_codes={},
                            action_codes={}, sanitisation_codes={})  # fmt: skip
    marked = replace(P, dataset_marking="SECRET")
    then = [_account("rev-1", ["data_engineer"]), _account("adm-1", ["osprey-admin"])]
    store = InMemoryAgeingStore()
    people = list(then)

    async def recipients(p: PendingPromotion) -> list[str]:
        return recipients_of(p, ["rev-1"], people, scheme=scheme)

    [alert] = await sweep(_Source([marked]), store, recipients, now=SENT + timedelta(days=3),
                          after_days=3)  # fmt: skip
    assert alert.recipients == ["adm-1", "rev-1"]
    people[:] = [now if p.id == now.id else p for p in then]
    served = await store.alerts_for(now.id, recipients)
    assert [n.promotion_id for n in served] == (["p1"] if change == "still a reviewer" else [])
