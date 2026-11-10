"""Publishing commits the recipe with dulwich, never the `git` binary (the owner's ruling of
9 November 2026, MORNING item 89; `09_INGEST_STUDIO.md` §6: the repository is the record).

`git` is GPL-2.0-only and leaves the Conduit's image once nothing there execs it, so the swap has
two invariants, each with the test that would fail if it were violated (rule 12):

* **The repository stays a git repository.** What dulwich writes, the real `git` reads as the
  same history: `test_publish_writes_a_commit_real_git_reads` and
  `test_a_second_publish_keeps_the_first_in_the_history` read it back with the host's `git`
  (a test may run git; the Conduit may not). Shown red with the commit removed
  (`process/lanes/studio-b/l1.7a/`).
* **Nothing on the publish path execs a binary.** `test_publish_never_execs_a_binary` replaces
  every process-spawning entry point with one that fails the test and empties `PATH`, so a `git`
  call anywhere under `commit_recipe_file` — not only in `studio_publish.py` — fails it. Shown red
  with a planted `asyncio.create_subprocess_exec("git", "status")`
  (`process/lanes/studio-b/l1.7a/`).

Offline: no stack, only a temporary directory.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
from dulwich.objects import Blob
from services.api import studio_publish
from services.api.studio_publish import GitCommitError, commit_recipe_file

GIT = shutil.which("git")
#: Skipped only off CI: in CI a missing git fails the test, so the history is always read back.
needs_git = pytest.mark.skipif(
    GIT is None and not os.environ.get("CI"), reason="the host's git reads the history back"
)


def _git(repo: Path, *args: str) -> str:
    assert GIT is not None
    return subprocess.run(
        [GIT, *args], cwd=repo, check=True, capture_output=True, text=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"},
    ).stdout  # fmt: skip


@needs_git
async def test_publish_writes_a_commit_real_git_reads(tmp_path: Path) -> None:
    repo = tmp_path / "recipe-volume"  # does not exist yet, as on a fresh volume
    data = b"id: alpha\nversion: 1\n"

    path = await commit_recipe_file("alpha", data, version=1, repo_root=repo)

    assert path == "recipes/alpha.yaml"
    assert _git(repo, "log", "--format=%s", "--", path).splitlines() == ["ingest: publish alpha v1"]
    assert _git(repo, "show", f"HEAD:{path}").encode() == data
    assert _git(repo, "symbolic-ref", "HEAD").strip() == "refs/heads/main"
    assert _git(repo, "log", "-1", "--format=%an <%ae>").strip() == (
        "OspreyFlow Ingest Studio <osprey@localhost>"
    )
    _git(repo, "fsck", "--strict")
    # The index was updated as `git add` would have: the working tree is clean.
    assert _git(repo, "status", "--porcelain") == ""


@needs_git
async def test_a_second_publish_keeps_the_first_in_the_history(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    first, second = b"id: alpha\nversion: 1\n", b"id: alpha\nversion: 2\n"

    await commit_recipe_file("alpha", first, version=1, repo_root=repo)
    await commit_recipe_file("beta", b"id: beta\n", version=1, repo_root=repo)
    path = await commit_recipe_file("alpha", second, version=2, repo_root=repo)

    assert _git(repo, "log", "--format=%s").splitlines() == [
        "ingest: publish alpha v2", "ingest: publish beta v1", "ingest: publish alpha v1",
    ]  # fmt: skip
    assert _git(repo, "show", f"HEAD:{path}").encode() == second
    assert _git(repo, "show", f"HEAD~2:{path}").encode() == first
    assert _git(repo, "show", "HEAD:recipes/beta.yaml") == "id: beta\n"
    _git(repo, "fsck", "--strict")
    assert _git(repo, "status", "--porcelain") == ""


@needs_git
async def test_republishing_identical_bytes_makes_no_commit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    data = b"id: alpha\nversion: 1\n"
    await commit_recipe_file("alpha", data, version=1, repo_root=repo)
    await commit_recipe_file("alpha", data, version=1, repo_root=repo)

    assert _git(repo, "rev-list", "--count", "HEAD").strip() == "1"


@needs_git
async def test_publish_commits_on_top_of_a_repository_real_git_made(tmp_path: Path) -> None:
    """A deployment whose recipe volume was initialised by the old `git` code keeps its history,
    and a file staged by someone else is not swept into the publish commit (`git commit -- path`
    committed only the recipe; so does this)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=trunk")
    (repo / "README").write_text("before\n")
    _git(repo, "add", "README")
    _git(repo, "-c", "user.name=Old", "-c", "user.email=old@localhost", "commit", "-m", "old")
    (repo / "other").write_text("staged, not ours\n")
    _git(repo, "add", "other")

    await commit_recipe_file("alpha", b"id: alpha\n", version=1, repo_root=repo)

    assert _git(repo, "log", "--format=%s", "trunk").splitlines() == [
        "ingest: publish alpha v1", "old",
    ]  # fmt: skip
    assert _git(repo, "ls-tree", "-r", "--name-only", "HEAD").split() == [
        "README", "recipes/alpha.yaml",
    ]  # fmt: skip
    # `other` is still staged, and only it.
    assert _git(repo, "status", "--porcelain").splitlines() == ["A  other"]
    _git(repo, "fsck", "--strict")


def _plant_every_config_driven_command(repo: Path, trap: Path) -> None:
    """Everything in a repository's config or tree that makes a real `git commit` run a program:
    a signer, a hooks directory and the hooks in it, a file-system monitor, a clean filter and a
    credential helper. Each names `trap`, which leaves a file behind if anything runs it."""
    trap.write_text(f"#!/bin/sh\necho ran >> {trap}.ran\nexit 1\n")
    trap.chmod(0o755)
    hooks = trap.parent / "hooks-path"
    for hooks_dir in (repo / ".git" / "hooks", hooks):
        hooks_dir.mkdir(parents=True, exist_ok=True)
        for hook in ("pre-commit", "prepare-commit-msg", "commit-msg", "post-commit",
                     "reference-transaction", "post-index-change"):  # fmt: skip
            (hooks_dir / hook).write_text(trap.read_text())
            (hooks_dir / hook).chmod(0o755)
    with (repo / ".git" / "config").open("a") as config:
        config.write(
            f"[commit]\n\tgpgsign = true\n[gpg]\n\tprogram = {trap}\n"
            f"[core]\n\thooksPath = {hooks}\n\tfsmonitor = {trap}\n"
            f'[filter "trap"]\n\tclean = {trap}\n\tsmudge = {trap}\n\tprocess = {trap}\n'
            f"\trequired = true\n[credential]\n\thelper = {trap}\n"
        )
    (repo / ".gitattributes").write_text("* filter=trap\n")


async def test_publish_never_execs_a_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No config-driven program runs (the independent review of L1.7a, item 2): with every one a
    real `git commit` honours planted, neither publish spawns anything.

    Three of the plants are shown to fire this trap when dulwich's own config-reading code is put
    in the commit's place (`l1.7a/red_plants.py`): the hooks in `.git/hooks` (its worktree
    commit), the signer `gpg.program` (the same commit with hooks skipped) and the clean filter
    (its worktree stage). The rest, `core.hooksPath`, the `reference-transaction` and
    `post-index-change` hooks, `core.fsmonitor` and the credential helper, are inert in dulwich
    1.2.21: it has no code that runs them. They stay planted because a real `git commit` honours
    them, so a later dulwich that does is caught here too."""
    spawned: list[str] = []

    def refuse(*args: object, **kwargs: object) -> None:
        spawned.append(repr(args[0]) if args else "?")
        raise AssertionError(f"the publish path spawned a process: {spawned[-1]}")

    def refuse_popen(self: object, args: object, *rest: object, **kwargs: object) -> None:
        refuse(args)

    async def refuse_async(*args: object, **kwargs: object) -> None:
        refuse(*args)

    # PATH holds one program, a trap named `gpg`: dulwich's signer is offered only where it finds
    # a `gpg`, so this makes the planted `gpg.program` reachable rather than inert by omission.
    path_dir = tmp_path / "path-with-only-a-gpg"
    path_dir.mkdir()
    (path_dir / "gpg").write_text(f"#!/bin/sh\necho ran >> {path_dir}/gpg.ran\nexit 1\n")
    (path_dir / "gpg").chmod(0o755)
    monkeypatch.setenv("PATH", str(path_dir))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", refuse_async)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", refuse_async)
    monkeypatch.setattr(subprocess.Popen, "__init__", refuse_popen)
    for name in ("system", "posix_spawn", "posix_spawnp", "execv", "execve", "execvp", "fork"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, refuse)

    repo = tmp_path / "repo"
    trap = tmp_path / "trap.sh"
    second = b"id: alpha\nversion: 2\n"
    try:
        await commit_recipe_file("alpha", b"id: alpha\n", version=1, repo_root=repo)
        _plant_every_config_driven_command(repo, trap)
        await commit_recipe_file("alpha", second, version=2, repo_root=repo)
    finally:
        # Asked even when a publish raised, so a spawn is what the failure says, not the
        # GitCommitError a refused spawn turns into.
        assert spawned == [], f"the publish spawned: {spawned}"
    assert not Path(f"{trap}.ran").exists()
    assert not (path_dir / "gpg.ran").exists()
    # The second commit holds the bytes given, unfiltered and unsigned.
    from dulwich.object_store import tree_lookup_path
    from dulwich.objects import Commit
    from dulwich.repo import Repo

    with Repo(str(repo)) as opened:
        head = opened[opened.head()]
        assert isinstance(head, Commit)
        assert head.gpgsig is None
        _, committed = tree_lookup_path(opened.__getitem__, head.tree, b"recipes/alpha.yaml")
        assert committed == Blob.from_string(second).id


@needs_git
async def test_concurrent_publishes_each_commit_their_own_bytes(tmp_path: Path) -> None:
    """The lock's invariant (rule 12): eight publishes of one recipe at once all succeed, never
    refusing each other or failing on each other's files, with one commit each holding its own
    version's bytes."""
    repo = tmp_path / "repo"
    versions = range(1, 9)
    await asyncio.gather(
        *(
            commit_recipe_file("alpha", f"version: {v}\n".encode(), version=v, repo_root=repo)
            for v in versions
        )
    )
    log = _git(repo, "log", "--format=%H %s").splitlines()
    assert len(log) == len(versions)
    for line in log:
        sha, subject = line.split(" ", 1)
        version = subject.rsplit(" v", 1)[1]
        assert _git(repo, "show", f"{sha}:recipes/alpha.yaml") == f"version: {version}\n"
    _git(repo, "fsck", "--strict")


@needs_git
async def test_a_failure_after_staging_leaves_nothing_committed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The index is written before `HEAD` moves, as `git add` preceded `git commit`: a failure
    writing the index raises, and the repository holds no commit the registry row does not name."""
    from dulwich.index import Index

    repo = tmp_path / "repo"
    await commit_recipe_file("alpha", b"version: 1\n", version=1, repo_root=repo)
    before = _git(repo, "rev-parse", "HEAD")

    def locked(self: Index, *args: object, **kwargs: object) -> None:
        raise OSError("index.lock is held")

    monkeypatch.setattr(Index, "write", locked)
    with pytest.raises(GitCommitError):
        await commit_recipe_file("alpha", b"version: 2\n", version=2, repo_root=repo)
    assert _git(repo, "rev-parse", "HEAD") == before


@needs_git
async def test_a_recipe_root_inside_another_repository_gets_its_own(tmp_path: Path) -> None:
    """The developer-host fallback root sits inside the monorepo's checkout. As the old
    `.git`-exists check did, the publish makes a repository at the root itself and never
    commits to the enclosing one."""
    outer = tmp_path / "outer"
    outer.mkdir()
    _git(outer, "init", "--initial-branch=trunk")
    root = outer / "inner"

    await commit_recipe_file("alpha", b"id: alpha\n", version=1, repo_root=root)

    assert (root / ".git").is_dir()
    assert _git(root, "log", "--format=%s").splitlines() == ["ingest: publish alpha v1"]
    assert _git(outer, "rev-list", "--all").strip() == ""


@needs_git
async def test_a_detached_head_moves_as_git_commit_moved_it(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    await commit_recipe_file("alpha", b"version: 1\n", version=1, repo_root=repo)
    first = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "--detach", "-q")

    await commit_recipe_file("alpha", b"version: 2\n", version=2, repo_root=repo)

    assert _git(repo, "rev-parse", "HEAD~1").strip() == first
    assert _git(repo, "rev-parse", "refs/heads/main").strip() == first
    assert _git(repo, "show", "HEAD:recipes/alpha.yaml") == "version: 2\n"


def test_the_module_names_no_process_api() -> None:
    """The static half: the git binary is not named, nor any way to spawn one, in the module
    that publishes. Read as text, so a call on a branch no test reaches is still caught."""
    source = Path(studio_publish.__file__).read_text(encoding="utf-8")
    for spawn in ("subprocess", "create_subprocess", "os.system", "posix_spawn", "os.exec"):
        assert spawn not in source, spawn


async def test_a_failed_write_is_a_typed_error_not_a_bare_500(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GitCommitError is what the Conduit maps to its typed response (app.py's handler); a
    dulwich or filesystem failure must surface as it, never as a bare exception, and its text
    (which names the volume's path here) must not reach the client."""
    repo = tmp_path / "repo"
    await commit_recipe_file("alpha", b"id: alpha\n", version=1, repo_root=repo)

    def broken(*args: object, **kwargs: object) -> object:
        raise OSError(f"[Errno 5] Input/output error: '{repo / '.git' / 'objects'}'")

    monkeypatch.setattr(studio_publish, "commit_tree_changes", broken)
    with pytest.raises(GitCommitError) as raised:
        await commit_recipe_file("alpha", b"id: alpha\nversion: 2\n", version=2, repo_root=repo)
    # The text is the client's (app.py's handler returns it): no volume path in it.
    assert str(tmp_path) not in str(raised.value)
    assert "recipes/alpha.yaml" in str(raised.value)
    assert isinstance(raised.value.__cause__, OSError)


def test_dulwich_is_admitted_by_the_licence_gate_through_its_apache_alternative() -> None:
    """Dulwich declares `Apache-2.0 OR GPL-2.0-or-later` and is taken under Apache-2.0 (the owner's
    ruling). Checked on the row pip-licenses really reports for the installed package — the shape
    `tools/licence_check.find_offenders` receives — and shown to pass for that reason only: the
    same row with its Apache-2.0 alternative removed is an offender (rule 15)."""
    from tools.licence_check import find_offenders, run_pip_licenses

    rows = [row for row in run_pip_licenses(None) if row["Name"].lower() == "dulwich"]
    assert len(rows) == 1, "dulwich is not installed, so Publish cannot commit"
    row = rows[0]
    assert "Apache-2.0" in row["License"]
    assert find_offenders([row]) == []
    gpl_only = {**row, "License": row["License"].replace("Apache-2.0 OR ", "")}
    assert gpl_only["License"] != row["License"]
    assert find_offenders([gpl_only]) == [gpl_only]


@needs_git
@pytest.mark.parametrize(
    "recipe_id", ["../x", ".git/x", "../../outside", "a/b", "..", ".hidden", ""]
)
async def test_a_recipe_id_that_is_not_one_file_name_is_refused(
    tmp_path: Path, recipe_id: str
) -> None:
    """A recipe id cannot escape `recipes/` (the independent review of L1.7a, item 1): an id that
    is not one plain file name is refused before anything is written, the repository holds no
    `..` or `.git` tree entry, and real git's strictest check stays clean."""
    repo = tmp_path / "repo"
    await commit_recipe_file("alpha", b"id: alpha\n", version=1, repo_root=repo)
    before = _git(repo, "rev-parse", "HEAD")

    with pytest.raises(GitCommitError):
        await commit_recipe_file(recipe_id, b"id: x\n", version=1, repo_root=repo)

    assert _git(repo, "rev-parse", "HEAD") == before
    _git(repo, "fsck", "--strict")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["repo"]
    assert _git(repo, "ls-files").split() == ["recipes/alpha.yaml"]
    assert sorted(p.name for p in (repo / "recipes").iterdir()) == ["alpha.yaml"]


@needs_git
async def test_a_symlinked_recipes_directory_is_refused(tmp_path: Path) -> None:
    """`recipes/` pointing elsewhere is refused, not written through (item 1)."""
    repo = tmp_path / "repo"
    await commit_recipe_file("alpha", b"id: alpha\n", version=1, repo_root=repo)
    before = _git(repo, "rev-parse", "HEAD")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    shutil.rmtree(repo / "recipes")
    (repo / "recipes").symlink_to(elsewhere, target_is_directory=True)

    with pytest.raises(GitCommitError) as raised:
        await commit_recipe_file("beta", b"id: beta\n", version=1, repo_root=repo)

    assert list(elsewhere.iterdir()) == []
    assert _git(repo, "rev-parse", "HEAD") == before
    assert str(tmp_path) not in str(raised.value)
    _git(repo, "fsck", "--strict")


@needs_git
async def test_a_symlinked_recipe_file_is_refused(tmp_path: Path) -> None:
    """`recipes/<id>.yaml` pointing at another file is refused, and that file is untouched
    (item 1)."""
    repo = tmp_path / "repo"
    await commit_recipe_file("alpha", b"id: alpha\n", version=1, repo_root=repo)
    before = _git(repo, "rev-parse", "HEAD")
    victim = tmp_path / "victim"
    victim.write_bytes(b"not the recipe's\n")
    (repo / "recipes" / "alpha.yaml").unlink()
    (repo / "recipes" / "alpha.yaml").symlink_to(victim)

    with pytest.raises(GitCommitError):
        await commit_recipe_file("alpha", b"id: alpha\nversion: 2\n", version=2, repo_root=repo)

    assert victim.read_bytes() == b"not the recipe's\n"
    assert (repo / "recipes" / "alpha.yaml").is_symlink()
    assert _git(repo, "rev-parse", "HEAD") == before
    _git(repo, "fsck", "--strict")


@needs_git
async def test_a_real_writer_moving_head_mid_commit_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The compare-and-swap against a real second writer (item 3; rule 15, not a fake refusal):
    real git commits between the publish reading `HEAD` and moving it. The publish raises, the
    other writer's commit is still `HEAD` with ours not on top of it, and fsck stays clean."""
    repo = tmp_path / "repo"
    await commit_recipe_file("alpha", b"version: 1\n", version=1, repo_root=repo)
    first = _git(repo, "rev-parse", "HEAD").strip()
    real = studio_publish.commit_tree_changes

    def with_a_rival(*args: object, **kwargs: object) -> object:
        (repo / "theirs").write_text("theirs\n")
        _git(repo, "add", "theirs")
        _git(repo, "-c", "user.name=Op", "-c", "user.email=op@localhost",
             "commit", "-q", "-m", "theirs", "--", "theirs")  # fmt: skip
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(studio_publish, "commit_tree_changes", with_a_rival)
    with pytest.raises(GitCommitError) as raised:
        await commit_recipe_file("alpha", b"version: 2\n", version=2, repo_root=repo)

    assert "moved" in str(raised.value)
    assert _git(repo, "log", "--format=%s").splitlines() == ["theirs", "ingest: publish alpha v1"]
    assert _git(repo, "rev-parse", "HEAD~1").strip() == first
    assert _git(repo, "show", "HEAD:recipes/alpha.yaml") == "version: 1\n"
    _git(repo, "fsck", "--strict")


async def test_the_index_is_read_and_written_under_a_lock_another_process_honours(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item 7, and the re-review's item 3: the file's write, the index's read-modify-write and the
    commit (and the index's read and the swap on `HEAD`) all hold an exclusive `flock` on the
    repository's publish lock, so the Prison
    Intelligence seed beside a running Conduit cannot lose the other's index entry. Probed from a
    second open of the lock file, as another process would take it, at each of the three."""
    import fcntl

    from dulwich.index import Index
    from dulwich.refs import DiskRefsContainer
    from dulwich.repo import Repo

    repo = tmp_path / "repo"
    await commit_recipe_file("alpha", b"version: 1\n", version=1, repo_root=repo)
    lock = repo / ".git" / studio_publish.PUBLISH_LOCK_NAME
    held: dict[str, bool] = {}

    def probe(where: str) -> None:
        with lock.open("a") as other:
            try:
                fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                held[where] = True
            else:
                fcntl.flock(other, fcntl.LOCK_UN)
                held[where] = False

    def wrap(where: str, real: Any) -> Any:
        def probed(*args: object, **kwargs: object) -> object:
            probe(where)
            return real(*args, **kwargs)

        return probed

    monkeypatch.setattr(
        studio_publish, "_write_recipe_file", wrap("write", studio_publish._write_recipe_file)
    )
    monkeypatch.setattr(Index, "write", wrap("index", Index.write))
    monkeypatch.setattr(
        studio_publish, "commit_tree_changes", wrap("commit", studio_publish.commit_tree_changes)
    )
    monkeypatch.setattr(Repo, "open_index", wrap("index read", Repo.open_index))
    monkeypatch.setattr(
        DiskRefsContainer, "set_if_equals", wrap("swap", DiskRefsContainer.set_if_equals)
    )
    await commit_recipe_file("alpha", b"version: 2\n", version=2, repo_root=repo)
    assert held == {
        "write": True, "index read": True, "index": True, "commit": True, "swap": True,
    }  # fmt: skip


@needs_git
async def test_a_linked_publish_lock_is_refused(tmp_path: Path) -> None:
    """The lock file is opened without following a link, so a link planted in its place cannot
    have a publish create or open a file elsewhere."""
    repo = tmp_path / "repo"
    await commit_recipe_file("alpha", b"version: 1\n", version=1, repo_root=repo)
    before = _git(repo, "rev-parse", "HEAD")
    lock = repo / ".git" / studio_publish.PUBLISH_LOCK_NAME
    lock.unlink()
    elsewhere = tmp_path / "elsewhere.lock"
    lock.symlink_to(elsewhere)

    with pytest.raises(GitCommitError):
        await commit_recipe_file("alpha", b"version: 2\n", version=2, repo_root=repo)

    assert not elsewhere.exists()
    assert _git(repo, "rev-parse", "HEAD") == before


@needs_git
async def test_a_rival_making_the_repository_first_is_joined_not_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First use on a fresh volume, with another process making the repository at the same moment
    (the lane review's item 3): the publish's own git directory is made aside, so the rival's
    lands first and the publish commits on top of it. Nothing is refused, no ref is left behind
    and the aside directory is gone. The rival is the real `git`, run once in the window between
    the aside directory being made and its rename; it is not a second dulwich publish."""
    from dulwich.repo import Repo

    root = tmp_path / "fresh"
    real = Repo.init
    made_aside: list[bool] = []

    def rival_first(path: str, **kwargs: Any) -> Repo:
        made = real(path, **kwargs)
        made_aside.append(not (root / ".git").exists())
        _git(root, "init", "-q", "--initial-branch=main")
        (root / "theirs").write_text("theirs\n")
        _git(root, "add", "theirs")
        _git(root, "-c", "user.name=Op", "-c", "user.email=op@localhost",
             "commit", "-q", "-m", "theirs")  # fmt: skip
        return made

    monkeypatch.setattr(Repo, "init", staticmethod(rival_first))
    await commit_recipe_file("alpha", b"id: alpha\n", version=1, repo_root=root)

    assert _git(root, "log", "--format=%s").splitlines() == ["ingest: publish alpha v1", "theirs"]
    assert _git(root, "for-each-ref", "--format=%(refname)").split() == ["refs/heads/main"]
    assert sorted(p.name for p in root.iterdir()) == [".git", "recipes", "theirs"]
    _git(root, "fsck", "--strict")
    assert made_aside == [True]  # last, so a collision fails on what it does, not on this flag


@needs_git
async def test_a_fresh_repository_is_on_main_whatever_the_user_s_config_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Neither the user's nor the system's git config is read, at first use (the first ref a
    user's config names) or when the index is opened: dulwich's only way to them is refused."""
    from dulwich.config import StackedConfig

    read: list[str] = []

    def never(*args: object, **kwargs: object) -> object:
        read.append("config")
        raise AssertionError("the publish read the user's or the system's git config")

    monkeypatch.setattr(StackedConfig, "default", classmethod(never))
    monkeypatch.setattr(StackedConfig, "default_backends", classmethod(never))
    repo = tmp_path / "repo"
    try:
        await commit_recipe_file("alpha", b"version: 1\n", version=1, repo_root=repo)
        await commit_recipe_file("alpha", b"version: 2\n", version=2, repo_root=repo)
    finally:
        # Asked even when a publish raised, so the failure names the read, not the wrapped error.
        assert read == [], "the publish read the user's or the system's git config"

    assert _git(repo, "symbolic-ref", "HEAD").strip() == "refs/heads/main"
    assert _git(repo, "log", "--format=%s").splitlines() == [
        "ingest: publish alpha v2", "ingest: publish alpha v1",
    ]  # fmt: skip


@needs_git
async def test_a_repository_whose_config_names_another_tree_is_refused(tmp_path: Path) -> None:
    """The repository's own config is read for `core.worktree`: one naming another tree is refused
    before anything is written, so the index can describe no tree but the one the recipe is
    written to. (`core.bare` in a `.git` directory's config is ignored by dulwich, and a bare
    repository has no index for git to read, so it is not asked here.)"""
    repo = tmp_path / "repo"
    await commit_recipe_file("alpha", b"version: 1\n", version=1, repo_root=repo)
    before = _git(repo, "rev-parse", "HEAD")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    with (repo / ".git" / "config").open("a") as config:
        config.write(f"[core]\n\tworktree = {elsewhere}\n")

    with pytest.raises(GitCommitError):
        await commit_recipe_file("alpha", b"version: 2\n", version=2, repo_root=repo)

    assert list(elsewhere.iterdir()) == []
    assert (repo / "recipes" / "alpha.yaml").read_bytes() == b"version: 1\n"
    assert _git(repo, "--git-dir", str(repo / ".git"), "rev-parse", "HEAD") == before


@needs_git
@pytest.mark.parametrize("recipe_id", ["01JC5Q8K3ZP6V2T9XR4W7HMNBD", "a_b.c-1", "9"])
async def test_an_id_of_the_shapes_the_studio_mints_is_accepted(
    tmp_path: Path, recipe_id: str
) -> None:
    """The id check refuses nothing real: a ULID (`new_id`), and dots, underscores and a leading
    digit (the lane review's minor)."""
    repo = tmp_path / "repo"
    path = await commit_recipe_file(recipe_id, b"id: x\n", version=1, repo_root=repo)
    assert path == f"recipes/{recipe_id}.yaml"
    assert _git(repo, "ls-files").split() == [path]


async def test_a_publish_held_off_too_long_is_refused_not_hung(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A process stopped while holding the publish lock does not hang every publish (the lane
    review's minor): after the wait, the publish is refused and nothing is written."""
    import fcntl
    import threading

    repo = tmp_path / "repo"
    await commit_recipe_file("alpha", b"version: 1\n", version=1, repo_root=repo)
    monkeypatch.setattr(studio_publish, "PUBLISH_LOCK_WAIT_SECONDS", 0.2)
    other = (repo / ".git" / studio_publish.PUBLISH_LOCK_NAME).open("a")
    fcntl.flock(other, fcntl.LOCK_EX)
    # Let go after 3 s, so a wait without limit ends (and fails this test) rather than hangs.
    release = threading.Timer(3.0, lambda: (fcntl.flock(other, fcntl.LOCK_UN), other.close()))
    release.start()
    try:
        with pytest.raises(GitCommitError) as raised:
            await commit_recipe_file("alpha", b"version: 2\n", version=2, repo_root=repo)
    finally:
        release.join()
    assert "another publish" in str(raised.value)
    assert (repo / "recipes" / "alpha.yaml").read_bytes() == b"version: 1\n"


@needs_git
async def test_a_temporary_file_a_crash_left_is_swept(tmp_path: Path) -> None:
    """A publish killed between writing its temporary file and renaming it leaves that file; the
    next publish sweeps it under the lock, so `git status` is clean and `git add -A` cannot
    commit it (the lane review's minor)."""
    repo = tmp_path / "repo"
    await commit_recipe_file("alpha", b"version: 1\n", version=1, repo_root=repo)
    left = repo / "recipes" / ".beta.yaml.0123456789abcdef.tmp"
    left.write_bytes(b"half a recipe")
    kept = repo / "recipes" / ".not-ours.tmp"
    kept.write_bytes(b"someone else's")

    await commit_recipe_file("alpha", b"version: 2\n", version=2, repo_root=repo)

    assert not left.exists()
    assert kept.exists()  # only the shape the publish itself makes is swept


@needs_git
@pytest.mark.parametrize("how", ["gitfile", "link"])
async def test_a_git_directory_that_is_not_the_root_s_own_is_refused(
    tmp_path: Path, how: str
) -> None:
    """A `.git` file naming another repository's directory, or a link at `.git`, is refused (the
    lane review's round 3, item 2): the index, the objects, the lock and `HEAD` written would be
    another repository's. That repository is left as it was."""
    other = tmp_path / "other"
    await commit_recipe_file("alpha", b"other's\n", version=1, repo_root=other)
    before = _git(other, "rev-parse", "HEAD")
    root = tmp_path / "root"
    root.mkdir()
    if how == "gitfile":
        (root / ".git").write_text(f"gitdir: {other / '.git'}\n")
    else:
        (root / ".git").symlink_to(other / ".git", target_is_directory=True)

    with pytest.raises(GitCommitError):
        await commit_recipe_file("alpha", b"ours\n", version=2, repo_root=root)

    assert _git(other, "rev-parse", "HEAD") == before
    assert _git(other, "status", "--porcelain") == ""
    assert not (root / "recipes").exists()


async def test_publishes_queued_behind_a_held_lock_share_one_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wait has one limit for both locks (the lane review's round 3, item 3): with the
    `flock` held elsewhere, two publishes queued in this process are both refused within about
    one wait, not one after the other, so queued publishes cannot each hold a worker thread for
    a further wait."""
    import fcntl
    import threading

    wait = 1.0
    repo = tmp_path / "repo"
    await commit_recipe_file("alpha", b"version: 1\n", version=1, repo_root=repo)
    monkeypatch.setattr(studio_publish, "PUBLISH_LOCK_WAIT_SECONDS", wait)
    other = (repo / ".git" / studio_publish.PUBLISH_LOCK_NAME).open("a")
    fcntl.flock(other, fcntl.LOCK_EX)
    release = threading.Timer(6.0, lambda: (fcntl.flock(other, fcntl.LOCK_UN), other.close()))
    release.start()
    try:
        started = time.monotonic()
        outcomes = await asyncio.gather(
            commit_recipe_file("alpha", b"version: 2\n", version=2, repo_root=repo),
            commit_recipe_file("alpha", b"version: 3\n", version=3, repo_root=repo),
            return_exceptions=True,
        )
        elapsed = time.monotonic() - started
    finally:
        release.join()
    assert all(isinstance(outcome, GitCommitError) for outcome in outcomes), outcomes
    assert elapsed < 1.6 * wait, f"the second publish waited {elapsed:.2f} s, a second wait"


@needs_git
async def test_an_aside_directory_a_crashed_first_use_left_is_swept(tmp_path: Path) -> None:
    """A first use killed before its rename leaves `.git-init-*` with a whole repository in it;
    the next first use sweeps one older than a live first use could be, so `git add -A` cannot add
    it as an embedded repository (the lane review's round 3, minor)."""
    root = tmp_path / "fresh"
    root.mkdir()
    stale = root / ".git-init-crashed"
    (stale / ".git").mkdir(parents=True)
    old = time.time() - 3600
    os.utime(stale, (old, old))

    await commit_recipe_file("alpha", b"id: alpha\n", version=1, repo_root=root)

    assert sorted(p.name for p in root.iterdir()) == [".git", "recipes"]
    assert _git(root, "status", "--porcelain") == ""
