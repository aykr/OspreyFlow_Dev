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
import functools
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from ontology.handling import HandlingScheme
from ports.graph import GraphPort
from schemas.analytics import EventRecord
from schemas.domain import EdgeWrite, NodeWrite, OntologySchema, Principal, SourceRef, TxId
from schemas.staging import FuzzyMatchStep, SqlStep, StagingStep
from schemas.ingest import (
    ExpertStepDisclosure,
    LoadReport,
    Recipe,
    RejectionRecord,
    RejectionRef,
    StagingStepCount,
)

from .engine import DryRunResult, RowKeys, dry_run_recipe, run_recipe
from .staging import ObjectStorageConfig
from .staging_catalogue import (
    StagedRef,
    StagedTable,
    StagingError,
    StagingRejection,
    StagingResult,
    map_input,
    read_staged_table,
    run_staging,
    stage_sources_and_lists,
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
    #: ADR-140 decision 16: what each expert step disclosed, as the run report says it.
    expert_steps: list[ExpertStepDisclosure] = field(default_factory=list)


def staging_rejection_record(rejection: StagingRejection) -> RejectionRecord:
    """A row a step refused, as the load report lists rejections. `row_index` is the refused row's
    own position in its own source, and the reason names that source (and, for a Join, the side),
    the step and the cause, never a value: a Join's right-side row is named as a row of the right
    table, never mistaken for a row of the left. Nothing of the row is in `sample`, so it carries
    no marking (ADR-127 Amendment 26). `refs` name every row it came from, by table, row and load
    (ADR-140 Amendment 12), never by key (rule 7)."""
    first = rejection.refs[0]
    side = f"{rejection.side} side, " if rejection.side else ""
    return RejectionRecord(
        row_index=first.row_index,
        reason=(
            f"staging step {rejection.step} ({side}{first.source} row {first.row_index}): "
            f"{rejection.reason}"
        ),
        sample="",
        refs=[
            RejectionRef(
                table=ref.source, row_index=ref.row_index, load_id=ref.load_id, side=rejection.side
            )
            for ref in rejection.refs
        ],
    )


def map_rejection_record(
    record: RejectionRecord, table: StagedTable | str
) -> RejectionRecord:
    """A row Map refused in a staged run: its `row_index` is its position in the staged table Map
    read, so the reason names that table, never leaving it to be mistaken for a source row. Its
    `refs` name that row of the staged table, then each source row it came from (Amendment 12)."""
    name = table if isinstance(table, str) else table.name
    refs = [RejectionRef(table=name, row_index=record.row_index)]
    if isinstance(table, StagedTable) and 0 <= record.row_index < len(table.rows):
        refs.extend(
            RejectionRef(table=r.source, row_index=r.row_index, load_id=r.load_id)
            for r in table.rows[record.row_index].refs
        )
    return record.model_copy(
        update={
            "reason": f"staged table {name} row {record.row_index}: {record.reason}",
            "refs": refs,
        }
    )


def expert_disclosures(steps: Sequence[StagingStep] | None) -> list[ExpertStepDisclosure]:
    """ADR-140 decision 16 and brief §5.3–5.4: what every run report, and Test, says of each expert
    step, in words: the SQL step's summary and SELECT; the fuzzy match's tables, comparisons and
    threshold, and the SAME_AS it writes, inferred and never a merge. Settings, never a row's value."""
    found: list[ExpertStepDisclosure] = []
    for step in steps or []:
        if isinstance(step, SqlStep):
            found.append(
                ExpertStepDisclosure(
                    step=step.id, kind="sql", label=step.label, summary=step.summary,
                    select=step.select, reads=list(step.inputs),
                )  # fmt: skip
            )
        elif isinstance(step, FuzzyMatchStep):
            found.append(
                ExpertStepDisclosure(
                    step=step.id,
                    kind="fuzzy_match",
                    label=step.label,
                    reads=[step.left, step.right],
                    compares=[f"{c.left} ≈ {c.right} by {c.method}" for c in step.compare]
                    + [f"only pairs agreeing on {b.method} of {b.left} and {b.right}"
                       for b in step.block_on],  # fmt: skip
                    threshold=step.threshold,
                    same_as=[step.same_as.left, step.same_as.right],
                )
            )
    return found


def step_counts(staging: StagingResult) -> list[StagingStepCount]:
    """Each step's counts, in run order, as the load report carries them (Amendment 12)."""
    return [StagingStepCount.model_validate(asdict(report)) for report in staging.reports]


def _stage(
    recipe: Recipe,
    sources: Mapping[str, StagedTable],
    lists: Mapping[str, StagedTable],
    dataset_id: str,
    subscribed: Collection[str],
    may_read: Callable[[StagedRef], bool] | None = None,
) -> StagingResult:
    if not recipe.staging:
        raise StagingError([f"recipe {recipe.id!r} has no staging steps"])
    return run_staging(
        recipe.staging,
        sources=sources,
        lists=lists,
        dataset_id=dataset_id,
        subscribed=subscribed,
        may_read=may_read,
    )


@dataclass
class PreparedStaging:
    """A staged load up to Map (Amendment 12): the steps run, each step's table written to staged
    Parquet, and the last read back. `rows` and `refs` are what Map reads; `stage_raw` writes the
    sources' raw rows and the lists' rows, which the engine calls after its own refusals."""

    staging: StagingResult
    table: StagedTable
    rows: list[dict[str, str]]
    refs: dict[int, tuple[SourceRef, ...]]
    paths: dict[str, str]
    rows_staged: int
    parquet_bytes: int
    rows_read: int
    stage_raw: Callable[[], object]
    #: The recipe's steps, for the run report's disclosure of its expert steps.
    steps: Sequence[StagingStep] = ()


async def prepare_staged_load(
    recipe: Recipe,
    *,
    sources: Mapping[str, StagedTable],
    lists: Mapping[str, StagedTable],
    dataset_id: str,
    subscribed: Collection[str] = (),
    load_id: str,
    storage: ObjectStorageConfig,
    may_read: Callable[[StagedRef], bool] | None = None,
) -> PreparedStaging:
    """`may_read` (ADR-140 decision 12): whether the person the run is for may read a source row;
    a SQL step's tables hold only those rows (`run_staging`)."""
    staging = await asyncio.to_thread(
        _stage, recipe, sources, lists, dataset_id, subscribed, may_read
    )
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
    return PreparedStaging(
        staging=staging,
        table=table,
        rows=rows,
        refs=refs,
        paths=paths,
        rows_staged=rows_staged,
        parquet_bytes=parquet_bytes,
        # "The rows it read" (ADR-110 Amendment 12) are the rows the sources gave, not the rows of
        # the table Map read, which staging may have joined, filtered or folded.
        rows_read=sum(len(t.rows) for t in sources.values()),
        # Each source's rows are the raw rows of the load that read them, and each list's rows are
        # kept at its version, so every ref names a row in a file that exists; never the table Map
        # reads. Run by the engine after its own refusals, as a plain run's raw staging is.
        stage_raw=functools.partial(
            stage_sources_and_lists, sources, staging.lists_read, storage=storage
        ),
        steps=list(recipe.staging or []),
    )


def finish_staged_report(report: LoadReport, prepared: PreparedStaging) -> None:
    """The load report of a staged run: the steps' rejections before Map's, each with its refs;
    the sources' rows as rows read; and each step's counts (Amendment 12)."""
    report.rejections = [
        *(staging_rejection_record(r) for r in prepared.staging.rejections),
        *(map_rejection_record(r, prepared.table) for r in report.rejections),
    ]
    report.rows_read = prepared.rows_read
    report.staging_steps = step_counts(prepared.staging)
    report.expert_steps = expert_disclosures(prepared.steps)


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
    may_read: Callable[[StagedRef], bool] | None = None,
    **engine: Any,
) -> StagedLoad:
    storage = storage or ObjectStorageConfig.from_env()
    prepared = await prepare_staged_load(
        recipe,
        sources=sources,
        lists=lists,
        dataset_id=dataset_id,
        subscribed=subscribed,
        load_id=load_id,
        storage=storage,
        may_read=may_read,
    )
    report, events = await run_recipe(
        recipe,
        prepared.rows,
        graph=graph,
        ontology=ontology,
        tx=tx,
        principal=principal,
        load_id=load_id,
        investigation_scope=investigation_scope,
        source=prepared.table.name,
        storage=storage,
        scheme=scheme,
        row_keys=row_keys,
        written=written,
        row_refs=prepared.refs,
        stage_raw=prepared.stage_raw,
        **engine,
    )
    finish_staged_report(report, prepared)
    return StagedLoad(
        report,
        events,
        prepared.staging,
        prepared.paths,
        prepared.rows_staged,
        prepared.parquet_bytes,
    )


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
        *(map_rejection_record(r, staging.output) for r in result.rejections),
    ]
    result.rows_read = sum(len(table.rows) for table in sources.values())
    return StagedTest(result, staging, expert_disclosures(recipe.staging))
