# ruff: noqa: E501
"""R1's domain guard (step 6, the orchestrator, 15 November 2026): a plant each way at the call site in
`r1_kind.checks()`, run red against `tests/test_r1_kind_domain_guard.py`, then the file put back from the
text saved before the plant (never from git). Run from the worktree root after a commit, offline on closed
ports, with OspreyFlow_Core's own venv."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORE = ROOT / "OspreyFlow_Core"
FILE = ROOT / "OspreyFlow_Build/process/lanes/platform/gates/r1_kind.py"
TEST = "../OspreyFlow_Build/tests/test_r1_kind_domain_guard.py"
PLANTS = [
    ("the domain probed whatever the release searches with (main's behaviour): a v0.5.1-shaped config", "    if searches_with_opensearch():\n", "    if True:\n", "without_opensearch"),
    ("the domain never probed: a v0.5.2-shaped config", "    if searches_with_opensearch():\n", "    if False:\n", "with_opensearch_has"),
]
env = {**os.environ, "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
       "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
env.pop("OSPREY_LANE", None)
saved = FILE.read_text(encoding="utf-8")
red = 0
for i, (what, old, new, k) in enumerate(PLANTS, 1):
    assert saved.count(old) == 1, what
    FILE.write_text(saved.replace(old, new), encoding="utf-8")
    try:
        env["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp()
        done = subprocess.run([str(CORE / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST, "-k", k],
                              check=False, cwd=CORE, env=env, capture_output=True, text=True)
        last = done.stdout.strip().splitlines()[-1]
        state = "RED" if done.returncode != 0 and "1 failed" in last else "NOT RED AS EXPECTED"
        red += state == "RED"
        print(f"plant {i}: {what}\n  -k '{k}': {state} ({last})")
    finally:
        FILE.write_text(saved, encoding="utf-8")
print(f"{red}/{len(PLANTS)} red")
raise SystemExit(0 if red == len(PLANTS) else 1)
