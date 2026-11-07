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
from collections.abc import AsyncIterator, Collection, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, get_args

import asyncpg
from pydantic import BaseModel, Field, model_validator
from services.ingest.engine import RowKeyRunInProgress

from conduit_common.identity import new_id
from schemas.domain import Handling
from schemas.ingest import (
    LoadRecord,
    LoadReport,
    PipelineRunReport,
    RowElements,
    RunMetering,
    SourceWatermark,
)

#: `source_refresh` (ADR-110 Amendment 6 point 5): a run started by its source's refresh policy.
RunTrigger = Literal["manual", "schedule", "watch", "release", "source_refresh"]
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
-- ADR-110 Amendment 8 point 2: what each kept row wrote, by stored id. NULL for a key kept
-- before it, which a full snapshot's withdrawal leaves in place and counts.
ALTER TABLE loaded_row_keys ADD COLUMN IF NOT EXISTS node_ids TEXT[];
ALTER TABLE loaded_row_keys ADD COLUMN IF NOT EXISTS edge_ids TEXT[];
CREATE INDEX IF NOT EXISTS loaded_row_keys_node_ids_idx ON loaded_row_keys USING gin (node_ids);
CREATE INDEX IF NOT EXISTS loaded_row_keys_edge_ids_idx ON loaded_row_keys USING gin (edge_ids);
-- Amendment 8 points 4 and 5: the keys a full snapshot withdrew, moved here whole with the load
-- that withdrew them, so a row that comes back is kept again in `loaded_row_keys` and the
-- refresh's revert can tell that it has.
CREATE TABLE IF NOT EXISTS withdrawn_row_keys (
    recipe_id TEXT NOT NULL,
    investigation_id TEXT NOT NULL,
    row_key TEXT NOT NULL,
    load_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL DEFAULT '',
    node_ids TEXT[],
    edge_ids TEXT[],
    withdrawn_by_load TEXT NOT NULL,
    PRIMARY KEY (recipe_id, investigation_id, row_key)
);
CREATE INDEX IF NOT EXISTS withdrawn_row_keys_by_idx ON withdrawn_row_keys (withdrawn_by_load);
CREATE INDEX IF NOT EXISTS withdrawn_row_keys_load_idx ON withdrawn_row_keys (load_id);
CREATE INDEX IF NOT EXISTS withdrawn_row_keys_node_ids_idx
    ON withdrawn_row_keys USING gin (node_ids);
CREATE INDEX IF NOT EXISTS withdrawn_row_keys_edge_ids_idx
    ON withdrawn_row_keys USING gin (edge_ids);
"""

#: The id lists of a load's record an element is held by (`elements_in_other_records`).
_RECORD_NODE_LISTS = ("created_node_ids", "merged_node_ids", "rule_node_ids")
_RECORD_EDGE_LISTS = ("touched_edge_ids", "created_edge_ids", "merged_edge_ids")


@dataclass(frozen=True)
class KeptRow:
    """A kept key and what its row wrote (ADR-110 Amendment 8 point 2); `None` for a key kept
    before rows recorded it."""

    row_key: str
    load_id: str
    node_ids: tuple[str, ...] | None
    edge_ids: tuple[str, ...] | None

#: The record's own id lists: what `unreverted_loads` leaves out, since it answers a question about
#: a load, not about its elements.
_ID_LISTS = (
    "created_node_ids",
    "rule_node_ids",
    "touched_edge_ids",
    "created_edge_ids",
    "merged_edge_ids",
    "merged_node_ids",
    "created_geometry_refs",
    "withdrawn_node_ids",
    "withdrawn_edge_ids",
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
-- The trigger's CHECK is the column's own, so a ledger made before a trigger was added refuses it:
-- connecting puts the current list back (ADR-110 Amendment 6, `source_refresh`).
ALTER TABLE recipe_runs DROP CONSTRAINT IF EXISTS recipe_runs_trigger_check;
ALTER TABLE recipe_runs ADD CONSTRAINT recipe_runs_trigger_check
    CHECK (trigger IN ({", ".join(f"'{t}'" for t in get_args(RunTrigger))}));
{_ADD_LOAD_RECORDS}
{_ADD_ROW_MARKINGS}
-- ADR-110 Amendment 6 point 9: what a succeeded run cost (`RunMetering`); NULL before it.
ALTER TABLE recipe_runs ADD COLUMN IF NOT EXISTS metering JSONB;
{_LOADED_ROW_KEYS}
"""

_COLUMNS = (
    "run_id, recipe_id, recipe_version, investigation_id, trigger, slot, run_as, source_handling, "
    "started_at, finished_at, outcome, rows_read, nodes_created, nodes_referenced, edges_created, "
    "rows_rejected, rows_held, load_id, failure, source_file, row_markings, metering"
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
    #: ADR-110 Amendment 6 point 9: a succeeded run's metering; `None` for any other, and for one
    #: from before. Counts of the run's own: withheld with the others by every route.
    metering: RunMetering | None = None

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
    metered = data.pop("metering")
    data["metering"] = None if metered is None else RunMetering.model_validate_json(metered)
    return RecipeRun.model_validate(data)


def _ids(elements: RowElements | None, field: str) -> list[str] | None:
    return None if elements is None else list(getattr(elements, field))


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
                "rows_rejected = $7, rows_held = $8, load_id = $9, row_markings = $10::jsonb, "
                "metering = $11::jsonb WHERE run_id = $1",
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
                None if report.metering is None else report.metering.model_dump_json(),
            )

    async def add_record(
        self,
        run_id: str,
        record: LoadRecord,
        *,
        row_keys: Sequence[str] = (),
        row_key_fingerprint: str = "",
        row_elements: Mapping[str, RowElements] | None = None,
        withdrawn_row_keys: Sequence[str] = (),
    ) -> None:
        """Appends a load's record to its run (ADR-127 decision 6), when the load's graph
        transaction commits and so before the run can `finish`: a run that fails afterwards still
        has the record a revert needs. A pipeline run appends one per branch.

        `row_keys` (decision 5) are kept for the record's recipe and case, with its load, **in the
        same transaction**: both land or neither does. The graph has committed already, so a crash
        between the two stores leaves rows loaded with neither (the run row stays `running`), and
        never a key for a row that did not load, nor a record whose keys were lost. A key already
        kept is left as it was.

        `row_elements` (ADR-110 Amendment 8 point 2) is what each key's row wrote, kept with it; a
        key it has no entry for records none. `withdrawn_row_keys` (points 4 and 5) are the keys of
        the record's recipe and case a full snapshot withdrew: moved to `withdrawn_row_keys` with
        the record's load, in the same transaction."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "UPDATE recipe_runs SET load_records = COALESCE(load_records, '[]'::jsonb) "
                "|| $2::jsonb WHERE run_id = $1",
                run_id,
                json.dumps([record.model_dump(mode="json")]),
            )
            keys = list(dict.fromkeys(row_keys))
            elements = row_elements or {}
            for start in range(0, len(keys), _KEY_CHUNK):
                chunk = keys[start : start + _KEY_CHUNK]
                # Each key's id lists as one JSON array of arrays (an array of arrays cannot be
                # ragged in Postgres): `null` for a key with no entry.
                nodes = [_ids(elements.get(k), "node_ids") for k in chunk]
                edges = [_ids(elements.get(k), "edge_ids") for k in chunk]
                await conn.execute(
                    "INSERT INTO loaded_row_keys "
                    "(recipe_id, investigation_id, row_key, load_id, fingerprint, node_ids, "
                    "edge_ids) "
                    "SELECT $1, $2, k.key, $4, $5, "
                    "CASE WHEN n.ids = 'null' THEN NULL ELSE "
                    "ARRAY(SELECT jsonb_array_elements_text(n.ids)) END, "
                    "CASE WHEN e.ids = 'null' THEN NULL ELSE "
                    "ARRAY(SELECT jsonb_array_elements_text(e.ids)) END "
                    "FROM unnest($3::text[]) WITH ORDINALITY AS k(key, i) "
                    "JOIN jsonb_array_elements($6::jsonb) WITH ORDINALITY AS n(ids, i) USING (i) "
                    "JOIN jsonb_array_elements($7::jsonb) WITH ORDINALITY AS e(ids, i) USING (i) "
                    "ON CONFLICT (recipe_id, investigation_id, row_key) DO NOTHING",
                    record.recipe_id,
                    record.investigation_id or "",
                    chunk,
                    record.load_id,
                    row_key_fingerprint,
                    json.dumps(nodes),
                    json.dumps(edges),
                )
            withdrawn = list(dict.fromkeys(withdrawn_row_keys))
            for start in range(0, len(withdrawn), _KEY_CHUNK):
                await conn.execute(
                    "WITH moved AS (DELETE FROM loaded_row_keys WHERE recipe_id = $1 "
                    "AND investigation_id = $2 AND row_key = ANY($3::text[]) RETURNING *) "
                    "INSERT INTO withdrawn_row_keys (recipe_id, investigation_id, row_key, "
                    "load_id, fingerprint, node_ids, edge_ids, withdrawn_by_load) "
                    "SELECT recipe_id, investigation_id, row_key, load_id, fingerprint, node_ids, "
                    "edge_ids, $4 FROM moved",
                    record.recipe_id,
                    record.investigation_id or "",
                    withdrawn[start : start + _KEY_CHUNK],
                    record.load_id,
                )

    async def dropped_row_keys(
        self, recipe_id: str, case: str, *, present: Collection[str]
    ) -> list[KeptRow]:
        """The keys the case keeps for the recipe that `present` (every key a full snapshot's rows
        carry) does not, each with its record (ADR-110 Amendment 8 point 3). A withdrawn key is not
        kept, so not dropped again. Every kept key is read and compared here: one pass over the
        (recipe, case) part of the primary key, unmeasured at a million keys."""
        dropped: list[KeptRow] = []
        async with self._pool.acquire() as conn, conn.transaction():
            async for row in conn.cursor(
                "SELECT row_key, load_id, node_ids, edge_ids FROM loaded_row_keys "
                "WHERE recipe_id = $1 AND investigation_id = $2 ORDER BY row_key",
                recipe_id,
                case,
            ):
                if row["row_key"] in present:
                    continue
                dropped.append(
                    KeptRow(
                        row_key=row["row_key"],
                        load_id=row["load_id"],
                        node_ids=None if row["node_ids"] is None else tuple(row["node_ids"]),
                        edge_ids=None if row["edge_ids"] is None else tuple(row["edge_ids"]),
                    )
                )
        return dropped

    async def elements_kept_by_other_rows(
        self,
        node_ids: Sequence[str],
        edge_ids: Sequence[str],
        *,
        recipe_id: str,
        case: str,
        excluding: Sequence[str],
        only_this_pipeline: bool = False,
    ) -> tuple[set[str], set[str]]:
        """Which of these nodes and links a kept row's record also names, of any recipe and any
        case, leaving out the (recipe, case) keys in `excluding` (the dropped ones). By the GIN
        indexes (`&&`). A withdrawn key keeps nothing. `only_this_pipeline`: the rows of
        `recipe_id` in `case` alone, which is all a snapshot's run may count (ADR-110 Amendment
        15: another pipeline's or another case's row keeps a link silently)."""
        own = " AND recipe_id = $2 AND investigation_id = $3" if only_this_pipeline else ""
        found: tuple[set[str], set[str]] = (set(), set())
        async with self._pool.acquire() as conn:
            for column, ids, into in (
                ("node_ids", node_ids, found[0]),
                ("edge_ids", edge_ids, found[1]),
            ):
                unique = list(dict.fromkeys(ids))
                for start in range(0, len(unique), _KEY_CHUNK):
                    chunk = unique[start : start + _KEY_CHUNK]
                    rows = await conn.fetch(
                        f"SELECT DISTINCT x FROM loaded_row_keys, unnest({column}) AS x "
                        f"WHERE {column} && $1::text[] AND x = ANY($1::text[]) "
                        "AND NOT (recipe_id = $2 AND investigation_id = $3 "
                        f"AND row_key = ANY($4::text[])){own}",
                        chunk,
                        recipe_id,
                        case,
                        list(excluding),
                    )
                    into.update(r["x"] for r in rows)
        return found

    async def elements_in_other_records(
        self,
        node_ids: Sequence[str],
        edge_ids: Sequence[str],
        *,
        excluding_loads: Sequence[str],
    ) -> tuple[set[str], set[str]]:
        """Which of these nodes and links an unreverted load's record lists (created, merged or a
        rule's), leaving out the loads in `excluding_loads`. Over every record (the jsonb `?|`
        operator), as `records_merging` asks."""
        nodes, edges = set(node_ids), set(edge_ids)
        if not nodes and not edges:
            return set(), set()
        every_list = " || ".join(
            f"COALESCE(rec->'{c}', '[]'::jsonb)" for c in (*_RECORD_NODE_LISTS, *_RECORD_EDGE_LISTS)
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT x FROM recipe_runs, jsonb_array_elements(load_records) AS rec, "
                f"jsonb_array_elements_text({every_list}) AS x "
                "WHERE load_records IS NOT NULL AND rec->>'reverted_at' IS NULL "
                "AND NOT (rec->>'load_id' = ANY($2::text[])) AND x = ANY($1::text[])",
                [*nodes, *edges],
                list(excluding_loads),
            )
        held = {r["x"] for r in rows}
        return held & nodes, held & edges

    async def withdrawn_keys_kept_again(self, load_id: str) -> int:
        """How many of the keys `load_id` withdrew are kept again by a later load: its revert is
        refused while any is (ADR-110 Amendment 8 point 5)."""
        async with self._pool.acquire() as conn:
            return int(
                await conn.fetchval(
                    "SELECT count(*) FROM withdrawn_row_keys w JOIN loaded_row_keys k "
                    "USING (recipe_id, investigation_id, row_key) WHERE w.withdrawn_by_load = $1",
                    load_id,
                )
            )

    async def restore_withdrawn_row_keys(self, load_id: str) -> int:
        """Moves the keys `load_id` withdrew back, each with the load that kept it and its record
        (the refresh's revert). Idempotent; a key kept again meanwhile is left where it is, which
        the revert refuses before it gets here."""
        async with self._pool.acquire() as conn:
            status = await conn.execute(
                "WITH moved AS (DELETE FROM withdrawn_row_keys w WHERE withdrawn_by_load = $1 "
                "AND NOT EXISTS (SELECT 1 FROM loaded_row_keys k WHERE k.recipe_id = w.recipe_id "
                "AND k.investigation_id = w.investigation_id AND k.row_key = w.row_key) "
                "RETURNING *) "
                "INSERT INTO loaded_row_keys (recipe_id, investigation_id, row_key, load_id, "
                "fingerprint, node_ids, edge_ids) "
                "SELECT recipe_id, investigation_id, row_key, load_id, fingerprint, node_ids, "
                "edge_ids FROM moved",
                load_id,
            )
        return int(status.split()[-1])

    async def watermark(
        self, recipe_id: str, case: str, source_id: str
    ) -> SourceWatermark | None:
        """The watermark an incremental refresh of `source_id` by this pipeline into this case reads
        from (ADR-110 Amendment 6 point 1): the one the latest unreverted load of a *succeeded* run
        reached. A failed run's is not kept, so the rows it did not finish are read again; a
        reverted load's is not, so the rows it took back are read again. Latest by the run's start:
        the executor's lock serialises a pipeline's runs. `None`: read every row."""
        async with self._pool.acquire() as conn:
            kept = await conn.fetchval(
                "SELECT rec->'watermark' FROM recipe_runs, "
                "jsonb_array_elements(load_records) AS rec "
                "WHERE load_records IS NOT NULL AND outcome = 'succeeded' "
                "AND rec->>'recipe_id' = $1 AND rec->>'investigation_id' = $2 "
                "AND rec->>'reverted_at' IS NULL AND rec->'watermark'->>'source_id' = $3 "
                "ORDER BY started_at DESC, rec->>'load_id' DESC LIMIT 1",
                recipe_id,
                case,
                source_id,
            )
        return None if kept is None else SourceWatermark.model_validate_json(kept)

    async def reads_past(self, load_id: str) -> int:
        """How many unreverted loads of later runs read the same source incrementally, for the same
        pipeline and case, past this load's watermark. The revert refuses while there is one: their
        watermark would leave this load's rows unread for good. No record, or one with no
        watermark: none."""
        async with self._pool.acquire() as conn:
            return int(
                await conn.fetchval(
                    "WITH me AS (SELECT r.started_at, mine.value AS mine FROM recipe_runs r, "
                    "jsonb_array_elements(r.load_records) AS mine "
                    "WHERE r.load_records IS NOT NULL AND mine.value->>'load_id' = $1 "
                    "AND jsonb_typeof(mine.value->'watermark') = 'object' "
                    "LIMIT 1) "
                    "SELECT count(*) FROM me, recipe_runs r, "
                    "jsonb_array_elements(r.load_records) AS rec "
                    "WHERE r.load_records IS NOT NULL AND r.started_at > me.started_at "
                    "AND rec->>'reverted_at' IS NULL "
                    "AND rec->>'recipe_id' = me.mine->>'recipe_id' "
                    "AND rec->>'investigation_id' = me.mine->>'investigation_id' "
                    "AND rec->'watermark'->>'source_id' = me.mine->'watermark'->>'source_id'",
                    load_id,
                )
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
                "SELECT fingerprint, count(DISTINCT load_id) AS loads FROM ("
                "SELECT fingerprint, load_id FROM loaded_row_keys "
                "WHERE recipe_id = $1 AND investigation_id = $2 UNION ALL "
                "SELECT fingerprint, load_id FROM withdrawn_row_keys "
                "WHERE recipe_id = $1 AND investigation_id = $2) AS kept GROUP BY fingerprint",
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
        async with self._pool.acquire() as conn, conn.transaction():
            status = await conn.execute(
                "DELETE FROM loaded_row_keys WHERE load_id = ANY($1::text[])", list(load_ids)
            )
            # A key these loads kept that a refresh withdrew is theirs too (ADR-110 Amendment 8
            # point 3): released with them, so the refresh's revert has nothing to restore.
            aside = await conn.execute(
                "DELETE FROM withdrawn_row_keys WHERE load_id = ANY($1::text[])", list(load_ids)
            )
        return int(status.split()[-1]) + int(aside.split()[-1])

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
        lists the commit-time record keeps (created and merged apart; its nodes in the rules' own
        list as well)."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE recipe_runs SET load_records = ("
                "SELECT jsonb_agg(CASE WHEN rec->>'load_id' = $2 THEN rec || jsonb_build_object("
                "'created_node_ids', COALESCE(rec->'created_node_ids', '[]'::jsonb) || $3::jsonb, "
                "'rule_node_ids', COALESCE(rec->'rule_node_ids', '[]'::jsonb) || $3::jsonb, "
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

    async def records_of_run(self, run_id: str) -> list[LoadRecord]:
        """The records a run of the ledger holds, by the run's own id (`recipe_runs.run_id`, the id
        the Studio lists a run by, which is not its load's), oldest first; none for an id that is no
        run. For the revert (build order step 15)."""
        async with self._pool.acquire() as conn:
            kept = await conn.fetch(
                "SELECT rec FROM recipe_runs, jsonb_array_elements(load_records) AS rec "
                "WHERE load_records IS NOT NULL AND run_id = $1 ORDER BY rec->>'load_id'",
                run_id,
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
                "AND trigger IN ('watch', 'source_refresh') AND source_file IS NOT NULL",
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
                "AND trigger IN ('schedule', 'watch', 'source_refresh') "
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
