#!/usr/bin/env python3
"""A builder cannot stop on red (process/lanes/v062/slice-line/README.md, "Gates").

The Stop hook for every session; it acts only for a builder seat (OSPREY_SEAT=builder, set by run_seat.py).
It runs only from the fixed place (~/.ospreyflow/slice-line/bin/stop_check.py), never a worktree's copy.

When the builder tries to finish, the slice's frozen checks and acceptance command run in its worktree.
Red: the stop is blocked and the builder gets the failure lines only, not the passes. Uncommitted work is
also red (what is not committed is not on the slice's branch). Green: a test record for the commit is
written for the board and the verifier, and the builder may stop. After MAX_RED blocked stops the builder
is let go, the slice is recorded as stopped on red, and it never shows as verifying or done.
Standard library only; Python 3.9 compatible.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

BIN = Path.home() / ".ospreyflow" / "slice-line"
DATA = Path(os.environ.get("OSPREY_SLICE_HOME") or str(BIN))
MAX_RED = 6
MAX_LINES = 80
TIMEOUT_S = 1500

FAIL_LINE = re.compile(
    r"^(FAILED|ERROR)\b|^E\s|^\s*(✗|×|✘)|\bFAIL\b|AssertionError|Error:|error:|^Traceback|"
    r"^\S+\.py:\d+:|\b\d+ (failed|errors?)\b|^make: \*\*\*|^RED:|^\s*at .+:\d+:\d+\)?$"
)


def failures_only(output: str) -> str:
    lines = [ln.rstrip() for ln in output.splitlines()]
    keep = [ln for ln in lines if FAIL_LINE.search(ln)]
    if not keep:  # a red exit with no recognisable failure line: the tail, which is where the reason is
        keep = [ln for ln in lines if ln.strip()][-15:]
    if len(keep) > MAX_LINES:
        keep = keep[:MAX_LINES] + ["... (" + str(len(keep) - MAX_LINES) + " more failure lines)"]
    return "\n".join(keep)


def run(cmd: str, cwd: str, slot=None) -> tuple:
    env = dict(os.environ)
    env.setdefault("ARCADEDB_HTTP_PORT", "9")  # a pure check never reaches a live store
    env.setdefault("POSTGRES_PORT", "9")
    if slot not in (None, ""):
        env["OSPREY_PORTS_SLOT"] = str(slot)  # the slice's own Playwright slot (slice_start.py), F8
    venv = Path(cwd) / "OspreyFlow_Core/.venv"
    if (venv / "bin/python").is_file():  # env: full built the worktree's own (F6): first on PATH
        env["VIRTUAL_ENV"] = str(venv)
        env["PATH"] = str(venv / "bin") + os.pathsep + env.get("PATH", "")
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT_S, env=env)
        return p.returncode, (p.stdout or "") + "\n" + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "RED: timed out after " + str(TIMEOUT_S) + " s: " + cmd


def git(args: list, cwd: str) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return p.stdout.rstrip()


def main() -> int:
    if os.environ.get("OSPREY_SEAT") != "builder":
        return 0
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        event = {}
    slice_id = os.environ.get("OSPREY_SLICE", "")
    wt = os.environ.get("OSPREY_SLICE_WORKTREE", "")
    rec = DATA / "records" / slice_id
    try:
        frozen = json.loads((rec / "frozen.json").read_text())
    except (OSError, ValueError):
        print(json.dumps({"decision": "block", "reason": "No frozen record for slice " + slice_id +
                          ": the slice was not started by slice_start.py. Stop and say so in one line."}))
        return 0

    try:
        slot = json.loads((rec / "state.json").read_text()).get("slot")
    except (OSError, ValueError):
        slot = None
    red_file = rec / "red_stops"
    reds = int(red_file.read_text()) if red_file.exists() else 0

    problems = []
    dirty = [ln for ln in git(["status", "--porcelain"], wt).splitlines()
             if not ln[3:].startswith(("OspreyFlow_Core/osprey.yaml", "OspreyFlow_Core/data/"))]
    if dirty:
        problems.append("RED: uncommitted changes (commit them to the slice branch):\n" + "\n".join(dirty[:20]))
    results = []
    for name in ("checks", "acceptance"):
        cmd = frozen.get(name) or ""
        if not cmd:
            continue
        code, out = run(cmd, wt, slot)
        results.append({"name": name, "command": cmd, "exit": code})
        if code != 0:
            problems.append("RED: " + name + " (exit " + str(code) + "): " + cmd + "\n" + failures_only(out))

    # the pure tests that scan what the slice touched (scan_map.tsv, the line's): run as part of the checks
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import scan_select
        scans = scan_select.not_named(scan_select.select(scan_select.touched(wt, frozen.get("base") or "main"),
                                                         scan_select.entries()),
                                      frozen.get("checks") or "", frozen.get("acceptance") or "")
    except Exception as e:  # fail closed: a slice's checks are never run without the scans the line requires
        scans = None
        problems.append("RED: the line's scan map could not be read or applied (" + type(e).__name__ + ": " + str(e) +
                        "); the owner reinstalls the line (install.sh). Stop and say so in one line.")
    if scans:
        cmd = scan_select.command(wt, scans)
        code, out = run(cmd, wt, slot)
        results.append({"name": "scans", "command": cmd, "exit": code, "tests": scans})
        if code != 0:
            problems.append("RED: scans (exit " + str(code) + "): the pure tests that walk the files this slice "
                            "touches (scan_map.tsv): " + ", ".join(scans) + "\n" + failures_only(out))

    sha = git(["rev-parse", "HEAD"], wt)
    if not problems:
        record = {"slice": slice_id, "commit": sha, "green": True, "run": "stop-" + uuid.uuid4().hex[:12],
                  "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "results": results,
                  "session": event.get("session_id", "")}
        tmp = rec / ("tests-" + sha + ".json.tmp")
        tmp.write_text(json.dumps(record, indent=1))
        os.replace(tmp, rec / ("tests-" + sha + ".json"))
        red_file.write_text("0")
        return 0

    reds += 1
    red_file.write_text(str(reds))
    if reds >= MAX_RED:
        (rec / "red_stop.json").write_text(json.dumps({"slice": slice_id, "commit": sha, "red_stops": reds,
                                                       "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                                       "last": problems}, indent=1))
        return 0  # let it end: run_seat.py records the slice as stopped on red, never as verifying
    print(json.dumps({"decision": "block", "reason": "The slice's checks are red, so you cannot finish yet "
                      "(attempt " + str(reds) + " of " + str(MAX_RED) + "). Fix these and try again:\n\n" +
                      "\n\n".join(problems)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
