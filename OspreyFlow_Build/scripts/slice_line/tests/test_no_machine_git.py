"""The owner's file 006 (22 November 2026, line fault 12): the suite never depends on the machine's git configuration.
It runs as a machine with no identity would (conftest.py), and the test world commits with its own identity, kept in its
repository's config, with the world's environment or without it.
"""
from __future__ import annotations

import os
import subprocess

from test_gates import sh, started, world  # noqa: F401  (world is a fixture)


def test_the_suite_runs_as_on_a_machine_with_no_git_identity(tmp_path):
    assert os.environ.get("GIT_CONFIG_GLOBAL") == "/dev/null" and os.environ.get("GIT_CONFIG_NOSYSTEM") == "1"
    subprocess.run(["git", "init", "-q", str(tmp_path / "r")], check=True)
    p = subprocess.run(["git", "commit", "--allow-empty", "-qm", "x"], cwd=tmp_path / "r", capture_output=True, text=True)
    assert p.returncode != 0 and "auto-detection is disabled" in p.stderr, p.stderr


def test_the_world_commits_with_its_own_identity_without_its_environment(world):
    w = world
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    for where in (w["repo"], wt):                     # the main checkout and a builder's worktree, as os.environ has it
        sh("git commit --allow-empty -qm 'no world environment'", where)
        assert sh("git log -1 --format=%ae", where).stdout.strip() == "t@t.invalid"
