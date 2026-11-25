"""017, item 1 (the owner's answer of 25 November 2026): early_warning.py sends the same bundle's shape, main's tip and
the slice's, to the build account's forced command, `checks <ID>`, at the moment it sends the early warning; the
result comes back only through the backup repository, never over SSH. Without the build setting nothing is sent; an
unreachable or refusing build account never changes the early warning's result.

Run as the conductor runs it, against both real runners behind the fake ssh (conftest.py): the early warning's, and
build_server/runner.py installed in a fake build account (bin/ and data/, a clone in its home), with docker, uv and
npm stood in (the stand-in docker answers only on that account's socket, and as rootless).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time

import pytest

from conftest import LINE, early, note, out, sh, ssh_calls

BUILD_MK = "ci: opentofu-check\nopentofu-check:\n\t@echo tofu\n"
DOCKER = """#!/bin/sh
[ "$DOCKER_HOST" = "unix://$XDG_RUNTIME_DIR/docker.sock" ] || exit 1
[ "$1" = info ] && echo '["name=rootless"]'
exit 0
"""
WRAP = """import json, sys
runner_py, harness = sys.argv[1], json.loads(open(sys.argv[2]).read())
sys.path.insert(0, runner_py.rsplit("/", 1)[0])
import runner
runner.LAUNCH = "direct"
runner.WORKER = [sys.executable, __file__, runner_py, sys.argv[2], "_work"]
runner.SYSTEM_SOCKETS = ()
sys.exit(runner.main(sys.argv[3:]))
"""
HOST = "build-box.example.invalid"


@pytest.fixture
def bw(world):
    w = world
    repo = w["repo"]
    (repo / "OspreyFlow_Build/Makefile").write_text(BUILD_MK)
    (repo / ".github/workflows").mkdir(parents=True)
    (repo / ".github/workflows/ci.yml").write_text('env:\n  UV_PYTHON: "3.12"\n')
    (repo / "OspreyFlow_Core").mkdir()
    (repo / "OspreyFlow_Core/Makefile").write_text("check:\n")
    sh("git add -A && git commit -qm 'ci: the gate targets'", repo, w["env"])
    build = w["tmp"] / "remote" / "ospreyflow_build"
    home, fake, run = build / "home", w["tmp"] / "buildbin", w["tmp"] / "buildrun"
    for d in (build / "bin", home, fake, run):
        d.mkdir(parents=True)
    shutil.copy(LINE / "build_server/runner.py", build / "bin/runner.py")
    sh(["git", "init", "-q", "-b", "main", str(home / "ospreyflow")], w["tmp"], w["env"])  # its clone (results only)
    for name, text in (("docker", DOCKER), ("uv", "#!/bin/sh\nexit 0\n"), ("npm", "#!/bin/sh\nexit 0\n")):
        (fake / name).write_text(text)
        (fake / name).chmod(0o755)
    (w["tmp"] / "build_wrap.py").write_text(WRAP)
    (w["tmp"] / "build_harness.json").write_text("{}")
    w["env"].update(FAKE_BUILD_PATH=f"{fake}{os.pathsep}{os.environ['PATH']}", FAKE_BUILD_HOME=str(home),
                    FAKE_BUILD_RUN=str(run), FAKE_BUILD_WRAPPER=str(w["tmp"] / "build_wrap.py"),
                    FAKE_BUILD_RUNNER=str(build / "bin/runner.py"),
                    FAKE_BUILD_HARNESS=str(w["tmp"] / "build_harness.json"))
    key = w["home"] / "keys" / "build"
    key.write_text("not a key: the fake ssh reads no key\n")
    w["build_setting"] = w["data"] / "build-server.json"
    w["build_setting"].write_text(json.dumps({"host": HOST, "user": "ospreyflow_build", "key_file": str(key)}))
    w.update(build=build, build_clone=home / "ospreyflow")
    return w


def build_calls(w):
    return [c for c in ssh_calls(w) if c[c.index("--") + 1].startswith("ospreyflow_build@")]


def build_result(w, seconds=60):
    end = time.monotonic() + seconds
    while True:
        p = subprocess.run(["git", "show", f"refs/heads/build-results:results/S1/{w['tip']}.json"],
                           cwd=str(w["build_clone"]), capture_output=True, text=True)
        if p.returncode == 0:
            return json.loads(p.stdout)
        assert time.monotonic() < end, "no build result"
        time.sleep(0.1)


def test_the_build_checks_are_sent_with_the_early_warning_and_check_the_same_candidate(bw):
    w = bw
    p = early(w, "S1")
    assert p.returncode == 0, p.stdout + p.stderr
    calls = build_calls(w)
    assert len(calls) == 1 and calls[0][calls[0].index("--") + 2:] == ["checks", "S1"], calls
    sent = w["tmp"] / "build-sent-0.bundle"
    heads = dict(reversed(ln.split(" ", 1)) for ln in out(["git", "bundle", "list-heads", str(sent)],
                                                          w["repo"]).splitlines())
    assert heads == {"refs/heads/main": out(["git", "rev-parse", "main"], w["repo"]), "refs/heads/lane/slice-S1": w["tip"]}
    m = re.search(rb"sent \(run ([0-9a-f]{16});", p.stdout)
    assert m, p.stdout
    r = build_result(w)
    assert r["id"] == m.group(1).decode() and r["verdict"] == "pass" and r["passed_targets"] == ["opentofu-check"], r
    ew_tree = re.search(r"Candidate tree hash: `([0-9a-f]{40})`", note(w).read_text()).group(1)
    assert r["tree"] == ew_tree, (r["tree"], ew_tree)                     # the early warning's candidate, exactly
    held = json.loads((w["data"] / "early-warning/build-held.json").read_text())["main"]
    assert held == out(["git", "rev-parse", "main"], w["repo"])
    line = json.loads((w["data"] / "early-warning/build-sent.jsonl").read_text().splitlines()[-1])
    assert line["state"] == "started" and line["slice"] == "S1" and line["tip"] == w["tip"], line


def test_nothing_of_the_build_setting_reaches_the_terminal(bw):
    w = bw
    p = early(w, "S1")
    for v in (HOST, "ospreyflow_build", "keys/build"):
        assert v.encode() not in p.stdout + p.stderr, v


def test_without_the_build_setting_nothing_is_sent_and_the_early_warning_is_as_before(bw):
    w = bw
    w["build_setting"].unlink()
    p = early(w, "S1")
    assert p.returncode == 0 and b"Build checks: not sent (no build setting)" in p.stdout, p.stdout + p.stderr
    assert build_calls(w) == [] and "GREEN" in note(w).read_text()


@pytest.mark.parametrize("how,words", [
    ("down", b"no answer from the build account (ssh exit 255)"),
    ("busy", b"refused by the build account (busy)"),
    ("bad-setting", b"not sent (the build setting is not usable)"),
])
def test_an_unreachable_or_refusing_build_account_never_changes_the_early_warning(bw, how, words):
    w = bw
    env = {}
    if how == "down":
        env["FAKE_SSH_BUILD"] = "down"
    elif how == "busy":
        (w["tmp"] / "build_harness.json").write_text("{}")
        jobs = w["build"] / "data/jobs"
        for i in range(20):                                              # MAX_QUEUE jobs waiting
            (jobs / f"{i:016x}").mkdir(parents=True)
            (jobs / f"{i:016x}" / "job.json").write_text("{}")
    elif how == "bad-setting":
        w["build_setting"].write_text(json.dumps({"host": "not a host;", "user": "x", "key_file": "/nowhere"}))
    p = early(w, "S1", env=env)
    assert p.returncode == 0 and words in p.stdout, p.stdout + p.stderr
    assert "GREEN" in note(w).read_text()


def test_the_next_bundle_is_built_on_what_the_build_account_holds_and_in_full_when_it_has_lost_it(bw):
    w = bw
    assert early(w, "S1").returncode == 0
    build_result(w)
    assert early(w, "S1", "--again").returncode == 0
    empty = w["tmp"] / "empty.git"
    sh(["git", "init", "-q", "--bare", str(empty)], w["tmp"])
    second = w["tmp"] / "build-sent-1.bundle"
    assert sh(["git", "bundle", "verify", str(second)], empty, check=False).returncode != 0   # incremental
    shutil.rmtree(w["build"] / "data/source.git")                         # the build account lost its copy
    p = early(w, "S1", "--again")
    assert p.returncode == 0 and b"Build checks: sent" in p.stdout, p.stdout + p.stderr
    third, fourth = w["tmp"] / "build-sent-2.bundle", w["tmp"] / "build-sent-3.bundle"
    assert sh(["git", "bundle", "verify", str(third)], empty, check=False).returncode != 0    # refused, then
    assert sh(["git", "bundle", "verify", str(fourth)], empty, check=False).returncode == 0   # sent in full
