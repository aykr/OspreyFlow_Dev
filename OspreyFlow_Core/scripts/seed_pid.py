"""Seeds the Prison Intelligence Dataset (synthetic), restores it between rehearsals, and carries
the two commands a presenter runs mid-demo (`06_DECISIONS.md` ADR-127 Amendment 23, as corrected by
Amendments 25 to 27 and 30 to 32; Brief 2 sections 5, 7 and 8).

    python -m scripts.seed_pid --case-name "Prison Intelligence Dataset (synthetic demo)" \\
        --grant ACCOUNT=LEVEL ...        # the seed (through `seed_internal`; Conduit stopped)
    python -m scripts.seed_pid --reset-live --case-name ... [--show-ids]   # the rehearsal reset
    python -m scripts.seed_pid --check --case-name ...       # the demo numbers, loading nothing
    python -m scripts.seed_pid --release-batch-2             # chapter 9 (Conduit stays up)
    python -m scripts.seed_pid --publish-reports-fallback    # chapter 4 fallback (Conduit stays up)

Run the first two through `python -m scripts.seed_internal prison-intelligence [--reset-live]
--stop-api` (or `ospreyflow demo add prison-intelligence`), inside the deployment's network, where
the stores and their passwords are. The seed needs the Conduit stopped for DuckDB's exclusive lock;
the last two write only files, or only Postgres and the recipe repository, and leave it running.

**The seed.** The case is made as the other seeds make theirs (`scripts.case_seed`). The loads are
made as the demo data engineer, `osprey-demo-engineer` (OFFICIAL, the demo unit, the role's rights;
Amendment 31 withdrew the SECRET-cleared worker, the dataset being OFFICIAL throughout), **scoped to
the case before any write**, so every node, link and picture is stamped with the dataset and a
reference finds only that dataset's nodes. The role holds no `EDIT_GRAPH`, which the picture path
needs, so that one right is granted to the persona within the pictures step alone and to nothing
else. The files are written into `<ingest root>/uploaded/<dataset>/`, the one folder the Conduit's
image may write, with batch 2 of the seized-phone file under `incoming/` beneath it, which the
Studio's listing does not show; nothing else (no manifest, no pictures) lands in the listed folder.
Each committed recipe but the reports recipe is compared with the row it would meet (the store's
own comparison, so a committed file never differs from its published row), then copied byte for byte
into the recipe repository, committed there, and entered as published. The reports recipe is entered
as a draft that Map has not been done on. Each file of the seed's part of `pid_files.SEED_ORDER` is
run, in that order, through the route's own `run_recipe_as`, unless the ledger already holds an
unreverted load of that recipe, version, case and source; a standing load is reported, with its
held, rejected and short-read rows, and fails the checks as it would have the first time. The
pictures go through `EntityPictureService.attach_for_seed`, to each subject found by reference that
has no picture history at all. A second seed adds nothing. Last, the seed computes Brief 2 section
8's demo numbers from the stores, as the persona, against the plan's own constants, and a failed
number fails the seed.

**No post-ingest resolution.** A run enqueues a `resolve_entity_type` job for `Person` after it
loads, and the Conduit's worker scores every pair of people its blocking rules bring together and
writes a `SAME_AS` link for each, onto whatever people it reads, the reports recipe's included:
links outside the loads, resting on their nodes, which would make every rehearsal reset refuse. So
the seed's runs are given a job queue that takes the job and enqueues nothing
(`without_post_ingest_resolution`). A live run of the recipes by the persona through the Conduit is
not changed by this and still enqueues it.

**The R17 guard.** Run before the reports, the incident-to-report recipe would make a bare, empty
report for each of its 589 rows (a reference that finds nothing is made, not refused), so every path
that runs a stage refuses it unless the case holds an unreverted load of the reports recipe.

**The reset** reverts, newest first, every unreverted load in the case of the incident-to-report
recipe and of the reports recipe, and every load of the seized-phone recipe whose source is batch 2
wherever under the dataset's folder it was read. On the first revert that refuses it stops, names
the refusal by its counts (link types and ids only with `--show-ids`), and gives the restore
procedure: a reseed skips loads that stand, so the way back is the backup taken after seeding.
Only when every revert has been made does it restore the reports recipe to its starting draft
(writing no new version when nothing was reverted and it is there already), rewrite the reports
file, remove batch 2 from the listed folder and every file the seed did not
write, naming each, and say what it cannot undo.

**Deviation from the amendment's wording, and why.** The amendment gives `docker compose exec api`
for `--release-batch-2` and the fallback; `seed_internal` runs them in a one-shot container from
the Conduit's image with the checkout mounted (as its inspection modes do), so the code is the
checkout's and not the image's older copy, and the Conduit is left running all the same.

**The scale cohort** is its own pack, `prison-intelligence-scale`, written by the plan writer
rather than through recipes (`scripts.seed_pid_scale`; ADR-127 Amendment 40).
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import dataclasses
import os
import re
import resource
import shutil
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any, Protocol, cast

import yaml
from scripts.case_seed import add_case_arguments, check_case_arguments, parse_grant, scope_for
from scripts.revert_load import build_revert_deps
from services.api.audit import AuditWriter
from services.api.case_brief import CaseBriefService, CaseBriefStore
from services.api.config import ApiConfig, PostgresConfig
from services.api.dataset_scope import scope_to_case
from services.api.datasets import DatasetRefusedError, PostgresDatasetStore
from services.api.document_content import UploadRefusedError
from services.api.entity_pictures import EntityPictureService
from services.api.history import InvestigationHistoryStore
from services.api.ingest_sources import UPLOAD_SUBDIR, ingest_root
from services.api.investigations import (
    AccessLevel,
    InsufficientAccessError,
    InvestigationNotFoundError,
    InvestigationStore,
)
from services.api.jobs import JobQueue
from services.api.recipe_run import RecipeRunDeps, run_recipe_as
from services.api.recipe_runs import RecipeRunStore
from services.api.run_resources import build_run_resources
from services.api.search import SearchRequest, search
from services.api.studio_map import HandlingLoosenedError
from services.api.studio_publish import (
    GitCommitError,
    RecipeNotRunnableError,
    build_recipe,
    commit_recipe_file,
    pack_versions_for,
    recipe_git_relative_path,
    serialise_recipe,
)
from services.api.studio_recipes import (
    SeededRecipeAnotherPublished,
    SeededRecipeContentDiffers,
    SeededRecipeNoLegalBasis,
    SeededRecipePinsDiffer,
    SourceDeclarationsInvalidError,
    StudioRecipeNotADraftError,
    StudioRecipeNotFoundError,
    StudioRecipeNotVerifiedError,
    StudioRecipeStore,
    check_seeded_recipe,
)
from services.api.working_set.service import WorkingSetService
from services.api.working_set.store import ValkeyWorkingSetStore
from services.extract.writer import NodeNotFoundError
from services.ingest.engine import RowKeyDefinitionChanged, RowKeyRunInProgress, StaleRecipeError
from services.ingest.load_revert import (
    RevertIncomplete,
    RevertRefused,
    links_resting_on,
    revert,
)
from services.ingest.pipeline import pipeline_run_violations
from services.ingest.recipe_loader import load_recipe
from services.ingest.recipe_rules import RecipeRuleError

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from demo_fixtures import pid_files, pid_plan, pid_writes
from demo_fixtures.datasets import PID
from demo_fixtures.pid_files import SEED_ORDER, SeedStage, seed_stages
from ontology.handling import HandlingScheme, load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.domain import ExpandRequest, Node, PatternQuery, Principal, Subgraph
from schemas.ingest import (
    LoadRecord,
    LoadReport,
    PipelineEdge,
    PipelineGraph,
    PipelineNode,
    PipelineNodeKind,
    PipelineRunReport,
    Recipe,
    StudioRecipeDraft,
    StudioRecipeStatus,
)
from schemas.rights import Right

#: The dataset's own folder under the ingest root's `uploaded/`, and the dataset it holds.
FOLDER = PID.id
INCOMING = "incoming"
#: The demo data engineer's username (`harness.realm.DEMO_ENGINEER_SUBJECT`, held equal by a test).
#: A deployment's Conduit knows him by his Keycloak subject, which `seed_internal` passes as
#: `--run-as`; with none (a local stack without Keycloak) the seed loads as this, and says so
#: (Amendment 34).
ENGINEER_USERNAME = "osprey-demo-engineer"
#: How many items of a long list are printed, always with the total (Amendment 34).
LISTED = 20
#: The deployment's switch for queued resolution (ADR-127 Amendment 33), as the Conduit reads it.
RESOLUTION_SWITCH = "OSPREY_POST_INGEST_RESOLUTION"
#: The demo unit the demo accounts and the seeded case share (`scripts.seed_internal.DEMO_UNIT`).
WORKER_UNIT = "verify"
LEGAL_BASIS = "Synthetic demonstration data"
FIXTURES = Path(pid_files.__file__).resolve().parent
#: A seed skips a load that stands, so reseeding cannot clear a case whose loads have links resting
#: on them. The way back from a stuck rehearsal is a backup taken after seeding (ADR-127 Amendment
#: 33): `ospreyflow backup` (`harness.backup`; it prints the set's folder) and `ospreyflow restore`
#: (`harness.restore`: a dry run without `--yes`, and it refuses a store that is not empty, which
#: `deploy/RUNBOOK.md` says to empty with `down -v` and bring back up first).
BACKUP_COMMAND = "ospreyflow backup"
RESTORE_COMMAND = "ospreyflow restore <the folder ospreyflow backup printed> --yes"


def restore_steps() -> tuple[str, ...]:
    """The restore procedure as lines. A backup holds the stores and not the ingest folder (a host
    bind mount), so a restore ends with the reset, which removes a released batch 2 and rewrites
    the reports file (Amendment 34)."""
    return (
        "To get back to the seeded state, restore the backup taken after seeding:",
        f"  1. Take it once the seed has finished, before anything is rehearsed: {BACKUP_COMMAND}",
        "  2. When the reset refuses: empty the deployment's volumes and bring it back up (the "
        "restore refuses a store that is not empty; deploy/RUNBOOK.md has the steps).",
        f"  3. Then: {RESTORE_COMMAND}",
        "     (Without --yes it is a dry run that shows what it would restore.)",
        "  4. Then put the files right: python -m scripts.seed_internal prison-intelligence "
        "--reset-live --stop-api",
        "     (A backup does not hold the ingest folder, so a released batch 2 and an edited "
        "reports file survive a restore until the reset removes and rewrites them.)",
    )


def resolution_is_on(environ: Mapping[str, str] = os.environ) -> bool:
    """The switch as the Conduit reads it (`services.api.config`): unset or empty is on; `on` and
    `off` in any case; anything else is refused by name."""
    raw = environ.get(RESOLUTION_SWITCH)
    value = (raw or "on").strip().lower() or "on"
    if value not in ("on", "off"):
        raise SeedRefusal(f"{RESOLUTION_SWITCH} must be 'on' or 'off', not {raw!r}")
    return value == "on"


def resolution_warning() -> list[str]:
    """What an operator is told while the switch is on (Amendment 34)."""
    return [
        f"warning: {RESOLUTION_SWITCH} is on in this deployment: a live run of the reports recipe "
        "queues resolution, whose worker writes SAME_AS links onto the people it made, and every "
        "rehearsal reset then refuses.",
        "  Set `components.post_ingest_resolution: false` in osprey.yaml, re-render the deployment "
        "(`ospreyflow install`) and restart the Conduit.",
    ]


def require_resolution_off(environ: Mapping[str, str] = os.environ) -> None:
    """`--release-batch-2` and `--reset-live` refuse while the switch is on (Amendment 34): a live
    run would then make every reset refuse."""
    if resolution_is_on(environ):
        raise SeedRefusal("\n".join(resolution_warning()))


def run_as_line(run_as: str, *, given: bool = True) -> str:
    if given:
        return f"Loading as {run_as} (--run-as)."
    return (
        f"Loading as {run_as}, the demo engineer's username: no --run-as was given, so this is a "
        "local stack without his sign-in subject."
    )


#: What the fallback does not do that the route's publish does, said when it runs.
FALLBACK_SKIPS = (
    "This is a publish as the Conduit's route makes it, but it skips the route's role, case Editor "
    "and Verify checks: it is the operator's command, and the committed file is what the engine's "
    "own golden test ran."
)


class SeedRefusal(Exception):
    """Something to put right before the command can go on; the message says what."""


class GuardRefused(SeedRefusal):
    """A stage that must not run yet (the incident-to-report recipe before the reports)."""


#: Every refusal the seed, the reset and the fallback can meet, each printed by its name with a
#: non-zero exit rather than a traceback (Amendment 30). Anything else is a defect and surfaces as
#: one.
REFUSALS: tuple[type[Exception], ...] = (
    SeedRefusal,
    SeededRecipeContentDiffers,
    SeededRecipePinsDiffer,
    SeededRecipeNoLegalBasis,
    SeededRecipeAnotherPublished,
    StaleRecipeError,
    RecipeRuleError,
    HandlingLoosenedError,
    SourceDeclarationsInvalidError,
    UploadRefusedError,
    NodeNotFoundError,
    StudioRecipeNotFoundError,
    StudioRecipeNotADraftError,
    StudioRecipeNotVerifiedError,
    RecipeNotRunnableError,
    GitCommitError,
    DatasetRefusedError,
    RowKeyDefinitionChanged,
    RowKeyRunInProgress,
)


# --- what the seed is made of: names derived from the committed files, never typed here ----------


@cache
def _recipe(recipe_file: str) -> Recipe:
    return load_recipe(FIXTURES / recipe_file)


def recipe_id_of(recipe_file: str) -> str:
    """The id a committed recipe file declares."""
    return _recipe(recipe_file).id


def _stage_of(file: str) -> SeedStage:
    return next(stage for stage in SEED_ORDER if stage.file == file)


def reports_recipe_file() -> str:
    return _stage_of(pid_files.REPORTS).recipe


def reports_recipe_id() -> str:
    return recipe_id_of(reports_recipe_file())


def incidents_recipe_id() -> str:
    return recipe_id_of(_stage_of(pid_files.REPORT_INCIDENTS).recipe)


def comms_recipe_id() -> str:
    return recipe_id_of(_stage_of(pid_files.BATCH_2).recipe)


def recipe_repo_root(environ: Mapping[str, str] = os.environ) -> Path:
    """The recipe repository the seed commits into, named by `OSPREY_RECIPE_REPO_ROOT` (the renderer
    sets it). Never defaulted: unset, `studio_publish` falls back to the product folder itself, and
    a seed that committed there would `git init` inside the checkout."""
    raw = environ.get("OSPREY_RECIPE_REPO_ROOT")
    if not raw:
        raise SeedRefusal(
            "OSPREY_RECIPE_REPO_ROOT is not set: the seed commits the recipes to the recipe "
            "repository, and without it that would be the checkout itself. Name a folder for it."
        )
    return Path(raw)


def agree_on_repository(committed_to: Path, read_by_runs: Path) -> None:
    """The repository the recipes are committed to is the one the runs read them from."""
    if committed_to != read_by_runs:
        raise SeedRefusal(
            f"{committed_to} is not the repository the runs read the recipes from "
            f"({read_by_runs}): OSPREY_RECIPE_REPO_ROOT changed since the process started"
        )


def stages_to_run() -> tuple[SeedStage, ...]:
    """The seed's own part of the one load order: before the analyst begins."""
    return seed_stages("seed")


def engineer(unit: str = WORKER_UNIT, run_as: str | None = None) -> Principal:
    """The demo data engineer: OFFICIAL, in the demo unit, holding the `data_engineer` role's
    rights and no more (Amendment 31), under the id he signs in as (`run_as`, his Keycloak
    subject) or, with none, his username (Amendment 34). Not scoped to a case: the seed scopes it
    before any write (`seed_all`)."""
    return Principal(
        id=run_as or ENGINEER_USERNAME,
        clearance="OFFICIAL",
        org_unit=unit,
        roles=["data_engineer"],
    )


def with_edit_graph(principal: Principal) -> Principal:
    """A copy of `principal` holding `EDIT_GRAPH` as well, which the picture path needs and the data
    engineer's role does not give. For the pictures step alone (Amendment 31): no deployment role
    changes, and no other step is handed it."""
    return principal.model_copy(
        update={"roles": [*principal.roles, f"right:{Right.EDIT_GRAPH.value}"]}
    )


def listed_folder(root: Path) -> Path:
    """The dataset's folder the Studio lists: `<root>/uploaded/<dataset>/`."""
    return root / UPLOAD_SUBDIR / FOLDER


def incoming_folder(root: Path) -> Path:
    """Beneath the listed folder, where the listing does not look: batch 2 waits here."""
    return listed_folder(root) / INCOMING


def source_of(root: Path, file: str) -> str:
    """A file's location as the Studio's listing names it (`ingest_sources.list_source_files`)."""
    return str(listed_folder(root) / file)


def starting_pipeline(source_location: str) -> PipelineGraph:
    """R9's draft pipeline: a domain model for the NIEM pack and one source at the reports file,
    read through `generic-csv`. Profile and Map are not done."""
    return PipelineGraph(
        nodes=[
            PipelineNode(
                id="domain",
                kind=PipelineNodeKind.DOMAIN_MODEL,
                label="Domain model",
                config={"pack": "niem"},
            ),
            PipelineNode(
                id="source",
                kind=PipelineNodeKind.SOURCE,
                label="Intelligence reports",
                config={"connector_profile": "generic-csv", "source_location": source_location},
            ),
        ],
        edges=[PipelineEdge(source="domain", target="source")],
    )


def one_case(case_ids: Sequence[str], name: str) -> str | None:
    """The one case of this name, or None when there is none. Two of one name are refused, not
    resolved by taking the first: the seed would load a case nobody chose (Amendment 30)."""
    if len(case_ids) > 1:
        raise SeedRefusal(
            f"{len(case_ids)} cases are called {name!r} ({', '.join(sorted(case_ids))}): the seed "
            "will not choose between them. Remove or rename all but one, or name the case by id "
            "with --investigation-scope."
        )
    return case_ids[0] if case_ids else None


# --- the files -----------------------------------------------------------------------------------


def _replace(part: Path, final: Path) -> None:
    os.replace(part, final)


def _place(
    source: Path, destination: Path, *, replace: Callable[[Path, Path], None] = _replace
) -> None:
    """Copies `source` to `destination` whole or not at all: the bytes go to a hidden part file
    beside it (which the picker does not offer) and are renamed into place."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.parent / f".{destination.name}.part"
    try:
        shutil.copyfile(source, part)
        replace(part, destination)
    finally:
        part.unlink(missing_ok=True)


def write_listed_files(
    plan: pid_plan.Plan,
    root: Path,
    *,
    write: Callable[[pid_plan.Plan, Path], pid_files.WriteReport] = pid_files.write_files,
) -> dict[str, int | None]:
    """Writes the plan's CSV files into the dataset's listed folder, and batch 2 under `incoming/`
    beneath it, and answers each name written with its row count. The generator writes beside them
    a manifest and the pictures; they stay in a scratch folder that is thrown away, so nothing but
    the seed's own files is ever listed. A second call rewrites every file byte for byte."""
    listed = listed_folder(root)
    written: dict[str, int | None] = {}
    with tempfile.TemporaryDirectory(prefix="pid-seed-") as scratch:
        report = write(plan, Path(scratch))
        for record in report.files:
            _place(Path(scratch) / record.name, listed / record.name)
            written[record.name] = record.rows
    return written


def rewrite_reports_file(
    plan: pid_plan.Plan,
    root: Path,
    *,
    write: Callable[[pid_plan.Plan, Path], pid_files.WriteReport] = pid_files.write_files,
) -> None:
    """The reports file as the generator writes it, in the listed folder again (the reset)."""
    with tempfile.TemporaryDirectory(prefix="pid-seed-") as scratch:
        write(plan, Path(scratch))
        _place(Path(scratch) / pid_files.REPORTS, listed_folder(root) / pid_files.REPORTS)


def release_batch_2(root: Path) -> str:
    """Chapter 9: copies batch 2 from `incoming/` into the listed folder. A file copy only, so the
    Conduit stays up. Refuses before the seed has written it; says so if it is there already."""
    source = incoming_folder(root) / pid_files.BATCH_2
    destination = listed_folder(root) / pid_files.BATCH_2
    if not source.is_file():
        raise SeedRefusal(
            f"batch 2 is not at {source}: seed the dataset first "
            "(`ospreyflow demo add prison-intelligence`)"
        )
    if destination.is_file() and destination.read_bytes() == source.read_bytes():
        return f"{pid_files.BATCH_2} is already in {listed_folder(root)}; nothing changed"
    _place(source, destination)
    return f"released {pid_files.BATCH_2} into {listed_folder(root)}"


# --- the recipes ---------------------------------------------------------------------------------


EnterPublished = Callable[..., Awaitable[Any]]


async def enter_recipes(
    root: Path,
    *,
    repo_root: Path,
    ontology: Any,
    scheme: HandlingScheme,
    commit: Callable[..., Awaitable[str]],
    compare: Callable[..., Awaitable[None]],
    enter: EnterPublished,
    enter_draft: EnterPublished,
    check: Callable[[Recipe, Any, HandlingScheme], None],
    now: datetime,
    worker_unit: str,
    published_by: str,
) -> dict[str, Any]:
    """Each committed recipe but the reports recipe: its checks first (`check`), then the row it
    would meet in the registry compared with the row it would enter (`compare`: the store's own
    comparison, which refuses by name a row that differs), then the committed file copied byte for
    byte into `recipes/<id>.yaml` of the recipe repository and committed there (`commit`), then its
    registry row entered as published (`enter`), with the source at the file its first stage reads.
    The comparison comes before the commit, so a committed file never differs from its published
    row (Amendment 30). The reports recipe is entered as the draft (`enter_draft`) and is neither
    committed nor published. Answers each recipe's row by its id."""
    rows: dict[str, Any] = {}
    reports_file = reports_recipe_file()
    for stage in SEED_ORDER:
        recipe = _recipe(stage.recipe)
        if recipe.id in rows:
            continue
        source = source_of(root, stage.file)
        if stage.recipe == reports_file:
            rows[recipe.id] = await enter_draft(
                recipe,
                source_location=source,
                dataset_id=FOLDER,
                owning_unit=worker_unit,
                created_by=published_by,
                now=now,
                pipeline=starting_pipeline(source),
            )
            continue
        check(recipe, ontology, scheme)
        git_path = recipe_git_relative_path(recipe.id)
        await compare(
            recipe,
            source_location=source,
            git_path=git_path,
            dataset_id=FOLDER,
            owning_unit=worker_unit,
        )
        committed = await commit(
            recipe.id,
            (FIXTURES / stage.recipe).read_bytes(),
            version=recipe.version,
            repo_root=repo_root,
        )
        rows[recipe.id] = await enter(
            recipe,
            source_location=source,
            git_path=committed,
            dataset_id=FOLDER,
            owning_unit=worker_unit,
            published_by=published_by,
            now=now,
            ontology=ontology,
            scheme=scheme,
        )
    return rows


# --- the runs ------------------------------------------------------------------------------------


class _NoJobs:
    """A job queue that takes a job and enqueues nothing."""

    async def submit(self, job_type: str, payload: dict[str, Any]) -> str:
        return ""


def without_post_ingest_resolution(deps: RecipeRunDeps) -> RecipeRunDeps:
    """The run's dependencies with a job queue that enqueues nothing, so a run of the seed's
    datasets enqueues no post-ingest resolution (Amendment 30, "Resolution's links"; the module
    docstring has why). Nothing else is changed. The route a person runs a recipe through keeps its
    own queue."""
    return dataclasses.replace(deps, jobs=cast(JobQueue, _NoJobs()))


@dataclass(frozen=True)
class Resolved:
    """A stage with what a run needs of it: its recipe's id and version, and its source."""

    stage: SeedStage
    recipe_id: str
    version: int
    source: str


def resolve(stage: SeedStage, root: Path) -> Resolved:
    recipe = _recipe(stage.recipe)
    return Resolved(stage, recipe.id, recipe.version, source_of(root, stage.file))


@dataclass(frozen=True)
class StandingRun:
    """What the run that made a standing load read: its rows, the rejected among them, the held."""

    rows_read: int
    rejected: int
    held: int


@dataclass(frozen=True)
class Interrupted:
    """A stage whose load record stands and whose latest run failed (a run that failed after its
    transaction committed): not a finished load, and not nothing."""

    load_id: str
    failure: str


@dataclass(frozen=True)
class StageResult:
    resolved: Resolved
    skipped: bool
    report: LoadReport | PipelineRunReport | None
    seconds: float
    #: For a stage not run because its load stands: what the run that made that load read, or None
    #: when no such run can be found in the ledger.
    standing: StandingRun | None = None
    #: A standing load whose latest run failed (`Interrupted`).
    interrupted: Interrupted | None = None


def pick_standing_run(runs: Sequence[Any], record: LoadRecord) -> StandingRun | Interrupted | None:
    """The finished run of the case that made `record`, among a recipe's runs (newest first): found
    by its load id (a pipeline run's branch records carry the run's id as a prefix)."""
    for run in runs:
        if (
            run.recipe_id == record.recipe_id
            and run.investigation_id == record.investigation_id
            and run.outcome == "succeeded"
            and run.load_id is not None
            and (record.load_id == run.load_id or record.load_id.startswith(f"{run.load_id}:"))
        ):
            return StandingRun(run.rows_read or 0, run.rows_rejected or 0, run.rows_held or 0)
    # No finished run made it: if the recipe's latest run in the case failed, the load is what that
    # run committed before it died, and the stage is interrupted (Amendment 34).
    latest = next(
        (
            r
            for r in runs
            if r.recipe_id == record.recipe_id and r.investigation_id == record.investigation_id
        ),
        None,
    )
    if latest is not None and latest.outcome == "failed":
        return Interrupted(
            record.load_id, str(getattr(latest, "failure", None) or "no reason recorded")
        )
    return None


def check_r17_guard(recipe_id: str, standing_recipe_ids: Sequence[str]) -> None:
    """The incident-to-report recipe is refused unless the case holds an unreverted load of the
    reports recipe: a reference that finds nothing makes a bare node, so run first it would make an
    empty report for each of its rows."""
    if recipe_id == incidents_recipe_id() and reports_recipe_id() not in standing_recipe_ids:
        raise GuardRefused(
            f"{recipe_id} is not run: the case holds no unreverted load of "
            f"{reports_recipe_id()}, and a reference that finds no report makes an empty one. "
            "Run the reports first."
        )


class _Ledger(Protocol):
    async def unreverted_loads(self, case: str, recipe_ids: Sequence[str]) -> list[LoadRecord]: ...


async def loaded_so_far(
    ledger: _Ledger, case: str, resolved: Sequence[Resolved]
) -> list[LoadRecord]:
    """The case's unreverted loads of the recipes the stages name (and of the reports recipe, when
    a stage is the incident-to-report recipe, for its guard)."""
    ids = {r.recipe_id for r in resolved}
    if incidents_recipe_id() in ids:
        ids.add(reports_recipe_id())
    return await ledger.unreverted_loads(case, sorted(ids))


async def run_stages(
    resolved: Sequence[Resolved],
    loaded: Sequence[LoadRecord],
    *,
    run: Callable[[Resolved], Awaitable[LoadReport | PipelineRunReport]],
    clock: Callable[[], float] = time.perf_counter,
    standing_of: Callable[[LoadRecord], Awaitable[StandingRun | Interrupted | None]] | None = None,
) -> list[StageResult]:
    """Runs each stage in the order given, unless the ledger holds its load (a record of the same
    recipe, version and source). The one place a stage is run, so the R17 guard cannot be skipped by
    a path that forgets it. A stage whose load stands is not read again, and `standing_of` is asked
    what the run that made it read, so a reseed reports it (Amendment 30)."""
    standing = [(r.recipe_id, r.recipe_version, r.source) for r in loaded]
    results: list[StageResult] = []
    for item in resolved:
        key = (item.recipe_id, item.version, item.source)
        if key in standing:
            record = next(r for r in loaded if (r.recipe_id, r.recipe_version, r.source) == key)
            made = await standing_of(record) if standing_of is not None else None
            if isinstance(made, Interrupted):
                results.append(StageResult(item, True, None, 0.0, None, made))
            else:
                results.append(StageResult(item, True, None, 0.0, made))
            continue
        check_r17_guard(item.recipe_id, [recipe for recipe, _, _ in standing])
        started = clock()
        report = await run(item)
        seconds = clock() - started
        standing.append(key)
        results.append(StageResult(item, False, report, seconds))
    return results


def peak_megabytes(raw: int, *, platform: str = sys.platform) -> float:
    """`ru_maxrss` in megabytes: bytes on macOS, kilobytes elsewhere."""
    return raw / (1024 * 1024) if platform == "darwin" else raw / 1024


def peak_now() -> float:
    return peak_megabytes(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


def measurement_lines(
    results: Sequence[StageResult], *, peak_before_mb: float, peak_after_mb: float
) -> list[str]:
    """R5's time and the process's peak memory around it (Brief 2 S5): measured only when R5 ran
    this time, and only with nothing else using the stack (rule 14)."""
    found = next((r for r in results if r.resolved.stage.file == pid_files.CALLS), None)
    if found is None:
        return []
    name = f"{found.resolved.recipe_id} ({pid_files.CALLS})"
    if found.skipped or found.report is None:
        return [
            f"{name} was not run this time (its load stands) so no time or memory was measured."
        ]
    return [
        f"{name}: {found.seconds:.1f} s for {found.report.rows_read:,} rows.",
        f"Peak resident memory of this process: {peak_before_mb:.0f} MB before it, "
        f"{peak_after_mb:.0f} MB after (a process-wide peak: it includes the work before the run, "
        "so it is an upper bound for the run).",
    ]


def _counts(result: StageResult) -> tuple[int, int, int] | None:
    """The rows a stage read, rejected and held: from its report, or from the run behind its
    standing load; None when neither is known."""
    if result.report is not None:
        report = result.report
        return report.rows_read, len(report.rejections), report.rows_held
    if result.standing is not None:
        return result.standing.rows_read, result.standing.rejected, result.standing.held
    return None


def summary_lines(results: Sequence[StageResult], *, run_as: str = ENGINEER_USERNAME) -> list[str]:
    """A line for each stage: what it read and made, or that its load stands and what the run that
    made it read."""
    lines: list[str] = []
    for r in results:
        label = f"{r.resolved.recipe_id}: {r.resolved.stage.file}"
        if r.interrupted is not None:
            lines.append(
                f"{label}: INTERRUPTED: its latest run failed ({r.interrupted.failure}) after load "
                f"{r.interrupted.load_id} was committed. Revert it with `python -m "
                f"scripts.revert_load {r.interrupted.load_id} --reverted-by {run_as}`, then seed "
                "again: the stage is loaded afresh."
            )
            continue
        if r.skipped or r.report is None:
            if r.standing is not None:
                lines.append(
                    f"{label}: already loaded, not read again; its run: "
                    f"{r.standing.rows_read:,} rows read, {r.standing.rejected:,} rejected, "
                    f"{r.standing.held:,} held"
                )
            else:
                lines.append(
                    f"{label}: already loaded, not read again; no run of it is in the ledger "
                    "to report"
                )
            continue
        report = r.report
        lines.append(
            f"{label}: {report.rows_read:,} rows read, {report.nodes_created:,} node(s) and "
            f"{report.edges_created:,} link(s) made, {report.nodes_referenced:,} found, "
            f"{len(report.rejections):,} rejected, {report.rows_held:,} held, "
            f"in {r.seconds:.1f} s"
        )
    return lines


def check_lines(
    results: Sequence[StageResult], rows_in_file: Mapping[str, int | None]
) -> tuple[list[str], bool]:
    """Brief 2 section 8's checks that need no Conduit: a file was read whole (the rows its run read
    are the rows the generator wrote), and nothing was held back. The same for a stage whose load
    stands, from the run that made it, so a reseed fails as the first seed would have; a standing
    load with no run to read fails, since it cannot be shown whole. The lines, and whether every
    check held."""
    lines: list[str] = []
    ok = True
    for r in results:
        file = r.resolved.stage.file
        if r.interrupted is not None:
            ok = False
            lines.append(
                f"check FAILED: {file} was interrupted (its latest run failed after load "
                f"{r.interrupted.load_id} was committed), so it is not a whole load"
            )
            continue
        counts = _counts(r)
        if counts is None:
            ok = False
            lines.append(
                f"check FAILED: {file} is already loaded, but the run that loaded it cannot be "
                "found, so it cannot be shown to have been read whole"
            )
            continue
        read, _rejected, held = counts
        wanted = rows_in_file.get(file)
        good = wanted is not None and read == wanted and held == 0
        ok = ok and good
        lines.append(
            f"check {'ok' if good else 'FAILED'}: {file} was read whole "
            f"({read:,} of {wanted if wanted is not None else '?'} rows, {held:,} held)"
        )
    return lines, ok


# --- the pictures --------------------------------------------------------------------------------

_IDENTIFIERS = (
    "prison_number", "nino", "site_ref", "establishment_ref", "org_ref", "incident_ref", "imei",
    "value_normalised", "message_id",
)  # fmt: skip
_REPORT_REFERENCE = re.compile(r"IR \d+")


def identity_of(plan: pid_plan.Plan, key: str) -> tuple[str, str, str]:
    """How the store names a plan entity: its type, and the first identifying property it holds
    with that property's value, which is what a reference finds it by. A handset is named by its
    14-digit body (`imei` drops the check digit, ADR-127 Amendment 18). `tests/ingest/
    pid_golden_support._identity` is held equal to this for every picture subject."""
    entity = plan.entity(key)
    for name in _IDENTIFIERS:
        if name in entity.properties:
            value = str(entity.properties[name])
            return (entity.entity_type, name, value[:14] if name == "imei" else value)
    if key in plan.report_texts:
        found = _REPORT_REFERENCE.match(plan.report_texts[key])
        if found is not None:
            return (entity.entity_type, "message_id", found.group())
    raise ValueError(f"{key} holds no identifying property to find it by")


@dataclass
class PictureSummary:
    attached: int = 0
    skipped: int = 0
    #: Subjects no reference found.
    missing: list[str] = field(default_factory=list)
    #: Subjects the picture service refused, with the reason.
    refused: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.refused


async def seed_pictures(
    plan: pid_plan.Plan,
    *,
    find: Callable[[str, str, str], Awaitable[Any]],
    attach: Callable[..., Awaitable[bool]],
) -> PictureSummary:
    """Attaches the plan's picture to each subject found by reference. A subject with any picture
    history is left alone (`attach` answers False: Amendment 27), one no reference finds is counted
    and fails the seed, and one the service refuses is named with its reason and fails it."""
    summary = PictureSummary()
    for key, (_, name, data) in zip(
        plan.picture_subjects, pid_writes.picture_writes(plan), strict=True
    ):
        entity_type, identifier, value = identity_of(plan, key)
        node = await find(entity_type, identifier, value)
        if node is None:
            summary.missing.append(key)
            continue
        try:
            attached = await attach(node.id, name=name, data=data, legal_basis=LEGAL_BASIS)
        except (UploadRefusedError, NodeNotFoundError, ValueError) as error:
            summary.refused.append((key, f"{type(error).__name__}: {error}"))
            continue
        if attached:
            summary.attached += 1
        else:
            summary.skipped += 1
    return summary


def picture_lines(summary: PictureSummary, subjects: int) -> list[str]:
    lines = [
        f"pictures: {subjects:,} subjects, {summary.attached:,} attached, {summary.skipped:,} "
        "already had a picture history and were left alone"
    ]
    if summary.missing:
        lines.append(
            f"{len(summary.missing)} subject(s) no reference found (first "
            f"{min(5, len(summary.missing))} of {len(summary.missing)}): {summary.missing[:5]}"
        )
    for key, why in summary.refused[:5]:
        lines.append(f"refused {key}: {why}")
    if len(summary.refused) > 5:
        lines.append(f"  (first 5 of {len(summary.refused)} refusals)")
    lines.append(f"check {'ok' if summary.ok else 'FAILED'}: every picture subject was found")
    return lines


# --- the inferred links: the plan's "graph port" shapes -------------------------------------------

#: The pseudo-file the plan gives the links no recipe loads (`pid_plan.LOAD_SHAPES`): model-derived
#: links, written inferred (rule 5) by the seed itself, as Brief 1 builds them
#: (`pid_writes.writes`).
GRAPH_PORT = "graph port"


@dataclass
class InferredSummary:
    written: int = 0
    present: int = 0
    #: Links whose end no reference found.
    missing: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing


def inferred_links(
    plan: pid_plan.Plan, *, created_at: datetime
) -> list[tuple[pid_plan.PlanLink, Any]]:
    """Every plan link whose shape's file is the graph port at the seed moment, with the write
    Brief 1 gives it: provenance inferred (who extracted it, how sure), the plan's marking and
    dates, the plan's own id. The ends are still the plan's ids: the seed finds the stored ends
    by reference."""
    types = {
        sh.link_type for sh in pid_plan.LOAD_SHAPES if sh.file == GRAPH_PORT and sh.moment == "seed"
    }
    _, writes = pid_writes.writes(plan, "seed", dataset=FOLDER, created_at=created_at)
    by_id = {w.id: w for w in writes}
    return [
        (link, by_id[pid_plan.link_id(link)])
        for link in pid_plan.links_at(plan, "seed", secret_cleared=True)
        if link.link_type in types
    ]


async def seed_inferred_links(
    plan: pid_plan.Plan,
    *,
    run_as: str = ENGINEER_USERNAME,
    find: Callable[[str, str, str], Awaitable[Any]],
    present: Callable[[str, str, str], Awaitable[bool]],
    write: Callable[[Sequence[Any]], Awaitable[None]],
    now: datetime,
) -> InferredSummary:
    """Writes the inferred links the loads leave out, each between the stored nodes found by
    reference. A link already live (same type and ends) is skipped, so a second seed writes none. A
    link whose end is not found is named and fails the seed."""
    summary = InferredSummary()
    pending: list[Any] = []
    for link, edge in inferred_links(plan, created_at=now):
        ends = []
        for key in (link.source, link.target):
            entity_type, identifier, value = identity_of(plan, key)
            node = await find(entity_type, identifier, value)
            if node is None:
                summary.missing.append(f"{link.link_type} {link.source} -> {link.target}")
                break
            ends.append(node.id)
        else:
            if await present(ends[0], link.link_type, ends[1]):
                summary.present += 1
            else:
                pending.append(
                    edge.model_copy(
                        update={"source": ends[0], "target": ends[1], "created_by": run_as}
                    )
                )
    if pending:
        await write(pending)
        summary.written = len(pending)
    return summary


def inferred_lines(summary: InferredSummary) -> list[str]:
    lines = [
        f"{summary.written} inferred link(s) written, {summary.present} already present "
        f"(the plan's {GRAPH_PORT} links, stored inferred)"
    ]
    for name in summary.missing[:5]:
        lines.append(f"no stored end for {name}")
    if summary.missing:
        lines.append(f"  (first {min(5, len(summary.missing))} of {len(summary.missing)} links)")
    lines.append(f"check {'ok' if summary.ok else 'FAILED'}: every inferred link's ends were found")
    return lines


# --- the case brief (ADR-128 decision 3): the priority requirement and its four ------------------
#
# Script chapter 1: "who is orchestrating throw overs, where and when do packages arrive, how are
# they organised, and what can be done to disrupt them", with the four information requirements
# shown as the case's brief. One requirement per clause, in the script's order. Written whole, in
# one step, as the case's Author, only when the case holds no brief: a second seed writes nothing,
# and an analyst's own brief is never overwritten. Every requirement is written open: the seed marks
# nothing answered (rule 5), and attaches nothing (the saved trend, pattern and assessment it would
# attach are the analyst's, made in the demo).

BRIEF_PRIORITY = (
    "Who is orchestrating the throw-overs, where and when do the packages arrive, how are they "
    "organised, and what can be done to disrupt them?"
)
BRIEF_REQUIREMENTS = (
    "Who is orchestrating the throw-overs?",
    "Where and when do the packages arrive?",
    "How are the throw-overs organised?",
    "What can be done to disrupt them?",
)


class _CaseLevels(Protocol):
    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Any: ...


def brief_author(grant_texts: Sequence[str], seeder: Principal) -> Principal:
    """Who the brief is written as (ADR-128 Amendment 4): the account the seed's own `--grant`
    makes the case's Author. The pack's grants (ADR-113 decision 8) make the demo admin the Author
    and the engineer who runs the seed an Editor, so writing as the seeder would always be refused.
    With no account granted Author, the seeder made the case and is its Author. Two are refused by
    name rather than one guessed. The account is given the seeder's clearance and unit and no
    role: the brief needs the Author level, not a right."""
    authors = [
        account
        for account, level in (parse_grant(text) for text in grant_texts)
        if level is AccessLevel.AUTHOR
    ]
    if not authors:
        return seeder
    if len(authors) > 1:
        raise SeedRefusal(
            f"{', '.join(authors)} are each granted author, so the brief's author is not clear: "
            "grant author to one account."
        )
    return seeder.model_copy(update={"id": authors[0], "roles": []})


async def require_author(cases: _CaseLevels, case_id: str, principal: Principal) -> None:
    """The brief is its case's Author's to write (`brief_author` names who that is). An account
    that is not the Author is refused by name before anything is written, not written through the
    store as someone with no standing."""
    try:
        await cases.get_authorized(case_id, principal, need=AccessLevel.AUTHOR)
    except (InvestigationNotFoundError, InsufficientAccessError) as error:
        raise SeedRefusal(
            f"{principal.id} is not the Author of case {case_id}, so the brief is not written: "
            "give that account the Author level, or run the seed as the case's Author."
        ) from error


@dataclass
class BriefSummary:
    #: The step wrote the brief now (False: the case already held one).
    written: bool = False
    #: How many requirements the brief read back holds.
    requirements: int = 0
    #: The brief read back holds a priority requirement and at least one requirement.
    ok: bool = False


class _BriefWriter(Protocol):
    async def seed_if_empty(
        self, investigation_id: str, principal: Principal, priority: str, requirements: list[str]
    ) -> bool: ...

    async def read(self, investigation_id: str, principal: Principal) -> Any: ...


async def seed_brief(service: _BriefWriter, case_id: str, author: Principal) -> BriefSummary:
    """Writes the PID's brief when the case has none, then reads it back as the author: what is
    reported is what the store holds, not what the write returned."""
    written = await service.seed_if_empty(case_id, author, BRIEF_PRIORITY, list(BRIEF_REQUIREMENTS))
    held = await service.read(case_id, author)
    return BriefSummary(
        written=written,
        requirements=len(held.requirements),
        ok=bool(held.priority) and len(held.requirements) > 0,
    )


def brief_lines(summary: BriefSummary, author_id: str) -> list[str]:
    if summary.written:
        said = (
            f"case brief: the priority requirement and {summary.requirements} information "
            f"requirements written, as {author_id}, all open"
        )
    else:
        said = (
            f"case brief: the case already holds a brief ({summary.requirements} information "
            "requirements), left alone"
        )
    return [
        said,
        f"check {'ok' if summary.ok else 'FAILED'}: the case holds a brief with a priority "
        "requirement and information requirements",
    ]


# --- the demo numbers (Amendment 32) -------------------------------------------------------------
#
# Brief 2 section 8 and Brief 1 section 5.8's table (without its Access row, ADR-120 Amendment 16),
# computed from the stores as the persona and held to the plan's own constants. Each check says what
# it measured. A figure the brief quotes is never typed here: it is read from `pid_plan`, or derived
# from the plan's own entities and links at the moment the case is at.


class _CheckGraph(Protocol):
    """The reads the checks make of the graph: the port's own methods, no more."""

    async def find_node(
        self, entity_type: str, identifier_field: str, value: str, principal: Principal
    ) -> Node | None: ...

    async def search_nodes(
        self, query: str, principal: Principal, *, limit: int = 20
    ) -> list[Node]: ...

    async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph: ...

    async def match(self, pattern: PatternQuery, principal: Principal) -> Subgraph: ...

    async def match_count(
        self, pattern: PatternQuery, principal: Principal, *, ceiling: int
    ) -> int: ...


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    #: True for a check with nothing to read yet (the reports load in chapter 4).
    skipped: bool = False


class _NotStored(Exception):
    """A subject the plan holds and the store, as the persona reads it, does not."""


def moment_of(records: Sequence[LoadRecord]) -> pid_plan.Moment:
    """The moment the case is at, from its standing loads: the seed's, once the reports and their
    incident links are loaded (chapter 4), and once batch 2 is too (chapter 9)."""
    standing = {r.recipe_id for r in records}
    if not {reports_recipe_id(), incidents_recipe_id()} <= standing:
        return "seed"
    return "chapter9" if any(is_batch_2(r) for r in records) else "chapter4"


async def _stored(graph: _CheckGraph, principal: Principal, plan: pid_plan.Plan, key: str) -> Node:
    entity_type, identifier, value = identity_of(plan, key)
    node = await graph.find_node(entity_type, identifier, value, principal)
    if node is None:
        raise _NotStored(f"{key} ({entity_type} {identifier}={value}) is not in the store")
    return node


async def _expand(
    graph: _CheckGraph,
    principal: Principal,
    ids: Sequence[str],
    edge_types: Sequence[str] | None = None,
    direction: str = "both",
) -> Subgraph:
    return await graph.expand(
        ExpandRequest(
            node_ids=list(ids),
            depth=1,
            edge_types=list(edge_types) if edge_types is not None else None,
            direction=direction,  # type: ignore[arg-type]
        ),
        principal,
    )


def _visible_links(plan: pid_plan.Plan, moment: pid_plan.Moment) -> list[pid_plan.PlanLink]:
    """What the demo analyst's persona may see of the plan by the end of `moment`."""
    return list(pid_plan.links_at(plan, moment, secret_cleared=False))


def _other_end(source: str, target: str, key: str) -> str:
    return target if source == key else source


async def _check_j1(
    graph: _CheckGraph, principal: Principal, plan: pid_plan.Plan, moment: pid_plan.Moment
) -> tuple[bool, str]:
    """J1: the principal's star. The plan's own links, counted, must equal its constant for the
    moment (45 in Act 1, 49 after chapter 4) and the store's star must hold exactly those, type for
    type."""
    me = await _stored(graph, principal, plan, "principal")
    star = await _expand(graph, principal, [me.id])
    mine = {e.id: e for e in star.edges if me.id in (e.source, e.target)}
    got = Counter(e.type for e in mine.values())
    planned = [lk for lk in _visible_links(plan, moment) if "principal" in (lk.source, lk.target)]
    want = Counter(lk.link_type for lk in planned)
    stated = (
        pid_plan.PRINCIPAL_LINK_COUNT_ACT1 if moment == "seed" else pid_plan.PRINCIPAL_LINK_COUNT
    )
    if len(planned) != stated:
        return False, f"the plan itself holds {len(planned)} links for the principal, not {stated}"
    detail = f"the principal has {len(mine)} links at the {moment} moment (the plan says {stated})"
    if len(mine) != stated or got != want:
        differ = dict((want - got) + (got - want))
        return False, f"{detail}; by type they differ: {differ}"
    return True, detail


async def _check_j2(
    graph: _CheckGraph, principal: Principal, plan: pid_plan.Plan, moment: pid_plan.Moment
) -> tuple[bool, str]:
    """J2: a search for the coordinator's number finds one `Endpoint`; every account the plan has
    call it links to it, the PIN accounts among them, each used by a prisoner."""
    number = str(plan.entity("number:coordinator").properties["value_normalised"])
    found = await search(graph, SearchRequest(query=number), principal)  # type: ignore[arg-type]
    endpoints = [n for n in found.nodes if n.type == "Endpoint"]
    if len(endpoints) != 1:
        return False, f"a search for {number} finds {len(endpoints)} Endpoint(s), not one"
    endpoint = endpoints[0]
    callers = sorted(
        {
            _other_end(lk.source, lk.target, "number:coordinator")
            for lk in _visible_links(plan, moment)
            if lk.link_type == "COMMUNICATED_WITH"
            and "number:coordinator" in (lk.source, lk.target)
        }
    )
    pins = [k for k in callers if k.startswith("pin:")]
    wanted = {(await _stored(graph, principal, plan, k)).id for k in callers}
    star = await _expand(graph, principal, [endpoint.id], ["COMMUNICATED_WITH"])
    linked = {_other_end(e.source, e.target, endpoint.id) for e in star.edges}
    detail = (
        f"one Endpoint for {number}; {len(pins)} PIN accounts link to it, each used by a prisoner"
    )
    if linked != wanted:
        return False, (
            f"{detail}: but {len(linked)} accounts call it and the plan has {len(wanted)}"
        )
    pin_ids = [(await _stored(graph, principal, plan, k)).id for k in pins]
    users = await _expand(graph, principal, pin_ids, ["USES"], "in")
    by_id = {n.id: n for n in users.nodes}
    for pin_id, key in zip(pin_ids, pins, strict=True):
        prisoners = [
            by_id[e.source]
            for e in users.edges
            if e.target == pin_id
            and e.source in by_id
            and by_id[e.source].type == "Person"
            and "prison_number" in by_id[e.source].properties
        ]
        if not prisoners:
            return False, f"{detail}: but {key} is used by no prisoner"
    return True, detail


async def _throw_overs_by_yard(
    graph: _CheckGraph, principal: Principal, plan: pid_plan.Plan
) -> dict[str, dict[str, Node]]:
    """Each yard's throw-over incidents, as the store holds them, by the yard's two-digit code."""
    yards = {
        code: await _stored(graph, principal, plan, f"yard:{code}") for code in pid_plan.YARD_COUNTS
    }
    code_of = {yard.id: code for code, yard in yards.items()}
    star = await _expand(graph, principal, [y.id for y in yards.values()], ["OCCURRED_AT"], "in")
    nodes = {n.id: n for n in star.nodes}
    found: dict[str, dict[str, Node]] = {code: {} for code in yards}
    for edge in star.edges:
        incident = nodes.get(edge.source)
        if (
            edge.target in code_of
            and incident is not None
            and incident.type == "Incident"
            and incident.properties.get("category") == "throw_over"
        ):
            found[code_of[edge.target]][incident.id] = incident
    return found


async def _check_ch2(
    graph: _CheckGraph, principal: Principal, plan: pid_plan.Plan, moment: pid_plan.Moment
) -> tuple[bool, str]:
    """Ch2: the throw-overs by yard are the plan's multiset, the four hotspot yards hold their share
    of the total, and each adjoins Wing F."""
    by_yard = await _throw_overs_by_yard(graph, principal, plan)
    counts = {code: len(incidents) for code, incidents in by_yard.items()}
    total = sum(counts.values())
    hotspot = sum(counts[c] for c in pid_plan.HOTSPOT_YARDS)
    hotspot_wanted = sum(pid_plan.YARD_COUNTS[c] for c in pid_plan.HOTSPOT_YARDS)
    wing_f = await _stored(graph, principal, plan, "zone:wing-f")
    yard_ids = {code: (await _stored(graph, principal, plan, f"yard:{code}")).id for code in counts}
    parts = await _expand(graph, principal, list(yard_ids.values()), ["PART_OF"], "out")
    adjoining = {
        code
        for code, yard_id in yard_ids.items()
        for edge in parts.edges
        if edge.source == yard_id and edge.target == wing_f.id
    }
    planned = {
        lk.source.removeprefix("yard:")
        for lk in _visible_links(plan, moment)
        if lk.link_type == "PART_OF"
        and lk.target == "zone:wing-f"
        and lk.source.startswith("yard:")
    }
    detail = (
        f"four hotspot yards hold {hotspot} of {total} throw-overs "
        f"({pid_plan.TOTAL_THROW_OVERS} in the plan), {hotspot / max(total, 1):.1%}, "
        "all adjoining Wing F"
    )
    problems = []
    if counts != dict(pid_plan.YARD_COUNTS):
        problems.append("the yards' counts are not the plan's")
    if total != pid_plan.TOTAL_THROW_OVERS or hotspot != hotspot_wanted:
        problems.append(f"the plan has {hotspot_wanted} of {pid_plan.TOTAL_THROW_OVERS}")
    if adjoining != planned or not set(pid_plan.HOTSPOT_YARDS) <= adjoining:
        problems.append(
            f"the yards adjoining Wing F are {sorted(adjoining)}, not {sorted(planned)}"
        )
    return (not problems), detail + ("" if not problems else f": {'; '.join(problems)}")


def _when(node: Node) -> datetime:
    value = node.properties["occurred_at"]
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


async def _check_ch3(
    graph: _CheckGraph, principal: Principal, plan: pid_plan.Plan, moment: pid_plan.Moment
) -> tuple[bool, str]:
    """Ch3: the throw-overs by hour and by weekday are the plan's multisets: the peak windows (the
    hours the plan counts above the mean), the weekend and the Sundays."""
    by_yard = await _throw_overs_by_yard(graph, principal, plan)
    times = [_when(n) for incidents in by_yard.values() for n in incidents.values()]
    hours = Counter(t.hour for t in times)
    weekdays = Counter(t.weekday() for t in times)
    mean = pid_plan.TOTAL_THROW_OVERS / 24
    peak = {h for h, c in pid_plan.HOUR_COUNTS.items() if c > mean}
    in_peak = sum(c for h, c in hours.items() if h in peak)
    peak_wanted = sum(pid_plan.HOUR_COUNTS[h] for h in peak)
    weekend = weekdays[5] + weekdays[6]
    weekend_wanted = pid_plan.WEEKDAY_COUNTS[5] + pid_plan.WEEKDAY_COUNTS[6]
    detail = (
        f"{in_peak} of {len(times)} throw-overs in the {len(peak)} peak hours, weekends {weekend} "
        f"({weekend / max(len(times), 1):.1%}), Sundays {weekdays[6]}"
    )
    problems = []
    if in_peak != peak_wanted:
        problems.append(f"the plan has {peak_wanted} in the peak hours")
    if weekend != weekend_wanted or weekdays[6] != pid_plan.WEEKDAY_COUNTS[6]:
        problems.append(
            f"the plan has {weekend_wanted} at weekends and {pid_plan.WEEKDAY_COUNTS[6]} on Sundays"
        )
    if dict(hours) != {h: c for h, c in pid_plan.HOUR_COUNTS.items() if c} or dict(
        weekdays
    ) != dict(pid_plan.WEEKDAY_COUNTS):
        problems.append("the hours or the weekdays are not the plan's multisets")
    return (not problems), detail + ("" if not problems else f": {'; '.join(problems)}")


async def _selected_reports(
    graph: _CheckGraph, principal: Principal, plan: pid_plan.Plan
) -> tuple[dict[str, Node], int, int]:
    """The reports the one pattern selects, as the persona reads them: the pattern is the plan's,
    with its zone pinned to the Wing F node as the store holds it. Also the count the port gives for
    it and the pattern's own limit (rule 2: a count that reaches the limit may have been cut)."""
    wing_f = await _stored(graph, principal, plan, "zone:wing-f")
    raw = copy.deepcopy(pid_plan.REPORT_PATTERN)
    for node in raw["nodes"]:
        if node["var"] == "zone":
            node["node_id"] = wing_f.id
    pattern = PatternQuery.model_validate(raw)
    matched = await graph.match(pattern, principal)
    reports = {n.id: n for n in matched.nodes if n.type == "Document"}
    counted = await graph.match_count(pattern, principal, ceiling=10 * pattern.limit)
    return reports, counted, pattern.limit


async def _check_ch5(
    graph: _CheckGraph, principal: Principal, plan: pid_plan.Plan, moment: pid_plan.Moment
) -> tuple[bool, str]:
    """Ch5: the one pattern selects the plan's reports, none cut short, and the plan's number of
    them name a person."""
    reports, counted, limit = await _selected_reports(graph, principal, plan)
    star = await _expand(graph, principal, list(reports), ["MENTIONED_IN"], "in")
    people = {n.id for n in star.nodes if n.type == "Person"}
    used = {e.target for e in star.edges if e.source in people and e.target in reports}
    detail = (
        f"the one pattern selects {len(reports)} reports ({pid_plan.REPORTS_SELECTED} in the "
        f"plan), {len(used)} naming a person ({pid_plan.REPORTS_USED})"
    )
    problems = []
    if len(reports) != pid_plan.REPORTS_SELECTED:
        problems.append("the selection is not the plan's")
    if counted >= limit:
        problems.append(f"the count {counted} reaches the pattern's limit {limit}")
    if len(used) != pid_plan.REPORTS_USED:
        problems.append("the reports naming a person are not the plan's")
    return (not problems), detail + ("" if not problems else f": {'; '.join(problems)}")


async def _check_ch6(
    graph: _CheckGraph, principal: Principal, plan: pid_plan.Plan, moment: pid_plan.Moment
) -> tuple[bool, str]:
    """Ch6: the principal and the coordinator are connected by the visits the plan has (the
    coordinator visits the principal), the one payer funds the plan's prisoners through their cash
    accounts, and the shared-number pattern is J2's."""
    links = _visible_links(plan, moment)
    coordinator = await _stored(graph, principal, plan, "coordinator")
    visits = {
        lk.target: lk.occurrences
        for lk in links
        if lk.link_type == "VISITED" and lk.source == "coordinator"
    }
    wanted_visits = {(await _stored(graph, principal, plan, k)).id: n for k, n in visits.items()}
    star = await _expand(graph, principal, [coordinator.id], ["VISITED"], "out")
    got_visits = {e.target: e.occurrences for e in star.edges if e.source == coordinator.id}
    account = await _stored(graph, principal, plan, "account:payer")
    funding = {
        lk.target: lk.occurrences
        for lk in links
        if lk.link_type == "TRANSACTED" and lk.source == "account:payer"
    }
    wanted_funding = {(await _stored(graph, principal, plan, k)).id: n for k, n in funding.items()}
    paid = await _expand(graph, principal, [account.id], ["TRANSACTED"], "out")
    got_funding = {e.target: e.occurrences for e in paid.edges if e.source == account.id}
    funded_people = {
        lk.source
        for lk in links
        if lk.link_type == "USES"
        and lk.target in funding
        and plan.entity(lk.source).entity_type == "Person"
    }
    wanted_people = {(await _stored(graph, principal, plan, k)).id for k in funded_people}
    owners = await _expand(graph, principal, list(got_funding), ["USES"], "in")
    kinds = {n.id: n for n in owners.nodes}
    got_people = {
        e.source
        for e in owners.edges
        if e.target in got_funding and e.source in kinds and kinds[e.source].type == "Person"
    }
    detail = (
        f"the coordinator visits {len(got_visits)} prisoners and one payer funds "
        f"{len(got_people)} through {len(got_funding)} accounts"
    )
    problems = []
    if got_visits != wanted_visits or not wanted_visits:
        problems.append("the coordinator's visits are not the plan's")
    if got_funding != wanted_funding or not wanted_funding:
        problems.append("the payer's transfers are not the plan's")
    if got_people != wanted_people:
        problems.append("the people those accounts belong to are not the plan's")
    return (not problems), detail + ("" if not problems else f": {'; '.join(problems)}")


_ACCOUNT_NUMBER = re.compile(r"SYN-\d+")


async def _check_ch11(
    graph: _CheckGraph, principal: Principal, plan: pid_plan.Plan, moment: pid_plan.Moment
) -> tuple[bool, str]:
    """Ch11: the four gaps are absent from the store as they are from the plan. The third member is
    named in no text document; the unidentified number is reached only by calls and has no owner;
    the account a report mentions that no entity carries is found by no search; and no person is
    linked to a throw-over."""
    problems = []
    third = await _stored(graph, principal, plan, "third_member")
    around = await _expand(graph, principal, [third.id])
    kinds = {n.id: n for n in around.nodes}
    for edge in around.edges:
        other = kinds.get(_other_end(edge.source, edge.target, third.id))
        if (
            other is not None
            and other.type == "Document"
            and other.properties.get("media_kind") != "image"
        ):
            problems.append("the third member is joined to a text document")
            break
    number = await _stored(graph, principal, plan, "number:unidentified")
    reaching = await _expand(graph, principal, [number.id])
    kinds = {n.id: n for n in reaching.nodes}
    if not reaching.edges or any(e.type != "COMMUNICATED_WITH" for e in reaching.edges):
        problems.append("the unidentified number is reached by more than calls, or by none")
    if any(
        kinds[_other_end(e.source, e.target, number.id)].type in ("Person", "Organisation")
        for e in reaching.edges
        if _other_end(e.source, e.target, number.id) in kinds
    ):
        problems.append("the unidentified number has a holder")
    held = {str(v) for e in plan.entities for v in e.properties.values()}
    unheld = sorted(
        {
            account
            for text in plan.report_texts.values()
            for account in _ACCOUNT_NUMBER.findall(text)
        }
        - held
    )
    if len(unheld) != 1:
        problems.append(f"the plan has {len(unheld)} accounts that only a report mentions, not one")
    for account in unheld:
        if (await search(graph, SearchRequest(query=account), principal)).nodes:  # type: ignore[arg-type]
            problems.append("the found account has a holder")
    by_yard = await _throw_overs_by_yard(graph, principal, plan)
    incident_ids = sorted({i for incidents in by_yard.values() for i in incidents})
    touching = await _expand(graph, principal, incident_ids)
    kinds = {n.id: n for n in touching.nodes}
    for edge in touching.edges:
        for end in (edge.source, edge.target):
            if end in kinds and kinds[end].type == "Person":
                problems.append("a person is linked to a throw-over")
                break
        else:
            continue
        break
    detail = (
        "no third member in a text report, an unidentified number with no holder, an account "
        "with no holder, no person linked to throwing"
    )
    return (not problems), detail if not problems else f"{detail}: {'; '.join(problems)}"


async def _check_s2(
    graph: _CheckGraph, principal: Principal, plan: pid_plan.Plan, moment: pid_plan.Moment
) -> tuple[bool, str]:
    """The handling row: at least one used report carries `S2`, and only the plan's `S2` reports do.
    (Export's refusal of a selection holding one is the Conduit's, tested there.)"""
    reports, _counted, _limit = await _selected_reports(graph, principal, plan)
    marked = {
        str(n.properties.get("message_id"))
        for n in reports.values()
        if n.handling.sanitisation_code == "S2"
    }
    planned = {
        identity_of(plan, e.key)[2]
        for e in plan.entities
        if e.entity_type == "Document" and e.handling.sanitisation_code == "S2"
    }
    detail = f"{len(marked)} of the {len(reports)} selected reports carry S2"
    if not marked or not marked <= planned:
        return False, f"{detail}: expected at least one, and only the plan's"
    return True, detail


#: Each check's name, what reads it, and the moments it has something to read at. The order is the
#: brief's. The reports load in chapter 4, so a number about them is not run at the seed moment.
_CHECKS: tuple[tuple[str, Callable[..., Awaitable[tuple[bool, str]]], tuple[str, ...]], ...] = (
    ("J1", _check_j1, ()),
    ("J2", _check_j2, ()),
    ("Ch2", _check_ch2, ()),
    ("Ch3", _check_ch3, ()),
    ("Ch5", _check_ch5, ("chapter4", "chapter9")),
    ("Ch6", _check_ch6, ()),
    ("Ch11 gaps", _check_ch11, ()),
    ("Handling S2", _check_s2, ("chapter4", "chapter9")),
)


async def run_demo_checks(
    graph: _CheckGraph, principal: Principal, plan: pid_plan.Plan, moment: pid_plan.Moment
) -> list[CheckResult]:
    """Brief 2 section 8's demo numbers over the stores at `moment`, as `principal`. A check that
    cannot run (the store raised, a subject the plan holds is not stored) is a failed check, never a
    pass."""
    results: list[CheckResult] = []
    for name, check, only_at in _CHECKS:
        if only_at and moment not in only_at:
            results.append(
                CheckResult(
                    name,
                    True,
                    f"not run at the {moment} moment: the reports load in chapter 4",
                    skipped=True,
                )
            )
            continue
        try:
            ok, detail = await check(graph, principal, plan, moment)
        except Exception as error:  # a check that cannot run has failed
            results.append(
                CheckResult(name, False, f"could not be run: {type(error).__name__}: {error}")
            )
            continue
        results.append(CheckResult(name, ok, detail))
    return results


def demo_check_lines(results: Sequence[CheckResult]) -> tuple[list[str], bool]:
    """A line for each demo number, and whether every one held (one not run is not a failure)."""
    lines = []
    for r in results:
        if r.skipped:
            lines.append(f"check not run: {r.name}: {r.detail}")
        else:
            lines.append(f"check {'ok' if r.ok else 'FAILED'}: {r.name}: {r.detail}")
    return lines, all(r.ok for r in results)


def exit_code(*, files_ok: bool, pictures_ok: bool, demo_ok: bool, brief_ok: bool = True) -> int:
    """0 only when every file was read whole, every picture found, every demo number held and the
    case's brief is there."""
    return 0 if files_ok and pictures_ok and demo_ok and brief_ok else 1


# --- the seed ------------------------------------------------------------------------------------


async def seed_all(
    principal: Principal,
    *,
    scope: Callable[[Principal], Awaitable[Principal]],
    enter_recipes: Callable[[Principal], Awaitable[Any]],
    run: Callable[[Principal], Awaitable[Any]],
    pictures: Callable[[Principal], Awaitable[Any]],
    checks: Callable[[Principal], Awaitable[Any]],
) -> tuple[Any, Any, Any, Any]:
    """The seed's steps in their order, the loader scoped to the case before any of them writes: the
    recipes, the runs, the pictures, the demo numbers. A loader the scope leaves unscoped stops it.
    The pictures step alone is handed `EDIT_GRAPH` as well (Amendment 31)."""
    scoped = await scope(principal)
    if scoped.datasets is None:
        raise RuntimeError("the seed worker is not scoped to the case: nothing was written")
    recipes = await enter_recipes(scoped)
    runs = await run(scoped)
    pics = await pictures(with_edit_graph(scoped))
    numbers = await checks(scoped)
    return recipes, runs, pics, numbers


# --- the reset -----------------------------------------------------------------------------------


def is_batch_2(record: LoadRecord) -> bool:
    """A load of the seized-phone recipe whose source is batch 2 anywhere under the dataset's
    folder, whether read from `incoming/` or from the listed folder."""
    parts = Path(record.source).parts
    return (
        record.recipe_id == comms_recipe_id()
        and parts[-1:] == (pid_files.BATCH_2,)
        and FOLDER in parts
    )


def choose_reset(records: Sequence[LoadRecord]) -> list[LoadRecord]:
    """The loads the reset reverts, newest first by load id: every unreverted load of the
    incident-to-report recipe and of the reports recipe, and of the seized-phone recipe only where
    its source is batch 2 under the dataset's folder (listed, or still under `incoming/`)."""
    wanted = {incidents_recipe_id(), reports_recipe_id()}
    return sorted(
        (r for r in records if r.recipe_id in wanted or is_batch_2(r)),
        key=lambda r: r.load_id,
        reverse=True,
    )


class _Graph(Protocol):
    async def live_edges_touching(self, node_ids: Sequence[str]) -> set[str]: ...

    async def get_edges(self, edge_ids: Sequence[str], principal: Principal) -> list[Any]: ...


class _LedgerWithRecords(_Ledger, Protocol):
    async def load_record(self, load_id: str) -> LoadRecord | None: ...


CANNOT_UNDO = (
    "What the reset cannot undo:",
    "  - Reverted runs stay in the ledger, so Data feeds shows a rehearsal run as the last run of "
    "the incident-to-report recipe or of the seized-phone recipe. No run time is faked.",
    "  - Alerts and the cases they opened.",
    "  - Review-queue findings.",
    "  - The contents of working sets.",
    "  - Hotlists and saved patterns.",
    "  - The reports recipe's climbing version number, and its commits in the recipe repository.",
    "  Nothing is deleted by hand.",
)


def is_starting_draft(row: Any, source_location: str, owning_unit: str) -> bool:
    """Whether the reports recipe's latest row is already its starting draft: a draft with Map not
    done, the starting pipeline, and the source, unit and dataset the seed gave it. Then a reset
    that reverted nothing has no new version to write (Amendment 30)."""
    return bool(
        row.status is StudioRecipeStatus.DRAFT
        and row.row_template is None
        and not row.unmapped_fields
        and row.deduplicate is None
        and row.pipeline == starting_pipeline(source_location)
        and row.source_location == source_location
        and row.owning_unit == owning_unit
        and row.dataset_id == FOLDER
    )


async def _say_resting_links(
    load: LoadRecord,
    refusal: Any,
    *,
    ledger: _LedgerWithRecords,
    graph: _Graph,
    worker: Principal,
    show_ids: bool,
    say: Callable[[str], None],
) -> None:
    """A refusal because live links outside a load rest on its nodes, in the engineer's own terms
    (Amendment 34): the links he can read, counted, and by type and id when he asked
    (`--show-ids`). The refusal's own count includes links he may not read, so it is not printed,
    and nothing says how many are left out."""
    record = await ledger.load_record(load.load_id)
    resting = await links_resting_on([record], graph) if record is not None else frozenset()  # type: ignore[arg-type]
    readable = await graph.get_edges(sorted(resting), worker) if resting else []
    say(
        f"load {refusal.load_id!r} cannot be reverted: {len(readable)} live link(s) you can read, "
        "outside it, rest on nodes it created"
    )
    if show_ids:
        for edge in readable[:LISTED]:
            say(f"  {edge.type} {edge.id}")
        if len(readable) > LISTED:
            say(f"  (showing {LISTED} of {len(readable)})")
    else:
        say("(Run with --show-ids to list them by type and id.)")


async def reset_live(
    *,
    case_id: str,
    root: Path,
    ledger: _LedgerWithRecords,
    graph: _Graph,
    worker: Principal,
    revert: Callable[..., Awaitable[Any]],
    deps: Any,
    now: datetime,
    restore_draft: Callable[[], Awaitable[None]],
    draft_is_starting: Callable[[], Awaitable[bool]],
    rewrite_reports: Callable[[], None],
    say: Callable[[str], None],
    show_ids: bool = False,
) -> int:
    """The rehearsal reset (Amendment 23, "The reset", as Amendment 32 simplified it). Reverts each
    chosen load, newest first. Exit 0 reset; 1 a revert was refused (it stops, names the refusal by
    its counts, and gives the restore procedure, with the draft and the files as they were); 2 a
    revert stopped part way (run it again). Only a complete run restores R9's draft and the
    files."""
    found = await ledger.unreverted_loads(
        case_id, [incidents_recipe_id(), reports_recipe_id(), comms_recipe_id()]
    )
    chosen = choose_reset(found)
    done: list[str] = []
    for load in chosen:
        try:
            await revert(load.load_id, reverted_by=worker.id, deps=deps, now=now)
        except RevertRefused as refused:
            for refusal in refused.refusals:
                if refusal.reason == "rests_on_by_live_links":
                    await _say_resting_links(
                        load,
                        refusal,
                        ledger=ledger,
                        graph=graph,
                        worker=worker,
                        show_ids=show_ids,
                        say=say,
                    )
                else:
                    say(refusal.words())
            say(
                f"Stopped at {load.load_id}; reverted: {', '.join(done) or 'none'}. The draft and "
                "the files are as they were. The reset cannot go on past a revert that refuses, "
                "and a reseed cannot clear a case whose loads have links resting on them."
            )
            for line in restore_steps():
                say(line)
            return 1
        except RevertIncomplete as incomplete:
            say(str(incomplete))
            say(
                f"Reverted so far: {', '.join(done) or 'none'}. Run the reset again to complete it."
            )
            return 2
        done.append(load.load_id)
        say(f"reverted {load.load_id}")
    if not chosen:
        say("There is no load to revert in this case.")
    if not done and await draft_is_starting():
        say("The reports recipe is already at its starting draft; no new version was written.")
    else:
        await restore_draft()
        say("restored the reports recipe to its starting draft")
    rewrite_reports()
    say(f"rewrote {pid_files.REPORTS}")
    listed = listed_folder(root)
    keep = {stage.file for stage in SEED_ORDER if stage.file != pid_files.BATCH_2}
    if listed.is_dir():
        for path in sorted(listed.iterdir()):
            if path.is_file() and path.name not in keep:
                path.unlink()
                say(f"removed {path.name} from the listed folder")
    for line in CANNOT_UNDO:
        say(line)
    return 0


# --- the fallback --------------------------------------------------------------------------------


_VERSION_LINE = re.compile(r"^version: \d+$", re.MULTILINE)


def with_version(text: str, version: int) -> str:
    """The recipe file with its `version:` line at `version`, and nothing else changed."""
    if _VERSION_LINE.search(text) is None:
        raise ValueError("the recipe file has no `version:` line to set")
    return _VERSION_LINE.sub(f"version: {version}", text, count=1)


_DECLARATIONS = ("units", "handling_columns")


def connect_fields(recipe: Recipe) -> dict[str, Any]:
    """What Connect holds of a recipe, as a row holds it: the connector, the source's marking with
    the `units` and `handling_columns` it declares beside it (always present, so that a stale one an
    engineer left is cleared), and the legal basis."""
    handling: dict[str, Any] = dict(recipe.defaults.handling)
    handling["units"] = list(recipe.defaults.units)
    handling["handling_columns"] = dict(recipe.defaults.handling_columns)
    return {
        "connector_profile": recipe.connector.profile,
        "handling": handling,
        "legal_basis": recipe.defaults.legal_basis,
    }


def _declared(handling: Mapping[str, Any]) -> dict[str, Any]:
    """A handling with an empty declaration left out, since a row entered from a file that has none
    holds none, and one cleared by an update holds an empty one: the same thing."""
    return {k: v for k, v in handling.items() if not (k in _DECLARATIONS and not v)}


def row_differences(row: StudioRecipeDraft, recipe: Recipe) -> list[str]:
    """The fields of a registry row (Connect's and Map's) that are not the committed recipe's, by
    name. Empty when the row and the file agree."""
    differing = []
    wanted = connect_fields(recipe)
    if row.connector_profile != wanted["connector_profile"]:
        differing.append("connector_profile")
    if _declared(row.handling) != _declared(wanted["handling"]):
        differing.append("handling")
    if row.legal_basis != wanted["legal_basis"]:
        differing.append("legal_basis")
    if row.row_template != recipe.row_template:
        differing.append("row_template")
    if list(row.unmapped_fields) != list(recipe.unmapped_fields):
        differing.append("unmapped_fields")
    if row.deduplicate != recipe.deduplicate:
        differing.append("deduplicate")
    return differing


async def publish_reports_fallback(
    store: Any,
    principal: Principal,
    *,
    ontology: Any,
    scheme: HandlingScheme,
    repo_root: Path,
    commit: Callable[..., Awaitable[str]],
    audit: Any,
    now: datetime,
) -> StudioRecipeDraft:
    """Publishes the committed, fully mapped reports recipe in place of a live mapping that went
    wrong, as the Conduit's publish route would (Amendment 30): at the draft row's version, with the
    row's content the file's (Connect's fields included, so the row and the committed file agree,
    which is checked after the writes and before anything is committed), the unrunnable-pipeline
    gate applied, the recipe committed with its pipeline as `build_recipe` builds it, the row
    flipped, and the `publish_studio_recipe` audit entry written. Goes through the store's own
    methods as the persona (the draft is in its unit and dataset), so only Postgres and the recipe
    repository are written. It skips the route's role, case Editor and Verify checks
    (`FALLBACK_SKIPS`). Refuses a recipe that is not a draft."""
    recipe_id = reports_recipe_id()
    draft = await store.get(recipe_id)
    if draft.status is not StudioRecipeStatus.DRAFT:
        raise SeedRefusal(
            f"{recipe_id} is {draft.status.value}, not a draft, so there is nothing to publish "
            "in its place (run the reset first to restore the draft)"
        )
    committed = (FIXTURES / reports_recipe_file()).read_text(encoding="utf-8")
    text = with_version(committed, draft.version)
    recipe = Recipe.model_validate(yaml.safe_load(text))
    # Before any write (Amendment 34): the row must be the seed's own, and what the writes below
    # would leave must be the committed file's.
    foreign = [
        name
        for name, got, wanted in (
            ("dataset_id", draft.dataset_id, FOLDER),
            ("label", draft.label, recipe.label),
        )
        if got != wanted
    ]
    if foreign:
        raise SeedRefusal(
            f"the draft of {recipe_id} is not the one the seed made: its "
            f"{', '.join(f'{n} is {getattr(draft, n)!r}' for n in foreign)}, so nothing was written"
        )
    fields = connect_fields(recipe)
    would_leave = draft.model_copy(
        update={
            "connector_profile": fields["connector_profile"],
            "handling": fields["handling"],
            "legal_basis": fields["legal_basis"],
            "deduplicate": recipe.deduplicate,
            "row_template": recipe.row_template,
            "unmapped_fields": list(recipe.unmapped_fields),
        }
    )
    differing_before = row_differences(would_leave, recipe)
    if differing_before:
        raise SeedRefusal(
            f"the writes would leave {recipe_id} differing from the committed file in "
            f"{', '.join(differing_before)}, so nothing was written"
        )
    check_seeded_recipe(recipe.model_copy(update={"pipeline": draft.pipeline}), ontology, scheme)
    if draft.pipeline is not None:
        unrunnable = pipeline_run_violations(draft.pipeline)
        if unrunnable:
            raise SeedRefusal(
                "the pipeline cannot be published, as the route refuses it: "
                f"{'; '.join(unrunnable)}"
            )
    await store.update_draft(
        recipe_id,
        principal,
        connector_profile=fields["connector_profile"],
        handling=fields["handling"],
        legal_basis=fields["legal_basis"],
        deduplicate=recipe.deduplicate,
    )
    await store.update_row_template(
        recipe_id,
        principal,
        row_template=recipe.row_template,
        unmapped_fields=list(recipe.unmapped_fields),
    )
    row = await store.get(recipe_id)
    differing = row_differences(row, recipe)
    if differing:
        raise SeedRefusal(
            f"the registry row of {recipe_id} still differs from the committed file in "
            f"{', '.join(differing)} after the fallback wrote them, so it is not committed or "
            "published"
        )
    await store.mark_verified(recipe_id, row.version, now=now)
    pins = pack_versions_for(row.pipeline, row.row_template, ontology)
    built = build_recipe(
        row,
        ontology_version=ontology.version,
        pack_versions=pins,
        schedule_cron=None,
        schedule_watch=None,
    )
    git_path = await commit(
        recipe_id, serialise_recipe(built).encode("utf-8"), version=row.version, repo_root=repo_root
    )
    published = await store.publish(
        recipe_id,
        principal,
        ontology_version=ontology.version,
        pack_versions=pins,
        git_path=git_path,
        schedule_cron=None,
        schedule_watch=None,
        now=now,
    )
    await audit.record(
        principal=principal,
        action="publish_studio_recipe",
        resolved_query={
            "recipe_id": recipe_id,
            "git_path": git_path,
            # `mark_verified` above is the operator's say-so: no Verify ran (Amendment 34).
            "verified_by": "operator's attestation",
            "verified_note": "no Verify ran; the committed file is what the golden test ran",
        },
        result_cardinality=1,
    )
    return cast(StudioRecipeDraft, published)


# --- the command ---------------------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.seed_pid",
        description="Seeds the Prison Intelligence Dataset (synthetic), or resets or carries "
        "a mid-demo step of it.",
    )
    add_case_arguments(parser)
    parser.add_argument("--org-unit", default=os.environ.get("OSPREY_ORG_UNIT", WORKER_UNIT))
    parser.add_argument(
        "--ingest-root", type=Path, default=None, help="Default: OSPREY_INGEST_ROOT."
    )
    parser.add_argument(
        "--run-as",
        default=None,
        help="The principal id to load as: the demo engineer's sign-in subject. Default: his "
        "username, which a local stack without a sign-in has.",
    )
    parser.add_argument(
        "--show-ids",
        action="store_true",
        help="With --reset-live: list the links that stop a revert by type and id, not counts.",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--reset-live", action="store_true", help="The rehearsal reset.")
    modes.add_argument(
        "--check",
        action="store_true",
        help="Run every demo number for the moment the stored loads reach; loads nothing.",
    )
    modes.add_argument(
        "--release-batch-2", action="store_true", help="Chapter 9: list batch 2 (Conduit stays up)."
    )
    modes.add_argument(
        "--publish-reports-fallback",
        action="store_true",
        help="Publish the committed reports recipe in place of a live mapping (Conduit stays up).",
    )
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    args.mode = (
        "reset" if args.reset_live
        else "check" if args.check
        else "release" if args.release_batch_2
        else "fallback" if args.publish_reports_fallback
        else "seed"
    )  # fmt: skip
    if args.mode == "seed":
        check_case_arguments(parser, args)
    elif args.mode in ("reset", "check") and not (args.case_name or args.investigation_scope):
        flag = "--reset-live" if args.mode == "reset" else "--check"
        parser.error(f"{flag} needs --case-name or --investigation-scope")
    return args


async def _find_case(dsn: str, args: argparse.Namespace, seeder: Principal) -> str | None:
    """The case the arguments name: by id as given, or the one case of the given name (two of one
    name are refused, `one_case`); None when there is none."""
    if args.investigation_scope:
        return str(args.investigation_scope)
    store = await InvestigationStore.connect(dsn)
    try:
        named = [c.id for c, _ in await store.list_for(seeder) if c.name == args.case_name]
    finally:
        await store.close()
    return one_case(named, args.case_name)


async def _seed(args: argparse.Namespace, root: Path) -> int:
    repo_root = recipe_repo_root()
    config = ApiConfig.from_env()
    resources = await build_run_resources(config)
    try:
        # Before the case is made and before a file is written (Amendment 30).
        agree_on_repository(repo_root, resources.recipe_repo_root)
        base = engineer(args.org_unit, args.run_as)
        await _find_case(config.postgres.dsn, args, base)  # refuses two cases of one name
        store = await StudioRecipeStore.connect(config.postgres.dsn)
        try:
            return await _seed_into(args, root, resources, store, repo_root, base)
        finally:
            await store.close()
    finally:
        await resources.close()


async def _require_author_of(case_id: str, persona: Principal) -> None:
    cases = await InvestigationStore.connect(PostgresConfig.from_env().dsn)
    try:
        await require_author(cases, case_id, persona)
    finally:
        await cases.close()


async def _seed_brief_into(case_id: str, author: Principal, audit: AuditWriter) -> BriefSummary:
    """Writes the brief through the case brief service as the case's Author, which `_seed_into` has
    confirmed, and audits the write when it was made (as another case edit is)."""
    store = await CaseBriefStore.connect(PostgresConfig.from_env().dsn)
    try:
        summary = await seed_brief(CaseBriefService(store, {}), case_id, author)
    finally:
        await store.close()
    if summary.written:
        await audit.record(
            principal=author,
            action="case_brief_seed",
            investigation_id=case_id,
            resolved_query={},
            result_cardinality=summary.requirements,
        )
    return summary


async def _seed_into(
    args: argparse.Namespace,
    root: Path,
    resources: Any,
    store: StudioRecipeStore,
    repo_root: Path,
    base: Principal,
) -> int:
    print(run_as_line(base.id, given=args.run_as is not None))
    if resolution_is_on():
        for line in resolution_warning():
            print(line)
    case_id = await scope_for(args, seeder=base, dataset=PID)
    # ADR-128: the brief is written as the case's Author, so an account that is not is refused
    # here, before a file is written, and not after the loads. Amendment 4: that is the account the
    # seed's grants make Author, which on a deployment is not the engineer who runs it.
    author = brief_author(args.grant, base)
    await _require_author_of(case_id, author)
    plan = pid_plan.build_plan("demo")
    print(f"Writing the files into {listed_folder(root)} ...", flush=True)
    rows = await asyncio.to_thread(write_listed_files, plan, root)
    print(f"  {len(rows)} file(s) written; batch 2 is under {INCOMING}/, out of the listing.")
    entered: dict[str, Any] = {}
    stages = [resolve(stage, root) for stage in stages_to_run()]
    peaks: dict[str, float] = {}
    inferred: list[InferredSummary] = []
    deps = without_post_ingest_resolution(resources.run_deps())

    async def scope(principal: Principal) -> Principal:
        return await scope_to_case(principal, case_id, resources.datasets_store)

    async def recipes(principal: Principal) -> None:
        entered.update(
            await enter_recipes(
                root,
                repo_root=repo_root,
                ontology=resources.ontology,
                scheme=resources.handling_scheme,
                commit=commit_recipe_file,
                compare=store.check_seeded_row,
                enter=store.enter_published_for_seed,
                enter_draft=store.enter_draft_for_seed,
                check=check_seeded_recipe,
                now=datetime.now(UTC),
                worker_unit=args.org_unit,
                published_by=base.id,
            )
        )
        print(f"  {len(entered)} recipe(s) in the registry: the reports recipe is the draft.")

    async def standing_of(record: LoadRecord) -> StandingRun | Interrupted | None:
        runs = await resources.recipe_runs.for_recipe(record.recipe_id, limit=500)
        return pick_standing_run(runs, record)

    async def run(principal: Principal) -> list[StageResult]:
        loaded = await loaded_so_far(resources.recipe_runs, case_id, stages)

        async def one(item: Resolved) -> LoadReport | PipelineRunReport:
            if item.stage.file == pid_files.CALLS:
                peaks["before"] = peak_now()
            report = await run_recipe_as(
                deps,
                principal=principal,
                recipe=entered[item.recipe_id],
                investigation_id=case_id,
                source_location=item.source,
                trigger="manual",
            )
            if item.stage.file == pid_files.CALLS:
                peaks["after"] = peak_now()
            return report

        results = await run_stages(stages, loaded, run=one, standing_of=standing_of)

        async def present(source: str, link_type: str, target: str) -> bool:
            star = await resources.graph.expand(
                ExpandRequest(node_ids=[source], depth=1, edge_types=[link_type], direction="out"),
                principal,
            )
            return any(e.source == source and e.target == target for e in star.edges)

        async def write(edges: Sequence[Any]) -> None:
            tx = await resources.graph.begin_transaction()
            try:
                await resources.graph.upsert_edges(list(edges), tx)
            except Exception:
                await resources.graph.rollback_transaction(tx)
                raise
            await resources.graph.commit_transaction(tx)

        async def find(entity_type: str, identifier: str, value: str) -> Any:
            return await resources.graph.find_node(entity_type, identifier, value, principal)

        inferred.append(
            await seed_inferred_links(
                plan, run_as=base.id, find=find, present=present, write=write, now=datetime.now(UTC)
            )
        )
        return results

    async def pictures(principal: Principal) -> PictureSummary:
        working = WorkingSetService(
            resources.graph,
            ValkeyWorkingSetStore(resources.valkey),
            resources.handling_scheme,
            valkey=resources.valkey,
        )
        service = EntityPictureService(
            working,
            resources.graph,
            resources.media,
            resources.ontology,
            scheme=resources.handling_scheme,
            audit=resources.audit,
        )

        async def find(entity_type: str, identifier: str, value: str) -> Any:
            return await resources.graph.find_node(entity_type, identifier, value, principal)

        async def attach(node_id: str, **kwargs: Any) -> bool:
            return await service.attach_for_seed(case_id, node_id, principal, **kwargs)

        return await seed_pictures(plan, find=find, attach=attach)

    async def checks(principal: Principal) -> tuple[pid_plan.Moment, list[CheckResult]]:
        standing = await resources.recipe_runs.unreverted_loads(
            case_id, [incidents_recipe_id(), reports_recipe_id(), comms_recipe_id()]
        )
        moment = moment_of(standing)
        return moment, await run_demo_checks(resources.graph, principal, plan, moment)

    _, results, summary, (moment, numbers) = await seed_all(
        base, scope=scope, enter_recipes=recipes, run=run, pictures=pictures, checks=checks
    )
    brief = await _seed_brief_into(case_id, author, resources.audit)
    draft = await store.get(reports_recipe_id())
    for line in summary_lines(results, run_as=base.id):
        print(line)
    for line in measurement_lines(
        results,
        peak_before_mb=peaks.get("before", 0.0),
        peak_after_mb=peaks.get("after", 0.0),
    ):
        print(line)
    for line in picture_lines(summary, len(plan.picture_subjects)):
        print(line)
    for line in inferred_lines(inferred[0]):
        print(line)
    for line in brief_lines(brief, author.id):
        print(line)
    file_lines, files_ok = check_lines(results, rows)
    for line in file_lines:
        print(line)
    print(f"The demo numbers, at the {moment} moment, as {base.id}:")
    number_lines, demo_ok = demo_check_lines(numbers)
    for line in number_lines:
        print(line)
    print(
        f"The reports recipe is {draft.status.value} at version {draft.version}"
        + (", with no row template (Map is not done)." if draft.row_template is None else ".")
    )
    print(f"Take a backup now, before anything is rehearsed: {BACKUP_COMMAND}")
    print(f"If a rehearsal reset ever refuses, restore it with: {RESTORE_COMMAND}")
    return exit_code(
        files_ok=files_ok,
        pictures_ok=summary.ok and inferred[0].ok,
        demo_ok=demo_ok,
        brief_ok=brief.ok,
    )


async def check_case(
    *,
    graph: _CheckGraph,
    ledger: _Ledger,
    principal: Principal,
    plan: pid_plan.Plan,
    case_id: str,
    say: Callable[[str], None],
    resolution_on: bool = False,
) -> int:
    """Every demo number for the moment the case's stored loads reach (`moment_of`), as `principal`,
    loading nothing. 0 when every number held (one not run is not a failure), 1 when one failed."""
    standing = await ledger.unreverted_loads(
        case_id, [incidents_recipe_id(), reports_recipe_id(), comms_recipe_id()]
    )
    moment = moment_of(standing)
    if resolution_on:
        for line in resolution_warning():
            say(line)
    say(f"The demo numbers, at the {moment} moment, as {principal.id}:")
    lines, ok = demo_check_lines(await run_demo_checks(graph, principal, plan, moment))
    for line in lines:
        say(line)
    return 0 if ok else 1


async def _check(args: argparse.Namespace) -> int:
    """`--check`: reads the graph, the dataset store and the run ledger, and opens nothing else.
    Not `build_run_resources`, which opens DuckDB (one writer), so this runs with the Conduit up."""
    config = ApiConfig.from_env()
    base = engineer(args.org_unit, args.run_as)
    case_id = await _find_case(config.postgres.dsn, args, base)
    if case_id is None:
        raise SeedRefusal("there is no such case to check")
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    datasets = await PostgresDatasetStore.connect(config.postgres.dsn)
    ledger = await RecipeRunStore.connect(config.postgres.dsn)
    try:
        graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
        # The deployment's ontology, as `build_run_resources` gives the seed's graph: without it the
        # adapter cannot read a type or resolve a link's stored name (ADR-127 Amendment 36). Taken
        # in memory only: `apply_schema` runs DDL and a backfill, and `--check` writes nothing.
        graph.use_schema(load_deployment_ontology())
        scoped = await scope_to_case(base, case_id, datasets)
        return await check_case(
            graph=graph,
            ledger=ledger,
            principal=scoped,
            plan=pid_plan.build_plan("demo"),
            case_id=case_id,
            say=print,
            resolution_on=resolution_is_on(),
        )
    finally:
        await ledger.close()
        await datasets.close()
        await client.aclose()


async def _reset(args: argparse.Namespace, root: Path) -> int:
    require_resolution_off()
    config = ApiConfig.from_env()
    base = engineer(args.org_unit, args.run_as)
    case_id = await _find_case(config.postgres.dsn, args, base)
    if case_id is None:
        print("There is no such case, so there is nothing to reset.")
        return 0
    plan = pid_plan.build_plan("demo")
    resources = await build_run_resources(config)
    store = await StudioRecipeStore.connect(config.postgres.dsn)
    history = await InvestigationHistoryStore.connect(config.postgres.dsn)
    try:
        scoped = await scope_to_case(base, case_id, resources.datasets_store)
        graph = GraphArcadeDBAdapter(resources.arcadedb_client, resources.handling_scheme)
        deps = build_revert_deps(
            scheme=resources.handling_scheme,
            graph=graph,
            analytics=resources.analytics,
            ledger=resources.recipe_runs,
            held_rows=resources.held_rows,
            alerts=resources.alerts_store,
            audit=resources.audit,
            history=history,
            valkey=resources.valkey,
        )
        source = source_of(root, pid_files.REPORTS)

        async def draft_is_starting() -> bool:
            try:
                row = await store.get(reports_recipe_id())
            except StudioRecipeNotFoundError:
                return False
            return is_starting_draft(row, source, args.org_unit)

        async def restore_draft() -> None:
            pipeline = starting_pipeline(source)
            try:
                await store.restore_to_draft(
                    reports_recipe_id(),
                    created_by=base.id,
                    owning_unit=args.org_unit,
                    now=datetime.now(UTC),
                    pipeline=pipeline,
                )
            except StudioRecipeNotFoundError:
                await store.enter_draft_for_seed(
                    _recipe(reports_recipe_file()),
                    source_location=source,
                    dataset_id=FOLDER,
                    owning_unit=args.org_unit,
                    created_by=base.id,
                    now=datetime.now(UTC),
                    pipeline=pipeline,
                )

        return await reset_live(
            case_id=case_id,
            root=root,
            ledger=resources.recipe_runs,
            graph=graph,
            worker=scoped,
            revert=revert,
            deps=deps,
            now=datetime.now(UTC),
            restore_draft=restore_draft,
            draft_is_starting=draft_is_starting,
            rewrite_reports=lambda: rewrite_reports_file(plan, root),
            say=print,
            show_ids=args.show_ids,
        )
    finally:
        await history.close()
        await store.close()
        await resources.close()


async def _fallback(args: argparse.Namespace) -> int:
    dsn = PostgresConfig.from_env().dsn
    repo_root = recipe_repo_root()
    store = await StudioRecipeStore.connect(dsn)
    audit = await AuditWriter.connect(dsn)
    try:
        principal = engineer(args.org_unit, args.run_as).model_copy(update={"datasets": [FOLDER]})
        published = await publish_reports_fallback(
            store,
            principal,
            ontology=load_deployment_ontology(),
            scheme=load_uk_le_scheme(),
            repo_root=repo_root,
            commit=commit_recipe_file,
            audit=audit,
            now=datetime.now(UTC),
        )
    finally:
        await audit.close()
        await store.close()
    print(
        f"Published {published.recipe_id} version {published.version} from the committed, fully "
        "mapped file. Run it from the Studio's Publish screen."
    )
    print(FALLBACK_SKIPS)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.ingest_root or ingest_root()
    try:
        if args.mode == "release":
            require_resolution_off()
            print(release_batch_2(root))
            return 0
        if args.mode == "reset":
            return asyncio.run(_reset(args, root))
        if args.mode == "fallback":
            return asyncio.run(_fallback(args))
        if args.mode == "check":
            return asyncio.run(_check(args))
        return asyncio.run(_seed(args, root))
    except REFUSALS as refusal:
        print(f"seed_pid: refused ({type(refusal).__name__}): {refusal}", file=sys.stderr)
        return 1
    except PermissionError as error:
        print(
            f"seed_pid: cannot write {error.filename}: the folder the Conduit's image may write is "
            f"{root / UPLOAD_SUBDIR}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
