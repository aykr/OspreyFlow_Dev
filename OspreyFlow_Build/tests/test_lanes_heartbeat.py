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

    def hold_lease(holder: str, minutes: int, stack: str = "a") -> None:
        lock = lease / ("stack.lease" if stack == "a" else f"stack-{stack}.lease")
        lock.mkdir(parents=True)
        (lock / "info").write_text(
            f"holder={holder}\nstack={stack}\npurpose=phase 6 route tests\nsince={_ago(minutes)}\n"
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


def _mine(show: subprocess.CompletedProcess[str]) -> list[str]:
    """The orchestrator's own queue: shown, never notified (the owner, 9 November 2026: a quiet lane and a
    long-held stack are the orchestrator's to settle in its own check, not the owner's)."""
    out = show.stdout
    if "FOR THE ORCHESTRATOR" not in out:
        return []
    section = out.split("FOR THE ORCHESTRATOR")[1].split("\n", 1)[1]
    return [line.strip()[2:] for line in section.splitlines() if line.strip().startswith("- ")]


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


def test_a_working_beat_older_than_the_quiet_limit_is_the_orchestrators(hb) -> None:
    _all_beat(hb)
    hb.age("glass", 46)
    show = hb("show")
    assert _needs(show) == []
    [line] = _mine(show)
    assert line.startswith("glass has been quiet since ") and line.endswith(" while working")


def test_a_waiting_for_owner_beat_needs_you(hb) -> None:
    _all_beat(hb)
    hb("beat", "case", "waiting-for-owner", "the owner's ruling on open question 1")
    assert _needs(hb("show")) == ["case is waiting for you: the owner's ruling on open question 1"]


def test_a_waiting_beat_that_names_no_owner_is_the_orchestrators(hb) -> None:
    """Lanes beat waiting-for-owner while they wait on the orchestrator (a merge, a slot, a stack): on
    10 November 2026 the owner was shown "case is waiting for you: L3.6 ... waiting for L2.10 to merge"
    under Needs you. A waiting note that does not name the owner is the orchestrator's, never notified."""
    _all_beat(hb)
    hb("beat", "case", "waiting-for-owner", "L3.6 plan ratified; waiting for L2.10 to merge")
    show = hb("show")
    assert _needs(show) == []
    assert _mine(show) == ["case is waiting for the orchestrator: L3.6 plan ratified; waiting for L2.10 to merge"]


def test_a_lease_older_than_its_limit_is_the_orchestrators(hb) -> None:
    _all_beat(hb)
    hb.hold_lease("studio", 121)
    show = hb("show")
    assert _needs(show) == []
    [line] = _mine(show)
    assert line.startswith("Test stack a has been leased by studio since ")


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
    hb("beat", "studio", "waiting-for-owner", "the owner's answer on open question 1")
    hb.age("studio", 46)
    now = int(datetime.now(UTC).timestamp())
    first = _needs(hb("show", OSPREY_NOW=str(now)))
    later = _needs(hb("show", OSPREY_NOW=str(now + 600)))
    assert len(first) == 1  # the quiet and ready-to-merge lines are the orchestrator's, not under NEEDS YOU
    assert later == first


def test_watch_notifies_once_per_new_line_not_on_every_pass(hb) -> None:
    _all_beat(hb)
    hb.age("glass", 46)  # quiet: the orchestrator's, never notified (the owner, 9 November 2026)
    hb.hold_lease("studio", 121)  # long-held: the orchestrator's too
    hb("beat", "case", "waiting-for-owner", "a question for the owner")
    hb("watch", "1", OSPREY_WATCH_PASSES="3")
    notes = hb.notified.read_text().splitlines()
    assert len(notes) == 1, notes
    hb("beat", "studio", "waiting-for-owner", "another question for the owner")
    hb("watch", "1", OSPREY_WATCH_PASSES="2")
    notes = hb.notified.read_text().splitlines()
    # A new watch starts with nothing seen, so both owner lines are new to it, once each.
    assert len(notes) == 3, notes
    assert not any("quiet" in n or "leased" in n for n in notes), notes


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
    """`show --full` says in words what is done and what is left: an overall total, then per lane a
    heading with its count and state, and every step on its own line with its status spelled out."""
    table = tmp_path / "progress.tsv"
    table.write_text(
        "# comment\n"
        "studio\tL1.1\tS\tdone\tFirst\nstudio\tL1.2\tL\treview\tSecond step\nstudio\tL1.3\tL\ttodo\tThird\n"
        "studio\tL1.4\tM\ttodo\tFourth\n"
        "case\tL3.1\tL\tbuilding\tOnly step\n"
    )
    hb("beat", "studio", "working", "on the drawer")
    out = hb("show", "--full", OSPREY_PROGRESS_FILE=str(table)).stdout
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
    hb("beat", "case", "waiting-for-owner", "a question for the owner")
    out = hb("show").stdout
    needs = out.split("NEEDS YOU:")[1].split("FOR THE ORCHESTRATOR")[0]
    assert "case is waiting for you" in needs and "glass is ready to merge" not in needs
    assert "glass is ready to merge" in out.split("FOR THE ORCHESTRATOR")[1]
    hb("watch", "1", OSPREY_WATCH_PASSES="1")
    notes = hb.notified.read_text().splitlines()
    assert len(notes) == 1 and "case is waiting for you: a question for the owner" in notes[0]


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


def test_a_lane_waiting_for_the_lease_is_the_orchestrators_whatever_state_it_beats(hb) -> None:
    """Found 7 November 2026, 23:40: glass beat waiting-for-owner while it waited only for the lease,
    which the orchestrator passes; the owner was shown it under Needs you."""
    _all_beat(hb)
    assert hb("beat", "glass", "waiting-for-owner", "round 1 fixes in; waiting for the glass lease for the live reds").returncode == 0
    assert hb("beat", "case", "waiting-for-owner", "Q1 for the owner: which of a, b or c?").returncode == 0
    show = hb("show")
    assert _needs(show) == ["case is waiting for you: Q1 for the owner: which of a, b or c?"]
    assert "glass is waiting for the lease: round 1 fixes in" in show.stdout.split("FOR THE ORCHESTRATOR")[1]


def test_shows_run_at_once_do_not_mix_their_lines(hb) -> None:
    """Found 7 November 2026, 23:45: the owner's running `watch` and the orchestrator's `show` wrote the
    same temporary files, so a line appeared twice, and the old script's line beside the new one's."""
    import concurrent.futures

    _all_beat(hb)
    assert hb("beat", "glass", "ready-to-merge", "L2.8 done").returncode == 0
    assert hb("beat", "case", "waiting-for-owner", "Q1 for the owner: which of a, b or c?").returncode == 0
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        outs = list(pool.map(lambda _: hb("show").stdout, range(16)))
    for out in outs:
        assert _needs(type("S", (), {"stdout": out})()) == ["case is waiting for you: Q1 for the owner: which of a, b or c?"], out
        assert out.count("glass is ready to merge") == 1, out



# --- Six lanes and two stacks (ADR-142 Amendment 3, 8 November 2026) -----------------------------------


def test_the_lanes_shown_by_default_are_the_six_of_amendment_3(hb) -> None:
    """With no OSPREY_LANES, the heartbeat shows the lanes scripts/lanes.conf lists, in its order, and not
    the retired glass lane (red against the four-lane default)."""
    out = hb("show", OSPREY_LANES="").stdout
    lanes = {"STUDIO", "STUDIO-B", "CASE", "CASE-B", "ADMIN", "RULES", "RULES-B", "PLATFORM", "DOCS", "GLASS"}
    order = [line.split(":", 1)[0] for line in out.splitlines() if line.split(":", 1)[0] in lanes]
    # ADR-142 Amendment 4 (the owner, 8 November): each sister lane listed after its parent.
    assert order == ["STUDIO", "STUDIO-B", "CASE", "CASE-B", "ADMIN", "RULES", "RULES-B", "PLATFORM", "DOCS"]
    assert "GLASS:" not in out


def test_each_test_stack_is_shown_with_its_holder(hb) -> None:
    _all_beat(hb)
    out = hb("show").stdout
    assert "Test stack a: free" in out and "Test stack b: free" in out and "Test stack c: free" in out
    hb.hold_lease("studio", 10, "a")
    hb.hold_lease("rules", 20, "b")
    out = hb("show").stdout
    assert "Test stack a: leased by studio for 'phase 6 route tests', 10 minutes" in out
    assert "Test stack b: leased by rules for 'phase 6 route tests', 20 minutes" in out


def test_a_stack_b_lease_older_than_its_limit_is_the_orchestrators(hb) -> None:
    _all_beat(hb)
    hb.hold_lease("rules", 121, "b")
    show = hb("show")
    assert _needs(show) == []
    [line] = _mine(show)
    assert line.startswith("Test stack b has been leased by rules since ")



def test_the_default_view_fits_one_screen_and_names_each_lanes_current_step(hb, tmp_path) -> None:
    """The owner, 8 November 2026: "make the heartbeat report a bit more readable so that I don't have to
    scroll". Six lanes with forty-odd steps ran to 68 lines, one per step. The default view is now one
    heading and at most one note line per lane, with the step each lane is on; the checklist is
    `show --full` (red against the per-step view)."""
    rows = []
    for lane in ("studio", "case", "admin", "rules", "platform", "docs"):
        rows += [f"{lane}\t{lane[:2].upper()}{i}\tM\t{'done' if i < 3 else ('building' if i == 3 else 'todo')}\tStep {i}"
                 for i in range(1, 9)]
    table = tmp_path / "progress.tsv"
    table.write_text("\n".join(rows) + "\n")
    for lane in ("studio", "case", "admin", "rules", "platform", "docs"):
        hb("beat", lane, "working", "x" * 300)
    out = hb("show", OSPREY_LANES="", OSPREY_PROGRESS_FILE=str(table)).stdout
    lines = out.splitlines()
    # Two lines per lane at most, for every lane the default view lists (ten with Amendment 4's sisters and platform-b).
    assert len(lines) <= 10 * 2 + 14, out  # ten lanes with platform-b; one line per test stack, seven with d to g (9 November 2026)
    at = next(i for i, line in enumerate(lines) if line.startswith("STUDIO:"))
    studio = lines[at]
    assert "2 of 8 done" in studio and lines[at + 1].strip().startswith("now ST3 Step 3")
    # A bar per lane and overall (the owner, the same afternoon: "some sort of progress bar").
    assert "[███░░░░░░░░░]" in studio, studio
    assert next(l for l in lines if l.startswith("OVERALL")).count("█") == 6  # 12 of 48, on a bar of 24
    assert not any(line.strip().startswith("to do ") for line in lines)
    assert all(len(line) <= 120 for line in lines), "a note is trimmed to the screen"
    full = hb("show", "--full", OSPREY_LANES="", OSPREY_PROGRESS_FILE=str(table)).stdout
    assert "to do        ST8" in full



# --- The orchestrator's estimates on the dashboard (the owner, 9 November 2026) ------------------------------


def test_show_prints_the_orchestrators_estimates_with_their_age(hb, tmp_path) -> None:
    table = tmp_path / "progress.tsv"
    table.write_text("studio\tL1.5\tL\tbuilding\tExpert steps\n")
    (tmp_path / "estimates.tsv").write_text(
        "# as of 2026-11-09T20:50:00Z\n"
        "studio\tL1.5\tlive run on b, then the merge\t~1 h\n"
        "case\tL3.9\tafter L3.4\t~8-10 h after L3.4\n"
    )
    out = hb("show", OSPREY_LANES="", OSPREY_PROGRESS_FILE=str(table)).stdout
    assert "ESTIMATED TIME TO MERGE (the orchestrator's, as of 20:50 UTC" in out and "m ago)" in out
    assert "live run on b, then the merge" in out and "~8-10 h after L3.4" in out
    needs = out.find("NEEDS YOU:") if "NEEDS YOU:" in out else out.index("Nothing needs you")
    assert out.index("ESTIMATED TIME TO MERGE") < needs  # above what needs the owner


def test_show_prints_no_estimates_section_without_the_file(hb, tmp_path) -> None:
    table = tmp_path / "progress.tsv"
    table.write_text("studio\tL1.5\tL\tbuilding\tExpert steps\n")
    out = hb("show", OSPREY_LANES="", OSPREY_PROGRESS_FILE=str(table)).stdout
    assert "ESTIMATED TIME TO MERGE" not in out



# --- The owner's short view (10 November 2026: "the dashboard is getting too busy to read") -------------------


def _summary_fixture(tmp_path):
    table = tmp_path / "progress.tsv"
    table.write_text("studio\tL1.5\tL\tdone\tExpert steps\nplatform\tP7\tL\tbuilding\tThe profile\n")
    (tmp_path / "estimates.tsv").write_text(
        "# as of 2026-11-10T05:36:00Z\n"
        "studio\tL1.7\toperations and releases\t~17:00\tA\n"
        "platform\tP7\tcloud-platform profile\t~20:00\tB\n"
        "docs\tD2a\tguides\t~07:15\n"
    )
    return table


def test_summary_is_short_and_splits_the_remaining_steps_by_track(hb, tmp_path) -> None:
    table = _summary_fixture(tmp_path)
    out = hb("summary", OSPREY_LANES="studio platform", OSPREY_PROGRESS_FILE=str(table)).stdout
    lines = out.splitlines()
    assert lines[0].startswith("OSPREYFLOW · 1 of 2 steps done · stacks in use: 0")
    assert "REMAINING (the orchestrator's estimates, as of 05:36 UTC):" in out
    demo, client = out.index("Demo track:"), out.index("Client track:")
    assert demo < out.index("operations and releases") < client < out.index("cloud-platform profile")
    assert demo < out.index("guides") < client  # a row with no track is the demo track's
    assert "LANES: studio - · platform -" in out
    assert "Test stack" not in out and "FOR THE ORCHESTRATOR" not in out  # the detail stays in `show`
    assert len(lines) <= 16, out


def test_watch_shows_the_default_view_unless_asked_for_the_full_view(hb, tmp_path) -> None:
    """The owner, 11 November 2026: watch prints the default view (the two views, the release, housekeeping
    and the Lanes table) on every pass, not the older summary by track; --full stays lane by lane."""
    table = _summary_fixture(tmp_path)
    env = {"OSPREY_WATCH_PASSES": "1", "OSPREY_LANES": "studio", "OSPREY_PROGRESS_FILE": str(table)}
    default = hb("watch", "1", **env).stdout
    for heading in ("VIEW 1 · FOUNDATION FEATURES", "VIEW 2 · DEPLOYMENT", "RELEASE", "HOUSEKEEPING", "LANES"):
        assert heading in default, heading
    assert "NEEDS YOU:\n  - studio has never sent a heartbeat" in default  # what needs the owner, shown each pass
    assert "Demo track" not in default and "Client track" not in default and "Test stack" not in default
    for args in (("--full",), ("--full", "1"), ("1", "--full")):
        full = hb("watch", *args, **env).stdout
        assert "Test stack" in full and "VIEW 1 · FOUNDATION FEATURES" not in full, args


def test_the_default_view_opens_with_the_overall_count_of_steps(hb, tmp_path) -> None:
    """The owner, 11 November 2026: the default view (and so watch) gives the overall count of steps, the same
    figures `show`'s OVERALL line gives, before the two views."""
    table = tmp_path / "progress.tsv"
    table.write_text(
        "studio\tL1.5\tL\tdone\tExpert steps\n"
        "studio\tL1.6\tL\tdone\tSchedules\n"
        "platform\tP7\tL\tbuilding\tThe profile\n"
        "case\tP9\tM\treview\tBackups\n"
        "admin\tT1\tS\ttodo\tFaster runs\n"
    )
    out = hb(OSPREY_LANES="studio", OSPREY_PROGRESS_FILE=str(table)).stdout
    line = "OVERALL: 2 of 5 steps done · 1 in review · 1 building · 1 not started"
    assert line in out
    assert out.index(line) < out.index("VIEW 1 · FOUNDATION FEATURES")
    watched = hb("watch", "1", OSPREY_WATCH_PASSES="1", OSPREY_LANES="studio", OSPREY_PROGRESS_FILE=str(table)).stdout
    assert line in watched


def test_the_older_summary_stays_available_as_its_own_verb(hb, tmp_path) -> None:
    table = _summary_fixture(tmp_path)
    out = hb("summary", OSPREY_LANES="studio", OSPREY_PROGRESS_FILE=str(table)).stdout
    assert "OSPREYFLOW ·" in out and "VIEW 1 · FOUNDATION FEATURES" not in out


def test_an_estimate_is_cut_by_characters_never_through_one(hb, tmp_path) -> None:
    """10 November 2026: an estimate reading "parts 2–5 …" was cut at a fixed byte width, through the en dash's
    three bytes, so `show` and `summary` printed invalid UTF-8 and every lane's lanes-check failed decoding them.
    The cut is by characters: an estimate of en dashes and arrows past the width comes out whole up to it."""
    table = tmp_path / "progress.tsv"
    table.write_text("admin\tT1\tM\tbuilding\tFaster runs\n")
    note = "–" * 30 + "→" * 30  # 60 characters, 180 bytes: any byte cut lands inside one
    (tmp_path / "estimates.tsv").write_text(f"# as of 2026-11-10T12:00:00Z\nadmin\tT1\t{note}\t~13:30\tA\n")
    for verb in ("show", "summary"):
        out = hb(verb, OSPREY_LANES="", OSPREY_PROGRESS_FILE=str(table)).stdout  # text=True: a bad byte raises
        assert "–" * 30 + "→" * 10 in out, verb


# --- the owner's default view (11 November 2026) ---------------------------------------------------------------
# The fixture is the real files' shape: progress.tsv's five columns, groups.tsv's header and four columns,
# estimates.tsv's "# as of" line and five columns, release.tsv's keys; the beats are written by the real `beat`.

_FEATURES = [
    "Ingest Studio", "Four places, the Glass and Admin", "Cases and drawing boards", "Rules and alerting",
    "Models and maps", "Laurium",
]
_DEPLOYMENTS = [
    "Local-lite", "Small (osprey-small runs v0.5.0)", "Client install (cloud-platform profile, shape: poc)",
    "After the client's install (the deferred steps)",
]


def _overview_fixture(hb, tmp_path: Path) -> dict[str, str]:
    steps = [  # lane, step, size, status, title, feature, deployment
        ("studio", "L1", "S", "done", "Ingest one: the first", "Ingest Studio", "Small"),
        ("studio", "L2", "M", "building", "Ingest two: the drawers", "Ingest Studio", "Small"),
        ("studio", "L3", "S", "todo", "Ingest three; the connectors", "Ingest Studio", "Client install"),
        ("case", "C1", "L", "review", "Case one (ADR-1): drawing", "Cases and drawing boards", "Small"),
        ("case", "C2", "S", "todo", "Case two", "Cases and drawing boards", "Local-lite"),
        ("admin", "A1", "M", "building", "Sign-in claims: Entra ID", "Four places, the Glass and Admin", "Client install"),
        ("admin", "A2", "S", "todo", "Admin two", "Four places, the Glass and Admin", "Small"),
        ("rules", "R1", "S", "building", "Rule one", "Rules and alerting", "Small"),
        ("rules", "R2", "S", "todo", "Rule two", "Rules and alerting", "After the client's install"),
        ("platform", "M1", "S", "done", "Map one", "Models and maps", "Small"),
        ("platform", "X1", "L", "building", "Laurium as an engine: part 1", "Laurium", "Client install"),
        ("docs", "H1", "S", "done", "Tidy one", "Housekeeping", "Housekeeping"),
        ("docs", "H2", "S", "building", "Tidy two", "Housekeeping", "Housekeeping"),
        ("docs", "H3", "S", "todo", "The client's guide", "Housekeeping", "Client install"),
    ]
    progress = tmp_path / "progress.tsv"
    progress.write_text("# lane, step, size, status, title\n" + "".join("\t".join(s[:5]) + "\n" for s in steps))
    (tmp_path / "groups.tsv").write_text(
        "# lane, step, feature, deployment\n"
        f"# Feature: {' | '.join(_FEATURES)} | Housekeeping\n"
        "# Deployment: Local-lite | Small | Client install | After the client's install | Housekeeping\n"
        + "".join(f"{s[0]}\t{s[1]}\t{s[5]}\t{s[6]}\n" for s in steps)
    )
    (tmp_path / "estimates.tsv").write_text(
        "# as of 2026-11-11T15:00Z\nstudio\tL2\tthe drawers\t12 Nov\tB\nadmin\tA1\tclaims\t13 Nov\tB\n"
    )
    (tmp_path / "release.tsv").write_text(
        "# key, value\nlast\tv0.5.0\npublished\t2026-11-11 06:35 UTC\ncut\t0000000\nrepository\tx/y\n"
        "next\tv0.5.1: the chain merged\nchain\t14 Nov\nsmall\tv0.5.0\n"
    )
    launcher = tmp_path / "launcher.sh"  # lanes_launch.sh's `alive`: only case's session runs here
    launcher.write_text('#!/bin/sh\n[ "$1" = alive ] && [ "$2" = case ] && { echo yes; exit 0; }\necho no; exit 1\n')
    launcher.chmod(0o755)
    env = {
        "OSPREY_LANES": "studio case admin rules platform docs",
        "OSPREY_PROGRESS_FILE": str(progress),
        "OSPREY_LAUNCHER": str(launcher),
        "OSPREY_ACCOUNTS_FILE": str(tmp_path / "accounts.conf"),
    }
    (tmp_path / "accounts.conf").write_text("account sol = ~/.claude-sol\nlane rules    = sol\n")
    for lane, state, note in [
        ("studio", "working", "L2: wiring the drawers"),
        ("case", "working", "C1 review fixes"),
        ("admin", "waiting-for-owner", "A1: the owner's ruling on the claim names, a or b"),
        ("rules", "ready-to-merge", "R1 gates green"),
        ("platform", "working", "X1 part 1 live run"),
        ("docs", "working", "H2 tidying"),
    ]:
        assert hb("beat", lane, state, note).returncode == 0
    return env


def _blocks(out: str) -> dict[str, list[str]]:
    """Each block's heading (two spaces in) and its lines (four spaces in)."""
    blocks: dict[str, list[str]] = {}
    current = None
    for line in out.splitlines():
        if line.startswith("  ") and not line.startswith("   ") and current is not False:
            current = line.strip()
            blocks[current] = []
        elif line.startswith("    ") and current:
            blocks[current].append(line.strip())
        if line == "LANES":
            current = False
    return blocks


def test_the_default_view_shows_its_blocks_in_the_owners_order(hb, tmp_path) -> None:
    out = hb(**_overview_fixture(hb, tmp_path)).stdout
    assert out.splitlines()[1] == "Client-install chain expected to finish merging: 14 Nov (estimates as of 15:00 UTC)"
    order = ["VIEW 1 · FOUNDATION FEATURES", *(f"  {f}\n" for f in _FEATURES), "VIEW 2 · DEPLOYMENT",
             *(f"  {d}\n" for d in _DEPLOYMENTS), "\nRELEASE\n", "\nHOUSEKEEPING\n", "  Housekeeping\n", "\nLANES\n"]
    at = [out.index(heading) for heading in order]
    assert at == sorted(at), out


def test_the_default_view_lists_only_steps_not_done_with_counts(hb, tmp_path) -> None:
    out = hb(**_overview_fixture(hb, tmp_path)).stdout
    blocks = _blocks(out)
    for done in ("(L1, studio)", "(M1, platform)", "(H1, docs)"):
        assert done not in out, done
    assert blocks["Ingest Studio"] == [
        "1 of 3 steps done",
        "Ingest two (L2, studio) · building · 12 Nov",
        "Ingest three (L3, studio) · not started · no estimate",
    ]
    assert blocks["Models and maps"] == ["1 of 1 steps done"]
    assert blocks["Small (osprey-small runs v0.5.0)"][0] == "2 of 6 steps done"
    assert blocks["Client install (cloud-platform profile, shape: poc)"][0] == "0 of 4 steps done"
    assert blocks["Housekeeping"] == ["1 of 2 steps done", "Tidy two (H2, docs) · building · no estimate"]


def test_the_default_view_says_each_state_in_plain_words(hb, tmp_path) -> None:
    import re

    out = hb(**_overview_fixture(hb, tmp_path)).stdout
    states = {
        line.split(" · ")[1]
        for lines in _blocks(out).values()
        for line in lines
        if " · " in line
    }
    assert states == {"building", "not started", "in review", "waiting to merge",
                      "needs you: A1: the owner's ruling on the…"}, states
    # The step table's and the beats' own codes never reach the owner ("in review" is the plain words for review).
    assert not re.search(r"\btodo\b|(?<!in )\breview\b|ready-to-merge|waiting-for-owner|being built", out), out


def test_the_default_views_lanes_table_names_each_lanes_step_and_next(hb, tmp_path) -> None:
    out = hb(**_overview_fixture(hb, tmp_path)).stdout
    rows = {line.split()[0]: " ".join(line.split()) for line in out.split("\nLANES\n")[1].splitlines()[1:] if line.startswith("  ")}
    assert rows["platform"].endswith("X1 (Laurium / Client install) free")
    assert rows["docs"].endswith("H2 (Housekeeping / Housekeeping) H3")
    assert rows["admin"].endswith("A1 (Four places, the Glass and Admin / Client install) A2")
    assert rows["case"].startswith("case default this Mac C1 ")
    assert rows["rules"].startswith("rules sol not running R1 ")


def test_the_lane_by_lane_view_is_kept_behind_lanes(hb, tmp_path) -> None:
    env = _overview_fixture(hb, tmp_path)
    lanes, show = hb("--lanes", **env).stdout, hb("show", **env).stdout
    assert lanes.splitlines()[0] == show.splitlines()[0] and lanes.startswith("OVERALL: ")
    assert "STUDIO: " in lanes and "VIEW 1" not in lanes
    full = hb("--lanes", "--full", **env).stdout
    assert "  done         H1     Tidy one" in full and "VIEW 1" not in full
