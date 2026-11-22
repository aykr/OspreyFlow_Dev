"""Two seats of one account starting together (LINE_FIXES_5_BRIEF.md, 6).

What the line shares per account: `accounts/<account>.json` (the windows each seat's stream reports, read and written
again at every rate-limit event; read by slice_start.py and the board for the 95% rule), `usage.tsv` (one row per
session; its header written when the file is not there) and the stop file. Two seats of one account, started in the
same second, each handle their session's stream at once: here two processes do exactly what run_seat.launch does with a
stream of rate-limit events and then append their usage, while a third reads the account as slice_start.py does. Before
the fix the account file was written through one fixed temporary name (two writers could rename each other's half-written
file into place) and read with no lock, and two seats could each write usage.tsv's header.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

from test_gates import world  # noqa: F401  (world is a fixture)

EVENTS = 150


def seat(w, name, n=EVENTS):
    """One seat's stream on account sol: n rate-limit events on its own window, then its usage row."""
    code = f"""
import sys, time
sys.path.insert(0, {str(w['lines'])!r})
import run_seat
start = float(sys.argv[1])
while time.time() < start:
    time.sleep(0.001)
for i in range({n}):
    run_seat.record_limits("sol", {{"rateLimitType": "{name}-" + str(i), "utilization": 0.1, "resetsAt": 0}})
run_seat.append_usage("S1", "CO1", "{name}", "sol", "m", "e", {{"session_id": "{name}", "usage": {{}}}})
"""
    return code


READER = """
import sys, time
sys.path.insert(0, {lines!r})
import common as c
start, bad, reads = float(sys.argv[1]), 0, 0
while time.time() < start:
    time.sleep(0.001)
end = start + 4
while time.time() < end:
    try:
        c.account_state("sol"); c.near_limit("sol"); reads += 1
    except Exception as e:
        bad += 1
print(bad, reads)
"""


def race(w):
    start = str(time.time() + 1.0)  # the two seats start within the same second
    env = {**w["env"]}
    procs = [subprocess.Popen([sys.executable, "-c", seat(w, n), start], env=env, cwd=str(w["repo"]),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for n in ("builder", "verifier")]
    reader = subprocess.Popen([sys.executable, "-c", READER.format(lines=str(w["lines"])), start], env=env,
                              cwd=str(w["repo"]), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    outs = [p.communicate(timeout=120) for p in procs]
    rout = reader.communicate(timeout=120)
    return procs, outs, reader, rout


def test_two_seats_of_one_account_at_once_both_run_and_nothing_shared_is_half_written(world):
    w = world
    procs, outs, reader, rout = race(w)
    for p, (o, e) in zip(procs, outs):
        assert p.returncode == 0 and "Traceback" not in e, e[-2000:]   # both seats ran
    bad, reads = (int(x) for x in rout[0].split())
    assert reader.returncode == 0 and reads > 0, rout
    assert bad == 0, f"the account file was read half-written or mid-rename {bad} times in {reads} reads"
    st = json.loads((w["data"] / "accounts/sol.json").read_text())
    for name in ("builder", "verifier"):                                 # no seat's windows lost to the other's write
        assert sum(1 for k in st["windows"] if k.startswith(name + "-")) == EVENTS, (name, len(st["windows"]))
    rows = (w["data"] / "usage.tsv").read_text().splitlines()
    assert rows[0].startswith("at\tslice") and sum(r.startswith("at\t") for r in rows) == 1, rows[:4]
    assert sorted(r.split("\t")[7] for r in rows[1:]) == ["builder", "verifier"], rows


STOPPER = """
import json, os, subprocess, sys, time
start = float(sys.argv[1])
while time.time() < start:
    time.sleep(0.001)
env = dict(os.environ, OSPREY_SEAT={seat!r}, OSPREY_ACCOUNT="sol", OSPREY_SLICE="S1")
ev = json.dumps({{"error": "rate_limit", "last_assistant_message": "limit " * 400}})
for i in range(40):
    subprocess.run([sys.executable, {hook!r}, "stop-failure"], input=ev, env=env, text=True, check=True)
"""
STOP_READER = """
import sys, time
sys.path.insert(0, {lines!r})
import common as c
start, bad, reads = float(sys.argv[1]), 0, 0
while time.time() < start:
    time.sleep(0.001)
end = start + 6
while time.time() < end:
    try:
        c.account_stop("sol"); reads += 1
    except Exception:
        bad += 1
print(bad, reads)
"""


def test_two_seats_stopped_at_once_leave_a_whole_stop_file(world):
    """Both seats of the account meet its limit together: each StopFailure hook writes the stop file, while
    slice_start.py reads it (the account's stop decides every new start)."""
    w = world
    hook = str(w["data"] / "bin/usage_hook.py")
    start = str(time.time() + 1.0)
    procs = [subprocess.Popen([sys.executable, "-c", STOPPER.format(seat=s, hook=hook), start], env=w["env"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for s in ("builder", "verifier")]
    reader = subprocess.Popen([sys.executable, "-c", STOP_READER.format(lines=str(w["lines"])), start], env=w["env"],
                              cwd=str(w["repo"]), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for p in procs:
        assert p.wait(timeout=120) == 0, p.stderr.read()[-2000:]
    out, err = reader.communicate(timeout=120)
    bad, reads = (int(x) for x in out.split())
    assert reads > 0 and bad == 0, f"the stop file was read half-written {bad} times in {reads} reads"
    assert json.loads((w["data"] / "accounts/sol.stopped.json").read_text())["error"] == "rate_limit"


def test_the_conductors_usage_row_and_a_seats_at_once_leave_one_header(world):
    """usage_hook.py (the conductor's SessionEnd) and run_seat.py (a seat's end) append to usage.tsv together."""
    w = world
    start = str(time.time() + 1.0)
    hook_rows = f"""
import sys, time
sys.path.insert(0, {str(w['data'] / 'bin')!r})
import usage_hook
start = float(sys.argv[1])
while time.time() < start:
    time.sleep(0.001)
for i in range(100):
    usage_hook.append_usage(["t", "conductor", "", "conductor", "default", "m", "e", "c" + str(i)] + [0] * 7)
"""
    seat_rows = f"""
import sys, time
sys.path.insert(0, {str(w['lines'])!r})
import run_seat
start = float(sys.argv[1])
while time.time() < start:
    time.sleep(0.001)
for i in range(100):
    run_seat.append_usage("S1", "CO1", "builder", "sol", "m", "e", {{"session_id": "s" + str(i), "usage": {{}}}})
"""
    procs = [subprocess.Popen([sys.executable, "-c", code, start], env=w["env"], cwd=str(w["repo"]),
                              stderr=subprocess.PIPE, text=True) for code in (hook_rows, seat_rows)]
    for p in procs:
        assert p.wait(timeout=120) == 0, p.stderr.read()[-2000:]
    rows = (w["data"] / "usage.tsv").read_text().splitlines()
    assert sum(r.startswith("at\t") for r in rows) == 1 and rows[0].startswith("at\t") and len(rows) == 201, rows[:3]
    assert all(len(r.split("\t")) == 15 for r in rows), [r for r in rows if len(r.split("\t")) != 15][:3]


def test_two_writers_of_one_record_never_share_a_temporary_file(world):
    """Any record two processes write (a slice's state.json: run_seat.py and resume.py) is written whole through a
    temporary name of each writer's own."""
    w = world
    start = str(time.time() + 1.0)
    writer = f"""
import sys, time
sys.path.insert(0, {str(w['lines'])!r})
import common as c
start = float(sys.argv[1])
while time.time() < start:
    time.sleep(0.001)
for i in range(300):
    c.write_json(c.DATA / "records/S1/state.json", {{"phase": "building", "round": i, "pad": "x" * 4000}})
"""
    reader = f"""
import json, sys, time
sys.path.insert(0, {str(w['lines'])!r})
import common as c
start, bad = float(sys.argv[1]), 0
while time.time() < start:
    time.sleep(0.001)
end = start + 3
while time.time() < end:
    try:
        json.loads((c.DATA / "records/S1/state.json").read_text())
    except FileNotFoundError:
        pass
    except ValueError:
        bad += 1
print(bad)
"""
    procs = [subprocess.Popen([sys.executable, "-c", writer, start], env=w["env"], cwd=str(w["repo"]),
                              stderr=subprocess.PIPE, text=True) for _ in range(2)]
    r = subprocess.Popen([sys.executable, "-c", reader, start], env=w["env"], cwd=str(w["repo"]),
                         stdout=subprocess.PIPE, text=True)
    for p in procs:
        assert p.wait(timeout=120) == 0, p.stderr.read()[-1500:]
    assert r.communicate(timeout=120)[0].strip() == "0"
    assert not list((w["data"] / "records/S1").glob("*.tmp"))
