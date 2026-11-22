"""The owner's file 007, line fault 13 (22 November 2026): the GitHub watcher reads every job of a run, a cancelled run
with failed jobs included, names the failed jobs, and names a failure that prints no FAILED line ("failed without a
test", as run 44902592322's conformance job did). Each is kept in records/github/<run>.json, countable, and the board's
GitHub line names them. The conductor read them by hand until now. A stop is still only a test of ours red twice.

gh is stood in (tests/fake_gh.py), answering `run view --json jobs` as the real one does.
"""
from __future__ import annotations

import json

from test_gates import sh, world  # noqa: F401  (world is a fixture)
from test_github_stop import DOWNLOAD, REAL, RUN, gh, gh_run, stop_file, watch
from test_main_ci import ready


def jobs(**by_attempt):
    return {"FAKE_GH_JOBS": json.dumps({f"{RUN}/{a[1:]}": js for a, js in by_attempt.items()})}


def job(name, conclusion):
    return {"name": name, "conclusion": conclusion, "status": "completed"}


def test_a_cancelled_run_with_a_failed_job_is_read_and_names_a_failure_with_no_test(world):
    w = world
    ready(w, **gh([gh_run(RUN, "cancelled")], {f"{RUN}/1": DOWNLOAD}),
          **jobs(a1=[job("lint", "success"), job("conformance", "failure"), job("e2e", "cancelled")]))
    p = watch(w)
    assert "failed jobs: conformance; conformance failed without a test (no FAILED line)" in p.stdout, p.stdout
    rec = json.loads((w["data"] / f"records/github/{RUN}.json").read_text())["attempts"]["1"]
    assert rec["failed_jobs"] == ["conformance"] and rec["without_a_test"] == ["conformance"], rec
    assert not stop_file(w).exists()


def test_a_cancelled_run_with_no_failed_job_is_said_and_writes_nothing_else(world):
    w = world
    ready(w, **gh([gh_run(RUN, "cancelled")]), **jobs(a1=[job("lint", "success"), job("e2e", "cancelled")]))
    p = watch(w)
    assert f"run {RUN} on main is cancelled, with no failed job: no stop." in p.stdout, p.stdout


def test_a_failed_run_names_each_failed_job_and_only_the_one_without_a_test_as_such(world):
    w = world
    ready(w, **gh([gh_run(RUN, "failure")], {f"{RUN}/1": REAL}),
          **jobs(a1=[job("conformance", "failure"), job("lint", "failure"), job("build", "success")]))
    p = watch(w)
    assert "failed jobs: conformance, lint; lint failed without a test" in p.stdout, p.stdout
    rec = json.loads((w["data"] / f"records/github/{RUN}.json").read_text())["attempts"]["1"]
    assert rec["without_a_test"] == ["lint"] and rec["tests"], rec


def test_the_boards_github_line_names_the_failed_jobs(world):
    w = world
    ready(w, **gh([gh_run(RUN, "failure")], {f"{RUN}/1": DOWNLOAD}), **jobs(a1=[job("conformance", "failure")]))
    watch(w)
    b = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False).stdout
    line = next(ln for ln in b.splitlines() if ln.startswith("main is red"))
    assert "failed jobs: conformance; conformance failed without a test" in line, line
