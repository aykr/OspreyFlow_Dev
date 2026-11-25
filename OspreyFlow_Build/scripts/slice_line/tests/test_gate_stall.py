"""A merge's command that prints nothing for 20 minutes is ended (the owner, 24 November 2026).

GR2a's gate hung twice that day when the network dropped (11:28 and 17:30), holding the merge lock for hours each time.
Now merge_slice.run() watches the merge log: a command whose output has not grown for the stall limit
(GATE_STALL_SECONDS, 20 minutes; OSPREY_GATE_STALL_SECONDS here) has its whole process group ended, the log says
"STALLED", and the merge is refused "stalled, not the part's fault", the stalled command named: no round, no finding,
the part's phase unchanged, the lock freed. A slow command that keeps printing is never ended.
"""
from __future__ import annotations

import json
import os
import time

from test_gates import built, merge, sh, verified, world  # noqa: F401  (world is a fixture)
from test_resume import set_state, state

SILENT = "echo started; sleep 60"
SLOW = "for i in 1 2 3 4 5 6 7 8; do echo tick $i; sleep 1; done"


def run_it(w, cmd, stall="2"):
    """merge_slice.run() on `cmd`, as the merge runs a command: ('ok', exit code) or ('stalled', its words)."""
    log = w["tmp"] / "run.log"
    code = (f"import sys, json; sys.path.insert(0, {str(w['lines'])!r}); import merge_slice as m; from pathlib import Path\n"
            "try:\n"
            f"    print(json.dumps(['ok', m.run(['sh', '-c', sys.argv[1]], Path({str(w['tmp'])!r}), Path({str(log)!r}))]))\n"
            "except m.Stalled as e:\n"
            "    print(json.dumps(['stalled', str(e), e.target]))\n")
    t0 = time.monotonic()
    p = sh([w["py"], "-c", code, cmd], w["repo"], {**w["env"], "OSPREY_GATE_STALL_SECONDS": stall}, check=False)
    assert p.returncode == 0, p.stdout + p.stderr
    return json.loads(p.stdout), time.monotonic() - t0, log.read_text()


def test_a_silent_command_is_ended_and_said_stalled(world):
    w = world
    pid_file = w["tmp"] / "child.pid"
    (said, *rest), took, log = run_it(w, f"sleep 60 & echo $! > {pid_file}; echo started; wait")
    assert said == "stalled" and "not the part's fault" in rest[0] and "sleep 60" in rest[1], rest
    assert took < 40, took                                                       # seconds, never the 60
    assert "STALLED:" in log and "printed nothing for 2 s" in log, log
    time.sleep(0.5)
    child = int(pid_file.read_text())
    try:
        os.kill(child, 0)
        alive = True
    except ProcessLookupError:
        alive = False
    assert not alive, "the stalled command's own child was left running"         # its whole process group ended


def test_a_slow_command_that_keeps_printing_is_not_ended(world):
    (said, code), took, log = run_it(world, SLOW)
    assert (said, code) == ("ok", 0) and "tick 8" in log and "STALLED" not in log, log


def test_a_command_that_prints_then_falls_silent_is_ended(world):
    (said, *_), took, log = run_it(world, "echo a; echo b; sleep 60")
    assert said == "stalled" and "b" in log and "STALLED:" in log


def test_a_merge_whose_gate_falls_silent_is_refused_stalled_and_frees_the_lock(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    t0 = time.monotonic()
    p = sh([w["py"], str(w["lines"] / "merge_slice.py"), "merge", "S1"], w["repo"],
           {**w["env"], "TEST_GATE_RUN": SILENT, "OSPREY_GATE_STALL_SECONDS": "2"}, check=False)
    assert p.returncode == 1 and "stalled, not the part's fault" in p.stderr and "sleep 60" in p.stderr, p.stderr
    assert time.monotonic() - t0 < 120
    rec = w["data"] / "records/S1"
    (r,) = [json.loads(f.read_text()) for f in rec.glob("refusal-stalled-*.json")]
    assert r["kind"] == "stalled" and "sleep 60" in r["target"] and r["tip"] == tip, r
    st = state(w)
    assert st["phase"] == "verified" and st["last_refusal_cause"].startswith("stalled:"), st     # no round, no finding
    assert not list(rec.glob("verify-gate-*.json"))
    assert not (w["data"] / "merge.running.json").exists()
    rows = (w["data"] / "refusals.tsv").read_text().splitlines()[1:]
    assert len(rows) == 1 and "\tstalled: " in rows[0], rows
    again = merge(w)                                                             # the lock is free: merged now
    assert again.returncode == 0, again.stdout + again.stderr


def test_a_merge_whose_gate_is_slow_but_prints_merges(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    p = sh([w["py"], str(w["lines"] / "merge_slice.py"), "merge", "S1"], w["repo"],
           {**w["env"], "TEST_GATE_RUN": SLOW, "OSPREY_GATE_STALL_SECONDS": "2"}, check=False)
    assert p.returncode == 0, p.stdout + p.stderr
    assert not list((w["data"] / "records/S1").glob("refusal-stalled-*.json"))


def test_the_stall_limit_is_twenty_minutes(world):
    w = world
    code = f"import sys; sys.path.insert(0, {str(w['lines'])!r}); import merge_slice as m; print(m.GATE_STALL_SECONDS)"
    env = {k: v for k, v in w["env"].items() if k != "OSPREY_GATE_STALL_SECONDS"}
    assert sh([w["py"], "-c", code], w["repo"], env).stdout.strip() == "1200"
