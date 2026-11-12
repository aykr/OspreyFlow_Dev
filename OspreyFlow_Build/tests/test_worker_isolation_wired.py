"""The per-worker store plugin is loaded by the root conftest, not by a flag on one make target.

`tests/worker_isolation.py` (admin's T1 part 4) gives each pytest-xdist worker its own stores. Part 4 loaded it
with `-p tests.worker_isolation` in `make test` alone, so a live run through `stack_lease.sh live`, a lane's own
`pytest -n 4`, or CI's job without that flag ran its workers against one shared set of stores. Part 5 puts it in the
root conftest's `pytest_plugins` (`process/lanes/admin/conftest-T1p4.diff`, a shared file sent as a diff), and
`makefile-T1p4.diff` drops the flag. The plugin is a no-op without `-n`.

**Red whatever is on the command line** (the orchestrator's review of part 5, must-fix 3): `has_plugin` alone is
satisfied by `-p tests.worker_isolation`, so it cannot tell the conftest diff was missed. The first case reads the root
conftest's own `pytest_plugins`, which no flag changes.
"""

from __future__ import annotations

import pytest


def test_the_root_conftest_names_the_worker_isolation_plugin() -> None:
    import tests.conftest as root

    assert "tests.worker_isolation" in root.pytest_plugins, (
        "the root conftest's pytest_plugins does not name tests.worker_isolation "
        "(process/lanes/admin/conftest-T1p4.diff); a -p flag on one make target is not enough"
    )


def test_the_worker_isolation_plugin_is_registered(pytestconfig: pytest.Config) -> None:
    assert pytestconfig.pluginmanager.has_plugin("tests.worker_isolation"), (
        "tests.worker_isolation is not registered"
    )


def test_make_tests_own_arguments_without_the_flag_load_the_plugin_under_xdist() -> None:
    """The orchestrator's review of part 5, should-fix 8: pytest as `make test` runs it (its own `-c` and pytest.ini),
    with no `-p tests.worker_isolation`, at `-n 2 --dist loadgroup`, on one case under `tests/` (so the root conftest
    is read, as it is for every file of the suite): the controller prints the plugin's own header. Red with the
    conftest diff missed, whatever is on the command line."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    build = Path(__file__).resolve().parents[1]
    core = build.parent / "OspreyFlow_Core"
    target = f"{Path(__file__).resolve()}::test_the_root_conftest_names_the_worker_isolation_plugin"
    # Offline, so it makes no store and needs none of the Valkey databases an enclosing run (make test's own, up to
    # all 15) has taken: no lane, no forced stores, and the enclosing run's count of databases taken cleared.
    dropped = ("PYTEST_ADDOPTS", "PYTEST_XDIST_WORKER", "OSPREY_LANE", "OSPREY_WORKER_STORES",
               "OSPREY_WORKER_VALKEY_TAKEN")  # fmt: skip
    env = {k: v for k, v in os.environ.items() if k not in dropped}
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-c", str(build / "pytest.ini"), "-p", "no:cacheprovider",
         "-n", "2", "--dist", "loadgroup", target],
        cwd=core, env=env, capture_output=True, text=True, timeout=300,
    )  # fmt: skip
    headers = [line for line in ran.stdout.splitlines() if line.startswith("worker_isolation: ")]
    assert headers and headers[0].startswith("worker_isolation: 2 workers") and "no stores made" in headers[0], (
        f"exit {ran.returncode}\n{ran.stdout[-1500:]}\n{ran.stderr[-1500:]}"
    )
