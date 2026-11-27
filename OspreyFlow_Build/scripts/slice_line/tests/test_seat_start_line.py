"""Server seats (017-2): the seat runs the line's run_seat.py as the order's main has it, never the clone's own copy.

GG3a's verifier, the first server verifier (server run 361735d22464d46a, 26 November 2026), ended at once with exit
2 and no session. Its seat.log:

    usage: run_seat.py [-h] {builder,verifier,conductor} [slice]
    run_seat.py: error: argument seat: invalid choice: '.../seats/GG3a-verifier/order.json'

The runner ran ~/ospreyflow/OspreyFlow_Build/scripts/slice_line/run_seat.py, the copy in its clone's own working tree.
The runner fetches into that clone and adds worktrees to it, but never checks its working tree out, so the copy there
was the clone's as first checked out, from before run_seat.py had its --order mode. That older run_seat.py read
`--order <path>` as a seat name.

Now the runner runs run_seat.py from the main tree it made for the seat, at exactly the main the Mac sent with the
order. These cases run the real start line the runner builds: the real runner, `env -i`, the real `runner.py _seat`
and the real run_seat.py, in a world whose clone's working tree has an older run_seat.py without --order. Only tmux is
stood in, as in test_seat_env_socket.py, because the Mac has no tmux; the stand-in runs the command after `--` as
given. run_seat.py in its --order mode then refuses to start a session there (no guard is installed in the test's
account), and that refusal, written to the seat's records, is what shows it read the order.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from test_build_runner import bw, forced, sh  # noqa: F401  (bw is a fixture)
from test_build_seats import GIT_ID, order, payload, results
from test_seat_env_socket import FAKE_TMUX, OWN_ENV, own_path, script

LINE = Path(__file__).resolve().parent.parent
LINE_REL = "OspreyFlow_Build/scripts/slice_line"
ORDER_MODE = '    if len(sys.argv) == 3 and sys.argv[1] == "--order":  # 017-2: on the build account, the runner\'s seat\n' \
             '        return from_order(Path(sys.argv[2]))\n'


def copy_line(into: Path, without_order_mode: bool = False) -> None:
    """The line's code (not its tests), as a checkout of main holds it; or as it was before --order."""
    dst = into / LINE_REL
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(LINE, dst, ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc"))
    if without_order_mode:
        f = dst / "run_seat.py"
        text = f.read_text()
        assert text.count(ORDER_MODE) == 1, "run_seat.py's --order mode is not where these cases expect it"
        f.write_text(text.replace(ORDER_MODE, ""))


def server_world(w, clone_has: str) -> None:
    """The Mac's main carries the line's code. The clone's working tree has an older run_seat.py, without --order
    (as on the build account), or no line at all."""
    if clone_has == "older-run-seat":
        copy_line(w["mac"], without_order_mode=True)
        sh("git add -A && git commit -qm 'the line before 017-2'", w["mac"], w["env"])
        sh(["git", "push", "-q", str(w["origin"]), "main"], w["mac"], w["env"])
        sh("git pull -q --ff-only", w["clone"], w["env"])
        assert "--order" not in (w["clone"] / LINE_REL / "run_seat.py").read_text()
    copy_line(w["mac"])
    sh("git add -A && git commit -qm 'the line with 017-2'", w["mac"], w["env"])
    w["main"] = sh(["git", "rev-parse", "main"], w["mac"], w["env"])


def start_call(w, cmd, stdin=b"", tmux=True):
    """The forced command with the runner's own seat command (no stand-in for run_seat.py); the user manager stood in,
    and tmux when tmux is True."""
    cfg = w["tmp"] / "own_env.json"
    if not cfg.exists():
        cfg.write_text(json.dumps({"set": {"PATH": own_path(w)}}))
    h = {"keep": ["FAKE_TMUX_DIR", "OWN_ENV_CFG", *GIT_ID], "own_env": [script(w, "own_env.py", OWN_ENV)]}
    if tmux:
        h.update(launch="systemd-run", tmux=script(w, "bin/tmux", FAKE_TMUX))
    return forced(w, cmd, stdin, harness=h, OWN_ENV_CFG=str(cfg), FAKE_TMUX_DIR=str(w["tmp"] / "tmux"), **GIT_ID)


def finished(w, seat, tmux, seconds=120):
    import time
    end = time.monotonic() + seconds
    while True:
        code, s = start_call(w, f"status S1 {seat}", tmux=tmux)
        assert code == 0, s
        if s["state"] not in ("running",):
            return s
        assert time.monotonic() < end, s
        time.sleep(0.3)


@pytest.mark.parametrize("clone_has", ["older-run-seat", "no-line"])
@pytest.mark.parametrize("tmux", [True, False], ids=["in-tmux", "launched-directly"])
def test_a_server_verifier_runs_the_order_s_run_seat_in_its_order_mode_not_the_clone_s_copy(bw, tmux, clone_has):
    w = bw
    server_world(w, clone_has)
    o = order("verifier", prompt="You are the verifier for slice S1.")
    code, said = start_call(w, "start S1 verifier", payload(w, o), tmux=tmux)
    assert code == 0 and said["state"] == "started", said
    st = finished(w, "verifier", tmux)
    log = (w["data"] / "seats" / "S1-verifier" / "seat.log").read_text()
    assert "usage: run_seat.py" not in log and "invalid choice" not in log, log
    assert "can't open file" not in log, log
    (r,) = results(w)
    session = r["records"].get("session.json")
    assert session and session.get("subtype") == "not started on the server", (log, r)
    assert "REFUSED TO START: the guard is not installed" in session["result"], session      # its own preflight
    assert r["main"] == w["main"] and st["exit"] == 1, (r, st)
