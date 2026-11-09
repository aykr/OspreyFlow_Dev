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
from pathlib import Path

import pytest
from services.api import studio_publish
from services.api.studio_publish import GitCommitError, commit_recipe_file

GIT = shutil.which("git")
needs_git = pytest.mark.skipif(GIT is None, reason="the host's git reads the history back")


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


async def test_publish_never_execs_a_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []

    def refuse(*args: object, **kwargs: object) -> None:
        calls.append(args)
        raise AssertionError(f"the publish path spawned a process: {args!r}")

    async def refuse_async(*args: object, **kwargs: object) -> None:
        refuse(*args)

    monkeypatch.setenv("PATH", str(tmp_path / "no-binaries-here"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", refuse_async)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", refuse_async)
    monkeypatch.setattr(subprocess.Popen, "__init__", refuse)
    for name in ("system", "posix_spawn", "posix_spawnp", "execv", "execve", "execvp", "fork"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, refuse)

    repo = tmp_path / "repo"
    # A hook a real `git commit` would run: the publish must not run it either.
    await commit_recipe_file("alpha", b"id: alpha\n", version=1, repo_root=repo)
    hook = repo / ".git" / "hooks" / "post-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    await commit_recipe_file("alpha", b"id: alpha\nversion: 2\n", version=2, repo_root=repo)

    assert calls == []


@needs_git
async def test_concurrent_publishes_each_commit_their_own_bytes(tmp_path: Path) -> None:
    """The lock's invariant (rule 12): publishes of one recipe at once never refuse each other,
    and each version's commit holds that version's bytes, not another's."""
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


async def test_a_failed_write_is_a_typed_error_not_a_bare_500(tmp_path: Path) -> None:
    """GitCommitError is what the Conduit maps to its typed response (app.py's handler); a
    dulwich or filesystem failure must surface as it, never as a bare exception."""
    blocker = tmp_path / "repo"
    blocker.mkdir()
    (blocker / ".git").write_text("not a repository\n")  # a file where the git dir should be

    with pytest.raises(GitCommitError) as raised:
        await commit_recipe_file("alpha", b"id: alpha\n", version=1, repo_root=blocker)
    # The text is the client's (app.py's handler returns it): no volume path in it.
    assert str(tmp_path) not in str(raised.value)
    assert "recipes/alpha.yaml" in str(raised.value)


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
