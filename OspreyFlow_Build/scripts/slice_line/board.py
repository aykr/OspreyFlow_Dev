#!/usr/bin/env python3
"""The board (process/lanes/v062/slice-line/README.md, "The board"): computed, never kept by hand.

Prints each slice's state from the backlog file on main, the branches, the verifier's records and the test
results, then writes the progress dashboard's status file whole (a temporary name, then renamed). This is
the only writer of that file. It replaces the heartbeat.

    board.py            print the board and write status.js
    board.py --quiet    write status.js only (merge_slice.py and run_seat.py call this after each event)
    board.py --usage    usage per slice and per account, from usage.tsv
    board.py --self-clears   every stop the line cleared itself (self-clears.tsv), for the conductor's morning report
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
import owed as owed_tests  # noqa: E402

STATES = ("building", "verifying", "done", "stopped")


class BadEntry(Exception):
    pass


def entry(state: str, *, track: str = "", branch: str = "", note: str = "", evidence: str = "",
          account: str = "", merged: dict | None = None, verify: dict | None = None,
          accepted: dict | None = None, owner_line: dict | None = None, progress: dict | None = None) -> dict:
    """One build's entry for status.js. Refuses an entry the dashboard must not show."""
    if state not in STATES:
        raise BadEntry(f"unknown state {state!r}")
    if state == "done":
        if not (merged and merged.get("merge") and merged.get("acceptance_run")):
            raise BadEntry("done needs the acceptance test green on main: no merge record with its test run")
        if accepted_narrower(merged, verify, accepted):
            pass  # the owner's acceptance of the verifier's findings for that tip stands in for the pass
        elif not (verify and verify.get("verdict") == "pass" and verify.get("commit") == merged.get("tip")):
            raise BadEntry("done needs a verifier's pass record for the merged commit, or the owner's acceptance of "
                           "its findings")
        if not evidence or merged["merge"][:7] not in evidence or merged["acceptance_run"] not in evidence:
            raise BadEntry("done needs evidence naming the commit and the test run")
    if state == "stopped" and not note:
        raise BadEntry("stopped needs, in note, the one decision the owner must make")
    out = {"state": state, "track": track, "branch": branch, "note": note, "evidence": evidence, "account": account}
    if state == "done" and accepted_narrower(merged, verify, accepted):
        out["accepted_findings"] = merged["accepted_findings"]["findings"]
    if owner_line and state == "stopped":
        out["owner_line"] = owner_line  # the owner has answered; the conductor has not applied it yet (7)
    if progress:
        out["progress"] = progress  # a merge running, stalled or stopped without a result (MERGE_PROGRESS_BRIEF.md)
    return out


#: A running merge whose log has not grown for this long, its process alive, is shown "stalled" (seconds).
STALL_SECONDS = 600


def merge_progress(rec: Path) -> dict | None:
    """The slice's merge progress for status.js, from records/<ID>/merge-progress.json while it says running: the step,
    "n of m", the seconds in the step and in the merge, the estimate left (None: no estimate), and its state: running,
    stalled (the log not grown for STALL_SECONDS, the process alive) or "no process" (the record says running and its
    process is gone, or no merge holds the lock: the merge stopped without a result). None when no merge is running."""
    r = c.read_json(rec / "merge-progress.json")
    if not isinstance(r, dict) or r.get("state") != "running" or not isinstance(r.get("step"), dict):
        return None
    import calendar
    import time
    import merge_slice
    st, now = r["step"], time.time()

    def ago(stamp):
        try:
            return now - calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))
        except (TypeError, ValueError):
            return None
    alive = isinstance(r.get("pid"), int) and c.pid_alive(r["pid"]) and merge_slice.merging() is not None
    quiet = ago((r.get("log") or {}).get("mtime"))
    stall = float(os.environ.get("OSPREY_STALL_SECONDS") or STALL_SECONDS)
    state = "no process" if not alive else ("stalled" if quiet is not None and quiet >= stall else "running")
    step_s, merge_s = ago(st.get("began")), ago(r.get("started"))
    out = {"state": state, "merge_id": r.get("merge_id"), "step": st.get("name"), "part": st.get("part") or "",
           "n_of": f"{st.get('n')} of {st.get('of')}", "step_seconds": round(step_s or 0),
           "merge_seconds": round(merge_s or 0), "estimate_left_s": r.get("estimate_left_s")}
    where = f"step {out['n_of']}, {out['step']}" + (f" ({out['part']})" if out["part"] else "")
    if state == "no process":
        out["said"] = f"merge stopped without a result ({where})"
    else:
        left = r.get("estimate_left_s")
        out["said"] = (f"merging: {where}, {round(out['merge_seconds'] / 60)} minutes in, "
                       + (f"about {max(round(left / 60), 1)} left" if isinstance(left, (int, float)) else "no estimate")
                       + (f"; stalled: the log has not grown for {round(quiet / 60)} minutes" if state == "stalled" else ""))
    return out


#: The owner's actions that answer each kind of stop (resume.py's): a line for another action is not shown as the answer,
#: since resume.py will refuse it (LINE_FIXES_5_BRIEF.md, 7). move-seat and undo-seat-failure answer any stop.
ANSWERS = {"red": ("clear-stop", "refreeze"), "findings": ("add-round", "accept", "refreeze"),
           "refused": ("add-round", "refreeze"), "other": ()}
ANY_STOP = ("move-seat", "undo-seat-failure")


def owners_line(sid: str, st: dict, rec: Path, lines: list[dict]) -> dict | None:
    """The owner's unapplied line in resume.tsv that answers this slice's stop, or None."""
    if st.get("phase") == "refused":
        kind = "refused"
    elif st.get("phase") != "stopped":
        return None
    elif (rec / "red_stop.json").exists():
        kind = "red"
    elif st.get("round", 1) >= st.get("rounds_limit", 1):
        kind = "findings"
    else:
        kind = "other"
    for ln in lines:
        if ln["slice"] == sid and (ln["action"] in ANSWERS[kind] or ln["action"] in ANY_STOP):
            return {"action": " ".join([ln["action"], *ln["args"]]), "date": ln["date"], "line": ln["text"]}
    return None


def accepted_narrower(merged: dict | None, verify: dict | None, accepted: dict | None) -> bool:
    """Merged on the owner's acceptance: the merge record names its findings, and the acceptance and the verifier's
    findings record are both for the merged tip."""
    tip = (merged or {}).get("tip")
    return bool(tip and (merged or {}).get("accepted_findings") and accepted and accepted.get("tip") == tip
                and verify and verify.get("verdict") == "findings" and verify.get("commit") == tip)


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
    try:
        lines = c.unapplied_lines()
    except OSError as e:
        lines = []
        problems.append(f"resume.tsv could not be read ({e}): no owner's line is shown as waiting")
    for s in slices:
        try:
            one_slice(s, ids, rows, builds, problems, lines)
        except Exception as e:  # noqa: BLE001 -- anything else one slice's records do: that slice reported, every other one shown
            sid = s.get("id", "?")
            problems.append(f"{sid}: its records could not be read ({type(e).__name__}: {e}); skipped, nothing written")
            rows.append({"slice": sid, "build": s.get("build", ""), "what": s.get("what", ""),
                         "state": "records unreadable", "from": "reported to the owner", "track": "", "account": ""})
    return rows, builds, problems


def one_slice(s: dict, ids: set, rows: list[dict], builds: dict, problems: list[str], lines: list[dict] = ()) -> None:
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
        accepted_m = record(rec / f"accepted-{merged.get('tip', '')}.json", problems, sid) if merged.get("tip") else None
        state = "done"
        evidence = f"commit {str(merged.get('merge', ''))[:7]} on main; test run {merged.get('acceptance_run', '')}"
        source = "merge record + verifier pass"
        if accepted_narrower(merged, verify_m, accepted_m):
            af = merged["accepted_findings"]
            note = f"merged, accepted narrower: {af.get('count', 0)} findings"
            if af.get("standing"):
                note += f" (standing accept: {len(af.get('backlog_rows') or [])} gaps in a test for the backlog)"
            source = "merge record + owner's acceptance"
        try:
            builds_entry = entry("done", note=note, evidence=evidence, merged=merged, verify=verify_m,
                                 accepted=accepted_m, **kw)
        except BadEntry as e:
            # skipped and reported; the slice is shown from its other records, as if there were no merge record
            problems.append(f"{sid}: merge record skipped, not shown as done: {e}")
            state, note, evidence, source, builds_entry = None, "", "", "", None
    if state == "done":
        pass  # the merge record and the verifier's pass speak for it
    elif st.get("phase") == "stopped":
        state, note, source = "stopped", st.get("note", ""), "stop record"
    elif st.get("phase") == "refused":  # the dashboard knows four states: a refused slice waits as a stopped one
        state, source = "stopped", "merge refusal"
        note = (f"refused by the gate: {st.get('refused_tests', 0)} tests" if st.get("refused_for") == "gate"
                else st.get("note") or "refused by the merge script") + "; resume.py send-back returns it to the builder"
    elif tip and verify and verify.get("verdict") == "pass":
        state, note, source = "verifying", "verifier passed; waiting for the merge script", "verifier record"
    elif tip and tests and tests.get("green"):
        state, note, source = "verifying", "checks green; verifier pending", "test record"
    elif branch_exists(branch) and (st or not frozen):
        state, source = "building", "branch exists, not green yet"
        if st.get("round", 1) > 1:
            note = f"round {st['round']} after the verifier's findings"
    sf = st.get("seat_failure")
    if isinstance(sf, dict) and state in ("building", "verifying"):  # a refused call: no verdict, never findings
        note = (f"seat failed: the {sf.get('seat')}'s call on {sf.get('account')} was refused "
                f"({str(sf.get('error', ''))[:80]}); the owner clears the account or moves the seat")
        source = "seat failure record"
    waiting = owners_line(sid, st, rec, list(lines)) if state else None  # a stopped or refused slice's alone
    if waiting:
        note = f"the owner's line is in: {waiting['action']} ({waiting['date']}), waiting to be applied"
        source = "resume.tsv (unapplied)"
    progress = merge_progress(rec) if state and state != "done" else None
    if progress:
        note = progress["said"]
        source = "merge progress record"
    if state and state != "done":
        try:
            builds_entry = entry(state, note=note, evidence=evidence, owner_line=waiting, progress=progress, **kw)
        except BadEntry as e:
            problems.append(f"{sid}: {e}")
            builds_entry = None
    if state and build not in ids:
        problems.append(f"{sid}: build id {build or '(none)'} is not in the plan: reported to the owner, not written")
    elif state and builds_entry:
        builds[build] = builds_entry
    if progress:
        shown = progress["said"][:60]
    elif waiting:
        shown = f"owner's line in: {waiting['action']}"[:60]
    elif st.get("phase") == "refused" and state == "stopped":
        shown = note.split(";")[0][:60]
    elif state == "stopped":
        shown = f"stopped: {note[:60]}"
    elif state == "done" and note:
        shown = note
    elif state and isinstance(sf, dict) and note.startswith("seat failed"):
        shown = f"{state}: seat failed on {sf.get('account')}"
    elif state:
        shown = state
    else:
        waits = [d.strip() for d in (s.get("after") or "").split(",")
                 if d.strip() and not c.read_json(c.rec_dir(d.strip()) / "merged.json")]
        shown = f"waiting on {', '.join(waits)}" if waits else "ready"
        source = "backlog file's after column"
    rows.append({"slice": sid, "build": build, "what": s["what"], "state": shown,
                 "from": source, "track": kw["track"], "account": kw["account"], "merged": state == "done"})


def slice_counts(rows: list[dict], ids: set) -> dict:
    """For each build of the plan with rows in the backlog file: how many of its slices have merged (shown done, from a
    merge record the board accepts) and how many are cut (its rows: a row added later raises it), and the two said as
    "M of N" (LINE_FIXES_5_BRIEF.md, C). A build with none merged says "0 of N"; it is never left out."""
    out: dict = {}
    for r in rows:
        if r["build"] not in ids:
            continue  # reported to the owner already, never written
        d = out.setdefault(r["build"], {"merged": 0, "cut": 0})
        d["cut"] += 1
        d["merged"] += 1 if r.get("merged") else 0
    for d in out.values():
        d["said"] = f"{d['merged']} of {d['cut']}"
    return out


def owed_list(problems: list[str]) -> list[dict]:
    """The live test files owed (owed.py): merged while the live step was off and not run since."""
    owed, unreadable = owed_tests.outstanding(c.DATA)
    problems.extend(f"live tests owed: {u}; what is owed may be more than shown" for u in unreadable)
    return [{"test": t, **o} for t, o in sorted(owed.items())]


#: The owner-approved diffs applied (merge_slice.py apply-approved; LINE_FIXES_5_BRIEF.md, 10), as committed on main.
APPLIED_REL = "OspreyFlow_Build/process/lanes/v062/approved/applied.tsv"


def applied_diffs() -> list[dict]:
    try:
        text = c.git(["show", f"main:{APPLIED_REL}"], c.REPO)
    except RuntimeError:
        return []
    rows = [ln.split("\t") for ln in text.splitlines()[1:] if ln.strip()]
    return [dict(zip(("date", "name", "hash8", "commit"), r)) for r in rows if len(r) >= 4]


def self_clear_lines(rows: list[dict] | None = None) -> list[str]:
    """Each stop the line cleared itself, one line each: the time, the slice, the stop, the cause, what it did."""
    return [f"cleared by the line: {r['slice']} ({r['stop']} stop, cause {r['cause']}) at {r['at']}: {r['what']}"
            for r in (c.self_clears() if rows is None else rows)]


def write_status(builds: dict, path: Path | None = None, owed: list[dict] | None = None, ci: dict | None = None,
                 counts: dict | None = None) -> Path:
    path = path or c.STATUS_FILE
    main = c.git(["rev-parse", "--short", "main"], c.REPO)
    try:
        dial = c.current_setting()
    except Exception:
        dial = "not set"
    for k, v in builds.items():
        if v.get("state") not in STATES:
            raise BadEntry(f"{k}: unknown state")
    counts = counts or {}
    builds = {k: {**v, **({"slices": counts[k]["said"], "slices_merged": counts[k]["merged"],
                           "slices_cut": counts[k]["cut"]} if k in counts else {})} for k, v in builds.items()}
    body = {"updated": c.now(), "main": main, "dial": dial, "builds": builds, "owed_live_tests": owed or [],
            "main_ci": ci or {"state": "unknown", "run": None, "url": "", "why": "not read"},
            "self_clears": c.self_clears(), "build_slices": counts, "approved_diffs": applied_diffs()}
    text = ("// Written by OspreyFlow_Build/scripts/slice_line/board.py. Never edited by hand.\n"
            "// state is one of: \"building\", \"verifying\", \"done\", \"stopped\". A build not started is left out.\n"
            f"window.OSPREY_STATUS = {json.dumps(body, indent=2)};\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)
    return path


def usage() -> None:
    """Usage per slice, account and seat, then totals per slice and per account with the account's windows beside them.
    cost_usd is Claude Code's own list-price figure for each session: an estimate, never a bill."""
    f = c.DATA / "usage.tsv"
    if not f.exists():
        print("No usage recorded yet.")
        return
    cols = ("input", "cache_create", "cache_read", "output")
    tot: dict = defaultdict(lambda: [0, 0, 0, 0, 0.0])
    per_slice: dict = defaultdict(lambda: [0, 0, 0, 0, 0.0])
    per_account: dict = defaultdict(lambda: [0, 0, 0, 0, 0.0])
    for r in csv.DictReader(f.open(), delimiter="\t"):
        for key, table in (((r["slice"], r["account"], r["seat"]), tot), (r["slice"], per_slice), (r["account"], per_account)):
            for i, col in enumerate(cols):
                table[key][i] += int(r[col] or 0)
            table[key][4] += float(r["cost_usd"] or 0)
    print("Usage. Cost is a list-price estimate, not a bill (Claude Code's own figure for each session).")
    head = f"{'input':>9} {'cache+':>10} {'cache read':>11} {'output':>9} {'list $':>8}"
    line = lambda v: f"{v[0]:9d} {v[1]:10d} {v[2]:11d} {v[3]:9d} {v[4]:8.2f}"
    print(f"\nper slice, account and seat\n{'slice':8} {'account':8} {'seat':20} {head}")
    for (s, a, seat), v in sorted(tot.items()):
        print(f"{s:8} {a:8} {seat:20} {line(v)}")
    print(f"\nper slice\n{'slice':8} {head}")
    for s, v in sorted(per_slice.items()):
        print(f"{s:8} {line(v)}")
    print(f"\nper account (windows as the account's last session reported them)\n{'account':8} {head}  windows")
    for a, v in sorted(per_account.items()):
        print(f"{a:8} {line(v)}  {windows_of(a)}")


def windows_of(account: str) -> str:
    wins = (c.account_state(account).get("windows") or {})
    out = []
    for name in ("five_hour", "seven_day"):
        info = wins.get(name) or {}
        shown = name.replace("_", "-")
        if info.get("utilization") is None:
            out.append(f"{shown}: not reported by its sessions' stream")
        else:
            out.append(f"{shown} {info['utilization']:.0%}")
    return "; ".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--usage", action="store_true")
    ap.add_argument("--self-clears", action="store_true")
    ap.add_argument("--slices-from", default="main", help="a ref, or 'working' for the working copy")
    a = ap.parse_args()
    if a.usage:
        usage()
        return 0
    if a.self_clears:
        print("\n".join(self_clear_lines()) or "The line has cleared no stop itself.")
        return 0
    try:  # the owner's word of 21 November 2026: a verified slice's conflict with main, seen before the merge
        import merge_slice
        conflicts = merge_slice.check_conflicts()
    except Exception as e:  # the look never stops the board; it says why
        conflicts = [f"the look for conflicts with main could not run ({type(e).__name__}: {e})"]
    try:
        slices = c.load_slices(None if a.slices_from == "working" else a.slices_from)
    except RuntimeError:
        slices = []
    rows, builds, problems = compute(slices)
    counts = slice_counts(rows, c.plan_ids())
    owed = owed_list(problems)
    ci = c.main_ci()
    path = write_status(builds, owed=owed, ci=ci, counts=counts)
    if not a.quiet:
        print(f"main {c.git(['rev-parse', '--short', 'main'], c.REPO)} · dial {c.current_setting()} · {c.now()}")
        for d in applied_diffs():  # for the top of the conductor's report to the owner (10)
            print(f"owner-approved diff applied: {d['name']} {d['hash8']} commit {d['commit'][:10]} ({d['date']})")
        if ci["state"] == "red":
            print(f"main is red: run {ci['run']} ({ci['why']}) {ci['url']}: not a gate; merges go on (a red run is "
                  "rerun once; a test of ours red twice stops them)")
        elif ci["state"] != "green":
            print(f"main's GitHub run cannot be read ({ci['why']}): not a gate; merges go on")
        if c.GITHUB_STOP.exists():
            print("merging stopped: " + c.github_stop_words(c.read_json(c.GITHUB_STOP)))
        for line in conflicts:
            print(line)
        print(f"{'slice':8} {'build':6} {'state':34} {'track':6} {'account':8} {'read from':30} what")
        for r in rows:
            print(f"{r['slice']:8} {r['build']:6} {r['state']:34} {r['track']:6} {r['account']:8} {r['from']:30} {r['what'][:60]}")
        print("slices merged of those cut, per build: " + ", ".join(f"{b} {d['said']}" for b, d in sorted(counts.items())))
        for acct in sorted({r['account'] for r in rows if r['account']} | {"default", "sol"}):
            near, stop = c.near_limit(acct), c.account_stop(acct)
            if near or stop:
                print(f"account {acct}: " + (near or "") + (f"; stopped: {stop['error']} at {stop['at']}" if stop else ""))
        if owed:
            print(f"live tests owed: {len(owed)} (merged with the live step off; a release is refused until each has run)")
            for o in owed:
                print(f"  {o['test']}   slice {o['slice']}, merge {o['merge'][:10]}")
        fixed = [r for r in c.owner_changes() if r["action"] == "correct-command"]
        for r in fixed:
            print(f"command corrected: {r['slice']} at {r['at']} ({r['detail'].split('command corrected: ', 1)[-1]})")
        for line in self_clear_lines():
            print(line)
        pending = c.DATA / "push.pending"
        if pending.exists():
            print(f"push pending ({pending.read_text().strip()[:10]}): waits for the run on main in progress; the "
                  "conductor runs merge_slice.py push-pending when it ends")
        print(f"status file: {path}")
    for p in problems:
        print(f"REPORT TO OWNER: {p}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
