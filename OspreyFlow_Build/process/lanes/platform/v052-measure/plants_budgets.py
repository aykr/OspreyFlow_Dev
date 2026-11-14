# ruff: noqa: E501
"""ADR-149 Amendment 2's budgets in the timer: one plant per check, each at its real call site, each
run red, then restored (rule 15). Run from the worktree root, offline on closed ports."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPT = ROOT / "OspreyFlow_Core/scripts/measure_search.py"
SPEC = ROOT / "OspreyFlow_Build/spec/06_DECISIONS.md"
TEST = "tests/test_measure_search.py"

PLANTS = [
    ("M1's any-over-2-s check removed", SCRIPT,
     '        if over is not None and max(times) > over:', '        if False:', "over_two_seconds"),
    ("the timer's M3 failure figure laxer than the table's", SCRIPT,
     '"names": {"measure": "M3", "budget_ms": 1000.0, "fail_ms": 2000.0}',
     '"names": {"measure": "M3", "budget_ms": 1000.0, "fail_ms": 2500.0}', "both_ways"),
    ("the table's M4 failure figure changed alone", SPEC,
     "| `fulltext` | ≤ 1.5 s | p95 > 3 s |", "| `fulltext` | ≤ 1.5 s | p95 > 4 s |", "both_ways"),
    ("a timed class with no row in the table", SPEC,
     "| `exact` | ≤ 1 s | p95 > 2 s |", "| no (dropped) | ≤ 1 s | p95 > 2 s |", "both_ways"),
    ("a run handed a figures file again", SCRIPT,
     '    parser.add_argument("--n", type=int, default=200)',
     '    parser.add_argument("--budgets")\n    parser.add_argument("--n", type=int, default=200)', "no_file_of_its_own"),
    ("full text sent to the suggestion route", SCRIPT,
     'SUGGEST_CLASSES = frozenset({"suggest"})', 'SUGGEST_CLASSES = frozenset({"suggest", "fulltext"})', "judged_at_m4"),
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
