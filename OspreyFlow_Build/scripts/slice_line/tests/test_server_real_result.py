"""The owner's file 011 (23 November 2026): the trial of the server's green did not count. PL7a2a's run 97dc976c7be6d175
was a finished pass on main c593730 for the Mac's own candidate tree 06e6087fb5, main unmoved, the switch on; the merge
recorded "the server's candidate tree None is not the Mac's 06e6087fb5", server_verdict null, shadow "no comparison".

The cause was the shape. The runner gives a slice's whole result at the top level (tree, verdict, passed_targets, ...),
with `group`, `position` and `of` for its place in a stack, and a `stack` list of bare {slice, tip} members, even for a
slice run alone. server_gate read any `stack` list as the shape asked for on 22 November (each member carrying its own
result) and took the bare member: no tree, no verdict.

The fixture is that run's result exactly as `early_warning.py fetch 97dc976c7be6d175` printed it on 23 November 2026
(tests/fixtures/server_result_97dc976c7be6d175.json), not a hand-made one. The first test reads it unchanged, against its
own real hashes. The others run the merge in the suite's world: there the hashes of main, the tip and the tree are the
world's own (a real run's hashes name commits only the real repository has), and nothing else of the result changes.
"""
from __future__ import annotations

import json
from pathlib import Path

from test_gates import sh, world  # noqa: F401  (world is a fixture)
from test_server_counts import gate_plan, makefiles, candidate_tree
from test_server_slot import note, ready, switch

REAL = json.loads((Path(__file__).resolve().parent / "fixtures/server_result_97dc976c7be6d175.json").read_text())
REAL_ID = "97dc976c7be6d175"


def call(w, expr):
    code = (f"import sys, json; sys.path.insert(0, {str(w['lines'])!r}); import server_gate; "
            f"r = json.loads(sys.stdin.read()); print(json.dumps({expr}))")
    return json.loads(sh([w["py"], "-c", code], w["repo"], w["env"], input=json.dumps(REAL)).stdout)


def test_the_real_result_reads_as_its_own_tree_and_verdict_and_is_the_same_candidate(world):
    w = world
    assert (REAL["id"], REAL["slice"], REAL["position"], REAL["of"]) == (REAL_ID, "PL7a2a", 1, 1)  # the run, unchanged
    e = call(w, f"server_gate.element(r, 'PL7a2a', {REAL['tip']!r})")
    assert (e["tree"], e["verdict"], e["state"], e["main"]) == (REAL["tree"], "pass", "done", REAL["main"]), e
    assert e["index"] == 0 and e["below"] == [] and e["above"] == [] and e["passed_targets"] == REAL["passed_targets"]
    why = call(w, f"server_gate.same_candidate(server_gate.element(r, 'PL7a2a', {REAL['tip']!r}), {REAL['main']!r}, "
                  f"{REAL['tip']!r}, {REAL['tree']!r})")
    assert why is None, why                                        # the Mac's tree for that merge was 06e6087fb5


def real_in_the_world(w, tip):
    """The real result with the world's main, tip and tree in place of the real repository's; nothing else changed."""
    main = sh("git rev-parse main", w["repo"]).stdout.strip()
    r = json.loads(json.dumps(REAL))
    r.update(slice="S1", main=main, holds_main=main, tip=tip, tree=candidate_tree(w, tip),
             stack=[{"slice": "S1", "tip": tip}])
    (w["tmp"] / "ew" / f"{REAL_ID}.json").write_text(json.dumps(r))
    return r


def trial(w, on):
    makefiles(w)
    wt, tip = ready(w)
    switch(w, "on\n" if on else None)
    note(w, tip, rid=REAL_ID, headline="GREEN")
    real_in_the_world(w, tip)
    return gate_plan(w)


def test_with_the_switch_on_a_green_for_the_macs_tree_on_an_unmoved_main_counts(world):
    p, plan, server = trial(world, on=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert server["same"] is True and server["server_verdict"] == "pass", server
    assert server["counted"] is True and server["run_id"] == REAL_ID, server
    assert plan is not None and server["shadow"] == "counted", (plan, server)    # not the whole gate


def test_with_the_switch_off_the_same_green_is_agree_in_the_shadow(world):
    p, plan, server = trial(world, on=False)
    assert p.returncode == 0, p.stdout + p.stderr
    assert plan is None and server["counted"] is False, (plan, server)          # the whole gate, as now
    assert server["shadow"] == "agree" and server["server_verdict"] == "pass", server


B_ID, A_TIP, B_TIP = "0123456789abcdef", "a" * 40, "b" * 40


def stacked(w, **b_change):
    """The real result's shape for a stack of two (A then B), each its own run: B's run is the real one with B's place."""
    ready(w)                                                       # the early warning stood in, to fetch A's run
    a = {**json.loads(json.dumps(REAL)), "slice": "A", "tip": A_TIP, "tree": "1" * 40,
         "group": [REAL_ID, B_ID], "position": 1, "of": 2, "stack": [{"slice": "A", "tip": A_TIP}, {"slice": "B", "tip": B_TIP}]}
    (w["tmp"] / "ew" / f"{REAL_ID}.json").write_text(json.dumps(a))
    return {**a, "id": B_ID, "slice": "B", "tip": B_TIP, "tree": "2" * 40, "position": 2, **b_change}


def element_of(w, r, slice_id, tip):
    code = (f"import sys, json; sys.path.insert(0, {str(w['lines'])!r}); import server_gate; "
            f"print(json.dumps(server_gate.element(json.loads(sys.stdin.read()), {slice_id!r}, {tip!r})))")
    return json.loads(sh([w["py"], "-c", code], w["repo"], w["env"], input=json.dumps(r)).stdout)


def test_a_run_stacked_above_another_takes_main_as_the_tree_of_the_run_below(world):
    w = world
    e = element_of(w, stacked(w), "B", B_TIP)
    assert (e["index"], e["base_tree"], e["below"], e["above"], e["tree"]) == (1, "1" * 40, ["A"], [], "2" * 40), e


def test_a_stack_that_does_not_place_the_run_where_its_position_says_never_counts(world):
    w = world
    r = stacked(w, stack=[{"slice": "A", "tip": A_TIP}, {"slice": "C", "tip": "c" * 40}])
    e = element_of(w, r, "B", B_TIP)
    assert e["base_tree"] is None and e["index"] == -1, e
    main = sh("git rev-parse main", w["repo"]).stdout.strip()
    code = (f"import sys, json; sys.path.insert(0, {str(w['lines'])!r}); import server_gate; "
            f"print(json.dumps(server_gate.same_candidate(json.loads(sys.stdin.read()), {main!r}, {B_TIP!r}, '2' * 40)))")
    why = json.loads(sh([w["py"], "-c", code], w["repo"], w["env"], input=json.dumps(e)).stdout)
    assert why, e                                                  # not the same candidate: the whole gate runs
