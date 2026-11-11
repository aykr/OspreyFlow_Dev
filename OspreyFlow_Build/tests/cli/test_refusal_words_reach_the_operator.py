"""Refresh's and update's refusals reach the operator through the CLI's `Redactor` (CARRIES; the
orchestrator's review of c5209b1, item 2; ADR-114 Amendment 39).

The CLI streams every child's output through `run.Redactor`, which hides any line naming
`password|secret|token`. Refresh's refusals name the variables Compose requires
(`OSPREY_POSTGRES_PASSWORD`, `OSPREY_LITELLM_SALT_SECRET`) and Amendment 39's own words said "it
keeps every secret", so `ospreyflow start --build` and `ospreyflow update` showed the operator only
"[a line naming a secret was hidden]" where the route out should have been.

Each case runs the real child (`python -m scripts.refresh`, or `harness.update`'s own printed lines)
through the real `SubprocessRunner` and `Redactor` main.py builds, and asserts the route is shown.
The child's `PATH` is a folder holding only a link to Python (Python's own folder may hold `docker`
too, as Homebrew's does), so a refusal that did not fire could not reach Docker.
`test_a_value_is_still_hidden_...` holds the other side: a line that holds a value stays hidden,
whatever it begins with.
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


def _no_docker(directory: Path) -> str:
    """A `PATH` with Python alone on it."""
    folder = directory.parent / "python-only"
    folder.mkdir(exist_ok=True)
    if not (folder / "python").exists():
        (folder / "python").symlink_to(sys.executable)
    return str(folder)


def _child_env(directory: Path) -> dict[str, str]:
    return {
        refresh.DEPLOYMENT_DIR_VARIABLE: str(directory),
        "PYTHONPATH": os.pathsep.join([str(CORE), str(CORE / "packages")]),
        "PATH": _no_docker(directory),
    }


def _without(folder: Path, name: str) -> None:
    env = folder / "deployment.env"
    env.write_text(
        "".join(
            line + "\n"
            for line in env.read_text(encoding="utf-8").splitlines()
            if not line.startswith(f"{name}=")
        ),
        encoding="utf-8",
    )


def _start_build(directory: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    """What `ospreyflow start --build` runs (main.py `_start`), through what main.py runs it
    with."""
    runner = SubprocessRunner(Redactor(directory / "deployment.env"))
    code = runner([sys.executable, "-m", "scripts.refresh"], env=_child_env(directory), cwd=CORE)
    return code, capsys.readouterr().out


def test_start_build_shows_the_gateway_database_refusal_reworded(
    deployment: Path,  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Names no variable: shown since its words no longer say "every secret" (the reword alone;
    the redactor's own branch is held by the cases naming a variable)."""
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
    _without(deployment, "OSPREY_POSTGRES_PASSWORD")
    code, said = _start_build(deployment, capsys)
    assert code == 1
    assert HIDDEN not in said, said
    assert "requires OSPREY_POSTGRES_PASSWORD, which deployment.env does not hold" in said
    assert "ospreyflow apply --name osprey-upg" in said
    assert "held-" not in said  # names, never a value


def test_update_shows_the_files_step_s_refusal_naming_the_variable(
    deployment: Path,  # noqa: F811
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`ospreyflow update` runs `harness.update` through the same runner (main.py's `update`
    branch). Its files step is the real `--files-only` child on a deployment missing
    `OSPREY_POSTGRES_PASSWORD`, its failure read as update reads it (`_ok_real`); update's own
    printed lines (the failure and the rollback) are replayed by a child through the runner."""
    _after_the_gateway_database(deployment)
    _without(deployment, "OSPREY_POSTGRES_PASSWORD")
    code, child_said = update._subprocess(
        [sys.executable, "-m", "scripts.refresh", "--files-only"],
        cwd=CORE,
        env={**os.environ, **_child_env(deployment)},
    )
    assert code == 1
    with pytest.raises(update.UpdateFailed) as failed:
        update._ok_real(lambda _argv: (code, child_said), [], "bring the files up to date")
    refused = failed.value
    assert "OSPREY_POSTGRES_PASSWORD" in refused.why

    fake = _Host(tmp_path)

    def files_step() -> dict[str, bool]:
        raise refused

    fake.files_up_to_date = files_step  # type: ignore[method-assign]
    assert _update(fake) == 1
    printed = capsys.readouterr()
    lines = tmp_path / "update-said.txt"
    lines.write_text(printed.out + printed.err, encoding="utf-8")
    runner = SubprocessRunner(Redactor(fake.directory / "deployment.env"))
    runner(
        [sys.executable, "-c", f"print(open({str(lines)!r}, encoding='utf-8').read())"],
        env={"PATH": _no_docker(deployment)},
    )
    said = capsys.readouterr().out
    failure = next(x for x in said.splitlines() if "failed at" in x)
    assert HIDDEN not in failure, said
    assert "requires OSPREY_POSTGRES_PASSWORD, which deployment.env does not hold" in failure
    assert "ospreyflow apply --name osprey-upg" in failure


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
        # A name in prose outside our two fixed phrases (my own lane review, item 4).
        "ospreyflow: OSPREY_POSTGRES_PASSWORD is hunter2",
        "ospreyflow: OSPREY_POSTGRES_PASSWORD, hunter2",
        "refresh: (OSPREY_X_SECRET) hunter2",
        "ospreyflow: the update to v0.5.0 failed at 'start the release': OSPREY_DB_PASSWORD was "
        "hunter2",
        # The orchestrator's review of ad4bef7, item 1: our phrase with a value after it, an
        # upper-case value inside the names list (a variable's name has an underscore), and our
        # whole sentence with a value after it.
        "refresh: requires OSPREY_X_PASSWORD, which deployment.env does not hold: hunter2",
        "refresh: This checkout's compose file requires OSPREY_POSTGRES_PASSWORD, HUNTER2, which "
        "deployment.env does not hold, so nothing was changed. Run `ospreyflow apply --name lab` "
        "with the checkout at the version you are moving to.",
        "refresh: This checkout's compose file requires OSPREY_POSTGRES_PASSWORD, which "
        "deployment.env does not hold, so nothing was changed. Run `ospreyflow apply --name lab` "
        "with the checkout at the version you are moving to. hunter2",
        "postgres  | password authentication failed for user osprey",
    ],
)
def test_a_value_is_still_hidden_whatever_the_line_begins_with(line: str) -> None:
    assert HIDDEN in Redactor("deployment.env")(line)


def _our_sentences(folder: Path) -> list[str]:
    """Refresh's own refusals as its `main` prints them, and as update reports its files step's
    (`refresh: …` as the failure's `why`), for a deployment at `folder`, the gateway's made by
    refresh's own function (`test_our_unset_refusal_is_refresh_s_own_words` holds the other)."""
    unset = (
        "This checkout's compose file requires OSPREY_POSTGRES_PASSWORD, OSPREY_LITELLM_SALT_SECRET"
        ", which deployment.env does not hold, so nothing was changed. Run `ospreyflow "
        f"apply{refresh._named(folder)}` with the checkout at the version you are moving to."
    )
    lines = [f"refresh: {x}" for x in (unset, refresh.before_the_gateway_database(folder))]
    update = "ospreyflow: the update to v0.5.0 failed at 'bring the files up to date': "
    return [*lines, *(update + x for x in lines)]


@pytest.mark.parametrize("name", ["osprey-upg", "secret-lab", "token-test-2"])
def test_our_own_refusal_naming_a_variable_is_shown(tmp_path: Path, name: str) -> None:
    """Shown only as our sentence in full: anchored, names alone, nothing after (the
    orchestrator's review of ad4bef7, item 1), whatever the deployment is called, `secret-lab`
    among them (its minor 7)."""
    folder = tmp_path / "deployments" / name
    for line in _our_sentences(folder):
        assert Redactor("deployment.env")(line) == line, line


def test_our_unset_refusal_is_refresh_s_own_words() -> None:
    """The unset sentence `_our_sentences` builds is the one refresh raises, held against its
    source, so the redactor's template and refresh's words cannot drift apart unseen."""
    source = Path(refresh.__file__).read_text(encoding="utf-8")
    said = '", which deployment.env does not hold, so nothing was changed. Run `ospreyflow "'
    assert said in source
    assert "apply{_named(directory)}` with the checkout at the version you are moving to." in source
