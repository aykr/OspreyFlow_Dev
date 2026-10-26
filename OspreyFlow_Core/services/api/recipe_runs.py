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

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal, get_args

import asyncpg
from pydantic import BaseModel, Field, model_validator
from services.ingest.engine import RowKeyRunInProgress

from conduit_common.identity import new_id
from schemas.domain import Handling
from schemas.ingest import LoadRecord, LoadReport, PipelineRunReport

RunTrigger = Literal["manual", "schedule", "watch", "release"]
RunOutcome = Literal["running", "succeeded", "failed", "refused", "blocked", "skipped", "missed"]
NotRunOutcome = Literal["refused", "blocked", "skipped", "missed"]
_NOT_RUN = frozenset(get_args(NotRunOutcome))

#: ADR-127 decision 6: the `LoadRecord` of each load the run made (a list: a pipeline run made one
#: per branch), beside the run. A ledger made before it has the table without the column, which
#: `CREATE TABLE IF NOT EXISTS` leaves so; connecting adds it. Never selected into `RecipeRun`: the
#: record holds ids of elements some readers may not see, and no route returns it.
_ADD_LOAD_RECORDS = "ALTER TABLE recipe_runs ADD COLUMN IF NOT EXISTS load_records JSONB;"

#: Rule 3, ADR-127 Amendment 23: every distinct marking the run's rows were written at
#: (`LoadReport.markings`), set when the run finishes. A run's counts include rows above the
#: source's own marking, so the routes that show them withhold them from a reader who may not view
#: one of these. NULL for a run written before the column existed, and for one that has not
#: finished or has failed: both read as the source's marking alone (`RecipeRun`). A ledger made
#: before it has the table without the column, which `CREATE TABLE IF NOT EXISTS` leaves so;
#: connecting adds it.
_ADD_ROW_MARKINGS = "ALTER TABLE recipe_runs ADD COLUMN IF NOT EXISTS row_markings JSONB;"

#: ADR-127 decision 5: the rows a recipe has loaded into a case, by the key of each (its fields
#: canonicalised, then hashed: `engine.dedup_key`), with the load that kept it. The primary key is
#: the lookup a run makes (`row_key = ANY(...)` for one recipe and case) and the guard against a key
#: kept twice; the index on `load_id` is what a revert releases a load's keys by. Nothing here names
#: a row's content, only a hash of its key fields.
_LOADED_ROW_KEYS = """
CREATE TABLE IF NOT EXISTS loaded_row_keys (
    recipe_id TEXT NOT NULL,
    investigation_id TEXT NOT NULL,
    row_key TEXT NOT NULL,
    load_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (recipe_id, investigation_id, row_key)
);
-- The definition of `deduplicate` that made each key (`engine.dedup_fingerprint`): a run under
-- another definition is refused while keys under this one are kept for its case. A table made
-- before it gets '' (no known definition), which no run's fingerprint equals.
ALTER TABLE loaded_row_keys ADD COLUMN IF NOT EXISTS fingerprint TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS loaded_row_keys_load_idx ON loaded_row_keys (load_id);
CREATE INDEX IF NOT EXISTS loaded_row_keys_fingerprint_idx
    ON loaded_row_keys (recipe_id, investigation_id, fingerprint, load_id);
"""

#: The record's own id lists: what `unreverted_loads` leaves out, since it answers a question about
#: a load, not about its elements.
_ID_LISTS = (
    "created_node_ids",
    "touched_edge_ids",
    "created_edge_ids",
    "merged_edge_ids",
    "merged_node_ids",
    "created_geometry_refs",
)

#: How long a second run of one recipe into one case waits for the first before it is refused, and
#: how often it asks (ADR-127 decision 5).
ROW_KEY_LOCK_WAIT_SECONDS = 30.0
_LOCK_POLL_SECONDS = 0.2

#: A lookup or an insert sends this many keys at a time, so a million-row file is a hundred
#: round trips, none of them an unbounded statement.
_KEY_CHUNK = 10_000

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
-- ADR-110 Amendment 3: a refusal that is not about the owner (an unreachable identity provider)
-- does not count toward the three that pause a schedule.
ALTER TABLE recipe_runs ADD COLUMN IF NOT EXISTS counts_toward_pause BOOLEAN NOT NULL DEFAULT TRUE;
-- ADR-110 Amendment 4: the file a folder watch took (name, size, modification time), so it is
-- taken once.
ALTER TABLE recipe_runs ADD COLUMN IF NOT EXISTS source_file TEXT;
CREATE INDEX IF NOT EXISTS recipe_runs_recipe_idx ON recipe_runs (recipe_id, started_at DESC);
{_ADD_LOAD_RECORDS}
{_ADD_ROW_MARKINGS}
{_LOADED_ROW_KEYS}
"""

_COLUMNS = (
    "run_id, recipe_id, recipe_version, investigation_id, trigger, slot, run_as, source_handling, "
    "started_at, finished_at, outcome, rows_read, nodes_created, nodes_referenced, edges_created, "
    "rows_rejected, rows_held, load_id, failure, source_file, row_markings"
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
    #: For a folder watch's run (trigger `watch`): the file's name, size and modification time.
    source_file: str | None = None
    #: Rule 3, ADR-127 Amendment 23: every marking the run's rows were written at. A run with none
    #: recorded (written before the column, or still running, or failed) reads as the source's
    #: marking alone, as it did before the column existed; a finished run that wrote no row has an
    #: empty list (the view still judges the source). Markings, never ids.
    markings: list[Handling] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _none_recorded_reads_as_the_source(cls, data: object) -> object:
        if isinstance(data, dict) and data.get("markings") is None and "source" in data:
            return {**data, "markings": [data["source"]]}
        return data


def _row(record: asyncpg.Record) -> RecipeRun:
    data = dict(record)
    data["source"] = Handling.model_validate_json(data.pop("source_handling"))
    raw = data.pop("row_markings")
    # asyncpg hands JSONB back as text unless a codec is set, and this pool sets none.
    recorded = json.loads(raw) if isinstance(raw, str) else raw
    data["markings"] = None if recorded is None else [Handling.model_validate(m) for m in recorded]
    return RecipeRun.model_validate(data)


class RecipeRunStore:
    def __init__(self, pool: asyncpg.Pool, dsn: str) -> None:
        self._pool = pool
        self._dsn = dsn

    @classmethod
    async def connect(cls, dsn: str) -> RecipeRunStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool, dsn)

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
        source_file: str | None = None,
    ) -> str:
        run_id = new_id()
        await self._insert(
            run_id, recipe_id, recipe_version, investigation_id, trigger, slot, run_as, source,
            started_at=now, finished_at=None, outcome="running", failure=None,
            source_file=source_file,
        )  # fmt: skip
        return run_id

    async def finish(
        self, run_id: str, *, report: LoadReport | PipelineRunReport, now: datetime
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE recipe_runs SET outcome = 'succeeded', finished_at = $2, rows_read = $3, "
                "nodes_created = $4, nodes_referenced = $5, edges_created = $6, "
                "rows_rejected = $7, rows_held = $8, load_id = $9, row_markings = $10::jsonb "
                "WHERE run_id = $1",
                run_id,
                now,
                report.rows_read,
                report.nodes_created,
                report.nodes_referenced,
                report.edges_created,
                len(report.rejections),
                report.rows_held,
                report.load_id,
                json.dumps([m.model_dump(mode="json") for m in report.markings]),
            )

    async def add_record(
        self,
        run_id: str,
        record: LoadRecord,
        *,
        row_keys: Sequence[str] = (),
        row_key_fingerprint: str = "",
    ) -> None:
        """Appends a load's record to its run (ADR-127 decision 6), when the load's graph
        transaction commits and so before the run can `finish`: a run that fails afterwards still
        has the record a revert needs. A pipeline run appends one per branch.

        `row_keys` (decision 5) are kept for the record's recipe and case, with its load, **in the
        same transaction**: both land or neither does. The graph has committed already, so a crash
        between the two stores leaves rows loaded with neither (the run row stays `running`), and
        never a key for a row that did not load, nor a record whose keys were lost. A key already
        kept is left as it was."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "UPDATE recipe_runs SET load_records = COALESCE(load_records, '[]'::jsonb) "
                "|| $2::jsonb WHERE run_id = $1",
                run_id,
                json.dumps([record.model_dump(mode="json")]),
            )
            keys = list(dict.fromkeys(row_keys))
            for start in range(0, len(keys), _KEY_CHUNK):
                await conn.execute(
                    "INSERT INTO loaded_row_keys "
                    "(recipe_id, investigation_id, row_key, load_id, fingerprint) "
                    "SELECT $1, $2, k, $4, $5 FROM unnest($3::text[]) AS k "
                    "ON CONFLICT (recipe_id, investigation_id, row_key) DO NOTHING",
                    record.recipe_id,
                    record.investigation_id or "",
                    keys[start : start + _KEY_CHUNK],
                    record.load_id,
                    row_key_fingerprint,
                )

    async def kept_row_keys(self, recipe_id: str, case: str, keys: Sequence[str]) -> set[str]:
        """Which of `keys` the case has kept for the recipe, whatever version and whichever load:
        by the primary key, in chunks. Another case's keys are not this case's (rule 3)."""
        kept: set[str] = set()
        unique = list(dict.fromkeys(keys))
        async with self._pool.acquire() as conn:
            for start in range(0, len(unique), _KEY_CHUNK):
                rows = await conn.fetch(
                    "SELECT row_key FROM loaded_row_keys WHERE recipe_id = $1 "
                    "AND investigation_id = $2 AND row_key = ANY($3::text[])",
                    recipe_id,
                    case,
                    unique[start : start + _KEY_CHUNK],
                )
                kept.update(r["row_key"] for r in rows)
        return kept

    async def fingerprints(self, recipe_id: str, case: str) -> dict[str, int]:
        """The definitions of `deduplicate` this recipe's kept keys in the case were made under,
        each with how many loads kept keys under it: a run whose own differs is refused, naming
        that count (`engine.RowKeyDefinitionChanged`). Read from the index on
        (recipe, case, fingerprint, load): one entry per kept key of the case, grouped, which at a
        million keys is a scan of that index and not of the table. Unmeasured."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT fingerprint, count(DISTINCT load_id) AS loads FROM loaded_row_keys "
                "WHERE recipe_id = $1 AND investigation_id = $2 GROUP BY fingerprint",
                recipe_id,
                case,
            )
        return {r["fingerprint"]: int(r["loads"]) for r in rows}

    @asynccontextmanager
    async def hold_row_keys(
        self, recipe_id: str, case: str, *, wait_seconds: float = ROW_KEY_LOCK_WAIT_SECONDS
    ) -> AsyncIterator[None]:
        """Serialises the runs of one recipe into one case (ADR-127 decision 5), from the check of
        the kept keys to the write of the load's record and keys: two overlapping runs would both
        find the keys absent and both load.

        A Postgres **advisory lock** on (recipe, case), taken on a connection of its own that stays
        out of the pool for as long as it is held (`asyncpg.connect` with the store's DSN, closed in
        `finally`): the lock belongs to that session, so it is released when the block ends, when it
        fails, and when the process dies (the session ends). It must not take a pooled connection:
        every running load holds one for its whole run, and `add_record` and the ledger's other
        calls need the pool, so as many runs as the pool has connections would deadlock.

        Another holder is waited for up to `wait_seconds` and then refused
        (`RowKeyRunInProgress`), so a request is never held open for a long load. Holds one server
        connection per running load, outside the pool's limit, and needs session-level locks: a
        transaction-mode connection pooler in front of Postgres would break it."""
        loop = asyncio.get_running_loop()
        conn = await asyncpg.connect(dsn=self._dsn)
        taken = False
        try:
            deadline = loop.time() + wait_seconds
            while True:
                taken = bool(
                    await conn.fetchval(
                        "SELECT pg_try_advisory_lock(hashtext($1), hashtext($2))",
                        recipe_id,
                        case,
                    )
                )
                if taken:
                    break
                if loop.time() >= deadline:
                    raise RowKeyRunInProgress(recipe_id)
                await asyncio.sleep(_LOCK_POLL_SECONDS)
            yield
        finally:
            try:
                if taken:
                    await conn.execute(
                        "SELECT pg_advisory_unlock(hashtext($1), hashtext($2))", recipe_id, case
                    )
            finally:
                await conn.close()

    async def kept(self, recipe_id: str, case: str, keys: Sequence[str]) -> set[str]:
        """`engine.RowKeys`: this store is the one a dry run asks, as a `LoadSink` is for a run."""
        return await self.kept_row_keys(recipe_id, case, keys)

    async def release_row_keys(self, load_ids: Sequence[str]) -> int:
        """Releases every key these loads kept, so a rerun of their rows loads again (a revert,
        decision 6). By load id; idempotent: a second call finds none and returns 0."""
        if not load_ids:
            return 0
        async with self._pool.acquire() as conn:
            status = await conn.execute(
                "DELETE FROM loaded_row_keys WHERE load_id = ANY($1::text[])", list(load_ids)
            )
        return int(status.split()[-1])

    async def add_geometries(self, run_id: str, load_id: str, refs: list[str]) -> None:
        """Records the geometry refs a load is about to insert, against that load's record."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE recipe_runs SET load_records = ("
                "SELECT jsonb_agg(CASE WHEN rec->>'load_id' = $2 "
                "THEN jsonb_set(rec, '{created_geometry_refs}', $3::jsonb) ELSE rec END) "
                "FROM jsonb_array_elements(load_records) AS rec) "
                "WHERE run_id = $1 AND load_records IS NOT NULL",
                run_id,
                load_id,
                json.dumps(refs),
            )

    async def add_rule_writes(
        self,
        run_id: str,
        load_id: str,
        *,
        node_ids: list[str],
        created_edge_ids: list[str],
        merged_edge_ids: list[str],
    ) -> None:
        """Adds what an alert raised after a load's commit wrote to that load's record, in the
        lists the commit-time record keeps (created and merged apart)."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE recipe_runs SET load_records = ("
                "SELECT jsonb_agg(CASE WHEN rec->>'load_id' = $2 THEN rec || jsonb_build_object("
                "'created_node_ids', COALESCE(rec->'created_node_ids', '[]'::jsonb) || $3::jsonb, "
                "'created_edge_ids', COALESCE(rec->'created_edge_ids', '[]'::jsonb) || $4::jsonb, "
                "'merged_edge_ids', COALESCE(rec->'merged_edge_ids', '[]'::jsonb) || $5::jsonb, "
                "'touched_edge_ids', COALESCE(rec->'touched_edge_ids', '[]'::jsonb) "
                "|| $4::jsonb || $5::jsonb) ELSE rec END) "
                "FROM jsonb_array_elements(load_records) AS rec) "
                "WHERE run_id = $1 AND load_records IS NOT NULL",
                run_id,
                load_id,
                json.dumps(node_ids),
                json.dumps(created_edge_ids),
                json.dumps(merged_edge_ids),
            )

    async def mark_uncovered(self, run_id: str, load_id: str) -> None:
        """Says on a load's record that a stage fed by it wrote elements no record covers."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE recipe_runs SET load_records = ("
                "SELECT jsonb_agg(CASE WHEN rec->>'load_id' = $2 "
                "THEN jsonb_set(rec, '{uncovered_writes}', 'true'::jsonb) ELSE rec END) "
                "FROM jsonb_array_elements(load_records) AS rec) "
                "WHERE run_id = $1 AND load_records IS NOT NULL",
                run_id,
                load_id,
            )

    async def load_record(self, load_id: str) -> LoadRecord | None:
        """The record of the load with this id, or `None` for a load the ledger has no record of
        (one from before records were kept, or one that never finished). For the revert; never read
        by a route."""
        async with self._pool.acquire() as conn:
            kept = await conn.fetchval(
                "SELECT rec FROM recipe_runs, jsonb_array_elements(load_records) AS rec "
                "WHERE load_records IS NOT NULL AND rec->>'load_id' = $1 LIMIT 1",
                load_id,
            )
        return None if kept is None else LoadRecord.model_validate_json(kept)

    async def records_with_prefix(self, prefix: str) -> list[LoadRecord]:
        """The records whose load id starts with `prefix`, oldest first: a pipeline run's branches
        are `<run>:<source node>`, so `"<run>:"` finds every one of that run and no other (`run1:`
        does not match `run10:`). For the revert."""
        async with self._pool.acquire() as conn:
            kept = await conn.fetch(
                "SELECT rec FROM recipe_runs, jsonb_array_elements(load_records) AS rec "
                "WHERE load_records IS NOT NULL AND starts_with(rec->>'load_id', $1) "
                "ORDER BY started_at, rec->>'load_id'",
                prefix,
            )
        return [LoadRecord.model_validate_json(r["rec"]) for r in kept]

    async def unreverted_loads(self, case: str, recipe_ids: Sequence[str]) -> list[LoadRecord]:
        """The case's loads of these recipes whose record is not reverted, newest first (by load
        id, a ULID), **without their id lists** (ADR-127 Amendment 23, "The runs" and "The reset"):
        a yes or no about a file ("is it loaded already?") and the order a reset reverts in, neither
        of which needs the ids of a million-row file's elements, which a revert reads for itself
        (`load_record`). For the Prison Intelligence seed; never read by a route. A pipeline run's
        branches are each a record. No recipe gives no loads, without asking the ledger."""
        if not recipe_ids:
            return []
        async with self._pool.acquire() as conn:
            kept = await conn.fetch(
                "SELECT rec - $3::text[] AS rec FROM recipe_runs, "
                "jsonb_array_elements(load_records) AS rec "
                "WHERE load_records IS NOT NULL AND investigation_id = $1 "
                "AND recipe_id = ANY($2::text[]) AND rec->>'reverted_at' IS NULL "
                "ORDER BY rec->>'load_id' DESC",
                case,
                list(recipe_ids),
                list(_ID_LISTS),
            )
        return [LoadRecord.model_validate_json(r["rec"]) for r in kept]

    async def releases_of(self, load_id: str) -> list[LoadRecord]:
        """The records of the releases of held rows that were held by `load_id`, reverted or not.
        For the revert's cascade."""
        async with self._pool.acquire() as conn:
            kept = await conn.fetch(
                "SELECT rec FROM recipe_runs, jsonb_array_elements(load_records) AS rec "
                "WHERE load_records IS NOT NULL AND rec->>'released_from' = $1 "
                "ORDER BY started_at, rec->>'load_id'",
                load_id,
            )
        return [LoadRecord.model_validate_json(r["rec"]) for r in kept]

    async def records_merging(
        self, node_ids: Sequence[str], edge_ids: Sequence[str]
    ) -> list[LoadRecord]:
        """The unreverted records that list one of these nodes in `merged_node_ids` or one of these
        links in `merged_edge_ids` (the jsonb `?|` operator: any element equal to any of the ids).
        For the revert, which refuses while a later load merged into what it would take back."""
        if not node_ids and not edge_ids:
            return []
        async with self._pool.acquire() as conn:
            kept = await conn.fetch(
                "SELECT rec FROM recipe_runs, jsonb_array_elements(load_records) AS rec "
                "WHERE load_records IS NOT NULL AND rec->>'reverted_at' IS NULL AND ("
                "COALESCE(rec->'merged_node_ids', '[]'::jsonb) ?| $1::text[] "
                "OR COALESCE(rec->'merged_edge_ids', '[]'::jsonb) ?| $2::text[]) "
                "ORDER BY started_at, rec->>'load_id'",
                list(node_ids),
                list(edge_ids),
            )
        return [LoadRecord.model_validate_json(r["rec"]) for r in kept]

    async def mark_reverted(self, load_id: str, *, reverted_by: str, at: datetime) -> None:
        """Marks the load's record reverted (`reverted_at`, `reverted_by`), in the run row that
        holds it; the other records of that row are kept as they are. A load the ledger holds no
        record of is an error, never a quiet no-op: a revert that thought it had marked one would
        be refused nothing on its rerun. Marking a record already marked marks it again, with the
        later time."""
        async with self._pool.acquire() as conn:
            marked = await conn.execute(
                "UPDATE recipe_runs SET load_records = ("
                "SELECT jsonb_agg(CASE WHEN rec->>'load_id' = $1 THEN rec || "
                "jsonb_build_object('reverted_at', $2::text, 'reverted_by', $3::text) "
                "ELSE rec END ORDER BY ord) "
                "FROM jsonb_array_elements(load_records) WITH ORDINALITY AS t(rec, ord)) "
                "WHERE load_records IS NOT NULL AND EXISTS ("
                "SELECT 1 FROM jsonb_array_elements(load_records) AS r WHERE r->>'load_id' = $1)",
                load_id,
                at.isoformat(),
                reverted_by,
            )
        if marked == "UPDATE 0":
            raise KeyError(f"the ledger holds no record of load {load_id!r}")

    async def fail(
        self,
        run_id: str,
        *,
        failure: str,
        now: datetime,
        markings: Sequence[Handling] = (),
    ) -> None:
        """Marks the run failed. `markings` are those of the loads that committed before it failed
        (the sink sees each committed report), which the run's counts include; none committed
        stores none, and the run reads as the source's marking alone, as a running run does
        (ADR-127 Amendment 26)."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE recipe_runs SET outcome = 'failed', finished_at = $2, failure = $3, "
                "row_markings = $4::jsonb WHERE run_id = $1",
                run_id,
                now,
                failure,
                json.dumps([m.model_dump(mode="json") for m in markings]) if markings else None,
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
        counts_toward_pause: bool = True,
        source_file: str | None = None,
    ) -> str:
        """A slot that did not run, and why (decisions 2–4)."""
        if outcome not in _NOT_RUN:
            raise ValueError(f"{outcome!r} is not an outcome for a slot that did not run")
        run_id = new_id()
        await self._insert(
            run_id, recipe_id, recipe_version, investigation_id, trigger, slot, run_as, source,
            started_at=now, finished_at=now, outcome=outcome, failure=failure,
            source_file=source_file,
        )  # fmt: skip
        if not counts_toward_pause:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE recipe_runs SET counts_toward_pause = FALSE WHERE run_id = $1", run_id
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
        source_file: str | None = None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO recipe_runs (run_id, recipe_id, recipe_version, investigation_id, "
                "trigger, slot, run_as, source_handling, started_at, finished_at, outcome, "
                "failure, source_file) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10, $11, $12, $13)",
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
                source_file,
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

    async def watched_files(self, recipe_id: str) -> set[str]:
        """Every file the recipe's folder watch has taken, whatever came of it (Amendment 4)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT source_file FROM recipe_runs WHERE recipe_id = $1 "
                "AND trigger = 'watch' AND source_file IS NOT NULL",
                recipe_id,
            )
        return {row["source_file"] for row in rows}

    async def refusals_in_a_row(self, recipe_id: str) -> int:
        """How many of the recipe's latest scheduled or watched runs were refused, back to the last
        that was not (decision 3: three pause the schedule). A refusal that does not count toward
        the pause (Amendment 3: the identity provider unreachable) is passed over — neither counted
        nor ending the run of refusals."""
        async with self._pool.acquire() as conn:
            outcomes = await conn.fetch(
                "SELECT outcome, counts_toward_pause FROM recipe_runs WHERE recipe_id = $1 "
                "AND trigger IN ('schedule', 'watch') "
                "ORDER BY started_at DESC, run_id DESC LIMIT 50",
                recipe_id,
            )
        count = 0
        for row in outcomes:
            if row["outcome"] == "refused" and not row["counts_toward_pause"]:
                continue
            if row["outcome"] != "refused":
                break
            count += 1
        return count
