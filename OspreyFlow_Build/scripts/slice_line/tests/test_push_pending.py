"""Every merge is pushed, waiting only while a run is in progress (the owner, 20 November 2026; LINE_FIXES_4_BRIEF.md,
1b).

push_main.sh asks gh as it always has (`gh run list --branch main --status in_progress|queued --json databaseId -q
length`, answered by tests/fake_gh.py as the real gh answers it) and defers only for a run in progress or queued: a
completed red run never holds a push back (on 20 November the push straight after a red run was the old rule's gap; it
is now the rule). A deferred push is kept in push.pending and never forgotten: the board prints "push pending
(<commit>)", and `merge_slice.py push-pending` (the conductor's, when a run ends) pushes it once nothing is in progress
or queued, with every rule of the push script still held (main's tip written by the merge script).
"""
from __future__ import annotations

import json

import pytest

from test_gates import guard, refused, sh, world  # noqa: F401  (world is a fixture)

URL = "https://github.com/o/r/actions/runs/"


def gh_run(run, conclusion, status="completed"):
    return {"databaseId": run, "attempt": 1, "conclusion": conclusion, "status": status, "url": f"{URL}{run}",
            "headSha": "d64ad0ec032def06143490f641e16deeffb3fc20", "headBranch": "main", "workflowName": "ci"}


RED = gh_run(44681092481, "failure")
GOING = {"in_progress": gh_run(44688870618, "", "in_progress"), "queued": gh_run(44688870619, "", "queued")}


def checked(w, *runs):
    """The world with the push script's own check of GitHub on (the suite's other tests turn it off)."""
    env = {k: v for k, v in w["env"].items() if k != "OSPREY_PUSH_NO_CI_CHECK"}
    env["FAKE_GH_RUNS"] = json.dumps(list(runs))
    return env


def merge_written(w):
    sh("git commit -q --allow-empty -m 'merge: slice S1' --trailer 'Slice-Merge: S1'", w["repo"], w["env"])
    return sh("git rev-parse HEAD", w["repo"]).stdout.strip()


def origin_main(w):
    return sh(["git", "ls-remote", str(w["origin"]), "refs/heads/main"], w["repo"]).stdout.split()[0]


def push(w, env):
    return sh([str(w["lines"] / "push_main.sh")], w["repo"], env, check=False)


def push_pending(w, env):
    return sh([w["py"], str(w["lines"] / "merge_slice.py"), "push-pending"], w["repo"], env, check=False)


def test_a_completed_red_run_does_not_defer_the_push(world):
    w = world
    head = merge_written(w)
    p = push(w, checked(w, RED))
    assert p.returncode == 0, p.stdout + p.stderr
    assert origin_main(w) == head and not (w["data"] / "push.pending").exists()


@pytest.mark.parametrize("status", ["in_progress", "queued"])
def test_a_run_in_progress_or_queued_defers_the_push_and_writes_it_pending(world, status):
    w = world
    before = origin_main(w)
    head = merge_written(w)
    p = push(w, checked(w, GOING[status], RED))
    assert p.returncode == 3 and "Deferred" in p.stdout, p.stdout + p.stderr
    assert origin_main(w) == before and (w["data"] / "push.pending").read_text().strip() == head


def test_a_push_clears_what_was_pending(world):
    w = world
    head = merge_written(w)
    assert push(w, checked(w, GOING["in_progress"], RED)).returncode == 3
    p = push(w, checked(w, RED))
    assert p.returncode == 0, p.stdout
    assert origin_main(w) == head and not (w["data"] / "push.pending").exists()


def test_push_pending_pushes_only_once_nothing_is_in_progress_or_queued(world):
    w = world
    before = origin_main(w)
    head = merge_written(w)
    assert push(w, checked(w, GOING["queued"], RED)).returncode == 3
    for status in ("in_progress", "queued"):
        p = push_pending(w, checked(w, GOING[status], RED))
        assert p.returncode == 1 and "still waits" in p.stderr, p.stdout + p.stderr
        assert origin_main(w) == before and (w["data"] / "push.pending").exists()
    p = push_pending(w, checked(w, RED))
    assert p.returncode == 0 and "Pushed main" in p.stdout, p.stdout + p.stderr
    assert origin_main(w) == head and not (w["data"] / "push.pending").exists()


def test_push_pending_with_nothing_pending_does_nothing(world):
    w = world
    before = origin_main(w)
    merge_written(w)
    p = push_pending(w, checked(w, RED))
    assert p.returncode == 0 and "No push is pending" in p.stdout, p.stdout + p.stderr
    assert origin_main(w) == before


def test_push_pending_refuses_when_mains_tip_was_not_written_by_the_merge_script(world):
    w = world
    before = origin_main(w)
    merge_written(w)
    assert push(w, checked(w, GOING["in_progress"])).returncode == 3
    sh("git commit -q --allow-empty -m 'a hand commit'", w["repo"], w["env"])
    p = push_pending(w, checked(w, RED))
    assert p.returncode == 1 and "not written by the merge script" in p.stderr, p.stdout + p.stderr
    assert origin_main(w) == before and (w["data"] / "push.pending").exists()


def test_the_board_prints_push_pending_with_its_commit(world):
    w = world
    head = merge_written(w)
    assert push(w, checked(w, GOING["in_progress"])).returncode == 3
    p = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], checked(w, GOING["in_progress"]), check=False)
    assert f"push pending ({head[:10]})" in p.stdout and "push-pending" in p.stdout, p.stdout + p.stderr


def test_push_pending_is_the_conductors_and_the_push_script_stays_the_owners(world):
    w = world
    cmd = f"{w['py']} OspreyFlow_Build/scripts/slice_line/merge_slice.py push-pending"
    assert guard(w, "Bash", {"command": cmd}, seat="conductor").returncode == 0
    for seat in ("builder", "verifier", "scout"):
        assert refused(guard(w, "Bash", {"command": cmd}, seat=seat)), seat
    for seat in ("conductor", "builder", "verifier", ""):
        assert refused(guard(w, "Bash", {"command": "OspreyFlow_Build/scripts/slice_line/push_main.sh"},
                             seat=seat or None)), seat
