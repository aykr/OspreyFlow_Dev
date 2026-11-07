"""`scripts/lanes_heartbeat.sh` (ADR-142 decision 9): lanes beat; the owner's monitor lists what needs
them, and `watch` notifies once per new line.

Rule 15: every beat is written by the real `beat` command and then aged by rewriting its `at=` line,
so the planted state is the shape `beat` writes; the lease is the shape `stack_lease.sh` writes;
`osascript` is a stand-in on `PATH` that records each notification it is asked for.
"""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

BUILD = Path(__file__).resolve().parents[1]
SCRIPT = BUILD / "scripts" / "lanes_heartbeat.sh"


def _ago(minutes: int) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def hb(tmp_path: Path):
    lanes = tmp_path / "lanes"
    lease = tmp_path / "lease"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    notified = tmp_path / "notified.log"
    fake = bin_dir / "osascript"
    fake.write_text(f'#!/bin/sh\nprintf "%s\\n" "$2" >> "{notified}"\n')
    fake.chmod(0o755)
    env = {
        **os.environ,
        "OSPREY_LANES_DIR": str(lanes),
        "OSPREY_LEASE_DIR": str(lease),
        "OSPREY_WORKTREES": str(tmp_path / "no-worktrees"),
        "OSPREY_LANES": "studio glass case",
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "TERM": "dumb",
    }

    def run(*args: str, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT), *args], env={**env, **extra}, capture_output=True, text=True
        )

    def age(lane: str, minutes: int) -> None:
        path = lanes / f"{lane}.beat"
        text = path.read_text()
        old = next(line for line in text.splitlines() if line.startswith("at="))
        path.write_text(text.replace(old, f"at={_ago(minutes)}"))

    def hold_lease(holder: str, minutes: int) -> None:
        (lease / "stack.lease").mkdir(parents=True)
        (lease / "stack.lease" / "info").write_text(
            f"holder={holder}\npurpose=phase 6 route tests\nsince={_ago(minutes)}\n"
            f"worktree=/x/{holder}\n"
        )

    run.age, run.hold_lease, run.notified = age, hold_lease, notified  # type: ignore[attr-defined]
    return run


def _needs(show: subprocess.CompletedProcess[str]) -> list[str]:
    out = show.stdout
    if "NEEDS YOU:" not in out:
        return []
    section = out.split("NEEDS YOU:")[1].split("FOR THE ORCHESTRATOR")[0]
    return [line.strip()[2:] for line in section.splitlines() if line.strip()]


def _all_beat(hb, state: str = "working") -> None:
    for lane in ("studio", "glass", "case"):
        assert hb("beat", lane, state, f"{lane} at work").returncode == 0


def test_an_unknown_state_is_refused(hb) -> None:
    refused = hb("beat", "studio", "coding", "x")
    assert refused.returncode == 2
    assert "Unknown state 'coding'" in refused.stderr


def test_fresh_working_lanes_need_nothing(hb) -> None:
    _all_beat(hb)
    assert _needs(hb("show")) == []


def test_a_working_beat_older_than_the_quiet_limit_needs_you(hb) -> None:
    _all_beat(hb)
    hb.age("glass", 46)
    [line] = _needs(hb("show"))
    assert line.startswith("glass has been quiet since ") and line.endswith(" while working")


def test_a_waiting_for_owner_beat_needs_you(hb) -> None:
    _all_beat(hb)
    hb("beat", "case", "waiting-for-owner", "question on open question 1")
    assert _needs(hb("show")) == ["case is waiting for you: question on open question 1"]


def test_a_lease_older_than_its_limit_needs_you(hb) -> None:
    _all_beat(hb)
    hb.hold_lease("studio", 121)
    [line] = _needs(hb("show"))
    assert line.startswith("The dev stack has been leased by studio since ")


def test_a_lane_that_never_beat_needs_you(hb) -> None:
    hb("beat", "studio", "working", "x")
    hb("beat", "glass", "working", "x")
    assert _needs(hb("show")) == ["case has never sent a heartbeat"]


def test_a_nudge_is_shown_at_the_next_beat_once(hb) -> None:
    hb("nudge", "studio", "rebase on main")
    first = hb("beat", "studio", "working", "x")
    assert "MESSAGE FROM THE ORCHESTRATOR" in first.stdout and "rebase on main" in first.stdout
    assert "MESSAGE FROM THE ORCHESTRATOR" not in hb("beat", "studio", "working", "x").stdout


def test_a_needs_line_reads_the_same_ten_minutes_later(hb) -> None:
    """What watch compares from pass to pass: a line that carried its own age would be new on every
    pass and notify every time."""
    _all_beat(hb)
    hb.age("glass", 46)
    hb("beat", "case", "ready-to-merge", "L3.1 done")
    hb.hold_lease("studio", 121)
    now = int(datetime.now(UTC).timestamp())
    first = _needs(hb("show", OSPREY_NOW=str(now)))
    later = _needs(hb("show", OSPREY_NOW=str(now + 600)))
    assert len(first) == 2  # the ready-to-merge line is the orchestrator's, not under NEEDS YOU
    assert later == first


def test_watch_notifies_once_per_new_line_not_on_every_pass(hb) -> None:
    _all_beat(hb)
    hb.age("glass", 46)
    hb("beat", "case", "waiting-for-owner", "a question")
    hb("watch", "1", OSPREY_WATCH_PASSES="3")
    notes = hb.notified.read_text().splitlines()
    assert len(notes) == 2, notes
    hb.age("studio", 50)
    hb("watch", "1", OSPREY_WATCH_PASSES="2")
    notes = hb.notified.read_text().splitlines()
    # A new watch starts with nothing seen, so all three are new to it, once each.
    assert len(notes) == 5, notes


def _repo_with_lane(base: Path, ahead: int, behind: int) -> Path:
    """A repository with `main` and `lane/glass`, the lane `ahead` commits ahead and `behind`
    behind, and the worktree folder the monitor looks in, as `lanes_launch.sh setup` makes it."""
    env = {**os.environ, "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    repo = base / "repo"
    repo.mkdir()

    def git(*a: str, cwd: Path = repo) -> None:
        subprocess.run(["git", *a], cwd=cwd, env=env, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("commit", "-q", "--allow-empty", "-m", "base")
    git("branch", "lane/glass")
    for i in range(behind):
        git("commit", "-q", "--allow-empty", "-m", f"main {i}")
    wt = base / "wt" / "glass"
    git("worktree", "add", "-q", str(wt), "lane/glass")
    for i in range(ahead):
        git("commit", "-q", "--allow-empty", "-m", f"lane {i}", cwd=wt)
    return base / "wt"


@pytest.mark.parametrize(("ahead", "flagged"), [(2, True), (0, False)])
def test_a_lane_behind_main_is_flagged_only_while_it_has_work_to_merge(
    hb, tmp_path, ahead, flagged
) -> None:
    """A merged lane (nothing ahead of main) is not asked to rebase however far main has moved."""
    worktrees = _repo_with_lane(tmp_path, ahead=ahead, behind=6)
    _all_beat(hb)
    out = hb("show", OSPREY_WORKTREES=str(worktrees)).stdout
    orchestrator = out.split("FOR THE ORCHESTRATOR")[1] if "FOR THE ORCHESTRATOR" in out else ""
    assert ("glass is 5 or more commits behind main: to rebase" in orchestrator) is flagged
    assert "behind main" not in out.split("FOR THE ORCHESTRATOR")[0]


def test_each_lane_reads_as_a_checklist_of_every_step_in_words(hb, tmp_path) -> None:
    """The view says in words what is done and what is left: an overall total, then per lane a
    heading with its count and state, and every step on its own line with its status spelled out."""
    table = tmp_path / "progress.tsv"
    table.write_text(
        "# comment\n"
        "studio\tL1.1\tS\tdone\tFirst\nstudio\tL1.2\tL\treview\tSecond step\nstudio\tL1.3\tL\ttodo\tThird\n"
        "studio\tL1.4\tM\ttodo\tFourth\n"
        "case\tL3.1\tL\tbuilding\tOnly step\n"
    )
    hb("beat", "studio", "working", "on the drawer")
    out = hb("show", OSPREY_PROGRESS_FILE=str(table)).stdout
    flat = [" ".join(line.split()) for line in out.splitlines()]
    assert "OVERALL: 1 of 5 steps done · 1 in review · 1 being built · 2 to do" in flat
    head = next(i for i, line in enumerate(flat) if line.startswith("STUDIO:"))
    assert flat[head].startswith("STUDIO: 1 of 4 done · working")
    steps = flat[head + 1 : head + 5]
    assert steps[0] == "done L1.1 First"
    assert steps[1].startswith("in review L1.2 Second step") and "now: on the drawer" in steps[1]
    assert steps[2] == "to do L1.3 Third" and steps[3] == "to do L1.4 Fourth"
    assert any(line.startswith("CASE: 0 of 1 done") for line in flat)
    assert any(line.startswith("being built L3.1 Only step") for line in flat)


def test_only_what_needs_the_owner_is_under_needs_you(hb) -> None:
    """A lane ready to merge, or behind main, is the orchestrator's to act on, not the owner's: it is
    listed under FOR THE ORCHESTRATOR and is never notified. A lane waiting for the owner stays under
    NEEDS YOU and is notified."""
    _all_beat(hb)
    hb("beat", "glass", "ready-to-merge", "done")
    hb("beat", "case", "waiting-for-owner", "a question")
    out = hb("show").stdout
    needs = out.split("NEEDS YOU:")[1].split("FOR THE ORCHESTRATOR")[0]
    assert "case is waiting for you" in needs and "glass is ready to merge" not in needs
    assert "glass is ready to merge" in out.split("FOR THE ORCHESTRATOR")[1]
    hb("watch", "1", OSPREY_WATCH_PASSES="1")
    notes = hb.notified.read_text().splitlines()
    assert len(notes) == 1 and "case is waiting for you: a question" in notes[0]


def test_a_paused_lane_is_shown_paused_with_its_account_and_never_as_stalled(hb, tmp_path) -> None:
    """ADR-142 Amendment 1 decision 7: the monitor shows the paused state, how long, and the account;
    a lane paused for hours is not quiet (red with `paused` handled as `working`)."""
    _all_beat(hb)
    assert hb("beat", "case", "paused", "paused at L3.1 fix 7").returncode == 0
    (tmp_path / "lanes" / "case.account").write_text("client\n")
    hb.age("case", 300)
    show = hb("show")
    assert _needs(show) == []
    case_line = next(line for line in show.stdout.splitlines() if line.startswith("CASE:"))
    assert "paused 300m ago" in case_line and "account client" in case_line
    studio_line = next(line for line in show.stdout.splitlines() if line.startswith("STUDIO:"))
    assert "account default" in studio_line


def test_a_lane_at_its_usage_limit_names_its_account_for_the_owner(hb, tmp_path) -> None:
    _all_beat(hb)
    (tmp_path / "lanes" / "glass.account").write_text("ayan\n")
    assert hb("beat", "glass", "blocked", "usage limit").returncode == 0
    [line] = _needs(hb("show"))
    assert line.startswith("glass stopped at its usage limit on account ayan")


def test_a_lane_blocked_only_on_the_lease_is_the_orchestrators_not_the_owners(hb) -> None:
    """The orchestrator passes the lease; a lane waiting for it needs nothing from the owner (found
    7 November 2026: studio and glass both under Needs you while case held the lease)."""
    _all_beat(hb)
    assert hb("beat", "glass", "blocked", "L2.8: waiting for the glass lease for the live round").returncode == 0
    assert hb("beat", "studio", "blocked", "a real block: the fixture repository is gone").returncode == 0
    show = hb("show")
    assert _needs(show) == ["studio is blocked: a real block: the fixture repository is gone"]
    mine = show.stdout.split("FOR THE ORCHESTRATOR")[1]
    assert "glass is waiting for the lease: L2.8: waiting for the glass lease" in mine
