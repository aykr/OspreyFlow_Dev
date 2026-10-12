"""A test never takes over or tears down a deployment it did not start — the 5 October 2026 loss.

`test_apply_env.py` brought up `osprey-local-lite` and then ran `docker compose -p
osprey-local-lite down -v`: the project name every local-lite render carries, the owner's real
deployment's included. Run as part of `make test` on the owner's machine it deleted that
deployment's containers and every volume: all the cases, the graph and the analytics store. What a
mistake would do, and the case that catches it:

- a test that tears down a project which already has containers, or only volumes (a stopped
  deployment still holds its data in them): `test_a_deployment_with_*_is_refused`;
- a new file that runs `down -v` without asking first:
  `test_every_teardown_in_the_tests_asks_first`,
  a scan of the test tree, shown red against a planted file.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.harness.deployment_guard import (
    DeploymentPresent,
    deployment_resources,
    refuse_to_touch_a_real_deployment,
    teardowns_that_do_not_ask,
)


def _docker(containers: str = "", volumes: str = ""):  # type: ignore[no-untyped-def]
    """Answers `docker ps -aq` and `docker volume ls -q` as the real CLI does: one id per line."""
    calls: list[list[str]] = []

    def run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        out = containers if args[1] == "ps" else volumes
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

    return run, calls


def test_a_deployment_with_containers_is_refused() -> None:
    run, calls = _docker(containers="3f2a9c1e5b7d\n8e4a9c21aa10\n")
    with pytest.raises(DeploymentPresent) as refused:
        deployment_resources("osprey-local-lite", run=run, refuse=True)
    assert "osprey-local-lite" in str(refused.value) and "2 container" in str(refused.value)
    assert all("label=com.docker.compose.project=osprey-local-lite" in a for a in calls)


def test_a_deployment_with_only_volumes_is_refused() -> None:
    """Stopped, its data is still in its volumes, and `down -v` deletes them."""
    run, _ = _docker(volumes="osprey-local-lite_osprey-data\n")
    with pytest.raises(DeploymentPresent) as refused:
        deployment_resources("osprey-local-lite", run=run, refuse=True)
    assert "1 volume" in str(refused.value)


def test_nothing_of_that_name_lets_the_test_run() -> None:
    run, _ = _docker()
    assert deployment_resources("osprey-local-lite", run=run, refuse=True) == ([], [])


def test_no_docker_means_no_deployment_to_lose() -> None:
    def run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("docker")

    assert deployment_resources("osprey-local-lite", run=run, refuse=True) == ([], [])


def test_the_refusal_skips_the_test_and_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    run, _ = _docker(containers="3f2a9c1e5b7d\n")
    monkeypatch.setattr("tests.harness.deployment_guard.subprocess.run", run)
    with pytest.raises(pytest.skip.Exception) as skipped:
        refuse_to_touch_a_real_deployment("osprey-local-lite")
    assert "would delete it" in str(skipped.value)


def test_every_teardown_in_the_tests_asks_first() -> None:
    tests_root = Path(__file__).resolve().parents[1]
    assert teardowns_that_do_not_ask(tests_root) == []


def test_the_scan_finds_a_teardown_that_does_not_ask(tmp_path: Path) -> None:
    """Shown red against the shape the real files use: the arguments one per line."""
    (tmp_path / "test_planted.py").write_text(
        'subprocess.run(\n    ["docker", "compose", "-p", PROJECT,\n     "down",\n     "-v"],\n)\n',
        encoding="utf-8",
    )
    (tmp_path / "test_asks.py").write_text(
        "refuse_to_touch_a_real_deployment(PROJECT)\n"
        'subprocess.run(["docker", "compose", "down", "-v"])\n',
        encoding="utf-8",
    )
    assert teardowns_that_do_not_ask(tmp_path) == ["test_planted.py"]


def test_an_argv_only_file_passes_only_while_it_never_asks_for_a_real_runner(tmp_path: Path) -> None:
    """`ospreyflow uninstall`'s own test asserts `down -v` as an argv through a fake runner; the
    moment that file reaches for the real runner, it is a teardown like any other."""
    folder = tmp_path / "cli"
    folder.mkdir()
    fake = 'assert rig.runner.argvs() == [[*_compose(rig), "down", "-v"]]\n'
    (folder / "test_uninstall.py").write_text(fake, encoding="utf-8")
    assert teardowns_that_do_not_ask(tmp_path) == []
    (folder / "test_uninstall.py").write_text("rig.use_real_runner = True\n" + fake, encoding="utf-8")
    assert teardowns_that_do_not_ask(tmp_path) == ["cli/test_uninstall.py"]
