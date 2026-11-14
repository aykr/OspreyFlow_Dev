# ruff: noqa: E501
"""M6, the feed's lag (measure_search.measure_lag and the live file's M6 case): one plant per check at its real
call site, each run red, then restored (rule 15). Run from the worktree root, offline on closed ports."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPT = ROOT / "OspreyFlow_Core/scripts/measure_search.py"
LIVE = ROOT / "OspreyFlow_Build/tests/perf/test_search_budget_live.py"
SPEC = ROOT / "OspreyFlow_Build/spec/06_DECISIONS.md"
TEST = "tests/test_measure_search.py"
PLANTS = [
    ("a fallback answer holding the node counted as the index's", SCRIPT,
     '        if answer is not None and answer.get("source", "index") == "index":', '        if answer is not None:',
     "fallback_answering_the_node"),
    ("M6's failure figure not applied", SCRIPT,
     '    p95 = _percentile(times, 0.95)\n    why = []\n    if p95 > budget["fail_ms"]:',
     '    p95 = _percentile(times, 0.95)\n    why = []\n    if False:', "lag_over_the_failure_figure"),
    ("a refused draw not counted", SCRIPT,
     '            problem = f"the draw was refused ({error or made})"', '            problem = ""', "refused_draw"),
    ("the board made inside the loop, once per draw", SCRIPT,
     '    for i in range(warmup + n):\n        unique = f"m6{uuid.uuid4().hex[:12]}"',
     '    for i in range(warmup + n):\n        _ms, board, error = _send(base, f"/v1/investigations/{case}/boards", {"name": "M6"}, token)\n        unique = f"m6{uuid.uuid4().hex[:12]}"',
     "in_time_meets_m6"),
    ("the live file's M6 verdict dropped", LIVE,
     '    assert found["verdict"] == "met", f"M6 lag: {found[\'why\']}"', "    assert found", "fails_m6_when"),
    ("the table's M6 failure figure changed alone", SPEC,
     "| `lag` | ≤ 5 s | p95 > 30 s |", "| `lag` | ≤ 5 s | p95 > 40 s |", "both_ways"),
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
