#!/usr/bin/env python3
"""The demo server's early-warning runner: the forced command of one SSH key (DEMO_SERVER_EARLY_WARNING_BRIEF.md).

ADVICE ONLY. The Mac's merge run (merge_slice.py merge) stays the only gate to main; nothing here is read by it.

    (forced command)  run             a git bundle on standard input (main's tip and one slice's tip): the candidate
                                      is built as merge_slice.py builds it and checked in a detached job; prints
                                      {"state": "started", "id": <16 hex>} and returns at once
    (forced command)  result <id>     the job's result, or {"state": "running", "seconds": n}
    runner.py _job <id>               the job itself, as systemd-run starts it (never reachable over SSH: the
                                      forced command takes no arguments and reads only SSH_ORIGINAL_COMMAND)

SSH_ORIGINAL_COMMAND is read once and matched whole against the two shapes in protocol.py; no part of it reaches a
shell (no subprocess here is started through a shell). It reads no other variable: no test switch, no work folder. Anything else is refused and logged in refusals.log by its reason
class and its length, never its text.

What a job does (merge_slice.py's recipe, reproduced; the owner's rulings 1 to 3): a worktree of the runner's own
bare source copy at main's tip; `git merge --no-ff` of the slice's tip; the slice's waiting scan rows applied in the
merge commit; the environment built as ci_env builds it (uv sync --frozen on ci.yml's UV_PYTHON, npm ci on ci.yml's
Node major, the closed store ports, the merger's Playwright slot, a pytest temp base of its own, nothing of the
caller's); then only the parts of `make -k ci` and `make test` that start no container and bind no fixed port
(lists.tsv), with the repository's own docker guard on (`no-local-stacks`), no Docker reachable at all (the runner's
user is in no docker group, a refusing `docker` is first on PATH, and each job checks Docker's socket refuses it), and
under a CPU, memory, time and disk cap. Everything else is named "not run", never passed.

Standard library only, Python 3.8 or later.
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lists as named_lists  # noqa: E402
import protocol as p  # noqa: E402

#: Fixed beside the code (install.sh: bin/ and data/ side by side), never taken from the environment.
WORK = HERE.parent / "data"
SOURCE = WORK / "source.git"
JOBS = WORK / "jobs"
TOOLS = WORK / "tools"
CACHE = WORK / "cache"
REFUSALS = WORK / "refusals.log"
#: 010: a red run's log and result, copied here once its result is written, for the summary account (osprey-summary)
#: to read; and that account's summaries, which `summary <id>` returns. Both beside data/, never inside it: the
#: summary account reads nothing of data/. install.sh makes them; without them nothing is handed over.
HANDOFF = HERE.parent / "handoff"
SUMMARIES = HERE.parent / "summaries"
#: 015: the summary's model and the jobs never overlap. The model's helper listens on a loopback port in the range the
#: job's shield leaves open, so a job starting beside it is refused, and one running beside it could reach it. Each job
#: holds this lock shared for its whole run; the summary asks the model only while it holds it alone, and lets it go
#: once the model is unloaded. A starting job waits for that, at most SUMMARY_WAIT_SECONDS (two asks and the unload).
MODEL_LOCK = HANDOFF / "model.lock"
SUMMARY_WAIT_SECONDS = 15 * 60
#: A breach is checked again for this long before the run is refused: a helper Ollama is closing may still listen
#: for a moment after it says the model is gone. Nothing has run while it waits.
SHIELD_SETTLE_SECONDS = 30
_HELD = []  # the job's own hold on MODEL_LOCK, kept open until the job's process ends
KEEP_JOBS = 40  # 009: a result is kept until the merge has asked for it by id, for several slices at once

#: merge_slice.py's OFFLINE_PORTS: an offline run reaches no store.
OFFLINE_PORTS = {"ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "VALKEY_PORT": "59993",
                 "CLICKHOUSE_HTTP_PORT": "59994"}
#: The lanes whose port slots the jobs take, one each, so three jobs at once never share a port (009). The merge
#: gate's own first; the others are lanes that never run on this machine (lane_ports.tsv keeps every slot's block clear
#: of the stacks' ports and of the owner's deployment's).
GATE_LANES = ("merger", "platform-b", "rules-b")
SLICE_REF = re.compile(r"\Arefs/heads/lane/slice-([A-Za-z0-9]+)\Z")
SHA = re.compile(r"\A[0-9a-f]{40}\Z")
#: merge_slice.py's own patterns for a failing test and a failed make target.
FAILED_TEST = p.FAILED_TEST  # one pattern, which the summary (010) also reads logs with
MAKE_ERROR = p.MAKE_ERROR
#: tests/local_docker_guard.py's skip, as pytest -rs prints it.
DOCKER_SKIP = re.compile(r"^SKIPPED \[\d+\] ([^:\s]+):\d+: a server-only test: it calls the docker CLI")


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def say(data: dict, code: int) -> int:
    sys.stdout.write(json.dumps(data, sort_keys=True) + "\n")
    sys.stdout.flush()
    return code


def refuse(reason: str, received: str | None = None, **words) -> int:
    """A refusal: logged by class and length only; told to the caller by class (and any words the runner wrote)."""
    WORK.mkdir(parents=True, exist_ok=True)
    with REFUSALS.open("a") as fh:
        fh.write(p.refusal_line(now(), reason, received))
    return say({"state": "refused", "reason": reason, **words}, 3)


def inside_work(path: Path) -> bool:
    """Whether `path`, every link followed, is inside the work folder: the runner writes, mounts and binds nothing
    outside it (the owner's point 6: never a demo volume or data folder)."""
    root = os.path.realpath(str(WORK))
    real = os.path.realpath(str(path))
    return real == root or real.startswith(root + os.sep)


def git(args: list, cwd: Path | None = None, check: bool = True, env: dict | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=str(cwd) if cwd else None, capture_output=True, text=True,
                       env=env or git_env())
    if check and r.returncode != 0:
        raise RuntimeError("git %s: exit %d" % (args[0], r.returncode))
    return r.stdout.strip()


def git_env() -> dict:
    """git with no user or system config, no credential, no hooks: the source copy has no remote and asks no one."""
    return {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(WORK), "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0", "GIT_AUTHOR_NAME": "osprey-early",
            "GIT_AUTHOR_EMAIL": "osprey-early@localhost", "GIT_COMMITTER_NAME": "osprey-early",
            "GIT_COMMITTER_EMAIL": "osprey-early@localhost", "LANG": "C.UTF-8"}


def ensure_source() -> None:
    if not (SOURCE / "HEAD").exists():
        SOURCE.mkdir(parents=True, exist_ok=True)
        git(["init", "-q", "--bare", str(SOURCE)])
        git(["-C", str(SOURCE), "config", "core.hooksPath", os.devnull])


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def job_alive(job: Path) -> bool:
    try:
        return pid_alive(int((job / "job.pid").read_text().strip()))
    except (OSError, ValueError):
        # started but not yet running its first line: alive while young
        return (job / "job.json").exists() and time.time() - (job / "job.json").stat().st_mtime < 60


def running_jobs() -> list:
    """The jobs started and not finished: up to MAX_JOBS run at once (009)."""
    if not JOBS.is_dir():
        return []
    return sorted(d.name for d in JOBS.iterdir()
                  if (d / "job.json").exists() and not (d / "result.json").exists() and job_alive(d))


def lanes_in_use(jobs: list) -> set:
    used = set()
    for jid in jobs:
        try:
            used.add(json.loads((JOBS / jid / "job.json").read_text()).get("lane", GATE_LANES[0]))
        except (OSError, ValueError):
            used.update(GATE_LANES)  # unreadable: assume the worst, so no slot is shared
    return used


# ------------------------------------------------------------------------------------------------- run

def receive(dest: Path) -> int:
    """The bundle from standard input, to `dest`, at most MAX_BUNDLE_BYTES; its size, or -1 when over the limit."""
    n = 0
    with dest.open("wb") as fh:
        while True:
            chunk = sys.stdin.buffer.read(1 << 20)
            if not chunk:
                return n
            n += len(chunk)
            if n > p.MAX_BUNDLE_BYTES:
                return -1
            fh.write(chunk)


def launch_capped(jid: str) -> bool:
    """Start the job detached, under the caps. Never uncapped: no systemd-run, no job. The job's python runs isolated
    (-I: no PYTHONPATH, no user site, nothing from the environment), as the forced command's own does."""
    me = [sys.executable, "-I", str(Path(__file__).resolve()), "_job", jid]
    run = shutil.which("systemd-run")
    if not run:
        return False
    cmd = [run, "--user", "--quiet", "--collect", "--unit", p.PREFIX + "job-" + jid,
           "--property", "CPUQuota=" + p.CPU_QUOTA, "--property", "MemoryMax=" + p.MEMORY_MAX,
           "--property", "MemorySwapMax=0", "--property", "RuntimeMaxSec=%d" % (p.MAX_RUN_SECONDS + 600),
           "--property", "IOSchedulingClass=best-effort", "--property", "IOSchedulingPriority=7",
           "--nice", str(p.NICE), "--", *me]
    return subprocess.run(cmd, capture_output=True, env={**os.environ}).returncode == 0


def do_run(received: str, order: list | None = None) -> int:
    """`run` (main and one slice) or `stack A B C` (main and those slices, tested as main+A, main+A+B, main+A+B+C at
    once, one job each: 009). The bundle carries refs/heads/main and exactly the slices named, no other head."""
    for d in (WORK, JOBS, TOOLS, CACHE):
        if d.exists() and not inside_work(d):
            return refuse("outside-work", received, words="%s leads outside the work folder" % d.name)
    JOBS.mkdir(parents=True, exist_ok=True)
    lock = (WORK / "run.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return refuse("busy", received)
    running = running_jobs()
    want = len(order) if order else 1
    if len(running) + want > p.MAX_JOBS:
        return refuse("busy", received, running=running, free=max(0, p.MAX_JOBS - len(running)))
    if shutil.disk_usage(str(WORK)).free < p.MIN_FREE_BYTES:
        return refuse("disk-floor", received, words="under %d GB free" % (p.MIN_FREE_BYTES // 1024 ** 3))
    lanes = [ln for ln in GATE_LANES if ln not in lanes_in_use(running)][:want]
    if len(lanes) < want:
        return refuse("busy", received, running=running, words="no free port slot")
    ids = []
    while len(ids) < want + (1 if order else 0):  # a stack has an id of its own, for its one result (012 c)
        jid = secrets.token_hex(p.ID_LENGTH // 2)
        if jid not in ids and not (JOBS / jid).exists():
            ids.append(jid)
    stack_id = ids.pop() if order else None
    job = JOBS / ids[0]
    job.mkdir()
    bundle = job / "bundle"

    def drop(reason: str, **words) -> int:
        for j in ids + ([stack_id] if stack_id else []):
            shutil.rmtree(str(JOBS / j), ignore_errors=True)
        for ref in git(["-C", str(SOURCE), "for-each-ref", "--format=%(refname)", "refs/early/%s/" % ids[0]],
                       check=False).splitlines():
            git(["-C", str(SOURCE), "update-ref", "-d", ref], check=False)
        return refuse(reason, received, **words)

    size = receive(bundle)
    if size < 0:
        return drop("bundle-too-large", words="over the %d MiB limit" % (p.MAX_BUNDLE_BYTES >> 20))
    if size == 0:
        return drop("bundle-empty")
    ensure_source()
    v = subprocess.run(["git", "-C", str(SOURCE), "bundle", "verify", str(bundle)], capture_output=True, text=True,
                       env=git_env())
    if v.returncode != 0:
        missing = sorted(set(re.findall(r"\b[0-9a-f]{40}\b", v.stderr)))
        if missing:
            return drop("bundle-prerequisites", missing=missing,
                        words="this machine does not hold the commits the bundle is built on: send a full bundle")
        return drop("bundle-unreadable")
    heads = {}
    for ln in git(["bundle", "list-heads", str(bundle)], cwd=SOURCE).splitlines():
        sha, _, ref = ln.partition(" ")
        heads[ref.strip()] = sha.strip()
    slices = {SLICE_REF.match(r).group(1): r for r in heads if SLICE_REF.match(r)}
    shown = [re.sub(r"[^\w/.-]", "?", r)[:80] for r in sorted(heads)]
    if set(heads) != {"refs/heads/main", *slices.values()} or (order is None and len(slices) != 1) \
            or (order is not None and set(slices) != set(order)):
        return drop("bundle-heads", heads=shown, words="a bundle carries refs/heads/main and one refs/heads/lane/slice-<ID>"
                    if order is None else "a stack's bundle carries refs/heads/main and exactly the slices named")
    order = order or list(slices)
    first = ids[0]
    git(["-C", str(SOURCE), "fetch", "-q", "--no-tags", str(bundle), "refs/heads/main:refs/early/%s/main" % first,
         *["%s:refs/early/%s/slice/%s" % (slices[s], first, s) for s in order]])
    tips = {}
    for name, ref in [("main", "main")] + [(s, "slice/" + s) for s in order]:
        got = git(["-C", str(SOURCE), "rev-parse", "--verify", "-q", "refs/early/%s/%s^{commit}" % (first, ref)],
                  check=False)
        if not SHA.match(got or ""):
            return drop("unresolved-tip", tip=name, words="the bundle's %s tip cannot be resolved here" % name)
        tips[name] = got
    bundle.unlink()
    for k, jid in enumerate(ids):
        stack = [{"slice": s, "tip": tips[s]} for s in order[:k + 1]]
        if k:  # each job holds its own refs to what it tests, so one job's end never drops another's commits
            (JOBS / jid).mkdir()
            for name, ref in [("main", "main")] + [(s["slice"], "slice/" + s["slice"]) for s in stack]:
                git(["-C", str(SOURCE), "update-ref", "refs/early/%s/%s" % (jid, ref), tips[name]])
        (JOBS / jid / "job.json").write_text(json.dumps({
            "id": jid, "slice": stack[-1]["slice"], "tip": stack[-1]["tip"], "main": tips["main"], "stack": stack,
            "position": k + 1, "of": len(ids), "group": ids, "lane": lanes[k], "bundle_bytes": size, "at": now(),
            **({"stack_id": stack_id} if stack_id else {})}))
    if stack_id:
        (JOBS / stack_id).mkdir()
        (JOBS / stack_id / "stack.json").write_text(json.dumps({"id": stack_id, "main": tips["main"], "order": order,
                                                              "ids": ids, "at": now()}))
    for k, jid in enumerate(ids):
        if not LAUNCH(jid):
            if k == 0:
                return drop("no-cap", words="systemd-run could not start the job under its caps; nothing was run")
            for later in ids[k:]:  # never left looking alive: a result that says what happened
                (JOBS / later / "result.json").write_text(json.dumps({
                    "state": "done", "id": later, "verdict": "error", "runner_version": p.RUNNER_VERSION,
                    "words": "systemd-run could not start this job under its caps; nothing was run"}))
            break
    if stack_id:
        return say({"state": "started", "id": stack_id, "ids": ids, "stack": order}, 0)
    return say({"state": "started", "id": ids[0], "ids": ids, "slice": order[0]}, 0)


#: What a stack's one result gives of each member (the line-fix session's shape, 012 c).
MEMBER_FIELDS = ("slice", "tip", "tree", "verdict", "failing", "passed_targets", "not_run")


def member(jid: str) -> dict:
    job = JOBS / jid
    res = job / "result.json"
    if res.exists():
        r = json.loads(res.read_text())
        return {"id": jid, "state": "done", **{k: r.get(k) for k in MEMBER_FIELDS}}
    meta = json.loads((job / "job.json").read_text()) if (job / "job.json").exists() else {}
    state = "running" if job.is_dir() and job_alive(job) else "died"
    return {"id": jid, "state": state, "slice": meta.get("slice"), "tip": meta.get("tip")}


def stack_result(stack_id: str) -> dict:
    """A stack's one result: each member in the order run, from each member job's own result."""
    meta = json.loads((JOBS / stack_id / "stack.json").read_text())
    members = [member(j) for j in meta["ids"]]
    states = {m["state"] for m in members}
    state = "running" if "running" in states else "died" if "died" in states else "done"
    return {"state": state, "id": stack_id, "main": meta["main"], "runner_version": p.RUNNER_VERSION,
            "stack": members, "advice": "advice only; the Mac's merge run is the gate"}


def do_summary(jid: str) -> int:
    """010: a red run's summary, by its id: the summary account's file, or pending while it is being made."""
    job = JOBS / jid
    if not job.is_dir() or not inside_work(job):
        return say({"state": "unknown", "id": jid}, 3)
    if not (job / "result.json").exists():
        return say({"state": "pending", "id": jid, "words": "the run has no result yet"}, 0)
    try:
        fd = os.open(str(SUMMARIES / (jid + ".json")), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        verdict = json.loads((job / "result.json").read_text()).get("verdict")
        if verdict != "fail":
            return say({"state": "none", "id": jid, "words": "only a red run is summarized (this one: %s)" % verdict}, 0)
        return say({"state": "pending", "id": jid, "words": "the summary is not made yet"}, 0)
    with os.fdopen(fd, "rb") as fh:
        raw = fh.read(p.MAX_SUMMARY_BYTES + 1)
    try:
        data = json.loads(raw) if len(raw) <= p.MAX_SUMMARY_BYTES else None
    except ValueError:
        data = None
    if not isinstance(data, dict) or data.get("id") != jid:
        return say({"state": "unknown", "id": jid, "words": "the summary file is not one this runner reads"}, 3)
    return say(data, 0)


def do_result(jid: str) -> int:
    job = JOBS / jid
    if not job.is_dir() or not inside_work(job):
        return say({"state": "unknown", "id": jid}, 3)
    if (job / "stack.json").exists():
        r = stack_result(jid)
        return say(r, 3 if r["state"] == "died" else 0)
    res = job / "result.json"
    if res.exists():
        return say(json.loads(res.read_text()), 0)
    started = json.loads((job / "job.json").read_text()).get("at", "")
    since = int(time.time() - (job / "job.json").stat().st_mtime)
    if job_alive(job):
        return say({"state": "running", "id": jid, "seconds": since, "started": started}, 0)
    return say({"state": "died", "id": jid, "seconds": since,
                "words": "the job ended without a result (killed at its time limit, or the machine restarted)"}, 3)


# ------------------------------------------------------------------------------------------------- the job

class Stop(Exception):
    def __init__(self, verdict: str, words: str, **extra):
        super().__init__(words)
        self.verdict, self.words, self.extra = verdict, words, extra


#: Where the kernel lists listening sockets, with each one's owner (Linux).
PROC = Path("/proc/net")
#: The resolvers the shield allows DNS to: install.sh fills the shield's DNS rule from this file's nameserver lines.
RESOLV = Path("/etc/resolv.conf")


def foreign_listeners(own_uid: int) -> list:
    """Every TCP socket another account is listening on, as (address, port), from /proc/net/tcp and tcp6. The
    address is only connected to, never written anywhere (results carry ports alone)."""
    found = []
    for name, family in (("tcp", socket.AF_INET), ("tcp6", socket.AF_INET6)):
        f = PROC / name
        if not f.exists():
            continue
        for ln in f.read_text().splitlines()[1:]:
            parts = ln.split()
            if len(parts) < 8 or parts[3] != "0A" or int(parts[7]) == own_uid:  # 0A: LISTEN
                continue
            hexaddr, hexport = parts[1].split(":")
            raw = bytes.fromhex(hexaddr)
            if family == socket.AF_INET:
                bound = socket.inet_ntop(family, raw[::-1])
                addr = "127.0.0.1" if bound == "0.0.0.0" else bound
            else:
                bound = socket.inet_ntop(family, b"".join(raw[i:i + 4][::-1] for i in range(0, 16, 4)))
                addr = "::1" if bound == "::" else bound
            found.append((family, addr, int(hexport, 16), bound))
    return found


def allowed_resolvers() -> set:
    """The nameserver addresses in /etc/resolv.conf, as packed bytes: the ones the shield's DNS rule names."""
    out = set()
    try:
        lines = RESOLV.read_text().splitlines()
    except OSError:
        return out
    for ln in lines:
        parts = ln.split()
        if len(parts) >= 2 and parts[0] == "nameserver":
            for family in (socket.AF_INET, socket.AF_INET6):
                try:
                    out.add(socket.inet_pton(family, parts[1].split("%")[0]))
                except OSError:
                    continue
    return out


def is_allowed_resolver(family: int, bound: str, port: int, resolvers: set) -> bool:
    """A listener that is exactly a resolver the shield allows: port 53, at its own listening address (never a
    wildcard), and that address a nameserver of /etc/resolv.conf. Anything else on 53, or at that address, is not."""
    if port != 53:
        return False
    try:
        return socket.inet_pton(family, bound) in resolvers
    except OSError:
        return False


def reachable(family: int, addr: str, port: int) -> bool:
    with socket.socket(family, socket.SOCK_STREAM) as s:
        s.settimeout(2)
        try:
            return s.connect_ex((addr, port)) == 0
        except OSError:
            return False


def wait_for_the_summary(log: Path) -> None:
    """Hold MODEL_LOCK shared for the job's run (015), waiting while a summary holds the model. No lock (no summary
    installed): nothing to wait for. Past SUMMARY_WAIT_SECONDS the job goes on, and its shield check decides."""
    try:
        fd = os.open(str(MODEL_LOCK), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return
    t0 = time.monotonic()
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            break
        except OSError:
            if time.monotonic() - t0 >= SUMMARY_WAIT_SECONDS:
                os.close(fd)
                with log.open("a") as fh:
                    fh.write("\n$ (the summary still held the model after %d s; going on to the shield check)\n"
                             % SUMMARY_WAIT_SECONDS)
                return
            time.sleep(2)
    _HELD.append(fd)
    waited = time.monotonic() - t0
    if waited >= 1:
        with log.open("a") as fh:
            fh.write("\n$ (waited %d s for the summary to unload its model)\n" % waited)


def settled_breaches() -> list:
    """shield_breaches(), checked again for SHIELD_SETTLE_SECONDS while it finds any: only a breach that stays counts."""
    end = time.monotonic() + SHIELD_SETTLE_SECONDS
    while True:
        found = shield_breaches()
        if not found or time.monotonic() >= end:
            return found
        time.sleep(3)


def shield_breaches() -> list:
    """The ports another account listens on that this account can reach: [] while the shield holds. Run inside every
    job before anything else; a breach refuses the run (the owner's ruling: no code under test reaches the demo)."""
    if not (PROC / "tcp").exists():
        return ["the listening sockets cannot be read (%s): the shield cannot be checked" % PROC]
    reached = []
    resolvers = allowed_resolvers()
    for family, addr, port, bound in foreign_listeners(os.getuid()):
        if is_allowed_resolver(family, bound, port, resolvers):
            continue  # the shield lets DNS reach it by design (its DNS rule): not a breach
        if reachable(family, addr, port):
            reached.append("port %d" % port)
    return sorted(set(reached))


def ci_value(tree: Path, pattern: str, what: str) -> str:
    """merge_slice.ci_python / ci_node_major: exactly one value in the tree's own ci.yml."""
    found = set(re.findall(pattern, (tree / ".github/workflows/ci.yml").read_text(), re.M))
    if len(found) != 1:
        raise Stop("error", "ci.yml names %d %s values; the job needs exactly one" % (len(found), what))
    return found.pop()


def lane_slot(tree: Path, lane: str = GATE_LANES[0]) -> str:
    for ln in (tree / "OspreyFlow_Build/scripts/lane_ports.tsv").read_text().splitlines():
        parts = ln.split("\t")
        if not ln.startswith("#") and len(parts) >= 2 and parts[0] == lane:
            return parts[1].strip()
    raise Stop("error", "lane_ports.tsv gives the %s lane no slot" % lane)


def closed_ports_in_use() -> list[str]:
    """The closed store ports must be closed here too: a listener on one would be a store the run could reach."""
    used = []
    for name, port in OFFLINE_PORTS.items():
        with socket.socket() as s:
            s.settimeout(1)
            if s.connect_ex(("127.0.0.1", int(port))) == 0:
                used.append("%s %s" % (name, port))
    return used


def make_tree(tree: Path, commit: str) -> None:
    """The candidate as a checkout of its own: a shared clone (its objects borrowed from the source copy, its own
    .git), so the tree resolves as its repository's root, as a CI checkout does. A worktree of the bare source copy
    made data/ the root (git's common folder data/source.git, its parent data/), and every job's temp folder lay
    inside it (run fc4d450f6f238ae2: "the token may not live inside the repository"). No remote is kept."""
    git(["clone", "-q", "--shared", "--no-checkout", str(SOURCE), str(tree)])
    git(["-C", str(tree), "remote", "remove", "origin"])
    git(["-C", str(tree), "checkout", "-q", "--detach", commit])


#: Where Docker's daemon listens on Linux. Each job checks that none of them answers this account.
DOCKER_SOCKETS = ("/var/run/docker.sock", "/run/docker.sock")


def docker_reachable() -> list:
    """The Docker sockets this account can connect to: [] while the refusal holds (no docker group). Checked in every
    job before anything runs, beside the shield, now that no DOCKER_HOST points the CLI at a dead socket."""
    open_ = []
    for path in DOCKER_SOCKETS:
        if not os.path.exists(path):
            continue
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            try:
                s.connect(path)
                open_.append(path)
            except OSError:
                pass
    return open_


def build_env(tree: Path, job: Path, lane: str = GATE_LANES[0]) -> dict:
    """ci_env's environment, from nothing of the caller's, with no Docker reachable."""
    py = ci_value(tree, r"^\s*UV_PYTHON:\s*[\"']?([0-9][0-9.]*)", "UV_PYTHON")
    major = ci_value(tree, r"node-version:\s*[\"']?(\d+)", "node-version")
    node_bin = TOOLS / "node" / ("v" + major) / "bin"
    uv_bin = TOOLS / "uv"
    for d in (node_bin, uv_bin):
        if not inside_work(d):
            raise Stop("error", "a tool folder leads outside the work folder")
    said = subprocess.run([str(node_bin / "node"), "--version"], capture_output=True, text=True) \
        if (node_bin / "node").exists() else None
    if not said or not said.stdout.startswith("v%s." % major):
        raise Stop("error", "no Node %s (ci.yml's) in the work folder's tools: install.sh puts it there" % major)
    shim = job / "no-docker"
    shim.mkdir()
    (shim / "docker").write_text("#!/bin/sh\necho 'refused: no container is started on the demo server "
                                 "(the early-warning runner)' >&2\nexit 1\n")
    (shim / "docker").chmod(0o755)
    lease = job / "lease"
    lease.mkdir()
    (lease / "no-local-stacks").write_text("the early-warning runner: no container on the demo server\n")
    home = job / "home"
    home.mkdir()
    env = {"PATH": os.pathsep.join([str(shim), str(node_bin), str(uv_bin), "/usr/local/bin", "/usr/bin", "/bin"]),
           "HOME": str(home), "LANG": "C.UTF-8", "TMPDIR": str(job / "tmp"),
           "UV_PYTHON": py, "UV_CACHE_DIR": str(CACHE / "uv"), "UV_PYTHON_INSTALL_DIR": str(TOOLS / "python"),
           "npm_config_cache": str(CACHE / "npm"), "PLAYWRIGHT_BROWSERS_PATH": str(TOOLS / "playwright"),
           "OSPREY_PORTS_SLOT": lane_slot(tree, lane), "PYTEST_DEBUG_TEMPROOT": str(job / "pytest"),
           "OSPREY_LEASE_DIR": str(lease), "TEST_WORKERS": str(p.TEST_WORKERS), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
           **OFFLINE_PORTS}
    for d in ("tmp", "pytest"):
        (job / d).mkdir()
    return env


#: DuckDB's spatial extension, fetched once over HTTPS (the shield refuses the plain HTTP DuckDB's own INSTALL uses:
#: run fc4d450f6f238ae2) for the DuckDB the tree locked, kept in the runner's cache, installed into the job's home by
#: DuckDB itself from that file and loaded (DuckDB checks the extension's signature on load). Its SHA-256 is recorded.
#: Three jobs run at once and share the cache, so each writes only files of its own there (015): a fetch into its own
#: part file, put in place whole; the unpacked extension in its own folder, removed once loaded. A shared unpacked file
#: was truncated by the next job's unpack while the first installed it (runs 1c7525d175792ee0 and d7ce43cd986f60e3:
#: "file too small to be a valid DuckDB extension"). A cached download that does not unpack is dropped, so the next
#: run fetches it again instead of every run failing on it.
DUCKDB_SPATIAL = r"""
import duckdb, gzip, hashlib, json, os, shutil, sys, tempfile, urllib.error, urllib.request, zlib
#: A client name of our own: the extension host refuses Python's default one with 403 (run fb4aa131a68d8fb4).
AGENT = "osprey-early-warning"
cache = sys.argv[1]
said = {"status": "failed"}
stage = "version"
try:
    version = said["version"] = duckdb.__version__
    stage = "platform"
    platform = said["platform"] = duckdb.sql("PRAGMA platform").fetchone()[0]
    url = "https://extensions.duckdb.org/v%s/%s/spatial.duckdb_extension.gz" % (version, platform)
    said["from"] = url
    folder = os.path.join(cache, "v" + version, platform)
    os.makedirs(folder, exist_ok=True)
    gz = os.path.join(folder, "spatial.duckdb_extension.gz")
    stage = "fetch"
    if not os.path.exists(gz):
        fd, part = tempfile.mkstemp(prefix="spatial.", suffix=".part", dir=folder)
        try:
            ask = urllib.request.Request(url, headers={"User-Agent": AGENT})
            with urllib.request.urlopen(ask, timeout=120) as answer, os.fdopen(fd, "wb") as out:
                out.write(answer.read())
            os.replace(part, gz)
        finally:
            if os.path.exists(part):
                os.remove(part)
    stage = "unpack"
    own = tempfile.mkdtemp(prefix="spatial.", dir=folder)
    try:
        ext = os.path.join(own, "spatial.duckdb_extension")
        with open(gz, "rb") as fh:
            packed = fh.read()
        try:
            data = gzip.decompress(packed)
        except (OSError, EOFError, zlib.error):
            try:
                os.remove(gz)
            except OSError:
                pass  # another job dropped it first
            raise
        with open(ext, "wb") as out:
            out.write(data)
        said["sha256"] = hashlib.sha256(packed).hexdigest()
        stage = "install"
        con = duckdb.connect()
        con.install_extension(ext)
        stage = "load"
        con.load_extension("spatial")
        said["status"] = "installed"
    finally:
        shutil.rmtree(own, ignore_errors=True)
except Exception as e:  # noqa: BLE001 - said, with its stage and reason, for the note
    said["stage"] = stage
    if isinstance(e, urllib.error.HTTPError):
        said["http_status"] = e.code  # the host's own answer, e.g. 403 (007)
    said["reason"] = " ".join(("%s: %s" % (type(e).__name__, e)).split())[:240]
print(json.dumps(said))
"""


def duckdb_spatial(core: Path, env: dict, log: Path, deadline: float) -> dict:
    """The tree's DuckDB given its spatial extension before the tests ask for it; what happened, for the result:
    installed, or failed with the stage it stopped at and why (006)."""
    py = core / ".venv/bin/python"
    if not py.is_file():
        return {"status": "not fetched", "reason": "the tree has no venv"}
    cache = CACHE / "duckdb"
    left = max(1, min(300, deadline - time.monotonic()))
    try:
        r = subprocess.run([str(py), "-c", DUCKDB_SPATIAL, str(cache)], cwd=str(core), env=env, capture_output=True,
                           text=True, timeout=left)
    except subprocess.TimeoutExpired:
        return {"status": "failed", "reason": "timed out after %d s" % left}
    with log.open("a") as fh:
        fh.write("\n$ (duckdb's spatial extension, over https)\n" + r.stdout + r.stderr)
    for ln in reversed(r.stdout.splitlines()):
        try:
            got = json.loads(ln)
        except ValueError:
            continue
        if isinstance(got, dict) and got.get("status") in ("installed", "failed"):
            return got
    tail = [ln for ln in r.stderr.splitlines() if ln.strip()]
    return {"status": "failed", "stage": "start",
            "reason": "exit %d%s" % (r.returncode, (": " + " ".join(tail[-1].split())[:240]) if tail else "")}


def run_step(cmd: list, cwd: Path, env: dict, log: Path, deadline: float) -> int:
    with log.open("a") as fh:
        fh.write("\n$ %s   (in %s)\n" % (" ".join(cmd), cwd))
        fh.flush()
        left = deadline - time.monotonic()
        if left <= 0:
            raise Stop("time-limit", "the run's time limit (%d s) was reached" % p.MAX_RUN_SECONDS)
        try:
            return subprocess.run(cmd, cwd=str(cwd), env=env, stdout=fh, stderr=subprocess.STDOUT,
                                  timeout=left).returncode
        except subprocess.TimeoutExpired:
            raise Stop("time-limit", "the run's time limit (%d s) was reached during %s" % (p.MAX_RUN_SECONDS, cmd[0]))


def apply_scan_rows(tree: Path, slice_id: str) -> list:
    """merge_slice.apply_scan_rows' change to the merge commit (the rows appended, the rows file removed, amended);
    its refusals are the Mac's merge's to make, not reproduced here."""
    rows_file = tree / ("OspreyFlow_Build/process/lanes/v062/scan_rows/%s.tsv" % slice_id)
    if not rows_file.is_file():
        return []
    lines = [ln for ln in rows_file.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    map_file = tree / "OspreyFlow_Build/scripts/slice_line/scan_map.tsv"
    text = map_file.read_text()
    map_file.write_text(text + ("" if text.endswith("\n") else "\n") + "".join(ln + "\n" for ln in lines))
    git(["add", "--", str(map_file.relative_to(tree))], cwd=tree)
    git(["rm", "-q", "--", str(rows_file.relative_to(tree))], cwd=tree)
    git(["commit", "-q", "--amend", "--no-edit"], cwd=tree)
    return lines


def mac_only_owners(tree: Path, specs: list) -> set:
    """The targets whose recipe, or the npm script it runs, names a Mac-only spec's file or folder: never counted as
    passed on this machine (012 b), whatever their exit."""
    owners = set()
    for makefile, kind in ((named_lists.BUILD_MAKEFILE, "ci"), (named_lists.CORE_MAKEFILE, "core")):
        try:
            text = (tree / makefile).read_text(encoding="utf-8")
        except OSError:
            continue
        for t in named_lists.prerequisites(text, "ci" if kind == "ci" else "check") + (["test"] if kind == "ci" else []):
            hay = []
            for _n, body in named_lists.recipe(text, t):
                hay.append(body)
                npm = named_lists._npm_script(tree, body)
                if npm:
                    hay.append(npm[1])
            joined = "\n".join(hay)
            if any(Path(s).name in joined or Path(s).parent.name in joined for s in specs):
                owners.add(t)
    return owners


def read_since(log: Path, start: int) -> list:
    with log.open("rb") as fh:
        fh.seek(start)
        return fh.read().decode(errors="replace").splitlines()


def gate(tree: Path, job: Path, log: Path, deadline: float, result: dict) -> list:
    """The container-free part of make -k ci and make test; the exit codes, the failing and the not-run names."""
    lists_file = tree / "OspreyFlow_Build/scripts/slice_line/demo_server/lists.tsv"
    if not lists_file.is_file():
        lists_file = named_lists.LISTS
    result["lists_from"] = "the candidate's" if lists_file != named_lists.LISTS else "the runner's installed copy"
    rows = {(r["kind"], r["name"]): r for r in named_lists.read_tsv(lists_file)}
    result["list_drift"] = named_lists.check(tree, lists_file, lists_file.parent / "mac_only.tsv"
                                             if (lists_file.parent / "mac_only.tsv").is_file() else named_lists.MAC_ONLY)
    not_run = result["not_run"]
    checks = result.setdefault("checks", [])  # every target make -k ci names, and make test: passed, failed or not run
    run_targets = {"ci": [], "core": []}
    for t in named_lists.derive_targets(tree):
        if t["name"] == "core-check":
            continue
        r = rows.get((t["kind"], t["name"]))
        why = None
        if r is None:
            why = {"name": t["name"], "why": "unlisted: in neither of lists.tsv's verdicts"}
        elif r["verdict"] == "not-run":
            why = {"name": t["name"], "why": r["reason"], "evidence": r["evidence"]}
        elif r["reason"] == "no-tool" and not shutil.which(t["name"]):
            why = {"name": t["name"], "why": "no-tool: %s is not installed on this machine" % t["name"]}
        if why:
            not_run["targets"].append(why)
            checks.append({"name": t["name"], "kind": t["kind"], "status": "not run", "why": why["why"]})
        else:
            run_targets[t["kind"]].append(t["name"])
    if any(r["name"] == "client-name-check" for r in not_run["targets"]):
        result["client_names"] = "not run (no client-name list on this machine)"
    listed, unlisted = named_lists.not_run_tests(tree, lists_file)
    not_run["test_files"] = [{"name": r["name"], "why": r["reason"], "evidence": r["evidence"]} for r in listed]
    not_run["test_files"] += [{"name": n, "why": "unlisted: starts a container or binds a fixed port, in neither "
                                                 "of lists.tsv's verdicts"} for n in unlisted]
    mac = named_lists.read_tsv(lists_file.parent / "mac_only.tsv" if (lists_file.parent / "mac_only.tsv").is_file()
                               else named_lists.MAC_ONLY, ("name", "snapshots", "evidence"))
    not_run["mac_only"] = [{"name": r["name"], "why": "not run on this machine: its snapshots are another platform's (%s)"
                            % r["evidence"]} for r in mac]
    not_run["live_step"] = "not run: the live step needs the test stacks (stack_lease.sh), which this machine does not hold"
    env = build_env(tree, job, result.get("lane", GATE_LANES[0]))
    core = tree / "OspreyFlow_Core"
    build = tree / "OspreyFlow_Build"
    if (core / ".venv").exists() or (core / "node_modules").exists():
        raise Stop("error", "the candidate already has a .venv or node_modules: the job builds its own, fresh")
    for cmd in (["uv", "sync", "--frozen"], ["npm", "ci", "--no-audit", "--no-fund"]):
        if run_step(cmd, core, env, log, deadline) != 0:
            raise Stop("error", "building the environment failed at %s (a download, or the lock)" % " ".join(cmd[:2]))
    said = subprocess.run([str(core / ".venv/bin/python"), "--version"], capture_output=True, text=True)
    if not (said.stdout + said.stderr).strip().startswith("Python %s." % env["UV_PYTHON"]):
        raise Stop("error", "the venv runs %s, not ci.yml's Python %s" % ((said.stdout + said.stderr).strip(), env["UV_PYTHON"]))
    result["duckdb_spatial"] = duckdb_spatial(core, env, log, deadline)
    used = closed_ports_in_use()
    if used:
        raise Stop("error", "a closed store port is listening on this machine (%s): nothing was run" % ", ".join(used))
    ignores = [x["name"] for x in not_run["test_files"]]
    # -rfEs: pytest's own default summary (f, E: each failed test and error named) and the skips' reasons. A bare -rs
    # replaces the default, and the failing tests went unnamed (run fc4d450f6f238ae2, PL11).
    env_test = {**env, "PYTEST_ADDOPTS": " ".join(["-rfEs"] + ["--ignore=../%s" % n for n in ignores])}
    codes = []
    result["passed_targets"] = []
    mac_owners = mac_only_owners(tree, [r["name"] for r in mac])
    # One make per target, so each target's own exit is known and recorded (009: the list a script reads), where one
    # make -k over them all gave a single exit for the lot.
    steps = [("make " + t, t, "ci", ["make", t]) for t in run_targets["ci"]]
    steps += [("make -C ../OspreyFlow_Core " + t, t, "core", ["make", "-C", "../OspreyFlow_Core", t])
              for t in run_targets["core"]]
    steps.append(("make test", "test", "test", ["make", "test"]))
    for name, target, kind, cmd in steps:
        start = log.stat().st_size if log.exists() else 0
        t0 = time.monotonic()
        code = run_step(cmd, build, env_test, log, deadline)
        lines = read_since(log, start)
        seconds = int(time.monotonic() - t0)
        codes.append({"step": name, "exit": code, "seconds": seconds})
        seen = len(result["failing"]["tests"])
        server_skips = 0  # docker calls the repository's guard skipped inside this target (the Mac reruns only make test's)
        pending = []  # failing tests seen since the last failed target: make -k runs the targets one after another
        by_target = result["failing"].setdefault("by_target", {})
        for ln in lines:
            m = MAKE_ERROR.match(ln)
            if m:
                if m.group(1) not in result["failing"]["targets"]:
                    result["failing"]["targets"].append(m.group(1))
                names = by_target.setdefault(m.group(1), [])
                names += [n for n in pending if n not in names]
                pending = []
                continue
            m = FAILED_TEST.match(ln)
            if m:
                n = (m.group(1) or m.group(2) or "").strip()
                if n and n not in result["failing"]["tests"]:
                    result["failing"]["tests"].append(n)
                if n and n not in pending:
                    pending.append(n)
            m = DOCKER_SKIP.match(ln)
            if m:
                server_skips += 1
            if m and m.group(1) not in not_run["docker_skipped"]:
                not_run["docker_skipped"].append(m.group(1))
        if code != 0 and target != "test" and target not in result["failing"]["targets"]:
            result["failing"]["targets"].append(target)  # failed, whether or not make's own error line named it
        if pending:  # failing tests with no failed target after them: named under the target, or the step
            names = by_target.setdefault(target if code != 0 and target != "test" else "(%s)" % name, [])
            names += [n for n in pending if n not in names]
        ok = code == 0 and len(result["failing"]["tests"]) == seen and not any(
            MAKE_ERROR.match(ln) for ln in lines)
        checks.append({"name": target, "kind": kind, "status": "passed" if ok else "failed", "exit": code,
                       "seconds": seconds})
        # 012 b: named passed only when it ran to completion and passed with nothing skipped inside it but what the
        # Mac reruns (make test's docker-guarded and not-run files), and when it owns no Mac-only spec
        if ok and (target == "test" or not server_skips) and target not in mac_owners:
            result["passed_targets"].append(target)
    return codes


def run_job(jid: str) -> int:
    job = JOBS / jid
    if not SHA.match("0" * 24 + jid) or not job.is_dir() or not inside_work(job):
        return 2
    (job / "job.pid").write_text(str(os.getpid()))
    meta = json.loads((job / "job.json").read_text())
    log = job / "log"
    t0 = time.monotonic()
    deadline = t0 + p.MAX_RUN_SECONDS
    tree = job / "tree"
    stack = meta.get("stack") or [{"slice": meta["slice"], "tip": meta["tip"]}]
    result = {"state": "done", "id": jid, "slice": meta["slice"], "main": meta["main"], "tip": meta["tip"],
              "stack": stack, "position": meta.get("position", 1), "of": meta.get("of", 1),
              "group": meta.get("group", [jid]), "lane": meta.get("lane", GATE_LANES[0]),
              **({"stack_id": meta["stack_id"]} if meta.get("stack_id") else {}),
              "runner_version": p.RUNNER_VERSION, "advice": "advice only; the Mac's merge run is the gate",
              "failing": {"targets": [], "tests": []},
              "not_run": {"targets": [], "test_files": [], "docker_skipped": [], "mac_only": [], "live_step": ""},
              "client_names": "not run (no client-name list on this machine)"}
    try:
        wait_for_the_summary(log)
        breaches = settled_breaches()
        if breaches:
            raise Stop("error", "the shield does not hold: this account reached %d port(s) another account listens on "
                       "(%s); nothing was run" % (len(breaches), ", ".join(breaches[:10])))
        if docker_reachable():
            raise Stop("error", "Docker's socket answers this account (%s): nothing was run" % ", ".join(docker_reachable()))
        make_tree(tree, meta["main"])
        result["scan_rows"], result["merges"] = [], []
        for i, s in enumerate(stack):  # in merge order, each as the Mac's merge makes it: --no-ff, then its scan rows
            msg = "merge: slice %s (early warning) %s\n\nSlice-Merge: %s\nSlice-Tip: %s" % (
                s["slice"], s["tip"][:10], s["slice"], s["tip"])
            m = subprocess.run(["git", "merge", "--no-ff", "-q", "-m", msg, s["tip"]], cwd=str(tree),
                               capture_output=True, text=True, env=git_env())
            if m.returncode != 0:
                files = git(["diff", "--name-only", "--diff-filter=U"], cwd=tree, check=False).splitlines()
                before = [x["slice"] for x in stack[:i]]
                raise Stop("conflict", "the slice does not merge cleanly onto main" if not before else
                           "%s does not merge cleanly onto main with %s merged first" % (s["slice"], ", ".join(before)),
                           conflicts=files[:20], conflict_slice=s["slice"])
            result["scan_rows"] += apply_scan_rows(tree, s["slice"])
            result["merges"].append(git(["rev-parse", "HEAD"], cwd=tree))
        result["merge"] = result["merges"][-1]
        result["tree"] = git(["rev-parse", "HEAD^{tree}"], cwd=tree)
        result["steps"] = GATE(tree, job, log, deadline, result)
        red = any(s["exit"] != 0 for s in result["steps"]) or result["failing"]["targets"] or result["failing"]["tests"]
        result["verdict"] = "fail" if red else "pass"
    except Stop as e:
        result.update(verdict=e.verdict, words=e.words, **e.extra)
    except Exception as e:  # noqa: BLE001 - any other fault is the runner's, never the slice's
        result.update(verdict="error", words="the runner failed: %s" % type(e).__name__)
    result["seconds"] = int(time.monotonic() - t0)
    result["finished"] = now()
    result["usage"] = own_usage()
    try:
        git(["-C", str(SOURCE), "update-ref", "refs/heads/main", meta["main"]])
        for ref in git(["-C", str(SOURCE), "for-each-ref", "--format=%(refname)", "refs/early/%s/" % jid],
                       check=False).splitlines():
            git(["-C", str(SOURCE), "update-ref", "-d", ref], check=False)
        result["holds_main"] = meta["main"]
    except Exception:  # noqa: BLE001
        pass
    clean_job(job, tree)  # first: a result means its work is gone, and the next job may start (run 7's race)
    tmp = job / "result.json.tmp"
    tmp.write_text(json.dumps(result, indent=1, sort_keys=True))
    os.replace(str(tmp), str(job / "result.json"))
    hand_over(job, result)  # after the result: nothing the summary does can hold it back
    prune_jobs()
    return 0


def hand_over(job: Path, result: dict) -> None:
    """A red run's log and result, copied for the summary account (010). Never fails the run."""
    try:
        if result.get("verdict") != "fail" or not HANDOFF.is_dir():
            return
        dest = HANDOFF / job.name
        dest.mkdir(mode=0o750)
        for name in ("log", "result.json"):
            if (job / name).is_file():
                shutil.copyfile(str(job / name), str(dest / name))
                os.chmod(str(dest / name), 0o640)
        os.chmod(str(dest), 0o750)
    except Exception:  # noqa: BLE001 - a summary is advice: its hand-over never stops a result
        pass


def own_usage() -> dict:
    """What this job used, from its own cgroup (cgroup v2): its peak memory and its processor time, so the caps can be
    set from measurements (009); {} where the machine has no such files (the Mac)."""
    try:
        rel = Path("/proc/self/cgroup").read_text().strip().splitlines()[0].split("::", 1)[1]
        base = Path("/sys/fs/cgroup") / rel.lstrip("/")
        used = {"memory_peak_bytes": int((base / "memory.peak").read_text().strip())}
        for ln in (base / "cpu.stat").read_text().splitlines():
            k, _, v = ln.partition(" ")
            if k == "usage_usec":
                used["cpu_seconds"] = int(v) // 1000000
        return used
    except (OSError, ValueError, IndexError):
        return {}


def clean_job(job: Path, tree: Path) -> None:
    """The job's own work removed after the run and before its result is written (the disk cap): the tree, its
    environment, its temp folders. A failure here never keeps the result from being written."""
    try:
        git(["-C", str(SOURCE), "worktree", "remove", "--force", str(tree)], check=False)
        git(["-C", str(SOURCE), "worktree", "prune"], check=False)
        for d in ("tree", "home", "tmp", "pytest", "lease", "no-docker", "line"):
            shutil.rmtree(str(job / d), ignore_errors=True)
        if (job / "log").exists() and (job / "log").stat().st_size > 4 << 20:
            data = (job / "log").read_bytes()[-(4 << 20):]
            (job / "log").write_bytes(data)
    except Exception:  # noqa: BLE001
        pass


def prune_jobs() -> None:
    """Only the last KEEP_JOBS jobs' results and logs are kept."""
    jobs = sorted((d for d in JOBS.iterdir() if (d / "result.json").exists()), key=lambda d: d.stat().st_mtime)
    for old in jobs[:-KEEP_JOBS]:
        shutil.rmtree(str(old), ignore_errors=True)
    for d in JOBS.iterdir():  # a stack's own folder goes with the last of its members
        try:
            if (d / "stack.json").exists() and not any((JOBS / j).exists()
                                                       for j in json.loads((d / "stack.json").read_text())["ids"]):
                shutil.rmtree(str(d), ignore_errors=True)
        except (OSError, ValueError, KeyError):
            pass
    if HANDOFF.is_dir():  # a hand-over goes once its summary is made, or its job is gone
        for d in HANDOFF.iterdir():
            if not d.is_dir() or d.is_symlink():
                continue  # model.lock (015), and anything not a hand-over
            if (SUMMARIES / (d.name + ".json")).exists() or not (JOBS / d.name).is_dir():
                shutil.rmtree(str(d), ignore_errors=True)


#: The job's launcher and its gate. Nothing in this file replaces either, and nothing here reads a variable that could:
#: the Mac's tests replace them only in a wrapper of their own under tests/, which install.sh never copies.
LAUNCH = launch_capped
GATE = gate


def main(argv: list) -> int:
    if len(argv) == 3 and argv[1] == "_job":
        return run_job(argv[2])
    if len(argv) != 1:
        return refuse("shape", " ".join(argv[1:]))
    received = os.environ.get("SSH_ORIGINAL_COMMAND")  # read once
    verb, arg = p.parse_command(received)
    if verb is None:
        return refuse(arg, received)
    if verb == "run":
        return do_run(received)
    if verb == "stack":
        return do_run(received, arg.split())
    if verb == "summary":
        return do_summary(arg)
    return do_result(arg)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
