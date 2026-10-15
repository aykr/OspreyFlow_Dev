"""Refuse to take over or tear down a deployment a test did not start (5 October 2026).

A live harness test renders `local-lite`, whose compose project is always `osprey-local-lite`, and
cleans up with `docker compose ... down -v`. That project name is host-wide: on a machine where the
owner's own deployment runs, the test's `up` takes it over and its `down -v` deletes every volume,
the cases, the graph and the analytics store with them. That happened, through `make test`.

So a test that brings up or tears down a project first calls `refuse_to_touch_a_real_deployment`:
if any container **or volume** of that project exists before the test starts (a stopped deployment
still holds its data in its volumes), the test is skipped, naming what is there, and touches
nothing. Run those tests on a machine with no deployment, or after the owner has removed it.

`teardowns_that_do_not_ask` is the check that every `down -v` in the test tree asks first
(`test_deployment_guard.py`). The one file allowed not to is `test_restore_exit_test.py`: it
destroys a deployment by design, and only the one its operator names in `OSPREY_TEST_COMPOSE_FILE`.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

LOCAL_LITE_PROJECT = "osprey-local-lite"

#: Destroys the deployment it is pointed at, by design, and only one named by its operator.
DESTROYS_BY_DESIGN = frozenset({"test_restore_exit_test.py"})

#: Assert the argv `ospreyflow uninstall` would run, through the command's fake runner, and never
#: run a process (ADR-114 Amendment 3). Passed only while the file never asks for the real runner:
#: the moment it does, the scan treats it like any other teardown.
FAKE_RUNNER_ONLY = frozenset({"test_uninstall.py"})

_THIS_FILE_AND_ITS_TEST = frozenset({"deployment_guard.py", "test_deployment_guard.py"})


class DeploymentPresent(Exception):
    """A deployment of this project name exists, so a test must not touch it."""


def deployment_resources(
    project: str,
    *,
    run: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    refuse: bool = False,
) -> tuple[list[str], list[str]]:
    """The containers and volumes labelled with `project`; with `refuse`, raises if there are any.
    No Docker on this machine means no deployment there to lose."""
    # Looked up when called, not bound as a default, so a test's stand-in for it is the one used.
    run = run or subprocess.run
    label = f"label=com.docker.compose.project={project}"
    found: list[list[str]] = []
    for args in (
        ["docker", "ps", "-aq", "--filter", label],
        ["docker", "volume", "ls", "-q", "--filter", label],
    ):
        try:
            result = run(args, capture_output=True, text=True, timeout=30, check=True)
        except FileNotFoundError:
            return [], []
        found.append([line for line in result.stdout.splitlines() if line.strip()])
    containers, volumes = found
    if refuse and (containers or volumes):
        raise DeploymentPresent(
            f"a deployment named {project!r} already exists here "
            f"({len(containers)} container(s), {len(volumes)} volume(s))"
        )
    return containers, volumes


def refuse_to_touch_a_real_deployment(project: str = LOCAL_LITE_PROJECT) -> None:
    """Skips the calling test if `project` already exists on this machine."""
    try:
        deployment_resources(project, refuse=True)
    except DeploymentPresent as present:
        pytest.skip(
            f"{present}: this test brings that project up and tears it down with its volumes, "
            "so it would delete it. Run it where no such deployment exists."
        )


_DOWN = re.compile(r'"down"')
_VOLUMES = re.compile(r'"-v"')


def teardowns_that_do_not_ask(tests_root: Path) -> list[str]:
    """Test files that run `docker compose ... down -v` without asking first, relative to
    `tests_root`, sorted."""
    offenders: list[str] = []
    for path in sorted(tests_root.rglob("*.py")):
        if path.name in _THIS_FILE_AND_ITS_TEST or path.name in DESTROYS_BY_DESIGN:
            continue
        text = path.read_text(encoding="utf-8")
        if path.name in FAKE_RUNNER_ONLY and "use_real_runner" not in text:
            continue
        if (
            _DOWN.search(text)
            and _VOLUMES.search(text)
            and "refuse_to_touch_a_real_deployment(" not in text
        ):
            offenders.append(path.relative_to(tests_root).as_posix())
    return offenders
