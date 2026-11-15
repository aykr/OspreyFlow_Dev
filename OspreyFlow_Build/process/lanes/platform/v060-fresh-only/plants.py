# ruff: noqa: E501
"""v0.6.0 is installed fresh (v0.6.0's item `rf`): one plant per call site and one in the rule itself,
each run red against `tests/harness/test_fresh_only.py`, then the file put back from the text saved
before the plant (never from git). Run from the worktree root after a commit, offline on closed ports."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORE = ROOT / "OspreyFlow_Core"
TEST = "../OspreyFlow_Build/tests/harness/test_fresh_only.py"
PLANTS = [
    ("update moves an earlier deployment onto v0.6.0 (7dd860e's behaviour)", CORE / "harness/update.py",
     "    if (why := fresh_only.refusal(current, tag)) is not None:\n", "    if (why := None) is not None:\n",
     "update_refuses"),
    ("an install over an earlier deployment goes ahead", CORE / "harness/apply.py",
     "        if previous_path.is_file():\n            from harness import fresh_only\n",
     "        if False:\n            from harness import fresh_only\n", "install_over_an_earlier"),
    ("the cloud-platform runbook has no check", CORE / "harness/cloud_platform/runbooks.py",
     "\n{_fresh_only(values)}", "", "runbook_refuses"),
    ("the runbook checks a fresh namespace as if it held a release", CORE / "harness/cloud_platform/runbooks.py",
     'if helm status "$RELEASE" -n "$NS" >/dev/null 2>&1; then', "if true; then", "fresh_namespace"),
    ("the rule lets a deployment that names no release through", CORE / "harness/fresh_only.py",
     "    if have is not None and have >= fresh:\n", "    if have is None or have >= fresh:\n", "the_rule"),
]
env = {**os.environ, "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
       "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
env.pop("OSPREY_LANE", None)
red = 0
for i, (what, path, old, new, k) in enumerate(PLANTS, 1):
    saved = path.read_text(encoding="utf-8")
    assert saved.count(old) == 1, what
    path.write_text(saved.replace(old, new), encoding="utf-8")
    try:
        env["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp()
        done = subprocess.run([str(CORE / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST, "-k", k],
                              check=False, cwd=CORE, env=env, capture_output=True, text=True)
        last = done.stdout.strip().splitlines()[-1]
        state = "RED" if done.returncode != 0 and "failed" in last else "GREEN (the plant was not caught)"
        red += state == "RED"
        print(f"plant {i}: {what}\n  -k '{k}': {state} ({last})")
    finally:
        path.write_text(saved, encoding="utf-8")
print(f"{red}/{len(PLANTS)} red")
raise SystemExit(0 if red == len(PLANTS) else 1)
