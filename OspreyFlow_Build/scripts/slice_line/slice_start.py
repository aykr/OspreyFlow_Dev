#!/usr/bin/env python3
"""Start one slice (process/lanes/v062/slice-line/README.md, "A slice's life").

    slice_start.py <slice>

Refuses a slice whose build id is not in the owner's plan (it is reported, not added), one waiting on a slice
not yet merged, one beyond the dial's builder count, one whose track's account is signed out, stopped, or
near its limit, and one whose frozen commands do not run (dry_run.py: on main, in a scratch worktree, the acceptance
is red for a reason no malformed command gives; then in the slice's own worktree, made as the builder will have it
(the rulings copy, the hashed client names, env: full's environment), every step of the checks is green with nothing
built, the slice's own new test files stood in: LINE_FIXES_5_BRIEF.md, B). A red there removes the worktree and the
branch and names the step and the failing tests. Otherwise: the slice's worktree on its own branch from main, its acceptance and checks commands
frozen (a change needs the owner's word: refreeze.py), and its account, track, dial setting and rounds fixed
for the whole slice (an account changes only between slices).
"""
from __future__ import annotations

import shutil
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


def bring_client_hashes(wt: Path) -> str:
    """F5: the client names' hashed list, from the main checkout into the worktree, only where git ignores it there
    (as the merge gate's bring_client_hashes); never committed. What happened, in words."""
    src = c.REPO / ms.CLIENT_HASHES_REL
    if not src.is_file() or not src.read_text().strip():
        return (f"The main checkout has no hashed client-name list ({ms.CLIENT_HASHES_REL}): the worktree has none, "
                "so a client-name check there says it did not run. The owner makes it with "
                "OspreyFlow_Build/marketing_site/client_hashes.py; the merge gate refuses without it.")
    if subprocess.run(["git", "-C", str(wt), "check-ignore", "-q", ms.CLIENT_HASHES_REL]).returncode != 0:
        return (f"The hashed client-name list was not copied: {ms.CLIENT_HASHES_REL} is not ignored by git in the "
                "worktree, and the list is never committed.")
    dest = wt / ms.CLIENT_HASHES_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    return "The hashed client-name list was copied into the worktree (ignored by git)."


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
    problems = dry_run.prove(row, slot=slot, log=log, checks=False)
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
    hashes = dry_run.builder_shaped(wt)[1]
    problems = dry_run.checks_in_tree(row, wt, slot, log)
    if not problems:  # the owner's file 005: the three project checks the full gate runs, from the start
        problems = dry_run.stop_check.project_checks(str(wt), slot)[0]
    left = [ln for ln in c.git(["status", "--porcelain"], wt).splitlines()
            if not ln[3:].startswith(("OspreyFlow_Core/osprey.yaml", "OspreyFlow_Core/data/"))]
    if not problems and left:
        problems = ["the checks leave files in the worktree that git does not ignore, which the Stop hook reads as "
                    "uncommitted work: " + "; ".join(left[:10])]
    if problems:
        c.git(["worktree", "remove", "--force", str(wt)], c.REPO, check=False)
        c.git(["branch", "-D", branch], c.REPO, check=False)
        raise SystemExit(f"NOT STARTED: {slice_id}'s checks cannot pass in its own worktree on main ({wt}, made as the "
                         "builder would have it; the worktree and the branch were removed, nothing was frozen):\n- "
                         + "\n- ".join(problems) + f"\nThe whole run: {log}")
    rec = c.rec_dir(slice_id)
    frozen = {"slice": slice_id, "build": row["build"], "branch": branch, "worktree": str(wt), "base": base,
              **{k: row[k] for k in c.FROZEN_KEYS}, "plant": c.plant_hash(c.plant_text(slice_id)), "frozen_at": c.now()}
    c.write_json(rec / "frozen.json", frozen)
    c.write_json(rec / "sessions.json", {"builder": [], "verifier": []})
    st = c.set_state(slice_id, phase="building", round=1, rounds_limit=conf["rounds"], setting=setting,
                     track=track, account=account, verifier_account=verifier_account, started=c.now(), slot=slot)
    subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "board.py"), "--quiet"])
    return {**frozen, **st, "hashes": hashes}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: slice_start.py <slice>")
    s = start(sys.argv[1])
    print(f"Started {s['slice']} ({s['build']}) on {s['branch']} in {s['worktree']}: track {s['track']}, "
          f"account {s['account']}, dial {s['setting']}, rounds {s['rounds_limit']}, Playwright slot {s['slot']}.")
    print(s["hashes"])
