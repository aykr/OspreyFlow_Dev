"""The heartbeat's route view (`process/lanes/ROUTE_052.md`, "The heartbeat's route view"; the owner,
13 November 2026: "for some of the grouping summarise and add progress bars so that it [is] more
readable").

The default view and `watch` show the route to the next release and nothing else needs reading: the
headline (the target, days left, on track, at risk or late, with a bar of steps done and one of days
used), one row per `route.tsv` step (its state from the lane's own progress row and beat, a bar from
the lane's stages, days behind its planned end, what it waits on, critical rows marked), what waits on
the owner and on the orchestrator (`owner_due.tsv`), the audit rulings in one line (`audit.tsv`), the
lane steps outside the route one line a lane, and the finished work in one line. One screen: 40 lines
of at most 120 characters. Without a `route.tsv` the default view is the overview, as before; the
overview stays behind `--overview` and `--full`, the lane-by-lane view behind `--lanes`.

Rule 15: every file is in the shape the orchestrator keeps it (the headers included), every beat is
written by the real `beat`, every stage list by the real `stages`, and the clock is `OSPREY_NOW`.
"""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.test_lanes_heartbeat import hb  # noqa: F401  (the fixture)


def _at(day: int) -> str:
    return str(int(datetime(2026, 11, day, 12, tzinfo=UTC).timestamp()))


ROUTE = (
    "# target\tv0.5.2\t2026-11-26\n"
    "# The route to v0.5.2. Kept by the orchestrator; the heartbeat's default view reads it.\n"
    "# id, title, lane, start, end, critical (y/n), after, progress (lane:step, or -)\n"
    "1\tv0.5.1 cut: the upgrade rehearsal and the CHANGELOG\torchestrator\t2026-11-14\t2026-11-17\tn\t-\t-\n"
    "2\tThe poc manifest and its render test\tplatform\t2026-11-14\t2026-11-15\tn\t-\tplatform:v052-manifest\n"
    "3c\tThe index feed: every change reaches the index\trules\t2026-11-14\t2026-11-19\ty\t-\trules:v052-index\n"
    "3d\tThe search service: names, full text, ranking\tstudio\t2026-11-14\t2026-11-20\ty\tA\tstudio:v052-search\n"
    "3e\tThe Glass's screen fixes\tcase\t2026-11-14\t2026-11-15\tn\t-\tcase:v052-fixes\n"
    "B\tClient-size synthetic data loaded once\trules\t2026-11-16\t2026-11-18\ty\t3c\trules:v052-load\n"
    "4\tThe measurement session on that load\tplatform\t2026-11-23\t2026-11-23\ty\t3c,3d,B\tplatform:v052-measure\n"
    "7\tCut v0.5.2\torchestrator\t2026-11-26\t2026-11-26\ty\t4\t-\n"
)
PROGRESS = (
    "# lane, step, size, status, title\n"
    "platform\tv052-manifest\tM\tdone\tv0.5.2 step 2: the poc manifest\n"
    "rules\tv052-index\tL\tbuilding\tv0.5.2 step 3c: the index feed\n"
    "studio\tv052-search\tL\treview\tv0.5.2 step 3d: the search service\n"
    "case\tv052-fixes\tS\ttodo\tv0.5.2 step 3e: the Glass's screen fixes\n"
    "rules\tv052-load\tM\ttodo\tv0.5.2 B: client-size data\n"
    "platform\tv052-measure\tS\ttodo\tv0.5.2 step 4: the measurement session\n"
    "docs\tsites\tM\tbuilding\tThe two new websites\n"
    "platform\tP8\tL\ttodo\tNothing on a shared disk\n"
    "admin\tD1\tM\ttodo\tThe Conduit's pool sizes from settings\n"
    "studio\tL1\tS\tdone\tIngest one\n"
    "case\tC1\tL\tdone\tCase one\n"
)
OWNER_DUE = (
    "# who (owner|orchestrator), due (YYYY-MM-DD), item, state (open|done)\n"
    "owner\t2026-11-18\tThe search navigation decision (3e′ waits on it)\topen\n"
    "owner\t2026-11-17\tThe acceptance bar's wording\topen\n"
    "owner\t2026-11-15\tA decision already made\tdone\n"
    "orchestrator\t2026-11-16\tThe search access design page (A)\topen\n"
    "orchestrator\t2026-11-14\tScheduled runs on Entra: options (audit 1)\topen\n"
)
AUDIT = (
    "# id, ruling, state, in v0.5.2 (yes|no|owner to decide)\n"
    "1\tScheduled runs under Entra: fix in v0.5.2\toptions pending\towner to decide\n"
    "2\tLaurium document reading: estimate the smallest screen\testimate pending\tno\n"
    "5\tAcceptance bar: spec 08 in the step 6 install test\tsettled\tyes\n"
)


@pytest.fixture
def route(hb, tmp_path: Path):  # noqa: F811
    (tmp_path / "route.tsv").write_text(ROUTE, encoding="utf-8")
    (tmp_path / "progress.tsv").write_text(PROGRESS, encoding="utf-8")
    (tmp_path / "owner_due.tsv").write_text(OWNER_DUE, encoding="utf-8")
    (tmp_path / "audit.tsv").write_text(AUDIT, encoding="utf-8")
    lanes = "platform rules studio case docs admin"
    for lane in lanes.split():
        assert hb("beat", lane, "working", f"{lane} at work").returncode == 0
    env = {"OSPREY_LANES": lanes, "OSPREY_PROGRESS_FILE": str(tmp_path / "progress.tsv")}

    def view(day: int = 16, *args: str) -> str:
        out = hb(*args, OSPREY_NOW=_at(day), **env)
        assert out.returncode == 0, out.stderr[-800:]
        return out.stdout

    view.env = env  # type: ignore[attr-defined]
    return view


def _row(out: str, step: str) -> str:
    return next(line for line in out.splitlines() if line.split()[:1] == [step]
                or line.split()[:2] == [step, "★"] or line.strip().startswith(f"{step} "))  # fmt: skip


def _section(out: str, heading: str) -> list[str]:
    start = next(i for i, line in enumerate(out.splitlines()) if line.startswith(heading))
    lines = out.splitlines()[start:]
    end = next((i for i, line in enumerate(lines[1:], 1) if not line.startswith("  ")), len(lines))
    return lines[:end]


# --- the headline -----------------------------------------------------------------------------------


def test_the_headline_says_the_target_the_days_left_and_on_track_with_two_bars(route) -> None:
    out = route(16)
    head = out.splitlines()
    assert head[1] == "ROUTE TO V0.5.2 · Thu 26 Nov · 10 days left · on track"
    # One of eight steps done (the manifest); the 16th is day 3 of the 13 from the 14th to the 26th.
    assert head[2].startswith("  [") and "1 of 8 steps done" in head[2] and "day 3 of 13" in head[2]


def test_a_critical_step_past_its_planned_end_undone_is_at_risk_and_named(route) -> None:
    out = route(20)  # B (critical) was due on the 18th, 3c (critical) on the 19th; neither is done
    assert out.splitlines()[1].endswith("· at risk")
    risk = out.splitlines()[3]
    assert risk.startswith("  At risk: B Client-size synthetic data loaded once (rules) was due Wed 18 Nov")
    assert risk.endswith("(+1 more at risk)")  # the earliest named, the rest counted


def test_a_step_past_its_end_that_is_not_critical_is_no_risk(route) -> None:
    out = route(16)  # 3e (not critical) was due on the 15th
    assert out.splitlines()[1].endswith("· on track") and "At risk" not in out


def test_past_the_target_undone_is_late(route) -> None:
    assert route(27).splitlines()[1].endswith("· late")


# --- the route's rows -------------------------------------------------------------------------------


def test_each_step_s_state_is_its_lane_s_own_and_done_only_when_merged(route, tmp_path) -> None:
    out = route(16)
    assert " done" in _row(out, "2")
    assert " running" in _row(out, "3c")  # building
    assert " built, waiting to merge" in _row(out, "3d")  # in review
    assert " not started" in _row(out, "3e") and " not started" in _row(out, "1")
    # In review is not done: "done" only when the progress row says merged.
    (tmp_path / "progress.tsv").write_text(
        PROGRESS.replace("v052-manifest\tM\tdone", "v052-manifest\tM\treview"), encoding="utf-8"
    )
    assert " done" not in _row(route(16), "2")


def test_a_step_whose_lane_is_blocked_on_it_is_blocked(route, hb) -> None:  # noqa: F811
    assert hb("beat", "rules", "blocked", "v052-index: the index service will not start").returncode == 0
    out = route(16)
    assert " blocked" in _row(out, "3c") and " blocked" not in _row(out, "B")


def test_each_row_says_its_lane_dates_what_it_waits_on_and_days_behind(route) -> None:
    out = route(16)
    row = _row(out, "B")
    assert "rules" in row and "16–18 Nov" in row and "after 3c" in row and "★" in row
    assert "1 day behind" in _row(out, "3e") and "behind" not in _row(out, "3c")  # due the 19th
    assert "★" not in _row(out, "3e")


def test_a_row_s_bar_is_its_lane_s_stages_when_they_name_its_step(route, hb) -> None:  # noqa: F811
    assert hb("stages", "rules", "v052-index", "1|done|Plan", "2|now|Feed", "3|todo|Rebuild",
              "4|todo|Drift").returncode == 0  # fmt: skip
    out = route(16)
    assert "[███░░░] running, stage 2 of 4" in _row(out, "3c")
    assert "[██████]" in _row(out, "2") and "[░░░░░░]" in _row(out, "3e")
    assert "stage" not in _row(out, "B")  # rules' stages are 3c's, not B's


# --- what waits on whom, the rulings, outside the route, finished ------------------------------------


def test_what_waits_on_the_owner_is_soonest_first_and_open_only(route, hb) -> None:  # noqa: F811
    assert hb("beat", "case", "blocked", "the fixture repository is gone").returncode == 0
    lines = _section(route(16), "WAITING ON YOU")
    text = "\n".join(lines)
    assert text.index("Tue 17 Nov · The acceptance bar's wording") < text.index("Wed 18 Nov · The search")
    assert "already made" not in text
    # What `show` says needs you comes first: under the cap it is never the line counted away.
    assert lines[1].strip() == "case is blocked: the fixture repository is gone"


def test_what_waits_on_the_orchestrator_is_soonest_first_with_its_count(route) -> None:
    lines = _section(route(16), "WAITING ON THE ORCHESTRATOR")
    assert "2 open" in lines[0]
    assert lines[1].strip().startswith("Sat 14 Nov · Scheduled runs") and "Mon 16 Nov" in lines[2]


def test_the_audit_rulings_are_one_line_with_a_bar(route) -> None:
    line = next(line for line in route(16).splitlines() if line.startswith("AUDIT RULINGS"))
    assert "1 of 3 settled" in line and "in v0.5.2: 1 yes, 1 no, 1 owner to decide" in line
    assert "[" in line


def test_the_steps_outside_the_route_are_one_line_a_lane(route) -> None:
    lines = _section(route(16), "OUTSIDE THIS ROUTE")
    body = [line.strip() for line in lines[1:]]
    assert body == ["admin: D1", "docs: sites", "platform: P8"]
    assert "v052" not in "\n".join(lines) and "L1" not in "\n".join(lines)  # on the route, or done


def test_the_finished_work_is_one_line_with_a_bar_and_a_count(route) -> None:
    line = next(line for line in route(16).splitlines() if line.startswith("FINISHED"))
    assert "3 of 11 steps merged" in line and "[" in line


# --- one screen, and the other views -----------------------------------------------------------------


def test_the_route_view_is_one_screen_on_a_busy_route(route, tmp_path) -> None:
    rows = "".join(
        f"{i}\tA step of the route with a long title that runs on and on, number {i}\tplatform\t"
        f"2026-11-{14 + i % 10:02d}\t2026-11-{15 + i % 10:02d}\t{'y' if i % 2 else 'n'}\t-\t-\n"
        for i in range(10, 23)
    )
    (tmp_path / "route.tsv").write_text(ROUTE.split("\n1\t")[0] + "\n" + rows, encoding="utf-8")
    (tmp_path / "owner_due.tsv").write_text(
        OWNER_DUE + "".join(f"orchestrator\t2026-11-{15 + i}\tAn item the orchestrator owes {i}\topen\n"
                            for i in range(10)),  # fmt: skip
        encoding="utf-8",
    )
    (tmp_path / "progress.tsv").write_text(
        PROGRESS + "".join(f"lane{i}\tS{i}\tS\ttodo\tA step outside the route\n" for i in range(12)),
        encoding="utf-8",
    )
    lines = route(16).splitlines()
    assert len(lines) <= 40, "\n".join(lines)
    assert all(len(line) <= 120 for line in lines), [line for line in lines if len(line) > 120]
    assert any("more" in line for line in lines)  # what does not fit is counted, never dropped silently


def test_without_a_route_the_default_view_is_the_overview(route, tmp_path) -> None:
    (tmp_path / "route.tsv").unlink()
    out = route(16)
    assert "VIEW 1 · FOUNDATION FEATURES" in out and "ROUTE TO" not in out


def test_the_overview_and_watch(route, hb) -> None:  # noqa: F811
    assert "VIEW 1 · FOUNDATION FEATURES" in route(16, "--overview")
    assert "VIEW 1 · FOUNDATION FEATURES" in route(16, "--full")
    watched = hb("watch", "1", OSPREY_WATCH_PASSES="1", OSPREY_NOW=_at(16), **route.env).stdout
    assert "ROUTE TO V0.5.2" in watched and "VIEW 1" not in watched


def test_a_step_whose_lane_has_posted_stages_under_way_reads_running(route, hb) -> None:  # noqa: F811
    """The owner's rule (13 Nov): from the lanes' own records, not typed by hand. Stages posted for the
    step with any done or under way read running though its progress row still says todo; stages all
    still to do do not; blocked wins; done only ever from the merged progress row."""
    assert hb("stages", "case", "v052-fixes", "1|done|Plan", "2|todo|Build").returncode == 0
    assert hb("stages", "rules", "v052-load", "1|todo|Plan", "2|todo|Load").returncode == 0
    out = route(16)
    assert " running, stage 2 of 2" in _row(out, "3e")  # progress row: todo
    assert " not started" in _row(out, "B")
    assert hb("beat", "case", "blocked", "v052-fixes: the screens will not build").returncode == 0
    assert " blocked" in _row(route(16), "3e")
    assert hb("stages", "case", "v052-fixes", "1|done|Plan", "2|done|Build").returncode == 0
    assert hb("beat", "case", "working", "v052-fixes all stages done").returncode == 0
    assert " done" not in _row(route(16), "3e") and " running" in _row(route(16), "3e")


# --- stages per (lane, step); their names under a row; built, waiting to merge (the owner, 13 Nov) ----


def test_two_steps_of_one_lane_keep_their_own_stages(route, hb) -> None:  # noqa: F811
    """A lane's post for a new step must not erase its earlier step's stages (platform's v052-standin post
    emptied steps 2 and 3a's bars): the stages are kept per lane and step."""
    assert hb("stages", "rules", "v052-index", "1|done|Plan", "2|now|Feed", "3|todo|Rebuild",
              "4|todo|Drift").returncode == 0  # fmt: skip
    assert hb("stages", "rules", "v052-load", "1|now|Plan", "2|todo|Load").returncode == 0
    out = route(16)
    assert "running, stage 2 of 4" in _row(out, "3c")
    assert "running, stage 1 of 2" in _row(out, "B")


def test_a_lane_s_stages_file_from_before_is_still_read_for_its_step(route, tmp_path) -> None:
    """The one file a lane kept before (<lane>.stages) is read for the step it names."""
    (tmp_path / "lanes" / "rules.stages").write_text(
        "step=v052-index\nat=2026-11-13T20:00:00Z\nstage=1|done|Plan\nstage=2|now|Feed\n",
        encoding="utf-8",
    )
    out = route(16)
    assert "running, stage 2 of 2" in _row(out, "3c") and "stage" not in _row(out, "B")


def _under(out: str, step: str) -> list[str]:
    lines = out.splitlines()
    at = lines.index(_row(out, step))
    under = []
    for line in lines[at + 1 :]:
        if not line.startswith("        "):
            break
        under.append(line.strip())
    return under


def test_a_running_row_lists_its_stages_by_name_and_others_stay_one_line(route, hb) -> None:  # noqa: F811
    assert hb("stages", "rules", "v052-index", "1|done|Plan", "2|now|Feed|the outbox", "3|blocked|Rebuild",
              "4|todo|Drift").returncode == 0  # fmt: skip
    assert hb("stages", "case", "v052-fixes", "1|todo|Plan").returncode == 0
    out = route(16)
    assert _under(out, "3c") == ["✅ 1. Plan", "⏳ 2. Feed · the outbox", "⛔ 3. Rebuild", "— 4. Drift"]
    assert _under(out, "3e") == []  # not started: one line
    assert _under(out, "2") == []  # done: one line
    assert _under(out, "3d") == []  # built, waiting to merge: one line


def test_review_rows_are_built_waiting_to_merge_and_the_headline_counts_them(route) -> None:
    out = route(16)
    assert "1 of 8 steps done · 1 built, waiting to merge" in out
    row = _row(out, "3d")
    assert "built, waiting to merge" in row and "running" not in row and "after A" in row
    assert "running" in _row(out, "3c")  # building is still running


def _all_running(hb, tmp_path: Path, end: str = "2026-11-20", crit: str = "n") -> None:  # noqa: F811
    rows, progress = "", PROGRESS
    for i in range(13):
        rows += f"{i}\tA step of the route, number {i}\tlane{i}\t2026-11-14\t{end}\t{crit}\t-\tlane{i}:s{i}\n"
        progress += f"lane{i}\ts{i}\tM\tbuilding\tStep {i}\n"
        assert hb("stages", f"lane{i}", f"s{i}", "1|done|Plan", "2|done|Red tests", "3|done|Build",
                  "4|now|Gates", "5|todo|Review", "6|todo|Merge").returncode == 0  # fmt: skip
    (tmp_path / "route.tsv").write_text(ROUTE.split("\n1\t")[0] + "\n" + rows, encoding="utf-8")
    (tmp_path / "progress.tsv").write_text(progress, encoding="utf-8")


def test_the_route_view_is_one_screen_with_every_step_running(route, hb, tmp_path) -> None:  # noqa: F811
    """Every step running with six stages each: the done stages fold to "✅ n done", a row's list to one
    line, and the screen still holds 40 lines of at most 120, the steps whose lists do not fit counted."""
    _all_running(hb, tmp_path)
    lines = route(16).splitlines()
    assert len(lines) <= 40, "\n".join(lines)
    assert all(len(line) <= 120 for line in lines)
    assert any(line.strip() == "✅ 3 done · ⏳ 4. Gates · — 2 to do" for line in lines), "\n".join(lines)
    # The steps whose lists do not fit are counted on a line of their own, not by another list's "+N more".
    assert "        +6 steps more running, their stages left out to keep one screen" in lines
    assert "⏳ 4. Gates" in "\n".join(lines)


def test_one_screen_with_every_step_running_on_a_day_a_step_is_at_risk(route, hb, tmp_path) -> None:  # noqa: F811
    """The at-risk line is the headline's fifth: the stages' room is one line less (hb2's review)."""
    _all_running(hb, tmp_path, end="2026-11-15", crit="y")
    lines = route(16).splitlines()
    assert any(line.startswith("  At risk:") for line in lines)
    assert len(lines) <= 40, "\n".join(lines)
    assert any(line.startswith("        +") and "more running" in line for line in lines)


def test_the_owner_s_fold_the_done_on_one_line_and_the_rest_in_full(route, hb) -> None:  # noqa: F811
    """When every list in full would not fit but folding the done stages does, that is the fold shown
    (the owner, 13 Nov): "✅ n done", then each stage still under way, blocked or to do by name."""
    six = ("1|done|Plan", "2|done|Red tests", "3|done|Build", "4|now|Gates", "5|todo|Review", "6|todo|Merge")
    for lane, step in (("rules", "v052-index"), ("case", "v052-fixes"), ("rules", "v052-load")):
        assert hb("stages", lane, step, *six).returncode == 0
    out = route(16)
    assert len(out.splitlines()) <= 40, out
    for step in ("3c", "3e", "B"):
        assert _under(out, step) == ["✅ 3 done", "⏳ 4. Gates", "— 5. Review", "— 6. Merge"], out


def test_a_step_with_spaces_a_slash_and_an_accent_is_found_where_it_was_written(
    route, hb, tmp_path  # noqa: F811
) -> None:
    """The writer (bash, here under LC_ALL=C, as launchd or a bare ssh runs it) and the views' one reader
    (perl) name the file alike, byte by byte (hb2's review)."""
    step = "ADR-147 Am 3/café"
    (tmp_path / "route.tsv").write_text(ROUTE.replace("rules:v052-index", f"rules:{step}"), encoding="utf-8")
    (tmp_path / "progress.tsv").write_text(PROGRESS.replace("v052-index", step), encoding="utf-8")
    assert hb("stages", "rules", step, "1|done|Plan", "2|now|Feed", LC_ALL="C").returncode == 0
    out = route(16)
    assert "running, stage 2 of 2" in _row(out, "3c")
    assert _under(out, "3c") == ["✅ 1. Plan", "⏳ 2. Feed"]


# --- done from git, ready from the route (the owner, 14 November 2026) --------------------------------
# Twice in a day the route showed steps building after they were on main, and later steps kept their typed dates
# after the steps before them finished, both from hand-typed rows. A row's step is done when the branch its sixth
# column names has its head on main through a merge, or merger/LANDED.md says it landed `done`; a step not started
# whose `after` steps are all done is ready, with the days it could gain. Rule 15: the repository is built by real
# git, its merges `--no-ff` as the merger's are, and LANDED.md's lines are in the shapes it holds today.

def _repo(base: Path) -> Path:
    """main, with lane/rules-index merged by a merge; lane/rules-load cut from main with nothing of its own;
    lane/case-fixes with a commit main lacks; lane/rules-v052-index, the name the lane-step convention would
    give 3c, merged too (a part merged ahead, as step 4's plan was)."""
    env = {**os.environ, "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.invalid"}  # fmt: skip
    repo = base / "repo"
    repo.mkdir()

    def git(*a: str) -> None:
        subprocess.run(["git", *a], cwd=repo, env=env, check=True, capture_output=True, text=True)

    git("init", "-q", "-b", "main")
    git("commit", "-q", "--allow-empty", "-m", "start")
    for branch in ("lane/rules-index", "lane/rules-v052-index"):
        git("checkout", "-q", "-b", branch)
        git("commit", "-q", "--allow-empty", "-m", f"work on {branch}")
        git("checkout", "-q", "main")
        git("merge", "-q", "--no-ff", branch, "-m", f"merge: {branch}")
    git("branch", "lane/rules-load")
    git("checkout", "-q", "-b", "lane/case-fixes")
    git("commit", "-q", "--allow-empty", "-m", "fixes not yet merged")
    git("checkout", "-q", "main")
    return repo


@pytest.fixture
def gitroute(route, hb, tmp_path: Path):  # noqa: F811
    repo = _repo(tmp_path)

    def view(day: int = 16, progress: str = PROGRESS, landed: str | None = None) -> str:
        (tmp_path / "progress.tsv").write_text(progress, encoding="utf-8")
        if landed is not None:
            (tmp_path / "merger").mkdir(exist_ok=True)
            (tmp_path / "merger" / "LANDED.md").write_text(landed, encoding="utf-8")
        out = hb(OSPREY_NOW=_at(day), OSPREY_REPO=str(repo), **route.env)
        assert out.returncode == 0, out.stderr[-800:]
        return out.stdout

    return view


def _branch(progress: str, step: str, branch: str) -> str:
    row = next(line for line in progress.splitlines() if f"\t{step}\t" in line)
    return progress.replace(row, f"{row}\t{branch}")


def test_a_row_typed_building_whose_branch_is_on_main_by_a_merge_shows_done(gitroute) -> None:
    out = gitroute(16, _branch(PROGRESS, "v052-index", "lane/rules-index"))
    assert " done" in _row(out, "3c") and "running" not in _row(out, "3c")
    assert "2 of 8 steps done" in out  # the headline counts it
    assert "3 of 11" not in out and "4 of 11 steps merged" in out  # and so does the finished line


def test_a_branch_not_on_main_by_a_merge_keeps_the_row_s_word(gitroute) -> None:
    # Cut from main with nothing of its own: an ancestor of main, but on its first-parent line, so not done.
    out = gitroute(16, _branch(PROGRESS, "v052-load", "lane/rules-load"))
    assert " not started" in _row(out, "B")
    # A commit main lacks; a branch no repository has; a dash: the typed word stands.
    out = gitroute(16, _branch(_branch(PROGRESS, "v052-fixes", "lane/case-fixes"), "v052-load", "lane/gone"))
    assert " not started" in _row(out, "3e") and " not started" in _row(out, "B")
    assert " running" in _row(gitroute(16, _branch(PROGRESS, "v052-index", "-")), "3c")


def test_a_row_naming_no_branch_is_never_given_one_by_its_name(gitroute) -> None:
    """lane/rules-v052-index is the lane-step convention's name for 3c and is on main by a merge, as step 4's
    plan, step 5's drafts and step 6's run sheet were on 14 November while their steps were not done."""
    assert " running" in _row(gitroute(16), "3c")


def test_a_landed_line_counts_only_when_it_says_the_step_is_done(gitroute) -> None:
    head = "# Merges the merger prepared\n\nda162e6 b6570fd case L3.H2\n0dcf45d 4e50d89\n"
    # Today's forms: two commits alone, and a part named by its step. Neither is the step done.
    out = gitroute(16, landed=head + "8d6a898 a386fe3 rules v052-index part one (v0.5.1)\n"
                   "4283b91 3bd66ec+bcca270 rules v052-load\n")  # fmt: skip
    assert " running" in _row(out, "3c") and " not started" in _row(out, "B")
    out = gitroute(16, landed=head + "aca0591 2916cf6 rules v052-index done (step 3c)\n")
    assert " done" in _row(out, "3c")
    assert " done" not in _row(out, "B")  # a line for one lane's step is not another's (B, after 3c, is ready)


def test_a_step_whose_after_steps_are_all_done_shows_ready_with_the_days(gitroute) -> None:
    """B is after 3c and typed to start on the 16th; on the 14th, 3c done, it is ready two days ahead. Step 4
    is after 3c, 3d and B: 3d is built, waiting to merge, so 4 is not ready."""
    out = gitroute(14, _branch(PROGRESS, "v052-index", "lane/rules-index"))
    assert " ready, 2 days ahead of its start" in _row(out, "B") and "after 3c" not in _row(out, "B")
    assert " not started" in _row(out, "4") and "after 3c,3d,B" in _row(out, "4")
    assert "· 1 ready to start" in out
    # On its typed start or after it, ready alone.
    assert _row(gitroute(16, _branch(PROGRESS, "v052-index", "lane/rules-index")), "B").count("ready ·") == 1


def test_ready_needs_every_after_step_done_and_a_route_step_to_name(gitroute, tmp_path) -> None:
    # 3d is after A, which is no step of the route: never ready, though 3d is built here.
    progress = _branch(PROGRESS, "v052-index", "lane/rules-index").replace(
        "v052-search\tL\treview", "v052-search\tL\ttodo")
    assert "ready" not in _row(gitroute(14, progress), "3d")
    # A step under way is not ready: it has started.
    progress = _branch(PROGRESS, "v052-index", "lane/rules-index").replace(
        "v052-load\tM\ttodo", "v052-load\tM\tbuilding")
    assert " running" in _row(gitroute(14, progress), "B")
