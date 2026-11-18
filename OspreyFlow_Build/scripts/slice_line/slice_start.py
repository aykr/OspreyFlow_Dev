#!/usr/bin/env python3
"""Start one slice (process/lanes/v062/slice-line/README.md, "A slice's life").

    slice_start.py <slice>

Refuses a slice whose build id is not in the owner's plan (it is reported, not added), one waiting on a slice
not yet merged, one beyond the dial's builder count, one whose track's account is signed out, stopped, or
near its limit, and one whose frozen commands do not run (dry_run.py: on main, in a scratch worktree, the checks
reach the last step of their chain green and the acceptance is red for a reason no malformed command gives). Otherwise: the slice's worktree on its own branch from main, its acceptance and checks commands
frozen (a change needs the owner's word: refreeze.py), and its account, track, dial setting and rounds fixed
for the whole slice (an account changes only between slices).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
import dry_run  # noqa: E402
import merge_slice as ms  # noqa: E402


def running_builders() -> dict:
    out = {}
    if c.RECORDS.exists():
        for d in c.RECORDS.iterdir():
            st = c.read_json(d / "state.json") or {}
            if st.get("phase") in ("building", "verifying"):
                out[d.name] = st
    return out


def start(slice_id: str) -> dict:
    row = c.slice_row(slice_id)
    if row["build"] not in c.plan_ids():
        raise SystemExit(f"REPORT TO OWNER: slice {slice_id}'s build id {row['build'] or '(none)'} is not in the plan; "
                         "it is not started and not added to the status file.")
    if c.read_json(c.rec_dir(slice_id) / "frozen.json"):
        raise SystemExit(f"{slice_id} has already started: run_seat.py carries it on.")
    waits = [d.strip() for d in row["after"].split(",") if d.strip() and not c.read_json(c.rec_dir(d.strip()) / "merged.json")]
    if waits:
        raise SystemExit(f"{slice_id} waits on {', '.join(waits)}.")
    setting = c.current_setting()
    conf = c.seat_settings("builder", setting)
    busy = running_builders()
    if len(busy) >= conf["builders"]:
        raise SystemExit(f"The dial ({setting}) allows {conf['builders']} builder(s) at once; busy: {', '.join(busy)}.")
    track = row["track"] or next(str(t) for t in range(1, conf["builders"] + 1)
                                 if str(t) not in {s.get("track") for s in busy.values()})
    account = c.account_for("builder", track)
    verifier_account = c.account_for("verifier")
    for acct in {account, verifier_account}:
        stop = c.account_stop(acct)
        if stop:
            raise SystemExit(f"STOPPED: account {acct} stopped ({stop['error']} at {stop['at']}). Track {track} waits for "
                             "the owner: sign in again, or wait for the limit to reset.")
        near = c.near_limit(acct)
        if near:
            raise SystemExit(f"STOPPED: {near}: no new slice starts on it. The owner decides; work is not moved to another account.")
        if not c.signed_in(acct):
            raise SystemExit(f"STOPPED: account {acct} is signed out. The owner signs in to it; nothing is started.")

    log = c.DATA / "dry-runs" / f"{slice_id}-start-{c.now().replace(':', '')}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    slot = c.allocate_slot(slice_id)
    problems = dry_run.prove(row, slot=slot, log=log)
    if problems:
        raise SystemExit(f"NOT STARTED: {slice_id}'s frozen commands do not run as written, proved on main in a scratch "
                         "worktree (nothing was created):\n- " + "\n- ".join(problems) + f"\nThe whole run: {log}")

    branch = row["branch"] or f"lane/slice-{slice_id}"
    wt = c.WT_ROOT / f"slice-{slice_id}"
    base = c.git(["rev-parse", "main"], c.REPO)
    c.git(["worktree", "add", "-b", branch, str(wt), "main"], c.REPO)
    c.git(["update-index", "--skip-worktree", "OspreyFlow_Core/osprey.yaml"], wt, check=False)
    if row["env"] == "full":  # F6: the worktree's own environment, built as CI builds it (never lanes_launch.sh)
        try:
            ms.slice_env(wt, log, slot)
        except ms.GateEnvError as e:
            c.git(["worktree", "remove", "--force", str(wt)], c.REPO, check=False)
            c.git(["branch", "-D", branch], c.REPO, check=False)
            raise SystemExit(f"NOT STARTED: {slice_id}'s environment (env: full) could not be built: {e}. "
                             f"The worktree was removed. See {log}")
    rec = c.rec_dir(slice_id)
    frozen = {"slice": slice_id, "build": row["build"], "branch": branch, "worktree": str(wt), "base": base,
              **{k: row[k] for k in c.FROZEN_KEYS}, "frozen_at": c.now()}
    c.write_json(rec / "frozen.json", frozen)
    c.write_json(rec / "sessions.json", {"builder": [], "verifier": []})
    st = c.set_state(slice_id, phase="building", round=1, rounds_limit=conf["rounds"], setting=setting,
                     track=track, account=account, verifier_account=verifier_account, started=c.now(), slot=slot)
    subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "board.py"), "--quiet"])
    return {**frozen, **st}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: slice_start.py <slice>")
    s = start(sys.argv[1])
    print(f"Started {s['slice']} ({s['build']}) on {s['branch']} in {s['worktree']}: track {s['track']}, "
          f"account {s['account']}, dial {s['setting']}, rounds {s['rounds_limit']}, Playwright slot {s['slot']}.")
