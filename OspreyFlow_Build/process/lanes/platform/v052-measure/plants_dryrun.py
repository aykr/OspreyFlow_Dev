# ruff: noqa: E501
"""Step 4's dry run and its record (results_table.py, the live gate's results): one plant per check at its real
call site, each run red, then restored (rule 15). Run from the worktree root, offline on closed ports."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
TABLE = ROOT / "OspreyFlow_Build/process/lanes/platform/v052-measure/results_table.py"
LIVE = ROOT / "OspreyFlow_Build/tests/perf/test_search_budget_live.py"
TEST = "tests/test_step4_dry_run.py"
PLANTS = [
    ("a measure with no result shown met", TABLE,
     '        found = f"not measured here: {elsewhere}" if elsewhere else "**not measured**"',
     '        found = "**met**"', "never_shown_met"),
    ("a measure left out of the record", TABLE,
     '    ("M8", "Drift check, B\'s whole load", "its Job\'s peak and time"),\n', "", "every_measure_s_row"),
    ("M10's result not recorded", LIVE,
     '    _record("M10", found)\n', "", "every_measure_s_row"),
    ("a figure typed in the renderer, not the amendment's", TABLE,
     "            found[cells[0]] = (cells[3], cells[4])", '            found[cells[0]] = ("≤ 1 s", cells[4])',
     "figures_are_the_amendment_s"),
]
env = {**os.environ, "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
       "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
env.pop("OSPREY_LANE", None)
red = 0
for i, (what, path, old, new, k) in enumerate(PLANTS, 1):
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, what
    path.write_text(text.replace(old, new), encoding="utf-8")
    try:
        env["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp()
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST, "-k", k],
                              cwd=ROOT / "OspreyFlow_Build", env=env, capture_output=True, text=True)
        last = done.stdout.strip().splitlines()[-1]
        state = "RED" if done.returncode != 0 and "failed" in last else "GREEN (the plant was not caught)"
        red += state == "RED"
        print(f"plant {i}: {what}\n  {TEST} -k '{k}': {state} ({last})")
    finally:
        path.write_text(text, encoding="utf-8")
print(f"{red}/{len(PLANTS)} red")
sys.exit(0 if red == len(PLANTS) else 1)
