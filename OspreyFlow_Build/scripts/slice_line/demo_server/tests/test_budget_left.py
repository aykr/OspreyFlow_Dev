"""D255 (the owner's ruling of 25 November 2026): the server's early warning does not judge the timing-budget tests
(`*.budget.test.*`: MatrixView.budget and the others). It leaves them to the Mac's remainder. Their margin is not
widened.

MatrixView.budget turned three server runs red for slices that do not touch it (3,226, 2,624 and 2,536 ms against its
2,500), each time with one or two other jobs on the server beside it. `make test` runs the workspace's budget files
last in test-js, after every other part of make test has run, so a budget failure is the last thing in make test.

On the runner's real gate (as test_gate.py runs it), a run whose only failures are budget tests in test-js, with make
test's two pytest runs each reporting no failure, is not red. The result names the budget tests under left_to_mac,
with rerun: test-js, and never names `test` as passed. The Mac's remainder then runs test-js whole, which runs the
budget files alone, as today (tests/test_server_budget.py). Any other failure beside a budget failure keeps the run
red as before, and so does a log that does not show both pytest runs clean.
"""
from __future__ import annotations

import pytest

from conftest import sh
from test_gate import mini, run_real_gate

BUDGET = "src/matrix/MatrixView.budget.test.tsx > MatrixView at 50,000 nodes and 250,000 links > opens inside §5's budget"
OTHER = "src/copyWords.test.ts > the Glass's copy > says pipeline"
ROUTE_RIGHTS = "1 passed in 0.52s"
SUITE_OK = "2419 passed, 16 skipped, 6 warnings in 538.15s (0:08:58)"
SUITE_RED = "1 failed, 2418 passed, 16 skipped in 540.01s (0:09:00)"


def vitest_fail(name: str) -> str:
    file, rest = name.split(" > ", 1)
    return ("\t@printf '\\033[41m\\033[1m FAIL \\033[22m\\033[49m %s\\033[2m > \\033[22m%s\\n'\n"
            % (file, rest.replace("'", "'\\''").replace("%", "%%")))


def make_test(w, pytest_lines=(ROUTE_RIGHTS, SUITE_OK), js=(BUDGET,), pytest_failed=None, live_collect_fails=False):
    """make test as the real Makefile has it: the route-rights test, the suite, live-collect and Core's test-js, each
    part run whatever the one before did, and make test failing after them if any failed."""
    repo = w["repo"]
    sh(["git", "switch", "-q", "main"], repo, w["env"])
    mk = repo / "OspreyFlow_Build/Makefile"
    head = mk.read_text().split("test:\n", 1)[0]
    test = ["test:", "\t@rm -f .tf"]
    test += ["\t@echo '%s'" % ln for ln in pytest_lines]
    if pytest_failed:
        test.append("\t@echo 'FAILED %s - boom'" % pytest_failed)
    test += ["\t$(MAKE) live-collect || touch .tf",
             "\t$(MAKE) -C ../OspreyFlow_Core test-js || touch .tf",
             "\t@if [ -f .tf ]; then rm -f .tf; echo 'make test: a part above failed' >&2; exit 1; fi",
             "live-collect:", "\t@%s" % ("false" if live_collect_fails else "true"), ""]
    mk.write_text(head.replace("red-check:\n\t@echo 'FAILED ../OspreyFlow_Build/tests/test_r.py::test_q - boom'\n"
                               "\t@false\n", "red-check:\n\t@true\n") + "\n".join(test))
    core = repo / "OspreyFlow_Core/Makefile"
    core.write_text(core.read_text() + "test-js:\n" + "".join(vitest_fail(n) for n in js)
                    + ("\t@false\n" if js else "\t@true\n"))
    sh("git commit -qam 'chore: make test as the real Makefile runs it'", repo, w["env"])


def test_a_run_red_only_on_a_timing_budget_is_not_red_and_leaves_the_budget_and_test_js_to_the_mac(world):
    w = world
    mini(w)
    make_test(w)
    a = run_real_gate(w)
    assert a["verdict"] == "pass", a
    assert a["failing"]["tests"] == [] and a["failing"]["targets"] == [], a["failing"]
    assert not any(a["failing"].get("by_target", {}).values()), a["failing"]
    left = a["left_to_mac"]
    assert left["rerun"] == "test-js" and left["failed"] == [BUDGET], left
    assert "test" not in a["passed_targets"], a["passed_targets"]           # the Mac runs test-js whole
    (check,) = [c for c in a["checks"] if c["name"] == "test"]
    assert check["status"] == "left to the Mac", check
    assert [s for s in a["steps"] if s["step"] == "make test"][0].get("left_to_mac") is True, a["steps"]


def test_a_green_run_says_the_budget_tests_are_not_judged_here(world):
    w = world
    mini(w)
    make_test(w, js=())
    a = run_real_gate(w)
    assert a["verdict"] == "pass" and "test" in a["passed_targets"], a
    assert a["left_to_mac"]["rerun"] is None and a["left_to_mac"]["failed"] == [], a["left_to_mac"]
    assert "not judged here" in a["left_to_mac"]["budget"], a["left_to_mac"]


@pytest.mark.parametrize("how", ["a-pytest-failure", "a-pytest-run-unreported", "an-ordinary-vitest-failure",
                                 "live-collect-failed"])
def test_a_budget_failure_beside_any_other_failure_or_an_unproved_run_stays_red(world, how):
    w = world
    mini(w)
    if how == "a-pytest-failure":
        make_test(w, pytest_lines=(ROUTE_RIGHTS, SUITE_RED),
                  pytest_failed="../OspreyFlow_Build/tests/test_x.py::test_y")
    elif how == "a-pytest-run-unreported":                         # the suite's own summary missing: it did not finish
        make_test(w, pytest_lines=(ROUTE_RIGHTS,))
    elif how == "an-ordinary-vitest-failure":
        make_test(w, js=(OTHER, BUDGET))
    else:
        make_test(w, live_collect_fails=True)
    a = run_real_gate(w)
    assert a["verdict"] == "fail", (how, a["failing"])
    assert BUDGET in a["failing"]["tests"], (how, a["failing"])
    assert a["left_to_mac"]["rerun"] is None, (how, a["left_to_mac"])
    assert "test" not in a["passed_targets"]
