"""The merge reports its progress for the dashboard (MERGE_PROGRESS_BRIEF.md; the owner, 19 November 2026: "make these
runs have intermediate status outputs going forward so that it is possible to track progress in the dashboard").

A merge writes records/<ID>/merge-progress.json as it goes: at each of its seven steps' start and end, and every few
seconds while one runs (the step, "n of 7", when it began, the steps done with their result and seconds, the log's size
and last write, and an estimate left only when the records give one). board.py puts it in status.js as the slice's
`progress`, and in the row's words: "merging: step 5 of 7, ...", "stalled" when the log has not grown while the process
lives, "merge stopped without a result" when the process is gone. The merge's own behaviour is unchanged, and a record
that cannot be written never fails it.

The merge runs as the conductor runs it, with the full gate's stand-in sleeping (TEST_GATE_SLEEP) so it can be read
mid-step; the board as the line runs it.
"""
from __future__ import annotations

import json
import subprocess
import time

from test_gates import built, merge, sh, verified, world  # noqa: F401  (world is a fixture)

STATUS = "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/status.js"
STEPS = ["checks before the gate", "red before: the acceptance on the base", "the merge onto main",
         "the acceptance, checks and scans on the merge result", "today's full gate", "landing on main", "the push"]


def ready(w):
    wt, tip = built(w)
    verified(w, wt, tip)
    p = w["data"] / "records/S1/state.json"
    st = json.loads(p.read_text())
    st.update(phase="verified", tip=tip)
    p.write_text(json.dumps(st))
    return tip


def record(w, name="merge-progress.json"):
    try:
        return json.loads((w["data"] / "records/S1" / name).read_text())
    except (OSError, ValueError):
        return None


def start(w, **env):
    e = {**w["env"], "TEST_GATE": "0", "OSPREY_PROGRESS_SECONDS": "0.5", **{k: str(v) for k, v in env.items()}}
    return subprocess.Popen([w["py"], str(w["lines"] / "merge_slice.py"), "merge", "S1"], cwd=str(w["repo"]), env=e,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def at_step(w, n, p, within=90):
    end = time.monotonic() + within
    while time.monotonic() < end:
        r = record(w)
        if r and r.get("step") and r["step"]["n"] == n and r["state"] == "running":
            return r
        if p.poll() is not None:
            raise AssertionError(f"the merge ended before step {n}: {p.stdout.read()} {p.stderr.read()}")
        time.sleep(0.2)
    raise AssertionError(f"no step {n} within {within} s: {record(w)}")


def board(w, **env):
    b = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], {**w["env"], **{k: str(v) for k, v in env.items()}},
           check=False)
    status = json.loads((w["repo"] / STATUS).read_text().split("window.OSPREY_STATUS = ", 1)[1].rstrip().rstrip(";"))
    return b, status["builds"]["CO1"]


def test_a_running_merge_shows_its_step_its_number_its_seconds_and_its_log(world):
    w = world
    tip = ready(w)
    p = start(w, TEST_GATE_SLEEP=4)
    try:
        r = at_step(w, 5, p)
        assert r["slice"] == "S1" and r["tip"] == tip and r["pid"] == p.pid and r["merge_id"].startswith("merge-"), r
        assert r["step"]["name"] == "today's full gate" and r["step"]["of"] == 7 and r["step"]["began"], r
        assert [d["name"] for d in r["done"]] == STEPS[:4], r["done"]
        assert [d["result"] for d in r["done"]] == ["passed", "red as expected", "passed", "passed"], r["done"]
        assert all(isinstance(d["seconds"], int) for d in r["done"])
        assert r["log"]["size"] > 0 and r["log"]["mtime"] and r["log"]["path"].endswith(r["merge_id"] + ".log"), r
        time.sleep(1.6)                                             # rewritten while the step runs, not only at its ends
        assert record(w)["updated"] != r["updated"], (r, record(w))
        b, co1 = board(w)
        assert co1["progress"]["state"] == "running" and co1["progress"]["n_of"] == "5 of 7", co1
        assert co1["note"].startswith("merging: step 5 of 7, today's full gate"), co1["note"]
        row = next(ln for ln in b.stdout.splitlines() if ln.startswith("S1 "))
        assert "merging: step 5 of 7" in row, b.stdout
    finally:
        out, err = p.communicate(timeout=120)
    assert p.returncode == 0, out + err
    r = record(w)
    assert r["state"] == "finished" and r["result"] == "merged" and [d["name"] for d in r["done"]] == STEPS, r
    assert "progress" not in board(w)[1]                            # done: no progress field


def test_a_step_that_writes_nothing_is_shown_stalled(world):
    w = world
    ready(w)
    p = start(w, TEST_GATE_SLEEP=8)
    try:
        at_step(w, 5, p)
        time.sleep(3)
        b, co1 = board(w, OSPREY_STALL_SECONDS=2)
        assert co1["progress"]["state"] == "stalled" and "stalled: the log has not grown" in co1["note"], co1
    finally:
        p.communicate(timeout=120)


def test_a_killed_merge_is_shown_stopped_without_a_result(world):
    w = world
    ready(w)
    p = start(w, TEST_GATE_SLEEP=60)
    at_step(w, 5, p)
    p.kill()
    p.communicate()
    b, co1 = board(w)
    assert co1["progress"]["state"] == "no process", co1
    assert co1["note"] == "merge stopped without a result (step 5 of 7, today's full gate)", co1["note"]


def test_a_red_step_is_recorded_red_with_its_seconds_and_the_merge_is_finished(world):
    w = world
    ready(w)
    p = merge(w, gate="1")
    assert p.returncode == 1, p.stdout + p.stderr
    r = record(w)
    assert r["state"] == "finished" and r["result"] == "refused" and "full gate is red" in r["why"], r
    assert r["done"][-1]["name"] == "today's full gate" and r["done"][-1]["result"] == "red", r["done"]
    assert isinstance(r["done"][-1]["seconds"], int)
    assert "progress" not in board(w)[1]


def history(w, slice_id, name, seconds):
    d = w["data"] / "records" / slice_id
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps({"slice": slice_id, "merge_id": name[len("merge-progress-"):-5], "state": "finished",
                                      "done": [{"name": n, "result": "passed", "seconds": seconds} for n in STEPS]}))


def test_with_nothing_to_go_on_there_is_no_estimate(world):
    w = world
    ready(w)
    p = start(w, TEST_GATE_SLEEP=3)
    try:
        r = at_step(w, 5, p)
        assert r["estimate_left_s"] is None and r["estimate_from"] == "no estimate", r
        assert "no estimate" in board(w)[1]["note"]
    finally:
        p.communicate(timeout=120)


def test_the_estimate_comes_from_the_slices_previous_attempt_before_any_other_slices(world):
    w = world
    ready(w)
    history(w, "S9", "merge-progress-s9old.json", 1000)
    p = start(w, TEST_GATE_SLEEP=3)
    try:
        r = at_step(w, 5, p)
        assert r["estimate_from"] == "the last 1 merge(s) of any slice" and 2900 <= r["estimate_left_s"] <= 3000, r
    finally:
        p.communicate(timeout=120)
    history(w, "S1", "merge-progress-s1old.json", 100)  # this slice's own earlier attempt, kept beside it
    sh(f"git reset -q --hard HEAD~1", w["repo"])           # main back before S1, so it merges again
    st = json.loads((w["data"] / "records/S1/state.json").read_text())
    st["phase"] = "verified"
    (w["data"] / "records/S1/state.json").write_text(json.dumps(st))
    (w["data"] / "records/S1/merged.json").unlink()
    p = start(w, TEST_GATE_SLEEP=3)
    try:
        r = at_step(w, 5, p)
        assert r["estimate_from"] == "this slice's previous attempt", r
    finally:
        p.communicate(timeout=120)


def test_two_merges_records_never_mix(world):
    w = world
    ready(w)
    history(w, "S1", "merge-progress-old.json", 7)
    old = (w["data"] / "records/S1/merge-progress-old.json").read_bytes()
    p = start(w, TEST_GATE_SLEEP=2)
    try:
        r = at_step(w, 5, p)
        assert r["merge_id"] != "old" and len(r["done"]) == 4, r          # its own steps only
    finally:
        p.communicate(timeout=120)
    r = record(w)
    kept = record(w, f"merge-progress-{r['merge_id'].removeprefix('merge-')}.json")
    assert kept == r and (w["data"] / "records/S1/merge-progress-old.json").read_bytes() == old


def test_a_record_that_cannot_be_written_never_fails_the_merge(world):
    w = world
    ready(w)
    (w["data"] / "records/S1/merge-progress.json").mkdir()                # nothing can replace a folder
    p = merge(w)
    assert p.returncode == 0, p.stdout + p.stderr
    logs = list((w["data"] / "records/S1").glob("merge-*.log"))
    text = "".join(f.read_text() for f in logs)
    assert text.count("the progress record could not be written") == 1, text[-2000:]
