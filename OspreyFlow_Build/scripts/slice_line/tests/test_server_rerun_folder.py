"""The Mac's rerun of a server's red runs each named target from the Makefile that has its rule (the owner, 24 November
2026, D225, second on his list).

PL12b, 23 November 2026, run 0537b90cee415260: the server named the targets test-js and test. test-js is a Core target
(make test runs it as make -C ../OspreyFlow_Core test-js); the rerun ran make -k test-js test in OspreyFlow_Build,
make said "No rule to make target `test-js'", and the rerun was red though all 17,843 tests in it passed and test-js
passed where make test ran it. PL12b was held from the merge slot all night. Now a target runs from Build's Makefile
when Build has its rule (as before), else from Core's; a target neither has is not rerun and is recorded as such
("unplaced"), never as red: the merge's whole gate settles it.

The real rerun_named is run against the real Makefiles of this tree, with only the environment (ci_env) and the
command runner (run) stood in: what is asserted is the folder and command each step is given.
"""
from __future__ import annotations

import json
import shutil

from test_gates import SRC, sh, world  # noqa: F401  (world is a fixture)
from test_server_slot import RID, note, ready, rerun, result, switch

BUILD_MK = SRC.parents[1] / "Makefile"
CORE_MK = SRC.parents[2] / "OspreyFlow_Core/Makefile"


def steps(w, tests, targets, core_extra=""):
    """[(command, folder relative to the tree), ...] and the rerun's exit code, from the real rerun_named."""
    tree = w["tmp"] / "tree"
    for mk, rel in ((BUILD_MK, "OspreyFlow_Build"), (CORE_MK, "OspreyFlow_Core")):
        (tree / rel).mkdir(parents=True, exist_ok=True)
        shutil.copy(mk, tree / rel / "Makefile")
    if core_extra:
        with (tree / "OspreyFlow_Core/Makefile").open("a") as fh:
            fh.write(core_extra)
    code = (f"import sys, json; sys.path.insert(0, {str(w['lines'])!r}); import merge_slice as m; from pathlib import Path\n"
            "seen = []\n"
            "m.ci_env = lambda tree, log, retries=None: {}\n"
            "def run(cmd, cwd, log, env=None, shell=False):\n"
            "    seen.append([cmd, str(Path(cwd).relative_to(Path(sys.argv[1])))])\n"
            "    return 0\n"
            "m.run = run\n"
            f"rc = m.rerun_named(Path(sys.argv[1]), Path(sys.argv[2]), {list(tests)!r}, {list(targets)!r})\n"
            "print(json.dumps({'rc': rc, 'seen': seen}))\n")
    out = sh([w["py"], "-c", code, str(tree), str(w["tmp"] / "rerun.log")], w["repo"], w["env"], check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    got = json.loads(out.stdout)
    return [(c[0], c[1]) for c in got["seen"]], got["rc"], (w["tmp"] / "rerun.log")


def test_pl12b_s_targets_test_js_and_test_each_run_from_its_own_makefile(world):
    seen, rc, _ = steps(world, [], ["test-js", "test"])
    assert (["make", "-k", "test"], "OspreyFlow_Build") in seen, seen                # make test: Build's own, as before
    assert (["make", "-k", "test-js"], "OspreyFlow_Core") in seen, seen              # test-js: Core's, where its rule is
    assert not any("test-js" in cmd and where == "OspreyFlow_Build" for cmd, where in seen), seen
    assert rc == 0


def test_a_target_both_makefiles_have_runs_from_build_as_before(world):
    """None does today; a Core rule for make test is added to the tree's copy of Core's Makefile."""
    seen, rc, _ = steps(world, [], ["test"], core_extra="\ntest:\n\techo core\n")
    assert seen == [(["make", "-k", "test"], "OspreyFlow_Build")], seen


def test_the_failing_tests_still_run_by_make_test_s_own_pytest_from_build(world):
    seen, rc, _ = steps(world, ["../OspreyFlow_Build/tests/test_x.py::test_y"], [])
    assert len(seen) == 1 and seen[0][1] == "OspreyFlow_Build" and "server-rerun" in seen[0][0], seen


def test_a_target_no_makefile_has_is_not_rerun_and_is_not_red(world):
    seen, rc, log = steps(world, [], ["no-such-target"])
    assert seen == [] and rc == 4, (seen, rc)                                        # UNPLACED
    assert "NOT PLACED" in log.read_text() and "no-such-target" in log.read_text()


def test_an_unplaced_target_beside_a_placed_one_reruns_the_placed_one(world):
    seen, rc, log = steps(world, [], ["test-js", "no-such-target"])
    assert seen == [(["make", "-k", "test-js"], "OspreyFlow_Core")] and rc == 0, (seen, rc)
    assert "NOT PLACED" in log.read_text()


def test_an_unplaced_rerun_is_recorded_so_and_frees_the_slot_for_the_whole_gate(world):
    w = world
    wt, tip = ready(w)
    switch(w)
    result(w, tip, tests=(), targets=("no-such-target",))
    note(w, tip)
    r = rerun(w, "4")                                                               # the stand-in's UNPLACED
    assert r.returncode == 0 and "not rerun" in r.stdout and "whole gate" in r.stdout, r.stdout + r.stderr
    rec = json.loads((w["data"] / f"records/S1/server-rerun-{RID}.json").read_text())
    assert rec["result"] == "unplaced", rec
    st = json.loads((w["data"] / "records/S1/state.json").read_text())
    assert st["phase"] == "verified", st                                            # never sent back on it
    from test_gates import merge
    p = merge(w)
    assert "not given the merge slot" not in p.stderr, p.stderr                     # the slot is free
