#!/usr/bin/env python3
"""The only writer to main (process/lanes/v062/slice-line/README.md, "The merge script").

    merge_slice.py merge <slice>                 one verified slice branch onto main, then the push step
    merge_slice.py records -m "<msg>" <path>...  the conductor's records, OspreyFlow_Build/process/lanes/v062/ only

`merge` refuses unless every one of these holds, in this order, and stops at the first that does not:
  1. no other merge is running (a lock), and the main checkout is on main with nothing uncommitted;
  2. the slice was started (its frozen record exists) and main's backlog row still matches what was frozen;
  3. a verifier's pass record exists for the branch's exact tip commit, from a session that did not build it;
  4. the branch touches no protected path (the owner's files, the never-staged files, the line itself);
  5. the acceptance test was red before the slice (the base, with the slice's acceptance files) ...
  6. ... and is green, with the slice's checks, on the merge result;
  7. today's full gate is green on the merge result (FULL_GATE, on the test server through stack_lease.sh,
     and the live files the change reaches, when there are any).
Then main is fast-forwarded to the tested merge commit (never anything untested), push_main.sh runs, and
board.py writes the board and the dashboard's status file. Nothing is changed on any refusal.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402

PROTECTED_PREFIXES = (
    "OspreyFlow_Core/Makefile", ".github/", "OspreyFlow_Core/osprey.yaml", "OspreyFlow_Core/data/", ".claude/",
    "OspreyFlow_Build/scripts/slice_line/", f"{c.V062_REL}/dial.yaml", f"{c.V062_REL}/accounts.yaml",
)
LEASE = "OspreyFlow_Build/scripts/stack_lease.sh"
GATE_LANE = "merger"


class Refused(Exception):
    pass


def run(cmd: list[str] | str, cwd: Path, log: Path | None = None, shell: bool = False) -> int:
    env = dict(os.environ)
    env.setdefault("ARCADEDB_HTTP_PORT", "9")
    env.setdefault("POSTGRES_PORT", "9")
    with (log.open("a") if log else open(os.devnull, "w")) as fh:
        fh.write(f"\n$ {cmd if isinstance(cmd, str) else ' '.join(cmd)}   (in {cwd})\n")
        fh.flush()
        return subprocess.run(cmd, cwd=str(cwd), shell=shell, stdout=fh, stderr=subprocess.STDOUT, env=env).returncode


def full_gate(tree: Path, base: str, log: Path) -> int:
    """Today's full gate on the merge result: make -k ci on the test server, then the live files it reaches."""
    lease = c.REPO / LEASE
    code = run([str(lease), "offline", GATE_LANE, "--", "make", "-k", "ci"], tree / "OspreyFlow_Build", log)
    if code != 0:
        return code
    sel = subprocess.run([str(c.REPO / "OspreyFlow_Core/.venv/bin/python"), "-m", "tools.live_select", "--base", base],
                         cwd=str(tree / "OspreyFlow_Build"), capture_output=True, text=True)
    if sel.returncode != 0:
        log.open("a").write(sel.stdout + sel.stderr)
        return sel.returncode
    if not sel.stdout.strip():
        log.open("a").write("\nNo live test file is reached by this change.\n")
        return 0
    steps = [["acquire", GATE_LANE, "slice merge live gate"], ["up", GATE_LANE], ["live", GATE_LANE, "--base", base]]
    code = 0
    try:
        for s in steps:
            code = run([str(lease), *s], tree / "OspreyFlow_Build", log)
            if code != 0:
                break
    finally:
        run([str(lease), "down", GATE_LANE], tree / "OspreyFlow_Build", log)
        run([str(lease), "release", GATE_LANE], tree / "OspreyFlow_Build", log)
    return code


FULL_GATE = full_gate  # tests replace this with a stand-in; nothing else does


def lock():
    c.DATA.mkdir(parents=True, exist_ok=True)
    fh = (c.DATA / "merge.lock").open("w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise Refused("another merge is running: one branch at a time.")
    return fh


OWNERS_LOCAL = ("OspreyFlow_Core/osprey.yaml", f"{c.V062_REL}/dial.yaml", f"{c.V062_REL}/accounts.yaml")


def main_ready(records: bool = False) -> str:
    """main is checked out and clean, apart from the owner's own local files (and, in records mode, the records)."""
    if c.git(["rev-parse", "--abbrev-ref", "HEAD"], c.REPO) != "main":
        raise Refused(f"the main checkout ({c.REPO}) is not on main.")
    dirty = [ln for ln in c.git(["status", "--porcelain", "--untracked-files=no"], c.REPO).splitlines()
             if not ln[3:].startswith(OWNERS_LOCAL) and not (records and ln[3:].startswith(c.V062_REL + "/"))]
    if dirty:
        raise Refused("the main checkout has uncommitted changes: " + "; ".join(dirty[:5]))
    return c.git(["rev-parse", "HEAD"], c.REPO)


def temp_tree(ref: str, name: str) -> Path:
    d = Path(tempfile.mkdtemp(prefix=f"slice-{name}-"))
    shutil.rmtree(d)
    c.git(["worktree", "add", "--detach", str(d), ref], c.REPO)
    return d


def drop_tree(d: Path) -> None:
    c.git(["worktree", "remove", "--force", str(d)], c.REPO, check=False)


def verifier_pass(slice_id: str, tip: str) -> dict:
    rec = c.read_json(c.rec_dir(slice_id) / f"verify-{tip}.json")
    if not rec:
        raise Refused(f"no verifier record for {slice_id} at its tip {tip[:10]}: the verifier has not passed this commit.")
    if rec.get("commit") != tip or rec.get("verdict") != "pass":
        raise Refused(f"the verifier's record for {tip[:10]} is not a pass ({rec.get('verdict')}).")
    builders = set((c.read_json(c.rec_dir(slice_id) / "sessions.json") or {}).get("builder", []))
    passes = rec.get("passes") or []
    if not passes:
        raise Refused("the verifier's record names no verifier session.")
    for p in passes:
        sid = p.get("session", "")
        if not sid or sid in builders:
            raise Refused("the verifier's record names a session that built the slice, or none.")
        tp = Path(p.get("transcript") or "")
        if not tp.is_file() or tip not in tp.read_text(errors="ignore"):
            raise Refused(f"the verifier session {sid[:8]}'s transcript is missing or never names {tip[:10]}.")
    return rec


def merge(slice_id: str) -> dict:
    fh = lock()
    trees: list[Path] = []
    rec = c.rec_dir(slice_id)
    log = rec / f"merge-{uuid.uuid4().hex[:8]}.log"
    try:
        base = main_ready()
        frozen = c.read_json(rec / "frozen.json")
        if not frozen:
            raise Refused(f"{slice_id} was never started (no frozen record).")
        row = c.slice_row(slice_id)
        if not c.frozen_matches(frozen, row):
            raise Refused(f"main's backlog row for {slice_id} no longer matches its frozen acceptance and checks: "
                          "a change needs the owner's word (refreeze.py).")
        branch = frozen["branch"]
        tip = c.git(["rev-parse", branch], c.REPO)
        if subprocess.run(["git", "merge-base", "--is-ancestor", tip, base], cwd=c.REPO).returncode == 0:
            raise Refused(f"{branch} is already on main.")
        verify = verifier_pass(slice_id, tip)
        touched = c.git(["diff", "--name-only", f"{base}...{tip}"], c.REPO).splitlines()
        bad = [p for p in touched if p.startswith(PROTECTED_PREFIXES)]
        if bad:
            raise Refused("the branch touches protected paths: " + ", ".join(bad[:8]))

        # 5. red before the slice: the base, with only the slice's acceptance files from the tip
        before = temp_tree(base, f"{slice_id}-before")
        trees.append(before)
        files = [f for f in (frozen.get("acceptance_files") or "").split(",") if f.strip()]
        if not files:
            raise Refused("the slice names no acceptance files, so red-before cannot be shown.")
        for f in files:
            f = f.strip()
            dest = before / f
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(subprocess.run(["git", "show", f"{tip}:{f}"], cwd=c.REPO, capture_output=True, check=True).stdout)
        if run(frozen["acceptance"], before, log, shell=True) == 0:
            raise Refused("the acceptance test passes without the slice's code: it was never red. See " + str(log))

        # 6. green on the merge result
        after = temp_tree(base, f"{slice_id}-merge")
        trees.append(after)
        msg = f"merge: slice {slice_id} ({frozen['build']}) {branch} {tip[:10]}\n\nSlice-Merge: {slice_id}\nSlice-Tip: {tip}"
        if subprocess.run(["git", "merge", "--no-ff", "-m", msg, tip], cwd=after, capture_output=True).returncode != 0:
            raise Refused(f"{branch} does not merge cleanly onto main: the builder rebases it.")
        merged = c.git(["rev-parse", "HEAD"], after)
        for name in ("acceptance", "checks"):
            if frozen.get(name) and run(frozen[name], after, log, shell=True) != 0:
                raise Refused(f"the slice's {name} is red on the merge result. See {log}")

        # 7. today's full gate on the merge result
        if FULL_GATE(after, base, log) != 0:
            raise Refused(f"today's full gate is red on the merge result. See {log}")

        if c.git(["rev-parse", "HEAD"], c.REPO) != base:
            raise Refused("main moved while the merge was being tested.")
        c.git(["merge", "--ff-only", merged], c.REPO)
        done = {"slice": slice_id, "build": frozen["build"], "merge": merged, "tip": tip, "base": base,
                "acceptance_run": log.name, "gate_run": log.name, "verifier": verify.get("passes"), "at": c.now()}
        c.write_json(rec / "merged.json", done)
        c.set_state(slice_id, phase="merged", merge=merged)
        push = subprocess.run([str(Path(__file__).resolve().parent / "push_main.sh")], cwd=c.REPO,
                              capture_output=True, text=True)
        done["push"] = {"exit": push.returncode, "said": (push.stdout + push.stderr).strip()[-400:]}
        c.write_json(rec / "merged.json", done)
        return done
    except Refused:
        c.set_state(slice_id, last_merge_refusal=c.now())
        raise
    finally:
        for t in trees:
            drop_tree(t)
        fh.close()


def records(message: str, paths: list[str]) -> str:
    fh = lock()
    try:
        if not paths:
            raise Refused("name the record files to commit.")
        for p in paths:
            rel = os.path.relpath(os.path.abspath(p), c.REPO) if os.path.isabs(p) else p
            if not rel.startswith(c.V062_REL + "/") or ".." in rel:
                raise Refused(f"records mode commits only {c.V062_REL}/: not {rel}.")
            if rel in (f"{c.V062_REL}/dial.yaml", f"{c.V062_REL}/accounts.yaml"):
                raise Refused(f"{rel} is the owner's file: records mode never commits it.")
        main_ready(records=True)
        working = c.load_slices(None) if (c.REPO / c.SLICES_REL).exists() else []
        rows = {r["id"]: r for r in working}
        for d in c.RECORDS.glob("*/frozen.json") if c.RECORDS.exists() else []:
            fr = c.read_json(d) or {}
            if fr.get("slice") in rows and not c.frozen_matches(fr, rows[fr["slice"]]) and \
                    not (c.read_json(d.parent / "merged.json")):
                raise Refused(f"slices.tsv changes the frozen acceptance or checks of started slice {fr['slice']}: "
                              "that needs the owner's word (refreeze.py).")
        c.git(["add", "--", *paths], c.REPO)
        staged = c.git(["diff", "--cached", "--name-only"], c.REPO).splitlines()
        outside = [p for p in staged if not p.startswith(c.V062_REL + "/")]
        if outside:
            c.git(["reset", "-q", "--", *paths], c.REPO)
            raise Refused("something outside the records folder is staged: " + ", ".join(outside))
        if not staged:
            raise Refused("nothing to commit.")
        c.git(["commit", "-q", "-m", f"{message}\n\nSlice-Records: yes"], c.REPO)
        sha = c.git(["rev-parse", "HEAD"], c.REPO)
        subprocess.run([str(Path(__file__).resolve().parent / "push_main.sh")], cwd=c.REPO)
        return sha
    finally:
        fh.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("merge")
    m.add_argument("slice")
    r = sub.add_parser("records")
    r.add_argument("-m", "--message", required=True)
    r.add_argument("paths", nargs="+")
    a = ap.parse_args()
    try:
        if a.cmd == "merge":
            done = merge(a.slice)
            print(json.dumps(done, indent=1))
        else:
            print("Committed", records(a.message, a.paths))
    except Refused as e:
        print(f"Refused: {e}", file=sys.stderr)
        rc = 1
    else:
        rc = 0
    subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "board.py"), "--quiet"])
    return rc


if __name__ == "__main__":
    sys.exit(main())
