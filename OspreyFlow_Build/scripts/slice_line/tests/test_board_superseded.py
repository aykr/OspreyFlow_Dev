"""D268 (the owner's ruling, 26 November 2026, on 58's question): the board follows a superseded red. When a newer
run of a part at the same tip has passed (server_gate.newer_green, which the merge already reads: 58), the board shows
the server green and names the red it superseded. It no longer tells the conductor to rerun the red on the Mac.

The board asks the server only when the early warning's own log records a newer run of the part at this tip. A newer
red, a newer run with no verdict, or a newer green at another tip leaves the board's red as it was."""
from __future__ import annotations

import pytest

from test_dashboard_paper import part, status
from test_gates import world  # noqa: F401  (world is a fixture)
from test_server_rerun_rm1a import THIRD, red_then, red_then_runs
from test_server_slot import OTHER, RID


def test_the_board_shows_a_red_superseded_by_a_newer_green_as_green(world):
    tip = red_then(world, "pass")
    n = world["repo"] / "OspreyFlow_Build/process/lanes/v062/early_warning" / f"S1-{tip[:8]}.md"
    n.write_text(n.read_text() + "  - test `OspreyFlow_Build/tests/test_x.py::test_y`\n")   # the red's first test
    _, body = status(world)
    srv = part(body, "S1")["server"]
    assert srv["state"] == "green" and srv["superseded_red"] == RID and srv["run_id"] == OTHER, srv
    assert "server-rerun" not in srv["said"] and f"supersedes the red of run {RID}" in srv["said"], srv
    assert "test" not in srv and srv["said"].startswith("server green (run "), srv       # the red's test not shown


@pytest.mark.parametrize("newer", ["error", "another-tip", "a-newer-red-after-it"])
def test_the_board_keeps_a_red_nothing_newer_has_passed(world, newer):
    if newer == "error":
        red_then(world, "error")
    elif newer == "another-tip":
        red_then(world, "pass", newer_tip="f" * 40)
    else:
        red_then_runs(world, (OTHER, "pass"), (THIRD, "fail"))
    _, body = status(world)
    srv = part(body, "S1")["server"]
    assert srv["state"] == "red" and "superseded_red" not in srv, srv
    assert "rerun it on the Mac: merge_slice.py server-rerun S1" in srv["said"], srv
