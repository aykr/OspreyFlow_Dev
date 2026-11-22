"""Item 6 of the owner's file 004 (22 November 2026): measure and report. `merge_slice.py server-report` (read only)
says the Mac-only remainder's time and the merge's time with the server's green counted, the same for merges that ran
the whole gate, how many refusals the server caught before the slot (a server red rerun red on the Mac), and the
shadow's tally, from the records the merges write.
"""
from __future__ import annotations

import json

from test_gates import sh, world  # noqa: F401  (world is a fixture)
from test_server_counts import gate_plan, green, setup

STEPS = ["checks before the gate", "red before: the acceptance on the base", "the merge onto main",
         "the acceptance, checks and scans on the merge result", "today's full gate", "landing on main", "the push"]


def report(w):
    p = sh([w["py"], str(w["lines"] / "merge_slice.py"), "server-report", "--json"], w["repo"], w["env"], check=False)
    assert p.returncode == 0, p.stdout + p.stderr
    return json.loads(p.stdout[:p.stdout.rindex("}") + 1])


def records(w):
    return {str(f): f.read_bytes() for f in sorted((w["data"] / "records").rglob("*")) if f.is_file()}


def fake_merge(w, sid, gate_s, counted):
    d = w["data"] / "records" / sid
    d.mkdir(parents=True, exist_ok=True)
    mid = f"{sid.lower()}0000"[:8]
    (d / "merged.json").write_text(json.dumps({"slice": sid, "merge": "a" * 40, "gate_run": f"merge-{mid}.log",
                                               "server": {"counted": counted}}))
    (d / f"merge-progress-{mid}.json").write_text(json.dumps({"state": "finished", "result": "merged", "done": [
        {"name": n, "result": "passed", "seconds": gate_s if n == "today's full gate" else 10} for n in STEPS]}))


def test_a_counted_merge_is_measured_from_its_own_records_and_the_report_changes_nothing(world):
    w = world
    wt, tip = setup(w, on=True)
    green(w, tip)
    p, plan, server = gate_plan(w)
    assert p.returncode == 0, p.stdout + p.stderr
    before = records(w)
    r = report(w)
    assert r["counted"]["merges"] == 1 and isinstance(r["counted"]["remainder_s"], int), r
    assert r["counted"]["each"][0]["slice"] == "S1" and r["whole"]["merges"] == 0, r
    assert r["shadow"]["counted"] == 1
    assert records(w) == before                                    # read only


def test_the_report_gives_the_averages_and_the_refusals_caught_before_the_slot(world):
    w = world
    fake_merge(w, "S7", 1500, False)
    fake_merge(w, "S8", 1700, False)
    fake_merge(w, "S9", 300, True)
    for sid, rid, res in (("S7", "1" * 16, "red"), ("S8", "2" * 16, "red"), ("S9", "3" * 16, "green")):
        (w["data"] / f"records/{sid}/server-rerun-{rid}.json").write_text(json.dumps({"result": res}))
    r = report(w)
    assert r["whole"] == {"merges": 2, "gate_s": 1600, "merge_s": 1660}, r["whole"]
    assert (r["counted"]["merges"], r["counted"]["remainder_s"], r["counted"]["merge_s"]) == (1, 300, 360), r
    assert r["caught_before_the_slot"] == 2 and r["environment_differences"] == 1, r
    words = sh([w["py"], str(w["lines"] / "merge_slice.py"), "server-report"], w["repo"], w["env"]).stdout
    assert "the Mac-only remainder took 5 min 0 s on average, the whole merge 6 min 0 s" in words, words
    assert "refusals the server caught before the slot (red there, rerun red on the Mac): 2" in words, words
