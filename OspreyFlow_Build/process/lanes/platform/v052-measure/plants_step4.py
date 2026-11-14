# ruff: noqa: E501
"""Step 4's stack runner (step4_stack.py): one plant per check at its real
call site, each run red, then restored (rule 15). Run from the worktree root, offline on closed ports."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
RUNNER = ROOT / "OspreyFlow_Build/process/lanes/platform/v052-measure/step4_stack.py"
TEST = "tests/test_step4_stack.py"
PLANTS = [
    ("the Conduit bound to every interface", RUNNER,
     '    return ["uvicorn", "services.api.app:app", "--host", "127.0.0.1", "--port", str(port)]',
     '    return ["uvicorn", "services.api.app:app", "--host", "0.0.0.0", "--port", str(port)]', "loopback"),
    ("a setting's value on the command line", RUNNER,
     '    return [arg for n in names for arg in ("-e", n)]',
     '    return [arg for n in names for arg in ("-e", f"{n}={environment[n]}")]', "no_value_reaches"),
    ("the Conduit's limits typed, not the manifest's", RUNNER,
     '        f"--cpus={cpus}", f"--memory={memory}"', '        "--cpus=4", f"--memory={memory}"', "poc_manifest"),
    ("the probe's read taken as a pass", RUNNER,
     '    if probed == 200:\n        return "a subject granted nothing read the case: the grants are not what is measured"\n',
     "", "stops_a_run"),
    ("M10 asked as the measuring subject", RUNNER,
     '        "OSPREY_MEASURE_PART_TOKEN": tokens[by_use["part"][0]],',
     '        "OSPREY_MEASURE_PART_TOKEN": tokens[by_use["measure"][0]],', "each_use"),
    ("a control without R", RUNNER,
     '         "codes": ["P", "C", "R"], "use": "control"}', '         "codes": ["P", "C"], "use": "control"}', "rules_granted"),
    ("each user's id left to Keycloak", RUNNER,
     '            "id": s["username"],\n', "", "principal_id_is_its_name"),
    ("the run's folder put into a name", RUNNER,
     '    last = run.rstrip("/").rsplit("/", 1)[-1].lower()', '    last = run.lower()', "names_docker_takes"),
    ("a poc setting lost without being named", RUNNER,
     '    env = {k: v for k, v in poc.items() if k not in DROPPED}',
     '    env = {k: v for k, v in poc.items() if k not in DROPPED and k != "OSPREY_ANALYTICS_ENGINE"}',
     "poc_s_own_settings"),
    ("the stack's hosts left as the cluster's", RUNNER,
     '        "ARCADEDB_HOST": loopback, "CLICKHOUSE_HOST": loopback, "OPENSEARCH_HOST": loopback,',
     '        "ARCADEDB_HOST": loopback,', "poc_s_own_settings"),
    ("the poc's directories left unwritable", RUNNER,
     '"--tmpfs", f"{w}:rw,uid=10001,gid=10001,mode=0700"', '"--tmpfs", f"{w}:ro"', "directories_writable"),
    ("the poc's files not mounted", RUNNER,
     '        *(a for host, at in mounts for a in ("-v", f"{host}:{at}:ro")),\n', "", "own_files_where"),
    ("the realm's users left as the deployment's", RUNNER,
     '    realm["users"] = realm_users()\n    return realm', "    return realm", "subjects_alone"),
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
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST, "-k", k],
                              cwd=ROOT / "OspreyFlow_Build", env=env, capture_output=True, text=True)
        last = done.stdout.strip().splitlines()[-1]
        state = "RED" if done.returncode != 0 and "failed" in last else "GREEN (the plant was not caught)"
        red += state == "RED"
        print(f"plant {i}: {what}\n  {TEST} -k '{k}': {state} ({last})")
    finally:
        path.write_text(text, encoding="utf-8")
print(f"{red}/{len(PLANTS)} red")
sys.exit(0 if red == len(PLANTS) else 1)
