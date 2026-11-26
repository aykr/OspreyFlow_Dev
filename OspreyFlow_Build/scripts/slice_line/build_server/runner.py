#!/usr/bin/env python3
"""The build account's container checks (the owner's file 017, item 1; his answer of 25 November 2026): the forced
command of the Mac's key to `ospreyflow_build` on the test server. No shell, four verbs in all:

    (forced command)  checks <ID>     a git bundle on standard input, of exactly main's tip and one slice's tip (sent
                                      by early_warning.py at the moment it sends the early warning); the candidate is
                                      built as the Mac's merge builds it and checked in a detached job; prints
                                      {"state": "started", "id": <16 hex>, "holds_main": <main>} and returns at once
    (forced command)  start | stop | status ...
                                      017-2's seats: refused until they are built
    runner.py _work                   the jobs, one at a time, as systemd-run starts them (never reachable over SSH:
                                      the forced command takes no arguments and reads only SSH_ORIGINAL_COMMAND)

SSH_ORIGINAL_COMMAND is matched whole; no part of it reaches a shell. Anything else is refused, and logged in
refusals.log by its reason and its length, never its text.

A job: a shared clone of this runner's own bare copy (data/source.git) at main's tip; `git merge --no-ff` of the
slice's tip; the slice's waiting scan rows applied in the merge commit (as merge_slice.py and the early warning do);
CI's Python (`uv sync --frozen`) and `npm ci`; then the container checks, TARGETS below, each the tree's gate lists.
They run in this account's own rootless Docker and nowhere else: the job sets DOCKER_HOST to this account's socket
itself (never taken from the caller), and nothing runs unless the system Docker's socket does not answer and
`docker info` answers as rootless.

Results go back only through the backup repository: each is one JSON file, `results/<ID>/<TIP>.json`, committed by
plumbing on the local branch `build-results` of this account's clone (~/ospreyflow), which the backup timer pushes.
Nothing here pushes, and nothing is ever answered over SSH but "started" or a refusal. A result:
    {state, id, runner, slice, tip, main, tree, verdict, words, passed_targets, failing {targets, tests},
     not_run {targets}, steps [{target, exit, seconds}], seconds, finished}
verdict: "pass" (every container check the tree's gate lists ran and exited 0), "fail", "conflict" or "error"
(`words` says why; nothing counts).

Standard library only, Python 3.8 or later. Installed as the early warning's runner is: bin/ and data/ side by side
(data/ is fixed beside the code, never taken from the environment).
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

RUNNER = "bc-1"
HERE = Path(__file__).resolve().parent
WORK = HERE.parent / "data"
SOURCE = WORK / "source.git"
JOBS = WORK / "jobs"
REFUSALS = WORK / "refusals.log"
CLONE = Path.home() / "ospreyflow"
RESULTS_BRANCH = "build-results"
#: A part's name as the early warning sends it (protocol.SLICE_PATTERN), a capital first: AD1c, PL7f, IS5a0.
SLICE = re.compile(r"\A[A-Z][A-Za-z0-9]{0,15}\Z")
SHA = re.compile(r"\A[0-9a-f]{40}\Z")
SEAT_VERBS = ("start", "stop", "status")  # 017-2
MAX_BUNDLE = 2 * 1024 ** 3
MAX_QUEUE = 20
#: How a job is started: systemd-run in the account's own user manager (it outlives the SSH session, under the
#: account's caps), or "direct" (the line's tests). WORKER is the command that runs the jobs.
LAUNCH = "systemd-run"
WORKER = [sys.executable, str(Path(__file__).resolve()), "_work"]
#: (makefile folder, gate target, target): the gate's container checks, in the order they run.
TARGETS = (
    [("OspreyFlow_Build", "ci", t) for t in ("opentofu-check", "chart-check", "cp-policy-check")]
    + [("OspreyFlow_Core", "check", t) for t in (
        "trivy", "trivy-image-ingest", "trivy-image-api", "trivy-image-workspace", "trivy-image-harness",
        "trivy-image-ner", "trivy-image-worker", "trivy-image-report-sync", "trivy-image-superset",
        "trivy-image-laurium", "harness-a11y")]
)
#: harness-a11y runs here only once demo-server has proved its browser runs in this account (the owner's answer of
#: 25 November 2026): this file, beside the runner and root's as the code is, says so. Without it the check is not
#: run, the result does not name it, and the Mac keeps it.
A11Y_READY = HERE / "harness-a11y.ready"
TARGET_SECONDS = 3600
SYSTEM_SOCKETS = ("/var/run/docker.sock", "/run/docker.sock")
#: What a job keeps of its caller's environment; DOCKER_HOST is set by the job itself.
KEPT = ("PATH", "HOME", "LANG", "XDG_RUNTIME_DIR", "USER", "LOGNAME")


class Stop(Exception):
    def __init__(self, verdict: str, words: str):
        super().__init__(words)
        self.verdict, self.words = verdict, words


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def say(data: dict, code: int) -> int:
    print(json.dumps(data), flush=True)
    return code


def refuse(reason: str, received: str | None = None, **words) -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    with REFUSALS.open("a") as fh:
        fh.write("%s\t%s\t%s\n" % (now(), reason, len(received) if received is not None else "-"))
    return say({"state": "refused", "reason": reason, **words}, 3)


def git_env() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k.startswith("GIT_CONFIG")}
    env.update(GIT_AUTHOR_NAME="ospreyflow_build", GIT_AUTHOR_EMAIL="build@ospreyflow-test.invalid",
               GIT_COMMITTER_NAME="ospreyflow_build", GIT_COMMITTER_EMAIL="build@ospreyflow-test.invalid")
    return env


def git(args: list, cwd: Path = SOURCE, check: bool = True, env: dict | None = None, input: str | None = None) -> str:
    p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, env=env or git_env(), input=input)
    if check and p.returncode != 0:
        raise Stop("error", "git %s failed: %s" % (args[0], (p.stderr or p.stdout).strip()[:200]))
    return p.stdout.strip()


# ------------------------------------------------------------------ the forced command


def receive(dest: Path) -> bool:
    """Standard input into dest, up to MAX_BUNDLE; False when it is larger."""
    n = 0
    with dest.open("wb") as fh:
        while True:
            chunk = sys.stdin.buffer.read(1 << 20)
            if not chunk:
                return True
            n += len(chunk)
            if n > MAX_BUNDLE:
                return False
            fh.write(chunk)


def pending() -> list:
    """The jobs received and not yet done, oldest first."""
    if not JOBS.is_dir():
        return []
    jobs = [j for j in JOBS.iterdir() if (j / "job.json").is_file() and not (j / "result.json").exists()]
    return sorted(jobs, key=lambda j: (j / "job.json").stat().st_mtime_ns)


def launch(rid: str) -> None:
    env = {k: v for k, v in os.environ.items() if k in KEPT}
    out = subprocess.DEVNULL
    if LAUNCH == "direct":
        subprocess.Popen(WORKER, env=env, stdin=out, stdout=out, stderr=out, start_new_session=True)
    else:
        subprocess.run(["systemd-run", "--user", "--quiet", "--collect", "--unit", "build-checks-" + rid, *WORKER],
                       env=env, stdin=out, stdout=out, stderr=out)


def do_checks(slice_id: str) -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    if not SOURCE.is_dir():
        git(["init", "-q", "--bare", str(SOURCE)], cwd=WORK)
    if len(pending()) >= MAX_QUEUE:
        return refuse("busy", words="%d jobs are waiting" % MAX_QUEUE)
    rid = secrets.token_hex(8)
    job = JOBS / rid
    job.mkdir(parents=True)
    bundle = job / "in.bundle"
    try:
        if not receive(bundle):
            return refuse("too-large")
        heads = {}
        for line in git(["bundle", "list-heads", str(bundle)], check=False).splitlines():
            sha, _, ref = line.partition(" ")
            heads[ref] = sha
        others = [r for r in heads if r != "refs/heads/main"]
        if "refs/heads/main" not in heads or len(others) != 1 or not others[0].startswith("refs/heads/") or \
                not all(SHA.match(h) for h in heads.values()):
            return refuse("bundle-shape", words="a bundle of exactly main and one slice branch")
        if subprocess.run(["git", "bundle", "verify", "-q", str(bundle)], cwd=str(SOURCE), capture_output=True,
                          env=git_env()).returncode != 0:
            return refuse("bundle-prerequisites")
        git(["fetch", "-q", str(bundle), "+refs/heads/*:refs/jobs/%s/*" % rid])
        main, tip = heads["refs/heads/main"], heads[others[0]]
        git(["update-ref", "refs/heads/main", main])  # what this copy holds, for the Mac's next, smaller bundle
        (job / "job.json").write_text(json.dumps({"slice": slice_id, "tip": tip, "main": main, "received": now()}))
    except Stop:
        return refuse("bundle-unreadable")
    finally:
        if bundle.exists():
            bundle.unlink()
        if not (job / "job.json").exists():
            shutil.rmtree(job, ignore_errors=True)
    launch(rid)
    return say({"state": "started", "id": rid, "holds_main": main}, 0)


def forced(cmd: str) -> int:
    parts = cmd.split(" ")
    if len(parts) == 2 and parts[0] == "checks" and SLICE.match(parts[1]):
        return do_checks(parts[1])
    if parts[0] in SEAT_VERBS:
        return refuse("not-yet", cmd, words="the seats (017-2) are not built yet")
    return refuse("shape", cmd)


# ------------------------------------------------------------------ Docker: this account's own, never the system's


def own_socket() -> str:
    run = os.environ.get("XDG_RUNTIME_DIR") or "/run/user/%d" % os.getuid()
    return "unix://%s/docker.sock" % run.rstrip("/")


def answers(path: str) -> bool:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect(path)
        return True
    except OSError:
        return False
    finally:
        s.close()


def job_env() -> dict:
    """The job's environment: the caller's few plain variables, and DOCKER_HOST this account's own socket."""
    env = {k: v for k, v in os.environ.items() if k in KEPT}
    env["DOCKER_HOST"] = own_socket()
    return env


def docker_check(env: dict) -> None:
    """Nothing runs unless Docker is this account's rootless daemon: the system Docker's socket not answering, and
    `docker info` on the job's own DOCKER_HOST answering as rootless."""
    for path in SYSTEM_SOCKETS:
        if answers(path):
            raise Stop("error", "the system Docker's socket %s answers this account; nothing was run" % path)
    p = subprocess.run(["docker", "info", "--format", "{{json .SecurityOptions}}"], capture_output=True, text=True,
                       env=env)
    if p.returncode != 0 or "rootless" not in p.stdout:
        raise Stop("error", "docker info does not answer as rootless on this account's socket (%s); nothing was run"
                   % (p.stderr or p.stdout).strip()[:160])


# ------------------------------------------------------------------ the candidate, as the Mac's merge builds it


def gate_targets(tree: Path, folder: str, gate: str) -> list:
    """The prerequisites of `gate` in the tree's own Makefile (one line, `gate: a b c`)."""
    try:
        text = (tree / folder / "Makefile").read_text()
    except OSError:
        return []
    m = re.search(r"^%s:([^\n=]*)$" % re.escape(gate), text, re.M)
    return m.group(1).split() if m else []


def apply_scan_rows(tree: Path, slice_id: str) -> None:
    """merge_slice.apply_scan_rows' change to the merge commit: the rows appended, the rows file removed, amended."""
    rows_file = tree / ("OspreyFlow_Build/process/lanes/v062/scan_rows/%s.tsv" % slice_id)
    if not rows_file.is_file():
        return
    lines = [ln for ln in rows_file.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    map_file = tree / "OspreyFlow_Build/scripts/slice_line/scan_map.tsv"
    text = map_file.read_text()
    map_file.write_text(text + ("" if text.endswith("\n") else "\n") + "".join(ln + "\n" for ln in lines))
    git(["add", "--", str(map_file.relative_to(tree))], cwd=tree)
    git(["rm", "-q", "--", str(rows_file.relative_to(tree))], cwd=tree)
    git(["commit", "-q", "--amend", "--no-edit"], cwd=tree)


def candidate(tree: Path, main: str, slice_id: str, tip: str) -> str:
    """The candidate checked out at `tree` (a shared clone of the runner's copy, no remote kept); its tree hash."""
    git(["clone", "-q", "--shared", "--no-checkout", str(SOURCE), str(tree)], cwd=WORK)
    git(["-C", str(tree), "remote", "remove", "origin"], cwd=WORK)
    git(["-C", str(tree), "checkout", "-q", "--detach", main], cwd=WORK)
    msg = "merge: slice %s (build checks) %s\n\nSlice-Merge: %s\nSlice-Tip: %s" % (slice_id, tip[:10], slice_id, tip)
    m = subprocess.run(["git", "merge", "--no-ff", "-q", "-m", msg, tip], cwd=str(tree), capture_output=True,
                       text=True, env=git_env())
    if m.returncode != 0:
        raise Stop("conflict", "the slice does not merge cleanly onto main")
    apply_scan_rows(tree, slice_id)
    return git(["rev-parse", "HEAD^{tree}"], cwd=tree)


def environment(tree: Path, env: dict, log) -> dict:
    """The tree's own environment, as the gate's: CI's Python (`uv sync --frozen`) and `npm ci` in Core."""
    py = re.findall(r"^\s*UV_PYTHON:\s*[\"']?([0-9][0-9.]*)", (tree / ".github/workflows/ci.yml").read_text(), re.M)
    if len(set(py)) != 1:
        raise Stop("error", "ci.yml names %d UV_PYTHON values; exactly one is needed" % len(set(py)))
    env = {**env, "UV_PYTHON": py[0]}
    for cmd in (["uv", "sync", "--frozen"], ["npm", "ci", "--no-audit", "--no-fund"]):
        log.write("\n$ %s\n" % " ".join(cmd))
        log.flush()
        p = subprocess.run(cmd, cwd=str(tree / "OspreyFlow_Core"), stdout=log, stderr=subprocess.STDOUT, env=env)
        if p.returncode != 0:
            raise Stop("error", "building the environment failed at: %s" % " ".join(cmd[:2]))
    return env


def run_targets(tree: Path, env: dict, log, result: dict) -> None:
    steps, passed, failing, not_run = [], [], [], []
    for folder, gate, target in TARGETS:
        if target not in gate_targets(tree, folder, gate):
            not_run.append({"name": target, "why": "not in this tree's %s" % gate})
            continue
        if target == "harness-a11y" and not A11Y_READY.is_file():
            not_run.append({"name": target, "why": "not proved on this server (no bin/harness-a11y.ready); the Mac keeps it"})
            continue
        log.write("\n$ make -C %s %s\n" % (folder, target))
        log.flush()
        t0 = time.monotonic()
        try:
            code = subprocess.run(["make", "-C", folder, target], cwd=str(tree), stdout=log, stderr=subprocess.STDOUT,
                                  env=env, timeout=TARGET_SECONDS).returncode
        except subprocess.TimeoutExpired:
            code = 124
        steps.append({"target": target, "exit": code, "seconds": int(time.monotonic() - t0)})
        (passed if code == 0 else failing).append(target)
    result.update(steps=steps, passed_targets=passed, failing={"targets": failing, "tests": []},
                  not_run={"targets": not_run})
    result["verdict"] = "pass" if steps and not failing else "fail"
    if not steps:
        result.update(verdict="error", words="the tree's gate lists none of the container checks")


# ------------------------------------------------------------------ results, on the local branch the backup takes


def result_path(slice_id: str, tip: str) -> str:
    return "results/%s/%s.json" % (slice_id, tip)


def write_result(result: dict) -> None:
    """The result committed on the clone's refs/heads/build-results by plumbing alone: no checkout, and never the
    clone's own index."""
    blob = git(["hash-object", "-w", "--stdin"], cwd=CLONE, input=json.dumps(result, indent=1) + "\n")
    index = WORK / "results.index"
    if index.exists():
        index.unlink()
    env = {**git_env(), "GIT_INDEX_FILE": str(index)}
    parent = git(["rev-parse", "-q", "--verify", "refs/heads/%s" % RESULTS_BRANCH], cwd=CLONE, check=False)
    if parent:
        git(["read-tree", parent], cwd=CLONE, env=env)
    git(["update-index", "--add", "--cacheinfo", "100644,%s,%s" % (blob, result_path(result["slice"], result["tip"]))],
        cwd=CLONE, env=env)
    tree = git(["write-tree"], cwd=CLONE, env=env)
    msg = "build checks: %s at %s on main %s: %s (%s)" % (result["slice"], result["tip"][:10], str(result["main"])[:10],
                                                         result["verdict"], result["id"])
    commit = git(["commit-tree", tree, *(["-p", parent] if parent else []), "-m", msg], cwd=CLONE)
    git(["update-ref", "refs/heads/%s" % RESULTS_BRANCH, commit, *([parent] if parent else [])], cwd=CLONE)
    index.unlink()


def run_one(job: Path) -> dict:
    meta = json.loads((job / "job.json").read_text())
    result = {"state": "done", "id": job.name, "runner": RUNNER, "slice": meta["slice"], "tip": meta["tip"],
              "main": meta["main"], "tree": None, "verdict": "error", "words": "", "passed_targets": [],
              "failing": {"targets": [], "tests": []}, "not_run": {"targets": []}, "steps": []}
    t0 = time.monotonic()
    tree = job / "tree"
    with (job / "log.txt").open("w") as log:
        try:
            env = job_env()
            docker_check(env)
            result["tree"] = candidate(tree, meta["main"], meta["slice"], meta["tip"])
            run_targets(tree, environment(tree, env, log), log, result)
        except Stop as e:
            result.update(verdict=e.verdict, words=e.words, passed_targets=[])
        except Exception as e:  # noqa: BLE001 - any other fault is the runner's, never the slice's
            result.update(verdict="error", words="the runner failed: %s" % type(e).__name__, passed_targets=[])
    result["seconds"] = int(time.monotonic() - t0)
    result["finished"] = now()
    if not result.get("words"):
        result.pop("words")
    shutil.rmtree(tree, ignore_errors=True)  # the log stays, for the owner
    for ref in git(["for-each-ref", "--format=%(refname)", "refs/jobs/%s/" % job.name], check=False).split():
        git(["update-ref", "-d", ref], check=False)
    return result


def work() -> int:
    """Every pending job, one at a time, under the one lock; looked for again after the lock is let go, so a job
    received meanwhile is never left waiting."""
    WORK.mkdir(parents=True, exist_ok=True)
    while True:
        with (WORK / "lock").open("w") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return 0
            for job in pending():
                try:
                    r = run_one(job)
                    write_result(r)
                except Exception as e:  # noqa: BLE001 - a job it cannot read or record never stops the rest
                    r = {"state": "done", "id": job.name, "verdict": "error",
                         "words": "the job could not be run or recorded: %s" % type(e).__name__}
                (job / "result.json").write_text(json.dumps(r, indent=1) + "\n")
        if not pending():
            return 0


def main(argv: list) -> int:
    if argv == ["_work"] and "SSH_ORIGINAL_COMMAND" not in os.environ:
        return work()
    return forced(os.environ.get("SSH_ORIGINAL_COMMAND", ""))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
