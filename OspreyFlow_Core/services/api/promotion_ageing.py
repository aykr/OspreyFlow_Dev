"""Operations' ageing and *Promotions overdue* (`06_DECISIONS.md` ADR-145 decision 9, O3;
Amendment 4 decision 11, R7; ADR-143 decisions 8 and 10).

**What ages, and when.** A promotion waiting for review ages from the moment it was sent for review;
at *Alert the reviewers and administrators after N days* (default 3, `alert_after_days`) it is
flagged overdue on Admin › Running › Operations and one alert is raised, **once**, to the dataset's
Authors holding `review_promotions` (never the proposer: a person is never the second person on
their own work) and to the administrators of the dataset's unit. The alert names the load and the
dataset, never what the promotion adds (rule 7).

**The seam for case's L3.4.** Promotions are not recorded yet. Everything here reads them through
one Protocol, `WaitingPromotions`, whose record is `PendingPromotion`; until L3.4 provides one, the
Conduit holds `NoPromotionsYet`, which says so (`recorded = False`) and lists none. L3.4 provides:

- `waiting_for_review(reader)`: the promotions waiting, **filtered in its own store** (rule 3) to
  those this reader may review: a promotion into a dataset of the reader's own unit whose Authors
  include the reader with `review_promotions`, or, for an administrator (`administer_system`), any
  into a dataset of the reader's own unit; and in either case only where the reader is cleared to
  the dataset's highest marking (Amendment 4 decision 11; `may_review`, the same predicate the
  alert's recipients are chosen by). Holding `operate_schedules`, which opens Operations, lists none
  on its own. `test_waiting_promotions_contract.py` is the contract L3.4's store must pass (rule 1);
- `all_waiting()`: every one waiting, for the sweep that raises the alerts (the system, not a
  reader; the alert is delivered only to its recipients, and its words name nothing a recipient's
  own read of the dataset would not).

**The sweep is admin's own** (`PromotionSweep`, run from the Conduit's lifespan each minute, or
every `OSPREY_PROMOTION_SWEEP_SECONDS`): it reads whatever source `app.state.waiting_promotions`
holds at each tick, so L3.4 has only to set it. A tick whose recipients cannot be read (the identity
provider down) raises nothing and the next tries again: an alert is never raised to fewer people
than decision 11 names. A promotion whose recipients are nobody is not raised (it would be spent
on no one): it is logged once and counted (`PromotionSweep.unreached`), and raised at the first tick
that finds a recipient (rule 2). L2.7's *Needs you* reads `alerts_for`, which carries no other
recipient and serves an alert only to someone who is still one of its recipients now.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import asyncpg

from ontology.errors import HandlingSchemeError
from ontology.handling import HandlingScheme
from schemas.admin import (
    AgeingRule,
    PersonAccount,
    PromotionOverdueAlert,
    PromotionOverdueNotice,
    WaitingPromotion,
)
from schemas.domain import Principal
from schemas.rights import Right, rights_for

from . import audit_section

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
    #: The highest marking among the items the promotion carries, as L3.4's record holds it: a
    #: recipient must be cleared to it too, since the Studio's list hides an item marked above its
    #: reader whatever the dataset's own marking (an unmarked dataset, or one lowered while the
    #: promotion waits; CARRIES row 46, L2.7). `None` when no item is marked.
    items_marking: str | None = None


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


def waiting_row(
    p: PendingPromotion, now: datetime, after_days: int, names: Mapping[str, str]
) -> WaitingPromotion:
    """A waiting promotion as Operations serves it: its proposer by name, never by id."""
    return WaitingPromotion(
        promotion_id=p.promotion_id,
        load_id=p.load_id,
        dataset_id=p.dataset_id,
        dataset_name=p.dataset_name,
        proposed_by_name=names.get(p.proposed_by, audit_section.NO_NAME),
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


def may_review(
    person_id: str,
    roles: Iterable[str],
    clearance: str | None,
    org_unit: str | None,
    p: PendingPromotion,
    authors: Iterable[str],
    custom: Mapping[str, Iterable[Right]] | None = None,
    scheme: HandlingScheme | None = None,
) -> bool:
    """Amendment 4 decision 11's people for one waiting promotion, all of the dataset's unit: one
    of the dataset's Authors (its home case's, `authors`) whose rights hold `review_promotions`, or
    an administrator (`administer_system`); and only one cleared to the dataset's highest marking
    and to the highest marking of the items it carries. The unit is asked of an Author too: the
    case recognises an Author grant only for a person of its own unit (`get_authorized`'s
    `owning_unit`), and a grant outlives a move. The Operations read lists a promotion to these
    people alone, and the alert goes to them."""
    if org_unit != p.dataset_unit:
        return False
    if not (
        cleared_to(clearance, p.dataset_marking, scheme)
        and cleared_to(clearance, p.items_marking, scheme)
    ):
        return False
    rights = rights_for(list(roles), custom)
    if person_id in set(authors) and Right.REVIEW_PROMOTIONS in rights:
        return True
    return Right.ADMINISTER_SYSTEM in rights


def recipients_of(
    p: PendingPromotion,
    authors: Sequence[str],
    people: Iterable[PersonAccount],
    custom: Mapping[str, Iterable[Right]] | None = None,
    scheme: HandlingScheme | None = None,
) -> list[str]:
    """Decision 11's recipients: those who `may_review` it, enabled accounts only, never a
    service account and never the proposer. The alert names the dataset, so it goes to nobody its
    marking is above."""
    return sorted(
        person.id for person in people
        if person.enabled and not person.system_account and person.id != p.proposed_by
        and may_review(person.id, person.roles, person.clearance, person.org_unit, p, authors,
                       custom, scheme)
    )  # fmt: skip


def cleared_to(clearance: str | None, marking: str | None, scheme: HandlingScheme | None) -> bool:
    """Whether a clearance reaches a marking, by the scheme's own dominance rule
    (`HandlingScheme.clears`). No marking asks nothing; no clearance, no scheme, or a marking the
    scheme does not define clears nothing."""
    if marking is None:
        return True
    if clearance is None or scheme is None:
        return False
    try:
        return scheme.clears(clearance, marking)
    except HandlingSchemeError:
        return False


#: Who an overdue promotion goes to, read now (the Conduit's `_promotion_recipients`).
Recipients = Callable[[PendingPromotion], Awaitable[list[str]]]


class OverdueAlerts(Protocol):
    async def raise_once(self, alert: PromotionOverdueAlert, promotion: PendingPromotion) -> bool:
        """True when this raised it; False when one was already raised for the promotion. The
        promotion is kept with it, so `alerts_for` can ask again who it is for now."""
        ...

    async def raised_of(self, promotion_ids: Sequence[str]) -> set[str]:
        """Of these promotions, those already alerted (so a tick reads no recipients for them)."""
        ...


async def sweep(
    source: WaitingPromotions,
    alerts: OverdueAlerts,
    recipients: Callable[[PendingPromotion], Awaitable[list[str]]],
    *,
    now: datetime,
    after_days: int,
    unreached: set[str] | None = None,
) -> list[PromotionOverdueAlert]:
    """Raises *Promotions overdue* for every promotion at or past N days not yet alerted, once each
    (the store's own uniqueness decides "once", so two sweeps at the same moment raise one). One
    whose recipients are nobody is not raised, so it is not spent: its id goes into `unreached`
    and a later sweep raises it once someone may review it."""
    raised: list[PromotionOverdueAlert] = []
    due = [p for p in await source.all_waiting() if is_overdue(p.proposed_at, now, after_days)]
    done = await alerts.raised_of([p.promotion_id for p in due]) if due else set()
    for p in due:
        if p.promotion_id in done:
            continue  # alerted already: its recipients are not read again
        to = await recipients(p)
        if not to:
            if unreached is not None:
                unreached.add(p.promotion_id)
            continue
        if unreached is not None:
            unreached.discard(p.promotion_id)
        alert = PromotionOverdueAlert(
            promotion_id=p.promotion_id,
            load_id=p.load_id,
            dataset_id=p.dataset_id,
            raised_at=now,
            recipients=to,
            words=overdue_words(p, now),
        )
        if await alerts.raise_once(alert, p):
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
        #: Overdue promotions no one may be alerted to yet (rule 2: counted, and each logged once).
        self.unreached: set[str] = set()

    async def tick(self, now: datetime) -> list[PromotionOverdueAlert]:
        source = self._source()
        if not source.recorded:
            return []
        before = set(self.unreached)
        raised = await sweep(
            source, self._store, self._recipients, now=now,
            after_days=await self._setting.alert_after_days(), unreached=self.unreached,
        )  # fmt: skip
        for promotion_id in sorted(self.unreached - before):
            log.warning(
                "promotion %s is overdue and no one may be alerted to it yet (%d such); it is "
                "raised once someone may review it", promotion_id, len(self.unreached),
            )  # fmt: skip
        return raised


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
    words TEXT NOT NULL,
    dataset_name TEXT NOT NULL,
    dataset_unit TEXT NOT NULL,
    dataset_marking TEXT,
    proposed_by TEXT NOT NULL,
    proposed_at TIMESTAMPTZ NOT NULL,
    items_marking TEXT
);
"""

#: L2.7: the items' marking, added to a table made before it. The catalogue is asked first, so a
#: start finding the column takes no lock (`ALTER TABLE … ADD COLUMN IF NOT EXISTS` takes an
#: exclusive one even when it changes nothing; CARRIES row 22).
_HAS_ITEMS_MARKING = (
    "SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() "
    "AND table_name = 'promotion_overdue_alerts' AND column_name = 'items_marking'"
)


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
            if await conn.fetchval(_HAS_ITEMS_MARKING) is None:
                await conn.execute(
                    "ALTER TABLE promotion_overdue_alerts "
                    "ADD COLUMN IF NOT EXISTS items_marking TEXT"
                )
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

    async def raise_once(self, alert: PromotionOverdueAlert, promotion: PendingPromotion) -> bool:
        import json

        async with self._pool.acquire() as conn:
            made = await conn.fetchval(
                "INSERT INTO promotion_overdue_alerts "
                "(promotion_id, load_id, dataset_id, raised_at, recipients, words, dataset_name, "
                "dataset_unit, dataset_marking, proposed_by, proposed_at, items_marking) "
                "VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10, $11, $12) "
                "ON CONFLICT (promotion_id) DO NOTHING RETURNING promotion_id",
                alert.promotion_id, alert.load_id, alert.dataset_id, alert.raised_at,
                json.dumps(alert.recipients), alert.words, promotion.dataset_name,
                promotion.dataset_unit, promotion.dataset_marking, promotion.proposed_by,
                promotion.proposed_at, promotion.items_marking,
            )  # fmt: skip
        return made is not None

    async def raised_of(self, promotion_ids: Sequence[str]) -> set[str]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT promotion_id FROM promotion_overdue_alerts "
                "WHERE promotion_id = ANY($1::text[])",
                list(promotion_ids),
            )
        return {r["promotion_id"] for r in rows}

    async def alerts_for(self, person: str, still: Recipients) -> list[PromotionOverdueNotice]:
        """The alerts raised to one person, newest first (L2.7's *Needs you* reads these), with no
        other recipient: who else was alerted is not that person's to read. Each is served only
        while the person is still one of its recipients, asked again now (`still`, the sweep's own
        `recipients`): still enabled, still an Author holding `review_promotions` or the dataset's
        unit's administrator, still cleared to its marking."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT promotion_id, load_id, dataset_id, raised_at, words, dataset_name, "
                "dataset_unit, dataset_marking, proposed_by, proposed_at, items_marking "
                "FROM promotion_overdue_alerts WHERE recipients ? $1 ORDER BY raised_at DESC",
                person,
            )
        return [
            PromotionOverdueNotice(**{k: r[k] for k in _NOTICE_FIELDS})
            for r in rows if person in await still(_kept_promotion(dict(r)))
        ]  # fmt: skip


_NOTICE_FIELDS = ("promotion_id", "load_id", "dataset_id", "raised_at", "words")


def _kept_promotion(row: Mapping[str, object]) -> PendingPromotion:
    return PendingPromotion(
        promotion_id=str(row["promotion_id"]), load_id=str(row["load_id"]),
        dataset_id=str(row["dataset_id"]), dataset_name=str(row["dataset_name"]),
        dataset_unit=str(row["dataset_unit"]), proposed_by=str(row["proposed_by"]),
        proposed_at=row["proposed_at"],  # type: ignore[arg-type]
        dataset_marking=row["dataset_marking"],  # type: ignore[arg-type]
        items_marking=row.get("items_marking"),  # type: ignore[arg-type]
    )  # fmt: skip


class InMemoryAgeingStore:
    """A store with no database (tests and a deployment without Postgres): the same "once", by the
    promotion's id, and the same default."""

    def __init__(self) -> None:
        self.days = DEFAULT_ALERT_AFTER_DAYS
        self.raised: dict[str, PromotionOverdueAlert] = {}
        self.kept: dict[str, PendingPromotion] = {}

    async def alert_after_days(self) -> int:
        return self.days

    async def set_alert_after_days(self, days: int) -> None:
        self.days = days

    async def raise_once(self, alert: PromotionOverdueAlert, promotion: PendingPromotion) -> bool:
        if alert.promotion_id in self.raised:
            return False
        self.raised[alert.promotion_id] = alert
        self.kept[alert.promotion_id] = promotion
        return True

    async def raised_of(self, promotion_ids: Sequence[str]) -> set[str]:
        return {i for i in promotion_ids if i in self.raised}

    async def alerts_for(self, person: str, still: Recipients) -> list[PromotionOverdueNotice]:
        return [
            PromotionOverdueNotice(**a.model_dump(include=set(_NOTICE_FIELDS)))
            for a in self.raised.values()
            if person in a.recipients and person in await still(self.kept[a.promotion_id])
        ]  # fmt: skip
