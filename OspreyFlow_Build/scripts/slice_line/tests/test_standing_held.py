"""A standing accept that a lock refuses is held, not lost (the owner's word of 21 November 2026, seen on IS5a0 and
PL11): it is tried again as soon as the lock frees, and no other round starts meanwhile. If the lock is still held after
the line's limit, the slice stops for the conductor (who runs resume.py <ID> accept when it frees); it never goes on to
another round with the accept dropped.

The verifier runs as run_seat.py runs it (test_finding_kind.run_verifier); the lock is held by another process. No
clock decides the order (the owner, 23 November 2026: the lock held for 5 seconds freed before the line looked when the
suite ran beside two builders, and apply_39 took its commit back on that red): the lock is held until the test lets it
go, and the test lets it go only once the line has said the accept is held.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

import pytest

from test_accept import rec, state
from test_finding_kind import FAULT, finding, verifier_code
from test_gates import world  # noqa: F401  (a fixture)
from test_standing_accept import GAPS, ON, at_verifier, switch, verified_round

HOLDER = """
import fcntl, sys
fh = open(sys.argv[1], "a")
fcntl.flock(fh, fcntl.LOCK_EX)
print("held", flush=True)
sys.stdin.read()
"""
#: How long the test waits for an event before it fails (never how long a lock is held).
EVENT_WAIT_S = 600


def hold(path):
    """Another process holds this lock until let go (let_go); returns once it holds it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.Popen([sys.executable, "-c", HOLDER, str(path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         text=True)
    assert p.stdout.readline().strip() == "held"
    return p


def let_go(holder):
    holder.stdin.close()
    holder.wait(timeout=EVENT_WAIT_S)


def until_said(proc, out, words):
    """Waits until the running line has printed these words (the event); fails if it ends first."""
    end = time.monotonic() + EVENT_WAIT_S
    while time.monotonic() < end:
        if words in out.read_text():
            return
        if proc.poll() is not None:
            raise AssertionError(f"the line ended before it said {words!r}: {out.read_text()}")
        time.sleep(0.1)
    raise AssertionError(f"the line did not say {words!r} within {EVENT_WAIT_S} s: {out.read_text()}")


def lock_of(w, which):
    if which == "the-slices-own-resume-lock":
        return w["data"] / "locks/resume-S1.lock"
    (w["data"] / "merge.running.json").write_text("{not json")  # a merge whose record names no slice: "?"
    return w["data"] / "merge.lock"


@pytest.mark.parametrize("which", ["the-slices-own-resume-lock", "a-merge-whose-record-names-no-slice"])
def test_a_standing_accept_a_lock_refuses_is_held_and_lands_when_the_lock_frees(world, which):
    w = world
    w["env"]["OSPREY_STANDING_HOLD_MINUTES"] = "60"               # the limit is not what this case is about
    switch(w, ON)
    wt, tip = at_verifier(w, round_=3, limit=5)
    code, _ = verifier_code(w, tip, GAPS)
    out = w["tmp"] / "verifier.out"
    holder = hold(lock_of(w, which))
    with out.open("w") as fh:
        p = subprocess.Popen([w["py"], "-c", code], cwd=w["repo"], env=w["env"], stdout=fh, stderr=subprocess.STDOUT)
        try:
            until_said(p, out, "the standing accept is held")      # the event: refused by the lock, and held
            assert not (rec(w) / f"accepted-{tip}.json").exists()  # not accepted while the lock is held
        finally:
            let_go(holder)
        rc = p.wait(timeout=EVENT_WAIT_S)
    said = out.read_text()
    st = state(w)
    assert rc == 0 and "Traceback" not in said, said
    assert st["phase"] == "verified" and st["round"] == 3, st      # accepted; no round 4 was started
    assert (rec(w) / f"accepted-{tip}.json").exists()


def test_a_standing_accept_held_past_the_limit_stops_the_slice_and_starts_no_round(world):
    w = world
    w["env"]["OSPREY_STANDING_HOLD_MINUTES"] = "0.05"              # 3 seconds
    switch(w, ON)
    wt, tip = at_verifier(w, round_=3, limit=5)
    code, _ = verifier_code(w, tip, GAPS)
    out = w["tmp"] / "verifier.out"
    holder = hold(lock_of(w, "the-slices-own-resume-lock"))       # held until the line has given up, however slow
    with out.open("w") as fh:
        p = subprocess.Popen([w["py"], "-c", code], cwd=w["repo"], env=w["env"], stdout=fh, stderr=subprocess.STDOUT)
        try:
            rc = p.wait(timeout=EVENT_WAIT_S)                      # the event: the line gives up while still held
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            rc = None
        finally:
            let_go(holder)
    said = out.read_text()
    assert rc is not None, f"the line was still holding after {EVENT_WAIT_S} s, past its limit: {said}"
    st = state(w)
    assert rc == 1 and "Traceback" not in said, said
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
