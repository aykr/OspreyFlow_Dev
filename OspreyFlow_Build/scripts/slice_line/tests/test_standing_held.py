"""A standing accept that a lock refuses is held, not lost (the owner's word of 21 November 2026, seen on IS5a0 and
PL11): it is tried again as soon as the lock frees, and no other round starts meanwhile. If the lock is still held after
the line's limit, the slice stops for the conductor (who runs resume.py <ID> accept when it frees); it never goes on to
another round with the accept dropped.

The verifier runs as run_seat.py runs it (test_finding_kind.run_verifier); the lock is held by another process.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

import pytest

from test_accept import rec, state
from test_finding_kind import FAULT, finding
from test_gates import world  # noqa: F401  (a fixture)
from test_standing_accept import GAPS, verified_round

HOLDER = """
import fcntl, sys, time
fh = open(sys.argv[1], "a")
fcntl.flock(fh, fcntl.LOCK_EX)
print("held", flush=True)
time.sleep(float(sys.argv[2]))
"""


def hold(path, seconds):
    """Another process holds this lock for so many seconds; returns once it holds it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.Popen([sys.executable, "-c", HOLDER, str(path), str(seconds)], stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "held"
    return p


def lock_of(w, which):
    if which == "the-slices-own-resume-lock":
        return w["data"] / "locks/resume-S1.lock"
    (w["data"] / "merge.running.json").write_text("{not json")  # a merge whose record names no slice: "?"
    return w["data"] / "merge.lock"


@pytest.mark.parametrize("which", ["the-slices-own-resume-lock", "a-merge-whose-record-names-no-slice"])
def test_a_standing_accept_a_lock_refuses_is_held_and_lands_when_the_lock_frees(world, which):
    w = world
    w["env"]["OSPREY_STANDING_HOLD_MINUTES"] = "2"
    holder = hold(lock_of(w, which), 5)
    try:
        t0 = time.monotonic()
        wt, tip, p = verified_round(w, GAPS, round_=3, limit=5)
        waited = time.monotonic() - t0
    finally:
        holder.kill()
        holder.wait()
    st = state(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "held" in p.stdout, p.stdout
    assert st["phase"] == "verified" and st["round"] == 3, st      # accepted; no round 4 was started
    assert (rec(w) / f"accepted-{tip}.json").exists()
    assert waited >= 3, waited                                     # it did wait for the lock


def test_a_standing_accept_held_past_the_limit_stops_the_slice_and_starts_no_round(world):
    w = world
    w["env"]["OSPREY_STANDING_HOLD_MINUTES"] = "0.05"              # 3 seconds
    holder = hold(lock_of(w, "the-slices-own-resume-lock"), 30)
    try:
        wt, tip, p = verified_round(w, GAPS, round_=3, limit=5)
    finally:
        holder.kill()
        holder.wait()
    st = state(w)
    assert p.returncode == 1, p.stdout + p.stderr
    assert st["phase"] == "stopped" and st["round"] == 3, st       # not round 4 with the accept dropped
    assert "standing accept" in st["note"] and "resume.py S1 accept" in st["note"], st["note"]
    assert not (rec(w) / f"accepted-{tip}.json").exists()


def test_a_standing_accept_refused_by_its_rule_is_not_held(world):
    """A refusal that is not a lock's (a fault in behaviour) goes on at once, as before: another round."""
    w = world
    w["env"]["OSPREY_STANDING_HOLD_MINUTES"] = "2"
    t0 = time.monotonic()
    wt, tip, p = verified_round(w, [*GAPS, finding(FAULT, "the button does nothing")], round_=3, limit=5)
    st = state(w)
    assert time.monotonic() - t0 < 60
    assert "held" not in p.stdout, p.stdout
    assert st["phase"] == "building" and st["round"] == 4, st
    assert json.loads((rec(w) / f"verify-{tip}.json").read_text())["verdict"] == "findings"
