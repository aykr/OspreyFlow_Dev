"""Item 4 of the owner's file 004 (22 November 2026): the switch is the owner's, off as built (test_server_slot.py shows
it), and the shadow is on from the first day: the Mac runs its whole gate as now, the server's result for the same
candidate is recorded beside it, agree or differ, for every merge; the owner turns counting on after the number of
agreements he names. A comparison is made only for the same candidate (main tip, slice tip, tree hash).
"""
from __future__ import annotations

import json

from test_server_counts import gate_plan, green, setup
from test_gates import sh, world  # noqa: F401  (world is a fixture)
from test_server_slot import RID


def rows(w):
    f = w["data"] / "server-shadow.tsv"
    return [ln.split("\t") for ln in f.read_text().splitlines()[1:]] if f.exists() else []


def tally(w):
    code = (f"import sys; sys.path.insert(0, {str(w['lines'])!r}); import server_gate, json; "
            "print(json.dumps(server_gate.shadow_tally()))")
    return json.loads(sh([w["py"], "-c", code], w["repo"], w["env"]).stdout)


def test_the_shadow_records_agree_when_the_server_and_the_macs_whole_gate_are_both_green(world):
    w = world
    wt, tip = setup(w, on=False)
    green(w, tip)
    p, plan, server = gate_plan(w)
    assert p.returncode == 0 and plan is None, (p.stdout + p.stderr, plan)       # the whole gate, as now
    assert server["shadow"] == "agree", server
    rec = json.loads((w["data"] / f"records/S1/server-shadow-{RID}.json").read_text())
    assert (rec["server"], rec["mac"], rec["result"], rec["tip"]) == ("green", "green", "agree", tip), rec
    assert [r[1:8] for r in rows(w)] == [["S1", tip, RID, "green", "green", "agree", ""]], rows(w)
    assert tally(w)["agree"] == 1


def test_the_shadow_records_differ_when_the_server_was_green_and_the_mac_red(world):
    w = world
    wt, tip = setup(w, on=False)
    green(w, tip)
    p, plan, server = gate_plan(w, gate="1")
    assert p.returncode == 1 and "full gate is red" in p.stderr, p.stderr          # the merge is refused as before
    rec = json.loads((w["data"] / f"records/S1/server-shadow-{RID}.json").read_text())
    assert rec["result"] == "differ" and "the server said green, the Mac's whole gate red" in rec["why"], rec
    assert tally(w)["differ"] == 1


def test_a_red_from_both_agrees(world):
    w = world
    wt, tip = setup(w, on=False)
    green(w, tip, verdict="fail")
    p, plan, server = gate_plan(w, gate="1")
    rec = json.loads((w["data"] / f"records/S1/server-shadow-{RID}.json").read_text())
    assert (rec["server"], rec["mac"], rec["result"]) == ("red", "red", "agree"), rec


def test_a_result_for_another_candidate_is_no_comparison(world):
    w = world
    wt, tip = setup(w, on=False)
    green(w, tip, tree="0" * 40)
    p, plan, server = gate_plan(w)
    assert p.returncode == 0 and server["shadow"] == "no comparison", server
    rec = json.loads((w["data"] / f"records/S1/server-shadow-{RID}.json").read_text())
    assert "candidate tree" in rec["why"], rec
    assert tally(w) == {"agree": 0, "differ": 0, "no comparison": 1, "counted": 0}


def test_with_the_switch_on_a_counted_merge_is_marked_counted_not_compared(world):
    w = world
    wt, tip = setup(w, on=True)
    green(w, tip)
    p, plan, server = gate_plan(w)
    assert p.returncode == 0 and plan is not None and server["shadow"] == "counted", (plan, server)
