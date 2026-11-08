"""A pipeline's staging steps in the Studio (ADR-140 Amendment 12, the redesign's phase 7b).

- **The gate** (`staging_gate`): the graph's rules for step nodes
  (`pipeline.staging_graph_violations`) and the catalogue's
  (`staging_catalogue.staging_rule_violations`) against the pipeline's source
  nodes and the dataset's lists, in their own words. The pipeline's save, Test, the preview and
  publish all ask it, so a drawer refuses what the save gate refuses, in the same words.
- **The sources** (`source_tables`): each source node's file, read through the same reader and
  confinement every source read passes, as a table named by the node's id. Each is read by a load
  of its own, `<the run's load>:<the node's id>`, as a pipeline's branches already are; the run's
  load id is new for every run, so no two runs ever share a raw file (L1.3's item 12, the
  check-then-write race on one source's raw rows, closed by construction).
- **The preview** (`preview_staging`, Q4 (a)): the steps up to one step, over the first ten rows of
  each source, with the reader's own rights (rule 3), writing nothing.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from services.ingest.pipeline import (
    pipeline_from_recipe,
    pipeline_rule_violations,
    staging_from_pipeline,
    staging_graph_violations,
    step_record_violations,
)
from services.ingest.profiler import profile_source
from services.ingest.reference_list_import import kept_lists, lists_for_run
from services.ingest.staged_run import staging_rejection_record, step_counts
from services.ingest.staging import ObjectStorageConfig
from services.ingest.staging_catalogue import (
    StagedTable,
    StagingError,
    run_staging,
    source_table,
    staging_rule_violations,
)

from ontology.handling import HandlingScheme
from schemas.dataset_model import ReferenceList
from schemas.domain import Principal
from schemas.ingest import (
    PipelineGraph,
    PipelineNode,
    PipelineNodeKind,
    StagingPreview,
    StagingPreviewInput,
    StudioRecipeDraft,
)
from schemas.staging import LookupStep, StagingStep, step_inputs

from .run_source import branch_location, topological
from .studio_map import resolve_source_handling
from .studio_profile import _read_rows, offered_to, sample_markings
from .target_models import TargetModelStore

#: Q4 (a): a drawer's live sample reads the first ten rows of each source, as Map's sample pages.
PREVIEW_ROWS = 10


@dataclass(frozen=True)
class StagedTestInputs:
    """What Test needs beyond the draft to run a staged pipeline (Amendment 12): the dataset's
    lists and the store their rows are kept in."""

    references: Sequence[ReferenceList]
    storage: ObjectStorageConfig


async def dataset_reference_lists(
    models: TargetModelStore | None, dataset_id: str | None, storage: ObjectStorageConfig
) -> list[ReferenceList]:
    """The lists a staging step's Lookup may read for a dataset (ADR-140 decision 4, Amendment
    12): those its live domain model refers to, by id, whose rows are kept for it, each at the
    highest version kept. None for a draft with no dataset or a dataset with no live model."""
    if models is None or not dataset_id:
        return []
    live = await models.live(dataset_id)
    if live is None:
        return []
    named = set(live.reference_lists)
    kept = await asyncio.to_thread(kept_lists, dataset_id, storage=storage)
    return [r for r in kept if r.id in named]


def source_nodes(pipeline: PipelineGraph) -> list[PipelineNode]:
    return [n for n in topological(pipeline) if n.kind is PipelineNodeKind.SOURCE]


def staging_gate(
    pipeline: PipelineGraph, *, references: Sequence[ReferenceList], dataset_id: str | None
) -> list[str]:
    """Every refusal of the pipeline's steps, in words; empty for a pipeline with none, or none
    wrong. A dataset-less draft has no lists, so a Lookup is refused as naming none."""
    problems = staging_graph_violations(pipeline)
    if problems:
        return problems
    steps = staging_from_pipeline(pipeline)
    if not steps:
        return []
    return staging_rule_violations(
        steps,
        sources=[n.id for n in source_nodes(pipeline)],
        lists=references,
        dataset_id=dataset_id or "",
    )


def sources_not_offered(pipeline: PipelineGraph, dataset_id: str | None) -> list[str]:
    """Each source node naming a file that is not one of the recipe's dataset's files in the
    ingest folder (`studio_profile._confined`), as words: the save gate's refusal, so a pipeline
    never holds a file its case could not pick (the orchestrator's review of L1.4, rules 3 and 4:
    a source node naming another dataset's uploaded file was previewed and loaded). A node naming
    no file reads the draft's, which Connect judged."""
    return [
        f"source '{node.label}' reads a file that is not one of this dataset's files in the "
        "ingest folder: choose it from the dataset's files, or upload it"
        for node in source_nodes(pipeline)
        if node.config.get("source_location")
        and not offered_to(str(node.config["source_location"]), dataset_id)
    ]


def _source_draft(draft: StudioRecipeDraft, node: PipelineNode) -> StudioRecipeDraft:
    """The draft as one source node reads its file: the node's own connector and file when it
    names them, else the draft's."""
    update = {
        key: node.config[key]
        for key in ("connector_profile", "source_location")
        if node.config.get(key)
    }
    return draft.model_copy(update=update) if update else draft


@dataclass
class SourceRows:
    tables: dict[str, StagedTable]
    #: Each source's rows as read, by node id, for judging each row's marking.
    raw: dict[str, list[dict[str, str]]]


def source_tables(
    draft: StudioRecipeDraft,
    pipeline: PipelineGraph,
    *,
    load_id: str,
    limit: int | None = None,
    location: str | None = None,
) -> SourceRows:
    """Each source node's rows as a table named by its id, read by its own load
    (`<load_id>:<node id>`); the first `limit` rows only, when given. `location`: a run's file,
    read by a source node that names none of its own (as `run_source.branch_location`)."""
    tables: dict[str, StagedTable] = {}
    raw: dict[str, list[dict[str, str]]] = {}
    for node in source_nodes(pipeline):
        reader = _source_draft(draft, node)
        chosen = branch_location(node, location)  # the run's file choice, as Verify's
        if chosen:
            reader = reader.model_copy(update={"source_location": chosen})
        rows = _read_rows(reader)
        if limit is not None:
            rows = rows[:limit]
        raw[node.id] = rows
        tables[node.id] = source_table(node.id, rows, load_id=f"{load_id}:{node.id}")
    return SourceRows(tables, raw)


def _ancestry(steps: Sequence[StagingStep], step_id: str) -> list[StagingStep]:
    """The steps `step_id` reads from, itself last, in run order: a preview runs no step it does
    not need, so every earlier one feeds a later one."""
    by_id = {s.id: s for s in steps}
    wanted: set[str] = set()
    stack = [step_id]
    while stack:
        at = stack.pop()
        if at in wanted or at not in by_id:
            continue
        wanted.add(at)
        stack.extend(step_inputs(by_id[at]))
    return [s for s in steps if s.id in wanted]


def _unsaved_sources(draft: StudioRecipeDraft, pipeline: PipelineGraph) -> list[str]:
    """The source nodes of `pipeline` that are not the saved draft's own, as words. A preview reads
    only the files the saved pipeline names (the review of L1.4: the request's own pipeline once
    named any file in the ingest folder, read at the viewer's level under the recipe's marking)."""
    saved = {n.id: n for n in source_nodes(pipeline_from_recipe(draft))}
    problems = []
    for node in source_nodes(pipeline):
        held = saved.get(node.id)
        keys = ("connector_profile", "source_location")
        if held is None or any(node.config.get(k) != held.config.get(k) for k in keys):
            problems.append(
                f"source '{node.label}' is not the saved pipeline's: save its source before a "
                "step's sample reads it"
            )
    return problems


#: What the preview says when it withholds the sample (rule 3).
WITHHELD = (
    "The sample is withheld: some of its source rows are above your clearance or restricted to "
    "another unit, and a step's own settings could be used to tell their values."
)


#: What the preview, and Test, say when the recipe's dataset is not one the reader's case reads.
DATASET_WITHHELD = (
    "The sample is withheld: it reads this dataset's files and lists, which only a case that "
    "reads the dataset may read."
)


#: What the preview says when a Lookup's list rows are not the reader's to read.
LISTS_WITHHELD = (
    "The sample is withheld: it reads this dataset's reference lists, which only a case that "
    "reads the dataset may read."
)


def preview_staging(
    draft: StudioRecipeDraft,
    body: StagingPreviewInput,
    *,
    principal: Principal,
    scheme: HandlingScheme,
    references: Sequence[ReferenceList],
    storage: ObjectStorageConfig,
) -> StagingPreview:
    """The steps up to `body.step` over the first ten rows of each source of the **saved**
    pipeline, with every refusal of the save gate for the pipeline the drawer holds beside it.
    Nothing is written: no staged Parquet, no raw rows.

    Rule 3 (the review of L1.4). The reader writes the steps that run over the rows, so a Filter,
    a Derive or a Join could be made to answer questions about a value it hides: masking a cell's
    shape is not enough. So **if the reader may not view every row the sample reads, nothing of the
    run is returned**: no rows, counts, rejections or profile, only the gate's words and
    `values_masked`. A source the request names that is not the saved draft's own is refused in
    words, and nothing is read."""
    pipeline = body.pipeline
    problems = [*pipeline_rule_violations(pipeline)]
    not_offered = sources_not_offered(pipeline, draft.dataset_id)
    problems.extend(not_offered)
    problems.extend(
        p
        for p in staging_gate(pipeline, references=references, dataset_id=draft.dataset_id)
        if p not in problems
    )
    unsaved = _unsaved_sources(draft, pipeline)
    if unsaved or not_offered:
        return StagingPreview(step=body.step, problems=[*problems, *unsaved])
    # A recipe's files and lists are its dataset's, read as its elements are, by a case that reads
    # the dataset (rule 4; the lane review's second round for a Lookup's lists, the orchestrator's
    # review of L1.4 for every step's sample, which shows the dataset's files' rows).
    if draft.dataset_id and draft.dataset_id not in (principal.datasets or []):
        return StagingPreview(
            step=body.step, problems=[*problems, DATASET_WITHHELD], values_masked=True
        )
    # A step's record the schema refuses cannot be run at all; any other refusal (a source not yet
    # used, a later step half set) is reported beside the sample, which runs whenever the steps
    # this one needs can.
    if step_record_violations(pipeline):
        return StagingPreview(step=body.step, problems=problems)
    steps = staging_from_pipeline(pipeline) or []
    if body.step not in {s.id for s in steps}:
        return StagingPreview(
            step=body.step, problems=[f"the pipeline has no step {body.step!r} to preview"]
        )
    wanted = _ancestry(steps, body.step)
    # A list's rows carry no marking of their own: they are the dataset's, read as its elements
    # are, by a case that reads the dataset (rule 4; the lane review's second round).
    if any(isinstance(s, LookupStep) for s in wanted) and (
        not draft.dataset_id or draft.dataset_id not in (principal.datasets or [])
    ):
        return StagingPreview(
            step=body.step, problems=[*problems, LISTS_WITHHELD], values_masked=True
        )
    read = source_tables(draft, pipeline, load_id="preview", limit=PREVIEW_ROWS)
    every_row = [r for rows in read.raw.values() for r in rows]
    sample = sample_markings(draft, scheme, every_row)
    if not sample.readable_by(principal, scheme):
        return StagingPreview(
            step=body.step, problems=[*problems, WITHHELD], values_masked=True
        )
    try:
        lists = lists_for_run(
            wanted, references, dataset_id=draft.dataset_id or "", storage=storage
        )
        result = run_staging(
            wanted, sources=read.tables, lists=lists, dataset_id=draft.dataset_id or ""
        )
    except StagingError as refused:
        return StagingPreview(
            step=body.step,
            problems=[*problems, *(p for p in refused.problems if p not in problems)],
        )
    table = result.output
    shown = [{c: row.cells.get(c) or "" for c in table.columns} for row in table.rows]
    profile = (
        profile_source(
            shown,
            source_handling=resolve_source_handling(draft),
            principal=principal,
            scheme=scheme,
            source_markings=sample.markings,
            unviewable=sample.unviewable,
        )
        if table.rows
        else None
    )
    return StagingPreview(
        step=body.step,
        problems=problems,
        columns=list(table.columns),
        rows=shown,
        values_masked=bool(profile and profile.values_masked),
        rows_sampled=len(every_row),
        counts=step_counts(result),
        rejections=[staging_rejection_record(r) for r in result.rejections],
        profile=profile,
    )


def staged_lists(
    draft: StudioRecipeDraft,
    steps: Sequence[StagingStep],
    references: Sequence[ReferenceList],
    storage: ObjectStorageConfig,
) -> Mapping[str, StagedTable]:
    return lists_for_run(steps, references, dataset_id=draft.dataset_id or "", storage=storage)
