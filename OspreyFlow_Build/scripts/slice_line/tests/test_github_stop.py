"""A test of ours failing twice on GitHub stops merging, until the owner clears it (the owner, 20 November 2026;
LINE_FIXES_4_BRIEF.md, 1c).

`merge_slice.py watch-github` (the conductor's; also run by `merge` before it starts and by `push-pending`) reads the
latest completed run on main; when it is red, it reads the failing tests from `gh run view <run> --attempt <n>
--log-failed` (pytest's `FAILED <path>::<test> - <why>` summary lines, after GitHub's job, step and timestamp) and
records them in records/github/<run>.json. The same test failing in that attempt and in the one before it on the same
commit (the run's previous attempt, or the previous run on the same head) writes github.stopped.json; while it is
there, `merge` refuses, naming the test, the job and the commit. A first red, a red that passes on rerun, a different
test on the rerun, a failure with no FAILED line (a download, the network, a runner) and gh unreadable write no stop.
`clear_github_stop.py` (the owner's; refused to every agent) removes it and keeps an audit line.

The log fixture is GitHub's own text for run 44681092481, attempt 1, recorded on 20 November 2026 (the summary, the
FAILED line and the exit; tests/fixtures/gh_log_failed_44681092481_attempt1.txt). gh_log_failed_another_test.txt is that
text with another test's name; gh_log_failed_download.txt is modelled on a runner's failed action download.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_gates import guard, refused, sh, world  # noqa: F401  (world is a fixture)
from test_main_ci import ready

FIX = Path(__file__).resolve().parent / "fixtures"
REAL = str(FIX / "gh_log_failed_44681092481_attempt1.txt")
OTHER = str(FIX / "gh_log_failed_another_test.txt")
DOWNLOAD = str(FIX / "gh_log_failed_download.txt")
RUN, HEAD = 44681092481, "d64ad0ec032def06143490f641e16deeffb3fc20"
TEST = "../OspreyFlow_Build/tests/ingest/test_typology_rules.py::" \
       "test_an_alert_explains_itself_with_its_transactions_links_and_node"
URL = "https://github.com/o/r/actions/runs/"


def gh_run(run, conclusion, attempt=1, head=HEAD, status="completed"):
    return {"databaseId": run, "attempt": attempt, "conclusion": conclusion, "status": status, "url": f"{URL}{run}",
            "headSha": head, "headBranch": "main", "workflowName": "ci", "event": "push"}


def gh(runs, logs=None):
    return {"FAKE_GH_RUNS": json.dumps(runs), "FAKE_GH_LOGS": json.dumps(logs or {})}


TWICE_ON_ONE_TEST = gh([gh_run(RUN, "failure", attempt=2)], {f"{RUN}/1": REAL, f"{RUN}/2": REAL})


def stop_file(w):
    return w["data"] / "github.stopped.json"


def watch(w):
    return sh([w["py"], str(w["lines"] / "merge_slice.py"), "watch-github"], w["repo"], w["env"], check=False)


def merge(w):
    return sh([w["py"], str(w["lines"] / "merge_slice.py"), "merge", "S1"], w["repo"], {**w["env"], "TEST_GATE": "0"},
              check=False)


def clear(w):
    return sh([w["py"], str(w["lines"] / "clear_github_stop.py")], w["repo"], w["env"], check=False)


def test_a_first_red_records_its_failing_test_writes_no_stop_and_does_not_hold_a_merge(world):
    w = world
    ready(w, **gh([gh_run(RUN, "failure")], {f"{RUN}/1": REAL}))
    p = merge(w)
    assert p.returncode == 0, p.stderr
    assert not stop_file(w).exists()
    rec = json.loads((w["data"] / f"records/github/{RUN}.json").read_text())
    assert rec["head"] == HEAD and rec["attempts"]["1"]["tests"] == [{"test": TEST, "job": "conformance"}], rec
    assert json.loads(p.stdout) and "github_at_merge" in json.loads((w["data"] / "records/S1/merged.json").read_text())


def test_a_red_that_passes_on_its_rerun_writes_no_stop(world):
    w = world
    w["env"].update(gh([gh_run(RUN, "success", attempt=2)], {f"{RUN}/1": REAL}))
    p = watch(w)
    assert p.returncode == 0 and not stop_file(w).exists(), p.stdout + p.stderr


@pytest.mark.parametrize("env", [
    TWICE_ON_ONE_TEST,
    gh([gh_run(RUN + 9, "failure"), gh_run(RUN, "failure")], {f"{RUN + 9}/1": REAL, f"{RUN}/1": REAL}),
], ids=["second-attempt", "next-run-on-the-same-head"])
def test_one_test_red_twice_on_one_commit_stops_merging_until_the_owner_clears_it(world, env):
    w = world
    tip = ready(w, **env)
    p = merge(w)
    assert p.returncode == 1, p.stdout + p.stderr
    for words in (TEST, "conformance", HEAD[:10], "clear_github_stop.py", "failed twice"):
        assert words in p.stderr, (words, p.stderr)
    assert sh("git rev-parse main", w["repo"]).stdout.strip() != tip
    stop = json.loads(stop_file(w).read_text())
    assert stop["test"] == TEST and stop["job"] == "conformance" and stop["commit"] == HEAD, stop
    assert len(stop["runs"]) == 2 and all(r["url"].startswith(URL) for r in stop["runs"]), stop
    c = clear(w)
    assert c.returncode == 0 and not stop_file(w).exists(), c.stdout + c.stderr
    audit = (w["data"] / "github-stop-clears.tsv").read_text()
    assert TEST in audit and HEAD in audit, audit
    p = merge(w)  # the same runs, read again: the owner's clear holds
    assert p.returncode == 0 and not stop_file(w).exists(), p.stderr


def test_the_same_test_red_on_another_commit_before_is_a_first_red_not_a_rerun(world):
    w = world
    other = "94aae91c37b04ceb62a9de2465bdeac6e8b3d94d"
    w["env"].update(gh([gh_run(RUN + 9, "failure"), gh_run(RUN, "failure", head=other)],
                       {f"{RUN + 9}/1": REAL, f"{RUN}/1": REAL}))
    p = watch(w)
    assert p.returncode == 0 and not stop_file(w).exists() and "first" in p.stdout, p.stdout + p.stderr


def test_a_different_test_failing_on_the_rerun_writes_no_stop(world):
    w = world
    w["env"].update(gh([gh_run(RUN, "failure", attempt=2)], {f"{RUN}/1": REAL, f"{RUN}/2": OTHER}))
    p = watch(w)
    assert p.returncode == 0 and not stop_file(w).exists(), p.stdout + p.stderr


def test_a_red_with_no_failed_line_names_no_test_and_is_never_a_stop(world):
    w = world
    w["env"].update(gh([gh_run(RUN, "failure", attempt=2)], {f"{RUN}/1": DOWNLOAD, f"{RUN}/2": DOWNLOAD}))
    p = watch(w)
    assert p.returncode == 0 and not stop_file(w).exists(), p.stdout + p.stderr
    rec = json.loads((w["data"] / f"records/github/{RUN}.json").read_text())
    assert rec["attempts"]["2"]["tests"] == [] and rec["attempts"]["1"]["tests"] == [], rec


@pytest.mark.parametrize("env", [{"FAKE_GH_EXIT": "1"}, {**TWICE_ON_ONE_TEST, "FAKE_GH_VIEW_EXIT": "1"}],
                         ids=["gh-fails", "log-unreadable"])
def test_gh_unreadable_writes_no_stop_and_refuses_no_merge(world, env):
    w = world
    ready(w, **env)
    p = merge(w)
    assert p.returncode == 0 and not stop_file(w).exists(), p.stderr


def test_a_stop_that_cannot_be_read_still_refuses(world):
    w = world
    ready(w)
    stop_file(w).write_text("{not json")
    p = merge(w)
    assert p.returncode == 1 and "clear_github_stop.py" in p.stderr, p.stderr


def test_watch_github_says_what_it_found_and_push_pending_runs_it(world):
    w = world
    w["env"].update(TWICE_ON_ONE_TEST)
    p = sh([w["py"], str(w["lines"] / "merge_slice.py"), "push-pending"], w["repo"], w["env"], check=False)
    assert stop_file(w).exists(), p.stdout + p.stderr
    stop_file(w).unlink()
    p = watch(w)
    assert p.returncode == 0 and "failed twice" in p.stdout and TEST in p.stdout, p.stdout + p.stderr
    assert stop_file(w).exists()


def test_the_board_prints_the_stop(world):
    w = world
    w["env"].update(TWICE_ON_ONE_TEST)
    watch(w)
    p = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False)
    line = next((ln for ln in p.stdout.splitlines() if ln.startswith("merging stopped")), "")
    assert TEST in line and "conformance" in line and "clear_github_stop.py" in line, p.stdout


def test_clear_github_stop_refuses_when_there_is_no_stop(world):
    w = world
    p = clear(w)
    assert p.returncode == 1 and "no GitHub stop" in p.stderr, p.stdout + p.stderr
    assert not (w["data"] / "github-stop-clears.tsv").exists()


def test_clear_github_stop_is_executable_and_refused_to_every_agent(world):
    w = world
    assert (w["lines"] / "clear_github_stop.py").stat().st_mode & 0o111
    for seat in ("conductor", "builder", "verifier", "scout", None):
        for cmd in (f"{w['py']} OspreyFlow_Build/scripts/slice_line/clear_github_stop.py",
                    "OspreyFlow_Build/scripts/slice_line/clear_github_stop.py", "python3 clear_github_stop.py"):
            assert refused(guard(w, "Bash", {"command": cmd}, seat=seat)), (seat, cmd)


def test_the_line_never_asks_github_to_rerun_or_cancel(world):
    w = world
    calls = w["tmp"] / "gh-calls.txt"
    ready(w, **TWICE_ON_ONE_TEST, FAKE_GH_CALLS=str(calls))
    merge(w)
    clear(w)
    merge(w)
    said = calls.read_text().splitlines()
    assert said and all(c.split()[:2] in (["run", "list"], ["run", "view"]) for c in said), said
