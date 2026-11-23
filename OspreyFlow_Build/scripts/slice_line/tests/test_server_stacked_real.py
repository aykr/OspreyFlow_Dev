"""The owner's file 013 (23 November 2026): with patch 36 on main, SE6c's merge still recorded "the server's candidate
tree None is not the Mac's 01aa7d2234" (run f8394584d97477d3), counted false, shadow "no comparison".

The stack was not the cause: patch 36 reads every real stacked result the line has (RL1 first of two under AD1a, SE6c
first of two under SE9, ...). SE6c's stack ran (run edfcda0e99098325, position 1 of 2, its tree the Mac's own, verdict
fail on one test the Mac then reran green). Then the early warning sent SE6c again, twice, in the 30 seconds before the
merge; both ended at once with verdict "error" ("the shield does not hold ... nothing was run") and no tree key. The
note named the newest, the merge read it, and element() took a result with no `tree` for the old stacked shape: tree
None. Now: a run of the runner's shape is read as its own run whatever it holds; a finished run with no verdict says
so; and when the note's run has none, the newest earlier run of the slice at that tip with a verdict is read instead
(the early warning's runs.jsonl), still checked to be the Mac's own candidate. An error never hides a verdict.

Every fixture is a run's result exactly as `early_warning.py fetch <id>` printed it on 23 November 2026. The sweep reads
each unchanged against its own hashes; the merges put the world's main, tip and trees in place of the real ones.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_gates import sh, world  # noqa: F401  (world is a fixture)
from test_server_counts import candidate_tree, gate_plan, makefiles
from test_server_slot import note, ready, switch

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ALONE, FIRST, ABOVE = "97dc976c7be6d175", "9ed33f6409e2c293", "9394c229769ec043"   # PL7a2a; RL1 under AD1a; AD1a
SE6C_ERROR, SE6C_FAIL, SE9_ABOVE = "f8394584d97477d3", "edfcda0e99098325", "f6789324db423ac2"


def real(rid):
    return json.loads((FIXTURES / f"server_result_{rid}.json").read_text())


REAL = sorted(p.name[len("server_result_"):-len(".json")] for p in FIXTURES.glob("server_result_*.json"))


def py(w, code, stdin):
    full = (f"import sys, json; sys.path.insert(0, {str(w['lines'])!r}); import server_gate; "
            f"r = json.loads(sys.stdin.read()); print(json.dumps({code}))")
    return json.loads(sh([w["py"], "-c", full], w["repo"], w["env"], input=json.dumps(stdin)).stdout)


# ------------------------------------------------------------------ every real result, read as its own run


@pytest.mark.parametrize("rid", REAL)
def test_every_real_result_reads_as_its_own_run(world, rid):
    """The test that would have caught 013 before patch 36 was applied: each real fetched result, unchanged, read by
    element() as the run it is, with its own verdict and tree; the run below a stacked one fetched by its id."""
    w = world
    ready(w)
    r = real(rid)
    for other in REAL:
        (w["tmp"] / "ew" / f"{other}.json").write_text(json.dumps(real(other)))
    e = py(w, f"server_gate.element(r, {r['slice']!r}, {r['tip']!r})", r)
    assert e is not None and (e["id"], e["state"], e["verdict"], e.get("tree")) == \
        (rid, r["state"], r["verdict"], r.get("tree")), e
    assert e["index"] == r["position"] - 1, e                    # every real stack places its run where it says
    if e["index"] == 0:
        assert e["main"] == r["main"] and e["below"] == [], e
    elif r["group"][e["index"] - 1] in REAL:                      # the run below is one of the fixtures
        assert e["base_tree"] == real(r["group"][e["index"] - 1])["tree"], e
    if e["index"]:
        return  # stacked above another: main must be the real repository's commit, which only the merges below test
    why = py(w, f"server_gate.same_candidate(r, {r['main']!r}, {r['tip']!r}, {str(r.get('tree'))!r})", e)
    if r["verdict"] in ("pass", "fail"):
        assert why is None, why                                  # the Mac's own candidate, read as the server ran it
    else:
        assert why and "ended without a verdict" in why and r["verdict"] in why and "tree None" not in why, why


# ------------------------------------------------------------------ the three shapes, merged in the world


def in_the_world(w, rid, tip, **change):
    """A real result with the world's main, tip and tree in place of the real repository's; nothing else changed."""
    main = sh("git rev-parse main", w["repo"]).stdout.strip()
    tree = change.pop("tree") if "tree" in change else candidate_tree(w, tip)
    r = {**real(rid), "slice": "S1", "main": main, "holds_main": main, "tip": tip, "tree": tree,
         "stack": [{"slice": "S1", "tip": tip}], **change}
    (w["tmp"] / "ew" / f"{rid}.json").write_text(json.dumps(r))
    return r


def shaped(w, how, tip):
    """S1's result in the shape of one real run: alone, first of a stack, or above another (the run below landed as
    the server tested it: its tree is main's)."""
    if how == "alone":
        return ALONE, in_the_world(w, ALONE, tip)
    if how == "first-of-a-stack":
        r = in_the_world(w, FIRST, tip)
        assert (r["position"], r["of"]) == (1, 2)
        return FIRST, r
    below = real(FIRST)
    main_tree = sh("git rev-parse main^{tree}", w["repo"]).stdout.strip()
    (w["tmp"] / "ew" / f"{FIRST}.json").write_text(json.dumps({**below, "slice": "A", "tip": "a" * 40, "tree": main_tree,
                                                               "stack": [{"slice": "A", "tip": "a" * 40}]}))
    r = in_the_world(w, ABOVE, tip, stack=[{"slice": "A", "tip": "a" * 40}, {"slice": "S1", "tip": tip}])
    assert (r["position"], r["of"], r["group"][0]) == (2, 2, FIRST)
    return ABOVE, r


def merged(w, how, on):
    makefiles(w)
    wt, tip = ready(w)
    switch(w, "on\n" if on else None)
    rid, _ = shaped(w, how, tip)
    note(w, tip, rid=rid, headline="GREEN")
    return rid, gate_plan(w)


SHAPES = ["alone", "first-of-a-stack", "above-another"]


@pytest.mark.parametrize("how", SHAPES)
def test_with_the_switch_on_a_real_green_of_each_shape_counts(world, how):
    rid, (p, plan, server) = merged(world, how, on=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert server["counted"] is True and server["run_id"] == rid and server["server_verdict"] == "pass", server
    assert plan is not None and server["shadow"] == "counted", (plan, server)


@pytest.mark.parametrize("how", SHAPES)
def test_with_the_switch_off_a_real_green_of_each_shape_is_agree(world, how):
    rid, (p, plan, server) = merged(world, how, on=False)
    assert p.returncode == 0, p.stdout + p.stderr
    assert plan is None and server["counted"] is False and server["same"] is True, (plan, server)
    assert server["shadow"] == "agree" and server["run_id"] == rid, server


# ------------------------------------------------------------------ SE6c: a newer run with no verdict


def runs_log(w, tip, *rids):
    """The early warning's log (runs.jsonl), oldest first, as it records each run it started or polled."""
    d = w["data"] / "early-warning"
    d.mkdir(parents=True, exist_ok=True)
    (d / "runs.jsonl").write_text("".join(json.dumps({"slice": "S1", "tip": tip, "id": r, "tree": None, "stack": ["S1"],
                                                      "standing": "verified", "at": "2026-11-23T07:12:40Z"}) + "\n"
                                          for r in rids))


def se6c(w, on, older):
    """S1 as SE6c was: the note names a newer run that ended in error (the real one); `older`, its earlier run."""
    makefiles(w)
    wt, tip = ready(w)
    switch(w, "on\n" if on else None)
    err = in_the_world(w, SE6C_ERROR, tip)
    del err["tree"]                                               # as the real one: no tree key at all
    (w["tmp"] / "ew" / f"{SE6C_ERROR}.json").write_text(json.dumps(err))
    if older:
        in_the_world(w, older, tip, position=1, of=1, group=[older])
        if real(older)["verdict"] == "fail":                      # the Mac's rerun of its red, green (07:13:09)
            (w["data"] / f"records/S1/server-rerun-{older}.json").write_text(json.dumps(
                {"slice": "S1", "tip": tip, "run_id": older, "result": "green"}))
        runs_log(w, tip, older, SE6C_ERROR)
    else:  # a green of the slice at another tip, and of another slice at this one, are never read for it
        in_the_world(w, FIRST, "f" * 40, tree="0" * 40, position=1, of=1, group=[FIRST])
        in_the_world(w, ALONE, tip, slice="S2", position=1, of=1, group=[ALONE])
        runs_log(w, tip, SE6C_ERROR)
        with (w["data"] / "early-warning/runs.jsonl").open("a") as fh:
            fh.write(json.dumps({"slice": "S1", "tip": "f" * 40, "id": FIRST}) + "\n")
            fh.write(json.dumps({"slice": "S2", "tip": tip, "id": ALONE}) + "\n")
    note(w, tip, rid=SE6C_ERROR, headline="NO VERDICT")
    return gate_plan(w)


def test_se6c_the_stacks_own_red_is_read_not_the_newer_error_and_the_shadow_differs(world):
    p, plan, server = se6c(world, on=False, older=SE6C_FAIL)
    assert p.returncode == 0, p.stdout + p.stderr
    assert server["run_id"] == SE6C_FAIL and server["server_verdict"] == "fail" and server["same"] is True, server
    assert server["newer_without_verdict"]["id"] == SE6C_ERROR and server["newer_without_verdict"]["verdict"] == "error"
    assert server["shadow"] == "differ" and "tree None" not in json.dumps(server), server


def test_an_error_never_hides_an_earlier_green_for_the_same_candidate(world):
    p, plan, server = se6c(world, on=True, older=FIRST)
    assert p.returncode == 0, p.stdout + p.stderr
    assert server["counted"] is True and server["run_id"] == FIRST, server
    assert server["newer_without_verdict"]["id"] == SE6C_ERROR, server


def test_a_run_with_no_verdict_and_none_before_it_says_so(world):
    p, plan, server = se6c(world, on=True, older=None)
    assert p.returncode == 0, p.stdout + p.stderr
    assert plan is None and server["counted"] is False and server["run_id"] == SE6C_ERROR, (plan, server)
    assert "ended without a verdict (error: the shield does not hold" in server["why"], server
    assert "tree None" not in server["why"] and server["shadow"] == "no comparison", server


def test_with_no_verdict_only_the_slices_own_runs_at_its_tip_are_read_in_place(world):
    """Each guard on its own: element() refuses a real result of another slice or tip, and the runs read in place of a
    run with no verdict are only the slice's at that tip, newest first, the note's own left out."""
    w = world
    ready(w)
    r = real(ALONE)
    assert py(w, f"server_gate.element(r, 'S2', {r['tip']!r})", r) is None
    assert py(w, f"server_gate.element(r, {r['slice']!r}, {'f' * 40!r})", r) is None
    tip = "a" * 40
    d = w["data"] / "early-warning"
    d.mkdir(parents=True, exist_ok=True)
    rows = [("S1", tip, "1111111111111111"), ("S2", tip, "2222222222222222"), ("S1", "b" * 40, "3333333333333333"),
            ("S1", tip, "4444444444444444"), ("S1", tip, SE6C_ERROR)]
    (d / "runs.jsonl").write_text("".join(json.dumps({"slice": s, "tip": t_, "id": i}) + "\n" for s, t_, i in rows))
    got = py(w, f"server_gate.older_runs('S1', {tip!r}, {SE6C_ERROR!r})", {})
    assert got == ["4444444444444444", "1111111111111111"], got
