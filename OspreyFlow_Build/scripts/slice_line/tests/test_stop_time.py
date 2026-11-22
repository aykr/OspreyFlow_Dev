"""The builder's Stop hook never outlives its installed limit (the owner's word of 21 November 2026). Claude Code
cancels a hook that runs past its `timeout`, and the builder's session then ends with no record: until this fix the
hook was installed at 1800 s while stop_check.py gave each of the checks, the acceptance and the scans 1500 s.

Now the hook's limit is stop_check.HOOK_TIMEOUT_S, which install.sh reads. Every command the hook runs shares one
allowance a margin under it; each gets only what is left. A command cut off (with every process it started) is red,
and the slice's record says which command, after how long, and why (stop-timeout-<commit>.json, and the words the
builder is given back).
"""
from __future__ import annotations

import importlib.util
import json
import re
import time

from test_gates import SRC, sh, started, stop_gate, world  # noqa: F401  (world is a fixture)
from test_register_everywhere import install

V062 = "OspreyFlow_Build/process/lanes/v062"


def stop_check_module():
    spec = importlib.util.spec_from_file_location("stop_check_src", SRC / "stop_check.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_the_whole_allowance_and_its_margin_fit_inside_the_hooks_installed_limit():
    m = stop_check_module()
    assert m.TIMEOUT_S <= m.ALLOWANCE_S and m.ALLOWANCE_S + m.MARGIN_S <= m.HOOK_TIMEOUT_S, \
        (m.TIMEOUT_S, m.ALLOWANCE_S, m.MARGIN_S, m.HOOK_TIMEOUT_S)
    assert m.MARGIN_S >= 30


def test_install_sh_takes_the_hooks_limit_from_stop_check(world):
    w = world
    f = w["lines"] / "stop_check.py"
    f.write_text(re.sub(r"^HOOK_TIMEOUT_S = \d+", "HOOK_TIMEOUT_S = 2400", f.read_text(), count=1, flags=re.M))
    p = install(w)
    assert p.returncode == 0, p.stdout + p.stderr
    s = json.loads((w["data"] / "settings.json").read_text())
    stop = [h for e in s["hooks"]["Stop"] for h in e["hooks"] if h["command"].endswith("stop_check.py")]
    assert [h["timeout"] for h in stop] == [2400], stop


def frozen_with(w, checks):
    tsv = w["repo"] / V062 / "slices.tsv"
    tsv.write_text(tsv.read_text().replace("sh accept.sh\ttrue", f"sh accept.sh\t{checks}"))
    sh("git commit -qam 'slice row'", w["repo"], w["env"])
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    return wt


def committed(w, wt, accept):
    (wt / "accept.sh").write_text(accept + "\n")
    sh("git add accept.sh && git commit -qm 'feat: S1'", wt, w["env"])
    return sh("git rev-parse HEAD", wt).stdout.strip()


def test_commands_that_together_pass_the_allowance_are_cut_off_inside_it_and_the_record_says_so(world):
    w = world
    wt = frozen_with(w, "sleep 3")
    tip = committed(w, wt, "sleep 3")
    w["env"]["OSPREY_STOP_ALLOWANCE_SECONDS"] = "5"
    t0 = time.monotonic()
    out = stop_gate(w, wt)
    took = time.monotonic() - t0
    assert took < 8, took                                          # inside the allowance, not 3 + 3 and on
    assert out and out["decision"] == "block", out
    assert "acceptance was cut off after" in out["reason"] and "allowance of 5 s" in out["reason"], out["reason"]
    rec = w["data"] / "records/S1"
    cut = json.loads((rec / f"stop-timeout-{tip}.json").read_text())
    assert cut["commit"] == tip and cut["allowance_s"] == 5, cut
    # the acceptance cut off, then the three project checks of the owner's file 005 not run (no time left)
    assert [(c["name"], c["run"]) for c in cut["cut"]] == [("acceptance", True)] + [(n, False) for n in ["route-coverage-check", "test-file-coverage-check", "mypy"]], cut
    assert cut["cut"][0]["by"] == "allowance" and 1 <= cut["cut"][0]["after_s"] <= 4, cut
    assert (rec / "red_stops").read_text() == "1" and not (rec / f"tests-{tip}.json").exists()


def test_a_command_whose_children_hold_its_output_is_still_ended_on_time(world):
    """A shell's child that keeps the output pipe open (here `sleep 30` under `sh accept.sh`) is ended with it."""
    w = world
    wt = frozen_with(w, "true")
    tip = committed(w, wt, "sleep 30")
    w["env"]["OSPREY_STOP_ALLOWANCE_SECONDS"] = "3"
    t0 = time.monotonic()
    out = stop_gate(w, wt)
    took = time.monotonic() - t0
    assert took < 9, took                                          # not the 10 s a pipe wait would add
    assert out and "acceptance was cut off after" in out["reason"], out
    assert json.loads((w["data"] / f"records/S1/stop-timeout-{tip}.json").read_text())["cut"][0]["name"] == "acceptance"


def test_a_command_left_with_no_time_is_not_run_and_the_record_names_it(world):
    w = world
    wt = frozen_with(w, "sleep 5")
    tip = committed(w, wt, "exit 0")
    w["env"]["OSPREY_STOP_ALLOWANCE_SECONDS"] = "2"
    out = stop_gate(w, wt)
    assert out and "checks was cut off after" in out["reason"] and "acceptance was not run" in out["reason"], out
    cut = json.loads((w["data"] / f"records/S1/stop-timeout-{tip}.json").read_text())["cut"]
    assert [(c["name"], c["run"]) for c in cut] == [("checks", True), ("acceptance", False)] + \
        [(n, False) for n in ["route-coverage-check", "test-file-coverage-check", "mypy"]], cut


def test_a_stop_inside_the_allowance_writes_no_timeout_record(world):
    w = world
    wt = frozen_with(w, "true")
    tip = committed(w, wt, "exit 0")
    assert stop_gate(w, wt) is None
    assert (w["data"] / f"records/S1/tests-{tip}.json").exists()
    assert not list((w["data"] / "records/S1").glob("stop-timeout-*.json"))
