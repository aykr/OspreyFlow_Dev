"""GitHub's run on main is a second opinion, not a gate (the owner, 20 November 2026; LINE_FIXES_4_BRIEF.md, 1a; this
replaces ADR-142 Amendment 9's "while main is red, every merge is refused").

merge_slice.py merge reads the latest completed run on main with gh, as it always has (common.main_ci(): `gh run list
--branch main --status completed --limit 1 --json ...`, answered by tests/fake_gh.py in the shape the real gh gives),
and no longer refuses on what it says: red, cancelled with nothing newer, or unreadable, the merge goes on on the
Mac's full gate alone. It records the state in merged.json (`github_at_merge`: state, run, url, why, at) and says it in
one line. Records mode never read it. board.py still prints "main is red: run N", now as a note, not a hold.
"""
from __future__ import annotations

import json

import pytest

from test_gates import built, merge, sh, verified, world  # noqa: F401  (world is a fixture)

URL = "https://github.com/o/r/actions/runs/"


def gh_run(run, conclusion, status="completed", head="d64ad0ec032def06143490f641e16deeffb3fc20", attempt=1):
    """One run as `gh run list --json` gives it."""
    return {"databaseId": run, "attempt": attempt, "conclusion": conclusion, "status": status, "url": f"{URL}{run}",
            "headSha": head, "headBranch": "main", "workflowName": "ci", "event": "push"}


RED = json.dumps([gh_run(44681092481, "failure")])
CANCELLED = json.dumps([gh_run(44040359545, "cancelled")])
GREEN = json.dumps([gh_run(44643717559, "success")])


def ready(w, **gh):
    wt, tip = built(w)
    verified(w, wt, tip)
    w["env"].update(gh)
    return tip


def merged_record(w):
    return json.loads((w["data"] / "records/S1/merged.json").read_text())


@pytest.mark.parametrize("gh, state, run, said", [
    ({"FAKE_GH_RUNS": RED}, "red", 44681092481, "GitHub's last run on main: red (run 44681092481), not a gate; merging"),
    ({"FAKE_GH_RUNS": CANCELLED}, "red", 44040359545,
     "GitHub's last run on main: red (run 44040359545), not a gate; merging"),
    ({"FAKE_GH_RUNS": GREEN}, "green", 44643717559,
     "GitHub's last run on main: green (run 44643717559), not a gate; merging"),
    ({"FAKE_GH_EXIT": "1"}, "unknown", None, "GitHub's last run on main: cannot be read"),
    ({"FAKE_GH_RUNS": "not json"}, "unknown", None, "GitHub's last run on main: cannot be read"),
    ({"FAKE_GH_RUNS": "[]"}, "unknown", None, "GitHub's last run on main: cannot be read"),
], ids=["red", "cancelled-nothing-newer", "green", "gh-fails", "not-json", "no-completed-run"])
def test_the_merge_goes_on_whatever_github_says_and_records_it(world, gh, state, run, said):
    w = world
    ready(w, **gh)
    p = merge(w)
    assert p.returncode == 0, p.stderr
    done = json.loads(p.stdout)
    assert sh("git rev-parse main", w["repo"]).stdout.strip() == done["merge"]
    assert said in p.stderr and "not a gate; merging" in p.stderr, p.stderr
    rec = merged_record(w)["github_at_merge"]
    assert rec["state"] == state and rec["run"] == run, rec
    assert set(rec) >= {"state", "run", "url", "why", "at"} and rec["at"].endswith("Z"), rec
    if run:
        assert rec["url"] == f"{URL}{run}", rec


def test_a_cancelled_run_with_a_newer_one_is_recorded_green_as_before(world):
    w = world
    ready(w, FAKE_GH_RUNS=json.dumps([gh_run(44040359546, "", status="in_progress"), gh_run(44040359545, "cancelled")]))
    p = merge(w)
    assert p.returncode == 0, p.stderr
    rec = merged_record(w)["github_at_merge"]
    assert rec["state"] == "green" and "newer run 44040359546" in rec["why"], rec


def test_the_other_refusals_still_hold_while_github_is_red(world):
    w = world
    wt, tip = built(w)  # no verifier pass for the tip
    w["env"]["FAKE_GH_RUNS"] = RED
    p = merge(w)
    assert p.returncode == 1 and "no verifier record" in p.stderr, p.stderr


def test_records_mode_still_commits_while_main_is_red(world):
    w = world
    w["env"]["FAKE_GH_RUNS"] = RED
    v062 = w["repo"] / "OspreyFlow_Build/process/lanes/v062"
    (v062 / "STOP.md").write_text("why the line stopped\n")
    p = sh([w["py"], str(w["lines"] / "merge_slice.py"), "records", "-m", "docs(process): the stop",
            "OspreyFlow_Build/process/lanes/v062/STOP.md"], w["repo"], w["env"], check=False)
    assert p.returncode == 0, p.stderr


def test_the_board_prints_main_is_red_as_a_note_not_a_hold_and_writes_it_to_the_status_file(world):
    w = world
    w["env"]["FAKE_GH_RUNS"] = RED
    p = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False)
    line = next((ln for ln in p.stdout.splitlines() if ln.startswith("main is red: run 44681092481")), "")
    assert line and "not a gate" in line and "no merge" not in line, p.stdout + p.stderr
    status = (w["repo"] / "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/status.js").read_text()
    body = json.loads(status.split("window.OSPREY_STATUS = ", 1)[1].rstrip().rstrip(";"))
    assert body["main_ci"]["state"] == "red" and body["main_ci"]["run"] == 44681092481, body["main_ci"]
    w["env"]["FAKE_GH_EXIT"] = "1"
    p = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False)
    line = next((ln for ln in p.stdout.splitlines() if ln.startswith("main's GitHub run cannot be read")), "")
    assert line and "not a gate" in line and "no merge" not in line, p.stdout
