"""F1, layer 2: the seat shim. A seat's environment resolves `claude` (and `claude-sol`, `claude-ayan`) to the line's
shim, which refuses unless run_seat.py created this launch's one-time token; so a refusal does not depend on the text
of a command. Each case runs the shim as a seat's shell would meet it: a command found on the seat's PATH.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from test_gates import SRC, sh, started, world  # noqa: F401  (world is a fixture)


def shimmed(w):
    """The shim installed as install.sh installs it, and a real claude stand-in that says it ran."""
    shim = w["data"] / "bin/shim"
    shim.mkdir(parents=True)
    for name in ("claude", "claude-sol", "claude-ayan"):
        shutil.copy(SRC / "seat_shim.sh", shim / name)
        (shim / name).chmod(0o555)
    ran = w["tmp"] / "real-claude-ran"
    real = w["tmp"] / "real-claude"
    real.write_text(f'#!/bin/sh\necho "ran $* token=${{OSPREY_LAUNCH_TOKEN:-none}}" >> "{ran}"\n')
    real.chmod(0o755)
    env = {**w["env"], "OSPREY_CLAUDE_BIN": str(real), "OSPREY_SEAT": "builder",
           "PATH": f"{shim}{os.pathsep}{w['env']['PATH']}"}
    return env, ran


@pytest.mark.parametrize("cmd", ["claude -p 'do it'", "claude-sol -p x", "claude-ayan -p x", "env claude -p x",
                                 "bash -c 'claude -p x'", "X=claude; $X -p x", "command -v claude >/dev/null && claude -p x"])
def test_seat_shim_refuses_a_launch_without_the_launchers_token(world, cmd):
    w = world
    env, ran = shimmed(w)
    p = subprocess.run(["/bin/sh", "-c", cmd], env=env, capture_output=True, text=True, cwd=str(w["repo"]))
    assert p.returncode == 126 and "started only by run_seat.py" in p.stderr, (cmd, p.returncode, p.stderr)
    assert not ran.exists()


def test_seat_shim_lets_run_seats_own_launch_through_once_and_its_session_never_holds_the_token(world):
    w = world
    env, ran = shimmed(w)
    token = "a" * 32
    (w["data"] / "launch").mkdir()
    (w["data"] / "launch" / token).write_text("builder S1\n")
    env = {**env, "OSPREY_LAUNCH_TOKEN": token}
    p = subprocess.run([str(w["data"] / "bin/shim/claude"), "-p", "x"], env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert ran.read_text() == "ran -p x token=none\n"          # the session itself never holds the token
    assert not (w["data"] / "launch" / token).exists()       # one use
    p = subprocess.run([str(w["data"] / "bin/shim/claude"), "-p", "again"], env=env, capture_output=True, text=True)
    assert p.returncode == 126 and ran.read_text().count("ran") == 1


@pytest.mark.parametrize("token", ["", "0" * 32, "../emails.sha256", "../bin/guard.py", ".kept"])
def test_seat_shim_refuses_a_token_that_is_not_one(world, token):
    """A token naming a file that is there but is no launch token (the line's own files, by a relative path, or a
    dot-file): refused, and the file left alone (the shim removes a token it accepts)."""
    w = world
    env, ran = shimmed(w)
    (w["data"] / "launch").mkdir()
    (w["data"] / "launch/.kept").write_text("x\n")
    target = (w["data"] / "launch" / token) if token else None
    before = target.read_bytes() if target and target.is_file() else None
    p = subprocess.run([str(w["data"] / "bin/shim/claude"), "-p", "x"], env={**env, "OSPREY_LAUNCH_TOKEN": token},
                       capture_output=True, text=True)
    assert p.returncode == 126 and not ran.exists(), (token, p.returncode)
    if before is not None:
        assert target.read_bytes() == before


def test_seat_shim_run_seat_launches_through_the_shim_with_it_first_on_the_seats_path_and_a_fresh_token(world):
    w = world
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    code = (f"import sys, json; sys.path.insert(0, {str(w['lines'])!r}); import run_seat; "
            "args, env = run_seat.seat_command('builder', 'default', 'sonnet', 'high', {'OSPREY_SLICE': 'S1'}, 'tok-' + 'x'*28); "
            "print(json.dumps({'args': args, 'path': env['PATH'], 'token': env.get('OSPREY_LAUNCH_TOKEN')}))")
    out = json.loads(sh([w["py"], "-c", code], w["repo"], w["env"]).stdout)
    shim = str(w["data"] / "bin/shim")
    assert out["args"][0] == shim + "/claude", out["args"]
    assert out["path"].split(os.pathsep)[0] == shim
    # a fresh one-time launch token, written where only the line writes, never the seat's own SessionStart token
    assert out["token"] and out["token"] != "tok-" + "x" * 28 and (w["data"] / "launch" / out["token"]).is_file()


def test_seat_shim_a_seat_refuses_to_start_when_the_shim_is_not_installed(world):
    w = world
    p, _ = started(w)
    data = w["data"]
    import hashlib
    m = {f: hashlib.sha256((data / "bin" / f).read_bytes()).hexdigest()
         for f in ("guard.py", "stop_check.py", "usage_hook.py", "scan_select.py", "scan_map.tsv")}
    (data / "manifest.json").write_text(json.dumps(m))
    (data / "settings.json").write_text(json.dumps({"hooks": {"x": "guard.py pre guard.py session-start stop_check.py "
                                                              "guard.py stop usage_hook.py stop-failure"}}))
    out = sh([w["py"], str(w["lines"] / "run_seat.py"), "builder", "S1"], w["repo"], w["env"], check=False)
    assert out.returncode == 3 and "seat shim" in out.stderr, out.stderr
