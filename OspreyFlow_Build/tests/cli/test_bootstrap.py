"""The bootstrap (`install.sh`, `install.ps1`) and the command's package metadata (ADR-114
decision 2; Amendment 3 decision 3).

What a mistake would do, and the case that catches it:
- a shell script that does not even parse — `test_install_sh_parses`;
- a bootstrap that installs the command somewhere the command cannot find its checkout again, or
  not at all — `test_both_scripts_install_the_tool_and_record_the_home_file`;
- a bootstrap that clones from nowhere without saying so —
  `test_both_scripts_refuse_in_words_without_a_repository`;
- the package declaring the wrong entry point or a dependency beyond PyYAML —
  `test_the_package_is_the_small_command_the_decision_describes`;
- the Python and the Windows scripts disagreeing on where the home file lives —
  `test_both_scripts_agree_with_the_command_on_the_home_file`;
- a second run of a bootstrap leaving the first run's recorded folder in place, so a reinstall or a
  repoint goes stale and the command follows the old one (ADR-114 Amendment 50 decision 2; the
  command says so when the recorded folder wins, but it is only true that a reinstall fixes it if
  the script overwrites) — `test_both_scripts_record_the_folder_they_install_on_every_run`;
- the bootstrap stripping what a checkout already has installed — found running it on the owner's
  developer checkout for B2e: a plain `uv sync` uninstalled the `extraction` extra (spaCy, torch,
  deepparse and their dependencies) and left their folders behind as broken namespace packages —
  `test_the_bootstrap_never_removes_installed_packages`.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest
import tomllib
from tools.layout import CORE


def test_install_sh_parses() -> None:
    sh = shutil.which("sh")
    if sh is None:
        pytest.skip("no sh on this machine")
    done = subprocess.run(
        [sh, "-n", str(CORE / "install.sh")], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr


def test_both_scripts_install_the_tool_and_record_the_home_file() -> None:
    for name in ("install.sh", "install.ps1"):
        text = (CORE / name).read_text(encoding="utf-8")
        assert "uv tool install" in text, name
        assert "ospreyflow/home" in text.replace("\\", "/"), name
        assert "uv sync" in text, name
        assert "ospreyflow doctor" in text and "ospreyflow install --mode lite" in text, name


def test_both_scripts_record_the_folder_they_install_on_every_run() -> None:
    """The record is written by a plain overwrite of the folder the script just installed, with no
    test of what was there: not appended, not written only when absent. Read from the scripts' own
    text, as the neighbouring cases are (neither can be run here: they install `uv` and a tool)."""
    sh = (CORE / "install.sh").read_text(encoding="utf-8").splitlines()
    (written,) = [i for i, line in enumerate(sh) if "$home_file" in line and ">" in line]
    assert sh[written].strip() == "printf '%s\\n' \"$product\" > \"$home_file\""  # one `>`, not `>>`
    start = next(i for i, line in enumerate(sh) if line.startswith("# 4."))
    between = [line.strip() for line in sh[start:written] if line.strip()]
    assert not [line for line in between if line.startswith(("if ", "[ ", "test ", "case "))], between
    assert 'uv tool install --editable "$product/cli"' in sh  # the folder it installs is `$product`

    ps = (CORE / "install.ps1").read_text(encoding="utf-8").splitlines()
    (written,) = [i for i, line in enumerate(ps) if "$homeFile" in line and "Content" in line]
    assert ps[written].strip() == "Set-Content -Path $homeFile -Value $product -Encoding utf8"
    start = next(i for i, line in enumerate(ps) if line.startswith("# 4."))
    between = [line.strip() for line in ps[start:written] if line.strip()]
    assert not [line for line in between if line.startswith(("if ", "if(", "} else"))], between
    assert "uv tool install --editable (Join-Path $product \"cli\")" in ps


def test_the_bootstrap_never_removes_installed_packages() -> None:
    for name in ("install.sh", "install.ps1"):
        lines = [
            line for line in (CORE / name).read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("uv sync")
        ]  # fmt: skip
        assert lines, name
        assert all("--inexact" in line.split() for line in lines), (name, lines)


def test_both_scripts_refuse_in_words_without_a_repository() -> None:
    for name in ("install.sh", "install.ps1"):
        text = (CORE / name).read_text(encoding="utf-8")
        assert "OSPREYFLOW_REPO" in text, name
        assert "set OSPREYFLOW_REPO" in text or "Set OSPREYFLOW_REPO" in text, name


def test_both_scripts_agree_with_the_command_on_the_home_file() -> None:
    from ospreyflow.home import HOME_FILE_PARTS

    assert HOME_FILE_PARTS == ("ospreyflow", "home")
    sh = (CORE / "install.sh").read_text(encoding="utf-8")
    assert ".config" in sh and "ospreyflow/home" in sh
    assert "APPDATA" in (CORE / "install.ps1").read_text(encoding="utf-8")


def test_the_package_is_the_small_command_the_decision_describes() -> None:
    meta = tomllib.loads((CORE / "cli" / "pyproject.toml").read_text(encoding="utf-8"))
    project = meta["project"]
    assert project["name"] == "ospreyflow-cli"
    assert project["scripts"] == {"ospreyflow": "ospreyflow.main:main"}
    assert [d.split(">")[0].lower() for d in project["dependencies"]] == ["pyyaml"]
    assert meta["build-system"]["build-backend"] == "hatchling.build"
    assert meta["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["ospreyflow"]
