"""The status file names every part of a build (the owner's file 014, 23 November 2026), so the dashboard can tick
each merged part and show a second part of the same build in flight: build_slices[<build>]["list"], in the order of
slices.tsv, each part's id, its row's `what` as written, its own state (merged, building, verifying, verified, stopped,
not started) and, when there is one, the same server object builds[<build>].server carries. builds[<build>] stays as
it was.

The case is PL7 on the morning of 23 November: four rows in slices.tsv (PL7a1 and PL7a2a merged; PL7c with its
verifier while PL7a2b builds), from the real rows on main and the two unmerged parts' real state files of that day
(tests/fixtures). The world's branches stand in for the real ones; PL7c's checks are green at its tip, as they were
when its verifier took it.
"""
from __future__ import annotations

import json
from pathlib import Path

from test_build_counts import STATUS, V062, board, merged
from test_gates import sh, world  # noqa: F401  (world is a fixture)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ROWS = (FIXTURES / "slices_PL7_2026-11-23.tsv").read_text()
ORDER = [ln.split("\t")[0] for ln in ROWS.splitlines()]
WHAT = {ln.split("\t")[0]: ln.split("\t")[2] for ln in ROWS.splitlines()}


def pl7(w):
    """PL7 in the world: its real rows on main, its build in the plan, two parts merged, two in flight."""
    (w["repo"] / V062 / "slices.tsv").write_text((w["repo"] / V062 / "slices.tsv").read_text() + ROWS)
    plan = w["repo"] / STATUS.replace("status.js", "index.html")
    plan.write_text(plan.read_text().replace("\n];", ',\n["PL7",7,1,"None","z",[],""]\n];'))
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'docs: PL7 rows' --trailer 'Slice-Records: yes'",
       w["repo"], w["env"])
    merged(w, "PL7a1", 71)
    merged(w, "PL7a2a", 72)
    for sid in ("PL7a2b", "PL7c"):
        rec = w["data"] / "records" / sid
        rec.mkdir(parents=True, exist_ok=True)
        st = json.loads((FIXTURES / f"state_{sid}_2026-11-23.json").read_text())
        sh(["git", "branch", f"lane/slice-{sid}", "main"], w["repo"])
        tip = sh(["git", "rev-parse", f"lane/slice-{sid}"], w["repo"]).stdout.strip()
        (rec / "state.json").write_text(json.dumps({**st, "tip": tip}))
        if sid == "PL7c":  # with its verifier: its checks green at its tip
            (rec / f"tests-{tip}.json").write_text(json.dumps({"slice": sid, "commit": tip, "green": True}))


def test_every_part_of_a_build_is_listed_with_its_own_state_in_the_order_of_slices_tsv(world):
    w = world
    pl7(w)
    _, body = board(w)
    parts = body["build_slices"]["PL7"]["list"]
    assert [p["id"] for p in parts] == ORDER, parts                     # every part, as slices.tsv orders them
    assert {p["id"]: p["state"] for p in parts} == {"PL7a1": "merged", "PL7a2a": "merged", "PL7c": "verifying",
                                                    "PL7a2b": "building"}, parts
    assert all(p["what"] == WHAT[p["id"]] for p in parts), parts        # the row's what, as written
    assert all(set(p) <= {"id", "what", "state", "said", "waiting_for", "server"} for p in parts), parts  # nothing else
    assert (body["build_slices"]["PL7"]["merged"], body["build_slices"]["PL7"]["cut"]) == (2, 4)
    assert body["builds"]["PL7"]["state"] in ("building", "verifying"), body["builds"]["PL7"]   # as before


def test_a_verified_part_and_its_server_object_are_listed(world):
    w = world
    pl7(w)
    rec = w["data"] / "records" / "PL7c"
    st = json.loads((rec / "state.json").read_text())
    st["phase"] = "verified"
    (rec / "state.json").write_text(json.dumps(st))
    (rec / f"verify-{st['tip']}.json").write_text(json.dumps({"slice": "PL7c", "commit": st["tip"], "verdict": "pass"}))
    _, body = board(w)
    (part,) = [p for p in body["build_slices"]["PL7"]["list"] if p["id"] == "PL7c"]
    assert part["state"] == "verified", part
    assert part["server"]["state"] == "none" and part["server"]["tip"] == st["tip"], part   # builds[].server's own shape
