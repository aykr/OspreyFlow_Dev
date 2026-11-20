"""A gate that fails only because a registry or a download could not be reached is retried once, and is never the
slice's fault (LINE_FIXES_3_BRIEF.md, 1d).

SE3's first merge attempt (19 November 2026) failed at `opentofu-check`: registry.opentofu.org, TLS handshake timeout.
The full gate runs here as merge_slice.full_gate runs it, in the suite's merge tree (test_gates.gate) with make and uv
stood in: make prints OpenTofu's own error for a registry it cannot reach and make's own error line for the target, as
`make -k ci` prints them. The merge then runs as the conductor runs it, with the gate's outcome stood in.
"""
from __future__ import annotations

import json

import pytest

from test_gates import built, gate, main_sha, merge, run_gate, sh, verified, world  # noqa: F401  (fixtures)

TOFU_TIMEOUT = """Initializing provider plugins...
- Finding hashicorp/kubernetes versions matching "~> 2.31"...
╷
│ Error: Failed to query available provider packages
│
│ Could not retrieve the list of available versions for provider hashicorp/kubernetes: could not connect to
│ registry.opentofu.org: failed to request discovery document: Get
│ "https://registry.opentofu.org/.well-known/terraform.json": net/http: TLS handshake timeout
╵
make: *** [opentofu-check] Error 1"""
OUR_FAILURE = """=========================== short test summary info ============================
FAILED ../OspreyFlow_Build/tests/test_admin_sections.py::test_each_section_s_routes_need_its_right[people] - AssertionError
1 failed, 812 passed in 61.02s
make: *** [core-check] Error 1"""
UV_DOWNLOAD = """error: Failed to download `numpy==2.1.3`
  Caused by: error sending request for url (https://files.pythonhosted.org/packages/numpy-2.1.3.whl)
  Caused by: client error (Connect)
  Caused by: tcp connect error: Connection reset by peer (os error 54)"""


def network_make(g, net_fails=1, ours="", uv_fails=0):
    """make: `make -k ci` prints the registry timeout for its first `net_fails` runs (and `ours`, a failure of our
    own, beside it), then passes; `make test` passes. uv sync fails its first `uv_fails` downloads."""
    t = g["tmp"]
    runs = t / "make-runs.txt"
    (t / "tofu.txt").write_text(TOFU_TIMEOUT + "\n")
    (t / "ours.txt").write_text(ours + "\n")
    (t / "uvdl.txt").write_text(UV_DOWNLOAD + "\n")
    (g["bin"] / "make").write_text(f"""#!/bin/sh
echo "$*" >> {runs}
if [ "$*" = "-k ci" ]; then
  n=$(grep -c '^-k ci$' {runs})
  if [ "$n" -le {net_fails} ]; then
    {'cat ' + str(t / 'ours.txt') if ours else ':'}
    cat {t / 'tofu.txt'}
    echo "make: Target 'ci' not remade because of errors."
    exit 2
  fi
fi
exit 0
""")
    uvruns = t / "uv-runs.txt"
    (g["bin"] / "uv").write_text(f"""#!/bin/sh
echo "$*" >> {uvruns}
if [ "$1" = sync ]; then
  n=$(grep -c '^sync' {uvruns})
  if [ "$n" -le {uv_fails} ]; then cat {t / 'uvdl.txt'}; exit 2; fi
  mkdir -p .venv/bin && cp "{g['bin'] / 'uv.python'}" .venv/bin/python
fi
exit 0
""")
    return runs, uvruns


def make_runs(runs):
    return runs.read_text().splitlines() if runs.exists() else []


def test_network_a_gate_red_only_for_a_registry_timeout_is_retried_once_and_green_merges(gate):
    g = gate
    runs, _ = network_make(g, net_fails=1)
    code, calls, log = run_gate(g)
    assert code == 0, log
    assert make_runs(runs) == ["-k ci", "-k ci", "test"], make_runs(runs)        # the failed step only, once
    assert "RETRY" in log and "make -k ci" in log and "registry.opentofu.org" in log, log
    retries = json.loads((g["tmp"] / "gate.retries.json").read_text())
    assert [r["step"] for r in retries] == ["make -k ci"] and "TLS handshake timeout" in retries[0]["why"], retries


@pytest.mark.parametrize("ours", [OUR_FAILURE, OUR_FAILURE.rsplit("\n", 1)[0],
                                  "ruff check: 3 errors (E501, F401, F841)\nmake: *** [lint-tools] Error 1"],
                         ids=["a-failed-test-and-its-target", "a-failed-test-alone", "a-failed-target-of-ours-alone"])
def test_network_a_registry_timeout_beside_a_failing_test_of_ours_is_not_retried(gate, ours):
    g = gate
    runs, _ = network_make(g, net_fails=1, ours=ours)
    code, calls, log = run_gate(g)
    assert code == 2, log
    assert make_runs(runs) == ["-k ci", "test"], make_runs(runs)                # never retried on a failed test
    assert "RETRY" not in log


def test_network_two_timeouts_in_a_row_give_kind_network(gate):
    g = gate
    runs, _ = network_make(g, net_fails=2)
    code, calls, log = run_gate(g)
    assert code == 5, log                                                       # NETWORK: not the slice's fault
    assert make_runs(runs) == ["-k ci", "-k ci"], make_runs(runs)
    assert "NETWORK" in log


def test_network_a_download_that_fails_while_the_gate_builds_its_environment_is_retried_once(gate):
    g = gate
    runs, uvruns = network_make(g, net_fails=0, uv_fails=1)
    code, calls, log = run_gate(g)
    assert code == 0, log
    assert [ln for ln in uvruns.read_text().splitlines() if ln.startswith("sync")] == ["sync --frozen"] * 2
    assert "RETRY" in log and "uv sync" in log
    runs, uvruns = network_make(g, net_fails=0, uv_fails=99)
    (g["tree"] / "OspreyFlow_Core/.venv").exists() and sh("rm -rf OspreyFlow_Core/.venv", g["tree"])
    code, calls, log = run_gate(g)
    assert code == 5, log


def test_network_the_merge_records_kind_network_as_no_fault_of_the_slice(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    st_before = json.loads((w["data"] / "records/S1/state.json").read_text())
    before = main_sha(w)
    p = merge(w, gate="5")
    assert p.returncode == 1 and "network" in p.stderr and "not the slice" in p.stderr, p.stderr
    assert main_sha(w) == before
    st = json.loads((w["data"] / "records/S1/state.json").read_text())
    assert st["phase"] == st_before["phase"] and st["round"] == st_before["round"] and "refused_for" not in st, st
    assert not (w["data"] / f"records/S1/verify-gate-{tip}.json").exists()      # no finding to the builder
    recs = [json.loads(f.read_text()) for f in (w["data"] / "records/S1").glob("refusal-network-*.json")]
    assert len(recs) == 1 and recs[0]["kind"] == "network" and recs[0]["tip"] == tip, recs


def test_network_a_retry_that_went_green_is_named_in_the_merge_record(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    retried = [{"step": "make -k ci", "why": "net/http: TLS handshake timeout"}]
    env = {**w["env"], "TEST_GATE": "0", "TEST_GATE_RETRIES": json.dumps(retried)}
    p = sh([w["py"], str(w["lines"] / "merge_slice.py"), "merge", "S1"], w["repo"], env, check=False)
    assert p.returncode == 0, p.stdout + p.stderr
    done = json.loads((w["data"] / "records/S1/merged.json").read_text())
    assert done["retried"] == retried, done
