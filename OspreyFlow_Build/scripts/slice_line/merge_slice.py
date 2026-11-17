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
  7. today's full gate is green on the merge result (FULL_GATE: make -k ci and make test in the merge tree's own
     environment, built as CI builds it, never the main checkout's; then the live files the change reaches, when
     there are any, on the test server through stack_lease.sh).
Then main is fast-forwarded to the tested merge commit (never anything untested), push_main.sh runs, and
board.py writes the board and the dashboard's status file. Nothing is changed on any refusal.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
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


def run(cmd: list[str] | str, cwd: Path, log: Path | None = None, shell: bool = False, env: dict | None = None) -> int:
    env = dict(os.environ if env is None else env)
    env.setdefault("ARCADEDB_HTTP_PORT", "9")
    env.setdefault("POSTGRES_PORT", "9")
    with (log.open("a") if log else open(os.devnull, "w")) as fh:
        fh.write(f"\n$ {cmd if isinstance(cmd, str) else ' '.join(cmd)}   (in {cwd})\n")
        fh.flush()
        return subprocess.run(cmd, cwd=str(cwd), shell=shell, stdout=fh, stderr=subprocess.STDOUT, env=env).returncode


#: The full gate's offline targets, both run on the merge result whatever the first one says: `make -k ci` (the
#: gates) and `make test` (the offline suite GitHub's `test` job runs; main went red on 17 November 2026 with
#: `make -k ci` alone green there, because the rollup test is only in `make test`).
FULL_GATE_TARGETS = (("make", "-k", "ci"), ("make", "test"))
#: Closed ports: an offline run reaches no store, and never the owner's deployment on 2480 (port guard).
OFFLINE_PORTS = {"ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "VALKEY_PORT": "59993",
                 "CLICKHOUSE_HTTP_PORT": "59994"}
#: What a caller's shell may carry that would point the gate at another environment (the main checkout's venv).
SCRUBBED = ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "PYTHONPATH", "PYTHONHOME", "CONDA_PREFIX", "CONDA_DEFAULT_ENV",
            "OSPREY_LANE", "OSPREY_PORTS_SLOT", "UV_PYTHON")


class GateEnvError(Exception):
    pass


def ci_node_major(tree: Path) -> str:
    """The Node major version CI's jobs set up (`node-version` in the tree's own ci.yml): exactly one."""
    text = (tree / ".github/workflows/ci.yml").read_text()
    majors = set(re.findall(r"node-version:\s*[\"']?(\d+)", text))
    if len(majors) != 1:
        raise GateEnvError(f"ci.yml names {len(majors)} Node versions ({', '.join(sorted(majors)) or 'none'}); "
                           "the gate needs exactly one to build its environment as CI does.")
    return majors.pop()


def ci_python(tree: Path) -> str:
    """The Python CI's jobs run (`UV_PYTHON` in the tree's own ci.yml): exactly one. Without it uv takes whichever
    Python it finds first; on the Mac that was 3.13 while CI runs 3.12 (the dry run, 17 November 2026)."""
    text = (tree / ".github/workflows/ci.yml").read_text()
    versions = set(re.findall(r"^\s*UV_PYTHON:\s*[\"']?([0-9][0-9.]*)", text, re.M))
    if len(versions) != 1:
        raise GateEnvError(f"ci.yml sets UV_PYTHON {len(versions)} ways ({', '.join(sorted(versions)) or 'none'}); "
                           "the gate needs exactly one to build its environment as CI does.")
    return versions.pop()


def node_dir(major: str, path: str) -> Path:
    """A bin folder whose `node` is CI's major: the line's own (~/.ospreyflow/slice-line/node/v<major>/bin), then PATH."""
    for d in [c.DATA / "node" / f"v{major}" / "bin", *map(Path, path.split(os.pathsep))]:
        node = d / "node"
        if node.is_file() and os.access(node, os.X_OK):
            v = subprocess.run([str(node), "--version"], capture_output=True, text=True, check=False).stdout.strip()
            if v.startswith(f"v{major}."):
                return d
    raise GateEnvError(f"no Node {major} (CI's) is installed: put one at {c.DATA / 'node' / f'v{major}'} "
                       f"(its bin/node), or on PATH. The gate does not run on another major.")


def lane_slot(tree: Path, lane: str) -> str:
    for ln in (tree / "OspreyFlow_Build/scripts/lane_ports.tsv").read_text().splitlines():
        parts = ln.split("\t")
        if not ln.startswith("#") and len(parts) >= 2 and parts[0] == lane:
            return parts[1].strip()
    raise GateEnvError(f"lane_ports.tsv gives the {lane} lane no Playwright slot.")


def ci_env(tree: Path, log: Path) -> dict:
    """The merge tree's own environment, built as GitHub's `test` job builds it, never the main checkout's.

    A fresh venv from the lock on CI's Python (`UV_PYTHON` from ci.yml; `uv sync --frozen`, no extras: the Mac's usual --all-extras venv carries spaCy,
    which no-langchain-check refuses), `npm ci` from the lock under CI's Node major, and a shell with nothing
    pointing elsewhere: no VIRTUAL_ENV, no other `.venv/bin` on PATH, the closed ports, the merger's slot.
    """
    core = tree / "OspreyFlow_Core"
    if (core / ".venv").exists() or (core / "node_modules").exists():
        raise GateEnvError(f"{core} already has a .venv or node_modules: the gate builds its own, fresh.")
    env = {k: v for k, v in os.environ.items() if k not in SCRUBBED and not k.startswith("npm_config_")}
    keep = [p for p in env.get("PATH", "").split(os.pathsep) if p and not p.rstrip("/").endswith("/.venv/bin")]
    nd = node_dir(ci_node_major(tree), os.pathsep.join(keep))
    env["PATH"] = os.pathsep.join([str(nd), *keep, str(Path.home() / ".local/bin")])
    py = ci_python(tree)
    env.update(OFFLINE_PORTS, OSPREY_PORTS_SLOT=lane_slot(tree, GATE_LANE), UV_PYTHON=py)
    uv = shutil.which("uv", path=env["PATH"])
    if not uv:
        raise GateEnvError("uv is not installed (CI's setup-uv): the gate cannot build its venv.")
    for cmd in ([uv, "sync", "--frozen"], [str(nd / "npm"), "ci", "--no-audit", "--no-fund"]):
        if run(cmd, core, log, env=env) != 0:
            raise GateEnvError(f"building the gate's environment failed at: {' '.join(cmd[1:3])}")
    venv_py = core / ".venv/bin/python"
    if not venv_py.is_file():
        raise GateEnvError("uv sync made no .venv in the merge tree.")
    said = subprocess.run([str(venv_py), "--version"], capture_output=True, text=True, check=False, env=env)
    if not (said.stdout + said.stderr).strip().startswith(f"Python {py}."):
        raise GateEnvError(f"the gate's venv runs {(said.stdout + said.stderr).strip() or 'nothing'}, not CI's "
                           f"Python {py}.")
    return env


def full_gate(tree: Path, base: str, log: Path) -> int:
    """Today's full gate on the merge result, in its own CI-built environment: make -k ci and make test, then the
    live files the change reaches (on the test server through the lease, as they need stores)."""
    lease = c.REPO / LEASE
    try:
        env = ci_env(tree, log)
    except GateEnvError as e:
        log.open("a").write(f"\nREFUSED: the gate's environment: {e}\n")
        return 3
    codes = []
    for target in FULL_GATE_TARGETS:
        started = time.monotonic()
        codes.append(run(list(target), tree / "OspreyFlow_Build", log, env=env))
        log.open("a").write(f"\n{' '.join(target)}: exit {codes[-1]} in {time.monotonic() - started:.0f} s\n")
    if any(codes):
        return next(x for x in codes if x)
    sel = subprocess.run([str(tree / "OspreyFlow_Core/.venv/bin/python"), "-m", "tools.live_select", "--base", base],
                         cwd=str(tree / "OspreyFlow_Build"), capture_output=True, text=True, env=env)
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
