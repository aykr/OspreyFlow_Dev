# ruff: noqa: E501
"""The fallback's words (docs' v0.5.2 sweep, EARLY_FACTS.md §4): one plant per place the words are
said, each that file put back to main's words alone, run red, then restored (rule 15). Run from the
worktree root after a commit, offline on closed ports."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
TEST = "tests/harness/test_search_fallback_words.py"
PLANTS = [
    ("the runbook's reduced-variant line", "OspreyFlow_Core/harness/render.py", "with_no_index"),
    ("the runbook's line when OpenSearch does not answer", "OspreyFlow_Core/harness/render.py", "does_not_answer"),
    ("Preflight's offer", "OspreyFlow_Core/harness/preflight/reduced.py", "preflight_offers"),
    ("the memory check's advice", "OspreyFlow_Core/harness/preflight/memory.py", "preflight_offers"),
    ("spec 05 §3", "OspreyFlow_Build/spec/05_DEPLOYMENT.md", "spec_05"),
]
env = {**os.environ, "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
       "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
env.pop("OSPREY_LANE", None)
red = 0
for i, (what, rel, k) in enumerate(PLANTS, 1):
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    main = subprocess.run(["git", "show", f"main:{rel}"], check=True, cwd=ROOT, capture_output=True, text=True).stdout
    path.write_text(main, encoding="utf-8")
    try:
        env["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp()
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST, "-k", k],
                              check=False, cwd=ROOT / "OspreyFlow_Build", env=env, capture_output=True, text=True)
        last = done.stdout.strip().splitlines()[-1]
        state = "RED" if done.returncode != 0 and "failed" in last else "GREEN (the plant was not caught)"
        red += state == "RED"
        print(f"plant {i}: {what} as on main\n  {TEST} -k '{k}': {state} ({last})")
    finally:
        path.write_text(text, encoding="utf-8")
print(f"{red}/{len(PLANTS)} red")
sys.exit(0 if red == len(PLANTS) else 1)
