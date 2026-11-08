"""A recipe with `staging:` steps, run or tested (ADR-140 decision 11; the redesign's phase 7).

`run_staged_recipe` (the load) and `dry_run_staged_recipe` (Test) do the same thing up to Map:
`staging_catalogue.run_staging` over the source tables and lists, then Map over the last table with
each row's refs, so the element records every source row it came from. They differ only where the
engine's own `run_recipe` and `dry_run_recipe` differ, so **Test and the load reject the same
rows** (the phase's test; `tests/ingest/test_staged_run.py`): a row a step refused is a rejection
of both, in the same words.

The load writes every step's table to staged Parquet (`<bucket>/loads/<load_id>/staged/`) and Map
reads the last one back from what was written, as `run_recipe` reads its resolved rows back, so a
table Parquet cannot hold fails here and not silently. Test writes nothing.
"""

from __future__ import annotations

import asyncio
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

from ontology.handling import HandlingScheme
from ports.graph import GraphPort
from schemas.analytics import EventRecord
from schemas.domain import EdgeWrite, NodeWrite, OntologySchema, Principal, TxId
from schemas.ingest import LoadReport, Recipe, RejectionRecord

from .engine import DryRunResult, RowKeys, dry_run_recipe, run_recipe
from .staging import ObjectStorageConfig
from .staging_catalogue import (
    StagedTable,
    StagingError,
    StagingRejection,
    StagingResult,
    map_input,
    read_staged_table,
    run_staging,
    stage_raw_sources,
    stage_table_counted,
)


@dataclass
class StagedLoad:
    report: LoadReport
    events: list[EventRecord]
    staging: StagingResult
    #: Each step's staged Parquet, by step id.
    staged_paths: dict[str, str]
    #: The run's metering for staging (ADR-110 Amendment 12; `RunMetering.rows_staged` and
    #: `parquet_bytes`): the rows every step's table holds, and the bytes their Parquet took.
    rows_staged: int = 0
    parquet_bytes: int = 0


@dataclass
class StagedTest:
    result: DryRunResult
    staging: StagingResult


def staging_rejection_record(rejection: StagingRejection) -> RejectionRecord:
    """A row a step refused, as the load report lists rejections. `row_index` is the refused row's
    own position in its own source, and the reason names that source (and, for a Join, the side),
    the step and the cause, never a value: a Join's right-side row is named as a row of the right
    table, never mistaken for a row of the left. Nothing of the row is in `sample`, so it carries
    no marking (ADR-127 Amendment 26)."""
    first = rejection.refs[0]
    side = f"{rejection.side} side, " if rejection.side else ""
    return RejectionRecord(
        row_index=first.row_index,
        reason=(
            f"staging step {rejection.step} ({side}{first.source} row {first.row_index}): "
            f"{rejection.reason}"
        ),
        sample="",
    )


def _stage(
    recipe: Recipe,
    sources: Mapping[str, StagedTable],
    lists: Mapping[str, StagedTable],
    dataset_id: str,
    subscribed: Collection[str],
) -> StagingResult:
    if not recipe.staging:
        raise StagingError([f"recipe {recipe.id!r} has no staging steps"])
    return run_staging(
        recipe.staging,
        sources=sources,
        lists=lists,
        dataset_id=dataset_id,
        subscribed=subscribed,
    )


async def run_staged_recipe(
    recipe: Recipe,
    *,
    sources: Mapping[str, StagedTable],
    lists: Mapping[str, StagedTable],
    dataset_id: str,
    subscribed: Collection[str] = (),
    graph: GraphPort,
    ontology: OntologySchema,
    tx: TxId,
    principal: Principal,
    load_id: str,
    investigation_scope: str,
    storage: ObjectStorageConfig | None = None,
    scheme: HandlingScheme | None = None,
    row_keys: RowKeys | None = None,
    written: list[NodeWrite | EdgeWrite] | None = None,
    **engine: Any,
) -> StagedLoad:
    storage = storage or ObjectStorageConfig.from_env()
    staging = await asyncio.to_thread(_stage, recipe, sources, lists, dataset_id, subscribed)
    # Each source's rows are the raw rows of the load that read them (`loads/<its load_id>/
    # raw.parquet`), so a ref's (source, row, load_id) names a row in a file that exists; never the
    # table Map reads, so `run_recipe` is told not to write its own raw rows.
    await asyncio.to_thread(stage_raw_sources, sources, storage=storage)
    paths: dict[str, str] = {}
    rows_staged = parquet_bytes = 0
    for step in recipe.staging or []:
        paths[step.id], size = await asyncio.to_thread(
            stage_table_counted, staging.tables[step.id], storage=storage, load_id=load_id
        )
        rows_staged += len(staging.tables[step.id].rows)
        parquet_bytes += size
    table = await asyncio.to_thread(read_staged_table, paths[staging.output.name], storage=storage)
    rows, refs = map_input(table)
    report, events = await run_recipe(
        recipe,
        rows,
        graph=graph,
        ontology=ontology,
        tx=tx,
        principal=principal,
        load_id=load_id,
        investigation_scope=investigation_scope,
        source=table.name,
        storage=storage,
        scheme=scheme,
        row_keys=row_keys,
        written=written,
        row_refs=refs,
        stage_raw=False,
        **engine,
    )
    report.rejections = [
        *(staging_rejection_record(r) for r in staging.rejections),
        *report.rejections,
    ]
    # "The rows it read" (ADR-110 Amendment 12) are the rows the sources gave, not the rows of the
    # table Map read, which staging may have joined, filtered or folded.
    report.rows_read = sum(len(table.rows) for table in sources.values())
    return StagedLoad(report, events, staging, paths, rows_staged, parquet_bytes)


async def dry_run_staged_recipe(
    recipe: Recipe,
    *,
    sources: Mapping[str, StagedTable],
    lists: Mapping[str, StagedTable],
    dataset_id: str,
    subscribed: Collection[str] = (),
    graph: GraphPort,
    ontology: OntologySchema,
    principal: Principal,
    scheme: HandlingScheme | None = None,
    row_keys: RowKeys | None = None,
    investigation_scope: str | None = None,
) -> StagedTest:
    staging = _stage(recipe, sources, lists, dataset_id, subscribed)
    rows, refs = map_input(staging.output)
    result = await dry_run_recipe(
        recipe,
        rows,
        graph=graph,
        ontology=ontology,
        principal=principal,
        source=staging.output.name,
        scheme=scheme,
        row_keys=row_keys,
        investigation_scope=investigation_scope,
        row_refs=refs,
    )
    result.rejections = [
        *(staging_rejection_record(r) for r in staging.rejections),
        *result.rejections,
    ]
    result.rows_read = sum(len(table.rows) for table in sources.values())
    return StagedTest(result, staging)
