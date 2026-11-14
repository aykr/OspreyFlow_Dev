# ruff: noqa: E501
"""The model timeouts as tunables in the cluster and cloud-platform renders (ADR-135 Amendment 13; the
orchestrator, 14 November 2026): one plant per thing the fix does, at its call site, run red, then the
file put back from the text saved before the plant (never from git). Run from the worktree root after a
commit, offline on closed ports, with OspreyFlow_Core's own venv."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORE = ROOT / "OspreyFlow_Core"
CLUSTER, RENDER = CORE / "harness/cluster.py", CORE / "harness/render.py"
B = "../OspreyFlow_Build/tests"
FOUR = [f"{B}/harness/test_cluster_render.py::test_every_secret_a_workload_reads_is_listed_for_the_install",
        f"{B}/harness/test_cloud_platform_poc.py::test_with_reporting_on_the_install_says_what_entra_s_administrator_registers_and_where_secrets_go",
        f"{B}/test_r1_kind_standins.py::test_the_terraform_stand_in_gives_reporting_s_variables_as_the_operator_would",
        f"{B}/test_r1_kind_standins.py::test_the_terraform_stand_in_makes_the_domains_secret_and_admits_what_its_policy_admits"]
NEW = f"{B}/harness/test_cluster_render.py::test_the_model_timeouts_reach_the_conduit_from_the_environment_at_their_defaults"
DEFAULTS = f"{B}/harness/test_cluster_render.py::test_the_rendered_model_timeouts_are_the_adapters_own_defaults"
PLANTS = [
    ("the timeouts left out of the cluster's environment (main's behaviour)", CLUSTER,
     "        environment.setdefault(name, seconds)\n", "        pass\n", [*FOUR, NEW], 5),
    ("the hosted timeout's default not the adapter's", RENDER,
     '    "OSPREY_HOSTED_MODEL_TIMEOUT_SECONDS": "120",\n', '    "OSPREY_HOSTED_MODEL_TIMEOUT_SECONDS": "60",\n', [NEW, DEFAULTS], 2),
]
env = {**os.environ, "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
       "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
env.pop("OSPREY_LANE", None)
red = 0
for i, (what, path, old, new, tests, expect) in enumerate(PLANTS, 1):
    saved = path.read_text(encoding="utf-8")
    assert saved.count(old) == 1, what
    path.write_text(saved.replace(old, new), encoding="utf-8")
    try:
        env["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp()
        done = subprocess.run([str(CORE / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests],
                              check=False, cwd=CORE, env=env, capture_output=True, text=True)
        last = done.stdout.strip().splitlines()[-1]
        state = "RED" if f"{expect} failed" in last else "NOT RED AS EXPECTED"
        red += state == "RED"
        print(f"plant {i}: {what}\n  {len(tests)} tests, {expect} expected red: {state} ({last})")
    finally:
        path.write_text(saved, encoding="utf-8")
print(f"{red}/{len(PLANTS)} red")
raise SystemExit(0 if red == len(PLANTS) else 1)
