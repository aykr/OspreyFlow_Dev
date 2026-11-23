"""One more round after a merge refusal, without the owner's line (his file 012, A1, 23 November 2026).

A standing permission in standing.tsv, beside the standing accept: `round-after-refusal per-day <N> <date>`. When a
verified slice's merge is refused past its rounds limit with the cause recorded (the gate's failing tests or targets),
resume.py send-back gives it one round to fix that cause alone, in place of the owner's add-round line, once for that
refusal; each use is logged in owner-changes.tsv and self-clears.tsv and shown on the board, against a daily budget.
Never: the same cause a second time for the slice; a finding that names a key, a credential or a security rule; a slice
stopped for red checks; a slice the owner has parked; past the budget. On 22 November it would have replaced four of
the owner's add-round lines (IS5a twice, SE8c, SE6b: each a refusal past the limit with its failing tests named).

Each case refuses a merge as the line refuses it (test_send_back's AD2 log: three failing tests named) and runs resume.py
as the conductor runs it.
"""
from __future__ import annotations

import json

import pytest

from test_gates import TODAY, sh, world  # noqa: F401  (world is a fixture)
from test_send_back import AD2_TESTS, V062, refused_by_the_gate, resume, set_state, state

ON = f"round-after-refusal\tper-day\t10\t{TODAY}\n"
ACCEPT = "accept-test-gaps\tfrom-round\t3\t2026-11-19\n"


def permission(w, body):
    f = w["repo"] / V062 / "standing.tsv"
    if body is None:
        f.unlink(missing_ok=True)
    else:
        f.write_text(body)


def past_the_limit(w, body=ON):
    """S1 refused by the merge gate in its last round, with the owner's standing file as given."""
    permission(w, body)
    wt, tip = refused_by_the_gate(w)
    lim = state(w)["rounds_limit"]
    set_state(w, round=lim)
    return tip, lim


def gate_record(w, tip):
    return w["data"] / f"records/S1/verify-gate-{tip}.json"


def changes(w):
    f = w["data"] / "owner-changes.tsv"
    return [ln.split("\t") for ln in f.read_text().splitlines()[1:]] if f.exists() else []


def logged(w, at, slice_id, action, detail):
    f = w["data"] / "owner-changes.tsv"
    if not f.exists():
        f.write_text("at\tslice\taction\tdetail\n")
    with f.open("a") as fh:
        fh.write(f"{at}\t{slice_id}\t{action}\t{detail}\n")


def nothing_given(w, p, before, *words):
    out = p.stdout + p.stderr
    assert p.returncode == 1 and p.stderr.startswith("Refused: ") and "Traceback" not in out, out
    assert all(x in p.stderr for x in words), p.stderr
    assert (w["data"] / "records/S1/state.json").read_bytes() == before
    assert not [r for r in changes(w) if "standing.tsv round-after-refusal" in r[3]]
    assert not list((w["data"] / "records/S1").glob("round-after-refusal-*.json"))


def board(w):
    return sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False).stdout


@pytest.mark.parametrize("body", [None, "", ACCEPT, f"round-after-refusal\tper-day\t11\t{TODAY}\n",
                                  f"round-after-refusal\tper-day\t0\t{TODAY}\n", "round-after-refusal\tper-day\t10\n",
                                  f"round-after-refusal\t10\t{TODAY}\n", ON + ON,
                                  ON + f"round-after-refusals\tper-day\t10\t{TODAY}\n"],
                         ids=["missing", "empty", "the-accept-alone", "more-than-ten", "none-a-day", "no-date",
                              "no-per-day", "twice", "beside-a-misspelt-line"])
def test_round_after_refusal_off_or_unclear_gives_nothing_past_the_limit(world, body):
    w = world
    tip, lim = past_the_limit(w, body)
    before = (w["data"] / "records/S1/state.json").read_bytes()
    nothing_given(w, resume(w, "send-back"), before, "add-round", "round-after-refusal")


def test_round_after_refusal_gives_one_round_for_the_named_cause_logged_and_shown(world):
    w = world
    tip, lim = past_the_limit(w, ACCEPT + ON)              # beside the standing accept's own line
    p = resume(w, "send-back")
    assert p.returncode == 0, p.stdout + p.stderr
    st = state(w)
    assert (st["phase"], st["round"], st["rounds_limit"]) == ("building", lim + 1, lim + 1), st
    assert "standing permission (round-after-refusal)" in p.stdout, p.stdout
    rows = [r for r in changes(w) if r[1] == "S1" and r[2] == "send-back"]
    assert len(rows) == 1 and rows[0][3].startswith("standing.tsv round-after-refusal: one more round"), rows
    assert "use 1 of 10 today" in rows[0][3] and f"limit {lim} -> {lim + 1}" in rows[0][3], rows
    clears = (w["data"] / "self-clears.tsv").read_text()
    assert "\tS1\trefused\tround-after-refusal\t" in clears, clears
    shown = board(w)
    assert "a round given by the line: S1 (a merge refusal, standing permission round-after-refusal)" in shown, shown
    assert "standing permission round-after-refusal: on, 1 of 10 used today" in shown, shown
    status = (w["repo"] / "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/status.js").read_text()
    body = json.loads(status.split("window.OSPREY_STATUS = ", 1)[1].rstrip().rstrip(";"))
    assert {"name": "round-after-refusal", "used": 1, "per_day": 10, "on": True}.items() <= \
        next(x for x in body["standing_today"] if x["name"] == "round-after-refusal").items(), body["standing_today"]
    code = f"import sys; sys.path.insert(0, {str(w['lines'])!r}); import run_seat; print(run_seat.last_findings('S1'))"
    told = sh([w["py"], "-c", code], w["repo"], w["env"]).stdout
    assert "standing permission for this merge refusal alone" in told and all(t in told for t in AD2_TESTS), told
    rec = json.loads((w["data"] / f"records/S1/round-after-refusal-{tip}.json").read_text())
    assert rec["cause"] and all(f.endswith(".py") for f in rec["cause"]), rec


def refused_again(w, tip, lim, files=None):
    """S1 refused again in its new last round; with `files`, the gate names other failing tests this time."""
    set_state(w, phase="refused", refused_for="gate", round=lim + 1, rounds_limit=lim + 1, tip=tip)
    if files:
        g = json.loads(gate_record(w, tip).read_text())
        g["findings"] = [{"file": f, "what": f"The merge gate's full run failed {f}::test_x", "evidence": "log"}
                         for f in files]
        gate_record(w, tip).write_text(json.dumps(g))


def test_round_after_refusal_never_twice_for_the_same_cause(world):
    w = world
    tip, lim = past_the_limit(w)
    assert resume(w, "send-back").returncode == 0
    refused_again(w, tip, lim)
    before = (w["data"] / "records/S1/state.json").read_bytes()
    p = resume(w, "send-back")
    out = p.stdout + p.stderr
    assert p.returncode == 1 and "Traceback" not in out and "same cause" in p.stderr, out
    assert (w["data"] / "records/S1/state.json").read_bytes() == before
    assert len([r for r in changes(w) if "standing.tsv round-after-refusal" in r[3]]) == 1
    (w["repo"] / V062 / "resume.tsv").write_text(f"S1\tadd-round\t{TODAY}\n")   # it comes to the owner
    assert resume(w, "send-back").returncode == 0 and state(w)["round"] == lim + 2


def test_round_after_refusal_gives_a_round_for_another_cause(world):
    w = world
    tip, lim = past_the_limit(w)
    assert resume(w, "send-back").returncode == 0
    refused_again(w, tip, lim, files=["OspreyFlow_Build/tests/test_other.py"])
    p = resume(w, "send-back")
    assert p.returncode == 0, p.stdout + p.stderr
    assert state(w)["round"] == lim + 2 and "use 2 of 10 today" in p.stdout, p.stdout


@pytest.mark.parametrize("what", ["the token is logged", "an auth check", "the API key", "security headers"])
def test_round_after_refusal_never_for_a_finding_naming_a_key_a_credential_or_a_security_rule(world, what):
    w = world
    tip, lim = past_the_limit(w)
    g = json.loads(gate_record(w, tip).read_text())
    g["findings"][0]["what"] += f" ({what})"
    gate_record(w, tip).write_text(json.dumps(g))
    before = (w["data"] / "records/S1/state.json").read_bytes()
    nothing_given(w, resume(w, "send-back"), before, "a key, a credential or a security rule")


@pytest.mark.parametrize("named", [False, True], ids=["no-red-named", "one-red-of-two-unnamed"])
def test_round_after_refusal_never_when_the_cause_is_not_recorded(world, named):
    w = world
    tip, lim = past_the_limit(w)
    g = json.loads(gate_record(w, tip).read_text())
    g["findings"] = [{"file": "", "what": "The merge gate's full run was red: see the log", "evidence": "the log"}]
    if named:  # a red the gate names beside one it does not: the cause is not recorded whole
        g["findings"].insert(0, {"file": "OspreyFlow_Build/tests/test_x.py", "what": "failed test_x", "evidence": "log"})
    gate_record(w, tip).write_text(json.dumps(g))
    before = (w["data"] / "records/S1/state.json").read_bytes()
    nothing_given(w, resume(w, "send-back"), before, "names no failing test")


@pytest.mark.parametrize("how", ["red-stop-cleared-by-the-owner", "red-stop-cleared-by-the-line", "parked"])
def test_round_after_refusal_never_for_a_slice_stopped_on_red_checks_or_parked(world, how):
    w = world
    tip, lim = past_the_limit(w)
    if how == "red-stop-cleared-by-the-owner":
        logged(w, "2026-11-20T00:00:00Z", "S1", "clear-stop", f"resume.tsv 2026-11-20 clear-stop: red stop at {tip[:10]} cleared")
        words = "stopped for red checks"
    elif how == "red-stop-cleared-by-the-line":
        (w["data"] / "self-clears.tsv").write_text("at\tslice\tstop\tcause\twhat\n2026-11-20T00:00:00Z\tS1\tred\ta\tmain merged\n")
        words = "stopped for red checks"
    else:
        (w["repo"] / V062 / "resume.tsv").write_text(f"S1\tpark\t{TODAY}\n")
        words = "parked"
        code = f"import sys; sys.path.insert(0, {str(w['lines'])!r}); import common; print(common.unapplied_lines())"
        assert sh([w["py"], "-c", code], w["repo"], w["env"]).stdout.strip() == "[]"   # never a line waiting
    before = (w["data"] / "records/S1/state.json").read_bytes()
    nothing_given(w, resume(w, "send-back"), before, words)


def test_round_after_refusal_at_its_budget_gives_no_more_today_and_the_board_says_so(world):
    w = world
    tip, lim = past_the_limit(w, f"round-after-refusal\tper-day\t1\t{TODAY}\n")
    logged(w, "2020-01-01T00:00:00Z", "S8", "send-back", "standing.tsv round-after-refusal: an old day's use")
    logged(w, f"{TODAY}T00:00:01Z", "S9", "send-back", "standing.tsv round-after-refusal: today's one use")
    before = (w["data"] / "records/S1/state.json").read_bytes()
    p = resume(w, "send-back")
    out = p.stdout + p.stderr
    assert p.returncode == 1 and "Traceback" not in out and "budget" in p.stderr, out
    assert (w["data"] / "records/S1/state.json").read_bytes() == before
    assert "standing permission round-after-refusal: AT ITS BUDGET, 1 of 1 used today" in board(w)
    permission(w, f"round-after-refusal\tper-day\t2\t{TODAY}\n")                # the old day's use is not counted
    assert resume(w, "send-back").returncode == 0


def test_round_after_refusal_within_the_limit_is_not_used(world):
    w = world
    permission(w, ON)
    refused_by_the_gate(w)
    set_state(w, round=1, rounds_limit=3)
    p = resume(w, "send-back")
    assert p.returncode == 0, p.stdout + p.stderr
    assert not [r for r in changes(w) if "standing.tsv" in r[3]] and "on, 0 of 10 used today" in board(w)


@pytest.mark.parametrize("body,on", [(ACCEPT + ON, True), (ON + ACCEPT, True), (ACCEPT + "accept-test-gaps-x 3\n", False)],
                         ids=["accept-first", "accept-second", "beside-a-line-of-no-name"])
def test_round_after_refusal_the_standing_accept_still_reads_its_own_line(world, body, on):
    w = world
    permission(w, body)
    code = (f"import sys; sys.path.insert(0, {str(w['lines'])!r}); import common; r, why = common.standing_rule(); "
            "print(bool(r), why)")
    said = sh([w["py"], "-c", code], w["repo"], w["env"]).stdout
    assert said.startswith(str(on)), said
