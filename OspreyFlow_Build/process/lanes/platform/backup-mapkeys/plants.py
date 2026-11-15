# ruff: noqa: E501
"""The map key file never in a cloud-platform set (ADR-147 decision 1; rules-b's find, 15 November 2026): one
plant per thing the fix does, at its call site in `services/api/platform_backup.py`, run red against
`tests/cloud_platform_backup/test_platform_backup_map_keys.py`, then the file put back from the text saved before
the plant (never from git). Run from the worktree root after a commit, offline on closed ports."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORE = ROOT / "OspreyFlow_Core"
FILE = CORE / "services/api/platform_backup.py"
TEST = "../OspreyFlow_Build/tests/cloud_platform_backup/test_platform_backup_map_keys.py"
PLANTS = [
    ("the claims run takes the whole folder (0246f9b's behaviour)",
     "            size, digest, taken = bucket.put_tree(key, folder, LEFT_OUT.get(name, ()))\n",
     "            size, digest, taken = bucket.put_tree(key, folder)\n", "never_the_map_key_file"),
    ("a restore puts a set's key file back",
     "            for never in kept:\n                (staging / never).unlink(missing_ok=True)\n",
     "", "puts_none_there"),
    ("a restore moves the claim's own key file aside with the rest",
     "                    if entry.name not in (LOST_FOUND, staging.name, archive.name, before.name, *kept):\n",
     "                    if entry.name not in (LOST_FOUND, staging.name, archive.name, before.name):\n",
     "keeps_the_deployment_s_own"),
    ("restore-claims names no provider",
     "            if keys := map_keys_to_enter(settings.claims_folder):\n",
     "            if keys := []:\n", "names_each_provider"),
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
