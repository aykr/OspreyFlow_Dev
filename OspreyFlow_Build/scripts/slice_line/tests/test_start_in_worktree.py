"""Each brief's checks are dry-run inside a real builder worktree before the slice starts (LINE_FIXES_5_BRIEF.md, B).

slice_start.py makes the slice's worktree as the builder will have it (the rulings copy in its git folder,
the hashed client names, env: full's environment) and runs every step of the row's checks there, with nothing built and
the slice's own new test files stood in. One that cannot pass there refuses the start in words naming the step and the
failing tests, and the worktree and the branch go. This is what would have found `test_layout` before PL4d3c's builder
spent six tries on it: the scratch tree of the old dry run had no rulings copy at its root, so the test passed there.
The acceptance command may be red: it is red first.
"""
from __future__ import annotations

import json
import sys

from test_gates import sh, started, world  # noqa: F401  (world is a fixture)
from test_self_clear import LAYOUT, LAYOUT_ID, PYTEST, commit_main, hashes_in_the_main_checkout, set_row

V062 = "OspreyFlow_Build/process/lanes/v062"
CHECKS = f"true && {PYTEST} tests/test_layout.py && echo checked"


def not_started(w, p):
    out = p.stdout + p.stderr
    assert p.returncode != 0 and "Traceback" not in out, out
    assert not (w["data"] / "records/S1/frozen.json").exists()
    assert not (w["tmp"] / "wt/slice-S1").exists()
    assert sh("git branch --list lane/slice-S1", w["repo"]).stdout.strip() == "", "the branch was left behind"
    assert not sh("git worktree list --porcelain", w["repo"]).stdout.count("slice-S1")
    return out


def test_a_check_that_fails_only_in_a_builders_worktree_refuses_the_start_in_words(world):
    """A file the line brings into every worktree and a fresh tree never has: the hashed client-name list (until 5,
    the rulings copy at the root was such a file, and test_layout failed on it)."""
    w = world
    set_row(w, checks=CHECKS)
    commit_main(w, {"tests/test_layout.py": LAYOUT})
    hashes_in_the_main_checkout(w)
    said = not_started(w, started(w)[0])
    assert "NOT STARTED" in said and "cannot pass in its own worktree" in said, said
    assert f"step 2 of 3 cannot pass there: {PYTEST} tests/test_layout.py" in said, said
    assert f"failing: {LAYOUT_ID}" in said and "left in the tree: ['OspreyFlow_Build/marketing_site/" in said, said


def test_a_clean_row_starts_and_its_worktree_is_the_builders(world):
    w = world
    set_row(w, checks=CHECKS)
    commit_main(w, {"tests/test_layout.py": LAYOUT, f"{V062}/RULINGS.md": "# Rulings\n"})  # the copy: no root entry
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert json.loads((w["data"] / "records/S1/frozen.json").read_text())["checks"] == CHECKS
    assert sh("git status --porcelain", wt).stdout.strip() == ""


def test_the_rulings_copy_is_in_the_worktree_from_its_start(world):
    w = world
    commit_main(w, {f"{V062}/RULINGS.md": "# Rulings\n\nOne.\n"})
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    copy = sh("git rev-parse --path-format=absolute --git-path slice-line/RULINGS.md", wt).stdout.strip()
    assert open(copy).read().startswith("# Rulings")


def test_the_acceptance_command_being_red_does_not_refuse(world):
    """The slice's own new test file is absent: the acceptance is red (as it must be first); in the checks it is stood
    in by a placeholder, which never stays in the worktree."""
    w = world
    py = f"{sys.executable} -m pytest -q -p no:cacheprovider"
    set_row(w, files="tests/test_new.py", acceptance=f"{py} tests/test_new.py",
            checks=f"{py} tests/test_new.py && echo reached-the-end")
    commit_main(w, {f"{V062}/RULINGS.md": "# Rulings\n"})
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert not (wt / "tests/test_new.py").exists()


def test_checks_that_leave_files_git_does_not_ignore_refuse_the_start(world):
    """The Stop hook reads any such file as uncommitted work: red at every stop."""
    w = world
    set_row(w, checks="touch left-behind.txt")
    commit_main(w, {})
    said = not_started(w, started(w)[0])
    assert "leave files in the worktree that git does not ignore" in said and "left-behind.txt" in said, said
