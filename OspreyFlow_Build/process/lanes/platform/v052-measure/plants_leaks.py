# ruff: noqa: E501
"""M10, the leak test at scale (measure_search.measure_leaks and the live file's M10 case): one plant per check at its real
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
    ("the control dropped: a case reaching nothing hidden passes", SCRIPT,
     "        if control is None or unreached:", "        if control is None:", "cannot_reach"),
    ("the hidden ids not looked for", SCRIPT,
     "            if any(node in t for t in texts):", "            if False:", "seen_or_counted and id"),
    ("the hidden words not looked for", SCRIPT,
     "            if any(word.lower() in t for t in lowered):", "            if False:", "seen_or_counted and text"),
    ("the totals not compared", SCRIPT,
     '        if "expect_total" in leak and answer.get("total") != leak["expect_total"]:',
     '        if False:', "seen_or_counted and count"),
    ("a fallback answer taken as the index's", SCRIPT,
     '        if path.endswith("/search") and answer.get("source", "index") != "index":', "        if False:",
     "fallback_answer_is_not_the_index_s_for_m10"),
    ("no cases taken as a pass", SCRIPT,
     '    if not cases:\n        raise SystemExit("M10: no leak cases: the test would pass having asked nothing")', "",
     "no_leak_cases"),
    ("the live file's M10 verdict dropped", LIVE,
     '    assert found["verdict"] == "met", "M10: " + "; ".join(found["failures"][:20])', "    assert found",
     "fails_m10_on_a_leak"),
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
