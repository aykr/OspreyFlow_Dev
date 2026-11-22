"""Item 5 of the owner's file 004 (22 November 2026): the board. For each waiting slice, its server result (running,
green, red and the test, none), and for a merge, which targets were taken from the server; with the shadow's tally.
The board shows what the note says, as a display only: the merge reads the runner's own result (items 1 to 4).
"""
from __future__ import annotations

import json

from test_gates import sh, world  # noqa: F401  (world is a fixture)
from test_server_counts import gate_plan, green, setup
from test_server_slot import FAILING, RID

V062 = "OspreyFlow_Build/process/lanes/v062"
STATUS = "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/status.js"


def board(w):
    b = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False)
    status = json.loads((w["repo"] / STATUS).read_text().split("window.OSPREY_STATUS = ", 1)[1].rstrip().rstrip(";"))
    line = next((ln for ln in b.stdout.splitlines() if ln.strip().startswith("S1 ") and "server" in ln), "")
    return b, status["builds"]["CO1"], line


def write_note(w, tip, headline, failing=""):
    d = w["repo"] / V062 / "early_warning"
    d.mkdir(parents=True, exist_ok=True)
    body = f"# Early warning: S1 at {tip[:8]}: {headline}\n\n- Run id: `{RID}`\n"
    if failing:
        body += f"\n## Failing (rerun each on the Mac before sending the slice back)\n\n- make target `test`\n  - test `{failing}`\n"
    (d / f"S1-{tip[:8]}.md").write_text(body)


def test_a_waiting_slice_shows_its_server_result_green_red_running_or_none(world):
    w = world
    wt, tip = setup(w, on=False)
    write_note(w, tip, "GREEN")
    b, co1, line = board(w)
    assert co1["server"]["state"] == "green" and co1["server"]["run_id"] == RID, co1
    assert "server green" in line and "server_counts is off" in b.stdout, b.stdout
    write_note(w, tip, "RED", FAILING)
    b, co1, line = board(w)
    assert co1["server"]["state"] == "red" and co1["server"]["test"] == FAILING, co1
    assert f"server red: {FAILING}" in line and "merge_slice.py server-rerun S1" in line, line
    run = w["data"] / "early-warning" / "running" / f"S1-{tip[:8]}.json"
    run.parent.mkdir(parents=True)
    run.write_text("{}")
    b, co1, line = board(w)
    assert co1["server"]["state"] == "running" and "server running" in line, (co1, line)
    run.unlink()
    (w["repo"] / V062 / "early_warning" / f"S1-{tip[:8]}.md").unlink()
    b, co1, line = board(w)
    assert co1["server"]["state"] == "none" and "server none" in line, (co1, line)


def test_a_slice_to_run_again_and_a_rerun_on_the_mac_are_shown(world):
    w = world
    wt, tip = setup(w, on=False)
    write_note(w, tip, "RED", FAILING)
    (w["data"] / "records/S1/server-again.json").write_text(json.dumps(
        {"slice": "S1", "tip": tip, "run_id": RID, "because": "S9, below it in the server's stack, was refused at merge"}))
    (w["data"] / f"records/S1/server-rerun-{RID}.json").write_text(json.dumps({"tip": tip, "result": "green"}))
    b, co1, line = board(w)
    assert co1["server"]["rerun"] == "green" and "rerun on the Mac: green" in line, line
    assert "run it on the server again (S9, below it" in line, line


def test_a_merge_shows_which_targets_it_took_from_the_server_and_the_shadow_tally(world):
    w = world
    wt, tip = setup(w, on=True)
    green(w, tip)
    p, plan, server = gate_plan(w)
    assert p.returncode == 0, p.stdout + p.stderr
    b, co1, line = board(w)
    assert co1["state"] == "done" and co1["server"]["counted"] is True, co1
    assert co1["server"]["taken"] == ["lint-tools", "opentofu-check", "core:lint", "core:typecheck", "test"], co1
    assert "server counted: 5 targets taken" in line and "the Mac ran client-name-check" in line, line
    assert "server shadow: 0 agree, 0 differ, 0 no comparison, 1 counted" in b.stdout, b.stdout
