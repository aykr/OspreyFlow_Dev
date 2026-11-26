"""Item 43 and world-files (the owner's order of 25 November 2026), shown by the apply of 55 on 26 November 2026,
06:42: the owner keeps local edits to dial.yaml and accounts.yaml in the main checkout, the apply scripts run the
line's suite there, and every test world copied the working files: an all-default accounts.yaml turned 16 cases red.
A test world now takes the owner's files as the checkout's HEAD commits them, never the working copies.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from test_gates import OWNER_WORLD_FILES, committed_owner_file, owner_files_into


def checkout(tmp: Path) -> Path:
    """A repository laid out as this one: the owner's files committed, then edited and not committed, as the owner's
    main checkout has them; returns its slice_line folder."""
    repo = tmp / "repo"
    v062 = repo / "OspreyFlow_Build/process/lanes/v062"
    line = repo / "OspreyFlow_Build/scripts/slice_line"
    v062.mkdir(parents=True)
    line.mkdir(parents=True)
    env = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t.invalid", "PATH": "/usr/bin:/bin:/usr/local/bin"}
    for name in OWNER_WORLD_FILES:
        (v062 / name).write_text(f"{name}: committed\n")
    subprocess.run("git init -q && git add -A && git commit -qm owner", shell=True, cwd=repo, env=env, check=True)
    for name in OWNER_WORLD_FILES:
        (v062 / name).write_text(f"{name}: the owner's local edit\n")
    return line


def test_a_world_takes_the_owner_files_as_committed_not_the_working_copies(tmp_path):
    line = checkout(tmp_path)
    dest = tmp_path / "world"
    dest.mkdir()
    owner_files_into(dest, line)
    for name in OWNER_WORLD_FILES:
        assert (dest / name).read_text() == f"{name}: committed\n", name


def test_a_file_not_committed_is_refused_not_read_from_the_working_tree(tmp_path):
    line = checkout(tmp_path)
    (line.parents[1] / "process/lanes/v062/new.yaml").write_text("x\n")
    with pytest.raises(AssertionError, match="not committed at HEAD"):
        committed_owner_file("new.yaml", line)


def test_this_checkouts_worlds_read_its_head(tmp_path):
    for name in OWNER_WORLD_FILES:
        assert committed_owner_file(name) == subprocess.run(
            ["git", "show", f"HEAD:OspreyFlow_Build/process/lanes/v062/{name}"], capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[4], check=True).stdout
