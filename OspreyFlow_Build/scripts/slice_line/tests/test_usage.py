"""Usage per slice, seat and account (the owner's ruling 4(e)): every seat session's row, the conductor's own (one per
session, with its scouts'), totals per account and per slice with the account's windows beside them, and the word that
cost is a list-price estimate, not a bill.
"""
from __future__ import annotations

import json
import subprocess

from test_gates import SYSPY, sh, world  # noqa: F401  (world is a fixture)

HEADER = ("at\tslice\tbuild\tseat\taccount\tmodel\teffort\tsession\tinput\tcache_create\tcache_read\toutput\tcost_usd\t"
          "five_hour\tseven_day\n")
TURN = {"type": "assistant", "message": {"model": "claude-sonnet", "usage": {
    "input_tokens": 10, "cache_creation_input_tokens": 5, "cache_read_input_tokens": 100, "output_tokens": 7}}}


def transcript(w, session, account_dir=".claude"):
    """A session's transcript where Claude Code keeps it, with one scout's beside it."""
    p = w["home"] / account_dir / "projects/-repo" / f"{session}.jsonl"
    (p.parent / session / "subagents").mkdir(parents=True)
    p.write_text(json.dumps(TURN) + "\n" + json.dumps(TURN) + "\n")
    (p.parent / session / "subagents/scout-1.jsonl").write_text(json.dumps(TURN) + "\n")
    return p


def windows(w, account, **kw):
    d = w["data"] / "accounts"
    d.mkdir(exist_ok=True)
    (d / f"{account}.json").write_text(json.dumps({"windows": {
        k: {"utilization": v, "resetsAt": 4102444800} for k, v in kw.items()}}))


def usage_rows(w):
    f = w["data"] / "usage.tsv"
    return [dict(zip(HEADER.split(), ln.split("\t"))) for ln in f.read_text().splitlines()[1:]] if f.exists() else []


def test_the_session_end_hook_writes_the_conductors_row_with_its_scouts_and_the_accounts_windows(world):
    w = world
    windows(w, "default", seven_day=0.07)
    tp = transcript(w, "c-1")
    ev = {"session_id": "c-1", "transcript_path": str(tp), "hook_event_name": "SessionEnd", "reason": "prompt_input_exit"}
    env = {**w["env"], "OSPREY_SEAT": "conductor", "OSPREY_ACCOUNT": "default"}
    p = subprocess.run([SYSPY, str(w["data"] / "bin/usage_hook.py"), "session-end"], input=json.dumps(ev), env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    [r] = usage_rows(w)
    assert (r["seat"], r["account"], r["session"], r["input"], r["output"]) == ("conductor+scouts", "default", "c-1", "30", "21")
    assert r["seven_day"] == "0.07" and r["five_hour"] == "", r


def test_run_seat_writes_the_conductors_row_when_the_hook_wrote_none_and_never_twice(world):
    w = world
    transcript(w, "c-2")
    code = (f"import sys; sys.path.insert(0, {str(w['lines'])!r}); import run_seat; "
            "run_seat.conductor_usage('c-2', 'default'); run_seat.conductor_usage('c-2', 'default')")
    sh([w["py"], "-c", code], w["repo"], w["env"])
    rows = usage_rows(w)
    assert len(rows) == 1 and rows[0]["session"] == "c-2" and rows[0]["input"] == "30", rows


def test_board_usage_totals_per_account_and_per_slice_with_the_windows_and_says_cost_is_an_estimate(world):
    w = world
    (w["data"] / "usage.tsv").write_text(HEADER + "".join(
        "\t".join(map(str, r)) + "\n" for r in (
            ("t", "S1", "CO1", "builder", "default", "sonnet", "high", "a", 100, 0, 1000, 50, 1.25, "", 0.07),
            ("t", "S1", "CO1", "verifier:acceptance", "sol", "opus", "high", "b", 200, 0, 0, 20, 2.5, 0.3, 0.3),
            ("t", "S2", "CO2", "builder", "sol", "sonnet", "high", "c", 10, 0, 0, 5, 0.25, 0.31, 0.31),
            ("t", "(all)", "", "conductor+scouts", "default", "sonnet", "", "d", 1, 0, 0, 1, "", "", 0.07))))
    windows(w, "default", seven_day=0.08)
    windows(w, "sol", five_hour=0.31, seven_day=0.32)
    p = sh([w["py"], str(w["lines"] / "board.py"), "--usage"], w["repo"], w["env"])
    out = p.stdout
    assert "list-price estimate, not a bill" in out
    per_account = out.split("per account", 1)[1]
    assert "default" in per_account and "1.25" in per_account and "sol" in per_account and "2.75" in per_account, out
    assert "five-hour 31%" in per_account and "seven-day 32%" in per_account, out
    assert "five-hour: not reported" in per_account and "seven-day 8%" in per_account, out  # the default account's stream
    per_slice = out.split("per slice", 1)[1].split("per account", 1)[0]
    assert "S1" in per_slice and "3.75" in per_slice and "S2" in per_slice and "(all)" in per_slice, out
