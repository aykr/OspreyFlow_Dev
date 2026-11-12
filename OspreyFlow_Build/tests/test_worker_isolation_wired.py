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
