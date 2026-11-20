"""A release still needs GitHub green on the commit released (the owner, 20 November 2026; LINE_FIXES_4_BRIEF.md, 1d).

release_green.py check <commit> (the standard library only, run by the system python3 as the release paths run
owed.py) asks gh as the brief says (`gh run list --commit <sha> --status completed --json ...`, answered by
tests/fake_gh.py as the real gh answers it) and passes only when the latest completed run of ci on exactly that
commit concluded success: a rerun that passed counts (gh gives a run's latest attempt); a green run on another commit,
the parent included, does not; none, red, or gh unreadable refuses in words naming the commit. Both release paths call
it before anything is built or exported: OspreyFlow_Build/tools/release_local.py and
OspreyFlow_Build/scripts/publish_user_repo_update.sh (their own behaviour is in OspreyFlow_Build/tests/test_release_owed.py).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SRC = HERE.parent
BUILD = SRC.parents[1]
COMMIT = "555c6b78ea45e6005aa39730b25610a797aabd34"
PARENT = "6318956b1450f2d6fc87e39b583d7739c16bcdda"
URL = "https://github.com/o/r/actions/runs/"


def gh_run(run, conclusion, head=COMMIT, attempt=1, workflow="ci", status="completed"):
    return {"databaseId": run, "attempt": attempt, "conclusion": conclusion, "status": status, "url": f"{URL}{run}",
            "headSha": head, "headBranch": "main", "workflowName": workflow, "event": "push"}


@pytest.fixture
def check(tmp_path):
    ghbin = tmp_path / "ghbin"
    ghbin.mkdir()
    shutil.copy(HERE / "fake_gh.py", ghbin / "gh")
    (ghbin / "gh").chmod(0o755)

    def run(commit=COMMIT, **gh):
        env = {"PATH": f"{ghbin}{os.pathsep}/usr/bin:/bin", "HOME": str(tmp_path), **gh}
        return subprocess.run(["/usr/bin/python3", str(SRC / "release_green.py"), "check", commit], env=env,
                              capture_output=True, text=True)
    return run


def runs(*r):
    return {"FAKE_GH_RUNS": json.dumps(list(r))}


def test_a_green_run_on_the_parent_but_none_on_the_commit_refuses_naming_the_commit(check):
    p = check(**runs(gh_run(44631429355, "success", head=PARENT)))
    assert p.returncode == 1 and COMMIT in p.stderr and "no completed run" in p.stderr, p.stdout + p.stderr


def test_a_red_run_that_passed_on_its_rerun_is_accepted(check):
    p = check(**runs(gh_run(44643717559, "success", attempt=2)))
    assert p.returncode == 0 and "success" in p.stdout and COMMIT[:10] in p.stdout, p.stdout + p.stderr


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "timed_out"])
def test_a_red_run_only_refuses_naming_the_run_and_the_commit(check, conclusion):
    p = check(**runs(gh_run(44643717559, conclusion), gh_run(44631429355, "success", head=PARENT)))
    assert p.returncode == 1 and COMMIT in p.stderr and "44643717559" in p.stderr and conclusion in p.stderr, p.stderr


def test_the_latest_completed_run_on_the_commit_decides(check):
    p = check(**runs(gh_run(44643717560, "failure"), gh_run(44643717559, "success")))
    assert p.returncode == 1 and "44643717560" in p.stderr, p.stdout + p.stderr
    p = check(**runs(gh_run(44643717560, "success"), gh_run(44643717559, "failure")))
    assert p.returncode == 0, p.stdout + p.stderr


def test_a_run_still_in_progress_or_of_another_workflow_does_not_count(check):
    p = check(**runs(gh_run(44643717561, "", status="in_progress"), gh_run(44643717560, "success", workflow="exit-tests")))
    assert p.returncode == 1 and "no completed run" in p.stderr and COMMIT in p.stderr, p.stdout + p.stderr


@pytest.mark.parametrize("gh", [{"FAKE_GH_EXIT": "1"}, {"FAKE_GH_RUNS": "not json"}], ids=["gh-fails", "not-json"])
def test_gh_unreadable_refuses_naming_the_commit(check, gh):
    p = check(**gh)
    assert p.returncode == 1 and COMMIT in p.stderr and "cannot be read" in p.stderr, p.stdout + p.stderr


def test_a_commit_that_is_not_a_whole_sha_is_refused(check):
    p = check(commit=COMMIT[:10], **runs(gh_run(44643717559, "success")))
    assert p.returncode == 1 and "whole commit" in p.stderr, p.stdout + p.stderr


def test_both_release_paths_check_github_green_before_they_build_or_export():
    local = (BUILD / "tools/release_local.py").read_text()
    main = local[local.index("def main("):]
    assert re.search(r"green_refusal\(sha\)", main) and main.index("green_refusal(sha)") < main.index("build_and_scan(")
    assert '"slice_line" / "release_green.py"' in local and '"check", sha]' in local
    publish = (BUILD / "scripts/publish_user_repo_update.sh").read_text()
    call = re.search(r'python3 "\$ROOT/ospreyflow/OspreyFlow_Build/scripts/slice_line/release_green\.py" check '
                     r'"\$\(git -C "\$ROOT/ospreyflow" rev-parse HEAD\)" \\\n\s*\|\| \{[^}]*exit 1; \}', publish)
    assert call is not None and 0 < call.start() < publish.index("publish-user-repo COMMIT=HEAD")
