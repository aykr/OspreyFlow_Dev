"""Item 3 of the owner's file 004 (22 November 2026): the stack. The server runs main+A, main+A+B, ... at once; slices
proved as a stack land in order, each on the tree the server tested: a slice stacked on others counts only when main
is exactly the tree the server ran it on. If one is refused, the ones stacked on it are not counted and are marked to
go to the server again.

Two slices, S1 and S3, stacked in that order; the full gate is stood in and records the targets it was given.
"""
from __future__ import annotations

import json

from test_gates import built, sh, started, stop_gate, verified, world  # noqa: F401  (world is a fixture)
from test_server_counts import makefiles
from test_server_slot import RID, ready, switch

V062 = "OspreyFlow_Build/process/lanes/v062"
PASSED = ["lint-tools", "opentofu-check", "client-name-check", "lint", "typecheck", "trivy", "test"]


def second(w):
    """S3, built green and verified, beside S1."""
    tsv = w["repo"] / V062 / "slices.tsv"
    tsv.write_text(tsv.read_text() + "S3\tCO1\tAnother\t-\t2\t-\tnone\taccept3.sh\tsh accept3.sh\ttrue\n")
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'docs: S3' --trailer 'Slice-Records: yes'",
       w["repo"], w["env"])
    p, wt = started(w, "S3")
    assert p.returncode == 0, p.stdout + p.stderr
    (wt / "accept3.sh").write_text("test -f feature3.txt\n")
    sh("git add accept3.sh && git commit -qm 'test: S3 acceptance, red'", wt, w["env"])
    (wt / "feature3.txt").write_text("done\n")
    sh("git add feature3.txt && git commit -qm 'feat: S3'", wt, w["env"])
    assert stop_gate(w, wt, "S3") is None
    tip = sh("git rev-parse HEAD", wt).stdout.strip()
    t = w["tmp"] / "transcript3.jsonl"
    t.write_text(json.dumps({"type": "assistant", "text": f"pass {tip}"}) + "\n")
    (w["data"] / f"records/S3/verify-{tip}.json").write_text(json.dumps({
        "slice": "S3", "commit": tip, "verdict": "pass",
        "passes": [{"pass": "acceptance", "verdict": "pass", "commit": tip, "session": "v-3", "transcript": str(t)}]}))
    f = w["data"] / "records/S3/state.json"
    f.write_text(json.dumps({**json.loads(f.read_text()), "phase": "verified", "tip": tip}))
    return wt, tip


def stacked(w, tip1, tip3):
    """The runner's result for main+S1, main+S1+S3: each member's tree as the server made it."""
    main = sh("git rev-parse main", w["repo"]).stdout.strip()
    t1 = sh(["git", "merge-tree", "--write-tree", main, tip1], w["repo"]).stdout.split()[0]
    m1 = sh(["git", "commit-tree", t1, "-p", main, "-p", tip1, "-m", "server: S1"], w["repo"], w["env"]).stdout.strip()
    t13 = sh(["git", "merge-tree", "--write-tree", m1, tip3], w["repo"]).stdout.split()[0]
    member = {"verdict": "pass", "failing": {"tests": [], "targets": []}, "passed_targets": PASSED, "not_run": {}}
    r = {"state": "done", "id": RID, "main": main,
         "stack": [{"slice": "S1", "tip": tip1, "tree": t1, **member}, {"slice": "S3", "tip": tip3, "tree": t13, **member}]}
    (w["tmp"] / "ew" / f"{RID}.json").write_text(json.dumps(r))
    d = w["repo"] / V062 / "early_warning"
    d.mkdir(parents=True, exist_ok=True)
    for sid, tip in (("S1", tip1), ("S3", tip3)):
        (d / f"{sid}-{tip[:8]}.md").write_text(f"# Early warning: {sid} at {tip[:8]}: GREEN\n\n- Run id: `{RID}`\n")
    return r


def merge_of(w, sid, gate="0"):
    (w["tmp"] / "plan.json").unlink(missing_ok=True)
    p = sh([w["py"], str(w["lines"] / "merge_slice.py"), "merge", sid], w["repo"],
           {**w["env"], "TEST_GATE": gate, "TEST_GATE_PLAN": str(w["tmp"] / "plan.json")}, check=False)
    plan = json.loads((w["tmp"] / "plan.json").read_text()) if (w["tmp"] / "plan.json").exists() else "not run"
    m = w["data"] / f"records/{sid}/merged.json"
    return p, plan, json.loads(m.read_text()).get("server") if m.exists() else None


def setup(w):
    makefiles(w)
    wt1, tip1 = ready(w)
    wt3, tip3 = second(w)
    switch(w)
    stacked(w, tip1, tip3)
    return tip1, tip3


def test_a_stack_lands_in_order_each_on_the_tree_the_server_tested(world):
    w = world
    tip1, tip3 = setup(w)
    p, plan, server = merge_of(w, "S1")
    assert p.returncode == 0 and server["counted"] is True, (p.stdout + p.stderr, server)
    p, plan, server = merge_of(w, "S3")
    assert p.returncode == 0, p.stdout + p.stderr
    assert server["counted"] is True and server["run_id"] == RID, server
    assert plan == [], plan                                    # every target proved: the Mac runs none of the gate


def test_a_refused_slice_under_the_stack_leaves_the_ones_above_uncounted_and_sent_again(world):
    w = world
    tip1, tip3 = setup(w)
    p, plan, server = merge_of(w, "S1", gate="1")              # S1's remainder red: refused
    assert p.returncode == 1, p.stdout + p.stderr
    again = json.loads((w["data"] / "records/S3/server-again.json").read_text())
    assert again["run_id"] == RID and again["tip"] == tip3 and "S1" in again["because"], again
    p, plan, server = merge_of(w, "S3")
    assert p.returncode == 0, p.stdout + p.stderr
    assert plan is None and server["counted"] is False and "stacked on S1" in server["why"], (plan, server)


def test_a_stack_out_of_order_counts_nothing_for_the_one_landed_out_of_turn(world):
    w = world
    tip1, tip3 = setup(w)
    p, plan, server = merge_of(w, "S3")                          # S3 before S1: main is not main+S1
    assert p.returncode == 0, p.stdout + p.stderr
    assert plan is None and server["counted"] is False and "stacked on S1" in server["why"], server
