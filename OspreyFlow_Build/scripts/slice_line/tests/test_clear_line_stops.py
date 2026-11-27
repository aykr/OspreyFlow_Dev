"""A stop clears without the owner's line when its cause is the line's and not the part's (his file 012, A2,
23 November 2026).

A standing permission in standing.tsv: `clear-line-stops per-day <N> <date>`. Every clearance the line makes itself
(resume.py self-clear: causes (a) and (b) of LINE_FIXES_5_BRIEF.md, A, and now (c)) is made on it, within a daily
budget, each use logged in owner-changes.tsv and self-clears.tsv and shown on the board, the red stop's own lines kept in
the clearance's record. Cause (c): the red stop is the scan map's alone (a new test that walks a folder with no row,
which a builder cannot add) and main now has the row, written since by the conductor: on 22 and 23 November five of the
owner's clear-stop lines followed such a row (IS5a, DC1c, SE6b, AD1a, PL12b). Never: with the permission off or its
budget spent; a red in the part's own acceptance or its own tests (its acceptance, its uncommitted work, the lint of its
own files, a failing test it wrote or changed); a slice the owner has parked; and, as before, a key, a credential or a
security rule, the eighth round, a verifier's findings, a refreeze.
"""
from __future__ import annotations

import json

import pytest

from test_gates import TODAY, sh, stop_gate, world  # noqa: F401  (world is a fixture)
from test_round_after_refusal import line_now
from test_resume import V062, changes, resume, said_refused, snapshot, state
from test_self_clear import (MAIN_ID, PERMISSION, a_slice_red_on_its_own, permission, clears, commit_main, layout_slice,
                             red_on_mains_check, red_six_times, red_stop, unchanged)
from test_stop_lint import WALKER, branch, tools

assert permission  # the standing line on for every case (test_self_clear's autouse fixture), unless a case says

ACCEPT = "accept-test-gaps\tfrom-round\t3\t2026-11-19\n"
ROWS = f"{V062}/scan_rows/S1.tsv"
LINE_MAP = "OspreyFlow_Build/scripts/slice_line/scan_map.tsv"


def standing(w, body):
    f = w["repo"] / V062 / "standing.tsv"
    if body is None:
        f.unlink(missing_ok=True)
    else:
        f.write_text(body)


def logged(w, at, slice_id, action, detail):
    f = w["data"] / "owner-changes.tsv"
    if not f.exists():
        f.write_text("at\tslice\taction\tdetail\n")
    with f.open("a") as fh:
        fh.write(f"{at}\t{slice_id}\t{action}\t{detail}\n")


def heads(w, wt):
    return sh("git rev-parse HEAD", wt).stdout, sh("git rev-parse main", w["repo"]).stdout


def board(w):
    return sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False).stdout


# ------------------------------------------------------------------ the permission and its budget


@pytest.mark.parametrize("body", [None, "", ACCEPT, f"clear-line-stops\tper-day\t11\t{TODAY}\n", PERMISSION + PERMISSION,
                                  PERMISSION + f"clear-line-stop\tper-day\t10\t{TODAY}\n"],
                         ids=["missing", "empty", "the-accept-alone", "more-than-ten", "twice", "beside-a-misspelt-line"])
def test_clear_line_stops_off_or_unclear_clears_nothing(world, body):
    w = world
    wt = red_on_mains_check(w)                                     # cause (a) holds
    standing(w, body)
    before, at = snapshot(w), heads(w, wt)
    p = resume(w, "S1", "self-clear")
    assert said_refused(p, "standing permission (clear-line-stops)", "owner's line"), p.stdout + p.stderr
    unchanged(w, wt, before, at)
    assert changes(w) == []


def test_clear_line_stops_at_its_budget_clears_no_more_today_and_the_board_says_so(world):
    w = world
    wt = red_on_mains_check(w)
    standing(w, f"clear-line-stops\tper-day\t1\t{TODAY}\n")
    logged(w, "2020-01-01T00:00:00Z", "S8", "self-clear", "standing.tsv clear-line-stops: an old day's use")
    logged(w, line_now(), "S9", "self-clear", "standing.tsv clear-line-stops: today's one use")
    before, at = snapshot(w), heads(w, wt)
    p = resume(w, "S1", "self-clear")
    assert said_refused(p, "budget"), p.stdout + p.stderr
    unchanged(w, wt, before, at)
    assert "standing permission clear-line-stops: AT ITS BUDGET, 1 of 1 used today" in board(w)
    standing(w, f"clear-line-stops\tper-day\t2\t{TODAY}\n")     # the old day's use is not counted
    p = resume(w, "S1", "self-clear")
    assert p.returncode == 0 and "cause a" in p.stdout and "use 2 of 2 today" in p.stdout, p.stdout + p.stderr


def test_clear_line_stops_each_use_is_logged_counted_and_keeps_the_red_stop(world):
    w = world
    wt = red_on_mains_check(w)
    red = json.loads((w["data"] / "records/S1/red_stop.json").read_text())
    p = resume(w, "S1", "self-clear")
    assert p.returncode == 0, p.stdout + p.stderr
    (row,) = [r for r in changes(w) if r[1] == "S1"]
    assert row[2] == "self-clear" and row[3].startswith("standing.tsv clear-line-stops: main ") and "use 1 of 10" in row[3]
    (rec,) = list((w["data"] / "records/S1").glob("self-clear-*.json"))
    assert json.loads(rec.read_text())["red_stop"] == red          # what was red, kept for the owner to judge later
    assert "standing permission clear-line-stops: on, 1 of 10 used today" in board(w)


# ------------------------------------------------------------------ never the part's own red


def own_test_red(w):
    wt = layout_slice(w)
    (wt / "tests/test_own.py").write_text("def test_own():\n    assert False\n")
    sh("git add -A tests && git commit -qm 'test: its own test'", wt, w["env"])
    red_stop(w, wt, "RED: checks (exit 1): pytest tests/test_layout.py tests/test_own.py\n"
                    "FAILED tests/test_own.py::test_own - AssertionError")
    return wt


@pytest.mark.parametrize("how", ["acceptance", "own-test", "own-lint", "uncommitted"])
def test_clear_line_stops_never_clears_a_red_in_the_parts_own_acceptance_or_tests(world, how):
    """Main has moved under each (cause (a) would hold on its own terms): the red is still the part's own."""
    w = world
    if how == "acceptance":
        wt = a_slice_red_on_its_own(w)
    elif how == "own-test":
        wt = own_test_red(w)
    else:
        wt = layout_slice(w)
        red_stop(w, wt, "RED: ruff check (exit 1) on the files this branch changed: ruff check\nF401 unused import"
                 if how == "own-lint" else "RED: uncommitted changes (commit them to the slice branch):\n M x.py")
    commit_main(w, {f"{V062}/notes.md": "main moved\n"})
    before, at = snapshot(w), heads(w, wt)
    p = resume(w, "S1", "self-clear")
    assert said_refused(p, "is its own", "never clears a red in the slice's own"), p.stdout + p.stderr
    unchanged(w, wt, before, at)


def test_clear_line_stops_never_for_a_slice_the_owner_parked(world):
    w = world
    wt = red_on_mains_check(w)
    (w["repo"] / V062 / "resume.tsv").write_text(f"S1\tpark\t{TODAY}\n")
    before, at = snapshot(w), heads(w, wt)
    p = resume(w, "S1", "self-clear")
    assert said_refused(p, "parked"), p.stdout + p.stderr
    unchanged(w, wt, before, at)


# ------------------------------------------------------------------ cause (c): the row the conductor has since written


def scan_red_slice(w):
    """S1 adds a test that walks a folder, with no row anywhere: the Stop hook's scan-map red, six times."""
    tools(w)
    wt = branch(w, {"OspreyFlow_Build/tests/test_walker.py": WALKER})
    red_six_times(w, wt)
    last = json.loads((w["data"] / "records/S1/red_stop.json").read_text())["last"]
    assert len(last) == 1 and last[0].startswith("RED: scan map:") and "tests/test_walker.py" in last[0], last
    return wt


@pytest.mark.parametrize("where", ["scan_rows", "scan_map"], ids=["the-slices-waiting-rows", "mains-scan-map"])
def test_clear_line_stops_cause_c_a_scan_map_red_is_cleared_once_main_has_the_row(world, where):
    w = world
    wt = scan_red_slice(w)
    before, at = snapshot(w), heads(w, wt)
    p = resume(w, "S1", "self-clear")                              # no row yet: the conductor has not written it
    assert said_refused(p, "not (c): main still has no scan-map row for tests/test_walker.py"), p.stdout + p.stderr
    unchanged(w, wt, before, at)
    row = "tests/test_walker.py\t-\twalks its own folder of pages only\n"
    m = w["repo"] / LINE_MAP
    m.write_text(m.read_text() + row)                              # written in the checkout, not yet on main: no row
    p = resume(w, "S1", "self-clear")
    assert said_refused(p, "not (c): main still has no scan-map row"), p.stdout + p.stderr
    unchanged(w, wt, before, at)
    sh(["git", "checkout", "--", LINE_MAP], w["repo"])
    if where == "scan_rows":
        commit_main(w, {ROWS: row}, "docs: S1's scan row")
    else:                                                          # a merge's row, on main before any reinstall
        m = w["repo"] / LINE_MAP
        commit_main(w, {LINE_MAP: m.read_text() + row}, "merge: a slice's scan row")
    round0 = state(w)["round"]
    p = resume(w, "S1", "self-clear")
    assert p.returncode == 0 and "cleared by the line (cause c)" in p.stdout, p.stdout + p.stderr
    assert "tests/test_walker.py" in p.stdout and "use 1 of 10 today" in p.stdout, p.stdout
    st = state(w)
    assert st["phase"] == "building" and st["round"] == round0, st
    assert not (w["data"] / "records/S1/red_stop.json").exists()
    assert [(r["stop"], r["cause"]) for r in clears(w)] == [("red", "c")]
    assert [r[3].split(":", 1)[0] for r in changes(w) if r[1] == "S1"] == ["standing.tsv clear-line-stops"]
    assert sh("git rev-parse HEAD", wt).stdout == at[0]            # nothing merged into the branch, nothing refrozen
    assert stop_gate(w, wt) is None                                 # the builder's next stop: green


def test_clear_line_stops_cause_c_never_beside_another_red(world):
    w = world
    wt = scan_red_slice(w)
    red = json.loads((w["data"] / "records/S1/red_stop.json").read_text())
    red_stop(w, wt, red["last"][0], f"RED: checks (exit 1): true\nFAILED {MAIN_ID} - AssertionError")
    commit_main(w, {ROWS: "tests/test_walker.py\t-\twalks its own folder of pages only\n"}, "docs: S1's scan row")
    p = resume(w, "S1", "self-clear")
    assert "cause c" not in p.stdout and all(r["cause"] != "c" for r in clears(w)), p.stdout + p.stderr  # (a) may hold
