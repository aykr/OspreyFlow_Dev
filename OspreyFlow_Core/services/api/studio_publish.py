"""Publish (`spec/09_INGEST_STUDIO.md` §6) — turns a verified
`StudioRecipeDraft` into a `Recipe` YAML file committed to version control,
and runs a published recipe as a real load.

Two things this module deliberately does *not* do: it never re-runs Verify
(`services/api/studio_verify.py`) to decide whether a draft may publish —
`StudioRecipeStore.publish`'s own `verified_at` check is the one gate for
that, so this module can assume it has already passed — and it never
persists a `LoadRecord` anywhere (`services/ingest/load_ledger.py`'s own
docstring: where a load ledger lives durably "is not decided here"). What
this module returns from a run is the `LoadReport` `run_recipe` already
produces, attributed with `load_id`/`recipe_id`/`recipe_version` exactly the
way `StagedRow` already threads those through (`01_DOMAIN_MODEL.md` §2.4) —
enough for `revert_load` (`services/ingest/revert.py`) to act on later, once
a durable ledger exists to hand it one (Phase 8's own territory, per
`revert.py`'s own docstring).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import yaml
from services.ingest.engine import run_recipe
from services.ingest.geometries import POINT_GEOMETRY_VERSION, point_geometries
from services.ingest.recipe_loader import load_recipe

from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from ports.media import MediaStore
from schemas.domain import OntologySchema, Principal
from schemas.ingest import (
    LoadReport,
    Recipe,
    RecipeDefaults,
    ScheduleConfig,
    StudioRecipeDraft,
    StudioRecipeStatus,
)

from .studio_profile import _read_rows as _read_recipe_rows
from .studio_profile import connector_for

__all__ = [
    "GitCommitError",
    "RecipeNotRunnableError",
    "build_recipe",
    "recipe_git_relative_path",
    "run_published_recipe",
    "serialise_recipe",
    "write_and_commit_recipe",
]

#: `git_path` (`spec/09_INGEST_STUDIO.md` §6's example: `recipes/<id>.yaml`)
#: is always relative to the repository root, which is three parents up
#: from this file (`services/api/studio_publish.py` -> `services/api` ->
#: `services` -> repo root) — the same `.parents[2]` computation
#: `services/api/app.py`'s own `_SITE_GRID_RECIPE_PATH` already uses.
_REPO_ROOT = Path(
    os.environ.get("OSPREY_RECIPE_REPO_ROOT") or Path(__file__).resolve().parents[2]
)
"""Where published recipes are committed.

**Round 13bf: the default above is correct on a developer's host and wrong inside a container.**
`.parents[2]` is `/app` there — the image's own code directory, which is rebuilt on every deploy
and is not a git repository. So §6's "the repository is the record" recorded nothing that
survived a `docker compose up --build`, and nobody noticed because the only test of publishing
supplies its own `repo_root` (`tests/ingest/test_studio_publish_pipeline.py`'s `git_repo`
fixture) and so never exercised this default at all.

`OSPREY_RECIPE_REPO_ROOT` is what the renderer sets, to a path under the already-persistent
`osprey-data` volume. The fallback keeps in-process behaviour unchanged.
"""


class GitCommitError(Exception):
    """Raised when `git add`/`git commit` fails for any reason other than
    "nothing to commit" (treated as success below — republishing identical
    content is not an error). Never swallowed into a bare 500: the registry
    row is not flipped to `published` unless the commit that makes "the
    repository is the record" (§6) true actually happened."""


class RecipeNotRunnableError(Exception):
    """Raised by `run_published_recipe` against a recipe whose `status` is
    not `published` — the registry-level, proactive half of blocking a
    stale/unfinished recipe from running (§6: "blocks their scheduled
    runs"). `services/ingest/engine.py`'s `StaleRecipeError` is the
    separate, reactive last-line guard at the engine's own `run_recipe`
    call and is unchanged by this — this exception is what stops a
    `flagged`/`draft`/`superseded` recipe from ever reaching that call in
    the first place, with a clearer message than a version mismatch would
    give."""

    def __init__(self, recipe_id: str, status: StudioRecipeStatus) -> None:
        self.recipe_id = recipe_id
        self.status = status
        super().__init__(
            f"recipe {recipe_id!r} is {status.value!r}, not published — "
            "only a published recipe can be run"
        )


def build_recipe(
    draft: StudioRecipeDraft,
    *,
    ontology_version: int,
    schedule_cron: str | None,
    schedule_watch: str | None,
) -> Recipe:
    """The full, publishable `Recipe` (`spec/09_INGEST_STUDIO.md` §6's own
    YAML shape) a verified draft resolves to. Requires `row_template` —
    the caller (the publish route) only reaches here once
    `StudioRecipeStore.publish` has already confirmed `verified_at` is
    set, which itself implies a row template exists (Verify cannot run
    without one, `services/api/studio_verify.py`'s own
    `RowTemplateMissingError`)."""
    assert draft.row_template is not None
    schedule = (
        ScheduleConfig(cron=schedule_cron, watch=schedule_watch)
        if schedule_cron or schedule_watch
        else None
    )
    return Recipe(
        id=draft.recipe_id,
        version=draft.version,
        label=draft.label,
        # Round 13bf — the profile's own settings reach the published recipe, so a layout's
        # `date_order` survives Publish. See `studio_profile.connector_for`.
        connector=connector_for(draft),
        ontology_version=ontology_version,
        defaults=RecipeDefaults(
            handling=draft.handling, provenance={}, legal_basis=draft.legal_basis
        ),
        row_template=draft.row_template,
        unmapped_fields=draft.unmapped_fields,
        schedule=schedule,
    )


def serialise_recipe(recipe: Recipe) -> str:
    return yaml.safe_dump(
        recipe.model_dump(mode="json", by_alias=True, exclude_none=True),
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )


def recipe_git_relative_path(recipe_id: str) -> str:
    return f"recipes/{recipe_id}.yaml"


async def _run_git(*args: str, cwd: Path) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    return proc.returncode or 0, stdout.decode(errors="replace")


async def _ensure_repository(repo_root: Path) -> None:
    """Make `repo_root` a git repository if it is not one already — round 13bf.

    A rendered deployment's recipe root is an empty directory on a fresh persistent volume, so
    the first publish would otherwise fail `git add` with "not a git repository" and surface as
    the same bare 500 this round came to fix. Initialising on first use keeps the operator's
    install step at "start the deployment", which is what `05_DEPLOYMENT.md` promises.

    The identity is set locally on this repository, never globally: the commits are the
    platform's own record of what was published, not any person's, and `published_by` on the
    registry row is where the accountable human is recorded (§6).
    """
    if (repo_root / ".git").exists():
        return
    repo_root.mkdir(parents=True, exist_ok=True)
    code, output = await _run_git("init", "--initial-branch=main", cwd=repo_root)
    if code != 0:
        raise GitCommitError(f"git init in {str(repo_root)!r} failed: {output}")
    await _run_git("config", "user.email", "osprey@localhost", cwd=repo_root)
    await _run_git("config", "user.name", "OspreyFlow Ingest Studio", cwd=repo_root)


async def write_and_commit_recipe(
    recipe: Recipe, *, repo_root: Path = _REPO_ROOT
) -> str:
    """Writes the recipe to `recipes/<id>.yaml` under `repo_root` and
    commits it — §6: "Publishing writes the recipe to version control, not
    only to the database." Returns the git-relative path stored as the
    registry row's own `git_path`. A commit with nothing changed
    (republishing byte-identical content) is not an error — every other
    non-zero exit is.

    **A stated gap, not a silent one**: this commits to whichever local checkout `repo_root` names —
    correct for the single-instance dev deployment this phase targets, not
    yet correct for a horizontally-scaled one, where a second Conduit
    instance's own checkout would never see this commit. Pushing to a
    shared remote (or routing every instance through one writable
    git-backed service) is real, undesigned work this phase does not do."""
    relative_path = recipe_git_relative_path(recipe.id)
    absolute_path = repo_root / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    absolute_path.write_text(serialise_recipe(recipe))

    await _ensure_repository(repo_root)

    code, output = await _run_git("add", relative_path, cwd=repo_root)
    if code != 0:
        raise GitCommitError(f"git add {relative_path!r} failed: {output}")

    code, output = await _run_git(
        "commit",
        "-m",
        f"ingest: publish {recipe.id} v{recipe.version}",
        "--",
        relative_path,
        cwd=repo_root,
    )
    if code != 0 and "nothing to commit" not in output:
        raise GitCommitError(f"git commit {relative_path!r} failed: {output}")
    return relative_path


async def run_published_recipe(
    draft: StudioRecipeDraft,
    principal: Principal,
    *,
    graph: GraphPort,
    ontology: OntologySchema,
    load_id: str,
    investigation_scope: str,
    source_location: str | None = None,
    repo_root: Path = _REPO_ROOT,
    analytics: AnalyticsPort | None = None,
    media: MediaStore | None = None,
) -> LoadReport:
    """§8: "Loader: run a published recipe against a file at or below their
    own clearance" — "a file", not necessarily the one Connect originally
    pointed at: a Loader's ordinary use of a schedule/watch recipe is
    against whatever the day's fresh export is. `source_location` is that
    override; `None` falls back to the draft's own recorded location, so
    a bare "run it again" (the same file, re-run — §6: "the deduplication
    key makes a re-run idempotent") needs no argument at all. Loads the
    recipe from its committed YAML — the repository is the record (§6) —
    rather than reconstructing it from the registry's own `content`
    column, so a run is provably against exactly what was published, not
    a second in-memory rebuild of it that could drift. Reads the *whole*
    source (`services/api/studio_profile.py`'s `_read_rows` already reads
    the entire file — Verify/Profile are what truncate to a bounded
    sample, at their own call sites, not this function)."""
    if draft.status is not StudioRecipeStatus.PUBLISHED:
        raise RecipeNotRunnableError(draft.recipe_id, draft.status)
    assert draft.git_path is not None
    recipe = load_recipe(repo_root / draft.git_path)

    read_from = draft if source_location is None else draft.model_copy(
        update={"source_location": source_location}
    )
    rows = _read_recipe_rows(read_from)
    tx = await graph.begin_transaction()
    try:
        report, events = await run_recipe(
            recipe,
            rows,
            graph=graph,
            ontology=ontology,
            tx=tx,
            principal=principal,
            load_id=load_id,
            investigation_scope=investigation_scope,
            source=read_from.source_location or draft.recipe_id,
            media=media,
        )
    except Exception:
        await graph.rollback_transaction(tx)
        raise
    await graph.commit_transaction(tx)
    # The run's events (a call's time, a message's text) go to the analytics store, as every seed's
    # do; they were dropped here, so nothing loaded through the Studio reached the timeline,
    # *Show messages* or extraction (found building ADR-094 step 2).
    if analytics is not None and events:
        await analytics.load_events(events)
    # The run's places go on the map the same way: each `Location`'s `geometry_ref` names a point
    # in the geometry partition, and nothing wrote one, so a place loaded here was never drawn
    # (9 October 2026). The partition is keyed by ref and insert-only, so a ref already there is
    # not loaded twice.
    points = point_geometries(recipe, rows)
    if analytics is not None and points:
        held = {
            record.geometry_ref
            for record in await analytics.get_geometries(
                [record.geometry_ref for record in points],
                principal,
                version=POINT_GEOMETRY_VERSION,
            )
        }
        await analytics.load_geometries([p for p in points if p.geometry_ref not in held])
    return report
