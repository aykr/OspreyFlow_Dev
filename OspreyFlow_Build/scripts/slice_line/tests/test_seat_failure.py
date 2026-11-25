"""A seat whose call was refused is a seat failure, retried: never a finding, never a round (LINE_FIXES_3_BRIEF.md, 1f;
the owner's word of 19 November 2026, evening). And the owner's command that clears a stopped account (the owner's
order of 19 November, evening: until then the only way was deleting the marker file by hand).

The refused call is CO2's own: its verifier session on sol came back in 332 ms with the result line in
fixtures/refused_403_result.json (is_error, api_error_status 403, api_error_code oauth_not_allowed_for_organization),
and run_seat.py wrote it as a verifier record with one finding, "no verdict returned", and sent CO2 back to its
builder for round 2. The seats run as run_seat.py runs them, with the Claude session stood in by a sequence of result
lines (the suite starts no session and never calls the sol account).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest

from test_finding_kind import FAULT, GAP, at_verifier, finding
from test_gates import bash, main_sha, merge, refused, sh, world  # noqa: F401  (world is a fixture)

V062 = "OspreyFlow_Build/process/lanes/v062"
from test_gates import TODAY  # noqa: E402  (the run's one date: 9)
REFUSED = json.loads((Path(__file__).resolve().parent / "fixtures/refused_403_result.json").read_text())
WORDS = "Your organization has disabled Claude subscription access for Claude Code"


def refused_with(status, code="x", is_error=True):
    return {**REFUSED, "api_error_status": status, "api_error_code": code, "is_error": is_error,
            "session_id": f"r-{status}"}


def verdict(tip, findings=(), v=None, session="v-ok"):
    v = v or ("findings" if findings else "pass")
    return {"type": "result", "subtype": "success", "is_error": False, "num_turns": 14, "session_id": session,
            "structured_output": {"verdict": v, "commit": tip, "findings": list(findings)}, "usage": {},
            "total_cost_usd": 0.4}


def builder_done(session="b-ok"):
    return {"type": "result", "subtype": "success", "is_error": False, "num_turns": 40, "session_id": session,
            "result": "done", "usage": {}, "total_cost_usd": 1.0}


def pin_dial(w, setting="balanced"):
    dial = w["repo"] / V062 / "dial.yaml"
    dial.write_text(re.sub(r"(?m)^current: \w+", f"current: {setting}", dial.read_text()))


def run_seat(w, seat, results):
    """run_seat.<seat>('S1'), its sessions stood in by `results`, one per launch, in order; no pause between tries.
    Returns (process, the accounts each launch was given)."""
    rf, calls, prompts = w["tmp"] / "results.json", w["tmp"] / "calls.json", w["tmp"] / "prompts.json"
    rf.write_text(json.dumps(results))
    t = w["tmp"] / "verifier-transcript.jsonl"
    code = f"""
import json, sys
sys.path.insert(0, {str(w['lines'])!r})
import run_seat
results, calls, prompts = json.load(open({str(rf)!r})), [], []
def launch(seat, account, cwd, prompt, model, effort, env_extra, log, extra=None, interactive=False):
    calls.append(account)
    prompts.append(prompt)
    res = results.pop(0)
    open({str(t)!r}, "w").write(json.dumps({{"type": "assistant", "text": json.dumps(res)}}) + "\\n")
    return res
run_seat.launch = launch
run_seat.transcript_of = lambda account, sid: {str(t)!r}
run_seat.SEAT_PAUSES = (0, 0, 0)
try:
    rc = getattr(run_seat, {seat!r})("S1")
finally:
    open({str(calls)!r}, "w").write(json.dumps(calls))
    open({str(prompts)!r}, "w").write(json.dumps(prompts))
sys.exit(rc)
"""
    p = sh([w["py"], "-c", code], w["repo"], w["env"], check=False)
    assert "Traceback" not in p.stderr, p.stderr
    return p, json.loads(calls.read_text())


def rec(w):
    return w["data"] / "records/S1"


def state(w):
    return json.loads((rec(w) / "state.json").read_text())


def failures(w):
    return [json.loads(f.read_text()) for f in sorted(rec(w).glob("seat-failure-*.json"))]


def stop_of(w, account):
    f = w["data"] / f"accounts/{account}.stopped.json"
    return json.loads(f.read_text()) if f.exists() else None


def verifying(w, round_=1, limit=2):
    pin_dial(w)
    return at_verifier(w, round_=round_, limit=limit)


# ------------------------------------------------------------------ the verifier's path


def test_seat_failure_a_refused_verifier_call_is_retried_and_three_refusals_leave_the_slice_where_it_was(world):
    w = world
    wt, tip = verifying(w)
    st0 = state(w)
    reds = (rec(w) / "red_stops").read_text() if (rec(w) / "red_stops").exists() else None
    p, calls = run_seat(w, "verifier", [REFUSED, REFUSED, REFUSED])
    assert p.returncode == 2, p.stdout + p.stderr
    assert calls == ["sol", "sol", "sol"]                                       # tried three times, then no more
    assert not (rec(w) / f"verify-{tip}.json").exists()                         # no verifier record, no finding
    st = state(w)
    assert (st["phase"], st["round"], st["rounds_limit"]) == ("verifying", st0["round"], st0["rounds_limit"]), st
    assert st["seat_failure"]["account"] == "sol" and "403" in st["seat_failure"]["error"], st
    fs = failures(w)
    assert len(fs) == 3 and all(f["kind"] == "seat_failure" and f["seat"] == "verifier" for f in fs), fs
    assert all(f["result"]["api_error_code"] == "oauth_not_allowed_for_organization" for f in fs)
    stop = stop_of(w, "sol")
    assert stop and WORDS in stop["error"] and "403" in stop["error"], stop
    assert WORDS in p.stdout and "sol" in p.stdout                              # the error's own words, for the owner
    assert not (rec(w) / "red_stop.json").exists()
    assert ((rec(w) / "red_stops").read_text() if (rec(w) / "red_stops").exists() else None) == reds


def test_seat_failure_a_refused_call_that_succeeds_on_the_second_try_gives_that_tries_verdict(world):
    w = world
    wt, tip = verifying(w)
    second = [finding(GAP, "no test fails if the list is empty")]
    p, calls = run_seat(w, "verifier", [REFUSED, verdict(tip, second)])
    assert calls == ["sol", "sol"], calls
    v = json.loads((rec(w) / f"verify-{tip}.json").read_text())
    assert v["findings"] == second and [x["session"] for x in v["passes"]] == ["v-ok"], v
    assert len(failures(w)) == 1 and stop_of(w, "sol") is None
    st = state(w)
    assert (st["phase"], st["round"]) == ("building", 2) and "seat_failure" not in st, st   # an ordinary round


@pytest.mark.parametrize("first", [refused_with(401), refused_with(408), refused_with(429, "rate_limit_error"),
                                   refused_with(500), refused_with(529, "overloaded_error"),
                                   refused_with(529, "overloaded_error", is_error=False),
                                   {k: v for k, v in REFUSED.items() if not k.startswith("api_error")},
                                   {"type": "result", "subtype": "success", "num_turns": 0, "session_id": "n-0"}, {}],
                         ids=["401", "408", "429", "500", "529", "529-without-is-error", "is-error-without-a-status",
                              "no-verdict-no-turns", "no-result-line"])
def test_seat_failure_every_refusal_shape_is_retried_not_recorded_as_a_finding(world, first):
    w = world
    wt, tip = verifying(w)
    p, calls = run_seat(w, "verifier", [first, verdict(tip)])
    assert p.returncode == 0 and len(calls) == 2, p.stdout + p.stderr
    assert json.loads((rec(w) / f"verify-{tip}.json").read_text())["verdict"] == "pass"
    assert state(w)["phase"] == "verified" and len(failures(w)) == 1


def test_seat_failure_a_real_verifier_result_with_findings_is_unchanged(world):
    w = world
    wt, tip = verifying(w)
    fs = [finding(FAULT, "the form saves before it validates"), finding(GAP, "no test pins the order")]
    p, calls = run_seat(w, "verifier", [verdict(tip, fs)])
    assert calls == ["sol"] and failures(w) == []
    v = json.loads((rec(w) / f"verify-{tip}.json").read_text())
    assert v["verdict"] == "findings" and v["findings"] == fs
    assert (state(w)["phase"], state(w)["round"]) == ("building", 2)


def test_seat_failure_is_read_by_nothing_that_reads_a_verdict(world):
    """No merge, no standing accept and no builder prompt takes a seat failure for a verifier's word; the board shows
    the failure and the account, never "findings"."""
    w = world
    wt, tip = verifying(w)
    run_seat(w, "verifier", [REFUSED, REFUSED, REFUSED])
    before = main_sha(w)
    m = merge(w)
    assert m.returncode == 1 and "no verifier record" in m.stderr and main_sha(w) == before, m.stderr
    code = (f"import sys; sys.path.insert(0, {str(w['lines'])!r}); import run_seat; "
            "print(repr(run_seat.last_findings('S1')))")
    assert sh([w["py"], "-c", code], w["repo"], w["env"]).stdout.strip() == "''"
    board = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False)
    row = next(ln for ln in board.stdout.splitlines() if ln.startswith("S1 "))
    assert "seat failed" in row and "sol" in row and "finding" not in row, board.stdout
    status = (w["repo"] / "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/status.js").read_text()
    co1 = json.loads(status.split("window.OSPREY_STATUS = ", 1)[1].rstrip().rstrip(";"))["builds"]["CO1"]
    assert co1["state"] == "verifying" and "seat failed" in co1["note"] and "finding" not in co1["note"], co1


def test_seat_failure_stops_retrying_once_the_account_is_stopped(world):
    """The StopFailure hook writes the account's stop at the first refusal (CO2, 17:07 UTC): a retry would be refused
    at the account check, so the line does not try again and says so."""
    w = world
    wt, tip = verifying(w)
    (w["data"] / "accounts").mkdir(exist_ok=True)
    stopfile = w["data"] / "accounts/sol.stopped.json"
    code = f"""
import json, sys
sys.path.insert(0, {str(w['lines'])!r})
import run_seat
calls = []
def launch(seat, account, cwd, prompt, model, effort, env_extra, log, extra=None, interactive=False):
    calls.append(account)  # the hook's stop, written while the session runs, as usage_hook.py writes it
    open({str(stopfile)!r}, "w").write(json.dumps({{"account": "sol", "error": "oauth_org_not_allowed", "at": "t"}}))
    return json.loads({json.dumps(json.dumps(REFUSED))})
run_seat.launch = launch
run_seat.SEAT_PAUSES = (0, 0, 0)
rc = run_seat.verifier("S1")
print("CALLS", json.dumps(calls))
sys.exit(rc)
"""
    p = sh([w["py"], "-c", code], w["repo"], w["env"], check=False)
    assert "Traceback" not in p.stderr, p.stderr
    assert p.returncode == 2 and 'CALLS ["sol"]' in p.stdout, p.stdout + p.stderr
    assert stop_of(w, "sol")["error"] == "oauth_org_not_allowed"               # the hook's own stop is kept
    assert state(w)["phase"] == "verifying" and not (rec(w) / f"verify-{tip}.json").exists()


# ------------------------------------------------------------------ the builder's path


def test_seat_failure_a_refused_builder_call_is_retried_and_counts_no_red_stop_and_no_round(world):
    w = world
    wt, tip = verifying(w)
    st = state(w)
    st["phase"] = "building"
    (rec(w) / "state.json").write_text(json.dumps(st))
    reds = (rec(w) / "red_stops").read_text() if (rec(w) / "red_stops").exists() else None
    p, calls = run_seat(w, "builder", [REFUSED, REFUSED, REFUSED])
    assert p.returncode == 2 and calls == ["default", "default", "default"], p.stdout + p.stderr
    after = state(w)
    assert (after["phase"], after["round"]) == ("building", st["round"]) and after["seat_failure"]["seat"] == "builder"
    assert not (rec(w) / "red_stop.json").exists()
    assert ((rec(w) / "red_stops").read_text() if (rec(w) / "red_stops").exists() else None) == reds
    assert stop_of(w, "default") and WORDS in stop_of(w, "default")["error"]
    assert len(failures(w)) == 3 and all(f["seat"] == "builder" for f in failures(w))


@pytest.mark.parametrize("first", [REFUSED, {"session_id": "no-result-line"}], ids=["403", "no-result-line"])
def test_seat_failure_a_builder_refused_once_then_working_goes_on_as_before(world, first):
    w = world
    wt, tip = verifying(w)
    st = state(w)
    st["phase"] = "building"
    (rec(w) / "state.json").write_text(json.dumps(st))
    p, calls = run_seat(w, "builder", [first, builder_done()])
    assert calls == ["default", "default"] and stop_of(w, "default") is None
    assert state(w)["phase"] == "verifying" and "seat_failure" not in state(w)    # green at the tip, as before
    sess = json.loads((rec(w) / "sessions.json").read_text())
    assert "b-ok" in sess["builder"] and REFUSED["session_id"] not in sess["builder"]


# ------------------------------------------------------------------ CO2's lost round, given back


def co2_as_it_was(w):
    """S1 as CO2 was left at 17:07 UTC on 19 November: the refused verifier call written as a findings record, round
    advanced, back to building; the session's own stream (its result line) in the records folder."""
    wt, tip = verifying(w, round_=1, limit=4)
    sid = REFUSED["session_id"]
    pas = {"pass": "acceptance", "verdict": "findings", "commit": "",
           "findings": [{"what": "no verdict returned", "evidence": "success"}], "session": sid, "account": "sol",
           "model": "opus", "transcript": ""}
    (rec(w) / f"verify-{tip}.json").write_text(json.dumps(
        {"slice": "S1", "commit": tip, "verdict": "findings", "passes": [pas], "findings": pas["findings"],
         "builder_sessions": [], "at": "2026-11-19T17:07:18Z", "kinds": {"fault": 0, "test_gap": 0, "no kind": 1}}))
    (rec(w) / "verifier-acceptance-11ccc0.jsonl").write_text(
        json.dumps({"type": "system", "subtype": "init", "session_id": sid}) + "\n" + json.dumps(REFUSED) + "\n")
    st = state(w)
    st.update(phase="building", round=2)
    (rec(w) / "state.json").write_text(json.dumps(st))
    return wt, tip


def undo(w):
    return sh([w["py"], str(w["lines"] / "resume.py"), "S1", "undo-seat-failure"], w["repo"], w["env"], check=False)


def test_undo_seat_failure_gives_co2_its_round_back_on_the_owners_line(world):
    w = world
    wt, tip = co2_as_it_was(w)
    p = undo(w)
    assert p.returncode == 1 and "no line" in p.stderr and state(w)["round"] == 2, p.stderr
    (w["repo"] / V062 / "resume.tsv").write_text(f"S1\tundo-seat-failure\t{TODAY}\n")
    bogus = json.loads((rec(w) / f"verify-{tip}.json").read_text())
    p = undo(w)
    assert p.returncode == 0, p.stdout + p.stderr
    st = state(w)
    assert (st["phase"], st["round"], st["tip"]) == ("verifying", 1, tip), st
    assert not (rec(w) / f"verify-{tip}.json").exists()
    fs = failures(w)
    assert len(fs) == 1 and fs[0]["kind"] == "seat_failure" and fs[0]["replaces"] == bogus, fs
    assert fs[0]["result"]["api_error_status"] == 403
    log = (w["data"] / "owner-changes.tsv").read_text()
    assert "undo-seat-failure" in log and "round 2 -> 1" in log
    p, calls = run_seat(w, "verifier", [verdict(tip)])                         # the verifier runs again, same tip
    assert p.returncode == 0 and state(w)["phase"] == "verified", p.stdout + p.stderr


@pytest.mark.parametrize("how", ["real-findings-real-stream", "no-verdict-text-but-the-stream-answered",
                                 "real-findings-beside-a-refused-stream"])
def test_undo_seat_failure_refuses_a_record_a_verifier_really_wrote(world, how):
    """Either half alone refuses: the record's findings must be only "no verdict returned", and the session's own
    stream must show its call refused."""
    w = world
    wt, tip = verifying(w, round_=1, limit=4)
    real = [finding(FAULT, "the total is wrong")]
    if how == "no-verdict-text-but-the-stream-answered":
        real = [{"what": "no verdict returned", "evidence": "success"}]
    run_seat(w, "verifier", [verdict(tip, real, v="findings")])
    assert state(w)["round"] == 2
    if how == "no-verdict-text-but-the-stream-answered":  # as the old code wrote a pass with no commit
        vf = rec(w) / f"verify-{tip}.json"
        v = json.loads(vf.read_text())
        for p_ in v["passes"]:
            p_["commit"] = ""
        vf.write_text(json.dumps(v))
    stream = {**REFUSED, "session_id": "v-ok"} if how == "real-findings-beside-a-refused-stream" else verdict(tip)
    (w["data"] / "records/S1/verifier-acceptance-x.jsonl").write_text(json.dumps(stream) + "\n")
    (w["repo"] / V062 / "resume.tsv").write_text(f"S1\tundo-seat-failure\t{TODAY}\n")
    before = (rec(w) / f"verify-{tip}.json").read_bytes()
    p = undo(w)
    assert p.returncode == 1 and "refused call" in p.stderr, p.stderr
    assert (rec(w) / f"verify-{tip}.json").read_bytes() == before and state(w)["round"] == 2


# ------------------------------------------------------------------ the owner clears a stopped account


def probing_claude(w, answer, code=0):
    """A claude for the probe: `auth status` signed in; `-p` answers with this result line and exit code. It records
    each call's arguments and config folder."""
    f, log = w["tmp"] / "claude-probe", w["tmp"] / "probe-calls.txt"
    (w["tmp"] / "probe-answer.json").write_text(json.dumps(answer))
    f.write_text(f"""#!/bin/sh
echo "${{CLAUDE_CONFIG_DIR:-default}} $*" >> {log}
[ "$1" = auth ] && {{ echo '{{"loggedIn": true}}'; exit 0; }}
cat {w["tmp"] / "probe-answer.json"}
exit {code}
""")
    f.chmod(0o755)
    return {**w["env"], "OSPREY_CLAUDE_BIN": str(f)}, log


def stopped(w, account="sol"):
    (w["data"] / "accounts").mkdir(exist_ok=True)
    (w["data"] / f"accounts/{account}.stopped.json").write_text(json.dumps(
        {"account": account, "error": "oauth_org_not_allowed", "at": "2026-11-19T17:07:17Z", "seat": "verifier",
         "slice": "CO2", "message": WORDS}))


def clear(w, env, account="sol"):
    return sh([w["py"], str(w["lines"] / "clear_account.py"), account], w["repo"], env, check=False)


def test_clear_account_removes_the_stop_only_when_the_probe_is_accepted_and_logs_it(world):
    w = world
    stopped(w)
    env, calls = probing_claude(w, {"type": "result", "subtype": "success", "is_error": False, "num_turns": 1,
                                    "result": "ok", "session_id": "p-1"})
    p = clear(w, env)
    assert p.returncode == 1 and "no line" in p.stderr and stop_of(w, "sol"), p.stderr     # the owner's line first
    assert not calls.exists()                                                              # and no call without it
    (w["repo"] / V062 / "resume.tsv").write_text(f"clear-account\tsol\t{TODAY}\n")
    p = clear(w, env)
    assert p.returncode == 0, p.stdout + p.stderr
    assert stop_of(w, "sol") is None
    probes = [ln for ln in calls.read_text().splitlines() if " -p " in f" {ln} "]
    assert len(probes) == 1 and probes[0].startswith(str(w["home"] / ".claude-sol")), probes   # one call, on sol
    log = (w["data"] / "owner-changes.tsv").read_text()
    assert "clear-account" in log and "sol" in log and "oauth_org_not_allowed" in log, log
    stopped(w)
    p = clear(w, env)
    assert p.returncode == 1 and "already used" in p.stderr and stop_of(w, "sol"), p.stderr


@pytest.mark.parametrize("answer", ["refused", "exit-1", "garbage"])
def test_clear_account_keeps_the_stop_when_the_probe_is_refused(world, answer):
    w = world
    stopped(w)
    (w["repo"] / V062 / "resume.tsv").write_text(f"clear-account\tsol\t{TODAY}\n")
    body = {"refused": REFUSED, "exit-1": {"type": "result", "is_error": False, "num_turns": 1}, "garbage": "nope"}[answer]
    env, _ = probing_claude(w, body, code=1 if answer == "exit-1" else 0)
    before = (w["data"] / "accounts/sol.stopped.json").read_bytes()
    p = clear(w, env)
    assert p.returncode == 1 and p.stderr.startswith("Refused: ") and "Traceback" not in p.stderr, p.stderr
    if answer == "refused":
        assert WORDS in p.stderr
    assert (w["data"] / "accounts/sol.stopped.json").read_bytes() == before
    log = w["data"] / "owner-changes.tsv"
    assert not log.exists() or "clear-account" not in log.read_text()


def test_clear_account_refuses_an_account_not_stopped_or_not_the_owners(world):
    w = world
    env, calls = probing_claude(w, REFUSED)
    (w["repo"] / V062 / "resume.tsv").write_text(f"clear-account\tsol\t{TODAY}\nclear-account\tnobody\t{TODAY}\n")
    p = clear(w, env)
    assert p.returncode == 1 and "not stopped" in p.stderr, p.stderr
    p = clear(w, env, "nobody")
    assert p.returncode == 1 and "accounts.yaml" in p.stderr, p.stderr
    assert not calls.exists() or " -p " not in calls.read_text()


@pytest.mark.parametrize("seat", ["", "conductor", "builder", "verifier"])
def test_clear_account_is_refused_to_every_agent(world, seat):
    w = world
    kw = {"seat": seat} if seat else {}
    if seat == "builder":
        kw["wt"] = w["repo"]
    for cmd in (f"{w['py']} OspreyFlow_Build/scripts/slice_line/clear_account.py sol",
                "python3 clear_account.py sol"):
        assert refused(bash(w, cmd, **kw)), (seat, cmd)
