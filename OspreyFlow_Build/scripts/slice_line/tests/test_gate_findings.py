"""The gate's findings never count the acceptance command's expected red on the base (LINE_FIXES_3_BRIEF.md, 1c).

BL6 (19 November 2026) was refused with "2 tests": one the real failure, the other the acceptance command's expected
red on the base, a collection error (`cannot import name 'client_name_check'`), from the red-before run earlier in the
same merge log. fixtures/red_before_and_one_gate_failure.log is a merge log in the shape merge_slice.run writes it (a
`$ <command>   (in <tree>)` header per run; the red-before run in the `slice-<ID>-before-*` tree), modelled on that
case. The merge itself runs as the conductor runs it, in a throwaway repository.
"""
from __future__ import annotations

import json
from pathlib import Path

from test_gates import built, main_sha, merge, sh, verified, world  # noqa: F401  (world is a fixture)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
LOG = (FIXTURES / "red_before_and_one_gate_failure.log").read_text()
REAL = "test_scans.py::test_the_real_scan_map_names_every_pure_walker_and_nothing_stale"


def findings(w, text):
    """merge_slice.gate_findings, run as the merge script's own module in the throwaway repository."""
    f = w["tmp"] / "log-under-test.log"
    f.write_text(text)
    code = (f"import sys, json; sys.path.insert(0, {str(w['lines'])!r}); import merge_slice as m; "
            f"print(json.dumps(m.gate_findings(open({str(f)!r}).read())))")
    names, fs = json.loads(sh([w["py"], "-c", code], w["repo"], w["env"]).stdout)
    return names, fs


def test_gate_findings_count_the_real_failure_and_not_the_expected_red_before(world):
    names, fs = findings(world, LOG)
    assert names == [REAL], names
    assert len(fs) == 1 and "client_name_check.py" in fs[0]["what"] and "cannot import" not in fs[0]["what"], fs


def test_gate_findings_of_a_log_with_only_the_expected_red_are_none(world):
    only_before = LOG.split("\n$ /opt/uv/bin/uv sync --frozen   (in /var/folders/xx/T/slice-BL6-merge-")[0]
    assert "ERROR ../OspreyFlow_Build/tests/test_client_name_check.py" in only_before
    assert findings(world, only_before) == ([], [])


def test_gate_findings_a_merge_refused_by_the_gate_counts_one_test_not_two(world):
    """The merge's own log: its red-before run prints a collection error, as BL6's did; the gate fails one test."""
    w = world
    accept = ("test -f feature.txt || { echo 'ERROR ../OspreyFlow_Build/tests/test_client_name_check.py'; "
              "echo \"E   ImportError: cannot import name 'client_name_check' from 'tools'\"; exit 1; }")
    wt, tip = built(w, accept=accept)
    verified(w, wt, tip)
    gate_log = w["tmp"] / "gate-part.log"
    gate_log.write_text(LOG.split("$ make -k ci", 1)[1])
    before = main_sha(w)
    p = merge(w, gate="2", gate_log=str(gate_log))
    assert p.returncode == 1 and "full gate is red" in p.stderr, p.stderr
    st = json.loads((w["data"] / "records/S1/state.json").read_text())
    assert st["refused_tests"] == 1, st
    rec = json.loads((w["data"] / f"records/S1/verify-gate-{tip}.json").read_text())
    assert [f["file"] for f in rec["findings"]] == ["test_scans.py"], rec["findings"]
    assert main_sha(w) == before


def test_gate_findings_a_merge_whose_only_red_is_the_expected_one_merges(world):
    w = world
    accept = "test -f feature.txt || { echo 'ERROR ../OspreyFlow_Build/tests/test_client_name_check.py'; exit 1; }"
    wt, tip = built(w, accept=accept)
    verified(w, wt, tip)
    p = merge(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "ERROR ../OspreyFlow_Build/tests/test_client_name_check.py" in \
        (w["data"] / "records/S1" / json.loads((w["data"] / "records/S1/merged.json").read_text())["gate_run"]).read_text()
