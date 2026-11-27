"""D255 (the owner's ruling of 25 November 2026), the Mac's side: the server does not judge the timing-budget tests,
and the Mac's remainder runs them.

- When the server's green names make test passed, the Mac still runs the budget files, as the workspace's own
  `npm run test:budget` runs them (one file at a time), and never takes them from the server.
- When the server left make test to the Mac because only budget tests failed in test-js (its result's left_to_mac:
  rerun test-js, every name a budget test), the Mac runs Core's test-js whole, which runs the budget files last and
  alone, with the test files the server did not run. It does not run all of make test.
- Any other shape of left_to_mac (a name that is not a budget test, or another rerun) is not trusted, and make test
  runs whole, as before.

The full gate is stood in, as in test_server_counts.py (it records the targets it was given).
"""
from __future__ import annotations

import json

import pytest

from test_gates import sh, world  # noqa: F401  (world is a fixture)
from test_server_counts import X, Y, gate_plan, green, setup

BUDGET = "src/matrix/MatrixView.budget.test.tsx > MatrixView at 50,000 nodes and 250,000 links > opens inside §5's budget"
PKG = {"name": "workspace", "scripts": {"test": "vitest run && vitest run --config vitest.budget.config.ts",
                                        "test:budget": "vitest run --config vitest.budget.config.ts"}}


def workspace(w, pkg=PKG):
    f = w["repo"] / "OspreyFlow_Core/apps/workspace/package.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(pkg))
    sh("git add -A OspreyFlow_Core && git commit -qm 'the workspace'", w["repo"], w["env"])


def test_a_server_green_never_stands_for_the_budget_tests_the_mac_runs_them(world):
    w = world
    workspace(w)
    wt, tip = setup(w)
    green(w, tip)
    p, plan, server = gate_plan(w)
    assert p.returncode == 0, p.stdout + p.stderr
    mk = plan[2][4]
    assert plan[-1] == ["make", "-f", "Makefile", "-f", mk, "server-budget"], plan
    assert "test" in server["taken"], server
    assert any("timing-budget" in m for m in server["mac_ran"]), server
    rules = (w["data"] / "records/S1").glob("*.remainder.mk")
    text = "".join(f.read_text() for f in rules)
    assert "server-budget:\n\t$(IN_CORE) npm run test:budget --workspace apps/workspace\n" in text, text


def test_a_tree_without_the_budget_script_adds_no_budget_step(world):
    w = world
    workspace(w, {"name": "workspace", "scripts": {"test": "vitest run"}})
    wt, tip = setup(w)
    green(w, tip)
    p, plan, server = gate_plan(w)
    assert not any("server-budget" in step for step in plan), plan


def test_make_test_left_to_the_mac_for_a_budget_alone_runs_test_js_whole_not_make_test(world):
    w = world
    workspace(w)
    wt, tip = setup(w)
    green(w, tip, passed_targets=["lint-tools", "opentofu-check", "lint", "typecheck"],
          left_to_mac={"budget": "not judged here", "failed": [BUDGET], "rerun": "test-js"})
    p, plan, server = gate_plan(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert ["make", "test"] not in plan, plan
    assert ["make", "-C", "../OspreyFlow_Core", "test-js"] in plan, plan
    mk = [s for s in plan if "server-test-files" in s][0][4]
    assert ["make", "-f", "Makefile", "-f", mk, "server-test-files", f"SERVER_TEST_FILES=../{Y} ../{X}"] in plan, plan
    assert not any("server-budget" in s for s in plan), plan               # test-js runs them already
    assert "test (all but test-js)" in server["taken"] and "test" not in server["taken"], server
    assert any("test-js" in m and BUDGET in m for m in server["mac_ran"]), server


@pytest.mark.parametrize("left", [
    {"failed": ["src/copyWords.test.ts > the Glass's copy > says pipeline"], "rerun": "test-js"},
    {"failed": [BUDGET], "rerun": "test"},
    {"failed": [], "rerun": "test-js"},
    "test-js"], ids=["not-a-budget-test", "another-rerun", "no-name", "not-a-record"])
def test_any_other_left_to_mac_is_not_trusted_and_make_test_runs_whole(world, left):
    w = world
    workspace(w)
    wt, tip = setup(w)
    green(w, tip, passed_targets=["lint-tools", "opentofu-check", "lint", "typecheck"], left_to_mac=left)
    p, plan, server = gate_plan(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert plan[-1] == ["make", "test"] and "test-js" not in json.dumps(plan), plan
    assert not any(t.startswith("test") for t in server["taken"]), server
