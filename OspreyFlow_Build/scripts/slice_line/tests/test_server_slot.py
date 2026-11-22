"""Item 1 of the owner's file 004 (22 November 2026): before the slot. A verified slice the demo server shows red is not
given the merge slot until its named tests are rerun on the Mac: green there, it queues as before; red there, it goes
back to its builder. A slice with no server result queues as before. Behind the owner's switch (server_counts, off as
built): off, nothing is held.

The server's result is the runner's own, fetched by run id (`early_warning.py fetch <id>`, stood in here by a script that
answers from files the test writes); the note in the lanes folder is read for the run id alone. merge_slice.py runs as
the conductor runs it; its rerun on the Mac is stood in (TEST_RERUN), as the full gate is.
"""
from __future__ import annotations

import json
import os

import pytest

from test_gates import built, guard, merge, refused, sh, verified, world  # noqa: F401  (world is a fixture)

V062 = "OspreyFlow_Build/process/lanes/v062"
RID = "924e14b4b4620ed0"
OTHER = "0123456789abcdef"
FAILING = "../OspreyFlow_Build/tests/test_release_local_matrix.py::test_it_builds_every_image_the_product_releases"

FAKE_EW = '''import json, os, re, sys
from pathlib import Path
if len(sys.argv) != 3 or sys.argv[1] != "fetch" or not re.fullmatch(r"[0-9a-f]{16}", sys.argv[2]):
    sys.exit(2)
f = Path(os.environ.get("TEST_EW_RESULTS", "/nonexistent")) / (sys.argv[2] + ".json")
if not f.is_file():
    print("no such run", file=sys.stderr)
    sys.exit(1)
print("connecting ...")
print(f.read_text().strip())
'''


def ready(w):
    wt, tip = built(w)
    verified(w, wt, tip)
    p = w["data"] / "records/S1/state.json"
    st = json.loads(p.read_text())
    st.update(phase="verified", tip=tip)
    p.write_text(json.dumps(st))
    (w["lines"] / "early_warning.py").write_text(FAKE_EW)  # committed, as main carries early_warning.py (009)
    sh("git add OspreyFlow_Build/scripts/slice_line/early_warning.py && git commit -qm 'test: the early warning stood in'",
       w["repo"], w["env"])
    w["env"]["TEST_EW_RESULTS"] = str(w["tmp"] / "ew")
    (w["tmp"] / "ew").mkdir(exist_ok=True)
    return wt, tip


def switch(w, text="on\n"):
    f = w["data"] / "server_counts"
    f.unlink(missing_ok=True)
    if text is not None:
        f.write_text(text)


def result(w, tip, rid=RID, verdict="fail", slice_id="S1", tests=(FAILING,), targets=("test",), **extra):
    main = sh("git rev-parse main", w["repo"]).stdout.strip()
    r = {"state": "done", "id": rid, "slice": slice_id, "main": main, "tip": tip, "verdict": verdict,
         "failing": {"tests": list(tests), "targets": list(targets), "by_target": {"test": list(tests)} if tests else {}},
         **extra}
    (w["tmp"] / "ew" / f"{rid}.json").write_text(json.dumps(r))
    return r


def note(w, tip, rid=RID, headline="RED"):
    d = w["repo"] / V062 / "early_warning"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"S1-{tip[:8]}.md").write_text(f"# Early warning: S1 at {tip[:8]}: {headline}\n\n- Run id: `{rid}`\n")


def state(w):
    return json.loads((w["data"] / "records/S1/state.json").read_text())


def main_sha(w):
    return sh("git rev-parse main", w["repo"]).stdout.strip()


def rerun(w, code="0"):
    return sh([w["py"], str(w["lines"] / "merge_slice.py"), "server-rerun", "S1"], w["repo"],
              {**w["env"], "TEST_RERUN": code, "TEST_RERUN_SEES": str(w["tmp"] / "rerun-sees.json")}, check=False)


def test_a_slice_the_server_shows_red_is_not_given_the_slot_until_rerun_and_green_on_the_mac(world):
    w = world
    wt, tip = ready(w)
    switch(w)
    result(w, tip)
    note(w, tip)
    before = main_sha(w)
    p = merge(w)
    assert p.returncode == 1 and "not given the merge slot" in p.stderr and "server-rerun S1" in p.stderr, p.stderr
    assert main_sha(w) == before and not list((w["data"] / "records/S1").glob("merge-*.log"))  # the slot never taken
    r = rerun(w, "0")
    assert r.returncode == 0 and "green on the Mac" in r.stdout, r.stdout + r.stderr
    seen = json.loads((w["tmp"] / "rerun-sees.json").read_text())
    assert seen == {"tests": [FAILING], "targets": [], "feature": True}, seen   # the named test, on main + the slice
    rec = json.loads((w["data"] / f"records/S1/server-rerun-{RID}.json").read_text())
    assert rec["result"] == "green" and rec["tip"] == tip and rec["run_id"] == RID, rec
    p = merge(w)
    assert p.returncode == 0, p.stdout + p.stderr                              # it queues as before


def test_red_on_the_mac_too_sends_the_slice_back_to_its_builder(world):
    w = world
    wt, tip = ready(w)
    switch(w)
    result(w, tip)
    note(w, tip)
    r = rerun(w, "1")
    assert r.returncode == 0 and "red on the Mac too" in r.stdout, r.stdout + r.stderr
    st = state(w)
    assert st["phase"] == "refused" and st["refused_for"] == "gate", st
    f = json.loads((w["data"] / f"records/S1/verify-gate-{tip}.json").read_text())["findings"]
    assert [x["what"] for x in f] == [f"Rerun on the Mac after the demo server's run {RID}: {FAILING} failed there too."]
    assert json.loads((w["data"] / f"records/S1/server-rerun-{RID}.json").read_text())["result"] == "red"
    p = merge(w)                                                               # never merged on a red rerun
    assert p.returncode == 1, p.stdout + p.stderr


def test_a_failing_target_with_no_test_named_is_rerun_by_its_target(world):
    w = world
    wt, tip = ready(w)
    switch(w)
    result(w, tip, tests=(), targets=("licence-check",))
    note(w, tip)
    assert rerun(w).returncode == 0
    assert json.loads((w["tmp"] / "rerun-sees.json").read_text())["targets"] == ["licence-check"]


@pytest.mark.parametrize("text", [None, "", "ON", "on ", "off", "on\non\n", "link"],
                         ids=["absent", "empty", "upper", "trailing-space", "off", "twice", "a-link"])
def test_with_the_switch_off_a_server_red_holds_nothing(world, text):
    w = world
    wt, tip = ready(w)
    if text == "link":
        (w["tmp"] / "elsewhere").write_text("on\n")
        switch(w, None)
        os.symlink(w["tmp"] / "elsewhere", w["data"] / "server_counts")
    else:
        switch(w, text)
    result(w, tip)
    note(w, tip)
    p = merge(w)
    assert p.returncode == 0, p.stdout + p.stderr


@pytest.mark.parametrize("how", ["no-note", "unfetchable", "another-tip", "another-slice", "green", "running",
                                 "note-says-red-run-is-green", "a-bad-run-id", "another-runs-answer"])
def test_no_red_result_from_the_runner_for_this_slice_at_this_tip_holds_nothing(world, how):
    w = world
    wt, tip = ready(w)
    switch(w)
    if how != "no-note":
        note(w, tip, rid="NOT-HEX" if how == "a-bad-run-id" else RID)
    if how == "another-tip":
        result(w, "f" * 40)
    elif how == "another-slice":
        result(w, tip, slice_id="S2")
    elif how in ("green", "note-says-red-run-is-green"):
        result(w, tip, verdict="pass", tests=(), targets=())       # the note's own words say RED: never read
    elif how == "running":
        r = result(w, tip)
        r["state"] = "running"
        (w["tmp"] / "ew" / f"{RID}.json").write_text(json.dumps(r))
    elif how == "a-bad-run-id":
        result(w, tip)
    elif how == "another-runs-answer":  # the fetch for RID answers with another run's result
        r = result(w, tip, rid=OTHER)
        (w["tmp"] / "ew" / f"{RID}.json").write_text(json.dumps(r))
    p = merge(w)
    assert p.returncode == 0, (how, p.stdout + p.stderr)


def test_a_rerun_with_no_red_result_is_refused_in_words(world):
    w = world
    wt, tip = ready(w)
    switch(w)
    result(w, tip, verdict="pass", tests=(), targets=())
    note(w, tip)
    r = rerun(w)
    assert r.returncode == 1 and "no red result from the demo server" in r.stderr, r.stdout + r.stderr


def test_the_switch_is_the_owners_alone(world):
    w = world
    for seat in ("conductor", "builder"):
        p = guard(w, "Bash", {"command": f"echo on > {w['data']}/server_counts"}, seat=seat)
        assert refused(p), (seat, p.stdout, p.stderr)
        p = guard(w, "Write", {"file_path": str(w["data"] / "server_counts"), "content": "on\n"}, seat=seat)
        assert refused(p), (seat, p.stdout, p.stderr)
