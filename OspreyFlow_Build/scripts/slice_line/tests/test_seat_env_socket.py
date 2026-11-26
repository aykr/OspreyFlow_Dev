"""Server seats (017-2), demo-server's three items of 26 November 2026.

1. A seat starts with the build account's own environment, as a job does, never the SSH session's: the session's PATH
   lacks ~/.local/bin, where uv and trivy are. The runner reads it from the account's user manager
   (runner.OWN_ENV, `systemctl --user show-environment`) and keeps only runner.KEPT of it; with no PATH there, or
   no answer, the seat does not start. Here a stand-in answers for the user manager.
2. A seat's tmux session is on the seats' own tmux server (`tmux -L ospreyflow-seats`), never the account's default
   one, which the away sessions share; status and stop look there too. Its command is wrapped in `env -i` with that
   environment, so a seats' server started earlier with another environment does not give it its own. tmux is stood
   in: one folder per socket, a session a process group, and a server's environment the one it started with.
3. Watching from root (the README): sudo -u ospreyflow_build tmux -L ospreyflow-seats ls.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from test_build_runner import forced  # noqa: F401
from test_build_runner import bw  # noqa: F401  (a fixture)
from test_build_seats import GIT_ID, payload, results, seat_world

SOCKET = "ospreyflow-seats"
FAKE_TMUX = r"""#!%(py)s
import json, os, signal, subprocess, sys
from pathlib import Path
a = sys.argv[1:]
sock = "default"
if a[:1] == ["-L"]:
    sock, a = a[1], a[2:]
root = Path(os.environ["FAKE_TMUX_DIR"]) / sock
root.mkdir(parents=True, exist_ok=True)
with open(Path(os.environ["FAKE_TMUX_DIR"]) / "calls.jsonl", "a") as fh:
    fh.write(json.dumps({"socket": sock, "args": a}) + "\n")
def alive(name):
    f = root / (name + ".json")
    if not f.exists():
        return False
    try:
        os.killpg(json.loads(f.read_text())["pid"], 0)
        return True
    except OSError:
        return False
if a[0] == "new-session":
    name, cmd = a[a.index("-s") + 1], a[a.index("--") + 1:]
    if alive(name):
        sys.exit(1)
    srv = root / "server_env.json"           # a server keeps the environment it started with
    if not srv.exists():
        srv.write_text(json.dumps(dict(os.environ)))
    p = subprocess.Popen(cmd, env=json.loads(srv.read_text()), start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (root / (name + ".json")).write_text(json.dumps({"pid": p.pid}))
elif a[0] == "has-session":
    sys.exit(0 if alive(a[a.index("-t") + 1].lstrip("=")) else 1)
elif a[0] == "kill-session":
    name = a[a.index("-t") + 1].lstrip("=")
    if not alive(name):
        sys.exit(1)
    os.killpg(json.loads((root / (name + ".json")).read_text())["pid"], signal.SIGTERM)
    (root / (name + ".json")).unlink()
elif a[0] == "ls":
    print("\n".join(sorted(f.stem for f in root.glob("*.json") if f.stem != "server_env" and alive(f.stem))))
else:
    sys.exit(2)
"""
OWN_ENV = r"""#!%(py)s
import json, os, sys
cfg = json.load(open(os.environ["OWN_ENV_CFG"]))
env = {k: v for k, v in os.environ.items() if k != "OWN_ENV_CFG"}
env.update(cfg.get("set", {}))
for k in cfg.get("drop", []):
    env.pop(k, None)
print("\n".join("%%s=%%s" %% kv for kv in env.items()))
sys.exit(cfg.get("exit", 0))
"""


def script(w, name, text):
    f = w["tmp"] / name
    f.write_text(text % {"py": sys.executable})
    f.chmod(0o755)
    return str(f)


def own_path(w):
    d = w["tmp"] / "own-local-bin"                     # ~/.local/bin: uv and trivy, on the account's own PATH only
    d.mkdir(exist_ok=True)
    return f"{d}{os.pathsep}{w['sshd']['PATH']}"


def seat_call(w, cmd, stdin=b"", tmux=False, own=None, **cfg):
    """The forced command, with the user manager stood in (own: what it answers) and, with tmux, tmux stood in."""
    cfg_file = w["tmp"] / "own_env.json"
    if own is not None or not cfg_file.exists():
        cfg_file.write_text(json.dumps(own if own is not None else {"set": {"PATH": own_path(w), "MANAGER_ONLY": "1"}}))
    h = seat_world(w, **cfg)
    h["keep"] = h["keep"] + ["FAKE_TMUX_DIR", "OWN_ENV_CFG"]
    h["own_env"] = [script(w, "own_env.py", OWN_ENV)]
    if tmux:
        h.update(launch="systemd-run", tmux=script(w, "bin/tmux", FAKE_TMUX))      # bin: on the SSH PATH too
    return forced(w, cmd, stdin, harness=h, SEAT_FAKE=str(w["tmp"] / "seat.json"), OWN_ENV_CFG=str(cfg_file),
                  FAKE_TMUX_DIR=str(w["tmp"] / "tmux"), **GIT_ID)


def until(w, state, tmux=False, seconds=60):
    end = time.monotonic() + seconds
    while True:
        code, s = seat_call(w, "status S1 builder", tmux=tmux)
        assert code == 0, s
        if s["state"] == state:
            return s
        assert time.monotonic() < end and s["state"] in ("running", state), s
        time.sleep(0.2)


def ran(w):
    (r,) = [r for r in results(w) if r["exit"] == 0][-1:]
    return r["records"]["ran.json"]


def sessions(w, sock):
    d = w["tmp"] / "tmux" / sock
    return sorted(f.stem for f in d.glob("*.json") if f.stem != "server_env") if d.is_dir() else []


# ------------------------------------------------------------------ 1. the account's own environment


@pytest.mark.parametrize("tmux", [False, True], ids=["launched-directly", "in-tmux"])
def test_a_seat_runs_with_the_accounts_own_path_never_the_ssh_sessions(bw, tmux):
    w = bw
    code, said = seat_call(w, "start S1 builder", payload(w), tmux=tmux)
    assert code == 0 and said["state"] == "started", said
    until(w, "done", tmux=tmux)
    r = ran(w)
    assert r["path"] == own_path(w) and r["path"] != w["sshd"]["PATH"], r["path"]
    assert "SSH_ORIGINAL_COMMAND" not in r["env"], r["env"]                  # nothing of the SSH session's
    assert "MANAGER_ONLY" not in r["env"], r["env"]                          # and only KEPT of the manager's


def test_a_seats_server_started_with_another_environment_does_not_give_the_seat_its_own(bw):
    w = bw
    srv = w["tmp"] / "tmux" / SOCKET
    srv.mkdir(parents=True)
    stale = {**os.environ, "PATH": w["sshd"]["PATH"], "FAKE_TMUX_DIR": str(w["tmp"] / "tmux")}
    (srv / "server_env.json").write_text(json.dumps(stale))                 # the seats' server, started earlier
    code, said = seat_call(w, "start S1 builder", payload(w), tmux=True)
    assert code == 0, said
    until(w, "done", tmux=True)
    assert ran(w)["path"] == own_path(w)


@pytest.mark.parametrize("own,words", [
    ({"set": {"PATH": "/usr/bin:/bin"}, "exit": 1}, "could not be read (exit 1)"),
    ({"drop": ["PATH"]}, "names no PATH"),
    ({"set": {"PATH": ""}}, "names no PATH"),
], ids=["no-answer", "no-path", "empty-path"])
@pytest.mark.parametrize("tmux", [False, True], ids=["launched-directly", "in-tmux"])
def test_a_seat_without_the_accounts_own_environment_never_starts(bw, own, words, tmux):
    w = bw
    code, said = seat_call(w, "start S1 builder", payload(w), tmux=tmux, own=own)
    assert code == 3 and said["reason"] == "no-own-environment" and words in said["words"], said
    assert seat_call(w, "status S1 builder", tmux=tmux)[1]["state"] == "none"
    assert not (w["data"] / "seats/S1-builder/wt").exists()
    assert sessions(w, SOCKET) == [] and sessions(w, "default") == []


# ------------------------------------------------------------------ 2. the seats' own tmux server


def away(w):
    """An away session on the account's default tmux server: a process group the seats must never touch."""
    d = w["tmp"] / "tmux" / "default"
    d.mkdir(parents=True, exist_ok=True)
    p = subprocess.Popen(["sleep", "300"], start_new_session=True)
    (d / "away-1.json").write_text(json.dumps({"pid": p.pid}))
    return p


def test_a_seat_runs_stops_and_answers_on_its_own_tmux_server_and_the_away_sessions_are_untouched(bw):
    w = bw
    a = away(w)
    try:
        code, said = seat_call(w, "start S1 builder", payload(w), tmux=True, sleep=30)
        assert code == 0, said
        assert sessions(w, SOCKET) == ["seat-S1-builder"] and sessions(w, "default") == ["away-1"]
        assert seat_call(w, "status S1 builder", tmux=True)[1]["state"] == "running"
        code, stopped = seat_call(w, "stop S1 builder", tmux=True)
        assert code == 0 and stopped["state"] == "stopped", stopped
        assert sessions(w, SOCKET) == []
        assert a.poll() is None and sessions(w, "default") == ["away-1"]          # the away session runs on
        calls = [json.loads(ln) for ln in (w["tmp"] / "tmux" / "calls.jsonl").read_text().splitlines()]
        assert calls and all(c["socket"] == SOCKET for c in calls), calls
        assert {c["args"][0] for c in calls} >= {"new-session", "has-session", "kill-session"}, calls
        code, again = seat_call(w, "start S1 builder", payload(w), tmux=True)       # it starts again there
        assert code == 0, again
        assert until(w, "done", tmux=True)["state"] == "done"
    finally:
        a.kill()


def test_a_seat_whose_session_is_gone_from_its_own_server_is_failed_though_the_default_has_one_by_its_name(bw):
    w = bw
    code, said = seat_call(w, "start S1 builder", payload(w), tmux=True, sleep=30)
    assert code == 0, said
    d = w["tmp"] / "tmux"
    pid = json.loads((d / SOCKET / "seat-S1-builder.json").read_text())["pid"]
    (d / "default").mkdir(exist_ok=True)
    decoy = subprocess.Popen(["sleep", "300"], start_new_session=True)
    try:
        (d / "default" / "seat-S1-builder.json").write_text(json.dumps({"pid": decoy.pid}))
        os.killpg(pid, signal.SIGKILL)
        s = until(w, "failed", tmux=True)
        assert "ended without its result" in s["words"], s
    finally:
        decoy.kill()


# ------------------------------------------------------------------ 3. the README says how root watches


def test_the_readme_says_how_root_watches_the_seats():
    readme = Path(__file__).resolve().parents[3] / "process/lanes/v062/slice-line/README.md"
    text = readme.read_text()
    assert f"sudo -u ospreyflow_build tmux -L {SOCKET} ls" in text
    runner = (Path(__file__).resolve().parents[1] / "build_server/runner.py").read_text()
    assert f'SEAT_SOCKET = "{SOCKET}"' in runner
