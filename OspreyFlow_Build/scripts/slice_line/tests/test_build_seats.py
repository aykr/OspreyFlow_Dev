"""017-2 (the owner's answers of 24 and 25 November 2026): seats on the server, the build account's side. The Mac
starts, stops and asks the status of a seat through the forced command only,
`start|stop|status <ID> builder|verifier`; no shell. `start` takes one tar on standard input, of exactly two regular files: in.bundle (main's tip and
lane/slice-<ID>, as `checks` takes) and order.json (the seat, the part, the round, the prompt, the model, the effort,
the account and the records the seat reads; nothing else). The runner makes the seat's trees in its own clone (the
builder's worktree on lane/slice-<ID>, the verifier's detached at the tip, main's tree beside them) and starts the
seat in a detached tmux session, one seat per part at a time. The seat's work comes back only through the backup
repository: the builder's commits on the clone's lane/slice-<ID>, and its result and records committed by plumbing on
the clone's seat-results branch, both for the backup timer to push. Nothing but "started", a status or a refusal is
ever answered over SSH.

The seat itself is stood in (runner.SEAT_RUN, set by the wrapper): it notes where it ran, and a builder commits and
writes a test record, as the Stop hook would.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
import time

import pytest

from test_build_runner import KEEP, bundle, bw, forced, sh  # noqa: F401  (bw is a fixture)

FAKE_SEAT = r"""import json, os, subprocess, sys, time
order_path = sys.argv[-1]
d = os.path.dirname(order_path)
o = json.load(open(order_path))
cfg = json.load(open(os.environ["SEAT_FAKE"])) if os.environ.get("SEAT_FAKE") else {}
head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
json.dump({"cwd": os.getcwd(), "head": head,
           "prompt": o["prompt"], "records": sorted(os.listdir(os.path.join(d, "records")))},
          open(os.path.join(d, "records", "ran.json"), "w"))
time.sleep(cfg.get("sleep", 0))
if o["seat"] == "builder" and cfg.get("commit", True):
    open("built.txt", "w").write("round %d\n" % o["round"])
    subprocess.run(["git", "add", "built.txt"], check=True)
    subprocess.run(["git", "commit", "-qm", "S1: built on the server"], check=True)
    tip = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    json.dump({"green": True, "tip": tip}, open(os.path.join(d, "records", "tests-%s.json" % tip), "w"))
sys.exit(cfg.get("exit", 0))
"""
GIT_ID = {"GIT_AUTHOR_NAME": "seat", "GIT_AUTHOR_EMAIL": "seat@t.invalid", "GIT_COMMITTER_NAME": "seat",
          "GIT_COMMITTER_EMAIL": "seat@t.invalid", "GIT_CONFIG_GLOBAL": "/dev/null"}


def order(seat="builder", part="S1", **over):
    o = {"seat": seat, "slice": part, "round": 2, "prompt": "You are the builder for slice S1.", "model": "opus",
         "effort": "high", "account": "sol", "records": {"frozen.json": {"checks": "make test"}, "state.json": {}}}
    o.update(over)
    return o


def tar(members: dict, links=()) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        for name in links:
            info = tarfile.TarInfo(name)
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tf.addfile(info)
    return buf.getvalue()


def payload(w, o=None, refs=None, extra=None):
    m = {"in.bundle": bundle(w, *(refs or ())), "order.json": json.dumps(o or order()).encode()}
    m.update(extra or {})
    return tar(m)


def seat_world(w, **cfg):
    fake = w["tmp"] / "fake_seat.py"
    fake.write_text(FAKE_SEAT)
    if cfg or not (w["tmp"] / "seat.json").exists():                       # a status call leaves them be
        (w["tmp"] / "seat.json").write_text(json.dumps(cfg))
    return {"keep": KEEP + [*GIT_ID, "SEAT_FAKE"], "seat_run": [sys.executable, str(fake)]}


def call(w, cmd, stdin=b"", **cfg):
    return forced(w, cmd, stdin, harness=seat_world(w, **cfg), SEAT_FAKE=str(w["tmp"] / "seat.json"), **GIT_ID)


def status(w, seat="builder", part="S1"):
    code, said = call(w, f"status {part} {seat}")
    assert code == 0, said
    return said


def until(w, state, seat="builder", seconds=60):
    end = time.monotonic() + seconds
    while True:
        s = status(w, seat)
        if s["state"] == state:
            return s
        assert time.monotonic() < end and s["state"] in ("running", state), s
        time.sleep(0.2)


def on(w, ref, path=None):
    return sh(["git", "show", f"{ref}:{path}"] if path else ["git", "rev-parse", ref], w["clone"], w["env"])


def results(w):
    files = sh(["git", "ls-tree", "-r", "--name-only", "refs/heads/seat-results"], w["clone"], w["env"]).split()
    return [json.loads(on(w, "refs/heads/seat-results", f)) for f in files]


# ------------------------------------------------------------------ a seat runs, and its work comes back by the clone


def test_a_builder_runs_in_its_worktree_and_its_work_and_records_are_committed_for_the_backup(bw):
    w = bw
    assert status(w)["state"] == "none"
    code, said = call(w, "start S1 builder", payload(w))
    assert code == 0 and said["state"] == "started" and said["seat"] == "builder", said
    done = until(w, "done")
    tip = on(w, "refs/heads/lane/slice-S1")
    assert tip != w["tip"] and done["tip"] == tip and done["main"] == w["main"], done
    assert sh(["git", "log", "-1", "--format=%s", tip], w["clone"], w["env"]) == "S1: built on the server"
    assert sh(["git", "rev-parse", f"{tip}~1"], w["clone"], w["env"]) == w["tip"]        # on the Mac's tip
    (r,) = results(w)
    assert r["seat"] == "builder" and r["tip_before"] == w["tip"] and r["tip"] == tip and r["exit"] == 0, r
    assert r["records"][f"tests-{tip}.json"] == {"green": True, "tip": tip}                 # the Stop hook's record
    ran = r["records"]["ran.json"]
    assert ran["cwd"].endswith("/S1-builder/wt") and ran["prompt"] == order()["prompt"], ran
    assert ran["head"] == w["tip"]                                                         # it began on the tip
    assert ran["records"] == ["frozen.json", "state.json"]                                 # the Mac's records, given
    assert said["id"] == r["id"] and set(said) == {"state", "slice", "seat", "id"}          # nothing else answered


def test_a_verifier_runs_on_the_tip_detached_and_leaves_the_branch_as_it_was(bw):
    w = bw
    code, said = call(w, "start S1 verifier", payload(w, order("verifier")))
    assert code == 0, said
    done = until(w, "done", "verifier")
    assert done["tip"] == w["tip"]
    assert sh(["git", "rev-parse", "-q", "--verify", "refs/heads/lane/slice-S1"], w["clone"], w["env"],
              check=False) in ("", w["tip"])
    (r,) = results(w)
    assert r["seat"] == "verifier" and r["records"]["ran.json"]["cwd"].endswith("/S1-verifier/vt"), r
    assert r["records"]["ran.json"]["head"] == w["tip"]                                   # the tip, not main


def test_a_seat_that_exits_red_is_failed_with_its_result_committed(bw):
    w = bw
    assert call(w, "start S1 builder", payload(w), exit=3, commit=False)[0] == 0
    s = until(w, "failed")
    assert s["exit"] == 3
    (r,) = results(w)
    assert r["exit"] == 3


def test_a_seat_whose_session_dies_is_failed_in_words(bw):
    w = bw
    harness = seat_world(w)
    harness["seat_run"] = ["sh", "-c", "kill -9 $PPID; sleep 5"]                          # the seat's runner killed
    code, said = forced(w, "start S1 builder", payload(w), harness=harness, **GIT_ID)
    assert code == 0, said
    time.sleep(1)
    s = until(w, "failed")
    assert "ended without its result" in s["words"], s


# ------------------------------------------------------------------ status and stop; one seat per part


def test_status_says_running_and_stop_ends_the_seat_and_its_process(bw):
    w = bw
    code, said = call(w, "start S1 builder", payload(w), sleep=30)
    assert code == 0, said
    s = status(w)
    assert s["state"] == "running" and s["id"] == said["id"], s
    pid = json.loads((w["data"] / "seats/S1-builder/pid.json").read_text())["pid"]
    code, stopped = call(w, "stop S1 builder")
    assert code == 0 and stopped["state"] == "stopped", stopped
    end = time.monotonic() + 10
    while True:
        try:
            os.killpg(pid, 0)
        except OSError:
            break
        assert time.monotonic() < end, "the seat's process group is still alive"
        time.sleep(0.1)
    assert status(w)["state"] == "stopped"
    assert call(w, "stop S1 builder")[1]["reason"] == "not-running"
    code, again = call(w, "start S1 builder", payload(w))                                 # a stopped seat starts again
    assert code == 0 and until(w, "done")["state"] == "done", again


@pytest.mark.parametrize("second", ["builder", "verifier"])
def test_one_seat_per_part_at_a_time(bw, second):
    w = bw
    assert call(w, "start S1 builder", payload(w), sleep=30)[0] == 0
    try:
        code, said = call(w, f"start S1 {second}", payload(w, order(second)))
        assert code == 3 and said["reason"] == "seat-running", said
    finally:
        call(w, "stop S1 builder")


def test_a_clone_branch_with_work_the_mac_has_not_fetched_is_never_overwritten(bw):
    w = bw
    sh(["git", "fetch", "-q", str(w["mac"]), "lane/slice-S1:lane/slice-S1"], w["clone"], w["env"])
    sh("git switch -q lane/slice-S1 && echo s > server.txt && git add -A && git commit -qm 'on the server' && "
       "git switch -q main", w["clone"], w["env"])
    ahead = on(w, "refs/heads/lane/slice-S1")
    code, said = call(w, "start S1 builder", payload(w))
    assert code == 3 and said["reason"] == "server-ahead", said
    assert on(w, "refs/heads/lane/slice-S1") == ahead


# ------------------------------------------------------------------ the tar and the order: their shape and nothing else


@pytest.mark.parametrize("case,reason", [
    ("extra-member", "order-shape"), ("no-order", "order-shape"), ("a-link", "order-shape"),
    ("not-a-tar", "order-shape"),
    ("order-other-seat", "order-shape"), ("order-other-part", "order-shape"), ("order-extra-key", "order-shape"),
    ("order-bad-model", "order-shape"), ("order-bad-record-name", "order-shape"), ("order-no-prompt", "order-shape"),
    ("bundle-other-branch", "bundle-shape"), ("bundle-main-only", "bundle-shape"),
])
def test_anything_but_the_tar_of_a_bundle_and_an_order_is_refused_and_nothing_starts(bw, case, reason):
    w = bw
    data = {
        "extra-member": lambda: payload(w, extra={"run.sh": b"#!/bin/sh\nid\n"}),
        "no-order": lambda: tar({"in.bundle": bundle(w)}),
        "a-link": lambda: tar({"in.bundle": bundle(w)}, links=["order.json"]),
        "not-a-tar": lambda: bundle(w),
        "order-other-seat": lambda: payload(w, order("verifier")),
        "order-other-part": lambda: payload(w, order(part="S2")),
        "order-extra-key": lambda: payload(w, {**order(), "command": "sh"}),
        "order-bad-model": lambda: payload(w, order(model="opus; rm -rf ~")),
        "order-bad-record-name": lambda: payload(w, order(records={"../../bin/runner.py": {}})),
        "order-no-prompt": lambda: payload(w, order(prompt=" ")),
        "bundle-other-branch": lambda: payload(w, refs=("refs/heads/main", "refs/heads/lane/slice-S1", "refs/heads/x")),
        "bundle-main-only": lambda: payload(w, refs=("refs/heads/main",)),
    }
    if case == "bundle-other-branch":
        sh(["git", "branch", "-f", "x", "main"], w["mac"], w["env"])
    code, said = call(w, "start S1 builder", data[case]())
    assert code == 3 and said["reason"] == reason, said
    assert status(w)["state"] == "none"
    assert not (w["data"] / "seats/S1-builder/pid.json").exists()
    assert "seat-results" not in sh(["git", "branch", "--list"], w["clone"], w["env"])
    log = (w["data"] / "refusals.log").read_text()
    assert f"\t{reason}\t" in log and "rm -rf" not in log
