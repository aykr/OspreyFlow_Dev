"""The run ledger (`06_DECISIONS.md` ADR-110 decision 6): one row per run of a published recipe,
manual or scheduled, and one per scheduled slot that did not run — refused, blocked, skipped or
missed — so a recipe's history says what happened at every slot, in words.

A run is written twice: `start` when it begins (outcome `running`), `finish` or `fail` when it ends,
so a run that dies with its Conduit is visible as one that never finished rather than as nothing.

Each row keeps the source's handling (`resolve_source_handling`): a count of what a load wrote is a
read, and the routes that show the ledger (the Admin area, the Studio, the Glass's *Data feeds*)
withhold counts from a reader who may not view the source (decision 8). This store takes no
principal; it is never read except through those routes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, get_args

import asyncpg
from pydantic import BaseModel

from conduit_common.identity import new_id
from schemas.domain import Handling
from schemas.ingest import LoadReport, PipelineRunReport

RunTrigger = Literal["manual", "schedule", "watch", "release"]
RunOutcome = Literal["running", "succeeded", "failed", "refused", "blocked", "skipped", "missed"]
NotRunOutcome = Literal["refused", "blocked", "skipped", "missed"]
_NOT_RUN = frozenset(get_args(NotRunOutcome))

_BOOTSTRAP_SQL = f"""
CREATE TABLE IF NOT EXISTS recipe_runs (
    run_id TEXT PRIMARY KEY,
    recipe_id TEXT NOT NULL,
    recipe_version INTEGER NOT NULL,
    investigation_id TEXT NOT NULL,
    trigger TEXT NOT NULL CHECK (trigger IN ({", ".join(f"'{t}'" for t in get_args(RunTrigger))})),
    slot TIMESTAMPTZ,
    run_as TEXT NOT NULL,
    source_handling JSONB NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    outcome TEXT NOT NULL CHECK (outcome IN ({", ".join(f"'{o}'" for o in get_args(RunOutcome))})),
    rows_read INTEGER,
    nodes_created INTEGER,
    nodes_referenced INTEGER,
    edges_created INTEGER,
    rows_rejected INTEGER,
    rows_held INTEGER,
    load_id TEXT,
    failure TEXT
);
CREATE INDEX IF NOT EXISTS recipe_runs_recipe_idx ON recipe_runs (recipe_id, started_at DESC);
"""

_COLUMNS = (
    "run_id, recipe_id, recipe_version, investigation_id, trigger, slot, run_as, source_handling, "
    "started_at, finished_at, outcome, rows_read, nodes_created, nodes_referenced, edges_created, "
    "rows_rejected, rows_held, load_id, failure"
)


class RecipeRun(BaseModel):
    run_id: str
    recipe_id: str
    recipe_version: int
    investigation_id: str
    trigger: RunTrigger
    slot: datetime | None
    run_as: str
    source: Handling
    started_at: datetime
    finished_at: datetime | None
    outcome: RunOutcome
    rows_read: int | None
    nodes_created: int | None
    nodes_referenced: int | None
    edges_created: int | None
    rows_rejected: int | None
    rows_held: int | None
    load_id: str | None
    failure: str | None


def _row(record: asyncpg.Record) -> RecipeRun:
    data = dict(record)
    data["source"] = Handling.model_validate_json(data.pop("source_handling"))
    return RecipeRun.model_validate(data)


class RecipeRunStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> RecipeRunStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def start(
        self,
        *,
        recipe_id: str,
        recipe_version: int,
        investigation_id: str,
        trigger: RunTrigger,
        slot: datetime | None,
        run_as: str,
        source: Handling,
        now: datetime,
    ) -> str:
        run_id = new_id()
        await self._insert(
            run_id, recipe_id, recipe_version, investigation_id, trigger, slot, run_as, source,
            started_at=now, finished_at=None, outcome="running", failure=None,
        )
        return run_id

    async def finish(
        self, run_id: str, *, report: LoadReport | PipelineRunReport, now: datetime
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE recipe_runs SET outcome = 'succeeded', finished_at = $2, rows_read = $3, "
                "nodes_created = $4, nodes_referenced = $5, edges_created = $6, "
                "rows_rejected = $7, rows_held = $8, load_id = $9 WHERE run_id = $1",
                run_id,
                now,
                report.rows_read,
                report.nodes_created,
                report.nodes_referenced,
                report.edges_created,
                len(report.rejections),
                report.rows_held,
                report.load_id,
            )

    async def fail(self, run_id: str, *, failure: str, now: datetime) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE recipe_runs SET outcome = 'failed', finished_at = $2, failure = $3 "
                "WHERE run_id = $1",
                run_id,
                now,
                failure,
            )

    async def record_not_run(
        self,
        *,
        recipe_id: str,
        recipe_version: int,
        investigation_id: str,
        trigger: RunTrigger,
        slot: datetime | None,
        run_as: str,
        source: Handling,
        outcome: NotRunOutcome,
        failure: str | None,
        now: datetime,
    ) -> str:
        """A slot that did not run, and why (decisions 2–4)."""
        if outcome not in _NOT_RUN:
            raise ValueError(f"{outcome!r} is not an outcome for a slot that did not run")
        run_id = new_id()
        await self._insert(
            run_id, recipe_id, recipe_version, investigation_id, trigger, slot, run_as, source,
            started_at=now, finished_at=now, outcome=outcome, failure=failure,
        )
        return run_id

    async def _insert(
        self,
        run_id: str,
        recipe_id: str,
        recipe_version: int,
        investigation_id: str,
        trigger: RunTrigger,
        slot: datetime | None,
        run_as: str,
        source: Handling,
        *,
        started_at: datetime,
        finished_at: datetime | None,
        outcome: RunOutcome,
        failure: str | None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO recipe_runs (run_id, recipe_id, recipe_version, investigation_id, "
                "trigger, slot, run_as, source_handling, started_at, finished_at, outcome, "
                "failure) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10, $11, $12)",
                run_id,
                recipe_id,
                recipe_version,
                investigation_id,
                trigger,
                slot,
                run_as,
                source.model_dump_json(),
                started_at,
                finished_at,
                outcome,
                failure,
            )

    async def for_recipe(self, recipe_id: str, *, limit: int = 50) -> list[RecipeRun]:
        """The recipe's runs, newest first."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM recipe_runs WHERE recipe_id = $1 "
                "ORDER BY started_at DESC, run_id DESC LIMIT $2",
                recipe_id,
                limit,
            )
        return [_row(r) for r in rows]

    async def last_slot(self, recipe_id: str) -> datetime | None:
        """The latest scheduled slot the ledger has any row for — run, or not run and why."""
        async with self._pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT max(slot) FROM recipe_runs WHERE recipe_id = $1 AND trigger = 'schedule'",
                recipe_id,
            )
        return value  # type: ignore[no-any-return]

    async def refusals_in_a_row(self, recipe_id: str) -> int:
        """How many of the recipe's latest scheduled runs were refused, back to the last that was
        not (decision 3: three pause the schedule)."""
        async with self._pool.acquire() as conn:
            outcomes = await conn.fetch(
                "SELECT outcome FROM recipe_runs WHERE recipe_id = $1 AND trigger = 'schedule' "
                "ORDER BY started_at DESC, run_id DESC LIMIT 50",
                recipe_id,
            )
        count = 0
        for row in outcomes:
            if row["outcome"] != "refused":
                break
            count += 1
        return count
