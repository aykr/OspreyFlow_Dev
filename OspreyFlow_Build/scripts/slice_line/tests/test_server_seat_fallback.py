"""The owner's word of 26 November 2026, evening: a server seat that fails to start, or ends with no session's result,
is run on the Mac at once, logged, the part unchanged, instead of holding every verifier start for the owner. Server
verifiers can then run unattended overnight.

The case is tonight's: GG3a's verifier on the server (run 361735d22464d46a) ended at once, exit 2, no session, its
seat.log run_seat.py's usage error (it was handed the order file as a seat). Here the server's seat prints exactly that
and exits 2. The Mac then runs the verifier itself, and its verdict is the part's, as a Mac verifier's is.

Only a seat that did no work on the server falls back:
- a verifier, which changes nothing, whenever the server did not start it or it gave no session's result;
- a builder only when the server refused to start it, or it gave no session's result with the branch where it was.
A seat still running on the server (refused seat-running), or one whose work the backup does not hold, stays as
before: the part where it was, for the owner. The fallback is written to the part's records
(server-fallback.jsonl) and said on standard output.
"""
from __future__ import annotations

import json

import pytest

from test_finding_kind import at_verifier
from test_round_table import at_round
from test_gates import world  # noqa: F401  (a fixture)
from test_server_seat import calls, fake, head, sh, state, sw, where  # noqa: F401  (sw is a fixture)

GG3A = ("import sys\n"
        "print('usage: run_seat.py [-h] {builder,verifier,conductor} [slice]', file=sys.stderr)\n"
        "print(\"run_seat.py: error: argument seat: invalid choice: '%s' (choose from 'builder', 'verifier', "
        "'conductor')\" % sys.argv[-1], file=sys.stderr)\n"
        "sys.exit(2)\n")


def server_seat_is(w, text):
    f = w["tmp"] / "server_seat_run.py"
    f.write_text(text)
    h = json.loads((w["tmp"] / "build_harness.json").read_text())
    (w["tmp"] / "build_harness.json").write_text(json.dumps({**h, "seat_run": [w["py"], str(f)]}))


MAC = r"""
import json, subprocess, sys
sys.path.insert(0, %(lines)r)
import run_seat
def launch(seat, account, cwd, prompt, model, effort, env_extra, log, extra=None, interactive=False):
    with open(%(macs)r, "a") as fh:
        fh.write(json.dumps({"seat": seat, "cwd": str(cwd)}) + "\n")
    tip = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(cwd), capture_output=True, text=True).stdout.strip()
    out = {"verdict": "pass", "commit": tip, "findings": []} if seat == "verifier" else None
    return {"type": "result", "subtype": "success", "session_id": "mac-" + seat, "usage": {}, "total_cost_usd": 0,
            **({"structured_output": out} if out else {"result": "done\n\nREADY"})}
run_seat.launch = launch
run_seat.transcript_of = lambda account, sid: ""
sys.exit(run_seat.%(seat)s("S1"))
"""


def run_seat(w, seat):
    """run_seat.py's builder or verifier, its Mac session stood in (each Mac launch written to macs.jsonl)."""
    code = MAC % {"lines": str(w["lines"]), "macs": str(w["tmp"] / "macs.jsonl"), "seat": seat}
    return sh([w["py"], "-c", code], w["repo"], w["env"], check=False)


def macs(w):
    f = w["tmp"] / "macs.jsonl"
    return [json.loads(ln) for ln in f.read_text().splitlines()] if f.exists() else []


def fallbacks(w):
    f = w["data"] / "records/S1/server-fallback.jsonl"
    return [json.loads(ln) for ln in f.read_text().splitlines()] if f.exists() else []


def test_gg3a_s_verifier_ending_without_a_session_on_the_server_runs_on_the_mac_at_once(sw):
    w = sw
    wt, tip = at_verifier(w)
    where(w, "verifier", "server")
    server_seat_is(w, GG3A)
    p = run_seat(w, "verifier")
    assert p.returncode == 0, p.stdout + p.stderr
    assert [c for c in calls(w) if c.startswith("start")] == ["start S1 verifier"]          # the server tried once
    v = json.loads((w["data"] / f"records/S1/verify-{tip}.json").read_text())
    assert v["verdict"] == "pass" and v["commit"] == tip, v                                  # the Mac's verdict
    (f,) = fallbacks(w)
    assert f["seat"] == "verifier" and f["tip"] == tip and "without a session's result" in f["why"], f
    assert "exit 2" in f["why"] and "runs on the Mac now" in p.stdout, (f, p.stdout)
    assert head(w, wt) == tip and [m["seat"] for m in macs(w)] == ["verifier"], macs(w)


def test_a_verifier_the_build_account_cannot_start_runs_on_the_mac(sw):
    w = sw
    wt, tip = at_verifier(w)
    where(w, "verifier", "server")
    fake(w, down=True)
    p = run_seat(w, "verifier")
    assert p.returncode == 0, p.stdout + p.stderr
    assert json.loads((w["data"] / f"records/S1/verify-{tip}.json").read_text())["verdict"] == "pass"
    (f,) = fallbacks(w)
    assert "did not start the verifier of S1" in f["why"], f


def test_a_builder_that_made_no_commit_and_gave_no_session_runs_on_the_mac(sw):
    w = sw
    wt = at_round(w, 2)
    where(w, "builder", "server")
    server_seat_is(w, GG3A)
    before = head(w, wt)
    p = run_seat(w, "builder")
    assert p.returncode == 0, p.stdout + p.stderr
    (f,) = fallbacks(w)
    assert f["seat"] == "builder" and f["round"] == 2 and "without a session's result" in f["why"], f
    assert [m["seat"] for m in macs(w)] == ["builder"] and macs(w)[0]["cwd"] == str(wt), macs(w)   # the Mac's round


def test_a_builder_that_committed_on_the_server_and_gave_no_session_stays_for_the_owner(sw):
    w = sw
    wt = at_round(w, 2)
    where(w, "builder", "server")
    server_seat_is(w, "import subprocess, sys\n"
                      "open('half.txt', 'w').write('half\\n')\n"
                      "subprocess.run(['git', 'add', 'half.txt'], check=True)\n"
                      "subprocess.run(['git', 'commit', '-qm', 'S1: half built'], check=True)\n"
                      "sys.exit(3)\n")
    before, st0 = head(w, wt), state(w)
    p = run_seat(w, "builder")
    assert p.returncode == 2 and "The part stays where it was" in p.stdout, p.stdout + p.stderr
    assert fallbacks(w) == [] and macs(w) == [] and head(w, wt) == before   # its half work not taken: the owner looks
    assert (state(w)["phase"], state(w)["round"]) == (st0["phase"], st0["round"])


def test_a_seat_the_server_still_runs_or_whose_work_the_backup_lacks_never_falls_back(sw):
    w = sw
    wt, tip = at_verifier(w)
    where(w, "verifier", "server")
    fake(w, no_backup=True)
    p = run_seat(w, "verifier")
    assert p.returncode == 2 and "The part stays where it was" in p.stdout, p.stdout + p.stderr
    assert fallbacks(w) == [] and macs(w) == []
    assert not (w["data"] / f"records/S1/verify-{tip}.json").exists()


START = r"""
import json, sys
sys.path.insert(0, %(lines)r)
import server_seat as s
s.ew.make_bundle = lambda branch, path, full: path.write_bytes(b"bundle")
s.ew.ssh = lambda bs, words, stdin=None, timeout=None: %(answer)s
try:
    s.start({}, "S1", %(seat)r, "lane/slice-S1", {})
except s.ServerSeatNotRun:
    print("not-run")
except s.ServerSeatError:
    print("held")
"""


@pytest.mark.parametrize("seat,answer,then", [
    ("verifier", '(3, {"state": "refused", "reason": "seat-running"})', "held"),     # it still runs there
    ("builder", '(3, {"state": "refused", "reason": "seat-running"})', "held"),
    ("builder", "(255, None)", "held"),                                              # it may have started there
    ("verifier", "(255, None)", "not-run"),                                          # a verifier changes nothing
    ("builder", '(3, {"state": "refused", "reason": "dirty-tree"})', "not-run"),     # the account's own refusal
    ("verifier", '(3, {"state": "refused", "reason": "busy"})', "not-run")])
def test_which_refusals_of_a_start_run_the_seat_on_the_mac(world, seat, answer, then):
    w = world
    code = START % {"lines": str(w["lines"]), "answer": answer, "seat": seat}
    p = sh([w["py"], "-c", code], w["repo"], w["env"], check=False)
    assert p.stdout.strip() == then, (seat, answer, p.stdout, p.stderr)
