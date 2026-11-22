"""The early warning's world: a throwaway repository shaped like this one, a fake home holding the slice's records, a
fake `ssh` that runs the real runner.py (from a copy installed in a fake server folder) as sshd's forced command would,
and a stand-in for the hour-long gate. No network, no Docker, no Claude session, no server.

The fake ssh models sshd's refusals as well as its grants (process/CLAUDE.md rule 15): the forced command always runs,
whatever was asked; the words asked for reach the runner only as SSH_ORIGINAL_COMMAND; FAKE_SSH=down is an
unreachable server (exit 255, and ssh's own words, which name the host, on stderr).
"""
from __future__ import annotations

import json
import os
import shutil
import uuid
import subprocess
import sys
from pathlib import Path

import pytest

LINE = Path(__file__).resolve().parents[2]  # scripts/slice_line
DEMO = LINE / "demo_server"
TIP_PATTERN = "[0-9a-f]{40}"
#: The seven files install.sh puts in bin/, as it names them.
SERVER_FILES = ("runner.py", "protocol.py", "lists.py", "lists.tsv", "mac_only.tsv", "cleanup.sh", "shield.nft")
WRAPPER = Path(__file__).resolve().parent / "harness_runner.py"


PROC_HEADER = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"


def DEFAULT_HARNESS(gate):
    """The direct launch (no systemd-run on the Mac), the stand-in gate, and a floor this Mac's disk clears."""
    proc = Path(gate).parent / "proc-net"
    proc.mkdir(exist_ok=True)
    for name in ("tcp", "tcp6"):  # nothing listening but this account's own
        if not (proc / name).exists():
            (proc / name).write_text(PROC_HEADER)
    return {"launch": "direct", "gate": str(gate), "min_free": 1, "proc": str(proc)}

FAKE_SSH = r'''#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
log = Path(os.environ["FAKE_SSH_LOG"])
args = sys.argv[1:]
words = args[args.index("--") + 2:]
with log.open("a") as fh:
    fh.write(json.dumps(args) + "\n")
if os.environ.get("FAKE_SSH") == "down":
    dest = args[args.index("--") + 1]
    sys.stderr.write("ssh: connect to host %s port 22: Connection refused\n" % dest.split("@")[-1])
    sys.exit(255)
data = sys.stdin.buffer.read()
if words[:1] == ["run"]:
    n = len(list(Path(os.environ["FAKE_SSH_LOG"]).parent.glob("sent-*.bundle")))
    (log.parent / ("sent-%d.bundle" % n)).write_bytes(data)
env = {"PATH": os.environ["PATH"], "HOME": os.environ["FAKE_REMOTE_HOME"]}  # what sshd passes, and no more
if words:
    env["SSH_ORIGINAL_COMMAND"] = " ".join(words)
r = subprocess.run([sys.executable, os.environ["FAKE_WRAPPER"], os.environ["FAKE_RUNNER"], os.environ["FAKE_HARNESS"]],
                   input=data, env=env)
sys.exit(r.returncode)
'''


def sh(cmd, cwd, env=None, check=True, input=None):
    p = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, input=input, shell=isinstance(cmd, str))
    if check and p.returncode != 0:
        raise AssertionError(f"{cmd} failed: {p.stdout!r}\n{p.stderr!r}")
    return p


def out(cmd, cwd, env=None):
    return sh(cmd, cwd, env).stdout.decode().strip()


@pytest.fixture
def world(tmp_path):
    home = tmp_path / "home"
    data = home / ".ospreyflow" / "slice-line"
    (data / "records" / "S1").mkdir(parents=True)
    env = {**os.environ, "HOME": str(home), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t.invalid"}
    for k in ("OSPREY_SLICE_HOME", "OSPREY_SEAT", "OSPREY_SLICE", "SSH_ORIGINAL_COMMAND"):
        env.pop(k, None)
    repo = tmp_path / "repo"
    lines = repo / "OspreyFlow_Build/scripts/slice_line"
    shutil.copytree(LINE, lines, ignore=shutil.ignore_patterns("tests", "__pycache__"))
    (repo / ".gitignore").write_text("OspreyFlow_Build/marketing_site/client_names.local.sha256\n")
    (repo / "OspreyFlow_Build/process/lanes/v062").mkdir(parents=True)
    (repo / "OspreyFlow_Build/process/lanes/v062/README.md").write_text("records\n")
    (repo / "shared.txt").write_text("main's line\n")
    sh(["git", "init", "-q", "-b", "main"], repo, env)
    sh("git add -A && git commit -qm 'chore: the world'", repo, env)
    sh(["git", "switch", "-q", "-c", "lane/slice-S1"], repo, env)
    (repo / "feature.txt").write_text("the slice's work\n")
    sh("git add feature.txt && git commit -qm 'feat: S1'", repo, env)
    tip = out(["git", "rev-parse", "HEAD"], repo)
    sh(["git", "switch", "-q", "main"], repo, env)
    (repo / "main-later.txt").write_text("main moved on\n")
    sh("git add main-later.txt && git commit -qm 'docs: main moves'", repo, env)
    rec = data / "records" / "S1"
    (rec / "frozen.json").write_text(json.dumps({"branch": "lane/slice-S1", "acceptance": "true"}))
    (rec / "state.json").write_text(json.dumps({"phase": "verified", "tip": tip}))
    # the fake server: the runner installed as install.sh installs it (bin/ and data/), and the fake ssh
    remote = tmp_path / "remote" / "osprey-early"
    (remote / "bin").mkdir(parents=True)
    (remote / "data").mkdir()
    (remote / "home").mkdir()
    for f in SERVER_FILES:
        shutil.copy(DEMO / f, remote / "bin" / f)
    sshbin = tmp_path / "sshbin"
    sshbin.mkdir()
    (sshbin / "ssh").write_text(FAKE_SSH)
    (sshbin / "ssh").chmod(0o755)
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps({"exit": 0}))
    harness = tmp_path / "harness.json"
    harness.write_text(json.dumps(DEFAULT_HARNESS(gate)))
    key = home / "keys" / "early"
    key.parent.mkdir(parents=True)
    key.write_text("not a key: the fake ssh reads no key\n")
    env.update(PATH=f"{sshbin}{os.pathsep}{env['PATH']}", FAKE_SSH_LOG=str(tmp_path / "ssh.log"),
               FAKE_REMOTE_WORK=str(remote / "data"), FAKE_REMOTE_HOME=str(remote / "home"),
               FAKE_RUNNER=str(remote / "bin" / "runner.py"), FAKE_WRAPPER=str(WRAPPER), FAKE_HARNESS=str(harness))
    w = {"tmp": tmp_path, "home": home, "data": data, "repo": repo, "lines": lines, "env": env, "tip": tip,
         "remote": remote, "gate": gate, "harness": harness, "key": key, "py": sys.executable,
         "setting": data / "demo-server.json"}
    setting(w)
    return w


def setting(w, **kw):
    s = {"host": "early-box.example.invalid", "user": "osprey-early", "key_file": str(w["key"]), "poll_seconds": 0,
         "max_wait_minutes": 1, **kw}
    w["setting"].write_text(json.dumps(s))
    return s


def early(w, *args, env=None):
    return sh([w["py"], str(w["lines"] / "early_warning.py"), *args], w["repo"], {**w["env"], **(env or {})},
              check=False)


def gate(w, **spec):
    w["gate"].write_text(json.dumps(spec))


def ssh_calls(w):
    f = w["tmp"] / "ssh.log"
    return [json.loads(ln) for ln in f.read_text().splitlines()] if f.exists() else []


def note(w, tip=None):
    return w["repo"] / "OspreyFlow_Build/process/lanes/v062/early_warning" / f"S1-{(tip or w['tip'])[:8]}.md"


def runner(w, command, stdin=b"", harness=None, env=None):
    """runner.py as sshd's forced command runs it (no arguments, the asked-for words in SSH_ORIGINAL_COMMAND), through
    the tests' own wrapper; `harness` replaces fields of the default harness file for this call only."""
    h = w["tmp"] / ("harness-%s.json" % uuid.uuid4().hex[:12])  # its own: a job it starts reads it later
    h.write_text(json.dumps({**DEFAULT_HARNESS(w["gate"]), **(harness or {})}))
    e = {"PATH": os.environ["PATH"], "HOME": str(w["remote"] / "home"), **(env or {})}
    if command is not None:
        e["SSH_ORIGINAL_COMMAND"] = command
    return subprocess.run([sys.executable, str(WRAPPER), str(w["remote"] / "bin" / "runner.py"), str(h)], input=stdin,
                          env=e, capture_output=True)
