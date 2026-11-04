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
- `open` opening the wrong address — `test_open_opens_the_configured_address`;
- `start` or `switch` bringing the stack up before the Conduit's upload folder is its own (ADR-114
  Amendment 33, found on the first server, 4 November 2026), or bringing it up when that failed —
  `test_start_and_stop_drive_compose_with_the_deployments_env_file`,
  `test_switch_with_nothing_else_running_only_starts_this_one`,
  `test_a_start_whose_upload_folder_cannot_be_prepared_brings_nothing_up` (the step itself:
  `tests/harness/test_ingest_uploads.py`);
- a step that cannot import the checkout's own packages (`schemas`, `ports`) — found running
  `ospreyflow backup` on the owner's machine for B2e, where it failed at its first import; every
  test until then had a fake runner, and every live run a shell with `PYTHONPATH` already set —
  `test_every_python_step_can_import_the_checkouts_packages`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from .conftest import Rig


def _compose(rig: Rig) -> list[str]:
    return [
        "docker", "compose",
        "--env-file", str(rig.deployment / "deployment.env"),
        "-f", str(rig.deployment / "compose.yaml"),
    ]  # fmt: skip


def _uploads(rig: Rig) -> list[str]:
    """The step before every `up`: the Conduit's upload folder made its own."""
    python = str(rig.product / ".venv" / "bin" / "python")
    return [python, "-m", "harness.ingest_uploads", str(rig.deployment / "compose.yaml")]


def _ps(*rows: tuple[str, str, str]) -> str:
    return "\n".join(
        json.dumps({"Service": s, "State": state, "Health": health}) for s, state, health in rows
    )


def test_start_and_stop_drive_compose_with_the_deployments_env_file(rig: Rig) -> None:
    rig.install_deployment()
    assert rig("start") == 0
    assert rig("stop") == 0
    assert rig.runner.argvs() == [
        _uploads(rig),
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
        _uploads(rig),
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
    assert rig.opened == ["http://ospreyflow.localhost"]


def test_backup_and_restore_pass_through_to_the_harness(rig: Rig) -> None:
    python = str(rig.product / ".venv" / "bin" / "python")
    assert rig("backup", "--profile", "local-lite") == 0
    assert rig("restore", "/tmp/x", "--yes") == 0
    first, second = rig.runner.calls
    assert first.argv == [python, "-m", "harness.backup", "--profile", "local-lite"]
    assert second.argv == [python, "-m", "harness.restore", "/tmp/x", "--yes"]
    assert first.cwd == second.cwd == rig.product


def test_update_passes_through_to_the_harness_naming_the_deployment(rig: Rig) -> None:
    """ADR-114 Amendment 8: `update` is the checkout's `harness.update`, told which deployment."""
    rig.install_deployment()
    python = str(rig.product / ".venv" / "bin" / "python")
    assert rig("update", "--check") == 0
    (call,) = rig.runner.calls
    assert call.argv == [
        python, "-m", "harness.update", "--deployment", str(rig.deployment), "--check",
    ]  # fmt: skip
    assert call.cwd == rig.product


def test_update_with_nothing_installed_is_refused_in_words(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rig("update", "--check") == 1
    assert "Nothing is installed here yet" in capsys.readouterr().err
    assert rig.runner.calls == []


def test_every_python_step_can_import_the_checkouts_packages(rig: Rig) -> None:
    rig.install_deployment()
    assert rig("backup") == 0
    assert rig("restore", "/tmp/x") == 0
    assert rig("start", "--build") == 0
    assert rig("demo", "list") == 0
    assert rig("install", "--mode", "lite", "--yes", "--force") == 0
    python = str(rig.product / ".venv" / "bin" / "python")
    stepped = [call for call in rig.runner.calls if call.argv[0] == python]
    assert len(stepped) >= 6, [call.argv for call in rig.runner.calls]
    wanted = {str(rig.product), str(rig.product / "packages")}
    for call in stepped:
        assert call.env is not None, call.argv
        assert wanted <= set(call.env["PYTHONPATH"].split(os.pathsep)), call.argv
    assert rig.capture_envs and all(
        env is not None and wanted <= set(env["PYTHONPATH"].split(os.pathsep))
        for env in rig.capture_envs
    )


def test_a_one_shot_step_that_finished_is_not_a_fault(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    """Seen on the owner's deployment, 13 October 2026: `status` exited 1 on a healthy deployment
    because its one-shot steps (Keycloak's database step, the speech model download) had exited —
    which is what they are for. A step rendered `restart: "no"` that exited 0 is *finished*; one that
    exited otherwise is a fault; and a long-running service that exited is a fault however it
    exited (after `ospreyflow stop`, every service exits 0)."""
    rig.install_deployment()
    (rig.deployment / "compose.yaml").write_text(
        "services:\n  glass: {restart: unless-stopped}\n  keycloak-db: {restart: 'no'}\n",
        encoding="utf-8",
    )

    def ps(*rows: tuple[str, str, int]) -> str:
        return "\n".join(json.dumps({"Service": s, "State": state, "Health": "", "ExitCode": code})
                         for s, state, code in rows)  # fmt: skip

    rig.ps_output = ps(("glass", "running", 0), ("keycloak-db", "exited", 0))
    assert rig("status") == 0
    assert "keycloak-db: finished" in capsys.readouterr().out
    rig.ps_output = ps(("glass", "running", 0), ("keycloak-db", "exited", 3))
    assert rig("status") == 1
    assert "keycloak-db: exited (code 3)" in capsys.readouterr().out
    rig.ps_output = ps(("glass", "exited", 0), ("keycloak-db", "exited", 0))
    assert rig("status") == 1


# --- switch: one deployment running at a time on one machine (ADR-132 Amendment 3) -------------


def _other_deployment(root: Path, name: str) -> Path:
    """Another product folder on the same machine, with a rendered deployment."""
    (root / "harness").mkdir(parents=True)
    (root / "harness" / "__init__.py").write_text("", encoding="utf-8")
    (root / "osprey.yaml").write_text("{}\n", encoding="utf-8")
    deployment = root / "deploy" / "generated" / name
    deployment.mkdir(parents=True)
    (deployment / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (deployment / "deployment.env").write_text("X=1\n", encoding="utf-8")
    return deployment


def _ls(*rows: tuple[str, str, Path]) -> str:
    return json.dumps([{"Name": n, "Status": s, "ConfigFiles": str(f)} for n, s, f in rows])


def test_switch_stops_the_other_running_deployment_then_starts_and_opens_this_one(
    rig: Rig, tmp_path: Path
) -> None:
    """Found running two Lite deployments on one machine (ADR-132 Amendment 1): Docker had the
    memory for one, and switching meant three commands with `OSPREYFLOW_HOME` set by hand. A project
    that is not an OspreyFlow deployment is never touched."""
    rig.install_deployment()
    other = _other_deployment(tmp_path / "second", "osprey-govuk")
    unrelated = tmp_path / "elsewhere" / "docker-compose.yml"
    rig.responses["ls"] = [
        (0, _ls(
            ("osprey-govuk", "running(16)", other / "compose.yaml"),
            ("osprey-local-lite", "exited(18)", rig.deployment / "compose.yaml"),
            ("noggin-mac", "running(2)", unrelated),
        ))  # fmt: skip
    ]

    assert rig("switch") == 0

    other_compose = [
        "docker", "compose",
        "--env-file", str(other / "deployment.env"),
        "-f", str(other / "compose.yaml"),
    ]  # fmt: skip
    assert rig.runner.argvs() == [
        [*other_compose, "stop"],
        _uploads(rig),
        [*_compose(rig), "up", "-d", "--wait"],
    ]
    assert rig.opened == ["http://ospreyflow.localhost"]


def test_switch_with_nothing_else_running_only_starts_this_one(rig: Rig) -> None:
    rig.install_deployment()
    own = ("osprey-local-lite", "exited(18)", rig.deployment / "compose.yaml")
    rig.responses["ls"] = [(0, _ls(own))]
    assert rig("switch") == 0
    assert rig.runner.argvs() == [_uploads(rig), [*_compose(rig), "up", "-d", "--wait"]]


def test_a_start_whose_upload_folder_cannot_be_prepared_brings_nothing_up(rig: Rig) -> None:
    rig.install_deployment()
    rig.runner.fail["harness.ingest_uploads"] = 1
    assert rig("start") != 0
    assert rig.runner.argvs() == [_uploads(rig)]


def test_switch_list_names_each_deployment_its_state_and_address(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.install_deployment()
    other = _other_deployment(tmp_path / "second", "osprey-govuk")
    rig.responses["ls"] = [
        (0, _ls(
            ("osprey-govuk", "running(16)", other / "compose.yaml"),
            ("osprey-local-lite", "exited(18)", rig.deployment / "compose.yaml"),
            ("noggin-mac", "running(2)", tmp_path / "elsewhere" / "docker-compose.yml"),
        ))  # fmt: skip
    ]
    assert rig("switch", "--list") == 0
    said = capsys.readouterr().out
    assert "osprey-govuk: running" in said and str(tmp_path / "second") in said
    assert "osprey-local-lite: stopped (this one)" in said
    assert "noggin" not in said
    assert rig.runner.argvs() == []
