"""017-2, the Mac's side (server_seat.py, run_seat.py): with the dial's `where: server` for a seat, run_seat.py starts
that seat on the build account through its forced command (`start`, then `status` until it is done), and takes the
seat's work only from the backup repository: the builder's branch, fast-forwarded into the Mac's worktree only if it
holds exactly the tip the seat's result names, and the seat's records (the Stop hook's test record) into the part's
records, each marked with its run. The part then goes on as a Mac seat's would. A seat the server cannot start, or
whose work the backup does not hold, leaves the part where it was.

The world: the line's own (test_gates), its part S1 at a builder round or waiting for the verifier; a fake build
account with the real build_server/runner.py behind a fake ssh (the forced command's words reach it only as
SSH_ORIGINAL_COMMAND), its clone a clone of the dev repository; and a bare repository standing in for the backup, to
which the fake ssh pushes the clone's branches after each call, as the backup timer would. The seat on the server is
stood in (it commits, and writes the test record and the session's result run_seat.py --order would leave).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

import pytest

from test_build_runner import KEEP, WRAP
from test_finding_kind import at_verifier
from test_gates import sh, world  # noqa: F401  (world is a fixture)
from test_round_table import at_round
from test_seat_failure import pin_dial

V062 = "OspreyFlow_Build/process/lanes/v062"
HOST = "build-box.example.invalid"
GIT_ID = {"GIT_AUTHOR_NAME": "seat", "GIT_AUTHOR_EMAIL": "seat@t.invalid", "GIT_COMMITTER_NAME": "seat",
          "GIT_COMMITTER_EMAIL": "seat@t.invalid", "GIT_CONFIG_GLOBAL": "/dev/null"}
FAKE_SSH = r"""#!/usr/bin/env python3
import json, os, subprocess, sys
args = sys.argv[1:]
words = args[args.index("--") + 2:]
cfg = json.load(open(os.environ["FAKE_BUILD"]))
open(cfg["log"], "a").write(" ".join(words) + "\n")
if cfg.get("down"):
    sys.exit(255)
env = {"PATH": os.environ["PATH"], "HOME": cfg["home"], "XDG_RUNTIME_DIR": cfg["run"],
       "SSH_ORIGINAL_COMMAND": " ".join(words), **cfg["keep"]}
p = subprocess.run([sys.executable, cfg["wrap"], cfg["runner"], cfg["harness"]], stdin=sys.stdin, env=env)
if not cfg.get("no_backup"):                                    # the backup timer
    refs = cfg.get("push", ["refs/heads/*:refs/heads/*"])
    subprocess.run(["git", "-C", cfg["clone"], "push", "-q", "--force", cfg["backup"], *refs], env=env)
sys.exit(p.returncode)
"""
FAKE_SEAT = r"""import json, os, subprocess, sys
order_path = sys.argv[-1]
d = os.path.dirname(order_path)
o = json.load(open(order_path))
rec = os.path.join(d, "records")
json.dump({"prompt": o["prompt"], "cwd": os.getcwd()}, open(os.path.join(rec, "ran.json"), "w"))
if o["seat"] == "builder":
    open("built.txt", "w").write("built on the server\n")
    subprocess.run(["git", "add", "built.txt"], check=True)
    subprocess.run(["git", "commit", "-qm", "S1: built on the server"], check=True)
    tip = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    json.dump({"green": True, "commit": tip, "tip": tip}, open(os.path.join(rec, "tests-%s.json" % tip), "w"))
    session = {"type": "result", "subtype": "success", "is_error": False, "session_id": "server-b", "result": "done\n\nREADY",
               "usage": {}, "total_cost_usd": 1.0}
else:
    tip = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    session = {"type": "result", "subtype": "success", "is_error": False, "session_id": "server-v", "usage": {},
               "total_cost_usd": 0.4, "structured_output": {"verdict": "pass", "commit": tip, "findings": []}}
json.dump(session, open(os.path.join(rec, "session.json"), "w"))
"""


def where(w, seat, value):
    """The dial's balanced setting, with `where: <value>` for this seat."""
    pin_dial(w)
    dial = w["repo"] / V062 / "dial.yaml"
    text = dial.read_text()
    head = text.index("  balanced:")
    i = text.index(f"      {seat}:", head)
    j = text.index("}", i)
    dial.write_text(text[:j] + f", where: {value}" + text[j:])


@pytest.fixture
def sw(world):
    w = world
    build = w["tmp"] / "remote" / "ospreyflow_build"
    home, run = build / "home", w["tmp"] / "buildrun"
    for d in (build / "bin", home, run):
        d.mkdir(parents=True)
    shutil.copy(w["lines"] / "build_server/runner.py", build / "bin/runner.py")
    clone, backup = home / "ospreyflow", w["tmp"] / "backup.git"
    sh(["git", "clone", "-q", str(w["origin"]), str(clone)], w["tmp"], w["env"])
    sh(["git", "init", "-q", "--bare", "-b", "main", str(backup)], w["tmp"], w["env"])
    seat = w["tmp"] / "fake_seat.py"
    seat.write_text(FAKE_SEAT)
    harness = w["tmp"] / "build_harness.json"
    harness.write_text(json.dumps({"keep": KEEP + list(GIT_ID), "seat_run": [sys.executable, str(seat)]}))
    wrap = w["tmp"] / "build_wrap.py"
    wrap.write_text(WRAP)
    bin_ = w["tmp"] / "sshbin"
    bin_.mkdir()
    (bin_ / "ssh").write_text(FAKE_SSH)
    (bin_ / "ssh").chmod(0o755)
    cfg = {"log": str(w["tmp"] / "ssh.log"), "home": str(home), "run": str(run), "keep": GIT_ID, "wrap": str(wrap),
           "runner": str(build / "bin/runner.py"), "harness": str(harness), "clone": str(clone), "backup": str(backup)}
    w["fake_build"] = w["tmp"] / "fake_build.json"
    w["fake_build"].write_text(json.dumps(cfg))
    w["env"].update(PATH=f"{bin_}{os.pathsep}{w['env']['PATH']}", FAKE_BUILD=str(w["fake_build"]))
    key = w["home"] / "keys" / "build"
    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_text("not a key: the fake ssh reads no key\n")
    (w["data"] / "build-server.json").write_text(json.dumps({"host": HOST, "user": "ospreyflow_build",
                                                              "key_file": str(key)}))
    (w["data"] / "build_backup").write_text(str(backup) + "\n")
    ss = w["lines"] / "server_seat.py"  # no waiting between polls, in this copy only
    ss.write_text(ss.read_text().replace("SEAT_POLL_SECONDS = 60", "SEAT_POLL_SECONDS = 0.2")
                  .replace("BACKUP_WAIT_MINUTES = 30", "BACKUP_WAIT_MINUTES = 0.05")
                  .replace("BACKUP_POLL_SECONDS = 30", "BACKUP_POLL_SECONDS = 0.2"))
    w.update(build=build, clone=clone, backup=backup)
    return w


def fake(w, **cfg):
    f = w["fake_build"]
    f.write_text(json.dumps({**json.loads(f.read_text()), **cfg}))


def calls(w):
    f = w["tmp"] / "ssh.log"
    return f.read_text().splitlines() if f.exists() else []


def run_seat(w, seat):
    return sh([w["py"], str(w["lines"] / "run_seat.py"), seat, "S1"], w["repo"], w["env"], check=False)


def state(w):
    return json.loads((w["data"] / "records/S1/state.json").read_text())


def head(w, where):
    return sh(["git", "rev-parse", "HEAD"], where, w["env"]).stdout.strip()


# ------------------------------------------------------------------ the builder on the server


def test_a_builder_on_the_server_comes_back_through_the_backup_and_the_part_goes_on(sw):
    w = sw
    wt = at_round(w, 2)
    where(w, "builder", "server")
    before = head(w, wt)
    p = run_seat(w, "builder")
    assert p.returncode == 0, p.stdout + p.stderr
    said = calls(w)
    assert said[0] == "start S1 builder" and all(c == "status S1 builder" for c in said[1:]) and len(said) >= 2, said
    tip = head(w, wt)
    assert tip != before and (wt / "built.txt").read_text() == "built on the server\n"     # fast-forwarded here
    assert sh(["git", "rev-parse", "lane/slice-S1"], w["repo"], w["env"]).stdout.strip() == tip
    assert sh(["git", "rev-parse", f"{tip}~1"], w["repo"], w["env"]).stdout.strip() == before
    t = json.loads((w["data"] / f"records/S1/tests-{tip}.json").read_text())
    assert t["green"] is True and re.fullmatch(r"[0-9a-f]{16}", t["from_server"]), t
    st = state(w)
    assert st["phase"] == "verifying" and st["tip"] == tip, st
    assert "the builder runs on the build account" in p.stdout


def test_the_server_seat_is_given_the_mac_records_and_its_own_paths(sw):
    w = sw
    wt = at_round(w, 2)
    where(w, "builder", "server")
    assert run_seat(w, "builder").returncode == 0
    order = json.loads((w["build"] / "data/seats/S1-builder/order.json").read_text())
    assert order["records"]["frozen.json"]["branch"] == "lane/slice-S1"
    assert order["records"]["mac.json"] == {"repo": str(w["repo"]), "tree": str(wt)}
    assert str(wt) in order["prompt"]                          # the Mac's paths, for run_seat.py --order to replace


@pytest.mark.parametrize("how,words", [
    ("down", "did not start the builder of S1: no answer"),
    ("no_backup", "the backup repository has no result of the builder of S1"),
    ("results_only", "is not the tip the seat's result names"),
])
def test_a_server_seat_that_cannot_start_or_come_back_leaves_the_part_where_it_was(sw, how, words):
    w = sw
    wt = at_round(w, 2)
    where(w, "builder", "server")
    fake(w, **({"push": ["refs/heads/seat-results:refs/heads/seat-results"]} if how == "results_only" else {how: True}))
    before, st0 = head(w, wt), state(w)
    p = run_seat(w, "builder")
    assert p.returncode == 2 and words in p.stdout and "The part stays where it was" in p.stdout, p.stdout + p.stderr
    assert head(w, wt) == before and not (wt / "built.txt").exists()
    st = state(w)
    assert (st["phase"], st["round"]) == (st0["phase"], st0["round"]), st
    assert not list((w["data"] / "records/S1").glob("seat-failure-*.json"))       # not the account's failure


def test_a_server_seat_that_ends_without_a_session_is_the_servers_fault_never_the_accounts(sw):
    """No retry and no stopped account: launch_seat's tries are for a refused call, and a seat that never gave a
    session's result on the server is not one."""
    w = sw
    at_round(w, 2)
    where(w, "builder", "server")
    h = json.loads((w["tmp"] / "build_harness.json").read_text())
    # it committed before it ended, so it did work there and is not run on the Mac (test_server_seat_fallback.py)
    (w["tmp"] / "build_harness.json").write_text(json.dumps({**h, "seat_run": [
        "sh", "-c", "echo half > half.txt && git add half.txt && git commit -qm 'S1: half' && exit 4"]}))
    st0 = state(w)
    p = run_seat(w, "builder")
    assert p.returncode == 2 and "without a session's result" in p.stdout and "exit 4" in p.stdout, p.stdout + p.stderr
    assert [c for c in calls(w) if c.startswith("start")] == ["start S1 builder"]           # tried once
    assert not list(w["data"].glob("accounts/*.stopped.json"))
    assert not list((w["data"] / "records/S1").glob("seat-failure-*.json"))
    assert (state(w)["phase"], state(w)["round"]) == (st0["phase"], st0["round"])


def test_a_dial_where_that_is_neither_mac_nor_server_starts_nothing(sw):
    w = sw
    at_round(w, 2)
    where(w, "builder", "elsewhere")
    p = run_seat(w, "builder")
    assert p.returncode == 2 and "NOT STARTED: the dial's where: 'elsewhere'" in p.stdout, p.stdout + p.stderr
    assert calls(w) == []


# ------------------------------------------------------------------ the verifier on the server


def test_a_verifier_on_the_server_gives_its_verdict_as_a_mac_verifier_does(sw):
    w = sw
    wt, tip = at_verifier(w)
    where(w, "verifier", "server")
    p = run_seat(w, "verifier")
    assert p.returncode == 0, p.stdout + p.stderr
    assert calls(w)[0] == "start S1 verifier"
    v = json.loads((w["data"] / f"records/S1/verify-{tip}.json").read_text())
    assert v["verdict"] == "pass" and v["commit"] == tip, v
    assert head(w, wt) == tip                                   # the verifier changes no branch


# ------------------------------------------------------------------ run_seat.py --order, on the server


def test_run_seat_order_runs_the_seat_in_the_servers_tree_and_leaves_its_records_for_the_runner(world, tmp_path):
    w = world
    d = tmp_path / "seat"
    (d / "records").mkdir(parents=True)
    tree, main = tmp_path / "wt", tmp_path / "main"
    tree.mkdir()
    main.mkdir()
    mac_tree, mac_repo = "/Users/o/osprey-wt/slice-S1", "/Users/o/ospreyflow"
    order = {"seat": "builder", "slice": "S1", "round": 2, "model": "sonnet", "effort": "high", "account": "sol",
             "prompt": f"Your worktree is {mac_tree}. Read {mac_repo}/{V062}/slices/S1_ROUND2_TABLE.md.",
             "trees": {"wt": str(tree), "main": str(main)},
             "records": {"frozen.json": {"branch": "lane/slice-S1"}, "state.json": {"phase": "building"},
                         "mac.json": {"repo": mac_repo, "tree": mac_tree}}}
    (d / "order.json").write_text(json.dumps(order))
    seen = tmp_path / "seen.json"
    code = f"""
import json, sys
sys.path.insert(0, {str(w['lines'])!r})
import run_seat, common as c
def launch(seat, account, cwd, prompt, model, effort, env_extra, log, extra=None, interactive=False):
    json.dump({{"seat": seat, "cwd": str(cwd), "prompt": prompt, "env": env_extra, "extra": extra}}, open({str(seen)!r}, "w"))
    (c.rec_dir("S1") / "tests-{'a' * 40}.json").write_text('{{"green": true}}')
    return {{"type": "result", "is_error": False, "session_id": "s"}}
run_seat.launch = launch
sys.argv = ["run_seat.py", "--order", {str(d / 'order.json')!r}]
sys.exit(run_seat.main())
"""
    stale = w["data"] / "records/S1" / f"tests-{'b' * 40}.json"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text('{"green": true}')                                   # an older record: not this seat's
    p = sh([w["py"], "-c", code], w["repo"], w["env"], check=False)
    assert p.returncode == 0, p.stdout + p.stderr
    s = json.loads(seen.read_text())
    assert s["cwd"] == str(tree) and s["env"] == {"OSPREY_SLICE": "S1", "OSPREY_SLICE_WORKTREE": str(tree)}
    assert s["prompt"] == f"Your worktree is {tree}. Read {main}/{V062}/slices/S1_ROUND2_TABLE.md.", s["prompt"]
    assert json.loads((w["data"] / "records/S1/frozen.json").read_text()) == {"branch": "lane/slice-S1"}
    left = sorted(x.name for x in (d / "records").iterdir())
    assert left == ["session.json", f"tests-{'a' * 40}.json"], left


def test_run_seat_order_on_a_server_without_the_guard_says_so_in_the_session(world, tmp_path):
    w = world
    d = tmp_path / "seat"
    (d / "records").mkdir(parents=True)
    order = {"seat": "verifier", "slice": "S1", "round": 1, "model": "opus", "effort": "high", "account": "sol",
             "prompt": "verify", "trees": {"vt": str(tmp_path), "main": str(tmp_path)}, "records": {}}
    (d / "order.json").write_text(json.dumps(order))
    p = sh([w["py"], str(w["lines"] / "run_seat.py"), "--order", str(d / "order.json")], w["repo"],
           {**w["env"], "OSPREY_SLICE_HOME": str(tmp_path / "no-install")}, check=False)
    assert p.returncode == 1, p.stdout + p.stderr
    s = json.loads((d / "records/session.json").read_text())
    assert s["is_error"] is True and "REFUSED TO START" in s["result"], s
