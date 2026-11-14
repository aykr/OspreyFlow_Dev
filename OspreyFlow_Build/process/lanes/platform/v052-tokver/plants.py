# ruff: noqa: E501
"""ADR-148 Amendment 18 in R1's Entra stand-in (platform-b's standin_v1.diff) and its run setting R1_ENTRA_TOKEN_VERSION: one plant per check at its real
call site, each run red, then restored (rule 15). Run from the worktree root, offline on closed ports."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SERVERS = ROOT / "OspreyFlow_Build/process/lanes/platform/gates/r1_kind_servers.py"
DRIVER = ROOT / "OspreyFlow_Build/process/lanes/platform/gates/r1_kind.py"
TEST = "tests"
PLANTS = [
    ("the stand-in's API tokens left v2.0 whatever the registration (the diff unapplied)", SERVERS,
     '        if str(config["api"].get("access_token_version", "2.0")) != "1.0":\n            return claims',
     '        return claims', "test_r1_entra_standin.py::test_a_v1_api_registration_gets_v1_access_tokens_as_entra_issues_them"),
    ("the person's v1 token without upn", SERVERS,
     '            v1["upn"] = v1["unique_name"] = claims["preferred_username"]', '            pass',
     "test_r1_entra_standin.py::test_a_v1_registration_s_glass_sign_in_keeps_its_id_token_at_v2"),
    ("the run's setting not read", DRIVER,
     '    version = os.environ.get("R1_ENTRA_TOKEN_VERSION", "2.0").strip() or "2.0"', '    version = "2.0"',
     "test_r1_kind_standins.py::test_the_entra_stand_in_s_api_tokens_are_v2_unless_a_run_asks_for_v1"),
    ("an unknown version let through", DRIVER,
     '    if version not in ("1.0", "2.0"):', '    if False:',
     "test_r1_kind_standins.py::test_a_token_version_entra_does_not_issue_is_refused_in_words"),
]
env = {**os.environ, "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
       "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
env.pop("OSPREY_LANE", None)
env.pop("R1_ENTRA_TOKEN_VERSION", None)
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
