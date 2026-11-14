"""The local-lite job loop's offline plants: each one violation, run alone against test_lite_job_loop.py
with a fresh PYTHONPYCACHEPREFIX on closed ports, then restored. A MISS (text not found, or nothing
selected) is not red. The loop itself is shown red and green live."""
import os
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE.parents[3]
CORE = BUILD.parent / "OspreyFlow_Core"
RENDER, APP, WM = "harness/render.py", "services/api/app.py", "services/api/worker_main.py"
TEST = "../OspreyFlow_Build/tests/services/api/test_lite_job_loop.py"
PLANTS = [
    ("small_told_service", RENDER, "_PROFILES_WITH_A_WORKER = frozenset({Profile.CLUSTER.value, Profile.CLOUD_PLATFORM.value})", "_PROFILES_WITH_A_WORKER = frozenset({Profile.CLUSTER.value, Profile.CLOUD_PLATFORM.value, Profile.SMALL.value})", "rendered_job_loop and small"),
    ("cluster_told_conduit", RENDER, "_PROFILES_WITH_A_WORKER = frozenset({Profile.CLUSTER.value, Profile.CLOUD_PLATFORM.value})", "_PROFILES_WITH_A_WORKER = frozenset({Profile.CLOUD_PLATFORM.value})", "rendered_job_loop and cluster"),
    ("env_line_dropped", RENDER, "        f\"OSPREY_JOB_WORKER={job_worker_place(config.profile.value)}\",\n", "", "rendered_job_loop and lite"),
    ("conduit_loops_when_unset", APP, "    return (os.environ if environ is None else environ).get(\"OSPREY_JOB_WORKER\") == \"conduit\"", "    return (os.environ if environ is None else environ).get(\"OSPREY_JOB_WORKER\") != \"service\"", "only_where_the_render"),
    ("compute_not_registered", WM, "        \"compute_metric\": \"services.api.compute_routes:run_compute_metric_job\",\n", "", "enqueues"),
    ("pattern_not_registered", WM, "        \"pattern_match\": \"services.api.patterns:run_pattern_match_job\",\n", "", "enqueues"),
]
CLOSED = {"ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
          "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
env = {k: v for k, v in os.environ.items() if k != "OSPREY_LANE"} | CLOSED
for name, path, old, new, k in PLANTS:
    f = CORE / path
    src = f.read_text(encoding="utf-8")
    record = HERE / f"plant_{name}.txt"
    if src.count(old) != 1:
        record.write_text(f"PLANT MISS {name}\n"); print("MISS", name); continue
    f.write_text(src.replace(old, new), encoding="utf-8")
    try:
        r = subprocess.run([str(CORE / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c",
                            "../OspreyFlow_Build/pytest.ini", "-m", "not live", TEST, "-k", k],
                           cwd=CORE, env=env | {"PYTHONPYCACHEPREFIX": tempfile.mkdtemp()}, capture_output=True,
                           text=True, timeout=300)
    finally:
        f.write_text(src, encoding="utf-8")
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith(("FAILED", "E   ")) or " passed" in ln or " failed" in ln]
    state = {0: "GREEN (not caught)", 5: "MISS (nothing selected)"}.get(r.returncode, "RED")
    record.write_text(f"# plant: {name} ({path}); fresh PYTHONPYCACHEPREFIX; closed ports; -k {k}\n# {state}\n" + "\n".join(lines[-6:]) + "\n")
    print(name, state, lines[-1] if lines else "")
