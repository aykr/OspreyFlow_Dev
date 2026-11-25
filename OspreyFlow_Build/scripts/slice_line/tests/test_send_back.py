"""A slice the merge gate refuses goes back to its builder with the gate's findings (the owner's order of 18 November
2026, after AD2; diffs/resume-ad2-round-2.sh is the specification).

The merge script runs as the conductor runs it, in a throwaway repository; its full gate is the suite's stand-in, whose
log holds AD2's real refusal (tests/fixtures/ad2_merge_gate.log: main at 8951b38 merged with lane/slice-AD2 at 993a434,
test_admin_sections.py failing for the People section, reproduced in a scratch clone on 18 November 2026).
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import pytest

from test_gates import built, merge, sh, verified, world  # noqa: F401  (world is a fixture)

AD2_LOG = str(Path(__file__).resolve().parent / "fixtures/ad2_merge_gate.log")
V062 = "OspreyFlow_Build/process/lanes/v062"
from test_gates import TODAY  # noqa: E402  (the run's one date: 9)
AD2_TESTS = ("test_each_built_section_s_routes_need_its_right[people]",
             "test_each_section_s_routes_refuse_a_principal_without_its_right[people]",
             "test_each_shared_read_is_read_by_exactly_the_sections_named")


def state(w):
    return json.loads((w["data"] / "records/S1/state.json").read_text())


def set_state(w, **kw):
    p = w["data"] / "records/S1/state.json"
    st = json.loads(p.read_text())
    st.update(kw)
    p.write_text(json.dumps(st))


def resume(w, action):
    return sh([w["py"], str(w["lines"] / "resume.py"), "S1", action], w["repo"], w["env"], check=False)


def refused_by_the_gate(w):
    wt, tip = built(w)
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    before = sh("git rev-parse main", w["repo"]).stdout
    p = merge(w, gate="2", gate_log=AD2_LOG)
    assert p.returncode == 1 and "full gate is red" in p.stderr, p.stderr
    assert sh("git rev-parse main", w["repo"]).stdout == before
    return wt, tip


def test_a_red_full_gate_records_the_failing_tests_as_findings_and_the_board_shows_it(world):
    w = world
    wt, tip = refused_by_the_gate(w)
    st = state(w)
    assert st["phase"] == "refused" and st["refused_tests"] == 3, st
    rec = json.loads((w["data"] / f"records/S1/verify-gate-{tip}.json").read_text())
    assert rec["verdict"] == "findings" and rec["commit"] == tip
    what = json.dumps(rec["findings"])
    assert all(t in what for t in AD2_TESTS), what
    assert "schedule_preview_route" in what and "69 more items" in what      # the failing lines, not only names
    assert "ruff check" not in what and "....." not in what                   # not the whole log
    # AD2's tests are not in its own files: once, the conductor's to rerun (the owner, 23 and 24 November 2026)
    body = board(w)
    assert "refused by another test (test_admin_sections.py)" in body["builds"]["CO1"]["note"], body["builds"]["CO1"]
    p = merge(w, gate="2", gate_log=AD2_LOG)                                   # the rerun: red again, as AD2's was
    assert p.returncode == 1 and "full gate is red" in p.stderr, p.stderr
    body = board(w)
    assert body["builds"]["CO1"]["state"] == "stopped" and "refused by the gate: 3 tests" in body["builds"]["CO1"]["note"]


def board(w):
    out = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    status = (w["repo"] / "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/status.js").read_text()
    return json.loads(status.split("window.OSPREY_STATUS = ", 1)[1].rstrip().rstrip(";"))


def test_the_builders_prompt_carries_the_gates_findings(world):
    w = world
    refused_by_the_gate(w)
    code = (f"import sys; sys.path.insert(0, {str(w['lines'])!r}); import run_seat; "
            "print(run_seat.last_findings('S1'))")
    p = sh([w["py"], "-c", code], w["repo"], w["env"])
    assert all(t in p.stdout for t in AD2_TESTS), p.stdout


@pytest.mark.parametrize("setting", ["thrift", "balanced"])
def test_send_back_within_the_rounds_limit_needs_no_owner_line_and_advances_the_round(world, setting):
    """Under a one-round and a four-round dial (the dial is auto, so which one the slice started on depends on the
    hour: GitHub run 44464391430 failed this case at 05:21 UTC on thrift's one round). The case is about a round below
    the limit, so it pins one, whatever the dial gave."""
    w = world
    dial = w["repo"] / V062 / "dial.yaml"
    dial.write_text(re.sub(r"(?m)^current: \w+", f"current: {setting}", dial.read_text()))
    refused_by_the_gate(w)
    set_state(w, round=1, rounds_limit=max(2, state(w)["rounds_limit"]))
    st0 = state(w)
    p = resume(w, "send-back")
    assert p.returncode == 0, p.stdout + p.stderr
    st = state(w)
    assert (st["phase"], st["round"], st["rounds_limit"]) == ("building", st0["round"] + 1, st0["rounds_limit"])
    log = (w["data"] / "owner-changes.tsv").read_text()
    assert "send-back" in log and "within the rounds limit" in log


def test_send_back_past_the_rounds_limit_needs_the_owners_add_round_line(world):
    w = world
    refused_by_the_gate(w)
    lim = state(w)["rounds_limit"]
    set_state(w, round=lim)
    before = (w["data"] / "records/S1/state.json").read_bytes()
    p = resume(w, "send-back")
    assert p.returncode == 1 and p.stderr.startswith("Refused: ") and "add-round" in p.stderr, p.stderr
    assert (w["data"] / "records/S1/state.json").read_bytes() == before
    (w["repo"] / V062 / "resume.tsv").write_text(f"S1\tadd-round\t{TODAY}\n")
    p = resume(w, "send-back")
    assert p.returncode == 0, p.stdout + p.stderr
    st = state(w)
    assert (st["phase"], st["round"], st["rounds_limit"]) == ("building", lim + 1, lim + 1)


def test_send_back_refuses_a_slice_the_gate_did_not_refuse(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    p = resume(w, "send-back")
    assert p.returncode == 1 and "not refused by the merge gate" in p.stderr, p.stderr
    assert state(w)["phase"] == "verified"


def test_a_merge_refused_for_a_records_only_conflict_goes_back_without_spending_a_round(world):
    """BL6: the branch's copy of RULINGS.md against main's newer one. send-back merges main in; the round is the same."""
    w = world
    rules = w["repo"] / V062 / "RULINGS.md"
    rules.write_text("# Rulings\n")
    sh(f"git add {V062}/RULINGS.md && git commit -qm 'docs: rulings' --trailer 'Slice-Records: yes'", w["repo"], w["env"])
    wt, tip = built(w, extra={f"{V062}/RULINGS.md": "# Rulings\n\nthe branch's copy\n"})
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    rules.write_text("# Rulings\n\nmain's newer text\n")
    sh(f"git commit -qam 'docs: newer rulings' --trailer 'Slice-Records: yes'", w["repo"], w["env"])
    p = merge(w)
    assert p.returncode == 1 and "does not merge cleanly" in p.stderr, p.stderr
    st0 = state(w)
    assert st0["phase"] == "refused" and st0["refused_for"] == "records"
    p = resume(w, "send-back")
    assert p.returncode == 0, p.stdout + p.stderr
    st = state(w)
    assert (st["phase"], st["round"]) == ("building", st0["round"])
    assert (wt / V062 / "RULINGS.md").read_text() == "# Rulings\n\nmain's newer text\n"
