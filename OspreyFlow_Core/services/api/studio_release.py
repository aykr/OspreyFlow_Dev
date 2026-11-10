"""Studio › Releases: a dataset's release exported as a YAML bundle, and a bundle imported as
drafts (`06_DECISIONS.md` ADR-140 Amendment 9 decision 4). The bundle itself is
`services/ingest/release.py`'s; this module reads the stores for an export and plans and writes an
import. `ospreyflow release export` and `ospreyflow release import --dry-run` call the two routes
that call these, so the command does what the Studio's buttons do.

**An export reads as the exporter** (rule 3): the dataset's live domain model; the published
pipelines the exporter's unit holds and whose source's marking the exporter may view, each other
one counted in words in the answer, never left out silently (rule 2); the dataset's own reference
lists the live model names, with their rows while small; the deployment-wide lists it subscribes
to, as definitions only; and the connections its pipelines' sources read through, by name.

**An import lands drafts, through the canvas's own gates.** Every pipeline in the bundle is judged
as the canvas's save judges it before anything is written (an expert step needs
`write_sql_transforms`; the graph's rules; each source a file of the receiving dataset's; the
staging gate against the lists the import would leave), and a bundle with any refusal writes
nothing (the strict option, logged in REPORT.md). The model lands as the dataset's draft, never
live: *Make live* stays a person's audited step. `dry_run` judges and plans the same and writes
nothing at all.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from services.ingest.pipeline import expert_steps_changed, pipeline_rule_violations
from services.ingest.release import (
    Bundle,
    ListToRelease,
    ReleaseRefused,
    build_bundle,
    pipeline_for,
    read_bundle,
)
from services.ingest.staging import ObjectStorageConfig

from ontology.handling import HandlingScheme, principal_may_view
from schemas.dataset_model import ReferenceList, TargetModelDraftInput
from schemas.domain import Principal
from schemas.ingest import (
    DeduplicateConfig,
    PipelineGraph,
    RowTemplate,
    StudioRecipeDraft,
    StudioRecipeStatus,
)
from schemas.release import (
    ReleasedPipeline,
    ReleaseImportItem,
    ReleaseImportPlan,
    ReleaseMetadata,
)
from schemas.rights import Right, rights_for

from .ingest_sources import UPLOAD_SUBDIR, ingest_root
from .list_connector import ListRows, ListStore
from .sources import SourceStore
from .studio_map import resolve_source_handling
from .studio_profile import offered_to
from .studio_recipes import StudioRecipeStore
from .studio_staging import (
    dataset_reference_lists,
    draft_marked,
    sources_not_offered,
    staging_gate,
)
from .target_models import TargetModelStore

#: An environment variable whose value is a secret: the values `deployment.env` fills that an
#: export must never carry (ADR-140 Amendment 9's planted secret).
_SECRET_NAME = re.compile(r"(?i)(password|secret|token|api_?key|private_?key|credential)")

EXPERT_IMPORT_WORDS = (
    "holds an expert step (SQL or fuzzy match), which only a holder of write_sql_transforms may add"
)


def locate(name: str, dataset_id: str) -> str | None:
    """The receiving dataset's file of `name`, as the canvas would offer it: its own folders first,
    then the folders every case is offered; `None` when it has none (the import's refusal)."""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    root = ingest_root()
    folders = [root / dataset_id, root / UPLOAD_SUBDIR / dataset_id, root, root / UPLOAD_SUBDIR]
    for folder in folders:
        candidate = folder / name
        if candidate.is_file() and offered_to(str(candidate), dataset_id):
            return str(candidate)
    return None


def located(released: ReleasedPipeline, dataset_id: str) -> tuple[ReleasedPipeline, list[str]]:
    """The released pipeline with each file it names found in the receiving dataset's folder, and
    the names it could not find."""
    missing: list[str] = []

    def find(name: str | None) -> str | None:
        if name is None:
            return None
        found = locate(name, dataset_id)
        if found is None:
            missing.append(name)
        return found

    graph = released.pipeline
    if graph is not None:
        graph = json.loads(json.dumps(graph))
        for node in graph.get("nodes", []):
            config = node.get("config") or {}
            if config.get("source_location"):
                config["source_location"] = find(str(config["source_location"])) or ""
    return (
        released.model_copy(
            update={"source_location": find(released.source_location), "pipeline": graph}
        ),
        sorted(set(missing)),
    )


def deployment_secrets(environ: Mapping[str, str] | None = None) -> list[str]:
    """Every secret value in the Conduit's environment, the one `deployment.env` fills."""
    env = os.environ if environ is None else environ
    return [v for k, v in env.items() if _SECRET_NAME.search(k) and v]


@dataclass(frozen=True)
class ExportResult:
    files: dict[str, bytes]
    #: Published pipelines left out because their source is marked above the exporter's view.
    left_out: int


def _locations(draft: StudioRecipeDraft) -> set[str]:
    found = {draft.source_location} if draft.source_location else set()
    for node in draft.pipeline.nodes if draft.pipeline else []:
        if node.config.get("source_location"):
            found.add(str(node.config["source_location"]))
    return found


async def export_release(
    *,
    dataset_id: str,
    principal: Principal,
    metadata: ReleaseMetadata,
    models: TargetModelStore,
    recipes: StudioRecipeStore,
    rows_kept: ListRows,
    staging_storage: ObjectStorageConfig,
    list_store: ListStore | None,
    sources: SourceStore,
    scheme: HandlingScheme,
    secrets: Sequence[str],
) -> ExportResult:
    live = await models.live(dataset_id)
    if live is None:
        raise ReleaseRefused(
            ["the dataset has no live domain model to release: make a version live first"]
        )
    published = [
        d
        for d in await recipes.list_all(principal)
        if d.dataset_id == dataset_id and d.status is StudioRecipeStatus.PUBLISHED
    ]
    viewable = [
        d for d in published if principal_may_view(resolve_source_handling(d), principal, scheme)
    ]
    references = await dataset_reference_lists(
        models, dataset_id, staging_storage, lists=list_store
    )
    lists: list[ListToRelease] = []
    for ref in references:
        rows = (
            await asyncio.to_thread(rows_kept.read, ref)
            if ref.kind == "reference" and ref.dataset_id == dataset_id
            else None
        )
        lists.append(ListToRelease(ref, rows))
    reads = set().union(*(_locations(d) for d in viewable)) if viewable else set()
    names: set[str] = set()
    for source in await sources.list_for(dataset_id):
        if source.location in reads:
            names.add((await sources.connection(source.connection_id)).name)
    files = build_bundle(
        name=metadata.name,
        version=metadata.version,
        model=live,
        pipelines=viewable,
        lists=lists,
        connections=names,
        secrets=secrets,
    )
    return ExportResult(files=files, left_out=len(published) - len(viewable))


def _gate_draft(
    released_handling: dict[str, object],
    dataset_id: str,
    principal: Principal,
    row_template: RowTemplate | None,
) -> StudioRecipeDraft:
    """A stand-in draft the staging gate reads the marked columns of, never stored."""
    return StudioRecipeDraft.model_validate(
        {
            "recipe_id": "release-import",
            "version": 1,
            "status": StudioRecipeStatus.DRAFT,
            "label": "release import",
            "handling": released_handling,
            "owning_unit": principal.org_unit,
            "created_by": principal.id,
            "created_at": datetime.now(UTC),
            "ready_for_profile": False,
            "row_template": row_template,
            "dataset_id": dataset_id,
        }
    )


async def plan_import(
    bundle: Bundle,
    *,
    dataset_id: str,
    principal: Principal,
    dry_run: bool,
    models: TargetModelStore,
    rows_kept: ListRows,
    staging_storage: ObjectStorageConfig,
    list_store: ListStore | None,
    sources: SourceStore,
) -> tuple[ReleaseImportPlan, list[ReferenceList]]:
    """What the import writes and every refusal, judged before anything is written. Returns the
    plan and the dataset's own lists the import would add (definitions at the receiving id)."""
    refused: list[str] = []
    notes: list[str] = []
    items: list[ReleaseImportItem] = []
    draft = await models.draft(dataset_id)
    items.append(
        ReleaseImportItem(
            role="domain_model",
            name="the domain model",
            action="replaces_draft" if draft is not None else "new_draft",
        )
    )
    kept = {(r.name, r.version) for r in await asyncio.to_thread(rows_kept.kept, dataset_id)}
    own_lists: list[ReferenceList] = []
    for listed in bundle.lists:
        if listed.kind == "screening":
            notes.append(
                f"the screening list {listed.name!r} is the deployment's: subscribe this dataset "
                "to it in Studio › Sources"
            )
            continue
        reference = ReferenceList(
            id=listed.id,
            dataset_id=dataset_id,
            name=listed.name,
            kind=listed.kind,
            key_column=listed.key_column,
            version=listed.version,
            schedule=listed.schedule,
        )
        if (listed.name, listed.version) in kept:
            notes.append(
                f"the list {listed.name!r} (version {listed.version}) is already kept here; "
                "it is left as it is"
            )
            continue
        if listed.name not in bundle.list_rows:
            notes.append(
                f"the list {listed.name!r} travelled without its rows: import them in Studio › "
                "Sources before a pipeline's Lookup reads it"
            )
            continue
        own_lists.append(reference)
        items.append(ReleaseImportItem(role="reference_list", name=listed.name, action="new_draft"))

    references = [
        *await dataset_reference_lists(models, dataset_id, staging_storage, lists=list_store),
        *own_lists,
    ]
    may_write_sql = Right.WRITE_SQL_TRANSFORMS in rights_for(principal.roles)
    for exported in bundle.pipelines:
        released, missing = located(exported, dataset_id)
        graph = pipeline_for(released, dataset_id) or PipelineGraph()
        name = released.label
        if expert_steps_changed(PipelineGraph(), graph) and not may_write_sql:
            refused.append(f"the pipeline {name!r} {EXPERT_IMPORT_WORDS}")
        refused.extend(
            f"the pipeline {name!r} reads a file named {m!r}, which this dataset's ingest folder "
            "does not hold: add it here first"
            for m in missing
        )
        if missing:
            items.append(ReleaseImportItem(role="pipeline", name=name, action="new_draft"))
            continue
        problems = pipeline_rule_violations(graph) if graph.nodes else []
        if graph.nodes:
            problems.extend(sources_not_offered(graph, dataset_id))
            template = (
                None
                if released.row_template is None
                else RowTemplate.model_validate(released.row_template)
            )
            gate = _gate_draft(released.handling, dataset_id, principal, template)
            problems.extend(
                p
                for p in staging_gate(
                    graph, references=references, dataset_id=dataset_id, marked=draft_marked(gate)
                )
                if p not in problems
            )
        refused.extend(f"the pipeline {name!r}: {p}" for p in problems)
        items.append(ReleaseImportItem(role="pipeline", name=name, action="new_draft"))

    here = {c.name for c in await sources.connections()}
    missing = sorted(set(bundle.manifest.spec.connections) - here)
    return (
        ReleaseImportPlan(
            dry_run=dry_run,
            release=bundle.manifest.metadata,
            items=items if not refused else [],
            refused=refused,
            missing_connections=missing,
            notes=notes,
        ),
        own_lists,
    )


async def apply_import(
    bundle: Bundle,
    plan: ReleaseImportPlan,
    own_lists: Sequence[ReferenceList],
    *,
    dataset_id: str,
    principal: Principal,
    models: TargetModelStore,
    recipes: StudioRecipeStore,
    rows_kept: ListRows,
) -> list[str]:
    """Writes the plan's drafts; returns the new pipeline drafts' ids. Never called for a dry run
    or a plan with a refusal."""
    assert not plan.dry_run and not plan.refused
    for reference in own_lists:
        rows: list[dict[str, object]] = [dict(r) for r in bundle.list_rows[reference.name]]
        await asyncio.to_thread(rows_kept.write, reference, rows)
    if await models.draft(dataset_id) is None:
        await models.open_draft(dataset_id, principal)
    await models.save_draft(
        dataset_id,
        TargetModelDraftInput(
            packs=bundle.model.packs,  # type: ignore[arg-type]
            extensions=bundle.model.extensions,
            reference_lists=bundle.model.reference_lists,
        ),
        principal,
    )
    made: list[str] = []
    for exported in bundle.pipelines:
        released, _ = located(exported, dataset_id)
        draft = await recipes.create_draft(
            principal,
            label=released.label,
            connector_profile=released.connector_profile or "generic-csv",
            source_location=released.source_location,
            handling=dict(released.handling),
            legal_basis=released.legal_basis,
            deduplicate=None
            if released.deduplicate is None
            else DeduplicateConfig.model_validate(released.deduplicate),
        )
        graph = pipeline_for(released, dataset_id)
        if graph is not None:
            await recipes.update_pipeline(draft.recipe_id, principal, pipeline=graph)
        if released.row_template is not None:
            await recipes.update_row_template(
                draft.recipe_id,
                principal,
                row_template=RowTemplate.model_validate(released.row_template),
                unmapped_fields=[],
            )
        made.append(draft.recipe_id)
    return made


def bundle_from_text(files: Mapping[str, str]) -> Bundle:
    """The import route's body, its files as text, read and checked."""
    return read_bundle({path: text.encode("utf-8") for path, text in files.items()})
