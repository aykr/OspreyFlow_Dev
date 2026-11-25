"""A merge refused by a test that is not one of the part's own files, or by a test the backlog lists as a known flake,
is the conductor's to rerun, not a stop for the owner (the owner, 23 November 2026).

PL14a, verified, was refused by the gate on test_pl4d3d_declared_units.py (backlog row 21, a test that depends on
chance), a file PL14a never touched. The board showed it "stopped" with "resume.py send-back returns it to the
builder" and counted it as waiting for the owner. Now: "refused by another test, with the conductor to rerun", the part
verified, waiting for the conductor. A failing test in the part's own files stays a stop, as before, unless the backlog
names it a known flake; a gate record naming no test file, or none at all, stays a stop. Once, not always (the
owner's answer, 24 November 2026): a second refusal of the same tip is a stop for the owner, since AD2 on 18 November
was refused by test_admin_sections.py, not its own file, and the fault was its own (test_send_back.py replays it).
"""
from __future__ import annotations

import json

from test_dashboard_paper import V062, part, set_state, status
from test_gates import built, verified, world  # noqa: F401  (world is a fixture)
from test_scan_rows import on_main

GLASS = "OspreyFlow_Build/tests/glass_trees/test_pl4d3d_declared_units.py"
GLASS_T = f"{GLASS}::test_two_builds_in_one_tree_collide_and_two_builds_of_build_to_do_not"
OWN = "OspreyFlow_Build/tests/test_s1_own.py"                    # the part's own test (ready adds it)
LIVE = "tests/test_worker_isolation_live.py"
BACKLOG = f"{V062}/BACKLOG.md"
FLAKE_ROW = (f"- **Row 22: `{LIVE}::test_without_the_plugin_each_worker_sees_both_in_every_store_the_red` is a live "
             "timing race.** A flake: it stops no merge.\n")


def refused_by(w, tip, *files, times=1):
    """The gate's refusal as merge_slice.refuse_to_builder writes it, naming these files' tests; refusals.tsv gets one
    row a refusal, as merge_slice.record_refusal writes it."""
    rec = w["data"] / "records/S1"
    tsv = w["data"] / "refusals.tsv"
    if not tsv.exists():
        tsv.write_text("at\tslice\ttip\tcause\n")
    with tsv.open("a") as fh:
        for _ in range(times):
            fh.write(f"2026-11-23T20:37:21Z\tS1\t{tip}\tthe full gate: test\n")
    (rec / f"verify-gate-{tip}.json").write_text(json.dumps(
        {"slice": "S1", "commit": tip, "verdict": "findings", "passes": [], "at": "2026-11-23T20:37:21Z",
         "findings": [{"file": f, "what": f"The merge gate's full run failed ../{f}::test_x: E assert []",
                       "evidence": "the merge log"} for f in files],
         "note": "written by merge_slice.py: today's full gate was red on the merge result; not a verifier session"}))
    set_state(w, phase="refused", refused_for="gate", refused_tests=len(files), refused_at="2026-11-23T20:37:21Z",
              note=f"refused by the gate: {len(files)} tests", last_merge_refusal="2026-11-23T20:37:21Z",
              last_refusal_cause="the full gate: test")


def ready(w):
    """S1 verified, its branch carrying its own test and a change to the live test the backlog calls a flake."""
    wt, tip = built(w, extra={OWN: "def test_s1():\n    assert True\n", f"OspreyFlow_Build/{LIVE}": "# S1 touched it\n"})
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    return wt, tip


def test_pl14a_refused_by_a_test_not_its_own_is_with_the_conductor_to_rerun(world):
    w = world
    _, tip = ready(w)
    refused_by(w, tip, GLASS)
    _, body = status(w)
    entry, mine = body["builds"]["CO1"], part(body, "S1")
    assert entry["state"] != "stopped", entry
    assert "refused by another test" in entry["note"] and "with the conductor to rerun" in entry["note"], entry
    assert "send-back" not in entry["note"] and "test_pl4d3d_declared_units.py" in entry["note"], entry
    assert mine["state"] == "verified" and mine["waiting_for"] == "the conductor to rerun", mine   # not "you"


def test_a_known_flake_in_the_parts_own_files_is_with_the_conductor_to_rerun(world):
    w = world
    on_main(w, {BACKLOG: "# the backlog\n\n## 23 November 2026: flakes\n\n" + FLAKE_ROW}, "docs: the backlog's flakes")
    _, tip = ready(w)
    refused_by(w, tip, f"OspreyFlow_Build/{LIVE}")
    _, body = status(w)
    entry, mine = body["builds"]["CO1"], part(body, "S1")
    assert entry["state"] != "stopped" and "with the conductor to rerun" in entry["note"], entry
    assert "known flake (backlog row 22)" in entry["note"], entry
    assert mine["state"] == "verified" and mine["waiting_for"] == "the conductor to rerun", mine


def test_a_failing_test_in_the_parts_own_files_is_still_a_stop_for_you(world):
    w = world
    _, tip = ready(w)
    refused_by(w, tip, OWN)
    _, body = status(w)
    assert body["builds"]["CO1"]["state"] == "stopped" and "send-back" in body["builds"]["CO1"]["note"]
    assert part(body, "S1")["state"] == "stopped" and part(body, "S1")["waiting_for"] == "you"


def test_one_own_test_beside_another_test_is_still_a_stop(world):
    w = world
    _, tip = ready(w)
    refused_by(w, tip, GLASS, OWN)
    _, body = status(w)
    assert body["builds"]["CO1"]["state"] == "stopped" and part(body, "S1")["waiting_for"] == "you"


def test_a_backlog_row_that_names_a_test_but_not_as_a_flake_does_not_make_it_one(world):
    w = world
    on_main(w, {BACKLOG: f"# the backlog\n\n- **Row 9: `{OWN}` checks the wrong field.** A fix is owed.\n"},
            "docs: a backlog row")
    _, tip = ready(w)
    refused_by(w, tip, OWN)
    _, body = status(w)
    assert body["builds"]["CO1"]["state"] == "stopped" and part(body, "S1")["waiting_for"] == "you"


def test_a_gate_record_naming_no_test_file_is_still_a_stop(world):
    w = world
    _, tip = ready(w)
    refused_by(w, tip, "")
    _, body = status(w)
    assert body["builds"]["CO1"]["state"] == "stopped" and part(body, "S1")["waiting_for"] == "you"


def test_a_second_refusal_of_the_same_tip_is_a_stop_for_you(world):
    """AD2's shape: a test not its own, red again on the rerun; the fault is the part's, and the owner's to send back."""
    w = world
    _, tip = ready(w)
    refused_by(w, tip, GLASS, times=2)
    _, body = status(w)
    assert body["builds"]["CO1"]["state"] == "stopped" and "send-back" in body["builds"]["CO1"]["note"]
    assert part(body, "S1")["state"] == "stopped" and part(body, "S1")["waiting_for"] == "you"


def test_a_refusal_of_an_earlier_tip_does_not_count(world):
    w = world
    _, tip = ready(w)
    (w["data"] / "refusals.tsv").write_text("at\tslice\ttip\tcause\n"
                                            f"2026-11-22T10:00:00Z\tS1\t{'0' * 40}\tthe full gate: test\n")
    refused_by(w, tip, GLASS)
    _, body = status(w)
    assert part(body, "S1")["waiting_for"] == "the conductor to rerun", part(body, "S1")
