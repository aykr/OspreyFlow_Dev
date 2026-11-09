"""Operations' ageing and *Promotions overdue* (`06_DECISIONS.md` ADR-145 decision 9, O3;
Amendment 4
decision 11, R7; ADR-143 decisions 8 and 10).

**What ages, and when.** A promotion waiting for review ages from the moment it was sent for review;
at *Alert the reviewers and administrators after N days* (default 3, `alert_after_days`) it is
flagged overdue on Admin › Running › Operations and one alert is raised, **once**, to the dataset's
Authors holding `review_promotions` (never the proposer: a person is never the second person on
their
own work) and to the administrators of the dataset's unit. The alert names the load and the dataset,
never what the promotion adds (rule 7).

**The seam for case's L3.4.** Promotions are not recorded yet. Everything here reads them through
one Protocol, `WaitingPromotions`, whose record is `PendingPromotion`; until L3.4 provides one, the
Conduit holds `NoPromotionsYet`, which says so (`recorded = False`) and lists none. L3.4 provides:

- `waiting_for_review(reader)`: the promotions waiting, **filtered in its own store by the reader's
  unit and clearance** (rule 3), for the Operations read;
- `all_waiting()`: every one waiting, for the sweep that raises the alerts (the system, not a
  reader; the alert is delivered only to its recipients, and its words name nothing a recipient's
  own read of the dataset would not).

**The sweep is admin's own** (`PromotionSweep`, run from the Conduit's lifespan each minute, or
every `OSPREY_PROMOTION_SWEEP_SECONDS`): it reads whatever source `app.state.waiting_promotions`
holds at each tick, so L3.4 has only to set it. A tick whose recipients cannot be read (the identity
provider down) raises nothing and the next tries again: an alert is never raised to fewer people
than decision 11 names. L2.7's *Needs you* reads `alerts_for`, which carries no other recipient.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import asyncpg

from schemas.admin import (
    AgeingRule,
    PersonAccount,
    PromotionOverdueAlert,
    PromotionOverdueNotice,
    WaitingPromotion,
)
from schemas.domain import Principal
from schemas.rights import Right, rights_for

DEFAULT_ALERT_AFTER_DAYS = 3
#: How often the sweep runs, unless `OSPREY_PROMOTION_SWEEP_SECONDS` says otherwise.
SWEEP_SECONDS = 60.0

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PendingPromotion:
    """A promotion waiting for review, as L3.4's record must at least hold it."""

    promotion_id: str
    load_id: str
    dataset_id: str
    dataset_name: str
    dataset_unit: str
    proposed_by: str
    proposed_at: datetime
    #: The dataset's highest marking (ADR-145 decision 8), when it has one: a recipient must be
    #: cleared to it, since the alert names the dataset.
    dataset_marking: str | None = None


class WaitingPromotions(Protocol):
    """The one seam case's L3.4 fills (the module docstring says what each part does)."""

    recorded: bool

    async def waiting_for_review(self, reader: Principal) -> list[PendingPromotion]: ...

    async def all_waiting(self) -> list[PendingPromotion]: ...


class NoPromotionsYet:
    """Until L3.4: no promotion is recorded, so none waits and none ages."""

    recorded = False

    async def waiting_for_review(self, reader: Principal) -> list[PendingPromotion]:
        return []

    async def all_waiting(self) -> list[PendingPromotion]:
        return []


def age_days(proposed_at: datetime, now: datetime) -> int:
    """Whole days waited: a promotion sent at 09:00 is one day old at 09:00 the next day."""
    return max(0, (now - proposed_at) // timedelta(days=1))


def is_overdue(proposed_at: datetime, now: datetime, after_days: int) -> bool:
    return age_days(proposed_at, now) >= after_days


def ageing_rules(after_days: int) -> list[AgeingRule]:
    """What ages in Operations, and when (O3), in words the screen shows as they are."""
    return [
        AgeingRule(
            what="A promotion waiting for review",
            after_days=after_days,
            then=(
                f"After {after_days} {'day' if after_days == 1 else 'days'} it is flagged overdue, "
                "and the dataset's Authors who may review it and the unit's administrators are "
                "alerted once. The alert names the load and the dataset, not what it adds."
            ),
        )
    ]


#: Said for a proposer the identity provider gives no name: never the account's id (rule 7).
NO_NAME = "An account with no name on record"


def waiting_row(
    p: PendingPromotion, now: datetime, after_days: int, names: Mapping[str, str]
) -> WaitingPromotion:
    """A waiting promotion as Operations serves it: its proposer by name, never by id."""
    return WaitingPromotion(
        promotion_id=p.promotion_id,
        load_id=p.load_id,
        dataset_id=p.dataset_id,
        dataset_name=p.dataset_name,
        proposed_by_name=names.get(p.proposed_by, NO_NAME),
        proposed_at=p.proposed_at,
        age_days=age_days(p.proposed_at, now),
        overdue=is_overdue(p.proposed_at, now, after_days),
    )


def overdue_words(p: PendingPromotion, now: datetime) -> str:
    """The alert's words: the load and the dataset, never what the promotion adds (rule 7)."""
    days = age_days(p.proposed_at, now)
    return (
        f"Promotion {p.load_id} into {p.dataset_name} has waited {days} "
        f"{'day' if days == 1 else 'days'} for review."
    )


def recipients_of(
    p: PendingPromotion,
    authors: Sequence[str],
    people: Iterable[PersonAccount],
    custom: Mapping[str, Iterable[Right]] | None = None,
    classification: Sequence[str] = (),
) -> list[str]:
    """Decision 11's recipients: the dataset's Authors (its home case's, `authors`) whose rights
    hold `review_promotions`, and the administrators (`administer_system`) of the dataset's unit;
    only enabled accounts, never a service account, never the proposer, and, where the dataset
    has a highest marking, only those cleared to it (`classification`, lowest first, the
    deployment's scheme): the alert names the dataset, so it goes to nobody its name is above."""
    held = set(authors)
    out: set[str] = set()
    for person in people:
        if not person.enabled or person.system_account or person.id == p.proposed_by:
            continue
        if not cleared_to(person.clearance, p.dataset_marking, classification):
            continue
        rights = rights_for(person.roles, custom)
        if person.id in held and Right.REVIEW_PROMOTIONS in rights:
            out.add(person.id)
        elif Right.ADMINISTER_SYSTEM in rights and person.org_unit == p.dataset_unit:
            out.add(person.id)
    return sorted(out)


def cleared_to(clearance: str | None, marking: str | None, classification: Sequence[str]) -> bool:
    """Whether a clearance reaches a marking in the scheme; an unknown one, or none, never does."""
    if marking is None:
        return True
    if clearance not in classification or marking not in classification:
        return False
    return classification.index(clearance) >= classification.index(marking)


class OverdueAlerts(Protocol):
    async def raise_once(self, alert: PromotionOverdueAlert) -> bool:
        """True when this raised it; False when one was already raised for the promotion."""
        ...


async def sweep(
    source: WaitingPromotions,
    alerts: OverdueAlerts,
    recipients: Callable[[PendingPromotion], Awaitable[list[str]]],
    *,
    now: datetime,
    after_days: int,
) -> list[PromotionOverdueAlert]:
    """Raises *Promotions overdue* for every promotion at or past N days not yet alerted, once each
    (the store's own uniqueness decides "once", so two sweeps at the same moment raise one)."""
    raised: list[PromotionOverdueAlert] = []
    for p in await source.all_waiting():
        if not is_overdue(p.proposed_at, now, after_days):
            continue
        alert = PromotionOverdueAlert(
            promotion_id=p.promotion_id,
            load_id=p.load_id,
            dataset_id=p.dataset_id,
            raised_at=now,
            recipients=await recipients(p),
            words=overdue_words(p, now),
        )
        if await alerts.raise_once(alert):
            raised.append(alert)
    return raised


class AgeingSetting(Protocol):
    async def alert_after_days(self) -> int: ...


class PromotionSweep:
    """Admin's scheduled job: raises *Promotions overdue* once each, at N days. `source` is asked
    at every tick, so the source L3.4 sets on `app.state` is the one swept."""

    def __init__(
        self,
        store: OverdueAlerts,
        setting: AgeingSetting,
        source: Callable[[], WaitingPromotions],
        recipients: Callable[[PendingPromotion], Awaitable[list[str]]],
    ) -> None:
        self._store = store
        self._setting = setting
        self._source = source
        self._recipients = recipients

    async def tick(self, now: datetime) -> list[PromotionOverdueAlert]:
        source = self._source()
        if not source.recorded:
            return []
        return await sweep(
            source, self._store, self._recipients, now=now,
            after_days=await self._setting.alert_after_days(),
        )  # fmt: skip


async def run_every(job: PromotionSweep, seconds: float) -> None:
    """The Conduit's lifespan task: a tick every `seconds`. A failed tick is logged and raises
    nothing; the next tries again."""
    while True:
        await asyncio.sleep(seconds)
        try:
            await job.tick(datetime.now(UTC))
        except Exception:  # noqa: BLE001 - logged; the next tick tries again
            log.exception("the promotions overdue sweep failed; trying again at the next tick")


_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS operations_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS promotion_overdue_alerts (
    promotion_id TEXT PRIMARY KEY,
    load_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    raised_at TIMESTAMPTZ NOT NULL,
    recipients JSONB NOT NULL,
    words TEXT NOT NULL
);
"""


class PromotionAgeingStore:
    """Operations' setting and the alerts raised, in the Conduit's database. `raise_once` is an
    `INSERT … ON CONFLICT DO NOTHING` on the promotion's id: the database, not the caller, makes it
    once."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PromotionAgeingStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=3)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def alert_after_days(self) -> int:
        async with self._pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT value FROM operations_settings WHERE key = 'promotion_alert_after_days'"
            )
        return int(value) if value is not None else DEFAULT_ALERT_AFTER_DAYS

    async def set_alert_after_days(self, days: int) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO operations_settings (key, value) "
                "VALUES ('promotion_alert_after_days', $1::jsonb) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                str(int(days)),
            )

    async def raise_once(self, alert: PromotionOverdueAlert) -> bool:
        import json

        async with self._pool.acquire() as conn:
            made = await conn.fetchval(
                "INSERT INTO promotion_overdue_alerts "
                "(promotion_id, load_id, dataset_id, raised_at, recipients, words) "
                "VALUES ($1, $2, $3, $4, $5::jsonb, $6) "
                "ON CONFLICT (promotion_id) DO NOTHING RETURNING promotion_id",
                alert.promotion_id, alert.load_id, alert.dataset_id, alert.raised_at,
                json.dumps(alert.recipients), alert.words,
            )  # fmt: skip
        return made is not None

    async def alerts_for(self, person: str) -> list[PromotionOverdueNotice]:
        """The alerts raised to one person, newest first (L2.7's *Needs you* reads these), with no
        other recipient: who else was alerted is not that person's to read."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT promotion_id, load_id, dataset_id, raised_at, words "
                "FROM promotion_overdue_alerts WHERE recipients ? $1 ORDER BY raised_at DESC",
                person,
            )
        return [PromotionOverdueNotice(**dict(r)) for r in rows]


class InMemoryAgeingStore:
    """A store with no database (tests and a deployment without Postgres): the same "once", by the
    promotion's id, and the same default."""

    def __init__(self) -> None:
        self.days = DEFAULT_ALERT_AFTER_DAYS
        self.raised: dict[str, PromotionOverdueAlert] = {}

    async def alert_after_days(self) -> int:
        return self.days

    async def set_alert_after_days(self, days: int) -> None:
        self.days = days

    async def raise_once(self, alert: PromotionOverdueAlert) -> bool:
        if alert.promotion_id in self.raised:
            return False
        self.raised[alert.promotion_id] = alert
        return True

    async def alerts_for(self, person: str) -> list[PromotionOverdueNotice]:
        return [
            PromotionOverdueNotice(**a.model_dump(exclude={"recipients"}))
            for a in self.raised.values() if person in a.recipients
        ]  # fmt: skip
