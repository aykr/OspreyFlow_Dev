"""The owner's ask of 26 November 2026, item 2, the Mac's side (build_gate.py, merge_slice.py's step 5): with the
owner's switch gate_on_build on, and no early-warning green already counting, the merge sends the merge commit it made
to the build account (`gate <ID>`), reads the gate's result only from the backup repository, takes it only for exactly
that commit, its base and its tree, and runs on the Mac only what the build account did not prove (client-name-check
always). A red there is the merge's red, its findings the build account's log's, unless only a network step failed.
Anything short of a result for exactly this commit: the Mac runs the whole gate itself, as now. Main moves only on the
Mac, by fast-forward, to the commit tested.

The world: the line's own (test_gates), with the real build_server/runner.py behind a fake ssh (test_server_seat's sw),
its stand-in tools (uv, npm, node, docker) on the build account's PATH alone; the backup timer pushes the build
account's clone before each fetch the Mac makes. The Mac's own full gate is stood in (it records the targets it was
given: null is the whole gate).
"""
from __future__ import annotations

import json
import os

import pytest

from test_build_gate_runner import CI_YML, NODE, UV
from test_build_runner import DOCKER, KEEP
from test_gates import sh, world  # noqa: F401  (world is a fixture)
from test_server_counts import gate_plan
from test_server_seat import GIT_ID, calls, fake, sw  # noqa: F401  (sw is a fixture)
from test_gates import built, verified

BUILD_MK = """ci: core-check lint-tools opentofu-check client-name-check
core-check:
\t$(MAKE) -C ../OspreyFlow_Core check
lint-tools:
\t@echo lint-tools
opentofu-check:
\t@if [ -n "$(NET_DOWN)" ]; then echo "Error: Could not resolve host registry.opentofu.org"; exit 1; fi
\t@docker run --rm alpine true
client-name-check:
\t@echo client-name-check
test:
\t@if [ -n "$(FAIL_TEST)" ]; then echo "FAILED ../OspreyFlow_Build/tests/test_x.py::test_y - boom"; exit 1; fi
"""
CORE_MK = """check: lint typecheck
lint:
\t@echo lint
typecheck:
\t@echo typecheck
"""
TIMER = """def fetch() -> bool:
    import os as _os, subprocess as _s
    if _os.environ.get("TEST_BACKUP_TIMER"):  # the backup timer, in this copy only
        _s.run(_os.environ["TEST_BACKUP_TIMER"], shell=True)
"""


@pytest.fixture
def gm(sw):
    w = sw
    tools = w["tmp"] / "buildtools"
    tools.mkdir()
    for name, text in (("uv", UV), ("node", NODE), ("npm", "#!/bin/sh\n[ \"$1\" = ci ] || exit 2\n"), ("docker", DOCKER)):
        (tools / name).write_text(text)
        (tools / name).chmod(0o755)
    harness = w["tmp"] / "gate_harness.json"
    harness.write_text(json.dumps({"keep": KEEP + list(GIT_ID) + ["FAIL_TEST", "NET_DOWN"]}))
    fake(w, harness=str(harness), keep={**GIT_ID, "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}",
                                        "FAKE_DOCKER_LOG": str(w["tmp"] / "docker.log")})
    for rel, text in (("OspreyFlow_Build/Makefile", BUILD_MK), ("OspreyFlow_Core/Makefile", CORE_MK),
                      (".github/workflows/ci.yml", CI_YML),
                      ("OspreyFlow_Build/scripts/lane_ports.tsv", "# lane\tslot\nmerger\t7\n")):
        (w["repo"] / rel).parent.mkdir(parents=True, exist_ok=True)
        (w["repo"] / rel).write_text(text)
    sh("git add -A OspreyFlow_Build/Makefile OspreyFlow_Core/Makefile .github OspreyFlow_Build/scripts/lane_ports.tsv "
       "&& git commit -qm 'the gate makefiles'", w["repo"], w["env"])
    bg = w["lines"] / "build_gate.py"  # no waiting between polls, and the backup timer, in this copy only
    bg.write_text(bg.read_text().replace("GATE_WAIT_MINUTES = 150", "GATE_WAIT_MINUTES = 0.5")
                  .replace("POLL_SECONDS = 60", "POLL_SECONDS = 0.2").replace("def fetch() -> bool:\n", TIMER, 1))
    w["env"]["TEST_BACKUP_TIMER"] = f"git -C {w['clone']} push -q --force {w['backup']} 'refs/heads/*:refs/heads/*'"
    sh("git add -A OspreyFlow_Build/scripts/slice_line && git commit -qm 'test: the copies stood in'", w["repo"], w["env"])
    wt, tip = built(w)        # test_server_slot.ready, but the real early_warning.py: the merge imports nothing of it
    verified(w, wt, tip)
    f = w["data"] / "records/S1/state.json"
    f.write_text(json.dumps({**json.loads(f.read_text()), "phase": "verified", "tip": tip}))
    return w


def gate_switch(w, text="on\n"):
    (w["data"] / "gate_on_build").write_text(text)


def merged(w):
    f = w["data"] / "records/S1/merged.json"
    return json.loads(f.read_text()) if f.exists() else None


def main_sha(w):
    return sh("git rev-parse main", w["repo"]).stdout.strip()


def backup_result(w, commit):
    p = sh(["git", "--git-dir", str(w["backup"]), "show", f"build-results:gates/S1/{commit}.json"], w["tmp"], w["env"],
           check=False)
    return json.loads(p.stdout) if p.returncode == 0 else None


def test_a_build_pass_for_exactly_the_merge_commit_leaves_the_mac_only_what_it_did_not_prove(gm):
    w = gm
    gate_switch(w)
    p, plan, _ = gate_plan(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert plan == [["make", "-k", "client-name-check"]], plan              # the hashed client list stays on the Mac
    assert "gate S1" in calls(w), calls(w)
    m = merged(w)
    bg = m["build_gate"]
    assert bg["used"] is True and bg["verdict"] == "pass", bg
    assert bg["taken"] == ["lint-tools", "opentofu-check", "core:lint", "core:typecheck", "test"], bg
    r = backup_result(w, main_sha(w))                                       # main is exactly the commit the gate ran
    assert r and r["id"] == bg["run_id"] and r["commit"] == m["merge"] == main_sha(w), r
    assert r["main"] == m["base"], r


def test_with_the_switch_off_the_mac_runs_the_whole_gate_and_calls_nothing(gm):
    w = gm
    p, plan, _ = gate_plan(w)
    assert p.returncode == 0 and plan is None, (p.stderr, plan)
    assert not any(x.startswith("gate") for x in calls(w)), calls(w)
    assert merged(w)["build_gate"] == {"used": False, "why": "the owner's switch (gate_on_build) is off"}


@pytest.mark.parametrize("text", ["off\n", "yes\n", "on please\n", ""])
def test_only_on_turns_it_on(gm, text):
    w = gm
    gate_switch(w, text)
    p, plan, _ = gate_plan(w)
    assert plan is None and not any(x.startswith("gate") for x in calls(w)), calls(w)


def test_a_build_red_is_the_merges_red_with_the_build_accounts_findings(gm):
    w = gm
    gate_switch(w)
    fake(w, keep={**json.loads(w["fake_build"].read_text())["keep"], "FAIL_TEST": "1"})
    before = main_sha(w)
    p, plan, _ = gate_plan(w)
    assert p.returncode != 0 and "today's full gate is red" in p.stderr, p.stdout + p.stderr
    assert plan == "not run", plan                                          # the Mac's own gate never ran
    assert main_sha(w) == before
    tip = json.loads((w["data"] / "records/S1/state.json").read_text())["tip"]
    found = json.loads((w["data"] / f"records/S1/verify-gate-{tip}.json").read_text())["findings"]
    assert any("test_x.py::test_y" in json.dumps(f) for f in found), found
    log = sorted((w["data"] / "records/S1").glob("merge-*.log"))[-1].read_text()
    assert "the build account's gate" in log and "FAILED ../OspreyFlow_Build/tests/test_x.py::test_y" in log


def test_a_build_red_only_on_a_network_step_leaves_the_whole_gate_to_the_mac(gm):
    w = gm
    gate_switch(w)
    fake(w, keep={**json.loads(w["fake_build"].read_text())["keep"], "NET_DOWN": "1"})
    p, plan, _ = gate_plan(w)
    assert p.returncode == 0 and plan is None, (p.stdout + p.stderr, plan)
    assert merged(w)["build_gate"]["network_only"].startswith("Error: Could not resolve host"), merged(w)


@pytest.mark.parametrize("how,why", [
    ("down", "did not start the gate"), ("no-backup-push", "holds no result"),
    ("no-setting", "no usable build setting"), ("no-backup-named", "no backup repository named")])
def test_anything_short_of_a_result_for_this_commit_leaves_the_whole_gate_to_the_mac(gm, how, why):
    w = gm
    gate_switch(w)
    if how == "down":
        fake(w, down=True)
    elif how == "no-backup-push":
        w["env"].pop("TEST_BACKUP_TIMER")
        fake(w, no_backup=True)
    elif how == "no-setting":
        (w["data"] / "build-server.json").unlink()
    else:
        (w["data"] / "build_backup").unlink()
    p, plan, _ = gate_plan(w)
    assert p.returncode == 0 and plan is None, (how, p.stdout + p.stderr, plan)
    bg = merged(w)["build_gate"]
    assert bg["used"] is False and why in bg["why"], (how, bg)


@pytest.mark.parametrize("field,value,why", [
    ("commit", "0" * 40, "not the merge commit"), ("main", "1" * 40, "not the base"), ("tree", "2" * 40, "not the merge's"),
    ("verdict", "error", "it ended error"), ("runner", "someone", "not the build runner's"),
    ("slice", "S2", "not run")])
def test_a_result_not_exactly_this_merges_is_never_taken(gm, field, value, why):
    """The backup is where to read, never proof: the build account's result is checked field by field (its file
    name already holds the slice and commit, so a wrong one is written there by hand here)."""
    w = gm
    gate_switch(w)
    bg = w["lines"] / "build_gate.py"
    bg.write_text(bg.read_text().replace(
        "                if isinstance(r, dict) and r.get(\"id\") == rid:\n",
        f"                if isinstance(r, dict):\n                    r[{field!r}] = {value!r}\n"
        "                if isinstance(r, dict) and r.get(\"id\") == rid:\n", 1))
    sh("git commit -qam 'test: the backup result changed, in this copy'", w["repo"], w["env"])
    p, plan, _ = gate_plan(w)
    assert p.returncode == 0 and plan is None, (field, p.stdout + p.stderr, plan)
    assert why in merged(w)["build_gate"]["why"], merged(w)


def test_an_early_warning_green_that_counts_is_used_and_the_build_account_is_not_called(gm):
    from test_server_counts import green
    from test_server_slot import FAKE_EW, note, switch
    w = gm
    (w["lines"] / "early_warning.py").write_text(FAKE_EW)  # the early warning's fetch, stood in as test_server_slot does
    sh("git commit -qam 'test: the early warning stood in'", w["repo"], w["env"])
    w["env"]["TEST_EW_RESULTS"] = str(w["tmp"] / "ew")
    (w["tmp"] / "ew").mkdir(exist_ok=True)
    gate_switch(w)
    switch(w)
    tip = json.loads((w["data"] / "records/S1/state.json").read_text())["tip"]
    note(w, tip, headline="GREEN")
    green(w, tip, passed_targets=["lint-tools", "opentofu-check", "lint", "typecheck", "test"],
          not_run={"targets": [{"name": "client-name-check", "why": "x"}]})
    p, plan, server = gate_plan(w)
    assert p.returncode == 0 and server["counted"] is True, (p.stderr, server)
    assert not any(x.startswith("gate") for x in calls(w)) and "build_gate" not in merged(w), calls(w)
