"""An owner's line moves a started slice's seat to another account (LINE_FIXES_3_BRIEF.md, 1g; the owner's word of 19
November 2026, after the sol account was blocked at the organisation level and every started slice on it was stuck).

resume.py runs as the conductor runs it; the verifier runs as run_seat.py runs it, its Claude session stood in by a
result line (the suite starts none), with run_seat.py's own transcript_of reading the fake home's config folders.
"""
from __future__ import annotations

import fcntl
import json
import subprocess
import time

import pytest

from test_finding_kind import at_verifier
from test_gates import main_sha, merge, sh, world  # noqa: F401  (world is a fixture)

V062 = "OspreyFlow_Build/process/lanes/v062"
TODAY = time.strftime("%Y-%m-%d", time.gmtime())


def move(w, *args, env=None):
    return sh([w["py"], str(w["lines"] / "resume.py"), "S1", "move-seat", *args], w["repo"], {**w["env"], **(env or {})},
              check=False)


def said_refused(p, *words):
    out = p.stdout + p.stderr
    return (p.returncode == 1 and p.stderr.startswith("Refused: ") and "Traceback" not in out
            and all(x in p.stderr for x in words))


def owner_line(w, *lines):
    (w["repo"] / V062 / "resume.tsv").write_text("".join(f"{ln}\n" for ln in lines))


def state(w):
    return json.loads((w["data"] / "records/S1/state.json").read_text())


def snapshot(w):
    return {str(p): p.read_bytes() for p in sorted((w["data"] / "records").rglob("*")) if p.is_file()}


def changes(w):
    f = w["data"] / "owner-changes.tsv"
    return [ln.split("\t") for ln in f.read_text().splitlines()[1:]] if f.exists() else []


def fake_claude(w, signed_out=()):
    """A claude whose `auth status` says signed out for the named accounts' config folders."""
    f = w["tmp"] / "claude-auth"
    cases = "".join(f'  *{"/.claude" if a == "default" else "/.claude-" + a}) echo \'{{"loggedIn": false}}\'; exit 0;;\n'
                    for a in signed_out)
    f.write_text('#!/bin/sh\ncase "${CLAUDE_CONFIG_DIR:-$HOME/.claude}" in\n' + cases + "esac\n"
                 'echo \'{"loggedIn": true}\'\n')
    f.chmod(0o755)
    return {"OSPREY_CLAUDE_BIN": str(f)}


def run_verifier_on_its_account(w, tip, session="v-moved", verdict="pass"):
    """run_seat.verifier('S1') with its session stood in; the stand-in records the account the launch was given and
    the config folder that account's launch environment names, and leaves the session's transcript where Claude Code
    leaves it: under that account's config folder. run_seat.transcript_of is the line's own."""
    seen = w["tmp"] / "launched.json"
    code = f"""
import json, sys
from pathlib import Path
sys.path.insert(0, {str(w['lines'])!r})
import common as c, run_seat
seen = []
def launch(seat, account, cwd, prompt, model, effort, env_extra, log, extra=None, interactive=False):
    cfg = c.claude_env(account).get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    seen.append({{"account": account, "config": cfg}})
    t = Path(cfg) / "projects" / "-verify-S1" / ({session!r} + ".jsonl")
    t.parent.mkdir(parents=True, exist_ok=True)
    t.write_text(json.dumps({{"type": "assistant", "text": {verdict!r} + " " + {tip!r}}}) + "\\n")
    out = {{"verdict": {verdict!r}, "commit": {tip!r}, "findings": []}}
    return {{"type": "result", "subtype": "success", "is_error": False, "num_turns": 9, "session_id": {session!r},
            "structured_output": out, "usage": {{}}, "total_cost_usd": 0}}
run_seat.launch = launch
rc = run_seat.verifier("S1")
open({str(seen)!r}, "w").write(json.dumps(seen))
sys.exit(rc)
"""
    p = sh([w["py"], "-c", code], w["repo"], w["env"], check=False)
    assert "Traceback" not in p.stderr, p.stderr
    return p, json.loads(seen.read_text())


# ------------------------------------------------------------------ the owner's word, and only it


@pytest.mark.parametrize("line", [None, "S9\tmove-seat\tverifier\tdefault\t@TODAY@",
                                  "S1\tmove-seat\tbuilder\tdefault\t@TODAY@", "S1\tmove-seat\tverifier\tsol\t@TODAY@",
                                  "S1\tmove-seat\tverifier\tdefault\t2020-01-01", "S1\tmove-seat\t@TODAY@",
                                  "# S1\tmove-seat\tverifier\tdefault\t@TODAY@"],
                         ids=["no-line", "another-slice", "another-seat", "another-account", "another-date", "no-seat",
                              "a-comment"])
def test_move_seat_refuses_without_the_owners_line_for_that_slice_seat_account_and_day(world, line):
    w = world
    at_verifier(w)
    if line:
        owner_line(w, line.replace("@TODAY@", TODAY))
    before = snapshot(w)
    p = move(w, "verifier", "default")
    assert said_refused(p, "no line", "move-seat"), p.stdout + p.stderr
    assert snapshot(w) == before and changes(w) == []


@pytest.mark.parametrize(("seat", "key", "frm", "to"), [("verifier", "verifier_account", "sol", "default"),
                                                       ("builder", "account", "default", "sol")])
def test_move_seat_rewrites_that_seats_account_alone_and_logs_it_once(world, seat, key, frm, to):
    w = world
    at_verifier(w)
    st0 = state(w)
    assert st0[key] == frm, st0
    owner_line(w, f"S1\tmove-seat\t{seat}\t{to}\t{TODAY}")
    before = snapshot(w)
    p = move(w, seat, to)
    assert p.returncode == 0, p.stdout + p.stderr
    st = state(w)
    assert st == {**st0, key: to}, (st0, st)                                  # that key, and nothing else
    after = snapshot(w)
    assert {k for k in after if after[k] != before.get(k)} == {str(w["data"] / "records/S1/state.json")}
    log = changes(w)
    assert len(log) == 1 and log[0][1:3] == ["S1", "move-seat"], log
    assert f"{seat} {frm} -> {to}" in log[0][3] and f"resume.tsv {TODAY}" in log[0][3], log
    p = move(w, seat, to)                                                      # one line, one use
    assert said_refused(p, "already used"), p.stderr
    assert len(changes(w)) == 1


def test_move_seat_refuses_while_a_seat_of_that_slice_runs_or_a_merge_runs(world):
    w = world
    at_verifier(w)
    owner_line(w, f"S1\tmove-seat\tverifier\tdefault\t{TODAY}")
    before = snapshot(w)
    with (w["data"] / "merge.lock").open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        p = move(w, "verifier", "default")
    assert said_refused(p, "another merge is running"), p.stderr
    # a seat running: run_seat.py's own running record, as it writes it, for a process that is alive
    code = (f"import sys, time; sys.path.insert(0, {str(w['lines'])!r}); import run_seat; "
            "cm = run_seat.seat_running('S1', 'builder', 'default'); cm.__enter__(); print('up', flush=True); "
            "time.sleep(60)")
    seat = subprocess.Popen([w["py"], "-c", code], cwd=str(w["repo"]), env=w["env"], stdout=subprocess.PIPE, text=True)
    try:
        assert seat.stdout.readline().strip() == "up"
        p = move(w, "verifier", "default")
        assert said_refused(p, "running", "builder"), p.stderr
    finally:
        seat.kill()
        seat.wait()
    assert changes(w) == []
    # a running record left by a process that has ended does not hold the slice
    p = move(w, "verifier", "default")
    assert p.returncode == 0, p.stdout + p.stderr
    assert {k for k, v in snapshot(w).items() if before.get(k) != v} <= {
        str(w["data"] / "records/S1/state.json"), str(w["data"] / "records/S1/running-builder.json")}


@pytest.mark.parametrize("how", ["signed-out", "stopped", "unknown"])
def test_move_seat_refuses_an_account_that_is_signed_out_stopped_or_not_the_owners(world, how):
    w = world
    at_verifier(w)
    to = "nobody" if how == "unknown" else "default"
    owner_line(w, f"S1\tmove-seat\tverifier\t{to}\t{TODAY}")
    env = fake_claude(w, signed_out=("default",) if how == "signed-out" else ())
    if how == "stopped":
        (w["data"] / "accounts").mkdir(exist_ok=True)
        (w["data"] / "accounts/default.stopped.json").write_text(json.dumps(
            {"account": "default", "error": "rate_limit", "at": "2026-11-19T00:00:00Z"}))
    before = snapshot(w)
    p = move(w, "verifier", to, env=env)
    word = {"signed-out": "signed out", "stopped": "stopped", "unknown": "accounts.yaml"}[how]
    assert said_refused(p, word), p.stderr
    assert snapshot(w) == before and changes(w) == []


@pytest.mark.parametrize("seat", ["builder", "verifier"])
def test_move_seat_sees_a_seat_running_for_the_whole_of_its_launch(world, seat):
    """run_seat.py's builder and verifier hold their running record while their session runs, and drop it after."""
    w = world
    wt, tip = at_verifier(w)
    if seat == "builder":
        st = state(w)
        st["phase"] = "building"
        (w["data"] / "records/S1/state.json").write_text(json.dumps(st))
    seen = w["tmp"] / "running-seen.json"
    code = f"""
import json, os, sys
sys.path.insert(0, {str(w['lines'])!r})
import common as c, run_seat
def launch(seat, account, cwd, prompt, model, effort, env_extra, log, extra=None, interactive=False):
    open({str(seen)!r}, "w").write(json.dumps(c.running_seats("S1")))
    out = {{"verdict": "pass", "commit": {tip!r}, "findings": []}}
    return {{"type": "result", "subtype": "success", "is_error": False, "num_turns": 9, "session_id": "s-run",
            "structured_output": out, "usage": {{}}, "total_cost_usd": 0}}
run_seat.launch = launch
run_seat.transcript_of = lambda a, s: ""
getattr(run_seat, {seat!r})("S1")
print(json.dumps({{"pid": os.getpid(), "after": c.running_seats("S1")}}))
"""
    p = sh([w["py"], "-c", code], w["repo"], w["env"], check=False)
    assert "Traceback" not in p.stderr, p.stderr
    out = json.loads(p.stdout.strip().splitlines()[-1])
    during = json.loads(seen.read_text())
    assert [(r["seat"], r["pid"]) for r in during] == [(seat, out["pid"])], during
    assert out["after"] == [] and not list((w["data"] / "records/S1").glob("running-*.json"))


# ------------------------------------------------------------------ after the move: the seat runs there, and merges


def test_move_seat_the_verifier_then_launches_on_the_new_account_and_the_merge_accepts_its_pass(world):
    """CO2 and PL3 (19 November): their verifier was on sol. Moved to the default account, the verifier's launch is
    given that account and its config folder (~/.claude, not ~/.claude-sol), its transcript is found there, and the
    merge takes its pass."""
    w = world
    wt, tip = at_verifier(w)
    owner_line(w, f"S1\tmove-seat\tverifier\tdefault\t{TODAY}")
    assert move(w, "verifier", "default").returncode == 0
    p, seen = run_verifier_on_its_account(w, tip)
    assert p.returncode == 0, p.stdout + p.stderr
    assert seen == [{"account": "default", "config": str(w["home"] / ".claude")}], seen
    rec = json.loads((w["data"] / f"records/S1/verify-{tip}.json").read_text())
    ps = rec["passes"][0]
    assert ps["account"] == "default" and ps["transcript"].startswith(str(w["home"] / ".claude/projects/")), ps
    assert state(w)["phase"] == "verified"
    before = main_sha(w)
    m = merge(w)
    assert m.returncode == 0, m.stdout + m.stderr
    assert main_sha(w) != before


def test_move_seat_onto_the_builders_account_never_takes_a_builders_session_as_the_verifiers(world):
    """The separation of builder and verifier is by session: with both seats on one account, a pass whose session is
    one the builder ran is refused by the merge."""
    w = world
    wt, tip = at_verifier(w)
    (w["data"] / "records/S1/sessions.json").write_text(json.dumps({"builder": ["b-1"], "verifier": []}))
    owner_line(w, f"S1\tmove-seat\tverifier\tdefault\t{TODAY}")
    assert move(w, "verifier", "default").returncode == 0
    run_verifier_on_its_account(w, tip, session="b-1")
    before = main_sha(w)
    m = merge(w)
    assert m.returncode == 1 and "built the slice" in m.stderr and main_sha(w) == before, m.stderr
