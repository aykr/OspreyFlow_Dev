"""The heartbeat (the owner, 25 November 2026): every long script of the line (tests/run.sh, each merge step) prints a
line with the time at least every 30 seconds, so a running script is told from a stalled one.

A heartbeat line is never output for 50's stall check: tests/run.sh beats inside the merge's own `make ci`, into the
merge log, so a hung suite that only beats would otherwise hold the merge lock for ever. merge_slice.run() and the
board's "stalled" read past heartbeat lines (common.OutputWatch). OSPREY_HEARTBEAT_SECONDS stands in for the 30.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from test_gates import SRC, sh, world  # noqa: F401  (world is a fixture)
from test_gate_stall import run_it
from test_merge_progress import at_step, board, ready, start

sys.path.insert(0, str(SRC))
import common  # noqa: E402

BEAT = re.compile(r"^\[heartbeat \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\] (.+), (?:\d+ min )?\d+ s in$", re.M)


def fake_python(w, seconds, out="", code=0):
    """A stand-in for the suite's python: silent for `seconds`, then `out`, then exit `code`."""
    f = w["tmp"] / f"fakepy-{seconds}-{code}"
    f.write_text(f"#!/bin/sh\nsleep {seconds}\n{f'echo {out}' if out else ''}\nexit {code}\n")
    f.chmod(0o755)
    return f


def suites(w):
    """The line's two real run.sh, copied into a git folder of their own (the test world's copy of the line has no
    tests folder; each run.sh finds its python and its root through git)."""
    d = w["tmp"] / "suites"
    if not d.exists():
        for rel in ("tests/run.sh", "demo_server/tests/run.sh"):
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text((SRC / rel).read_text())
        sh(["git", "init", "-q", str(d)], w["tmp"], w["env"])
    return d


def suite_cmd(w, py, rel="tests/run.sh", every="0.3"):
    var = "EARLY_WARNING_PY" if rel.startswith("demo_server") else "SLICE_LINE_PY"
    return f"{var}={py} OSPREY_HEARTBEAT_SECONDS={every} bash {suites(w) / rel}"


def run_suite(w, cmd, limit=30):
    """A suite run with a bound: in its own process group, killed whole at `limit` seconds, so a suite left waiting on
    its own beat (a planted fault) fails here rather than holding the test, and the planted-fault run, for ever."""
    p = subprocess.Popen(cmd, shell=True, cwd=str(w["repo"]), env=w["env"], text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        out, err = p.communicate(timeout=limit)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        out, err = p.communicate()
        pytest.fail(f"the suite was still running after {limit} s:\n{out}\n{err}")
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)


# ------------------------------------------------------------------ the suites beat


@pytest.mark.parametrize("rel,what", [("tests/run.sh", "the slice line's suite"),
                                      ("demo_server/tests/run.sh", "the early warning's suite")])
def test_a_suite_beats_while_it_runs_and_keeps_its_exit_code(world, rel, what):
    w = world
    py = fake_python(w, 1.5, "the-suite-said-this", 3)
    t0 = time.monotonic()
    p = run_suite(w, suite_cmd(w, py, rel))
    assert p.returncode == 3 and "the-suite-said-this" in p.stdout, p.stdout + p.stderr
    beats = BEAT.findall(p.stderr)
    assert len(beats) >= 3 and all(what in b for b in beats), p.stderr
    assert all(common.HEARTBEAT_LINE.fullmatch((ln + "\n").encode()) for ln in p.stderr.splitlines()
               if ln.startswith("[heartbeat")), p.stderr                  # the shape the stall check reads past
    assert time.monotonic() - t0 < 10                                     # nothing left holding its output open
    assert BEAT.search(p.stdout) is None                                  # standard error only


@pytest.mark.parametrize("rel", ["tests/run.sh", "demo_server/tests/run.sh"])
def test_a_suite_that_ends_between_beats_leaves_nothing_holding_its_output(world, rel):
    """A beat's sleep is ended with the suite: a caller reading the suite's output through a pipe is not kept waiting
    for the next beat (30 s in earnest; 20 here)."""
    w = world
    t0 = time.monotonic()
    p = run_suite(w, suite_cmd(w, fake_python(w, 0.5, "done"), rel, every="20"), limit=10)
    assert p.returncode == 0 and "done" in p.stdout, p.stdout + p.stderr
    assert time.monotonic() - t0 < 10, time.monotonic() - t0


def test_the_heartbeat_is_at_least_every_30_seconds_by_default():
    text = (SRC / "tests/run.sh").read_text() + (SRC / "demo_server/tests/run.sh").read_text()
    assert text.count("${OSPREY_HEARTBEAT_SECONDS:-30}") == 2 and common.HEARTBEAT_SECONDS == 30


# ------------------------------------------------------------------ a heartbeat is never output for the stall check


def test_a_suite_that_only_beats_is_still_ended_as_stalled(world):
    """The real tests/run.sh, hung (its python silent), run as the merge's make ci runs it: it beats every 0.3 s, and
    the merge's run() ends it at the stall limit all the same."""
    w = world
    (said, *rest), took, log = run_it(w, suite_cmd(w, fake_python(w, 60)), stall="2")
    assert said == "stalled" and "tests/run.sh" in rest[1], (said, rest)
    assert len(BEAT.findall(log)) >= 3, log                               # it did beat, into the merge log
    assert took < 40, took


@pytest.mark.parametrize("rel", ["tests/run.sh", "demo_server/tests/run.sh"])
def test_a_passing_suite_never_ends_red_by_its_own_beat(world, rel):
    """The apply of 55, 26 November 2026, 06:42: tests/run.sh exited 1 with every test it ran green. The beat's TERM
    trap ran `kill "$s"` under set -e; when its sleep had just ended, the kill failed and the beat exited 1 before
    `exit 0`, and the suite's EXIT trap waited on it, also under set -e, so the suite ended 1. A race, so many runs,
    each with a fast beat and a suite that passes: every one must end 0."""
    w = world
    py = fake_python(w, 0.05)
    codes = [run_suite(w, suite_cmd(w, py, rel, every="0.01")).returncode for _ in range(40)]
    assert codes == [0] * 40, codes


@pytest.mark.parametrize("rel", ["tests/run.sh", "demo_server/tests/run.sh"])
def test_a_failing_suite_keeps_its_own_exit_through_the_beat(world, rel):
    w = world
    py = fake_python(w, 0.05, code=3)
    codes = {run_suite(w, suite_cmd(w, py, rel, every="0.01")).returncode for _ in range(40)}
    assert codes == {3}, codes


def test_a_suite_that_prints_between_its_beats_is_not_ended(world):
    w = world
    loop = w["tmp"] / "slowpy"
    loop.write_text("#!/bin/sh\nfor i in 1 2 3 4 5 6; do echo tick $i; sleep 0.8; done\nexit 0\n")
    loop.chmod(0o755)
    (said, code), took, log = run_it(w, suite_cmd(w, loop), stall="2")
    assert (said, code) == ("ok", 0) and "tick 6" in log and "STALLED" not in log, log


def test_a_merge_whose_gate_only_beats_is_refused_stalled(world):
    w = world
    ready(w)
    p = sh([w["py"], str(w["lines"] / "merge_slice.py"), "merge", "S1"], w["repo"],
           {**w["env"], "TEST_GATE_RUN": suite_cmd(w, fake_python(w, 60)), "OSPREY_GATE_STALL_SECONDS": "2"}, check=False)
    assert p.returncode != 0 and "stalled, not the part's fault" in p.stderr, p.stdout + p.stderr


def test_the_board_shows_a_merge_whose_log_only_beats_stalled(world):
    w = world
    ready(w)
    p = start(w, TEST_GATE_RUN=suite_cmd(w, fake_python(w, 8)), OSPREY_GATE_STALL_SECONDS=60)
    try:
        r = at_step(w, 5, p)
        time.sleep(3.5)
        log = Path(r["log"]["path"]).read_text()
        assert BEAT.search(log), log                                      # the log grew, by heartbeat lines alone
        b, co1 = board(w, OSPREY_STALL_SECONDS=2)
        assert co1["progress"]["state"] == "stalled", co1
    finally:
        p.communicate(timeout=120)


@pytest.mark.parametrize("pieces,counted", [
    ([b"[heartbeat 2026-11-25T05:12:30Z] tests/run.sh: the suite, 30 s in\n"], False),
    ([b"[heartbeat 2026-11-25T05:12:30Z] tests/run.sh: the sui", b"te, 30 s in\n"], False),     # written in two
    ([b"[heart", b"beat 2026-11-25T05:12:30Z] x, 1 s in\n"], False),
    ([b"....", b"[heartbeat 2026-11-25T05:12:30Z] x, 1 s in\n"], True),                   # dots before it: output
    ([b"[heartbeat 2026-11-25T05:12:30Z] x, 1 s in\n.."], True),                          # and after it
    ([b"[heartbeat soon] not one\n"], True),
], ids=["whole", "split", "split-in-its-mark", "dots-first", "dots-after", "not-its-shape"])
def test_output_is_what_is_not_a_heartbeat_line(tmp_path, pieces, counted):
    log = tmp_path / "m.log"
    log.write_bytes(b"$ make ci\n")
    watch = common.OutputWatch(log)
    watch.last -= 100                                                     # quiet for 100 s so far
    for piece in pieces:
        with log.open("ab") as fh:
            fh.write(piece)
        watch.look()
    assert (watch.look() < 50) is counted


# ------------------------------------------------------------------ each merge step beats, on standard error


def test_a_running_merge_beats_with_its_step_and_its_answer_stays_json(world):
    w = world
    ready(w)
    p = start(w, TEST_GATE_SLEEP=3, OSPREY_HEARTBEAT_SECONDS=0.4)
    out, err = p.communicate(timeout=120)
    assert p.returncode == 0, out + err
    json.loads(out)                                                       # standard output is the answer alone
    beats = BEAT.findall(err)
    assert any(b.startswith("merge_slice.py merge S1: step 5 of 7, today's full gate") for b in beats), err


@pytest.mark.parametrize("script,argv,words", [
    ("early_warning.py", ["S1"], "early_warning.py S1"),
    ("dry_run.py", None, "dry run of S1's commands on main"),
])
def test_the_early_warning_and_the_dry_run_beat(world, script, argv, words):
    """Each beats while its work runs (the work stood in by a sleep, at its own call site)."""
    w = world
    mod = script[:-3]
    if mod == "early_warning":
        body = (f"m._main = lambda argv: (time.sleep(1.5), 0)[1]\n"
                f"sys.exit(m.main({argv!r} + ['--key', '/home/x/secret-key']))")
    else:
        body = ("m._prove = lambda *a: (time.sleep(1.5), [])[1]\n"
                "sys.exit(len(m.prove({'id': 'S1', 'checks': 'true', 'acceptance': 'false'})))")
    code = f"import sys, time; sys.path.insert(0, {str(w['lines'])!r}); import {mod} as m\n{body}\n"
    p = sh([w["py"], "-c", code], w["repo"], {**w["env"], "OSPREY_HEARTBEAT_SECONDS": "0.4"}, check=False)
    assert p.returncode == 0, p.stdout + p.stderr
    beats = BEAT.findall(p.stderr)
    assert len(beats) >= 2 and all(b == words for b in beats), p.stderr
    assert "secret-key" not in p.stderr                                   # never an argument's path or value
