"""Item 2 of the owner's file 004 (22 November 2026): the server's green counts. When the runner's own result (fetched
by run id) is a finished pass for exactly the tree the merge produces (the same main tip, the same slice tip, the same
candidate tree hash), the merge's full gate runs only what the server did not prove: each `ci` target the result does
not name as run and passed (core-check by Core's own `check` targets), and `make test` whole unless the server names
it passed, then only the test files it did not run. The scans (before the gate), the live step, the landing and the
push run as before. If main has moved, or the hash differs, or the result cannot be fetched, or the owner's switch is
off, the whole gate runs as now.

The full gate is stood in (it records the targets it was given: null is the whole gate).
"""
from __future__ import annotations

import json

import pytest

from test_gates import sh, world  # noqa: F401  (world is a fixture)
from test_server_slot import RID, note, ready, switch

CI = "ci: core-check lint-tools opentofu-check client-name-check\n"
CHECK = "check: lint typecheck trivy\n"
X, Y = "OspreyFlow_Build/tests/test_docker_x.py", "OspreyFlow_Build/tests/harness/test_docker_y.py"


def makefiles(w):
    (w["repo"] / "OspreyFlow_Build/Makefile").write_text(CI)
    (w["repo"] / "OspreyFlow_Core/Makefile").write_text(CHECK)
    sh("git add -A OspreyFlow_Build/Makefile OspreyFlow_Core/Makefile && git commit -qm 'ci targets'", w["repo"], w["env"])


def candidate_tree(w, tip):
    return sh(["git", "merge-tree", "--write-tree", "main", tip], w["repo"]).stdout.split()[0]


def green(w, at, **change):
    main = sh("git rev-parse main", w["repo"]).stdout.strip()
    r = {"state": "done", "id": RID, "slice": "S1", "main": main, "tip": at, "tree": candidate_tree(w, at),
         "verdict": "pass", "failing": {"tests": [], "targets": []},
         "passed_targets": ["lint-tools", "opentofu-check", "lint", "typecheck", "test"],
         "not_run": {"targets": [{"name": "client-name-check", "why": "client-names"}, {"name": "trivy", "why": "no-tool"}],
                     "test_files": [{"name": "../" + X, "why": "container"}], "docker_skipped": ["../" + Y],
                     "mac_only": [{"name": "OspreyFlow_Core/apps/workspace/map-verify/contrast.spec.ts"}]}}
    r.update(change)
    (w["tmp"] / "ew" / f"{RID}.json").write_text(json.dumps(r))
    return r


def setup(w, on=True):
    makefiles(w)
    wt, tip = ready(w)
    switch(w, "on\n" if on else None)
    note(w, tip, headline="GREEN")
    return wt, tip


def gate_plan(w, gate="0"):
    (w["tmp"] / "plan.json").unlink(missing_ok=True)
    p = sh([w["py"], str(w["lines"] / "merge_slice.py"), "merge", "S1"], w["repo"],
        {**w["env"], "TEST_GATE": gate, "TEST_GATE_PLAN": str(w["tmp"] / "plan.json")}, check=False)
    plan = json.loads((w["tmp"] / "plan.json").read_text()) if (w["tmp"] / "plan.json").exists() else "not run"
    merged = w["data"] / "records/S1/merged.json"
    return p, plan, (json.loads(merged.read_text()).get("server") if merged.exists() else None)


def test_a_green_for_exactly_this_tree_counts_and_the_mac_runs_only_what_the_server_did_not(world):
    w = world
    wt, tip = setup(w)
    green(w, tip)
    p, plan, server = gate_plan(w)
    assert p.returncode == 0, p.stdout + p.stderr
    mk = plan[2][4]
    assert mk.endswith(".remainder.mk"), plan
    assert plan == [["make", "-k", "client-name-check"], ["make", "-k", "-C", "../OspreyFlow_Core", "trivy"],
                    ["make", "-f", "Makefile", "-f", mk, "server-test-files",
                     f"SERVER_TEST_FILES=../{Y} ../{X}"]], plan
    assert server["counted"] is True and server["run_id"] == RID, server
    assert server["taken"] == ["lint-tools", "opentofu-check", "core:lint", "core:typecheck", "test"], server
    assert server["mac_ran"][:2] == ["client-name-check", "core:trivy"], server


@pytest.mark.parametrize("how,why", [
    ("another-tree", "candidate tree"), ("main-moved", "main has moved"), ("another-tip", "no result"),
    ("red", "not a finished pass"), ("running", "not a finished pass"), ("no-passed-list", "names no target"),
    ("unfetchable", "no result"), ("note-edited-by-hand", "no result")])
def test_anything_short_of_a_pass_for_exactly_this_tree_runs_the_whole_gate(world, how, why):
    w = world
    wt, tip = setup(w)
    if how == "another-tree":
        green(w, tip, tree="0" * 40)
    elif how == "main-moved":
        green(w, tip, main=sh("git rev-parse main~1", w["repo"]).stdout.strip())
    elif how == "another-tip":
        green(w, tip, tip="f" * 40)
    elif how == "red":
        green(w, tip, verdict="fail")
    elif how == "running":
        green(w, tip, state="running")
    elif how == "no-passed-list":
        r = green(w, tip)
        del r["passed_targets"]
        (w["tmp"] / "ew" / f"{RID}.json").write_text(json.dumps(r))
    elif how == "note-edited-by-hand":  # the note says GREEN and names another run: what is fetched decides
        green(w, tip)
        note(w, tip, rid="ffffffffffffffff", headline="GREEN")
    p, plan, server = gate_plan(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert plan is None, (how, plan)                              # the whole gate, as now
    assert server["counted"] is False and why in server["why"], (how, server)


def test_a_green_with_a_target_missing_runs_that_target_on_the_mac(world):
    w = world
    wt, tip = setup(w)
    green(w, tip, passed_targets=["lint-tools", "lint", "typecheck", "test"])   # opentofu-check not named
    p, plan, server = gate_plan(w)
    assert plan[0] == ["make", "-k", "opentofu-check", "client-name-check"], plan
    assert "opentofu-check" not in server["taken"]


def test_make_test_runs_whole_when_the_server_does_not_name_it_passed_or_skipped_a_file_the_mac_cannot_place(world):
    w = world
    wt, tip = setup(w)
    green(w, tip, passed_targets=["lint-tools", "opentofu-check", "lint", "typecheck"])
    p, plan, server = gate_plan(w)
    assert plan[-1] == ["make", "test"] and "test" not in server["taken"], plan
    sh("git reset -q --hard HEAD~1", w["repo"])                    # main back before S1, to merge it again
    st = json.loads((w["data"] / "records/S1/state.json").read_text())
    st["phase"] = "verified"
    (w["data"] / "records/S1/state.json").write_text(json.dumps(st))
    (w["data"] / "records/S1/merged.json").unlink()
    green(w, tip, not_run={"test_files": [{"name": "OspreyFlow_Core/apps/x.spec.ts"}]})
    p, plan, server = gate_plan(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert plan[-1] == ["make", "test"] and "test" not in server["taken"], plan


def test_with_the_switch_off_the_whole_gate_runs_and_the_record_says_why(world):
    w = world
    wt, tip = setup(w, on=False)
    green(w, tip)
    p, plan, server = gate_plan(w)
    assert p.returncode == 0 and plan is None, plan
    assert server["run_id"] == RID and server["counted"] is False, server
    assert server["why"] == "the owner's switch (server_counts) is off" and server["tree"] == candidate_tree(w, tip)


def test_a_red_remainder_refuses_the_merge_as_the_whole_gate_would(world):
    w = world
    wt, tip = setup(w)
    green(w, tip)
    before = sh("git rev-parse main", w["repo"]).stdout.strip()
    p, plan, server = gate_plan(w, gate="1")
    assert p.returncode == 1 and "full gate is red" in p.stderr, p.stderr
    assert sh("git rev-parse main", w["repo"]).stdout.strip() == before
