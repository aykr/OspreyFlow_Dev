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
enough for the revert (`services/ingest/load_revert.py`) to act on; the run
ledger now keeps each load's record (ADR-127 decision 6).
"""

from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import re
import secrets
import shutil
import stat
import tempfile
import threading
import time
from collections.abc import Collection, Iterator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack, contextmanager, suppress
from pathlib import Path
from typing import Any, Protocol

import yaml
from dulwich.config import ConfigFile, StackedConfig
from dulwich.errors import NotGitRepository, NotTreeError
from dulwich.index import index_entry_from_stat, validate_path
from dulwich.object_store import commit_tree_changes, tree_lookup_path
from dulwich.objects import ZERO_SHA, Blob, Commit, ObjectID, Tree
from dulwich.refs import HEADREF, Ref
from dulwich.repo import Repo
from services.ingest.engine import (
    RowRejected,
    recipe_handlings,
    row_marking,
    run_recipe,
)
from services.ingest.geometries import POINT_GEOMETRY_VERSION, point_geometries
from services.ingest.pipeline import recipe_packs, staging_from_pipeline
from services.ingest.recipe_loader import load_recipe
from services.ingest.recipe_rules import RecipeRuleError, check_reference_matches
from services.ingest.snapshot_withdrawal import DroppedRow, plan_withdrawal
from services.ingest.staged_run import PreparedStaging
from services.ingest.watermark import RefreshRead, WatermarkRead, WatermarkRefused, read_past

from conduit_common.transactions import rollback_keeping_failure
from ontology.handling import HandlingScheme, merge_handling
from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from ports.media import MediaStore
from schemas.analytics import EventRecord
from schemas.domain import (
    EdgeWrite,
    Handling,
    HeldRow,
    NodeWrite,
    OntologySchema,
    Principal,
    TxId,
)
from schemas.ingest import (
    LinkPriorState,
    LoadReport,
    PipelineGraph,
    Recipe,
    RecipeDefaults,
    RejectionRecord,
    RowTemplate,
    ScheduleConfig,
    SourceWatermark,
    StudioRecipeDraft,
    StudioRecipeStatus,
    stored_digest,
)

from .rule_evaluation import (
    PreCommitVerdict,
    RuleGate,
    RuleWrites,
    alert_handling,
    held_rows_for,
)
from .studio_profile import _read_rows as _read_recipe_rows
from .studio_profile import connector_for

__all__ = [
    "GitCommitError",
    "RecipeNotRunnableError",
    "build_recipe",
    "load_published_recipe",
    "load_with_rules",
    "pack_versions_for",
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
_REPO_ROOT = Path(os.environ.get("OSPREY_RECIPE_REPO_ROOT") or Path(__file__).resolve().parents[2])
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
    """Raised when committing a published recipe fails (dulwich since the owner's ruling of
    9 November 2026; the `git` binary before) for any reason other than
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


def pack_versions_for(
    pipeline: PipelineGraph | None, row_template: RowTemplate, ontology: OntologySchema
) -> dict[str, int]:
    """The pins a publish stamps (`06_DECISIONS.md` ADR-120 D10, Amendment 1): each pack the
    pipeline names or whose types the row template writes, at the version the loaded ontology
    carries. `{}` for a recipe that names and writes none. A pack the ontology does not carry is
    refused by name rather than dropped, since the recipe could never run."""
    pins: dict[str, int] = {}
    for pack in recipe_packs(pipeline, row_template, ontology):
        if pack not in ontology.packs:
            raise ValueError(
                f"the recipe needs the pack {pack!r}, which the loaded ontology does not carry"
            )
        pins[pack] = ontology.packs[pack]
    return pins


def check_before_publish(draft: StudioRecipeDraft, ontology: OntologySchema) -> None:
    """What a publish refuses beyond Verify having passed (ADR-127 Amendment 37): a reference on a
    field the store cannot find an entity by. Raises `RecipeRuleError`; writes nothing."""
    assert draft.row_template is not None
    check_reference_matches(draft.row_template, ontology)


def build_recipe(
    draft: StudioRecipeDraft,
    *,
    ontology_version: int,
    pack_versions: dict[str, int] | None,
    schedule_cron: str | None,
    schedule_watch: str | None,
) -> Recipe:
    """The full, publishable `Recipe` (`spec/09_INGEST_STUDIO.md` §6's own
    YAML shape) a verified draft resolves to. Requires `row_template` —
    the caller (the publish route) only reaches here once
    `StudioRecipeStore.publish` has already confirmed `verified_at` is
    set, which itself implies a row template exists (Verify cannot run
    without one, `services/api/studio_verify.py`'s own
    `RowTemplateMissingError`).

    `pack_versions` has no default and may be `None` (ADR-120 Amendment 2, decision 3): a
    re-commit passes the row's pins exactly as stored, none included; a fresh publish always
    passes a map, and the store's `publish` refuses `None`."""
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
        pack_versions=pack_versions,
        defaults=RecipeDefaults.for_source(draft.handling, draft.legal_basis),
        row_template=draft.row_template,
        unmapped_fields=draft.unmapped_fields,
        schedule=schedule,
        # ADR-108 phase C: the published YAML carries the topology the runner executes, so a run
        # is provably against what was published. `None` for a v1 draft — its YAML is unchanged.
        pipeline=draft.pipeline,
        # ADR-140 Amendment 12 (Q1 (a)): the steps are the pipeline's step nodes, in run order,
        # judged by the save gate at the publish route before this is built.
        staging=staging_from_pipeline(draft.pipeline) if draft.pipeline is not None else None,
        # ADR-127 decision 5: what makes a row the same row again, into the committed file, so a
        # run keeps and checks the keys of the rows it loads.
        deduplicate=draft.deduplicate,
    )


def load_published_recipe(row: StudioRecipeDraft, repo_root: Path) -> Recipe:
    """The committed recipe of a published Studio row, with the row's pins when the file has none
    (`06_DECISIONS.md` ADR-120 Amendment 2, decision 1). A file committed before pinning carries no
    `pack_versions`, while the backfill stamps the registry row; a run that read the file alone
    would be refused by the engine for a recipe whose row is pinned. Pins written in the file
    always win. Every load of a published row's file in `services/api` goes through here."""
    assert row.git_path is not None
    recipe = load_recipe(repo_root / row.git_path)
    if recipe.pack_versions is None and row.pack_versions is not None:
        return recipe.model_copy(update={"pack_versions": dict(row.pack_versions)})
    return recipe


def serialise_recipe(recipe: Recipe) -> str:
    return yaml.safe_dump(
        recipe.model_dump(mode="json", by_alias=True, exclude_none=True),
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )


def recipe_git_relative_path(recipe_id: str) -> str:
    return f"recipes/{recipe_id}.yaml"


#: The platform's own identity on every publish commit (§6: `published_by` on the registry row
#: records the accountable human; the commit is the platform's record of what was published).
_COMMIT_IDENTITY = b"OspreyFlow Ingest Studio <osprey@localhost>"

#: A recipe id is one plain file name under `recipes/`: a letter or digit, then letters, digits,
#: `.`, `_` or `-`. So `recipes/<id>.yaml` can name no other directory, no `..` and no `.git`
#: (the independent review of L1.7a, item 1). Every id the Studio mints (a ULID) and every
#: committed recipe's id (`site-grid`, `osm-gazetteer`, the seed's) is of this shape.
_RECIPE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")

#: The file under the repository's git directory that a publish holds an exclusive `flock` on,
#: from writing the recipe file to moving `HEAD`.
PUBLISH_LOCK_NAME = "osprey-publish.lock"

#: How long a publish waits for another to let the repository go before it is refused (a seed
#: process stopped while holding the lock must not hang every publish; the re-review's minor).
PUBLISH_LOCK_WAIT_SECONDS = 30.0

#: The directory a first use makes its git directory in before renaming it into place; one a
#: crashed first use left is swept once it is older than any live first use could be.
_ASIDE_PREFIX = ".git-init-"
_ASIDE = re.compile(re.escape(_ASIDE_PREFIX) + r"[a-z0-9_]{8}")
_ASIDE_STALE_SECONDS = 600.0

#: A temporary file `_write_recipe_file` makes beside a recipe; one a crash left is swept.
_TEMPORARY = re.compile(r"\.[A-Za-z0-9][A-Za-z0-9._-]*\.yaml\.[0-9a-f]{16}\.tmp")

#: One publish at a time in this process, from writing the file to moving `HEAD`, and, with the
#: `flock` on `PUBLISH_LOCK_NAME`, one at a time across processes (the Prison Intelligence seed
#: beside a running Conduit): the index is read, changed and written under both, so neither loses
#: the other's entry, and two publishes never refuse each other or commit each other's bytes. A
#: writer that takes neither, such as an operator's own `git commit` on the volume, is held off at
#: `HEAD` by the compare-and-swap, and at the index only by git's own `index.lock` on each write,
#: so its index change and a publish's can still race; the commit it makes cannot be lost.
_REPOSITORY_LOCK = threading.Lock()

_log = logging.getLogger(__name__)


def _open_repository(repo_root: Path) -> Repo:
    """The repository at `repo_root`, made on first use — round 13bf.

    A rendered deployment's recipe root is an empty directory on a fresh persistent volume, so
    initialising on first use keeps the operator's install step at "start the deployment", which
    is what `05_DEPLOYMENT.md` promises. `HEAD` names `refs/heads/main`, as
    `git init --initial-branch=main` made it before the dulwich swap; a repository the old code
    (or anyone) made is opened as it is, on whichever ref its `HEAD` names.

    The first use cannot race another process's (the re-review, item 3): the git directory is
    made beside the root's own, its `HEAD` already naming `refs/heads/main`, and renamed into
    place in one step. If another process's lands first, the rename fails and that repository is
    opened instead, so neither publish is refused and none lands on a ref `HEAD` then leaves. The
    user's and the system's git config are not read for it (such as the first ref it names).

    The repository's own config is read when it is opened (its format, `core.bare` and
    `core.worktree`); one that is bare or names a worktree other than `repo_root` is refused, so
    the index can describe no tree but the one the file is written to.
    """
    try:
        repo = Repo(str(repo_root))
    except NotGitRepository:
        repo = _initialise(repo_root)
    own = repo_root / ".git"
    try:
        own_is_a_directory = stat.S_ISDIR(os.lstat(own).st_mode)
    except FileNotFoundError:
        own_is_a_directory = False
    if not own_is_a_directory or Path(repo.commondir()).resolve() != own.resolve():
        # A `.git` file naming another repository's directory, a link at `.git`, or a linked
        # worktree's `commondir`: the objects, refs and config written or read would be another
        # repository's. Checked after the open, so a link put there by a first use's rival is
        # seen too.
        repo.close()
        raise GitCommitError("the recipe repository's .git is not a directory of its own")
    if repo.bare or Path(repo.path).resolve() != repo_root.resolve():
        repo.close()
        raise GitCommitError(
            "the recipe repository is bare or its config names another working tree"
        )
    return repo


def _sweep_asides(repo_root: Path) -> None:
    """Remove an aside directory a crashed first use left, once older than any live first use
    could be: only `tempfile.mkdtemp`'s own shape, empty or holding one `.git`, so an operator's
    directory is never touched."""
    for left in repo_root.iterdir():
        if _ASIDE.fullmatch(left.name):
            with suppress(OSError):
                # Only what a first use makes: the aside empty, or holding one `.git` and nothing
                # else (L1.7a's carry). Anything more is not ours, however old.
                ours = sorted(os.listdir(left)) in ([], [".git"])
                if ours and time.time() - left.lstat().st_mtime > _ASIDE_STALE_SECONDS:
                    shutil.rmtree(left)


def _initialise(repo_root: Path) -> Repo:
    repo_root.mkdir(parents=True, exist_ok=True)
    _sweep_asides(repo_root)
    making = Path(tempfile.mkdtemp(prefix=_ASIDE_PREFIX, dir=repo_root))
    try:
        with Repo.init(str(making), config=StackedConfig([ConfigFile()])) as made:
            made.refs.set_symbolic_ref(HEADREF, Ref(b"refs/heads/main"))
        os.rename(making / ".git", repo_root / ".git")
    except OSError:
        if not (repo_root / ".git" / "objects").is_dir():
            raise  # no other process's repository is there: the real failure, kept
    finally:
        shutil.rmtree(making, ignore_errors=True)
    return Repo(str(repo_root))


def _held_off() -> GitCommitError:
    return GitCommitError(
        f"another publish has held the recipe repository for over {PUBLISH_LOCK_WAIT_SECONDS:g} s; "
        "publish again"
    )


@contextmanager
def _publish_lock(repo: Repo, deadline: float) -> Iterator[None]:
    """The exclusive `flock` on `PUBLISH_LOCK_NAME`, its file opened without following a link,
    waited for until `deadline` (the same one the in-process lock was waited for under)."""
    path = os.path.join(repo.controldir(), PUBLISH_LOCK_NAME)
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o666)
    except OSError as exc:
        raise GitCommitError(
            f"the recipe repository's {PUBLISH_LOCK_NAME} is a symbolic link or cannot be opened"
        ) from exc
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise _held_off() from None
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _write_recipe_file(repo_root: Path, relative_path: str, data: bytes) -> os.stat_result:
    """Write `data` to `relative_path` under `repo_root` without following a symbolic link at any
    component below the root (item 1): each directory is opened with `O_NOFOLLOW` relative to the
    one above it, a link where the file goes is refused, and the bytes go to a new file beside it
    that `os.replace` then puts in its place. Returns the written file's own `lstat`."""
    name = relative_path.rsplit("/", 1)[-1]
    fd = _open_recipe_directory(repo_root, relative_path, make=True)
    try:
        try:
            existing = os.lstat(name, dir_fd=fd)
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(existing.st_mode):
                raise GitCommitError(
                    f"{relative_path!r} in the recipe repository is a symbolic link or not a "
                    "file, so it is not written"
                )
        # A temporary file a crash left behind (under the lock, so it is no live publish's).
        for left in os.listdir(fd):
            if _TEMPORARY.fullmatch(left):
                with suppress(FileNotFoundError):
                    os.unlink(left, dir_fd=fd)
        temporary = f".{name}.{secrets.token_hex(8)}.tmp"
        out = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o666, dir_fd=fd
        )
        try:
            with os.fdopen(out, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
        except BaseException:
            with suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=fd)
            raise
        try:
            os.fsync(fd)
            return os.lstat(name, dir_fd=fd)
        except OSError as exc:  # the new bytes are in place: the caller puts them back
            raise _FailedAfterTheWrite from exc
    finally:
        os.close(fd)


class _FailedAfterTheWrite(Exception):
    """`_write_recipe_file` failed after `os.replace` put the new bytes in place; its cause is the
    failure itself."""


def _open_recipe_directory(repo_root: Path, relative_path: str, *, make: bool) -> int:
    """A descriptor on the directory that holds `relative_path`'s file, reached from `repo_root`
    without following a symbolic link at any component below it (each opened with `O_NOFOLLOW`
    relative to the one above), each made first when `make`. The caller closes it."""
    fd = os.open(repo_root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for directory in relative_path.split("/")[:-1]:
            if make:
                with suppress(FileExistsError):
                    os.mkdir(directory, dir_fd=fd)
            try:
                inner = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except OSError as exc:
                raise GitCommitError(
                    f"{directory!r} in the recipe repository is a symbolic link or not a "
                    f"directory, so {relative_path!r} is not written"
                ) from exc
            os.close(fd)
            fd = inner
    except BaseException:
        os.close(fd)
        raise
    return fd


def _commit_file(repo_root: Path, relative_path: str, data: bytes, message: str) -> None:
    """Commit `data` at `relative_path` exactly as `git add <path>` then
    `git commit -m <message> -- <path>` did, with dulwich and without the `git` binary (the
    owner's ruling of 9 November 2026). The commit object is built here rather than through
    dulwich's porcelain on purpose: porcelain reads the repository's config, and its config can
    name a hook, a signer, a file-system monitor, a filter or a credential helper, each an
    executable it would run. No config-driven program runs: the repository's own config is read
    only for its format, `core.bare` and `core.worktree` (`_open_repository`), and the index is
    opened with an empty config, not the user's or the system's.

    Only this one path changes between the parent's tree and the new one, so anything else staged
    in the index stays staged and out of the commit, as `git commit -- <path>` left it. A file
    whose bytes are already the committed ones makes no commit (republishing identical content is
    not an error), but its index entry is still refreshed.

    The file is written, staged and committed under the locks above, from `data` itself, so a
    concurrent publish of the same recipe cannot commit the other's bytes under this one's
    message. The index is written before `HEAD` moves, the order `git add` then `git commit` had:
    a failure after the index leaves the recipe staged and uncommitted, never committed while the
    registry row is left unpublished.
    """
    path = relative_path.encode("utf-8")
    # One limit for both locks, so publishes queued behind a held `flock` are refused within one
    # wait, none holding a worker thread for a wait of its own after another's.
    deadline = time.monotonic() + PUBLISH_LOCK_WAIT_SECONDS
    if not _REPOSITORY_LOCK.acquire(timeout=PUBLISH_LOCK_WAIT_SECONDS):
        raise _held_off()
    try:
        with _open_repository(repo_root) as repo, _publish_lock(repo, deadline):
            _sweep_asides(repo_root)
            # A refused publish leaves nothing ahead of `HEAD`: `load_published_recipe` reads the
            # working tree, so once the new bytes are in place, any failure puts the file and its
            # index entry back as `HEAD` holds them. A refusal before that wrote nothing.
            _refuse_a_head_that_is_no_commit(repo)
            try:
                written = _write_recipe_file(repo_root, relative_path, data)
            except _FailedAfterTheWrite as failed:
                _put_back_as_head_holds(repo, repo_root, relative_path)
                raise (failed.__cause__ or failed) from None
            try:
                _stage_and_commit(repo, path, written, data, message)
            except Exception:
                _put_back_as_head_holds(repo, repo_root, relative_path)
                raise
    finally:
        _REPOSITORY_LOCK.release()


def _refuse_a_head_that_is_no_commit(repo: Repo) -> None:
    """Refused before anything is written: a `HEAD` that names something other than a commit (an
    annotated tag, say). What it holds is unknown, so a write could be neither committed nor put
    back. A `HEAD` with no commit yet is a fresh repository's, and passes."""
    try:
        head_id = repo.refs[HEADREF]
    except KeyError:
        return
    if not isinstance(repo[head_id], Commit):
        raise GitCommitError("the recipe repository's HEAD is not a commit")


def _put_back_as_head_holds(repo: Repo, repo_root: Path, relative_path: str) -> None:
    """After a refused publish, the recipe's file and index entry as the current `HEAD` holds
    them (a rival's commit included), or neither if `HEAD` has no such file. Best effort: a
    failure here is logged and the publish's own error is the one raised."""
    path = relative_path.encode("utf-8")
    try:
        committed: bytes | None = None
        try:
            head_id: ObjectID | None = repo.refs[HEADREF]
        except KeyError:
            head_id = None  # no commit yet: `HEAD` holds no file
        if head_id is not None:
            head = repo[head_id]
            if not isinstance(head, Commit):
                # Not a commit (an annotated tag, say): what `HEAD` holds cannot be read, so the
                # file is left as it is rather than removing a recipe that may be published.
                _log.error("%s left as written: the recipe repository's HEAD is not a commit", path)
                return
            try:
                _, blob_id = tree_lookup_path(repo.object_store.__getitem__, head.tree, path)
            except (KeyError, NotTreeError):  # no such file, or `recipes` is a file in `HEAD`
                blob_id = None
            if blob_id is not None:
                blob = repo[blob_id]
                if not isinstance(blob, Blob):
                    _log.error("%s left as written: HEAD holds no file there", path)
                    return
                committed = blob.as_raw_string()
        index = repo.open_index(config=ConfigFile())
        if committed is None:
            _remove_recipe_file(repo_root, relative_path)
            if path in index:
                del index[path]
        else:
            written = _write_recipe_file(repo_root, relative_path, committed)
            index[path] = index_entry_from_stat(written, Blob.from_string(committed).id)
        index.write()
    except Exception:
        _log.exception("putting %s back as HEAD holds it in %s failed", relative_path, repo_root)


def _remove_recipe_file(repo_root: Path, relative_path: str) -> None:
    """Remove the recipe's file without following a link at any component below the root."""
    fd = _open_recipe_directory(repo_root, relative_path, make=False)
    try:
        with suppress(FileNotFoundError):
            os.unlink(relative_path.rsplit("/", 1)[-1], dir_fd=fd)
    finally:
        os.close(fd)


def _stage_and_commit(
    repo: Repo, path: bytes, written: os.stat_result, data: bytes, message: str
) -> None:
    blob = Blob.from_string(data)
    head: ObjectID | None
    try:
        head = repo.refs[HEADREF]
    except KeyError:
        head = None  # `HEAD` names a ref with no commit yet
    parent: Commit | None = None
    if head is not None:
        found = repo[head]
        if not isinstance(found, Commit):
            raise GitCommitError("the recipe repository's HEAD is not a commit")
        parent = found
    parent_tree = parent.tree if parent is not None else None

    # What `git add` did: the index says the working-tree file is this blob, so `git status`
    # on the volume is clean once the commit lands.
    repo.object_store.add_object(blob)
    index = repo.open_index(config=ConfigFile())  # its settings from no config, not the user's
    index[path] = index_entry_from_stat(written, blob.id)
    index.write()

    unchanged = False
    if parent_tree is not None:
        try:
            _, committed = tree_lookup_path(repo.object_store.__getitem__, parent_tree, path)
            unchanged = committed == blob.id
        except KeyError:
            pass

    if not unchanged:
        base: ObjectID | Tree = parent_tree if parent_tree is not None else Tree()
        commit = Commit()
        commit.tree = commit_tree_changes(repo.object_store, base, [(path, 0o100644, blob.id)])
        commit.parents = [head] if head is not None else []
        commit.author = commit.committer = _COMMIT_IDENTITY
        commit.author_time = commit.commit_time = int(time.time())
        commit.author_timezone = commit.commit_timezone = 0
        commit.message = message.encode("utf-8") + b"\n"  # `git commit -m` ends it so
        repo.object_store.add_object(commit)
        if not repo.refs.set_if_equals(
            HEADREF, head if head is not None else ZERO_SHA, commit.id,
            committer=_COMMIT_IDENTITY, message=b"commit: " + message.encode("utf-8"),
        ):  # fmt: skip
            raise GitCommitError(
                f"the recipe repository's HEAD moved while {path.decode()!r} was being "
                "committed; publish again"
            )


async def write_and_commit_recipe(recipe: Recipe, *, repo_root: Path = _REPO_ROOT) -> str:
    """Writes the recipe to `recipes/<id>.yaml` under `repo_root` and
    commits it — §6: "Publishing writes the recipe to version control, not
    only to the database." Returns the git-relative path stored as the
    registry row's own `git_path`. A commit with nothing changed
    (republishing byte-identical content) is not an error — every other
    failure is.

    **A stated gap, not a silent one**: this commits to whichever local checkout `repo_root` names —
    correct for the single-instance dev deployment this phase targets, not
    yet correct for a horizontally-scaled one, where a second Conduit
    instance's own checkout would never see this commit. Pushing to a
    shared remote (or routing every instance through one writable
    git-backed service) is real, undesigned work this phase does not do."""
    return await commit_recipe_file(
        recipe.id, serialise_recipe(recipe).encode("utf-8"), version=recipe.version,
        repo_root=repo_root,
    )  # fmt: skip


async def commit_recipe_file(
    recipe_id: str, data: bytes, *, version: int, repo_root: Path = _REPO_ROOT
) -> str:
    """The commit half of `write_and_commit_recipe`, for a file that is to be exactly `data`:
    writes it to `recipes/<recipe_id>.yaml` under `repo_root` and commits it as `ingest: publish
    <id> v<version>`, and returns the git-relative path. The Prison Intelligence seed copies each
    committed recipe here byte for byte (ADR-127 Amendment 23), which `serialise_recipe` would not
    keep (it drops comments and reorders). A commit with nothing changed is not an error; every
    other failure raises `GitCommitError`.

    The commit is dulwich's (`_commit_file`), run on a worker thread because dulwich's file I/O is
    synchronous; the repository it writes is an ordinary git repository, which `git log` reads."""
    if _RECIPE_ID.fullmatch(recipe_id) is None:
        raise GitCommitError(
            f"the recipe id {recipe_id!r} is not one file name the recipe repository can hold"
        )
    relative_path = recipe_git_relative_path(recipe_id)
    if not validate_path(relative_path.encode("utf-8")):  # dulwich's own check, as git's fsck
        raise GitCommitError(f"{relative_path!r} is not a path the recipe repository can hold")
    message = f"ingest: publish {recipe_id} v{version}"
    try:
        await asyncio.to_thread(_commit_file, repo_root, relative_path, data, message)
    except GitCommitError:
        raise
    except Exception as exc:  # dulwich's errors share no base; any failure is this typed one
        # The text reaches the client (app.py's handler), so it names the recipe's path and the
        # failure's kind, never the volume's path or the exception's own text; both are logged.
        _log.exception("committing %s in %s failed", relative_path, repo_root)
        raise GitCommitError(f"committing {relative_path!r} failed ({type(exc).__name__})") from exc
    return relative_path


class LoadSink(Protocol):
    """Where a load tells the run ledger what it has done, as it does it (ADR-127 decision 6): the
    record when the graph commits, so a failure in anything after still leaves it, and the geometry
    refs about to be inserted. `services/api/load_records.LedgerSink` writes them to the ledger."""

    async def committed(self, report: LoadReport, *, source: str) -> None: ...

    async def kept(self, recipe_id: str, case: str, keys: Sequence[str]) -> set[str]:
        """Which of these row keys the case already kept for the recipe (ADR-127 decision 5): asked
        only for a recipe with `deduplicate`."""
        ...

    async def fingerprints(self, recipe_id: str, case: str) -> dict[str, int]:
        """The definitions of `deduplicate` the case's kept keys were made under, each with how
        many loads kept keys under it: a run whose own differs is refused."""
        ...

    def hold_row_keys(self, recipe_id: str, case: str) -> AbstractAsyncContextManager[None]:
        """Serialises runs of one recipe into one case (ADR-127 decision 5): held from the check of
        the kept keys to the write of the load's record and keys. A second holder waits a short
        while and is then refused (`RowKeyRunInProgress`)."""
        ...

    async def geometries(self, load_id: str, refs: Sequence[str]) -> None: ...

    async def rule_writes(
        self,
        load_id: str,
        *,
        node_ids: Sequence[str],
        created_edge_ids: Sequence[str],
        merged_edge_ids: Sequence[str],
    ) -> None: ...

    async def uncovered(self, load_id: str) -> None: ...

    # ADR-110 Amendment 8 point 3: asked only by a full snapshot's withdrawal.
    async def dropped_row_keys(
        self, recipe_id: str, case: str, *, present: Collection[str]
    ) -> Sequence[DroppedRow]: ...

    async def withdrawn_event_ids(self, load_id: str) -> list[str]:
        """The events of the rows `load_id` withdrew, by each key's record (Amendment 15)."""
        ...

    async def withdrawn_row_keys_among(
        self, recipe_id: str, case: str, keys: Sequence[str]
    ) -> set[str]:
        """Which of these keys an earlier full snapshot withdrew: rows back (Amendment 15)."""
        ...

    async def withdrawn_row_links(
        self, recipe_id: str, case: str, keys: Sequence[str]
    ) -> dict[str, dict[str, str]]:
        """Of these keys, those withdrawn, each with its recorded links and their types
        (Amendments 16 and 18)."""
        ...

    # ADR-110 Amendment 6 point 1: asked only by an incremental refresh.
    async def watermark(
        self, recipe_id: str, case: str, source_id: str
    ) -> SourceWatermark | None: ...


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
    rules: RuleGate | None = None,
    scheme: HandlingScheme | None = None,
    sink: LoadSink | None = None,
    withdraw_dropped: bool = False,
    refresh: RefreshRead | None = None,
) -> LoadReport:
    """`refresh` (ADR-110 Amendment 6 point 1): how a source refresh reads the file. A full
    snapshot with *withdraw* withdraws its dropped rows (as `withdraw_dropped`); an incremental one
    loads only the rows past the watermark this pipeline last reached for the case
    (`watermark.read_past`), and its record keeps the one it reaches.

    §8: "Loader: run a published recipe against a file at or below their
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
    recipe = load_published_recipe(draft, repo_root)

    read_from = (
        draft
        if source_location is None
        else draft.model_copy(update={"source_location": source_location})
    )
    # The whole file, read and parsed in a worker thread (ADR-127 Amendment 29): held on the event
    # loop it starves the keep-alive of the transaction the run opens next.
    rows = await asyncio.to_thread(lambda: list(_read_recipe_rows(read_from)))
    withdraw_dropped = withdraw_dropped or (refresh is not None and refresh.withdraws)
    past: WatermarkRead | None = None
    row_numbers: list[int] | None = None
    if refresh is not None and refresh.incremental:
        past = await _rows_past_the_watermark(recipe, rows, refresh, sink, investigation_scope)
        rows, row_numbers = past.rows, past.row_numbers
    report, events, held_rows = await load_with_rules(
        recipe,
        rows,
        principal,
        graph=graph,
        ontology=ontology,
        load_id=load_id,
        investigation_scope=investigation_scope,
        source=read_from.source_location or draft.recipe_id,
        media=media,
        rules=rules,
        scheme=scheme,
        sink=sink,
        withdraw_dropped=withdraw_dropped,
        row_numbers=row_numbers,
        past=past,
    )
    if analytics is not None and sink is not None:
        await withdraw_dropped_rows_events(report, sink, analytics)
    await after_the_load(
        recipe,
        rows,
        report,
        events,
        held_rows,
        principal,
        row_numbers=row_numbers,
        load_id=load_id,
        analytics=analytics,
        rules=rules,
        scheme=scheme,
        sink=sink,
    )
    return report


async def after_the_load(
    recipe: Recipe,
    rows: Sequence[Mapping[str, str]],
    report: LoadReport,
    events: list[EventRecord],
    held_rows: frozenset[int],
    principal: Principal,
    *,
    row_numbers: list[int] | None,
    load_id: str,
    analytics: AnalyticsPort | None,
    rules: RuleGate | None,
    scheme: HandlingScheme | None,
    sink: LoadSink | None,
) -> None:
    """What every committed load does next, a plain one's and a staged one's alike (ADR-140
    Amendment 12): its events to the analytics store, its places to the map, and the case's
    post-commit rules."""
    # The run's events (a call's time, a message's text) go to the analytics store, as every seed's
    # do; they were dropped here, so nothing loaded through the Studio reached the timeline,
    # *Show messages* or extraction (found building ADR-094 step 2).
    if analytics is not None and events:
        await analytics.load_events(events)
    # The run's places go on the map the same way: each `Location`'s `geometry_ref` names a point
    # in the geometry partition, and nothing wrote one, so a place loaded here was never drawn
    # (9 October 2026). The partition is keyed by ref and insert-only, so a ref already there is
    # not loaded twice.
    # A held row (ADR-109 ruling 1) reached no store, its place included.
    points = await asyncio.to_thread(
        lambda: point_geometries(
            recipe,
            [
                r
                for n, r in zip(row_numbers or range(len(rows)), rows, strict=True)
                if n not in held_rows
            ],
            scheme=scheme or (rules.scheme if rules is not None else None),
        )
    )
    if analytics is not None and points:
        held = {
            record.geometry_ref
            for record in await analytics.get_geometries(
                [record.geometry_ref for record in points],
                principal,
                version=POINT_GEOMETRY_VERSION,
            )
        }
        fresh = [p for p in points if p.geometry_ref not in held]
        # Recorded before they are inserted (ADR-127 decision 6): a failure between the two leaves
        # refs that are absent, which a revert removes nothing for, never a point nothing records.
        if sink is not None and fresh:
            await sink.geometries(load_id, [p.geometry_ref for p in fresh])
        await analytics.load_geometries(fresh)
    # ADR-109 ruling 1: the case's post-commit rules, once the load's events can be read with it.
    if rules is not None:
        report.rule_notes.extend(await post_commit_notes(rules, events, load_id=load_id, sink=sink))


async def load_with_rules(
    recipe: Recipe,
    rows: list[dict[str, str]],
    principal: Principal,
    *,
    graph: GraphPort,
    ontology: OntologySchema,
    load_id: str,
    investigation_scope: str,
    source: str,
    media: MediaStore | None = None,
    rules: RuleGate | None = None,
    row_numbers: list[int] | None = None,
    scheme: HandlingScheme | None = None,
    sink: LoadSink | None = None,
    withdraw_dropped: bool = False,
    past: WatermarkRead | None = None,
    staged: PreparedStaging | None = None,
) -> tuple[LoadReport, list[EventRecord], frozenset[int]]:
    """One load in one graph transaction, judged by the case's pre-commit rules before it commits
    (`06_DECISIONS.md` ADR-109 ruling 1). A hit loads with its alert: the `Alert` node is written
    into the same transaction, the queue row follows the commit. A rule that fails holds the rows
    it could not judge: the transaction is rolled back, the rows go to the quarantine, and the load
    runs again without them — a second pass whose remaining rows carry no money movement for a
    typology to judge, so it cannot hold again; if it ever did, the load is refused rather than
    part-loaded silently (rule 2).

    `withdraw_dropped` (ADR-110 Amendments 8 point 3 and 15): `rows` are a full snapshot, and the
    rows the case kept for the recipe that it no longer carries are found under the same lock that
    serialises the runs (`snapshot_withdrawal.plan_withdrawal`); their keys move aside with the
    load's record and their own events go after it (`run_published_recipe`). The graph is untouched.
    Only with a sink, which answers the ledger's questions, and a recipe with `deduplicate`: a
    refresh never runs a keyless pipeline (Amendment 6 point 2).

    `staged` (ADR-140 Amendment 12): a staged run prepared up to Map (`staged_run.
    prepare_staged_load`); `rows` are its last table's, each element records the source rows its
    row came from, and the sources' raw rows are written by the engine after its own refusals."""
    if withdraw_dropped and (sink is None or recipe.deduplicate is None):
        raise RecipeRuleError(
            [
                "A full snapshot withdraws its dropped rows by their deduplication key: this "
                "pipeline has none, or the run keeps no ledger."
            ]
        )
    # ADR-127 decision 5: runs of one recipe into one case are serialised from the check of the kept
    # keys (in `run_recipe`) to the write of the load's record and keys (`sink.committed`), so two
    # overlapping runs cannot both find a row's key absent and both load it. Only a recipe with
    # `deduplicate` takes the lock; it is released when the record is written, or on any failure.
    locks = AsyncExitStack()
    try:
        if sink is not None and recipe.deduplicate is not None:
            await locks.enter_async_context(sink.hold_row_keys(recipe.id, investigation_scope))
        # What a column may bind is judged against the caller's scheme, else the case's rules' own.
        scheme = scheme or (rules.scheme if rules is not None else None)
        unseen = (
            alert_handling(rules.scheme, recipe_handlings(recipe, rules.scheme))
            if rules is not None
            else None
        )
        held = PreCommitVerdict()
        skip: frozenset[int] = frozenset()
        while True:
            written: list[NodeWrite | EdgeWrite] = []
            tx = await graph.begin_transaction()
            try:
                # ADR-110 Amendment 16: a returning row's own link, read as stored in this
                # transaction before the load writes, so its revert can put it back.
                own_links = _OwnLinks(sink, graph, tx) if sink is not None else None
                report, events = await run_recipe(
                    recipe,
                    rows,
                    graph=graph,
                    ontology=ontology,
                    tx=tx,
                    principal=principal,
                    load_id=load_id,
                    investigation_scope=investigation_scope,
                    source=source,
                    media=media,
                    skip_row_indices=skip,
                    row_numbers=row_numbers,
                    written=written,
                    scheme=scheme,
                    # The store of loaded rows is the ledger's, reached through the sink (ADR-127
                    # decision 5). A recipe without `deduplicate` is asked too, for the one question
                    # of whether the case holds keys it would reload (it keeps none itself).
                    row_keys=own_links,
                    row_refs=staged.refs if staged is not None else None,
                    stage_raw=staged.stage_raw if staged is not None else True,
                )
                verdict = (
                    await rules.pre_commit(
                        events, tx, load_id=load_id, unseen=unseen, written=written
                    )
                    if rules is not None
                    else PreCommitVerdict()
                )
            except BaseException:
                await rollback_keeping_failure(graph, tx)
                raise
            if not verdict.hold:
                break
            await graph.rollback_transaction(tx)
            if skip:
                raise RuntimeError(
                    "rows were still unjudged after holding the first ones — nothing was loaded"
                )
            held = verdict
            skip = frozenset(verdict.hold)

        # Each held row is marked by its own row's resolved marking (ADR-127 decision 3), never
        # by the recipe's floor, whose units are the first marking's. The markings are settled
        # before the commit: a row none can be made for (`row_marking` refuses it) is a rejection
        # in the report, not a held row lost once the load has committed. It was left out of the
        # graph already (it is among the rows `skip` holds back), so nothing of it is committed.
        held_rows: list[HeldRow] = []
        try:
            if rules is not None and held.hold:
                rule_scheme = rules.scheme
                handlings = recipe_handlings(recipe, rule_scheme)
                floor = handlings[0]
                for other in handlings[1:]:
                    floor = merge_handling(floor, other, rule_scheme)
                by_row: dict[int, Handling] = {}
                numbers = list(row_numbers) if row_numbers is not None else list(range(len(rows)))
                position = {n: i for i, n in enumerate(numbers)}
                refused: list[int] = []
                for number in sorted(held.hold):
                    if number not in position:
                        continue
                    try:
                        by_row[number] = row_marking(recipe, rows[position[number]], rule_scheme)
                    except RowRejected as exc:
                        refused.append(number)
                        report.rejections.append(
                            RejectionRecord(row_index=number, reason=exc.reason, sample="")
                        )
                by_row_object = {id(rows[position[n]]): marking for n, marking in by_row.items()}
                held_rows = held_rows_for(
                    PreCommitVerdict(
                        hold={n: v for n, v in held.hold.items() if n not in refused},
                        findings=held.findings,
                        notes=held.notes,
                    ),
                    rows,
                    row_numbers=row_numbers,
                    investigation_id=rules.investigation_id,
                    recipe_id=recipe.id,
                    recipe_version=recipe.version,
                    load_id=load_id,
                    source=source,
                    handling=floor,
                    dataset_id=principal.datasets[0] if principal.datasets else None,
                    row_handling=lambda row: by_row_object[id(row)],
                )
            if withdraw_dropped:
                assert sink is not None
                await _withdraw_dropped_rows(recipe, rows, report, sink, investigation_scope)
            if own_links is not None:
                merged = _own_key_merges(report, own_links.own, own_links.priors)
                # And each as this load left it, read again in its transaction after its write:
                # the revert goes ahead only while the link still reads back to that.
                report.own_key_merges = [
                    prior.model_copy(
                        update={"left_digest": stored_digest(left.stored) if left else None}
                    )
                    for prior in merged
                    for left in [await graph.read_link_state(prior.edge_id, prior.edge_type, tx)]
                ]
            if past is not None:
                # Before the commit, so the record the commit writes keeps the watermark reached.
                report.watermark = past.reached
                report.rows_below_watermark = past.below
                report.rows_without_watermark = past.without
                report.refresh_notes = [*past.notes, *report.refresh_notes]
        except BaseException:
            # Anything but a refusal (`RowRejected` is handled per row above) leaves the open
            # transaction rolled back, not abandoned: nothing of this load is committed.
            await rollback_keeping_failure(graph, tx)
            raise
        await graph.commit_transaction(tx)
        if rules is not None:
            _fold_rule_writes(report, verdict.writes)
        # The load's record, now: the graph holds it, and everything after (the rules, the events,
        # the points, the resolution jobs, the change stream) can fail without losing what a revert
        # needs.
        if sink is not None:
            await sink.committed(report, source=source)
    finally:
        await locks.aclose()

    if rules is not None:
        await rules.after_commit(verdict)
        if held_rows:
            await rules.hold(held_rows)
        report.rows_held = len(held_rows)
        report.rule_notes = [*held.notes, *verdict.notes]
        rules.last_written = written
        await rules.record_expiries(written)
    return report, events, skip


async def _rows_past_the_watermark(
    recipe: Recipe,
    rows: list[dict[str, str]],
    refresh: RefreshRead,
    sink: LoadSink | None,
    case: str,
) -> WatermarkRead:
    """ADR-110 Amendment 6 point 1: the rows of an incremental refresh past the watermark this
    pipeline last reached for the case, off the event loop. Refused in words, before anything
    loads, without a ledger to ask, for a keyless pipeline (point 2), or for a file the watermark
    cannot judge."""
    if sink is None or recipe.deduplicate is None:
        raise RecipeRuleError(
            [
                "An incremental refresh reads past a watermark and keeps rows by their "
                "deduplication key: this pipeline has none, or the run keeps no ledger."
            ]
        )
    assert refresh.watermark_column is not None
    kept = await sink.watermark(recipe.id, case, refresh.source_id)
    column = refresh.watermark_column
    try:
        return await asyncio.to_thread(
            read_past, rows, source_id=refresh.source_id, column=column, kept=kept
        )
    except WatermarkRefused as refused:
        raise RecipeRuleError([f"The incremental refresh was refused: {refused}."]) from refused


async def withdraw_dropped_rows_events(
    report: LoadReport, sink: LoadSink, analytics: AnalyticsPort
) -> int:
    """ADR-110 Amendment 15: a full snapshot's dropped rows take back their own events and nothing
    else, by the ids each row's key records, after the load's record (which moves the keys aside)
    is in. Returns how many were set aside. A failure here fails the run, in words; the revert puts
    back whatever was set aside."""
    if not report.withdrawn_row_keys:
        return 0
    ids = await sink.withdrawn_event_ids(report.load_id)
    return await analytics.withdraw_events_by_id(ids, report.load_id)


class _OwnLinks:
    """ADR-110 Amendment 16: the sink, as the engine asks it which of the file's keys the case has
    kept. That question comes before the load writes, inside its transaction, with every row's key
    (computed off the event loop, Amendment 29), so it is where a returning row's own link is read
    as stored: of the keys not kept, those an earlier full snapshot of this pipeline in this case
    withdrew, each with the links its record holds. Asked of this pipeline's own keys in this case
    alone (rule 3). Every other question goes to the sink unchanged."""

    def __init__(self, sink: LoadSink, graph: GraphPort, tx: TxId) -> None:
        self._sink, self._graph, self._tx = sink, graph, tx
        self.own: dict[str, dict[str, str]] = {}
        self.priors: dict[str, LinkPriorState] = {}

    async def kept(self, recipe_id: str, case: str, keys: Sequence[str]) -> set[str]:
        kept = set(await self._sink.kept(recipe_id, case, keys))
        # A withdrawn key is not kept (it was moved aside), so only the others can be one.
        back = [key for key in keys if key not in kept]
        self.own = await self._sink.withdrawn_row_links(recipe_id, case, back) if back else {}
        self.priors = {}
        # ADR-110 Amendment 18: each link read by its own recorded type, never by id alone; a key
        # kept before rows recorded their link types holds none, so its link is never captured.
        for edge_id, edge_type in sorted(
            {(e, t) for ls in self.own.values() for e, t in ls.items()}
        ):
            state = await self._graph.read_link_state(edge_id, edge_type, self._tx)
            if state is not None:
                self.priors[edge_id] = state
        return kept

    def __getattr__(self, name: str) -> Any:
        return getattr(self._sink, name)


def _own_key_merges(
    report: LoadReport, own: Mapping[str, Mapping[str, str]], priors: Mapping[str, LinkPriorState]
) -> list[LinkPriorState]:
    """The links this load merged into that a returning row's own withdrawn key recorded, each as
    stored before the merge. Any other merge stays a merge (ADR-127 decision 6): its load is still
    refused a revert."""
    merged = set(report.merged_edge_ids)
    found: dict[str, LinkPriorState] = {}
    for key in report.kept_row_keys:
        links, elements = own.get(key), report.kept_row_elements.get(key)
        if not links or elements is None:
            continue
        for edge_id in elements.edge_ids:
            if edge_id in merged and edge_id in links and edge_id in priors:
                found.setdefault(edge_id, priors[edge_id])
    return list(found.values())


async def _withdraw_dropped_rows(
    recipe: Recipe,
    rows: list[dict[str, str]],
    report: LoadReport,
    sink: LoadSink,
    case: str,
) -> None:
    """ADR-110 Amendment 15: which dropped rows withdraw their events, decided under the lock that
    serialises the runs, and the report told, for the ledger (the keys, which move aside with the
    record after the commit) and the reader (the counts and words). No graph change: the rows'
    nodes and links stay until their load is reverted, so `withdrawn_node_ids` and
    `withdrawn_edge_ids` stay empty. The events go once the record is in
    (`run_published_recipe`)."""
    plan = await plan_withdrawal(recipe, rows, case=case, ledger=sink)
    report.withdrawn_row_keys = plan.row_keys
    report.rows_withdrawn = len(plan.row_keys)
    report.rows_left_in_place = plan.rows_left_in_place
    report.refresh_notes = plan.notes


def _fold_rule_writes(report: LoadReport, writes: RuleWrites) -> None:
    """What the pre-commit rules wrote into the load's transaction (an `Alert`, its links, what the
    finding wrote alongside) belongs to the load (ADR-127 decision 6), so its record has it. It is
    kept in the report's `rule_*` fields, not in `created_node_ids` and `touched_edge_ids`, which
    the change stream and the enrich stage read as what the recipe wrote: monitors must not see an
    alert as a new ingest node. A link a rule merged into one this load created is the load's own,
    not a merge into another load's."""
    report.rule_node_ids.extend(writes.node_ids)
    report.rule_created_edge_ids.extend(writes.created_edge_ids)
    own = {*report.created_edge_ids, *report.rule_created_edge_ids}
    for edge_id in writes.merged_edge_ids:
        if edge_id in own or edge_id in report.rule_merged_edge_ids:
            continue
        report.rule_merged_edge_ids.append(edge_id)


async def post_commit_notes(
    rules: RuleGate,
    events: Sequence[EventRecord],
    *,
    load_id: str,
    sink: LoadSink | None,
) -> list[str]:
    """The case's post-commit rules, and what they wrote told to the load's record (ADR-127
    decision 6): an alert raised after the commit is written in a transaction of its own, so it is
    not in the record the commit made. Best effort as the rules are: whatever was written before a
    rule failed is still recorded."""
    writes = RuleWrites()
    try:
        return await rules.post_commit(
            events, load_id=load_id, written=rules.last_written, writes=writes
        )
    finally:
        if sink is not None and writes:
            await sink.rule_writes(
                load_id,
                node_ids=writes.node_ids,
                created_edge_ids=writes.created_edge_ids,
                merged_edge_ids=writes.merged_edge_ids,
            )
