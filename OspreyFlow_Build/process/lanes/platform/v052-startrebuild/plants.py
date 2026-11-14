# ruff: noqa: E501
"""`ospreyflow start --build` rebuilds the search index (route S9; ADR-150 Amendment 2): one plant
per thing the fix does, each planted at its real call site in `scripts/refresh.py`, run red against
`tests/test_refresh_search_rebuild.py`, then the file put back from the text saved before the plant
(never from git, rule 15). Run from the worktree root after a commit, offline on closed ports, with
OspreyFlow_Core's own venv."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORE = ROOT / "OspreyFlow_Core"
FILE = CORE / "scripts/refresh.py"
TEST = "../OspreyFlow_Build/tests/test_refresh_search_rebuild.py"
CALL = '    _search_index_rebuilt(directory / "compose.yaml", compose, run)\n'
FIRST_UP = '    run([*compose, "up", "-d", "--wait"])\n    if proxy_changed:\n'
REGISTER = "    identity = _identity_origin(directory / \"deployment.env\")\n"
PLANTS = [
    ("start --build never rebuilds (main's behaviour)", [(CALL, "")], "rebuilds_the_index or fails"),
    ("the rebuild right after the first up, before the theme's restart",
     [(CALL, ""), (FIRST_UP, FIRST_UP.replace("    if proxy_changed:\n", CALL + "    if proxy_changed:\n"))],
     "rebuilds_the_index"),
    ("the rebuild before the sign-in accounts are registered",
     [(CALL, ""), (REGISTER, CALL + REGISTER)], "fails"),
    ("a rebuild whatever compose renders",
     [("    if not search_rebuild.renders_opensearch(compose_file):\n        return\n", "")], "without_opensearch"),
    ("a failed rebuild in the compose call's own words",
     [("    except RefreshFailed as failed:\n        raise RefreshFailed(\n            f\"The stack is up and",
       "    except ValueError as failed:\n        raise RefreshFailed(\n            f\"The stack is up and")], "fails"),
]
env = {**os.environ, "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
       "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
env.pop("OSPREY_LANE", None)
saved = FILE.read_text(encoding="utf-8")
red = 0
for i, (what, edits, k) in enumerate(PLANTS, 1):
    text = saved
    for old, new in edits:
        assert text.count(old) == 1, (what, old)
        text = text.replace(old, new)
    FILE.write_text(text, encoding="utf-8")
    try:
        env["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp()
        done = subprocess.run([str(CORE / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST, "-k", k],
                              check=False, cwd=CORE, env=env, capture_output=True, text=True)
        last = done.stdout.strip().splitlines()[-1]
        state = "RED" if done.returncode != 0 and "failed" in last else "GREEN (the plant was not caught)"
        red += state == "RED"
        print(f"plant {i}: {what}\n  {TEST} -k '{k}': {state} ({last})")
    finally:
        FILE.write_text(saved, encoding="utf-8")
print(f"{red}/{len(PLANTS)} red")
raise SystemExit(0 if red == len(PLANTS) else 1)
