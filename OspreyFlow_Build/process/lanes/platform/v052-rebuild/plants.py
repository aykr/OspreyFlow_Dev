# ruff: noqa: E501
"""ADR-150 Amendment 2 (every path that brings v0.5.2 up rebuilds the index) and INSTALL.md's Entra count: one plant per check at its real
call site, each run red, then restored (rule 15). Run from the worktree root, offline on closed ports."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
APPLY = ROOT / "OspreyFlow_Core/harness/apply.py"
UPDATE = ROOT / "OspreyFlow_Core/harness/update.py"
RUNBOOKS = ROOT / "OspreyFlow_Core/harness/cloud_platform/runbooks.py"
TEST = "tests/harness"
PLANTS = [
    ("install's rebuild removed (main's)", APPLY,
     '        if search_rebuild.renders_opensearch(compose_file):\n            _run(',
     '        if False:\n            _run(', "test_apply_search_rebuild.py"),
    ("update's rebuild removed (main's)", UPDATE,
     '        if search_rebuild.renders_opensearch(directory / "compose.yaml"):',
     "        if False:", "test_update_apply.py"),
    ("step 5's rebuild removed (main's)", RUNBOOKS,
     '    if "searchIndex" in values:\n        rollouts += ', '    if False:\n        rollouts += ',
     "test_cloud_platform_search_rebuild.py"),
    ("the Entra count typed as two (main's)", RUNBOOKS,
     "    return 2 + int(config.reporting.superset) + int(config.reporting.sync)", "    return 2",
     "test_cloud_platform_entra_count.py"),
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
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"{TEST}/{k}"],
                              cwd=ROOT / "OspreyFlow_Build", env=env, capture_output=True, text=True)
        last = done.stdout.strip().splitlines()[-1]
        state = "RED" if done.returncode != 0 and "failed" in last else "GREEN (the plant was not caught)"
        red += state == "RED"
        print(f"plant {i}: {what}\n  {TEST}/{k}: {state} ({last})")
    finally:
        path.write_text(text, encoding="utf-8")
print(f"{red}/{len(PLANTS)} red")
sys.exit(0 if red == len(PLANTS) else 1)
