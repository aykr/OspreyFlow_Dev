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
    stage_table,
)


@dataclass
class StagedLoad:
    report: LoadReport
    events: list[EventRecord]
    staging: StagingResult
    #: Each step's staged Parquet, by step id.
    staged_paths: dict[str, str]


@dataclass
class StagedTest:
    result: DryRunResult
    staging: StagingResult


def staging_rejection_record(rejection: StagingRejection) -> RejectionRecord:
    """A row a step refused, as the load report lists rejections. The reason names the step and the
    cause, never a value; nothing of the row is in `sample`, so it carries no marking (ADR-127
    Amendment 26)."""
    return RejectionRecord(
        row_index=rejection.refs[0].row_index,
        reason=f"staging step {rejection.step}: {rejection.reason}",
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
        recipe.staging, sources=sources, lists=lists, dataset_id=dataset_id, subscribed=subscribed
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
    paths: dict[str, str] = {}
    for step in recipe.staging or []:
        paths[step.id] = await asyncio.to_thread(
            stage_table, staging.tables[step.id], storage=storage, load_id=load_id
        )
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
        **engine,
    )
    report.rejections = [
        *(staging_rejection_record(r) for r in staging.rejections),
        *report.rejections,
    ]
    return StagedLoad(report, events, staging, paths)


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
    return StagedTest(result, staging)
