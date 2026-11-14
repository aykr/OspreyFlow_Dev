# ruff: noqa: E501
"""Step 4's token life and refused-token stop (the rerun on d, 14 November 2026): one plant per
check at its real call site, each run red, then restored (rule 15). Run from the worktree root,
offline on closed ports."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
RUNNER = ROOT / "OspreyFlow_Build/process/lanes/platform/v052-measure/step4_stack.py"
MEASURE = ROOT / "OspreyFlow_Core/scripts/measure_search.py"
GATE = ROOT / "OspreyFlow_Build/tests/perf/test_search_budget_live.py"
STACK, TIMER = "tests/test_step4_stack.py", "tests/test_measure_search.py"
PLANTS = [
    (
        "the realm left at Keycloak's 300 s",
        RUNNER,
        '        "accessTokenLifespan": TOKEN_LIFE_S,\n',
        "",
        STACK,
        "life_longer",
    ),
    (
        "a short-lived token let through",
        RUNNER,
        "if life < TOKEN_LIFE_NEEDED_S}",
        "if life < 0}",
        STACK,
        "shorter_than",
    ),
    (
        "a 401 timed as one more error",
        MEASURE,
        "        if error.code == 401:\n",
        "        if error.code == 0:\n",
        TIMER,
        "stops_the_measure",
    ),
    (
        "a 401 in M10 read as reaching nothing",
        MEASURE,
        "        if error.code == 401:\n",
        "        if error.code == 0:\n",
        TIMER,
        "stops_m10",
    ),
    (
        "the live gate measuring on past a 401",
        GATE,
        '            pytest.exit(f"step 4: {refused}", returncode=3)\n',
        "            raise\n",
        TIMER,
        "stops_the_whole_run",
    ),
    (
        "a failed control's error hidden by its ids",
        MEASURE,
        "answer does not name {error}, so",
        "answer does not name {leak['never_ids']}, so",
        TIMER,
        "errs",
    ),
]
env = {
    **os.environ,
    "ARCADEDB_HTTP_PORT": "59991",
    "POSTGRES_PORT": "59992",
    "POSTGRES_PASSWORD": "throwaway",
    "VALKEY_PORT": "59993",
    "CLICKHOUSE_HTTP_PORT": "59994",
}
env.pop("OSPREY_LANE", None)
red = 0
for i, (what, path, old, new, test, k) in enumerate(PLANTS, 1):
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, what
    path.write_text(text.replace(old, new), encoding="utf-8")
    try:
        env["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp()
        done = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", test, "-k", k],
            check=False,
            cwd=ROOT / "OspreyFlow_Build",
            env=env,
            capture_output=True,
            text=True,
        )
        last = done.stdout.strip().splitlines()[-1]
        state = (
            "RED"
            if done.returncode != 0 and "failed" in last
            else "GREEN (the plant was not caught)"
        )
        red += state == "RED"
        print(f"plant {i}: {what}\n  {test} -k '{k}': {state} ({last})")
    finally:
        path.write_text(text, encoding="utf-8")
print(f"{red}/{len(PLANTS)} red")
sys.exit(0 if red == len(PLANTS) else 1)
