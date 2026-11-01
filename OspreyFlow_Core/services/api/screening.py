"""Screening lists and name screening (`06_DECISIONS.md` ADR-109 phase F, the KYC addendum's
Component 6).

**A screening list is not a hotlist, and not graph content.** A hotlist (ADR-038) is one owner's one
exact identifier; a screening list is a licensed register — sanctions, politically exposed persons,
adverse media — of names matched fuzzily, deployment-wide. It is held here, outside the graph, so
that only an entry a customer actually matches ever enters a case (data minimisation: a real list,
admitted locally under the owner's exceptions file, is never copied wholesale into the graph).

**Matching reuses the resolution engine's own comparison.** Names are compared with DuckDB's
`jaro_winkler_similarity` — the function `ontology/resolution_functions.py` maps
`jaro_winkler(...)` to for Splink — over each name's tokens in sorted order, so "PETROV, Elena" and
"Elena Petrov" agree. A date of birth on both sides that disagrees rules the pair out. A hit is a
suggestion, scored, for a person to judge (rule 5): it is written `inferred`, never asserted.

**Rule 9.** Everything committed is synthetic
(`packages/demo_fixtures/screening_list_synthetic.yaml`, `packages/demo_fixtures/screening_lists/`).
`scripts/load_screening_list.py` and a subscription's refresh (`screening_refresh.py`) refuse a list
that is not synthetic unless the device's local `real_data_exceptions.yaml` names it — OpenSanctions
(CC-BY-NC 4.0, spec 00 §7) included.

**A list as a managed source (ADR-133 decision 4, stage (c)).** A subscribed list keeps its
version, its number of entries, when it last changed and why its last attempt failed
(`screening_lists`), and each refresh is recorded (`screening_list_updates`). `apply_update`
replaces a list's entries whole in one transaction and says which entries it added, changed and
removed — the changed entries are all a re-screening reads.

**A refresh's re-screening is counted per unit (the owner's answer of 1 November 2026; rules 3 and
7).** Each screening rule re-screens as its own deployer, so what it re-screened, raised and failed
belongs to the deployer's organisational unit (`screening_list_update_units`). An administrator
reads a refresh through `updates(org_unit=...)` and `update_for(...)`: the query joins their own
unit's row and nothing else, so another unit's customers, alerts and rule names never leave the
store. The whole-deployment totals stay on `screening_list_updates` for the operator's command and
the audit; no route selects them.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Literal

import asyncpg
import duckdb

from schemas.monitoring import ListSchedule
from schemas.screening import (
    ScreeningListStatus,
    ScreeningListUpdate,
    ScreeningSubscriptionInput,
)

Listing = Literal["sanction", "pep", "adverse_media"]

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS screening_entries (
    id TEXT PRIMARY KEY,
    list_name TEXT NOT NULL,
    listing TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    date_of_birth DATE,
    country TEXT,
    synthetic BOOLEAN NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS screening_entries_type_idx ON screening_entries (entity_type);
ALTER TABLE screening_entries ADD COLUMN IF NOT EXISTS aliases TEXT[] NOT NULL DEFAULT '{}';
CREATE TABLE IF NOT EXISTS screening_lists (
    list_name TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    location TEXT NOT NULL,
    dataset TEXT,
    use_for TEXT NOT NULL,
    version TEXT,
    entry_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ,
    attempted_at TIMESTAMPTZ,
    failure TEXT,
    synthetic BOOLEAN NOT NULL DEFAULT FALSE,
    subscribed_by TEXT NOT NULL,
    subscribed_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS screening_list_updates (
    id TEXT PRIMARY KEY,
    list_name TEXT NOT NULL,
    at TIMESTAMPTZ NOT NULL,
    outcome TEXT NOT NULL,
    version TEXT,
    previous_version TEXT,
    added INTEGER NOT NULL DEFAULT 0,
    changed INTEGER NOT NULL DEFAULT 0,
    removed INTEGER NOT NULL DEFAULT 0,
    rescreened INTEGER NOT NULL DEFAULT 0,
    alerts INTEGER NOT NULL DEFAULT 0,
    words TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS screening_list_updates_at_idx ON screening_list_updates (at DESC);
-- ADR-133 stage (d): a list's refresh schedule (Amendment 3, item 4), whom it runs as, since when,
-- and the last slot it ran; and how each refresh was started.
ALTER TABLE screening_lists ADD COLUMN IF NOT EXISTS schedule_every TEXT;
ALTER TABLE screening_lists ADD COLUMN IF NOT EXISTS schedule_hour INTEGER;
ALTER TABLE screening_lists ADD COLUMN IF NOT EXISTS schedule_weekday INTEGER;
ALTER TABLE screening_lists ADD COLUMN IF NOT EXISTS schedule_owner TEXT;
ALTER TABLE screening_lists ADD COLUMN IF NOT EXISTS schedule_set_at TIMESTAMPTZ;
ALTER TABLE screening_lists ADD COLUMN IF NOT EXISTS schedule_last_slot TIMESTAMPTZ;
ALTER TABLE screening_list_updates ADD COLUMN IF NOT EXISTS trigger TEXT NOT NULL DEFAULT 'manual';
-- The owner's answer of 1 November 2026: a refresh's re-screening counted per unit, and the words
-- about the list alone (version, entries changed), which every unit may read.
ALTER TABLE screening_list_updates ADD COLUMN IF NOT EXISTS list_words TEXT;
CREATE TABLE IF NOT EXISTS screening_list_update_units (
    update_id TEXT NOT NULL,
    org_unit TEXT NOT NULL,
    rescreened INTEGER NOT NULL DEFAULT 0,
    alerts INTEGER NOT NULL DEFAULT 0,
    failures TEXT[] NOT NULL DEFAULT '{}',
    PRIMARY KEY (update_id, org_unit)
);
"""


@dataclass
class UnitCounts:
    """What one unit's screening rules did in one refresh: customers re-screened, alerts raised,
    and each rule that could not re-screen, in words."""

    rescreened: int = 0
    alerts: int = 0
    failures: list[str] = field(default_factory=list)


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def unit_words(list_words: str, screened_entries: int, counts: UnitCounts) -> str:
    """An updated refresh in words for one unit: the list's own words, then that unit's counts and
    failures alone."""
    words = (
        f"{list_words} {_plural(counts.rescreened, 'customer')} re-screened against "
        f"{_plural(screened_entries, 'changed entry', 'changed entries')}; "
        f"{_plural(counts.alerts, 'alert')} raised."
    )
    if counts.failures:
        words += " " + " ".join(f"{f[0].upper()}{f[1:]}." for f in counts.failures)
    return words


@dataclass(frozen=True)
class ScheduledList:
    """A list with a refresh schedule, as the scheduler reads it."""

    list_name: str
    schedule: ListSchedule
    owner: str
    set_at: datetime
    last_slot: datetime | None


@dataclass(frozen=True)
class ScreeningEntry:
    id: str
    list_name: str
    listing: Listing
    entity_type: Literal["Person", "Organisation"]
    name: str
    date_of_birth: date | None = None
    country: str | None = None
    synthetic: bool = True
    #: Every other name the list gives (ADR-133 stage (c)); a name matches on any of them.
    aliases: tuple[str, ...] = ()

    def fingerprint(self) -> tuple[object, ...]:
        """What makes two versions of one entry the same entry: everything screening reads."""
        return (self.listing, self.entity_type, self.name, tuple(sorted(self.aliases)),
                self.date_of_birth, self.country)  # fmt: skip


@dataclass(frozen=True)
class ListDiff:
    """What one update of a list changed, entry by entry (by the publisher's own reference)."""

    list_name: str
    previous_version: str | None
    version: str
    added: tuple[ScreeningEntry, ...]
    changed: tuple[ScreeningEntry, ...]
    removed: tuple[str, ...]
    unchanged: int

    @property
    def to_screen(self) -> tuple[ScreeningEntry, ...]:
        """The entries a customer could newly match: added or changed. A removed entry raises
        nothing new, and an unchanged one was screened when it arrived."""
        return (*self.added, *self.changed)


def diff_entries(
    list_name: str,
    before: Sequence[ScreeningEntry],
    after: Sequence[ScreeningEntry],
    *,
    previous_version: str | None,
    version: str,
) -> ListDiff:
    old = {e.id: e for e in before}
    new = {e.id: e for e in after}

    def same(a: ScreeningEntry, b: ScreeningEntry) -> bool:
        return a.fingerprint() == b.fingerprint()

    return ListDiff(
        list_name=list_name,
        previous_version=previous_version,
        version=version,
        added=tuple(e for i, e in new.items() if i not in old),
        changed=tuple(e for i, e in new.items() if i in old and not same(old[i], e)),
        removed=tuple(sorted(i for i in old if i not in new)),
        unchanged=sum(1 for i, e in new.items() if i in old and same(old[i], e)),
    )


@dataclass(frozen=True)
class ScreeningHit:
    entry: ScreeningEntry
    score: float


def normalised(name: str) -> str:
    """Case, accents and punctuation folded away, tokens sorted: the form two spellings of one name
    share."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    tokens = re.findall(r"[a-z0-9]+", folded.casefold())
    return " ".join(sorted(tokens))


def screen(
    name: str,
    date_of_birth: date | None,
    entries: Sequence[ScreeningEntry],
    *,
    min_score: float,
) -> list[ScreeningHit]:
    """Every entry the name matches at `min_score` or above, best first; an entry whose date of
    birth disagrees with a known one is not a match, however close the name."""
    probe = normalised(name)
    if not probe or not entries:
        return []
    candidates = [
        e
        for e in entries
        if not (date_of_birth and e.date_of_birth and e.date_of_birth != date_of_birth)
    ]
    if not candidates:
        return []
    # Each entry's names — its own and its aliases — scored alike; the entry scores its best.
    names = [(i, normalised(n)) for i, e in enumerate(candidates) for n in (e.name, *e.aliases)]
    con = duckdb.connect()
    try:
        scores = con.execute(
            "SELECT jaro_winkler_similarity(?, unnest(?::VARCHAR[]))",
            [probe, [n for _, n in names]],
        ).fetchall()
    finally:
        con.close()
    best: dict[int, float] = {}
    for (index, _), row in zip(names, scores, strict=True):
        best[index] = max(best.get(index, 0.0), float(row[0]))
    hits = [
        ScreeningHit(entry=candidates[i], score=round(score, 4))
        for i, score in best.items()
        if score >= min_score
    ]
    return sorted(hits, key=lambda h: (-h.score, h.entry.id))


class ScreeningListStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> ScreeningListStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def replace_list(self, list_name: str, entries: Sequence[ScreeningEntry]) -> int:
        """The named list, replaced whole in one transaction — a reload never leaves half of an
        old list beside half of a new one."""
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("DELETE FROM screening_entries WHERE list_name = $1", list_name)
            await self._insert(conn, list_name, entries, now)
        return len(entries)

    @staticmethod
    async def _insert(
        conn: asyncpg.Connection, list_name: str, entries: Sequence[ScreeningEntry], now: datetime
    ) -> None:
        await conn.executemany(
            "INSERT INTO screening_entries (id, list_name, listing, entity_type, name, "
            "date_of_birth, country, synthetic, loaded_at, aliases) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
            [
                (e.id, list_name, e.listing, e.entity_type, e.name, e.date_of_birth,
                 e.country, e.synthetic, now, list(e.aliases))
                for e in entries
            ],
        )  # fmt: skip

    async def entries(self, entity_type: str) -> list[ScreeningEntry]:
        """Reference data, read by the screening rules' evaluation only (never a route)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, list_name, listing, entity_type, name, date_of_birth, country, "
                "synthetic, aliases FROM screening_entries WHERE entity_type = $1 ORDER BY id",
                entity_type,
            )
        return [_entry(r) for r in rows]

    # --- a list as a managed source (ADR-133 decision 4, stage (c)) ------------------------------

    async def subscribe(
        self, spec: ScreeningSubscriptionInput, by: str, *, synthetic: bool
    ) -> ScreeningListStatus:
        """A new subscription, or a changed one (its source, location or dataset); its entries stay
        until its next refresh replaces them."""
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO screening_lists (list_name, source, location, dataset, use_for, "
                "synthetic, subscribed_by, subscribed_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
                "ON CONFLICT (list_name) DO UPDATE SET source = EXCLUDED.source, "
                "location = EXCLUDED.location, dataset = EXCLUDED.dataset, "
                "use_for = EXCLUDED.use_for, synthetic = EXCLUDED.synthetic",
                spec.list_name, spec.source, spec.location, spec.dataset, spec.use, synthetic,
                by, now,
            )  # fmt: skip
        found = await self.subscription(spec.list_name)
        assert found is not None
        return found

    async def subscription(self, list_name: str) -> ScreeningListStatus | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(f"{_LIST_SELECT} WHERE list_name = $1", list_name)
        return _status(row) if row else None

    async def use_of(self, list_name: str) -> str:
        async with self._pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT use_for FROM screening_lists WHERE list_name = $1", list_name
            )
        return str(value or "local_development")

    async def subscriptions(self) -> list[ScreeningListStatus]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(f"{_LIST_SELECT} ORDER BY list_name")
        return [_status(r) for r in rows]

    async def apply_update(
        self,
        list_name: str,
        version: str,
        entries: Sequence[ScreeningEntry],
        *,
        synthetic: bool,
    ) -> ListDiff:
        """The list's entries replaced whole by this version's, in one transaction, the list row
        locked so two refreshes of one list never interleave; returns what changed."""
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn, conn.transaction():
            previous = await conn.fetchval(
                "SELECT version FROM screening_lists WHERE list_name = $1 FOR UPDATE", list_name
            )
            rows = await conn.fetch(
                "SELECT id, list_name, listing, entity_type, name, date_of_birth, country, "
                "synthetic, aliases FROM screening_entries WHERE list_name = $1",
                list_name,
            )
            diff = diff_entries(
                list_name, [_entry(r) for r in rows], entries,
                previous_version=previous, version=version,
            )  # fmt: skip
            await conn.execute("DELETE FROM screening_entries WHERE list_name = $1", list_name)
            await self._insert(conn, list_name, entries, now)
            changed = bool(diff.added or diff.changed or diff.removed) or previous != version
            await conn.execute(
                "UPDATE screening_lists SET version = $2, entry_count = $3, attempted_at = $4, "
                "failure = NULL, synthetic = $5, "
                "updated_at = CASE WHEN $6 THEN $4 ELSE updated_at END WHERE list_name = $1",
                list_name, version, len(entries), now, synthetic, changed,
            )  # fmt: skip
        return diff

    async def record_update(
        self,
        update: ScreeningListUpdate,
        *,
        list_words: str | None = None,
        by_unit: Mapping[str, UnitCounts] | None = None,
    ) -> None:
        """A refresh's record; a refused or failed one also sets the list's failure, in words. An
        updated one also keeps the words about the list alone and each unit's own counts."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO screening_list_updates (id, list_name, at, outcome, version, "
                "previous_version, added, changed, removed, rescreened, alerts, words, trigger, "
                "list_words) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)",
                update.id, update.list_name, update.at, update.outcome, update.version,
                update.previous_version, update.added, update.changed, update.delisted,
                update.rescreened, update.alerts, update.words, update.trigger, list_words,
            )  # fmt: skip
            for unit, counts in (by_unit or {}).items():
                await conn.execute(
                    "INSERT INTO screening_list_update_units (update_id, org_unit, rescreened, "
                    "alerts, failures) VALUES ($1, $2, $3, $4, $5)",
                    update.id, unit, counts.rescreened, counts.alerts, counts.failures,
                )  # fmt: skip
            if update.outcome in ("refused", "failed"):
                await conn.execute(
                    "UPDATE screening_lists SET attempted_at = $2, failure = $3 "
                    "WHERE list_name = $1",
                    update.list_name, update.at, update.words,
                )  # fmt: skip

    async def set_schedule(
        self, list_name: str, schedule: ListSchedule | None, by: str
    ) -> ScreeningListStatus:
        """The list's refresh schedule set (or, with `None`, stopped), as `by`, who it then runs
        as. Raises `LookupError` for a list never subscribed, and `ListScheduleRefused` for a
        schedule that cannot be kept."""
        from .list_schedule import check_list_schedule

        if schedule is not None:
            check_list_schedule(schedule)
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn:
            done = await conn.execute(
                "UPDATE screening_lists SET schedule_every = $2, schedule_hour = $3, "
                "schedule_weekday = $4, schedule_owner = $5, schedule_set_at = $6, "
                "schedule_last_slot = NULL WHERE list_name = $1",
                list_name,
                schedule.every if schedule else None,
                schedule.hour if schedule else None,
                schedule.weekday if schedule else None,
                by if schedule else None,
                now if schedule else None,
            )
        if done.endswith(" 0"):
            raise LookupError(list_name)
        found = await self.subscription(list_name)
        assert found is not None
        return found

    async def scheduled_lists(self) -> list[ScheduledList]:
        """Every list with a schedule: the scheduler's read, never a route."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT list_name, schedule_every, schedule_hour, schedule_weekday, "
                "schedule_owner, schedule_set_at, schedule_last_slot FROM screening_lists "
                "WHERE schedule_every IS NOT NULL ORDER BY list_name"
            )
        return [
            ScheduledList(
                list_name=r["list_name"],
                schedule=ListSchedule(
                    every=r["schedule_every"],
                    hour=r["schedule_hour"],
                    weekday=r["schedule_weekday"],
                ),  # fmt: skip
                owner=r["schedule_owner"],
                set_at=r["schedule_set_at"],
                last_slot=r["schedule_last_slot"],
            )
            for r in rows
        ]

    async def mark_slot(self, list_name: str, slot: datetime) -> bool:
        """The slot taken, once: false when another replica (or an earlier tick) has taken it or
        a later one."""
        async with self._pool.acquire() as conn:
            done = await conn.execute(
                "UPDATE screening_lists SET schedule_last_slot = $2 WHERE list_name = $1 AND "
                "(schedule_last_slot IS NULL OR schedule_last_slot < $2)",
                list_name,
                slot,
            )
        return not done.endswith(" 0")

    async def updates(self, *, org_unit: str, limit: int = 20) -> list[ScreeningListUpdate]:
        """The latest refreshes, newest first, each counted for `org_unit` alone: the query joins
        that unit's own counts and nothing else (rules 3 and 7)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(f"{_UPDATE_SELECT} ORDER BY u.at DESC, u.id DESC LIMIT $2",
                                    org_unit, limit)  # fmt: skip
        return [_update(r) for r in rows]

    async def update_for(self, update_id: str, *, org_unit: str) -> ScreeningListUpdate | None:
        """One refresh counted for `org_unit` alone, as `updates` counts it."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(f"{_UPDATE_SELECT} WHERE u.id = $2", org_unit, update_id)
        return _update(row) if row is not None else None


#: A refresh as one unit reads it. The whole-deployment `rescreened`, `alerts` and `words` of an
#: updated refresh are never selected; the unit's own row is joined by `$1` in the query.
_UPDATE_SELECT = (
    "SELECT u.id, u.list_name, u.at, u.outcome, u.version, u.previous_version, u.added, "
    "u.changed, u.removed AS delisted, u.trigger, u.list_words, "
    "CASE WHEN u.outcome = 'updated' THEN NULL ELSE u.words END AS words, "
    "COALESCE(n.rescreened, 0) AS rescreened, COALESCE(n.alerts, 0) AS alerts, "
    "COALESCE(n.failures, '{}') AS failures "
    "FROM screening_list_updates u "
    "LEFT JOIN screening_list_update_units n ON n.update_id = u.id AND n.org_unit = $1"
)


def _update(row: asyncpg.Record) -> ScreeningListUpdate:
    """A refresh as one unit reads it. An updated refresh's words are the list's own words and the
    unit's own counts; one recorded before counts were kept per unit says only what the list did."""
    words = row["words"]
    rescreened, alerts = row["rescreened"], row["alerts"]
    if row["outcome"] == "updated":
        if row["list_words"] is not None:
            counts = UnitCounts(rescreened, alerts, list(row["failures"]))
            words = unit_words(row["list_words"], row["added"] + row["changed"], counts)
        else:
            words = (
                f"Version {row['version']}: {row['added']:,} added, {row['changed']:,} changed, "
                f"{row['delisted']:,} removed. Who it re-screened was not counted by unit then, "
                "so it is not shown."
            )
    return ScreeningListUpdate(
        id=row["id"], list_name=row["list_name"], at=row["at"], outcome=row["outcome"],
        version=row["version"], previous_version=row["previous_version"], added=row["added"],
        changed=row["changed"], delisted=row["delisted"], rescreened=rescreened, alerts=alerts,
        words=words, trigger=row["trigger"],
    )  # fmt: skip


_LIST_SELECT = (
    "SELECT list_name, source, location, dataset, synthetic, version, entry_count, updated_at, "
    "attempted_at, failure, schedule_every, schedule_hour, schedule_weekday, schedule_owner "
    "FROM screening_lists"
)


def _status(row: asyncpg.Record) -> ScreeningListStatus:
    from .rule_schedule import cron_of, schedule_words
    from .scheduler import DEFAULT_TIMEZONE, next_slot
    from .screening_refresh import LICENCES

    schedule = (
        ListSchedule(
            every=row["schedule_every"], hour=row["schedule_hour"], weekday=row["schedule_weekday"]
        )  # fmt: skip
        if row["schedule_every"]
        else None
    )
    return ScreeningListStatus(
        list_name=row["list_name"], source=row["source"], location=row["location"],
        dataset=row["dataset"], synthetic=row["synthetic"], licence=LICENCES[row["source"]],
        version=row["version"], entries=row["entry_count"], updated_at=row["updated_at"],
        attempted_at=row["attempted_at"], failure=row["failure"], schedule=schedule,
        schedule_words=schedule_words(schedule) if schedule else None,
        schedule_owner=row["schedule_owner"] if schedule else None,
        next_refresh=next_slot(cron_of(schedule), DEFAULT_TIMEZONE, after=datetime.now(UTC))
        if schedule
        else None,
    )  # fmt: skip


def _entry(r: asyncpg.Record) -> ScreeningEntry:
    return ScreeningEntry(
        id=r["id"], list_name=r["list_name"], listing=r["listing"],
        entity_type=r["entity_type"], name=r["name"], date_of_birth=r["date_of_birth"],
        country=r["country"], synthetic=r["synthetic"], aliases=tuple(r["aliases"] or ()),
    )  # fmt: skip


__all__ = [
    "ListDiff",
    "ScreeningEntry",
    "diff_entries",
    "ScreeningHit",
    "ScreeningListStore",
    "UnitCounts",
    "normalised",
    "unit_words",
    "screen",
]
