"""A red GitHub run on main stops merging and shows on the board (F2; ADR-142 Amendment 9: "while main is red, every
merge is refused"). merge_slice.py merge reads the latest completed run on main with gh, as the script calls it
(`gh run list --branch main --status completed --limit 1 --json ...`, the suite's stand-in answering only that shape):
failure refuses naming the run; cancelled with nothing newer refuses; gh that cannot be read refuses (never green).
Records mode is exempt. board.py prints "main is red: run N" and writes it to status.js.
"""
from __future__ import annotations

import json

import pytest

from test_gates import built, merge, sh, verified, world  # noqa: F401  (world is a fixture)

RED = '[{"databaseId": 44031786619, "conclusion": "failure", "status": "completed", "url": "https://github.invalid/r/44031786619"}]'
CANCELLED = '[{"databaseId": 44040359545, "conclusion": "cancelled", "status": "completed", "url": "https://github.invalid/r/44040359545"}]'
NEWER = '[{"databaseId": 44040359546, "conclusion": "", "status": "in_progress", "url": "https://github.invalid/r/44040359546"}]'


def ready(w, **gh):
    wt, tip = built(w)
    verified(w, wt, tip)
    w["env"].update(gh)
    return sh("git rev-parse main", w["repo"]).stdout, sh(["git", "ls-remote", str(w["origin"]), "refs/heads/main"], w["repo"]).stdout


def unchanged(w, before):
    return (sh("git rev-parse main", w["repo"]).stdout, sh(["git", "ls-remote", str(w["origin"]), "refs/heads/main"],
                                                           w["repo"]).stdout) == before


def test_a_failed_run_on_main_refuses_the_merge_naming_it(world):
    w = world
    before = ready(w, FAKE_GH_COMPLETED=RED)
    p = merge(w)
    assert p.returncode == 1 and "main is red" in p.stderr and "44031786619" in p.stderr, p.stderr
    assert "https://github.invalid/r/44031786619" in p.stderr and unchanged(w, before)


def test_a_cancelled_run_with_nothing_newer_refuses_and_with_a_newer_run_does_not(world):
    w = world
    before = ready(w, FAKE_GH_COMPLETED=CANCELLED)
    p = merge(w)
    assert p.returncode == 1 and "cancelled" in p.stderr and "44040359545" in p.stderr, p.stderr
    assert unchanged(w, before)
    w["env"]["FAKE_GH_LATEST"] = NEWER
    p = merge(w)
    assert p.returncode == 0, p.stderr


@pytest.mark.parametrize("gh", [{"FAKE_GH_EXIT": "1"}, {"FAKE_GH_COMPLETED": "not json"}, {"FAKE_GH_COMPLETED": "[]"}],
                         ids=["gh-fails", "not-json", "no-completed-run"])
def test_a_main_run_that_cannot_be_read_refuses_never_green(world, gh):
    w = world
    before = ready(w, **gh)
    p = merge(w)
    assert p.returncode == 1 and "main's GitHub run" in p.stderr and "cannot" in p.stderr, p.stderr
    assert unchanged(w, before)


def test_records_mode_still_commits_while_main_is_red(world):
    w = world
    w["env"]["FAKE_GH_COMPLETED"] = RED
    v062 = w["repo"] / "OspreyFlow_Build/process/lanes/v062"
    (v062 / "STOP.md").write_text("why the line stopped\n")
    p = sh([w["py"], str(w["lines"] / "merge_slice.py"), "records", "-m", "docs(process): the stop",
            "OspreyFlow_Build/process/lanes/v062/STOP.md"], w["repo"], w["env"], check=False)
    assert p.returncode == 0, p.stderr


def test_the_board_prints_main_is_red_and_writes_it_to_the_status_file(world):
    w = world
    w["env"]["FAKE_GH_COMPLETED"] = RED
    p = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False)
    assert "main is red: run 44031786619" in p.stdout, p.stdout + p.stderr
    status = (w["repo"] / "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/status.js").read_text()
    body = json.loads(status.split("window.OSPREY_STATUS = ", 1)[1].rstrip().rstrip(";"))
    assert body["main_ci"]["state"] == "red" and body["main_ci"]["run"] == 44031786619, body["main_ci"]
    w["env"]["FAKE_GH_EXIT"] = "1"
    p = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False)
    assert "main's GitHub run cannot be read" in p.stdout, p.stdout
