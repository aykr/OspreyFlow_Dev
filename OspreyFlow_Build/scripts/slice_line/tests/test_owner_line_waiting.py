"""The board shows "the owner's line is in" as its own state (LINE_FIXES_5_BRIEF.md, 7).

Between the owner adding a line to resume.tsv and the conductor applying it, the board showed the slice as "stopped" or
"refused by the gate", and the dashboard could not tell a stop waiting for the owner from one he had answered. Now a slice
with an unapplied line that answers its stop shows "the owner's line is in: <action> (<date>), waiting to be applied" (the
board's row, the status entry's note and its `owner_line`); it goes when the action is applied (its use logged), and a
line for an action that does not answer the stop (resume.py would refuse it) is not shown.
"""
from __future__ import annotations

import json

import pytest

from test_gates import sh, world  # noqa: F401  (world is a fixture)
from test_resume import TODAY, at_limit, owner_line, red_stopped, resume, set_state

STATUS = "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/status.js"


def board(w):
    p = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"])
    row = next(ln for ln in p.stdout.splitlines() if ln.startswith("S1 "))
    body = json.loads((w["repo"] / STATUS).read_text().split("window.OSPREY_STATUS = ", 1)[1].rstrip().rstrip(";"))
    return row, body["builds"].get("CO1", {})


def waiting(row, entry, action):
    return (f"owner's line in: {action}" in row and entry.get("state") == "stopped"
            and entry.get("note") == f"the owner's line is in: {action} ({TODAY}), waiting to be applied"
            and entry.get("owner_line", {}).get("action") == action)


def test_an_unapplied_line_shows_the_state_and_applied_it_goes(world):
    w = world
    at_limit(w)
    row, entry = board(w)
    assert "stopped" in row and "owner_line" not in entry, (row, entry)
    owner_line(w, f"S1\tadd-round\t{TODAY}")
    row, entry = board(w)
    assert waiting(row, entry, "add-round"), (row, entry)
    assert resume(w, "S1", "add-round").returncode == 0
    row, entry = board(w)
    assert "owner's line" not in row and "owner_line" not in entry, (row, entry)
    set_state(w, phase="stopped", note="findings again: allow another round?")  # stopped at the new limit
    row, entry = board(w)
    assert "owner's line" not in row and "owner_line" not in entry, (row, entry)  # that line is used


@pytest.mark.parametrize("stop,action,shown", [
    ("findings", "accept", True), ("findings", "clear-stop", False),
    ("red", "clear-stop", True), ("red", "add-round", False), ("red", "accept", False),
    ("refused", "add-round", True), ("refused", "clear-stop", False),
], ids=lambda x: str(x))
def test_only_a_line_that_answers_the_stop_shows_it(world, stop, action, shown):
    w = world
    if stop == "red":
        red_stopped(w)
    else:
        at_limit(w)
        if stop == "refused":
            set_state(w, phase="refused", refused_for="gate", refused_tests=2)
    owner_line(w, f"S1\t{action}\t{TODAY}")
    row, entry = board(w)
    assert waiting(row, entry, action) is shown, (row, entry)
    if not shown:
        assert entry.get("state") == "stopped" and "owner's line" not in entry.get("note", ""), entry


def test_a_move_seat_line_answers_any_stop(world):
    w = world
    red_stopped(w)
    owner_line(w, f"S1\tmove-seat\tbuilder\tsol\t{TODAY}")
    row, entry = board(w)
    assert waiting(row, entry, "move-seat builder sol"), (row, entry)


def test_a_slice_not_stopped_never_shows_it(world):
    w = world
    at_limit(w)
    set_state(w, phase="building")
    owner_line(w, f"S1\tadd-round\t{TODAY}")
    row, entry = board(w)
    assert "owner's line" not in row and "owner_line" not in entry, (row, entry)


def day(offset):
    import time
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() + offset * 86400))


@pytest.mark.parametrize("offset", [-1, -30])
def test_a_line_whose_date_has_passed_is_not_shown_since_resume_never_applies_it(world, offset):
    """The conductor, 25 November 2026: the board showed an unused owner's line whatever its date; resume.py applies a
    line on its own day only (UTC), so a line whose date has passed is waiting for nothing."""
    w = world
    at_limit(w)
    owner_line(w, f"S1\tadd-round\t{day(offset)}")
    row, entry = board(w)
    assert "owner's line" not in row and "owner_line" not in entry, (row, entry)
    assert resume(w, "S1", "add-round").returncode != 0                     # and resume.py does refuse it


def test_beside_a_past_line_todays_line_is_the_one_shown(world):
    w = world
    at_limit(w)
    owner_line(w, f"S1\taccept\t{day(-1)}", f"S1\tadd-round\t{TODAY}")
    row, entry = board(w)
    assert waiting(row, entry, "add-round"), (row, entry)
