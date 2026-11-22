#!/usr/bin/env python3
"""The only writer to main (process/lanes/v062/slice-line/README.md, "The merge script").

    merge_slice.py merge <slice>                 one verified slice branch onto main, then the push step
    merge_slice.py records -m "<msg>" <path>...  the conductor's records, OspreyFlow_Build/process/lanes/v062/ only
    merge_slice.py push-pending                  a push the push step deferred (push.pending), once no run on main is
                                                 in progress or queued (1b); the conductor runs it when a run ends
    merge_slice.py watch-github                  the latest red run on main read for its failing tests; one test of
                                                 ours red twice on a commit stops merging (1c); the conductor runs it

`merge` refuses unless every one of these holds, in this order, and stops at the first that does not:
  1. no other merge is running (a lock), and the main checkout is on main with nothing uncommitted; and no test of
     ours has failed twice on GitHub on one commit (watch-github, run first: github.stopped.json, until the owner's
     clear_github_stop.py). GitHub's last
     completed run on main is read and recorded (merged.json's github_at_merge) and said in one line, but it is a
     second opinion, not a gate: red, cancelled or unreadable, the merge goes on (the owner, 20 November 2026);
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
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
import owed as owed_tests  # noqa: E402
import server_gate  # noqa: E402
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


#: What the merge says beside its result (GitHub's last run, what watch-github found), printed by main() after the
#: result, so a refusal's stderr still starts with "Refused: ".
NOTES: list[str] = []


def note(text: str) -> None:
    NOTES.append(text)


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


class NetworkError(GateEnvError):
    pass


def own_pytest_base(env: dict, base: Path, log: Path) -> None:
    """pytest's temp base for this run of the merge alone (PYTEST_DEBUG_TEMPROOT), so another pytest on the Mac,
    which keeps only its newest few pytest-N folders under the shared base, cannot remove the merge's (1e: SE3, GG1,
    19 November 2026). The merge removes it with its trees."""
    base.mkdir(parents=True, exist_ok=True)
    env["PYTEST_DEBUG_TEMPROOT"] = str(base)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.open("a").write(f"\npytest's temp base: {base}\n")


def gate_pytest_base(tree: Path) -> Path:
    """The full gate's own pytest base: beside the merge tree (never inside it, where a scanner would walk it)."""
    return Path(str(tree).rstrip("/") + "-pytest")


#: A step that failed only because a registry or a download could not be reached (1d: SE3's opentofu-check,
#: registry.opentofu.org, TLS handshake timeout, 19 November 2026): OpenTofu's provider registry, Docker's pulls, npm's
#: and uv's downloads, as each prints it.
NETWORK = 5
NETWORK_SIGNS = re.compile(
    r"Failed to resolve provider packages|Failed to query available provider packages|could not connect to registry"
    r"|TLS handshake timeout|net/http: request canceled|i/o timeout|toomanyrequests|error pulling image"
    r"|failed to resolve reference|Error response from daemon: (?:Get|Head) \"https://|ETIMEDOUT|ECONNRESET|EAI_AGAIN"
    r"|ENOTFOUND|socket hang up|error sending request for url|Failed to download|Connection reset by peer"
    r"|Could not resolve host|Temporary failure in name resolution")
#: The make targets of `make -k ci` whose own work reaches a registry or pulls an image (OspreyFlow_Build/Makefile:
#: opentofu-check runs tofu init in a pulled image; chart-check pulls helm's). A failed target outside these is ours.
NETWORK_STEPS = ("opentofu-check", "chart-check")
MAKE_ERROR = re.compile(r"^make(?:\[\d+\])?: \*\*\* \[(?:[^\]]*?:\s*)?([\w./-]+)\] Error \d+")


def network_only(text: str, tests: bool = True) -> str | None:
    """The network line, when a step's own output says it failed only on a network step: a network signature, no
    failed test of ours (for a step that runs tests), and no failed make target but the network steps. Else None."""
    lines = gate_part(text)
    if tests and any(FAILED_TEST.match(ln) for ln in lines):
        return None
    if {m.group(1) for ln in lines if (m := MAKE_ERROR.match(ln))} - set(NETWORK_STEPS):
        return None
    hits = [ln.strip(" │") for ln in lines if NETWORK_SIGNS.search(ln)]
    return " | ".join(hits[:3]) or None


def run_step(name: str, cmd: list[str], cwd: Path, log: Path, env: dict, retries: list, tests: bool = True) -> int:
    """One step of the full gate, run once more (once) when it failed only on a network step; NETWORK when the retry
    failed so too. Never retried on a failed test. Each retry is said in the log and kept in `retries`."""
    def since(start: int) -> str:
        with log.open("rb") as fh:
            fh.seek(start)
            return fh.read().decode(errors="replace")
    start = log.stat().st_size if log.exists() else 0
    code = run(cmd, cwd, log, env=env)
    why = network_only(since(start), tests) if code != 0 else None
    if not why:
        return code
    log.open("a").write(f"\nRETRY: {name} failed only on a network step ({why}): it runs once more.\n")
    start = log.stat().st_size
    code = run(cmd, cwd, log, env=env)
    retries.append({"step": name, "why": why, "retry_exit": code})
    if code == 0:
        return 0
    again = network_only(since(start), tests)
    if again:
        log.open("a").write(f"\nNETWORK: {name} failed twice on a network step ({again}): not the slice's fault.\n")
        return NETWORK
    return code


def ci_env(tree: Path, log: Path, retries: list | None = None) -> dict:
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
    own_pytest_base(env, gate_pytest_base(tree), log)
    uv = shutil.which("uv", path=env["PATH"])
    if not uv:
        raise GateEnvError("uv is not installed (CI's setup-uv): the gate cannot build its venv.")
    for cmd in ([uv, "sync", "--frozen"], [str(nd / "npm"), "ci", "--no-audit", "--no-fund"]):
        code = run_step(f"{Path(cmd[0]).name} {' '.join(cmd[1:])}", cmd, core, log, env,
                        retries if retries is not None else [], tests=False)
        if code == NETWORK:
            raise NetworkError(f"building the gate's environment could not download, twice, at: {' '.join(cmd[1:3])}")
        if code != 0:
            raise GateEnvError(f"building the gate's environment failed at: {' '.join(cmd[1:3])}")
    venv_py = core / ".venv/bin/python"
    if not venv_py.is_file():
        raise GateEnvError("uv sync made no .venv in the merge tree.")
    said = subprocess.run([str(venv_py), "--version"], capture_output=True, text=True, check=False, env=env)
    if not (said.stdout + said.stderr).strip().startswith(f"Python {py}."):
        raise GateEnvError(f"the gate's venv runs {(said.stdout + said.stderr).strip() or 'nothing'}, not CI's "
                           f"Python {py}.")
    return env


def slice_env(tree: Path, log: Path, slot: int | str | None = None, venv: Path | None = None,
              pytest_base: Path | None = None) -> dict:
    """The environment a slice's frozen commands run in, built as CI's `test` job builds it (F4, F6), so a command
    need not carry its own `uv run` or `npm ci`: a venv from the lock on CI's Python (`uv sync --frozen`; into `venv`,
    outside the tree, when given, else the tree's own OspreyFlow_Core/.venv), first on PATH; `npm ci` under CI's Node
    in the tree; closed ports; and the slice's Playwright slot (F8). A tree with no Python project or no Node lock
    gets none of that part. A command's own `export OSPREY_PORTS_SLOT=` or UV_PROJECT_ENVIRONMENT= still wins.
    `pytest_base`: pytest's temp base of the merge's own (1e), outside the tree, removed by the merge."""
    core = tree / "OspreyFlow_Core"
    env = {k: v for k, v in os.environ.items() if k not in SCRUBBED and not k.startswith("npm_config_")}
    path = [p for p in env.get("PATH", "").split(os.pathsep) if p and not p.rstrip("/").endswith("/.venv/bin")]
    env.update(OFFLINE_PORTS)
    if pytest_base is not None:
        own_pytest_base(env, pytest_base, log)
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
    retries: list = []

    def said_retries() -> None:
        if retries:
            c.write_json(log.with_suffix(".retries.json"), retries)  # merge() names them in merged.json
    try:
        bring_client_hashes(tree)
        env = ci_env(tree, log, retries)
    except NetworkError as e:
        log.open("a").write(f"\nNETWORK: the gate's environment: {e}\n")
        said_retries()
        return NETWORK
    except GateEnvError as e:
        log.open("a").write(f"\nREFUSED: the gate's environment: {e}\n")
        return 3
    codes = []
    for target in FULL_GATE_TARGETS:
        started = time.monotonic()
        if PROGRESS:
            PROGRESS.part(" ".join(target))
        codes.append(run_step(" ".join(target), list(target), tree / "OspreyFlow_Build", log, env, retries))
        log.open("a").write(f"\n{' '.join(target)}: exit {codes[-1]} in {time.monotonic() - started:.0f} s\n")
        if codes[-1] == NETWORK:
            said_retries()
            return NETWORK
    said_retries()
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


#: Which slice the running merge is merging (LINE_FIXES_5_BRIEF.md, 2): written under the merge lock, removed with it.
#: resume.py lets an action on any other slice go on meanwhile.
RUNNING = "merge.running.json"


def merging() -> str | None:
    """The slice a running merge holds the lock for; None when no merge runs. A merge that runs but whose record cannot
    be read gives "?" (every slice is then taken as the merging one)."""
    fh = (c.DATA / "merge.lock").open("a")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return str((c.read_json(c.DATA / RUNNING) or {}).get("slice") or "?")
    else:
        fcntl.flock(fh, fcntl.LOCK_UN)
        return None
    finally:
        fh.close()


#: How often a wait for the merge lock looks again (seconds).
WAIT_POLL_SECONDS = 2


def lock_after_merge(minutes: float, doing: str):
    """The merge lock, waited for while a merge runs (LINE_FIXES_5_BRIEF.md, 2; the owner, 21 November 2026: a running
    merge blocked two decision commits). For what must land on a tree no merge is testing: an owner-approved diff
    changes files the gate reads, so it is never landed beneath a merge's tested result, but it no longer needs asking
    again: it waits, says so once, and goes on when the merge is done. Refused, nothing changed, after `minutes`."""
    end, said = time.time() + minutes * 60, False
    while True:
        try:
            return lock()
        except Refused:
            busy = (c.read_json(c.DATA / RUNNING) or {}).get("slice") or "?"
            if time.time() >= end:
                raise Refused(f"a merge ({busy}) is still running after {minutes:g} minutes: {doing} waits for it. "
                              "Nothing changed; run it again when the merge is done.") from None
            if not said:
                print(f"a merge ({busy}) is running: {doing} waits for it, then goes on.", file=sys.stderr, flush=True)
                said = True
            time.sleep(WAIT_POLL_SECONDS)


@contextlib.contextmanager
def records_lock():
    """Commits to the main checkout one at a time: a records commit, and a merge's landing (2). Waits; held seconds."""
    c.DATA.mkdir(parents=True, exist_ok=True)
    with (c.DATA / "records.lock").open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield


def land(slice_id: str, base: str, merged: str, tip: str, touched: list[str]) -> tuple[str, list[str]]:
    """What main is fast-forwarded to, and the commits that moved main under the gate (2). When main is still the base
    the gate tested: the tested merge commit. When records commits moved it (each a Slice-Records commit with one
    parent, together changing only files in the records folder that are not the merge's scan rows, the owner's files or
    a file the slice changed): the tested merge made again on the moved main, by git merge-tree with the base as the
    merge base, kept only when its tree differs from the tested one in exactly those files, each as main has it; its
    message names the merge commit tested. Anything else moving main refuses, as before: nothing tested is ever
    landed on a tree it was not tested on, and no records commit is lost (main keeps it; the merge waits)."""
    now = c.git(["rev-parse", "HEAD"], c.REPO)
    if now == base:
        return merged, []
    moved_words = f"main moved while the merge was being tested (from {base[:10]} to {now[:10]})"
    if subprocess.run(["git", "merge-base", "--is-ancestor", base, now], cwd=c.REPO).returncode != 0:
        raise Refused(f"{moved_words}, and not forward. Nothing landed; run the merge again.")
    commits = c.git(["rev-list", "--reverse", f"{base}..{now}"], c.REPO).split()
    for sha in commits:
        parents = c.git(["rev-list", "--parents", "-n", "1", sha], c.REPO).split()[1:]
        trailers = c.git(["log", "-1", "--format=%(trailers:only,unfold)", sha], c.REPO)
        if len(parents) != 1 or "Slice-Records: yes" not in trailers:
            raise Refused(f"{moved_words} by {sha[:10]}, which is not a records commit. Nothing landed; run the merge "
                          "again.")
    paths = sorted(c.git(["diff", "--name-only", "--no-renames", base, now], c.REPO).split())
    tested = [f for f in paths if not f.startswith(c.V062_REL + "/") or f.startswith(SCAN_ROWS_REL + "/")
              or f in OWNER_FILES or f in touched]
    if tested:
        raise Refused(f"{moved_words}, in a path the gate tested or the merge reads ({', '.join(tested[:5])}). "
                      "Nothing landed; run the merge again.")
    p = subprocess.run(["git", "merge-tree", "--write-tree", "--merge-base", base, merged, now], cwd=c.REPO,
                       capture_output=True, text=True)
    tree = p.stdout.split("\n", 1)[0].strip()
    if p.returncode != 0 or not tree:
        raise Refused(f"{moved_words}, and the records commits do not merge cleanly with the tested result. Nothing "
                      "landed; run the merge again.")
    differ = sorted(c.git(["diff", "--name-only", "--no-renames", merged, tree], c.REPO).split())
    same = all(c.git(["rev-parse", f"{tree}:{f}"], c.REPO, check=False) == c.git(["rev-parse", f"{now}:{f}"], c.REPO,
                                                                                    check=False) for f in paths)
    if differ != paths or not same:
        raise Refused(f"{moved_words}, and the tested result on the moved main differs from it in more than the records "
                      f"commits' files ({', '.join(differ[:5])}). Nothing landed; run the merge again.")
    msg = c.git(["log", "-1", "--format=%B", merged], c.REPO).rstrip() + f"\nSlice-Tested: {merged}"
    landed = c.git(["commit-tree", tree, "-p", now, "-p", tip, "-m", msg], c.REPO)
    return landed, commits


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


#: The early look for a conflict with main (the owner's word of 21 November 2026; LINE_FAULTS_2026-11-21.md, 8): for
#: each verified slice, the main commit and the tip it was last merged with in git merge-tree, and what that named.
CONFLICT_SEEN = "conflict-check.json"


def check_conflicts() -> list[str]:
    """Each verified slice merged with main in git merge-tree, read-only (it writes objects alone: no branch, ref, index
    or worktree), once for each pair of main and tip it has not seen. A conflict is recorded as the merge records one
    (refuse_to_builder: refused for `conflict`, or `records` when only the records folder conflicts), so resume.py
    send-back returns the slice with no round spent, and the board shows "verified, conflicts with main in <files>".
    Nothing while a merge runs (the next look after it sees the moved main) or a resume.py action holds the slice.
    What it found, in words."""
    try:
        held = lock()
    except Refused:
        return []
    said = []
    try:
        base = c.git(["rev-parse", "main"], c.REPO)
        seen_f = c.DATA / CONFLICT_SEEN
        seen = c.read_json(seen_f) or {}
        records = c.DATA / "records"
        for d in sorted(records.iterdir()) if records.is_dir() else []:
            sid = d.name
            st = c.read_json(d / "state.json") or {}
            tip = st.get("tip") or ""
            if st.get("phase") != "verified" or not tip or seen.get(sid, {}).get("main") == base and \
                    seen.get(sid, {}).get("tip") == tip:
                continue
            one = (c.DATA / "locks" / f"resume-{sid}.lock")
            one.parent.mkdir(parents=True, exist_ok=True)
            fh = one.open("w")
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fh.close()
                continue
            try:
                files = merge_conflicts(base, tip)
                seen[sid] = {"main": base, "tip": tip, "files": files}
                if files:
                    named = ", ".join(files)
                    kind = "records" if all(f.startswith(c.V062_REL + "/") for f in files) else "conflict"
                    what = (f"The branch conflicts with main only in the records folder ({named}): resume.py send-back "
                            "merges main into it, taking main's records." if kind == "records" else
                            f"The branch conflicts with main in {named}. Your one task: merge main into this branch "
                            "(git merge main) and resolve each conflict keeping both sides of an append-only change "
                            "(both rows of a table, both entries of a list: main's first, then yours); change nothing "
                            "else, then run the checks and the acceptance command. A conflict that is not such an "
                            "append is not yours to settle alone: say so in your final message.")
                    refuse_to_builder(sid, tip, f"verified, conflicts with main in {named}", [{
                        "file": files[0], "what": what,
                        "evidence": f"git merge-tree --write-tree --name-only on main {base[:10]} and the tip names "
                                    f"{named} (the line's look when a verifier passes and when main moves)"}], 0, kind)
                    said.append(f"{sid}: verified, conflicts with main in {named}: recorded; resume.py {sid} send-back "
                                "returns it to the builder (no round spent).")
            finally:
                fh.close()
        c.write_json(seen_f, seen)
    finally:
        held.close()
    return said


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


#: pytest's summary line for a failed test, as `gh run view --log-failed` gives it after GitHub's job, step and
#: timestamp (run 44681092481, 20 November 2026: `conformance<TAB><step><TAB>2026-11-20T06:26:58.8411472Z FAILED
#: ../OspreyFlow_Build/tests/ingest/test_typology_rules.py::test_an_alert_... - adapters...ArcadeDBError: ...`).
GH_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z ")
GH_FAILED = re.compile(r"^FAILED (.+?)(?: - .*)?$")
GH_LIST_FIELDS = "databaseId,attempt,conclusion,status,headSha,url,workflowName"


def failed_tests(log_failed: str) -> list[dict]:
    """The tests a run's failed log names, each with its job, once each, in the order printed. A job that failed on a
    download, the network or a runner prints no FAILED line, so it names no test."""
    out: list[dict] = []
    for ln in log_failed.splitlines():
        parts = ln.split("\t", 2)
        job, text = (parts[0], parts[2]) if len(parts) == 3 else ("", ln)
        m = GH_FAILED.match(GH_STAMP.sub("", text.strip(), count=1))
        if m and all(t["test"] != m.group(1).strip() for t in out):
            out.append({"test": m.group(1).strip(), "job": job})
    return out


def gh_json(args: list[str]):
    p = subprocess.run(["gh", *args], cwd=str(c.REPO), capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise ValueError(f"gh {' '.join(args[:2])} exit {p.returncode}: {(p.stderr or p.stdout).strip()[:200]}")
    return p.stdout


def attempt_tests(run: dict, attempt: int) -> list[dict]:
    """One completed attempt's failing tests, read once with gh and kept in records/github/<run>.json (a completed
    attempt never changes)."""
    f = c.GITHUB_RECORDS / f"{run['databaseId']}.json"
    rec = c.read_json(f) or {"run": run["databaseId"], "head": run.get("headSha"), "url": run.get("url"),
                              "workflow": run.get("workflowName"), "attempts": {}}
    have = rec["attempts"].get(str(attempt))
    if have is not None:
        return have["tests"]
    tests = failed_tests(gh_json(["run", "view", str(run["databaseId"]), "--attempt", str(attempt), "--log-failed"]))
    rec["attempts"][str(attempt)] = {"tests": tests, "read_at": c.now()}
    c.write_json(f, rec)
    return tests


def cleared_stops() -> set[str]:
    rows = c.GITHUB_CLEARS.read_text().splitlines()[1:] if c.GITHUB_CLEARS.exists() else []
    return {r.split("\t")[1] for r in rows if len(r.split("\t")) > 1}


def watch_github() -> str:
    """1c: the latest completed run on main, when red, read for its failing tests; the same test failing in it and in
    the attempt before it on the same commit (the run's previous attempt, or the previous run on that head) writes
    the stop (github.stopped.json). A first red, a red that passed on rerun, a different test, a failure with no FAILED
    line, a pair the owner already cleared, and gh unreadable write none. What it found, in one line; never raises."""
    try:
        runs = json.loads(gh_json(["run", "list", "--branch", "main", "--status", "completed", "--limit", "20",
                                   "--json", GH_LIST_FIELDS]))
        if not runs:
            return "watch-github: no run on main has completed: nothing to watch."
        last = runs[0]
        if last.get("conclusion") != "failure":
            return f"watch-github: run {last.get('databaseId')} on main is {last.get('conclusion')}: no stop."
        attempt = int(last.get("attempt") or 1)
        now = attempt_tests(last, attempt)
        if attempt > 1:
            prev, prev_attempt = last, attempt - 1
        else:
            prev = next((r for r in runs[1:] if r.get("headSha") == last.get("headSha")), None)
            prev_attempt = int(prev.get("attempt") or 1) if prev else 0
        if not prev:
            return (f"watch-github: run {last['databaseId']} is red, its first on {str(last.get('headSha'))[:10]} "
                    f"({len(now)} failing tests): recorded, no stop; a red run is rerun once.")
        before = {t["test"] for t in attempt_tests(prev, prev_attempt)}
        both = [t for t in now if t["test"] in before]
        if not both:
            return (f"watch-github: run {last['databaseId']} attempt {attempt} is red again on "
                    f"{str(last.get('headSha'))[:10]}, but no test failed in both ({len(now)} now, {len(before)} "
                    "before): no stop.")
        key = f"{last.get('headSha')}:{prev['databaseId']}/{prev_attempt}:{last['databaseId']}/{attempt}"
        stop = {"test": both[0]["test"], "tests": [t["test"] for t in both], "job": both[0]["job"],
                "commit": last.get("headSha"), "key": key, "at": c.now(),
                "runs": [{"run": prev["databaseId"], "attempt": prev_attempt, "url": prev.get("url")},
                         {"run": last["databaseId"], "attempt": attempt, "url": last.get("url")}]}
        if key in cleared_stops():
            return f"watch-github: {stop['test']} failed twice on {str(last.get('headSha'))[:10]}; the owner cleared it."
        if not c.GITHUB_STOP.exists():
            c.write_json(c.GITHUB_STOP, stop)
        return "watch-github: " + c.github_stop_words(c.read_json(c.GITHUB_STOP))
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as e:
        return f"watch-github: GitHub could not be read ({e}): nothing recorded, no stop."


def github_stop() -> None:
    """While the stop is there (a test of ours failed twice on GitHub), no merge, in words that say what and who."""
    if c.GITHUB_STOP.exists():
        raise Refused(c.github_stop_words(c.read_json(c.GITHUB_STOP)))


def github_at_merge() -> dict:
    """GitHub's last completed run on main, as common.main_ci() reads it, with the time: recorded in merged.json and
    said in one line, never a reason to refuse (the owner, 20 November 2026: merges go on the Mac's full gate alone,
    whatever GitHub's last run says; a run that cannot be read is no reason to hold a merge the gate passed)."""
    ci = {**c.main_ci(), "at": c.now()}
    shown = {"green": "green", "red": "red"}.get(ci["state"])
    said = f"{shown} (run {ci['run']})" if shown else f"cannot be read ({ci['why']})"
    note(f"GitHub's last run on main: {said}, not a gate; merging")
    return ci


#: The merge's progress record (MERGE_PROGRESS_BRIEF.md; the owner, 19 November 2026: "intermediate status outputs ...
#: to track progress in the dashboard"): records/<ID>/merge-progress.json, rewritten whole (beside it, then renamed) at
#: each step's start and end and every PROGRESS_SECONDS while one runs. Names, numbers and times only; never test output.
PROGRESS_FILE = "merge-progress.json"
PROGRESS_SECONDS = 30
STEPS = ("checks before the gate", "red before: the acceptance on the base", "the merge onto main",
         "the acceptance, checks and scans on the merge result", "today's full gate", "landing on main", "the push")
PROGRESS = None  # the running merge's Progress, for full_gate's parts


def progress_history(slice_id: str) -> tuple[dict, str]:
    """Seconds per step from this slice's previous attempt (its newest finished record), else the mean of the last
    three finished merges of any slice; ({}, "no estimate") when there is nothing to go on. Never invented."""
    def secs(f: Path) -> dict:
        r = c.read_json(f) or {}
        return {d["name"]: d["seconds"] for d in r.get("done") or [] if isinstance(d.get("seconds"), (int, float))}
    own = sorted(c.rec_dir(slice_id).glob("merge-progress-*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in own:
        if secs(f):
            return secs(f), "this slice's previous attempt"
    every = sorted((c.DATA / "records").glob("*/merge-progress-*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    runs = [x for x in (secs(f) for f in every) if x][:3]
    if not runs:
        return {}, "no estimate"
    names = {n for r in runs for n in r}
    return ({n: sum(r[n] for r in runs if n in r) / sum(1 for r in runs if n in r) for n in names},
            f"the last {len(runs)} merge(s) of any slice")


class Progress:
    """The record one merge writes as it goes. Best effort: a write that fails never fails or slows the merge, and says
    so once in the merge log."""

    def __init__(self, slice_id: str, log: Path):
        self.f = c.rec_dir(slice_id) / PROGRESS_FILE
        self.log = log
        self.t0 = time.time()
        self.step_t0 = self.t0
        self.said_failure = False
        self.mutex = threading.Lock()
        self.history, self.source = progress_history(slice_id)
        self.rec = {"slice": slice_id, "tip": "", "merge_id": log.stem, "pid": os.getpid(), "started": c.now(),
                    "state": "running", "result": None, "step": None, "done": [], "log": {"path": str(log)},
                    "estimate_left_s": None, "estimate_from": "no estimate"}
        self.board = None
        self.stop = threading.Event()
        self.beat = threading.Thread(target=self._beat, daemon=True)
        self.beat.start()

    def _beat(self) -> None:
        every = float(os.environ.get("OSPREY_PROGRESS_SECONDS") or PROGRESS_SECONDS)
        while not self.stop.wait(every):
            self.write()

    def _estimate(self) -> None:
        st = self.rec["step"]
        left = STEPS[st["n"] - 1:] if st else ()
        if not st or self.rec["state"] != "running" or any(n not in self.history for n in left):
            self.rec["estimate_left_s"], self.rec["estimate_from"] = None, "no estimate"
            return
        now_in = time.time() - self.step_t0
        self.rec["estimate_left_s"] = round(max(self.history[left[0]] - now_in, 0) + sum(self.history[n] for n in left[1:]))
        self.rec["estimate_from"] = self.source

    def write(self) -> None:
        with self.mutex:
            try:
                st = self.log.stat() if self.log.exists() else None
                self.rec["log"] = {"path": str(self.log), "size": st.st_size if st else 0,
                                   "mtime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)) if st else None}
                self._estimate()
                self.rec["updated"] = c.now()
                tmp = self.f.with_name(self.f.name + ".tmp")
                tmp.write_text(json.dumps(self.rec, indent=1))
                os.replace(tmp, self.f)
            except OSError as e:
                if not self.said_failure:
                    self.said_failure = True
                    try:
                        with self.log.open("a") as fh:
                            fh.write(f"\n(the progress record could not be written: {e}; the merge goes on without it)\n")
                    except OSError:
                        pass

    def _close_step(self, result: str) -> None:
        st = self.rec["step"]
        if st:
            self.rec["done"].append({"name": st["name"], "result": result, "seconds": round(time.time() - self.step_t0)})

    def _board(self) -> None:
        """board.py --quiet, so status.js carries the step: one at a time, and never waited for by a step."""
        try:
            if self.board and self.board.poll() is None:
                return
            self.board = subprocess.Popen([sys.executable, str(Path(__file__).resolve().parent / "board.py"), "--quiet"],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    def step(self, n: int) -> None:
        prev = self.rec["step"]
        self._close_step("red as expected" if prev and prev["n"] == 2 else "passed")
        self.step_t0 = time.time()
        self.rec["step"] = {"name": STEPS[n - 1], "n": n, "of": len(STEPS), "began": c.now(), "part": ""}
        self.write()
        self._board()

    def part(self, name: str) -> None:
        if self.rec["step"]:
            self.rec["step"]["part"] = name
            self.write()

    def finish(self, result: str, why: str = "") -> None:
        if self.rec["state"] != "running":
            return
        self._close_step("passed" if result == "merged" else "red")
        self.rec.update(state="finished", result=result, why=why[:300], finished=c.now())
        self.stop.set()
        self.write()
        try:  # kept beside it, for the next merge's estimate
            shutil.copyfile(self.f, self.f.with_name(f"merge-progress-{self.rec['merge_id'].removeprefix('merge-')}.json"))
        except OSError:
            pass
        if self.board:
            try:
                self.board.wait(timeout=30)
            except subprocess.TimeoutExpired:
                pass


def server_hold(slice_id: str) -> str | None:
    """Why the slice is not given the slot (server_gate.slot_hold), for its branch's tip; None when nothing holds it."""
    frozen = c.read_json(c.rec_dir(slice_id) / "frozen.json") or {}
    if not frozen.get("branch"):
        return None
    try:
        tip = c.git(["rev-parse", frozen["branch"]], c.REPO)
    except RuntimeError:
        return None
    return server_gate.slot_hold(slice_id, tip)


def rerun_named(tree: Path, log: Path, tests: list[str], targets: list[str]) -> int:
    """The demo server's named failures, rerun on the Mac in the gate's own environment (ci_env): the tests by
    make test's own pytest command (the Makefile's IN_CORE and PYTEST, through a second makefile beside the log, the
    Makefile itself unchanged), and a failing target with no test named by make -k. 0 when every one is green."""
    try:
        env = ci_env(tree, log)
    except (NetworkError, GateEnvError) as e:
        log.open("a").write(f"\nREFUSED: the rerun's environment: {e}\n")
        return 3
    codes = []
    if tests:
        mk = log.with_suffix(".mk")
        mk.write_text("server-rerun:\n\t$(IN_CORE) $(PYTEST) $(RERUN_TESTS)\n")
        codes.append(run_step("the server's failing tests, rerun", ["make", "-f", "Makefile", "-f", str(mk), "server-rerun",
                                                                    "RERUN_TESTS=" + " ".join(tests)],
                              tree / "OspreyFlow_Build", log, env, []))
    if targets:
        codes.append(run_step("the server's failing targets, rerun", ["make", "-k", *targets], tree / "OspreyFlow_Build",
                              log, env, [], tests=False))
    return next((x for x in codes if x), 0)


#: The Mac's rerun of a server's red; the line's tests stand it in, as they stand in FULL_GATE.
SERVER_RERUN = rerun_named


def server_rerun(slice_id: str) -> str:
    """merge_slice.py server-rerun <ID> (item 1): the server's named failures for the slice's tip, rerun on the Mac on
    the same candidate (main with the slice merged in). Green: recorded, and the slice queues as before. Red: recorded,
    and the slice goes back to its builder as a gate refusal, the failing names its findings."""
    rec = c.rec_dir(slice_id)
    frozen = c.read_json(rec / "frozen.json")
    if not frozen:
        raise Refused(f"{slice_id} was never started (no frozen record).")
    if c.state(slice_id).get("phase") != "verified":
        raise Refused(f"{slice_id} is not verified: a server result is read only for a verified slice.")
    tip = c.git(["rev-parse", frozen["branch"]], c.REPO)
    rid, e = server_gate.server_result(slice_id, tip)
    if not server_gate.is_red(e):
        raise Refused(f"no red result from the demo server for {slice_id} at {tip[:10]} (run {rid or 'none named'}): "
                      "nothing to rerun.")
    tests, bare = server_gate.failing_names(e)
    if not tests and not bare:
        raise Refused(f"the server's run {rid} names no failing test or target: nothing to rerun; the merge's whole gate "
                      "settles it.")
    base = c.git(["rev-parse", "main"], c.REPO)
    log = rec / f"server-rerun-{rid}.log"
    tree = temp_tree(base, f"{slice_id}-rerun")
    try:
        if subprocess.run(["git", "merge", "--no-ff", "-q", "-m", f"rerun {slice_id}", tip], cwd=tree,
                          capture_output=True).returncode != 0:
            raise Refused(f"{slice_id} does not merge cleanly onto main: the merge's conflict check settles it.")
        t0 = time.monotonic()
        code = SERVER_RERUN(tree, log, tests, bare)
        seconds = round(time.monotonic() - t0)
    finally:
        drop_tree(tree)
        shutil.rmtree(tree, ignore_errors=True)
    result = "green" if code == 0 else "red"
    c.write_json(server_gate.rerun_record(slice_id, rid), {
        "slice": slice_id, "tip": tip, "main": base, "run_id": rid, "result": result, "tests": tests, "targets": bare,
        "seconds": seconds, "log": log.name, "at": c.now()})
    named = ", ".join(tests + bare)
    if result == "green":
        return (f"{slice_id}: the server's red ({named}) is green on the Mac ({seconds} s): an environment difference, "
                f"recorded; it queues for the merge as before.")
    refuse_to_builder(slice_id, tip, "the demo server's red, rerun on the Mac, was red there too", [
        {"file": n.split("::")[0].replace("../", ""), "what": f"Rerun on the Mac after the demo server's run {rid}: {n} "
         "failed there too.", "evidence": f"the rerun's log ({log.name} in this slice's records)"} for n in tests + bare],
        len(tests), "gate")
    return (f"{slice_id}: the server's red ({named}) is red on the Mac too ({seconds} s): back to its builder "
            f"(resume.py {slice_id} send-back).")


def merge(slice_id: str) -> dict:
    held = server_hold(slice_id)  # the owner's word of 22 November 2026, item 1: a server red is rerun before the slot
    if held:
        raise Refused(held)
    fh = lock()
    c.write_json(c.DATA / RUNNING, {"slice": slice_id, "pid": os.getpid(), "at": c.now()})
    trees: list[Path] = []
    rec = c.rec_dir(slice_id)
    log = rec / f"merge-{uuid.uuid4().hex[:8]}.log"
    global PROGRESS
    prog = PROGRESS = Progress(slice_id, log)
    try:
        prog.step(1)
        base = main_ready(records=True)  # 9: the conductor's uncommitted records do not hold a merge (below)
        note(watch_github())  # 1c: a test of ours red twice stops merging
        github_stop()
        github = github_at_merge()  # a record, never a decision (1a: GitHub is a second opinion, not a gate)
        frozen = c.read_json(rec / "frozen.json")
        if not frozen:
            raise Refused(f"{slice_id} was never started (no frozen record).")
        row = c.slice_row(slice_id)
        if not c.frozen_matches(frozen, row):
            raise Refused(f"main's backlog row for {slice_id} no longer matches its frozen acceptance and checks: "
                          "a change needs the owner's word (refreeze.py).")
        branch = frozen["branch"]
        tip = c.git(["rev-parse", branch], c.REPO)
        prog.rec["tip"] = tip
        if subprocess.run(["git", "merge-base", "--is-ancestor", tip, base], cwd=c.REPO).returncode == 0:
            raise Refused(f"{branch} is already on main.")
        accepted = acceptance(slice_id, tip)
        verify = accepted["verifier"] if accepted else verifier_pass(slice_id, tip)
        touched = c.git(["diff", "--name-only", f"{base}...{tip}"], c.REPO).splitlines()
        bad = [p for p in touched if p.startswith(PROTECTED_PREFIXES)]
        if bad:
            raise Refused("the branch touches protected paths: " + ", ".join(bad[:8]))
        dirty = [ln[3:] for ln in c.git(["status", "--porcelain", "--untracked-files=no"], c.REPO).splitlines()
                 if not ln[3:].startswith(OWNERS_LOCAL)]
        both = sorted(set(dirty) & set(touched))
        if both:  # 9: main's fast-forward would meet them: commit them (records) first
            raise Refused("the main checkout has uncommitted changes to files the branch changes: " + ", ".join(both[:5])
                          + ". Commit them with merge_slice.py records (or set them aside), then merge.")

        # 5. red before the slice: the base, with only the slice's acceptance files from the tip
        prog.step(2)
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
            env_before = slice_env(before, log, slot, envs / "before", pytest_base=envs / "pytest-before")
        except GateEnvError as e:
            raise Refused(f"the acceptance run's environment could not be built: {e}. See {log}")
        if run(frozen["acceptance"], before, log, shell=True, env=env_before) == 0:
            raise Refused("the acceptance test passes without the slice's code: it was never red. See " + str(log))

        # 6. green on the merge result
        prog.step(3)
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
        prog.step(4)
        scan_rows = apply_scan_rows(slice_id, after, base, tip)  # 1b: in the merge commit itself
        merged = c.git(["rev-parse", "HEAD"], after)
        try:
            env_after = slice_env(after, log, slot, envs / "after", pytest_base=envs / "pytest-after")
        except GateEnvError as e:
            raise Refused(f"the merge result's environment could not be built: {e}. See {log}")
        for name in ("acceptance", "checks"):
            if frozen.get(name) and run(frozen[name], after, log, shell=True, env=env_after) != 0:
                # line fault 17 (the owner's file 008, SE6b): recorded for the builder, so send-back works, as a
                # refusal at the full gate and at the scans is; left at `verified`, no action could move the slice
                names, findings = gate_findings(log.read_text(errors="replace"))
                if not names:
                    findings = [{"file": "", "what": f"The slice's {name} command is red on the merge result (main with the "
                                 f"slice merged in), though green on the slice's own tip: {frozen[name][:200]}",
                                 "evidence": "the merge log (a merge-*.log in this slice's records)"}]
                refuse_to_builder(slice_id, tip, f"the slice's {name} was red on the merge result", findings, len(names),
                                  "gate")
                raise Refused(f"the slice's {name} is red on the merge result. Recorded: resume.py {slice_id} send-back "
                              f"returns it to the builder. See {log}")
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
        prog.step(5)
        code = FULL_GATE(after, base, log)
        retried = c.read_json(log.with_suffix(".retries.json"))
        if code == NETWORK:  # 1d: a registry or download unreachable twice: the slice's fault in nothing
            c.write_json(rec / f"refusal-network-{uuid.uuid4().hex[:8]}.json",
                         {"kind": "network", "slice": slice_id, "tip": tip, "merge_log": log.name, "retried": retried,
                          "note": "not a fault of the slice: no round, no finding", "at": c.now()})
            raise Refused("today's full gate could not reach a registry or a download, twice (network): not the slice's "
                          "fault, so no round and no finding to the builder. The conductor tells the owner and runs the "
                          f"merge again. See {log}")
        if code != 0:
            names, findings = gate_findings(log.read_text(errors="replace") if log.exists() else "")
            refuse_to_builder(slice_id, tip, "today's full gate was red on the merge result", findings, len(names), "gate")
            raise Refused(f"today's full gate is red on the merge result. See {log}")

        prog.step(6)
        with records_lock():  # no records commit between the check and the fast-forward
            landed, under = land(slice_id, base, merged, tip, touched)
            c.git(["merge", "--ff-only", landed], c.REPO)
        done = {"slice": slice_id, "build": frozen["build"], "merge": landed, "tip": tip, "base": base,
                "acceptance_run": log.name, "gate_run": log.name, "verifier": verify.get("passes"),
                "github_at_merge": github, "at": c.now()}
        if under:  # 2: records commits that moved main under the gate, landed beneath the tested result
            done.update(tested_merge=merged, landed_on=c.git(["rev-parse", f"{landed}^1"], c.REPO), records_under_gate=under)
        if retried:
            done["retried"] = retried  # 1d: steps run once more after a network failure, and green the second time
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
        c.set_state(slice_id, phase="merged", merge=landed)
        prog.step(7)
        push = subprocess.run([str(Path(__file__).resolve().parent / "push_main.sh")], cwd=c.REPO,
                              capture_output=True, text=True)
        done["push"] = {"exit": push.returncode, "said": (push.stdout + push.stderr).strip()[-400:]}
        c.write_json(rec / "merged.json", done)
        prog.finish("merged")
        return done
    except Refused as e:
        c.set_state(slice_id, last_merge_refusal=c.now())
        prog.finish("refused", str(e))
        raise
    except BaseException as e:
        prog.finish("ended with an error", type(e).__name__)
        raise
    finally:
        for t in trees:
            drop_tree(t)
            shutil.rmtree(t, ignore_errors=True)
            shutil.rmtree(gate_pytest_base(t), ignore_errors=True)  # the full gate's pytest base (1e)
        (c.DATA / RUNNING).unlink(missing_ok=True)
        fh.close()


PUSH_PENDING = "push.pending"


def push_pending() -> str:
    """The push the push step deferred, run once no run on main is in progress or queued (1b: every merge is pushed;
    a deferred push is never forgotten). Nothing pending: said, nothing done. A run still going: refused, the push
    still waits. Otherwise push_main.sh runs, with every rule it keeps (main's tip written by the merge script, the
    recorded origin, a fast-forward), and its words are given back. Under the merge lock, so no merge runs meanwhile."""
    fh = lock()
    try:
        note(watch_github())
        pending = c.DATA / PUSH_PENDING
        if not pending.is_file():
            return "No push is pending."
        sha = pending.read_text().strip()[:10]
        busy = c.main_runs_going()
        if busy:
            raise Refused(f"a run on main is {busy}: the push of {sha} still waits (push.pending). Run push-pending "
                          "again when it ends.")
        p = subprocess.run([str(Path(__file__).resolve().parent / "push_main.sh")], cwd=c.REPO, capture_output=True,
                           text=True)
        said = (p.stdout + p.stderr).strip()
        if p.returncode != 0:
            raise Refused(f"the pending push of {sha} did not go (push_main.sh exit {p.returncode}): {said}")
        return said
    finally:
        fh.close()


def records(message: str, paths: list[str]) -> str:
    """A commit of the records folder alone. While a merge runs it goes on (LINE_FIXES_5_BRIEF.md, 2): the merge's
    landing takes it beneath the tested result (land()); commits are one at a time (records_lock)."""
    try:
        fh = lock()
    except Refused:
        fh = None  # a merge runs: its landing handles main having moved by this commit
    try:
        with records_lock():
            return _records(message, paths, push=fh is not None)
    finally:
        if fh:
            fh.close()


def _records(message: str, paths: list[str], push: bool = True) -> str:
    if not paths:
        raise Refused("name the record files to commit.")
    rels = []
    for p in paths:
        rel = os.path.relpath(os.path.abspath(p), c.REPO) if os.path.isabs(p) else p
        rels.append(os.path.normpath(rel))
        if not rel.startswith(c.V062_REL + "/") or ".." in rel:
            raise Refused(f"records mode commits only {c.V062_REL}/: not {rel}.")
        if rel in OWNER_FILES:
            raise Refused(f"{rel} is the owner's file: records mode never commits it.")
    main_ready(records=True)
    working = c.load_slices(None) if (c.REPO / c.SLICES_REL).exists() else []
    rows = {r["id"]: r for r in working}
    refreezes = {ln["slice"] for ln in c.unapplied_lines() if ln["action"] == "refreeze"}
    for d in c.RECORDS.glob("*/frozen.json") if c.RECORDS.exists() else []:
        fr = c.read_json(d) or {}
        if fr.get("slice") in rows and not c.frozen_matches(fr, rows[fr["slice"]]) and \
                not (c.read_json(d.parent / "merged.json")):
            if fr["slice"] in refreezes and c.SLICES_REL not in rels:
                continue  # 8.1: the owner's refreeze line covers it, and resume.py refreeze commits slices.tsv itself
            if fr["slice"] in refreezes:
                raise Refused(f"slices.tsv waits for the owner's refreeze of {fr['slice']} (resume.tsv), which commits it: "
                              "leave it out of this records commit, then run resume.py " + fr["slice"] + " refreeze.")
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
    if push:  # while a merge runs, its own push carries this commit
        subprocess.run([str(Path(__file__).resolve().parent / "push_main.sh")], cwd=c.REPO)
    return sha


# ------------------------------------------------------------------ the owner's approved diffs (LINE_FIXES_5_BRIEF.md, 10)

#: Where the conductor's proposed diffs are (the owner names one by its file name, without or with `.diff`).
PROPOSALS_REL = f"{c.V062_REL}/slice-line/proposals"
#: The approvals (the conductor's attestation of the owner's "approved: <name> <hash8>" in chat) and the list of applied
#: diffs the board prints and the conductor copies to the top of each report: committed records, beside the rest.
APPROVED_REL = f"{c.V062_REL}/approved"
APPLIED_REL = f"{APPROVED_REL}/applied.tsv"
#: The only files an approved diff may touch (the owner, 21 November 2026).
APPROVED_FILES = ("OspreyFlow_Build/spec/06_DECISIONS.md", "OspreyFlow_Build/spec/ADR_RESERVATIONS.md",
                  "OspreyFlow_Build/spec/design/DESIGN.md", "OspreyFlow_Core/DESIGN.md", "OspreyFlow_Build/process/CLAUDE.md")
#: Never, named in the refusal's words (anything not in APPROVED_FILES is refused anyway).
NEVER_APPROVED = ("OspreyFlow_Core/Makefile", ".github/", "OspreyFlow_Core/harness/signatures.py", *OWNER_FILES)
#: The decision checks run on the result before it is committed (OspreyFlow_Build/Makefile's targets of the same names).
DECISION_CHECKS = ("tools.adr_reservations_check", "tools.doc_citations_check", "tools.decision_log_publication_check")
OWNER_TRAILER = "Owner-Approved-Diff"


def today() -> str:
    """The line's one date (resume.today(), UTC), imported here as resume.py imports this module."""
    import resume
    return resume.today()


def diff_file(name: str) -> tuple[str, Path]:
    """The diff's name (its file name without .diff) and path in the main checkout's proposals folder."""
    stem = name[:-5] if name.endswith(".diff") else name
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", stem):
        raise Refused(f"{name!r} is not a diff's name (the file name in {PROPOSALS_REL}, no folder).")
    return stem, c.REPO / PROPOSALS_REL / f"{stem}.diff"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def approve_diff(name: str, hash8: str) -> str:
    """The conductor's record of the owner's "approved: <name> <hash8>": refused unless hash8 is the first 8 characters
    of the diff file's SHA-256 now; committed in records mode as approved/<name>.json."""
    stem, f = diff_file(name)
    if not f.is_file():
        raise Refused(f"there is no diff {stem} ({f}). Nothing recorded.")
    digest = sha256(f)
    if not re.fullmatch(r"[0-9a-f]{8}", hash8 or "") or digest[:8] != hash8:
        raise Refused(f"the owner's hash8 {hash8!r} is not {stem}.diff's ({digest[:8]}): the diff is not the one he approved, "
                      "or the hash was copied wrong. Ask him again. Nothing recorded.")
    rel = f"{APPROVED_REL}/{stem}.json"
    c.write_json(c.REPO / rel, {"name": stem, "file": f"{PROPOSALS_REL}/{stem}.diff", "sha256": digest, "hash8": hash8,
                                "date": today(), "at": c.now(),
                                "by": "the conductor, on the owner's word in chat: approved: " + f"{stem} {hash8}"})
    sha = records(f"docs(process): the owner's approval of {stem} ({hash8})", [rel])
    return f"Recorded the owner's approval of {stem} ({hash8}) in {rel}, committed {sha[:10]}."


def diff_paths(diff: Path, cwd: Path) -> list[str]:
    """The files the diff touches (git apply --numstat), refused for a rename, a copy or a mode change."""
    summary = subprocess.run(["git", "apply", "--summary", str(diff)], cwd=str(cwd), capture_output=True, text=True)
    numstat = subprocess.run(["git", "apply", "--numstat", str(diff)], cwd=str(cwd), capture_output=True, text=True)
    if summary.returncode or numstat.returncode:
        raise Refused(f"git cannot read the diff: {(summary.stderr or numstat.stderr).strip()[:300]}. Nothing changed.")
    odd = [ln.strip() for ln in summary.stdout.splitlines() if re.match(r"\s*(rename|copy|mode change)\b", ln)]
    if odd:
        raise Refused("the diff renames, copies or changes a file's mode (" + "; ".join(odd[:3]) + "): never an approved "
                      "diff's. Nothing changed.")
    paths = [ln.split("\t", 2)[2] for ln in numstat.stdout.splitlines() if ln.count("\t") >= 2]
    if not paths or any("=>" in q for q in paths):
        raise Refused("the diff names no file, or a renamed one. Nothing changed.")
    return paths


def apply_approved(name: str, wait: float = 120) -> str:
    """The owner-approved diff applied, checked and committed to main with its trailer, then pushed; refused in words,
    with nothing staged or committed, unless every rule holds (LINE_FIXES_5_BRIEF.md, 10)."""
    stem, f = diff_file(name)
    fh = lock_after_merge(wait, f"apply-approved {stem}")
    tree = None
    try:
        rec = c.read_json(c.REPO / APPROVED_REL / f"{stem}.json")
        if not rec or rec.get("name") != stem:
            raise Refused(f"no approval of {stem} is recorded ({APPROVED_REL}/{stem}.json): the conductor records the owner's "
                          f"word first (merge_slice.py approve-diff {stem} <hash8>). Nothing changed.")
        if not f.is_file():
            raise Refused(f"the approved diff {stem}.diff is not there any more: the approval is stale. Nothing changed.")
        if sha256(f) != rec.get("sha256"):
            raise Refused(f"{stem}.diff has changed since the owner approved it ({rec.get('hash8')} then, "
                          f"{sha256(f)[:8]} now): ask him again. Nothing changed.")
        base = main_ready()
        paths = diff_paths(f, c.REPO)
        never = [q for q in paths if q.startswith(NEVER_APPROVED) or q in NEVER_APPROVED]
        outside = [q for q in paths if q not in APPROVED_FILES]
        if never or outside:
            raise Refused(f"the diff touches {', '.join(never or outside)}: an approved diff touches only "
                          f"{', '.join(APPROVED_FILES)}" + (" and never the Makefile, a workflow, harness/signatures.py or "
                                                           "the owner's lanes files" if never else "")
                          + ". The whole diff is refused. Nothing changed.")
        tree = temp_tree(base, f"approved-{stem}")
        check = subprocess.run(["git", "apply", "--check", str(f)], cwd=str(tree), capture_output=True, text=True)
        if check.returncode:
            raise Refused(f"{stem}.diff does not apply to main ({base[:10]}): {check.stderr.strip()[:300]}. Nothing changed.")
        c.git(["apply", "--index", str(f)], tree)
        py = c.REPO / "OspreyFlow_Core/.venv/bin/python"
        py = str(py) if py.is_file() else sys.executable
        env = {**os.environ, "PYTHONPATH": str(tree / "OspreyFlow_Build"), "PYTHONDONTWRITEBYTECODE": "1"}
        for mod in DECISION_CHECKS:
            q = subprocess.run([py, "-m", mod], cwd=str(tree / "OspreyFlow_Core"), env=env, capture_output=True, text=True)
            if q.returncode:
                said = "\n".join([ln for ln in (q.stdout + q.stderr).splitlines() if ln.strip()][-8:])
                raise Refused(f"{stem}.diff applied, but {mod} is red on the result: nothing committed.\n{said}")
        date = today()
        c.git(["commit", "-q", "-m", f"docs(spec): {stem} (approved by the owner, {date})\n\nThe owner's approved diff "
               f"{stem}.diff, sha256 {rec['sha256'][:8]} ({rec['sha256']}), applied by merge_slice.py apply-approved.\n\n"
               f"Slice-Records: yes\n{OWNER_TRAILER}: {stem}"], tree)
        commit = c.git(["rev-parse", "HEAD"], tree)
        with records_lock():
            if c.git(["rev-parse", "HEAD"], c.REPO) != base:
                raise Refused("main moved while the approved diff was being checked: nothing landed; run it again.")
            c.git(["merge", "-q", "--ff-only", commit], c.REPO)
            listed = c.REPO / APPLIED_REL
            listed.parent.mkdir(parents=True, exist_ok=True)
            if not listed.exists():
                listed.write_text("date\tname\thash8\tcommit\n")
            with listed.open("a") as out:
                out.write(f"{date}\t{stem}\t{rec['sha256'][:8]}\t{commit}\n")
            c.git(["add", "--", APPLIED_REL], c.REPO)
            c.git(["commit", "-q", "-m", f"docs(process): {stem} applied ({commit[:10]}), for the owner's next report"
                   "\n\nSlice-Records: yes", "--", APPLIED_REL], c.REPO)
        push = subprocess.run([str(Path(__file__).resolve().parent / "push_main.sh")], cwd=c.REPO, capture_output=True,
                              text=True)
        return (f"Applied the owner's approved {stem} ({rec['sha256'][:8]}): commit {commit[:10]} on main, listed in "
                f"{APPLIED_REL}. Push: {(push.stdout + push.stderr).strip()[-200:]}")
    finally:
        if tree:
            drop_tree(tree)
            shutil.rmtree(tree, ignore_errors=True)
        fh.close()


def wait_idle(minutes: float) -> str:
    """Wait until no merge runs (LINE_FIXES_5_BRIEF.md, 9: a wait that polled `pgrep -f 'merge_slice.py merge'` matched its
    own command line). The merge lock itself is the answer: free is idle. Refused after `minutes`."""
    end = time.time() + minutes * 60
    while True:
        busy = merging()
        if busy is None:
            return "no merge is running."
        if time.time() >= end:
            raise Refused(f"a merge ({busy}) is still running after {minutes:g} minutes.")
        time.sleep(WAIT_POLL_SECONDS)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("merge")
    m.add_argument("slice")
    r = sub.add_parser("records")
    r.add_argument("-m", "--message", required=True)
    r.add_argument("paths", nargs="+")
    sub.add_parser("push-pending")
    sub.add_parser("watch-github")
    wi = sub.add_parser("wait-idle")
    wi.add_argument("--minutes", type=float, default=120)
    ad = sub.add_parser("approve-diff")
    ad.add_argument("name")
    ad.add_argument("hash8")
    sr = sub.add_parser("server-rerun")
    sr.add_argument("slice")
    aa = sub.add_parser("apply-approved")
    aa.add_argument("name")
    aa.add_argument("--wait", type=float, default=120, metavar="MINUTES", help="how long to wait for a running merge")
    a = ap.parse_args()
    try:
        if a.cmd == "merge":
            done = merge(a.slice)
            print(json.dumps(done, indent=1))
        elif a.cmd == "push-pending":
            print(push_pending())
        elif a.cmd == "watch-github":
            print(watch_github())
        elif a.cmd == "wait-idle":
            print(wait_idle(a.minutes))
        elif a.cmd == "approve-diff":
            print(approve_diff(a.name, a.hash8))
        elif a.cmd == "server-rerun":
            print(server_rerun(a.slice))
        elif a.cmd == "apply-approved":
            print(apply_approved(a.name, a.wait))
        else:
            print("Committed", records(a.message, a.paths))
    except Refused as e:
        print(f"Refused: {e}", file=sys.stderr)
        rc = 1
    else:
        rc = 0
    for n in NOTES:
        print(n, file=sys.stderr)
    subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "board.py"), "--quiet"])
    return rc


if __name__ == "__main__":
    sys.exit(main())
