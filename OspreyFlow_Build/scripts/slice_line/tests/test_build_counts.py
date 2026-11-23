"""The board writes, for each build, how many of its slices have merged and how many are cut (LINE_FIXES_5_BRIEF.md, C),
so the dashboard shows PL4 as "9 of 12" and not as nothing. "Cut" is the build's rows in slices.tsv on main (a row added
later raises it); "merged" is its slices the board shows done, from merge records it accepts. Both go into the status
file the board already writes: on each build's entry (`slices`, `slices_merged`, `slices_cut`) and, for every build of
the plan with rows, in `build_slices`, so a build with none merged says "0 of N" and is never left out.
"""
from __future__ import annotations

import json

from test_gates import sh, world  # noqa: F401  (world is a fixture)

V062 = "OspreyFlow_Build/process/lanes/v062"
STATUS = "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/status.js"


def rows(w, *extra):
    """slices.tsv on main with these rows added (id, build), each with S1's commands."""
    tsv = w["repo"] / V062 / "slices.tsv"
    tsv.write_text(tsv.read_text() + "".join(f"{i}\t{b}\tslice {i}\t-\t1\t-\tnone\taccept.sh\tsh accept.sh\ttrue\n"
                                             for i, b in extra))
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'docs: rows' --trailer 'Slice-Records: yes'",
       w["repo"], w["env"])


def merged(w, sid, n):
    """The records the merge script leaves for a merged slice: merged.json and the verifier's pass for its tip."""
    rec = w["data"] / "records" / sid
    rec.mkdir(parents=True, exist_ok=True)
    tip, merge = f"{n:040x}", f"{n + 100:040x}"
    (rec / "merged.json").write_text(json.dumps({"slice": sid, "tip": tip, "merge": merge,
                                                 "acceptance_run": f"merge-{n}.log"}))
    (rec / f"verify-{tip}.json").write_text(json.dumps({"slice": sid, "commit": tip, "verdict": "pass"}))


def stopped(w, sid):
    rec = w["data"] / "records" / sid
    rec.mkdir(parents=True, exist_ok=True)
    (rec / "state.json").write_text(json.dumps({"phase": "stopped", "note": "findings: your word?", "track": "1"}))


def board(w):
    p = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"])
    body = json.loads((w["repo"] / STATUS).read_text().split("window.OSPREY_STATUS = ", 1)[1].rstrip().rstrip(";"))
    return p.stdout, body


def test_a_build_with_three_rows_and_two_merged_writes_2_of_3(world):
    w = world
    rows(w, ("S3", "CO1"), ("S4", "CO1"))   # with S1: three rows for CO1
    merged(w, "S3", 3)
    merged(w, "S4", 4)
    out, body = board(w)
    assert body["builds"]["CO1"]["state"] == "done"
    assert (body["builds"]["CO1"]["slices"], body["builds"]["CO1"]["slices_merged"],
            body["builds"]["CO1"]["slices_cut"]) == ("2 of 3", 2, 3), body["builds"]["CO1"]
    assert {k: body["build_slices"]["CO1"][k] for k in ("merged", "cut", "said")} == {"merged": 2, "cut": 3, "said": "2 of 3"}, \
        body["build_slices"]
    assert "CO1 2 of 3" in out, out


def test_a_new_row_raises_the_cut(world):
    w = world
    rows(w, ("S3", "CO1"), ("S4", "CO1"))
    merged(w, "S3", 3)
    merged(w, "S4", 4)
    rows(w, ("S5", "CO1"))
    _, body = board(w)
    assert body["builds"]["CO1"]["slices"] == "2 of 4" and body["build_slices"]["CO1"]["cut"] == 4, body


def test_a_build_with_no_merged_slice_writes_0_of_n_not_an_absence(world):
    w = world
    rows(w, ("B1", "BL1"), ("B2", "BL1"))
    _, body = board(w)
    assert {k: body["build_slices"]["BL1"][k] for k in ("merged", "cut", "said")} == {"merged": 0, "cut": 2, "said": "0 of 2"}, \
        body["build_slices"]
    assert "BL1" not in body["builds"]  # not started: the dashboard's four states hold, the count is still written
    stopped(w, "B1")
    _, body = board(w)
    assert body["builds"]["BL1"]["state"] == "stopped" and body["builds"]["BL1"]["slices"] == "0 of 2", body["builds"]


def test_a_merge_record_the_board_refuses_is_not_counted_merged(world):
    w = world
    rows(w, ("S3", "CO1"))
    merged(w, "S3", 3)
    (w["data"] / "records/S3" / f"verify-{3:040x}.json").unlink()  # no verifier's pass: never done, never counted
    _, body = board(w)
    assert body["build_slices"]["CO1"]["said"] == "0 of 2", body["build_slices"]


def test_a_build_not_in_the_plan_is_not_counted(world):
    w = world
    _, body = board(w)
    assert "ZZ9" not in body["build_slices"] and body["build_slices"]["CO1"]["said"] == "0 of 1", body["build_slices"]
