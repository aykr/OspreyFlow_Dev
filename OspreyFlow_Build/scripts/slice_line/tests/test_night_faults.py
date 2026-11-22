"""The fault list of the night of 20 to 21 November (LINE_FIXES_5_BRIEF.md, 9; LINE_FAULTS_2026-11-21.md).

3. A merge refused because the conductor's own records were uncommitted in the main checkout ("the main checkout has
   uncommitted changes"): now records-folder files it has not committed do not hold a merge, unless the branch changes
   one of them (main's fast-forward would meet it); anything else uncommitted still refuses.
4. A background wait polling `pgrep -f 'merge_slice.py merge'` matched its own command line: `merge_slice.py wait-idle`
   waits on the merge lock itself, which is free when no merge runs.
(1, the tests that crossed midnight, is test_gates.TODAY and its test there.)
"""
from __future__ import annotations

import subprocess
import sys
import time

from test_gates import built, main_sha, merge, sh, verified, world  # noqa: F401  (world is a fixture)

V062 = "OspreyFlow_Build/process/lanes/v062"
HOLD = """
import fcntl, json, sys, time
from pathlib import Path
d = Path(sys.argv[1])
fh = (d / "merge.lock").open("w")
fcntl.flock(fh, fcntl.LOCK_EX)
(d / "merge.running.json").write_text(json.dumps({"slice": "S7", "pid": 1}))
print("held", flush=True)
time.sleep(float(sys.argv[2]))
(d / "merge.running.json").unlink()
"""


def hold(w, seconds):
    p = subprocess.Popen([sys.executable, "-c", HOLD, str(w["data"]), str(seconds)], stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "held"
    return p


def wait_idle(w, minutes):
    return sh([w["py"], str(w["lines"] / "merge_slice.py"), "wait-idle", "--minutes", str(minutes)], w["repo"],
              w["env"], check=False)


def test_wait_idle_returns_when_the_merge_ends(world):
    w = world
    h = hold(w, 3)
    t0 = time.time()
    p = wait_idle(w, 1)
    assert p.returncode == 0 and "no merge is running" in p.stdout and time.time() - t0 >= 2, p.stdout + p.stderr
    h.wait()


def test_wait_idle_says_which_merge_still_runs_when_it_gives_up(world):
    w = world
    h = hold(w, 8)
    p = wait_idle(w, 0.03)
    assert p.returncode == 1 and "a merge (S7) is still running" in p.stderr, p.stdout + p.stderr
    h.kill()


def test_wait_idle_with_no_merge_returns_at_once(world):
    p = wait_idle(world, 1)
    assert p.returncode == 0 and "no merge is running" in p.stdout, p.stderr


def test_the_conductors_uncommitted_records_do_not_hold_a_merge(world):
    w = world
    brief = w["repo"] / V062 / "slices/S9.md"
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text("a brief\n")
    sh(f"git add {V062}/slices/S9.md && git commit -qm 'docs: S9' --trailer 'Slice-Records: yes'", w["repo"], w["env"])
    wt, tip = built(w)
    verified(w, wt, tip)
    brief.write_text("a brief, being edited\n")
    p = merge(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert brief.read_text() == "a brief, being edited\n"
    assert f"{V062}/slices/S9.md" in sh("git status --porcelain", w["repo"]).stdout  # still the conductor's, uncommitted


def test_an_uncommitted_file_the_branch_changes_still_refuses_before_the_gate(world):
    w = world
    brief = w["repo"] / V062 / "slices/S1.md"
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text("a\n")
    sh(f"git add {V062}/slices/S1.md && git commit -qm 'docs: S1' --trailer 'Slice-Records: yes'", w["repo"], w["env"])
    (w["lines"] / "scan_map.tsv").write_text("# test\tprefixes\twhy\n")
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'test: no scans' --trailer 'Slice-Records: yes'",
       w["repo"], w["env"])
    wt, tip = built(w, extra={f"{V062}/slices/S1.md": "b\n"})
    verified(w, wt, tip)
    brief.write_text("c\n")
    head = main_sha(w)
    p = merge(w)
    assert p.returncode == 1 and "uncommitted changes to files the branch changes" in p.stderr, p.stdout + p.stderr
    assert main_sha(w) == head and brief.read_text() == "c\n"


def test_anything_else_uncommitted_still_refuses(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    (w["repo"] / "README.md").write_text("an edit\n")
    p = merge(w)
    assert p.returncode == 1 and "the main checkout has uncommitted changes" in p.stderr, p.stderr
