#!/usr/bin/env python3
"""The only writer to main (process/lanes/v062/slice-line/README.md, "The merge script").

    merge_slice.py merge <slice>                 one verified slice branch onto main, then the push step
    merge_slice.py records -m "<msg>" <path>...  the conductor's records, OspreyFlow_Build/process/lanes/v062/ only

`merge` refuses unless every one of these holds, in this order, and stops at the first that does not:
  1. no other merge is running (a lock), and the main checkout is on main with nothing uncommitted; and main's
     latest completed GitHub run is green (a failed one, a cancelled one with nothing newer, or one gh cannot read
     refuses: F2);
  2. the slice was started (its frozen record exists) and main's backlog row still matches what was frozen;
  3. a verifier's pass record exists for the branch's exact tip commit, from a session that did not build it; or,
     in its place and for that exact tip only, the owner's acceptance (resume.py accept: accepted-<tip>.json, its
     use logged in owner-changes.tsv) of that same verifier's findings record for the tip, unchanged;
  4. the branch touches no protected path (the owner's files, the never-staged files, the line itself);
  5. the acceptance test was red before the slice (the base, with the slice's acceptance files) ...
  6. ... and is green, with the slice's checks, on the merge result;
  7. today's full gate is green on the merge result (FULL_GATE: make -k ci and make test in the merge tree's own
     environment, built as CI builds it, never the main checkout's; then the live step: the live files the change
     itself reaches (live_select --reached), when there are any, on the test server through stack_lease.sh, once
     the server's run queue is clear, or not at all while the owner's live_step.yaml has it off).
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

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
import owed as owed_tests  # noqa: E402
import scan_select  # noqa: E402

#: The owner's files in the records folder: no slice changes them and records mode never commits them.
OWNER_FILES = (f"{c.V062_REL}/dial.yaml", f"{c.V062_REL}/accounts.yaml", f"{c.V062_REL}/live_step.yaml",
               f"{c.V062_REL}/resume.tsv", f"{c.V062_REL}/standing.tsv")
#: A slice's scan rows, waiting on main for its merge (1b): the conductor's records, never a slice's branch.
SCAN_ROWS_REL = f"{c.V062_REL}/scan_rows"
LINE_MAP_REL = "OspreyFlow_Build/scripts/slice_line/scan_map.tsv"
PROTECTED_PREFIXES = (
    "OspreyFlow_Core/Makefile", ".github/", "OspreyFlow_Core/osprey.yaml", "OspreyFlow_Core/data/", ".claude/",
    "OspreyFlow_Build/scripts/slice_line/", *OWNER_FILES, SCAN_ROWS_REL + "/",
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


def slice_env(tree: Path, log: Path, slot: int | str | None = None, venv: Path | None = None) -> dict:
    """The environment a slice's frozen commands run in, built as CI's `test` job builds it (F4, F6), so a command
    need not carry its own `uv run` or `npm ci`: a venv from the lock on CI's Python (`uv sync --frozen`; into `venv`,
    outside the tree, when given, else the tree's own OspreyFlow_Core/.venv), first on PATH; `npm ci` under CI's Node
    in the tree; closed ports; and the slice's Playwright slot (F8). A tree with no Python project or no Node lock
    gets none of that part. A command's own `export OSPREY_PORTS_SLOT=` or UV_PROJECT_ENVIRONMENT= still wins."""
    core = tree / "OspreyFlow_Core"
    env = {k: v for k, v in os.environ.items() if k not in SCRUBBED and not k.startswith("npm_config_")}
    path = [p for p in env.get("PATH", "").split(os.pathsep) if p and not p.rstrip("/").endswith("/.venv/bin")]
    env.update(OFFLINE_PORTS)
    if slot not in (None, ""):
        env["OSPREY_PORTS_SLOT"] = str(slot)
    if (core / "pyproject.toml").is_file():
        py = ci_python(tree)
        uv = shutil.which("uv", path=os.pathsep.join([*path, str(Path.home() / ".local/bin")]))
        if not uv:
            raise GateEnvError("uv is not installed (CI's setup-uv): the slice's environment cannot be built.")
        target = venv or core / ".venv"
        env["UV_PYTHON"] = py
        if venv:
            env["UV_PROJECT_ENVIRONMENT"] = str(venv)
        if run([uv, "sync", "--frozen"], core, log, env={**env, "PATH": os.pathsep.join(path)}) != 0:
            raise GateEnvError("building the slice's environment failed at: uv sync --frozen")
        env["VIRTUAL_ENV"] = str(target)
        path.insert(0, str(target / "bin"))
    if (core / "package-lock.json").is_file():
        nd = node_dir(ci_node_major(tree), os.pathsep.join(path))
        path.insert(0, str(nd))
        if run([str(nd / "npm"), "ci", "--no-audit", "--no-fund"], core, log, env={**env, "PATH": os.pathsep.join(path)}) != 0:
            raise GateEnvError("building the slice's environment failed at: npm ci")
    env["PATH"] = os.pathsep.join(path)
    return env


def drop_env(tree: Path) -> None:
    """What slice_env put in a merge tree, removed, so the full gate builds its own, fresh (ci_env refuses either)."""
    for name in ("node_modules", ".venv"):
        shutil.rmtree(tree / "OspreyFlow_Core" / name, ignore_errors=True)


#: The client names' hashed list (OspreyFlow_Build/marketing_site/client_hashes.py), gitignored, kept on this Mac only
#: (the owner's ruling, 12 November 2026). The merge tree is a fresh checkout without it, so the gate copies it in
#: from the main checkout, after the merge commit is made and only where the tree's own rules keep it out of git; a
#: merge is refused without it (the owner, 18 November 2026, for BL6's client-name check).
CLIENT_HASHES_REL = "OspreyFlow_Build/marketing_site/client_names.local.sha256"


def bring_client_hashes(tree: Path) -> None:
    src = c.REPO / CLIENT_HASHES_REL
    if not src.is_file() or not src.read_text().strip():
        raise GateEnvError(f"the client names' hashed list is missing from the main checkout ({src}): the gate checks "
                           "every page and record against it, so no merge without it. The owner makes it with "
                           "OspreyFlow_Build/marketing_site/client_hashes.py.")
    if subprocess.run(["git", "-C", str(tree), "check-ignore", "-q", CLIENT_HASHES_REL]).returncode != 0:
        raise GateEnvError(f"{CLIENT_HASHES_REL} is not ignored by git in the merge tree: the list is never committed, "
                           "so it is not copied in.")
    dest = tree / CLIENT_HASHES_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)


LIVE_STEP_FILE = c.REPO / c.V062_REL / "live_step.yaml"
QUEUE_POLL_SECONDS = 60


def live_step_setting() -> tuple[bool, int]:
    """The owner's live_step.yaml: whether the live step runs, and how long it waits for the server's queue.
    Missing, unreadable or not a plain true/false: the merge is refused, never guessed."""
    try:
        data = yaml.safe_load(LIVE_STEP_FILE.read_text())
    except (OSError, yaml.YAMLError) as e:
        raise GateEnvError(f"the owner's live step setting ({LIVE_STEP_FILE}) cannot be read: {e}")
    data = data if isinstance(data, dict) else {}
    on, wait = data.get("live_step"), data.get("queue_wait_minutes", 60)
    if not isinstance(on, bool) or not isinstance(wait, int) or isinstance(wait, bool) or wait < 0:
        raise GateEnvError(f"{LIVE_STEP_FILE} must say live_step: true or false, and queue_wait_minutes: a whole number.")
    return on, wait


def queue_hosts(tree: Path) -> list[str]:
    """Every host a test stack runs on (scripts/lane_stack_hosts.tsv): the queue is checked on each."""
    f = tree / "OspreyFlow_Build/scripts/lane_stack_hosts.tsv"
    rows = [ln.split("\t") for ln in (f.read_text().splitlines() if f.exists() else []) if ln and not ln.startswith("#")]
    return sorted({r[1].strip() for r in rows if len(r) >= 2 and r[1].strip()})


def queue_blocker(host: str) -> str | None:
    """Why the merger may not run on `host` now, or None: the queue (osprey-runs/QUEUE) is empty or has the merger
    first, and no make runs there. A host that cannot be read is a blocker, never taken as clear."""
    queue = f"{os.environ.get('OSPREY_REMOTE_ROOT', 'osprey-runs')}/QUEUE"
    p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", host,
                        f"head -n 1 {queue} 2>/dev/null; echo '<<end>>'; pgrep -x make || true"],
                       capture_output=True, text=True, check=False)
    if p.returncode != 0 or "<<end>>" not in p.stdout:
        return f"{host}: its run queue could not be read (ssh exit {p.returncode})"
    first, _, makes = p.stdout.partition("<<end>>")
    first = first.strip()
    if first not in ("", GATE_LANE):
        return f"{host}: the run queue has {first!r} first"
    if makes.strip():
        return f"{host}: make is running there (pids {' '.join(makes.split())})"
    return None


def wait_for_queue(tree: Path, wait_minutes: int, log: Path) -> str | None:
    """Wait until every stack host's queue is clear; the last blocker if `wait_minutes` pass first."""
    deadline = time.monotonic() + wait_minutes * 60
    while True:
        blockers = [b for h in queue_hosts(tree) if (b := queue_blocker(h))]
        if not blockers:
            return None
        log.open("a").write("\nWaiting for the server's run queue: " + "; ".join(blockers) + "\n")
        if time.monotonic() + QUEUE_POLL_SECONDS > deadline:
            return "; ".join(blockers)
        time.sleep(QUEUE_POLL_SECONDS)


def full_gate(tree: Path, base: str, log: Path) -> int:
    """Today's full gate on the merge result, in its own CI-built environment: make -k ci and make test, then the
    live step: the live files the change itself reaches, on the test server through the lease, as they need stores
    (live_step.yaml: off, or on after the server's run queue clears)."""
    lease = c.REPO / LEASE
    try:
        bring_client_hashes(tree)
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
    sel = subprocess.run([str(tree / "OspreyFlow_Core/.venv/bin/python"), "-m", "tools.live_select", "--base", base,
                          "--reached"],
                         cwd=str(tree / "OspreyFlow_Build"), capture_output=True, text=True, env=env)
    if sel.returncode != 0:
        log.open("a").write(sel.stdout + sel.stderr)
        return sel.returncode
    reached = sel.stdout.split()
    try:
        on, wait = live_step_setting()
    except GateEnvError as e:
        log.open("a").write(f"\nREFUSED: {e}\n")
        return 3
    owed, unreadable = owed_tests.outstanding(c.DATA) if on else ({}, [])
    if unreadable:
        log.open("a").write("\nREFUSED: what live tests are owed cannot be read: " + "; ".join(unreadable) + "\n")
        return 3
    owed_paths = sorted(set(owed) - set(reached))
    if not reached and not owed_paths:
        log.open("a").write("\nNo live test file is reached by this change: the live step takes no stack.\n")
        return 0
    if not on:
        log.open("a").write(f"\nLIVE STEP OFF (live_step.yaml): {len(reached)} live test files this change reaches "
                            "were not run:\n" + "".join(f"  {t}\n" for t in reached))
        c.write_json(log.with_suffix(".live.json"), {"live_step": "off", "not_run": reached})
        return 0
    blocked = wait_for_queue(tree, wait, log)
    if blocked:
        log.open("a").write(f"\nREFUSED: the server's run queue did not clear in {wait} minutes: {blocked}\n")
        return 4
    if owed_paths:
        log.open("a").write(f"\nThe live step also runs the {len(owed_paths)} live test files owed:\n"
                            + "".join(f"  {t}\n" for t in owed_paths))
    live = ["live", GATE_LANE, "--base", base, *(["--", *(f"../OspreyFlow_Build/{t}" for t in owed_paths)] if owed_paths else [])]
    steps = [["acquire", GATE_LANE, "slice merge live gate"], ["up", GATE_LANE], live]
    code = 0
    try:
        for s in steps:
            code = run([str(lease), *s], tree / "OspreyFlow_Build", log)
            if code != 0:
                break
    finally:
        run([str(lease), "down", GATE_LANE], tree / "OspreyFlow_Build", log)
        run([str(lease), "release", GATE_LANE], tree / "OspreyFlow_Build", log)
    if code == 0 and (owed_paths or reached):
        owed_tests.record_paid(sorted(set(owed_paths) | set(reached)), c.git(["rev-parse", "HEAD"], tree, check=False), log.name,
                                 c.DATA)
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


OWNERS_LOCAL = ("OspreyFlow_Core/osprey.yaml", *OWNER_FILES)


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
    return verifier_sessions(slice_id, tip, rec)


def verifier_sessions(slice_id: str, tip: str, rec: dict) -> dict:
    """The record names verifier sessions, none of which built the slice, each of whose transcripts names the tip."""
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


#: The owner's acceptance of a verifier's findings (resume.py accept), as owner-changes.tsv logs each use.
ACCEPT_ACTIONS = ("accept",)


def acceptance(slice_id: str, tip: str) -> dict | None:
    """The owner's acceptance for exactly this tip, or None when there is no acceptance record for it. Refused when
    one is there but does not stand: a record for another tip, no verifier findings record for the tip behind it, the
    findings not those the verifier returned, or no logged use of the owner's word for that slice and tip."""
    rec = c.rec_dir(slice_id)
    acc = c.read_json(rec / f"accepted-{tip}.json")
    if acc is None:
        return None
    if acc.get("tip") != tip or acc.get("slice") != slice_id:
        raise Refused(f"the acceptance record for {tip[:10]} names another tip or slice: it is for one tip only.")
    verify = c.read_json(rec / f"verify-{tip}.json")
    if not verify or verify.get("commit") != tip or verify.get("verdict") != "findings":
        raise Refused(f"the acceptance for {tip[:10]} has no verifier findings record for that tip behind it "
                      f"({(verify or {}).get('verdict', 'none')}): the owner accepts only what a verifier saw.")
    if verify.get("findings") != acc.get("findings") or not acc.get("findings"):
        raise Refused(f"the acceptance for {tip[:10]} does not hold the verifier's findings for that tip verbatim.")
    verifier_sessions(slice_id, tip, verify)
    if acc.get("by") == "standing":  # the owner's standing line is read again: still there, and still met
        import run_seat as rs
        rule, why = c.standing_rule()
        if not rule:
            raise Refused(f"the acceptance for {tip[:10]} was on the owner's standing word, which no longer holds: {why}.")
        legacy = rs.is_legacy(verify)
        if int(acc.get("round") or 0) < rule["from_round"] or \
                any(rs.kind_of(f, legacy) != rs.GAP for f in verify["findings"]):
            raise Refused(f"the standing acceptance for {tip[:10]} does not meet the owner's line ({rule['line']}): "
                          "round below it, or a finding that is not a gap in a test.")
    if not any(r["slice"] == slice_id and r["action"] in ACCEPT_ACTIONS and f"tip {tip}" in r["detail"]
               for r in c.owner_changes()):
        raise Refused(f"no use of an acceptance for {slice_id} at {tip[:10]} is logged in owner-changes.tsv: the "
                      "record was not written by resume.py.")
    return {**acc, "verifier": verify}


#: A failing test in the gate's log, as pytest, vitest and Playwright print it, and the lines that say why.
FAILED_TEST = re.compile(r"^(?:FAILED|ERROR) (\S+)|^\s*(?:FAIL|✘|×)\s+(\S+.*)$")
WHY_LINE = re.compile(r"^E\s{2,}\S|^\s*(?:Error|AssertionError|expect\()|^make(?:\[\d+\])?: \*\*\*|^make [\w -]+: exit [1-9]")
MAX_WHY = 12


#: A run's header in the merge log, as run() writes it, and the tree the red-before run is made in (temp_tree's
#: `slice-<ID>-before-*`): that run is meant to be red, so nothing it prints is a finding (1c: BL6's collection error).
RUN_HEADER = re.compile(r"^\$ .*\(in (\S+)\)\s*$")
RED_BEFORE_TREE = re.compile(r"/slice-[^/]+-before-[^/]+(?:/|$)")


def gate_part(log_text: str) -> list[str]:
    """The merge log's lines, less every run in the red-before tree (its expected red)."""
    out, skip = [], False
    for ln in log_text.splitlines():
        m = RUN_HEADER.match(ln)
        if m:
            skip = bool(RED_BEFORE_TREE.search(m.group(1)))
        if not skip:
            out.append(ln)
    return out


def gate_findings(log_text: str) -> tuple[list[str], list[dict]]:
    """The failing tests the gate's log names, and one finding each with its failing lines (not the whole log). The
    red-before run's output is left out: its red is the expected result. A log with nothing else gives none."""
    lines = gate_part(log_text)
    if not any(ln.strip() for ln in lines):
        return [], []
    names: list[str] = []
    for ln in lines:
        m = FAILED_TEST.match(ln)
        if m:
            name = (m.group(1) or m.group(2) or "").strip()
            if name and name not in names:
                names.append(name)
    findings = []
    for name in names:
        short = name.split("::")[-1]
        # pytest's section for this test: from its "___ name ___" header to the next header
        start = next((i for i, ln in enumerate(lines) if ln.startswith("_") and f" {short} " in ln), None)
        why = []
        if start is not None:
            for ln in lines[start + 1:]:
                if ln.startswith("_") and ln.endswith("_") or ln.startswith("="):
                    break
                if WHY_LINE.search(ln):
                    why.append(ln.strip())
        findings.append({"file": name.split("::")[0].lstrip("./").replace("../", ""),
                         "what": f"The merge gate's full run failed {name}: " + (" | ".join(why[:MAX_WHY]) or "see the log"),
                         "evidence": "the merge log's failing lines (a merge-*.log in this slice's records)"})
    if not findings:
        why = [ln.strip() for ln in lines if WHY_LINE.search(ln)][:MAX_WHY]
        findings.append({"file": "", "what": "The merge gate's full run was red: " + (" | ".join(why) or "see the log"),
                         "evidence": "the merge log (a merge-*.log in this slice's records)"})
    return names, findings


def refuse_to_builder(slice_id: str, tip: str, why: str, findings: list[dict], tests: int, refused_for: str) -> None:
    """Record the gate's refusal as findings the builder's prompt carries, and put the slice where the board shows it;
    resume.py send-back returns it to the builder."""
    c.write_json(c.rec_dir(slice_id) / f"verify-gate-{tip}.json",
                 {"slice": slice_id, "commit": tip, "verdict": "findings", "passes": [], "findings": findings,
                  "note": f"written by merge_slice.py: {why}; not a verifier session", "at": c.now()})
    c.set_state(slice_id, phase="refused", refused_for=refused_for, refused_tests=tests, refused_at=c.now(),
                note=f"refused by the gate: {tests} tests" if refused_for == "gate" else why)


def merge_conflicts(base: str, tip: str) -> list[str]:
    """The files the tip conflicts with main in, as git merge-tree names them; [] when it names none."""
    p = subprocess.run(["git", "merge-tree", "--write-tree", "--name-only", "--no-messages", base, tip], cwd=c.REPO,
                       capture_output=True, text=True)
    return [ln for ln in p.stdout.splitlines()[1:] if ln.strip()] if p.returncode == 1 else []


def records_only_conflict(base: str, tip: str) -> list[str]:
    """The files the tip conflicts with main in, when every one is in the records folder; [] otherwise."""
    files = merge_conflicts(base, tip)
    return files if files and all(f.startswith(c.V062_REL + "/") for f in files) else []


def apply_scan_rows(slice_id: str, tree: Path, base: str, tip: str) -> list[str]:
    """The slice's scan rows, applied in the merge commit, and the map checked for what the branch changes (1b).

    The rows wait on main in SCAN_ROWS_REL/<slice>.tsv (the conductor's records mode, from rows the verifier or the
    owner proposed; nothing in main's suite reads them, so main stays green while they wait). Each must only add: name a
    test file the branch adds, one with no row yet, with its prefixes or `-` and a why. They are appended to
    scan_map.tsv and the rows file removed, by amending the merge commit, so the map never names a test main lacks and
    the slice's tip is unchanged. Then, on the merge result: no test the branch adds or changes walks a folder with no
    row (scan_select.unmapped), and no row names a test the branch removes or a prefix that is not there (stale).
    Refused in words, not as the slice's fault; the full gate's own run of the line's suite checks the whole map."""
    build = tree / "OspreyFlow_Build"
    map_file = tree / LINE_MAP_REL
    table = scan_select.load(map_file.read_text())
    named = {t for t, _, _ in table}
    status = [ln.split("\t", 1) for ln in c.git(["diff", "--name-status", "--no-renames", f"{base}...{tip}"],
                                                  c.REPO).splitlines() if "\t" in ln]
    tests = {p[len("OspreyFlow_Build/"):]: s for s, p in status if p.startswith("OspreyFlow_Build/tests/")}
    rows_file = tree / SCAN_ROWS_REL / f"{slice_id}.tsv"
    shown = f"{SCAN_ROWS_REL}/{slice_id}.tsv"
    applied: list[str] = []
    if rows_file.is_file():
        lines = [ln for ln in rows_file.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
        try:
            rows = scan_select.load("\n".join(lines))
        except ValueError as e:
            raise Refused(f"{shown} cannot be read: {e}. Nothing changed.")
        for (t, _prefixes, why), ln in zip(rows, lines):
            if t in named:
                raise Refused(f"{shown} names {t}, which already has a row in scan_map.tsv: a recorded row only adds, "
                              "never edits or replaces one. Nothing changed.")
            if tests.get(t) != "A":
                raise Refused(f"{shown} names {t}, a test file the branch does not add: a row is only ever added with "
                              "the test it names, in the same merge. Nothing changed.")
            if not why.strip():
                raise Refused(f"{shown}: the row for {t} gives no why (its prefixes, or - and why it walks no folder "
                              "of the repository). Nothing changed.")
            applied.append(ln)
            named.add(t)
        table += rows
        text = map_file.read_text()
        map_file.write_text(text + ("" if text.endswith("\n") else "\n") + "".join(f"{ln}\n" for ln in applied))
        c.git(["add", "--", LINE_MAP_REL], tree)
        c.git(["rm", "-q", "--", f"{SCAN_ROWS_REL}/{slice_id}.tsv"], tree)
        c.git(["commit", "-q", "--amend", "--no-edit"], tree)
    scope = set(tests) | {t for t, _, _ in table if t in tests}
    missing = scan_select.unmapped(build, table, only={t for t, s in tests.items() if s != "D"})
    if missing:
        raise Refused("the merge result has pure tests that walk a folder with no row in scan_map.tsv: "
                      + ", ".join(missing) + f". The conductor records a row for each in {shown} (records mode; rows "
                      "the verifier or the owner proposed: the test, its prefixes or -, and why), and the merge applies "
                      "them. Nothing changed.")
    stale = [s for s in scan_select.stale(build, table) if s.split(":")[0] in scope]
    if stale:
        raise Refused("on the merge result, scan_map.tsv would name what is not there: " + "; ".join(stale)
                      + ". Nothing changed.")
    return applied


def merge(slice_id: str) -> dict:
    fh = lock()
    trees: list[Path] = []
    rec = c.rec_dir(slice_id)
    log = rec / f"merge-{uuid.uuid4().hex[:8]}.log"
    try:
        base = main_ready()
        ci = c.main_ci()  # F2: while main is red, every merge is refused (ADR-142 Amendment 9)
        if ci["state"] == "red":
            raise Refused(f"main is red: GitHub run {ci['run']} ({ci['why']}) {ci['url']}. No merge until a run on main "
                          "is green (RULINGS.md, GitHub failures: the conductor reruns a fault that is not ours).")
        if ci["state"] != "green":
            raise Refused(f"main's GitHub run cannot be read, so it is not taken as green: {ci['why']}.")
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
        accepted = acceptance(slice_id, tip)
        verify = accepted["verifier"] if accepted else verifier_pass(slice_id, tip)
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
        slot = c.state(slice_id).get("slot")
        envs = Path(tempfile.mkdtemp(prefix=f"slice-{slice_id}-envs-"))
        trees.append(envs)
        try:
            env_before = slice_env(before, log, slot, envs / "before")
        except GateEnvError as e:
            raise Refused(f"the acceptance run's environment could not be built: {e}. See {log}")
        if run(frozen["acceptance"], before, log, shell=True, env=env_before) == 0:
            raise Refused("the acceptance test passes without the slice's code: it was never red. See " + str(log))

        # 6. green on the merge result
        after = temp_tree(base, f"{slice_id}-merge")
        trees.append(after)
        msg = f"merge: slice {slice_id} ({frozen['build']}) {branch} {tip[:10]}\n\nSlice-Merge: {slice_id}\nSlice-Tip: {tip}"
        if subprocess.run(["git", "merge", "--no-ff", "-m", msg, tip], cwd=after, capture_output=True).returncode != 0:
            files = records_only_conflict(base, tip)
            if files:
                refuse_to_builder(slice_id, tip, "a merge conflict in the records folder alone", [{
                    "file": files[0], "what": "The branch conflicts with main only in the records folder (" +
                    ", ".join(files) + "): resume.py send-back merges main into it, taking main's records.",
                    "evidence": "git merge-tree on main and the tip"}], 0, "records")
                raise Refused(f"{branch} does not merge cleanly onto main, in the records folder alone ("
                              + ", ".join(files) + "): resume.py send-back merges main into it.")
            files = merge_conflicts(base, tip)
            if files:  # any other conflict: recorded, so send-back returns it to the builder (no round: 1a)
                named = ", ".join(files)
                refuse_to_builder(slice_id, tip, "a merge conflict with main", [{
                    "file": files[0],
                    "what": f"The branch conflicts with main in {named}. Your one task: merge main into this branch "
                            "(git merge main) and resolve each conflict keeping both sides of an append-only change "
                            "(both rows of a table, both entries of a list: main's first, then yours); change nothing "
                            "else, then run the checks and the acceptance command. A conflict that is not such an "
                            "append is not yours to settle alone: say so in your final message.",
                    "evidence": f"git merge-tree --write-tree --name-only on main and the tip names {named}"}],
                    0, "conflict")
                raise Refused(f"{branch} does not merge cleanly onto main: it conflicts with main in {named}. Recorded: "
                              f"resume.py {slice_id} send-back returns it to the builder to merge main in (no round "
                              "spent).")
            raise Refused(f"{branch} does not merge cleanly onto main, and git merge-tree names no conflicting file: not "
                          "recorded as the slice's fault, and the slice is left where it was; the conductor looks at the "
                          f"merge (a hook, a lock, the tree). See {log}")
        scan_rows = apply_scan_rows(slice_id, after, base, tip)  # 1b: in the merge commit itself
        merged = c.git(["rev-parse", "HEAD"], after)
        try:
            env_after = slice_env(after, log, slot, envs / "after")
        except GateEnvError as e:
            raise Refused(f"the merge result's environment could not be built: {e}. See {log}")
        for name in ("acceptance", "checks"):
            if frozen.get(name) and run(frozen[name], after, log, shell=True, env=env_after) != 0:
                raise Refused(f"the slice's {name} is red on the merge result. See {log}")
        # the pure tests that scan what the slice touched (scan_map.tsv), on the merge result
        scans = scan_select.not_named(scan_select.select(touched, scan_select.load((after / LINE_MAP_REL).read_text())),
                                      frozen.get("checks") or "", frozen.get("acceptance") or "")
        if scans and run(scan_select.command(after, scans, python=(
                str(Path(env_after["VIRTUAL_ENV"]) / "bin/python") if env_after.get("VIRTUAL_ENV") else "")), after, log, shell=True, env=env_after) != 0:
            names, findings = gate_findings(log.read_text(errors="replace"))
            refuse_to_builder(slice_id, tip, "the scans of the files it touches were red on the merge result", findings,
                              len(names), "gate")
            raise Refused("the pure tests that scan the files this slice touches are red on the merge result ("
                          + ", ".join(scans) + f"). See {log}")
        drop_env(after)  # the full gate builds its own, fresh

        # 7. today's full gate on the merge result
        if FULL_GATE(after, base, log) != 0:
            names, findings = gate_findings(log.read_text(errors="replace") if log.exists() else "")
            refuse_to_builder(slice_id, tip, "today's full gate was red on the merge result", findings, len(names), "gate")
            raise Refused(f"today's full gate is red on the merge result. See {log}")

        if c.git(["rev-parse", "HEAD"], c.REPO) != base:
            raise Refused("main moved while the merge was being tested.")
        c.git(["merge", "--ff-only", merged], c.REPO)
        done = {"slice": slice_id, "build": frozen["build"], "merge": merged, "tip": tip, "base": base,
                "acceptance_run": log.name, "gate_run": log.name, "verifier": verify.get("passes"), "at": c.now()}
        if scan_rows:
            done["scan_rows"] = scan_rows  # applied to scan_map.tsv in the merge commit, from SCAN_ROWS_REL
        live = c.read_json(log.with_suffix(".live.json"))
        if live:
            done["live_step"] = live  # off: the live files this change reaches, named, not run
        if accepted:  # merged narrower: what the verifier found and the owner accepted, for the conductor's report
            done["accepted_findings"] = {
                "count": len(accepted["findings"]), "findings": accepted["findings"],
                "faults_in_behaviour": accepted.get("faults_in_behaviour", []),
                "gaps_in_a_test": accepted.get("gaps_in_a_test", []), "no_kind": accepted.get("no_kind", []),
                "record": f"accepted-{tip}.json", "line": accepted.get("line"), "by": accepted.get("by"),
                "standing": accepted.get("by") == "standing", "rule": accepted.get("rule"),
                # each gap in a test, for the conductor to turn into a backlog row (the owner's order, 19 November)
                "backlog_rows": accepted.get("gaps_in_a_test", [])}
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
            shutil.rmtree(t, ignore_errors=True)
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
            if rel in OWNER_FILES:
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
