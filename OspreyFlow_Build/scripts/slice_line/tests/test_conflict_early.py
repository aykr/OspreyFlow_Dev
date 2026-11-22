"""A conflict with main is seen before the merge (the owner's word of 21 November 2026; LINE_FAULTS_2026-11-21.md, 8:
DC1c sat verified for hours while it conflicted with main, and the board said "verified" throughout).

When a verifier passes, and whenever main moves (each board run looks again once main or the slice's tip is new to
it), the line merges each verified slice with main in `git merge-tree`, read-only: it writes no branch, ref, index or
worktree. A conflict is recorded as the merge records one (a findings record naming the files; refused for `conflict`,
or `records` when only the records folder conflicts), so resume.py send-back returns the slice to its builder with no
round spent, and the board shows "verified, conflicts with main in <files>". A merge running holds the look back; the
board's next run looks.
"""
from __future__ import annotations

import fcntl
import json
import subprocess

from test_finding_kind import at_verifier, run_verifier
from test_gates import built, sh, verified, world  # noqa: F401  (world is a fixture)
from test_merge_conflict import HEAD, MAINS, OURS, TABLE, changes, resume, set_state, state, table_on_main

V062 = "OspreyFlow_Build/process/lanes/v062"


def board(w):
    return sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False)


def verified_slice(w):
    table_on_main(w, HEAD)
    wt, tip = built(w, extra={TABLE: HEAD + OURS})
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    assert board(w).returncode == 0
    assert state(w)["phase"] == "verified"
    return wt, tip


def untouched(w, wt):
    """Everything git could have written but objects: refs, the index and status of both trees, the worktree list."""
    return [sh(cmd, where, w["env"]).stdout for cmd, where in (
        ("git for-each-ref --format='%(refname) %(objectname)'", w["repo"]), ("git worktree list --porcelain", w["repo"]),
        ("git status --porcelain --untracked-files=all", w["repo"]), ("git ls-files -s", w["repo"]),
        ("git status --porcelain --untracked-files=all", wt), ("git ls-files -s", wt), ("git rev-parse HEAD", wt))]


def test_when_main_moves_a_verified_slice_that_conflicts_is_shown_and_recorded_for_a_free_send_back(world):
    w = world
    wt, tip = verified_slice(w)
    table_on_main(w, HEAD + MAINS)                                 # main moves: another row in the same place
    before = untouched(w, wt)
    b = board(w)
    assert untouched(w, wt) == before                              # read-only: no branch, ref, index or worktree
    row = next(ln for ln in b.stdout.splitlines() if ln.startswith("S1 "))
    assert f"verified, conflicts with main in {TABLE}" in row, b.stdout
    st = state(w)
    assert (st["phase"], st["refused_for"], st["refused_tests"]) == ("refused", "conflict", 0), st
    assert st["note"] == f"verified, conflicts with main in {TABLE}", st
    f = json.loads((w["data"] / f"records/S1/verify-gate-{tip}.json").read_text())["findings"]
    assert len(f) == 1 and f[0]["file"] == TABLE and "merge main into this branch" in f[0]["what"], f
    lim = state(w)["rounds_limit"]
    set_state(w, round=lim)
    p = resume(w)                                                   # as at merge: no round, no line
    assert p.returncode == 0, p.stdout + p.stderr
    assert (state(w)["phase"], state(w)["round"]) == ("building", lim)
    assert "conflict" in changes(w)[0][3] and "round unchanged" in changes(w)[0][3]


def test_when_the_verifier_passes_a_conflict_already_there_is_found_at_once(world):
    w = world
    table_on_main(w, HEAD)
    wt, tip = at_verifier(w, round_=1, limit=3)
    (wt / TABLE).parent.mkdir(parents=True, exist_ok=True)
    (wt / TABLE).write_text(HEAD + OURS)
    sh(f"git add {TABLE} && git commit -qm 'feat: a row'", wt, w["env"])
    from test_gates import stop_gate
    assert stop_gate(w, wt) is None
    tip = sh("git rev-parse HEAD", wt).stdout.strip()
    set_state(w, phase="verifying", tip=tip)
    table_on_main(w, HEAD + MAINS)
    p, _ = run_verifier(w, tip, [], verdict="pass")
    st = state(w)
    assert (st["phase"], st["refused_for"]) == ("refused", "conflict"), (st, p.stdout)
    assert st["note"] == f"verified, conflicts with main in {TABLE}"


def test_a_verified_slice_that_merges_cleanly_stays_verified_and_is_looked_at_once_per_main(world):
    w = world
    wt, tip = verified_slice(w)
    (w["repo"] / "notes").mkdir(exist_ok=True)
    (w["repo"] / "notes/other.md").write_text("other\n")
    sh("git add notes/other.md && git commit -qm 'docs: other'", w["repo"], w["env"])
    board(w)
    assert state(w)["phase"] == "verified"
    main = sh("git rev-parse main", w["repo"]).stdout.strip()
    seen = json.loads((w["data"] / "conflict-check.json").read_text())
    assert seen["S1"] == {"main": main, "tip": tip, "files": []}, seen


def test_a_records_only_conflict_found_early_keeps_its_own_kind(world):
    w = world
    rules = f"{V062}/notes.md"
    (w["repo"] / rules).write_text("one\n")
    sh(f"git add {rules} && git commit -qm 'records: notes'", w["repo"], w["env"])
    wt, tip = built(w, extra={rules: "one\nslice\n"})
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    (w["repo"] / rules).write_text("one\nmain\n")
    sh(f"git add {rules} && git commit -qm 'records: notes again'", w["repo"], w["env"])
    board(w)
    st = state(w)
    assert (st["phase"], st["refused_for"]) == ("refused", "records"), st
    assert st["note"] == f"verified, conflicts with main in {rules}", st


def test_while_a_merge_runs_the_look_waits_for_the_next_board_run(world):
    w = world
    wt, tip = verified_slice(w)
    table_on_main(w, HEAD + MAINS)
    holder = subprocess.Popen([w["py"], "-c", "import fcntl, sys, time; fh = open(sys.argv[1], 'a'); "
                               "fcntl.flock(fh, fcntl.LOCK_EX); print('held', flush=True); time.sleep(60)",
                               str(w["data"] / "merge.lock")], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        (w["data"] / "merge.running.json").write_text(json.dumps({"slice": "S9"}))
        board(w)
        assert state(w)["phase"] == "verified"                     # not looked at under a running merge
    finally:
        holder.kill()
        holder.wait()
    (w["data"] / "merge.running.json").unlink()
    board(w)
    assert state(w)["phase"] == "refused" and state(w)["refused_for"] == "conflict"
