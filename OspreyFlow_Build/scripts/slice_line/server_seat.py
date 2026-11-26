"""017-2, the Mac's side (the owner's answers of 24 and 25 November 2026): a builder or verifier run on the build
account, where the dial says so. The Mac sends `start <ID> <seat>` through the build account's forced command, with
one tar on standard input (in.bundle: main's tip and lane/slice-<ID>; order.json: the seat, part, round, prompt,
model, effort, account and the records the seat reads), asks `status <ID> <seat>` every SEAT_POLL_SECONDS, and when
the seat is done takes its work only from the backup repository, never over SSH: the part's branch and the clone's
seat-results branch, fetched into server_gate's cache of the backup. The result must be the runner's own for this
part, seat and run; a builder's branch must hold exactly the tip the result names, and the Mac's branch is moved
there only by fast-forward. The seat's records (the Stop hook's test record, a red stop) are copied into the part's
records, each marked with the run it came from, and the session's result is handed back as launch() hands it back.

Paths in the prompt are the Mac's; the order carries the Mac's checkout and worktree, and run_seat.py --order on the
server puts its own trees in their place.
"""
from __future__ import annotations

import io
import json
import re
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

import common as c
import early_warning as ew
import server_gate as sg

WHERE = ("mac", "server")
SEAT_POLL_SECONDS = 60
#: How long the Mac waits for the backup timer to push a finished seat's result (minutes).
BACKUP_WAIT_MINUTES = 30
BACKUP_POLL_SECONDS = 30
STATUS_MISSES = 5
SEAT_RESULTS = "seat-results"
RUN_ID = re.compile(r"\A[0-9a-f]{16}\Z")
#: Records the server's seat writes that the Mac takes into the part's records (the Stop hook's and the guard's);
#: ran.json and session.json are the runner's, read here and not copied.
TAKEN = re.compile(r"\A(tests-[0-9a-f]{40}|red_stop)\.json\Z")


class ServerSeatError(Exception):
    """The server's seat could not be run or its work not taken back: in words, nothing of the Mac's changed."""


def where(seat_settings: dict) -> str:
    """The dial's `where:` for this seat: mac (the default) or server."""
    w = seat_settings.get("where", "mac")
    if w not in WHERE:
        raise ServerSeatError(f"the dial's where: {w!r} is neither mac nor server")
    return w


def order_tar(bundle: Path, order: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data in (("in.bundle", bundle.read_bytes()), ("order.json", json.dumps(order).encode())):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def setting() -> dict:
    if not ew.BUILD_SETTING.is_file():
        raise ServerSeatError("no build setting: the server's seats need the build account's key (build-server.json)")
    try:
        return ew.load_setting(ew.BUILD_SETTING)
    except ew.Refused:
        raise ServerSeatError("the build setting is not usable") from None


def start(bs: dict, slice_id: str, seat: str, branch: str, order: dict) -> str:
    with tempfile.TemporaryDirectory(prefix="server-seat-") as d:
        b = Path(d) / "in.bundle"
        ew.make_bundle(branch, b, True)
        f = Path(d) / "order.tar"
        f.write_bytes(order_tar(b, order))
        with f.open("rb") as fh:
            code, data = ew.ssh(bs, ["start", slice_id, seat], stdin=fh, timeout=900)
    if not data or data.get("state") != "started" or not RUN_ID.match(str(data.get("id", ""))):
        why = (data or {}).get("reason") or f"no answer (ssh exit {code})"
        raise ServerSeatError(f"the build account did not start the {seat} of {slice_id}: {why}")
    return data["id"]


def wait(bs: dict, slice_id: str, seat: str, rid: str) -> dict:
    misses = 0
    while True:
        time.sleep(SEAT_POLL_SECONDS)
        code, st = ew.ssh(bs, ["status", slice_id, seat], timeout=120)
        if not st:
            misses += 1
            if misses >= STATUS_MISSES:
                raise ServerSeatError(f"the build account did not answer for the {seat} of {slice_id} "
                                      f"{STATUS_MISSES} times running (ssh exit {code}); the seat may still run there")
            continue
        misses = 0
        if st.get("id") != rid:
            raise ServerSeatError(f"the build account's {seat} of {slice_id} is another run ({st.get('id')}, not {rid})")
        if st.get("state") in ("done", "failed", "stopped"):
            return st


def fetch(refs: list[str]) -> None:
    url = sg.build_backup()
    if not url:
        raise ServerSeatError(f"no backup repository named (the owner's file {sg.BUILD_BACKUP})")
    cache = c.DATA / sg.BUILD_CACHE
    if not cache.is_dir():
        subprocess.run(["git", "init", "-q", "--bare", str(cache)], capture_output=True, text=True, check=True)
    p = sg.build_git(["fetch", "-q", "--no-tags", "--", url, *[f"+refs/heads/{r}:refs/heads/{r}" for r in refs]])
    if not p or p.returncode != 0:
        raise ServerSeatError("the backup repository could not be fetched")


def result_from_backup(slice_id: str, seat: str, rid: str, branch: str) -> dict:
    """The seat's result as the backup holds it, once the backup timer has pushed it."""
    path = f"seats/{slice_id}/{seat}-{rid}.json"
    end = time.monotonic() + BACKUP_WAIT_MINUTES * 60
    while True:
        try:
            fetch([SEAT_RESULTS])
            p = sg.build_git(["show", f"refs/heads/{SEAT_RESULTS}:{path}"], 30)
            if p and p.returncode == 0:
                break
        except ServerSeatError:
            pass
        if time.monotonic() >= end:
            raise ServerSeatError(f"the backup repository has no result of the {seat} of {slice_id} (run {rid}) after "
                                  f"{BACKUP_WAIT_MINUTES} minutes: the backup timer has not pushed it")
        time.sleep(BACKUP_POLL_SECONDS)
    try:
        r = json.loads(p.stdout)
    except ValueError:
        raise ServerSeatError("the seat's result in the backup is not JSON") from None
    if seat == "builder":
        try:
            fetch([branch])  # the branch is checked against the result's tip in take_branch
        except ServerSeatError:
            pass
    if not isinstance(r, dict) or r.get("runner") != sg.BUILD_RUNNER or (r.get("id"), r.get("slice"), r.get("seat")) \
            != (rid, slice_id, seat):
        raise ServerSeatError(f"the backup's result is not the runner's own for the {seat} of {slice_id} (run {rid})")
    return r


def take_branch(r: dict, branch: str, tree: Path) -> None:
    """The builder's work, from the backup's copy of the branch: it must be the tip the result names, and the Mac's
    worktree takes it by fast-forward only."""
    tip = str(r.get("tip", ""))
    have = sg.build_git(["rev-parse", "-q", "--verify", f"refs/heads/{branch}"], 30)
    if not re.fullmatch(r"[0-9a-f]{40}", tip) or not have or have.stdout.strip() != tip:
        raise ServerSeatError(f"the backup's {branch} is not the tip the seat's result names ({tip[:10]})")
    cache = str(c.DATA / sg.BUILD_CACHE)
    c.git(["fetch", "-q", "--no-tags", cache, f"refs/heads/{branch}"], tree)
    p = subprocess.run(["git", "merge", "-q", "--ff-only", tip], cwd=str(tree), capture_output=True, text=True)
    if p.returncode != 0:
        raise ServerSeatError(f"the Mac's {branch} does not fast-forward to the server's {tip[:10]}: "
                              f"{p.stderr.strip()[:200]}")


def take_records(slice_id: str, r: dict) -> list[str]:
    taken = []
    for name, value in sorted((r.get("records") or {}).items()):
        if TAKEN.match(name) and isinstance(value, dict):
            c.write_json(c.rec_dir(slice_id) / name, {**value, "from_server": r["id"]})
            taken.append(name)
    return taken


def run(slice_id: str, seat: str, rnd: int, prompt: str, model: str, effort: str, account: str, branch: str,
        tree: Path, records: dict) -> dict:
    """The seat on the server, start to finish; the session's result, as launch() gives it."""
    bs = setting()
    order = {"seat": seat, "slice": slice_id, "round": rnd, "prompt": prompt, "model": model, "effort": effort,
             "account": account, "records": {**records, "mac.json": {"repo": str(c.REPO), "tree": str(tree)}}}
    rid = start(bs, slice_id, seat, branch, order)
    print(f"{slice_id}: the {seat} runs on the build account (run {rid}); asking its status every "
          f"{SEAT_POLL_SECONDS} s.", flush=True)
    st = wait(bs, slice_id, seat, rid)
    r = result_from_backup(slice_id, seat, rid, branch)
    if seat == "builder":
        take_branch(r, branch, tree)
    take_records(slice_id, r)
    session = r.get("session") if isinstance(r.get("session"), dict) else {}
    if not session:  # never handed to launch_seat as an empty session: that would read as the account's refusal
        raise ServerSeatError(f"the {seat} of {slice_id} ended {st.get('state')} on the build account without a "
                              f"session's result (run {rid}, exit {r.get('exit')}{'; ' + st['words'] if st.get('words') else ''}); "
                              f"its log is seats/{slice_id}-{seat}/seat.log in the build account's data")
    return {**session, "server_run": rid}
