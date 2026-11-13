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
    assert " running" in _row(out, "3c") and " running" in _row(out, "3d")  # building, in review
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
