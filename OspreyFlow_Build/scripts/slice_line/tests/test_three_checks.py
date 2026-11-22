"""The owner's file 005 (22 November 2026): five merges were refused by three checks the full gate runs and a slice's
own checks did not (CO1, IS5a twice, SE6b, SE8c): route-coverage-check, test-file-coverage-check and mypy. The line runs
them at the start and at every stop, in the builder's worktree, as its own step (not the slice's frozen row: a slice
started before them meets them at its next stop, with no refreeze). And a refused merge says its cause in a few words
(which check), with a running count by cause on the board.

The three are stood in (TEST_PROJECT_<NAME>'s exit code; TEST_PROJECT_SEES lists each run), in both copies alike.
"""
from __future__ import annotations

import json

from test_gates import built, merge, sh, started, stop_gate, verified, world  # noqa: F401  (world is a fixture)

V062 = "OspreyFlow_Build/process/lanes/v062"
THREE = ["route-coverage-check", "test-file-coverage-check", "mypy"]


def test_every_stop_runs_the_three_and_a_red_one_blocks_the_builder_in_words(world):
    w = world
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    frozen = (w["data"] / "records/S1/frozen.json").read_text()
    (wt / "accept.sh").write_text("exit 0\n")
    sh("git add accept.sh && git commit -qm 'feat: S1'", wt, w["env"])
    w["env"]["TEST_PROJECT_ROUTE_COVERAGE_CHECK"] = "2"
    w["env"]["TEST_PROJECT_SEES"] = str(w["tmp"] / "seen.txt")
    out = stop_gate(w, wt)
    assert out and out["decision"] == "block", out
    assert "RED: route-coverage-check (exit 2), a check the merge's full gate runs" in out["reason"], out["reason"]
    assert (w["tmp"] / "seen.txt").read_text().split() == THREE              # all three, in order, at this stop
    tip = sh("git rev-parse HEAD", wt).stdout.strip()
    assert not (w["data"] / f"records/S1/tests-{tip}.json").exists()
    assert (w["data"] / "records/S1/frozen.json").read_text() == frozen      # the frozen row is unchanged
    w["env"]["TEST_PROJECT_ROUTE_COVERAGE_CHECK"] = "0"
    assert stop_gate(w, wt) is None
    rec = json.loads((w["data"] / f"records/S1/tests-{tip}.json").read_text())
    assert [r["name"] for r in rec["results"] if r["name"] in THREE] == THREE, rec["results"]


def test_mypy_red_on_main_refuses_the_start_and_leaves_nothing(world):
    w = world
    w["env"]["TEST_PROJECT_MYPY"] = "1"
    p, wt = started(w)
    assert p.returncode != 0 and "NOT STARTED" in p.stdout + p.stderr and "RED: mypy (exit 1)" in p.stdout + p.stderr, \
        p.stdout + p.stderr
    assert not wt.exists() and not (w["data"] / "records/S1/frozen.json").exists()


def board(w):
    return sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False).stdout


def test_a_refused_merge_says_which_check_and_the_board_counts_refusals_by_cause(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    log = w["tmp"] / "gate.log"
    log.write_text("FAILED x\nmake[1]: *** [mypy] Error 1\nmake: *** [ci] Error 2\n")
    p = merge(w, gate="1", gate_log=str(log))
    assert p.returncode == 1, p.stdout + p.stderr
    st = json.loads((w["data"] / "records/S1/state.json").read_text())
    assert st["last_refusal_cause"] == "the full gate: mypy", st
    b = board(w)
    row = next(ln for ln in b.splitlines() if ln.startswith("S1 "))
    assert "(the full gate: mypy)" in row, b
    assert "merge refusals by cause: the full gate: mypy 1" in b, b
    st["phase"] = "verified"
    (w["data"] / "records/S1/state.json").write_text(json.dumps(st))
    merge(w, gate="1", gate_log=str(log))
    assert "merge refusals by cause: the full gate: mypy 2" in board(w)


def test_a_conflict_is_counted_as_its_own_cause(world):
    from test_merge_conflict import conflicted
    w = world
    conflicted(w)
    p = merge(w)
    assert p.returncode == 1
    assert json.loads((w["data"] / "records/S1/state.json").read_text())["last_refusal_cause"] == "a conflict with main"
    assert "merge refusals by cause: a conflict with main 1" in board(w)
