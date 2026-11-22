"""012 a and d: `early_warning.py fetch <id>` prints the runner's own result line for that run, unchanged, from the
server and never from a note; and while a run is in flight a file under early-warning/running/ says so, removed when
it ends. Against the local fake server."""
from __future__ import annotations

import json
import re
import subprocess
import time

from conftest import early, gate, note, runner, sh
from test_stack import slices


def ran_id(w):
    return re.search(r"Run id: `([0-9a-f]{16})`", note(w).read_text()).group(1)


def test_fetch_prints_the_runners_own_line_for_the_run_and_exits_0(world):
    w = world
    gate(w, exit=0)
    assert early(w, "S1").returncode == 0
    jid = ran_id(w)
    p = early(w, "fetch", jid)
    own = runner(w, "result " + jid).stdout.decode().strip().splitlines()[-1]
    assert p.returncode == 0 and p.stdout.decode() == own + "\n"  # one line, exactly as `result <id>` gives it
    assert json.loads(p.stdout)["id"] == jid


def test_fetch_never_reads_the_note(world):
    w = world
    gate(w, exit=1, targets=["a-check"])
    early(w, "S1")
    jid = ran_id(w)
    note(w).write_text(note(w).read_text().replace("RED", "GREEN"))
    p = early(w, "fetch", jid)
    assert p.returncode == 0 and json.loads(p.stdout)["verdict"] == "fail"


def test_fetch_of_a_run_the_server_does_not_hold_or_cannot_be_reached_is_non_zero(world):
    w = world
    p = early(w, "fetch", "feedfacefeedface")
    assert p.returncode == 3 and json.loads(p.stdout)["state"] == "unknown"
    p = early(w, "fetch", "feedfacefeedface", env={"FAKE_SSH": "down"})
    assert p.returncode == 4 and p.stdout == b""
    for bad in (["fetch"], ["fetch", "x"], ["fetch", "feedfacefeedface", "more"]):
        assert early(w, *bad).returncode == 2


def test_a_run_in_flight_has_its_running_file_and_it_is_gone_when_the_run_ends(world):
    w = world
    gate(w, exit=0, sleep=3)
    f = w["data"] / "early-warning/running" / f"S1-{w['tip'][:8]}.json"
    py = [w["py"], str(w["lines"] / "early_warning.py"), "S1"]
    proc = subprocess.Popen(py, cwd=str(w["repo"]), env=w["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    end = time.monotonic() + 15
    while not f.exists() and time.monotonic() < end and proc.poll() is None:
        time.sleep(0.1)
    seen = json.loads(f.read_text())
    assert seen["slice"] == "S1" and seen["tip"] == w["tip"] and re.fullmatch("[0-9a-f]{16}", seen["id"])
    assert proc.wait(timeout=60) == 0
    assert not f.exists()


def test_a_stacks_members_each_have_their_running_file_and_their_note_names_the_stacks_id(world):
    w = world
    tips = slices(w, "S2")
    rec = w["data"] / "records" / "S2"
    rec.mkdir(parents=True)
    (rec / "frozen.json").write_text(json.dumps({"branch": "lane/slice-S2", "acceptance": "true"}))
    (rec / "state.json").write_text(json.dumps({"phase": "verified", "tip": tips["S2"]}))
    gate(w, exit=0, sleep=3)
    run = w["data"] / "early-warning/running"
    proc = subprocess.Popen([w["py"], str(w["lines"] / "early_warning.py"), "S1", "S2"], cwd=str(w["repo"]),
                            env=w["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    end = time.monotonic() + 15
    while time.monotonic() < end and len(list(run.glob("*.json")) if run.exists() else []) < 2:
        time.sleep(0.1)
    names = sorted(x.name for x in run.glob("*.json"))
    assert names == sorted([f"S1-{w['tip'][:8]}.json", f"S2-{tips['S2'][:8]}.json"])
    stack_id = json.loads((run / names[0]).read_text())["stack_id"]
    assert proc.wait(timeout=60) == 0
    assert list(run.glob("*.json")) == []
    for path in (note(w), note(w).parent / f"S2-{tips['S2'][:8]}-after-S1.md"):
        assert f"The stack's run id: `{stack_id}`" in path.read_text()
    whole = json.loads(early(w, "fetch", stack_id).stdout)
    assert [m["slice"] for m in whole["stack"]] == ["S1", "S2"] and whole["state"] == "done"
