"""The installed runner can be steered by nothing in its environment (the owner's condition before install, 21 November
2026): with each old test switch set, a work folder named elsewhere, and a PYTHONPATH carrying planted modules, an
SSH-shaped request still launches the job only through systemd-run's caps, and the job runs the real gate.

The request runs the forced command exactly as install.sh prints it (`/usr/bin/python3 -I <bin>/runner.py`, with the
python under test in /usr/bin/python3's place), through `sh -c` as sshd runs it. A fake systemd-run records its
arguments and then starts the job it was given, in the environment it was given, so the job sees every variable too.
The only seam is the disk floor: this Mac has less than protocol.py's 40 GB free, so the launch test alone goes through
tests/harness_runner.py with {"launch": "capped", "gate": null} (runner.py's own launch and gate, untouched) and a
lower floor; the forced-command tests use no seam at all."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

from conftest import DEMO, PROC_HEADER, WRAPPER, sh
from test_gate import bundle, mini

OLD_SWITCHES = ("OSPREY_EARLY_TEST_LAUNCH", "OSPREY_EARLY_TEST_GATE", "OSPREY_EARLY_TEST_MIN_FREE", "OSPREY_EARLY_WORK")

FAKE_SYSTEMD_RUN = r'''#!/usr/bin/env -S python3 -I
import json, os, subprocess, sys
a = sys.argv[1:]
with open(os.environ["FAKE_SYSTEMD_LOG"], "a") as fh:
    fh.write(json.dumps(a) + "\n")
job = a[a.index("--") + 1:]  # [python, -I, <bin>/runner.py, _job, <id>]: recorded above as given
# the Mac has no /proc/net, so the job runs through the tests' wrapper with that one stand-in (gate and launch untouched)
job = [job[0], "-I", os.environ["FAKE_JOB_WRAPPER"], job[2], os.environ["FAKE_JOB_HARNESS"], *job[3:]]
subprocess.Popen(job, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                 start_new_session=True, env=dict(os.environ))
'''


def forced_command(w):
    """The command= value install.sh prints, for this test's folder and python."""
    text = (DEMO / "install.sh").read_text()
    line = next(ln for ln in text.splitlines() if "restrict <PUBLIC KEY" in ln)
    cmd = re.search(r'command=\\"(.*?)\\",restrict', line).group(1)
    assert cmd.startswith("/usr/bin/python3 -I ")
    return cmd.replace("$ROOT", str(w["remote"])).replace("/usr/bin/python3", sys.executable, 1)


def steering(w, tmp):
    """Every variable that once steered the runner, set as a hostile environment would set it."""
    planted = tmp / "planted"
    planted.mkdir()
    (planted / "sitecustomize.py").write_text(f"open({str(tmp / 'site-ran')!r}, 'w').write('ran')\n")
    (planted / "protocol.py").write_text("raise SystemExit('a planted protocol.py was imported')\n")
    elsewhere = tmp / "elsewhere"
    (elsewhere / "jobs").mkdir(parents=True)
    stand_in = tmp / "stand-in.json"
    stand_in.write_text(json.dumps({"exit": 0}))
    return {"OSPREY_EARLY_TEST_LAUNCH": "direct", "OSPREY_EARLY_TEST_GATE": str(stand_in),
            "OSPREY_EARLY_TEST_MIN_FREE": "1", "OSPREY_EARLY_WORK": str(elsewhere), "PYTHONPATH": str(planted),
            "PYTHONSTARTUP": str(planted / "sitecustomize.py")}


def test_the_installed_runner_names_no_test_switch_and_reads_only_the_ssh_command():
    text = (DEMO / "runner.py").read_text()
    for name in OLD_SWITCHES:
        assert name not in text, name
    reads = re.findall(r"os\.environ(?:\.get)?\(?\[?[\"']?(\w*)", text)
    assert [r for r in reads if r] == ["SSH_ORIGINAL_COMMAND"]
    assert "harness_runner" not in text and "stand_in" not in text
    assert "harness_runner.py" not in (DEMO / "install.sh").read_text()


def test_with_every_switch_set_the_forced_command_ignores_them(world, tmp_path):
    """The forced command, as sshd runs it, with a hostile environment: the work folder is bin/../data (a result there
    is the answer, not one planted elsewhere), and -I keeps the planted modules out."""
    w = world
    env = {"PATH": os.environ["PATH"], "HOME": str(w["remote"] / "home"), **steering(w, tmp_path),
           "SSH_ORIGINAL_COMMAND": "result 0123456789abcdef"}
    for where, said in ((w["remote"] / "data/jobs", "the real one"), (tmp_path / "elsewhere/jobs", "the planted one")):
        (where / "0123456789abcdef").mkdir(parents=True)
        (where / "0123456789abcdef/job.json").write_text("{}")
        (where / "0123456789abcdef/result.json").write_text(json.dumps({"state": "done", "words": said}))
    p = subprocess.run(["sh", "-c", forced_command(w)], env=env, capture_output=True)
    assert json.loads(p.stdout.decode().splitlines()[-1])["words"] == "the real one", p.stderr
    assert not (tmp_path / "site-ran").exists()  # -I: no PYTHONPATH, no sitecustomize, no startup file
    env["SSH_ORIGINAL_COMMAND"] = "run; ls"
    p = subprocess.run(["sh", "-c", forced_command(w)], env=env, capture_output=True)
    assert json.loads(p.stdout.decode().splitlines()[-1])["reason"] == "shape"
    assert not list((tmp_path / "elsewhere").glob("refusals.log"))  # logged in its own folder, not where it was told


def test_with_every_switch_set_a_run_still_launches_capped_and_runs_the_real_gate(world, tmp_path):
    w = world
    ran, tip = mini(w)
    fake = tmp_path / "sysbin"
    fake.mkdir()
    (fake / "systemd-run").write_text(FAKE_SYSTEMD_RUN)
    (fake / "systemd-run").chmod(0o755)
    log = tmp_path / "systemd-run.log"
    harness = tmp_path / "floor-only.json"
    proc = tmp_path / "proc-net"
    proc.mkdir(exist_ok=True)
    for name in ("tcp", "tcp6"):
        (proc / name).write_text(PROC_HEADER)  # the Mac has no /proc/net: nothing listening, in its format
    harness.write_text(json.dumps({"launch": "capped", "gate": None, "min_free": 1, "proc": str(proc)}))
    env = {"PATH": f"{fake}{os.pathsep}{os.environ['PATH']}", "HOME": str(w["remote"] / "home"),
           "FAKE_SYSTEMD_LOG": str(log), "FAKE_JOB_WRAPPER": str(WRAPPER), "FAKE_JOB_HARNESS": str(harness),
           **steering(w, tmp_path), "SSH_ORIGINAL_COMMAND": "run"}
    p = subprocess.run([sys.executable, "-I", str(WRAPPER), str(w["remote"] / "bin/runner.py"), str(harness)],
                       input=bundle(w), env=env, capture_output=True)
    a = json.loads(p.stdout.decode().splitlines()[-1])
    assert a["state"] == "started", (a, p.stderr)
    calls = [json.loads(ln) for ln in log.read_text().splitlines()]
    assert len(calls) == 1
    call = calls[0]
    for want in ("--user", "CPUQuota=600%", "MemoryMax=16G", "MemorySwapMax=0", "IOSchedulingClass=best-effort"):
        assert want in call, want
    assert any(x.startswith("RuntimeMaxSec=") for x in call)
    job = call[call.index("--") + 1:]
    assert job[1] == "-I" and job[2].endswith("bin/runner.py") and job[3] == "_job"  # the installed file, isolated
    result = w["remote"] / "data/jobs" / a["id"] / "result.json"
    end = time.monotonic() + 60
    while not result.exists() and time.monotonic() < end:
        time.sleep(0.3)
    r = json.loads(result.read_text())
    assert r["lists_from"] == "the candidate's" and r["lists_from"] != "stand-in"  # the real gate, not a stand-in
    assert "good-check" in ran.read_text() and r["verdict"] == "fail" and "red-check" in r["failing"]["targets"]
    assert not (tmp_path / "site-ran").exists()
    assert not list((tmp_path / "elsewhere/jobs").iterdir())
