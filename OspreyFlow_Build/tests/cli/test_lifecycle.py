"""`start`, `stop`, `status`, `open`, `logs`, `backup`, `restore` (ADR-114 Amendment 3 decision 4):
Compose driven against the rendered deployment, status in words.

What a mistake would do, and the case that catches it:
- Compose run without the deployment's env file, so every service loses its settings —
  `test_start_and_stop_drive_compose_with_the_deployments_env_file`;
- `start --build` not doing what `make refresh` did — `test_start_build_runs_refresh`;
- a stopped or unhealthy service reported as fine —
  `test_status_says_each_service_in_words_and_exits_nonzero_unless_all_are_up`;
- a command run against a deployment that does not exist —
  `test_nothing_installed_is_refused_in_words`;
- the `--start` spelling not working — `test_the_dashed_spelling_is_an_alias`;
- logs losing its service, follow or tail — `test_logs_passes_service_follow_and_tail`;
- backup and restore not reaching the harness from the product folder —
  `test_backup_and_restore_pass_through_to_the_harness`;
- `open` opening the wrong address — `test_open_opens_the_configured_address`.
"""

from __future__ import annotations

import json

import pytest

from .conftest import Rig


def _compose(rig: Rig) -> list[str]:
    return [
        "docker", "compose",
        "--env-file", str(rig.deployment / "deployment.env"),
        "-f", str(rig.deployment / "compose.yaml"),
    ]  # fmt: skip


def _ps(*rows: tuple[str, str, str]) -> str:
    return "\n".join(
        json.dumps({"Service": s, "State": state, "Health": health}) for s, state, health in rows
    )


def test_start_and_stop_drive_compose_with_the_deployments_env_file(rig: Rig) -> None:
    rig.install_deployment()
    assert rig("start") == 0
    assert rig("stop") == 0
    assert rig.runner.argvs() == [
        [*_compose(rig), "up", "-d", "--wait"],
        [*_compose(rig), "stop"],
    ]


def test_start_build_runs_refresh(rig: Rig) -> None:
    rig.install_deployment()
    assert rig("start", "--build") == 0
    (call,) = rig.runner.calls
    assert call.argv == [str(rig.product / ".venv" / "bin" / "python"), "-m", "scripts.refresh"]
    assert call.cwd == rig.product


def test_nothing_installed_is_refused_in_words(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    for verb in ("start", "stop", "status", "logs", "uninstall"):
        assert rig(verb) == 1, verb
        assert "Nothing is installed here yet" in capsys.readouterr().err
    assert rig.runner.calls == []


def test_status_says_each_service_in_words_and_exits_nonzero_unless_all_are_up(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.install_deployment()
    rig.ps_output = _ps(("glass", "running", "healthy"), ("graph", "running", ""))
    assert rig("status") == 0
    out = capsys.readouterr().out
    assert "glass: running, healthy" in out
    assert "graph: running" in out and "graph: running," not in out

    rig.ps_output = _ps(("glass", "running", "healthy"), ("api", "running", "unhealthy"))
    assert rig("status") == 1
    assert "api: running, unhealthy" in capsys.readouterr().out

    rig.ps_output = _ps(("glass", "running", "healthy"), ("search", "exited", ""))
    assert rig("status") == 1
    assert "search: exited" in capsys.readouterr().out

    rig.ps_output = _ps(("api", "running", "starting"))
    assert rig("status") == 1

    rig.ps_output = ""
    assert rig("status") == 1  # nothing running is not "all up"


def test_status_reads_the_json_array_older_compose_prints(rig: Rig) -> None:
    rig.install_deployment()
    rig.ps_output = json.dumps([{"Service": "glass", "State": "running", "Health": "healthy"}])
    assert rig("status") == 0


def test_the_dashed_spelling_is_an_alias(rig: Rig) -> None:
    rig.install_deployment()
    assert rig("--start") == 0
    assert rig("--stop") == 0
    assert rig.runner.argvs() == [
        [*_compose(rig), "up", "-d", "--wait"],
        [*_compose(rig), "stop"],
    ]


def test_logs_passes_service_follow_and_tail(rig: Rig) -> None:
    rig.install_deployment()
    assert rig("logs") == 0
    assert rig("logs", "api", "--follow", "--tail", "50") == 0
    assert rig.runner.argvs() == [
        [*_compose(rig), "logs", "--tail", "200"],
        [*_compose(rig), "logs", "--follow", "--tail", "50", "api"],
    ]


def test_open_opens_the_configured_address(rig: Rig) -> None:
    assert rig("open") == 0
    assert rig.opened == ["http://localhost:8080"]


def test_backup_and_restore_pass_through_to_the_harness(rig: Rig) -> None:
    python = str(rig.product / ".venv" / "bin" / "python")
    assert rig("backup", "--profile", "local-lite") == 0
    assert rig("restore", "/tmp/x", "--yes") == 0
    first, second = rig.runner.calls
    assert first.argv == [python, "-m", "harness.backup", "--profile", "local-lite"]
    assert second.argv == [python, "-m", "harness.restore", "/tmp/x", "--yes"]
    assert first.cwd == second.cwd == rig.product
