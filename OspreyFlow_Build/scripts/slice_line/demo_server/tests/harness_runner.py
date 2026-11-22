"""The Mac's tests' own way into runner.py, and the only one: never installed (install.sh copies the files its FILES names, and
this is not one of them), and nothing in runner.py reads it, names it or reads any variable that could select it.

    python harness_runner.py <the runner.py under test> <harness.json> [runner.py's own arguments]

harness.json, written by the test itself (never the environment):
    {"launch": "direct" | "capped",   direct: the job as a plain detached process (the Mac has no systemd-run);
                                       capped: runner.py's own launch_capped, untouched
     "gate": "<a JSON file>" | null,  a stand-in for the hour-long gate (its exit, failing names, checks, a sleep); null: the
                                       real gate, untouched
     "proc": "<a folder>" | null,     /proc/net's stand-in: its tcp and tcp6 files, written by the test
     "docker_sockets": [<paths>],     the Docker sockets a job checks are closed (none by default: the Mac's
                                       own Docker answers its owner)
     "slow_clean": <seconds> | null,  the job's clean-up made that much slower, so a result written before its
                                       work is gone is seen (run 7's race)
     "min_free": <bytes> | null}      the free-space floor for this test; null: protocol.py's own (40 GB),
                                       which a test must not rely on: the Mac's free space varies

The job the direct launch starts runs through this wrapper again, with the same harness file, so it sees the same
stand-ins. Everything else is runner.py's own: its command parsing, its refusals, its bundle checks, its merge.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

RUNNER = Path(sys.argv[1]).resolve()
HARNESS = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(RUNNER.parent))
import runner  # noqa: E402

conf = json.loads(HARNESS.read_text())


def direct(jid: str) -> bool:
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), str(RUNNER), str(HARNESS), "_job", jid],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return True


def stand_in_gate(tree, job, log, deadline, result):
    spec = json.loads(Path(conf["gate"]).read_text())
    time.sleep(float(spec.get("sleep", 0)))
    result["failing"]["targets"] += spec.get("targets", [])
    result["failing"]["tests"] += spec.get("tests", [])
    if spec.get("by_target"):
        result["failing"]["by_target"] = spec["by_target"]
    result["not_run"]["targets"] += spec.get("not_run", [])
    if "duckdb_spatial" in spec:
        result["duckdb_spatial"] = spec["duckdb_spatial"]
    if "checks" in spec:  # 009: the per-target statuses the real gate records
        result["checks"] = spec["checks"]
    result["lists_from"] = "stand-in"
    result["list_drift"] = []
    red = any((Path(tree) / f).exists() for f in spec.get("red_with", []))  # 013: red for a candidate holding it
    if red:
        result["failing"]["targets"] += ["test"]
    return [{"step": "stand-in", "exit": 1 if red else int(spec.get("exit", 0)), "seconds": 0}]


if conf.get("launch") == "direct":
    runner.LAUNCH = direct
if conf.get("gate"):
    runner.GATE = stand_in_gate
if conf.get("proc"):
    runner.PROC = Path(conf["proc"])  # the Mac has no /proc/net: a folder of the test's own, in its format
runner.DOCKER_SOCKETS = tuple(conf.get("docker_sockets", ()))  # the Mac's own Docker answers its owner
if conf.get("slow_clean"):
    _clean = runner.clean_job

    def slow_clean(job, tree):
        time.sleep(float(conf["slow_clean"]))
        _clean(job, tree)
    runner.clean_job = slow_clean
if conf.get("min_free") is not None:
    runner.p.MIN_FREE_BYTES = int(conf["min_free"])
sys.exit(runner.main([str(RUNNER), *sys.argv[3:]]))
