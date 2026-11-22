"""test_layout in a builder's worktree (LINE_FIXES_5_BRIEF.md, 5).

The line put its copy of main's RULINGS.md at `Claude outputs/slice-line/RULINGS.md` in every slice worktree, a folder
at the tree's root, and `tests/test_layout.py::test_no_product_folder_is_left_at_the_root` failed on it ("still at the
root: ['Claude outputs']"), so PL4d3c stopped and BL1b's fix could not be proved in its worktree. The copy now lives in
the worktree's own git folder (`git rev-parse --git-path slice-line/RULINGS.md`), which is no entry of the tree, and a
copy left at the old place is removed. The test itself is unchanged: a stray root folder still fails it.
"""
from __future__ import annotations

from pathlib import Path

from test_gates import sh, started, world  # noqa: F401  (world is a fixture)
from test_self_clear import LAYOUT_STAND_IN, PYTEST, commit_main

V062 = "OspreyFlow_Build/process/lanes/v062"
OLD = "Claude outputs/slice-line/RULINGS.md"


def deliver(w, wt):
    code = (f"import sys; sys.path.insert(0, {str(w['lines'])!r}); import common as c, run_seat; from pathlib import Path; "
            f"print(run_seat.rulings_note(Path({str(wt)!r})))")
    return sh([w["py"], "-c", code], w["repo"], w["env"]).stdout


def copy_of(wt):
    return Path(sh("git rev-parse --path-format=absolute --git-path slice-line/RULINGS.md", wt).stdout.strip())


def test_a_worktree_made_by_the_line_passes_the_layout_test(world):
    w = world
    commit_main(w, {f"{V062}/RULINGS.md": "# Rulings\n\nOne.\n", "tests/test_layout.py": LAYOUT_STAND_IN})
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    said = deliver(w, wt)  # as before every builder and verifier session
    tracked = set(sh("git ls-tree --name-only HEAD", wt).stdout.split()) | {".git"}
    assert {q.name for q in wt.iterdir()} <= tracked, sorted(q.name for q in wt.iterdir())  # the line adds no root entry
    assert sh(f"{PYTEST} tests/test_layout.py", wt, w["env"], check=False).returncode == 0
    assert copy_of(wt).read_text().startswith("# Rulings") and str(copy_of(wt)) in said, said
    assert sh("git status --porcelain --ignored", wt).stdout.strip() == "", "the copy is among the tree's files"


def test_a_planted_stray_root_folder_still_fails_it(world):
    w = world
    commit_main(w, {"tests/test_layout.py": LAYOUT_STAND_IN})
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    (wt / "Claude outputs").mkdir()
    q = sh(f"{PYTEST} tests/test_layout.py", wt, w["env"], check=False)
    assert q.returncode == 1 and "still at the root: ['Claude outputs']" in q.stdout, q.stdout


def test_a_copy_left_at_the_old_place_is_removed_with_its_folders(world):
    w = world
    commit_main(w, {f"{V062}/RULINGS.md": "# Rulings\n"})
    p, wt = started(w)
    (wt / OLD).parent.mkdir(parents=True)
    (wt / OLD).write_text("# Rulings, as the line left them on 20 November\n")
    deliver(w, wt)
    assert not (wt / "Claude outputs").exists() and copy_of(wt).is_file()


def test_the_old_folder_stays_when_something_else_is_in_it(world):
    w = world
    commit_main(w, {f"{V062}/RULINGS.md": "# Rulings\n"})
    p, wt = started(w)
    (wt / OLD).parent.mkdir(parents=True)
    (wt / OLD).write_text("old\n")
    (wt / "Claude outputs/notes.md").write_text("someone's\n")
    deliver(w, wt)
    assert not (wt / OLD).exists() and (wt / "Claude outputs/notes.md").read_text() == "someone's\n"
