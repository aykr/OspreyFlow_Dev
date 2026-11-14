# ruff: noqa: E501
"""M9, the fallback (measure_search.measure_fallback): one plant per check at its real
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
    ("a fallback that says nothing taken as one that says so", SCRIPT,
     '                elif not answer.get("limited") or not (answer.get("limited_reason") or "").strip():',
     "                elif False:", "late_silent_or_absent and silent"),
    ("the timeout not applied", SCRIPT,
     "            if ms > within[route]:", "            if False:", "late_silent_or_absent and slow"),
    ("an index's answer taken for the fallback", SCRIPT,
     '                if answer.get("source") != "fallback":', "                if False:",
     "late_silent_or_absent and stuck"),
    ("the index's return not waited for", SCRIPT,
     "    if recovered_s is None:\n", "    if False:\n", "late_silent_or_absent and never_back"),
    ("OpenSearch started again only when all went well", SCRIPT,
     "    finally:\n        start()\n", "    except Exception:\n        raise\n    start()\n",
     "started_again_when"),
    ("a session that never had the index measured anyway", SCRIPT,
     '    if before is None or before.get("source") not in ("index",):', "    if False:", "never_had"),
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
