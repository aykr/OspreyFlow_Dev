#!/usr/bin/env python3
"""A builder cannot stop on red (process/lanes/v062/slice-line/README.md, "Gates").

The Stop hook for every session; it acts only for a builder seat (OSPREY_SEAT=builder, set by run_seat.py).
It runs only from the fixed place (~/.ospreyflow/slice-line/bin/stop_check.py), never a worktree's copy.

When the builder tries to finish, the slice's frozen checks and acceptance command run in its worktree.
Red: the stop is blocked and the builder gets the failure lines only, not the passes. Uncommitted work is
also red (what is not committed is not on the slice's branch). Green: a test record for the commit is
written for the board and the verifier, and the builder may stop. After MAX_RED blocked stops the builder
is let go, the slice is recorded as stopped on red, and it never shows as verifying or done.

Beside the frozen commands and the scans, the files the branch changed against its base meet CI's lint and the scan
map (LINE_FIXES_5_BRIEF.md, 4; SE7, PL4c and PL4d2 each lost a round or a merge to them at the pre-merge check):
`ruff check` and `ruff format --check` on OspreyFlow_Core's Python (where CI lints it, with Core's settings), eslint on
OspreyFlow_Core's and OspreyFlow_Build/tools' JavaScript and TypeScript (CI's `npm run lint` and `lint-tools`), and
every new test under OspreyFlow_Build/tests that walks a folder needs its row (scan_map.tsv, or the slice's rows
waiting on main in scan_rows/<ID>.tsv). Red there is red like any other: the same round, the finding sent back.
Standard library only; Python 3.9 compatible.
"""
from __future__ import annotations

import json
import os
import re
import shutil
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


def seat_env(cwd: str, slot=None) -> dict:
    """The environment the builder's frozen commands run in at Stop (slice_start.py proves the checks in the same)."""
    env = dict(os.environ)
    env.setdefault("ARCADEDB_HTTP_PORT", "9")  # a pure check never reaches a live store
    env.setdefault("POSTGRES_PORT", "9")
    if slot not in (None, ""):
        env["OSPREY_PORTS_SLOT"] = str(slot)  # the slice's own Playwright slot (slice_start.py), F8
    venv = Path(cwd) / "OspreyFlow_Core/.venv"
    if (venv / "bin/python").is_file():  # env: full built the worktree's own (F6): first on PATH
        env["VIRTUAL_ENV"] = str(venv)
        env["PATH"] = str(venv / "bin") + os.pathsep + env.get("PATH", "")
    return env


def run(cmd: str, cwd: str, slot=None) -> tuple:
    env = seat_env(cwd, slot)
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT_S, env=env)
        return p.returncode, (p.stdout or "") + "\n" + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "RED: timed out after " + str(TIMEOUT_S) + " s: " + cmd


def git(args: list, cwd: str) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return p.stdout.rstrip()


CORE = "OspreyFlow_Core/"
TOOLS = "OspreyFlow_Build/tools/"
JS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
SCAN_ROWS = "OspreyFlow_Build/process/lanes/v062/scan_rows/"


def tool(wt: str, env: dict, local: str, name: str):
    """The worktree's own copy of a tool (its venv's, its node_modules'), else the one on the seat's PATH, else None."""
    own = Path(wt) / local
    return str(own) if own.is_file() else shutil.which(name, path=env.get("PATH"))


def lint(wt: str, base: str, slice_id: str, slot=None) -> tuple:
    """(problems, results) of CI's lint and the scan-map check on the files the branch changed against its base."""
    env = seat_env(wt, slot)
    changed = [f for f in git(["diff", "--name-only", "--no-renames", "--diff-filter=AMR", base + "...HEAD"], wt).splitlines()
               if f.strip()]
    added = set(git(["diff", "--name-only", "--no-renames", "--diff-filter=A", base + "...HEAD"], wt).splitlines())
    problems, results = [], []

    def one(name, cmd, cwd, files, why):
        if not files:
            return
        if cmd[0] is None:  # fail closed: the builder installs it in its own worktree (both are gitignored)
            results.append({"name": name, "command": why, "exit": None, "files": files})
            problems.append("RED: " + name + ": " + why + " is not installed in the worktree or on PATH, and this branch "
                            "changes " + ", ".join(files[:5]) + ". Install it in your worktree (cd OspreyFlow_Core && "
                            + ("uv sync --frozen" if why.startswith("ruff") else "npm ci") + ") and stop again.")
            return
        try:
            q = subprocess.run([*cmd, *files], cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT_S, env=env)
            code, out = q.returncode, (q.stdout or "") + "\n" + (q.stderr or "")
        except subprocess.TimeoutExpired:
            code, out = 124, "timed out after " + str(TIMEOUT_S) + " s"
        results.append({"name": name, "command": " ".join(cmd), "exit": code, "files": files})
        if code != 0:
            lines = [ln for ln in out.splitlines() if ln.strip()]
            problems.append("RED: " + name + " (exit " + str(code) + ") on the files this branch changed: " +
                            " ".join(cmd) + "\n" + "\n".join(lines[:MAX_LINES]))

    core = str(Path(wt) / "OspreyFlow_Core")
    py = [f[len(CORE):] for f in changed if f.startswith(CORE) and f.endswith(".py")]
    ruff = tool(wt, env, CORE + ".venv/bin/ruff", "ruff")
    one("ruff check", [ruff, "check", "--force-exclude"], core, py, "ruff check")
    one("ruff format", [ruff, "format", "--check", "--force-exclude"], core, py, "ruff format --check")
    eslint = tool(wt, env, CORE + "node_modules/.bin/eslint", "eslint")
    one("eslint", [eslint], core, [f[len(CORE):] for f in changed if f.startswith(CORE) and f.endswith(JS)], "eslint")
    one("eslint (tools)", [eslint, "-c", str(Path(core) / "eslint.config.js")], str(Path(wt) / "OspreyFlow_Build"),
        [f[len("OspreyFlow_Build/"):] for f in changed if f.startswith(TOOLS) and f.endswith(JS)], "eslint")

    new = {f[len("OspreyFlow_Build/"):] for f in added
           if f.startswith("OspreyFlow_Build/tests/") and Path(f).name.startswith("test_") and f.endswith(".py")}
    if new:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import scan_select
        table = scan_select.entries()
        rows = subprocess.run(["git", "show", "main:" + SCAN_ROWS + slice_id + ".tsv"], cwd=wt, capture_output=True,
                              text=True)
        if rows.returncode == 0:
            table += scan_select.load(rows.stdout)
        missing = scan_select.unmapped(Path(wt) / "OspreyFlow_Build", table, only=new)
        results.append({"name": "scan map", "command": "scan_select.unmapped (new tests)", "exit": 1 if missing else 0,
                        "tests": sorted(new)})
        if missing:
            problems.append("RED: scan map: a new test walks a folder and has no row in scan_map.tsv (nor in "
                            + SCAN_ROWS + slice_id + ".tsv on main): " + ", ".join(missing) + ". Say so in one line "
                            "with the prefixes it walks: the verifier or the owner proposes its row, and the conductor "
                            "commits it in records mode; you cannot add it yourself.")
    return problems, results


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

    try:  # LINE_FIXES_5_BRIEF.md, 4: CI's lint and the scan map, on what the branch changed
        lp, lr = lint(wt, frozen.get("base") or "main", slice_id, slot)
        problems += lp
        results += lr
    except Exception as e:  # fail closed, as for the scans
        problems.append("RED: the lint and scan-map check could not run (" + type(e).__name__ + ": " + str(e) +
                        "); the owner reinstalls the line (install.sh). Stop and say so in one line.")

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
