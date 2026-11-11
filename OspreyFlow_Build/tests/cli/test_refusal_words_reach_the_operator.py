"""Refresh's and update's refusals reach the operator through the CLI's `Redactor` (CARRIES; the
orchestrator's review of c5209b1, item 2; ADR-114 Amendment 39).

The CLI streams every child's output through `run.Redactor`, which hides any line naming
`password|secret|token`. Refresh's refusals name the variables Compose requires
(`OSPREY_POSTGRES_PASSWORD`, `OSPREY_LITELLM_SALT_SECRET`) and Amendment 39's own words said "it keeps
every secret", so `ospreyflow start --build` and `ospreyflow update` showed the operator only
"[a line naming a secret was hidden]" where the route out should have been.

Each case runs the real child (`python -m scripts.refresh`, or `harness.update`'s own printed lines)
through the real `SubprocessRunner` and `Redactor` main.py builds, and asserts the route is shown.
The child's `PATH` holds only Python's own folder, so a refusal that did not fire could not reach
Docker. `test_a_value_is_still_hidden_...` holds the other side: a line that holds a value stays
hidden, whatever it begins with.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from harness import update
from ospreyflow.run import Redactor, SubprocessRunner
from scripts import refresh

from tests.harness.test_update_apply import _Host, _update
from tests.test_refresh_before_the_gateway import (  # noqa: F401 - the fixture, by its name
    _after_the_gateway_database,
    deployment,
)

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
HIDDEN = "a line naming a secret was hidden"


def _child_env(directory: Path) -> dict[str, str]:
    return {
        refresh.DEPLOYMENT_DIR_VARIABLE: str(directory),
        "PYTHONPATH": os.pathsep.join([str(CORE), str(CORE / "packages")]),
        "PATH": str(Path(sys.executable).parent),  # no docker to reach
    }


def _start_build(directory: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    """What `ospreyflow start --build` runs (main.py `_start`), through what main.py runs it with."""
    runner = SubprocessRunner(Redactor(directory / "deployment.env"))
    code = runner(
        [sys.executable, "-m", "scripts.refresh"], env=_child_env(directory), cwd=CORE
    )
    return code, capsys.readouterr().out


def test_start_build_shows_the_gateway_database_refusal(
    deployment: Path,  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, said = _start_build(deployment, capsys)
    assert code == 1
    assert HIDDEN not in said, said
    assert "ospreyflow backup --name osprey-upg" in said
    assert "ospreyflow apply --name osprey-upg" in said


def test_start_build_shows_the_unset_required_refusal_naming_the_variable(
    deployment: Path,  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    _after_the_gateway_database(deployment)
    env = deployment / "deployment.env"
    env.write_text(
        "".join(
            line + "\n"
            for line in env.read_text(encoding="utf-8").splitlines()
            if not line.startswith("OSPREY_POSTGRES_PASSWORD=")
        ),
        encoding="utf-8",
    )
    code, said = _start_build(deployment, capsys)
    assert code == 1
    assert HIDDEN not in said, said
    assert "requires OSPREY_POSTGRES_PASSWORD, which deployment.env does not hold" in said
    assert "ospreyflow apply --name osprey-upg" in said
    assert "held-" not in said  # names, never a value


def test_update_shows_the_files_step_s_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`ospreyflow update` runs `harness.update`, through the same runner (main.py's `update`
    branch). Its files step fails with the last line refresh prints; update's own lines (the
    failure and the rollback) are replayed by a child through the runner as update printed them."""
    fake = _Host(tmp_path)
    words = "refresh: " + refresh.before_the_gateway_database(fake.directory)

    def refused() -> dict[str, bool]:
        raise update.UpdateFailed("bring the files up to date", words)

    fake.files_up_to_date = refused  # type: ignore[method-assign]
    assert _update(fake) == 1
    printed = capsys.readouterr()
    lines = tmp_path / "update-said.txt"
    lines.write_text(printed.out + printed.err, encoding="utf-8")
    runner = SubprocessRunner(Redactor(fake.directory / "deployment.env"))
    runner(
        [sys.executable, "-c", f"print(open({str(lines)!r}, encoding='utf-8').read())"],
        env={"PATH": str(Path(sys.executable).parent)},
    )
    said = capsys.readouterr().out
    assert "failed at 'bring the files up to date'" in said
    assert HIDDEN not in said.split("failed at")[1].splitlines()[0], said
    assert "ospreyflow apply" in said


@pytest.mark.parametrize(
    "line",
    [
        "refresh: OSPREY_POSTGRES_PASSWORD=hunter2",
        "refresh: OSPREY_POSTGRES_PASSWORD: hunter2",
        "ospreyflow: {'OSPREY_POSTGRES_PASSWORD': 'hunter2'}",
        'ospreyflow: "OSPREY_POSTGRES_PASSWORD": "hunter2"',
        "ospreyflow: OSPREY_POSTGRES_PASSWORD hunter2",
        "refresh: the admin password is hunter2",
        "OSPREY_POSTGRES_PASSWORD, which deployment.env does not hold",  # not our own words
        "postgres  | password authentication failed for user osprey",
    ],
)
def test_a_value_is_still_hidden_whatever_the_line_begins_with(line: str) -> None:
    assert HIDDEN in Redactor("deployment.env")(line)


@pytest.mark.parametrize(
    "line",
    [
        "refresh: This checkout's compose file requires OSPREY_POSTGRES_PASSWORD, "
        "OSPREY_LITELLM_SALT_SECRET, which deployment.env does not hold, so nothing was changed.",
        "ospreyflow: the update to v0.5.0 failed at 'bring the files up to date': refresh: "
        "requires OSPREY_LITELLM_DB_PASSWORD, which deployment.env does not hold.",
    ],
)
def test_our_own_refusal_naming_a_variable_is_shown(line: str) -> None:
    assert Redactor("deployment.env")(line) == line
