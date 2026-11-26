"""The merge's full gate on the build account (the owner's ask of 26 November 2026, item 2), behind the owner's own
switch (gate_on_build, "on" only; off as built).

At the merge's step 5, when the early warning's green does not already count, the Mac sends the merge commit it made
(and will land) to the build account's forced command, `gate <ID>`, as a bundle of exactly HEAD. The build account
runs today's full gate on exactly that commit (build_server/runner.py's gate job: each `ci` prerequisite but
client-name-check, each of Core's `check` targets, make test, in CI's environment) and commits its result and log on
its build-results branch; the backup timer pushes them. The Mac reads them only from the backup repository, as for the
container checks, and takes the result only when it is the runner's own, for this part, this run, exactly the commit
sent, its first parent the base the Mac merged onto, and its tree the Mac's own. Then:

- a pass: the Mac runs only what the build account did not prove (server_gate.remainder, as for a counted early
  warning: client-name-check always, anything not run or skipped there, and the live step), then lands as before.
- a fail: its log is added to the merge's log, and the merge is refused to the builder as a red full gate is, unless
  the failure was only a network step (merge_slice.network_only), when the Mac runs the whole gate itself.
- anything else (the switch off, no build setting or backup, the call refused, no result in GATE_WAIT_MINUTES, an
  error, a result that is not exactly this commit's): the Mac runs today's whole gate itself, as now, and the merge's
  log says why.

Main still moves only on the Mac, only by fast-forward, and only to the commit tested (land()); nothing here changes
what the gate checks: the targets are the commit's own Makefiles', run there or here.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

import common as c
import server_gate as sg

SWITCH = "gate_on_build"
#: How long the Mac waits for the gate's result in the backup repository: the gate's own time (41 minutes median on
#: the Mac, 24 to 26 November), the build account's queue, and the backup timer's push.
GATE_WAIT_MINUTES = 150
POLL_SECONDS = 60
HELD = "build-gate-held.json"
RUN_ID = re.compile(r"\A[0-9a-f]{16}\Z")


class NotOnBuild(Exception):
    """Why the build account's gate is not used for this merge: the Mac runs the whole gate itself."""


def on() -> bool:
    f = c.DATA / SWITCH
    try:
        return not f.is_symlink() and f.is_file() and f.read_text().strip() == "on"
    except OSError:
        return False


def bundle(after: Path, dest: Path, base: str) -> None:
    """The merge commit as HEAD, from the merge tree; less what the build account already holds (its main, when it is
    an ancestor of the base), so the next bundle is small."""
    held = (c.read_json(c.DATA / HELD) or {}).get("main", "")
    args = ["bundle", "create", "-q", str(dest), "HEAD"]
    if re.fullmatch(r"[0-9a-f]{40}", held or "") and \
            subprocess.run(["git", "merge-base", "--is-ancestor", held, base], cwd=after).returncode == 0:
        args.append(f"^{held}")
    c.git(args, after)


def send(slice_id: str, after: Path, base: str) -> str:
    import early_warning as ew  # here, not at the top: merge_slice.py imports this module, and the merge must not
    #                             depend on the early warning's script loading
    try:
        bs = ew.load_setting(ew.BUILD_SETTING) if ew.BUILD_SETTING.is_file() else None
    except ew.Refused:
        bs = None
    if not bs:
        raise NotOnBuild("no usable build setting (build-server.json)")
    with tempfile.TemporaryDirectory(prefix="build-gate-") as d:
        b = Path(d) / "gate.bundle"
        bundle(after, b, base)
        with b.open("rb") as fh:
            code, said = ew.ssh(bs, ["gate", slice_id], stdin=fh, timeout=900)
    if not said or said.get("state") != "started" or not RUN_ID.match(str(said.get("id", ""))):
        raise NotOnBuild(f"the build account did not start the gate: {(said or {}).get('reason') or f'ssh exit {code}'}")
    if re.fullmatch(r"[0-9a-f]{40}", str(said.get("holds_main", ""))):
        c.write_json(c.DATA / HELD, {"main": said["holds_main"], "at": c.now()})
    return said["id"]


def fetched(path: str) -> str | None:
    p = sg.build_git(["show", f"refs/heads/{sg.BUILD_BRANCH}:{path}"], 60)
    return p.stdout if p and p.returncode == 0 else None


def fetch() -> bool:
    url = sg.build_backup()
    if not url:
        raise NotOnBuild(f"no backup repository named (the owner's file {sg.BUILD_BACKUP})")
    cache = c.DATA / sg.BUILD_CACHE
    if not cache.is_dir() and subprocess.run(["git", "init", "-q", "--bare", str(cache)],
                                             capture_output=True).returncode != 0:
        raise NotOnBuild("the backup's cache could not be made")
    p = sg.build_git(["fetch", "-q", "--no-tags", "--", url,
                      f"+refs/heads/{sg.BUILD_BRANCH}:refs/heads/{sg.BUILD_BRANCH}"])
    return bool(p and p.returncode == 0)


def wait(slice_id: str, merged: str, rid: str) -> dict:
    """The gate's result for exactly this commit and run, once the backup holds it."""
    path = f"gates/{slice_id}/{merged}.json"
    end = time.monotonic() + GATE_WAIT_MINUTES * 60
    while True:
        if fetch():
            text = fetched(path)
            if text is not None:
                try:
                    r = json.loads(text)
                except ValueError:
                    raise NotOnBuild("the gate's result in the backup is not JSON") from None
                if isinstance(r, dict) and r.get("id") == rid:
                    return r
        if time.monotonic() >= end:
            raise NotOnBuild(f"the backup repository holds no result of run {rid} after {GATE_WAIT_MINUTES} minutes")
        time.sleep(POLL_SECONDS)


def mismatch(r: dict, slice_id: str, rid: str, merged: str, base: str, tree: str) -> str | None:
    """Why the result does not stand for this merge (None when it does)."""
    if r.get("runner") != sg.BUILD_RUNNER or r.get("kind") != "gate" or r.get("state") != "done":
        return "it is not the build runner's finished gate"
    if (r.get("id"), r.get("slice")) != (rid, slice_id):
        return f"it is run {r.get('id')} of {r.get('slice')}, not run {rid} of {slice_id}"
    if r.get("commit") != merged:
        return f"it tested {str(r.get('commit'))[:10]}, not the merge commit {merged[:10]}"
    if r.get("main") != base:
        return f"its main is {str(r.get('main'))[:10]}, not the base {base[:10]}"
    if r.get("tree") != tree:
        return f"its tree is {str(r.get('tree'))[:12]}, not the merge's {tree[:12]}"
    if r.get("verdict") not in ("pass", "fail"):
        return f"it ended {r.get('verdict')}: {r.get('words') or 'no words'}"
    if not isinstance(r.get("passed_targets"), list):
        return "it names no target it ran and passed"
    return None


def run(slice_id: str, base: str, merged: str, after: Path, log: Path) -> dict:
    """{"used": False, "why"} when the Mac runs the whole gate itself; else {"used": True, "run_id", "verdict", and for
    a pass the remainder's "plan"; for a fail the log text}. Never raises: every reason not to use it is said."""
    if not on():
        return {"used": False, "why": f"the owner's switch ({SWITCH}) is off"}
    t0 = time.monotonic()
    try:
        rid = send(slice_id, after, base)
        log.open("a").write(f"\nthe merge's full gate runs on the build account (run {rid}, commit {merged[:10]}); "
                            "its result is read from the backup repository\n")
        r = wait(slice_id, merged, rid)
        tree = c.git(["rev-parse", "HEAD^{tree}"], after)
        why = mismatch(r, slice_id, rid, merged, base, tree)
        if why:
            raise NotOnBuild(f"the build account's gate result does not stand for this merge: {why}")
    except NotOnBuild as e:
        log.open("a").write(f"\nNOT ON THE BUILD ACCOUNT: {e}. The Mac runs the whole gate itself.\n")
        return {"used": False, "why": str(e)}
    out = {"used": True, "run_id": rid, "verdict": r["verdict"], "seconds": round(time.monotonic() - t0),
           "server_seconds": r.get("seconds"), "steps": r.get("steps") or []}
    if r["verdict"] == "fail":
        text = fetched(str(r.get("log") or "")) or ""
        out.update(log=text, failing=r.get("failing") or {})
        return out
    out["plan"] = sg.remainder(r, after, log.with_suffix(".build-remainder.mk"))
    log.open("a").write(f"\nthe build account's gate (run {rid}) passed: taken {', '.join(out['plan']['taken'])}; "
                        f"the Mac runs: {'; '.join(out['plan']['mac']) or 'nothing of the full gate'}\n")
    return out
