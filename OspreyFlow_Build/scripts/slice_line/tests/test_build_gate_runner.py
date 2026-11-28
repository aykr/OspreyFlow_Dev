"""The owner's ask of 26 November 2026, item 2, the build account's side: `gate <ID>` takes a bundle of exactly one
ref, HEAD, the merge commit the Mac made and will land, and a detached job runs today's full gate on exactly that
commit: each `ci` prerequisite but core-check and client-name-check (the owner's hashed client list never leaves the
Mac), each of Core's `check` targets (harness-a11y once proved here), and make test, in CI's environment (ci.yml's
Python and Node, the closed store ports, the merger's slot), in this account's rootless Docker only. Its result, in the
early warning's shape, and its log are committed on build-results for the backup timer. Nothing is merged here.

The world is test_build_runner's (bw): make and git real; docker, uv, npm and node stood in, the stand-in docker
refusing as the real one does.
"""
from __future__ import annotations

import json
import os
import shutil
import socket

import pytest

from test_build_runner import KEEP, bw, done, forced, sh  # noqa: F401  (bw is a fixture)

GATE_BUILD_MK = """ci: core-check lint-tools opentofu-check client-name-check
core-check:
\t$(MAKE) -C ../OspreyFlow_Core check
lint-tools:
\t@echo lint-tools >> "$(MARKS)"; test -z "$(FAIL_LINT)" && { [ -z "$(SLOW_LINT)" ] || sleep 5; }
opentofu-check:
\t@echo opentofu-check >> "$(MARKS)"; docker run --rm alpine true
client-name-check:
\t@echo client-name-check >> "$(MARKS)"
test:
\t@echo "test $$OSPREY_PORTS_SLOT $$POSTGRES_PORT $$UV_PYTHON" >> "$(MARKS)"
\t@if [ -n "$(FAIL_TEST)" ]; then echo "FAILED ../OspreyFlow_Build/tests/test_x.py::test_it's_red - boom"; exit 1; fi
\t@if [ -n "$(SKIP_DOCKER)" ]; then echo "SKIPPED [1] ../OspreyFlow_Build/tests/test_d.py:3: a server-only test: it calls the docker CLI"; fi
"""
GATE_CORE_MK = """check: lint trivy harness-a11y
lint:
\t@echo lint >> "$(MARKS)"
trivy:
\t@echo trivy >> "$(MARKS)"; docker run --rm aquasec/trivy
harness-a11y:
\t@echo harness-a11y >> "$(MARKS)"
"""
CI_YML = 'env:\n  UV_PYTHON: "3.12"\njobs:\n  a:\n    steps:\n      - uses: actions/setup-node@v4\n        with: { node-version: "22" }\n'
UV = """#!/bin/sh
[ "$1 $2" = 'sync --frozen' ] || exit 2
mkdir -p .venv/bin
printf '#!/bin/sh\\necho "Python %s.9"\\n' "$UV_PYTHON" > .venv/bin/python
chmod +x .venv/bin/python
"""
NODE = '#!/bin/sh\necho "v${FAKE_NODE_MAJOR:-22}.11.0"\n'
GATE_KEEP = KEEP + ["FAIL_TEST", "FAIL_LINT", "SKIP_DOCKER", "FAKE_NODE_MAJOR", "SLOW_LINT"]
RAN_HERE = ["lint", "trivy", "harness-a11y", "lint-tools", "opentofu-check", "test"]


@pytest.fixture
def gw(bw):
    """bw, its Makefiles the gate's shape, and a merge commit the Mac made: main, the slice merged --no-ff."""
    w = bw
    fake = w["tmp"] / "bin"
    (fake / "uv").write_text(UV)
    (fake / "node").write_text(NODE)
    (fake / "node").chmod(0o755)
    m = w["mac"]
    for rel, text in (("OspreyFlow_Build/Makefile", GATE_BUILD_MK), ("OspreyFlow_Core/Makefile", GATE_CORE_MK),
                      (".github/workflows/ci.yml", CI_YML),
                      ("OspreyFlow_Build/scripts/lane_ports.tsv", "# lane\tslot\nmerger\t7\nplatform-b\t3\n")):
        (m / rel).parent.mkdir(parents=True, exist_ok=True)
        (m / rel).write_text(text)
    sh("git add -A && git commit -qm 'the gate makefiles' && git switch -qc merge-made-on-the-mac && "
       f"git merge -q --no-ff -m 'merge: slice S1' {w['tip']} && git switch -q main", m, w["env"])
    w["commit"] = sh(["git", "rev-parse", "merge-made-on-the-mac"], m, w["env"])
    w["base"] = sh(["git", "rev-parse", "main"], m, w["env"])
    return w


def gate_bundle(w, ref="merge-made-on-the-mac", head=True):
    """As build_gate.bundle makes it: the merge commit as HEAD, from a worktree holding it."""
    wt = w["tmp"] / "after"
    shutil.rmtree(wt, ignore_errors=True)
    sh(["git", "worktree", "add", "-q", "--detach", str(wt), ref], w["mac"], w["env"])
    b = w["tmp"] / "gate.bundle"
    b.unlink(missing_ok=True)
    sh(["git", "bundle", "create", "-q", str(b), "HEAD" if head else "refs/heads/main"], wt, w["env"])
    sh(["git", "worktree", "remove", "--force", str(wt)], w["mac"], w["env"])
    return b.read_bytes()


def gate(w, data=None, keep=None, harness=None, **extra):
    code, said = forced(w, "gate S1", gate_bundle(w) if data is None else data,
                        harness={"keep": GATE_KEEP + (keep or []), **(harness or {})}, **extra)
    assert code == 0 and said["state"] == "started", said
    return done(w, said["id"]), said


def committed(w, name):
    return sh(["git", "show", f"refs/heads/build-results:gates/S1/{w['commit']}.{name}"], w["clone"], w["env"])


def marks(w):
    return w["marks"].read_text().splitlines() if w["marks"].exists() else []


def test_gate_runs_todays_full_gate_on_exactly_the_commit_the_mac_made(gw):
    w = gw
    r, said = gate(w)
    assert r["verdict"] == "pass" and r["kind"] == "gate" and r["commit"] == w["commit"], r
    assert r["main"] == w["base"] == said["holds_main"] and r["tip"] == w["tip"], r
    assert r["tree"] == sh(["git", "rev-parse", f"{w['commit']}^{{tree}}"], w["mac"], w["env"]), r  # merged nowhere else
    ran = [m.split()[0] for m in marks(w)]
    assert ran == RAN_HERE, ran                                    # one make per target, the commit's own Makefiles
    assert sorted(r["passed_targets"]) == sorted(RAN_HERE), r
    assert {"name": "client-name-check", "why": "the owner's hashed client list never leaves the Mac"} \
        in r["not_run"]["targets"], r
    assert json.loads(committed(w, "json")) == r and "$ make test" in committed(w, "log")
    assert r["log"] == f"gates/S1/{w['commit']}.log"


def test_the_gate_runs_in_ci_s_environment_the_closed_ports_and_the_merger_s_slot(gw):
    w = gw
    gate(w)
    line = next(m for m in marks(w) if m.startswith("test "))
    assert line == "test 7 59992 3.12", line                       # the merger's slot; a closed port; ci.yml's Python


def test_a_red_test_is_a_fail_naming_it_and_every_other_target_still_runs(gw):
    w = gw
    r, _ = gate(w, FAIL_TEST="1")
    assert r["verdict"] == "fail" and "test" not in r["passed_targets"], r
    assert r["failing"]["tests"] == ["../OspreyFlow_Build/tests/test_x.py::test_it's_red"], r
    assert [m.split()[0] for m in marks(w)] == RAN_HERE


def test_a_red_target_is_a_fail_naming_it_and_the_rest_still_run(gw):
    w = gw
    r, _ = gate(w, FAIL_LINT="1")
    assert r["verdict"] == "fail" and "lint-tools" in r["failing"]["targets"], r
    assert "lint-tools" not in r["passed_targets"] and "test" in r["passed_targets"], r


def test_a_red_target_make_does_not_name_a_timed_out_one_is_named_failing(gw):
    w = gw
    r, _ = gate(w, harness={"target_seconds": 1}, SLOW_LINT="1")
    assert r["verdict"] == "fail" and "lint-tools" in r["failing"]["targets"], r
    assert {"target": "lint-tools", "exit": 124} == {k: v for k, v in r["steps"][3].items() if k != "seconds"}, r


def test_a_test_skipped_as_server_only_is_named_for_the_mac_to_run(gw):
    w = gw
    r, _ = gate(w, SKIP_DOCKER="1")
    assert r["not_run"]["docker_skipped"] == ["../OspreyFlow_Build/tests/test_d.py"], r
    assert "test" in r["passed_targets"], r                        # make test's own skips the Mac reruns (remainder)


def test_harness_a11y_stays_on_the_mac_until_it_is_proved_here(gw):
    w = gw
    (w["server"] / "bin/harness-a11y.ready").unlink()
    r, _ = gate(w)
    assert "harness-a11y" not in [m.split()[0] for m in marks(w)] and "harness-a11y" not in r["passed_targets"], r
    assert any(x["name"] == "harness-a11y" for x in r["not_run"]["targets"]), r


@pytest.mark.parametrize("how,words", [
    ("node", "not ci.yml's Node 22"), ("rootful", "does not answer as rootless")])
def test_nothing_runs_in_another_environment(gw, how, words):
    w = gw
    r, _ = gate(w, **({"FAKE_NODE_MAJOR": "20"} if how == "node" else {"FAKE_ROOTFUL": "1"}))
    assert r["verdict"] == "error" and words in r["words"] and r["passed_targets"] == [], r
    assert marks(w) == [], marks(w)


def test_nothing_runs_while_a_closed_store_port_listens_here(gw):
    w = gw
    srv = socket.socket()
    try:
        srv.bind(("127.0.0.1", 59991))
    except OSError:
        pytest.skip("59991 is in use on this machine")
    srv.listen(1)
    try:
        r, _ = gate(w)
    finally:
        srv.close()
    assert r["verdict"] == "error" and "ARCADEDB_HTTP_PORT 59991" in r["words"] and marks(w) == [], r


@pytest.mark.parametrize("how", ["main-and-a-slice", "not-a-merge"])
def test_a_bundle_of_anything_but_one_merge_commit_as_head_is_refused_and_nothing_kept(gw, how):
    w = gw
    if how == "main-and-a-slice":     # the checks verb's shape
        b = w["tmp"] / "b.bundle"
        sh(["git", "bundle", "create", "-q", str(b), "refs/heads/main", "refs/heads/lane/slice-S1"], w["mac"], w["env"])
        data = b.read_bytes()
    else:                             # HEAD, but the slice's own tip, no merge
        data = gate_bundle(w, ref="lane/slice-S1")
    code, said = forced(w, "gate S1", data)
    assert said["state"] == "refused" and said["reason"] == "bundle-shape", said
    assert not (w["data"] / "jobs").exists() or not list((w["data"] / "jobs").iterdir())
    assert marks(w) == []


@pytest.mark.parametrize("cmd", ["gate", "gate S1 now", "gate s1", "gate S1;id"])
def test_gate_in_any_other_shape_is_refused(gw, cmd):
    code, said = forced(gw, cmd, gate_bundle(gw))
    assert said["state"] == "refused" and said["reason"] == "shape", said
