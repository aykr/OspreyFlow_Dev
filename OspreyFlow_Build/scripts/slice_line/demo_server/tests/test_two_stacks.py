"""The one exception to the freeze (the owner's word of 26 November 2026): two early-warning stacks side by side when
there is room. The queue verified parts wait in is this runner's: at most 3 jobs (protocol.MAX_JOBS), a stack one
job per part, so a stack of 3 fills it, and the next stack was refused busy for about 45 minutes.

How many jobs run at once, in which port slots and under which caps, is demo-server's to set, in capacity.json
beside the runner (runner.CAPACITY; root's, as the code is, and not a file install.sh writes):

    {"max_jobs": 6, "lanes": ["merger", "platform-b", "rules-b", "case-b", "studio-b", "docs"],
     "cpu_quota": "250%", "memory_max": "8G", "test_workers": 2}

- Without the file, or with one the runner cannot take whole, everything is as today: 3 jobs, the three gate lanes,
  400% and 12G each, 4 test workers. One that cannot be taken is said in the refusal.
- Past today's 3 jobs, a stack starts only when the machine has room for it at that moment: MemAvailable in
  /proc/meminfo at least its jobs' memory_max together. Otherwise it is refused busy, saying how much room there is.
- Each job takes its own lane (port slot) from the file's lanes, never one a running job holds, never `demo`.
- Each job runs under the file's caps (systemd-run's CPUQuota and MemoryMax).

Against the local fake server, with the stand-in gate. The machine's memory is stood in (harness "meminfo")."""
from __future__ import annotations

import json
import os
import time

import pytest

from conftest import runner
from test_runner import answer, bundle_of, wait
from test_stack import slices, stack_bundle

SIX = ["merger", "platform-b", "rules-b", "case-b", "studio-b", "docs"]
GIB = 1024 ** 3


def capacity(w, **c):
    f = w["remote"] / "bin" / "capacity.json"
    f.write_text(json.dumps(c) if c else "")
    if not c:
        f.unlink()


def meminfo(w, available_gib):
    f = w["tmp"] / "meminfo"
    f.write_text("MemTotal:       65011712 kB\nMemFree:         1000000 kB\n"
                 f"MemAvailable:   {int(available_gib * GIB / 1024)} kB\n")
    return {"meminfo": str(f)}


def two_stacks(w, room_gib, sleep=4):
    slices(w, "S2", "S3", "S4", "S5", "S6")
    w["gate"].write_text(json.dumps({"exit": 0, "sleep": sleep}))
    h = meminfo(w, room_gib)
    first = runner(w, "stack S1 S2 S3", stack_bundle(w, "S1", "S2", "S3"), harness=h)
    assert first.returncode == 0 and answer(first)["state"] == "started", answer(first)
    second = runner(w, "stack S4 S5 S6", stack_bundle(w, "S4", "S5", "S6"), harness=h)
    return answer(first), second


def test_without_demo_server_s_file_a_second_stack_waits_as_today(world):
    w = world
    a, p = two_stacks(w, room_gib=60)
    assert p.returncode == 3 and answer(p)["reason"] == "busy" and answer(p)["free"] == 0, answer(p)
    for j in a["ids"]:
        wait(w, j)


def test_with_room_and_demo_server_s_file_a_second_stack_runs_beside_the_first_each_job_in_its_own_slot(world):
    w = world
    capacity(w, max_jobs=6, lanes=SIX, cpu_quota="250%", memory_max="8G", test_workers=2)
    a, p = two_stacks(w, room_gib=30)                                 # 3 x 8 GB = 24 GB needed
    b = answer(p)
    assert p.returncode == 0 and b["state"] == "started", b
    time.sleep(1)
    ids = a["ids"] + b["ids"]
    assert [answer(runner(w, "result " + j))["state"] for j in ids] == ["running"] * 6   # side by side
    done = [wait(w, j) for j in ids]
    assert all(r["verdict"] == "pass" for r in done), done
    lanes = [r["lane"] for r in done]
    assert sorted(lanes) == sorted(SIX), lanes                         # six slots, never shared
    assert [r["slice"] for r in done[3:]] == ["S4", "S5", "S6"]


def test_a_second_stack_without_room_at_that_moment_is_refused_busy_saying_so(world):
    w = world
    capacity(w, max_jobs=6, lanes=SIX, cpu_quota="250%", memory_max="8G", test_workers=2)
    a, p = two_stacks(w, room_gib=20)                                 # 24 GB needed
    b = answer(p)
    assert p.returncode == 3 and b["reason"] == "busy" and "no room" in b["words"] and "20" in b["words"], b
    for j in a["ids"]:
        assert wait(w, j)["verdict"] == "pass"


@pytest.mark.parametrize("bad", [
    {"max_jobs": 6, "lanes": SIX[:5]},                                # fewer slots than jobs
    {"max_jobs": 6, "lanes": SIX[:5] + ["demo"]},                     # the demo's own slot
    {"max_jobs": 9, "lanes": SIX + ["admin", "case", "glass"]},       # past two stacks
    {"max_jobs": 6, "lanes": SIX, "memory_max": "64G"},               # caps it cannot be
    {"max_jobs": 6, "lanes": SIX, "cpu_quota": "400"},
    "not json"], ids=["few-lanes", "demo-lane", "too-many", "memory", "cpu", "unreadable"])
def test_a_file_the_runner_cannot_take_whole_leaves_today_s_limits_and_says_so(world, bad):
    w = world
    f = w["remote"] / "bin" / "capacity.json"
    f.write_text(bad if isinstance(bad, str) else json.dumps(bad))
    a, p = two_stacks(w, room_gib=60)
    b = answer(p)
    assert p.returncode == 3 and b["reason"] == "busy" and b["free"] == 0, b
    assert "capacity.json" in b.get("capacity", ""), b
    for j in a["ids"]:
        wait(w, j)


def test_each_job_runs_under_the_file_s_caps(world):
    w = world
    capacity(w, max_jobs=6, lanes=SIX, cpu_quota="250%", memory_max="8G", test_workers=2)
    fake = w["tmp"] / "fakebin"
    fake.mkdir()
    (fake / "systemd-run").write_text("#!/bin/sh\necho \"$@\" >> %s\n" % (w["tmp"] / "systemd-run.log"))
    (fake / "systemd-run").chmod(0o755)
    p = runner(w, "run", bundle_of(w, "refs/heads/main", "refs/heads/lane/slice-S1"), harness={"launch": "capped", **meminfo(w, 60)},
               env={"PATH": f"{fake}{os.pathsep}{os.environ['PATH']}"})
    assert p.returncode == 0 and answer(p)["state"] == "started", answer(p)
    said = (w["tmp"] / "systemd-run.log").read_text()
    assert "CPUQuota=250%" in said and "MemoryMax=8G" in said, said
