"""`tests/committed.py` reads what git holds, in the shape a lane worktree actually has: the file
committed with one text, the working copy holding another, and `--skip-worktree` set so `git
status` shows nothing (`scripts/lanes_launch.sh`'s `setup`)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.committed import committed_copy, committed_text

COMMITTED = "map:\n  default: osm-local\n"
OWNERS = "map:\n  default: osm-local-great-britain\n"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def lane(tmp_path: Path) -> Path:
    repo = tmp_path / "lane"
    core = repo / "OspreyFlow_Core"
    core.mkdir(parents=True)
    _git(repo, "init", "-q")
    (core / "osprey.yaml").write_text(COMMITTED, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "-qm", "c")
    (core / "osprey.yaml").write_text(OWNERS, encoding="utf-8")
    _git(repo, "update-index", "--skip-worktree", "OspreyFlow_Core/osprey.yaml")
    return core / "osprey.yaml"


def test_a_skip_worktree_copy_is_not_what_it_reads(lane: Path, tmp_path: Path) -> None:
    # The lane's own state: git reports nothing, the file on disk is the owner's.
    assert _git(lane.parents[1], "status", "--porcelain") == ""
    assert lane.read_text(encoding="utf-8") == OWNERS

    assert committed_text(lane) == COMMITTED
    assert committed_copy(lane, tmp_path / "out").read_text(encoding="utf-8") == COMMITTED


def test_a_file_git_does_not_hold_is_refused_not_read_from_disk(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    loose = repo / "osprey.yaml"
    loose.write_text(OWNERS, encoding="utf-8")

    with pytest.raises(RuntimeError, match="git cannot show the committed"):
        committed_text(loose)
