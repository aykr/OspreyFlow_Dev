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

**A list is read only by whom its marking clears (ADR-146 Amendment 7, the orchestrator's review of
12 November 2026; rule 3 in the adapter).** A list's marking is kept in `screening_list_markings`
(its entries carry it too), so it outlives the list's entries and needs no subscription. Every read
a person's work reaches (`entries`, `subscriptions`, `updates`, `update_for`, `hidden`) takes the
reader's `ListClearance` and filters in its `WHERE`, so no caller can screen against, or show, a
list its reader may not read. `replace_list` refuses to lower a list's marking, as a refresh never
does (`apply_update` keeps it).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from typing import Literal

import asyncpg
import duckdb

from ontology.handling import HandlingScheme
from schemas.domain import Principal
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
-- ADR-146 Amendment 7: the list's marking, carried by each of its entries; NULL is OFFICIAL, P.
ALTER TABLE screening_entries ADD COLUMN IF NOT EXISTS classification TEXT;
ALTER TABLE screening_entries ADD COLUMN IF NOT EXISTS handling_code TEXT;
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
-- ADR-146 Amendment 7 (the orchestrator's review): a list's marking, kept apart from its entries so
-- an emptied list, or one loaded with no subscription, keeps it; a list with no row is OFFICIAL, P.
CREATE TABLE IF NOT EXISTS screening_list_markings (
    list_name TEXT PRIMARY KEY,
    classification TEXT NOT NULL,
    handling_code TEXT NOT NULL
);
INSERT INTO screening_list_markings (list_name, classification, handling_code)
    SELECT DISTINCT ON (list_name) list_name, classification, COALESCE(handling_code, 'P')
    FROM screening_entries WHERE classification IS NOT NULL
    ORDER BY list_name ON CONFLICT (list_name) DO NOTHING;
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


DEFAULT_CLASSIFICATION, DEFAULT_HANDLING_CODE = "OFFICIAL", "P"


@dataclass(frozen=True)
class ListClearance:
    """The list markings one reader is cleared for (ADR-146 Amendment 7): every classification
    their clearance dominates and every handling code they may receive. A list's match is written
    in the reader's own unit (`kyc_rules.list_handling`), so a restricted code is one they hold;
    `handling_readable` over a list's marking answers the same (`test_screening.py`). Passed to
    every store read a person's work reaches, which filters in its `WHERE` (rule 3)."""

    classifications: tuple[str, ...]
    codes: tuple[str, ...]

    @classmethod
    def of(cls, principal: Principal, scheme: HandlingScheme) -> ListClearance:
        return cls.of_clearance(principal.clearance, principal.receivable_handling_codes, scheme)

    @classmethod
    def of_clearance(
        cls, clearance: str | None, receivable: Sequence[str], scheme: HandlingScheme
    ) -> ListClearance:
        """As `of`, from a clearance and handling codes alone: a directory account's, for one who
        is to be given a list's schedule (`admin_people.markings_hold`)."""
        try:
            classifications = tuple(
                c for c in scheme.classification
                if clearance is not None and scheme.clears(clearance, c)
            )  # fmt: skip
        except Exception:  # noqa: BLE001 - a clearance outside the scheme clears nothing
            classifications = ()
        codes = tuple(
            k for k, d in scheme.handling_codes.items()
            if d.dissemination != "restricted" or k in receivable
        )  # fmt: skip
        return cls(classifications, codes)

    def admits(self, classification: str | None, code: str | None) -> bool:
        return (classification or DEFAULT_CLASSIFICATION) in self.classifications and (
            code or DEFAULT_HANDLING_CODE
        ) in self.codes


class MarkingLowered(ValueError):
    """A reload that would lower a list's marking, refused in words (the orchestrator's review,
    item 8): a list loaded SECRET is never read again as OFFICIAL by loading its file without
    one."""


#: A list's marking in a query over `screening_entries` (`e`) or a table naming lists (`l`): the
#: kept marking, else the entry's own, else OFFICIAL, P.
def _admitted_sql(table: str, cls_param: int) -> str:
    entry = table == "e"
    cls = "COALESCE(m.classification" + (", e.classification" if entry else "") + ", 'OFFICIAL')"
    code = "COALESCE(m.handling_code" + (", e.handling_code" if entry else "") + ", 'P')"
    return f"{cls} = ANY(${cls_param}::text[]) AND {code} = ANY(${cls_param + 1}::text[])"


def _markings_join(table: str) -> str:
    return f" LEFT JOIN screening_list_markings m ON m.list_name = {table}.list_name"


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
    #: ADR-146 Amendment 7: the list's marking, which its listed party (and so each match on it)
    #: carries: only a reader it clears is shown a match on the list. `None` is the default,
    #: OFFICIAL with handling code P, as every list was marked before.
    classification: str | None = None
    handling_code: str | None = None

    def fingerprint(self) -> tuple[object, ...]:
        """What makes two versions of one entry the same entry: everything screening reads."""
        return (self.listing, self.entity_type, self.name, tuple(sorted(self.aliases)),
                self.date_of_birth, self.country, self.classification,
                self.handling_code)  # fmt: skip


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

    async def replace_list(
        self, list_name: str, entries: Sequence[ScreeningEntry], *, scheme: HandlingScheme
    ) -> int:
        """The named list, replaced whole in one transaction — a reload never leaves half of an
        old list beside half of a new one. Refused (`MarkingLowered`), with nothing changed, where
        the file's marking (none is OFFICIAL, P) is below the list's kept one or names another
        handling code at the same classification: lowering a list is removing it and loading it
        again, never a reload."""
        now = datetime.now(UTC)
        new = _list_marking(entries)
        async with self._pool.acquire() as conn, conn.transaction():
            kept = await _kept_marking(conn, list_name, lock=True)
            if kept is not None and _lowers(scheme, kept, new):
                raise MarkingLowered(
                    f"“{list_name}” is held at {kept[0]} {kept[1]}; this file's marking "
                    f"({new[0]} {new[1]}) would lower it, so nothing was loaded. Remove the list "
                    "first to load it lower."
                )
            await conn.execute("DELETE FROM screening_entries WHERE list_name = $1", list_name)
            await self._insert(conn, list_name, entries, now)
            await _keep_marking(conn, list_name, new)
        return len(entries)

    @staticmethod
    async def _insert(
        conn: asyncpg.Connection, list_name: str, entries: Sequence[ScreeningEntry], now: datetime
    ) -> None:
        await conn.executemany(
            "INSERT INTO screening_entries (id, list_name, listing, entity_type, name, "
            "date_of_birth, country, synthetic, loaded_at, aliases, classification, "
            "handling_code) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)",
            [
                (e.id, list_name, e.listing, e.entity_type, e.name, e.date_of_birth,
                 e.country, e.synthetic, now, list(e.aliases), e.classification,
                 e.handling_code)
                for e in entries
            ],
        )  # fmt: skip

    async def entries(self, entity_type: str, *, cleared: ListClearance) -> list[ScreeningEntry]:
        """Reference data, read by the screening rules' evaluation and a sentence's preview as the
        rule's deployer or the previewer, never a route: only the lists `cleared` admits, in the
        query (ADR-146 Amendment 7, point 8; rule 3)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT e.id, e.list_name, e.listing, e.entity_type, e.name, e.date_of_birth, "
                "e.country, e.synthetic, e.aliases, "
                "COALESCE(m.classification, e.classification) AS classification, "
                "COALESCE(m.handling_code, e.handling_code) AS handling_code "
                f"FROM screening_entries e{_markings_join('e')} "
                f"WHERE e.entity_type = $1 AND {_admitted_sql('e', 2)} ORDER BY e.id",
                entity_type, list(cleared.classifications), list(cleared.codes),
            )  # fmt: skip
        return [_entry(r) for r in rows]

    async def hidden(self, list_name: str, *, cleared: ListClearance) -> bool:
        """Whether a list of this name is held at a marking `cleared` does not admit: a route
        answers it as it answers a list no one subscribed, before it reads or changes anything."""
        async with self._pool.acquire() as conn:
            kept = await _kept_marking(conn, list_name)
            if kept is None and await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM screening_lists WHERE list_name = $1) OR "
                "EXISTS (SELECT 1 FROM screening_entries WHERE list_name = $1)",
                list_name,
            ):
                # A list held with no marking is OFFICIAL, P, as every read of it takes it (the lane
                # review of the second pass, defect 9: a reader below OFFICIAL could refresh it).
                kept = (DEFAULT_CLASSIFICATION, DEFAULT_HANDLING_CODE)
        return kept is not None and not cleared.admits(*kept)

    async def markings(self, list_names: Collection[str]) -> dict[str, tuple[str, str]]:
        """Each named list's kept marking, as it stands now (a list with none kept is left out, and
        is OFFICIAL, P): what an audit entry recorded at an older marking is read by too."""
        if not list_names:
            return {}
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT list_name, classification, handling_code FROM screening_list_markings "
                "WHERE list_name = ANY($1::text[])",
                sorted(list_names),
            )
        return {r["list_name"]: (r["classification"], r["handling_code"]) for r in rows}

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

    async def subscriptions(self, *, cleared: ListClearance | None) -> list[ScreeningListStatus]:
        """Every subscribed list `cleared` admits, in the query (rule 3); `None` only for the
        operator's own command and the scheduler, which read every list as the system."""
        async with self._pool.acquire() as conn:
            if cleared is None:
                rows = await conn.fetch(f"{_LIST_SELECT} ORDER BY list_name")
            else:
                rows = await conn.fetch(
                    f"{_LIST_SELECT}{_markings_join('screening_lists')} "
                    f"WHERE {_admitted_sql('l', 1)} ORDER BY screening_lists.list_name",
                    list(cleared.classifications), list(cleared.codes),
                )  # fmt: skip
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
                "synthetic, aliases, classification, handling_code FROM screening_entries "
                "WHERE list_name = $1",
                list_name,
            )
            # ADR-146 Amendment 7 (the lane review's item 10): a refresh's file carries no marking,
            # so a marked list keeps the one it was loaded with, never dropped to OFFICIAL by an
            # update of the same name; kept apart from the entries, so an emptied list keeps it too.
            marked = await _kept_marking(conn, list_name)
            if marked is not None:
                entries = [
                    e if e.classification is not None else replace(
                        e, classification=marked[0], handling_code=marked[1],
                    )
                    for e in entries
                ]  # fmt: skip
                await _keep_marking(conn, list_name, marked)
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

    async def updates(
        self, *, org_unit: str, cleared: ListClearance, limit: int = 20
    ) -> list[ScreeningListUpdate]:
        """The latest refreshes of the lists `cleared` admits, newest first, each counted for
        `org_unit` alone: the query joins that unit's own counts and nothing else (rules 3, 7)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"{_UPDATE_SELECT}{_markings_join('u')} WHERE {_admitted_sql('l', 3)} "
                "ORDER BY u.at DESC, u.id DESC LIMIT $2",
                org_unit, limit, list(cleared.classifications), list(cleared.codes),
            )  # fmt: skip
        return [_update(r) for r in rows]

    async def update_for(
        self, update_id: str, *, org_unit: str, cleared: ListClearance
    ) -> ScreeningListUpdate | None:
        """One refresh counted for `org_unit` alone, as `updates` counts it; none for a list
        `cleared` does not admit."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"{_UPDATE_SELECT}{_markings_join('u')} "
                f"WHERE u.id = $2 AND {_admitted_sql('l', 3)}",
                org_unit, update_id, list(cleared.classifications), list(cleared.codes),
            )  # fmt: skip
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
    "SELECT screening_lists.list_name, source, location, dataset, synthetic, version, "
    "entry_count, updated_at, attempted_at, failure, schedule_every, schedule_hour, "
    "schedule_weekday, schedule_owner FROM screening_lists"
)


def _list_marking(entries: Sequence[ScreeningEntry]) -> tuple[str, str]:
    """The marking a file gives its list (every entry carries the file's): none is OFFICIAL, P."""
    first = entries[0] if entries else None
    return (
        (first.classification if first else None) or DEFAULT_CLASSIFICATION,
        (first.handling_code if first else None) or DEFAULT_HANDLING_CODE,
    )


async def _kept_marking(
    conn: asyncpg.Connection, list_name: str, *, lock: bool = False
) -> tuple[str, str] | None:
    """The list's kept marking, else its entries' (a list loaded before it was kept apart)."""
    row = await conn.fetchrow(
        "SELECT classification, handling_code FROM screening_list_markings WHERE list_name = $1"
        + (" FOR UPDATE" if lock else ""),
        list_name,
    )
    if row is None:
        row = await conn.fetchrow(
            "SELECT classification, COALESCE(handling_code, 'P') AS handling_code "
            "FROM screening_entries WHERE list_name = $1 AND classification IS NOT NULL LIMIT 1",
            list_name,
        )
    return (row["classification"], row["handling_code"]) if row is not None else None


async def _keep_marking(conn: asyncpg.Connection, list_name: str, marking: tuple[str, str]) -> None:
    await conn.execute(
        "INSERT INTO screening_list_markings (list_name, classification, handling_code) "
        "VALUES ($1, $2, $3) ON CONFLICT (list_name) DO UPDATE SET "
        "classification = EXCLUDED.classification, handling_code = EXCLUDED.handling_code",
        list_name, *marking,
    )  # fmt: skip


def _lowers(scheme: HandlingScheme, kept: tuple[str, str], new: tuple[str, str]) -> bool:
    """A new marking below the kept one, or another handling code at the same classification
    (a code is not ranked, so changing it is treated as lowering it: strict)."""
    try:
        old_rank = scheme.classification.index(kept[0])
        new_rank = scheme.classification.index(new[0])
    except ValueError:
        return True
    return new_rank < old_rank or (new_rank == old_rank and new[1] != kept[1])


def _status(row: asyncpg.Record) -> ScreeningListStatus:
    from .rule_schedule import cron_of, schedule_words
    from .scheduler import DEFAULT_TIMEZONE, next_slot
    from .screening_refresh import CLOSED_LISTS, LICENCE_NOT_CONFIRMED, LICENCES

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
        licence_confirmed=row["source"] not in LICENCE_NOT_CONFIRMED,
        licence_note=LICENCE_NOT_CONFIRMED.get(row["source"]),
        closed_note=CLOSED_LISTS.get(row["source"]),
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
        classification=r["classification"], handling_code=r["handling_code"],
    )  # fmt: skip


__all__ = [
    "ListClearance",
    "MarkingLowered",
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
