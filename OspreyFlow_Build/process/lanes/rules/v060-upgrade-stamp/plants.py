"""Red first (rule 15) for the cached-upgrade trap (v0.6.0): each place the stamp must reach,
planted out alone, its test red, the file restored from its own saved text (never by git) and the
test green again. Offline, closed ports. Run from the repository root:

    PYTHONPYCACHEPREFIX=$(mktemp -d) OspreyFlow_Core/.venv/bin/python \\
        OspreyFlow_Build/process/lanes/rules/v060-upgrade-stamp/plants.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORE = ROOT / "OspreyFlow_Core"
BUILD = ROOT / "OspreyFlow_Build"
TESTS = "../OspreyFlow_Build/tests/test_upgrade_stamp.py"
LANE = BUILD / "process/lanes/rules/v060-upgrade-stamp"

#: (name, file, planted out, replacement, the test that must go red)
PLANTS = [
    ("U1 a Dockerfile without the stamp (Superset's ARG gone)", CORE / "deploy/superset/Dockerfile",
     "ARG OSPREY_UPGRADE_STAMP=\nRUN echo", "RUN echo",
     "test_every_upgrading_dockerfile_keys_its_upgrade_on_the_stamp[superset]"),
    ("U2 an upgrade step not naming the stamp (the worker's)", CORE / "services/worker/Dockerfile",
     'RUN echo "distribution fixes as of ${OSPREY_UPGRADE_STAMP:-an unstamped build}" && apt-get',
     "RUN apt-get",
     "test_every_upgrading_dockerfile_keys_its_upgrade_on_the_stamp[worker]"),
    ("U3 a Makefile build without the stamp", CORE / "Makefile",
     "docker build --pull --build-arg OSPREY_UPGRADE_STAMP=$(UPGRADE_STAMP) -f services/worker/",
     "docker build --pull -f services/worker/",
     "test_every_makefile_build_passes_the_day_s_stamp[OspreyFlow_Core]"),
    ("U4 a CI workflow build without the stamp (in the owner's diff)",
     LANE / "workflows_upgrade_stamp.diff",
     '+      - run: docker build --build-arg OSPREY_UPGRADE_STAMP="$(date -u +%F)" -f services/worker/',
     "+      - run: docker build -f services/worker/",
     "test_every_workflow_build_passes_the_day_s_stamp"),
    ("U5 ospreyflow start --build without the stamp", CORE / "scripts/refresh.py",
     'run([*compose, "build", "--pull", *upgrade_stamp.build_args()])',
     'run([*compose, "build", "--pull"])',
     "test_start_build_passes_the_stamp"),
    ("U6 the harness's apply building without the stamp", CORE / "harness/apply.py",
     '["build", "--pull", *upgrade_stamp.build_args()]', '["build", "--pull"]',
     "test_apply_passes_the_stamp_when_it_builds"),
    ("U7 the local release building without the stamp", BUILD / "tools/release_local.py",
     '"--pull", *upgrade_stamp.build_args(), "-f"', '"--pull", "-f"',
     "test_the_local_release_passes_the_stamp"),
]

ENV = {**os.environ, "OSPREY_PORTS_SLOT": "9", "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992",
       "POSTGRES_PASSWORD": "throwaway", "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}  # fmt: skip
ENV.pop("OSPREY_LANE", None)


def pytest(test: str | None = None) -> tuple[bool, str]:
    target = f"{TESTS}::{test}" if test else TESTS
    done = subprocess.run([".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-p",
                           "no:cacheprovider", "-q", target], cwd=CORE, env=ENV,
                          capture_output=True, text=True)  # fmt: skip
    lines = [x for x in done.stdout.splitlines() if x.strip()]
    return done.returncode == 0, lines[-1] if lines else done.stderr[-300:]


def main() -> int:
    ok, summary = pytest()
    print(f"built: {'GREEN' if ok else 'RED'} - {summary}")
    bad = 0 if ok else 1
    for name, path, old, new, test in PLANTS:
        text = path.read_text(encoding="utf-8")
        if text.count(old) != 1:
            print(f"{name}: NOT PLANTED - the text is not in the file once")
            bad += 1
            continue
        try:
            path.write_text(text.replace(old, new), encoding="utf-8")
            ok, summary = pytest(test)
            print(f"{name}: {'GREEN (a plant its test does not see)' if ok else 'RED'} - {summary}")
            bad += ok
        finally:
            path.write_text(text, encoding="utf-8")
    ok, summary = pytest()
    print(f"restored: {'GREEN' if ok else 'RED'} - {summary}")
    return 1 if bad or not ok else 0


if __name__ == "__main__":
    sys.exit(main())
