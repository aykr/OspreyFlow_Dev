# ruff: noqa: E501
"""The live budget gate (tests/perf/test_search_budget_live.py): one plant per check at the file's own lines, each
run red through the cases that run the file as step 6 does, then restored (rule 15)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
LIVE = ROOT / "OspreyFlow_Build/tests/perf/test_search_budget_live.py"
TEST = "tests/test_measure_search.py"
PLANTS = [
    ("the gate's verdict check dropped", '    assert found["verdict"] == "met", f"{found[\'measure\']} {query_class}: {found[\'why\']}"',
     "    assert found", "over_its_failure_figure"),
    ("a class with no queries passed unmeasured", '    assert queries, (',
     "    if not queries:\n        return\n    assert queries, (", "leaves_out"),
    ("the gate run without a named stack, against a default", '        pytest.skip(', '        return {name: os.environ.get(name, "") for name in _NAMED}\n        pytest.skip(', "no_stack_is_named"),
]
env = {**os.environ, "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
       "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
env.pop("OSPREY_LANE", None)
red = 0
for i, (what, old, new, k) in enumerate(PLANTS, 1):
    text = LIVE.read_text(encoding="utf-8")
    assert text.count(old) == 1, what
    LIVE.write_text(text.replace(old, new), encoding="utf-8")
    try:
        env["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp()
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST, "-k", k],
                              cwd=ROOT / "OspreyFlow_Build", env=env, capture_output=True, text=True)
        last = done.stdout.strip().splitlines()[-1]
        state = "RED" if done.returncode != 0 and "failed" in last else "GREEN (the plant was not caught)"
        red += state == "RED"
        print(f"plant {i}: {what}\n  {TEST} -k '{k}': {state} ({last})")
    finally:
        LIVE.write_text(text, encoding="utf-8")
print(f"{red}/{len(PLANTS)} red")
sys.exit(0 if red == len(PLANTS) else 1)
