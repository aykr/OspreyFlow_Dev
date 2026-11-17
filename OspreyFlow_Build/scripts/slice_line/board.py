#!/usr/bin/env python3
"""The board (process/lanes/v062/slice-line/README.md, "The board"): computed, never kept by hand.

Prints each slice's state from the backlog file on main, the branches, the verifier's records and the test
results, then writes the progress dashboard's status file whole (a temporary name, then renamed). This is
the only writer of that file. It replaces the heartbeat.

    board.py            print the board and write status.js
    board.py --quiet    write status.js only (merge_slice.py and run_seat.py call this after each event)
    board.py --usage    usage per slice and per account, from usage.tsv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402

STATES = ("building", "verifying", "done", "stopped")


class BadEntry(Exception):
    pass


def entry(state: str, *, track: str = "", branch: str = "", note: str = "", evidence: str = "",
          account: str = "", merged: dict | None = None, verify: dict | None = None) -> dict:
    """One build's entry for status.js. Refuses an entry the dashboard must not show."""
    if state not in STATES:
        raise BadEntry(f"unknown state {state!r}")
    if state == "done":
        if not (merged and merged.get("merge") and merged.get("acceptance_run")):
            raise BadEntry("done needs the acceptance test green on main: no merge record with its test run")
        if not (verify and verify.get("verdict") == "pass" and verify.get("commit") == merged.get("tip")):
            raise BadEntry("done needs a verifier's pass record for the merged commit")
        if not evidence or merged["merge"][:7] not in evidence or merged["acceptance_run"] not in evidence:
            raise BadEntry("done needs evidence naming the commit and the test run")
    if state == "stopped" and not note:
        raise BadEntry("stopped needs, in note, the one decision the owner must make")
    return {"state": state, "track": track, "branch": branch, "note": note, "evidence": evidence, "account": account}


def branch_exists(b: str) -> bool:
    return bool(b) and bool(c.git(["branch", "--list", b], c.REPO, check=False))


def record(path: Path, problems: list[str], sid: str) -> dict | None:
    """One record file: a dict, or None when there is none. A file that is there but unreadable, or not a JSON
    object, is skipped and reported to the owner: one bad record never stops the board."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        problems.append(f"{sid}: record {path.name} is unreadable ({e}); skipped")
        return None
    if not isinstance(data, dict):
        problems.append(f"{sid}: record {path.name} is not a JSON object; skipped")
        return None
    return data


def compute(slices: list[dict]) -> tuple[list[dict], dict, list[str]]:
    rows, builds, problems = [], {}, []
    ids = c.plan_ids()
    for s in slices:
        try:
            one_slice(s, ids, rows, builds, problems)
        except Exception as e:  # noqa: BLE001 -- anything else one slice's records do: that slice reported, every other one shown
            sid = s.get("id", "?")
            problems.append(f"{sid}: its records could not be read ({type(e).__name__}: {e}); skipped, nothing written")
            rows.append({"slice": sid, "build": s.get("build", ""), "what": s.get("what", ""),
                         "state": "records unreadable", "from": "reported to the owner", "track": "", "account": ""})
    return rows, builds, problems


def one_slice(s: dict, ids: set, rows: list[dict], builds: dict, problems: list[str]) -> None:
    """One slice's row and status entry, from its records; a bad record is skipped and reported (record())."""
    sid, build = s["id"], s["build"]
    rec = c.rec_dir(sid)
    st = record(rec / "state.json", problems, sid) or {}
    frozen = record(rec / "frozen.json", problems, sid) or {}
    branch = frozen.get("branch") or s.get("branch") or f"lane/slice-{sid}"
    merged = record(rec / "merged.json", problems, sid)
    tip = c.git(["rev-parse", branch], c.REPO, check=False) if branch_exists(branch) else ""
    verify = record(rec / f"verify-{tip}.json", problems, sid) if tip else None
    tests = record(rec / f"tests-{tip}.json", problems, sid) if tip else None
    track = str(st.get("track") or s.get("track") or "")
    account = st.get("account", "")
    if not account and track:
        try:
            account = c.account_for("builder", track)
        except (OSError, KeyError, TypeError):
            account = ""
    kw = {"track": track, "branch": branch, "account": account}
    state, note, evidence, source = None, "", "", ""
    builds_entry = None
    if merged:
        verify_m = record(rec / f"verify-{merged.get('tip', '')}.json", problems, sid) if merged.get("tip") else None
        state = "done"
        evidence = f"commit {str(merged.get('merge', ''))[:7]} on main; test run {merged.get('acceptance_run', '')}"
        source = "merge record + verifier pass"
        try:
            builds_entry = entry("done", evidence=evidence, merged=merged, verify=verify_m, **kw)
        except BadEntry as e:
            # skipped and reported; the slice is shown from its other records, as if there were no merge record
            problems.append(f"{sid}: merge record skipped, not shown as done: {e}")
            state, evidence, source, builds_entry = None, "", "", None
    if state == "done":
        pass  # the merge record and the verifier's pass speak for it
    elif st.get("phase") == "stopped":
        state, note, source = "stopped", st.get("note", ""), "stop record"
    elif tip and verify and verify.get("verdict") == "pass":
        state, note, source = "verifying", "verifier passed; waiting for the merge script", "verifier record"
    elif tip and tests and tests.get("green"):
        state, note, source = "verifying", "checks green; verifier pending", "test record"
    elif branch_exists(branch) and (st or not frozen):
        state, source = "building", "branch exists, not green yet"
        if st.get("round", 1) > 1:
            note = f"round {st['round']} after the verifier's findings"
    if state and state != "done":
        try:
            builds_entry = entry(state, note=note, evidence=evidence, **kw)
        except BadEntry as e:
            problems.append(f"{sid}: {e}")
            builds_entry = None
    if state and build not in ids:
        problems.append(f"{sid}: build id {build or '(none)'} is not in the plan: reported to the owner, not written")
    elif state and builds_entry:
        builds[build] = builds_entry
    if state == "stopped":
        shown = f"stopped: {note[:60]}"
    elif state:
        shown = state
    else:
        waits = [d.strip() for d in (s.get("after") or "").split(",")
                 if d.strip() and not c.read_json(c.rec_dir(d.strip()) / "merged.json")]
        shown = f"waiting on {', '.join(waits)}" if waits else "ready"
        source = "backlog file's after column"
    rows.append({"slice": sid, "build": build, "what": s["what"], "state": shown,
                 "from": source, "track": kw["track"], "account": kw["account"]})


def write_status(builds: dict, path: Path | None = None) -> Path:
    path = path or c.STATUS_FILE
    main = c.git(["rev-parse", "--short", "main"], c.REPO)
    try:
        dial = c.current_setting()
    except Exception:
        dial = "not set"
    for k, v in builds.items():
        if v.get("state") not in STATES:
            raise BadEntry(f"{k}: unknown state")
    body = {"updated": c.now(), "main": main, "dial": dial, "builds": builds}
    text = ("// Written by OspreyFlow_Build/scripts/slice_line/board.py. Never edited by hand.\n"
            "// state is one of: \"building\", \"verifying\", \"done\", \"stopped\". A build not started is left out.\n"
            f"window.OSPREY_STATUS = {json.dumps(body, indent=2)};\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)
    return path


def usage() -> None:
    f = c.DATA / "usage.tsv"
    if not f.exists():
        print("No usage recorded yet.")
        return
    tot: dict = defaultdict(lambda: [0, 0, 0, 0, 0.0])
    for r in csv.DictReader(f.open(), delimiter="\t"):
        k = (r["slice"], r["account"], r["seat"])
        for i, col in enumerate(("input", "cache_create", "cache_read", "output")):
            tot[k][i] += int(r[col] or 0)
        tot[k][4] += float(r["cost_usd"] or 0)
    print(f"{'slice':8} {'account':8} {'seat':18} {'input':>9} {'cache+':>10} {'cache read':>11} {'output':>9} {'list $':>8}")
    for (s, a, seat), v in sorted(tot.items()):
        print(f"{s:8} {a:8} {seat:18} {v[0]:9d} {v[1]:10d} {v[2]:11d} {v[3]:9d} {v[4]:8.2f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--usage", action="store_true")
    ap.add_argument("--slices-from", default="main", help="a ref, or 'working' for the working copy")
    a = ap.parse_args()
    if a.usage:
        usage()
        return 0
    try:
        slices = c.load_slices(None if a.slices_from == "working" else a.slices_from)
    except RuntimeError:
        slices = []
    rows, builds, problems = compute(slices)
    path = write_status(builds)
    if not a.quiet:
        print(f"main {c.git(['rev-parse', '--short', 'main'], c.REPO)} · dial {c.current_setting()} · {c.now()}")
        print(f"{'slice':8} {'build':6} {'state':34} {'track':6} {'account':8} {'read from':30} what")
        for r in rows:
            print(f"{r['slice']:8} {r['build']:6} {r['state']:34} {r['track']:6} {r['account']:8} {r['from']:30} {r['what'][:60]}")
        for acct in sorted({r['account'] for r in rows if r['account']} | {"default", "sol"}):
            near, stop = c.near_limit(acct), c.account_stop(acct)
            if near or stop:
                print(f"account {acct}: " + (near or "") + (f"; stopped: {stop['error']} at {stop['at']}" if stop else ""))
        pending = c.DATA / "push.pending"
        if pending.exists():
            print(f"push pending: {pending.read_text().strip()[:10]} waits for main's CI run to finish")
        print(f"status file: {path}")
    for p in problems:
        print(f"REPORT TO OWNER: {p}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
