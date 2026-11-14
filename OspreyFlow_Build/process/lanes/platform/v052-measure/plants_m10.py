# ruff: noqa: E501
"""M10's echo and floor (the orchestrator's ruling of 14 November 2026, on rules' first M10 results):
one plant per thing the fix does, each at its call site in `scripts/measure_search.py` (or the live
gate's), run red, then the file put back from the text saved before the plant (never from git). Run
from the worktree root after a commit, offline on closed ports, with OspreyFlow_Core's own venv (the
platform worktree's: `VENV` below)."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORE = ROOT / "OspreyFlow_Core"
VENV = Path(os.environ.get("VENV", "/Users/ayankar/dev/osprey-wt/platform/OspreyFlow_Core/.venv"))
MEASURE = CORE / "scripts/measure_search.py"
GATE = ROOT / "OspreyFlow_Build/tests/perf/test_search_budget_live.py"
TEST = "../OspreyFlow_Build/tests/test_measure_search.py"
PLANTS = [
    (
        "the echo read as the answer (main's behaviour)",
        MEASURE,
        [
            (
                '        texts = _answer_strings(answer, leak["query"])\n',
                "        texts = list(_strings(answer))\n",
            )
        ],
        "own_echo",
    ),
    (
        "whatever is under `query` left out, sent or not",
        MEASURE,
        [('    if answer.get("query") == sent:\n', '    if "query" in answer:\n')],
        "not_the_query_sent",
    ),
    (
        "an unreached control failed as before",
        MEASURE,
        [("            indeterminate.append(\n", "            failures.append(\n")],
        "indeterminate or 90_percent",
    ),
    (
        "no floor: indeterminate cases leave the file met",
        MEASURE,
        [("    elif reached < REACHED_AT_LEAST * len(cases):\n", "    elif reached < 0:\n")],
        "90_percent",
    ),
    (
        "the floor at 80%",
        MEASURE,
        [("REACHED_AT_LEAST = 0.9\n", "REACHED_AT_LEAST = 0.8\n")],
        "90_percent",
    ),
    (
        "the floor read before the leaks",
        MEASURE,
        [
            (
                '    if failures:\n        verdict = "not met"\n    elif reached < REACHED_AT_LEAST * len(cases):\n        verdict = "unmeasured"\n',
                '    if reached < REACHED_AT_LEAST * len(cases):\n        verdict = "unmeasured"\n    elif failures:\n        verdict = "not met"\n',
            )
        ],
        "whatever_share",
    ),
    (
        "the live gate passing an unmeasured file",
        GATE,
        [
            (
                '    assert found["verdict"] == "met", (\n',
                '    assert found["verdict"] in ("met", "unmeasured"), (\n',
            )
        ],
        "fails_an_unmeasured",
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
for i, (what, path, edits, k) in enumerate(PLANTS, 1):
    saved = path.read_text(encoding="utf-8")
    text = saved
    for old, new in edits:
        assert text.count(old) == 1, (what, old)
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
    try:
        env["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp()
        done = subprocess.run(
            [
                str(VENV / "bin/python"),
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                TEST,
                "-k",
                k,
            ],
            check=False,
            cwd=CORE,
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
        print(f"plant {i}: {what}\n  {TEST} -k '{k}': {state} ({last})")
    finally:
        path.write_text(saved, encoding="utf-8")
print(f"{red}/{len(PLANTS)} red")
raise SystemExit(0 if red == len(PLANTS) else 1)
