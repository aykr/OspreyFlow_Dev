"""Two faults in the Mac's rerun of a server's red, from the conductor (RM1a, 26 November 2026, 02:34).

1. The rerun built one shell line of every failing name (make's RERUN_TESTS, read by the shell), so a name holding an
   apostrophe ("opens inside §5's first-frame budget") broke the line; and it ran every name with pytest, a vitest
   name included. Now each name reaches its runner as one argument, never through a shell's words: a pytest node id
   by make test's own pytest, a vitest name by vitest in the workspace that holds its file (its budget config for a
   budget test), filtered to that one case by its full name. A name no runner can place is not rerun and is not red.
2. A newer run on the server of the same slice at the same tip that passed supersedes an older red: the slice is not
   held from the slot for the older red, and there is nothing to rerun. A newer red is never passed over for an older
   green, and a newer run with no verdict supersedes nothing.

The real rerun_named runs against this tree's real Makefiles; the environment (ci_env) is stood in, and so is either
the command runner (what each step is given) or the runners themselves (what each one receives, through a real make
and a real shell).
"""
from __future__ import annotations

import json
import os
import re
import shutil

from test_gates import SRC, merge, sh, world  # noqa: F401  (world is a fixture)
from test_server_rerun_folder import BUILD_MK, CORE_MK
from test_server_slot import OTHER, RID, note, ready, rerun, result, switch
from test_server_stacked_real import runs_log

BUDGET = "src/matrix/MatrixView.budget.test.tsx"
BUDGET_CASE = "MatrixView at 50,000 nodes > opens inside §5's first-frame budget"
BUDGET_NAME = f"{BUDGET} > {BUDGET_CASE}"          # RM1a's own name, as the runner's failing_test reads it
PYTEST_NAME = "../OspreyFlow_Build/tests/test_x.py::test_y"
ODD_PYTEST = "../OspreyFlow_Build/tests/test_x.py::test_z[it's $HOME `id` \"q\" ; a&b]"


def tree_of(w, files=()):
    tree = w["tmp"] / "tree"
    for mk, rel in ((BUILD_MK, "OspreyFlow_Build"), (CORE_MK, "OspreyFlow_Core")):
        (tree / rel).mkdir(parents=True, exist_ok=True)
        shutil.copy(mk, tree / rel / "Makefile")
    for f in files:
        p = tree / "OspreyFlow_Core" / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("// a test file\n")
    return tree


def steps(w, tests, files=()):
    """[(command, folder relative to the tree)], the exit code and the log, from the real rerun_named, run stood in."""
    tree = tree_of(w, files)
    code = (f"import sys, json; sys.path.insert(0, {str(w['lines'])!r}); import merge_slice as m; from pathlib import Path\n"
            "seen = []\n"
            "m.ci_env = lambda tree, log, retries=None: {}\n"
            "def run(cmd, cwd, log, env=None, shell=False):\n"
            "    assert not shell and isinstance(cmd, list), cmd\n"
            "    seen.append([cmd, str(Path(cwd).relative_to(Path(sys.argv[1])))])\n"
            "    return 0\n"
            "m.run = run\n"
            f"rc = m.rerun_named(Path(sys.argv[1]), Path(sys.argv[2]), json.loads(sys.argv[3]), [])\n"
            "print(json.dumps({'rc': rc, 'seen': seen}))\n")
    out = sh([w["py"], "-c", code, str(tree), str(w["tmp"] / "rerun.log"), json.dumps(list(tests))], w["repo"], w["env"],
             check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    got = json.loads(out.stdout)
    return [(c[0], c[1]) for c in got["seen"]], got["rc"], w["tmp"] / "rerun.log"


def received(w, tests, files=()):
    """What make test's pytest and vitest themselves receive, through the real make and shell: [(runner, argv, folder)]."""
    tree = tree_of(w, files)
    seen = w["tmp"] / "received.jsonl"
    seen.unlink(missing_ok=True)
    fake = ("#!/usr/bin/env python3\nimport json, os, sys\n"
            f"open({str(seen)!r}, 'a').write(json.dumps([os.path.basename(sys.argv[0]), sys.argv[1:], os.getcwd()]) + '\\n')\n")
    for rel in ("OspreyFlow_Core/.venv/bin/pytest", "OspreyFlow_Core/node_modules/.bin/vitest"):
        p = tree / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(fake)
        p.chmod(0o755)
    code = (f"import sys, json, os; sys.path.insert(0, {str(w['lines'])!r}); import merge_slice as m; from pathlib import Path\n"
            "m.ci_env = lambda tree, log, retries=None: {'PATH': os.environ['PATH'], 'HOME': os.environ.get('HOME', '/')}\n"
            f"rc = m.rerun_named(Path(sys.argv[1]), Path(sys.argv[2]), json.loads(sys.argv[3]), [])\n"
            "print(json.dumps({'rc': rc}))\n")
    out = sh([w["py"], "-c", code, str(tree), str(w["tmp"] / "rerun.log"), json.dumps(list(tests))], w["repo"], w["env"],
             check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    rows = [json.loads(ln) for ln in seen.read_text().splitlines()] if seen.exists() else []
    return [(r[0], r[1], os.path.relpath(r[2], tree)) for r in rows], json.loads(out.stdout)["rc"], \
        (w["tmp"] / "rerun.log").read_text()


# ------------------------------------------------------------------ 1. each name to its own runner, as one argument


def test_rm1a_s_vitest_name_runs_with_vitest_in_its_workspace_with_the_budget_config(world):
    seen, rc, _ = steps(world, [BUDGET_NAME], [f"apps/workspace/{BUDGET}"])
    assert len(seen) == 1, seen
    cmd, where = seen[0]
    assert where == "OspreyFlow_Core/apps/workspace", seen
    assert cmd[0].endswith("OspreyFlow_Core/node_modules/.bin/vitest") and "pytest" not in " ".join(cmd[1:]), cmd
    assert cmd[1:] == ["run", "--config", "vitest.budget.config.ts", BUDGET, "-t", cmd[-1]], cmd
    pattern = re.compile(cmd[-1])                    # vitest's -t is a RegExp over the case's full name, " > "-joined
    assert pattern.search(BUDGET_CASE), cmd[-1]
    assert not pattern.search(BUDGET_CASE + " again") and not pattern.search("x " + BUDGET_CASE), cmd[-1]
    assert rc == 0


def test_rm1a_s_name_reaches_vitest_whole_through_the_real_shell(world):
    got, rc, log = received(world, [BUDGET_NAME], [f"apps/workspace/{BUDGET}"])
    assert [g[0] for g in got] == ["vitest"], (got, log)
    runner, argv, where = got[0]
    assert where == "OspreyFlow_Core/apps/workspace" and argv[:4] == ["run", "--config", "vitest.budget.config.ts", BUDGET]
    assert re.search(argv[-1], BUDGET_CASE), argv


def test_a_pytest_name_with_quotes_and_shell_words_reaches_pytest_whole(world):
    got, rc, log = received(world, [PYTEST_NAME, ODD_PYTEST])
    assert len(got) == 1 and got[0][0] == "pytest", (got, log)
    runner, argv, where = got[0]
    assert where == "OspreyFlow_Core" and argv[-2:] == [PYTEST_NAME, ODD_PYTEST], argv  # make test's own pytest, -c kept
    assert "-c" in argv and argv[argv.index("-c") + 1].endswith("OspreyFlow_Build/pytest.ini"), argv
    assert rc == 0


def test_pytest_and_vitest_names_together_each_go_to_their_own_runner(world):
    got, rc, log = received(world, [PYTEST_NAME, BUDGET_NAME], [f"apps/workspace/{BUDGET}"])
    by = {g[0]: g for g in got}
    assert set(by) == {"pytest", "vitest"}, got
    assert BUDGET_NAME not in by["pytest"][1] and not any("§5" in a for a in by["pytest"][1]), by["pytest"]
    assert PYTEST_NAME not in by["vitest"][1], by["vitest"]


def test_a_vitest_case_outside_the_budget_runs_with_the_workspace_s_own_config(world):
    seen, rc, _ = steps(world, ["src/a.test.ts > a group > a case"], ["apps/harness/src/a.test.ts"])
    assert len(seen) == 1 and seen[0][1] == "OspreyFlow_Core/apps/harness", seen
    assert "--config" not in seen[0][0] and seen[0][0][1:3] == ["run", "src/a.test.ts"], seen


def test_a_vitest_file_s_own_failure_runs_the_whole_file(world):
    seen, rc, _ = steps(world, ["src/a.test.ts [ src/a.test.ts ]"], ["packages/glass-shared/src/a.test.ts"])
    assert seen and seen[0][1] == "OspreyFlow_Core/packages/glass-shared" and "-t" not in seen[0][0], seen
    assert seen[0][0][-1] == "src/a.test.ts", seen


def test_a_vitest_file_named_bare_runs_the_whole_file_with_vitest(world):
    seen, rc, _ = steps(world, ["src/a.test.ts"], ["apps/harness/src/a.test.ts"])
    assert seen and seen[0][1] == "OspreyFlow_Core/apps/harness" and seen[0][0][1:] == ["run", "src/a.test.ts"], seen


def test_a_vitest_name_whose_file_no_workspace_or_two_workspaces_hold_is_not_rerun_and_not_red(world):
    seen, rc, log = steps(world, ["src/gone.test.ts > a case"])
    assert seen == [] and rc == 4 and "NOT PLACED" in log.read_text(), (seen, rc)
    seen, rc, log = steps(world, ["src/a.test.ts > a case"], ["apps/harness/src/a.test.ts", "apps/workspace/src/a.test.ts"])
    assert seen == [] and rc == 4, (seen, rc)


def test_a_name_no_runner_can_place_beside_a_pytest_name_leaves_the_pytest_one_run(world):
    pw = "1 [chromium] › tests/a.spec.ts:12:3 › a walk"
    seen, rc, log = steps(world, [PYTEST_NAME, pw])
    assert len(seen) == 1 and seen[0][1] == "OspreyFlow_Build" and rc == 0, seen
    assert "NOT PLACED" in log.read_text() and "a walk" in log.read_text()


# ------------------------------------------------------------------ 2. a newer green supersedes an older red


def red_then(w, newer_verdict, *, newer_tip=None):
    """S1 verified; the note names RID, red; the log has OTHER after it, with `newer_verdict`, at newer_tip (S1's tip)."""
    wt, tip = ready(w)
    switch(w)
    result(w, tip)
    note(w, tip)
    result(w, newer_tip or tip, rid=OTHER, verdict=newer_verdict, tests=(), targets=())
    runs_log(w, tip, RID)
    with (w["data"] / "early-warning/runs.jsonl").open("a") as fh:
        fh.write(json.dumps({"slice": "S1", "tip": newer_tip or tip, "id": OTHER, "tree": None, "stack": ["S1"]}) + "\n")
    return tip


def test_a_newer_green_at_the_same_tip_supersedes_the_older_red(world):
    red_then(world, "pass")
    r = rerun(world)                                 # nothing to rerun: the red is superseded
    assert r.returncode != 0 and "no red result" in r.stderr, r.stdout + r.stderr
    p = merge(world)
    assert "not given the merge slot" not in p.stderr and p.returncode == 0, p.stdout + p.stderr


def test_a_newer_red_is_never_passed_over_for_an_older_green(world):
    w = world
    wt, tip = ready(w)
    switch(w)
    result(w, tip, rid=OTHER, verdict="pass", tests=(), targets=())
    result(w, tip)
    note(w, tip)
    runs_log(w, tip, OTHER, RID)                     # the green first, the note's red after it
    p = merge(w)
    assert p.returncode == 1 and "not given the merge slot" in p.stderr, p.stdout + p.stderr


def test_a_newer_run_with_no_verdict_supersedes_nothing(world):
    red_then(world, "error")
    p = merge(world)
    assert p.returncode == 1 and "not given the merge slot" in p.stderr, p.stdout + p.stderr


def test_a_newer_green_at_another_tip_supersedes_nothing(world):
    red_then(world, "pass", newer_tip="f" * 40)
    p = merge(world)
    assert p.returncode == 1 and "not given the merge slot" in p.stderr, p.stdout + p.stderr


THIRD = "fedcba9876543210"


def red_then_runs(w, *newer):
    """S1 verified; the note names RID, red; the log then has each (id, verdict) of `newer`, oldest first."""
    wt, tip = ready(w)
    switch(w)
    result(w, tip)
    note(w, tip)
    for rid, verdict in newer:
        result(w, tip, rid=rid, verdict=verdict, tests=(), targets=())
    runs_log(w, tip, RID, *[r for r, _ in newer])
    return tip


def test_a_newer_red_after_a_newer_green_still_holds(world):
    red_then_runs(world, (OTHER, "pass"), (THIRD, "fail"))          # the newest verdict is red: it decides
    p = merge(world)
    assert p.returncode == 1 and "not given the merge slot" in p.stderr, p.stdout + p.stderr


def test_a_newer_error_does_not_hide_a_newer_green(world):
    red_then_runs(world, (OTHER, "pass"), (THIRD, "error"))         # an error decides nothing: the green stands
    r = rerun(world)
    assert r.returncode != 0 and "no red result" in r.stderr, r.stdout + r.stderr


def test_a_newer_run_the_log_places_at_this_tip_but_the_server_says_is_another_tip_supersedes_nothing(world):
    """The log is where to ask, never the answer: the server's own result must be S1's at this tip."""
    w = world
    wt, tip = ready(w)
    switch(w)
    result(w, tip)
    note(w, tip)
    result(w, "f" * 40, rid=OTHER, verdict="pass", tests=(), targets=())   # the server's answer: another tip
    runs_log(w, tip, RID, OTHER)                                           # the log: this tip
    p = merge(w)
    assert p.returncode == 1 and "not given the merge slot" in p.stderr, p.stdout + p.stderr
