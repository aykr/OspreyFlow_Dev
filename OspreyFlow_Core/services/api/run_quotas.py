"""Run quotas (`06_DECISIONS.md` ADR-141 decision 6; the redesign's phase 10 step 2).

A dataset's or a unit's quota of runs a day, checked in `run_recipe_as`, the one place every
trigger's run starts (manual, schedule, watch, source refresh, external), so every trigger obeys
it. A day is a calendar day in Europe/London, the deployment's wall clock (ADR-110 decision 7).
A run past a quota is **refused in words** and recorded *refused*, before anything is read; it does
not count toward the three refusals that pause a schedule, since it says nothing about the owner
(ADR-141 open question 2, taken here: logged in REPORT.md).

**The budget alert.** When a run brings the day's count to `alert_at_share` of a quota (80% unless
set), one alert is recorded for that quota and day (`quota_alerts`), shown on Admin › Running ›
Operations (`OperationsRollup.alerts`). Its delivery to each administrator's own inbox is admin's
(*Needs you*), left named.

Rows per run and staged bytes per run (the decision's other two quotas) are not built here: they
are judged mid-run, and are named as left in REPORT.md.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Protocol
from zoneinfo import ZoneInfo

import asyncpg

from schemas.operations import QuotaScope, RunQuota

_LONDON = ZoneInfo("Europe/London")

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS run_quotas (
    scope TEXT NOT NULL CHECK (scope IN ('dataset', 'unit')),
    key TEXT NOT NULL,
    runs_per_day INTEGER CHECK (runs_per_day IS NULL OR runs_per_day >= 1),
    alert_at_share DOUBLE PRECISION NOT NULL CHECK (alert_at_share > 0 AND alert_at_share < 1),
    PRIMARY KEY (scope, key)
);
CREATE TABLE IF NOT EXISTS quota_alerts (
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    day DATE NOT NULL,
    raised_at TIMESTAMPTZ NOT NULL,
    words TEXT NOT NULL,
    PRIMARY KEY (scope, key, day)
);
"""


class QuotaRefused(Exception):
    """A run past a quota, refused in words before anything is read (rule 2)."""


@dataclass(frozen=True)
class QuotaLimit:
    """A quota a run's start is held to, judged again under its lock as the run is recorded
    (`RecipeRunStore.start`), so two runs into one dataset cannot both take its last run."""

    scope: QuotaScope
    key: str
    runs_per_day: int
    since: datetime


def quota_words(scope: str, limit: int) -> str:
    """A quota refusal's words. They reach the owner, the service identity and Operations' readers
    of one unit, and the day's count is every unit's runs, so they tell none (rules 3 and 7)."""
    return (
        f"{_WHOSE[scope]} quota of {_runs(limit)} a day is used; "
        "the next may start after midnight, or an administrator may raise the quota in "
        "Admin › Running › Operations"
    )


@dataclass(frozen=True)
class QuotaAlert:
    scope: QuotaScope
    key: str
    day: str
    words: str


class RunCounts(Protocol):
    async def runs_since(
        self, *, since: datetime, dataset_id: str | None = None, owning_unit: str | None = None
    ) -> int: ...


class QuotaStore(Protocol):
    async def get(self, scope: QuotaScope, key: str) -> RunQuota | None: ...
    async def set(self, quota: RunQuota) -> None: ...
    async def remove(self, scope: QuotaScope, key: str) -> None: ...
    async def all(self) -> list[RunQuota]: ...
    async def reached_by(
        self, *, units: Sequence[str] | None, datasets: Sequence[str]
    ) -> list[RunQuota]: ...
    async def raise_once(self, alert: QuotaAlert, *, at: datetime) -> bool: ...
    async def alerts(
        self, *, since_day: str, of: Sequence[tuple[str, str]] | None
    ) -> list[QuotaAlert]: ...


@dataclass
class InMemoryQuotaStore:
    """The Postgres store's behaviour for tests: one quota a scope and key, an alert once a day."""

    quotas: dict[tuple[str, str], RunQuota] = field(default_factory=dict)
    raised: dict[tuple[str, str, str], QuotaAlert] = field(default_factory=dict)

    async def get(self, scope: QuotaScope, key: str) -> RunQuota | None:
        return self.quotas.get((scope, key))

    async def set(self, quota: RunQuota) -> None:
        self.quotas[(quota.scope, quota.key)] = quota

    async def remove(self, scope: QuotaScope, key: str) -> None:
        self.quotas.pop((scope, key), None)

    async def all(self) -> list[RunQuota]:
        return sorted(self.quotas.values(), key=lambda q: (q.scope, q.key))

    async def reached_by(
        self, *, units: Sequence[str] | None, datasets: Sequence[str]
    ) -> list[RunQuota]:
        return [
            q
            for q in await self.all()
            if units is None
            or (q.scope == "unit" and q.key in units)
            or (q.scope == "dataset" and q.key in datasets)
        ]

    async def raise_once(self, alert: QuotaAlert, *, at: datetime) -> bool:
        key = (alert.scope, alert.key, alert.day)
        if key in self.raised:
            return False
        self.raised[key] = alert
        return True

    async def alerts(
        self, *, since_day: str, of: Sequence[tuple[str, str]] | None
    ) -> list[QuotaAlert]:
        wanted = None if of is None else set(of)
        return [
            a
            for a in self.raised.values()
            if a.day >= since_day and (wanted is None or (a.scope, a.key) in wanted)
        ]


class PostgresQuotaStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PostgresQuotaStore:
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def get(self, scope: QuotaScope, key: str) -> RunQuota | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT scope, key, runs_per_day, alert_at_share FROM run_quotas "
                "WHERE scope = $1 AND key = $2",
                scope,
                key,
            )
        return None if row is None else RunQuota.model_validate(dict(row))

    async def set(self, quota: RunQuota) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO run_quotas (scope, key, runs_per_day, alert_at_share) "
                "VALUES ($1, $2, $3, $4) ON CONFLICT (scope, key) DO UPDATE SET "
                "runs_per_day = EXCLUDED.runs_per_day, alert_at_share = EXCLUDED.alert_at_share",
                quota.scope,
                quota.key,
                quota.runs_per_day,
                quota.alert_at_share,
            )

    async def remove(self, scope: QuotaScope, key: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM run_quotas WHERE scope = $1 AND key = $2", scope, key)

    async def all(self) -> list[RunQuota]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT scope, key, runs_per_day, alert_at_share FROM run_quotas "
                "ORDER BY scope, key"
            )
        return [RunQuota.model_validate(dict(r)) for r in rows]

    async def reached_by(
        self, *, units: Sequence[str] | None, datasets: Sequence[str]
    ) -> list[RunQuota]:
        """The quotas a reader of `units` (`None`: every unit) sees: their units' own and those of
        the datasets their units' runs went into, filtered in the `WHERE` (rule 3)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT scope, key, runs_per_day, alert_at_share FROM run_quotas WHERE "
                "$1::text[] IS NULL OR (scope = 'unit' AND key = ANY($1::text[])) "
                "OR (scope = 'dataset' AND key = ANY($2::text[])) ORDER BY scope, key",
                None if units is None else list(units),
                list(datasets),
            )
        return [RunQuota.model_validate(dict(r)) for r in rows]

    async def raise_once(self, alert: QuotaAlert, *, at: datetime) -> bool:
        async with self._pool.acquire() as conn:
            status = await conn.execute(
                "INSERT INTO quota_alerts (scope, key, day, raised_at, words) "
                "VALUES ($1, $2, $3::date, $4, $5) ON CONFLICT DO NOTHING",
                alert.scope,
                alert.key,
                # asyncpg takes a `date` for a date parameter, never its ISO text.
                date.fromisoformat(alert.day),
                at,
                alert.words,
            )
        return str(status).endswith(" 1")

    async def alerts(
        self, *, since_day: str, of: Sequence[tuple[str, str]] | None
    ) -> list[QuotaAlert]:
        """The budget alerts since `since_day` of the quotas `of` (`None`: every quota), filtered
        in the `WHERE` (rule 3)."""
        scopes = None if of is None else [s for s, _ in of]
        keys = None if of is None else [k for _, k in of]
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT a.scope, a.key, a.day::text AS day, a.words FROM quota_alerts a "
                "WHERE a.day >= $1::date AND ($2::text[] IS NULL OR (a.scope, a.key) IN "
                "(SELECT * FROM unnest($2::text[], $3::text[]))) "
                "ORDER BY a.day DESC, a.scope, a.key",
                date.fromisoformat(since_day),
                scopes,
                keys,
            )
        return [QuotaAlert(r["scope"], r["key"], r["day"], r["words"]) for r in rows]


def day_start(now: datetime) -> datetime:
    """Midnight of `now`'s day in Europe/London, as an aware instant."""
    local = now.astimezone(_LONDON)
    return datetime.combine(local.date(), time(0), tzinfo=_LONDON)


def _runs(n: int) -> str:
    return f"{n} run{'' if n == 1 else 's'}"


_WHOSE = {"dataset": "the dataset's", "unit": "the unit's"}


async def judge(
    quotas: QuotaStore,
    runs: RunCounts,
    *,
    dataset_id: str | None,
    owning_unit: str | None,
    now: datetime,
) -> list[QuotaLimit]:
    """Refuses (`QuotaRefused`) a run past its dataset's or its unit's quota of runs a day, and
    records the budget alert once a day when this run reaches a quota's alert share. Returns the
    limits the run's start is held to again, under their locks, as it is recorded."""
    since = day_start(now)
    limits: list[QuotaLimit] = []
    day = since.date().isoformat()
    for scope, key in (("dataset", dataset_id), ("unit", owning_unit)):
        if not key:
            continue
        quota = await quotas.get(scope, key)  # type: ignore[arg-type]
        if quota is None or quota.runs_per_day is None:
            continue
        today = (
            await runs.runs_since(since=since, dataset_id=key)
            if scope == "dataset"
            else await runs.runs_since(since=since, owning_unit=key)
        )
        limit = quota.runs_per_day
        if today >= limit:
            raise QuotaRefused(quota_words(scope, limit))
        limits.append(QuotaLimit(scope, key, limit, since))  # type: ignore[arg-type]
        if today + 1 >= math.ceil(limit * quota.alert_at_share):
            # The share it was set to reach, never the day's count (every unit's runs: rule 7).
            words = (
                f"{_WHOSE[scope].capitalize()} runs today reached "
                f"{round(quota.alert_at_share * 100)}% of its quota of {_runs(limit)} a day"
            )
            await quotas.raise_once(QuotaAlert(scope, key, day, words), at=now)  # type: ignore[arg-type]
    return limits
